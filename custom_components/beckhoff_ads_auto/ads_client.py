from __future__ import annotations

import logging
import re
import struct
import threading
from ctypes import create_string_buffer
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from functools import partial
from itertools import product
from typing import Any

import pyads
from pyads.constants import ADSIGRP_SYM_DT_UPLOAD, ADSIGRP_SYM_UPLOADINFO2, ADSIOFFS_DEVDATA_ADSSTATE

from .const import TYPE_MAPPING, TypeInfo
from .exceptions import BeckhoffAdsConnectionError, BeckhoffAdsReadError, BeckhoffAdsWriteError

_LOGGER = logging.getLogger(__name__)
_ADS_DATATYPE_ENTRY = struct.Struct("<8I5H")
_ADS_UPLOAD_INFO2_SIZE = 24

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

@dataclass(frozen=True, slots=True)
class DatatypeArrayInfo:
    lower_bound: int
    elements: int

@dataclass(frozen=True, slots=True)
class DatatypeEntry:
    name: str
    type_name: str
    comment: str
    size: int
    offset: int
    data_type: int
    flags: int
    array_info: tuple[DatatypeArrayInfo, ...] = ()
    sub_items: tuple["DatatypeEntry", ...] = ()

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
        self._datatype_cache: dict[str, DatatypeEntry] | None = None

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
                self._datatype_cache = None

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
        try:
            datatypes = self._get_all_datatypes(connection)
        except Exception:
            _LOGGER.debug("Unable to load ADS datatype metadata, keeping direct primitive discovery only", exc_info=True)
            datatypes = {}
        result: dict[str, SymbolDescriptor] = {}
        for symbol in symbols:
            path = str(getattr(symbol, "name", ""))
            if not path or not _is_under_roots(path, roots):
                continue
            raw_type = str(getattr(symbol, "symbol_type", "") or "")
            datatype = datatypes.get(_normalize_datatype_name(raw_type))
            kind = "primitive" if classify_type(raw_type) else "container" if datatype is not None else "unsupported"
            _LOGGER.debug(
                "ADS raw symbol path=%s type=%s size=%s read_only=%s kind=%s",
                path,
                raw_type,
                getattr(symbol, "size", None),
                bool(getattr(symbol, "read_only", False)),
                kind,
            )
            for descriptor in self._expand_symbol(symbol, datatypes, include, exclude, read_only, include_arrays):
                result[descriptor.path] = descriptor
        return result

    def _expand_symbol(
        self,
        symbol: Any,
        datatypes: dict[str, DatatypeEntry],
        include: str,
        exclude: str,
        read_only: str,
        include_arrays: bool,
    ) -> list[SymbolDescriptor]:
        path = str(getattr(symbol, "name", ""))
        if "[" in path and not include_arrays:
            return []
        raw_type = str(getattr(symbol, "symbol_type", "") or "")
        symbol_read_only = bool(getattr(symbol, "read_only", False))
        comment = str(getattr(symbol, "comment", "") or "")
        size = getattr(symbol, "size", None)
        info = classify_type(raw_type)
        if info is not None:
            descriptor = _build_descriptor(path, info, symbol_read_only, comment, size, include, exclude, read_only)
            return [descriptor] if descriptor is not None else []
        datatype_key = _normalize_datatype_name(raw_type)
        datatype = datatypes.get(datatype_key)
        if datatype is None:
            _LOGGER.debug("Skipping unsupported ADS symbol path=%s type=%s: datatype metadata not found", path, raw_type)
            return []
        expanded = list(
            _expand_datatype(
                path,
                datatype,
                datatypes,
                symbol_read_only,
                comment,
                size,
                include,
                exclude,
                read_only,
                include_arrays,
                seen={datatype_key},
            )
        )
        if not expanded:
            _LOGGER.debug("ADS container path=%s type=%s produced no supported primitive leaves", path, raw_type)
        return expanded

    def _get_all_datatypes(self, connection: pyads.Connection) -> dict[str, DatatypeEntry]:
        if self._datatype_cache is not None:
            return self._datatype_cache
        upload_info = connection.read(
            ADSIGRP_SYM_UPLOADINFO2,
            ADSIOFFS_DEVDATA_ADSSTATE,
            partial(create_string_buffer, _ADS_UPLOAD_INFO2_SIZE),
            return_ctypes=True,
        )
        upload_info_bytes = bytes(upload_info)
        if len(upload_info_bytes) < 16:
            self._datatype_cache = {}
            return self._datatype_cache
        datatype_count, datatype_size = struct.unpack_from("<II", upload_info_bytes, 8)
        if datatype_count <= 0 or datatype_size <= 0:
            self._datatype_cache = {}
            return self._datatype_cache
        datatype_buffer = connection.read(
            ADSIGRP_SYM_DT_UPLOAD,
            ADSIOFFS_DEVDATA_ADSSTATE,
            partial(create_string_buffer, datatype_size),
            return_ctypes=True,
        )
        entries, _ = _parse_datatype_entries(bytes(datatype_buffer), 0, datatype_count)
        self._datatype_cache = {_normalize_datatype_name(entry.name): entry for entry in entries if entry.name}
        return self._datatype_cache

    def read_many(self, descriptors: list[SymbolDescriptor]) -> dict[str, Any]:
        if not descriptors:
            return {}
        connection = self._ensure()
        try:
            return {
                descriptor.path: _normalize_value(connection.read_by_name(descriptor.path), descriptor.normalized_type)
                for descriptor in descriptors
            }
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
            connection.write_by_name(descriptor.path, _coerce_value(value, descriptor.normalized_type))
        except Exception as err:
            self.close()
            raise BeckhoffAdsWriteError(str(err)) from err

def _is_under_roots(path: str, roots: list[str]) -> bool:
    return any(path == root or path.startswith(root + ".") or path.startswith(root + "[") for root in roots)

def _normalize_datatype_name(value: Any) -> str:
    return str(value or "").strip().upper()

def _build_descriptor(
    path: str,
    info: TypeInfo,
    symbol_read_only: bool,
    comment: str,
    size: int | None,
    include: str,
    exclude: str,
    read_only: str,
) -> SymbolDescriptor | None:
    if include and not _matches(path, include):
        return None
    if exclude and _matches(path, exclude):
        return None
    forced_ro = bool(read_only and _matches(path, read_only))
    return SymbolDescriptor(path, info.plc_type, info, not (symbol_read_only or forced_ro), comment, size)

def _expand_datatype(
    path: str,
    datatype: DatatypeEntry,
    datatypes: dict[str, DatatypeEntry],
    symbol_read_only: bool,
    fallback_comment: str,
    size: int | None,
    include: str,
    exclude: str,
    read_only: str,
    include_arrays: bool,
    seen: set[str],
):
    if datatype.sub_items:
        for item in datatype.sub_items:
            child_path = f"{path}.{item.name}" if item.name else path
            yield from _expand_datatype_item(
                child_path,
                item,
                datatypes,
                symbol_read_only,
                fallback_comment,
                size,
                include,
                exclude,
                read_only,
                include_arrays,
                seen,
            )
        return
    yield from _expand_datatype_item(
        path,
        datatype,
        datatypes,
        symbol_read_only,
        fallback_comment,
        size,
        include,
        exclude,
        read_only,
        include_arrays,
        seen,
    )

def _expand_datatype_item(
    path: str,
    datatype: DatatypeEntry,
    datatypes: dict[str, DatatypeEntry],
    symbol_read_only: bool,
    fallback_comment: str,
    size: int | None,
    include: str,
    exclude: str,
    read_only: str,
    include_arrays: bool,
    seen: set[str],
):
    comment = datatype.comment or fallback_comment
    if datatype.array_info:
        if not include_arrays:
            _LOGGER.debug("Skipping ADS array leaf path=%s type=%s because include_arrays is disabled", path, datatype.type_name)
            return
        for indexed_path in _expand_array_paths(path, datatype.array_info):
            if datatype.sub_items:
                for item in datatype.sub_items:
                    yield from _expand_datatype_item(
                        f"{indexed_path}.{item.name}",
                        item,
                        datatypes,
                        symbol_read_only,
                        comment,
                        size,
                        include,
                        exclude,
                        read_only,
                        include_arrays,
                        seen,
                    )
                continue
            info = classify_type(datatype.type_name or datatype.name)
            if info is not None:
                descriptor = _build_descriptor(indexed_path, info, symbol_read_only, comment, size, include, exclude, read_only)
                if descriptor is not None:
                    yield descriptor
                continue
            yield from _expand_datatype_reference(
                indexed_path,
                datatype.type_name,
                datatypes,
                symbol_read_only,
                comment,
                size,
                include,
                exclude,
                read_only,
                include_arrays,
                seen,
            )
        return
    if datatype.sub_items:
        for item in datatype.sub_items:
            yield from _expand_datatype_item(
                f"{path}.{item.name}",
                item,
                datatypes,
                symbol_read_only,
                comment,
                size,
                include,
                exclude,
                read_only,
                include_arrays,
                seen,
            )
        return
    info = classify_type(datatype.type_name or datatype.name)
    if info is not None:
        descriptor = _build_descriptor(path, info, symbol_read_only, comment, size, include, exclude, read_only)
        if descriptor is not None:
            yield descriptor
        return
    yield from _expand_datatype_reference(
        path,
        datatype.type_name or datatype.name,
        datatypes,
        symbol_read_only,
        comment,
        size,
        include,
        exclude,
        read_only,
        include_arrays,
        seen,
    )

def _expand_datatype_reference(
    path: str,
    type_name: str,
    datatypes: dict[str, DatatypeEntry],
    symbol_read_only: bool,
    comment: str,
    size: int | None,
    include: str,
    exclude: str,
    read_only: str,
    include_arrays: bool,
    seen: set[str],
):
    key = _normalize_datatype_name(type_name)
    if key in seen:
        _LOGGER.debug("Skipping recursive ADS datatype expansion path=%s type=%s", path, type_name)
        return
    datatype = datatypes.get(key)
    if datatype is None:
        _LOGGER.debug("Skipping unsupported ADS leaf path=%s type=%s", path, type_name)
        return
    yield from _expand_datatype(
        path,
        datatype,
        datatypes,
        symbol_read_only,
        comment,
        size,
        include,
        exclude,
        read_only,
        include_arrays,
        seen | {key},
    )

def _expand_array_paths(path: str, array_info: tuple[DatatypeArrayInfo, ...]) -> list[str]:
    dimensions = [range(info.lower_bound, info.lower_bound + info.elements) for info in array_info]
    return [path + "".join(f"[{index}]" for index in indices) for indices in product(*dimensions)]

def _parse_datatype_entries(payload: bytes, offset: int, count: int) -> tuple[list[DatatypeEntry], int]:
    entries: list[DatatypeEntry] = []
    cursor = offset
    for _ in range(count):
        entry, cursor = _parse_datatype_entry(payload, cursor)
        entries.append(entry)
    return entries, cursor

def _parse_datatype_entry(payload: bytes, offset: int) -> tuple[DatatypeEntry, int]:
    if offset + _ADS_DATATYPE_ENTRY.size > len(payload):
        raise ValueError("ADS datatype payload truncated")
    (
        entry_length,
        version,
        hash_value,
        type_hash_value,
        size,
        entry_offset,
        data_type,
        flags,
        name_length,
        type_length,
        comment_length,
        array_dim,
        sub_items,
    ) = _ADS_DATATYPE_ENTRY.unpack_from(payload, offset)
    del version, hash_value, type_hash_value
    end = offset + entry_length
    if entry_length < _ADS_DATATYPE_ENTRY.size or end > len(payload):
        raise ValueError("ADS datatype entry length is invalid")
    cursor = offset + _ADS_DATATYPE_ENTRY.size
    name, cursor = _read_ads_string(payload, cursor, name_length)
    type_name, cursor = _read_ads_string(payload, cursor, type_length)
    comment, cursor = _read_ads_string(payload, cursor, comment_length)
    array_info: list[DatatypeArrayInfo] = []
    for _ in range(array_dim):
        if cursor + 8 > end:
            raise ValueError("ADS datatype array metadata truncated")
        lower_bound, elements = struct.unpack_from("<II", payload, cursor)
        array_info.append(DatatypeArrayInfo(lower_bound, elements))
        cursor += 8
    sub_item_entries: list[DatatypeEntry] = []
    for _ in range(sub_items):
        item, cursor = _parse_datatype_entry(payload, cursor)
        sub_item_entries.append(item)
    return (
        DatatypeEntry(name, type_name, comment, size, entry_offset, data_type, flags, tuple(array_info), tuple(sub_item_entries)),
        end,
    )

def _read_ads_string(payload: bytes, offset: int, expected_length: int) -> tuple[str, int]:
    end = offset + expected_length
    if end >= len(payload):
        raise ValueError("ADS datatype string truncated")
    value = payload[offset:end].decode("latin-1", errors="replace")
    return value, end + 1

def _normalize_value(value: Any, plc_type: str) -> Any:
    if value is None:
        return None
    if plc_type == "TIME":
        return str(timedelta(milliseconds=int(value)))
    if plc_type in {"TIME_OF_DAY", "TOD"}:
        total_ms = int(value)
        hours, remainder = divmod(total_ms, 3_600_000)
        minutes, remainder = divmod(remainder, 60_000)
        seconds, milliseconds = divmod(remainder, 1000)
        return time(hour=hours % 24, minute=minutes, second=seconds, microsecond=milliseconds * 1000).isoformat(timespec="milliseconds")
    if plc_type == "DATE":
        return (date(1970, 1, 1) + timedelta(days=int(value))).isoformat()
    if plc_type in {"DATE_AND_TIME", "DT"}:
        return datetime.fromtimestamp(int(value), tz=UTC).isoformat().replace("+00:00", "Z")
    return value

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
    if plc_type == "TIME":
        return _parse_duration_ms(value)
    if plc_type in {"TIME_OF_DAY", "TOD"}:
        return _parse_time_of_day_ms(value)
    if plc_type == "DATE":
        return _parse_date_days(value)
    if plc_type in {"DATE_AND_TIME", "DT"}:
        return _parse_datetime_seconds(value)
    return float(value) if plc_type in {"REAL", "LREAL"} else int(value)

def _parse_duration_ms(value: Any) -> int:
    if isinstance(value, timedelta):
        return int(value.total_seconds() * 1000)
    if isinstance(value, (int, float)):
        return int(value)
    text = str(value).strip()
    if ":" not in text:
        return int(float(text))
    days = 0
    if "day" in text:
        day_text, text = text.split(",", 1)
        days = int(day_text.split()[0])
        text = text.strip()
    hours, minutes, seconds = text.split(":")
    total_seconds = int(hours) * 3600 + int(minutes) * 60 + float(seconds)
    return int((days * 86400 + total_seconds) * 1000)

def _parse_time_of_day_ms(value: Any) -> int:
    if isinstance(value, (int, float)):
        return int(value)
    if isinstance(value, time):
        return ((value.hour * 3600 + value.minute * 60 + value.second) * 1000) + value.microsecond // 1000
    parsed = time.fromisoformat(str(value).strip())
    return ((parsed.hour * 3600 + parsed.minute * 60 + parsed.second) * 1000) + parsed.microsecond // 1000

def _parse_date_days(value: Any) -> int:
    if isinstance(value, (int, float)):
        return int(value)
    parsed = value if isinstance(value, date) and not isinstance(value, datetime) else date.fromisoformat(str(value).strip())
    return (parsed - date(1970, 1, 1)).days

def _parse_datetime_seconds(value: Any) -> int:
    if isinstance(value, (int, float)):
        return int(value)
    parsed = value if isinstance(value, datetime) else datetime.fromisoformat(str(value).strip().replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return int(parsed.timestamp())
