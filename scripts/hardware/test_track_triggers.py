#!/usr/bin/env python3
"""
Test script to verify track triggering on Digitakt
Sends MIDI notes 0-7 to trigger tracks 1-8
"""

import time

import mido


def test_track_triggers():
    """Test triggering each track individually"""

    # Find Digitakt output port
    output_port = None
    for port_name in mido.get_output_names():
        if "Elektron Digitakt" in port_name:
            output_port = mido.open_output(port_name)
            print(f"✓ Connected to MIDI output: {port_name}")
            break

    if not output_port:
        print("✗ Could not find Digitakt MIDI output port")
        return False

    try:
        print("\nTesting track triggers (MIDI notes 0-7)...")
        print("Make sure your Digitakt has samples loaded on tracks 1-8!")
        print()

        # Test each track (Digitakt 1 has 8 audio tracks)
        for track in range(1, 9):
            note = track - 1  # Track 1 = note 0, Track 2 = note 1, etc.

            print(f"Triggering Track {track} (MIDI note {note})...")

            # Send note on
            note_on = mido.Message("note_on", note=note, velocity=100)
            output_port.send(note_on)

            time.sleep(0.05)

            # Send note off
            note_off = mido.Message("note_off", note=note)
            output_port.send(note_off)

            time.sleep(0.3)  # Wait between triggers

        print("\n✓ Test complete!")
        print("\nDid you hear all 8 tracks trigger?")
        print("If not, check:")
        print("  - Tracks have samples loaded")
        print("  - Track MIDI channels are set correctly (or use AUTO CHANNEL)")
        print("  - Digitakt volume is up")

        return True

    except Exception as e:
        print(f"✗ Error: {e}")
        return False

    finally:
        output_port.close()
        print("\nMIDI port closed.")


if __name__ == "__main__":
    print("Digitakt Track Trigger Test")
    print("=" * 60)
    test_track_triggers()
