from __future__ import annotations

import logging
import os
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG_PATH = PROJECT_ROOT / "veemo.toml"


@dataclass(slots=True)
class BackendSettings:
    kind: str = "inksight"
    base_url: str = "https://www.inksight.site"
    request_timeout_seconds: int = 30
    heartbeat_enabled: bool = True
    heartbeat_interval_seconds: int = 600


@dataclass(slots=True)
class DeviceSettings:
    name: str = "veemo-rpi"
    mac_override: str = ""
    refresh_minutes: int = 30
    full_refresh_every: int = 10
    skip_unchanged_frames: bool = True


@dataclass(slots=True)
class DisplaySettings:
    model: str = "waveshare_epd_4in2_v2"
    width: int = 400
    height: int = 300
    fast_mode: bool = True
    sleep_after_render: bool = False


@dataclass(slots=True)
class LoggingSettings:
    level: str = "INFO"


@dataclass(slots=True)
class Settings:
    backend: BackendSettings
    device: DeviceSettings
    display: DisplaySettings
    logging: LoggingSettings
    config_path: Path


def _read_toml(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"Config file not found: {path}")
    with path.open("rb") as handle:
        data = tomllib.load(handle)
    if not isinstance(data, dict):
        raise ValueError(f"Config root must be a TOML table: {path}")
    return data


def _merge_dataclass(cls, raw: dict[str, Any] | None):
    raw = raw or {}
    return cls(**raw)


def _normalize_base_url(url: str) -> str:
    normalized = url.strip().rstrip("/")
    if not normalized.startswith(("http://", "https://")):
        raise ValueError("backend.base_url must start with http:// or https://")
    return normalized


def load_settings(path: Path | None = None) -> Settings:
    config_path = path or Path(os.environ.get("VEEMO_CONFIG", DEFAULT_CONFIG_PATH))
    raw = _read_toml(config_path)

    backend = _merge_dataclass(BackendSettings, raw.get("backend"))
    device = _merge_dataclass(DeviceSettings, raw.get("device"))
    display = _merge_dataclass(DisplaySettings, raw.get("display"))
    logging_cfg = _merge_dataclass(LoggingSettings, raw.get("logging"))

    backend.base_url = _normalize_base_url(
        os.environ.get("VEEMO_BACKEND_BASE_URL", backend.base_url)
    )
    logging_cfg.level = os.environ.get("VEEMO_LOG_LEVEL", logging_cfg.level).upper()

    if backend.kind != "inksight":
        raise ValueError(f"Unsupported backend.kind: {backend.kind}")
    if backend.request_timeout_seconds <= 0:
        raise ValueError("backend.request_timeout_seconds must be > 0")
    if backend.heartbeat_interval_seconds <= 0:
        raise ValueError("backend.heartbeat_interval_seconds must be > 0")
    if device.refresh_minutes <= 0:
        raise ValueError("device.refresh_minutes must be > 0")
    if device.full_refresh_every <= 0:
        raise ValueError("device.full_refresh_every must be > 0")
    if display.model != "waveshare_epd_4in2_v2":
        raise ValueError(f"Unsupported display.model: {display.model}")
    if (display.width, display.height) != (400, 300):
        raise ValueError("Veemo v1 only supports a 400x300 display")
    if logging_cfg.level not in logging.getLevelNamesMapping():
        raise ValueError(f"Unsupported logging.level: {logging_cfg.level}")

    return Settings(
        backend=backend,
        device=device,
        display=display,
        logging=logging_cfg,
        config_path=config_path,
    )


def configure_logging(settings: Settings) -> None:
    logging.basicConfig(
        level=getattr(logging, settings.logging.level),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
