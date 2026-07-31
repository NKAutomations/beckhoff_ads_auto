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
    def __init__(self, host: str, ams_net_id: str, port: int, local_ams_net_id: str | None = None, timeout: float = 5.0) -> None:
        self.host, self.ams_net_id, self.port = host, ams_net_id, port
        self.local_ams_net_id = local_ams_net_id.strip() if local_ams_net_id else None
        self.timeout = float(timeout)
        self._connection: pyads.Connection | None = None
        self._lock = threading.RLock()
        self._local_router_configured = False

    def _configure_local_router(self) -> None:
        if not self.local_ams_net_id or self._local_router_configured:
            return
        try:
            _LOGGER.debug("Configuring local ADS AMS Net ID: %s", self.local_ams_net_id)
            pyads.open_port()
            pyads.set_local_address(self.local_ams_net_id)
            pyads.close_port()
            self._local_router_configured = True
        except Exception:
            try:
                pyads.close_port()
            except Exception:
                _LOGGER.debug("Error closing temporary pyads router port", exc_info=True)
            raise

    def _set_timeout(self) -> None:
        timeout_ms = int(self.timeout * 1000)
        connection_timeout = getattr(self._connection, "set_timeout", None)
        if callable(connection_timeout):
            connection_timeout(timeout_ms)
            return
        global_timeout = getattr(pyads, "set_timeout", None)
        if callable(global_timeout):
            global_timeout(timeout_ms)
            return
        raise TypeError("Installed pyads version has no callable timeout API")

    def connect(self) -> None:
        with self._lock:
            if self._connection and self._connection.is_open:
                return
            _LOGGER.debug(
                "Opening ADS connection to target=%s port=%s host=%s local_ams=%s timeout=%.2fs",
                self.ams_net_id, self.port, self.host, self.local_ams_net_id, self.timeout,
            )
            try:
                self._configure_local_router()
                self._connection = pyads.Connection(self.ams_net_id, self.port, self.host)
                self._connection.open()
                self._set_timeout()
                _LOGGER.debug("ADS connection opened successfully")
            except Exception as err:
                _LOGGER.exception("ADS connection failed: %s", err)
                self._connection = None
                raise BeckhoffAdsConnectionError(str(err)) from err

    def close(self) -> None:
        with self._lock:
            if self._connection:
                try:
                    self._connection.close()
                except Exception:
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
            symbol_read_only = bool(getattr(symbol, "read_only", False))
            result[path] = SymbolDescriptor(path, info.plc_type, info, not (symbol_read_only or forced_ro), str(getattr(symbol, "comment", "") or ""), getattr(symbol, "size", None))
        return result

    def read_many(self, descriptors: list[SymbolDescriptor]) -> dict[str, Any]:
        if not descriptors:
            return {}
        connection = self._ensure()
        try:
            return {descriptor.path: connection.read_by_name(descriptor.path, descriptor.plc_type) for descriptor in descriptors}
        except Exception as err:
            self.close()
            raise BeckhoffAdsReadError(str(err)) from err

    def read(self, descriptor: SymbolDescriptor) -> Any:
        return self.read_many([descriptor]).get(descriptor.path)

    def write(self, descriptor: SymbolDescriptor, value: Any) -> None:
        if not descriptor.writable:
            raise BeckhoffAdsWriteError(f"Symbol is read-only: {descriptor.path}")
        connection = self._ensure()
        try:
            connection.write_by_name(descriptor.path, _coerce_value(value, descriptor.normalized_type), descriptor.plc_type)
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
        return value.lower() in {"1", "true", "on", "yes"} if isinstance(value, str) else bool(value)
    if plc_type == "STRING":
        return str(value)
    return float(value) if plc_type in {"REAL", "LREAL"} else int(value)
