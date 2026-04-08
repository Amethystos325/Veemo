from __future__ import annotations

import importlib
import io
import logging
import sys
from dataclasses import dataclass
from pathlib import Path

from PIL import Image, UnidentifiedImageError

from .config import PROJECT_ROOT, DisplaySettings


LOGGER = logging.getLogger(__name__)
WAVESHARE_LIB_PATH = (
    PROJECT_ROOT / "platforms" / "raspberry3b+" / "examples" / "python" / "lib"
)


class DisplayError(RuntimeError):
    """Raised when display operations fail."""


@dataclass(slots=True)
class BmpFrame:
    image: Image.Image
    digest: str


class WaveshareEPD4in2V2Display:
    def __init__(self, settings: DisplaySettings):
        self.settings = settings
        self._driver_module = None
        self._epd = None
        self._initialized_mode: str | None = None

    def init(self) -> None:
        self._ensure_driver()
        LOGGER.info("Display driver ready for %sx%s", self.settings.width, self.settings.height)

    def display_full(self, bmp_bytes: bytes) -> None:
        image = self._load_bmp(bmp_bytes)
        epd = self._ensure_driver()
        LOGGER.info("Displaying full refresh frame (%s bytes)", len(bmp_bytes))
        epd.init()
        epd.display(epd.getbuffer(image))
        self._initialized_mode = "full"
        if self.settings.sleep_after_render:
            self.sleep()

    def display_fast(self, bmp_bytes: bytes) -> None:
        image = self._load_bmp(bmp_bytes)
        epd = self._ensure_driver()
        LOGGER.info("Displaying fast refresh frame (%s bytes)", len(bmp_bytes))
        epd.init_fast(epd.Seconds_1_5S)
        epd.display_Fast(epd.getbuffer(image))
        self._initialized_mode = "fast"
        if self.settings.sleep_after_render:
            self.sleep()

    def sleep(self) -> None:
        epd = self._ensure_driver()
        LOGGER.info("Putting display into sleep mode")
        epd.sleep()
        self._initialized_mode = None

    def close(self) -> None:
        if self._driver_module is None:
            return
        epdconfig = getattr(self._driver_module, "epdconfig", None)
        if epdconfig is None:
            return
        module_exit = getattr(epdconfig, "module_exit", None)
        if module_exit is None:
            return
        try:
            LOGGER.info("Closing display GPIO/SPI resources")
            module_exit(cleanup=True)
        except Exception as exc:
            LOGGER.warning("Display resource cleanup failed: %s", exc)
        finally:
            self._epd = None
            self._driver_module = None
            self._initialized_mode = None

    def _ensure_driver(self):
        if self._epd is not None:
            return self._epd
        if not WAVESHARE_LIB_PATH.exists():
            raise DisplayError(f"Waveshare library not found: {WAVESHARE_LIB_PATH}")
        lib_path = str(WAVESHARE_LIB_PATH)
        if lib_path not in sys.path:
            sys.path.insert(0, lib_path)
        try:
            self._driver_module = importlib.import_module("waveshare_epd.epd4in2_V2")
        except ModuleNotFoundError as exc:
            raise DisplayError(f"Failed to import Waveshare driver: {exc}") from exc
        self._epd = self._driver_module.EPD()
        LOGGER.debug("Loaded Waveshare driver from %s", WAVESHARE_LIB_PATH)
        return self._epd

    def _load_bmp(self, bmp_bytes: bytes) -> Image.Image:
        try:
            with Image.open(io.BytesIO(bmp_bytes)) as image:
                if image.format != "BMP":
                    raise DisplayError("Expected BMP image data")
                if image.size != (self.settings.width, self.settings.height):
                    raise DisplayError(
                        f"Expected {self.settings.width}x{self.settings.height} BMP, got {image.size[0]}x{image.size[1]}"
                    )
                converted = image.convert("1")
                converted.load()
                return converted
        except (UnidentifiedImageError, OSError) as exc:
            raise DisplayError(f"Failed to parse BMP image: {exc}") from exc
