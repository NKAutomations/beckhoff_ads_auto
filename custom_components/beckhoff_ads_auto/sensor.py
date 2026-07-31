from __future__ import annotations

from homeassistant.components.sensor import SensorEntity, SensorStateClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .entity_factory import ADSBaseEntity
from .platform_helpers import descriptors_for

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    coordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([ADSSensor(coordinator, d) for d in descriptors_for(coordinator, "sensor")])
    coordinator.register_adder("sensor", lambda paths: async_add_entities([ADSSensor(coordinator, coordinator.symbols[p]) for p in paths]))

class ADSSensor(ADSBaseEntity, SensorEntity):
    def __init__(self, coordinator, descriptor) -> None:
        super().__init__(coordinator, descriptor)
        self._attr_state_class = SensorStateClass.MEASUREMENT if descriptor.info.numeric else None

    @property
    def native_value(self):
        return self.value
