#!/usr/bin/env python3
"""
MCP Server for Digitakt (original) MIDI Control - FastMCP Version
Provides tools to send MIDI messages to the Elektron Digitakt

NOTE: This is for the original Digitakt, NOT Digitakt II.
Key differences from Digitakt II:
- 8 audio tracks (not 16)
- 8 MIDI tracks (separate from audio tracks)
- Only 1 LFO (not 3)
- No Chorus effect
- Different AMP CC numbers (Volume=7, Pan=10)
"""

import asyncio
import json
import logging
import time
from pathlib import Path
from typing import Annotated

import mido
from mcp.server.fastmcp import FastMCP

from nrpn_constants import (
    get_param_name,
)
from parameter_map import (
    get_all_parameters,
    get_parameter_info,
    get_parameters_by_category,
)
from shared import (
    connect_midi,
    delayed_note_off,
    log_cc,
    log_nrpn,
    log_program_change,
    log_sysex,
    log_transport,
    note_name,
)

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("digitakt-midi-server")

# Create FastMCP instance
mcp = FastMCP("digitakt-midi")

# MIDI port name - will be auto-detected
DIGITAKT_PORT_NAME = "Elektron Digitakt"

# Preset directory (for automation presets)
PRESET_DIR = Path.home() / ".mcp-config" / "digitakt" / "presets"
PRESET_DIR.mkdir(parents=True, exist_ok=True)

# Pattern directory (for full patterns)
PATTERN_DIR = Path.home() / ".mcp-config" / "digitakt" / "patterns"
PATTERN_DIR.mkdir(parents=True, exist_ok=True)

# Recordings directory (for MIDI recordings)
RECORDINGS_DIR = Path.home() / ".mcp-config" / "digitakt" / "recordings"
RECORDINGS_DIR.mkdir(parents=True, exist_ok=True)

# Global MIDI port references
output_port: mido.ports.BaseOutput | None = None
input_port: mido.ports.BaseInput | None = None

# Global history for last played melody/pattern
last_melody = None
last_tracks = None
last_loop = None
last_multi_channel_pattern = None


def _connect():
    """Connect to Digitakt MIDI ports using shared helper"""
    global output_port, input_port
    output_port, input_port = connect_midi(DIGITAKT_PORT_NAME, logger)


# ============================================================================
# DEVICE-SPECIFIC LOGGING (Digitakt drum track detection)
# ============================================================================


def log_note_on(note: int, velocity: int, channel: int):
    """Log a note on - Digitakt-specific: notes 0-7 are drum track triggers"""
    if note < 8:
        logger.info(f"🥁 NOTE ON  Track {note + 1} vel={velocity} ch={channel + 1}")
    else:
        logger.info(f"🎹 NOTE ON  {note_name(note)} ({note}) vel={velocity} ch={channel + 1}")


def log_note_off(note: int, channel: int):
    if note < 8:
        logger.debug(f"   NOTE OFF Track {note + 1} ch={channel + 1}")
    else:
        logger.debug(f"   NOTE OFF {note_name(note)} ({note}) ch={channel + 1}")


def check_connection() -> str | None:
    """Check if MIDI output is connected. Returns error message or None."""
    if not output_port:
        return "Error: Not connected to Digitakt MIDI output port"
    return None


# ============================================================================
# BASIC MIDI TOOLS
# ============================================================================


@mcp.tool()
async def send_note(
    note: Annotated[
        int, "MIDI note number (0-127). Track triggers: 0-7 (Track 1-8). Chromatic: 12-84 (plays active track)."
    ],
    velocity: Annotated[int, "Note velocity (1-127). Default is 100."] = 100,
    duration: Annotated[float, "How long to hold the note in seconds. Default is 0.1."] = 0.1,
    channel: Annotated[int, "MIDI channel (1-16). Default is 1."] = 1,
) -> str:
    """Send a MIDI note on/off message to the Digitakt.

    To trigger one-shots on specific audio tracks, use notes 0-7 (Track 1-8).
    To play the active track chromatically, use notes 12-84.
    """
    if err := check_connection():
        return err

    ch = channel - 1  # Convert to 0-indexed

    msg_on = mido.Message("note_on", note=note, velocity=velocity, channel=ch)
    output_port.send(msg_on)
    log_note_on(note, velocity, ch)

    await asyncio.sleep(duration)

    msg_off = mido.Message("note_off", note=note, velocity=0, channel=ch)
    output_port.send(msg_off)
    log_note_off(note, ch)

    return f"Sent note {note} (velocity {velocity}) on channel {channel} for {duration}s"


@mcp.tool()
async def trigger_track(
    track: Annotated[int, "Track number (1-8). Tracks 1-8 correspond to MIDI notes 0-7."],
    velocity: Annotated[int, "Note velocity (1-127). Default is 100."] = 100,
    duration: Annotated[float, "How long to hold the note in seconds. Default is 0.1."] = 0.1,
    channel: Annotated[int, "MIDI channel (1-16). Default is 1 (AUTO CHANNEL)."] = 1,
) -> str:
    """Trigger a one-shot sample on a specific Digitakt track (1-8).

    This is a convenience wrapper that sends the correct MIDI note (0-7) to trigger the track.
    """
    if err := check_connection():
        return err

    ch = channel - 1
    note = track - 1  # Convert track (1-8) to note (0-7)

    msg_on = mido.Message("note_on", note=note, velocity=velocity, channel=ch)
    output_port.send(msg_on)
    log_note_on(note, velocity, ch)

    await asyncio.sleep(duration)

    msg_off = mido.Message("note_off", note=note, velocity=0, channel=ch)
    output_port.send(msg_off)
    log_note_off(note, ch)

    return f"Triggered Track {track} (note {note}, velocity {velocity}) on channel {channel} for {duration}s"


@mcp.tool()
def send_cc(
    cc_number: Annotated[int, "CC number (0-127). Common CCs: 74=Filter Freq, 71=Filter Res, 73=Attack, 75=Decay."],
    value: Annotated[int, "CC value (0-127)"],
    channel: Annotated[int, "MIDI channel (1-16). Default is 1."] = 1,
) -> str:
    """Send a MIDI Control Change (CC) message to control Digitakt parameters."""
    if err := check_connection():
        return err

    ch = channel - 1
    msg = mido.Message("control_change", control=cc_number, value=value, channel=ch)
    output_port.send(msg)
    log_cc(logger, cc_number, value, ch)

    return f"Sent CC {cc_number} = {value} on channel {channel}"


@mcp.tool()
def send_program_change(
    program: Annotated[int, "Program number (0-127). Patterns are numbered 0-127 across banks."],
    channel: Annotated[int, "MIDI channel (1-16). Default is 1."] = 1,
) -> str:
    """Send a MIDI Program Change message to switch patterns on the Digitakt."""
    if err := check_connection():
        return err

    ch = channel - 1
    msg = mido.Message("program_change", program=program, channel=ch)
    output_port.send(msg)
    log_program_change(logger, program, ch)

    return f"Sent Program Change to {program} on channel {channel}"


@mcp.tool()
def send_nrpn(
    msb: Annotated[int, "NRPN MSB (0-127). Use 1 for track parameters."],
    lsb: Annotated[int, "NRPN LSB (0-127). Parameter number within the page."],
    value: Annotated[int, "Parameter value (0-127)"],
    channel: Annotated[int, "MIDI channel (1-16). Channels 1-8 control tracks 1-8. Default is 1."] = 1,
) -> str:
    """Send a MIDI NRPN message for detailed parameter control.

    NRPN (Non-Registered Parameter Number) allows control of parameters not available via CC.
    On Digitakt: MSB=1 for track params, LSB selects the parameter, channel 1-8 = track 1-8.
    """
    if err := check_connection():
        return err

    ch = channel - 1

    # Send NRPN (4 CC messages)
    output_port.send(mido.Message("control_change", control=99, value=msb, channel=ch))
    output_port.send(mido.Message("control_change", control=98, value=lsb, channel=ch))
    output_port.send(mido.Message("control_change", control=6, value=value, channel=ch))
    output_port.send(mido.Message("control_change", control=38, value=0, channel=ch))

    param_name = get_param_name(msb, lsb)
    log_nrpn(logger, msb, lsb, value, ch, param_name)

    return f"Sent NRPN {msb}:{lsb} = {value} on channel {channel}" + (f" ({param_name})" if param_name else "")


# ============================================================================
# TRANSPORT TOOLS
# ============================================================================


@mcp.tool()
def send_midi_start() -> str:
    """Send MIDI Start message to start Digitakt sequencer from the beginning."""
    if err := check_connection():
        return err

    msg = mido.Message("start")
    output_port.send(msg)
    log_transport(logger, "START")

    return "Sent MIDI Start"


@mcp.tool()
def send_midi_stop() -> str:
    """Send MIDI Stop message to stop Digitakt sequencer."""
    if err := check_connection():
        return err

    msg = mido.Message("stop")
    output_port.send(msg)
    log_transport(logger, "STOP")

    return "Sent MIDI Stop"


@mcp.tool()
def send_midi_continue() -> str:
    """Send MIDI Continue message to resume Digitakt sequencer from current position."""
    if err := check_connection():
        return err

    msg = mido.Message("continue")
    output_port.send(msg)
    log_transport(logger, "CONTINUE")

    return "Sent MIDI Continue"


@mcp.tool()
def send_song_position(position: Annotated[int, "Song position in sixteenth notes (0-16383)"]) -> str:
    """Send Song Position Pointer message to set the playback position."""
    if err := check_connection():
        return err

    msg = mido.Message("songpos", pos=position)
    output_port.send(msg)
    logger.info(f"🎯 SONG POSITION: {position}")

    return f"Sent Song Position: {position}"


# ============================================================================
# TRIG TOOLS
# ============================================================================


@mcp.tool()
def set_trig_note(
    track: Annotated[int, "Track number (1-8)"],
    step: Annotated[int, "Step number (1-64)"],
    note: Annotated[int, "MIDI note number (0-127). 60 = C4."],
    channel: Annotated[int, "MIDI channel (1-16). Default matches track."] = 0,
) -> str:
    """Set the note for a specific trig step on a track using NRPN.

    This sets the note that will play when the step triggers.
    """
    if err := check_connection():
        return err

    ch = (channel if channel > 0 else track) - 1

    # NRPN for trig note: MSB=3, LSB=step-1
    msb = 3
    lsb = step - 1

    output_port.send(mido.Message("control_change", control=99, value=msb, channel=ch))
    output_port.send(mido.Message("control_change", control=98, value=lsb, channel=ch))
    output_port.send(mido.Message("control_change", control=6, value=note, channel=ch))
    output_port.send(mido.Message("control_change", control=38, value=0, channel=ch))

    log_nrpn(logger, msb, lsb, note, ch, f"Trig {step} Note")

    return f"Set Track {track} Step {step} note to {note} ({note_name(note)})"


@mcp.tool()
def set_trig_velocity(
    track: Annotated[int, "Track number (1-8)"],
    step: Annotated[int, "Step number (1-64)"],
    velocity: Annotated[int, "Velocity (0-127). 0 = accent off, 127 = full accent."],
    channel: Annotated[int, "MIDI channel (1-16). Default matches track."] = 0,
) -> str:
    """Set the velocity for a specific trig step on a track using NRPN."""
    if err := check_connection():
        return err

    ch = (channel if channel > 0 else track) - 1

    # NRPN for trig velocity: MSB=4, LSB=step-1
    msb = 4
    lsb = step - 1

    output_port.send(mido.Message("control_change", control=99, value=msb, channel=ch))
    output_port.send(mido.Message("control_change", control=98, value=lsb, channel=ch))
    output_port.send(mido.Message("control_change", control=6, value=velocity, channel=ch))
    output_port.send(mido.Message("control_change", control=38, value=0, channel=ch))

    log_nrpn(logger, msb, lsb, velocity, ch, f"Trig {step} Velocity")

    return f"Set Track {track} Step {step} velocity to {velocity}"


@mcp.tool()
def set_trig_length(
    track: Annotated[int, "Track number (1-8)"],
    step: Annotated[int, "Step number (1-64)"],
    length: Annotated[int, "Length (0-127). Higher = longer note."],
    channel: Annotated[int, "MIDI channel (1-16). Default matches track."] = 0,
) -> str:
    """Set the note length for a specific trig step on a track using NRPN."""
    if err := check_connection():
        return err

    ch = (channel if channel > 0 else track) - 1

    # NRPN for trig length: MSB=5, LSB=step-1
    msb = 5
    lsb = step - 1

    output_port.send(mido.Message("control_change", control=99, value=msb, channel=ch))
    output_port.send(mido.Message("control_change", control=98, value=lsb, channel=ch))
    output_port.send(mido.Message("control_change", control=6, value=length, channel=ch))
    output_port.send(mido.Message("control_change", control=38, value=0, channel=ch))

    log_nrpn(logger, msb, lsb, length, ch, f"Trig {step} Length")

    return f"Set Track {track} Step {step} length to {length}"


@mcp.tool()
def reset_velocities(
    track: Annotated[int, "Track number (1-8)"],
    steps: Annotated[int, "Number of steps to reset (1-64). Default is 16."] = 16,
    velocity: Annotated[int, "Velocity to set (0-127). Default is 100."] = 100,
    channel: Annotated[int, "MIDI channel (1-16). Default matches track."] = 0,
) -> str:
    """Reset velocities for all steps on a track to a uniform value."""
    if err := check_connection():
        return err

    ch = (channel if channel > 0 else track) - 1

    for step in range(1, steps + 1):
        msb = 4
        lsb = step - 1

        output_port.send(mido.Message("control_change", control=99, value=msb, channel=ch))
        output_port.send(mido.Message("control_change", control=98, value=lsb, channel=ch))
        output_port.send(mido.Message("control_change", control=6, value=velocity, channel=ch))
        output_port.send(mido.Message("control_change", control=38, value=0, channel=ch))

    logger.info(f"🔄 Reset Track {track} velocities (steps 1-{steps}) to {velocity}")

    return f"Reset Track {track} steps 1-{steps} velocities to {velocity}"


# ============================================================================
# PARAMETER TOOLS
# ============================================================================


@mcp.tool()
def list_parameters(
    category: Annotated[str, "Optional: filter by category name. Shows all if not specified."] = None,
) -> str:
    """List all available parameters that can be automated, organized by category."""
    categories = get_parameters_by_category()

    if category:
        if category in categories:
            params = categories[category]
            result = f"Parameters in category '{category}' ({len(params)}):\n\n"
            for param in params:
                result += f"- {param}\n"
        else:
            result = f"Error: Unknown category '{category}'\n"
            result += f"Available categories: {', '.join(categories.keys())}"
    else:
        result = "Available parameters by category:\n\n"
        for cat_name, params in categories.items():
            result += f"{cat_name} ({len(params)}):\n"
            for param in params:
                result += f"  - {param}\n"
            result += "\n"

        result += f"Total: {len(get_all_parameters())} parameters\n"
        result += "\nUse 'category' parameter to filter by category."

    return result


@mcp.tool()
def set_parameter(
    name: Annotated[str, "Parameter name (e.g., 'filter_freq', 'lfo_speed', 'delay_time')"],
    value: Annotated[int, "Parameter value (0-127 typically, depends on parameter)"],
    channel: Annotated[int, "MIDI channel (1-16). Channels 1-8 = tracks 1-8. Default is 1."] = 1,
) -> str:
    """Set a named Digitakt parameter using the parameter map.

    Use list_parameters to see available parameters.
    """
    if err := check_connection():
        return err

    info = get_parameter_info(name)
    if not info:
        return f"Unknown parameter: {name}. Use list_parameters to see available parameters."

    # Validate value range
    min_val = info.get("min", 0)
    max_val = info.get("max", 127)
    if not (min_val <= value <= max_val):
        return f"Value {value} out of range for {name}. Valid range: {min_val}-{max_val}"

    ch = channel - 1
    cc = info.get("cc")

    if cc is not None:
        msg = mido.Message("control_change", control=cc, value=value, channel=ch)
        output_port.send(msg)
        log_cc(logger, cc, value, ch, name)
        return f"Set {name} = {value} (CC {cc}) on channel {channel}"
    else:
        return f"Parameter {name} does not have a CC mapping"


# ============================================================================
# SEQUENCE & SYSEX TOOLS
# ============================================================================


@mcp.tool()
async def send_note_sequence(
    notes: Annotated[list, "Array of note events. Each event is [note, velocity, duration_sec]."],
    delay: Annotated[float, "Delay between notes in seconds. Default is 0.25."] = 0.25,
    channel: Annotated[int, "MIDI channel (1-16). Default is 1."] = 1,
) -> str:
    """Send a sequence of MIDI notes with timing. Useful for creating rhythms or melodies."""
    if err := check_connection():
        return err

    ch = channel - 1

    for i, (note, velocity, duration) in enumerate(notes):
        msg_on = mido.Message("note_on", note=int(note), velocity=int(velocity), channel=ch)
        output_port.send(msg_on)
        log_note_on(int(note), int(velocity), ch)

        await asyncio.sleep(duration)

        msg_off = mido.Message("note_off", note=int(note), velocity=0, channel=ch)
        output_port.send(msg_off)

        if i < len(notes) - 1:
            await asyncio.sleep(delay)

    return f"Sent sequence of {len(notes)} notes on channel {channel}"


@mcp.tool()
def send_sysex(
    data: Annotated[list, "Array of bytes (0-127) for SysEx message. F0/F7 framing is added automatically."] = None,
    hex_string: Annotated[
        str, "Alternative: hex string like '00 20 3C 0E 00'. F0/F7 framing added automatically."
    ] = None,
) -> str:
    """Send a SysEx (System Exclusive) message to the Digitakt."""
    if err := check_connection():
        return err

    sysex_data = None

    if data:
        sysex_data = data
    elif hex_string:
        hex_str = hex_string.replace(" ", "").replace("0x", "")
        sysex_data = [int(hex_str[i : i + 2], 16) for i in range(0, len(hex_str), 2)]

    if not sysex_data:
        return "Error: Must provide either 'data' array or 'hex_string'"

    msg = mido.Message("sysex", data=sysex_data)
    output_port.send(msg)
    log_sysex(logger, sysex_data)

    hex_display = " ".join([f"{b:02X}" for b in sysex_data[:16]])
    if len(sysex_data) > 16:
        hex_display += f"... ({len(sysex_data)} bytes total)"

    return f"Sent SysEx message: F0 {hex_display} F7"


# ============================================================================
# PLAYBACK TOOLS (with MIDI clock)
# ============================================================================


async def _delayed_note_off(note: int, duration: float, channel: int = 0):
    """Send note off after a delay (wraps shared helper with module-level port)"""
    await delayed_note_off(output_port, note, duration, channel)


@mcp.tool()
async def play_with_clock(
    bars: Annotated[int, "Number of bars to play. Default is 4."] = 4,
    bpm: Annotated[float, "Tempo in BPM. Default is 120."] = 120,
    send_start: Annotated[bool, "Send MIDI Start at beginning. Default is True."] = True,
    send_stop: Annotated[bool, "Send MIDI Stop at end. Default is True."] = True,
) -> str:
    """Play MIDI clock for a specified number of bars.

    This sends MIDI clock messages to sync the Digitakt's sequencer.
    24 clocks per quarter note, 96 per bar (4/4 time).
    """
    if err := check_connection():
        return err

    clock_interval = 60.0 / (bpm * 24)
    total_pulses = int(bars * 96)

    logger.info(f"▶️  PLAY CLOCK: {bars} bars @ {bpm} BPM")

    if send_start:
        output_port.send(mido.Message("start"))
        log_transport(logger, "START")

    start_time = time.time()

    for i in range(total_pulses):
        output_port.send(mido.Message("clock"))

        next_pulse_time = start_time + (i + 1) * clock_interval
        sleep_duration = next_pulse_time - time.time()

        if sleep_duration > 0:
            await asyncio.sleep(sleep_duration)

    if send_stop:
        output_port.send(mido.Message("stop"))
        log_transport(logger, "STOP")
        status = "and stopped"
    else:
        status = "(still running)"

    return f"Played {bars} bars at {bpm} BPM {status}"


@mcp.tool()
async def play_pattern_with_tracks(
    triggers: Annotated[list, "Array of [beat, track, velocity] tuples. Beat is 0-based, track is 1-8."],
    bars: Annotated[int, "Number of bars to play. Default is 4."] = 4,
    bpm: Annotated[float, "Tempo in BPM. Default is 120."] = 120,
    send_stop: Annotated[bool, "Send MIDI Stop at end. Default is True."] = True,
) -> str:
    """Play a pattern with track triggers synced to MIDI clock.

    Each trigger is [beat_position, track_number, velocity].
    Beat positions are in quarter notes (0 = start, 1 = beat 2, etc).
    """
    global last_tracks
    if err := check_connection():
        return err

    last_tracks = {"bpm": bpm, "triggers": triggers}

    clock_interval = 60.0 / (bpm * 24)
    total_pulses = int(bars * 96)

    trigger_schedule = []
    for trigger in triggers:
        beat = trigger[0]
        track = trigger[1]
        velocity = trigger[2] if len(trigger) > 2 else 100
        pulse_index = int(beat * 24)
        trigger_schedule.append((pulse_index, track, velocity, beat))

    trigger_schedule.sort(key=lambda x: x[0])

    logger.info(f"▶️  PLAY PATTERN: {bars} bars @ {bpm} BPM, {len(triggers)} triggers")

    output_port.send(mido.Message("start"))
    log_transport(logger, "START")

    start_time = time.time()
    trigger_idx = 0

    for i in range(total_pulses):
        output_port.send(mido.Message("clock"))

        while trigger_idx < len(trigger_schedule) and trigger_schedule[trigger_idx][0] == i:
            pulse, track, velocity, beat = trigger_schedule[trigger_idx]
            note = track - 1
            output_port.send(mido.Message("note_on", note=note, velocity=velocity, channel=0))
            log_note_on(note, velocity, 0)
            asyncio.create_task(_delayed_note_off(note, 0.05, 0))
            trigger_idx += 1

        next_pulse_time = start_time + (i + 1) * clock_interval
        sleep_duration = next_pulse_time - time.time()

        if sleep_duration > 0:
            await asyncio.sleep(sleep_duration)

    if send_stop:
        output_port.send(mido.Message("stop"))
        log_transport(logger, "STOP")
        status = "and stopped"
    else:
        status = "(still running)"

    return f"Played {bars} bars at {bpm} BPM with {len(triggers)} track triggers {status}"


@mcp.tool()
async def play_pattern_with_melody(
    notes: Annotated[list, "Array of [beat, note, velocity, duration] tuples."],
    bars: Annotated[int, "Number of bars to play. Default is 4."] = 4,
    bpm: Annotated[float, "Tempo in BPM. Default is 120."] = 120,
    channel: Annotated[int, "MIDI channel for melody. Default is 1."] = 1,
    send_stop: Annotated[bool, "Send MIDI Stop at end. Default is True."] = True,
) -> str:
    """Play a melody pattern synced to MIDI clock.

    Each note is [beat_position, midi_note, velocity, duration_seconds].
    Beat positions are in quarter notes.
    """
    global last_melody
    if err := check_connection():
        return err

    ch = channel - 1
    last_melody = {"bpm": bpm, "notes": notes, "channel": channel}

    clock_interval = 60.0 / (bpm * 24)
    total_pulses = int(bars * 96)

    note_schedule = []
    for note_data in notes:
        beat = note_data[0]
        note = note_data[1]
        velocity = note_data[2] if len(note_data) > 2 else 100
        duration = note_data[3] if len(note_data) > 3 else 0.1
        pulse_index = int(beat * 24)
        note_schedule.append((pulse_index, note, velocity, duration))

    note_schedule.sort(key=lambda x: x[0])

    logger.info(f"▶️  PLAY MELODY: {bars} bars @ {bpm} BPM, {len(notes)} notes on ch={channel}")

    output_port.send(mido.Message("start"))
    log_transport(logger, "START")

    start_time = time.time()
    note_idx = 0

    for i in range(total_pulses):
        output_port.send(mido.Message("clock"))

        while note_idx < len(note_schedule) and note_schedule[note_idx][0] == i:
            pulse, note, velocity, duration = note_schedule[note_idx]
            output_port.send(mido.Message("note_on", note=note, velocity=velocity, channel=ch))
            log_note_on(note, velocity, ch)
            asyncio.create_task(_delayed_note_off(note, duration, ch))
            note_idx += 1

        next_pulse_time = start_time + (i + 1) * clock_interval
        sleep_duration = next_pulse_time - time.time()

        if sleep_duration > 0:
            await asyncio.sleep(sleep_duration)

    if send_stop:
        output_port.send(mido.Message("stop"))
        log_transport(logger, "STOP")
        status = "and stopped"
    else:
        status = "(still running)"

    return f"Played {bars} bars at {bpm} BPM with {len(notes)} melody notes {status}"


@mcp.tool()
async def play_pattern_with_loop(
    loop_notes: Annotated[list, "Notes to loop: [[beat_offset, note, velocity], ...]. Beat offset is within the loop."],
    loop_length: Annotated[float, "Loop length in bars. Default is 1."] = 1,
    bars: Annotated[int, "Total bars to play. Default is 4."] = 4,
    bpm: Annotated[float, "Tempo in BPM. Default is 120."] = 120,
    channel: Annotated[int, "MIDI channel. Default is 1."] = 1,
    send_stop: Annotated[bool, "Send MIDI Stop at end. Default is True."] = True,
) -> str:
    """Play a looping pattern synced to MIDI clock.

    The loop_notes define a pattern that repeats every loop_length bars.
    """
    global last_loop
    if err := check_connection():
        return err

    ch = channel - 1
    last_loop = {"bpm": bpm, "loop_notes": loop_notes, "loop_length": loop_length, "channel": channel}

    clock_interval = 60.0 / (bpm * 24)
    total_pulses = int(bars * 96)
    loop_pulses = int(loop_length * 96)

    loop_schedule = []
    for note_data in loop_notes:
        beat_offset = note_data[0]
        note = note_data[1]
        velocity = note_data[2] if len(note_data) > 2 else 100
        pulse_offset = int(beat_offset * 24)
        loop_schedule.append((pulse_offset, note, velocity))

    loop_schedule.sort(key=lambda x: x[0])

    output_port.send(mido.Message("start"))
    log_transport(logger, "START")

    start_time = time.time()

    for i in range(total_pulses):
        output_port.send(mido.Message("clock"))

        loop_position = i % loop_pulses

        for pulse_offset, note, velocity in loop_schedule:
            if pulse_offset == loop_position:
                output_port.send(mido.Message("note_on", note=note, velocity=velocity, channel=ch))
                asyncio.create_task(_delayed_note_off(note, 0.05, ch))

        next_pulse_time = start_time + (i + 1) * clock_interval
        sleep_duration = next_pulse_time - time.time()

        if sleep_duration > 0:
            await asyncio.sleep(sleep_duration)

    if send_stop:
        output_port.send(mido.Message("stop"))
        status = "and stopped"
    else:
        status = "(still running)"

    num_loops = bars / loop_length
    return f"Played {bars} bars at {bpm} BPM with {len(loop_notes)} notes looping every {loop_length} bar(s) ({num_loops:.1f} loops) {status}"


@mcp.tool()
async def play_pattern_with_tracks_and_melody(
    track_triggers: Annotated[
        list, "Track triggers: [[beat, track, velocity], ...]. Optional 4th element for chromatic note."
    ] = None,
    melody_notes: Annotated[list, "Melody notes: [[beat, note, velocity, duration], ...]."] = None,
    bars: Annotated[int, "Number of bars to play. Default is 4."] = 4,
    bpm: Annotated[float, "Tempo in BPM. Default is 120."] = 120,
    channel: Annotated[int, "MIDI channel for melody. Default is 1."] = 1,
    midi_start_at_beat: Annotated[float, "Beat to send MIDI Start. Default is 0."] = 0,
    preroll_bars: Annotated[int, "Bars to delay melody notes (for preroll). Default is 0."] = 0,
    send_stop: Annotated[bool, "Send MIDI Stop at end. Default is True."] = True,
) -> str:
    """Play a pattern combining track triggers and melody notes.

    Track triggers use their track number as the MIDI channel.
    Melody notes use the specified channel.
    """
    if err := check_connection():
        return err

    track_triggers = track_triggers or []
    melody_notes = melody_notes or []
    ch = channel - 1

    clock_interval = 60.0 / (bpm * 24)
    total_pulses = int(bars * 96)
    start_pulse = int(midi_start_at_beat * 24)
    preroll_beats = preroll_bars * 4

    event_schedule = []

    for trigger_data in track_triggers:
        beat = trigger_data[0]
        track = trigger_data[1]
        velocity = trigger_data[2] if len(trigger_data) > 2 else 100
        note = trigger_data[3] if len(trigger_data) > 3 else track - 1
        pulse_index = int(beat * 24)
        track_channel = track - 1
        event_schedule.append(("track", pulse_index, note, velocity, 0.05, track_channel))

    for note_data in melody_notes:
        beat = note_data[0] + preroll_beats
        note = note_data[1]
        velocity = note_data[2] if len(note_data) > 2 else 100
        duration = note_data[3] if len(note_data) > 3 else 0.1
        pulse_index = int(beat * 24)
        event_schedule.append(("melody", pulse_index, note, velocity, duration, ch))

    event_schedule.sort(key=lambda x: x[1])

    start_time = time.time()
    event_idx = 0
    midi_started = False

    for i in range(total_pulses):
        if i == start_pulse and not midi_started:
            if midi_start_at_beat > 0:
                spp_position = int(midi_start_at_beat * 4)
                output_port.send(mido.Message("songpos", pos=spp_position))
            output_port.send(mido.Message("start"))
            log_transport(logger, "START")
            midi_started = True

        if midi_started:
            output_port.send(mido.Message("clock"))

        while event_idx < len(event_schedule) and event_schedule[event_idx][1] == i:
            event_type, pulse, note, velocity, duration, evt_ch = event_schedule[event_idx]
            output_port.send(mido.Message("note_on", note=note, velocity=velocity, channel=evt_ch))
            log_note_on(note, velocity, evt_ch)
            asyncio.create_task(_delayed_note_off(note, duration, evt_ch))
            event_idx += 1

        next_pulse_time = start_time + (i + 1) * clock_interval
        sleep_duration = next_pulse_time - time.time()

        if sleep_duration > 0:
            await asyncio.sleep(sleep_duration)

    if send_stop and midi_started:
        output_port.send(mido.Message("stop"))
        log_transport(logger, "STOP")
        status = "and stopped"
    elif midi_started:
        status = "(still running)"
    else:
        status = "(no MIDI Start sent)"

    return f"Played {bars} bars at {bpm} BPM with {len(track_triggers)} triggers + {len(melody_notes)} melody notes {status}"


@mcp.tool()
async def play_pattern_with_multi_channel_midi(
    track_triggers: Annotated[list, "Track triggers: [[beat, track, velocity], ...]."] = None,
    midi_channels: Annotated[dict, "Notes per channel: {'9': [[beat, note, vel, dur], ...], ...}"] = None,
    bars: Annotated[int, "Number of bars to play. Default is 4."] = 4,
    bpm: Annotated[float, "Tempo in BPM. Default is 120."] = 120,
    parameter_automation: Annotated[dict, "Parameter automation: {'param': [[beat, value], ...]}"] = None,
    automation_loop_bars: Annotated[int, "Bars for automation to loop. 0 = no loop."] = 0,
    send_clock: Annotated[bool, "Send MIDI clock. Default is True."] = True,
    send_stop: Annotated[bool, "Send MIDI Stop at end. Default is True."] = True,
) -> str:
    """Play a complex pattern with multi-channel MIDI and parameter automation.

    track_triggers: Digitakt track triggers [[beat, track_num, velocity], ...]
    midi_channels: Notes per MIDI channel {"channel": [[beat, note, velocity, duration], ...]}
    parameter_automation: Automation curves {"param_name": [[beat, value], ...]}
    """
    global last_multi_channel_pattern
    if err := check_connection():
        return err

    track_triggers = track_triggers or []
    midi_channels = midi_channels or {}
    parameter_automation = parameter_automation or {}

    last_multi_channel_pattern = {
        "bpm": bpm,
        "bars": bars,
        "track_triggers": track_triggers,
        "midi_channels": midi_channels,
    }

    clock_interval = 60.0 / (bpm * 24)
    total_pulses = int(bars * 96)

    event_schedule = []

    # Add track triggers
    for trigger_data in track_triggers:
        beat = trigger_data[0]
        track = trigger_data[1]
        velocity = trigger_data[2] if len(trigger_data) > 2 else 100
        note = trigger_data[3] if len(trigger_data) > 3 else track - 1
        pulse_index = int(beat * 24)
        track_channel = track - 1
        event_schedule.append(("note", pulse_index, note, velocity, 0.05, track_channel))

    # Add MIDI channel notes
    for channel_str, notes in midi_channels.items():
        ch = int(channel_str) - 1
        for note_data in notes:
            beat = note_data[0]
            note = note_data[1]
            velocity = note_data[2] if len(note_data) > 2 else 100
            duration = note_data[3] if len(note_data) > 3 else 0.5
            pulse_index = int(beat * 24)
            event_schedule.append(("note", pulse_index, note, velocity, duration, ch))

    # Add parameter automation
    for param_name, param_events in parameter_automation.items():
        param_info = get_parameter_info(param_name)
        if not param_info:
            continue

        for beat, value in param_events:
            pulse_index = int(beat * 24)
            if param_info.get("cc") is not None:
                event_schedule.append(("cc", pulse_index, param_info["cc"], value, 0, 0))

    event_schedule.sort(key=lambda x: x[1])

    logger.info(f"▶️  PLAY MULTI-CHANNEL: {bars} bars @ {bpm} BPM")

    if send_clock:
        output_port.send(mido.Message("start"))
        log_transport(logger, "START")

    start_time = time.time()
    event_idx = 0

    for i in range(total_pulses):
        if send_clock:
            output_port.send(mido.Message("clock"))

        while event_idx < len(event_schedule) and event_schedule[event_idx][1] == i:
            evt = event_schedule[event_idx]
            evt_type = evt[0]

            if evt_type == "note":
                _, pulse, note, velocity, duration, ch = evt
                output_port.send(mido.Message("note_on", note=note, velocity=velocity, channel=ch))
                asyncio.create_task(_delayed_note_off(note, duration, ch))
            elif evt_type == "cc":
                _, pulse, cc, value, _, ch = evt
                output_port.send(mido.Message("control_change", control=cc, value=value, channel=ch))

            event_idx += 1

        next_pulse_time = start_time + (i + 1) * clock_interval
        sleep_duration = next_pulse_time - time.time()

        if sleep_duration > 0:
            await asyncio.sleep(sleep_duration)

    if send_stop and send_clock:
        output_port.send(mido.Message("stop"))
        log_transport(logger, "STOP")
        status = "and stopped"
    else:
        status = "(still running)" if send_clock else "(no clock)"

    return f"Played {bars} bars at {bpm} BPM with {len(track_triggers)} triggers + {len(midi_channels)} MIDI channels {status}"


# ============================================================================
# PARAMETER AUTOMATION TOOLS
# ============================================================================


@mcp.tool()
async def send_parameter_sweep(
    parameter: Annotated[str, "Parameter name (e.g., 'filter_freq', 'lfo_speed')"],
    start_value: Annotated[int, "Starting value (0-127)"],
    end_value: Annotated[int, "Ending value (0-127)"],
    duration: Annotated[float, "Sweep duration in seconds"],
    steps: Annotated[int, "Number of steps. Default is 64."] = 64,
    channel: Annotated[int, "MIDI channel (1-16). Default is 1."] = 1,
) -> str:
    """Sweep a parameter from start to end value over a duration."""
    if err := check_connection():
        return err

    param_info = get_parameter_info(parameter)
    if not param_info:
        return f"Unknown parameter: {parameter}"

    cc = param_info.get("cc")
    if cc is None:
        return f"Parameter {parameter} does not have a CC mapping"

    ch = channel - 1
    step_duration = duration / steps
    value_step = (end_value - start_value) / steps

    logger.info(f"🎚️  SWEEP {parameter}: {start_value} → {end_value} over {duration}s")

    for i in range(steps + 1):
        value = int(start_value + value_step * i)
        value = max(0, min(127, value))
        output_port.send(mido.Message("control_change", control=cc, value=value, channel=ch))
        await asyncio.sleep(step_duration)

    return f"Swept {parameter} from {start_value} to {end_value} over {duration}s"


@mcp.tool()
async def send_parameter_envelope(
    parameter: Annotated[str, "Parameter name (e.g., 'filter_freq')"],
    attack_time: Annotated[float, "Attack time in seconds"],
    attack_level: Annotated[int, "Attack peak level (0-127)"],
    decay_time: Annotated[float, "Decay time in seconds"],
    sustain_level: Annotated[int, "Sustain level (0-127)"],
    sustain_time: Annotated[float, "Sustain time in seconds"],
    release_time: Annotated[float, "Release time in seconds"],
    start_level: Annotated[int, "Starting level. Default is 0."] = 0,
    end_level: Annotated[int, "Ending level. Default is 0."] = 0,
    channel: Annotated[int, "MIDI channel (1-16). Default is 1."] = 1,
    steps_per_second: Annotated[int, "Resolution. Default is 30."] = 30,
) -> str:
    """Apply an ADSR envelope to a parameter."""
    if err := check_connection():
        return err

    param_info = get_parameter_info(parameter)
    if not param_info:
        return f"Unknown parameter: {parameter}"

    cc = param_info.get("cc")
    if cc is None:
        return f"Parameter {parameter} does not have a CC mapping"

    ch = channel - 1

    async def sweep(from_val, to_val, duration):
        if duration <= 0:
            return
        steps = max(1, int(duration * steps_per_second))
        step_duration = duration / steps
        for i in range(steps + 1):
            t = i / steps
            value = int(from_val + (to_val - from_val) * t)
            value = max(0, min(127, value))
            output_port.send(mido.Message("control_change", control=cc, value=value, channel=ch))
            await asyncio.sleep(step_duration)

    logger.info(f"🎚️  ENVELOPE {parameter}: A={attack_time}s D={decay_time}s S={sustain_time}s R={release_time}s")

    # Attack
    await sweep(start_level, attack_level, attack_time)
    # Decay
    await sweep(attack_level, sustain_level, decay_time)
    # Sustain
    await asyncio.sleep(sustain_time)
    # Release
    await sweep(sustain_level, end_level, release_time)

    return f"Applied envelope to {parameter}"


@mcp.tool()
async def play_pattern_with_parameter_automation(
    triggers: Annotated[list, "Track triggers: [[beat, track, velocity], ...]"],
    parameter_automation: Annotated[dict, "Automation: {'param': [[beat, value], ...]}"],
    bars: Annotated[int, "Number of bars. Default is 4."] = 4,
    bpm: Annotated[float, "Tempo in BPM. Default is 120."] = 120,
    automation_loop_bars: Annotated[int, "Bars for automation loop. 0 = no loop."] = 0,
    send_stop: Annotated[bool, "Send MIDI Stop at end. Default is True."] = True,
) -> str:
    """Play a pattern with synchronized parameter automation."""
    if err := check_connection():
        return err

    clock_interval = 60.0 / (bpm * 24)
    total_pulses = int(bars * 96)
    automation_loop_pulses = int(automation_loop_bars * 96) if automation_loop_bars > 0 else 0

    # Build event schedule
    event_schedule = []

    # Add triggers
    for trigger in triggers:
        beat = trigger[0]
        track = trigger[1]
        velocity = trigger[2] if len(trigger) > 2 else 100
        note = track - 1
        pulse = int(beat * 24)
        event_schedule.append(("note", pulse, note, velocity, 0))

    # Add automation
    for param_name, events in parameter_automation.items():
        param_info = get_parameter_info(param_name)
        if not param_info or param_info.get("cc") is None:
            continue
        cc = param_info["cc"]
        for beat, value in events:
            pulse = int(beat * 24)
            event_schedule.append(("cc", pulse, cc, value, 0))

    event_schedule.sort(key=lambda x: x[1])

    logger.info(f"▶️  PLAY WITH AUTOMATION: {bars} bars @ {bpm} BPM")

    output_port.send(mido.Message("start"))
    log_transport(logger, "START")

    start_time = time.time()
    event_idx = 0

    for i in range(total_pulses):
        output_port.send(mido.Message("clock"))

        effective_pulse = i
        if automation_loop_pulses > 0:
            effective_pulse = i % automation_loop_pulses

        while event_idx < len(event_schedule):
            evt = event_schedule[event_idx]
            evt_pulse = evt[1]

            # Handle looping automation
            check_pulse = evt_pulse
            if automation_loop_pulses > 0 and evt[0] == "cc":
                check_pulse = evt_pulse % automation_loop_pulses if evt_pulse < total_pulses else evt_pulse

            if evt[0] == "note" and evt_pulse == i:
                _, pulse, note, velocity, _ = evt
                output_port.send(mido.Message("note_on", note=note, velocity=velocity, channel=0))
                asyncio.create_task(_delayed_note_off(note, 0.05, 0))
                event_idx += 1
            elif evt[0] == "cc" and check_pulse == effective_pulse:
                _, pulse, cc, value, _ = evt
                output_port.send(mido.Message("control_change", control=cc, value=value, channel=0))
                event_idx += 1
            else:
                break

        next_pulse_time = start_time + (i + 1) * clock_interval
        sleep_duration = next_pulse_time - time.time()

        if sleep_duration > 0:
            await asyncio.sleep(sleep_duration)

    if send_stop:
        output_port.send(mido.Message("stop"))
        log_transport(logger, "STOP")

    return f"Played {bars} bars with {len(triggers)} triggers and {len(parameter_automation)} automated parameters"


# ============================================================================
# EXPORT TOOLS
# ============================================================================


@mcp.tool()
def export_pattern_to_midi(
    filename: Annotated[str, "Output filename"],
    bpm: Annotated[float, "Tempo in BPM. Default is 120."] = 120,
    bars: Annotated[int, "Number of bars. Default is 4."] = 4,
    track_triggers: Annotated[list, "Track triggers: [[beat, track, velocity], ...]"] = None,
    melody_notes: Annotated[list, "Melody notes: [[beat, note, velocity, duration], ...]"] = None,
    melody_channel: Annotated[int, "MIDI channel for melody. Default is 1."] = 1,
) -> str:
    """Export a pattern to a standard MIDI file."""
    track_triggers = track_triggers or []
    melody_notes = melody_notes or []

    if not filename.endswith(".mid"):
        filename += ".mid"

    filepath = RECORDINGS_DIR / filename

    mid = mido.MidiFile()
    ticks_per_beat = mid.ticks_per_beat

    # Tempo track
    tempo_track = mido.MidiTrack()
    mid.tracks.append(tempo_track)
    tempo_track.append(mido.MetaMessage("set_tempo", tempo=mido.bpm2tempo(bpm)))
    tempo_track.append(mido.MetaMessage("time_signature", numerator=4, denominator=4))

    # Drum track
    if track_triggers:
        drum_track = mido.MidiTrack()
        mid.tracks.append(drum_track)
        drum_track.append(mido.MetaMessage("track_name", name="Digitakt Drums"))

        sorted_triggers = sorted(track_triggers, key=lambda x: x[0])
        current_tick = 0

        for trigger in sorted_triggers:
            beat = trigger[0]
            track_num = trigger[1]
            velocity = trigger[2] if len(trigger) > 2 else 100
            note = trigger[3] if len(trigger) > 3 else track_num - 1

            tick = int(beat * ticks_per_beat)
            delta_time = tick - current_tick

            drum_track.append(mido.Message("note_on", channel=0, note=note, velocity=velocity, time=delta_time))
            note_off_ticks = int(0.1 * ticks_per_beat * bpm / 60)
            drum_track.append(mido.Message("note_off", channel=0, note=note, velocity=0, time=note_off_ticks))

            current_tick = tick + note_off_ticks

        drum_track.append(mido.MetaMessage("end_of_track", time=0))

    # Melody track
    if melody_notes:
        melody_track = mido.MidiTrack()
        mid.tracks.append(melody_track)
        melody_track.append(mido.MetaMessage("track_name", name=f"Melody Ch{melody_channel}"))

        sorted_notes = sorted(melody_notes, key=lambda x: x[0])
        current_tick = 0
        ch = melody_channel - 1

        for note_data in sorted_notes:
            beat = note_data[0]
            note = note_data[1]
            velocity = note_data[2] if len(note_data) > 2 else 100
            duration = note_data[3] if len(note_data) > 3 else 0.5

            tick = int(beat * ticks_per_beat)
            delta_time = tick - current_tick

            melody_track.append(mido.Message("note_on", channel=ch, note=note, velocity=velocity, time=delta_time))
            duration_ticks = int(duration * ticks_per_beat * bpm / 60)
            melody_track.append(mido.Message("note_off", channel=ch, note=note, velocity=0, time=duration_ticks))

            current_tick = tick + duration_ticks

        melody_track.append(mido.MetaMessage("end_of_track", time=0))

    mid.save(filepath)

    return (
        f"Exported pattern to {filepath}: {bars} bars, {len(track_triggers)} triggers, {len(melody_notes)} melody notes"
    )


@mcp.tool()
def update_pattern(
    pattern_name: Annotated[str, "Name of the pattern to update"],
    bpm: Annotated[float, "New tempo (optional)"] = None,
    bars: Annotated[int, "New bar count (optional)"] = None,
    track_triggers: Annotated[list, "New track triggers (optional)"] = None,
    midi_channels: Annotated[dict, "New MIDI channel data (optional)"] = None,
    parameter_automation: Annotated[dict, "New automation (optional)"] = None,
    automation_loop_bars: Annotated[int, "New automation loop bars (optional)"] = None,
    description: Annotated[str, "New description (optional)"] = None,
) -> str:
    """Update specific fields of an existing pattern."""
    if pattern_name.endswith(".json"):
        pattern_name = pattern_name[:-5]

    pattern_file = PATTERN_DIR / f"{pattern_name}.json"

    if not pattern_file.exists():
        return f"Error: Pattern '{pattern_name}' not found"

    with open(pattern_file) as f:
        pattern_data = json.load(f)

    updated_fields = []
    if bpm is not None:
        pattern_data["bpm"] = bpm
        updated_fields.append("bpm")
    if bars is not None:
        pattern_data["bars"] = bars
        updated_fields.append("bars")
    if track_triggers is not None:
        pattern_data["track_triggers"] = track_triggers
        updated_fields.append("track_triggers")
    if midi_channels is not None:
        pattern_data["midi_channels"] = midi_channels
        updated_fields.append("midi_channels")
    if parameter_automation is not None:
        pattern_data["parameter_automation"] = parameter_automation
        updated_fields.append("parameter_automation")
    if automation_loop_bars is not None:
        pattern_data["automation_loop_bars"] = automation_loop_bars
        updated_fields.append("automation_loop_bars")
    if description is not None:
        pattern_data["description"] = description
        updated_fields.append("description")

    with open(pattern_file, "w") as f:
        json.dump(pattern_data, f, indent=2)

    return f"Updated pattern '{pattern_name}': modified {', '.join(updated_fields)}"


@mcp.tool()
def edit_pattern_chords(
    pattern_name: Annotated[str, "Name of the pattern to edit"],
    bar: Annotated[int, "Bar number (0-based) where to place the chord"],
    chord_notes: Annotated[list, "MIDI notes for the chord (e.g., [60, 64, 67] for C major)"],
    channels: Annotated[list, "MIDI channels to use for chord notes. Default is [9, 10, 11, 12]."] = None,
    velocity: Annotated[int, "Velocity for chord notes. Default is 75."] = 75,
) -> str:
    """Edit chord notes at a specific bar position in a pattern."""
    if pattern_name.endswith(".json"):
        pattern_name = pattern_name[:-5]

    pattern_file = PATTERN_DIR / f"{pattern_name}.json"

    if not pattern_file.exists():
        return f"Error: Pattern '{pattern_name}' not found"

    channels = channels or [9, 10, 11, 12]

    with open(pattern_file) as f:
        pattern_data = json.load(f)

    midi_channels = pattern_data.get("midi_channels", {})
    total_bars = pattern_data.get("bars", 4)
    beat_position = bar * 4  # 4 beats per bar

    # Calculate duration to next chord
    next_chord_beat = total_bars * 4
    for ch_str in [str(ch) for ch in channels]:
        if ch_str in midi_channels:
            for note_data in midi_channels[ch_str]:
                note_beat = note_data[0]
                if note_beat > beat_position:
                    next_chord_beat = min(next_chord_beat, note_beat)

    duration = next_chord_beat - beat_position - 0.1
    if duration < 0.1:
        duration = 0.1

    # Remove existing notes at this position for these channels
    for ch in channels:
        ch_str = str(ch)
        if ch_str in midi_channels:
            midi_channels[ch_str] = [n for n in midi_channels[ch_str] if abs(n[0] - beat_position) > 0.01]
        else:
            midi_channels[ch_str] = []

    # Add new chord notes
    for i, note in enumerate(chord_notes):
        if i < len(channels):
            ch_str = str(channels[i])
            offset = i * 0.01  # Slight strum effect
            midi_channels[ch_str].append([beat_position + offset, note, velocity, duration])

    # Sort and save
    for ch_str in midi_channels:
        midi_channels[ch_str].sort(key=lambda x: x[0])

    pattern_data["midi_channels"] = midi_channels

    with open(pattern_file, "w") as f:
        json.dump(pattern_data, f, indent=2)

    return f"Set chord {chord_notes} at bar {bar} in pattern '{pattern_name}'"


@mcp.tool()
def edit_pattern_triggers(
    pattern_name: Annotated[str, "Name of the pattern to edit"],
    track: Annotated[int, "Track number (1-8)"],
    beats: Annotated[list, "Beat positions for triggers (e.g., [0, 1, 2, 3])"],
    velocity: Annotated[int, "Velocity for triggers. Default is 100."] = 100,
    note: Annotated[int, "Chromatic note (optional). If omitted, uses track-1 as note."] = None,
    mode: Annotated[str, "Edit mode: 'add', 'remove', or 'replace'. Default is 'add'."] = "add",
) -> str:
    """Edit track triggers in a pattern."""
    if pattern_name.endswith(".json"):
        pattern_name = pattern_name[:-5]

    pattern_file = PATTERN_DIR / f"{pattern_name}.json"

    if not pattern_file.exists():
        return f"Error: Pattern '{pattern_name}' not found"

    with open(pattern_file) as f:
        pattern_data = json.load(f)

    track_triggers = pattern_data.get("track_triggers", [])

    if mode == "replace":
        # Remove all existing triggers for this track
        track_triggers = [t for t in track_triggers if t[1] != track]
        # Add new triggers
        for beat in beats:
            if note is not None:
                track_triggers.append([beat, track, velocity, note])
            else:
                track_triggers.append([beat, track, velocity])
        action = f"Replaced track {track} triggers"

    elif mode == "remove":
        beats_set = set(beats)
        original_count = len([t for t in track_triggers if t[1] == track])
        track_triggers = [t for t in track_triggers if not (t[1] == track and t[0] in beats_set)]
        removed = original_count - len([t for t in track_triggers if t[1] == track])
        action = f"Removed {removed} triggers from track {track}"

    else:  # add
        existing = {t[0] for t in track_triggers if t[1] == track}
        added = 0
        for beat in beats:
            if beat not in existing:
                if note is not None:
                    track_triggers.append([beat, track, velocity, note])
                else:
                    track_triggers.append([beat, track, velocity])
                added += 1
        action = f"Added {added} triggers to track {track}"

    track_triggers.sort(key=lambda x: x[0])
    pattern_data["track_triggers"] = track_triggers

    with open(pattern_file, "w") as f:
        json.dump(pattern_data, f, indent=2)

    track_count = len([t for t in track_triggers if t[1] == track])
    return f"{action} in pattern '{pattern_name}'. Track {track} now has {track_count} triggers."


@mcp.tool()
def export_automation_to_midi(
    filename: Annotated[str, "Output filename"],
    automation: Annotated[dict, "Automation data: {'parameter_automation': {...}, 'bars': N, 'bpm': N}"],
    channel: Annotated[int, "MIDI channel. Default is 1."] = 1,
) -> str:
    """Export parameter automation to a MIDI file."""
    if not filename.endswith(".mid"):
        filename += ".mid"

    filepath = RECORDINGS_DIR / filename
    ch = channel - 1

    parameter_automation = automation.get("parameter_automation", {})
    bpm = automation.get("bpm", 120)

    mid = mido.MidiFile()
    track = mido.MidiTrack()
    mid.tracks.append(track)

    track.append(mido.MetaMessage("set_tempo", tempo=mido.bpm2tempo(bpm)))

    events = []
    for param_name, param_events in parameter_automation.items():
        param_info = get_parameter_info(param_name)
        if not param_info:
            continue

        for beat, value in param_events:
            ticks = int(beat * 480)
            if param_info.get("cc") is not None:
                events.append((ticks, "cc", param_info["cc"], value))

    events.sort(key=lambda x: x[0])

    last_ticks = 0
    for event in events:
        ticks, _, cc, value = event
        delta = ticks - last_ticks
        track.append(mido.Message("control_change", control=cc, value=value, channel=ch, time=delta))
        last_ticks = ticks

    mid.save(filepath)

    return f"Exported automation to {filepath}: {len(events)} CC events"


# ============================================================================
# SAVE/EXPORT TOOLS
# ============================================================================


@mcp.tool()
def save_last_melody(filename: Annotated[str, "Output filename (without extension, will add .mid)"]) -> str:
    """Save the last played melody to a MIDI file."""
    global last_melody
    if not last_melody:
        return "No melody has been played yet. Use play_pattern_with_melody first."

    if not filename.endswith(".mid"):
        filename += ".mid"

    filepath = RECORDINGS_DIR / filename
    bpm = last_melody["bpm"]
    notes = last_melody["notes"]
    channel = last_melody.get("channel", 1) - 1

    mid = mido.MidiFile()
    tempo_track = mido.MidiTrack()
    mid.tracks.append(tempo_track)
    tempo_track.append(mido.MetaMessage("set_tempo", tempo=mido.bpm2tempo(bpm)))

    melody_track = mido.MidiTrack()
    mid.tracks.append(melody_track)
    melody_track.append(mido.MetaMessage("track_name", name="Melody"))

    ticks_per_beat = mid.ticks_per_beat
    sorted_notes = sorted(notes, key=lambda x: x[0])

    current_tick = 0
    for note_data in sorted_notes:
        beat = note_data[0]
        note = note_data[1]
        velocity = note_data[2] if len(note_data) > 2 else 100
        duration = note_data[3] if len(note_data) > 3 else 0.1

        tick = int(beat * ticks_per_beat)
        delta_time = tick - current_tick

        melody_track.append(mido.Message("note_on", channel=channel, note=note, velocity=velocity, time=delta_time))
        duration_ticks = int(duration * ticks_per_beat * bpm / 60)
        melody_track.append(mido.Message("note_off", channel=channel, note=note, velocity=0, time=duration_ticks))

        current_tick = tick + duration_ticks

    melody_track.append(mido.MetaMessage("end_of_track", time=0))
    mid.save(filepath)

    return f"Saved melody to {filepath} ({len(notes)} notes at {bpm} BPM)"


@mcp.tool()
def save_last_pattern(filename: Annotated[str, "Output filename (without extension, will add .mid)"]) -> str:
    """Save the last played track pattern to a MIDI file."""
    global last_tracks
    if not last_tracks:
        return "No pattern has been played yet. Use play_pattern_with_tracks first."

    if not filename.endswith(".mid"):
        filename += ".mid"

    filepath = RECORDINGS_DIR / filename
    bpm = last_tracks["bpm"]
    triggers = last_tracks["triggers"]

    mid = mido.MidiFile()
    tempo_track = mido.MidiTrack()
    mid.tracks.append(tempo_track)
    tempo_track.append(mido.MetaMessage("set_tempo", tempo=mido.bpm2tempo(bpm)))

    drum_track = mido.MidiTrack()
    mid.tracks.append(drum_track)
    drum_track.append(mido.MetaMessage("track_name", name="Drums"))

    ticks_per_beat = mid.ticks_per_beat
    sorted_triggers = sorted(triggers, key=lambda x: x[0])

    current_tick = 0
    for trigger in sorted_triggers:
        beat = trigger[0]
        track = trigger[1]
        velocity = trigger[2] if len(trigger) > 2 else 100
        note = track - 1

        tick = int(beat * ticks_per_beat)
        delta_time = tick - current_tick

        drum_track.append(mido.Message("note_on", channel=0, note=note, velocity=velocity, time=delta_time))
        note_off_ticks = int(0.1 * ticks_per_beat * bpm / 60)
        drum_track.append(mido.Message("note_off", channel=0, note=note, velocity=0, time=note_off_ticks))

        current_tick = tick + note_off_ticks

    drum_track.append(mido.MetaMessage("end_of_track", time=0))
    mid.save(filepath)

    return f"Saved pattern to {filepath} ({len(triggers)} triggers at {bpm} BPM)"


# ============================================================================
# AUTOMATION PRESET TOOLS
# ============================================================================


@mcp.tool()
def save_automation_preset(
    name: Annotated[str, "Preset name"],
    parameter_automation: Annotated[dict, "Automation data: {'param': [[beat, value], ...]}"],
    description: Annotated[str, "Description of the preset"] = "",
) -> str:
    """Save parameter automation as a reusable preset."""
    preset_file = PRESET_DIR / f"{name}.json"

    preset_data = {"name": name, "description": description, "parameter_automation": parameter_automation}

    with open(preset_file, "w") as f:
        json.dump(preset_data, f, indent=2)

    return f"Saved automation preset '{name}' to {preset_file}"


@mcp.tool()
def load_automation_preset(name: Annotated[str, "Preset name to load"]) -> str:
    """Load a saved automation preset."""
    preset_file = PRESET_DIR / f"{name}.json"

    if not preset_file.exists():
        return f"Error: Preset '{name}' not found at {preset_file}"

    with open(preset_file) as f:
        preset_data = json.load(f)

    return json.dumps(preset_data, indent=2)


@mcp.tool()
def list_automation_presets() -> str:
    """List all saved automation presets."""
    preset_files = list(PRESET_DIR.glob("*.json"))

    if not preset_files:
        return f"No presets found in {PRESET_DIR}"

    result = f"Available automation presets ({len(preset_files)}):\n\n"

    for preset_file in sorted(preset_files):
        try:
            with open(preset_file) as f:
                preset_data = json.load(f)
            pname = preset_data.get("name", preset_file.stem)
            desc = preset_data.get("description", "No description")
            result += f"- {pname}: {desc}\n"
        except Exception as e:
            result += f"- {preset_file.stem}: (Error loading: {e})\n"

    result += f"\nPresets stored in: {PRESET_DIR}"

    return result


# ============================================================================
# PATTERN SAVE/LOAD TOOLS
# ============================================================================


@mcp.tool()
def save_pattern(
    pattern_name: Annotated[str, "Name for the pattern"],
    bpm: Annotated[float, "Tempo in BPM"],
    bars: Annotated[int, "Number of bars"],
    track_triggers: Annotated[list, "Track triggers: [[beat, track, velocity], ...]"],
    midi_channels: Annotated[dict, "Notes per channel: {'9': [[beat, note, vel, dur], ...]}"],
    parameter_automation: Annotated[dict, "Parameter automation"] = None,
    automation_loop_bars: Annotated[int, "Bars for automation loop. 0 = no loop."] = 0,
    description: Annotated[str, "Pattern description"] = "",
) -> str:
    """Save a complete pattern including triggers, MIDI notes, and automation."""
    if pattern_name.endswith(".json"):
        pattern_name = pattern_name[:-5]

    pattern_file = PATTERN_DIR / f"{pattern_name}.json"

    pattern_data = {
        "name": pattern_name,
        "description": description,
        "bpm": bpm,
        "bars": bars,
        "track_triggers": track_triggers,
        "midi_channels": midi_channels,
        "parameter_automation": parameter_automation or {},
        "automation_loop_bars": automation_loop_bars,
    }

    with open(pattern_file, "w") as f:
        json.dump(pattern_data, f, indent=2)

    return (
        f"Saved pattern '{pattern_name}' to {pattern_file}\n"
        f"  BPM: {bpm}, Bars: {bars}\n"
        f"  Track triggers: {len(track_triggers)}\n"
        f"  MIDI channels: {list(midi_channels.keys())}"
    )


@mcp.tool()
def load_pattern(
    pattern_name: Annotated[str, "Name of the pattern to load"],
    play: Annotated[bool, "Whether to play the pattern after loading"] = False,
    repeat: Annotated[int, "Number of times to repeat when playing. Default is 1."] = 1,
) -> str:
    """Load a saved pattern and optionally play it."""
    if pattern_name.endswith(".json"):
        pattern_name = pattern_name[:-5]

    pattern_file = PATTERN_DIR / f"{pattern_name}.json"

    if not pattern_file.exists():
        return f"Error: Pattern '{pattern_name}' not found at {pattern_file}"

    with open(pattern_file) as f:
        pattern_data = json.load(f)

    if play:
        return f"Pattern '{pattern_name}' loaded. Use play_pattern_with_multi_channel_midi with the pattern data to play it."
    else:
        return (
            f"Loaded pattern '{pattern_name}':\n"
            f"  Description: {pattern_data.get('description', 'N/A')}\n"
            f"  BPM: {pattern_data.get('bpm')}, Bars: {pattern_data.get('bars')}\n"
            f"  Track triggers: {len(pattern_data.get('track_triggers', []))}\n"
            f"  MIDI channels: {list(pattern_data.get('midi_channels', {}).keys())}\n\n"
            f"Pattern data:\n{json.dumps(pattern_data, indent=2)}"
        )


@mcp.tool()
def list_patterns() -> str:
    """List all saved patterns."""
    pattern_files = list(PATTERN_DIR.glob("*.json"))

    if not pattern_files:
        return f"No patterns found in {PATTERN_DIR}"

    result = f"Available patterns ({len(pattern_files)}):\n\n"

    for pattern_file in sorted(pattern_files):
        try:
            with open(pattern_file) as f:
                pattern_data = json.load(f)
            pname = pattern_data.get("name", pattern_file.stem)
            desc = pattern_data.get("description", "No description")
            bpm = pattern_data.get("bpm", "?")
            bars = pattern_data.get("bars", "?")
            num_triggers = len(pattern_data.get("track_triggers", []))
            channels = list(pattern_data.get("midi_channels", {}).keys())
            result += f"- {pname}: {desc}\n"
            result += f"    BPM: {bpm}, Bars: {bars}, Triggers: {num_triggers}, Channels: {channels}\n"
        except Exception as e:
            result += f"- {pattern_file.stem}: (Error loading: {e})\n"

    result += f"\nPatterns stored in: {PATTERN_DIR}"
    return result


@mcp.tool()
def delete_pattern(pattern_name: Annotated[str, "Name of the pattern to delete"]) -> str:
    """Delete a saved pattern."""
    if pattern_name.endswith(".json"):
        pattern_name = pattern_name[:-5]

    pattern_file = PATTERN_DIR / f"{pattern_name}.json"

    if not pattern_file.exists():
        return f"Error: Pattern '{pattern_name}' not found at {pattern_file}"

    pattern_file.unlink()
    return f"Deleted pattern '{pattern_name}'"


# ============================================================================
# RECORDING TOOLS
# ============================================================================


@mcp.tool()
async def monitor_midi_input(duration: Annotated[float, "Duration to monitor in seconds. Default is 10."] = 10) -> str:
    """Monitor incoming MIDI messages for a specified duration."""
    if not input_port:
        return "Error: Not connected to Digitakt MIDI input port"

    logger.info(f"👂 MONITORING MIDI INPUT for {duration} seconds...")

    messages = []
    start_time = time.time()

    while time.time() - start_time < duration:
        for msg in input_port.iter_pending():
            elapsed = time.time() - start_time
            messages.append(f"{elapsed:.2f}s: {msg}")
            logger.info(f"📥 {msg}")

        await asyncio.sleep(0.01)

    if not messages:
        return f"No MIDI messages received in {duration} seconds"

    return f"Received {len(messages)} messages:\n" + "\n".join(messages[:50])


@mcp.tool()
async def record_midi_input(
    filename: Annotated[str, "Output filename (will be saved in recordings directory)"],
    duration_sec: Annotated[float, "Recording duration in seconds. Default is 30."] = 30,
    bpm: Annotated[float, "Tempo for the recording. Default is 120."] = 120,
) -> str:
    """Record incoming MIDI to a .mid file."""
    if not input_port:
        return "Error: Not connected to Digitakt MIDI input port"

    if not filename.endswith(".mid"):
        filename += ".mid"

    filepath = RECORDINGS_DIR / filename

    logger.info(f"⏺️  RECORDING MIDI INPUT to {filepath} for {duration_sec} seconds...")

    mid = mido.MidiFile()
    tempo_track = mido.MidiTrack()
    mid.tracks.append(tempo_track)
    tempo_track.append(mido.MetaMessage("set_tempo", tempo=mido.bpm2tempo(bpm)))

    recording_track = mido.MidiTrack()
    mid.tracks.append(recording_track)
    recording_track.append(mido.MetaMessage("track_name", name="Recording"))

    ticks_per_beat = mid.ticks_per_beat
    ticks_per_second = ticks_per_beat * bpm / 60

    messages = []
    start_time = time.time()

    while time.time() - start_time < duration_sec:
        for msg in input_port.iter_pending():
            elapsed = time.time() - start_time
            if not msg.is_meta:
                messages.append((elapsed, msg))
                logger.info(f"📥 {elapsed:.2f}s: {msg}")

        await asyncio.sleep(0.01)

    # Convert to MIDI file format
    current_tick = 0
    for elapsed, msg in messages:
        tick = int(elapsed * ticks_per_second)
        delta = tick - current_tick

        if msg.type in ("note_on", "note_off", "control_change"):
            recording_track.append(msg.copy(time=delta))
            current_tick = tick

    recording_track.append(mido.MetaMessage("end_of_track", time=0))
    mid.save(filepath)

    return f"Recorded {len(messages)} MIDI messages to {filepath}"


@mcp.tool()
def list_midi_recordings() -> str:
    """List all MIDI recordings in the recordings directory."""
    midi_files = list(RECORDINGS_DIR.glob("*.mid"))

    if not midi_files:
        return f"No recordings found in {RECORDINGS_DIR}"

    result = f"MIDI Recordings ({len(midi_files)}):\n\n"

    for midi_file in sorted(midi_files):
        try:
            mid = mido.MidiFile(midi_file)
            duration = mid.length
            num_tracks = len(mid.tracks)
            result += f"- {midi_file.name}: {duration:.1f}s, {num_tracks} tracks\n"
        except Exception as e:
            result += f"- {midi_file.name}: (Error reading: {e})\n"

    result += f"\nRecordings stored in: {RECORDINGS_DIR}"
    return result


@mcp.tool()
async def play_midi_file(
    filename: Annotated[str, "MIDI file to play (from recordings directory)"],
    channel_offset: Annotated[int, "Offset to add to all MIDI channels. Default is 0."] = 0,
) -> str:
    """Play a MIDI file through the Digitakt."""
    if err := check_connection():
        return err

    if not filename.endswith(".mid"):
        filename += ".mid"

    filepath = RECORDINGS_DIR / filename

    if not filepath.exists():
        return f"Error: File not found: {filepath}"

    mid = mido.MidiFile(filepath)

    logger.info(f"▶️  PLAYING MIDI FILE: {filepath}")

    for msg in mid.play():
        if not msg.is_meta:
            if hasattr(msg, "channel"):
                new_channel = (msg.channel + channel_offset) % 16
                msg = msg.copy(channel=new_channel)
            output_port.send(msg)

    return f"Played {filepath}"


# ============================================================================
# RESOURCES
# ============================================================================


@mcp.resource("midi://ports")
def get_midi_ports() -> str:
    """List all available MIDI input and output ports."""
    ports = {"inputs": mido.get_input_names(), "outputs": mido.get_output_names()}
    return json.dumps(ports, indent=2)


@mcp.resource("midi://digitakt/status")
def get_digitakt_status() -> str:
    """Get current Digitakt connection status."""
    status = []
    status.append(f"Digitakt Port Name: {DIGITAKT_PORT_NAME}")
    status.append(f"Output Connected: {output_port is not None}")
    status.append(f"Input Connected: {input_port is not None}")

    if output_port:
        status.append(f"Output Port: {output_port.name}")
    if input_port:
        status.append(f"Input Port: {input_port.name}")

    return "\n".join(status)


# ============================================================================
# MAIN
# ============================================================================


def main():
    """Main entry point"""
    _connect()
    mcp.run()


if __name__ == "__main__":
    main()
