"""Sensor platform for Inumet Uruguay."""

from __future__ import annotations

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    DEGREE,
    PERCENTAGE,
    UnitOfPressure,
    UnitOfSpeed,
    UnitOfTemperature,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, MANUFACTURER, NAME, VERSION
from .coordinator import InumetDataUpdateCoordinator

# El 'key' ahora es el idStr de la API
ENTITY_DESCRIPTIONS: tuple[SensorEntityDescription, ...] = (
    SensorEntityDescription(
        key="TempAire",
        name="Temperatura",
        device_class=SensorDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    SensorEntityDescription(
        key="HumRelativa",
        name="Humedad Relativa",
        device_class=SensorDeviceClass.HUMIDITY,
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    SensorEntityDescription(
        key="PresAtmMar",
        name="Presión",
        device_class=SensorDeviceClass.ATMOSPHERIC_PRESSURE,
        native_unit_of_measurement=UnitOfPressure.HPA,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    SensorEntityDescription(
        key="IntViento",
        name="Intensidad de Viento",
        device_class=SensorDeviceClass.WIND_SPEED,
        native_unit_of_measurement=UnitOfSpeed.KNOTS,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:weather-windy",
    ),
    SensorEntityDescription(
        key="DirViento",
        name="Dirección del Viento",
        native_unit_of_measurement=DEGREE,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:compass-outline",
    ),
)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up the sensor platform."""
    coordinator: InumetDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        InumetWeatherSensor(coordinator, entry, description)
        for description in ENTITY_DESCRIPTIONS
    )


class InumetWeatherSensor(CoordinatorEntity[InumetDataUpdateCoordinator], SensorEntity):
    """Inumet Weather Sensor class."""

    def __init__(
        self,
        coordinator: InumetDataUpdateCoordinator,
        entry: ConfigEntry,
        description: SensorEntityDescription,
    ) -> None:
        """Initialize the sensor class."""
        super().__init__(coordinator)
        self.entity_description = description
        self.station_id = entry.data["station_id"]

        self._attr_has_entity_name = True
        self._attr_unique_id = f"{entry.entry_id}_{description.key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=f"{NAME} - {entry.title}",
            manufacturer=MANUFACTURER,
            sw_version=VERSION,
            model="Estación Meteorológica",
        )

    @property
    def native_value(self) -> float | str | None:
        """Return the native value of the sensor."""
        try:
            estado_data = self.coordinator.data["estado"]

            # Encontrar el índice de la estación y de la variable
            station_idx = next(
                (
                    i
                    for i, estacion in enumerate(estado_data["estaciones"])
                    if estacion["id"] == self.station_id
                ),
                None,
            )
            variable_idx = next(
                (
                    i
                    for i, variable in enumerate(estado_data["variables"])
                    if variable["idStr"] == self.entity_description.key
                ),
                None,
            )

            if station_idx is not None and variable_idx is not None:
                values = estado_data["observaciones"][variable_idx]["datos"][
                    station_idx
                ]
                value = next(
                    (
                        item
                        for item in reversed(values)
                        if item not in (None, "", "variable", "-")
                    ),
                    None,
                )
                if value == "TRAZA":
                    return 0.0
                return float(value) if value is not None else None
            return None
        except (KeyError, IndexError, TypeError, ValueError):
            return None
