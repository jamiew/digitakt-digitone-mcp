"""Tests for the tools and specs unique to each device."""

import pytest

from elektron_mcp.devices import DEVICES
from elektron_mcp.devices.digitone import ALGORITHM_DESCRIPTIONS
from elektron_mcp.devices.digitone_cc import Syn1CC, Syn2CC


class TestSpecs:
    def test_every_device_has_a_distinct_slug_port_and_storage(self):
        assert {s.slug for s in DEVICES.values()} == set(DEVICES)
        assert len({s.port_name for s in DEVICES.values()}) == len(DEVICES)

    def test_parameter_tables_parse(self):
        """parse_parameters raises on malformed entries, so this covers the whole table."""
        for spec in DEVICES.values():
            assert spec.parameters
            assert all(p.minimum <= p.maximum for p in spec.parameters.values())
            assert all(p.cc is not None for p in spec.parameters.values() if p.kind == "cc")
            assert all(p.msb is not None and p.lsb is not None for p in spec.parameters.values() if p.kind == "nrpn")

    def test_categories_only_reference_real_parameters(self):
        for spec in DEVICES.values():
            listed = {name for names in spec.categories.values() for name in names}
            assert listed <= set(spec.parameters)


class TestDigitakt:
    async def test_only_digitakt_exposes_trigger_tools(self, digitakt, digitone):
        assert "trigger_track" in await digitakt.tool_names()
        assert "trigger_track" not in await digitone.tool_names()

    async def test_trigger_track_maps_track_to_note(self, digitakt):
        result = await digitakt.call("trigger_track", track=3, velocity=80, duration=0.01, channel=1)

        assert "Track 3" in result
        note_on = digitakt.port.messages[0]
        assert (note_on.note, note_on.velocity) == (2, 80)  # track 3 -> note 2

    async def test_set_trig_note_addresses_the_step_by_nrpn(self, digitakt):
        result = await digitakt.call("set_trig_note", track=1, step=5, note=60, channel=1)

        assert "Step 5" in result
        # MSB 3 selects the trig-note page; LSB is the zero-based step.
        assert digitakt.port.controls() == [(99, 3), (98, 4), (6, 60), (38, 0)]

    async def test_reset_velocities_writes_every_step(self, digitakt):
        await digitakt.call("reset_velocities", track=1, steps=4, velocity=100)

        assert len(digitakt.port.controls()) == 4 * 4

    async def test_track_pattern_fires_each_trigger(self, digitakt):
        await digitakt.call("play_pattern_with_tracks", triggers=[[0, 1, 100], [1, 2, 90]], bars=1, bpm=240)

        assert [m.note for m in digitakt.port.of_type("note_on")] == [0, 1]


class TestDigitone:
    async def test_only_digitone_exposes_fm_tools(self, digitakt, digitone):
        fm_tools = {"set_algorithm", "set_ratios", "set_operator_levels", "set_operator_envelope", "set_chorus"}
        assert fm_tools <= await digitone.tool_names()
        assert not (fm_tools & await digitakt.tool_names())

    async def test_play_chord_sends_every_note_together(self, digitone):
        result = await digitone.call("play_chord", notes=[60, 64, 67], velocity=100, duration=0.01)

        assert "C4" in result
        assert [m.note for m in digitone.port.of_type("note_on")] == [60, 64, 67]
        assert len(digitone.port.of_type("note_off")) == 3

    async def test_set_algorithm_is_one_indexed_on_the_display(self, digitone):
        result = await digitone.call("set_algorithm", algorithm=1, channel=1)

        assert digitone.port.controls() == [(Syn1CC.ALGORITHM, 0)]
        assert ALGORITHM_DESCRIPTIONS[1] in result

    async def test_set_algorithm_rejects_out_of_range(self, digitone):
        with pytest.raises(Exception, match="1-8"):
            await digitone.call("set_algorithm", algorithm=9)

    async def test_set_parameter_enforces_the_declared_range(self, digitone):
        """`fm_algorithm` is 0-7. The old code looked for min/max keys the table never had,
        so it fell back to 0-127 and happily sent out-of-range values."""
        assert digitone.device.spec.parameters["fm_algorithm"].maximum == 7

        with pytest.raises(Exception, match="out of range"):
            await digitone.call("set_parameter", name="fm_algorithm", value=100)

    async def test_set_ratios_only_sends_what_was_given(self, digitone):
        await digitone.call("set_ratios", ratio_a=64)

        assert digitone.port.controls() == [(Syn1CC.RATIO_A, 64)]

    async def test_operator_envelope_sends_each_named_stage(self, digitone):
        """Regression: this used to read its arguments via locals() inside a loop."""
        result = await digitone.call("set_operator_envelope", operator="A", attack=10, decay=20, level=30)

        assert digitone.port.controls() == [
            (Syn2CC.A_ENV_ATTACK, 10),
            (Syn2CC.A_ENV_DECAY, 20),
            (Syn2CC.A_LEVEL, 30),
        ]
        assert "attack=10" in result and "decay=20" in result and "level=30" in result

    async def test_operator_envelope_rejects_a_bad_operator(self, digitone):
        with pytest.raises(Exception, match="'A' or 'B'"):
            await digitone.call("set_operator_envelope", operator="C", attack=1)
