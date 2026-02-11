"""
Unit tests for Digitone MCP server.
Tests that the Digitone server produces correct MIDI messages without requiring hardware.
"""

import asyncio
import sys
from pathlib import Path
from unittest.mock import MagicMock

# Add parent dir to path
sys.path.insert(0, str(Path(__file__).parent.parent))


class MockMidiPort:
    """Mock MIDI port that records all sent messages"""

    def __init__(self):
        self.messages = []
        self.name = "Mock Digitone"

    def send(self, msg):
        self.messages.append(msg)

    def clear(self):
        self.messages = []

    def get_message_types(self):
        return [m.type for m in self.messages]


mock_output = MockMidiPort()
mock_input = MagicMock()
mock_input.iter_pending = MagicMock(return_value=iter([]))


def setup_mocks():
    import mido

    mido.get_output_names = MagicMock(return_value=["Elektron Digitone"])
    mido.get_input_names = MagicMock(return_value=["Elektron Digitone"])
    mido.open_output = MagicMock(return_value=mock_output)
    mido.open_input = MagicMock(return_value=mock_input)


setup_mocks()

import server_digitone as server


def test_send_note():
    """Test send_note produces correct MIDI messages"""
    mock_output.clear()
    server.output_port = mock_output

    result = asyncio.run(server.send_note(note=60, velocity=100, duration=0.01, channel=1))

    assert "C4" in result
    assert len(mock_output.messages) == 2

    note_on = mock_output.messages[0]
    assert note_on.type == "note_on"
    assert note_on.note == 60
    assert note_on.velocity == 100
    assert note_on.channel == 0

    note_off = mock_output.messages[1]
    assert note_off.type == "note_off"
    assert note_off.note == 60


def test_play_chord():
    """Test play_chord sends multiple note_ons then note_offs"""
    mock_output.clear()
    server.output_port = mock_output

    result = asyncio.run(server.play_chord(notes=[60, 64, 67], velocity=80, duration=0.01, channel=1))

    assert "chord" in result.lower()

    # 3 note_ons + 3 note_offs = 6 messages
    assert len(mock_output.messages) == 6

    note_ons = [m for m in mock_output.messages if m.type == "note_on"]
    note_offs = [m for m in mock_output.messages if m.type == "note_off"]
    assert len(note_ons) == 3
    assert len(note_offs) == 3

    on_notes = sorted([m.note for m in note_ons])
    assert on_notes == [60, 64, 67]

    for m in note_ons:
        assert m.velocity == 80
        assert m.channel == 0


def test_send_cc():
    """Test send_cc produces correct CC message"""
    mock_output.clear()
    server.output_port = mock_output

    result = server.send_cc(cc_number=90, value=3, channel=1)

    assert "CC 90" in result
    assert len(mock_output.messages) == 1

    cc = mock_output.messages[0]
    assert cc.type == "control_change"
    assert cc.control == 90
    assert cc.value == 3
    assert cc.channel == 0


def test_send_nrpn():
    """Test send_nrpn sends 4 CC messages"""
    mock_output.clear()
    server.output_port = mock_output

    result = server.send_nrpn(msb=1, lsb=72, value=5, channel=1)

    assert "NRPN 1:72" in result
    assert len(mock_output.messages) == 4

    assert mock_output.messages[0].control == 99
    assert mock_output.messages[0].value == 1
    assert mock_output.messages[1].control == 98
    assert mock_output.messages[1].value == 72
    assert mock_output.messages[2].control == 6
    assert mock_output.messages[2].value == 5
    assert mock_output.messages[3].control == 38


def test_send_nrpn_14bit():
    """Test send_nrpn with 14-bit values (for ratio offsets)"""
    mock_output.clear()
    server.output_port = mock_output

    # Value 1000: MSB = 7 (1000 >> 7 = 7), LSB = 104 (1000 & 127 = 104)
    result = server.send_nrpn(msb=1, lsb=95, value=1000, channel=1)

    assert "NRPN 1:95" in result
    data_msb = mock_output.messages[2].value
    data_lsb = mock_output.messages[3].value
    assert data_msb == 7  # 1000 >> 7
    assert data_lsb == 104  # 1000 & 127


def test_transport_messages():
    """Test transport messages"""
    mock_output.clear()
    server.output_port = mock_output

    server.send_midi_start()
    server.send_midi_stop()
    server.send_midi_continue()

    assert len(mock_output.messages) == 3
    assert mock_output.messages[0].type == "start"
    assert mock_output.messages[1].type == "stop"
    assert mock_output.messages[2].type == "continue"


def test_set_algorithm():
    """Test set_algorithm sends correct CC"""
    mock_output.clear()
    server.output_port = mock_output

    result = server.set_algorithm(algorithm=3, channel=1)

    assert "algorithm 3" in result.lower()
    assert len(mock_output.messages) == 1

    cc = mock_output.messages[0]
    assert cc.type == "control_change"
    assert cc.control == 90  # Syn1CC.ALGORITHM
    assert cc.value == 2  # 0-indexed
    assert cc.channel == 0


def test_set_algorithm_bounds():
    """Test algorithm validation"""
    server.output_port = mock_output

    result = server.set_algorithm(algorithm=0, channel=1)
    assert "Error" in result

    result = server.set_algorithm(algorithm=9, channel=1)
    assert "Error" in result


def test_set_ratios():
    """Test set_ratios sends correct CCs"""
    mock_output.clear()
    server.output_port = mock_output

    result = server.set_ratios(ratio_c=64, ratio_a=32, ratio_b=16, channel=2)

    assert "C=64" in result
    assert "A=32" in result
    assert "B=16" in result
    assert len(mock_output.messages) == 3

    # CC 91 = Ratio C, CC 92 = Ratio A, CC 16 = Ratio B MSB
    ccs = [m.control for m in mock_output.messages]
    assert 91 in ccs
    assert 92 in ccs
    assert 16 in ccs

    for m in mock_output.messages:
        assert m.channel == 1  # channel 2 = 0-indexed 1


def test_set_operator_levels():
    """Test set_operator_levels sends correct CCs"""
    mock_output.clear()
    server.output_port = mock_output

    result = server.set_operator_levels(a_level=100, b_level=50, channel=1)

    assert "A=100" in result
    assert "B=50" in result
    assert len(mock_output.messages) == 2

    # CC 78 = A Level, CC 82 = B Level
    assert mock_output.messages[0].control == 78
    assert mock_output.messages[0].value == 100
    assert mock_output.messages[1].control == 82
    assert mock_output.messages[1].value == 50


def test_set_operator_envelope():
    """Test set_operator_envelope for A and B"""
    mock_output.clear()
    server.output_port = mock_output

    result = server.set_operator_envelope(operator="A", attack=30, decay=50, end=20, level=100, channel=1)

    assert "operator A" in result
    assert len(mock_output.messages) == 4

    # CC 75=A Attack, 76=A Decay, 77=A End, 78=A Level
    ccs = {m.control: m.value for m in mock_output.messages}
    assert ccs[75] == 30
    assert ccs[76] == 50
    assert ccs[77] == 20
    assert ccs[78] == 100

    # Test B envelope
    mock_output.clear()
    result = server.set_operator_envelope(operator="B", attack=10, level=80, channel=1)

    assert "operator B" in result
    ccs = {m.control: m.value for m in mock_output.messages}
    assert ccs[79] == 10  # B Attack
    assert ccs[82] == 80  # B Level


def test_set_chorus():
    """Test set_chorus sends CCs on FX channel"""
    mock_output.clear()
    server.output_port = mock_output

    result = server.set_chorus(depth=64, speed=32, mix=100, channel=9)

    assert "chorus" in result.lower()
    assert len(mock_output.messages) == 3

    for m in mock_output.messages:
        assert m.channel == 8  # channel 9 = 0-indexed 8


def test_list_parameters():
    """Test list_parameters returns Digitone parameters"""
    result = server.list_parameters()

    assert "parameters" in result.lower()
    assert "FM Synthesis" in result
    assert "Operator Envelopes" in result
    assert "Chorus" in result


def test_list_parameters_by_category():
    """Test filtering by category"""
    result = server.list_parameters(category="FM Synthesis (SYN1)")
    assert "fm_algorithm" in result
    assert "fm_ratio_c" in result


def test_set_parameter():
    """Test set_parameter with named parameters"""
    mock_output.clear()
    server.output_port = mock_output

    result = server.set_parameter(name="fm_feedback", value=64, channel=1)
    assert "fm_feedback" in result
    assert "64" in result

    cc = mock_output.messages[0]
    assert cc.control == 19  # Syn1CC.FEEDBACK_MSB
    assert cc.value == 64


def test_pattern_save_load():
    """Test pattern save and load"""
    import tempfile

    original_dir = server.PATTERN_DIR
    with tempfile.TemporaryDirectory() as tmpdir:
        server.PATTERN_DIR = Path(tmpdir)

        result = server.save_pattern(
            pattern_name="test_dn",
            bpm=125,
            bars=4,
            midi_channels={"1": [[0, 60, 100, 0.5]]},
            description="Test Digitone pattern",
        )

        assert "Saved pattern" in result
        assert (server.PATTERN_DIR / "test_dn.json").exists()

        result = server.load_pattern(pattern_name="test_dn")
        assert "test_dn" in result
        assert "125" in result

        result = server.list_patterns()
        assert "test_dn" in result

        result = server.delete_pattern(pattern_name="test_dn")
        assert "Deleted" in result

        server.PATTERN_DIR = original_dir


def test_play_with_clock():
    """Test play_with_clock sends correct pulses"""
    mock_output.clear()
    server.output_port = mock_output

    result = asyncio.run(server.play_with_clock(bars=1, bpm=120, send_start=True, send_stop=True))

    assert "1 bars" in result

    msg_types = mock_output.get_message_types()
    assert msg_types[0] == "start"
    assert msg_types[-1] == "stop"
    assert msg_types.count("clock") == 96


def test_resources():
    """Test resource functions"""
    setup_mocks()  # Re-setup in case another test file overrode mido mocks
    ports = server.get_midi_ports()
    assert "Elektron Digitone" in ports

    status = server.get_digitone_status()
    assert "Connected" in status


def test_check_connection_error():
    """Test error when not connected"""
    server.output_port = None
    result = server.send_cc(cc_number=90, value=3)
    assert "Error" in result
    assert "Not connected" in result
    server.output_port = mock_output


def test_note_sequence():
    """Test send_note_sequence"""
    mock_output.clear()
    server.output_port = mock_output

    notes = [[60, 100, 0.01], [62, 100, 0.01]]
    result = asyncio.run(server.send_note_sequence(notes=notes, delay=0.01, channel=1))

    assert "2 notes" in result
    assert len(mock_output.messages) == 4  # on, off, on, off


def test_parameter_map_categories():
    """Test parameter_map_digitone has expected categories"""
    from parameter_map_digitone import get_parameters_by_category

    cats = get_parameters_by_category()
    assert "FM Synthesis (SYN1)" in cats
    assert "Operator Envelopes (SYN2)" in cats
    assert "Filter" in cats
    assert "Amp" in cats
    assert "LFO 1" in cats
    assert "LFO 2" in cats
    assert "Chorus FX" in cats
    assert "Delay FX" in cats
    assert "Reverb FX" in cats


def test_parameter_map_fm_params():
    """Test FM-specific parameters exist"""
    from parameter_map_digitone import get_parameter_info

    assert get_parameter_info("fm_algorithm") is not None
    assert get_parameter_info("fm_ratio_c") is not None
    assert get_parameter_info("fm_feedback") is not None
    assert get_parameter_info("fm_mix") is not None
    assert get_parameter_info("op_a_level") is not None
    assert get_parameter_info("op_b_level") is not None

    alg = get_parameter_info("fm_algorithm")
    assert alg["cc"] == 90
    assert alg["range"] == (0, 7)


def test_nrpn_constants():
    """Test NRPN constant lookups"""
    from nrpn_constants_digitone import get_param_name

    assert get_param_name(1, 72) == "Algorithm"
    assert get_param_name(1, 73) == "Ratio C"
    assert get_param_name(1, 83) == "A Level"
    assert get_param_name(2, 0) == "Chorus Depth"
    assert get_param_name(2, 10) == "Delay Time"
    assert get_param_name(2, 20) == "Reverb Predelay"
    assert "Unknown" in get_param_name(99, 99)
