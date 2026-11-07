"""Live playback events and seamless background pattern playback.

Adapted from koii studio's events and player modules:
https://github.com/benjaminr/mcp-koii
Copyright (c) 2025 Benjamin Rowell, used under the MIT License.
See THIRD_PARTY_NOTICES.md.
"""

from __future__ import annotations

import threading
import time
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Protocol, cast

import mido

from elektron_mcp.pattern_language import Section, timeline


class _NoteMessage(Protocol):
    type: str
    channel: int
    note: int
    velocity: int


_SPIN_SECONDS = 0.002


class EventBus:
    """Recent playback and storage events, kept for the live resource to poll."""

    def __init__(self, history: int = 100):
        self._lock = threading.Lock()
        self._history: deque[dict[str, Any]] = deque(maxlen=history)
        self._current_pass: dict[str, Any] | None = None

    def publish(self, event_type: str, **data: Any) -> dict[str, Any]:
        event = {"type": event_type, "time": time.time(), **data}
        with self._lock:
            self._history.append(event)
            if event_type == "pass":
                self._current_pass = event
            elif event_type == "stopped":
                self._current_pass = None
        return event

    def snapshot(self) -> dict[str, Any]:
        """State for a visualizer that opens after playback has started."""
        with self._lock:
            return {"current_pass": self._current_pass, "recent": list(self._history)}


@dataclass(slots=True)
class _Program:
    label: str
    events: list[tuple[float, mido.Message]]
    duration: float
    loop: bool
    info: dict[str, Any] = field(default_factory=dict)


class PatternPlayer:
    """Background player that swaps queued material only at a loop boundary."""

    def __init__(
        self,
        send: Callable[[mido.Message], None],
        events: EventBus,
        clock: Callable[[], float] = time.perf_counter,
    ):
        self._send = send
        self._events = events
        self._clock = clock
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._current: _Program | None = None
        self._pending: _Program | None = None
        self._active: set[tuple[int, int]] = set()
        self._cycle_start = 0.0
        self._cycles = 0

    def play(self, sections: list[Section], loop: bool, label: str, info: dict[str, Any] | None = None) -> str:
        """Start now, or queue behind the current loop for a gapless switch."""
        messages, duration = timeline(sections)
        if duration <= 0:
            raise ValueError("pattern duration must be greater than zero")
        program = _Program(label=label, events=messages, duration=duration, loop=loop, info=info or {})
        remaining = 0.0
        with self._lock:
            running = self._thread is not None and self._thread.is_alive()
            queued_behind = self._current if running and self._current is not None and self._current.loop else None
            if queued_behind is not None:
                self._pending = program
                remaining = max(0.0, self._cycle_start + queued_behind.duration - self._clock())
        if queued_behind is not None:
            self._events.publish("queued", label=label, after=queued_behind.label, starts_in=remaining)
            return f"Queued '{label}' after the current loop of '{queued_behind.label}' ({remaining:.1f}s)"

        self.stop()
        with self._lock:
            self._current = program
            self._pending = None
            self._stop.clear()
            self._cycles = 0
            self._thread = threading.Thread(target=self._run, name="elektron-pattern-player", daemon=True)
            self._thread.start()
        return f"Playing '{label}'" + (" on loop" if loop else f" ({duration:.1f}s)")

    def stop(self) -> bool:
        thread = self._thread
        if thread is None or not thread.is_alive():
            return False
        self._stop.set()
        thread.join(timeout=2.0)
        return True

    @property
    def status(self) -> str | None:
        with self._lock:
            if self._current is None or self._thread is None or not self._thread.is_alive():
                return None
            status = f"'{self._current.label}'"
            if self._current.loop:
                status += f" looping (pass {self._cycles + 1})"
            else:
                remaining = self._cycle_start + self._current.duration - self._clock()
                status += f" ({max(0.0, remaining):.1f}s left)"
            if self._pending is not None:
                status += f", then '{self._pending.label}'"
            return status

    def _wait_until(self, target: float) -> bool:
        while True:
            remaining = target - self._clock()
            if remaining <= 0:
                return not self._stop.is_set()
            if remaining > _SPIN_SECONDS:
                if self._stop.wait(min(remaining - _SPIN_SECONDS, 0.05)):
                    return False
            elif self._stop.is_set():
                return False

    def _emit(self, message: mido.Message) -> None:
        note_message = cast(_NoteMessage, message)
        key = (note_message.channel, note_message.note)
        if note_message.type == "note_on" and note_message.velocity > 0:
            self._active.add(key)
        else:
            self._active.discard(key)
        self._send(message)

    def _release_all(self) -> None:
        for channel, note in sorted(self._active):
            self._send(mido.Message("note_off", note=note, velocity=0, channel=channel))
        self._active.clear()

    def _announce_pass(self, program: _Program, start: float) -> None:
        started_at = time.time() - (self._clock() - start)
        self._events.publish(
            "pass",
            label=program.label,
            started_at=started_at,
            duration=program.duration,
            loop=program.loop,
            number=self._cycles + 1,
            **program.info,
        )

    def _run(self) -> None:
        start = self._clock()
        try:
            while True:
                with self._lock:
                    program = self._current
                    self._cycle_start = start
                if program is None:
                    return
                self._announce_pass(program, start)
                for at, message in program.events:
                    if not self._wait_until(start + at):
                        return
                    self._emit(message)
                if not self._wait_until(start + program.duration):
                    return
                start += program.duration
                with self._lock:
                    if self._pending is not None:
                        self._current, self._pending = self._pending, None
                        self._cycles = 0
                    elif program.loop:
                        self._cycles += 1
                    else:
                        self._current = None
                        return
        finally:
            self._release_all()
            with self._lock:
                self._current = None
                self._pending = None
            self._events.publish("stopped")
