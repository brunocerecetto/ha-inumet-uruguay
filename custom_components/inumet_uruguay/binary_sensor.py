"""Binary sensor platform for Inumet Uruguay."""

from __future__ import annotations

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, MANUFACTURER, NAME, VERSION
from .coordinator import InumetDataUpdateCoordinator


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up the binary_sensor platform."""
    coordinator: InumetDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([InumetAlertsBinarySensor(coordinator, entry)])


class InumetAlertsBinarySensor(
    CoordinatorEntity[InumetDataUpdateCoordinator], BinarySensorEntity
):
    """Inumet Alerts binary_sensor class."""

    _attr_has_entity_name = True
    _attr_name = "Alerta"
    _attr_device_class = BinarySensorDeviceClass.SAFETY

    def __init__(
        self, coordinator: InumetDataUpdateCoordinator, entry: ConfigEntry
    ) -> None:
        """Initialize the binary_sensor class."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_alerts"

        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=f"{NAME} - {entry.data['station_name']}",
            manufacturer=MANUFACTURER,
            sw_version=VERSION,
            model="Estación Meteorológica",
            entry_type="service",
        )

    @property
    def is_on(self) -> bool:
        """Return true if there are active alerts."""
        return self.coordinator.data.get("has_alerts", False)

    @property
    def extra_state_attributes(self) -> dict | None:
        """Return the state attributes."""
        if not self.is_on:
            return None

        alerts_list = self.coordinator.data.get("active_alerts", [])

        return {
            "cantidad_alertas": len(alerts_list),
            "alertas": alerts_list,
            "ultima_actualizacion": self.coordinator.data.get("last_updated_timestamp"),
        }
