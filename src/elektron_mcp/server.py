"""The shared MCP server.

`build_server(spec)` produces a complete MCPServer for any Elektron device.
Tools are closures over a `DeviceServer`, which is what lets one implementation
serve every machine — the old per-device module globals could not be shared.
"""

import asyncio
import inspect
import json
import logging
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from importlib.metadata import version
from typing import Annotated, Any, Literal, TypeVar

import mido
from mcp.server.mcpserver import Context, MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import Tool as MCPTool
from mcp.types import ToolAnnotations
from pydantic import Field, WithJsonSchema

from elektron_mcp import clock, midifile
from elektron_mcp.clock import Event, cc_event, note_event
from elektron_mcp.device import DeviceSpec, Parameter
from elektron_mcp.elektroid import Elektroid
from elektron_mcp.midi import MidiConnection, available_ports, note_name
from elektron_mcp.storage import Storage, read_json, write_json

# Event rows from the model, e.g. [beat, note, velocity, duration]. Advertised as
# plain numbers, but validated as `int | float` so whole numbers stay ints: notes and
# tracks must be ints by the time they reach mido.
Row = list[Annotated[int | float, WithJsonSchema({"type": "number"})]]

ToolFn = TypeVar("ToolFn", bound=Callable[..., Any])

# Every tool declares one of these so clients can tell what it touches.
# "Open world" means it reaches the hardware; local file tools are closed-world.
PLAYS = ToolAnnotations(read_only_hint=False, destructive_hint=False, idempotent_hint=False, open_world_hint=True)
"""Sends notes, clock or transport. Additive: nothing on the device is overwritten."""
SETS = ToolAnnotations(read_only_hint=False, destructive_hint=True, idempotent_hint=True, open_world_hint=True)
"""Overwrites a sound or sequencer value on the device. Unsaved tweaks are lost."""
LISTENS = ToolAnnotations(read_only_hint=True, open_world_hint=True)
"""Reads from the device: incoming MIDI, or what's in its storage."""
READS = ToolAnnotations(read_only_hint=True, open_world_hint=False)
"""Reads local data only."""
WRITES = ToolAnnotations(read_only_hint=False, destructive_hint=True, idempotent_hint=True, open_world_hint=False)
"""Creates or overwrites a local file."""

Channel = Annotated[int, Field(ge=1, le=16, description="MIDI channel.")]
Velocity = Annotated[int, Field(ge=1, le=127, description="Note velocity.")]
MidiValue = Annotated[int, Field(ge=0, le=127)]
Note = Annotated[int, Field(ge=0, le=127, description="MIDI note number. 60 = C4.")]
Bars = Annotated[int, Field(ge=1, le=256, description="Number of bars to play.")]
Bpm = Annotated[float, Field(ge=20, le=300, description="Tempo in BPM.")]
SendStop = Annotated[bool, Field(description="Send MIDI Stop at the end.")]
Triggers = list[Row]
_CHANNEL_NOTES = "Notes per MIDI channel: {'9': [[beat, note, velocity, duration_sec], ...]}."
_AUTOMATION = "Automation: {'param_name': [[beat, value], ...]}."
# Optional variants carry the description themselves: on `X | None` it would only
# land inside one anyOf branch, where clients don't show it.
ChannelNotes = Annotated[dict[str, list[Row]], Field(description=_CHANNEL_NOTES)]
OptionalChannelNotes = Annotated[dict[str, list[Row]] | None, Field(description=_CHANNEL_NOTES)]
Automation = Annotated[dict[str, list[Row]], Field(description=_AUTOMATION)]
OptionalAutomation = Annotated[dict[str, list[Row]] | None, Field(description=_AUTOMATION)]
AutomationLoop = Annotated[int, Field(ge=0, description="Bars for the automation to loop over. 0 = no loop.")]


def _instructions(spec: DeviceSpec) -> str:
    return (
        f"Controls an Elektron {spec.display_name} over USB MIDI. {spec.notes}\n"
        "Channels are 1-16 as shown on the device. Beats are quarter notes counted from 0 (4 per bar). "
        f"list_parameters gives parameter names; the midi://{spec.slug}/parameters resource has CC/NRPN "
        "numbers and ranges. 'Not connected' errors mean the device wasn't on USB when the server started."
    )


def _strip_titles(schema: Any) -> Any:
    """Drop pydantic's auto-generated "title" keys ("Bpm", "send_noteArguments", ...).

    They restate the property name, and across ~45 tools they cost about 1k tokens.
    Keys inside "properties" are parameter names, not keywords, so they're kept.
    """
    if isinstance(schema, list):
        return [_strip_titles(item) for item in schema]
    if not isinstance(schema, dict):
        return schema
    return {
        key: {name: _strip_titles(sub) for name, sub in value.items()} if key == "properties" else _strip_titles(value)
        for key, value in schema.items()
        if key != "title"
    }


class ElektronMCPServer(MCPServer):
    async def list_tools(self) -> list[MCPTool]:
        return [
            tool.model_copy(update={"input_schema": _strip_titles(tool.input_schema)})
            for tool in await super().list_tools()
        ]


@dataclass
class PlaybackHistory:
    """Last-played material, so it can be exported after the fact."""

    melody: dict[str, Any] | None = None
    tracks: dict[str, Any] | None = None
    loop: dict[str, Any] | None = None
    multi_channel: dict[str, Any] | None = None


@dataclass
class DeviceServer:
    """Bundles everything a tool needs: the device, its ports, its storage."""

    spec: DeviceSpec
    connection: MidiConnection
    storage: Storage
    mcp: ElektronMCPServer
    logger: logging.Logger
    elektroid: Elektroid
    """Storage access (+Drive, sample slots, sounds). Tools read it at call time, so tests can swap it."""
    history: PlaybackHistory = field(default_factory=PlaybackHistory)

    # -------------------------------------------------------------- helpers

    def log_note_on(self, note: int, velocity: int, channel: int) -> None:
        if self.spec.trigger_notes and note < self.spec.track_count:
            self.logger.info(f"🥁 NOTE ON  Track {note + 1} vel={velocity} ch={channel + 1}")
        else:
            self.logger.info(f"🎹 NOTE ON  {note_name(note)} ({note}) vel={velocity} ch={channel + 1}")

    def log_note_off(self, note: int, channel: int) -> None:
        if self.spec.trigger_notes and note < self.spec.track_count:
            self.logger.debug(f"   NOTE OFF Track {note + 1} ch={channel + 1}")
        else:
            self.logger.debug(f"   NOTE OFF {note_name(note)} ({note}) ch={channel + 1}")

    def resolve(self, name: str) -> Parameter:
        """Look up a parameter or raise with a useful message."""
        parameter = self.spec.parameter(name)
        if parameter is None:
            raise ToolError(f"Unknown parameter {name!r}. Use list_parameters to see what's available.")
        return parameter

    def apply(self, parameter: Parameter, value: int, channel: int) -> str:
        """Send a parameter by whichever transport it uses. Returns a description."""
        if not parameter.in_range(value):
            raise ToolError(
                f"Value {value} out of range for {parameter.name}: valid range is "
                f"{parameter.minimum}-{parameter.maximum}"
            )

        if parameter.kind == "cc":
            assert parameter.cc is not None
            self.connection.cc(parameter.cc, value, channel)
            self.connection.log_cc(parameter.cc, value, channel, parameter.name)
            return f"CC {parameter.cc}"

        assert parameter.msb is not None and parameter.lsb is not None
        self.connection.nrpn(parameter.msb, parameter.lsb, value, channel)
        self.connection.log_nrpn(parameter.msb, parameter.lsb, value, channel, parameter.name)
        return f"NRPN {parameter.msb}:{parameter.lsb}"

    def tool(self, annotations: ToolAnnotations) -> Callable[[ToolFn], ToolFn]:
        """Register a function as an MCP tool with the given hints. Returns it unchanged.

        Tools return plain text, so the generated `{"result": str}` output schema would
        only repeat every result as structured content; it's turned off.
        """

        def register(fn: ToolFn) -> ToolFn:
            description = inspect.cleandoc(fn.__doc__ or "")
            self.mcp.tool(description=description, annotations=annotations, structured_output=False)(fn)
            return fn

        return register


def bar_progress(ctx: Context) -> clock.Progress:
    """Report each finished bar as MCP progress, so clients can show a long pattern advancing."""

    async def report(bar: int, total: int) -> None:
        await ctx.report_progress(bar, total, f"Bar {bar}/{total}")

    return report


def build_server(spec: DeviceSpec, *, storage_root=None) -> DeviceServer:
    """Assemble an MCPServer for one device."""
    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger(f"{spec.slug}-midi-server")

    device = DeviceServer(
        spec=spec,
        connection=MidiConnection(port_name=spec.port_name, display_name=spec.display_name, logger=logger),
        storage=Storage.for_device(spec.slug, root=storage_root),
        mcp=ElektronMCPServer(
            f"{spec.slug}-midi",
            title=f"Elektron {spec.display_name}",
            version=version("digitakt-digitone-mcp"),
            instructions=_instructions(spec),
        ),
        logger=logger,
        elektroid=Elektroid(spec.port_name),
    )

    _register_core(device)
    _register_transport(device)
    _register_parameters(device)
    _register_playback(device)
    _register_automation(device)
    _register_patterns(device)
    _register_presets(device)
    _register_export(device)
    _register_recording(device)
    _register_resources(device)

    if spec.register_tools is not None:
        spec.register_tools(device)

    return device


# ============================================================================
# CORE MIDI
# ============================================================================


def _register_core(device: DeviceServer) -> None:
    spec = device.spec
    connection = device.connection

    note_hint = (
        f"Track triggers: 0-{spec.track_count - 1} (Track 1-{spec.track_count}). Chromatic: 12-84."
        if spec.trigger_notes
        else f"{spec.display_name} plays chromatically on each track."
    )

    @device.tool(PLAYS)
    async def send_note(
        note: Annotated[Note, Field(description=f"MIDI note number. {note_hint}")],
        velocity: Velocity = 100,
        duration: Annotated[float, Field(ge=0, le=30, description="Seconds to hold the note.")] = 0.1,
        channel: Channel = 1,
    ) -> str:
        """Send a MIDI note on/off."""
        ch = channel - 1
        connection.note_on(note, velocity, ch)
        device.log_note_on(note, velocity, ch)

        await asyncio.sleep(duration)

        connection.note_off(note, ch)
        device.log_note_off(note, ch)
        return f"Sent note {note_name(note)} ({note}) vel={velocity} ch={channel} for {duration}s"

    @device.tool(SETS)
    def send_cc(
        cc_number: Annotated[
            MidiValue, Field(description="CC number. 74=Filter Freq, 75=Filter Res, 7=Volume, 10=Pan.")
        ],
        value: Annotated[MidiValue, Field(description="CC value.")],
        channel: Channel = 1,
    ) -> str:
        """Send a raw MIDI Control Change message."""
        ch = channel - 1
        connection.cc(cc_number, value, ch)
        connection.log_cc(cc_number, value, ch)
        return f"Sent CC {cc_number} = {value} on channel {channel}"

    @device.tool(PLAYS)
    def send_program_change(
        program: Annotated[MidiValue, Field(description="Program number. Patterns are numbered across banks.")],
        channel: Channel = 1,
    ) -> str:
        """Switch patterns with a MIDI Program Change."""
        ch = channel - 1
        connection.send(mido.Message("program_change", program=program, channel=ch))
        connection.log_program_change(program, ch)
        return f"Sent Program Change to {program} on channel {channel}"

    @device.tool(SETS)
    def send_nrpn(
        msb: Annotated[MidiValue, Field(description="NRPN MSB. Usually 1 for track parameters.")],
        lsb: Annotated[MidiValue, Field(description="NRPN LSB. Parameter number within the page.")],
        value: Annotated[MidiValue, Field(description="Parameter value.")],
        channel: Annotated[
            Channel, Field(description=f"MIDI channel. Channels 1-{spec.track_count} address tracks.")
        ] = 1,
    ) -> str:
        """Send a raw NRPN message, for parameters with no CC mapping."""
        ch = channel - 1
        connection.nrpn(msb, lsb, value, ch)
        name = spec.nrpn_name_lookup(msb, lsb)
        connection.log_nrpn(msb, lsb, value, ch, name)
        return f"Sent NRPN {msb}:{lsb} = {value} on channel {channel}" + (f" ({name})" if name else "")

    @device.tool(PLAYS)
    async def send_note_sequence(
        notes: Annotated[list[Row], Field(description="Note events, each [note, velocity, duration_sec].")],
        delay: Annotated[float, Field(ge=0, description="Gap between notes, in seconds.")] = 0.25,
        channel: Channel = 1,
    ) -> str:
        """Play a sequence of notes back to back, without MIDI clock."""
        ch = channel - 1
        for index, row in enumerate(notes):
            note, velocity, duration = int(row[0]), int(row[1]), float(row[2])
            connection.note_on(note, velocity, ch)
            device.log_note_on(note, velocity, ch)
            await asyncio.sleep(duration)
            connection.note_off(note, ch)
            if index < len(notes) - 1:
                await asyncio.sleep(delay)
        return f"Sent sequence of {len(notes)} notes on channel {channel}"

    @device.tool(SETS)
    def send_sysex(
        data: Annotated[
            list[MidiValue] | None, Field(description="Byte values. F0/F7 framing is added for you.")
        ] = None,
        hex_string: Annotated[str | None, Field(description="Alternative to data: hex like '00 20 3C 0E 00'.")] = None,
    ) -> str:
        """Send a SysEx message."""
        if data:
            payload = [int(b) for b in data]
        elif hex_string:
            cleaned = hex_string.replace(" ", "").replace("0x", "")
            payload = [int(cleaned[i : i + 2], 16) for i in range(0, len(cleaned), 2)]
        else:
            raise ToolError("Must provide either 'data' or 'hex_string'")

        connection.send(mido.Message("sysex", data=payload))
        connection.log_sysex(payload)

        display = " ".join(f"{b:02X}" for b in payload[:16])
        if len(payload) > 16:
            display += f"... ({len(payload)} bytes total)"
        return f"Sent SysEx message: F0 {display} F7"


# ============================================================================
# TRANSPORT
# ============================================================================


def _register_transport(device: DeviceServer) -> None:
    connection = device.connection

    @device.tool(PLAYS)
    def send_midi_start() -> str:
        """Start the sequencer from the beginning."""
        connection.send(mido.Message("start"))
        connection.log_transport("START")
        return "Sent MIDI Start"

    @device.tool(PLAYS)
    def send_midi_stop() -> str:
        """Stop the sequencer."""
        connection.send(mido.Message("stop"))
        connection.log_transport("STOP")
        return "Sent MIDI Stop"

    @device.tool(PLAYS)
    def send_midi_continue() -> str:
        """Resume the sequencer from its current position."""
        connection.send(mido.Message("continue"))
        connection.log_transport("CONTINUE")
        return "Sent MIDI Continue"

    @device.tool(PLAYS)
    def send_song_position(
        position: Annotated[int, Field(ge=0, le=16383, description="Position in sixteenth notes.")],
    ) -> str:
        """Set playback position with a Song Position Pointer."""
        connection.send(mido.Message("songpos", pos=position))
        device.logger.info(f"🎯 SONG POSITION: {position}")
        return f"Sent Song Position: {position}"


# ============================================================================
# PARAMETERS
# ============================================================================


def _register_parameters(device: DeviceServer) -> None:
    spec = device.spec

    @device.tool(READS)
    def list_parameters(
        category: Annotated[
            str | None, Field(description="Filter to one category. Omit to list every category.")
        ] = None,
    ) -> str:
        """List named parameters available to set_parameter, grouped by category."""
        categories = spec.categories

        if category:
            if category not in categories:
                raise ToolError(f"Unknown category {category!r}. Available: {', '.join(categories)}")
            names = categories[category]
            lines = [f"Parameters in '{category}' ({len(names)}):", ""]
            lines += [f"- {n}" for n in names]
            return "\n".join(lines)

        lines = ["Available parameters by category:", ""]
        for cat_name, names in categories.items():
            lines.append(f"{cat_name} ({len(names)}):")
            lines += [f"  - {n}" for n in names]
            lines.append("")
        lines.append(f"Total: {len(spec.parameters)} parameters")
        lines.append("Pass 'category' to filter.")
        return "\n".join(lines)

    @device.tool(SETS)
    def set_parameter(
        name: Annotated[str, Field(description="Parameter name, e.g. 'filter_cutoff', 'lfo_speed', 'delay_time'.")],
        value: Annotated[int, Field(description="Value. Valid range depends on the parameter.")],
        channel: Annotated[
            Channel, Field(description=f"MIDI channel. Channels 1-{spec.track_count} address tracks.")
        ] = 1,
    ) -> str:
        """Set a named parameter. Handles both CC and NRPN parameters.

        Use list_parameters to discover names.
        """
        parameter = device.resolve(name)
        transport = device.apply(parameter, value, channel - 1)
        return f"Set {name} = {value} ({transport}) on channel {channel}"


# ============================================================================
# PLAYBACK
# ============================================================================


def _register_playback(device: DeviceServer) -> None:
    connection = device.connection

    @device.tool(PLAYS)
    async def play_with_clock(
        ctx: Context,
        bars: Bars = 4,
        bpm: Bpm = 120,
        send_start: Annotated[bool, Field(description="Send MIDI Start at the beginning.")] = True,
        send_stop: SendStop = True,
    ) -> str:
        """Run MIDI clock for a number of bars to drive the sequencer."""
        device.logger.info(f"▶️  PLAY CLOCK: {bars} bars @ {bpm} BPM")
        await clock.play(
            connection, [], bars=bars, bpm=bpm, send_start=send_start, send_stop=send_stop, progress=bar_progress(ctx)
        )
        return f"Played {bars} bars at {bpm} BPM {'and stopped' if send_stop else '(still running)'}"

    @device.tool(PLAYS)
    async def play_pattern_with_melody(
        ctx: Context,
        notes: Annotated[list[Row], Field(description="Notes as [beat, note, velocity, duration_sec].")],
        bars: Bars = 4,
        bpm: Bpm = 120,
        channel: Channel = 1,
        send_stop: SendStop = True,
    ) -> str:
        """Play a melody locked to MIDI clock. Beat positions are quarter notes."""
        ch = channel - 1
        device.history.melody = {"bpm": bpm, "notes": notes, "channel": channel}

        events = [
            note_event(
                beat=row[0],
                note=int(row[1]),
                velocity=int(row[2]) if len(row) > 2 else 100,
                duration=float(row[3]) if len(row) > 3 else 0.1,
                channel=ch,
            )
            for row in notes
        ]

        device.logger.info(f"▶️  PLAY MELODY: {bars} bars @ {bpm} BPM, {len(notes)} notes on ch={channel}")
        await clock.play(connection, events, bars=bars, bpm=bpm, send_stop=send_stop, progress=bar_progress(ctx))
        return f"Played {bars} bars at {bpm} BPM with {len(notes)} melody notes"

    @device.tool(PLAYS)
    async def play_pattern_with_loop(
        ctx: Context,
        loop_notes: Annotated[list[Row], Field(description="Notes as [beat_offset, note, velocity] within the loop.")],
        loop_length: Annotated[float, Field(gt=0, description="Loop length in bars.")] = 1,
        bars: Annotated[Bars, Field(description="Total bars to play.")] = 4,
        bpm: Bpm = 120,
        channel: Channel = 1,
        send_stop: SendStop = True,
    ) -> str:
        """Play a short pattern that repeats for the full duration."""
        ch = channel - 1
        device.history.loop = {"bpm": bpm, "loop_notes": loop_notes, "loop_length": loop_length, "channel": channel}
        loop_pulses = int(loop_length * clock.PULSES_PER_BAR)

        events = [
            note_event(
                beat=row[0],
                note=int(row[1]),
                velocity=int(row[2]) if len(row) > 2 else 100,
                channel=ch,
                loop_pulses=loop_pulses,
            )
            for row in loop_notes
        ]

        await clock.play(connection, events, bars=bars, bpm=bpm, send_stop=send_stop, progress=bar_progress(ctx))
        return (
            f"Played {bars} bars at {bpm} BPM with {len(loop_notes)} notes "
            f"looping every {loop_length} bar(s) ({bars / loop_length:.1f} loops)"
        )

    @device.tool(PLAYS)
    async def play_pattern_with_multi_channel_midi(
        ctx: Context,
        track_triggers: Annotated[
            Triggers | None, Field(description="Track triggers as [beat, track, velocity].")
        ] = None,
        midi_channels: OptionalChannelNotes = None,
        bars: Bars = 4,
        bpm: Bpm = 120,
        parameter_automation: OptionalAutomation = None,
        automation_loop_bars: AutomationLoop = 0,
        send_clock: Annotated[bool, Field(description="Send MIDI clock.")] = True,
        send_stop: SendStop = True,
    ) -> str:
        """Play a full arrangement: track triggers, per-channel notes, and parameter automation."""
        track_triggers = track_triggers or []
        midi_channels = midi_channels or {}
        parameter_automation = parameter_automation or {}

        device.history.multi_channel = {
            "bpm": bpm,
            "bars": bars,
            "track_triggers": track_triggers,
            "midi_channels": midi_channels,
        }

        events: list[Event] = []

        for row in track_triggers:
            track = int(row[1])
            events.append(
                note_event(
                    beat=row[0],
                    note=int(row[3]) if len(row) > 3 else track - 1,
                    velocity=int(row[2]) if len(row) > 2 else 100,
                    channel=track - 1,
                )
            )

        for channel_str, rows in midi_channels.items():
            ch = int(channel_str) - 1
            for row in rows:
                events.append(
                    note_event(
                        beat=row[0],
                        note=int(row[1]),
                        velocity=int(row[2]) if len(row) > 2 else 100,
                        duration=float(row[3]) if len(row) > 3 else 0.5,
                        channel=ch,
                    )
                )

        events += _automation_events(device, parameter_automation, automation_loop_bars)

        device.logger.info(f"▶️  PLAY MULTI-CHANNEL: {bars} bars @ {bpm} BPM")
        await clock.play(
            connection,
            events,
            bars=bars,
            bpm=bpm,
            send_start=send_clock,
            send_clock=send_clock,
            send_stop=send_stop,
            progress=bar_progress(ctx),
        )
        return (
            f"Played {bars} bars at {bpm} BPM with {len(track_triggers)} triggers + {len(midi_channels)} MIDI channels"
        )

    @device.tool(PLAYS)
    async def play_pattern_with_parameter_automation(
        ctx: Context,
        triggers: Annotated[Triggers, Field(description="Track triggers as [beat, track, velocity].")],
        parameter_automation: Automation,
        bars: Bars = 4,
        bpm: Bpm = 120,
        automation_loop_bars: AutomationLoop = 0,
        send_stop: SendStop = True,
    ) -> str:
        """Play triggers with parameter automation running alongside."""
        events: list[Event] = [
            note_event(
                beat=row[0],
                note=int(row[1]) - 1,
                velocity=int(row[2]) if len(row) > 2 else 100,
                channel=0,
            )
            for row in triggers
        ]
        events += _automation_events(device, parameter_automation, automation_loop_bars)

        device.logger.info(f"▶️  PLAY WITH AUTOMATION: {bars} bars @ {bpm} BPM")
        await clock.play(connection, events, bars=bars, bpm=bpm, send_stop=send_stop, progress=bar_progress(ctx))
        return f"Played {bars} bars with {len(triggers)} triggers and {len(parameter_automation)} automated parameters"


def _automation_events(device: DeviceServer, automation: dict, loop_bars: int) -> list[Event]:
    """Turn {param: [[beat, value], ...]} into CC events, skipping unknown/NRPN params."""
    loop_pulses = int(loop_bars * clock.PULSES_PER_BAR) if loop_bars > 0 else None
    events: list[Event] = []

    for name, rows in automation.items():
        parameter = device.spec.parameter(name)
        if parameter is None or parameter.cc is None:
            device.logger.warning(f"Skipping automation for {name!r}: unknown or has no CC mapping")
            continue
        for beat, value in rows:
            events.append(
                cc_event(beat=beat, control=parameter.cc, value=parameter.clamp(int(value)), loop_pulses=loop_pulses)
            )

    return events


# ============================================================================
# AUTOMATION
# ============================================================================


def _register_automation(device: DeviceServer) -> None:
    connection = device.connection

    @device.tool(SETS)
    async def send_parameter_sweep(
        parameter: Annotated[str, Field(description="Parameter name, e.g. 'filter_cutoff'.")],
        start_value: Annotated[int, Field(description="Starting value.")],
        end_value: Annotated[int, Field(description="Ending value.")],
        duration: Annotated[float, Field(gt=0, le=120, description="Sweep duration in seconds.")],
        steps: Annotated[int, Field(ge=1, le=1024, description="Number of intermediate steps.")] = 64,
        channel: Channel = 1,
    ) -> str:
        """Ramp a parameter from one value to another over time."""
        spec_param = device.resolve(parameter)
        if spec_param.cc is None:
            raise ToolError(f"{parameter} is an NRPN parameter; sweeps require a CC mapping")

        ch = channel - 1
        step_duration = duration / steps
        increment = (end_value - start_value) / steps

        device.logger.info(f"🎚️  SWEEP {parameter}: {start_value} → {end_value} over {duration}s")

        for index in range(steps + 1):
            connection.cc(spec_param.cc, spec_param.clamp(int(start_value + increment * index)), ch)
            await asyncio.sleep(step_duration)

        return f"Swept {parameter} from {start_value} to {end_value} over {duration}s"

    @device.tool(SETS)
    async def send_parameter_envelope(
        parameter: Annotated[str, Field(description="Parameter name, e.g. 'filter_cutoff'.")],
        attack_time: Annotated[float, Field(ge=0, description="Attack time in seconds.")],
        attack_level: Annotated[int, Field(description="Peak level reached at the end of attack.")],
        decay_time: Annotated[float, Field(ge=0, description="Decay time in seconds.")],
        sustain_level: Annotated[int, Field(description="Level held during sustain.")],
        sustain_time: Annotated[float, Field(ge=0, description="Sustain duration in seconds.")],
        release_time: Annotated[float, Field(ge=0, description="Release time in seconds.")],
        start_level: Annotated[int, Field(description="Level before the attack begins.")] = 0,
        end_level: Annotated[int, Field(description="Level after release completes.")] = 0,
        channel: Channel = 1,
        steps_per_second: Annotated[int, Field(ge=1, le=200, description="Update resolution.")] = 30,
    ) -> str:
        """Shape a parameter with an ADSR envelope."""
        spec_param = device.resolve(parameter)
        if spec_param.cc is None:
            raise ToolError(f"{parameter} is an NRPN parameter; envelopes require a CC mapping")

        ch = channel - 1
        cc_number = spec_param.cc

        async def ramp(start: int, end: int, seconds: float) -> None:
            if seconds <= 0:
                return
            steps = max(1, int(seconds * steps_per_second))
            for index in range(steps + 1):
                position = index / steps
                connection.cc(cc_number, spec_param.clamp(int(start + (end - start) * position)), ch)
                await asyncio.sleep(seconds / steps)

        device.logger.info(
            f"🎚️  ENVELOPE {parameter}: A={attack_time}s D={decay_time}s S={sustain_time}s R={release_time}s"
        )

        await ramp(start_level, attack_level, attack_time)
        await ramp(attack_level, sustain_level, decay_time)
        await asyncio.sleep(sustain_time)
        await ramp(sustain_level, end_level, release_time)

        return f"Applied envelope to {parameter}"


# ============================================================================
# PATTERNS
# ============================================================================


def _register_patterns(device: DeviceServer) -> None:
    storage = device.storage

    @device.tool(WRITES)
    def save_pattern(
        pattern_name: Annotated[str, Field(description="Name to save under.")],
        bpm: Bpm,
        bars: Annotated[Bars, Field(description="Number of bars.")],
        track_triggers: Annotated[Triggers, Field(description="Track triggers as [beat, track, velocity].")],
        midi_channels: ChannelNotes,
        parameter_automation: OptionalAutomation = None,
        automation_loop_bars: AutomationLoop = 0,
        description: Annotated[str, Field(description="Description of the pattern.")] = "",
    ) -> str:
        """Save a full pattern — triggers, notes and automation — to disk."""
        path = storage.pattern_path(pattern_name)
        write_json(
            path,
            {
                "name": path.stem,
                "description": description,
                "bpm": bpm,
                "bars": bars,
                "track_triggers": track_triggers,
                "midi_channels": midi_channels,
                "parameter_automation": parameter_automation or {},
                "automation_loop_bars": automation_loop_bars,
            },
        )
        return (
            f"Saved pattern '{path.stem}' to {path}\n"
            f"  BPM: {bpm}, Bars: {bars}\n"
            f"  Track triggers: {len(track_triggers)}\n"
            f"  MIDI channels: {list(midi_channels)}"
        )

    @device.tool(READS)
    def load_pattern(pattern_name: Annotated[str, Field(description="Name of the pattern to load.")]) -> str:
        """Load a saved pattern and return its data."""
        path = storage.pattern_path(pattern_name)
        data = read_json(path)
        if data is None:
            raise ToolError(f"Pattern '{path.stem}' not found at {path}")

        return (
            f"Loaded pattern '{path.stem}':\n"
            f"  Description: {data.get('description', 'N/A')}\n"
            f"  BPM: {data.get('bpm')}, Bars: {data.get('bars')}\n"
            f"  Track triggers: {len(data.get('track_triggers', []))}\n"
            f"  MIDI channels: {list(data.get('midi_channels', {}))}\n\n"
            f"Pattern data:\n{json.dumps(data, indent=2)}"
        )

    @device.tool(READS)
    def list_patterns() -> str:
        """List every saved pattern."""
        paths = sorted(storage.patterns.glob("*.json"))
        if not paths:
            return f"No patterns found in {storage.patterns}"

        lines = [f"Available patterns ({len(paths)}):", ""]
        for path in paths:
            try:
                data = read_json(path) or {}
                lines.append(f"- {data.get('name', path.stem)}: {data.get('description', 'No description')}")
                lines.append(
                    f"    BPM: {data.get('bpm', '?')}, Bars: {data.get('bars', '?')}, "
                    f"Triggers: {len(data.get('track_triggers', []))}, "
                    f"Channels: {list(data.get('midi_channels', {}))}"
                )
            except (OSError, json.JSONDecodeError) as exc:
                lines.append(f"- {path.stem}: (could not read: {exc})")

        lines += ["", f"Patterns stored in: {storage.patterns}"]
        return "\n".join(lines)

    @device.tool(WRITES)
    def delete_pattern(pattern_name: Annotated[str, Field(description="Name of the pattern to delete.")]) -> str:
        """Delete a saved pattern."""
        path = storage.pattern_path(pattern_name)
        if not path.exists():
            raise ToolError(f"Pattern '{path.stem}' not found at {path}")
        path.unlink()
        return f"Deleted pattern '{path.stem}'"

    @device.tool(WRITES)
    def update_pattern(
        pattern_name: Annotated[str, Field(description="Name of the pattern to update.")],
        bpm: Annotated[Bpm | None, Field(description="New tempo.")] = None,
        bars: Annotated[Bars | None, Field(description="New bar count.")] = None,
        track_triggers: Annotated[Triggers | None, Field(description="Replacement track triggers.")] = None,
        midi_channels: Annotated[ChannelNotes | None, Field(description="Replacement MIDI channel data.")] = None,
        parameter_automation: Annotated[Automation | None, Field(description="Replacement automation.")] = None,
        automation_loop_bars: Annotated[AutomationLoop | None, Field(description="New automation loop length.")] = None,
        description: Annotated[str | None, Field(description="New description.")] = None,
    ) -> str:
        """Update individual fields of a saved pattern, leaving the rest alone."""
        path = storage.pattern_path(pattern_name)
        data = read_json(path)
        if data is None:
            raise ToolError(f"Pattern '{path.stem}' not found at {path}")

        updates = {
            "bpm": bpm,
            "bars": bars,
            "track_triggers": track_triggers,
            "midi_channels": midi_channels,
            "parameter_automation": parameter_automation,
            "automation_loop_bars": automation_loop_bars,
            "description": description,
        }
        changed = [key for key, value in updates.items() if value is not None]
        data.update({key: updates[key] for key in changed})
        write_json(path, data)

        return f"Updated pattern '{path.stem}': modified {', '.join(changed) if changed else 'nothing'}"

    @device.tool(WRITES)
    def edit_pattern_triggers(
        pattern_name: Annotated[str, Field(description="Name of the pattern to edit.")],
        track: Annotated[int, Field(ge=1, le=16, description=f"Track number (1-{device.spec.track_count}).")],
        beats: Annotated[list[int | float], Field(description="Beat positions, e.g. [0, 1, 2, 3].")],
        velocity: Velocity = 100,
        note: Annotated[Note | None, Field(description="Chromatic note. Defaults to the track's trigger note.")] = None,
        mode: Annotated[
            Literal["add", "remove", "replace"], Field(description="How `beats` combine with existing triggers.")
        ] = "add",
    ) -> str:
        """Add, remove or replace a track's triggers in a saved pattern."""
        path = storage.pattern_path(pattern_name)
        data = read_json(path)
        if data is None:
            raise ToolError(f"Pattern '{path.stem}' not found at {path}")

        triggers = data.get("track_triggers", [])

        def new_trigger(beat: float) -> list:
            return [beat, track, velocity, note] if note is not None else [beat, track, velocity]

        if mode == "replace":
            triggers = [t for t in triggers if t[1] != track]
            triggers += [new_trigger(b) for b in beats]
            action = f"Replaced track {track} triggers"
        elif mode == "remove":
            wanted = set(beats)
            before = sum(1 for t in triggers if t[1] == track)
            triggers = [t for t in triggers if not (t[1] == track and t[0] in wanted)]
            action = f"Removed {before - sum(1 for t in triggers if t[1] == track)} triggers from track {track}"
        else:
            existing = {t[0] for t in triggers if t[1] == track}
            fresh = [b for b in beats if b not in existing]
            triggers += [new_trigger(b) for b in fresh]
            action = f"Added {len(fresh)} triggers to track {track}"

        triggers.sort(key=lambda t: t[0])
        data["track_triggers"] = triggers
        write_json(path, data)

        count = sum(1 for t in triggers if t[1] == track)
        return f"{action} in pattern '{path.stem}'. Track {track} now has {count} triggers."

    @device.tool(WRITES)
    def edit_pattern_chords(
        pattern_name: Annotated[str, Field(description="Name of the pattern to edit.")],
        bar: Annotated[int, Field(ge=0, description="Bar number (0-based) to place the chord on.")],
        chord_notes: Annotated[list[Note], Field(description="MIDI notes, e.g. [60, 64, 67] for C major.")],
        channels: Annotated[
            list[Channel] | None, Field(description="MIDI channels to spread the chord across. Default 9-12.")
        ] = None,
        velocity: Velocity = 75,
    ) -> str:
        """Place a chord at a bar position, one note per MIDI channel.

        Each note goes on its own channel so monophonic MIDI tracks can voice a chord
        together; the note is held until the next chord.
        """
        path = storage.pattern_path(pattern_name)
        data = read_json(path)
        if data is None:
            raise ToolError(f"Pattern '{path.stem}' not found at {path}")

        channels = channels or [9, 10, 11, 12]
        midi_channels = data.get("midi_channels", {})
        beat_position = bar * 4

        # Hold each note until whatever comes next on these channels.
        next_beat = data.get("bars", 4) * 4
        for channel in channels:
            for row in midi_channels.get(str(channel), []):
                if row[0] > beat_position:
                    next_beat = min(next_beat, row[0])
        duration = max(0.1, next_beat - beat_position - 0.1)

        for channel in channels:
            key = str(channel)
            midi_channels[key] = [n for n in midi_channels.get(key, []) if abs(n[0] - beat_position) > 0.01]

        for index, note in enumerate(chord_notes[: len(channels)]):
            # Tiny per-note offset gives a subtle strum rather than a hard block chord.
            midi_channels[str(channels[index])].append([beat_position + index * 0.01, note, velocity, duration])

        for rows in midi_channels.values():
            rows.sort(key=lambda row: row[0])

        data["midi_channels"] = midi_channels
        write_json(path, data)

        return f"Set chord {chord_notes} at bar {bar} in pattern '{path.stem}'"


# ============================================================================
# AUTOMATION PRESETS
# ============================================================================


def _register_presets(device: DeviceServer) -> None:
    storage = device.storage

    @device.tool(WRITES)
    def save_automation_preset(
        name: Annotated[str, Field(description="Preset name.")],
        parameter_automation: Automation,
        description: Annotated[str, Field(description="What this preset does.")] = "",
    ) -> str:
        """Save parameter automation for reuse across patterns."""
        path = storage.preset_path(name)
        write_json(path, {"name": path.stem, "description": description, "parameter_automation": parameter_automation})
        return f"Saved automation preset '{path.stem}' to {path}"

    @device.tool(READS)
    def load_automation_preset(name: Annotated[str, Field(description="Preset name to load.")]) -> str:
        """Load a saved automation preset."""
        path = storage.preset_path(name)
        data = read_json(path)
        if data is None:
            raise ToolError(f"Preset '{path.stem}' not found at {path}")
        return json.dumps(data, indent=2)

    @device.tool(READS)
    def list_automation_presets() -> str:
        """List every saved automation preset."""
        paths = sorted(storage.presets.glob("*.json"))
        if not paths:
            return f"No presets found in {storage.presets}"

        lines = [f"Available automation presets ({len(paths)}):", ""]
        for path in paths:
            try:
                data = read_json(path) or {}
                lines.append(f"- {data.get('name', path.stem)}: {data.get('description', 'No description')}")
            except (OSError, json.JSONDecodeError) as exc:
                lines.append(f"- {path.stem}: (could not read: {exc})")

        lines += ["", f"Presets stored in: {storage.presets}"]
        return "\n".join(lines)


# ============================================================================
# EXPORT
# ============================================================================


def _register_export(device: DeviceServer) -> None:
    storage = device.storage

    @device.tool(WRITES)
    def export_pattern_to_midi(
        filename: Annotated[str, Field(description="Output filename; .mid is added if missing.")],
        bpm: Bpm = 120,
        bars: Annotated[Bars, Field(description="Number of bars.")] = 4,
        track_triggers: Annotated[
            Triggers | None, Field(description="Track triggers as [beat, track, velocity].")
        ] = None,
        melody_notes: Annotated[
            list[Row] | None, Field(description="Melody notes as [beat, note, velocity, duration_sec].")
        ] = None,
        melody_channel: Channel = 1,
    ) -> str:
        """Export a pattern to a standard MIDI file."""
        track_triggers = track_triggers or []
        melody_notes = melody_notes or []
        path = storage.recording_path(filename)

        midifile.write_pattern(
            path,
            bpm=bpm,
            track_triggers=track_triggers,
            melody_notes=melody_notes,
            melody_channel=melody_channel,
            drum_track_name=f"{device.spec.display_name} Drums",
        )
        return (
            f"Exported pattern to {path}: {bars} bars, {len(track_triggers)} triggers, {len(melody_notes)} melody notes"
        )

    @device.tool(WRITES)
    def export_automation_to_midi(
        filename: Annotated[str, Field(description="Output filename; .mid is added if missing.")],
        automation: Annotated[dict[str, Any], Field(description="{'parameter_automation': {...}, 'bpm': N}.")],
        channel: Channel = 1,
    ) -> str:
        """Export parameter automation as CC events in a MIDI file."""
        path = storage.recording_path(filename)
        bpm = automation.get("bpm", 120)

        events: list[tuple[float, int, int]] = []
        for name, rows in automation.get("parameter_automation", {}).items():
            parameter = device.spec.parameter(name)
            if parameter is None or parameter.cc is None:
                continue
            events += [(beat, parameter.cc, parameter.clamp(int(value))) for beat, value in rows]

        count = midifile.write_automation(path, bpm=bpm, events=events, channel=channel - 1)
        return f"Exported automation to {path}: {count} CC events"

    @device.tool(WRITES)
    def save_last_melody(
        filename: Annotated[str, Field(description="Output filename; .mid is added if missing.")],
    ) -> str:
        """Save the most recently played melody to a MIDI file."""
        melody = device.history.melody
        if not melody:
            raise ToolError("No melody has been played yet. Use play_pattern_with_melody first.")

        path = storage.recording_path(filename)
        count = midifile.write_notes(
            path,
            bpm=melody["bpm"],
            notes=melody["notes"],
            channel=melody.get("channel", 1) - 1,
            track_name="Melody",
        )
        return f"Saved melody to {path} ({count} notes at {melody['bpm']} BPM)"

    @device.tool(WRITES)
    def save_last_pattern(
        filename: Annotated[str, Field(description="Output filename; .mid is added if missing.")],
    ) -> str:
        """Save the most recently played track pattern to a MIDI file."""
        tracks = device.history.tracks
        if not tracks:
            raise ToolError("No pattern has been played yet. Use play_pattern_with_tracks first.")

        path = storage.recording_path(filename)
        notes = [[row[0], int(row[1]) - 1, row[2] if len(row) > 2 else 100, 0.1] for row in tracks["triggers"]]
        count = midifile.write_notes(path, bpm=tracks["bpm"], notes=notes, channel=0, track_name="Drums")
        return f"Saved pattern to {path} ({count} triggers at {tracks['bpm']} BPM)"


# ============================================================================
# RECORDING
# ============================================================================


def _register_recording(device: DeviceServer) -> None:
    connection = device.connection
    storage = device.storage

    @device.tool(LISTENS)
    async def monitor_midi_input(
        duration: Annotated[float, Field(gt=0, le=300, description="How long to listen, in seconds.")] = 10,
    ) -> str:
        """Watch incoming MIDI and report what arrived."""
        port = connection.require_input()
        device.logger.info(f"👂 MONITORING MIDI INPUT for {duration} seconds...")

        messages: list[str] = []
        started = time.time()
        while time.time() - started < duration:
            for message in port.iter_pending():
                messages.append(f"{time.time() - started:.2f}s: {message}")
                device.logger.info(f"📥 {message}")
            await asyncio.sleep(0.01)

        if not messages:
            return f"No MIDI messages received in {duration} seconds"
        return f"Received {len(messages)} messages:\n" + "\n".join(messages[:50])

    @device.tool(WRITES)
    async def record_midi_input(
        filename: Annotated[str, Field(description="Output filename; .mid is added if missing.")],
        duration_sec: Annotated[float, Field(gt=0, le=600, description="Recording length in seconds.")] = 30,
        bpm: Annotated[Bpm, Field(description="Tempo written into the file.")] = 120,
    ) -> str:
        """Record incoming MIDI to a .mid file."""
        port = connection.require_input()
        path = storage.recording_path(filename)
        device.logger.info(f"⏺️  RECORDING MIDI INPUT to {path} for {duration_sec} seconds...")

        captured: list[tuple[float, mido.Message]] = []
        started = time.time()
        while time.time() - started < duration_sec:
            for message in port.iter_pending():
                if not message.is_meta:
                    elapsed = time.time() - started
                    captured.append((elapsed, message))
                    device.logger.info(f"📥 {elapsed:.2f}s: {message}")
            await asyncio.sleep(0.01)

        midifile.write_recording(path, bpm=bpm, messages=captured)
        return f"Recorded {len(captured)} MIDI messages to {path}"

    @device.tool(READS)
    def list_midi_recordings() -> str:
        """List the MIDI files in the recordings directory."""
        paths = sorted(storage.recordings.glob("*.mid"))
        if not paths:
            return f"No recordings found in {storage.recordings}"

        lines = [f"MIDI Recordings ({len(paths)}):", ""]
        for path in paths:
            try:
                loaded = mido.MidiFile(path)
                lines.append(f"- {path.name}: {loaded.length:.1f}s, {len(loaded.tracks)} tracks")
            except (OSError, ValueError, EOFError) as exc:
                lines.append(f"- {path.name}: (could not read: {exc})")

        lines += ["", f"Recordings stored in: {storage.recordings}"]
        return "\n".join(lines)

    @device.tool(PLAYS)
    async def play_midi_file(
        filename: Annotated[str, Field(description="MIDI file in the recordings directory.")],
        channel_offset: Annotated[int, Field(ge=-15, le=15, description="Shift every channel by this amount.")] = 0,
    ) -> str:
        """Play a MIDI file out to the device."""
        path = storage.recording_path(filename)
        if not path.exists():
            raise ToolError(f"File not found: {path}")

        device.logger.info(f"▶️  PLAYING MIDI FILE: {path}")
        # Iterating a MidiFile yields messages whose .time is the delta in seconds.
        # MidiFile.play() would do the same with time.sleep and block the event loop.
        for message in mido.MidiFile(path):
            await asyncio.sleep(message.time)
            if message.is_meta:
                continue
            if hasattr(message, "channel"):
                message = message.copy(channel=(message.channel + channel_offset) % 16)
            connection.send(message)

        return f"Played {path}"


# ============================================================================
# RESOURCES
# ============================================================================


def _register_resources(device: DeviceServer) -> None:
    spec = device.spec
    connection = device.connection

    @device.mcp.resource("midi://ports", mime_type="application/json")
    def midi_ports() -> str:
        """Every MIDI input and output port visible on this machine."""
        return json.dumps(available_ports(), indent=2)

    @device.mcp.resource(f"midi://{spec.slug}/status")
    def device_status() -> str:
        """Connection status for this device."""
        lines = [
            f"Device: {spec.display_name}",
            f"Port name: {spec.port_name}",
            f"Output connected: {connection.output_port is not None}",
            f"Input connected: {connection.input_port is not None}",
            f"Tracks: {spec.track_count}",
        ]
        if connection.output_port is not None:
            lines.append(f"Output port: {connection.output_port.name}")
        if connection.input_port is not None:
            lines.append(f"Input port: {connection.input_port.name}")
        if spec.notes:
            lines += ["", spec.notes]
        return "\n".join(lines)

    @device.mcp.resource(f"midi://{spec.slug}/parameters", mime_type="application/json")
    def device_parameters() -> str:
        """The full parameter table, so it doesn't have to live in tool descriptions."""
        return json.dumps(
            {
                name: {
                    "type": parameter.kind,
                    "cc": parameter.cc,
                    "msb": parameter.msb,
                    "lsb": parameter.lsb,
                    "range": [parameter.minimum, parameter.maximum],
                }
                for name, parameter in spec.parameters.items()
            },
            indent=2,
        )
