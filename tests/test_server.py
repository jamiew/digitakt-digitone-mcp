"""Tests for the shared server core, run against every device."""

import json

import pytest

from elektron_mcp.midi import NotConnectedError


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


class TestClock:
    async def test_one_bar_is_start_96_clocks_stop(self, any_device):
        await any_device.call("play_with_clock", bars=1, bpm=240, send_start=True, send_stop=True)

        types = any_device.port.types
        assert types[0] == "start"
        assert types[-1] == "stop"
        assert types.count("clock") == 96

    async def test_melody_notes_land_inside_the_clock_stream(self, any_device):
        await any_device.call(
            "play_pattern_with_melody",
            notes=[[0, 60, 100, 0.01], [1, 64, 100, 0.01]],
            bars=1,
            bpm=240,
            channel=1,
        )

        assert [m.note for m in any_device.port.of_type("note_on")] == [60, 64]

    async def test_loop_repeats_its_notes_each_bar(self, any_device):
        await any_device.call(
            "play_pattern_with_loop",
            loop_notes=[[0, 60, 100]],
            loop_length=1,
            bars=4,
            bpm=240,
            channel=1,
        )

        # One note per bar of loop, for four bars.
        assert len(any_device.port.of_type("note_on")) == 4


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
        with pytest.raises(Exception, match="Unknown parameter"):
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
        with pytest.raises(Exception, match="not found"):
            await any_device.call("load_pattern", pattern_name="nope")


class TestExport:
    async def test_export_pattern_writes_a_midi_file(self, any_device):
        await any_device.call(
            "export_pattern_to_midi",
            filename="out",
            bpm=120,
            bars=1,
            track_triggers=[[0, 1, 100]],
            melody_notes=[[0, 60, 100, 0.5]],
        )

        assert any_device.device.storage.recording_path("out").exists()


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
    async def test_tools_fail_loudly_when_disconnected(self, any_device):
        any_device.device.connection.output_port = None

        with pytest.raises(NotConnectedError, match="Not connected"):
            any_device.device.connection.cc(74, 100, 0)
