from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field

from .backend import BackendError
from .config import Settings
from .types import BackendAdapter, RenderResult


LOGGER = logging.getLogger(__name__)
RETRY_DELAYS_SECONDS = (5, 15, 30, 60, 120)
ACTIVE_POLL_INTERVAL_SECONDS = 5


@dataclass(slots=True)
class RunnerState:
    effective_refresh_minutes: int
    successful_refreshes: int = 0
    last_digest: str | None = None
    last_heartbeat_at: float = 0.0
    retry_index: int = 0
    first_frame_rendered: bool = False


@dataclass(slots=True)
class RenderOutcome:
    rendered: bool
    skipped: bool
    used_full_refresh: bool
    retry_delay_seconds: int | None = None
    refresh_minutes: int | None = None
    reason: str | None = None


@dataclass(slots=True)
class VeemoRunner:
    settings: Settings
    backend: BackendAdapter
    display: object
    state: RunnerState = field(init=False)

    def __post_init__(self) -> None:
        self.state = RunnerState(effective_refresh_minutes=self.settings.device.refresh_minutes)

    def run_forever(self) -> None:
        while True:
            outcome = self.run_once()
            self._maybe_send_heartbeat()
            if outcome.retry_delay_seconds is not None:
                LOGGER.info("Sleeping %ss before retry", outcome.retry_delay_seconds)
                time.sleep(outcome.retry_delay_seconds)
                continue
            refresh_minutes = outcome.refresh_minutes or self.state.effective_refresh_minutes
            sleep_seconds = max(refresh_minutes * 60, 1)
            LOGGER.info("Sleeping %ss until next poll", sleep_seconds)
            if self._sleep_until_next_poll(sleep_seconds):
                LOGGER.info("Remote action requested immediate refresh")
                continue

    def run_once(self) -> RenderOutcome:
        try:
            LOGGER.info("Starting render cycle")
            render = self.backend.fetch_render()
            outcome = self._handle_render(render)
            self.state.retry_index = 0
            if outcome.rendered:
                LOGGER.info(
                    "Render cycle complete: refresh=%s next_poll_min=%s",
                    "full" if outcome.used_full_refresh else "fast",
                    outcome.refresh_minutes,
                )
            elif outcome.skipped:
                LOGGER.info("Render cycle complete: frame skipped (%s)", outcome.reason)
            return outcome
        except Exception as exc:
            delay = self._next_retry_delay()
            LOGGER.warning("Render cycle failed: %s", exc)
            return RenderOutcome(
                rendered=False,
                skipped=False,
                used_full_refresh=False,
                retry_delay_seconds=delay,
                reason=str(exc),
            )

    def _handle_render(self, render: RenderResult) -> RenderOutcome:
        if render.refresh_minutes_override is not None:
            LOGGER.info(
                "Applying backend refresh override: %s min -> %s min",
                self.state.effective_refresh_minutes,
                render.refresh_minutes_override,
            )
            self.state.effective_refresh_minutes = render.refresh_minutes_override

        if (
            self.settings.device.skip_unchanged_frames
            and not render.force_refresh
            and self.state.last_digest
            and render.etag_or_digest == self.state.last_digest
        ):
            LOGGER.info("Skipping unchanged frame")
            return RenderOutcome(
                rendered=False,
                skipped=True,
                used_full_refresh=False,
                refresh_minutes=self.state.effective_refresh_minutes,
                reason="unchanged",
            )

        use_full_refresh = self._should_use_full_refresh()
        if use_full_refresh:
            self.display.display_full(render.bmp_bytes)
        else:
            self.display.display_fast(render.bmp_bytes)

        self.state.first_frame_rendered = True
        self.state.last_digest = render.etag_or_digest
        if use_full_refresh:
            self.state.successful_refreshes = 0
        else:
            self.state.successful_refreshes += 1

        return RenderOutcome(
            rendered=True,
            skipped=False,
            used_full_refresh=use_full_refresh,
            refresh_minutes=self.state.effective_refresh_minutes,
        )

    def _should_use_full_refresh(self) -> bool:
        if not self.state.first_frame_rendered:
            return True
        if not self.settings.display.fast_mode:
            return True
        return self.state.successful_refreshes >= (
            self.settings.device.full_refresh_every - 1
        )

    def _next_retry_delay(self) -> int:
        index = min(self.state.retry_index, len(RETRY_DELAYS_SECONDS) - 1)
        delay = RETRY_DELAYS_SECONDS[index]
        self.state.retry_index += 1
        return delay

    def _maybe_send_heartbeat(self) -> None:
        if not self.settings.backend.heartbeat_enabled:
            return
        now = time.monotonic()
        if now - self.state.last_heartbeat_at < self.settings.backend.heartbeat_interval_seconds:
            return
        if self.backend.post_heartbeat():
            self.state.last_heartbeat_at = now
            LOGGER.info("Heartbeat cycle complete")

    def _sleep_until_next_poll(self, sleep_seconds: int) -> bool:
        deadline = time.monotonic() + max(sleep_seconds, 0)
        while True:
            now = time.monotonic()
            remaining = deadline - now
            if remaining <= 0:
                return False
            self._maybe_send_heartbeat()
            if self.backend.has_pending_remote_action():
                return True
            time.sleep(min(ACTIVE_POLL_INTERVAL_SECONDS, remaining))
