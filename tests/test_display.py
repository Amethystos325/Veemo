from __future__ import annotations

import io

import pytest
from PIL import Image

from veemo.config import DisplaySettings
from veemo.display import DisplayError, WaveshareEPD4in2V2Display


def make_bmp(width: int, height: int) -> bytes:
    image = Image.new("1", (width, height), 1)
    buf = io.BytesIO()
    image.save(buf, format="BMP")
    return buf.getvalue()


def test_load_bmp_accepts_expected_dimensions():
    display = WaveshareEPD4in2V2Display(DisplaySettings())
    image = display._load_bmp(make_bmp(400, 300))
    assert image.size == (400, 300)


def test_load_bmp_rejects_dimension_mismatch():
    display = WaveshareEPD4in2V2Display(DisplaySettings())
    with pytest.raises(DisplayError, match="Expected 400x300"):
        display._load_bmp(make_bmp(200, 150))
