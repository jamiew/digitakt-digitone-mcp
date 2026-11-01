"""MIDI clock playback.

The six `play_pattern_*` tools in the old servers each reimplemented the same
clock loop with small variations. They're all expressible as "build a list of
scheduled events, then run one loop", which is what this module is.
"""

from __future__ import annotations

import asyncio
import contextlib
import math
import time
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from typing import Literal

import mido
from mcp.server.mcpserver.exceptions import ToolError

from elektron_mcp.midi import MidiConnection

PULSES_PER_BEAT = 24
"""MIDI clock resolution: 24 pulses per quarter note."""

PULSES_PER_BAR = PULSES_PER_BEAT * 4
"""96 pulses per bar, assuming 4/4."""

EventKind = Literal["note", "cc"]

Progress = Callable[[int, int], Awaitable[None]]
"""Called as `progress(bars_done, total_bars)` after each bar."""


def pulses(beat: float) -> int:
    """Convert a beat position (in quarter notes) to a clock pulse index."""
    return int(beat * PULSES_PER_BEAT)


def clock_interval(bpm: float) -> float:
    """Seconds between clock pulses at a given tempo."""
    return 60.0 / (bpm * PULSES_PER_BEAT)


@dataclass(frozen=True, slots=True)
class Event:
    """One scheduled MIDI event.

    `loop_pulses` makes the event repeat on that period instead of firing once,
    which is how looping patterns and looping automation are expressed.
    """

    pulse: int
    kind: EventKind
    channel: int
    # note events
    note: int = 0
    velocity: int = 100
    duration: float = 0.05
    # cc events
    control: int = 0
    value: int = 0
    loop_pulses: int | None = None

    @property
    def is_looping(self) -> bool:
        return self.loop_pulses is not None and self.loop_pulses > 0


def _check(label: str, value: int, low: int, high: int, offset: int = 0) -> None:
    # Checked while building events, before playback sends Start; mido would otherwise
    # raise mid-pattern with an error the client never sees.
    if not low <= value <= high:
        raise ToolError(f"{label} {value + offset} is out of range {low + offset}-{high + offset}")


def note_event(
    beat: float,
    note: int,
    velocity: int = 100,
    duration: float = 0.05,
    channel: int = 0,
    loop_pulses: int | None = None,
) -> Event:
    _check("Note", note, 0, 127)
    _check("Velocity", velocity, 0, 127)
    _check("MIDI channel", channel, 0, 15, offset=1)
    return Event(
        pulse=pulses(beat),
        kind="note",
        channel=channel,
        note=note,
        velocity=velocity,
        duration=duration,
        loop_pulses=loop_pulses,
    )


def cc_event(beat: float, control: int, value: int, channel: int = 0, loop_pulses: int | None = None) -> Event:
    _check("CC number", control, 0, 127)
    _check("CC value", value, 0, 127)
    _check("MIDI channel", channel, 0, 15, offset=1)
    return Event(
        pulse=pulses(beat),
        kind="cc",
        channel=channel,
        control=control,
        value=value,
        loop_pulses=loop_pulses,
    )


async def play(
    connection: MidiConnection,
    events: Sequence[Event],
    *,
    bars: float,
    bpm: float,
    send_start: bool = True,
    send_stop: bool = True,
    send_clock: bool = True,
    start_at_beat: float = 0.0,
    progress: Progress | None = None,
) -> None:
    """Run the clock for `bars` bars, firing `events` at their scheduled pulses.

    Timing is anchored to an absolute start time rather than accumulated sleeps,
    so pulses don't drift over a long pattern.
    """
    connection.require_output()

    interval = clock_interval(bpm)
    total_pulses = int(bars * PULSES_PER_BAR)
    total_bars = math.ceil(bars)
    start_pulse = pulses(start_at_beat)

    one_shots = sorted((e for e in events if not e.is_looping), key=lambda e: e.pulse)
    looping = [e for e in events if e.is_looping]

    started = False
    event_index = 0
    began_at = time.monotonic()

    try:
        for pulse_index in range(total_pulses):
            if not started and pulse_index >= start_pulse:
                if send_start:
                    # Song Position Pointer counts sixteenth notes, so 4 per beat.
                    if start_at_beat > 0:
                        connection.send(mido.Message("songpos", pos=int(start_at_beat * 4)))
                    connection.send(mido.Message("start"))
                    connection.log_transport("START")
                started = True

            if send_clock and started:
                connection.send(mido.Message("clock"))

            # `<=` so an event before the current pulse (e.g. a negative beat) fires
            # now instead of blocking every event after it.
            while event_index < len(one_shots) and one_shots[event_index].pulse <= pulse_index:
                _fire(connection, one_shots[event_index])
                event_index += 1

            for event in looping:
                assert event.loop_pulses is not None
                if pulse_index % event.loop_pulses == event.pulse % event.loop_pulses:
                    _fire(connection, event)

            deadline = began_at + (pulse_index + 1) * interval
            remaining = deadline - time.monotonic()
            if remaining > 0:
                await asyncio.sleep(remaining)

            if progress is not None and ((pulse_index + 1) % PULSES_PER_BAR == 0 or pulse_index + 1 == total_pulses):
                # Timing is anchored to began_at, so a slow notification doesn't push later pulses back.
                await progress(math.ceil((pulse_index + 1) / PULSES_PER_BAR), total_bars)
    except BaseException:
        # Cancelled by the client, or a send failed. Without a Stop the device sits
        # mid-pattern waiting for clock that will never come.
        if started and connection.output_port is not None:
            # If the port itself failed, this send fails too; keep the original error.
            with contextlib.suppress(Exception):
                connection.send(mido.Message("stop"))
                connection.log_transport("STOP (interrupted)")
        raise

    if send_stop and started:
        connection.send(mido.Message("stop"))
        connection.log_transport("STOP")


# asyncio only holds weak references to tasks, so a note-off scheduled and then
# forgotten can be garbage-collected before it runs — which leaves a stuck note.
_pending_note_offs: set[asyncio.Task] = set()


def _fire(connection: MidiConnection, event: Event) -> None:
    if event.kind == "note":
        connection.note_on(event.note, event.velocity, event.channel)
        task = asyncio.create_task(connection.note_off_after(event.note, event.duration, event.channel))
        _pending_note_offs.add(task)
        task.add_done_callback(_pending_note_offs.discard)
    else:
        connection.cc(event.control, event.value, event.channel)
