"""Writing standard MIDI files."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

import mido

TICKS_PER_BEAT = 480


def _append_notes(
    track: mido.MidiTrack,
    notes: Sequence[Sequence[float]],
    *,
    bpm: float,
    channel: int,
    ticks_per_beat: int,
    default_duration: float,
) -> int:
    """Append [beat, note, velocity, duration] rows as note on/off pairs.

    Rows are delta-timed, so they must be written in beat order.
    """
    current_tick = 0

    for row in sorted(notes, key=lambda r: r[0]):
        beat, note = row[0], int(row[1])
        velocity = int(row[2]) if len(row) > 2 else 100
        duration = float(row[3]) if len(row) > 3 else default_duration

        tick = int(beat * ticks_per_beat)
        # Seconds -> ticks: duration * (beats per second) * ticks per beat.
        duration_ticks = int(duration * ticks_per_beat * bpm / 60)

        track.append(mido.Message("note_on", channel=channel, note=note, velocity=velocity, time=tick - current_tick))
        track.append(mido.Message("note_off", channel=channel, note=note, velocity=0, time=duration_ticks))
        current_tick = tick + duration_ticks

    track.append(mido.MetaMessage("end_of_track", time=0))
    return len(notes)


def write_notes(
    path: Path,
    *,
    bpm: float,
    notes: Sequence[Sequence[float]],
    channel: int = 0,
    track_name: str = "Notes",
    default_duration: float = 0.5,
) -> int:
    """Write a single-track MIDI file. Returns the note count."""
    midi = mido.MidiFile(ticks_per_beat=TICKS_PER_BEAT)

    tempo_track = mido.MidiTrack()
    midi.tracks.append(tempo_track)
    tempo_track.append(mido.MetaMessage("set_tempo", tempo=mido.bpm2tempo(bpm)))

    note_track = mido.MidiTrack()
    midi.tracks.append(note_track)
    note_track.append(mido.MetaMessage("track_name", name=track_name))

    count = _append_notes(
        note_track,
        notes,
        bpm=bpm,
        channel=channel,
        ticks_per_beat=midi.ticks_per_beat,
        default_duration=default_duration,
    )
    midi.save(path)
    return count


def write_pattern(
    path: Path,
    *,
    bpm: float,
    track_triggers: Sequence[Sequence[float]],
    melody_notes: Sequence[Sequence[float]],
    melody_channel: int = 1,
    drum_track_name: str = "Drums",
) -> None:
    """Write a two-track MIDI file: drum triggers plus a melody."""
    midi = mido.MidiFile(ticks_per_beat=TICKS_PER_BEAT)

    tempo_track = mido.MidiTrack()
    midi.tracks.append(tempo_track)
    tempo_track.append(mido.MetaMessage("set_tempo", tempo=mido.bpm2tempo(bpm)))
    tempo_track.append(mido.MetaMessage("time_signature", numerator=4, denominator=4))

    if track_triggers:
        drum_track = mido.MidiTrack()
        midi.tracks.append(drum_track)
        drum_track.append(mido.MetaMessage("track_name", name=drum_track_name))
        # A trigger row is [beat, track, velocity, note?]; tracks map to notes 0-N.
        rows = [
            [row[0], row[3] if len(row) > 3 else int(row[1]) - 1, row[2] if len(row) > 2 else 100, 0.1]
            for row in track_triggers
        ]
        _append_notes(drum_track, rows, bpm=bpm, channel=0, ticks_per_beat=midi.ticks_per_beat, default_duration=0.1)

    if melody_notes:
        melody_track = mido.MidiTrack()
        midi.tracks.append(melody_track)
        melody_track.append(mido.MetaMessage("track_name", name=f"Melody Ch{melody_channel}"))
        _append_notes(
            melody_track,
            melody_notes,
            bpm=bpm,
            channel=melody_channel - 1,
            ticks_per_beat=midi.ticks_per_beat,
            default_duration=0.5,
        )

    midi.save(path)


def write_automation(path: Path, *, bpm: float, events: Sequence[tuple[float, int, int]], channel: int = 0) -> int:
    """Write CC automation as a MIDI file. Events are (beat, cc, value). Returns the count."""
    midi = mido.MidiFile(ticks_per_beat=TICKS_PER_BEAT)
    track = mido.MidiTrack()
    midi.tracks.append(track)
    track.append(mido.MetaMessage("set_tempo", tempo=mido.bpm2tempo(bpm)))

    last_tick = 0
    for beat, control, value in sorted(events, key=lambda e: e[0]):
        tick = int(beat * midi.ticks_per_beat)
        track.append(
            mido.Message("control_change", control=control, value=value, channel=channel, time=tick - last_tick)
        )
        last_tick = tick

    track.append(mido.MetaMessage("end_of_track", time=0))
    midi.save(path)
    return len(events)


def write_recording(path: Path, *, bpm: float, messages: Sequence[tuple[float, mido.Message]]) -> int:
    """Write captured (elapsed_seconds, message) pairs to a MIDI file. Returns the count."""
    midi = mido.MidiFile(ticks_per_beat=TICKS_PER_BEAT)

    tempo_track = mido.MidiTrack()
    midi.tracks.append(tempo_track)
    tempo_track.append(mido.MetaMessage("set_tempo", tempo=mido.bpm2tempo(bpm)))

    track = mido.MidiTrack()
    midi.tracks.append(track)
    track.append(mido.MetaMessage("track_name", name="Recording"))

    ticks_per_second = midi.ticks_per_beat * bpm / 60
    written = 0
    current_tick = 0

    for elapsed, message in messages:
        if message.type not in ("note_on", "note_off", "control_change"):  # ty: ignore[unresolved-attribute]
            continue
        tick = int(elapsed * ticks_per_second)
        track.append(message.copy(time=tick - current_tick))
        current_tick = tick
        written += 1

    track.append(mido.MetaMessage("end_of_track", time=0))
    midi.save(path)
    return written
