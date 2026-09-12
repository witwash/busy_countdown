"""Read what is actually on the BUSY Bar screen.

``GET /api/screen`` advertises ``Content-Type: image/bmp`` but in firmware
1.2.3 / API 27.5.0 it returns **base64-encoded raw pixels** with no image
header, and the two displays use different formats:

- front (72x16 RGB): BGR888, 3 bytes per pixel -> 3456 bytes
- back (160x80 greyscale): 4bpp packed, **two pixels per byte** -> 6400 bytes

This module decodes both into Pillow images so a script can verify its own
output instead of guessing.
"""

from __future__ import annotations

import base64

from PIL import Image

from .device import BACK_H, BACK_W, FRONT_H, FRONT_W, Device

_SIZES = {0: (FRONT_W, FRONT_H), 1: (BACK_W, BACK_H)}


def screenshot(dev: Device, display: int = 0) -> Image.Image:
    """Capture a display. ``display``: 0 = front matrix, 1 = back screen.

    The front comes back as RGB; the back is greyscale, returned as an ``L``
    image with the 4-bit levels scaled up to 0-255.
    """
    if display not in _SIZES:
        raise ValueError("display must be 0 (front) or 1 (back)")
    width, height = _SIZES[display]
    raw = dev.request("GET", "/api/screen", params={"display": display}).content
    pixels = base64.b64decode(raw)

    if display == 0:
        expected = width * height * 3
        if len(pixels) != expected:
            raise ValueError(f"expected {expected} bytes of pixel data, got {len(pixels)}")
        # Wire order is BGR, not RGB.
        return Image.frombytes("RGB", (width, height), pixels, "raw", "BGR")

    # Back screen: 4 bits per pixel, two pixels packed into each byte,
    # high nibble first. 160*80/2 = 6400 bytes.
    expected = width * height // 2
    if len(pixels) != expected:
        raise ValueError(f"expected {expected} bytes of pixel data, got {len(pixels)}")
    unpacked = bytearray(width * height)
    for i, byte in enumerate(pixels):
        unpacked[i * 2] = (byte >> 4) * 17  # 0-15 -> 0-255
        unpacked[i * 2 + 1] = (byte & 0x0F) * 17
    return Image.frombytes("L", (width, height), bytes(unpacked))


def save_png(img: Image.Image, path: str, scale: int = 8) -> str:
    """Save a screenshot upscaled with nearest-neighbour so pixels stay crisp."""
    if scale > 1:
        img = img.resize((img.width * scale, img.height * scale), Image.NEAREST)
    img.save(path)
    return path
