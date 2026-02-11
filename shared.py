"""
Shared MIDI helpers for Elektron device MCP servers.
Used by both server_fastmcp.py (Digitakt) and server_digitone.py (Digitone).
"""

import asyncio
import json
import logging
import time

import mido

# ============================================================================
# MIDI CONNECTION
# ============================================================================


def connect_midi(port_name: str, logger: logging.Logger):
    """Connect to an Elektron device's MIDI ports by name.
    Returns (output_port, input_port) tuple. Either may be None if not found.
    """
    output_port = None
    input_port = None

    try:
        for name in mido.get_output_names():
            if port_name in name:
                output_port = mido.open_output(name)
                logger.info(f"Connected to MIDI output: {name}")
                break

        for name in mido.get_input_names():
            if port_name in name:
                input_port = mido.open_input(name)
                logger.info(f"Connected to MIDI input: {name}")
                break

        if not output_port:
            logger.warning(f"Could not find MIDI output port for {port_name}")
        if not input_port:
            logger.warning(f"Could not find MIDI input port for {port_name}")

    except Exception as e:
        logger.error(f"Error connecting to MIDI: {e}")

    return output_port, input_port


# ============================================================================
# LOGGING HELPERS
# ============================================================================


def note_name(note: int) -> str:
    """Convert MIDI note number to name (e.g., 60 -> C4)"""
    names = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
    octave = (note // 12) - 1
    return f"{names[note % 12]}{octave}"


def log_cc(logger: logging.Logger, cc: int, value: int, channel: int, param_name: str = None):
    if param_name:
        logger.info(f"🎛️  CC {cc:3d} = {value:3d}  ch={channel + 1}  ({param_name})")
    else:
        logger.info(f"🎛️  CC {cc:3d} = {value:3d}  ch={channel + 1}")


def log_nrpn(logger: logging.Logger, msb: int, lsb: int, value: int, channel: int, param_name: str = None):
    if param_name:
        logger.info(f"🎚️  NRPN {msb}:{lsb} = {value:3d}  ch={channel + 1}  ({param_name})")
    else:
        logger.info(f"🎚️  NRPN {msb}:{lsb} = {value:3d}  ch={channel + 1}")


def log_transport(logger: logging.Logger, msg_type: str):
    logger.info(f"🚀 TRANSPORT: {msg_type}")


def log_program_change(logger: logging.Logger, program: int, channel: int):
    logger.info(f"📀 PROGRAM CHANGE: {program}  ch={channel + 1}")


def log_clock(logger: logging.Logger):
    logger.debug("⏱️  CLOCK")


def log_sysex(logger: logging.Logger, data: list):
    hex_display = " ".join([f"{b:02X}" for b in data[:16]])
    if len(data) > 16:
        hex_display += f"... ({len(data)} bytes)"
    logger.info(f"📡 SYSEX: F0 {hex_display} F7")


# ============================================================================
# CLOCK & NOTE HELPERS
# ============================================================================


async def delayed_note_off(output_port, note: int, duration: float, channel: int = 0):
    """Send note off after a delay"""
    await asyncio.sleep(duration)
    if output_port:
        output_port.send(mido.Message("note_off", note=note, velocity=0, channel=channel))


async def send_clock_pulses(
    output_port,
    logger: logging.Logger,
    total_pulses: int,
    clock_interval: float,
    event_schedule: list,
    send_start: bool = True,
    send_stop: bool = True,
):
    """Core clock loop: sends MIDI clock pulses and fires events at the right time.

    event_schedule: list of tuples sorted by pulse index.
      ("note", pulse, note, velocity, duration, channel)
      ("cc", pulse, cc, value, 0, channel)
    """
    if send_start:
        output_port.send(mido.Message("start"))
        log_transport(logger, "START")

    start_time = time.time()
    event_idx = 0

    for i in range(total_pulses):
        output_port.send(mido.Message("clock"))

        while event_idx < len(event_schedule) and event_schedule[event_idx][1] == i:
            evt = event_schedule[event_idx]
            evt_type = evt[0]

            if evt_type == "note":
                _, _pulse, note, velocity, duration, ch = evt
                output_port.send(mido.Message("note_on", note=note, velocity=velocity, channel=ch))
                asyncio.create_task(delayed_note_off(output_port, note, duration, ch))
            elif evt_type == "cc":
                _, _pulse, cc, value, _, ch = evt
                output_port.send(mido.Message("control_change", control=cc, value=value, channel=ch))

            event_idx += 1

        next_pulse_time = start_time + (i + 1) * clock_interval
        sleep_duration = next_pulse_time - time.time()
        if sleep_duration > 0:
            await asyncio.sleep(sleep_duration)

    if send_stop:
        output_port.send(mido.Message("stop"))
        log_transport(logger, "STOP")


# ============================================================================
# PATTERN / PRESET STORAGE
# ============================================================================


def save_json(filepath, data):
    """Save data as JSON to a file."""
    with open(filepath, "w") as f:
        json.dump(data, f, indent=2)


def load_json(filepath):
    """Load JSON data from a file. Returns None if not found."""
    if not filepath.exists():
        return None
    with open(filepath) as f:
        return json.load(f)


def list_json_files(directory):
    """List all JSON files in a directory, sorted."""
    return sorted(directory.glob("*.json"))


# ============================================================================
# MIDI FILE HELPERS
# ============================================================================


def export_notes_to_midi(filepath, bpm, note_events, channel=0, track_name="Notes"):
    """Export a list of note events to a MIDI file.

    note_events: list of (beat, note, velocity, duration_seconds)
    """
    mid = mido.MidiFile()
    ticks_per_beat = mid.ticks_per_beat

    tempo_track = mido.MidiTrack()
    mid.tracks.append(tempo_track)
    tempo_track.append(mido.MetaMessage("set_tempo", tempo=mido.bpm2tempo(bpm)))

    note_track = mido.MidiTrack()
    mid.tracks.append(note_track)
    note_track.append(mido.MetaMessage("track_name", name=track_name))

    sorted_notes = sorted(note_events, key=lambda x: x[0])
    current_tick = 0

    for note_data in sorted_notes:
        beat = note_data[0]
        note = note_data[1]
        velocity = note_data[2] if len(note_data) > 2 else 100
        duration = note_data[3] if len(note_data) > 3 else 0.5

        tick = int(beat * ticks_per_beat)
        delta_time = tick - current_tick

        note_track.append(mido.Message("note_on", channel=channel, note=note, velocity=velocity, time=delta_time))
        duration_ticks = int(duration * ticks_per_beat * bpm / 60)
        note_track.append(mido.Message("note_off", channel=channel, note=note, velocity=0, time=duration_ticks))
        current_tick = tick + duration_ticks

    note_track.append(mido.MetaMessage("end_of_track", time=0))
    mid.save(filepath)
    return len(sorted_notes)
