# BUSY Bar HTTP API — field notes

Verified against **firmware 1.2.3, API 27.5.0** (serial BB.1) on 2026-09-08.
The authoritative machine-readable spec is [`openapi.yaml`](openapi.yaml),
downloaded straight off the device (`curl http://10.0.4.20/openapi.yaml`).
Re-download it after a firmware update — it is the source of truth, these
notes only add what the spec leaves out.

## Connecting

| Transport | Base URL | Auth |
|---|---|---|
| USB ethernet | `http://10.0.4.20/api` | none |
| Wi-Fi LAN | `http://<device-ip>/api` | `X-API-Token: <password>` (enable in local web UI) |
| Cloud | `https://api.busy.app/busybar` | `Authorization: Bearer <token>` from cloud.busy.app/api-tokens |

Interactive Swagger UI lives on the device at <http://10.0.4.20/docs/>.

`/api/status/ws` and `/api/screen` are **local-only** — the cloud proxy lists
them but refuses the upgrade for every token.

## Displays

| Display | Value | Size | Notes |
|---|---|---|---|
| Front LED matrix | `"front"` / `display=0` | 72 x 16 | RGB |
| Back screen | `"back"` / `display=1` | 160 x 80 | greyscale |

## Drawing — `POST /api/display/draw`

Body is a `DisplayElements` object: `application_name` (required),
`elements` (required, >= 1), optional `priority` and `led_notification_color`.

Element types: `text`, `image`, `animation`, `countdown`, `rectangle`,
`xpmbitmap`. Every element needs `id` and `type`; the rest is per-type.

### Priority — the thing that silently breaks apps

`priority` is 1..100, default 50. A draw is accepted only when its priority
is **>=** the priority of the currently running system app:

| System app | Priority |
|---|---|
| stub / poweroff | 0 (always preemptable) |
| any standard built-in app | 10 |
| active BUSY / CUSTOM work session | 90 |

A losing request returns **HTTP 409**, not a silent no-op. So an app that
must survive a running work session needs `priority >= 90`. Equal-priority
requests from a *different* `application_name` override what is on screen.

### Element lifetime

`timeout` (seconds, 0 = forever) and `display_until` (Unix seconds) are
**mutually exclusive**. Without either, elements persist until cleared.

Redrawing an element with the same `id` updates it in place — that is the
cheap way to animate without flicker.

`DELETE /api/display/draw` clears. Body `{"application_name": ..., "element_ids": [...]}`;
omit `element_ids` to clear all of that app's elements. Always clear on exit,
or your elements linger on the device until reboot.

### Text

`text` must be **printable ASCII only** (`\x20`-`\x7E`) — the fonts are
bitmap ASCII, so no accents, em dashes or emoji. Colors are `#RRGGBBAA`
(8 hex digits — a 6-digit color is rejected).

Fonts: `tiny`, `small`, `normal`, `condensed`, `bold`, `large`,
`extra_large`, `global`. Measured metrics are in
[`font-metrics.md`](font-metrics.md). `global` follows the user's device
setting, so its size is not fixed — avoid it when layout must be exact.

Scrolling long text: set `width` plus `scroll_rate` (pixels per **minute**,
not per second), with optional `scroll_start_delay` / `scroll_repeat_delay`
in milliseconds.

### Positioning

`x` / `y` place the element's **anchor**, and `align` chooses which anchor:
`top_left`, `top_mid`, `top_right`, `mid_left`, `center`, `mid_right`,
`bottom_left`, `bottom_mid`, `bottom_right`. So centering on the front
display is `align: "center", x: 36, y: 8` — not `x: 0, y: 0`.

`z_index` orders overlapping elements, higher on top.

### `countdown` — a real clock, on-device

```json
{"id": "t", "type": "countdown", "timestamp": "1788480194",
 "direction": "time_left", "show_hours": "when_non_zero", "color": "#FFFFFFFF"}
```

`timestamp` is a Unix-seconds value **as a string**. `direction` is
`time_left` or `time_since`; `show_hours` is `when_non_zero` or `always`.
The firmware ticks it, so a countdown needs one request, not one per second.
It is driven by **device time** — sync it against `GET /api/time` (note `/api/time/timestamp` is POST-only, it *sets* the clock)
rather than the host clock, or the display will be off by the drift.

### `xpmbitmap` — arbitrary pixel art with no upload

Inline XPM2 text, so no asset round-trip. Limits: <= 32 colors, <= 4 chars
per pixel, and it must fit the target display.

```
! XPM2
3 2 2 1
a c #FF0000
b c none
aba
bab
```

## Assets and audio

`POST /api/assets/upload?application_name=<app>&file=<name>` with
`Content-Type: application/octet-stream` and the raw bytes as the body —
the filename is a **query parameter**, not multipart. Subdirectories in the
name are created automatically.

Audio plays `.snd` files: `POST /api/audio/play` with `application_name` and
either `path` (your asset) or `stock_path` (e.g. `shared/beep.snd`).
`busylib.converter.convert_for_storage()` converts wav/png/gif into the
device formats.

## The BUSY / CUSTOM timer — `PUT /api/busy/profiles/{slot}`

`slot` is `busy` or `custom` (not a number). A `SIMPLE` profile carries
`total_time_ms`, and **the API enforces no minimum** — a 45-second CUSTOM
profile is accepted, runs, and ends with the native "Well done!" screen, even
though the on-device UI will not let you dial below 5 minutes.

Tempting as a standalone short timer, but it is a *work session*, not a plain
countdown: it applies a theme, can trigger smart-home actions, and syncs to
the mobile app and cloud. `PUT` requires the full object, and
`profile_timestamp_ms` decides which copy wins when syncing — stamp it to now.
`tools/bb_timer.py` wraps this, including `backup` / `restore`.

The front display shows the theme during a session, not a countdown; the
remaining time and status live on the back screen.

## Reading the screen back — `GET /api/screen?display=N`

Undocumented quirk: the response advertises `Content-Type: image/bmp` but is
actually **base64 text of raw pixels** with no image header, and the two
displays use *different* formats:

| display | format | bytes |
|---|---|---|
| 0 (front, 72x16 RGB) | BGR888, 3 bytes/px | 3456 |
| 1 (back, 160x80 grey) | **4bpp packed, 2 px/byte**, high nibble first | 6400 |

Assuming BGR888 for the back display decodes to garbage (or a length error).
`busyplay.screen.screenshot()` handles both.

Allow **~0.3 s** after a draw before capturing, or you read the previous
frame. This makes a real verify loop possible: draw, capture, assert.

## Input

`POST /api/input?key=<key>` **injects** a press. Keys: `up`, `down`, `ok`,
`back`, `start`, `busy`, `custom`, `off`, `apps`, `settings`.

To **receive** physical input, use the `/api/status/ws` WebSocket: connect,
send `{"enable": true}`, then read protobuf `State` messages. Each
`StateUpdate` carries one of `device_name`, `power`, `brightness`,
`audio_volume`, `wifi`, `update_state`, `update_check`, `timezone`, `matter`,
`frame`, `input`, `timer`, `ble`, `auto_update_state`, `timer_profiles`.

`input` events are `BSB_Input.InputEvent`, a oneof of:

- `button_event` — `button` in {`OK`, `BACK`, `START`}, `action` in {`PRESS`, `RELEASE`}
- `switch_event` — `position` in {`BUSY`, `CUSTOM`, `OFF`, `APPS`, `SETTINGS`}
- `encoder_event` — `delta` (rotary, signed)

Note the stream exposes only OK/BACK/START as buttons, while `POST /api/input`
also accepts `up`/`down` and the switch positions.

The stream also pushes `frame` updates (~10/s, front display only), which is
a cheaper live mirror than polling `/api/screen`.

## `busylib` (Python) vs raw HTTP

`busylib` 2.0.2 pins `API_VERSION = "25.0.0"` while this device reports
27.5.0, so it prints *"Busy Lib is outdated for this device API"* on every
connect. Silence it with `BUSY_API_VERSION=27.5.0` in the environment —
but first confirm the methods you use still match the spec.

Its `DisplayElementType` covers `text`, `image`, `animation`, `countdown`,
`rectangle` — **not `xpmbitmap`**. For newer element types, post raw JSON.
That is why `busyplay.Device` is a thin HTTP client rather than a busylib
wrapper; `busylib` is still worth it for mDNS discovery, protobuf state
streaming and media conversion.
