#!/usr/bin/env python3
"""
Unit tests for FastMCP migration.
Tests that the new FastMCP server produces correct MIDI messages without requiring hardware.
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
        self.name = "Mock Digitakt"

    def send(self, msg):
        self.messages.append(msg)

    def clear(self):
        self.messages = []

    def get_message_types(self):
        return [m.type for m in self.messages]


# Create mock port before importing server
mock_output = MockMidiPort()
mock_input = MagicMock()
mock_input.iter_pending = MagicMock(return_value=iter([]))


def setup_mocks():
    """Patch mido and set up mock ports"""
    import mido

    # Patch get_output_names and get_input_names
    mido.get_output_names = MagicMock(return_value=["Elektron Digitakt"])
    mido.get_input_names = MagicMock(return_value=["Elektron Digitakt"])
    mido.open_output = MagicMock(return_value=mock_output)
    mido.open_input = MagicMock(return_value=mock_input)


setup_mocks()

# Now import the server module
import server_fastmcp as server


def test_send_note():
    """Test send_note produces correct MIDI messages"""
    mock_output.clear()
    server.output_port = mock_output

    result = asyncio.run(server.send_note(note=60, velocity=100, duration=0.01, channel=1))

    assert "Sent note 60" in result
    assert len(mock_output.messages) == 2

    note_on = mock_output.messages[0]
    assert note_on.type == "note_on"
    assert note_on.note == 60
    assert note_on.velocity == 100
    assert note_on.channel == 0  # 0-indexed

    note_off = mock_output.messages[1]
    assert note_off.type == "note_off"
    assert note_off.note == 60

    print("✓ test_send_note passed")


def test_trigger_track():
    """Test trigger_track converts track number to correct note"""
    mock_output.clear()
    server.output_port = mock_output

    result = asyncio.run(server.trigger_track(track=3, velocity=80, duration=0.01, channel=1))

    assert "Track 3" in result
    note_on = mock_output.messages[0]
    assert note_on.note == 2  # Track 3 = note 2 (0-indexed)
    assert note_on.velocity == 80

    print("✓ test_trigger_track passed")


def test_send_cc():
    """Test send_cc produces correct CC message"""
    mock_output.clear()
    server.output_port = mock_output

    result = server.send_cc(cc_number=74, value=100, channel=2)

    assert "CC 74" in result
    assert len(mock_output.messages) == 1

    cc = mock_output.messages[0]
    assert cc.type == "control_change"
    assert cc.control == 74
    assert cc.value == 100
    assert cc.channel == 1  # 0-indexed

    print("✓ test_send_cc passed")


def test_send_nrpn():
    """Test send_nrpn produces correct 4-message sequence"""
    mock_output.clear()
    server.output_port = mock_output

    result = server.send_nrpn(msb=1, lsb=5, value=64, channel=1)

    assert "NRPN 1:5" in result
    assert len(mock_output.messages) == 4

    # Check NRPN sequence: CC99, CC98, CC6, CC38
    assert mock_output.messages[0].control == 99
    assert mock_output.messages[0].value == 1  # MSB
    assert mock_output.messages[1].control == 98
    assert mock_output.messages[1].value == 5  # LSB
    assert mock_output.messages[2].control == 6
    assert mock_output.messages[2].value == 64  # Data
    assert mock_output.messages[3].control == 38

    print("✓ test_send_nrpn passed")


def test_transport_messages():
    """Test transport messages (start, stop, continue)"""
    mock_output.clear()
    server.output_port = mock_output

    server.send_midi_start()
    server.send_midi_stop()
    server.send_midi_continue()

    assert len(mock_output.messages) == 3
    assert mock_output.messages[0].type == "start"
    assert mock_output.messages[1].type == "stop"
    assert mock_output.messages[2].type == "continue"

    print("✓ test_transport_messages passed")


def test_program_change():
    """Test program change message"""
    mock_output.clear()
    server.output_port = mock_output

    result = server.send_program_change(program=42, channel=1)

    assert "42" in result
    pc = mock_output.messages[0]
    assert pc.type == "program_change"
    assert pc.program == 42

    print("✓ test_program_change passed")


def test_trig_note():
    """Test set_trig_note sends correct NRPN"""
    mock_output.clear()
    server.output_port = mock_output

    result = server.set_trig_note(track=1, step=5, note=60, channel=1)

    assert "Step 5" in result
    # Should be 4 CC messages for NRPN
    assert len(mock_output.messages) == 4
    # MSB=3 for trig note, LSB=step-1
    assert mock_output.messages[0].value == 3  # MSB
    assert mock_output.messages[1].value == 4  # LSB (step 5 = index 4)

    print("✓ test_trig_note passed")


def test_play_with_clock():
    """Test play_with_clock sends correct number of clock pulses"""
    mock_output.clear()
    server.output_port = mock_output

    # Play 1 bar at 120 BPM (should be quick)
    result = asyncio.run(server.play_with_clock(bars=1, bpm=120, send_start=True, send_stop=True))

    assert "1 bars" in result

    # Should have: 1 start + 96 clocks + 1 stop = 98 messages
    msg_types = mock_output.get_message_types()
    assert msg_types[0] == "start"
    assert msg_types[-1] == "stop"
    assert msg_types.count("clock") == 96

    print("✓ test_play_with_clock passed")


def test_pattern_save_load():
    """Test pattern save and load"""
    import tempfile

    # Temporarily redirect pattern dir
    original_dir = server.PATTERN_DIR
    with tempfile.TemporaryDirectory() as tmpdir:
        server.PATTERN_DIR = Path(tmpdir)

        # Save a pattern
        result = server.save_pattern(
            pattern_name="test_pattern",
            bpm=120,
            bars=4,
            track_triggers=[[0, 1, 100], [1, 2, 80]],
            midi_channels={"9": [[0, 60, 100, 0.5]]},
            description="Test pattern",
        )

        assert "Saved pattern" in result
        assert (server.PATTERN_DIR / "test_pattern.json").exists()

        # Load it back
        result = server.load_pattern(pattern_name="test_pattern", play=False)

        assert "test_pattern" in result
        assert "120" in result  # BPM

        # List patterns
        result = server.list_patterns()
        assert "test_pattern" in result

        # Delete pattern
        result = server.delete_pattern(pattern_name="test_pattern")
        assert "Deleted" in result
        assert not (server.PATTERN_DIR / "test_pattern.json").exists()

        server.PATTERN_DIR = original_dir

    print("✓ test_pattern_save_load passed")


def test_list_parameters():
    """Test list_parameters returns parameter info"""
    result = server.list_parameters()

    # Should contain some known parameters
    assert "parameters" in result.lower()
    assert "filter" in result.lower() or "Filter" in result

    print("✓ test_list_parameters passed")


def test_resources():
    """Test resource functions"""
    ports = server.get_midi_ports()
    assert "Elektron Digitakt" in ports

    status = server.get_digitakt_status()
    assert "Connected" in status

    print("✓ test_resources passed")


def test_note_sequence():
    """Test send_note_sequence"""
    mock_output.clear()
    server.output_port = mock_output

    notes = [[60, 100, 0.01], [62, 100, 0.01]]
    result = asyncio.run(server.send_note_sequence(notes=notes, delay=0.01, channel=1))

    assert "2 notes" in result
    # Should have 4 messages: on, off, on, off
    assert len(mock_output.messages) == 4

    print("✓ test_note_sequence passed")


def test_check_connection_error():
    """Test that tools return error when not connected"""
    server.output_port = None

    result = server.send_cc(cc_number=74, value=100)
    assert "Error" in result
    assert "Not connected" in result

    # Restore mock
    server.output_port = mock_output

    print("✓ test_check_connection_error passed")


def run_all_tests():
    """Run all tests"""
    print("\n" + "=" * 60)
    print("FastMCP Migration Tests")
    print("=" * 60 + "\n")

    tests = [
        test_send_note,
        test_trigger_track,
        test_send_cc,
        test_send_nrpn,
        test_transport_messages,
        test_program_change,
        test_trig_note,
        test_play_with_clock,
        test_pattern_save_load,
        test_list_parameters,
        test_resources,
        test_note_sequence,
        test_check_connection_error,
    ]

    passed = 0
    failed = 0

    for test in tests:
        try:
            test()
            passed += 1
        except AssertionError as e:
            print(f"✗ {test.__name__} FAILED: {e}")
            failed += 1
        except Exception as e:
            print(f"✗ {test.__name__} ERROR: {e}")
            failed += 1

    print("\n" + "=" * 60)
    print(f"Results: {passed} passed, {failed} failed")
    print("=" * 60)

    return failed == 0


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)
