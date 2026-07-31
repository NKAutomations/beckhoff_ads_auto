from __future__ import annotations

import asyncio
import logging
from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import HomeAssistant

from .ads_client import ADSClient
from .const import (CONF_AMS_NET_ID, CONF_EXCLUDE, CONF_HOST, CONF_INCLUDE, CONF_INCLUDE_ARRAYS,
                    CONF_LOCAL_AMS_NET_ID, CONF_POLL_INTERVAL, CONF_PORT, CONF_READ_ONLY, CONF_ROOTS,
                    CONF_TIMEOUT, CONF_WRITE_ENABLE, DEFAULT_POLL_INTERVAL, DEFAULT_PORT, DEFAULT_TIMEOUT,
                    DOMAIN)

_LOGGER = logging.getLogger(__name__)

class BeckhoffConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None):
        errors: dict[str, str] = {}
        if user_input:
            try:
                await self.hass.async_add_executor_job(
                    ADSClient(
                        user_input[CONF_HOST],
                        user_input[CONF_AMS_NET_ID],
                        int(user_input[CONF_PORT]),
                        user_input.get(CONF_LOCAL_AMS_NET_ID) or None,
                        float(user_input.get(CONF_TIMEOUT, DEFAULT_TIMEOUT)),
                    ).test_connection
                )
            except Exception as err:
                _LOGGER.exception("ADS config-flow connection test failed: %s", err)
                errors["base"] = "cannot_connect"
            else:
                await self.async_set_unique_id(f"{user_input[CONF_AMS_NET_ID]}:{user_input[CONF_PORT]}")
                self._abort_if_unique_id_configured()
                return self.async_create_entry(title=user_input[CONF_AMS_NET_ID], data=user_input)
        schema = vol.Schema({
            vol.Required(CONF_HOST, default="127.0.0.1"): str,
            vol.Required(CONF_AMS_NET_ID): str,
            vol.Optional(CONF_LOCAL_AMS_NET_ID, default=""): str,
            vol.Required(CONF_PORT, default=DEFAULT_PORT): vol.Coerce(int),
            vol.Required(CONF_TIMEOUT, default=DEFAULT_TIMEOUT): vol.All(vol.Coerce(float), vol.Range(min=0.2, max=30)),
            vol.Required(CONF_ROOTS, default="GVL_HA"): str,
            vol.Required(CONF_POLL_INTERVAL, default=DEFAULT_POLL_INTERVAL): vol.All(vol.Coerce(float), vol.Range(min=0.5, max=10)),
            vol.Required(CONF_WRITE_ENABLE, default=False): bool,
        })
        return self.async_show_form(step_id="user", data_schema=schema, errors=errors)

    @staticmethod
    @config_entries.callback
    def async_get_options_flow(config_entry):
        return BeckhoffOptionsFlow(config_entry)

class BeckhoffOptionsFlow(config_entries.OptionsFlow):
    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        super().__init__(config_entry)

    async def async_step_init(self, user_input: dict[str, Any] | None = None):
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)
        current = {**self.config_entry.data, **self.config_entry.options}
        return self.async_show_form(step_id="init", data_schema=vol.Schema({
            vol.Optional(CONF_LOCAL_AMS_NET_ID, default=current.get(CONF_LOCAL_AMS_NET_ID, "")): str,
            vol.Required(CONF_TIMEOUT, default=current.get(CONF_TIMEOUT, DEFAULT_TIMEOUT)): vol.All(vol.Coerce(float), vol.Range(min=0.2, max=30)),
            vol.Required(CONF_ROOTS, default=current.get(CONF_ROOTS, "GVL_HA")): str,
            vol.Required(CONF_POLL_INTERVAL, default=current.get(CONF_POLL_INTERVAL, DEFAULT_POLL_INTERVAL)): vol.All(vol.Coerce(float), vol.Range(min=0.5, max=10)),
            vol.Required(CONF_WRITE_ENABLE, default=current.get(CONF_WRITE_ENABLE, False)): bool,
            vol.Optional(CONF_INCLUDE, default=current.get(CONF_INCLUDE, "")): str,
            vol.Optional(CONF_EXCLUDE, default=current.get(CONF_EXCLUDE, "")): str,
            vol.Optional(CONF_READ_ONLY, default=current.get(CONF_READ_ONLY, "")): str,
            vol.Required(CONF_INCLUDE_ARRAYS, default=current.get(CONF_INCLUDE_ARRAYS, False)): bool,
        }))
