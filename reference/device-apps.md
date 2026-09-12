# On-device JavaScript apps

The BUSY Bar **does** have an app format. Apps installed into
`/ext/user_assets/` are enumerated by the firmware and listed in the **APPS
menu**, and run on-device with no host computer involved.

Sources, in order of authority:

- [`documentation/JavaScript Applications.dox.md`](https://github.com/busy-app/busybar-firmware/blob/dev/documentation/JavaScript%20Applications.dox.md)
  in the firmware repo — the file structure and manifest schema below are
  quoted from it.
- `applications/services/js_runner/` in the same repo — what the runtime
  actually exposes.
- The shipped example on the device itself:
  `/ext/user_assets/app.busy.js_example/`.

Note the public docs at <https://docs.busy.app/bar/dev> still say *"The SDK for
developing BUSY Bar apps (JS) is under development"* and
<https://docs.busy.app/bar/apps-and-integrations> says *"Support for installing
user apps on BUSY Bar is coming soon."* The mechanism works on firmware 1.2.3
but is unreleased, so treat it as subject to change across updates.

## File structure

```
/ext/user_assets
└── org.author.example_app          <- must equal manifest "id"
    ├── appmeta
    │   ├── manifest.json           REQUIRED
    │   ├── settings.json           optional ("to be decided" upstream)
    │   ├── icon_front_8x8.png      optional, 8x8 colour PNG
    │   └── icon_back_11x11.png     optional, 11x11 greyscale PNG
    └── scripts
        └── main.js                 REQUIRED — the entry point
```

Directory and file names are limited to 32 characters of `[a-zA-Z0-9._-]`;
the full path is capped at 256 characters. Extra directories (`resources`,
`images`, `sounds`, ...) are allowed. Additional `.js` files may sit beside
`main.js`.

## Manifest

Required: `format_version` (1), `id` (1-32 chars, must match the directory
name), `name` (shown in the menu), `version` (`MAJOR.MINOR.PATCH`).
Optional: `description`, `author`, `heap_size_kib` (1-256, default 32),
`debug` (default false).

**`debug: true` hides the app unless developer mode is enabled** — that is why
the shipped `app.busy.js_example` never appears in the APPS menu.

## What the JavaScript runtime provides

The interpreter is [JerryScript](https://jerryscript.net/). `js_runner.c`
registers exactly four things:

| Global | Provides |
|---|---|
| `console` | `log`, `info`, `error` (goes to the firmware log, not the screen) |
| timers | `setInterval`, `clearInterval`, `setTimeout`, `clearTimeout` |
| `fetch` | `fetch`, `Request`, `Headers`, streaming response bodies, `useDeviceKey` |
| `localStorage` | `getItem`, `setItem`, `removeItem`, `clear`, `key`, `length` — persists across launches |

Modern syntax works: `async`/`await`, promises, `for await`, template literals.

### BACK does not exit a running app (firmware 1.2.3)

`js_app_launcher_scene_run.c` handles the Back event like this:

```c
} else if(event->type == SceneManagerEventTypeBack) {
    // TODO: Special Back key treatment?
    consumed = true;
}
```

Returning `consumed = true` tells the scene manager the event was handled, so
the scene is never popped — **BACK does nothing at all while a JS app runs.**

Two ways out:

1. **Move the mode switch off APPS.** Works immediately, from the user's side.
2. **Let the script finish.** `app_has_background_tasks()` is
   `!script_evaluation_done || has_active_interval() || has_active_fetch()`.
   Clear your last interval and, once no fetch is in flight, `js_runner` fires
   its termination callback and the launcher pops back to the APPS menu. This
   is the only exit a script itself controls, so a long-running app should
   bound its own lifetime.

### The relaunch loop — why leaving an app puts you straight back in it

This is the one that actually traps you, and it looks like "BACK does nothing":
the screen blinks and the app is back.

Picking an app in the menu calls `apps_menu_set_active_application()`, which
writes the id into `/ext/apps_data/apps_menu/settings.json` and saves
**immediately**. When the launcher later exits, `apps_menu` is started again
with no argument, so `apps_menu_get_mode()` returns `AppsMenuModeResume`, and:

```c
} else if(apps_menu_has_active_application(&settings)) {
    if(apps_menu_start_application(settings.active_application, true)) {
        return NULL;   // relaunch; the menu is never drawn
    }
}
```

So the app restarts before the list is shown — one blink, and you are back in
the app with no way out.

Clearing the file from the host does not help, because launching the app from
the menu writes it again. **The app has to clear it itself at startup**, which
it can do over the storage HTTP API with `fetch` — read
`/api/storage/read?path=...`, set `active_application` to `""`, and POST it
back to `/api/storage/write?path=...`. `apps_menu` re-reads the file when it
comes back, and never rewrites it on exit, so the change sticks.
`apps/device/app.busy.countdown` does this in `releaseMenuResume()`.

Only `AppsMenuModeShowMenu` (argument `reset`) clears the setting on its own.

### The hard limit: no input, no direct drawing

There is **no JS binding for the buttons, encoder or switch**, and none for
the display either — `js_setup_*` covers only the four globals above, and
`js_app_launcher_scene_run.c` consumes the Back key itself rather than
forwarding it. A search of the firmware for any input binding returns nothing.

So an on-device app:

- draws by `fetch`-ing its own `POST /api/display/draw`, like a host app;
- **cannot react to a button press.** Launching it from the APPS menu is the
  only user input it will ever receive.

There is also no WebSocket in the runtime, so `/api/status/ws` — the only
channel that reports input — is unreachable from JS. Anything interactive has
to run on a host and talk to the device over HTTP.

## The APPS menu will not show your app until you enable JS apps

This is the one that will waste your afternoon. A correctly installed app is
**invisible** unless a flag file exists:

```
/ext/apps_data/apps_menu/js_apps_enabled
```

`apps_menu_is_js_apps_enabled()` just stats that path; if it is missing,
`apps_menu_scene_main_on_enter()` skips JS app enumeration entirely — no error,
no log line, the app simply is not there. Any non-directory file will do; the
contents are ignored.

The flag also changes the native list: with JS apps **off** the menu ends with
a **"Coming soon..."** entry, and with it **on** that entry is dropped and your
apps take its place. So "Coming soon..." disappearing is the visible signal
that the flag took effect.

There are two independent gates, easily confused:

| Gate | Controls | How to satisfy |
|---|---|---|
| `/ext/apps_data/apps_menu/js_apps_enabled` | whether **any** JS app is listed | create the file |
| manifest `debug: true` + `FuriHalNvmFlagDebug` | whether a **debug** app is listed | set `debug: false` |

The shipped `app.busy.js_example` is hidden by the second one.

## Installing

`tools/bb_app.py` wraps `/api/storage/{mkdir,write,list,remove}`:

```bash
uv run python tools/bb_app.py enable     # once per device — see above
uv run python tools/bb_app.py list
uv run python tools/bb_app.py install apps/device/app.busy.countdown
uv run python tools/bb_app.py remove app.busy.countdown
uv run python tools/bb_app.py logs --grep Countdown
```

The menu list is built in the scene's `on_enter`, so leaving the APPS menu and
re-entering picks up a newly installed app; no reboot needed.

## Seeing `console` output

`POST /api/log_dump?filename=X` snapshots the in-memory firmware log to
`/ext/X.txt`, which you can then read back. `js_app_launcher` routes a JS app's
`console.log` / `.info` / `.error` into that log, so this is the only way to
get output off an on-device app. `tools/bb_app.py logs` does the round trip.

## Quirks found on firmware 1.2.3

- `GET /api/storage/read` returns **400** for
  `/ext/user_assets/app.busy.js_example/appmeta/icon_back_11x11.png` even
  though it is listed and the sibling front icon reads fine. Writing a file of
  that name works, so it is a read-path quirk, not a naming restriction.
- The APPS menu is navigated with the **rotary encoder**, and `POST /api/input`
  cannot inject encoder rotation (`up`/`down` do nothing there). A menu
  selection cannot be automated from the host — it needs a human hand.
