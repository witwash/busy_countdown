"""Set the device's native BUSY / CUSTOM timer to an arbitrary duration.

The on-device UI will not let you pick a work timer shorter than 5 minutes,
but `PUT /api/busy/profiles/{slot}` has no such floor — a 45-second CUSTOM
profile is accepted and runs. That makes the bar a standalone short-turn
timer: flip the switch to CUSTOM, and the device's own buttons start, pause
and reset it, with the native end-of-session sound.

    uv run python tools/bb_timer.py show
    uv run python tools/bb_timer.py set custom 45s --title TURN
    uv run python tools/bb_timer.py backup  scratch/profiles
    uv run python tools/bb_timer.py restore scratch/profiles

Durations accept 45, 45s, 2m, 1m30s, 1:30 or 1:05:00.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "apps"))

from busyplay import Device, DeviceError  # noqa: E402
from turn_timer import format_span, parse_duration  # noqa: E402

SLOTS = ("busy", "custom")


def get_profile(dev: Device, slot: str) -> dict:
    return dev.get(f"/api/busy/profiles/{slot}")


def put_profile(dev: Device, slot: str, profile: dict) -> None:
    # The device keeps the newest profile when syncing, so stamp it now.
    profile["profile_timestamp_ms"] = int(time.time() * 1000)
    dev.request("PUT", f"/api/busy/profiles/{slot}", json=profile)


def describe(profile: dict) -> str:
    settings = profile.get("timer_settings", {})
    kind = settings.get("type")
    if kind == "SIMPLE":
        detail = format_span(settings["total_time_ms"] / 1000)
    elif kind == "INTERVAL":
        detail = (
            f"{format_span(settings['interval_work_ms'] / 1000)} work / "
            f"{format_span(settings['interval_rest_ms'] / 1000)} rest "
            f"x{settings['interval_work_cycles_count']}"
        )
    else:
        detail = "no limit"
    theme = profile.get("busy_bar_settings", {}).get("theme", "?")
    return f"{profile.get('title','?'):<10} {kind:<9} {detail:<28} theme={theme}"


def main() -> None:
    ap = argparse.ArgumentParser(prog="bb_timer", description=__doc__)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("show")

    p = sub.add_parser("set")
    p.add_argument("slot", choices=SLOTS)
    p.add_argument("duration", help="45s, 2m, 1m30s, 1:30 ...")
    p.add_argument("--title", help="name shown on the device")
    p.add_argument("--theme", help="e.g. chill_time, busy, on_air, flow")

    p = sub.add_parser("backup")
    p.add_argument("directory", type=Path)
    p = sub.add_parser("restore")
    p.add_argument("directory", type=Path)

    args = ap.parse_args()

    with Device(app="bb_timer") as dev:
        if args.cmd == "show":
            for slot in SLOTS:
                print(f"{slot:<8} {describe(get_profile(dev, slot))}")

        elif args.cmd == "set":
            seconds = parse_duration(args.duration)
            if seconds < 1:
                raise SystemExit("duration must be at least 1 second")
            profile = get_profile(dev, args.slot)
            profile["timer_settings"] = {
                "type": "SIMPLE",
                "total_time_ms": int(round(seconds * 1000)),
            }
            if args.title:
                profile["title"] = args.title
            if args.theme:
                profile["busy_bar_settings"]["theme"] = args.theme
            put_profile(dev, args.slot, profile)
            print(f"{args.slot}: {describe(get_profile(dev, args.slot))}")
            print(f"Flip the switch to {args.slot.upper()} to run it.")

        elif args.cmd == "backup":
            args.directory.mkdir(parents=True, exist_ok=True)
            for slot in SLOTS:
                path = args.directory / f"{slot}.json"
                path.write_text(json.dumps(get_profile(dev, slot), indent=2))
                print("saved", path)

        elif args.cmd == "restore":
            for slot in SLOTS:
                path = args.directory / f"{slot}.json"
                if not path.is_file():
                    print(f"skipping {slot}: no {path}")
                    continue
                put_profile(dev, slot, json.loads(path.read_text()))
                print(f"{slot}: {describe(get_profile(dev, slot))}")


if __name__ == "__main__":
    main()
