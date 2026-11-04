"""Strict text notation for Elektron patterns and compact song arrangements.

Adapted from koii studio's notation and sequence modules:
https://github.com/benjaminr/mcp-koii
Copyright (c) 2025 Benjamin Rowell, used under the MIT License.
See THIRD_PARTY_NOTICES.md.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from fractions import Fraction
from typing import TYPE_CHECKING, Literal

import mido

if TYPE_CHECKING:
    from collections.abc import Callable

    from elektron_mcp.device import DeviceSpec

HOLD = "hold"
Step = int | Literal["hold"] | None

STEP_VELOCITY = {"x": 100, "X": 127, "o": 50}
STEP_VELOCITY.update({str(level): round(level * 127 / 9) for level in range(1, 10)})
IGNORED_CHARS = {" ", "\t", "|"}
GRIDS: dict[str, tuple[Fraction, int]] = {
    "1/4": (Fraction(1), 1),
    "1/8": (Fraction(1, 2), 2),
    "1/16": (Fraction(1, 4), 4),
    "1/32": (Fraction(1, 8), 8),
    "1/8t": (Fraction(1, 3), 3),
    "1/16t": (Fraction(1, 6), 6),
}
DEFAULT_BPM = 120
BPM_RANGE = (20, 300)
SWING_RANGE = (50, 75)
MAX_STEPS = 1024

_NAME = r"[A-Za-z0-9][\w.\-]*"
_TRACK_RE = re.compile(rf"^(?P<name>{_NAME})\s*:(?P<steps>.*)$")
_NOTES_RE = re.compile(rf"^(?P<name>{_NAME})\s+notes\s*:(?P<notes>.*)$", re.IGNORECASE)
_NOTE_NAME_RE = re.compile(r"^([A-Ga-g])([#b]?)(-?\d)$")
_TRACK_TARGET_RE = re.compile(r"^t(\d{1,2})$", re.IGNORECASE)
_CHANNEL_RE = re.compile(r"^ch(\d{1,2})$", re.IGNORECASE)
_SECTION_RE = re.compile(r"^(?P<names>[\w.\-]+(?:\s*\+\s*[\w.\-]+)*)(?:\s+x\s*(?P<n>\d+))?$")
_PITCH_CLASS = {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11}
_NOTE_NAMES = ("C", "C#", "D", "Eb", "E", "F", "F#", "G", "Ab", "A", "Bb", "B")

NOTE_OFF = 0
NOTE_ON = 1


@dataclass(frozen=True, slots=True)
class Issue:
    line: int
    column: int | None
    message: str

    def __str__(self) -> str:
        if not self.line:
            return self.message
        where = f"line {self.line}" + (f", col {self.column}" if self.column else "")
        return f"{where}: {self.message}"


class NotationError(ValueError):
    """One or more pattern or arrangement errors."""

    def __init__(self, issues: list[Issue]):
        self.issues = issues
        super().__init__("\n".join(str(issue) for issue in issues))


@dataclass(frozen=True, slots=True)
class Target:
    """A fixed trigger or a chromatic MIDI channel."""

    kind: Literal["trigger", "channel"]
    channel: int
    note: int | None = None
    label: str = ""

    @property
    def pitched(self) -> bool:
        return self.kind == "channel"


@dataclass(slots=True)
class Track:
    name: str
    target: Target
    steps: list[Step] = field(default_factory=list)
    symbols: list[str] = field(default_factory=list)
    notes: list[tuple[int, ...]] = field(default_factory=list)
    line: int = 0


@dataclass(slots=True)
class Pattern:
    tracks: list[Track]
    length: int
    bpm: int = DEFAULT_BPM
    swing: int = 50
    grid: str = "1/16"
    source: str = ""
    maps: dict[str, str] = field(default_factory=dict)

    @property
    def step_beats(self) -> Fraction:
        return GRIDS[self.grid][0]

    @property
    def length_beats(self) -> Fraction:
        return self.length * self.step_beats


@dataclass(frozen=True, slots=True)
class ArrangementPart:
    names: list[str]
    repeat: int = 1


@dataclass(frozen=True, slots=True)
class MidiEvent:
    beat: Fraction
    kind: int
    note: int
    velocity: int
    channel: int


@dataclass(slots=True)
class Section:
    label: str
    bpm: int
    length_beats: Fraction
    events: list[MidiEvent] = field(default_factory=list)
    patterns: list[tuple[str, Pattern]] = field(default_factory=list)

    @property
    def seconds(self) -> float:
        return float(self.length_beats) * 60.0 / self.bpm


def strip_comment(line: str) -> str:
    """Remove a comment while preserving sharps in note names such as C#2."""
    for index, char in enumerate(line):
        if char == "#" and (index == 0 or line[index - 1].isspace()):
            return line[:index]
    return line


def parse_note(token: str) -> int | None:
    """Parse C4, F#2, Bb1 or a MIDI number."""
    if token.isdigit():
        value = int(token)
        return value if value <= 127 else None
    match = _NOTE_NAME_RE.match(token)
    if not match:
        return None
    letter, accidental, octave = match.groups()
    value = (int(octave) + 1) * 12 + _PITCH_CLASS[letter.upper()]
    value += {"#": 1, "b": -1, "": 0}[accidental]
    return value if 0 <= value <= 127 else None


def note_name(note: int) -> str:
    return f"{_NOTE_NAMES[note % 12]}{note // 12 - 1}"


def parse_target(text: str, spec: DeviceSpec) -> Target | None:
    """Parse tN, chN or a fixed MIDI note number."""
    text = text.strip()
    match = _TRACK_TARGET_RE.match(text)
    if match:
        track = int(match.group(1))
        if 1 <= track <= spec.track_count:
            note = track - 1 if spec.trigger_notes else 60
            return Target("trigger", channel=track, note=note, label=f"t{track}")
        return None
    match = _CHANNEL_RE.match(text)
    if match and 1 <= int(match.group(1)) <= 16:
        channel = int(match.group(1))
        return Target("channel", channel=channel, label=f"ch{channel}")
    if text.isdigit() and 0 <= int(text) <= 127:
        note = int(text)
        return Target("trigger", channel=1, note=note, label=str(note))
    return None


def _resolve_name(name: str, maps: dict[str, Target], spec: DeviceSpec) -> Target | None:
    key = name.lower()
    if key in maps:
        return maps[key]
    alias = spec.pattern_aliases.get(key)
    return parse_target(alias or name, spec)


def _parse_steps(
    text: str,
    line_no: int,
    column_start: int,
    issues: list[Issue],
    previous: Step = None,
) -> tuple[list[Step], list[str]]:
    steps: list[Step] = []
    symbols: list[str] = []
    for offset, char in enumerate(text):
        if char in IGNORED_CHARS:
            continue
        symbols.append(char)
        if char in STEP_VELOCITY:
            steps.append(STEP_VELOCITY[char])
        elif char == ".":
            steps.append(None)
        elif char == "-":
            before = steps[-1] if steps else previous
            if before is None:
                issues.append(Issue(line_no, column_start + offset, "'-' (hold) must follow a hit or another '-'"))
            steps.append(HOLD)
        elif char == "0":
            issues.append(Issue(line_no, column_start + offset, "'0' is not a step; use '.' or 1-9"))
            steps.append(None)
        else:
            issues.append(
                Issue(
                    line_no,
                    column_start + offset,
                    f"unknown step '{char}'. Use x X o 1-9 (hits), . (rest), or - (hold)",
                )
            )
            steps.append(None)
    return steps, symbols


def _parse_directive(
    body: str,
    line_no: int,
    spec: DeviceSpec,
    settings: dict[str, int | str],
    maps: dict[str, Target],
    issues: list[Issue],
) -> None:
    parts = body.split(None, 1)
    key = parts[0].lower() if parts else ""
    value = parts[1].strip() if len(parts) > 1 else ""
    if key == "bpm":
        if not value.isdigit() or not BPM_RANGE[0] <= int(value) <= BPM_RANGE[1]:
            issues.append(Issue(line_no, None, f"@bpm needs a whole number from {BPM_RANGE[0]} to {BPM_RANGE[1]}"))
        else:
            settings["bpm"] = int(value)
    elif key == "swing":
        if not value.isdigit() or not SWING_RANGE[0] <= int(value) <= SWING_RANGE[1]:
            issues.append(Issue(line_no, None, "@swing needs a percent from 50 to 75"))
        else:
            settings["swing"] = int(value)
    elif key == "grid":
        if value.lower() not in GRIDS:
            issues.append(Issue(line_no, None, f"@grid must be one of {', '.join(GRIDS)}"))
        else:
            settings["grid"] = value.lower()
    elif key == "map":
        name, separator, target_text = value.partition("=")
        name = name.strip()
        target = parse_target(target_text, spec) if separator else None
        if not separator or not re.fullmatch(_NAME, name):
            issues.append(Issue(line_no, None, "write @map as: @map name = target  (e.g. @map bass = ch2)"))
        elif target is None:
            issues.append(
                Issue(
                    line_no,
                    None,
                    f"@map target '{target_text.strip()}' is not t1-t{spec.track_count}, ch1-ch16, or note 0-127",
                )
            )
        else:
            maps[name.lower()] = target
    else:
        issues.append(Issue(line_no, None, f"unknown directive '@{key}'. Use @bpm, @swing, @grid or @map"))


def parse_pattern(text: str, spec: DeviceSpec) -> Pattern:
    """Parse pattern text or raise one error containing every issue."""
    issues: list[Issue] = []
    settings: dict[str, int | str] = {}
    maps: dict[str, Target] = {}
    step_lines: list[tuple[int, str, str, int]] = []
    note_lines: list[tuple[int, str, str, int]] = []

    for line_no, raw in enumerate(text.splitlines(), start=1):
        line = strip_comment(raw).rstrip()
        stripped = line.strip()
        if not stripped:
            continue
        indent = len(line) - len(line.lstrip())
        if stripped.startswith("@"):
            _parse_directive(stripped[1:], line_no, spec, settings, maps, issues)
            continue
        match = _NOTES_RE.match(stripped)
        if match:
            note_lines.append((line_no, match.group("name"), match.group("notes"), indent + match.start("notes") + 1))
            continue
        match = _TRACK_RE.match(stripped)
        if match:
            step_lines.append((line_no, match.group("name"), match.group("steps"), indent + match.start("steps") + 1))
            continue
        issues.append(Issue(line_no, None, f"can't read '{stripped}'. Expected 'name: steps' or '@directive'"))

    tracks: dict[str, Track] = {}
    for line_no, name, steps_text, column in step_lines:
        key = name.lower()
        if key not in tracks:
            target = _resolve_name(name, maps, spec)
            if target is None:
                aliases = ", ".join(sorted(spec.pattern_aliases)) or "none"
                issues.append(
                    Issue(
                        line_no,
                        None,
                        f"unknown track '{name}'. Use t1-t{spec.track_count}, ch1-ch16, an alias ({aliases}), "
                        "or add '@map name = target'",
                    )
                )
                target = Target("trigger", channel=1, note=0, label="?")
            tracks[key] = Track(name=name, target=target, line=line_no)
        previous = tracks[key].steps[-1] if tracks[key].steps else None
        steps, symbols = _parse_steps(steps_text, line_no, column, issues, previous)
        if not steps:
            issues.append(Issue(line_no, None, f"track '{name}' has no steps"))
        tracks[key].steps.extend(steps)
        tracks[key].symbols.extend(symbols)

    for line_no, name, notes_text, column in note_lines:
        track = tracks.get(name.lower())
        if track is None:
            issues.append(Issue(line_no, None, f"'{name} notes' has no '{name}:' rhythm line"))
            continue
        for match in re.finditer(r"\S+", notes_text):
            chord: list[int] = []
            for part in match.group(0).split("+"):
                note = parse_note(part)
                if note is None:
                    issues.append(
                        Issue(
                            line_no,
                            column + match.start(),
                            f"'{part}' is not a note. Use C2, F#3, Bb1, 0-127, or join a chord with +",
                        )
                    )
                else:
                    chord.append(note)
            if chord:
                track.notes.append(tuple(chord))

    for track in tracks.values():
        if track.target.pitched and not track.notes:
            issues.append(
                Issue(
                    track.line,
                    None,
                    f"'{track.name}' plays on {track.target.label} and needs a '{track.name} notes:' line",
                )
            )
        elif not track.target.pitched and track.notes:
            issues.append(
                Issue(
                    track.line,
                    None,
                    f"'{track.name}' is a fixed trigger. Map it to ch1-ch16 before adding a notes line",
                )
            )

    if not tracks and not issues:
        issues.append(Issue(1, None, "no tracks. Write at least one line like 'kick: x...x...x...x...'"))

    length = max((len(track.steps) for track in tracks.values()), default=0)
    if length > MAX_STEPS:
        issues.append(Issue(1, None, f"pattern is {length} steps; the limit is {MAX_STEPS}"))
    misfits = [track for track in tracks.values() if track.steps and length % len(track.steps)]
    if misfits:
        longest = next(track for track in tracks.values() if len(track.steps) == length)
        steps_per_beat = GRIDS[str(settings.get("grid", "1/16"))][1]
        for track in misfits:
            issues.append(
                Issue(
                    track.line,
                    None,
                    f"'{track.name}' has {len(track.steps)} steps, which does not divide '{longest.name}' "
                    f"({length} steps)",
                )
            )
        for track in (longest, *misfits):
            if len(track.steps) % steps_per_beat:
                issues.append(
                    Issue(
                        track.line,
                        None,
                        f"'{track.name}' is not a whole number of beats ({steps_per_beat} steps per beat)",
                    )
                )

    if issues:
        raise NotationError(sorted(issues, key=lambda issue: (issue.line, issue.column or 0)))

    return Pattern(
        tracks=list(tracks.values()),
        length=length,
        bpm=int(settings.get("bpm", DEFAULT_BPM)),
        swing=int(settings.get("swing", 50)),
        grid=str(settings.get("grid", "1/16")),
        source=text,
        maps={name: target.label for name, target in maps.items()},
    )


def parse_arrangement(text: str) -> list[ArrangementPart]:
    """Parse ``intro x2, verse+bass x4, outro``."""
    issues: list[Issue] = []
    parts: list[ArrangementPart] = []
    for line_no, raw in enumerate(text.splitlines() or [text], start=1):
        for item in strip_comment(raw).split(","):
            item = item.strip()
            if not item:
                continue
            match = _SECTION_RE.match(item)
            if not match:
                issues.append(Issue(line_no, None, f"can't read section '{item}'. Write 'name', 'name x4' or 'a+b x2'"))
                continue
            repeat = int(match.group("n") or 1)
            if not 1 <= repeat <= 999:
                issues.append(Issue(line_no, None, f"repeat count in '{item}' must be 1-999"))
                continue
            parts.append(
                ArrangementPart(names=[name.strip() for name in match.group("names").split("+")], repeat=repeat)
            )
    if not parts and not issues:
        issues.append(Issue(1, None, "empty arrangement"))
    if issues:
        raise NotationError(issues)
    return parts


def _step_time(index: int, pattern: Pattern) -> Fraction:
    beat = index * pattern.step_beats
    if index % 2 == 1 and pattern.swing != 50:
        beat += pattern.step_beats * Fraction(pattern.swing - 50, 50)
    return beat


def compile_pattern(pattern: Pattern, cycles: int = 1) -> list[MidiEvent]:
    """Compile one parsed pattern into exact beat-positioned MIDI events."""
    events: list[MidiEvent] = []
    for track in pattern.tracks:
        steps = track.steps * (pattern.length // len(track.steps))
        note_index = 0
        for cycle in range(cycles):
            offset = cycle * pattern.length_beats
            for index, step in enumerate(steps):
                if step is None or step == HOLD:
                    continue
                end = index + 1
                while end < pattern.length and steps[end] == HOLD:
                    end += 1
                start_beat = offset + _step_time(index, pattern)
                end_beat = offset + (_step_time(end, pattern) if end < pattern.length else pattern.length_beats)
                if track.target.pitched:
                    chord = track.notes[note_index % len(track.notes)]
                    note_index += 1
                else:
                    assert track.target.note is not None
                    chord = (track.target.note,)
                channel = track.target.channel - 1
                for note in chord:
                    events.append(MidiEvent(start_beat, NOTE_ON, note, step, channel))
                    events.append(MidiEvent(end_beat, NOTE_OFF, note, 0, channel))
    events.sort(key=lambda event: (event.beat, event.kind, event.note, event.channel))
    return events


def layer(patterns: list[tuple[str, Pattern]], bpm: int | None = None) -> Section:
    """Layer patterns, repeating shorter patterns when they divide the longest."""
    longest = max(pattern.length_beats for _, pattern in patterns)
    issues = [
        Issue(0, None, f"'{name}' is {pattern.length_beats} beats and does not divide {longest} beats")
        for name, pattern in patterns
        if longest % pattern.length_beats
    ]
    if issues:
        raise NotationError(issues)
    events: list[MidiEvent] = []
    for _, pattern in patterns:
        events.extend(compile_pattern(pattern, cycles=int(longest / pattern.length_beats)))
    events.sort(key=lambda event: (event.beat, event.kind, event.note, event.channel))
    return Section(
        label="+".join(name for name, _ in patterns),
        bpm=bpm or patterns[0][1].bpm,
        length_beats=longest,
        events=events,
        patterns=list(patterns),
    )


def expand_arrangement(
    arrangement: str,
    get_pattern: Callable[[str], Pattern | None],
    bpm: int | None = None,
) -> list[Section]:
    """Expand compact song text into one section per pass."""
    sections: list[Section] = []
    issues: list[Issue] = []
    for part in parse_arrangement(arrangement):
        found: list[tuple[str, Pattern]] = []
        for name in part.names:
            pattern = get_pattern(name)
            if pattern is None:
                issues.append(Issue(0, None, f"no text pattern named '{name}'"))
            else:
                found.append((name, pattern))
        if len(found) == len(part.names):
            section = layer(found, bpm)
            sections.extend([section] * part.repeat)
    if issues:
        raise NotationError(issues)
    return sections


def timeline(sections: list[Section]) -> tuple[list[tuple[float, mido.Message]], float]:
    """Flatten sections into absolute seconds and MIDI messages."""
    output: list[tuple[float, mido.Message]] = []
    start = 0.0
    for section in sections:
        seconds_per_beat = 60.0 / section.bpm
        for event in section.events:
            kind = "note_on" if event.kind == NOTE_ON else "note_off"
            output.append(
                (
                    start + float(event.beat) * seconds_per_beat,
                    mido.Message(kind, note=event.note, velocity=event.velocity, channel=event.channel),
                )
            )
        start += section.seconds
    return output, start


def format_steps(symbols: list[str], steps_per_beat: int) -> str:
    return "|".join(
        "".join(symbols[index : index + steps_per_beat]) for index in range(0, len(symbols), steps_per_beat)
    )


def render_pattern(pattern: Pattern) -> str:
    """Return a compact normalized pattern description."""
    steps_per_beat = GRIDS[pattern.grid][1]
    bars = pattern.length_beats / 4
    length = (
        f"{bars} bar{'s' if bars != 1 else ''}" if bars.denominator == 1 else f"{float(pattern.length_beats):g} beats"
    )
    header = f"{pattern.length} steps of {pattern.grid} ({length}) · {pattern.bpm} BPM"
    if pattern.swing != 50:
        header += f" · swing {pattern.swing}%"
    width = max(len(track.name) for track in pattern.tracks)
    lines = [header]
    for track in pattern.tracks:
        row = (
            f"  {track.name.ljust(width)}  {track.target.label.ljust(5)} {format_steps(track.symbols, steps_per_beat)}"
        )
        if len(track.steps) < pattern.length:
            row += f"  x{pattern.length // len(track.steps)}"
        if track.notes:
            row += "   " + " ".join("+".join(note_name(note) for note in chord) for chord in track.notes)
        lines.append(row)
    return "\n".join(lines)


def pattern_to_dict(pattern: Pattern) -> dict:
    """JSON-friendly pattern state for live visualizers."""
    return {
        "bpm": pattern.bpm,
        "swing": pattern.swing,
        "grid": pattern.grid,
        "steps_per_beat": GRIDS[pattern.grid][1],
        "length": pattern.length,
        "beats": float(pattern.length_beats),
        "source": pattern.source,
        "tracks": [
            {
                "name": track.name,
                "target": {
                    "kind": track.target.kind,
                    "label": track.target.label,
                    "note": track.target.note,
                    "channel": track.target.channel,
                },
                "symbols": track.symbols,
                "notes": ["+".join(note_name(note) for note in chord) for chord in track.notes],
            }
            for track in pattern.tracks
        ],
    }
