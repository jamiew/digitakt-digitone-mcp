#!/usr/bin/env python3
"""
Hip-hop beat playback script for Digitakt + Digitone setup.

Usage:
    uv run python play_hiphop.py                    # Everything
    uv run python play_hiphop.py --drums            # Drums only
    uv run python play_hiphop.py --chords           # Chords only
    uv run python play_hiphop.py --bass             # Bass only
    uv run python play_hiphop.py --lead             # Lead only
    uv run python play_hiphop.py --chords --bass    # Combine any
    uv run python play_hiphop.py --synths           # All synths (no drums)
    uv run python play_hiphop.py --loops 16         # Number of 8-bar loops (default: 8)
    uv run python play_hiphop.py --bpm 100          # Tempo (default: 90)
"""

import argparse
import mido
from mido import MidiFile, MidiTrack, Message, MetaMessage
import time

# Channel mapping (0-indexed)
# Digitakt audio tracks 1-8 = channels 0-7
# Digitone via MIDI tracks: ch9=chords, ch11=bass, ch13=lead
CH_CHORDS = 8   # Channel 9
CH_BASS = 10    # Channel 11
CH_LEAD = 12    # Channel 13

# Drum tracks
KICK, SNARE, TOM, CLAP, COWBELL, HIHAT, OPEN_HAT, CYMBAL = 1, 2, 3, 4, 5, 6, 7, 8

# Chord voicings
Am7 =   [57, 60, 64, 67]
Fmaj7 = [53, 57, 60, 64]
Dm9 =   [50, 57, 60, 64, 66]
E7 =    [52, 56, 59, 62]

CHORD_PROG = [Am7, Am7, Fmaj7, Fmaj7, Dm9, Dm9, E7, E7]
CHORD_NAMES = ['Am7', 'Am7', 'Fmaj7', 'Fmaj7', 'Dm9', 'Dm9', 'E7', 'E7']
BASS_ROOTS = [57, 57, 53, 53, 50, 50, 52, 52]  # A3, A3, F3, F3, D3, D3, E3, E3 (2 octaves up)

# Bass pattern: step -> (interval, velocity)
BASS_PATTERN = {0: (0, 100), 6: (0, 70), 10: (12, 85), 13: (7, 55)}

# Lead phrases: bar -> [(step, note, velocity, length), ...]
LEAD_PHRASES = {
    0: [(4, 72, 75, 2), (10, 69, 70, 2)],
    2: [(2, 65, 75, 3), (10, 69, 80, 2)],
    4: [(0, 74, 80, 2), (6, 72, 70, 2)],
    6: [(2, 67, 75, 2), (8, 64, 70, 2), (12, 67, 80, 3)],
}


def get_drum_hits(step):
    """Get drum hits for a given step (0-15)."""
    hits = []
    # Kick
    if step in [0, 7, 10]:
        hits.append((KICK, 120 if step == 0 else 100))
    # Snare + clap
    if step in [4, 12]:
        hits.append((SNARE, 110))
        hits.append((CLAP, 75))
    # Closed hi-hat
    if step in [0, 2, 4, 6, 8, 10, 12, 14]:
        vel = 75 if step % 4 == 0 else 50
        hits.append((HIHAT, vel))
    # Ghost hats
    if step in [3, 7, 11, 15]:
        hits.append((HIHAT, 30))
    # Open hat
    if step in [3, 11]:
        hits.append((OPEN_HAT, 65))
    return hits


def play(port, bpm=90, loops=8, drums=True, chords=True, bass=True, lead=True):
    """Play the hip-hop pattern."""
    sixteenth = 60.0 / bpm / 4

    current_chord = None
    active_bass = None

    parts = []
    if drums: parts.append("Drums")
    if chords: parts.append("Chords")
    if bass: parts.append("Bass")
    if lead: parts.append("Lead")

    print(f"Playing {loops} loops at {bpm} BPM")
    print(f"Parts: {', '.join(parts)}")
    print()

    def note_on(note, vel, ch):
        port.send(mido.Message('note_on', note=note, velocity=vel, channel=ch))

    def note_off(note, ch):
        port.send(mido.Message('note_off', note=note, velocity=0, channel=ch))

    def trigger(track, velocity):
        port.send(mido.Message('note_on', note=track-1, velocity=velocity, channel=track-1))

    def release(track):
        port.send(mido.Message('note_off', note=track-1, velocity=0, channel=track-1))

    try:
        for loop in range(loops):
            print(f"Loop {loop + 1}/{loops}")

            for bar in range(8):
                chord_notes = CHORD_PROG[bar]
                bass_root = BASS_ROOTS[bar]

                for step in range(16):
                    # Chords (on beat 1)
                    if chords and step == 0:
                        if current_chord:
                            for n in current_chord:
                                note_off(n, CH_CHORDS)
                        for n in chord_notes:
                            note_on(n, 70, CH_CHORDS)
                        current_chord = chord_notes

                    # Bass
                    if bass and step in BASS_PATTERN:
                        if active_bass:
                            note_off(active_bass, CH_BASS)
                        rel, vel = BASS_PATTERN[step]
                        active_bass = bass_root + rel
                        note_on(active_bass, vel, CH_BASS)

                    # Lead
                    if lead and bar in LEAD_PHRASES:
                        for ls, lnote, lvel, llen in LEAD_PHRASES[bar]:
                            if ls == step:
                                note_on(lnote, lvel, CH_LEAD)
                            if step == ls + llen:
                                note_off(lnote, CH_LEAD)

                    # Drums
                    if drums:
                        for track, vel in get_drum_hits(step):
                            trigger(track, vel)

                    time.sleep(sixteenth * 0.85)

                    # Release drums
                    if drums:
                        for track, _ in get_drum_hits(step):
                            release(track)

                    time.sleep(sixteenth * 0.15)

    finally:
        # Cleanup
        if current_chord:
            for n in current_chord:
                note_off(n, CH_CHORDS)
        if active_bass:
            note_off(active_bass, CH_BASS)
        print("\nDone!")


def export_midi(filename, bpm=90, bars=8, drums=True, chords=True, bass=True, lead=True):
    """Export the pattern to a MIDI file."""
    ticks_per_beat = 480
    ticks_per_16th = ticks_per_beat // 4

    mid = MidiFile(ticks_per_beat=ticks_per_beat)

    # Create tracks
    if drums:
        drum_track = MidiTrack()
        mid.tracks.append(drum_track)
        drum_track.append(MetaMessage('track_name', name='Drums', time=0))
        drum_track.append(MetaMessage('set_tempo', tempo=mido.bpm2tempo(bpm), time=0))

    if chords:
        chord_track = MidiTrack()
        mid.tracks.append(chord_track)
        chord_track.append(MetaMessage('track_name', name='Chords', time=0))

    if bass:
        bass_track = MidiTrack()
        mid.tracks.append(bass_track)
        bass_track.append(MetaMessage('track_name', name='Bass', time=0))

    if lead:
        lead_track = MidiTrack()
        mid.tracks.append(lead_track)
        lead_track.append(MetaMessage('track_name', name='Lead', time=0))

    # Build events for each bar
    for bar in range(bars):
        chord_notes = CHORD_PROG[bar % 8]
        bass_root = BASS_ROOTS[bar % 8]

        for step in range(16):
            abs_tick = (bar * 16 + step) * ticks_per_16th

            # Drums
            if drums:
                for track_num, vel in get_drum_hits(step):
                    note = track_num - 1 + 36  # Map to GM drum notes (kick=36)
                    drum_track.append(Message('note_on', note=note, velocity=vel, channel=9, time=0))

            # Chords (on beat 1)
            if chords and step == 0:
                for n in chord_notes:
                    chord_track.append(Message('note_on', note=n, velocity=70, channel=CH_CHORDS, time=0))

            # Bass
            if bass and step in BASS_PATTERN:
                rel, vel = BASS_PATTERN[step]
                bass_note = bass_root + rel
                bass_track.append(Message('note_on', note=bass_note, velocity=vel, channel=CH_BASS, time=0))

            # Lead
            if lead and (bar % 8) in LEAD_PHRASES:
                for ls, lnote, lvel, llen in LEAD_PHRASES[bar % 8]:
                    if ls == step:
                        lead_track.append(Message('note_on', note=lnote, velocity=lvel, channel=CH_LEAD, time=0))

    # Convert absolute times to delta times and add note-offs
    def finalize_track(track, note_length_ticks=ticks_per_16th):
        events = []
        for msg in track:
            if isinstance(msg, MetaMessage):
                events.append((0, msg))
            else:
                events.append((msg.time, msg))

        # Sort and convert to delta
        final_track = MidiTrack()
        last_time = 0
        for abs_time, msg in sorted(events, key=lambda x: x[0]):
            delta = abs_time - last_time
            if isinstance(msg, MetaMessage):
                final_track.append(msg.copy(time=delta))
            else:
                final_track.append(msg.copy(time=delta))
            last_time = abs_time
        return final_track

    # Simpler approach: rebuild with proper timing
    mid2 = MidiFile(ticks_per_beat=ticks_per_beat)

    # Drum track
    if drums:
        dt = MidiTrack()
        mid2.tracks.append(dt)
        dt.append(MetaMessage('track_name', name='Drums', time=0))
        dt.append(MetaMessage('set_tempo', tempo=mido.bpm2tempo(bpm), time=0))

        time_cursor = 0
        for bar in range(bars):
            for step in range(16):
                hits = get_drum_hits(step)
                if hits:
                    dt.append(Message('note_on', note=36 + hits[0][0], velocity=hits[0][1], channel=9, time=time_cursor))
                    time_cursor = 0
                    for track_num, vel in hits[1:]:
                        dt.append(Message('note_on', note=36 + track_num, velocity=vel, channel=9, time=0))
                    # Note offs
                    dt.append(Message('note_off', note=36 + hits[0][0], velocity=0, channel=9, time=ticks_per_16th // 2))
                    for track_num, _ in hits[1:]:
                        dt.append(Message('note_off', note=36 + track_num, velocity=0, channel=9, time=0))
                    time_cursor = ticks_per_16th // 2
                else:
                    time_cursor += ticks_per_16th

    # Chord track
    if chords:
        ct = MidiTrack()
        mid2.tracks.append(ct)
        ct.append(MetaMessage('track_name', name='Chords', time=0))

        time_cursor = 0
        prev_chord = None
        for bar in range(bars):
            chord_notes = CHORD_PROG[bar % 8]
            # Note off previous chord
            if prev_chord and bar > 0:
                for i, n in enumerate(prev_chord):
                    ct.append(Message('note_off', note=n, velocity=0, channel=CH_CHORDS, time=0 if i > 0 else time_cursor))
                time_cursor = 0
            # Note on new chord
            for i, n in enumerate(chord_notes):
                ct.append(Message('note_on', note=n, velocity=70, channel=CH_CHORDS, time=0 if i > 0 else time_cursor))
            prev_chord = chord_notes
            time_cursor = 16 * ticks_per_16th  # One bar
        # Final note off
        if prev_chord:
            for i, n in enumerate(prev_chord):
                ct.append(Message('note_off', note=n, velocity=0, channel=CH_CHORDS, time=0 if i > 0 else time_cursor))

    # Bass track
    if bass:
        bt = MidiTrack()
        mid2.tracks.append(bt)
        bt.append(MetaMessage('track_name', name='Bass', time=0))

        time_cursor = 0
        for bar in range(bars):
            bass_root = BASS_ROOTS[bar % 8]
            for step in range(16):
                if step in BASS_PATTERN:
                    rel, vel = BASS_PATTERN[step]
                    bass_note = bass_root + rel
                    bt.append(Message('note_on', note=bass_note, velocity=vel, channel=CH_BASS, time=time_cursor))
                    bt.append(Message('note_off', note=bass_note, velocity=0, channel=CH_BASS, time=ticks_per_16th))
                    time_cursor = 0
                else:
                    time_cursor += ticks_per_16th

    # Lead track
    if lead:
        lt = MidiTrack()
        mid2.tracks.append(lt)
        lt.append(MetaMessage('track_name', name='Lead', time=0))

        # Collect all lead events
        events = []
        for bar in range(bars):
            bar_in_prog = bar % 8
            if bar_in_prog in LEAD_PHRASES:
                for ls, lnote, lvel, llen in LEAD_PHRASES[bar_in_prog]:
                    start_tick = (bar * 16 + ls) * ticks_per_16th
                    end_tick = start_tick + llen * ticks_per_16th
                    events.append((start_tick, 'on', lnote, lvel))
                    events.append((end_tick, 'off', lnote, 0))

        events.sort(key=lambda x: (x[0], x[1] == 'on'))  # offs before ons at same time
        last_tick = 0
        for tick, typ, note, vel in events:
            delta = tick - last_tick
            if typ == 'on':
                lt.append(Message('note_on', note=note, velocity=vel, channel=CH_LEAD, time=delta))
            else:
                lt.append(Message('note_off', note=note, velocity=0, channel=CH_LEAD, time=delta))
            last_tick = tick

    mid2.save(filename)
    print(f"Exported to {filename}")
    print(f"  {bars} bars at {bpm} BPM")
    parts = []
    if drums: parts.append("Drums")
    if chords: parts.append("Chords")
    if bass: parts.append("Bass")
    if lead: parts.append("Lead")
    print(f"  Parts: {', '.join(parts)}")


def main():
    parser = argparse.ArgumentParser(description="Play hip-hop beat on Digitakt + Digitone")
    parser.add_argument("--drums", action="store_true", help="Include drums")
    parser.add_argument("--chords", action="store_true", help="Include chords")
    parser.add_argument("--bass", action="store_true", help="Include bass")
    parser.add_argument("--lead", action="store_true", help="Include lead")
    parser.add_argument("--synths", action="store_true", help="All synths (chords + bass + lead)")
    parser.add_argument("--loops", type=int, default=8, help="Number of 8-bar loops (default: 8)")
    parser.add_argument("--bpm", type=int, default=90, help="Tempo (default: 90)")
    parser.add_argument("--export", type=str, metavar="FILE", help="Export to .mid file instead of playing")
    args = parser.parse_args()

    # Determine what to play
    any_specified = args.drums or args.chords or args.bass or args.lead or args.synths

    if not any_specified:
        # Nothing specified = play everything
        drums, chords, bass, lead = True, True, True, True
    else:
        drums = args.drums
        chords = args.chords or args.synths
        bass = args.bass or args.synths
        lead = args.lead or args.synths

    # Export mode
    if args.export:
        filename = args.export if args.export.endswith('.mid') else args.export + '.mid'
        export_midi(filename, bpm=args.bpm, bars=args.loops * 8, drums=drums, chords=chords, bass=bass, lead=lead)
        return

    # Connect to Digitakt
    port = None
    for port_name in mido.get_output_names():
        if "Elektron Digitakt" in port_name:
            port = mido.open_output(port_name)
            print(f"Connected to {port_name}")
            break

    if not port:
        print("Error: Could not find Digitakt MIDI port")
        return

    try:
        play(port, bpm=args.bpm, loops=args.loops, drums=drums, chords=chords, bass=bass, lead=lead)
    except KeyboardInterrupt:
        print("\nStopped by user")
    finally:
        port.close()


if __name__ == "__main__":
    main()
