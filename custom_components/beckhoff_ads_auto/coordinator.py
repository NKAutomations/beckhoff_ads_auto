from __future__ import annotations

import asyncio
import logging
from datetime import timedelta
from typing import Any, Callable

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .ads_client import ADSClient, SymbolDescriptor
from .const import (CONF_AMS_NET_ID, CONF_EXCLUDE, CONF_HOST, CONF_INCLUDE, CONF_INCLUDE_ARRAYS,
                    CONF_POLL_INTERVAL, CONF_READ_ONLY, CONF_ROOTS, CONF_WRITE_ENABLE, DEFAULT_POLL_INTERVAL, DOMAIN)
from .exceptions import BeckhoffAdsError

_LOGGER = logging.getLogger(__name__)

class ADSCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        self.entry = entry
        config = {**entry.data, **entry.options}
        self.client = ADSClient(config[CONF_HOST], config[CONF_AMS_NET_ID], int(config.get("port", 851)))
        self.roots = _csv(config.get(CONF_ROOTS, ""))
        self.include, self.exclude, self.read_only = config.get(CONF_INCLUDE, ""), config.get(CONF_EXCLUDE, ""), config.get(CONF_READ_ONLY, "")
        self.include_arrays = bool(config.get(CONF_INCLUDE_ARRAYS, False))
        self.write_enable = bool(config.get(CONF_WRITE_ENABLE, False))
        self.symbols: dict[str, SymbolDescriptor] = {}
        self._adders: dict[str, Callable[[list[Any]], None]] = {}
        super().__init__(hass, _LOGGER, name=f"Beckhoff ADS {config[CONF_AMS_NET_ID]}", update_interval=timedelta(seconds=float(config.get(CONF_POLL_INTERVAL, DEFAULT_POLL_INTERVAL))))

    async def _async_update_data(self) -> dict[str, Any]:
        try:
            if not self.symbols:
                self.symbols = await self.hass.async_add_executor_job(self.client.discover, self.roots, self.include, self.exclude, self.read_only, self.include_arrays)
            descriptors = list(self.symbols.values())
            return await self.hass.async_add_executor_job(self.client.read_many, descriptors)
        except BeckhoffAdsError as err:
            raise UpdateFailed(str(err)) from err
        except Exception as err:
            raise UpdateFailed(f"ADS polling failed: {err}") from err

    async def async_rescan(self) -> None:
        try:
            discovered = await self.hass.async_add_executor_job(self.client.discover, self.roots, self.include, self.exclude, self.read_only, self.include_arrays)
        except BeckhoffAdsError as err:
            _LOGGER.warning("ADS rescan failed: %s", err)
            return
        new_paths = set(discovered) - set(self.symbols)
        removed_paths = set(self.symbols) - set(discovered)
        self.symbols = discovered
        _LOGGER.debug("ADS rescan found %d symbols, %d new, %d removed", len(discovered), len(new_paths), len(removed_paths))
        for domain, adder in self._adders.items():
            entities = [path for path in new_paths if _domain_for(self.symbols[path], self.write_enable) == domain]
            if entities:
                adder(entities)
        await self.async_request_refresh()

    def register_adder(self, domain: str, callback: Callable[[list[Any]], None]) -> None:
        self._adders[domain] = callback

    async def async_read_symbol(self, path: str) -> Any:
        descriptor = self.symbols.get(path)
        if descriptor is None:
            await self.async_rescan()
            descriptor = self.symbols.get(path)
        if descriptor is None:
            raise ValueError(f"Unknown symbol: {path}")
        return await self.hass.async_add_executor_job(self.client.read, descriptor)

    async def async_write_symbol(self, path: str, value: Any) -> None:
        if not self.write_enable:
            raise ValueError("Writing is disabled in integration options")
        descriptor = self.symbols.get(path)
        if descriptor is None:
            raise ValueError(f"Unknown symbol: {path}")
        await self.hass.async_add_executor_job(self.client.write, descriptor, value)
        await self.async_request_refresh()

    async def async_shutdown(self) -> None:
        await self.hass.async_add_executor_job(self.client.close)
        self._adders.clear()

def _csv(value: str | list[str]) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    return [item.strip() for item in str(value).split(",") if item.strip()]

def _domain_for(descriptor: SymbolDescriptor, write_enable: bool) -> str:
    if descriptor.info.boolean:
        return "switch" if write_enable and descriptor.writable else "binary_sensor"
    if descriptor.info.numeric:
        return "number" if write_enable and descriptor.writable else "sensor"
    if descriptor.info.string:
        return "text" if write_enable and descriptor.writable else "sensor"
    return descriptor.info.domain
