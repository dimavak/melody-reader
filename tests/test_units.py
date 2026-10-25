"""Fast tests that do not run homr. Run with: python -m pytest tests"""

import os
import tempfile

from melody_reader import checks, export, site, song
from melody_reader.omr import Notehead


def _note(pitch, dur, **kw):
    n = {"pitch": pitch, "dur": dur, "dots": 0, "tie": None, "fermata": False, "grace": False, "x": 10.0, "y": 10.0}
    n.update(kw)
    return n


def _song(measures, time="2/4"):
    return {
        "id": "t",
        "key": 0,
        "time": time,
        "clef": "G2",
        "systems": [{"lines": [10, 20, 30, 40, 50], "x0": 0, "x1": 300, "unit": 10}],
        "measures": [
            {"index": i + 1, "time": None, "notes": notes, "flags": [], "system": 0, "box": [0, 0, 100, 60]}
            for i, notes in enumerate(measures)
        ],
    }


def test_align_skips_extra_noteheads():
    heads = [Notehead(10, 0, 4), Notehead(20, 0, 9), Notehead(30, 0, 6)]
    # expected positions: A4=4, C5=6; the head at position 9 is noise
    assert song._align([4, 6], heads) == [0, 2]


def test_diatonic_positions_for_treble_clef():
    bottom = song.BOTTOM_LINE["G2"]
    assert song.diatonic("E4") - bottom + 1 == 1  # bottom line
    assert song.diatonic("F5") - bottom + 1 == 9  # top line
    assert song.diatonic("F#4") == song.diatonic("F4")


def test_compare_flags_only_different_bars():
    a = _song([[_note("A4", 1), _note("B4", 1)], [_note("C5", 2)]])
    b = _song([[_note("A4", 1), _note("B4", 1)], [_note("C5", 1.5), _note("D5", 0.5)]])
    checks.compare(a, b)
    assert a["measures"][0]["flags"] == []
    assert a["measures"][1]["flags"] == ["disagree"]
    assert [n["pitch"] for n in a["measures"][1]["alt"]] == ["C5", "D5"]


def test_compare_handles_a_missing_bar():
    a = _song([[_note("A4", 2)], [_note("B4", 2)], [_note("C5", 2)]])
    b = _song([[_note("A4", 2)], [_note("C5", 2)]])
    checks.compare(a, b)
    assert [m["flags"] for m in a["measures"]] == [[], ["disagree"], []]


def test_rules_bar_length_and_fermata_dot():
    s = _song(
        [
            [_note("A4", 1)],  # pickup: allowed short
            [_note("A4", 1), _note("B4", 1.5, dots=1, fermata=True)],  # too long + fermata over dot
            [_note("C5", 1)],  # short inside the song
            [_note("A4", 1)],  # last bar: allowed short
        ]
    )
    checks.apply_rules(s)
    assert [m["flags"] for m in s["measures"]] == [[], ["duration", "fermata-dot"], ["duration"], []]


def test_export_round_trip():
    s = _song([[_note("F#4", 0.5), _note("Bb4", 0.5), _note(None, 1)], [_note("C5", 2, fermata=True)]])
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "x.musicxml")
        export.to_musicxml(s, path)
        import music21 as m21

        notes = list(m21.converter.parse(path).flatten().notesAndRests)
    assert [n.name if n.isNote else "rest" for n in notes] == ["F#", "B-", "rest", "C"]
    assert notes[-1].expressions and notes[-1].quarterLength == 2


def test_repeat_signs_survive_export_and_reading_back():
    s = _song([[_note("A4", 2)], [_note("C5", 2)], [_note("D5", 2)]])
    s["measures"][1]["repeat_start"] = True
    s["measures"][1]["repeat_end"] = True
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "x.musicxml")
        export.to_musicxml(s, path)
        import music21 as m21

        bars = list(m21.converter.parse(path).parts[0].getElementsByClass(m21.stream.Measure))
    assert [song._repeats(b) for b in bars] == [{}, {"repeat_start": True, "repeat_end": True}, {}]


def test_short_last_bar_is_flagged_without_a_pickup():
    s = _song([[_note("A4", 2)], [_note("B4", 2)], [_note("G4", 1.5)]])
    checks.apply_rules(s)
    assert [m["flags"] for m in s["measures"]] == [[], [], ["duration"]]


def test_vote_picks_the_reading_the_third_run_agrees_with():
    a = _song([[_note("A4", 2)], [_note("C5", 2)], [_note("D5", 2)]])
    b = _song([[_note("A4", 2)], [_note("C5", 1), _note("C5", 1)], [_note("E5", 2)]])
    third = _song([[_note("A4", 2)], [_note("C5", 1), _note("C5", 1)], [_note("F5", 2)]])
    third["engine"] = {"variant": "3x"}
    checks.compare(a, b)
    checks.vote(a, third)
    assert "vote" not in a["measures"][0]
    assert a["measures"][1]["vote"] == {"choice": "B", "source": "3x"}
    assert a["measures"][2]["vote"] == {"choice": "unknown", "source": "3x"}


def _site_song(measures):
    s = _song(measures)
    s["source"] = {"file": "scans/t.png", "width": 300, "height": 100}
    for m in s["measures"]:
        for n in m["notes"]:
            n["system"] = 0
    return s


def test_site_entry_merges_ties_marks_fermatas_and_doubtful_bars():
    s = _site_song(
        [
            [_note("F#4", 1, tie="start", x=30.0), _note("F#4", 1, tie="stop", x=60.0)],
            [_note("Bb4", 1.5, fermata=True, x=90.0), _note(None, 0.5, x=120.0)],
        ]
    )
    s["measures"][1]["flags"] = ["duration"]
    e = site.entry(s)
    assert e["ev"] == [[66, 2.0, 0.1, 0.1, 0, 0], [70, 1.5, 0.3, 0.1, 0, 6], [-1, 0.5, 0.4, 0.1, 0, 4]]
    assert e["st"] == [[0.0, 1.0, 0.1, 0.5]] and "seq" not in e


def test_site_repeats_play_the_bars_twice():
    s = _site_song([[_note("A4", 2)], [_note("C5", 2)], [_note("D5", 1), _note("E5", 1)]])
    s["measures"][1]["repeat_start"] = True
    s["measures"][2]["repeat_end"] = True
    assert site.entry(s)["seq"] == [0, 1, 2, 3, 1, 2, 3]


def test_site_merge_keeps_old_repeats_and_old_entry_when_nothing_is_read():
    old = {
        "ev": [[69, 1, 0.1, 0.1, 0, 0], [72, 1, 0.5, 0.1, 0, 0], [74, 1, 0.9, 0.1, 0, 0]],
        "st": [],
        "seq": [0, 1, 2, 1, 2],
    }
    s = _site_song([[_note("A4", 1, x=30.0), _note("B4", 1, x=60.0)], [_note("C5", 1, x=150.0), _note("D5", 1, x=270.0)]])
    assert site.merge(old, s)["seq"] == [0, 1, 2, 3, 2, 3]
    s["measures"][1]["repeat_end"] = True
    assert "seq" not in site.merge(None, s)
    assert site.merge(old, _site_song([[_note(None, 2)]])) is old
