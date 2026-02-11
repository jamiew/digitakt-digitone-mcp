"""
MCP Server for Digitone (original) MIDI Control - FastMCP Version
Provides tools to send MIDI messages to the Elektron Digitone.

Key differences from Digitakt server:
- 4 synth tracks (not 8 audio tracks)
- 4-operator FM synthesis (not sample playback)
- 2 LFOs per track (not 1)
- Has Chorus effect
- Polyphonic (8 voices shared across 4 tracks)
"""

import asyncio
import json
import logging
import time
from pathlib import Path
from typing import Annotated

import mido
from mcp.server.fastmcp import FastMCP

from nrpn_constants_digitone import (
    Syn1CC,
    Syn2CC,
    get_param_name,
)
from parameter_map_digitone import (
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
logger = logging.getLogger("digitone-midi-server")

# Create FastMCP instance
mcp = FastMCP("digitone-midi")

# MIDI port name
DIGITONE_PORT_NAME = "Elektron Digitone"

# Storage directories
PRESET_DIR = Path.home() / ".mcp-config" / "digitone" / "presets"
PRESET_DIR.mkdir(parents=True, exist_ok=True)

PATTERN_DIR = Path.home() / ".mcp-config" / "digitone" / "patterns"
PATTERN_DIR.mkdir(parents=True, exist_ok=True)

RECORDINGS_DIR = Path.home() / ".mcp-config" / "digitone" / "recordings"
RECORDINGS_DIR.mkdir(parents=True, exist_ok=True)

# Global MIDI port references
output_port: mido.ports.BaseOutput | None = None
input_port: mido.ports.BaseInput | None = None

# Global history
last_melody = None
last_multi_channel_pattern = None


def _connect():
    """Connect to Digitone MIDI ports"""
    global output_port, input_port
    output_port, input_port = connect_midi(DIGITONE_PORT_NAME, logger)


# ============================================================================
# DEVICE-SPECIFIC LOGGING (Digitone: all notes are chromatic)
# ============================================================================


def log_note_on(note: int, velocity: int, channel: int):
    logger.info(f"🎹 NOTE ON  {note_name(note)} ({note}) vel={velocity} ch={channel + 1}")


def log_note_off(note: int, channel: int):
    logger.debug(f"   NOTE OFF {note_name(note)} ({note}) ch={channel + 1}")


def check_connection() -> str | None:
    if not output_port:
        return "Error: Not connected to Digitone MIDI output port"
    return None


async def _delayed_note_off(note: int, duration: float, channel: int = 0):
    await delayed_note_off(output_port, note, duration, channel)


# ============================================================================
# BASIC MIDI TOOLS
# ============================================================================


@mcp.tool()
async def send_note(
    note: Annotated[int, "MIDI note (0-127). Digitone plays chromatically on each track."],
    velocity: Annotated[int, "Velocity (1-127)."] = 100,
    duration: Annotated[float, "Duration in seconds."] = 0.1,
    channel: Annotated[int, "MIDI channel (1-16). Tracks 1-4 = channels 1-4."] = 1,
) -> str:
    """Send a MIDI note to the Digitone."""
    if err := check_connection():
        return err

    ch = channel - 1
    msg_on = mido.Message("note_on", note=note, velocity=velocity, channel=ch)
    output_port.send(msg_on)
    log_note_on(note, velocity, ch)

    await asyncio.sleep(duration)

    msg_off = mido.Message("note_off", note=note, velocity=0, channel=ch)
    output_port.send(msg_off)
    log_note_off(note, ch)

    return f"Sent note {note_name(note)} ({note}) vel={velocity} ch={channel} for {duration}s"


@mcp.tool()
async def play_chord(
    notes: Annotated[list, "List of MIDI note numbers (e.g. [60, 64, 67] for C major)."],
    velocity: Annotated[int, "Velocity for all notes."] = 100,
    duration: Annotated[float, "Duration in seconds."] = 0.5,
    channel: Annotated[int, "MIDI channel (1-16)."] = 1,
) -> str:
    """Play a chord (multiple simultaneous notes). Digitone supports up to 8 voices."""
    if err := check_connection():
        return err

    ch = channel - 1
    for n in notes:
        output_port.send(mido.Message("note_on", note=n, velocity=velocity, channel=ch))
        log_note_on(n, velocity, ch)

    await asyncio.sleep(duration)

    for n in notes:
        output_port.send(mido.Message("note_off", note=n, velocity=0, channel=ch))

    names = [note_name(n) for n in notes]
    return f"Played chord [{', '.join(names)}] vel={velocity} ch={channel} for {duration}s"


@mcp.tool()
def send_cc(
    cc_number: Annotated[int, "CC number (0-127)."],
    value: Annotated[int, "CC value (0-127)"],
    channel: Annotated[int, "MIDI channel (1-16)."] = 1,
) -> str:
    """Send a MIDI Control Change (CC) message."""
    if err := check_connection():
        return err

    ch = channel - 1
    msg = mido.Message("control_change", control=cc_number, value=value, channel=ch)
    output_port.send(msg)
    log_cc(logger, cc_number, value, ch)

    return f"Sent CC {cc_number} = {value} on channel {channel}"


@mcp.tool()
def send_program_change(
    program: Annotated[int, "Program number (0-127)."],
    channel: Annotated[int, "MIDI channel (1-16)."] = 1,
) -> str:
    """Send a MIDI Program Change to switch patterns."""
    if err := check_connection():
        return err

    ch = channel - 1
    msg = mido.Message("program_change", program=program, channel=ch)
    output_port.send(msg)
    log_program_change(logger, program, ch)

    return f"Sent Program Change to {program} on channel {channel}"


@mcp.tool()
def send_nrpn(
    msb: Annotated[int, "NRPN MSB (0-127). 1=track params, 2=FX params, 3=trig params."],
    lsb: Annotated[int, "NRPN LSB (0-127). Parameter number."],
    value: Annotated[int, "Parameter value. 0-127 for 7-bit, 0-16383 for 14-bit."],
    channel: Annotated[int, "MIDI channel (1-16). Channels 1-4 = synth tracks 1-4."] = 1,
) -> str:
    """Send a MIDI NRPN message for detailed parameter control.

    Use 14-bit values for ratio offsets (NRPN-only params with ~2000 steps).
    """
    if err := check_connection():
        return err

    ch = channel - 1

    data_msb = (value >> 7) & 0x7F if value > 127 else value
    data_lsb = value & 0x7F if value > 127 else 0

    output_port.send(mido.Message("control_change", control=99, value=msb, channel=ch))
    output_port.send(mido.Message("control_change", control=98, value=lsb, channel=ch))
    output_port.send(mido.Message("control_change", control=6, value=data_msb, channel=ch))
    output_port.send(mido.Message("control_change", control=38, value=data_lsb, channel=ch))

    param_name = get_param_name(msb, lsb)
    log_nrpn(logger, msb, lsb, value, ch, param_name)

    return f"Sent NRPN {msb}:{lsb} = {value} on channel {channel}" + (
        f" ({param_name})" if param_name and "Unknown" not in param_name else ""
    )


# ============================================================================
# TRANSPORT TOOLS
# ============================================================================


@mcp.tool()
def send_midi_start() -> str:
    """Send MIDI Start to start Digitone sequencer."""
    if err := check_connection():
        return err
    output_port.send(mido.Message("start"))
    log_transport(logger, "START")
    return "Sent MIDI Start"


@mcp.tool()
def send_midi_stop() -> str:
    """Send MIDI Stop to stop Digitone sequencer."""
    if err := check_connection():
        return err
    output_port.send(mido.Message("stop"))
    log_transport(logger, "STOP")
    return "Sent MIDI Stop"


@mcp.tool()
def send_midi_continue() -> str:
    """Send MIDI Continue to resume Digitone sequencer."""
    if err := check_connection():
        return err
    output_port.send(mido.Message("continue"))
    log_transport(logger, "CONTINUE")
    return "Sent MIDI Continue"


@mcp.tool()
def send_song_position(position: Annotated[int, "Song position in sixteenth notes (0-16383)"]) -> str:
    """Send Song Position Pointer."""
    if err := check_connection():
        return err
    output_port.send(mido.Message("songpos", pos=position))
    logger.info(f"🎯 SONG POSITION: {position}")
    return f"Sent Song Position: {position}"


# ============================================================================
# FM SYNTHESIS TOOLS (Digitone-specific)
# ============================================================================

# Algorithm descriptions: how the 4 operators (C, A, B1, B2) are routed
ALGORITHM_DESCRIPTIONS = {
    0: "1: [B2→B1→A→C] Full cascade, deepest modulation",
    1: "2: [B2→B1→C, A→C] Two modulators into carrier",
    2: "3: [B2→B1, A→C] Branch: A modulates C, B chain separate",
    3: "4: [B2→B1→C, A] A is carrier, B chain modulates C",
    4: "5: [B2→C, B1→C, A→C] Three modulators into one carrier",
    5: "6: [B2→C, B1, A→C] Two modulators into C, B1 carrier",
    6: "7: [B2→C, B1, A] Three carriers, one modulator",
    7: "8: [B2, B1, A, C] All carriers, no modulation (organ/additive)",
}


@mcp.tool()
def set_algorithm(
    algorithm: Annotated[int, "Algorithm number (1-8)."],
    channel: Annotated[int, "MIDI channel (1-4). Default is 1."] = 1,
) -> str:
    """Set the FM algorithm (operator routing) on a Digitone track.

    Algorithms determine how operators modulate each other.
    Lower numbers = more modulation chains. 8 = all carriers (organ-like).
    """
    if err := check_connection():
        return err

    if not (1 <= algorithm <= 8):
        return "Error: Algorithm must be 1-8"

    ch = channel - 1
    value = algorithm - 1  # 0-indexed CC value
    output_port.send(mido.Message("control_change", control=Syn1CC.ALGORITHM, value=value, channel=ch))
    log_cc(logger, Syn1CC.ALGORITHM, value, ch, "Algorithm")

    desc = ALGORITHM_DESCRIPTIONS.get(value, "")
    return f"Set algorithm {algorithm} on channel {channel}: {desc}"


@mcp.tool()
def set_ratios(
    ratio_c: Annotated[int, "Carrier C ratio (0-127). Integer ratios set pitch."] = None,
    ratio_a: Annotated[int, "Operator A ratio (0-127). Non-integer = metallic/inharmonic."] = None,
    ratio_b: Annotated[int, "Operator B ratio (0-127). Controls both B1 and B2."] = None,
    channel: Annotated[int, "MIDI channel (1-4)."] = 1,
) -> str:
    """Set FM operator frequency ratios.

    Ratio tips: 1:1=saw-like, 2:1=square-like, 3:1=narrow pulse, non-integer=bells/metallic.
    """
    if err := check_connection():
        return err

    ch = channel - 1
    results = []

    if ratio_c is not None:
        output_port.send(mido.Message("control_change", control=Syn1CC.RATIO_C, value=ratio_c, channel=ch))
        log_cc(logger, Syn1CC.RATIO_C, ratio_c, ch, "Ratio C")
        results.append(f"C={ratio_c}")

    if ratio_a is not None:
        output_port.send(mido.Message("control_change", control=Syn1CC.RATIO_A, value=ratio_a, channel=ch))
        log_cc(logger, Syn1CC.RATIO_A, ratio_a, ch, "Ratio A")
        results.append(f"A={ratio_a}")

    if ratio_b is not None:
        output_port.send(mido.Message("control_change", control=Syn1CC.RATIO_B_MSB, value=ratio_b, channel=ch))
        log_cc(logger, Syn1CC.RATIO_B_MSB, ratio_b, ch, "Ratio B")
        results.append(f"B={ratio_b}")

    if not results:
        return "No ratios specified"

    return f"Set ratios {', '.join(results)} on channel {channel}"


@mcp.tool()
def set_operator_levels(
    a_level: Annotated[int, "Operator A modulation depth (0-127). Higher = more harmonics."] = None,
    b_level: Annotated[int, "Operator B modulation depth (0-127). Controls B1+B2."] = None,
    channel: Annotated[int, "MIDI channel (1-4)."] = 1,
) -> str:
    """Set operator modulation levels (modulation index).

    These control how much each operator modulates its target. Higher = brighter/harsher.
    """
    if err := check_connection():
        return err

    ch = channel - 1
    results = []

    if a_level is not None:
        output_port.send(mido.Message("control_change", control=Syn2CC.A_LEVEL, value=a_level, channel=ch))
        log_cc(logger, Syn2CC.A_LEVEL, a_level, ch, "A Level")
        results.append(f"A={a_level}")

    if b_level is not None:
        output_port.send(mido.Message("control_change", control=Syn2CC.B_LEVEL, value=b_level, channel=ch))
        log_cc(logger, Syn2CC.B_LEVEL, b_level, ch, "B Level")
        results.append(f"B={b_level}")

    if not results:
        return "No levels specified"

    return f"Set operator levels {', '.join(results)} on channel {channel}"


@mcp.tool()
def set_operator_envelope(
    operator: Annotated[str, "'A' or 'B'. A controls one operator, B controls B1+B2."],
    attack: Annotated[int, "Attack time (0-127)."] = None,
    decay: Annotated[int, "Decay time (0-127)."] = None,
    end: Annotated[int, "End level (0-127). Unique to FM - sustain level after decay."] = None,
    level: Annotated[int, "Peak level / modulation depth (0-127)."] = None,
    channel: Annotated[int, "MIDI channel (1-4)."] = 1,
) -> str:
    """Set an operator envelope (A or B). Controls modulation depth over time."""
    if err := check_connection():
        return err

    operator = operator.upper()
    if operator not in ("A", "B"):
        return "Error: operator must be 'A' or 'B'"

    ch = channel - 1
    results = []

    if operator == "A":
        ccs = {
            "attack": Syn2CC.A_ENV_ATTACK,
            "decay": Syn2CC.A_ENV_DECAY,
            "end": Syn2CC.A_ENV_END,
            "level": Syn2CC.A_LEVEL,
        }
    else:
        ccs = {
            "attack": Syn2CC.B_ENV_ATTACK,
            "decay": Syn2CC.B_ENV_DECAY,
            "end": Syn2CC.B_ENV_END,
            "level": Syn2CC.B_LEVEL,
        }

    for param_name, cc in ccs.items():
        val = locals().get(param_name)
        if val is not None:
            output_port.send(mido.Message("control_change", control=cc, value=val, channel=ch))
            log_cc(logger, cc, val, ch, f"Op {operator} {param_name}")
            results.append(f"{param_name}={val}")

    if not results:
        return "No envelope parameters specified"

    return f"Set operator {operator} envelope: {', '.join(results)} on channel {channel}"


@mcp.tool()
def set_chorus(
    depth: Annotated[int, "Chorus depth (0-127)."] = None,
    speed: Annotated[int, "Chorus speed (0-127)."] = None,
    hp: Annotated[int, "High-pass filter (0-127)."] = None,
    width: Annotated[int, "Stereo width (0-127)."] = None,
    mix: Annotated[int, "Mix volume (0-127)."] = None,
    channel: Annotated[int, "FX channel (default 9)."] = 9,
) -> str:
    """Set chorus effect parameters. Sent on the FX channel (default 9)."""
    if err := check_connection():
        return err

    from nrpn_constants_digitone import ChorusCC

    ch = channel - 1
    results = []

    params = [
        (depth, ChorusCC.DEPTH_MSB, "depth"),
        (speed, ChorusCC.SPEED_MSB, "speed"),
        (hp, ChorusCC.HP, "hp"),
        (width, ChorusCC.WIDTH, "width"),
        (mix, ChorusCC.MIX, "mix"),
    ]

    for val, cc, name in params:
        if val is not None:
            output_port.send(mido.Message("control_change", control=cc, value=val, channel=ch))
            log_cc(logger, cc, val, ch, f"Chorus {name}")
            results.append(f"{name}={val}")

    if not results:
        return "No chorus parameters specified"

    return f"Set chorus: {', '.join(results)} on channel {channel}"


# ============================================================================
# PARAMETER TOOLS
# ============================================================================


@mcp.tool()
def list_parameters(
    category: Annotated[str, "Filter by category name. Shows all if not specified."] = None,
) -> str:
    """List available Digitone parameters for automation."""
    categories = get_parameters_by_category()

    if category:
        if category in categories:
            params = categories[category]
            result = f"Parameters in '{category}' ({len(params)}):\n\n"
            for param in params:
                result += f"- {param}\n"
        else:
            result = f"Error: Unknown category '{category}'\n"
            result += f"Available: {', '.join(categories.keys())}"
    else:
        result = "Available parameters by category:\n\n"
        for cat_name, params in categories.items():
            result += f"{cat_name} ({len(params)}):\n"
            for param in params:
                result += f"  - {param}\n"
            result += "\n"
        result += f"Total: {len(get_all_parameters())} parameters\n"

    return result


@mcp.tool()
def set_parameter(
    name: Annotated[str, "Parameter name (e.g., 'fm_algorithm', 'filter_frequency', 'op_a_level')"],
    value: Annotated[int, "Parameter value"],
    channel: Annotated[int, "MIDI channel (1-16). Tracks 1-4 = channels 1-4."] = 1,
) -> str:
    """Set a named Digitone parameter. Use list_parameters to see available names."""
    if err := check_connection():
        return err

    info = get_parameter_info(name)
    if not info:
        return f"Unknown parameter: {name}. Use list_parameters to see available parameters."

    min_val = info.get("min", info.get("range", (0, 127))[0])
    max_val = info.get("max", info.get("range", (0, 127))[1])
    if not (min_val <= value <= max_val):
        return f"Value {value} out of range for {name}. Valid: {min_val}-{max_val}"

    ch = channel - 1
    cc = info.get("cc")

    if cc is not None:
        output_port.send(mido.Message("control_change", control=cc, value=value, channel=ch))
        log_cc(logger, cc, value, ch, name)
        return f"Set {name} = {value} (CC {cc}) on channel {channel}"
    else:
        return f"Parameter {name} does not have a CC mapping"


# ============================================================================
# SEQUENCE & SYSEX TOOLS
# ============================================================================


@mcp.tool()
async def send_note_sequence(
    notes: Annotated[list, "Array of [note, velocity, duration_sec] events."],
    delay: Annotated[float, "Delay between notes in seconds."] = 0.25,
    channel: Annotated[int, "MIDI channel (1-16)."] = 1,
) -> str:
    """Send a sequence of MIDI notes with timing."""
    if err := check_connection():
        return err

    ch = channel - 1

    for i, (note, velocity, duration) in enumerate(notes):
        output_port.send(mido.Message("note_on", note=int(note), velocity=int(velocity), channel=ch))
        log_note_on(int(note), int(velocity), ch)
        await asyncio.sleep(duration)
        output_port.send(mido.Message("note_off", note=int(note), velocity=0, channel=ch))
        if i < len(notes) - 1:
            await asyncio.sleep(delay)

    return f"Sent sequence of {len(notes)} notes on channel {channel}"


@mcp.tool()
def send_sysex(
    data: Annotated[list, "Bytes (0-127) for SysEx message. F0/F7 added automatically."] = None,
    hex_string: Annotated[str, "Hex string like '00 20 3C'. F0/F7 added automatically."] = None,
) -> str:
    """Send a SysEx message to the Digitone."""
    if err := check_connection():
        return err

    sysex_data = None
    if data:
        sysex_data = data
    elif hex_string:
        hex_str = hex_string.replace(" ", "").replace("0x", "")
        sysex_data = [int(hex_str[i : i + 2], 16) for i in range(0, len(hex_str), 2)]

    if not sysex_data:
        return "Error: Must provide either 'data' or 'hex_string'"

    msg = mido.Message("sysex", data=sysex_data)
    output_port.send(msg)
    log_sysex(logger, sysex_data)

    hex_display = " ".join([f"{b:02X}" for b in sysex_data[:16]])
    if len(sysex_data) > 16:
        hex_display += f"... ({len(sysex_data)} bytes total)"

    return f"Sent SysEx: F0 {hex_display} F7"


# ============================================================================
# PLAYBACK TOOLS (with MIDI clock)
# ============================================================================


@mcp.tool()
async def play_with_clock(
    bars: Annotated[int, "Number of bars to play."] = 4,
    bpm: Annotated[float, "Tempo in BPM."] = 120,
    send_start: Annotated[bool, "Send MIDI Start at beginning."] = True,
    send_stop: Annotated[bool, "Send MIDI Stop at end."] = True,
) -> str:
    """Play MIDI clock for a specified number of bars. 24 clocks per quarter note."""
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
async def play_pattern_with_melody(
    notes: Annotated[list, "Array of [beat, note, velocity, duration] tuples."],
    bars: Annotated[int, "Number of bars."] = 4,
    bpm: Annotated[float, "Tempo in BPM."] = 120,
    channel: Annotated[int, "MIDI channel for melody."] = 1,
    send_stop: Annotated[bool, "Send MIDI Stop at end."] = True,
) -> str:
    """Play a melody pattern synced to MIDI clock."""
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
    loop_notes: Annotated[list, "Notes to loop: [[beat_offset, note, velocity], ...]."],
    loop_length: Annotated[float, "Loop length in bars."] = 1,
    bars: Annotated[int, "Total bars to play."] = 4,
    bpm: Annotated[float, "Tempo in BPM."] = 120,
    channel: Annotated[int, "MIDI channel."] = 1,
    send_stop: Annotated[bool, "Send MIDI Stop at end."] = True,
) -> str:
    """Play a looping pattern synced to MIDI clock."""
    if err := check_connection():
        return err

    ch = channel - 1
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

    return f"Played {bars} bars at {bpm} BPM, looping every {loop_length} bar(s) {status}"


@mcp.tool()
async def play_pattern_with_multi_channel_midi(
    midi_channels: Annotated[dict, "Notes per channel: {'1': [[beat, note, vel, dur], ...], ...}"] = None,
    bars: Annotated[int, "Number of bars."] = 4,
    bpm: Annotated[float, "Tempo in BPM."] = 120,
    parameter_automation: Annotated[dict, "Automation: {'param': [[beat, value], ...]}"] = None,
    send_clock: Annotated[bool, "Send MIDI clock."] = True,
    send_stop: Annotated[bool, "Send MIDI Stop at end."] = True,
) -> str:
    """Play a multi-channel pattern with optional parameter automation."""
    global last_multi_channel_pattern
    if err := check_connection():
        return err

    midi_channels = midi_channels or {}
    parameter_automation = parameter_automation or {}

    last_multi_channel_pattern = {"bpm": bpm, "bars": bars, "midi_channels": midi_channels}

    clock_interval = 60.0 / (bpm * 24)
    total_pulses = int(bars * 96)

    event_schedule = []

    for channel_str, notes in midi_channels.items():
        ch = int(channel_str) - 1
        for note_data in notes:
            beat = note_data[0]
            note = note_data[1]
            velocity = note_data[2] if len(note_data) > 2 else 100
            duration = note_data[3] if len(note_data) > 3 else 0.5
            pulse_index = int(beat * 24)
            event_schedule.append(("note", pulse_index, note, velocity, duration, ch))

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
                _, _pulse, note, velocity, duration, ch = evt
                output_port.send(mido.Message("note_on", note=note, velocity=velocity, channel=ch))
                asyncio.create_task(_delayed_note_off(note, duration, ch))
            elif evt_type == "cc":
                _, _pulse, cc, value, _, ch = evt
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

    return f"Played {bars} bars at {bpm} BPM with {len(midi_channels)} channels {status}"


# ============================================================================
# PARAMETER AUTOMATION TOOLS
# ============================================================================


@mcp.tool()
async def send_parameter_sweep(
    parameter: Annotated[str, "Parameter name (e.g., 'fm_feedback', 'filter_frequency')"],
    start_value: Annotated[int, "Starting value (0-127)"],
    end_value: Annotated[int, "Ending value (0-127)"],
    duration: Annotated[float, "Sweep duration in seconds"],
    steps: Annotated[int, "Number of steps."] = 64,
    channel: Annotated[int, "MIDI channel (1-16)."] = 1,
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
    parameter: Annotated[str, "Parameter name"],
    attack_time: Annotated[float, "Attack time in seconds"],
    attack_level: Annotated[int, "Attack peak level (0-127)"],
    decay_time: Annotated[float, "Decay time in seconds"],
    sustain_level: Annotated[int, "Sustain level (0-127)"],
    sustain_time: Annotated[float, "Sustain hold time in seconds"],
    release_time: Annotated[float, "Release time in seconds"],
    start_level: Annotated[int, "Starting level."] = 0,
    end_level: Annotated[int, "Ending level."] = 0,
    channel: Annotated[int, "MIDI channel (1-16)."] = 1,
    steps_per_second: Annotated[int, "Resolution."] = 30,
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

    async def sweep(from_val, to_val, dur):
        if dur <= 0:
            return
        s = max(1, int(dur * steps_per_second))
        step_dur = dur / s
        for i in range(s + 1):
            t = i / s
            val = int(from_val + (to_val - from_val) * t)
            val = max(0, min(127, val))
            output_port.send(mido.Message("control_change", control=cc, value=val, channel=ch))
            await asyncio.sleep(step_dur)

    await sweep(start_level, attack_level, attack_time)
    await sweep(attack_level, sustain_level, decay_time)
    await asyncio.sleep(sustain_time)
    await sweep(sustain_level, end_level, release_time)

    return f"Applied envelope to {parameter}"


@mcp.tool()
async def play_pattern_with_parameter_automation(
    midi_channels: Annotated[dict, "Notes per channel: {'1': [[beat, note, vel, dur], ...]}"],
    parameter_automation: Annotated[dict, "Automation: {'param': [[beat, value], ...]}"],
    bars: Annotated[int, "Number of bars."] = 4,
    bpm: Annotated[float, "Tempo in BPM."] = 120,
    send_stop: Annotated[bool, "Send MIDI Stop at end."] = True,
) -> str:
    """Play a pattern with synchronized parameter automation."""
    if err := check_connection():
        return err

    clock_interval = 60.0 / (bpm * 24)
    total_pulses = int(bars * 96)

    event_schedule = []

    for channel_str, notes in midi_channels.items():
        ch = int(channel_str) - 1
        for note_data in notes:
            beat = note_data[0]
            note = note_data[1]
            velocity = note_data[2] if len(note_data) > 2 else 100
            duration = note_data[3] if len(note_data) > 3 else 0.5
            pulse = int(beat * 24)
            event_schedule.append(("note", pulse, note, velocity, duration, ch))

    for param_name, events in parameter_automation.items():
        param_info = get_parameter_info(param_name)
        if not param_info or param_info.get("cc") is None:
            continue
        cc = param_info["cc"]
        for beat, value in events:
            pulse = int(beat * 24)
            event_schedule.append(("cc", pulse, cc, value, 0, 0))

    event_schedule.sort(key=lambda x: x[1])

    output_port.send(mido.Message("start"))
    log_transport(logger, "START")

    start_time = time.time()
    event_idx = 0

    for i in range(total_pulses):
        output_port.send(mido.Message("clock"))

        while event_idx < len(event_schedule) and event_schedule[event_idx][1] == i:
            evt = event_schedule[event_idx]
            if evt[0] == "note":
                _, _p, note, velocity, duration, ch = evt
                output_port.send(mido.Message("note_on", note=note, velocity=velocity, channel=ch))
                asyncio.create_task(_delayed_note_off(note, duration, ch))
            elif evt[0] == "cc":
                _, _p, cc, value, _, ch = evt
                output_port.send(mido.Message("control_change", control=cc, value=value, channel=ch))
            event_idx += 1

        next_pulse_time = start_time + (i + 1) * clock_interval
        sleep_duration = next_pulse_time - time.time()
        if sleep_duration > 0:
            await asyncio.sleep(sleep_duration)

    if send_stop:
        output_port.send(mido.Message("stop"))
        log_transport(logger, "STOP")

    return f"Played {bars} bars with {len(midi_channels)} channels and {len(parameter_automation)} automated params"


# ============================================================================
# EXPORT TOOLS
# ============================================================================


@mcp.tool()
def export_pattern_to_midi(
    filename: Annotated[str, "Output filename"],
    bpm: Annotated[float, "Tempo in BPM."] = 120,
    bars: Annotated[int, "Number of bars."] = 4,
    melody_notes: Annotated[list, "Melody notes: [[beat, note, velocity, duration], ...]"] = None,
    melody_channel: Annotated[int, "MIDI channel for melody."] = 1,
) -> str:
    """Export a pattern to a standard MIDI file."""
    melody_notes = melody_notes or []

    if not filename.endswith(".mid"):
        filename += ".mid"

    filepath = RECORDINGS_DIR / filename

    mid = mido.MidiFile()
    ticks_per_beat = mid.ticks_per_beat

    tempo_track = mido.MidiTrack()
    mid.tracks.append(tempo_track)
    tempo_track.append(mido.MetaMessage("set_tempo", tempo=mido.bpm2tempo(bpm)))
    tempo_track.append(mido.MetaMessage("time_signature", numerator=4, denominator=4))

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

    return f"Exported to {filepath}: {bars} bars, {len(melody_notes)} notes"


@mcp.tool()
def export_automation_to_midi(
    filename: Annotated[str, "Output filename"],
    automation: Annotated[dict, "Automation data: {'parameter_automation': {...}, 'bpm': N}"],
    channel: Annotated[int, "MIDI channel."] = 1,
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
def save_last_melody(filename: Annotated[str, "Output filename (.mid)"]) -> str:
    """Save the last played melody to a MIDI file."""
    global last_melody
    if not last_melody:
        return "No melody played yet. Use play_pattern_with_melody first."

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
def save_last_pattern(filename: Annotated[str, "Output filename (.mid)"]) -> str:
    """Save the last played multi-channel pattern to a MIDI file."""
    global last_multi_channel_pattern
    if not last_multi_channel_pattern:
        return "No pattern played yet. Use play_pattern_with_multi_channel_midi first."

    if not filename.endswith(".mid"):
        filename += ".mid"

    filepath = RECORDINGS_DIR / filename
    bpm = last_multi_channel_pattern["bpm"]
    midi_channels = last_multi_channel_pattern.get("midi_channels", {})

    mid = mido.MidiFile()
    tempo_track = mido.MidiTrack()
    mid.tracks.append(tempo_track)
    tempo_track.append(mido.MetaMessage("set_tempo", tempo=mido.bpm2tempo(bpm)))

    ticks_per_beat = mid.ticks_per_beat
    total_notes = 0

    for channel_str, notes in midi_channels.items():
        ch = int(channel_str) - 1
        track = mido.MidiTrack()
        mid.tracks.append(track)
        track.append(mido.MetaMessage("track_name", name=f"Channel {channel_str}"))

        sorted_notes = sorted(notes, key=lambda x: x[0])
        current_tick = 0

        for note_data in sorted_notes:
            beat = note_data[0]
            note = note_data[1]
            velocity = note_data[2] if len(note_data) > 2 else 100
            duration = note_data[3] if len(note_data) > 3 else 0.5

            tick = int(beat * ticks_per_beat)
            delta_time = tick - current_tick

            track.append(mido.Message("note_on", channel=ch, note=note, velocity=velocity, time=delta_time))
            duration_ticks = int(duration * ticks_per_beat * bpm / 60)
            track.append(mido.Message("note_off", channel=ch, note=note, velocity=0, time=duration_ticks))
            current_tick = tick + duration_ticks
            total_notes += 1

        track.append(mido.MetaMessage("end_of_track", time=0))

    mid.save(filepath)

    return f"Saved pattern to {filepath} ({total_notes} notes at {bpm} BPM)"


# ============================================================================
# AUTOMATION PRESET TOOLS
# ============================================================================


@mcp.tool()
def save_automation_preset(
    name: Annotated[str, "Preset name"],
    parameter_automation: Annotated[dict, "Automation: {'param': [[beat, value], ...]}"],
    description: Annotated[str, "Description"] = "",
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

    result = f"Available presets ({len(preset_files)}):\n\n"
    for preset_file in sorted(preset_files):
        try:
            with open(preset_file) as f:
                preset_data = json.load(f)
            pname = preset_data.get("name", preset_file.stem)
            desc = preset_data.get("description", "No description")
            result += f"- {pname}: {desc}\n"
        except Exception as e:
            result += f"- {preset_file.stem}: (Error: {e})\n"

    return result


# ============================================================================
# PATTERN SAVE/LOAD TOOLS
# ============================================================================


@mcp.tool()
def save_pattern(
    pattern_name: Annotated[str, "Pattern name"],
    bpm: Annotated[float, "Tempo"],
    bars: Annotated[int, "Number of bars"],
    midi_channels: Annotated[dict, "Notes per channel: {'1': [[beat, note, vel, dur], ...]}"],
    parameter_automation: Annotated[dict, "Parameter automation"] = None,
    description: Annotated[str, "Description"] = "",
) -> str:
    """Save a complete Digitone pattern."""
    if pattern_name.endswith(".json"):
        pattern_name = pattern_name[:-5]

    pattern_file = PATTERN_DIR / f"{pattern_name}.json"
    pattern_data = {
        "name": pattern_name,
        "description": description,
        "bpm": bpm,
        "bars": bars,
        "midi_channels": midi_channels,
        "parameter_automation": parameter_automation or {},
    }

    with open(pattern_file, "w") as f:
        json.dump(pattern_data, f, indent=2)

    return (
        f"Saved pattern '{pattern_name}' to {pattern_file}\n"
        f"  BPM: {bpm}, Bars: {bars}\n"
        f"  MIDI channels: {list(midi_channels.keys())}"
    )


@mcp.tool()
def load_pattern(
    pattern_name: Annotated[str, "Pattern name to load"],
    play: Annotated[bool, "Whether to play after loading"] = False,
) -> str:
    """Load a saved Digitone pattern."""
    if pattern_name.endswith(".json"):
        pattern_name = pattern_name[:-5]

    pattern_file = PATTERN_DIR / f"{pattern_name}.json"
    if not pattern_file.exists():
        return f"Error: Pattern '{pattern_name}' not found"

    with open(pattern_file) as f:
        pattern_data = json.load(f)

    if play:
        return f"Pattern '{pattern_name}' loaded. Use play_pattern_with_multi_channel_midi to play."

    return (
        f"Loaded pattern '{pattern_name}':\n"
        f"  Description: {pattern_data.get('description', 'N/A')}\n"
        f"  BPM: {pattern_data.get('bpm')}, Bars: {pattern_data.get('bars')}\n"
        f"  MIDI channels: {list(pattern_data.get('midi_channels', {}).keys())}\n\n"
        f"Pattern data:\n{json.dumps(pattern_data, indent=2)}"
    )


@mcp.tool()
def update_pattern(
    pattern_name: Annotated[str, "Pattern name"],
    bpm: Annotated[float, "New tempo"] = None,
    bars: Annotated[int, "New bar count"] = None,
    midi_channels: Annotated[dict, "New MIDI channel data"] = None,
    parameter_automation: Annotated[dict, "New automation"] = None,
    description: Annotated[str, "New description"] = None,
) -> str:
    """Update specific fields of an existing pattern."""
    if pattern_name.endswith(".json"):
        pattern_name = pattern_name[:-5]

    pattern_file = PATTERN_DIR / f"{pattern_name}.json"
    if not pattern_file.exists():
        return f"Error: Pattern '{pattern_name}' not found"

    with open(pattern_file) as f:
        pattern_data = json.load(f)

    updated = []
    if bpm is not None:
        pattern_data["bpm"] = bpm
        updated.append("bpm")
    if bars is not None:
        pattern_data["bars"] = bars
        updated.append("bars")
    if midi_channels is not None:
        pattern_data["midi_channels"] = midi_channels
        updated.append("midi_channels")
    if parameter_automation is not None:
        pattern_data["parameter_automation"] = parameter_automation
        updated.append("parameter_automation")
    if description is not None:
        pattern_data["description"] = description
        updated.append("description")

    with open(pattern_file, "w") as f:
        json.dump(pattern_data, f, indent=2)

    return f"Updated pattern '{pattern_name}': modified {', '.join(updated)}"


@mcp.tool()
def list_patterns() -> str:
    """List all saved Digitone patterns."""
    pattern_files = list(PATTERN_DIR.glob("*.json"))
    if not pattern_files:
        return f"No patterns found in {PATTERN_DIR}"

    result = f"Available patterns ({len(pattern_files)}):\n\n"
    for pf in sorted(pattern_files):
        try:
            with open(pf) as f:
                pd = json.load(f)
            result += f"- {pd.get('name', pf.stem)}: {pd.get('description', 'N/A')}\n"
            result += f"    BPM: {pd.get('bpm')}, Bars: {pd.get('bars')}, Channels: {list(pd.get('midi_channels', {}).keys())}\n"
        except Exception as e:
            result += f"- {pf.stem}: (Error: {e})\n"

    return result


@mcp.tool()
def delete_pattern(pattern_name: Annotated[str, "Pattern name to delete"]) -> str:
    """Delete a saved pattern."""
    if pattern_name.endswith(".json"):
        pattern_name = pattern_name[:-5]

    pattern_file = PATTERN_DIR / f"{pattern_name}.json"
    if not pattern_file.exists():
        return f"Error: Pattern '{pattern_name}' not found"

    pattern_file.unlink()
    return f"Deleted pattern '{pattern_name}'"


# ============================================================================
# RECORDING TOOLS
# ============================================================================


@mcp.tool()
async def monitor_midi_input(duration: Annotated[float, "Duration to monitor in seconds."] = 10) -> str:
    """Monitor incoming MIDI messages."""
    if not input_port:
        return "Error: Not connected to Digitone MIDI input port"

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
    filename: Annotated[str, "Output filename"],
    duration_sec: Annotated[float, "Recording duration in seconds."] = 30,
    bpm: Annotated[float, "Tempo for the recording."] = 120,
) -> str:
    """Record incoming MIDI to a .mid file."""
    if not input_port:
        return "Error: Not connected to Digitone MIDI input port"

    if not filename.endswith(".mid"):
        filename += ".mid"

    filepath = RECORDINGS_DIR / filename
    logger.info(f"⏺️  RECORDING to {filepath} for {duration_sec}s...")

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
        await asyncio.sleep(0.01)

    current_tick = 0
    for elapsed, msg in messages:
        tick = int(elapsed * ticks_per_second)
        delta = tick - current_tick
        if msg.type in ("note_on", "note_off", "control_change"):
            recording_track.append(msg.copy(time=delta))
            current_tick = tick

    recording_track.append(mido.MetaMessage("end_of_track", time=0))
    mid.save(filepath)

    return f"Recorded {len(messages)} messages to {filepath}"


@mcp.tool()
def list_midi_recordings() -> str:
    """List all MIDI recordings."""
    midi_files = list(RECORDINGS_DIR.glob("*.mid"))
    if not midi_files:
        return f"No recordings found in {RECORDINGS_DIR}"

    result = f"Recordings ({len(midi_files)}):\n\n"
    for mf in sorted(midi_files):
        try:
            mid = mido.MidiFile(mf)
            result += f"- {mf.name}: {mid.length:.1f}s, {len(mid.tracks)} tracks\n"
        except Exception as e:
            result += f"- {mf.name}: (Error: {e})\n"

    return result


@mcp.tool()
async def play_midi_file(
    filename: Annotated[str, "MIDI file to play"],
    channel_offset: Annotated[int, "Offset to add to channels."] = 0,
) -> str:
    """Play a MIDI file through the Digitone."""
    if err := check_connection():
        return err

    if not filename.endswith(".mid"):
        filename += ".mid"

    filepath = RECORDINGS_DIR / filename
    if not filepath.exists():
        return f"Error: File not found: {filepath}"

    mid = mido.MidiFile(filepath)
    logger.info(f"▶️  PLAYING: {filepath}")

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
    """List all available MIDI ports."""
    ports = {"inputs": mido.get_input_names(), "outputs": mido.get_output_names()}
    return json.dumps(ports, indent=2)


@mcp.resource("midi://digitone/status")
def get_digitone_status() -> str:
    """Get Digitone connection status."""
    status = []
    status.append(f"Digitone Port Name: {DIGITONE_PORT_NAME}")
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
