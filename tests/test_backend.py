from __future__ import annotations

from dataclasses import dataclass

from veemo.backend import InksightCompatibleBackend
from veemo.config import BackendSettings, DeviceSettings, DisplaySettings
from veemo.identity import DeviceIdentity


@dataclass
class FakeResponse:
    status_code: int
    json_data: dict | None = None
    content: bytes = b""
    text: str = ""
    headers: dict[str, str] | None = None

    def json(self):
        if self.json_data is None:
            raise ValueError("No JSON")
        return self.json_data


class FakeSession:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def post(self, url, timeout=None, **kwargs):
        self.calls.append(("POST", url, kwargs))
        return self.responses.pop(0)

    def get(self, url, timeout=None, **kwargs):
        self.calls.append(("GET", url, kwargs))
        return self.responses.pop(0)


def make_backend(session: FakeSession) -> InksightCompatibleBackend:
    return InksightCompatibleBackend(
        settings=BackendSettings(),
        device_settings=DeviceSettings(),
        display_settings=DisplaySettings(),
        identity=DeviceIdentity(
            mac="AA:BB:CC:DD:EE:FF",
            device_name="veemo-rpi",
            hostname="pi",
        ),
        session=session,
    )


def test_ensure_device_token_reuses_cached_token():
    session = FakeSession([FakeResponse(200, json_data={"token": "abc123", "new": True})])
    backend = make_backend(session)

    assert backend.ensure_device_token() == "abc123"
    assert backend.ensure_device_token() == "abc123"
    assert len(session.calls) == 1


def test_fetch_render_parses_headers_and_retries_on_401(monkeypatch):
    session = FakeSession(
        [
            FakeResponse(200, json_data={"token": "old-token", "new": True}),
            FakeResponse(401, text="unauthorized", headers={}),
            FakeResponse(200, json_data={"token": "new-token", "new": False}),
            FakeResponse(
                200,
                content=b"BMP",
                headers={
                    "X-Content-Fallback": "1",
                    "X-Cache-Hit": "0",
                    "X-Refresh-Minutes": "45",
                    "X-Preview-Push": "true",
                    "ETag": "abc",
                },
            ),
        ]
    )
    monkeypatch.setattr("veemo.backend.detect_wifi_rssi", lambda: -55)
    backend = make_backend(session)

    result = backend.fetch_render()

    assert result.bmp_bytes == b"BMP"
    assert result.content_fallback is True
    assert result.cache_hit is False
    assert result.refresh_minutes_override == 45
    assert result.force_refresh is True
    assert result.etag_or_digest == "abc"
    assert len(session.calls) == 4


def test_post_heartbeat_retries_on_401(monkeypatch):
    session = FakeSession(
        [
            FakeResponse(200, json_data={"token": "old-token", "new": True}),
            FakeResponse(401, text="unauthorized"),
            FakeResponse(200, json_data={"token": "new-token", "new": False}),
            FakeResponse(200, json_data={"ok": True}),
        ]
    )
    monkeypatch.setattr("veemo.backend.detect_wifi_rssi", lambda: -40)
    backend = make_backend(session)

    assert backend.post_heartbeat() is True
    assert len(session.calls) == 4


def test_set_runtime_mode_retries_on_401():
    session = FakeSession(
        [
            FakeResponse(200, json_data={"token": "old-token", "new": True}),
            FakeResponse(401, text="unauthorized"),
            FakeResponse(200, json_data={"token": "new-token", "new": False}),
            FakeResponse(200, json_data={"ok": True, "runtime_mode": "active"}),
        ]
    )
    backend = make_backend(session)

    assert backend.set_runtime_mode("active") is True
    assert len(session.calls) == 4


def test_has_pending_remote_action_reads_device_state():
    session = FakeSession(
        [
            FakeResponse(200, json_data={"token": "token", "new": True}),
            FakeResponse(
                200,
                json_data={"runtime_mode": "active", "pending_refresh": 1, "pending_mode": ""},
            ),
        ]
    )
    backend = make_backend(session)

    assert backend.has_pending_remote_action() is True
    assert len(session.calls) == 2
