# busy_countdown — BUSY Bar playground

A workbench for building custom apps for the BUSY Bar (72x16 RGB LED matrix
device). Two kinds of app are possible:

- **Host app** — a program on this machine driving the bar over its HTTP API.
  The only kind that can react to the buttons, encoder or switch.
- **On-device app** — JavaScript installed into `/ext/user_assets/`, listed in
  the device's APPS menu, running with no computer attached. The runtime has
  **no input binding**, so these cannot respond to button presses.
  See `reference/device-apps.md`.

## Skills

Two skills carry the domain knowledge and are installed **globally** at
`~/.claude/skills/`, so they apply in any future BUSY Bar project:

- **`busybar-app`** — the API, transports, priority, input, assets, debugging.
- **`busybar-screen`** — layout, fonts, what fits on 72x16, color, animation.

Load them before writing device code. They bundle their own reference copies;
the originals live in `reference/`.

## Layout

```
reference/openapi.yaml     spec pulled off the device — the source of truth
reference/api-notes.md     distilled behaviour + undocumented quirks
reference/font-metrics.md  font sizes measured on the real hardware
src/busyplay/              thin HTTP client + screenshot decoder
apps/turn_timer.py         the turn timer (host app: buttons + tracking)
apps/device/app.busy.countdown/  on-device JS app: 3 min countdown + overtime
reference/device-apps.md   the on-device app format and its limits
tools/bb_app.py            install / list / remove on-device apps
tools/bb_timer.py          set the native BUSY/CUSTOM timer to any duration
tools/bb.py                CLI: status, text, shot, clear, press, ls
tools/probe_fonts.py       regenerates font-metrics.md from the device
tools/probe_input.py       prints live button / switch / encoder events
examples/                  runnable, verified against the hardware
scratch/                   screenshots and throwaway output (gitignored)
```

## Running things

```bash
uv run python examples/01_hello_text.py
uv run python tools/bb.py status
```

Set `BUSY_API_VERSION=27.5.0` when using `busylib` directly — it pins 25.0.0
and warns otherwise. `busyplay` uses raw HTTP and is unaffected.

## Device

Verified against firmware **1.2.3 / API 27.5.0** over USB at `10.0.4.20`.
Override with `BUSY_BAR_ADDR`; `BUSY_BAR_TOKEN` (cloud) and
`BUSY_BAR_PASSWORD` (Wi-Fi) are read from the environment if set.

After a firmware update, re-pull the spec and re-measure:

```bash
curl -s http://10.0.4.20/openapi.yaml -o reference/openapi.yaml
uv run python tools/probe_fonts.py
```

## Conventions

- Always `clear()` on exit, including on Ctrl-C — untimed elements survive the
  process and stay on the device until reboot.
- Give every element a `timeout` as a dead-man switch.
- Verify visually rather than assuming: draw, wait ~0.3 s, capture
  `GET /api/screen`, look at the PNG.

## The turn timer — `apps/turn_timer.py`

Per-player turn clock for poker and board game sessions. Arbitrary durations,
no lower or upper bound — the built-in device timer will not go below 5
minutes, which is why this exists.

```bash
uv run python apps/turn_timer.py --turn 45 --players 4
uv run python apps/turn_timer.py --turn 1m30s --players Alice,Bob,Cara
```

| | device | terminal |
|---|---|---|
| start turn / pass to next player | `OK` | `Enter` |
| pause / resume | `START` | `p` |
| abort turn (records nothing) | `BACK` | `b` |
| change turn length, live | encoder | `+` / `-` |
| quit and print the summary | — | `q` / Ctrl-C |

Design decisions worth knowing before changing it:

- **Self-rendered digits, not the `countdown` element.** `countdown` cannot
  drift and costs one request, but it ignores `font` and renders 5px tall.
  Across a table that is unreadable, so the app pays ~2-3 requests/second for
  10px `extra_large` digits. Frames are diffed and only sent when the pixels
  would change, plus a 4s heartbeat to outrun the 10s element `timeout`.
- **`time.monotonic()` throughout.** Nothing is anchored to the device or
  host wall clock, so there is no drift to reconcile and recorded turn
  lengths survive a clock change.
- **Turns run into overtime rather than stopping** — the point is to measure
  how long people actually take. Expiry flashes red, fires the status LED
  once and plays `shared/sounds/calendar_reminder_ends.snd`.
- **Layout is 72x16.** Digits centred at `(36, 5)`, 3px bar at `y=13`, player
  tag top-left. The tag is dropped automatically when the clock string needs
  the full width (turn lengths of an hour or more) rather than clipping.
- Paused time is excluded from a player's recorded turn.

## The on-device countdown — `apps/device/app.busy.countdown` (SHELVED)

**Not installed on the device.** Kept as source to return to when the JS app
support in the firmware matures. Removed on firmware 1.2.3 because there is no
usable way to exit it — see below.

A JavaScript app that runs on the bar itself with no computer attached, listed
in the APPS menu. Open it and a 3:00 countdown starts; at zero it plays
`calendar_reminder_ends.snd` and keeps counting **up** as `+M:SS` so you can
see by how much you ran over. `DURATION_SECONDS` and `OVERTIME_LIMIT_SECONDS`
are constants at the top of `scripts/main.js`.

```bash
uv run python tools/bb_app.py enable    # once per device, or it stays invisible
uv run python tools/bb_app.py install apps/device/app.busy.countdown
uv run python tools/bb_app.py remove app.busy.countdown
```

Verified working: it appears in the APPS menu, runs, renders correctly on both
displays, and the logic is tested against stubs with JavaScriptCore
(`osascript -l JavaScript tools/test_device_countdown.js`, 39 assertions).

**Why it was pulled.** Three firmware-side problems, all in
`reference/device-apps.md` with the source that causes them:

1. The APPS menu hides JS apps unless
   `/ext/apps_data/apps_menu/js_apps_enabled` exists — no error, just absent.
2. Launching an app saves it as `active_application`, and the menu *resumes*
   it on next entry rather than listing apps, so leaving snaps straight back
   in. The app works around this by clearing the setting itself at startup.
3. **BACK still does not return to the menu even with (2) fixed** — tested on
   hardware. `js_app_launcher`'s run scene consumes the Back event without
   popping the scene (`// TODO: Special Back key treatment?`). The only exits
   are moving the mode switch off APPS, or the script finishing on its own.

The runtime also has **no input binding whatsoever** (`console`, timers,
`fetch`, `localStorage` and nothing else), so nothing interactive can ever be
an on-device app until the firmware adds one. Host apps like
`apps/turn_timer.py` remain the only way to read the buttons.
