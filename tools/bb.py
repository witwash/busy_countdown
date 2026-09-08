"""Quick command line for poking at the BUSY Bar.

    uv run python tools/bb.py status
    uv run python tools/bb.py text "HELLO" --font large --color '#00FF88FF'
    uv run python tools/bb.py shot            # -> scratch/shot.png
    uv run python tools/bb.py clear [app]
    uv run python tools/bb.py press ok
    uv run python tools/bb.py ls /ext/apps_assets/shared/sounds
"""

from __future__ import annotations

import argparse
import json
import time

from busyplay import Device, save_png, screenshot


def main() -> None:
    ap = argparse.ArgumentParser(prog="bb", description=__doc__)
    ap.add_argument("--app", default="bb_cli", help="application_name to draw under")
    sub = ap.add_subparsers(dest="cmd", required=True)

    sub.add_parser("status")
    sub.add_parser("time")

    p = sub.add_parser("text")
    p.add_argument("text")
    p.add_argument("--font", default="normal")
    p.add_argument("--color", default="#FFFFFFFF")
    p.add_argument("--timeout", type=int, default=15)
    p.add_argument("--priority", type=int, default=50)

    p = sub.add_parser("shot")
    p.add_argument("--display", type=int, default=0, choices=[0, 1])
    p.add_argument("--out", default="scratch/shot.png")
    p.add_argument("--scale", type=int, default=8)

    p = sub.add_parser("clear")
    p.add_argument("app_name", nargs="?")

    p = sub.add_parser("press")
    p.add_argument("key")

    p = sub.add_parser("ls")
    p.add_argument("path")

    args = ap.parse_args()

    with Device(app=args.app) as dev:
        if args.cmd == "status":
            print(json.dumps(dev.status(), indent=2))
        elif args.cmd == "time":
            print(dev.get("/api/time"), "-> epoch", dev.device_epoch())
        elif args.cmd == "text":
            dev.draw(
                [{
                    "id": "cli", "type": "text", "text": args.text,
                    "font": args.font, "color": args.color,
                    "align": "center", "x": 36, "y": 8,
                    "display": "front", "timeout": args.timeout,
                }],
                priority=args.priority,
            )
            print(f"drawn for {args.timeout}s")
        elif args.cmd == "shot":
            time.sleep(0.35)
            img = screenshot(dev, args.display)
            lit = sum(1 for px in img.get_flattened_data() if px != (0, 0, 0))
            print(f"{lit}/{img.width * img.height} pixels lit")
            print("saved", save_png(img, args.out, args.scale))
        elif args.cmd == "clear":
            Device(app=args.app_name or args.app).clear()
            print("cleared", args.app_name or args.app)
        elif args.cmd == "press":
            dev.press(args.key)
            print("pressed", args.key)
        elif args.cmd == "ls":
            for entry in dev.get("/api/storage/list", params={"path": args.path})["list"]:
                print(f"{entry['type']:5} {entry['name']}")


if __name__ == "__main__":
    main()
