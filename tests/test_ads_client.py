from __future__ import annotations

import struct
from types import SimpleNamespace

from custom_components.beckhoff_ads_auto.ads_client import ADSClient, DatatypeArrayInfo, DatatypeEntry, SymbolDescriptor, _parse_datatype_entries, classify_type


class FakeConnection:
    def __init__(self, symbols=None, values=None):
        self.symbols = list(symbols or [])
        self.values = dict(values or {})
        self.read_calls = []
        self.write_calls = []

    def get_all_symbols(self):
        return list(self.symbols)

    def read_by_name(self, path, plc_datatype=None):
        self.read_calls.append((path, plc_datatype))
        return self.values[path]

    def write_by_name(self, path, value, plc_datatype=None):
        self.write_calls.append((path, value, plc_datatype))


def _symbol(name: str, symbol_type: str, *, read_only: bool = False, comment: str = "", size: int | None = None):
    return SimpleNamespace(name=name, symbol_type=symbol_type, read_only=read_only, comment=comment, size=size)


def _datatype(name: str, type_name: str = "", *, comment: str = "", size: int = 0, array_info=(), sub_items=()):
    return DatatypeEntry(name, type_name, comment, size, 0, 0, 0, tuple(array_info), tuple(sub_items))


def _discover(client: ADSClient, connection: FakeConnection, datatypes: dict[str, DatatypeEntry], **kwargs):
    client._ensure = lambda: connection
    client._get_all_datatypes = lambda _: datatypes
    return client.discover(["GVL_IOBroker"], **kwargs)


def _encode_datatype_entry(name: str, type_name: str, comment: str = "", *, array_info=(), sub_items=(), size: int = 0) -> bytes:
    dynamic = (
        name.encode("latin-1") + b"\x00"
        + type_name.encode("latin-1") + b"\x00"
        + comment.encode("latin-1") + b"\x00"
        + b"".join(struct.pack("<II", lower, elements) for lower, elements in array_info)
        + b"".join(sub_items)
    )
    header = struct.pack(
        "<8I5H",
        42 + len(dynamic),
        1,
        0,
        0,
        size,
        0,
        0,
        0,
        len(name),
        len(type_name),
        len(comment),
        len(array_info),
        len(sub_items),
    )
    return header + dynamic


def test_direct_primitive_discovery_preserved():
    client = ADSClient("192.168.178.27", "192.168.178.76.1.1", 851)
    connection = FakeConnection(
        symbols=[
            _symbol("GVL_IOBroker.bIOBrokerRX", "BOOL", comment="RX"),
            _symbol("MAIN.Other", "BOOL"),
        ]
    )

    discovered = _discover(client, connection, {})

    assert list(discovered) == ["GVL_IOBroker.bIOBrokerRX"]
    assert discovered["GVL_IOBroker.bIOBrokerRX"].comment == "RX"
    assert discovered["GVL_IOBroker.bIOBrokerRX"].info.boolean


def test_datatype_payload_parser_handles_nested_entries():
    nested = _encode_datatype_entry("NestedValue", "BOOL")
    container = _encode_datatype_entry("MY_DUT", "", sub_items=(nested,))

    entries, cursor = _parse_datatype_entries(container, 0, 1)

    assert cursor == len(container)
    assert entries[0].name == "MY_DUT"
    assert entries[0].sub_items[0].name == "NestedValue"
    assert entries[0].sub_items[0].type_name == "BOOL"


def test_nested_dut_expansion_and_time_date_normalization():
    client = ADSClient("192.168.178.27", "192.168.178.76.1.1", 851)
    connection = FakeConnection(
        symbols=[
            _symbol("GVL_IOBroker.MyDut", "MY_DUT"),
            _symbol("GVL_IOBroker.bDirect", "BOOL"),
        ],
        values={
            "GVL_IOBroker.MyDut.SomeBool": True,
            "GVL_IOBroker.MyDut.Nested.Counter": 5,
            "GVL_IOBroker.MyDut.Timestamp": 1_722_862_861,
            "GVL_IOBroker.bDirect": False,
        },
    )
    datatypes = {
        "MY_DUT": _datatype(
            "MY_DUT",
            sub_items=(
                _datatype("SomeBool", "BOOL"),
                _datatype("Nested", "MY_NESTED"),
                _datatype("Timestamp", "DT"),
            ),
        ),
        "MY_NESTED": _datatype("MY_NESTED", sub_items=(_datatype("Counter", "DINT"),)),
    }

    discovered = _discover(client, connection, datatypes)

    assert set(discovered) == {
        "GVL_IOBroker.MyDut.SomeBool",
        "GVL_IOBroker.MyDut.Nested.Counter",
        "GVL_IOBroker.MyDut.Timestamp",
        "GVL_IOBroker.bDirect",
    }

    values = client.read_many(list(discovered.values()))

    assert values["GVL_IOBroker.MyDut.Timestamp"].endswith("Z")
    assert connection.read_calls[0][1] is None


def test_unsupported_custom_type_logged_and_skipped(caplog):
    caplog.set_level("DEBUG")
    client = ADSClient("192.168.178.27", "192.168.178.76.1.1", 851)
    connection = FakeConnection(symbols=[_symbol("GVL_IOBroker.Unsupported", "MISSING_DUT")])

    discovered = _discover(client, connection, {})

    assert discovered == {}
    assert "datatype metadata not found" in caplog.text


def test_filters_and_array_option_apply_to_expanded_leaf_paths():
    client = ADSClient("192.168.178.27", "192.168.178.76.1.1", 851)
    connection = FakeConnection(symbols=[_symbol("GVL_IOBroker.Filtered", "FILTER_DUT")])
    datatypes = {
        "FILTER_DUT": _datatype(
            "FILTER_DUT",
            sub_items=(
                _datatype("Allowed", "BOOL"),
                _datatype("Blocked", "BOOL"),
                _datatype("ReadOnly", "DINT"),
                _datatype("ArrayValue", "INT", array_info=(DatatypeArrayInfo(1, 2),)),
            ),
        )
    }

    discovered = _discover(
        client,
        connection,
        datatypes,
        include="Allowed|ReadOnly|ArrayValue",
        exclude="Blocked",
        read_only=r"ReadOnly|ArrayValue\[2\]",
        include_arrays=True,
    )

    assert set(discovered) == {
        "GVL_IOBroker.Filtered.Allowed",
        "GVL_IOBroker.Filtered.ReadOnly",
        "GVL_IOBroker.Filtered.ArrayValue[1]",
        "GVL_IOBroker.Filtered.ArrayValue[2]",
    }
    assert discovered["GVL_IOBroker.Filtered.Allowed"].writable is True
    assert discovered["GVL_IOBroker.Filtered.ReadOnly"].writable is False
    assert discovered["GVL_IOBroker.Filtered.ArrayValue[1]"].writable is True
    assert discovered["GVL_IOBroker.Filtered.ArrayValue[2]"].writable is False

    no_arrays = _discover(client, connection, datatypes, include_arrays=False)
    assert "GVL_IOBroker.Filtered.ArrayValue[1]" not in no_arrays


def test_write_uses_runtime_type_lookup_for_time_values():
    client = ADSClient("192.168.178.27", "192.168.178.76.1.1", 851)
    connection = FakeConnection()
    client._ensure = lambda: connection
    descriptor = SymbolDescriptor("GVL_IOBroker.Delay", "TIME", classify_type("TIME"), True)

    client.write(descriptor, "01:02:03.004")

    assert connection.write_calls == [("GVL_IOBroker.Delay", 3_723_004, None)]
