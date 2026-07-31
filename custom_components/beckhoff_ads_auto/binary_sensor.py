from __future__ import annotations

from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .entity_factory import ADSBaseEntity
from .platform_helpers import descriptors_for

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    coordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([ADSBinarySensor(coordinator, d) for d in descriptors_for(coordinator, "binary_sensor")])
    coordinator.register_adder("binary_sensor", lambda paths: async_add_entities([ADSBinarySensor(coordinator, coordinator.symbols[p]) for p in paths]))

class ADSBinarySensor(ADSBaseEntity, BinarySensorEntity):
    @property
    def is_on(self):
        return bool(self.value) if self.value is not None else None
