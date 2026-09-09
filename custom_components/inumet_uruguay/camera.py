"""Camera platform for Inumet Uruguay based on a dynamic URL."""

from __future__ import annotations

import logging

from homeassistant.components.camera import Camera
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, MANUFACTURER, NAME, VERSION
from .coordinator import InumetDataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up the Inumet camera platform."""
    coordinator: InumetDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]

    # Nos aseguramos de que los datos del coordinador estén listos antes de añadir la entidad
    if coordinator.data and coordinator.data.get("estado"):
        async_add_entities([InumetCamera(coordinator, entry)])
    else:
        _LOGGER.warning(
            "No se pudo configurar la cámara de Inumet porque los datos iniciales no están disponibles."
        )


class InumetCamera(CoordinatorEntity[InumetDataUpdateCoordinator], Camera):
    """An Inumet camera entity that provides a stream URL as an attribute."""

    _attr_has_entity_name = True

    def __init__(
        self, coordinator: InumetDataUpdateCoordinator, entry: ConfigEntry
    ) -> None:
        """Initialize the camera."""
        super().__init__(coordinator)
        Camera.__init__(self)
        self.station_id = entry.data["station_id"]

        self._attr_name = "Cámara Estación"
        self._attr_unique_id = f"{entry.entry_id}_camera"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=f"{NAME} ({entry.title})",
            manufacturer=MANUFACTURER,
            model="Estación Meteorológica",
            sw_version=VERSION,
        )
        self._url = None  # Se calculará en la primera actualización

    def _update_url(self) -> None:
        """Calculate and store the camera URL based on coordinator data."""
        if not self.coordinator.data or not self.coordinator.data.get("estado"):
            self._url = None
            return

        station_data = next(
            (
                est
                for est in self.coordinator.data["estado"]["estaciones"]
                if est["id"] == self.station_id
            ),
            None,
        )

        if station_data and (id_str := station_data.get("idStr")):
            self._url = (
                f"https://www.inumet.gub.uy/reportes/camaras_estaciones/{id_str}.webm"
            )
        else:
            self._url = None

    @property
    def image_url(self) -> str | None:
        """Return the URL of the image."""
        self._update_url()
        return self._url

    @property
    def extra_state_attributes(self) -> dict:
        """Return extra state attributes."""
        # Este es el atributo que usaremos en nuestra tarjeta
        self._update_url()
        return {"direct_url": self._url}

    async def async_camera_image(
        self, width: int | None = None, height: int | None = None
    ) -> bytes | None:
        """Return a camera image. Returning None forces use of image_url."""
        return None
