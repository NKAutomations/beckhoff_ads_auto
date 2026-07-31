from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from custom_components.beckhoff_ads_auto import coordinator as coordinator_module
from custom_components.beckhoff_ads_auto.const import (
    CONF_AMS_NET_ID,
    CONF_HOST,
    CONF_LOCAL_AMS_NET_ID,
    CONF_POLL_INTERVAL,
    CONF_PORT,
    CONF_ROOTS,
    CONF_TIMEOUT,
)


def test_coordinator_passes_local_ams_timeout_and_port(monkeypatch):
    calls = {}

    class FakeADSClient:
        def __init__(self, host, ams_net_id, port, local_ams_net_id=None, timeout=5.0):
            calls["args"] = (host, ams_net_id, port, local_ams_net_id, timeout)

    monkeypatch.setattr(coordinator_module, "ADSClient", FakeADSClient)

    entry = ConfigEntry(
        data={
            CONF_HOST: "192.168.178.27",
            CONF_AMS_NET_ID: "192.168.178.76.1.1",
            CONF_PORT: 851,
            CONF_ROOTS: "GVL_IOBroker",
            CONF_POLL_INTERVAL: 2.0,
        },
        options={
            CONF_LOCAL_AMS_NET_ID: "192.168.254.254.1.1",
            CONF_TIMEOUT: 7.5,
        },
        entry_id="entry-1",
    )

    coordinator = coordinator_module.ADSCoordinator(HomeAssistant(), entry)

    assert calls["args"] == (
        "192.168.178.27",
        "192.168.178.76.1.1",
        851,
        "192.168.254.254.1.1",
        7.5,
    )
    assert coordinator.roots == ["GVL_IOBroker"]
