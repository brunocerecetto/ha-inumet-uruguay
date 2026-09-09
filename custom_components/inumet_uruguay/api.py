"""Client for the public data sources published by Inumet."""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone
from time import monotonic
from typing import Any
from urllib.parse import urljoin

import aiohttp

from .const import (
    BASE_URL,
    ESTACIONES_PATH,
    ESTADO_ACTUAL_PATH,
    ESTADO_ACTUAL_V2_PATH,
    FORECAST_PATH,
    GENERAL_ALERTS_PATH,
    INFO_RESOURCES_PATH,
    SPECIAL_ALERTS_PATH,
)

_LOGGER = logging.getLogger(__package__)

RESOURCE_CACHE_SECONDS = 6 * 60 * 60

DEFAULT_RESOURCES = {
    "estaciones": ESTACIONES_PATH,
    "estadoactual": ESTADO_ACTUAL_V2_PATH,
    "pronosticoV2": FORECAST_PATH,
    "nivelRiesgoV2": GENERAL_ALERTS_PATH,
}


class InumetApiError(Exception):
    """Raised when an Inumet resource cannot be read."""


def decode_json(text: str, source: str = "Inumet") -> dict[str, Any]:
    """Decode JSON without relying on the server's Content-Type header."""
    try:
        data = json.loads(text)
    except (TypeError, json.JSONDecodeError) as err:
        raise InumetApiError(f"Respuesta JSON inválida de {source}") from err

    if not isinstance(data, dict):
        raise InumetApiError(f"Formato inesperado recibido de {source}")
    return data


def _parse_inumet_datetime(value: Any) -> datetime | None:
    """Parse the local date format used by Inumet alert feeds."""
    if not isinstance(value, str) or not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def normalize_alerts(
    general: dict[str, Any] | None,
    special: dict[str, Any] | None,
    now: datetime,
) -> list[dict[str, Any]]:
    """Return active alerts from the two official Inumet feeds."""
    alerts: list[dict[str, Any]] = []
    now_comparable = now.replace(tzinfo=None)

    for source, payload in (("advertencia", general), ("aviso", special)):
        if not isinstance(payload, dict):
            continue
        items = payload.get("advertencias")
        if not isinstance(items, list):
            continue

        for index, item in enumerate(items):
            if not isinstance(item, dict):
                continue
            expires = _parse_inumet_datetime(item.get("finalizacion"))
            if expires is not None:
                expires_comparable = expires.replace(tzinfo=None)
                if expires_comparable < now_comparable:
                    continue

            risks = item.get("riesgoFenomeno")
            levels = (
                [value for value in risks.values() if isinstance(value, (int, float))]
                if isinstance(risks, dict)
                else []
            )
            max_level = int(max(levels, default=1))
            severity = {2: "amarilla", 3: "naranja", 4: "roja"}.get(
                max_level, "informativa"
            )

            alerts.append(
                {
                    "id": item.get("id", item.get("indice", f"{source}-{index}")),
                    "tipo": source,
                    "titulo": item.get("fenomeno"),
                    "severidad": severity,
                    "descripcion": item.get("descripcion"),
                    "areas_afectadas": item.get("zonas"),
                    "inicio": item.get("comienzo"),
                    "expira": item.get("finalizacion"),
                    "probabilidad": item.get("probabilidad"),
                }
            )

    return alerts


def normalize_current_conditions(
    current: dict[str, Any], station_catalog: dict[str, Any] | None
) -> dict[str, Any]:
    """Convert estadoActualV2 into the detailed observation matrix format."""
    raw_stations = current.get("estaciones", [])
    if not isinstance(raw_stations, list):
        raise InumetApiError("Formato inesperado en estadoActualV2")

    catalog_by_id = {}
    if isinstance(station_catalog, dict):
        catalog_by_id = {
            item.get("id"): item
            for item in station_catalog.get("estaciones", [])
            if isinstance(item, dict) and item.get("id") is not None
        }

    stations: list[dict[str, Any]] = []
    for raw in raw_stations:
        if not isinstance(raw, dict) or raw.get("id") is None:
            continue
        catalog = catalog_by_id.get(raw["id"], {})
        name = raw.get("estacion") or catalog.get("NombreEstacion") or str(raw["id"])
        stations.append(
            {
                "id": raw["id"],
                "idStr": catalog.get("idStr"),
                "nombre": name,
                "displayName": name,
                "displayNamePublic": name,
                "latitud": catalog.get("Latitud"),
                "longitud": catalog.get("Longitud"),
                "estado": catalog.get("estado"),
                "gerencia": "INUMET",
            }
        )

    variable_map = {
        "DirViento": "dirViento",
        "HumRelativa": "humedad",
        "IntRafaga": "intRafaga",
        "IntViento": "intViento",
        "PresAtmMar": "presion",
        "TempPtoRocio": "temperaturaPuntoRocio",
        "TempAire": "temperatura",
        "Visibilidad": "visibilidad",
    }
    variables = [{"idStr": key} for key in variable_map]
    observations = [
        {
            "datos": [
                [raw.get(source_key)]
                for raw in raw_stations
                if isinstance(raw, dict) and raw.get("id") is not None
            ]
        }
        for source_key in variable_map.values()
    ]

    date = current.get("Fecha")
    time = current.get("Hora")
    return {
        "estaciones": stations,
        "variables": variables,
        "observaciones": observations,
        "fechas": [
            f"{date} {time}"
            if date and time
            else datetime.now(timezone.utc).isoformat()
        ],
    }


class InumetApiClient:
    """Read Inumet's public resources without third-party libraries."""

    def __init__(self, session: aiohttp.ClientSession) -> None:
        """Initialize the client."""
        self._session = session
        self._resources = DEFAULT_RESOURCES.copy()
        self._resources_updated = 0.0
        self._resources_lock = asyncio.Lock()

    @staticmethod
    def _url(path: str) -> str:
        return urljoin(f"{BASE_URL}/", path.lstrip("/"))

    async def _request_json(self, path: str) -> dict[str, Any]:
        url = self._url(path)
        try:
            async with self._session.get(
                url, timeout=aiohttp.ClientTimeout(total=20)
            ) as response:
                if response.status != 200:
                    raise InumetApiError(f"HTTP {response.status} al consultar {url}")
                return decode_json(await response.text(), url)
        except (aiohttp.ClientError, asyncio.TimeoutError) as err:
            raise InumetApiError(f"No se pudo consultar {url}: {err}") from err

    async def async_get_resources(self) -> dict[str, str]:
        """Discover current endpoints from the resource list used by Inumet."""
        if monotonic() - self._resources_updated < RESOURCE_CACHE_SECONDS:
            return self._resources

        async with self._resources_lock:
            if monotonic() - self._resources_updated < RESOURCE_CACHE_SECONDS:
                return self._resources
            try:
                data = await self._request_json(INFO_RESOURCES_PATH)
                discovered = {
                    item["nombre"]: item["url"]
                    for item in data.get("info_recursos", [])
                    if isinstance(item, dict)
                    and isinstance(item.get("nombre"), str)
                    and isinstance(item.get("url"), str)
                    and "://" not in item["url"]
                    and not item["url"].startswith("//")
                }
                self._resources.update(discovered)
            except InumetApiError as err:
                _LOGGER.debug("No se pudo actualizar el índice de recursos: %s", err)
            self._resources_updated = monotonic()
            return self._resources

    async def async_get_observations(self) -> dict[str, Any]:
        """Get detailed observations, with estadoActualV2 as a fallback."""
        try:
            return await self._request_json(ESTADO_ACTUAL_PATH)
        except InumetApiError as detailed_error:
            resources = await self.async_get_resources()
            try:
                current, catalog = await asyncio.gather(
                    self._request_json(resources["estadoactual"]),
                    self._request_json(resources["estaciones"]),
                )
                return normalize_current_conditions(current, catalog)
            except (InumetApiError, KeyError) as fallback_error:
                raise InumetApiError(
                    f"Fallaron las observaciones detalladas ({detailed_error}) y el respaldo ({fallback_error})"
                ) from fallback_error

    async def async_get_forecast(self) -> dict[str, Any]:
        """Get the national forecast."""
        resources = await self.async_get_resources()
        try:
            # The JSON feed currently contains a longer forecast than the MCH
            # path advertised for the mobile application.
            return await self._request_json(FORECAST_PATH)
        except InumetApiError:
            path = resources.get("pronosticoV2", FORECAST_PATH)
            if path != FORECAST_PATH:
                return await self._request_json(path)
            raise

    async def async_get_general_alerts(self) -> dict[str, Any]:
        """Get meteorological warnings."""
        resources = await self.async_get_resources()
        path = resources.get("nivelRiesgoV2", GENERAL_ALERTS_PATH)
        try:
            return await self._request_json(path)
        except InumetApiError:
            if path != GENERAL_ALERTS_PATH:
                return await self._request_json(GENERAL_ALERTS_PATH)
            raise

    async def async_get_special_alerts(self) -> dict[str, Any]:
        """Get heat, cold, and other public notices."""
        return await self._request_json(SPECIAL_ALERTS_PATH)
