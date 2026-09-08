"""Inline pixel art with `xpmbitmap` — no asset upload, no round trip.

`busylib` 2.0.2 does not know this element type, which is why the playground
posts raw JSON instead of wrapping the library.

    uv run python examples/04_xpm_bitmap.py
"""

import time

from busyplay import Device, save_png, screenshot

HEART = """! XPM2
9 8 3 1
r c #FF0044
p c #FF88AA
. c none
.rr...rr.
rrrr.rrrr
rrrrrrrrr
rrrrrrrrr
.rrrrrrr.
..rrrrr..
...rrr...
....p....
"""

with Device(app="pixelart") as dev:
    dev.draw([
        {
            "id": "heart",
            "type": "xpmbitmap",
            "data": HEART,
            "align": "center",
            "x": 20,
            "y": 8,
            "display": "front",
            "timeout": 12,
        },
        {
            "id": "caption",
            "type": "text",
            "text": "PIXELS",
            "font": "normal",
            "color": "#FFCC00FF",
            "align": "mid_left",
            "x": 32,
            "y": 8,
            "display": "front",
            "timeout": 12,
        },
    ])

    time.sleep(0.35)
    print("saved", save_png(screenshot(dev), "scratch/04_xpm.png"))
    time.sleep(4)
    dev.clear()
