"""Minimal HTTP client for the BUSY Bar."""

from __future__ import annotations

import os
from typing import Any, Iterable

import requests

USB_ADDR = "10.0.4.20"
FRONT_W, FRONT_H = 72, 16
BACK_W, BACK_H = 160, 80


class DeviceError(RuntimeError):
    """The device rejected a request."""


class Device:
    """Talks to a BUSY Bar over the HTTP API.

    Address resolution order: explicit ``addr`` -> ``$BUSY_BAR_ADDR`` -> USB default.
    Set ``$BUSY_BAR_TOKEN`` for cloud access, or ``$BUSY_BAR_PASSWORD`` for a
    password-protected Wi-Fi LAN connection.
    """

    def __init__(
        self,
        addr: str | None = None,
        app: str = "playground",
        timeout: float = 5.0,
    ) -> None:
        addr = addr or os.environ.get("BUSY_BAR_ADDR") or USB_ADDR
        if not addr.startswith(("http://", "https://")):
            addr = f"http://{addr}"
        self.base = addr.rstrip("/")
        self.app = app
        self.timeout = timeout
        self.session = requests.Session()
        if token := os.environ.get("BUSY_BAR_TOKEN"):
            self.session.headers["Authorization"] = f"Bearer {token}"
        if password := os.environ.get("BUSY_BAR_PASSWORD"):
            self.session.headers["X-API-Token"] = password

    # -- plumbing ---------------------------------------------------------

    def request(self, method: str, path: str, **kw: Any) -> requests.Response:
        kw.setdefault("timeout", self.timeout)
        resp = self.session.request(method, f"{self.base}{path}", **kw)
        if not resp.ok:
            raise DeviceError(f"{method} {path} -> {resp.status_code}: {resp.text[:300]}")
        return resp

    def get(self, path: str, **kw: Any) -> Any:
        return self.request("GET", path, **kw).json()

    # -- system -----------------------------------------------------------

    def version(self) -> dict:
        return self.get("/api/version")

    def status(self) -> dict:
        return self.get("/api/status")

    def device_epoch(self) -> int:
        """Unix seconds according to the bar's RTC.

        `GET /api/time` returns ISO 8601 with an offset; `/api/time/timestamp`
        is POST-only (it sets the clock). Anchor `countdown` elements to this
        rather than the host clock so the display cannot drift from the device.
        """
        from datetime import datetime

        iso = self.get("/api/time")["timestamp"]
        return int(datetime.fromisoformat(iso).timestamp())

    def press(self, key: str) -> None:
        """Send a key press. One of: up down ok back start busy custom off apps settings."""
        self.request("POST", "/api/input", params={"key": key})

    # -- display ----------------------------------------------------------

    def draw(
        self,
        elements: Iterable[dict],
        priority: int = 50,
        led_color: str | None = None,
    ) -> None:
        """Draw elements on the display.

        Priority must beat the active system app: built-in apps sit at 10, an
        active BUSY/CUSTOM work session at 90. A losing request returns HTTP 409.
        """
        body: dict[str, Any] = {
            "application_name": self.app,
            "priority": priority,
            "elements": list(elements),
        }
        if led_color:
            body["led_notification_color"] = led_color
        self.request("POST", "/api/display/draw", json=body)

    def clear(self, element_ids: Iterable[str] | None = None) -> None:
        """Clear this app's elements, or just the named ones."""
        body: dict[str, Any] = {"application_name": self.app}
        if element_ids is not None:
            body["element_ids"] = list(element_ids)
        self.request("DELETE", "/api/display/draw", json=body)

    def brightness(self) -> Any:
        return self.get("/api/display/brightness")

    # -- storage ----------------------------------------------------------
    #
    # On-device JavaScript apps live in /ext/user_assets/<app_id>/ and are
    # picked up by the APPS menu. See reference/device-apps.md.

    def storage_list(self, path: str) -> list[dict]:
        return self.get("/api/storage/list", params={"path": path})["list"]

    def storage_read(self, path: str) -> bytes:
        return self.request("GET", "/api/storage/read", params={"path": path}).content

    def storage_write(self, path: str, data: bytes) -> None:
        self.request(
            "POST",
            "/api/storage/write",
            params={"path": path},
            headers={"Content-Type": "application/octet-stream"},
            data=data,
        )

    def storage_mkdir(self, path: str) -> None:
        """Create a directory. Succeeds quietly if it already exists."""
        try:
            self.request("POST", "/api/storage/mkdir", params={"path": path})
        except DeviceError as exc:
            if "400" not in str(exc):  # already exists reports 400
                raise

    def storage_remove(self, path: str) -> None:
        self.request("DELETE", "/api/storage/remove", params={"path": path})

    def storage_rmtree(self, path: str) -> None:
        """Depth-first delete: the device only removes empty directories."""
        for entry in self.storage_list(path):
            child = f"{path}/{entry['name']}"
            if entry["type"] == "dir":
                self.storage_rmtree(child)
            else:
                self.storage_remove(child)
        self.storage_remove(path)

    # -- assets and audio -------------------------------------------------

    def upload_asset(self, filename: str, data: bytes) -> None:
        """Upload raw bytes into this app's assets directory."""
        self.request(
            "POST",
            "/api/assets/upload",
            params={"application_name": self.app, "file": filename},
            headers={"Content-Type": "application/octet-stream"},
            data=data,
        )

    def delete_assets(self) -> None:
        self.request("DELETE", "/api/assets/upload", params={"application_name": self.app})

    def play(self, path: str | None = None, stock_path: str | None = None) -> None:
        body: dict[str, Any] = {"application_name": self.app}
        if path:
            body["path"] = path
        elif stock_path:
            body["stock_path"] = stock_path
        else:
            raise ValueError("pass path= or stock_path=")
        self.request("POST", "/api/audio/play", json=body)

    def stop_audio(self) -> None:
        self.request("DELETE", "/api/audio/play")

    # -- context manager --------------------------------------------------

    def __enter__(self) -> "Device":
        return self

    def __exit__(self, *exc: object) -> None:
        self.session.close()
