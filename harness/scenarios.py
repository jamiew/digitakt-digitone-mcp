"""Prompts with checks on the tool calls they should produce.

Models phrase things differently, so each requirement lists the acceptable calls
and passes if any one of them succeeded. Keep prompts concrete (track numbers,
values) so a pass means the MCP surface is clear, not that the model guessed well.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from harness.providers import ToolOutcome

Check = Callable[[Any], bool]


@dataclass(frozen=True)
class Expect:
    """A tool call with argument checks. Plain values must match; callables are predicates."""

    tool: str
    args: dict[str, Any] = field(default_factory=dict)
    error: bool = False
    """Match a call that failed instead of one that succeeded."""

    def matches(self, outcome: ToolOutcome) -> bool:
        if outcome.call.name != self.tool or outcome.is_error != self.error:
            return False
        return all(_check(outcome.arguments.get(key), want) for key, want in self.args.items())

    def __str__(self) -> str:
        parts = [f"{k}={'…' if callable(v) else repr(v)}" for k, v in self.args.items()]
        return f"{self.tool}({', '.join(parts)}){' failing' if self.error else ''}"


def _check(value: Any, want: Any) -> bool:
    if callable(want):
        try:
            return bool(want(value))
        except (TypeError, ValueError, IndexError, KeyError):
            return False
    if isinstance(want, int | float) and isinstance(value, int | float):
        return abs(value - want) < 1e-6
    return value == want


@dataclass(frozen=True)
class Scenario:
    name: str
    prompt: str
    requires: list[list[Expect]]
    """Every group must be satisfied by at least one of its Expects."""

    def failures(self, outcomes: list[ToolOutcome]) -> list[str]:
        return [
            " or ".join(str(e) for e in group)
            for group in self.requires
            if not any(e.matches(o) for e in group for o in outcomes)
        ]


def any_of(*options: Expect) -> list[Expect]:
    return list(options)


# --------------------------------------------------------------- predicates


def triggers_on(track: int, beats: set[float]) -> Check:
    """Rows like [beat, track, velocity]: `track` fires on exactly `beats`."""
    return lambda rows: {float(r[0]) for r in rows if int(r[1]) == track} == beats


def pitches(*notes: int) -> Check:
    return lambda rows: [int(r[1]) for r in sorted(rows, key=lambda r: r[0])] == list(notes)


def pitch_classes(*classes: int) -> Check:
    return lambda notes: {int(n) % 12 for n in notes} == set(classes)


# ----------------------------------------------------------------- shared

UNKNOWN_PARAMETER = Scenario(
    "unknown-parameter",
    "Set the parameter called warp_drive to 10 on track 1.",
    # Either it tries and sees the server's error, or it checks the list first.
    # Both prove tool errors and parameter discovery reach the model.
    [any_of(Expect("set_parameter", {"name": "warp_drive"}, error=True), Expect("list_parameters"))],
)

PATTERN_FILES = Scenario(
    "pattern-files",
    "Save a 1-bar pattern named harness-check at 120 BPM with track 1 on every beat and no MIDI channels. "
    "Then confirm it's in the saved pattern list, then delete it.",
    [
        any_of(Expect("save_pattern", {"pattern_name": "harness-check", "bars": 1})),
        any_of(Expect("list_patterns"), Expect("load_pattern", {"pattern_name": "harness-check"})),
        any_of(Expect("delete_pattern", {"pattern_name": "harness-check"})),
    ],
)

# ----------------------------------------------------------------- devices

DIGITAKT = [
    Scenario(
        "trigger",
        "Trigger track 1 once.",
        [any_of(Expect("trigger_track", {"track": 1}), Expect("send_note", {"note": 0, "channel": 1}))],
    ),
    Scenario(
        "filter",
        "Set the filter cutoff on track 2 to 40.",
        [
            any_of(
                Expect("set_parameter", {"name": "filter_cutoff", "value": 40, "channel": 2}),
                Expect("send_cc", {"cc_number": 74, "value": 40, "channel": 2}),
            )
        ],
    ),
    Scenario(
        "four-on-the-floor",
        "Play one bar at 120 BPM with track 1 on every quarter note.",
        [
            any_of(
                Expect("play_pattern_with_tracks", {"bars": 1, "triggers": triggers_on(1, {0, 1, 2, 3})}),
                Expect(
                    "play_pattern_with_multi_channel_midi",
                    {"bars": 1, "track_triggers": triggers_on(1, {0, 1, 2, 3})},
                ),
            )
        ],
    ),
    Scenario(
        "trig-velocity",
        "On the Digitakt's sequencer, set step 5 of track 3 to velocity 64.",
        [any_of(Expect("set_trig_velocity", {"track": 3, "step": 5, "velocity": 64}))],
    ),
    UNKNOWN_PARAMETER,
    PATTERN_FILES,
]

DIGITONE = [
    Scenario(
        "chord",
        "Play a C major triad on track 1.",
        [any_of(Expect("play_chord", {"notes": pitch_classes(0, 4, 7), "channel": 1}))],
    ),
    Scenario(
        "algorithm",
        "Switch track 2 to FM algorithm 5.",
        [
            any_of(
                Expect("set_algorithm", {"algorithm": 5, "channel": 2}),
                Expect("set_parameter", {"name": "fm_algorithm", "value": 4, "channel": 2}),
            )
        ],
    ),
    Scenario(
        "arpeggio",
        "Play one bar at 100 BPM on track 1: C4, E4, G4, C5 as quarter notes.",
        [any_of(Expect("play_pattern_with_melody", {"bars": 1, "channel": 1, "notes": pitches(60, 64, 67, 72)}))],
    ),
    Scenario(
        "chorus",
        "Set the chorus mix to 100.",
        [any_of(Expect("set_chorus", {"mix": 100}), Expect("set_parameter", {"name": "chorus_mix", "value": 100}))],
    ),
    UNKNOWN_PARAMETER,
    PATTERN_FILES,
]

SCENARIOS = {"digitakt": DIGITAKT, "digitone": DIGITONE}
