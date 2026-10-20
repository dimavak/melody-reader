"""Fast tests that do not run homr. Run with: python -m pytest tests"""

import json
import os
import tempfile
from types import SimpleNamespace

from PIL import Image

from melody_reader import checks, export, llm, song
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


class _FakeMessages:
    def __init__(self, answer):
        self.answer = answer
        self.calls = []

    def create(self, **kw):
        self.calls.append(kw)
        return SimpleNamespace(stop_reason="end_turn", content=[SimpleNamespace(type="text", text=json.dumps(self.answer))])


def test_llm_check_only_asks_about_disagreeing_bars():
    s = _song([[_note("A4", 2)], [_note("B4", 2)]])
    s["measures"][1]["flags"] = ["disagree"]
    s["measures"][1]["alt"] = [_note("B4", 1), _note("C5", 1)]
    fake = _FakeMessages({"choice": "B", "reason": "two quarter notes"})
    client = SimpleNamespace(beta=SimpleNamespace(messages=fake))
    with tempfile.TemporaryDirectory() as tmp:
        img = os.path.join(tmp, "scan.png")
        Image.new("L", (300, 80), 255).save(img)
        assert llm.check_song(img, s, client=client) == 1
    assert s["measures"][1]["llm"] == {"choice": "B", "reason": "two quarter notes"}
    assert "llm" not in s["measures"][0]
    call = fake.calls[0]
    assert call["model"] == "claude-opus-5-5"
    assert call["messages"][0]["content"][0]["type"] == "image"
    assert "B4 1, C5 1" in call["messages"][0]["content"][1]["text"]


def test_short_last_bar_is_flagged_without_a_pickup():
    s = _song([[_note("A4", 2)], [_note("B4", 2)], [_note("G4", 1.5)]])
    checks.apply_rules(s)
    assert [m["flags"] for m in s["measures"]] == [[], [], ["duration"]]
