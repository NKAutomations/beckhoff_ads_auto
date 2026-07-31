from __future__ import annotations

from homeassistant.components.text import TextEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .entity_factory import ADSBaseEntity
from .platform_helpers import descriptors_for

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    coordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([ADSText(coordinator, d) for d in descriptors_for(coordinator, "text")])
    coordinator.register_adder("text", lambda paths: async_add_entities([ADSText(coordinator, coordinator.symbols[p]) for p in paths]))

class ADSText(ADSBaseEntity, TextEntity):
    _attr_native_max = 255

    @property
    def native_value(self):
        return str(self.value) if self.value is not None else None

    async def async_set_value(self, value: str) -> None:
        await self.async_write(value)
