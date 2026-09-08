# BUSY Bar font metrics (measured)

Measured on firmware 1.2.3 / API 27.5.0 by drawing to the front display
(72x16) and reading the framebuffer back via `GET /api/screen`.
Regenerate with `uv run python tools/probe_fonts.py`.

| font | digit WxH | advance (px/char) | cap height | digits across 72px | lowercase |
|---|---|---|---|---|---|
| `tiny` | 3x4 | 3.88 | 4 | 18 | yes |
| `small` | 3x5 | 3.88 | 5 | 18 | yes |
| `normal` | 5x7 | 5.88 | 7 | 12 | yes |
| `condensed` | 4x7 | 4.88 | 7 | 14 | yes |
| `bold` | 6x7 | 6.88 | 7 | 10 | yes |
| `large` | 6x9 | 6.88 | 9 | 10 | yes |
| `extra_large` | 7x10 | 7.88 | 10 | 9 | yes |

`global` is not listed: it follows the user's device-wide font setting,
so its metrics are not fixed. Avoid it when layout must be exact.

Advance is the average horizontal step per glyph for `8`, including
inter-character spacing, so `advance * len(text)` estimates label width.
