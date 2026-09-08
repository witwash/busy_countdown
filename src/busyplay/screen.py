"""Read what is actually on the BUSY Bar screen.

``GET /api/screen`` advertises ``Content-Type: image/bmp`` but in firmware
1.2.3 / API 27.5.0 it returns **base64-encoded raw BGR888 pixels** with no
image header: 72x16x3 bytes for the front display, 160x80x3 for the back.
This module decodes that into a Pillow image so a script can verify its own
output instead of guessing.
"""

from __future__ import annotations

import base64

from PIL import Image

from .device import BACK_H, BACK_W, FRONT_H, FRONT_W, Device

_SIZES = {0: (FRONT_W, FRONT_H), 1: (BACK_W, BACK_H)}


def screenshot(dev: Device, display: int = 0) -> Image.Image:
    """Capture a display. ``display``: 0 = front matrix, 1 = back screen."""
    if display not in _SIZES:
        raise ValueError("display must be 0 (front) or 1 (back)")
    width, height = _SIZES[display]
    raw = dev.request("GET", "/api/screen", params={"display": display}).content
    pixels = base64.b64decode(raw)
    expected = width * height * 3
    if len(pixels) != expected:
        raise ValueError(f"expected {expected} bytes of pixel data, got {len(pixels)}")
    # Wire order is BGR, not RGB.
    return Image.frombytes("RGB", (width, height), pixels, "raw", "BGR")


def save_png(img: Image.Image, path: str, scale: int = 8) -> str:
    """Save a screenshot upscaled with nearest-neighbour so pixels stay crisp."""
    if scale > 1:
        img = img.resize((img.width * scale, img.height * scale), Image.NEAREST)
    img.save(path)
    return path
