from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(slots=True)
class RenderResult:
    bmp_bytes: bytes
    content_fallback: bool
    cache_hit: bool | None
    refresh_minutes_override: int | None
    force_refresh: bool
    etag_or_digest: str | None


class BackendAdapter(Protocol):
    def ensure_device_token(self) -> str: ...

    def fetch_render(self) -> RenderResult: ...

    def post_heartbeat(self) -> bool: ...
