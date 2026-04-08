from __future__ import annotations

import re
import socket
import subprocess
import uuid
from dataclasses import dataclass
from pathlib import Path

from .config import DeviceSettings


MAC_RE = re.compile(r"^([0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2}$")
WIRELESS_PROC_PATH = Path("/proc/net/wireless")


@dataclass(slots=True)
class DeviceIdentity:
    mac: str
    device_name: str
    hostname: str


def normalize_mac(raw_mac: str) -> str:
    cleaned = raw_mac.strip().replace("-", ":").upper()
    if not MAC_RE.fullmatch(cleaned):
        raise ValueError(f"Invalid MAC address: {raw_mac}")
    return cleaned


def auto_detect_mac() -> str:
    detected = uuid.getnode()
    if (detected >> 40) % 2:
        raise RuntimeError("Could not determine a globally unique MAC address")
    mac = ":".join(f"{(detected >> shift) & 0xFF:02X}" for shift in range(40, -1, -8))
    return normalize_mac(mac)


def detect_wifi_rssi() -> int:
    proc_rssi = _read_proc_net_wireless_rssi()
    if proc_rssi is not None:
        return proc_rssi

    iw_rssi = _read_iw_signal_rssi()
    if iw_rssi is not None:
        return iw_rssi

    nmcli_rssi = _read_nmcli_signal_rssi()
    if nmcli_rssi is not None:
        return nmcli_rssi

    return 0


def detect_wifi_ssid() -> str:
    iwgetid_ssid = _read_iwgetid_ssid()
    if iwgetid_ssid:
        return iwgetid_ssid

    nmcli_ssid = _read_nmcli_ssid()
    if nmcli_ssid:
        return nmcli_ssid

    return ""


def _read_proc_net_wireless_rssi() -> int | None:
    if not WIRELESS_PROC_PATH.exists():
        return None
    try:
        lines = WIRELESS_PROC_PATH.read_text().splitlines()
    except OSError:
        return None

    for line in lines[2:]:
        if ":" not in line:
            continue
        _, metrics_raw = line.split(":", 1)
        metrics = metrics_raw.split()
        if len(metrics) < 3:
            continue
        level_raw = metrics[2].rstrip(".")
        try:
            return int(float(level_raw))
        except ValueError:
            continue
    return None


def _read_iw_signal_rssi() -> int | None:
    try:
        result = subprocess.run(
            ["iw", "dev"],
            check=False,
            capture_output=True,
            text=True,
        )
    except FileNotFoundError:
        return None
    if result.returncode != 0 or not result.stdout:
        return None
    match = re.search(r"signal:\s*(-?\d+)\s*dBm", result.stdout)
    if not match:
        return None
    return int(match.group(1))


def _read_nmcli_signal_rssi() -> int | None:
    try:
        result = subprocess.run(
            ["nmcli", "-t", "-f", "active,signal", "dev", "wifi"],
            check=False,
            capture_output=True,
            text=True,
        )
    except FileNotFoundError:
        return None
    if result.returncode != 0 or not result.stdout:
        return None
    for line in result.stdout.splitlines():
        if not line.startswith("yes:"):
            continue
        try:
            signal_percent = int(line.split(":", 1)[1])
        except ValueError:
            continue
        signal_percent = max(0, min(signal_percent, 100))
        return int(signal_percent / 2) - 100
    return None


def _read_iwgetid_ssid() -> str:
    try:
        result = subprocess.run(
            ["iwgetid", "-r"],
            check=False,
            capture_output=True,
            text=True,
        )
    except FileNotFoundError:
        return ""
    if result.returncode != 0:
        return ""
    return result.stdout.strip()


def _read_nmcli_ssid() -> str:
    try:
        result = subprocess.run(
            ["nmcli", "-t", "-f", "active,ssid", "dev", "wifi"],
            check=False,
            capture_output=True,
            text=True,
        )
    except FileNotFoundError:
        return ""
    if result.returncode != 0 or not result.stdout:
        return ""
    for line in result.stdout.splitlines():
        if not line.startswith("yes:"):
            continue
        return line.split(":", 1)[1].strip()
    return ""


def _run_command(command: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        check=False,
        capture_output=True,
        text=True,
    )


def _legacy_detect_wifi_rssi() -> int:
    commands = [
        ["iwgetid", "-r"],
        ["iw", "dev"],
    ]
    for command in commands:
        try:
            result = _run_command(command)
        except FileNotFoundError:
            continue
        if command[:2] == ["iwgetid", "-r"]:
            if result.returncode == 0 and result.stdout.strip():
                break
        else:
            if result.returncode != 0 or not result.stdout:
                continue
            match = re.search(r"signal:\s*(-?\d+)\s*dBm", result.stdout)
            if match:
                return int(match.group(1))
    return 0


def build_identity(device_settings: DeviceSettings) -> DeviceIdentity:
    mac = (
        normalize_mac(device_settings.mac_override)
        if device_settings.mac_override
        else auto_detect_mac()
    )
    hostname = socket.gethostname()
    return DeviceIdentity(mac=mac, device_name=device_settings.name, hostname=hostname)
