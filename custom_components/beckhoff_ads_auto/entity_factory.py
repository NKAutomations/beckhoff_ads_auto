from __future__ import annotations

import re
from typing import Any

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity import Entity

from .ads_client import SymbolDescriptor
from .const import DOMAIN

class ADSBaseEntity(Entity):
    _attr_should_poll = False

    def __init__(self, coordinator, descriptor: SymbolDescriptor) -> None:
        self.coordinator = coordinator
        self.descriptor = descriptor
        self._attr_unique_id = f"{coordinator.client.ams_net_id}_{descriptor.path}".replace(".", "_")
        self._attr_name = _friendly_name(descriptor)
        self._attr_device_info = DeviceInfo(identifiers={(DOMAIN, coordinator.client.ams_net_id)}, name=f"Beckhoff PLC {coordinator.client.ams_net_id}", manufacturer="Beckhoff", model="TwinCAT ADS", configuration_url=f"http://{coordinator.client.host}")

    @property
    def available(self) -> bool:
        return self.descriptor.path in self.coordinator.data and self.coordinator.last_update_success

    @property
    def value(self) -> Any:
        return self.coordinator.data.get(self.descriptor.path)

    async def async_write(self, value: Any) -> None:
        await self.coordinator.async_write_symbol(self.descriptor.path, value)

def _friendly_name(descriptor: SymbolDescriptor) -> str:
    comment = descriptor.comment.strip()
    if comment:
        return comment.split("\n", 1)[0].strip()
    return re.sub(r"([a-z])([A-Z])", r"\1 \2", descriptor.path.rsplit(".", 1)[-1]).replace("_", " ")
