from __future__ import annotations

import asyncio
import logging
from typing import Any

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, ServiceCall, SupportsResponse
from homeassistant.helpers import config_validation as cv

from .ads_client import ADSClient
from .const import (ATTR_ENTRY_ID, ATTR_SYMBOL, ATTR_VALUE, DOMAIN, SERVICE_READ_SYMBOL,
                    SERVICE_RESCAN, SERVICE_WRITE_SYMBOL)
from .coordinator import ADSCoordinator

_LOGGER = logging.getLogger(__name__)
PLATFORMS = ["sensor", "binary_sensor", "switch", "number", "text", "button"]

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    coordinator = ADSCoordinator(hass, entry)
    try:
        await coordinator.async_config_entry_first_refresh()
    except Exception:
        _LOGGER.exception(
            "Initial ADS refresh failed for entry=%s target=%s host=%s port=%s",
            entry.entry_id,
            coordinator.client.ams_net_id,
            coordinator.client.host,
            coordinator.client.port,
        )
        await coordinator.async_shutdown()
        raise
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator
    try:
        await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    except Exception:
        _LOGGER.exception(
            "ADS platform setup failed for entry=%s symbols=%s",
            entry.entry_id,
            len(coordinator.symbols),
        )
        hass.data.get(DOMAIN, {}).pop(entry.entry_id, None)
        await coordinator.async_shutdown()
        raise
    entry.async_on_unload(entry.add_update_listener(_async_options_updated))
    return True

async def _async_options_updated(hass: HomeAssistant, entry: ConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    coordinator: ADSCoordinator | None = hass.data.get(DOMAIN, {}).pop(entry.entry_id, None)
    if coordinator:
        await coordinator.async_shutdown()
    return True

def _coordinator(hass: HomeAssistant, call: ServiceCall) -> ADSCoordinator:
    entries = hass.data.get(DOMAIN, {})
    entry_id = call.data.get(ATTR_ENTRY_ID)
    if entry_id:
        coordinator = entries.get(entry_id)
        if coordinator is None:
            raise ValueError(f"Unknown entry_id: {entry_id}")
        return coordinator
    if len(entries) != 1:
        raise ValueError("entry_id is required when multiple PLCs are configured")
    return next(iter(entries.values()))

async def _handle_rescan(call: ServiceCall) -> None:
    await _coordinator(call.hass, call).async_rescan()

async def _handle_read(call: ServiceCall) -> dict[str, Any]:
    value = await _coordinator(call.hass, call).async_read_symbol(call.data[ATTR_SYMBOL])
    return {"symbol": call.data[ATTR_SYMBOL], "value": value}

async def _handle_write(call: ServiceCall) -> None:
    await _coordinator(call.hass, call).async_write_symbol(call.data[ATTR_SYMBOL], call.data[ATTR_VALUE])

async def async_setup(hass: HomeAssistant, config: dict[str, Any]) -> bool:
    if hass.services.has_service(DOMAIN, SERVICE_RESCAN):
        return True
    hass.services.async_register(DOMAIN, SERVICE_RESCAN, _handle_rescan,
                                 schema=vol.Schema({vol.Optional(ATTR_ENTRY_ID): cv.string}))
    hass.services.async_register(DOMAIN, SERVICE_READ_SYMBOL, _handle_read,
                                 schema=vol.Schema({vol.Required(ATTR_SYMBOL): cv.string, vol.Optional(ATTR_ENTRY_ID): cv.string}),
                                 supports_response=SupportsResponse.ONLY)
    hass.services.async_register(DOMAIN, SERVICE_WRITE_SYMBOL, _handle_write,
                                 schema=vol.Schema({vol.Required(ATTR_SYMBOL): cv.string, vol.Required(ATTR_VALUE): vol.Any(str, int, float, bool), vol.Optional(ATTR_ENTRY_ID): cv.string}))
    return True
