"""Strict notation and compact arrangement behavior."""

from fractions import Fraction

import pytest

from elektron_mcp.devices.digitakt import SPEC as DIGITAKT
from elektron_mcp.devices.digitone import SPEC as DIGITONE
from elektron_mcp.pattern_language import (
    HOLD,
    NOTE_OFF,
    NOTE_ON,
    NotationError,
    compile_pattern,
    expand_arrangement,
    layer,
    parse_arrangement,
    parse_pattern,
)


def test_digitakt_aliases_and_step_symbols_are_strict():
    pattern = parse_pattern("kick: xXo1 9x-. |x--.", DIGITAKT)
    track = pattern.tracks[0]

    assert (track.target.label, track.target.channel, track.target.note) == ("t1", 1, 0)
    assert track.steps == [100, 127, 50, 14, 127, 100, HOLD, None, 100, HOLD, HOLD, None]


def test_digitone_pitched_tracks_cycle_notes_and_chords():
    pattern = parse_pattern("bass: x.x.x.\nbass notes: C2 G1+D2", DIGITONE)
    note_ons = [event for event in compile_pattern(pattern) if event.kind == NOTE_ON]

    assert [(event.beat, event.note, event.channel) for event in note_ons] == [
        (0, 36, 1),
        (Fraction(1, 2), 31, 1),
        (Fraction(1, 2), 38, 1),
        (1, 36, 1),
    ]


def test_parser_returns_all_useful_line_errors():
    with pytest.raises(NotationError) as caught:
        parse_pattern("kick: -..q\nunknown: x...", DIGITAKT)

    messages = [str(issue) for issue in caught.value.issues]
    assert "line 1, col 7: '-' (hold) must follow a hit or another '-'" in messages
    assert "line 1, col 10: unknown step 'q'" in messages[1]
    assert "line 2: unknown track 'unknown'" in messages[2]


def test_short_tracks_repeat_and_mismatched_tracks_fail():
    pattern = parse_pattern("kick: x...x...x...x...\nhat: x.", DIGITAKT)
    assert pattern.length == 16
    assert len([event for event in compile_pattern(pattern) if event.kind == NOTE_ON and event.note == 5]) == 8

    with pytest.raises(NotationError, match="does not divide"):
        parse_pattern("kick: x...x...\nhat: x.x.x.", DIGITAKT)


def test_holds_extend_notes_and_note_off_precedes_retrigger():
    events = compile_pattern(parse_pattern("kick: x-x", DIGITAKT))

    assert [event.kind for event in events if event.beat == Fraction(1, 2)] == [NOTE_OFF, NOTE_ON]


def test_swing_moves_every_second_step():
    events = compile_pattern(parse_pattern("@swing 66\nhat: xxxx", DIGITAKT))
    starts = [event.beat for event in events if event.kind == NOTE_ON]

    step = Fraction(1, 4)
    assert starts == [0, step + step * Fraction(16, 50), 2 * step, 3 * step + step * Fraction(16, 50)]


def test_compact_arrangements_repeat_and_layer_patterns():
    parts = parse_arrangement("intro x2, verse+bass x4, outro")
    assert [(part.names, part.repeat) for part in parts] == [
        (["intro"], 2),
        (["verse", "bass"], 4),
        (["outro"], 1),
    ]

    patterns = {
        "verse": parse_pattern("kick: x...x...", DIGITAKT),
        "bass": parse_pattern("@map bass = ch11\nbass: x...\nbass notes: C1", DIGITAKT),
    }
    sections = expand_arrangement("verse+bass x2", patterns.get)

    assert [section.label for section in sections] == ["verse+bass", "verse+bass"]
    assert sections[0].length_beats == 2


def test_layering_refuses_patterns_that_do_not_fit_evenly():
    four = parse_pattern("kick: x...", DIGITAKT)
    three = parse_pattern("hat: x.x", DIGITAKT)

    with pytest.raises(NotationError, match="does not divide"):
        layer([("four", four), ("three", three)])
