# busy_countdown

Playground for building custom [BUSY Bar](https://docs.busy.app) apps in Python.

The device exposes a plain HTTP API — there is no plugin format and nothing
gets installed onto the bar. An app is just a script that draws to it.

```bash
uv sync
uv run python tools/bb.py status
uv run python examples/01_hello_text.py
uv run python apps/turn_timer.py --turn 45 --players 4
```

- `apps/turn_timer.py` — per-player turn timer for poker and board games:
  arbitrary turn lengths, overtime, and a per-player summary on exit
- `apps/device/app.busy.countdown` — runs **on** the bar from its APPS menu:
  a 3 min countdown that keeps counting once it runs over (JavaScript; the
  runtime has no button input — see `reference/device-apps.md`)
- `reference/` — the OpenAPI spec pulled off the device, plus measured notes
- `src/busyplay/` — small HTTP client and a screenshot decoder
- `examples/` — text, native countdown, shapes, inline pixel art, input
- `tools/` — `bb.py` CLI and the probes that generate the reference data

Two skills at `~/.claude/skills/` (`busybar-app`, `busybar-screen`) hold the
API and design knowledge for future projects. See `CLAUDE.md` for details.

Verified against firmware 1.2.3 / API 27.5.0 over USB at `10.0.4.20`.
