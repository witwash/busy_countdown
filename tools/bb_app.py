"""Install, list and remove on-device JavaScript apps.

The firmware enumerates `/ext/user_assets/<app_id>/` and lists what it finds
in the APPS menu. An app is a manifest, an entry script and optional icons —
see reference/device-apps.md for the format.

    uv run python tools/bb_app.py enable         # REQUIRED once per device
    uv run python tools/bb_app.py list
    uv run python tools/bb_app.py install apps/device/app.busy.countdown
    uv run python tools/bb_app.py remove app.busy.countdown
    uv run python tools/bb_app.py logs           # console.* output from a running app

`enable` creates /ext/apps_data/apps_menu/js_apps_enabled. The APPS menu checks
for that file and skips listing JS apps entirely when it is missing, so without
it a correctly installed app simply never appears.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

from busyplay import Device, DeviceError

USER_ASSETS = "/ext/user_assets"

# The APPS menu only enumerates JS apps when this file exists — see
# apps_menu_is_js_apps_enabled() in the firmware. Without it your app is
# installed correctly and still invisible.
JS_ENABLE_FLAG = "/ext/apps_data/apps_menu/js_apps_enabled"

# `^/ext(/[a-zA-Z0-9._\-]*)*$` per the storage API, and the app docs limit a
# directory name to 32 characters of the same alphabet.
NAME_RE = re.compile(r"^[a-zA-Z0-9._-]{1,32}$")
VERSION_RE = re.compile(r"^[0-9]+\.[0-9]+\.[0-9]+$")


def validate(app_dir: Path) -> dict:
    """Check the local app against the documented structure before uploading."""
    manifest_path = app_dir / "appmeta" / "manifest.json"
    entry = app_dir / "scripts" / "main.js"
    problems = []

    if not manifest_path.is_file():
        raise SystemExit(f"{app_dir}: missing appmeta/manifest.json")
    if not entry.is_file():
        raise SystemExit(f"{app_dir}: missing scripts/main.js (the entry point)")

    manifest = json.loads(manifest_path.read_text())
    for key in ("format_version", "id", "name", "version"):
        if key not in manifest:
            problems.append(f"manifest is missing required key {key!r}")

    app_id = manifest.get("id", "")
    if not NAME_RE.fullmatch(app_id):
        problems.append(f"id {app_id!r} must be 1-32 chars of [a-zA-Z0-9._-]")
    if app_id != app_dir.name:
        problems.append(f"id {app_id!r} must match the directory name {app_dir.name!r}")
    if not VERSION_RE.fullmatch(str(manifest.get("version", ""))):
        problems.append(f"version {manifest.get('version')!r} must be MAJOR.MINOR.PATCH")

    heap = manifest.get("heap_size_kib", 32)
    if not isinstance(heap, int) or not 1 <= heap <= 256:
        problems.append(f"heap_size_kib {heap!r} must be an integer 1-256")
    if manifest.get("debug"):
        problems.append("debug is true — the app is hidden unless developer mode is on")

    for path in sorted(app_dir.rglob("*")):
        rel = path.relative_to(app_dir)
        for part in rel.parts:
            if not NAME_RE.fullmatch(part):
                problems.append(f"path segment {part!r} in {rel} is not allowed on device")

    if problems:
        raise SystemExit("\n".join(f"{app_dir.name}: {p}" for p in problems))
    return manifest


def install(dev: Device, app_dir: Path) -> None:
    manifest = validate(app_dir)
    app_id = manifest["id"]
    root = f"{USER_ASSETS}/{app_id}"

    files = sorted(p for p in app_dir.rglob("*") if p.is_file())
    dirs = sorted({p.parent.relative_to(app_dir) for p in files})

    dev.storage_mkdir(root)
    for d in dirs:
        if str(d) != ".":
            dev.storage_mkdir(f"{root}/{d.as_posix()}")

    for path in files:
        rel = path.relative_to(app_dir).as_posix()
        data = path.read_bytes()
        dev.storage_write(f"{root}/{rel}", data)
        print(f"  {rel}  ({len(data)} bytes)")

    print(f"installed {manifest['name']!r} ({app_id}) to {root}")
    if js_apps_enabled(dev):
        print("Leave and re-enter the APPS menu — the list is built on entry.")
    else:
        print("WARNING: JS apps are disabled, so this will not appear in the")
        print("APPS menu. Run `bb_app enable` first.")


def remove(dev: Device, app_id: str) -> None:
    if not NAME_RE.fullmatch(app_id):
        raise SystemExit(f"bad app id {app_id!r}")
    dev.storage_rmtree(f"{USER_ASSETS}/{app_id}")
    print(f"removed {app_id}")


def list_apps(dev: Device) -> None:
    try:
        entries = dev.storage_list(USER_ASSETS)
    except DeviceError as exc:
        raise SystemExit(f"cannot list {USER_ASSETS}: {exc}")
    state = "enabled" if js_apps_enabled(dev) else "DISABLED — run `bb_app enable`"
    print(f"JS apps in the APPS menu: {state}\n")
    found = False
    for entry in entries:
        if entry["type"] != "dir":
            continue
        path = f"{USER_ASSETS}/{entry['name']}/appmeta/manifest.json"
        try:
            manifest = json.loads(dev.storage_read(path))
        except (DeviceError, ValueError):
            print(f"{entry['name']:<28} (no readable manifest — not an app)")
            continue
        found = True
        flags = " [debug: hidden unless developer mode]" if manifest.get("debug") else ""
        print(f"{manifest.get('id', entry['name']):<28} {manifest.get('name','?')} "
              f"v{manifest.get('version','?')}{flags}")
    if not found:
        print("(no installed apps)")


def js_apps_enabled(dev: Device) -> bool:
    try:
        entries = dev.storage_list("/ext/apps_data/apps_menu")
    except DeviceError:
        return False
    name = JS_ENABLE_FLAG.rsplit("/", 1)[1]
    return any(e["name"] == name and e["type"] == "file" for e in entries)


def set_js_apps_enabled(dev: Device, enabled: bool) -> None:
    if enabled:
        dev.storage_write(JS_ENABLE_FLAG, b"1")
        print("JS apps enabled in the APPS menu.")
        print("Leave the APPS menu and re-enter it — the list is built on entry.")
        print("The 'Coming soon...' entry is replaced by your apps when this is on.")
    else:
        try:
            dev.storage_remove(JS_ENABLE_FLAG)
        except DeviceError:
            pass
        print("JS apps hidden from the APPS menu again.")


def logs(dev: Device, pattern: str | None, lines: int) -> None:
    """Snapshot the device log buffer and print it.

    A JS app's `console.log/info/error` is routed to the firmware log by
    js_app_launcher, so this is how you see output from an on-device app.
    """
    path = dev.request("POST", "/api/log_dump", params={"filename": "bb_app"}).json()["path"]
    text = dev.storage_read(path).decode("utf-8", "replace")
    dev.storage_remove(path)

    # Strip the ANSI colouring the firmware writes into the buffer.
    plain = re.sub(r"\x1b\[[0-9;]*m", "", text)
    selected = [ln for ln in plain.splitlines() if pattern is None or pattern.lower() in ln.lower()]
    for line in selected[-lines:]:
        print(line)
    if not selected:
        print(f"(no lines matching {pattern!r})")


def main() -> None:
    ap = argparse.ArgumentParser(prog="bb_app", description=__doc__)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("list")
    sub.add_parser("enable", help="let the APPS menu show installed JS apps")
    sub.add_parser("disable", help="hide JS apps from the APPS menu again")

    p = sub.add_parser("logs", help="console output from a running on-device app")
    p.add_argument("--grep", default="Js", help="substring filter (default: Js)")
    p.add_argument("--lines", type=int, default=40)
    p.add_argument("--all", action="store_true", help="do not filter")
    p = sub.add_parser("install")
    p.add_argument("app_dir", type=Path)
    p = sub.add_parser("remove")
    p.add_argument("app_id")
    args = ap.parse_args()

    with Device(app="bb_app") as dev:
        if args.cmd == "list":
            list_apps(dev)
        elif args.cmd == "install":
            install(dev, args.app_dir)
        elif args.cmd == "remove":
            remove(dev, args.app_id)
        elif args.cmd == "enable":
            set_js_apps_enabled(dev, True)
        elif args.cmd == "disable":
            set_js_apps_enabled(dev, False)
        elif args.cmd == "logs":
            logs(dev, None if args.all else args.grep, args.lines)


if __name__ == "__main__":
    main()
