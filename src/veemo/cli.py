from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

import requests

from .backend import InksightCompatibleBackend
from .config import Settings, configure_logging, load_settings
from .display import DisplayError, WaveshareEPD4in2V2Display
from .identity import build_identity, detect_wifi_rssi, detect_wifi_ssid
from .runner import VeemoRunner


LOGGER = logging.getLogger(__name__)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Veemo InkSight-compatible client")
    parser.add_argument(
        "--config",
        type=Path,
        default=None,
        help="Path to veemo.toml",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("run", help="Run continuously")
    subparsers.add_parser("once", help="Fetch and display one frame")
    subparsers.add_parser("doctor", help="Run diagnostics")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    settings = load_settings(args.config)
    configure_logging(settings)

    identity = build_identity(settings.device)
    display = WaveshareEPD4in2V2Display(settings.display)
    backend = InksightCompatibleBackend(
        settings=settings.backend,
        device_settings=settings.device,
        display_settings=settings.display,
        identity=identity,
    )
    runner = VeemoRunner(settings=settings, backend=backend, display=display)

    if args.command == "doctor":
        try:
            return run_doctor(settings, identity, backend, display)
        finally:
            display.close()
    if args.command == "once":
        try:
            display.init()
            outcome = runner.run_once()
            runner._maybe_send_heartbeat()
            LOGGER.info(
                "Once command finished: rendered=%s skipped=%s reason=%s",
                outcome.rendered,
                outcome.skipped,
                outcome.reason,
            )
            return 0 if outcome.retry_delay_seconds is None else 1
        finally:
            display.close()
    if args.command == "run":
        try:
            display.init()
            backend.set_runtime_mode("active")
            runner.run_forever()
            return 0
        finally:
            backend.set_runtime_mode("interval")
            display.close()
    parser.error(f"Unsupported command: {args.command}")
    return 2


def run_doctor(settings: Settings, identity, backend, display) -> int:
    LOGGER.info("Config: %s", settings.config_path)
    LOGGER.info("Backend: %s", settings.backend.base_url)
    LOGGER.info("MAC: %s", identity.mac)
    LOGGER.info("Host: %s", identity.hostname)
    LOGGER.info("SSID: %s", detect_wifi_ssid() or "<unknown>")
    LOGGER.info("RSSI: %s", detect_wifi_rssi())
    if _check_backend_reachable(settings):
        LOGGER.info("Backend HTTP probe succeeded")
    else:
        LOGGER.error("Backend HTTP probe failed")
        return 1

    try:
        display.init()
        LOGGER.info("Display driver initialization succeeded")
    except DisplayError as exc:
        LOGGER.error("Display init failed: %s", exc)
        return 1

    try:
        token = backend.ensure_device_token()
        LOGGER.info("Backend token acquisition succeeded (%s chars)", len(token))
    except Exception as exc:
        LOGGER.error("Backend token acquisition failed: %s", exc)
        return 1
    return 0


def _check_backend_reachable(settings: Settings) -> bool:
    try:
        response = requests.get(
            settings.backend.base_url,
            timeout=settings.backend.request_timeout_seconds,
            allow_redirects=True,
        )
    except requests.RequestException as exc:
        LOGGER.error("Backend HTTP probe failed: %s", exc)
        return False
    LOGGER.info("Backend HTTP probe status: %s", response.status_code)
    return 200 <= response.status_code < 500


if __name__ == "__main__":
    sys.exit(main())
