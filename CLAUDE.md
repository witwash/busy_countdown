# busy_countdown — BUSY Bar playground

A workbench for building custom apps for the BUSY Bar (72x16 RGB LED matrix
device). There is no plugin format on the device — an "app" is a program on
this machine that drives the bar over its HTTP API.

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

## Planned app

A turn timer for poker and board game sessions: track how long each player
takes on their turn. Arbitrary durations — no lower or upper bound (the
built-in timer will not go below 5 minutes, which is why this exists).
Not yet implemented.
