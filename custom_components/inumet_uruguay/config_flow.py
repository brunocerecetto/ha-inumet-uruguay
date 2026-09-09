"""Config flow for Inumet Uruguay."""

from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import InumetApiClient, InumetApiError
from .const import (
    CONF_STATION_ID,
    CONF_STATION_NAME,
    CONF_UPDATE_INTERVAL,
    DEFAULT_UPDATE_INTERVAL,
    DOMAIN,
)


class InumetFlowHandler(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Inumet Uruguay."""

    VERSION = 1
    _attr_translation_domain = DOMAIN

    def __init__(self) -> None:
        """Initialize the config flow."""
        self.station_options: dict[int, str] = {}

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the user step."""
        if len(self._async_current_entries()) >= 3:
            return self.async_abort(reason="max_instances_reached")

        errors: dict[str, str] = {}

        if user_input is not None:
            station_id = user_input[CONF_STATION_ID]
            station_name = self.station_options.get(station_id, "Estación Desconocida")

            data_to_save = {
                CONF_STATION_ID: station_id,
                CONF_STATION_NAME: station_name,
                CONF_UPDATE_INTERVAL: user_input[CONF_UPDATE_INTERVAL],
            }

            return self.async_create_entry(title=station_name, data=data_to_save)

        try:
            session = async_get_clientsession(self.hass)
            data = await InumetApiClient(session).async_get_observations()
            station_options = {
                station["id"]: station.get("displayNamePublic")
                or station.get("nombre")
                or str(station["id"])
                for station in data.get("estaciones", [])
                if station.get("id") is not None and station.get("gerencia") == "INUMET"
            }
            self.station_options = dict(
                sorted(station_options.items(), key=lambda item: item[1])
            )

        except InumetApiError:
            errors["base"] = "cannot_connect"

        if not self.station_options:
            return self.async_show_form(step_id="user", errors=errors)

        data_schema = vol.Schema(
            {
                vol.Required(CONF_STATION_ID): vol.In(self.station_options),
                vol.Required(
                    CONF_UPDATE_INTERVAL, default=DEFAULT_UPDATE_INTERVAL
                ): vol.All(vol.Coerce(int), vol.Range(min=30, max=240)),
            }
        )

        return self.async_show_form(
            step_id="user", data_schema=data_schema, errors=errors
        )

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> OptionsFlowHandler:
        """Get the options flow for this handler."""
        return OptionsFlowHandler(config_entry)


class OptionsFlowHandler(config_entries.OptionsFlow):
    """Handle an options flow."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        """Initialize options flow."""
        self.config_entry = config_entry

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Manage the options."""
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        schema = vol.Schema(
            {
                vol.Required(
                    CONF_UPDATE_INTERVAL,
                    default=self.config_entry.options.get(
                        CONF_UPDATE_INTERVAL,
                        self.config_entry.data.get(
                            CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL
                        ),
                    ),
                ): vol.All(vol.Coerce(int), vol.Range(min=30, max=240)),
            }
        )
        return self.async_show_form(step_id="init", data_schema=schema)
