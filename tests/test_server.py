"""Tests for the shared server core, run against every device."""

import asyncio
import itertools
import json
import logging
import time
from importlib.metadata import version

import mido
import pytest
from mcp.client import Client

from conftest import RecordingPort, ToolError
from elektron_mcp import clock
from elektron_mcp.midi import MidiConnection


class TestCoreMidi:
    async def test_send_note_emits_on_then_off(self, any_device):
        result = await any_device.call("send_note", note=60, velocity=100, duration=0.01, channel=1)

        assert "60" in result
        assert any_device.port.types == ["note_on", "note_off"]

        note_on = any_device.port.messages[0]
        assert (note_on.note, note_on.velocity, note_on.channel) == (60, 100, 0)
        assert any_device.port.messages[1].note == 60

    async def test_send_cc_is_one_message_on_zero_indexed_channel(self, any_device):
        result = await any_device.call("send_cc", cc_number=74, value=100, channel=2)

        assert "CC 74" in result
        message = any_device.port.messages[0]
        assert (message.type, message.control, message.value, message.channel) == ("control_change", 74, 100, 1)

    async def test_send_nrpn_emits_the_four_cc_sequence(self, any_device):
        result = await any_device.call("send_nrpn", msb=1, lsb=5, value=64, channel=1)

        assert "NRPN 1:5" in result
        assert any_device.port.controls() == [(99, 1), (98, 5), (6, 64), (38, 0)]

    async def test_program_change(self, any_device):
        await any_device.call("send_program_change", program=42, channel=1)

        message = any_device.port.messages[0]
        assert (message.type, message.program) == ("program_change", 42)

    async def test_note_sequence_plays_every_note(self, any_device):
        await any_device.call("send_note_sequence", notes=[[60, 100, 0.01], [62, 100, 0.01]], delay=0.01, channel=1)

        assert any_device.port.types == ["note_on", "note_off", "note_on", "note_off"]

    async def test_sysex_accepts_a_hex_string(self, any_device):
        await any_device.call("send_sysex", hex_string="00 20 3C")

        message = any_device.port.messages[0]
        assert message.type == "sysex"
        assert list(message.data) == [0x00, 0x20, 0x3C]

    async def test_sysex_hex_string_may_include_framing(self, any_device):
        await any_device.call("send_sysex", hex_string="F0 00 20 3C F7")

        assert list(any_device.port.messages[0].data) == [0x00, 0x20, 0x3C]


class TestTransport:
    async def test_start_stop_continue(self, any_device):
        await any_device.call("send_midi_start")
        await any_device.call("send_midi_stop")
        await any_device.call("send_midi_continue")

        assert any_device.port.types == ["start", "stop", "continue"]

    async def test_song_position(self, any_device):
        await any_device.call("send_song_position", position=64)

        message = any_device.port.messages[0]
        assert (message.type, message.pos) == ("songpos", 64)


def _clocks_before_each_note(port: RecordingPort) -> list[int]:
    """How many clock pulses went out before each note-on, i.e. where each note landed."""
    return [port.types[:index].count("clock") for index, kind in enumerate(port.types) if kind == "note_on"]


class TestClock:
    """Playback tests run on looptime's virtual event-loop clock, so whole bars take no real time.

    The real-time tests at the end cover cancellation and tick timing.
    """

    @pytest.mark.looptime
    async def test_one_bar_is_start_96_clocks_stop(self, any_device, looptime):
        await any_device.call("play_with_clock", bars=1, bpm=240, send_start=True, send_stop=True)

        types = any_device.port.types
        assert types[0] == "start"
        assert types[-1] == "stop"
        assert types.count("clock") == 96
        # One bar at 240 BPM is one second.
        assert looptime == pytest.approx(1.0, abs=0.01)

    @pytest.mark.looptime
    async def test_melody_notes_land_inside_the_clock_stream(self, any_device):
        await any_device.call(
            "play_pattern_with_melody",
            notes=[[0, 60, 100, 0.01], [1, 64, 100, 0.01]],
            bars=1,
            bpm=240,
            channel=1,
        )

        assert [m.note for m in any_device.port.of_type("note_on")] == [60, 64]
        assert _clocks_before_each_note(any_device.port) == [1, 25]

    @pytest.mark.looptime
    async def test_loop_repeats_its_notes_each_bar(self, any_device):
        await any_device.call(
            "play_pattern_with_loop",
            loop_notes=[[0, 60, 100]],
            loop_length=1,
            bars=4,
            bpm=240,
            channel=1,
        )

        # One note at the top of each bar, for four bars.
        assert _clocks_before_each_note(any_device.port) == [1, 97, 193, 289]

    @pytest.mark.looptime
    async def test_long_patterns_report_progress_each_bar(self, any_device):
        updates: list[tuple[float, float | None]] = []

        async def on_progress(progress, total, message):
            updates.append((progress, total))

        async with Client(any_device.device.mcp) as client:
            await client.call_tool("play_with_clock", {"bars": 2, "bpm": 300}, progress_callback=on_progress)

        assert updates == [(1, 2), (2, 2)]

    @pytest.mark.looptime
    async def test_automation_repeats_every_loop(self, any_device):
        await any_device.call(
            "play_pattern_with_parameter_automation",
            triggers=[[0, 1, 100]],
            parameter_automation={"filter_cutoff": [[0, 20], [2, 80]]},
            automation_loop_bars=1,
            bars=4,
            bpm=240,
        )

        assert [value for _, value in any_device.port.controls()] == [20, 80] * 4

    async def test_a_slow_progress_client_never_delays_a_clock_tick(self):
        """Progress used to be awaited inside the clock loop, so a slow client stalled the beat."""

        class TimedPort(RecordingPort):
            def __init__(self) -> None:
                super().__init__()
                self.sent_at: list[float] = []

            def send(self, message: mido.Message) -> None:
                super().send(message)
                self.sent_at.append(time.perf_counter())

        port = TimedPort()
        connection = MidiConnection(port_name="x", display_name="x", logger=logging.getLogger("test"))
        connection.output_port = port
        reported: list[int] = []

        async def slow_progress(bar, total):
            await asyncio.sleep(0.3)
            reported.append(bar)

        await clock.play(connection, [], bars=2, bpm=600, progress=slow_progress)

        ticks = [at for message, at in zip(port.messages, port.sent_at, strict=True) if message.type == "clock"]
        assert len(ticks) == 192
        assert max(b - a for a, b in itertools.pairwise(ticks)) < clock.clock_interval(600) + 0.05
        assert reported[-1] == 2

    async def test_cancelling_playback_stops_the_sequencer(self):
        """Otherwise the device sits mid-pattern waiting for clock that never comes."""
        port = RecordingPort()
        connection = MidiConnection(port_name="x", display_name="x", logger=logging.getLogger("test"))
        connection.output_port = port

        task = asyncio.create_task(clock.play(connection, [], bars=8, bpm=120))
        await asyncio.sleep(0.05)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

        assert port.types[0] == "start"
        assert port.types[-1] == "stop"

    @pytest.mark.looptime
    async def test_a_failure_mid_pattern_still_stops_the_sequencer(self):
        """A progress notification can fail if the client goes away mid-pattern."""
        port = RecordingPort()
        connection = MidiConnection(port_name="x", display_name="x", logger=logging.getLogger("test"))
        connection.output_port = port

        async def broken_progress(bar, total):
            raise RuntimeError("client went away")

        with pytest.raises(RuntimeError):
            await clock.play(connection, [], bars=4, bpm=300, progress=broken_progress)

        assert port.types[0] == "start"
        assert port.types[-1] == "stop"
        # The failure surfaces at the next bar instead of playing out all four.
        assert port.types.count("clock") == 2 * 96

    async def test_out_of_range_notes_are_rejected_before_start(self, any_device):
        """mido used to raise mid-pattern, after Start, leaving the device running with no Stop."""
        with pytest.raises(ToolError, match="Note 200 is out of range"):
            await any_device.call("play_pattern_with_melody", notes=[[0, 60], [1, 200]], bars=1, bpm=300)
        assert any_device.port.messages == []

    async def test_bad_channel_keys_are_explained(self, any_device):
        with pytest.raises(ToolError, match="channel numbers 1-16"):
            await any_device.call("play_pattern_with_multi_channel_midi", midi_channels={"bass": [[0, 40]]})
        with pytest.raises(ToolError, match="MIDI channel 17 is out of range 1-16"):
            await any_device.call("play_pattern_with_multi_channel_midi", midi_channels={"17": [[0, 40]]})
        assert any_device.port.messages == []


class TestParameters:
    async def test_list_parameters_groups_by_category(self, any_device):
        result = await any_device.call("list_parameters")

        assert "Filter" in result
        assert "Total:" in result

    async def test_set_parameter_sends_a_cc(self, any_device):
        # Devices disagree on which CC this is (Digitakt 74, Digitone 23), so ask the spec.
        expected = any_device.device.spec.parameters["filter_cutoff"].cc

        await any_device.call("set_parameter", name="filter_cutoff", value=100, channel=1)

        assert any_device.port.controls() == [(expected, 100)]

    async def test_set_parameter_rejects_unknown_names(self, any_device):
        with pytest.raises(ToolError, match="Unknown parameter"):
            await any_device.call("set_parameter", name="not_a_real_parameter", value=1)

    async def test_set_parameter_handles_nrpn_parameters(self, any_device):
        """NRPN parameters used to be rejected outright, stranding half the table."""
        nrpn = [p for p in any_device.device.spec.parameters.values() if p.kind == "nrpn"]
        assert nrpn, "expected the device to define some NRPN parameters"

        result = await any_device.call("set_parameter", name=nrpn[0].name, value=nrpn[0].minimum)

        assert "NRPN" in result
        assert len(any_device.port.controls()) == 4


class TestPatterns:
    async def test_save_load_list_delete_round_trip(self, any_device):
        await any_device.call(
            "save_pattern",
            pattern_name="test_pattern",
            bpm=120,
            bars=4,
            track_triggers=[[0, 1, 100], [1, 2, 80]],
            midi_channels={"9": [[0, 60, 100, 0.5]]},
            description="Test pattern",
        )
        path = any_device.device.storage.pattern_path("test_pattern")
        assert path.exists()

        loaded = await any_device.call("load_pattern", pattern_name="test_pattern")
        assert "test_pattern" in loaded
        assert "120" in loaded

        assert "test_pattern" in await any_device.call("list_patterns")

        await any_device.call("delete_pattern", pattern_name="test_pattern")
        assert not path.exists()

    async def test_update_pattern_touches_only_named_fields(self, any_device):
        await any_device.call(
            "save_pattern",
            pattern_name="p",
            bpm=120,
            bars=4,
            track_triggers=[[0, 1, 100]],
            midi_channels={},
            description="original",
        )

        await any_device.call("update_pattern", pattern_name="p", bpm=140)

        data = json.loads(any_device.device.storage.pattern_path("p").read_text())
        assert data["bpm"] == 140
        assert data["description"] == "original"
        assert data["track_triggers"] == [[0, 1, 100]]

    async def test_edit_pattern_triggers_adds_without_duplicating(self, any_device):
        await any_device.call(
            "save_pattern",
            pattern_name="p",
            bpm=120,
            bars=1,
            track_triggers=[[0, 1, 100]],
            midi_channels={},
        )

        await any_device.call("edit_pattern_triggers", pattern_name="p", track=1, beats=[0, 2], mode="add")

        data = json.loads(any_device.device.storage.pattern_path("p").read_text())
        assert sorted(t[0] for t in data["track_triggers"]) == [0, 2]

    async def test_missing_pattern_raises(self, any_device):
        with pytest.raises(ToolError, match="not found"):
            await any_device.call("load_pattern", pattern_name="nope")

    @pytest.mark.parametrize("name", ["../escaped", "sub/p", "..", ""])
    async def test_names_cannot_leave_the_data_directory(self, any_device, name):
        with pytest.raises(ToolError, match="Invalid name"):
            await any_device.call(
                "save_pattern", pattern_name=name, bpm=120, bars=1, track_triggers=[], midi_channels={}
            )
        with pytest.raises(ToolError, match="Invalid name"):
            await any_device.call("delete_pattern", pattern_name=name)

        storage_root = any_device.device.storage.patterns.parent.parent
        assert not list(storage_root.rglob("*.json"))


def _track_hit(device, track: int) -> tuple[int, int]:
    """(zero-based channel, note) a text-pattern tN hit sends."""
    return (0, track - 1) if device.spec.trigger_notes else (track - 1, 60)


async def _until(condition, timeout: float = 3.0) -> None:
    """Wait for background playback to reach a state, instead of guessing a sleep."""
    deadline = time.monotonic() + timeout
    while not condition():
        assert time.monotonic() < deadline, "timed out waiting for playback"
        await asyncio.sleep(0.01)


class TestPatternLanguage:
    async def test_text_pattern_and_song_round_trip(self, any_device):
        first = "@bpm 300\n@grid 1/32\nt1: x"
        second = "@bpm 300\n@grid 1/32\nt2: x"

        checked = await any_device.call("check_pattern", text=first)
        assert "1 steps of 1/32" in checked
        await any_device.call("save_pattern_text", pattern_name="intro", text=first)
        await any_device.call("save_pattern_text", pattern_name="verse", text=second)
        saved = await any_device.call(
            "save_song",
            song_name="track",
            arrangement="intro x2, verse",
        )

        assert "3 passes" in saved
        assert "intro x2, verse" in await any_device.call("list_songs")
        assert "Text:" in await any_device.call("list_patterns")
        assert first in await any_device.call("load_pattern", pattern_name="intro")

        await any_device.call("play_pattern_text", what="track")
        await _until(lambda: any_device.device.player.status is None)

        notes = any_device.port.of_type("note_on")
        assert [(message.channel, message.note) for message in notes] == [
            _track_hit(any_device.device, 1),
            _track_hit(any_device.device, 1),
            _track_hit(any_device.device, 2),
        ]

    async def test_loop_switches_at_boundary_and_publishes_live_state(self, any_device):
        # A 0.8s pass, so the queue call lands well inside it.
        current = "@bpm 300\n@grid 1/4\nt1: x..."
        next_pattern = "@bpm 300\n@grid 1/32\nt2: x..."
        await any_device.call("save_pattern_text", pattern_name="current", text=current)
        await any_device.call("save_pattern_text", pattern_name="next", text=next_pattern)

        assert "on loop" in await any_device.call("play_pattern_text", what="current", loop=True)
        queued = await any_device.call("play_pattern_text", what="next", loop=True)
        live = json.loads(await any_device.read(f"midi://{any_device.device.spec.slug}/live"))

        assert queued.startswith("Queued")
        assert live["current_pass"]["label"] == "current"
        assert any(event["type"] == "queued" and event["label"] == "next" for event in live["recent"])

        def sent():
            return [(message.channel, message.note) for message in any_device.port.of_type("note_on")]

        await _until(lambda: _track_hit(any_device.device, 2) in sent())
        assert sent()[0] == _track_hit(any_device.device, 1)
        assert await any_device.call("stop_pattern_playback") == "Stopped pattern playback"
        stopped = json.loads(await any_device.read(f"midi://{any_device.device.spec.slug}/live"))
        assert stopped["current_pass"] is None

    async def test_a_queued_pattern_without_loop_plays_once_then_stops(self, any_device):
        """Queued material used to be forced to loop, ignoring loop=False."""
        await any_device.call("save_pattern_text", pattern_name="current", text="@bpm 300\n@grid 1/8\nt1: x...")
        await any_device.call("save_pattern_text", pattern_name="next", text="@bpm 300\n@grid 1/32\nt2: x...")

        await any_device.call("play_pattern_text", what="current", loop=True)
        assert (await any_device.call("play_pattern_text", what="next")).startswith("Queued")

        await _until(lambda: any_device.device.player.status is None)
        hits = [(m.channel, m.note) for m in any_device.port.of_type("note_on")]
        assert hits.count(_track_hit(any_device.device, 2)) == 1

    async def test_text_pattern_errors_keep_line_and_column(self, any_device):
        with pytest.raises(ToolError, match=r"line 1, col 5.*hold"):
            await any_device.call("check_pattern", text="t1: -..q")

    async def test_structured_edit_tools_refuse_text_patterns(self, any_device):
        await any_device.call("save_pattern_text", pattern_name="text", text="t1: x...")

        with pytest.raises(ToolError, match="uses text notation"):
            await any_device.call("update_pattern", pattern_name="text", bpm=140)


class TestExport:
    async def test_export_explains_out_of_range_rows(self, any_device):
        """mido raised ValueError here, which mcp 2.x hid behind a bare "Error executing tool"."""
        with pytest.raises(ToolError, match="Can't export"):
            await any_device.call("export_pattern_to_midi", filename="out", track_triggers=[[0, 0, 100]])
        with pytest.raises(ToolError, match="Can't export"):
            await any_device.call(
                "export_automation_to_midi", filename="auto", automation={"parameter_automation": {"filter_cutoff": 5}}
            )

    async def test_simultaneous_notes_export_at_the_right_times(self, any_device):
        """Rows were written one after another, so a chord or two hits on one beat gave a
        negative delta time and the export failed."""
        await any_device.call(
            "export_pattern_to_midi",
            filename="out",
            bpm=120,
            track_triggers=[[0, 1, 100], [0, 2, 100]],
            melody_notes=[[0, 60, 100, 1.0], [0, 64, 100, 1.0], [1, 67, 100, 0.25]],
        )

        midi = mido.MidiFile(any_device.device.storage.recording_path("out"))
        melody = midi.tracks[2]
        ticks = 0
        timeline = []
        for message in melody:
            ticks += message.time
            if message.type in ("note_on", "note_off"):
                timeline.append((ticks, message.type, message.note))
        # At 120 BPM a beat is 0.5s: the 1s chord lasts 2 beats and outlasts the note at beat 1.
        beat = midi.ticks_per_beat
        assert timeline == [
            (0, "note_on", 60),
            (0, "note_on", 64),
            (beat, "note_on", 67),
            (beat * 3 // 2, "note_off", 67),
            (beat * 2, "note_off", 60),
            (beat * 2, "note_off", 64),
        ]


class TestRecording:
    async def test_monitor_summarizes_realtime_floods_and_keeps_useful_events(self, any_device):
        pending = [mido.Message("clock") for _ in range(100)]
        pending.append(mido.Message("control_change", control=23, value=96))

        def iter_pending():
            nonlocal pending
            messages, pending = pending, []
            return iter(messages)

        any_device.port.iter_pending = iter_pending

        result = await any_device.call("monitor_midi_input", duration=0.02)

        assert "Received 101 messages (clock=100, control_change=1)." in result
        assert "control_change channel=0 control=23 value=96" in result
        assert result.count("clock") == 1


class TestResources:
    async def test_status_reports_the_connection(self, any_device):
        slug = any_device.device.spec.slug
        status = await any_device.read(f"midi://{slug}/status")

        assert "Output connected: True" in status

    async def test_parameters_resource_is_machine_readable(self, any_device):
        slug = any_device.device.spec.slug
        parameters = json.loads(await any_device.read(f"midi://{slug}/parameters"))

        assert len(parameters) == len(any_device.device.spec.parameters)
        assert all("range" in entry for entry in parameters.values())


class TestConnection:
    async def test_disconnected_tools_tell_the_client_why(self, any_device):
        """mcp 2.x hides the text of unexpected exceptions, so this must stay a ToolError."""
        any_device.device.connection.output_port = None

        with pytest.raises(ToolError, match="Not connected"):
            await any_device.call("send_cc", cc_number=74, value=100)


class TestSchema:
    async def test_every_parameter_is_described(self, any_device):
        """Bare `Annotated[int, "text"]` metadata is silently dropped from the schema."""
        for tool in await any_device.tools():
            for name, prop in tool.input_schema["properties"].items():
                assert prop.get("description"), f"{tool.name}.{name} has no description"

    async def test_every_array_declares_its_items(self, any_device):
        """OpenAI rejects function schemas with an untyped array."""

        def arrays(schema):
            if isinstance(schema, dict):
                if schema.get("type") == "array":
                    yield schema
                for value in schema.values():
                    yield from arrays(value)
            elif isinstance(schema, list):
                for value in schema:
                    yield from arrays(value)

        for tool in await any_device.tools():
            for array in arrays(tool.input_schema):
                assert "items" in array, f"{tool.name} has an array without items"

    async def test_out_of_range_arguments_are_rejected_before_sending(self, any_device):
        with pytest.raises(ToolError):
            await any_device.call("send_cc", cc_number=74, value=128)
        assert any_device.port.messages == []

    async def test_every_tool_declares_its_hints(self, any_device):
        """Clients use these to decide what needs confirmation; mcp defaults would claim destructive."""
        for tool in await any_device.tools():
            hints = tool.annotations
            assert hints is not None and hints.read_only_hint is not None, tool.name
            assert hints.open_world_hint is not None, tool.name
            if not hints.read_only_hint:
                assert hints.destructive_hint is not None and hints.idempotent_hint is not None, tool.name

    async def test_tool_schemas_stay_inside_the_token_budget(self, any_device):
        """About 4 characters per token, counted the way the docs report it. Budget: 7.5k per server."""
        tools = await any_device.tools()
        chars = sum(len(t.name) + len(t.description or "") + len(json.dumps(t.input_schema)) for t in tools)
        assert chars / 4 < 7500

    async def test_server_reports_its_version_and_instructions(self, any_device):
        async with Client(any_device.device.mcp) as client:
            assert client.server_info.version == version("digitakt-digitone-mcp")
            assert f"midi://{any_device.device.spec.slug}/parameters" in (client.instructions or "")
