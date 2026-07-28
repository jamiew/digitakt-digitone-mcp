"""Elektron Digitone (original, not Digitone II).

Quirks that distinguish it from the Digitakt:
- 4 synth tracks rather than 8 sample tracks
- 4-operator FM synthesis (operators C, A, B1, B2)
- 8 voices shared across the tracks, so tracks are polyphonic
- 2 LFOs per track, and it has a Chorus effect
"""

import asyncio
from typing import Annotated

from elektron_mcp.device import DeviceSpec, parse_parameters
from elektron_mcp.devices.digitone_cc import ChorusCC, Syn1CC, Syn2CC, get_param_name
from elektron_mcp.devices.digitone_params import PARAMETER_MAP, get_parameters_by_category
from elektron_mcp.midi import note_name
from elektron_mcp.server import DeviceServer, build_server

TRACK_COUNT = 4
VOICE_COUNT = 8
FX_CHANNEL = 9

# How the four operators (C, A, B1, B2) are routed in each algorithm.
ALGORITHM_DESCRIPTIONS = {
    1: "[B2→B1→A→C] Full cascade, deepest modulation",
    2: "[B2→B1→C, A→C] Two modulators into carrier",
    3: "[B2→B1, A→C] Branch: A modulates C, B chain separate",
    4: "[B2→B1→C, A] A is carrier, B chain modulates C",
    5: "[B2→C, B1→C, A→C] Three modulators into one carrier",
    6: "[B2→C, B1, A→C] Two modulators into C, B1 carrier",
    7: "[B2→C, B1, A] Three carriers, one modulator",
    8: "[B2, B1, A, C] All carriers, no modulation (organ/additive)",
}


def register_tools(device: DeviceServer) -> None:
    """Add the FM synthesis and polyphony tools unique to the Digitone."""
    connection = device.connection

    @device.tool
    async def play_chord(
        notes: Annotated[list, "MIDI note numbers, e.g. [60, 64, 67] for C major."],
        velocity: Annotated[int, "Velocity for every note."] = 100,
        duration: Annotated[float, "How long to hold the chord, in seconds."] = 0.5,
        channel: Annotated[int, f"MIDI channel (1-16). Tracks 1-{TRACK_COUNT} are channels 1-{TRACK_COUNT}."] = 1,
    ) -> str:
        """Play simultaneous notes. The Digitone shares 8 voices across its 4 tracks."""
        ch = channel - 1
        pitches = [int(n) for n in notes]

        for note in pitches:
            connection.note_on(note, velocity, ch)
            device.log_note_on(note, velocity, ch)

        await asyncio.sleep(duration)

        for note in pitches:
            connection.note_off(note, ch)

        names = ", ".join(note_name(n) for n in pitches)
        return f"Played chord [{names}] vel={velocity} ch={channel} for {duration}s"

    @device.tool
    def set_algorithm(
        algorithm: Annotated[int, "Algorithm number (1-8)."],
        channel: Annotated[int, f"MIDI channel (1-{TRACK_COUNT})."] = 1,
    ) -> str:
        """Choose the FM algorithm, i.e. how the four operators modulate each other.

        Lower numbers are deeper modulation chains; 8 is all carriers (organ-like).
        """
        if not 1 <= algorithm <= 8:
            raise ValueError(f"Algorithm must be 1-8, got {algorithm}")

        ch = channel - 1
        value = algorithm - 1  # The CC is 0-indexed while the display is 1-indexed.
        connection.cc(Syn1CC.ALGORITHM, value, ch)
        connection.log_cc(Syn1CC.ALGORITHM, value, ch, "Algorithm")

        return f"Set algorithm {algorithm} on channel {channel}: {ALGORITHM_DESCRIPTIONS[algorithm]}"

    @device.tool
    def set_ratios(
        ratio_c: Annotated[int | None, "Carrier C ratio (0-127). Integer ratios set pitch."] = None,
        ratio_a: Annotated[int | None, "Operator A ratio (0-127). Non-integer is metallic."] = None,
        ratio_b: Annotated[int | None, "Operator B ratio (0-127). Applies to both B1 and B2."] = None,
        channel: Annotated[int, f"MIDI channel (1-{TRACK_COUNT})."] = 1,
    ) -> str:
        """Set operator frequency ratios.

        1:1 is saw-like, 2:1 square-like, 3:1 a narrow pulse; non-integer ratios give
        bells and metallic timbres.
        """
        ch = channel - 1
        settings = [
            (ratio_c, Syn1CC.RATIO_C, "C"),
            (ratio_a, Syn1CC.RATIO_A, "A"),
            (ratio_b, Syn1CC.RATIO_B_MSB, "B"),
        ]

        applied = []
        for value, cc, label in settings:
            if value is None:
                continue
            connection.cc(cc, value, ch)
            connection.log_cc(cc, value, ch, f"Ratio {label}")
            applied.append(f"{label}={value}")

        if not applied:
            return "No ratios specified"
        return f"Set ratios {', '.join(applied)} on channel {channel}"

    @device.tool
    def set_operator_levels(
        a_level: Annotated[int | None, "Operator A modulation depth (0-127)."] = None,
        b_level: Annotated[int | None, "Operator B modulation depth (0-127). Applies to B1 and B2."] = None,
        channel: Annotated[int, f"MIDI channel (1-{TRACK_COUNT})."] = 1,
    ) -> str:
        """Set modulation index per operator. Higher values are brighter and harsher."""
        ch = channel - 1
        settings = [(a_level, Syn2CC.A_LEVEL, "A"), (b_level, Syn2CC.B_LEVEL, "B")]

        applied = []
        for value, cc, label in settings:
            if value is None:
                continue
            connection.cc(cc, value, ch)
            connection.log_cc(cc, value, ch, f"{label} Level")
            applied.append(f"{label}={value}")

        if not applied:
            return "No levels specified"
        return f"Set operator levels {', '.join(applied)} on channel {channel}"

    @device.tool
    def set_operator_envelope(
        operator: Annotated[str, "'A' or 'B'. B covers both B1 and B2."],
        attack: Annotated[int | None, "Attack time (0-127)."] = None,
        decay: Annotated[int | None, "Decay time (0-127)."] = None,
        end: Annotated[int | None, "End level (0-127). FM-specific: the level held after decay."] = None,
        level: Annotated[int | None, "Peak modulation depth (0-127)."] = None,
        channel: Annotated[int, f"MIDI channel (1-{TRACK_COUNT})."] = 1,
    ) -> str:
        """Shape how an operator's modulation depth changes over time."""
        name = operator.upper()
        if name not in ("A", "B"):
            raise ValueError(f"operator must be 'A' or 'B', got {operator!r}")

        ch = channel - 1
        if name == "A":
            ccs = (Syn2CC.A_ENV_ATTACK, Syn2CC.A_ENV_DECAY, Syn2CC.A_ENV_END, Syn2CC.A_LEVEL)
        else:
            ccs = (Syn2CC.B_ENV_ATTACK, Syn2CC.B_ENV_DECAY, Syn2CC.B_ENV_END, Syn2CC.B_LEVEL)

        applied = []
        for value, cc, label in zip((attack, decay, end, level), ccs, ("attack", "decay", "end", "level"), strict=True):
            if value is None:
                continue
            connection.cc(cc, value, ch)
            connection.log_cc(cc, value, ch, f"Op {name} {label}")
            applied.append(f"{label}={value}")

        if not applied:
            return "No envelope parameters specified"
        return f"Set operator {name} envelope: {', '.join(applied)} on channel {channel}"

    @device.tool
    def set_chorus(
        depth: Annotated[int | None, "Chorus depth (0-127)."] = None,
        speed: Annotated[int | None, "Chorus speed (0-127)."] = None,
        hp: Annotated[int | None, "High-pass filter (0-127)."] = None,
        width: Annotated[int | None, "Stereo width (0-127)."] = None,
        mix: Annotated[int | None, "Mix level (0-127)."] = None,
        channel: Annotated[int, "FX channel."] = FX_CHANNEL,
    ) -> str:
        """Set the chorus effect. The Digitakt has no chorus; this is Digitone-only."""
        ch = channel - 1
        settings = [
            (depth, ChorusCC.DEPTH_MSB, "depth"),
            (speed, ChorusCC.SPEED_MSB, "speed"),
            (hp, ChorusCC.HP, "hp"),
            (width, ChorusCC.WIDTH, "width"),
            (mix, ChorusCC.MIX, "mix"),
        ]

        applied = []
        for value, cc, label in settings:
            if value is None:
                continue
            connection.cc(cc, value, ch)
            connection.log_cc(cc, value, ch, f"Chorus {label}")
            applied.append(f"{label}={value}")

        if not applied:
            return "No chorus parameters specified"
        return f"Set chorus: {', '.join(applied)} on channel {channel}"


SPEC = DeviceSpec(
    slug="digitone",
    display_name="Digitone",
    port_name="Elektron Digitone",
    track_count=TRACK_COUNT,
    trigger_notes=False,
    parameters=parse_parameters(PARAMETER_MAP),
    categories=get_parameters_by_category(),
    nrpn_name_lookup=get_param_name,
    register_tools=register_tools,
    notes=(
        f"Digitone (original): {TRACK_COUNT} FM synth tracks on channels 1-{TRACK_COUNT}, "
        f"{VOICE_COUNT} shared voices, 2 LFOs per track, Chorus on FX channel {FX_CHANNEL}. "
        "All tracks play chromatically."
    ),
)


def main() -> None:
    """Console entry point for `digitone-mcp`."""
    device = build_server(SPEC)
    device.connection.connect()
    device.mcp.run()
