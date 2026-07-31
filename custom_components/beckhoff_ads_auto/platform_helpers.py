from __future__ import annotations

from .coordinator import _domain_for

def descriptors_for(coordinator, domain: str):
    return [d for d in coordinator.symbols.values() if _domain_for(d, coordinator.write_enable) == domain]
