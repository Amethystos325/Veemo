from __future__ import annotations

from pathlib import Path

import pytest

from veemo.config import DeviceSettings
from veemo.identity import (
    _read_iwgetid_ssid,
    _read_nmcli_signal_rssi,
    _read_nmcli_ssid,
    _read_proc_net_wireless_rssi,
    auto_detect_mac,
    build_identity,
    detect_wifi_ssid,
    normalize_mac,
)


def test_build_identity_uses_mac_override():
    identity = build_identity(
        DeviceSettings(
            name="veemo-rpi",
            mac_override="aa-bb-cc-dd-ee-ff",
            refresh_minutes=30,
            full_refresh_every=10,
            skip_unchanged_frames=True,
        )
    )

    assert identity.mac == "AA:BB:CC:DD:EE:FF"


def test_auto_detect_mac_rejects_local_address(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr("veemo.identity.uuid.getnode", lambda: 0x030000000001)
    with pytest.raises(RuntimeError, match="globally unique"):
        auto_detect_mac()


def test_normalize_mac_rejects_bad_input():
    with pytest.raises(ValueError):
        normalize_mac("not-a-mac")


def test_read_proc_net_wireless_rssi(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    wireless = tmp_path / "wireless"
    wireless.write_text(
        "Inter-| sta-|   Quality        |   Discarded packets               | Missed | WE\n"
        " face | tus | link level noise |  nwid  crypt   frag  retry   misc | beacon | 22\n"
        " wlan0: 0000   70.  -42.  -256        0      0      0      0      0        0\n"
    )
    monkeypatch.setattr("veemo.identity.WIRELESS_PROC_PATH", wireless)

    assert _read_proc_net_wireless_rssi() == -42


def test_read_nmcli_signal_rssi(monkeypatch: pytest.MonkeyPatch):
    class Result:
        returncode = 0
        stdout = "yes:80\nno:30\n"

    monkeypatch.setattr("veemo.identity.subprocess.run", lambda *args, **kwargs: Result())

    assert _read_nmcli_signal_rssi() == -60


def test_detect_wifi_ssid_falls_back_to_nmcli(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr("veemo.identity._read_iwgetid_ssid", lambda: "")
    monkeypatch.setattr("veemo.identity._read_nmcli_ssid", lambda: "Astralink_Portal")

    assert detect_wifi_ssid() == "Astralink_Portal"
