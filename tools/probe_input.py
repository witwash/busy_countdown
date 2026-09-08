"""Listen to the device state stream and print decoded input events.

Run it, then press OK / BACK / START, flip the mode switch, or turn the
encoder on the BUSY Bar. Useful for checking that a device can drive an app.
"""

from __future__ import annotations

import asyncio
import os
import sys

from busylib import AsyncBusyBar

DURATION = float(sys.argv[1]) if len(sys.argv) > 1 else 25.0
ADDR = os.environ.get("BUSY_BAR_ADDR", "10.0.4.20")


async def main() -> None:
    seen: dict[str, int] = {}
    events = 0
    print(f"listening {DURATION:.0f}s on {ADDR} — press buttons now", flush=True)
    async with AsyncBusyBar(ADDR) as bb:
        stream = bb.stream_status_ws()
        loop = asyncio.get_event_loop()
        end = loop.time() + DURATION
        while loop.time() < end:
            try:
                msg = await asyncio.wait_for(stream.__anext__(), timeout=end - loop.time())
            except (asyncio.TimeoutError, StopAsyncIteration):
                break
            if not isinstance(msg, dict):
                continue
            for update in msg.get("updates", []) or []:
                for key, value in update.items():
                    seen[key] = seen.get(key, 0) + 1
                    if "input" in key.lower():
                        events += 1
                        print("INPUT:", value, flush=True)
    print(f"\nupdate kinds seen: {seen}")
    print(f"input events: {events}")


if __name__ == "__main__":
    asyncio.run(main())
