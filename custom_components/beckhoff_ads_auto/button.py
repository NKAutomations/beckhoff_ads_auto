from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    async_add_entities([RescanButton(hass.data[DOMAIN][entry.entry_id])])

class RescanButton(ButtonEntity):
    _attr_has_entity_name = True
    _attr_name = "Rescan symbols"

    def __init__(self, coordinator) -> None:
        self.coordinator = coordinator
        self._attr_unique_id = f"{coordinator.client.ams_net_id}_rescan"
        self._attr_device_info = {"identifiers": {(DOMAIN, coordinator.client.ams_net_id)}, "name": f"Beckhoff PLC {coordinator.client.ams_net_id}", "manufacturer": "Beckhoff"}

    async def async_press(self) -> None:
        await self.coordinator.async_rescan()
