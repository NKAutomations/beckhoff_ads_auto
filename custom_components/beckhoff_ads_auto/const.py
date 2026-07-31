from __future__ import annotations

from dataclasses import dataclass
from typing import Final

DOMAIN: Final = "beckhoff_ads_auto"
CONF_AMS_NET_ID: Final = "ams_net_id"
CONF_HOST: Final = "host"
CONF_PORT: Final = "port"
CONF_ROOTS: Final = "roots"
CONF_POLL_INTERVAL: Final = "poll_interval"
CONF_WRITE_ENABLE: Final = "write_enable"
CONF_INCLUDE: Final = "include"
CONF_EXCLUDE: Final = "exclude"
CONF_READ_ONLY: Final = "read_only"
CONF_INCLUDE_ARRAYS: Final = "include_arrays"
DEFAULT_PORT: Final = 851
DEFAULT_POLL_INTERVAL: Final = 2.0
SERVICE_RESCAN: Final = "rescan"
SERVICE_READ_SYMBOL: Final = "read_symbol"
SERVICE_WRITE_SYMBOL: Final = "write_symbol"
ATTR_SYMBOL: Final = "symbol"
ATTR_VALUE: Final = "value"
ATTR_ENTRY_ID: Final = "entry_id"

@dataclass(frozen=True, slots=True)
class TypeInfo:
    plc_type: str
    domain: str
    writable: bool
    numeric: bool = False
    string: bool = False
    boolean: bool = False
    unit: str | None = None

TYPE_MAPPING: Final[dict[str, TypeInfo]] = {
    "BOOL": TypeInfo("BOOL", "binary_sensor", False, boolean=True),
    "BYTE": TypeInfo("BYTE", "sensor", True, numeric=True),
    "WORD": TypeInfo("WORD", "sensor", True, numeric=True),
    "DWORD": TypeInfo("DWORD", "sensor", True, numeric=True),
    "SINT": TypeInfo("SINT", "sensor", True, numeric=True),
    "USINT": TypeInfo("USINT", "sensor", True, numeric=True),
    "INT": TypeInfo("INT", "sensor", True, numeric=True),
    "UINT": TypeInfo("UINT", "sensor", True, numeric=True),
    "DINT": TypeInfo("DINT", "sensor", True, numeric=True),
    "UDINT": TypeInfo("UDINT", "sensor", True, numeric=True),
    "LINT": TypeInfo("LINT", "sensor", True, numeric=True),
    "ULINT": TypeInfo("ULINT", "sensor", True, numeric=True),
    "REAL": TypeInfo("REAL", "sensor", True, numeric=True),
    "LREAL": TypeInfo("LREAL", "sensor", True, numeric=True),
    "STRING": TypeInfo("STRING", "sensor", True, string=True),
}

NUMERIC_TYPES: Final = {key for key, value in TYPE_MAPPING.items() if value.numeric}
