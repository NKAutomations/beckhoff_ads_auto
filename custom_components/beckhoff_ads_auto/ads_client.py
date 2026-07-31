from __future__ import annotations

import logging
import re
import threading
from dataclasses import dataclass
from typing import Any

import pyads

from .const import TYPE_MAPPING, TypeInfo
from .exceptions import BeckhoffAdsConnectionError, BeckhoffAdsReadError, BeckhoffAdsWriteError

_LOGGER = logging.getLogger(__name__)

@dataclass(slots=True)
class SymbolDescriptor:
    path: str
    plc_type: str
    info: TypeInfo
    writable: bool
    comment: str = ""
    size: int | None = None

    @property
    def normalized_type(self) -> str:
        return self.info.plc_type

def normalize_type(value: Any) -> str:
    text = str(value or "").upper().strip()
    if text.startswith("STRING"):
        return "STRING"
    return text.split("(", 1)[0].strip()

def classify_type(value: Any) -> TypeInfo | None:
    return TYPE_MAPPING.get(normalize_type(value))

class ADSClient:
    def __init__(self, host: str, ams_net_id: str, port: int) -> None:
        self.host, self.ams_net_id, self.port = host, ams_net_id, port
        self._connection: pyads.Connection | None = None
        self._lock = threading.RLock()

    def connect(self) -> None:
        with self._lock:
            if self._connection and self._connection.is_open:
                return
            _LOGGER.debug("Opening ADS connection to %s:%s via %s", self.ams_net_id, self.port, self.host)
            try:
                self._connection = pyads.Connection(self.ams_net_id, self.port, self.host)
                self._connection.open()
            except Exception as err:
                self._connection = None
                raise BeckhoffAdsConnectionError(str(err)) from err

    def close(self) -> None:
        with self._lock:
            if self._connection:
                try:
                    self._connection.close()
                except Exception:  # pragma: no cover - best effort cleanup
                    _LOGGER.debug("Error while closing ADS connection", exc_info=True)
                self._connection = None

    def _ensure(self) -> pyads.Connection:
        self.connect()
        assert self._connection is not None
        return self._connection

    def test_connection(self) -> None:
        self.connect()
        self.close()

    def discover(self, roots: list[str], include: str = "", exclude: str = "", read_only: str = "", include_arrays: bool = False) -> dict[str, SymbolDescriptor]:
        connection = self._ensure()
        try:
            symbols = connection.get_all_symbols()
        except Exception as err:
            self.close()
            raise BeckhoffAdsConnectionError(str(err)) from err
        result: dict[str, SymbolDescriptor] = {}
        for symbol in symbols:
            path = str(getattr(symbol, "name", ""))
            if not path or not any(path == root or path.startswith(root + ".") or path.startswith(root + "[") for root in roots):
                continue
            if "[" in path and not include_arrays:
                continue
            info = classify_type(getattr(symbol, "symbol_type", ""))
            if info is None:
                continue
            if include and not _matches(path, include):
                continue
            if exclude and _matches(path, exclude):
                continue
            forced_ro = bool(read_only and _matches(path, read_only))
            try:
                symbol_read_only = bool(getattr(symbol, "read_only", False))
            except Exception:
                symbol_read_only = False
            result[path] = SymbolDescriptor(path, info.plc_type, info, not (symbol_read_only or forced_ro), str(getattr(symbol, "comment", "") or ""), getattr(symbol, "size", None))
        _LOGGER.debug("Discovered %d supported ADS symbols below roots %s", len(result), roots)
        return result

    def read_many(self, descriptors: list[SymbolDescriptor]) -> dict[str, Any]:
        if not descriptors:
            return {}
        connection = self._ensure()
        values: dict[str, Any] = {}
        try:
            # pyads has no portable multi-read API across all supported versions;
            # keeping one connection and doing reads under one lock is reliable.
            for descriptor in descriptors:
                values[descriptor.path] = connection.read_by_name(descriptor.path, descriptor.plc_type)
            _LOGGER.debug("Read %d ADS symbols", len(values))
        except Exception as err:
            self.close()
            raise BeckhoffAdsReadError(str(err)) from err
        return values

    def read(self, descriptor: SymbolDescriptor) -> Any:
        return self.read_many([descriptor]).get(descriptor.path)

    def write(self, descriptor: SymbolDescriptor, value: Any) -> None:
        if not descriptor.writable:
            raise BeckhoffAdsWriteError(f"Symbol is read-only: {descriptor.path}")
        connection = self._ensure()
        try:
            connection.write_by_name(descriptor.path, _coerce_value(value, descriptor.normalized_type), descriptor.plc_type)
            _LOGGER.debug("Wrote ADS symbol %s", descriptor.path)
        except Exception as err:
            self.close()
            raise BeckhoffAdsWriteError(str(err)) from err

def _matches(path: str, pattern: str) -> bool:
    try:
        return bool(re.search(pattern, path))
    except re.error:
        return path.startswith(pattern)

def _coerce_value(value: Any, plc_type: str) -> Any:
    if plc_type == "BOOL":
        if isinstance(value, str):
            return value.lower() in {"1", "true", "on", "yes"}
        return bool(value)
    if plc_type == "STRING":
        return str(value)
    return float(value) if plc_type in {"REAL", "LREAL"} else int(value)
