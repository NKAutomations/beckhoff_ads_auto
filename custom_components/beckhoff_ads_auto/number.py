from __future__ import annotations

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .entity_factory import ADSBaseEntity
from .platform_helpers import descriptors_for

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    coordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([ADSNumber(coordinator, d) for d in descriptors_for(coordinator, "number")])
    coordinator.register_adder("number", lambda paths: async_add_entities([ADSNumber(coordinator, coordinator.symbols[p]) for p in paths]))

class ADSNumber(ADSBaseEntity, NumberEntity):
    _attr_native_min_value = -2147483648
    _attr_native_max_value = 4294967295
    _attr_native_step = 0.01
    _attr_mode = NumberMode.BOX

    @property
    def native_value(self):
        return self.value

    async def async_set_native_value(self, value: float) -> None:
        await self.async_write(value)
