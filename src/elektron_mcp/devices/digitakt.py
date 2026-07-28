"""Elektron Digitakt (original, not Digitakt II).

Quirks that distinguish it from the Digitakt II:
- 8 audio tracks, plus 8 separate MIDI tracks (II has 16 audio tracks)
- 1 LFO per track (II has 3)
- No Chorus effect
- Volume is CC 7 and Pan is CC 10; Delay/Reverb sends live in the AMP page
"""

import asyncio
from typing import Annotated

from elektron_mcp import clock
from elektron_mcp.clock import note_event
from elektron_mcp.device import DeviceSpec, parse_parameters
from elektron_mcp.devices.digitakt_cc import get_param_name
from elektron_mcp.devices.digitakt_params import PARAMETER_MAP, get_parameters_by_category
from elektron_mcp.midi import note_name
from elektron_mcp.server import DeviceServer, build_server

TRACK_COUNT = 8

# Trig NRPN pages: the LSB is the step index, the MSB selects which attribute.
TRIG_NOTE_MSB = 3
TRIG_VELOCITY_MSB = 4
TRIG_LENGTH_MSB = 5


def register_tools(device: DeviceServer) -> None:
    """Add the tools that only make sense on a sample-triggering Digitakt."""
    connection = device.connection

    # ---------------------------------------------------------------- triggers

    @device.tool
    async def trigger_track(
        track: Annotated[int, f"Track number (1-{TRACK_COUNT})."],
        velocity: Annotated[int, "Note velocity (1-127)."] = 100,
        duration: Annotated[float, "How long to hold the note, in seconds."] = 0.1,
        channel: Annotated[int, "MIDI channel (1-16). Default is the AUTO channel."] = 1,
    ) -> str:
        """Fire a one-shot sample on a Digitakt track.

        Convenience wrapper: tracks 1-8 are MIDI notes 0-7.
        """
        ch = channel - 1
        note = track - 1

        connection.note_on(note, velocity, ch)
        device.log_note_on(note, velocity, ch)
        await asyncio.sleep(duration)
        connection.note_off(note, ch)
        device.log_note_off(note, ch)

        return f"Triggered Track {track} (note {note}, velocity {velocity}) on channel {channel} for {duration}s"

    # ------------------------------------------------------------------- trigs

    def _set_trig(msb: int, track: int, step: int, value: int, channel: int, label: str) -> None:
        # Channel 0 means "use the track's own channel", which is the usual setup.
        ch = (channel if channel > 0 else track) - 1
        connection.nrpn(msb, step - 1, value, ch)
        connection.log_nrpn(msb, step - 1, value, ch, f"Trig {step} {label}")

    @device.tool
    def set_trig_note(
        track: Annotated[int, f"Track number (1-{TRACK_COUNT})."],
        step: Annotated[int, "Step number (1-64)."],
        note: Annotated[int, "MIDI note number (0-127). 60 = C4."],
        channel: Annotated[int, "MIDI channel (1-16). 0 uses the track's own channel."] = 0,
    ) -> str:
        """Set which note a sequencer step plays."""
        _set_trig(TRIG_NOTE_MSB, track, step, note, channel, "Note")
        return f"Set Track {track} Step {step} note to {note} ({note_name(note)})"

    @device.tool
    def set_trig_velocity(
        track: Annotated[int, f"Track number (1-{TRACK_COUNT})."],
        step: Annotated[int, "Step number (1-64)."],
        velocity: Annotated[int, "Velocity (0-127). 0 = accent off, 127 = full accent."],
        channel: Annotated[int, "MIDI channel (1-16). 0 uses the track's own channel."] = 0,
    ) -> str:
        """Set the velocity of a sequencer step."""
        _set_trig(TRIG_VELOCITY_MSB, track, step, velocity, channel, "Velocity")
        return f"Set Track {track} Step {step} velocity to {velocity}"

    @device.tool
    def set_trig_length(
        track: Annotated[int, f"Track number (1-{TRACK_COUNT})."],
        step: Annotated[int, "Step number (1-64)."],
        length: Annotated[int, "Length (0-127). Higher is longer."],
        channel: Annotated[int, "MIDI channel (1-16). 0 uses the track's own channel."] = 0,
    ) -> str:
        """Set the note length of a sequencer step."""
        _set_trig(TRIG_LENGTH_MSB, track, step, length, channel, "Length")
        return f"Set Track {track} Step {step} length to {length}"

    @device.tool
    def reset_velocities(
        track: Annotated[int, f"Track number (1-{TRACK_COUNT})."],
        steps: Annotated[int, "How many steps to reset (1-64)."] = 16,
        velocity: Annotated[int, "Velocity to write to every step."] = 100,
        channel: Annotated[int, "MIDI channel (1-16). 0 uses the track's own channel."] = 0,
    ) -> str:
        """Flatten every step's velocity on a track to one value."""
        for step in range(1, steps + 1):
            _set_trig(TRIG_VELOCITY_MSB, track, step, velocity, channel, "Velocity")
        device.logger.info(f"🔄 Reset Track {track} velocities (steps 1-{steps}) to {velocity}")
        return f"Reset Track {track} steps 1-{steps} velocities to {velocity}"

    # ---------------------------------------------------------------- playback

    @device.tool
    async def play_pattern_with_tracks(
        triggers: Annotated[list, f"Triggers as [beat, track, velocity]. Track is 1-{TRACK_COUNT}."],
        bars: Annotated[int, "Number of bars to play."] = 4,
        bpm: Annotated[float, "Tempo in BPM."] = 120,
        send_stop: Annotated[bool, "Send MIDI Stop at the end."] = True,
    ) -> str:
        """Play a drum pattern of track triggers, locked to MIDI clock.

        Beat positions are quarter notes: 0 is the downbeat, 1 is beat 2.
        """
        device.history.tracks = {"bpm": bpm, "triggers": triggers}

        events = [
            note_event(
                beat=row[0],
                note=int(row[1]) - 1,
                velocity=int(row[2]) if len(row) > 2 else 100,
                channel=0,
            )
            for row in triggers
        ]

        device.logger.info(f"▶️  PLAY PATTERN: {bars} bars @ {bpm} BPM, {len(triggers)} triggers")
        await clock.play(connection, events, bars=bars, bpm=bpm, send_stop=send_stop)
        return f"Played {bars} bars at {bpm} BPM with {len(triggers)} track triggers"

    @device.tool
    async def play_pattern_with_tracks_and_melody(
        track_triggers: Annotated[list | None, "Triggers as [beat, track, velocity, note?]."] = None,
        melody_notes: Annotated[list | None, "Melody as [beat, note, velocity, duration]."] = None,
        bars: Annotated[int, "Number of bars to play."] = 4,
        bpm: Annotated[float, "Tempo in BPM."] = 120,
        channel: Annotated[int, "MIDI channel for the melody."] = 1,
        midi_start_at_beat: Annotated[float, "Delay MIDI Start until this beat."] = 0,
        preroll_bars: Annotated[int, "Bars of count-in before the melody enters."] = 0,
        send_stop: Annotated[bool, "Send MIDI Stop at the end."] = True,
    ) -> str:
        """Play drums and a melody together.

        Each trigger goes out on its own track's channel; the melody uses `channel`.
        """
        track_triggers = track_triggers or []
        melody_notes = melody_notes or []
        preroll_beats = preroll_bars * 4

        events = [
            note_event(
                beat=row[0],
                note=int(row[3]) if len(row) > 3 else int(row[1]) - 1,
                velocity=int(row[2]) if len(row) > 2 else 100,
                channel=int(row[1]) - 1,
            )
            for row in track_triggers
        ]
        events += [
            note_event(
                beat=row[0] + preroll_beats,
                note=int(row[1]),
                velocity=int(row[2]) if len(row) > 2 else 100,
                duration=float(row[3]) if len(row) > 3 else 0.1,
                channel=channel - 1,
            )
            for row in melody_notes
        ]

        await clock.play(connection, events, bars=bars, bpm=bpm, send_stop=send_stop, start_at_beat=midi_start_at_beat)
        return f"Played {bars} bars at {bpm} BPM with {len(track_triggers)} triggers + {len(melody_notes)} melody notes"


SPEC = DeviceSpec(
    slug="digitakt",
    display_name="Digitakt",
    port_name="Elektron Digitakt",
    track_count=TRACK_COUNT,
    trigger_notes=True,
    parameters=parse_parameters(PARAMETER_MAP),
    categories=get_parameters_by_category(),
    nrpn_name_lookup=get_param_name,
    register_tools=register_tools,
    notes=(
        "Digitakt (original): 8 audio tracks on channels 1-8, 8 MIDI tracks, 1 LFO per track, no Chorus. "
        "Notes 0-7 trigger tracks 1-8; notes 12-84 play the active track chromatically."
    ),
)


def main() -> None:
    """Console entry point for `digitakt-mcp`."""
    device = build_server(SPEC)
    device.connection.connect()
    device.mcp.run()
