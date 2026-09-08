"""Rectangles, z-index and a progress bar driven by same-id redraws.

Redrawing an element with the same `id` updates it in place, which is how you
animate without flicker or a clear-then-draw gap.

    uv run python examples/03_shapes_and_bar.py
"""

import time

from busyplay import Device

WIDTH = 72

with Device(app="shapes") as dev:
    for step in range(0, 21):
        pct = step / 20
        filled = max(1, round(WIDTH * pct))
        dev.draw([
            {
                "id": "track",
                "type": "rectangle",
                "x": 0, "y": 11, "width": WIDTH, "height": 3,
                "fill": "solid", "fill_colors": ["#202020FF"],
                "border_width": 0, "z_index": 0, "display": "front", "timeout": 30,
            },
            {
                "id": "fill",
                "type": "rectangle",
                "x": 0, "y": 11, "width": filled, "height": 3,
                "fill": "gradient_h", "fill_colors": ["#00AAFFFF", "#FF00AAFF"],
                "border_width": 0, "z_index": 1, "display": "front", "timeout": 30,
            },
            {
                "id": "label",
                "type": "text",
                "text": f"{int(pct * 100):3d}%",
                "font": "small",
                "color": "#FFFFFFFF",
                "align": "top_mid", "x": 36, "y": 1,
                "z_index": 2, "display": "front", "timeout": 30,
            },
        ])
        time.sleep(0.15)

    time.sleep(1)
    dev.clear()
