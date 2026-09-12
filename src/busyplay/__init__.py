"""Helpers for building and debugging custom BUSY Bar apps.

Thin layer over the BUSY Bar HTTP API. Uses raw HTTP rather than `busylib`
so that element types newer than the library (e.g. ``xpmbitmap``) still work.
"""

from .device import Device, DeviceError, FRONT_H, FRONT_W, BACK_H, BACK_W, USB_ADDR
from .screen import screenshot, save_png

__all__ = [
    "Device",
    "DeviceError",
    "screenshot",
    "save_png",
    "USB_ADDR",
    "FRONT_W",
    "FRONT_H",
    "BACK_W",
    "BACK_H",
]
