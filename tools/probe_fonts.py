"""Measure the real pixel metrics of every BUSY Bar font.

Draws sample strings on the device and reads the framebuffer back, so the
numbers are observed rather than assumed. Writes reference/font-metrics.md.
"""

from __future__ import annotations

import time

from busyplay import Device, screenshot

FONTS = ["tiny", "small", "normal", "condensed", "bold", "large", "extra_large"]
SETTLE = 0.35


def ink_bbox(img):
    """Bounding box of non-black pixels, or None."""
    px = img.load()
    xs, ys = [], []
    for y in range(img.height):
        for x in range(img.width):
            if px[x, y] != (0, 0, 0):
                xs.append(x)
                ys.append(y)
    if not xs:
        return None
    return min(xs), min(ys), max(xs), max(ys)


def measure(dev: Device, font: str, text: str):
    dev.clear()
    dev.draw([{
        "id": "m", "type": "text", "text": text, "font": font,
        "color": "#FFFFFFFF", "align": "top_left", "x": 0, "y": 0,
        "display": "front", "timeout": 20,
    }])
    time.sleep(SETTLE)
    box = ink_bbox(screenshot(dev))
    dev.clear()
    return box


def main() -> None:
    rows = []
    with Device(app="fontprobe") as dev:
        for font in FONTS:
            digits = measure(dev, font, "8")
            eight = measure(dev, font, "88888888")
            caps = measure(dev, font, "ABCXYZ")
            low = measure(dev, font, "abcxyz")
            if not digits or not eight:
                rows.append((font, "-", "-", "-", "-", "did not render"))
                continue
            dw = digits[2] - digits[0] + 1
            dh = digits[3] - digits[1] + 1
            # 8 glyphs laid out end to end -> advance includes inter-glyph spacing
            advance = round((eight[2] - eight[0] + 1) / 8, 2)
            cap_h = (caps[3] - caps[1] + 1) if caps else 0
            has_lower = "yes" if low else "NO"
            fits = int(72 // advance)
            rows.append((font, f"{dw}x{dh}", advance, cap_h, fits, has_lower))

    lines = [
        "# BUSY Bar font metrics (measured)",
        "",
        "Measured on firmware 1.2.3 / API 27.5.0 by drawing to the front display",
        "(72x16) and reading the framebuffer back via `GET /api/screen`.",
        "Regenerate with `uv run python tools/probe_fonts.py`.",
        "",
        "| font | digit WxH | advance (px/char) | cap height | digits across 72px | lowercase |",
        "|---|---|---|---|---|---|",
    ]
    for font, dim, adv, cap, fits, low in rows:
        lines.append(f"| `{font}` | {dim} | {adv} | {cap} | {fits} | {low} |")
    lines += [
        "",
        "`global` is not listed: it follows the user's device-wide font setting,",
        "so its metrics are not fixed. Avoid it when layout must be exact.",
        "",
        "Advance is the average horizontal step per glyph for `8`, including",
        "inter-character spacing, so `advance * len(text)` estimates label width.",
    ]
    out = "reference/font-metrics.md"
    with open(out, "w") as fh:
        fh.write("\n".join(lines) + "\n")
    print("\n".join(lines))
    print(f"\nwrote {out}")


if __name__ == "__main__":
    main()
