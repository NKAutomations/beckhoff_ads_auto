from __future__ import annotations

import asyncio
from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.helpers import selector

from .ads_client import ADSClient
from .const import (CONF_AMS_NET_ID, CONF_EXCLUDE, CONF_HOST, CONF_INCLUDE, CONF_INCLUDE_ARRAYS,
                    CONF_POLL_INTERVAL, CONF_READ_ONLY, CONF_ROOTS, CONF_WRITE_ENABLE, DEFAULT_POLL_INTERVAL,
                    DEFAULT_PORT, DOMAIN)

class BeckhoffConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None):
        errors: dict[str, str] = {}
        if user_input:
            try:
                await self.hass.async_add_executor_job(ADSClient(user_input[CONF_HOST], user_input[CONF_AMS_NET_ID], user_input["port"]).test_connection)
            except Exception:
                errors["base"] = "cannot_connect"
            else:
                await self.async_set_unique_id(f"{user_input[CONF_AMS_NET_ID]}:{user_input['port']}")
                self._abort_if_unique_id_configured()
                return self.async_create_entry(title=user_input[CONF_AMS_NET_ID], data=user_input)
        schema = vol.Schema({
            vol.Required(CONF_HOST, default="127.0.0.1"): str,
            vol.Required(CONF_AMS_NET_ID): str,
            vol.Required("port", default=DEFAULT_PORT): vol.Coerce(int),
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
        self.config_entry = config_entry

    async def async_step_init(self, user_input: dict[str, Any] | None = None):
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)
        current = {**self.config_entry.data, **self.config_entry.options}
        return self.async_show_form(step_id="init", data_schema=vol.Schema({
            vol.Required(CONF_ROOTS, default=current.get(CONF_ROOTS, "GVL_HA")): str,
            vol.Required(CONF_POLL_INTERVAL, default=current.get(CONF_POLL_INTERVAL, DEFAULT_POLL_INTERVAL)): vol.All(vol.Coerce(float), vol.Range(min=0.5, max=10)),
            vol.Required(CONF_WRITE_ENABLE, default=current.get(CONF_WRITE_ENABLE, False)): bool,
            vol.Optional(CONF_INCLUDE, default=current.get(CONF_INCLUDE, "")): str,
            vol.Optional(CONF_EXCLUDE, default=current.get(CONF_EXCLUDE, "")): str,
            vol.Optional(CONF_READ_ONLY, default=current.get(CONF_READ_ONLY, "")): str,
            vol.Required(CONF_INCLUDE_ARRAYS, default=current.get(CONF_INCLUDE_ARRAYS, False)): bool,
        }))
