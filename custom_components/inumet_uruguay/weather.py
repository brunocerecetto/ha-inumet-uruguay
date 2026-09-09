"""Weather platform for Inumet Uruguay."""

from __future__ import annotations

from datetime import time, timedelta

from homeassistant.components.weather import (
    Forecast,
    WeatherEntity,
    WeatherEntityFeature,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfPressure, UnitOfSpeed, UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import dt as dt_util

from .const import DOMAIN, MANUFACTURER, NAME, VERSION
from .coordinator import InumetDataUpdateCoordinator

# --- MAPEOS MOVIDOS AQUÍ PARA EVITAR ERRORES DE IMPORTACIÓN ---
DEPARTMENT_TO_ZONE_ID_MAP = {
    "AR": 66,
    "CA": 88,
    "CL": 65,
    "CO": 86,
    "DU": 67,
    "FS": 67,
    "FR": 67,
    "LA": 68,
    "MA": 89,
    "MO": 88,
    "PA": 86,
    "RN": 86,
    "RI": 65,
    "RO": 68,
    "SA": 66,
    "SJ": 88,
    "SO": 86,
    "TA": 65,
    "TT": 68,
}

CONDITION_MAP = {
    "1": "sunny",
    "2": "partlycloudy",
    "3": "partlycloudy",
    "4": "cloudy",
    "5": "cloudy",
    "6": "cloudy",
    "7": "rainy",
    "8": "fog",
    "9": "partlycloudy",
    "10": "lightning",
    "11": "lightning-rainy",
    "12": "windy",
    "13": "cloudy",
    "14": "fog",
    "15": "fog",
    "16": "fog",
    "17": "snowy",
    "18": "exceptional",
    "19": "windy-variant",
    "20": "clear-night",
    "21": "partlycloudy",
    "22": "partlycloudy",
    "23": "rainy",
    "24": "cloudy",
}


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up the weather platform."""
    coordinator: InumetDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([InumetWeather(coordinator, entry)])


class InumetWeather(CoordinatorEntity[InumetDataUpdateCoordinator], WeatherEntity):
    """Inumet Weather Entity."""

    _attr_native_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_native_pressure_unit = UnitOfPressure.HPA
    _attr_native_wind_speed_unit = (
        UnitOfSpeed.KNOTS
    )  # Volvemos a nudos como el original
    _attr_attribution = "Datos proporcionados por Inumet"
    _attr_supported_features = WeatherEntityFeature.FORECAST_DAILY

    def __init__(
        self, coordinator: InumetDataUpdateCoordinator, entry: ConfigEntry
    ) -> None:
        """Initialize the weather entity."""
        super().__init__(coordinator)
        self.station_id = entry.data["station_id"]
        self._attr_name = entry.title
        self._attr_unique_id = f"{entry.entry_id}_weather"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=f"{NAME} - {entry.title}",
            manufacturer=MANUFACTURER,
            sw_version=VERSION,
            model="Estación Meteorológica",
        )

    def _get_current_observation(self, variable_id_str: str) -> float | None:
        """Helper to get a value from the observations data."""
        try:
            if not self.coordinator.data or not self.coordinator.data.get("estado"):
                return None
            estado_data = self.coordinator.data["estado"]
            station_idx = next(
                i
                for i, est in enumerate(estado_data["estaciones"])
                if est["id"] == self.station_id
            )
            variable_idx = next(
                i
                for i, var in enumerate(estado_data["variables"])
                if var["idStr"] == variable_id_str
            )
            values = estado_data["observaciones"][variable_idx]["datos"][station_idx]
            value = next(
                (
                    item
                    for item in reversed(values)
                    if item not in (None, "", "variable", "-")
                ),
                None,
            )
            return float(value) if value is not None else None
        except (StopIteration, KeyError, IndexError, TypeError, ValueError):
            return None

    def _get_forecast_item_for_day(self, day_offset: int) -> dict | None:
        """Helper to get the forecast data for a specific day."""
        if not self.coordinator.data or not self.coordinator.data.get("forecast"):
            return None
        estado_data = self.coordinator.data.get("estado") or {}
        station_data = next(
            (
                est
                for est in estado_data.get("estaciones", [])
                if est["id"] == self.station_id
            ),
            None,
        )
        if not station_data:
            return None
        zone_id = DEPARTMENT_TO_ZONE_ID_MAP.get(station_data.get("estado"))
        if not zone_id:
            return None
        for item in self.coordinator.data["forecast"].get("items", []):
            if item.get("zonaId") == zone_id and item.get("diaMasN") == day_offset:
                return item
        return None

    @property
    def condition(self) -> str | None:
        """Return the current weather condition."""
        today_forecast = self._get_forecast_item_for_day(0)
        if today_forecast:
            return CONDITION_MAP.get(str(today_forecast.get("estadoTiempo")))
        return None

    @property
    def native_temperature(self) -> float | None:
        return self._get_current_observation("TempAire")

    @property
    def native_pressure(self) -> float | None:
        return self._get_current_observation("PresAtmMar")

    @property
    def humidity(self) -> float | None:
        return self._get_current_observation("HumRelativa")

    @property
    def native_wind_speed(self) -> float | None:
        return self._get_current_observation("IntViento")

    @property
    def wind_bearing(self) -> float | None:
        return self._get_current_observation("DirViento")

    @property
    def native_temperature_high(self) -> float | None:
        """Return the high temperature of the current day."""
        today_forecast = self._get_forecast_item_for_day(0)
        return today_forecast.get("tempMax") if today_forecast else None

    @property
    def native_temperature_low(self) -> float | None:
        """Return the low temperature of the current day."""
        today_forecast = self._get_forecast_item_for_day(0)
        return today_forecast.get("tempMin") if today_forecast else None

    async def async_forecast_daily(self) -> list[Forecast] | None:
        """Return the daily forecast."""
        if not self.coordinator.data or not self.coordinator.data.get("forecast"):
            return None

        forecast_items = self.coordinator.data["forecast"].get("items", [])
        start_date_str = self.coordinator.data["forecast"].get("inicioPronostico")
        if not forecast_items or not start_date_str:
            return None

        estado_data = self.coordinator.data.get("estado") or {}
        station_data = next(
            (
                est
                for est in estado_data.get("estaciones", [])
                if est["id"] == self.station_id
            ),
            None,
        )
        if not station_data:
            return None
        zone_id = DEPARTMENT_TO_ZONE_ID_MAP.get(station_data.get("estado"))
        if not zone_id:
            return None

        start_date = dt_util.parse_date(start_date_str)
        forecasts = []

        for item in forecast_items:
            if item.get("zonaId") == zone_id:
                day_offset = item.get("diaMasN", 0)

                # --- El arreglo definitivo para la fecha y zona horaria ---
                forecast_date = start_date + timedelta(days=day_offset)
                naive_datetime = dt_util.dt.datetime.combine(forecast_date, time.min)
                aware_datetime = naive_datetime.replace(
                    tzinfo=dt_util.DEFAULT_TIME_ZONE
                )

                forecast = {
                    "datetime": aware_datetime.isoformat(),
                    "native_temperature": item.get("tempMax"),
                    "native_templow": item.get("tempMin"),
                    "condition": CONDITION_MAP.get(str(item.get("estadoTiempo"))),
                }
                forecasts.append(forecast)

        return forecasts
