"""The native `countdown` element: one request, the firmware does the ticking.

Uses device time, not host time, so the display cannot drift from the bar.

    uv run python examples/02_countdown.py 90
"""

import sys
import time

from busyplay import Device

seconds = int(sys.argv[1]) if len(sys.argv) > 1 else 30

with Device(app="countdown_demo") as dev:
    now = dev.device_epoch()
    dev.draw(
        [
            {
                "id": "clock",
                "type": "countdown",
                "timestamp": str(now + seconds),
                "direction": "time_left",
                "show_hours": "when_non_zero",
                "color": "#00FF66FF",
                "font": "extra_large",
                "align": "center",
                "x": 36,
                "y": 8,
                "display": "front",
                "timeout": seconds + 2,
            }
        ]
    )
    print(f"counting down {seconds}s on the device — nothing else to send")
    time.sleep(min(seconds, 10))
    dev.clear()
