from __future__ import annotations

from dataclasses import dataclass, field

from veemo.config import BackendSettings, DeviceSettings, DisplaySettings, LoggingSettings, Settings
from veemo.runner import VeemoRunner
from veemo.types import RenderResult


@dataclass
class FakeBackend:
    renders: list[RenderResult]
    heartbeat_calls: int = 0
    pending_actions: list[bool] = field(default_factory=list)
    runtime_modes: list[str] = field(default_factory=list)

    def ensure_device_token(self) -> str:
        return "token"

    def fetch_render(self) -> RenderResult:
        return self.renders.pop(0)

    def post_heartbeat(self) -> bool:
        self.heartbeat_calls += 1
        return True

    def set_runtime_mode(self, mode: str) -> bool:
        self.runtime_modes.append(mode)
        return True

    def has_pending_remote_action(self) -> bool:
        if not self.pending_actions:
            return False
        return self.pending_actions.pop(0)


@dataclass
class FakeDisplay:
    full_calls: int = 0
    fast_calls: int = 0

    def display_full(self, bmp_bytes: bytes) -> None:
        self.full_calls += 1

    def display_fast(self, bmp_bytes: bytes) -> None:
        self.fast_calls += 1


def make_settings() -> Settings:
    return Settings(
        backend=BackendSettings(),
        device=DeviceSettings(refresh_minutes=30, full_refresh_every=3),
        display=DisplaySettings(),
        logging=LoggingSettings(),
        config_path=None,  # type: ignore[arg-type]
    )


def make_render(digest: str, force_refresh: bool = False, refresh_override: int | None = None):
    return RenderResult(
        bmp_bytes=b"bmp",
        content_fallback=False,
        cache_hit=None,
        refresh_minutes_override=refresh_override,
        force_refresh=force_refresh,
        etag_or_digest=digest,
    )


def test_runner_skips_unchanged_frames():
    backend = FakeBackend([make_render("a"), make_render("a")])
    display = FakeDisplay()
    runner = VeemoRunner(settings=make_settings(), backend=backend, display=display)

    first = runner.run_once()
    second = runner.run_once()

    assert first.rendered is True
    assert second.skipped is True
    assert display.full_calls == 1
    assert display.fast_calls == 0


def test_runner_uses_periodic_full_refresh():
    backend = FakeBackend([make_render("a"), make_render("b"), make_render("c"), make_render("d")])
    display = FakeDisplay()
    runner = VeemoRunner(settings=make_settings(), backend=backend, display=display)

    runner.run_once()
    runner.run_once()
    runner.run_once()
    runner.run_once()

    assert display.full_calls == 2
    assert display.fast_calls == 2


def test_runner_applies_refresh_override_and_retries():
    backend = FakeBackend([make_render("a", refresh_override=45)])
    display = FakeDisplay()
    runner = VeemoRunner(settings=make_settings(), backend=backend, display=display)

    success = runner.run_once()
    failure = runner.run_once()

    assert success.refresh_minutes == 45
    assert runner.state.effective_refresh_minutes == 45
    assert failure.retry_delay_seconds == 5


def test_runner_wakes_early_for_pending_action(monkeypatch):
    backend = FakeBackend([make_render("a")], pending_actions=[False, True])
    display = FakeDisplay()
    runner = VeemoRunner(settings=make_settings(), backend=backend, display=display)

    current = {"value": 0.0}

    def fake_monotonic():
        return current["value"]

    def fake_sleep(seconds: float):
        current["value"] += seconds

    monkeypatch.setattr("veemo.runner.time.monotonic", fake_monotonic)
    monkeypatch.setattr("veemo.runner.time.sleep", fake_sleep)

    assert runner._sleep_until_next_poll(60) is True
    assert current["value"] == 5
