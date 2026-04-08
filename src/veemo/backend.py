from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass, field
from typing import Any

import requests

from .config import BackendSettings, DisplaySettings, DeviceSettings
from .identity import DeviceIdentity, detect_wifi_rssi
from .types import RenderResult


LOGGER = logging.getLogger(__name__)


class BackendError(RuntimeError):
    """Raised when the backend request cannot be completed."""


@dataclass(slots=True)
class InksightCompatibleBackend:
    settings: BackendSettings
    device_settings: DeviceSettings
    display_settings: DisplaySettings
    identity: DeviceIdentity
    session: requests.Session | Any | None = None
    voltage: float = 3.3
    _session: requests.Session | Any = field(init=False, repr=False)
    _device_token: str | None = field(init=False, default=None, repr=False)

    def __post_init__(self) -> None:
        self._session = self.session or requests.Session()

    def ensure_device_token(self) -> str:
        if self._device_token:
            LOGGER.debug("Reusing cached device token for %s", self.identity.mac)
            return self._device_token

        url = f"{self.settings.base_url}/api/device/{self.identity.mac}/token"
        LOGGER.info("Requesting device token from %s", url)
        response = self._post(url, json={})
        payload = self._json(response)
        token = str(payload.get("token", "")).strip()
        if not token:
            raise BackendError("Backend returned an empty device token")
        self._device_token = token
        LOGGER.info("Using device token for %s", self.identity.mac)
        return token

    def fetch_render(self) -> RenderResult:
        return self._fetch_render_with_retry(retry_on_401=True)

    def post_heartbeat(self) -> bool:
        try:
            self._post_heartbeat_with_retry(retry_on_401=True)
            return True
        except BackendError as exc:
            LOGGER.warning("Heartbeat failed: %s", exc)
            return False

    def _fetch_render_with_retry(self, retry_on_401: bool) -> RenderResult:
        rssi = detect_wifi_rssi()
        params = {
            "v": f"{self.voltage:.2f}",
            "mac": self.identity.mac,
            "rssi": str(rssi),
            "refresh_min": str(self.device_settings.refresh_minutes),
            "w": str(self.display_settings.width),
            "h": str(self.display_settings.height),
            "bpp": "1",
            "colors": "2",
        }
        url = f"{self.settings.base_url}/api/render"
        LOGGER.info(
            "Fetching render: mac=%s size=%sx%s refresh_min=%s rssi=%s",
            self.identity.mac,
            self.display_settings.width,
            self.display_settings.height,
            self.device_settings.refresh_minutes,
            rssi,
        )
        response = self._get(url, params=params, headers=self._auth_headers())
        if response.status_code == 401 and retry_on_401:
            LOGGER.warning("Render request returned 401, refreshing device token and retrying once")
            self._device_token = None
            self.ensure_device_token()
            return self._fetch_render_with_retry(retry_on_401=False)
        if response.status_code != 200:
            raise BackendError(
                f"Render request failed with status {response.status_code}: {response.text[:200]}"
            )
        bmp_bytes = response.content
        digest = response.headers.get("ETag")
        if not digest:
            digest = hashlib.sha256(bmp_bytes).hexdigest()
        result = RenderResult(
            bmp_bytes=bmp_bytes,
            content_fallback=_is_truthy_header(response.headers.get("X-Content-Fallback")),
            cache_hit=_parse_cache_hit(response.headers.get("X-Cache-Hit")),
            refresh_minutes_override=_parse_refresh_override(
                response.headers.get("X-Refresh-Minutes")
            ),
            force_refresh=_is_truthy_header(response.headers.get("X-Preview-Push")),
            etag_or_digest=digest,
        )
        LOGGER.info(
            "Render fetched: bytes=%s cache_hit=%s fallback=%s refresh_override=%s force_refresh=%s digest=%s",
            len(result.bmp_bytes),
            result.cache_hit,
            result.content_fallback,
            result.refresh_minutes_override,
            result.force_refresh,
            (result.etag_or_digest or "")[:16],
        )
        return result

    def _post_heartbeat_with_retry(self, retry_on_401: bool) -> None:
        url = f"{self.settings.base_url}/api/device/{self.identity.mac}/heartbeat"
        rssi = detect_wifi_rssi()
        payload = {
            "battery_voltage": self.voltage,
            "wifi_rssi": rssi,
        }
        LOGGER.info(
            "Posting heartbeat: mac=%s voltage=%.2f rssi=%s",
            self.identity.mac,
            self.voltage,
            rssi,
        )
        response = self._post(url, json=payload, headers=self._auth_headers())
        if response.status_code == 401 and retry_on_401:
            LOGGER.warning("Heartbeat returned 401, refreshing device token and retrying once")
            self._device_token = None
            self.ensure_device_token()
            self._post_heartbeat_with_retry(retry_on_401=False)
            return
        if response.status_code < 200 or response.status_code >= 300:
            raise BackendError(f"Heartbeat failed with status {response.status_code}")
        LOGGER.info("Heartbeat accepted with status %s", response.status_code)

    def _auth_headers(self) -> dict[str, str]:
        return {
            "X-Device-Token": self.ensure_device_token(),
            "Accept-Encoding": "identity",
        }

    def _get(self, url: str, **kwargs: Any):
        try:
            return self._session.get(url, timeout=self.settings.request_timeout_seconds, **kwargs)
        except requests.RequestException as exc:
            raise BackendError(f"GET {url} failed: {exc}") from exc

    def _post(self, url: str, **kwargs: Any):
        try:
            return self._session.post(url, timeout=self.settings.request_timeout_seconds, **kwargs)
        except requests.RequestException as exc:
            raise BackendError(f"POST {url} failed: {exc}") from exc

    @staticmethod
    def _json(response) -> dict[str, Any]:
        try:
            payload = response.json()
        except ValueError as exc:
            raise BackendError(f"Invalid JSON response: {exc}") from exc
        if not isinstance(payload, dict):
            raise BackendError("Expected a JSON object response")
        return payload


def _is_truthy_header(value: str | None) -> bool:
    return (value or "").strip().lower() in {"1", "true", "yes"}


def _parse_cache_hit(value: str | None) -> bool | None:
    if value is None:
        return None
    return _is_truthy_header(value)


def _parse_refresh_override(value: str | None) -> int | None:
    if not value:
        return None
    try:
        parsed = int(value)
    except ValueError:
        return None
    return parsed if parsed > 0 else None
