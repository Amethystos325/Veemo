from __future__ import annotations

from pathlib import Path

import pytest

from veemo.config import load_settings


def test_load_settings_with_defaults_and_env_override(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    config_path = tmp_path / "veemo.toml"
    config_path.write_text(
        """
[backend]
kind = "inksight"

[device]
name = "kiosk"
""".strip()
    )
    monkeypatch.setenv("VEEMO_BACKEND_BASE_URL", "https://example.com/")
    monkeypatch.setenv("VEEMO_LOG_LEVEL", "debug")

    settings = load_settings(config_path)

    assert settings.backend.base_url == "https://example.com"
    assert settings.logging.level == "DEBUG"
    assert settings.device.name == "kiosk"
    assert settings.device.refresh_minutes == 30
    assert settings.display.width == 400


def test_load_settings_rejects_invalid_display_size(tmp_path: Path):
    config_path = tmp_path / "veemo.toml"
    config_path.write_text(
        """
[backend]
kind = "inksight"

[display]
width = 800
height = 480
""".strip()
    )

    with pytest.raises(ValueError, match="400x300"):
        load_settings(config_path)
