from __future__ import annotations

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .entity_factory import ADSBaseEntity
from .platform_helpers import descriptors_for

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    coordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([ADSSwitch(coordinator, d) for d in descriptors_for(coordinator, "switch")])
    coordinator.register_adder("switch", lambda paths: async_add_entities([ADSSwitch(coordinator, coordinator.symbols[p]) for p in paths]))

class ADSSwitch(ADSBaseEntity, SwitchEntity):
    @property
    def is_on(self):
        return bool(self.value) if self.value is not None else None

    async def async_turn_on(self, **kwargs):
        await self.async_write(True)

    async def async_turn_off(self, **kwargs):
        await self.async_write(False)
