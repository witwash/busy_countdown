"""React to the physical buttons.

The `/api/status/ws` stream carries `input` events alongside frame and system
updates. Buttons report PRESS and RELEASE separately — act on one or you will
handle every press twice.

    uv run python examples/05_watch_input.py
"""

import asyncio
import os

from busylib import AsyncBusyBar

ADDR = os.environ.get("BUSY_BAR_ADDR", "10.0.4.20")


async def watch(seconds: float = 30.0) -> None:
    print(f"press OK / BACK / START, flip the switch or turn the encoder ({seconds:.0f}s)")
    async with AsyncBusyBar(ADDR) as bb:
        stream = bb.stream_status_ws()
        loop = asyncio.get_event_loop()
        end = loop.time() + seconds
        while loop.time() < end:
            try:
                msg = await asyncio.wait_for(stream.__anext__(), timeout=end - loop.time())
            except (asyncio.TimeoutError, StopAsyncIteration):
                break
            if not isinstance(msg, dict):
                continue
            for update in msg.get("updates", []) or []:
                event = update.get("input")
                if not event:
                    continue
                if button := event.get("button_event"):
                    if button.get("action") == "PRESS":
                        print("button:", button["button"])
                elif switch := event.get("switch_event"):
                    print("switch ->", switch.get("position"))
                elif encoder := event.get("encoder_event"):
                    print("encoder delta:", encoder.get("delta"))


if __name__ == "__main__":
    # Silences busylib's version warning: it pins API 25.0.0, device is 27.5.0.
    os.environ.setdefault("BUSY_API_VERSION", "27.5.0")
    asyncio.run(watch())
