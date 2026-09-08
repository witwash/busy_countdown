"""Draw text, then read the screen back to prove it rendered.

    uv run python examples/01_hello_text.py
"""

import time

from busyplay import Device, save_png, screenshot

with Device(app="hello") as dev:
    dev.draw([
        {
            "id": "greeting",
            "type": "text",
            "text": "HELLO",
            "font": "large",
            "color": "#FF00AAFF",
            "align": "center",
            "x": 36,
            "y": 8,
            "display": "front",
            "timeout": 10,
        }
    ])

    time.sleep(0.35)  # let the frame settle before capturing
    img = screenshot(dev)
    lit = sum(1 for px in img.get_flattened_data() if px != (0, 0, 0))
    print(f"{lit} pixels lit out of {img.width * img.height}")
    print("saved", save_png(img, "scratch/01_hello.png"))

    time.sleep(3)
    dev.clear()
