"""Turn timer for poker and board game sessions.

Counts down each player's turn on the front matrix, keeps running into
overtime instead of just stopping, and records how long every player actually
took. Turn lengths are arbitrary -- the built-in device timer will not go
below 5 minutes, which is the reason this exists.

    uv run python apps/turn_timer.py --turn 45 --players 4
    uv run python apps/turn_timer.py --turn 1m30s --players Alice,Bob,Cara

Controls (device buttons, or the terminal keys in brackets):

    OK      [Enter]  start the turn / end it and pass to the next player
    START   [p]      pause / resume
    BACK    [b]      abort the turn, back to idle (nothing recorded)
    encoder [+ / -]  change the turn length, takes effect immediately
                     [q]      quit and print the session summary

The screen is self-rendered rather than using the firmware `countdown`
element: `countdown` cannot drift and costs one request, but it ignores
`font` and always renders 5px tall. Across a table that is unreadable, so we
pay ~2-3 requests/second for 10px `extra_large` digits instead. Frames are
only sent when the pixels would actually change.
"""

from __future__ import annotations

import argparse
import asyncio
import math
import os
import re
import sys
import time
from dataclasses import dataclass, field

# busylib pins API 25.0.0 and warns against this device's 27.5.0. Set before
# the import so the check never sees the unset value.
os.environ.setdefault("BUSY_API_VERSION", "27.5.0")

from busyplay import Device, DeviceError  # noqa: E402

# --------------------------------------------------------------------------
# layout constants -- see reference/font-metrics.md
# --------------------------------------------------------------------------

FRONT_W = 72
DIGIT_FONT = "extra_large"  # 7x10 glyphs
DIGIT_ADVANCE = 7.88
TAG_FONT = "tiny"  # 3x4 glyphs
TAG_ADVANCE = 3.88

DIGIT_Y = 5  # `center` anchor -> glyphs occupy rows 0..10
BAR_Y = 13
BAR_H = 3

# Saturated primaries only; mid-greys turn to mush on discrete LEDs.
GREEN = "#00FF66FF"
AMBER = "#FFAA00FF"
RED = "#FF2200FF"
TRACK = "#181818FF"
TAG_COLOR = "#5588AAFF"
IDLE_COLOR = "#00FF6655"  # same green, de-emphasised with alpha
PAUSE_COLOR = "#00AAFFFF"
PAUSE_DIM = "#00AAFF33"
OFF = "#00000000"

ALERT_SOUND = "shared/sounds/calendar_reminder_ends.snd"
ALERT_LED = "#FF0000FF"

ELEMENT_TIMEOUT = 10  # dead-man switch: display self-clears if we die
HEARTBEAT = 4.0  # ...so redraw at least this often to keep it alive
TICK = 0.2

# --------------------------------------------------------------------------
# durations and formatting -- pure
# --------------------------------------------------------------------------

_DUR_PART = re.compile(r"(\d+(?:\.\d+)?)([hms]?)")
_UNITS = {"h": 3600.0, "m": 60.0, "s": 1.0, "": 1.0}


def parse_duration(text: str) -> float:
    """Accept ``45``, ``45s``, ``2m``, ``1m30s``, ``1:30`` or ``1:05:00``."""
    s = text.strip().lower()
    if not s:
        raise ValueError("empty duration")
    if ":" in s:
        total = 0.0
        for part in s.split(":"):
            total = total * 60 + float(part)
        return total
    total, consumed = 0.0, 0
    for match in _DUR_PART.finditer(s):
        if match.start() != consumed:
            break
        total += float(match.group(1)) * _UNITS[match.group(2)]
        consumed = match.end()
    if consumed != len(s):
        raise ValueError(f"cannot parse duration {text!r}")
    return total


def clock_style(duration: float) -> str:
    """Pick a width from the *turn length*, so the string cannot reflow mid-turn."""
    if duration >= 3600:
        return "hms"
    return "ms" if duration >= 60 else "s"


def format_clock(seconds: float, style: str) -> str:
    total = max(0, int(seconds))
    hours, rest = divmod(total, 3600)
    minutes, secs = divmod(rest, 60)
    if style == "hms":
        return f"{hours}:{minutes:02d}:{secs:02d}"
    if style == "ms":
        return f"{total // 60}:{total % 60:02d}"
    return str(total)


def format_span(seconds: float) -> str:
    """Human-readable duration for the terminal summary."""
    total = int(round(seconds))
    hours, rest = divmod(total, 3600)
    minutes, secs = divmod(rest, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes}:{secs:02d}"


def encoder_step(seconds: float) -> float:
    """Coarser steps for longer turns, so one flick is always ~useful."""
    if seconds < 60:
        return 5.0
    return 15.0 if seconds < 600 else 60.0


def player_tag(name: str) -> str:
    """Two or three printable-ASCII characters -- all that fits beside the digits."""
    clean = "".join(c for c in name.upper() if 0x20 <= ord(c) <= 0x7E).strip()
    return clean[:3] or "?"


# --------------------------------------------------------------------------
# state machine -- pure, no device calls, driven by a monotonic clock
# --------------------------------------------------------------------------

IDLE, RUNNING, PAUSED = "idle", "running", "paused"


@dataclass
class Turn:
    player: int
    seconds: float
    overtime: bool


@dataclass
class TurnTimer:
    players: list[str]
    turn_seconds: float
    index: int = 0
    state: str = IDLE
    started_at: float | None = None
    banked: float = 0.0  # elapsed accumulated before the current pause/resume
    log: list[Turn] = field(default_factory=list)

    # -- queries ----------------------------------------------------------

    @property
    def player(self) -> str:
        return self.players[self.index]

    def elapsed(self, now: float) -> float:
        if self.state == RUNNING and self.started_at is not None:
            return self.banked + (now - self.started_at)
        return self.banked if self.state == PAUSED else 0.0

    def remaining(self, now: float) -> float:
        """Seconds left; negative once the turn has run over."""
        return self.turn_seconds - self.elapsed(now)

    def is_overtime(self, now: float) -> bool:
        return self.state != IDLE and self.remaining(now) <= 0

    # -- transitions ------------------------------------------------------

    def start(self, now: float) -> None:
        self.state = RUNNING
        self.started_at = now
        self.banked = 0.0

    def advance(self, now: float) -> Turn:
        """Record the current turn, move to the next player, start their clock."""
        taken = self.elapsed(now)
        turn = Turn(self.index, taken, taken > self.turn_seconds)
        self.log.append(turn)
        self.index = (self.index + 1) % len(self.players)
        self.start(now)
        return turn

    def press_ok(self, now: float) -> Turn | None:
        if self.state == IDLE:
            self.start(now)
            return None
        return self.advance(now)

    def toggle_pause(self, now: float) -> None:
        if self.state == RUNNING:
            self.banked = self.elapsed(now)
            self.started_at = None
            self.state = PAUSED
        elif self.state == PAUSED:
            self.started_at = now
            self.state = RUNNING

    def abort(self) -> None:
        """Drop the current turn without recording it."""
        self.state = IDLE
        self.started_at = None
        self.banked = 0.0

    def adjust(self, delta_steps: int) -> None:
        step = encoder_step(self.turn_seconds)
        self.turn_seconds = max(step, self.turn_seconds + step * delta_steps)

    # -- reporting --------------------------------------------------------

    def summary(self) -> list[dict]:
        rows = []
        for i, name in enumerate(self.players):
            spans = [t.seconds for t in self.log if t.player == i]
            if not spans:
                continue
            rows.append(
                {
                    "player": name,
                    "turns": len(spans),
                    "total": sum(spans),
                    "avg": sum(spans) / len(spans),
                    "longest": max(spans),
                    "over": sum(1 for t in self.log if t.player == i and t.overtime),
                }
            )
        return rows


# --------------------------------------------------------------------------
# rendering -- pure: state in, display elements out
# --------------------------------------------------------------------------


def tag_fits(digits: str, tag: str) -> bool:
    """True when the player tag clears the centred digits at x=36."""
    left_free = FRONT_W / 2 - len(digits) * DIGIT_ADVANCE / 2
    return len(tag) * TAG_ADVANCE + 2 <= left_free


def urgency_color(remaining: float, duration: float) -> str:
    if remaining <= 5:
        return RED
    fraction = remaining / duration if duration > 0 else 0.0
    if fraction > 0.5:
        return GREEN
    return AMBER if fraction > 0.2 else RED


def build_elements(timer: TurnTimer, now: float) -> list[dict]:
    style = clock_style(timer.turn_seconds)
    remaining = timer.remaining(now)
    overtime = timer.is_overtime(now)

    if timer.state == IDLE:
        digits = format_clock(timer.turn_seconds, style)
        digit_color, bar_color, filled = IDLE_COLOR, IDLE_COLOR, FRONT_W
    elif overtime:
        over = -remaining
        digits = "+" + format_clock(over, clock_style(max(timer.turn_seconds, over)))
        # Flash at 2Hz: an expired turn has to interrupt a conversation.
        lit = int(now * 2) % 2 == 0
        digit_color = RED if lit else OFF
        bar_color, filled = (RED if lit else OFF), FRONT_W
    else:
        # ceil so the last whole second is displayed for a full second
        digits = format_clock(math.ceil(remaining - 1e-9), style)
        filled = max(1, round(FRONT_W * remaining / timer.turn_seconds))
        if timer.state == PAUSED:
            # Blink at 1Hz -- unmistakably "stopped" without stealing a row.
            digit_color = PAUSE_COLOR if int(now) % 2 == 0 else PAUSE_DIM
            bar_color = PAUSE_DIM
        else:
            digit_color = bar_color = urgency_color(remaining, timer.turn_seconds)

    elements = [
        {
            "id": "track",
            "type": "rectangle",
            "x": 0, "y": BAR_Y, "width": FRONT_W, "height": BAR_H,
            "fill": "solid", "fill_colors": [TRACK], "border_width": 0,
            "z_index": 0, "display": "front", "timeout": ELEMENT_TIMEOUT,
        },
        {
            "id": "bar",
            "type": "rectangle",
            # `width` has a minimum of 1 in the spec, so the bar bottoms out
            # at a 1px sliver rather than vanishing.
            "x": 0, "y": BAR_Y, "width": max(1, filled), "height": BAR_H,
            "fill": "solid", "fill_colors": [bar_color], "border_width": 0,
            "z_index": 1, "display": "front", "timeout": ELEMENT_TIMEOUT,
        },
        {
            "id": "digits",
            "type": "text",
            "text": digits, "font": DIGIT_FONT, "color": digit_color,
            "align": "center", "x": FRONT_W // 2, "y": DIGIT_Y,
            "z_index": 2, "display": "front", "timeout": ELEMENT_TIMEOUT,
        },
    ]

    tag = player_tag(timer.player)
    if tag_fits(digits, tag):
        elements.append(
            {
                "id": "tag",
                "type": "text",
                "text": tag, "font": TAG_FONT, "color": TAG_COLOR,
                "align": "top_left", "x": 0, "y": 0,
                "z_index": 2, "display": "front", "timeout": ELEMENT_TIMEOUT,
            }
        )
    else:
        # Turn lengths over an hour need all 72px for digits; the tag would
        # collide, so drop it rather than clip the clock.
        elements.append(
            {
                "id": "tag",
                "type": "text",
                "text": " ", "font": TAG_FONT, "color": OFF,
                "align": "top_left", "x": 0, "y": 0,
                "z_index": 2, "display": "front", "timeout": ELEMENT_TIMEOUT,
            }
        )
    return elements


# --------------------------------------------------------------------------
# driver
# --------------------------------------------------------------------------


class App:
    def __init__(self, timer: TurnTimer, dev: Device, priority: int, quiet: bool) -> None:
        self.timer = timer
        self.dev = dev
        self.priority = priority
        self.quiet = quiet
        self.stop = asyncio.Event()
        self._last_frame: list[dict] | None = None
        self._last_sent = 0.0
        self._alerted = False  # so the LED and sound fire once per turn

    # -- commands, shared by device buttons and terminal keys -------------

    def cmd_ok(self) -> None:
        turn = self.timer.press_ok(time.monotonic())
        self._alerted = False
        if turn is None:
            self.say(f"turn started: {self.timer.player}")
        else:
            flag = "  OVER" if turn.overtime else ""
            self.say(
                f"{self.timer.players[turn.player]} took {format_span(turn.seconds)}{flag}"
                f"  ->  {self.timer.player}"
            )

    def cmd_pause(self) -> None:
        if self.timer.state == IDLE:
            return
        self.timer.toggle_pause(time.monotonic())
        self.say("paused" if self.timer.state == PAUSED else "resumed")

    def cmd_back(self) -> None:
        if self.timer.state == IDLE:
            return
        self.timer.abort()
        self._alerted = False
        self.say(f"turn aborted, {self.timer.player} still to play")

    def cmd_adjust(self, steps: int) -> None:
        self.timer.adjust(steps)
        self.say(f"turn length {format_span(self.timer.turn_seconds)}")

    def say(self, message: str) -> None:
        if not self.quiet:
            print(message, flush=True)

    # -- loops ------------------------------------------------------------

    async def render_loop(self) -> None:
        while not self.stop.is_set():
            now = time.monotonic()
            frame = build_elements(self.timer, now)
            led = None

            if self.timer.is_overtime(now) and not self._alerted:
                self._alerted = True
                led = ALERT_LED
                await self._alert_sound()

            due = now - self._last_sent >= HEARTBEAT
            if frame != self._last_frame or due or led:
                try:
                    await asyncio.to_thread(
                        self.dev.draw, frame, priority=self.priority, led_color=led
                    )
                except DeviceError as exc:
                    self._report_draw_failure(exc)
                else:
                    self._last_frame, self._last_sent = frame, now

            try:
                await asyncio.wait_for(self.stop.wait(), timeout=TICK)
            except asyncio.TimeoutError:
                pass

    async def _alert_sound(self) -> None:
        try:
            await asyncio.to_thread(self.dev.play, None, ALERT_SOUND)
        except DeviceError as exc:
            self.say(f"(could not play alert sound: {exc})")

    def _report_draw_failure(self, exc: DeviceError) -> None:
        if "409" in str(exc):
            self.say(
                "draw rejected (409): a higher-priority app owns the screen -- "
                "a BUSY/CUSTOM work session sits at 90. Re-run with "
                "--priority 90 to sit alongside it."
            )
        else:
            self.say(f"draw failed: {exc}")

    async def device_input_loop(self, addr: str) -> None:
        """Physical buttons and encoder over the status WebSocket.

        Losing the stream must not take the timer down -- the terminal keys
        still work -- so reconnect quietly in the background.
        """
        from busylib import AsyncBusyBar

        while not self.stop.is_set():
            try:
                async with AsyncBusyBar(addr) as bar:
                    async for message in bar.stream_status_ws():
                        if self.stop.is_set():
                            return
                        if isinstance(message, dict):
                            self._handle_status(message)
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # noqa: BLE001 - any transport error retries
                if self.stop.is_set():
                    return
                self.say(f"(input stream lost: {exc}; retrying)")
                await asyncio.sleep(2.0)

    def _handle_status(self, message: dict) -> None:
        for update in message.get("updates") or []:
            event = update.get("input")
            if not event:
                continue
            if button := event.get("button_event"):
                # PRESS only -- acting on RELEASE too fires every press twice.
                if button.get("action") != "PRESS":
                    continue
                name = button.get("button")
                if name == "OK":
                    self.cmd_ok()
                elif name == "START":
                    self.cmd_pause()
                elif name == "BACK":
                    self.cmd_back()
            elif encoder := event.get("encoder_event"):
                if delta := encoder.get("delta"):
                    self.cmd_adjust(int(delta))

    def attach_terminal(self, loop: asyncio.AbstractEventLoop) -> bool:
        """Drive the timer from the keyboard as well, when stdin is a tty."""
        if not sys.stdin.isatty():
            return False

        def on_line() -> None:
            line = sys.stdin.readline()
            if line == "":  # EOF -- stop polling a dead stdin
                loop.remove_reader(sys.stdin.fileno())
                return
            key = line.strip().lower()
            if key == "":
                self.cmd_ok()
            elif key == "p":
                self.cmd_pause()
            elif key == "b":
                self.cmd_back()
            elif key in {"+", "="}:
                self.cmd_adjust(1)
            elif key == "-":
                self.cmd_adjust(-1)
            elif key == "q":
                self.stop.set()

        loop.add_reader(sys.stdin.fileno(), on_line)
        return True


def print_summary(timer: TurnTimer) -> None:
    rows = timer.summary()
    print()
    if not rows:
        print("no turns recorded")
        return
    print(f"{'player':<10}{'turns':>6}{'total':>9}{'avg':>8}{'longest':>9}{'over':>6}")
    for row in rows:
        print(
            f"{row['player'][:10]:<10}{row['turns']:>6}"
            f"{format_span(row['total']):>9}{format_span(row['avg']):>8}"
            f"{format_span(row['longest']):>9}{row['over']:>6}"
        )
    total = sum(r["total"] for r in rows)
    turns = sum(r["turns"] for r in rows)
    print(f"{'-' * 48}")
    print(
        f"{turns} turn{'' if turns == 1 else 's'}, {format_span(total)} of play, "
        f"turn length {format_span(timer.turn_seconds)}"
    )


def build_players(spec: str) -> list[str]:
    if spec.isdigit():
        count = int(spec)
        if count < 1:
            raise ValueError("need at least one player")
        return [f"P{i + 1}" for i in range(count)]
    names = [n.strip() for n in spec.split(",") if n.strip()]
    if not names:
        raise ValueError("no player names given")
    return names


async def main_async(args: argparse.Namespace) -> None:
    timer = TurnTimer(build_players(args.players), args.turn)
    addr = args.addr or os.environ.get("BUSY_BAR_ADDR") or "10.0.4.20"

    with Device(addr=addr, app=args.app) as dev:
        app = App(timer, dev, args.priority, args.quiet)
        loop = asyncio.get_running_loop()

        print(
            f"turn timer: {len(timer.players)} players "
            f"({', '.join(timer.players)}), {format_span(timer.turn_seconds)} per turn"
        )
        terminal = app.attach_terminal(loop)
        if terminal:
            print("keys: [Enter] next  [p] pause  [b] abort  [+/-] length  [q] quit")
        print("device: OK next / START pause / BACK abort / encoder length")

        tasks = [asyncio.create_task(app.render_loop())]
        if not args.no_input:
            tasks.append(asyncio.create_task(app.device_input_loop(addr)))
        try:
            await app.stop.wait()
        except asyncio.CancelledError:
            pass  # Ctrl-C: fall through and shut down cleanly
        finally:
            app.stop.set()
            if terminal:
                loop.remove_reader(sys.stdin.fileno())
            for task in tasks:
                task.cancel()
            try:
                await asyncio.gather(*tasks, return_exceptions=True)
            finally:
                # Elements outlive the process, so the clear has to happen
                # even if a second Ctrl-C lands during shutdown -- hence a
                # blocking call in an inner `finally`, not an await.
                try:
                    dev.clear()
                except DeviceError as exc:
                    print(f"warning: could not clear the display: {exc}")

    print_summary(timer)


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="turn_timer",
        description="Per-player turn timer for the BUSY Bar.",
    )
    parser.add_argument(
        "--turn", default="45",
        help="turn length: 45, 45s, 2m, 1m30s, 1:30 or 1:05:00 (default: 45)",
    )
    parser.add_argument(
        "--players", default="4",
        help="a player count (4) or names (Alice,Bob,Cara). Default: 4",
    )
    parser.add_argument("--app", default="turn_timer", help="application_name to draw under")
    parser.add_argument(
        "--priority", type=int, default=50,
        help="1-100; must beat the running system app. A BUSY work session is 90.",
    )
    parser.add_argument("--addr", help="device address (default: $BUSY_BAR_ADDR or 10.0.4.20)")
    parser.add_argument(
        "--no-input", action="store_true",
        help="skip the device WebSocket and use terminal keys only",
    )
    parser.add_argument("--quiet", action="store_true", help="only print the final summary")
    args = parser.parse_args()

    try:
        args.turn = parse_duration(args.turn)
    except ValueError as exc:
        parser.error(str(exc))
    if args.turn < 1:
        parser.error("turn length must be at least 1 second")
    try:
        build_players(args.players)
    except ValueError as exc:
        parser.error(str(exc))

    try:
        asyncio.run(main_async(args))
    except KeyboardInterrupt:
        # asyncio.run cancels main_async, whose `finally` clears the display.
        pass


if __name__ == "__main__":
    main()
