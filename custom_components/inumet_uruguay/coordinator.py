"""DataUpdateCoordinator for Inumet Uruguay."""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Awaitable
from datetime import timedelta
from typing import Any

import aiohttp
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .api import InumetApiClient, InumetApiError, normalize_alerts
from .const import (
    BASE_URL,
    CONF_UPDATE_INTERVAL,
    DEFAULT_UPDATE_INTERVAL,
    NAME,
)

_LOGGER = logging.getLogger(__package__)


class InumetDataUpdateCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Manage updates from Inumet's public data sources."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        """Initialize the coordinator."""
        self.config_entry = entry
        self.session = async_get_clientsession(hass)
        self.client = InumetApiClient(self.session)
        interval = entry.options.get(
            CONF_UPDATE_INTERVAL,
            entry.data.get(CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL),
        )
        super().__init__(
            hass,
            _LOGGER,
            name=f"{NAME} ({entry.title})",
            update_interval=timedelta(minutes=interval),
        )

    async def _async_find_latest_uv_url(self) -> str | None:
        """Find the latest UV map from the listing used by Inumet's UV viewer."""
        try:
            async with self.session.get(
                f"{BASE_URL}/reportes/geonetcast/uv.json",
                timeout=aiohttp.ClientTimeout(total=10),
            ) as response:
                if response.status != 200:
                    return None
                listing = json.loads(await response.text())
                # The listing redirects to another domain; images live next to it.
                base = str(response.url).rsplit("/", 1)[0]
        except (aiohttp.ClientError, asyncio.TimeoutError, ValueError):
            return None

        paths = [
            path
            for path in listing.get("LES-inidice_uv", [])
            if isinstance(path, str) and path.rsplit("/", 1)[-1].startswith("iuvcsk_")
        ]
        return f"{base}/{max(paths)}" if paths else None

    async def _result_or_previous(
        self,
        name: str,
        request: Awaitable[dict[str, Any]],
    ) -> dict[str, Any] | None:
        """Return fresh source data or retain its last successful value."""
        try:
            return await request
        except InumetApiError as err:
            _LOGGER.warning("No se pudo actualizar %s: %s", name, err)
            if self.data:
                previous = self.data.get(name)
                return previous if isinstance(previous, dict) else None
            return None

    async def _async_update_data(self) -> dict[str, Any]:
        """Fetch observations, forecast, and alerts independently."""
        estado, forecast, adv_gral, avisos, latest_uv_url = await asyncio.gather(
            self._result_or_previous("estado", self.client.async_get_observations()),
            self._result_or_previous("forecast", self.client.async_get_forecast()),
            self._result_or_previous(
                "adv_gral", self.client.async_get_general_alerts()
            ),
            self._result_or_previous("avisos", self.client.async_get_special_alerts()),
            self._async_find_latest_uv_url(),
        )

        if estado is None and forecast is None:
            raise UpdateFailed(
                "No se pudieron obtener observaciones ni pronóstico de Inumet"
            )

        active_alerts = normalize_alerts(adv_gral, avisos, dt_util.now())
        return {
            "estado": estado,
            "forecast": forecast,
            "adv_gral": adv_gral,
            "avisos": avisos,
            "active_alerts": active_alerts,
            "has_alerts": bool(active_alerts),
            "latest_uv_url": latest_uv_url
            or (self.data.get("latest_uv_url") if self.data else None),
            "last_updated_timestamp": dt_util.utcnow(),
        }
