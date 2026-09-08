# busy_countdown

Playground for building custom [BUSY Bar](https://docs.busy.app) apps in Python.

The device exposes a plain HTTP API — there is no plugin format and nothing
gets installed onto the bar. An app is just a script that draws to it.

```bash
uv sync
uv run python tools/bb.py status
uv run python examples/01_hello_text.py
```

- `reference/` — the OpenAPI spec pulled off the device, plus measured notes
- `src/busyplay/` — small HTTP client and a screenshot decoder
- `examples/` — text, native countdown, shapes, inline pixel art, input
- `tools/` — `bb.py` CLI and the probes that generate the reference data

Two skills at `~/.claude/skills/` (`busybar-app`, `busybar-screen`) hold the
API and design knowledge for future projects. See `CLAUDE.md` for details.

Verified against firmware 1.2.3 / API 27.5.0 over USB at `10.0.4.20`.
