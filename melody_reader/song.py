"""Build the song JSON from a homr result.

The song JSON is the single source of truth: the editor reads and writes it,
MusicXML and melodies.js are generated from it. Coordinates are in pixels of
the original scan.
"""

from __future__ import annotations

import io
from fractions import Fraction

import music21 as m21

from melody_reader.omr import HomrResult, StaffInfo

SCHEMA_VERSION = 1
STEPS = "CDEFGAB"
# Diatonic number of the pitch on the bottom staff line, per clef
BOTTOM_LINE = {"G2": 4 * 7 + 2, "F4": 2 * 7 + 4, "C3": 3 * 7 + 3, "C4": 3 * 7 + 1}


def diatonic(pitch: str) -> int:
    """'F#4' -> 4*7 + 3. Accidentals do not change the staff position."""
    return int(pitch[-1]) * 7 + STEPS.index(pitch[0])


def _clef(symbols) -> str:
    for s in symbols:
        if s.rhythm.startswith("clef_"):
            return s.rhythm[5:]
    return "G2"


def _events_per_staff(symbols) -> list[tuple[int, str]]:
    """(staff index, 'note' | 'rest') for every note or rest, in reading order."""
    out: list[tuple[int, str]] = []
    staff = 0
    joined = False
    for s in symbols:
        if s.rhythm == "newline":
            staff += 1
        elif s.rhythm == "chord":
            joined = True
        elif s.rhythm.startswith(("note", "rest")):
            if joined:
                joined = False
                continue
            out.append((staff, "rest" if s.rhythm.startswith("rest") else "note"))
    return out


def _align(expected: list[int], heads: list) -> list[int | None]:
    """Match notes (expected staff positions, in order) to detected noteheads (sorted by x).

    Edit-distance alignment: a head at the expected position is free, one step off
    is cheap, anything else is expensive. Returns the head index for each note.
    """
    n, m = len(expected), len(heads)
    skip_note, skip_head = 1.0, 0.6
    cost = [[0.0] * (m + 1) for _ in range(n + 1)]
    for i in range(1, n + 1):
        cost[i][0] = i * skip_note
    for j in range(1, m + 1):
        cost[0][j] = j * skip_head
    for i in range(1, n + 1):
        for j in range(1, m + 1):
            d = abs(expected[i - 1] - heads[j - 1].position)
            match = 0.0 if d == 0 else 0.4 if d == 1 else 1.5
            cost[i][j] = min(
                cost[i - 1][j - 1] + match,
                cost[i - 1][j] + skip_note,
                cost[i][j - 1] + skip_head,
            )
    result: list[int | None] = [None] * n
    i, j = n, m
    while i > 0 and j > 0:
        d = abs(expected[i - 1] - heads[j - 1].position)
        match = 0.0 if d == 0 else 0.4 if d == 1 else 1.5
        if abs(cost[i][j] - (cost[i - 1][j - 1] + match)) < 1e-9:
            result[i - 1] = j - 1
            i, j = i - 1, j - 1
        elif abs(cost[i][j] - (cost[i - 1][j] + skip_note)) < 1e-9:
            i -= 1
        else:
            j -= 1
    return result


def _y_for_position(staff: StaffInfo, position: int) -> float:
    bottom = staff.lines[-1]
    return bottom - (position - 1) * staff.unit / 2


def _fill_missing_x(notes: list[dict], staff: StaffInfo) -> None:
    """Notes or rests with no matched notehead get x between their neighbours."""
    known = [(i, n["x"]) for i, n in enumerate(notes) if n["x"] is not None]
    for i, n in enumerate(notes):
        if n["x"] is not None:
            continue
        left = max(((k, x) for k, x in known if k < i), default=(-1, staff.x0))
        right = min(((k, x) for k, x in known if k > i), default=(len(notes), staff.x1))
        t = (i - left[0]) / (right[0] - left[0])
        n["x"] = left[1] + t * (right[1] - left[1])


def _note_dict(el) -> dict:
    is_rest = el.isRest
    if el.isChord:
        el = el.notes[-1]
    tie = el.tie.type if getattr(el, "tie", None) is not None else None
    return {
        "pitch": None if is_rest else el.pitch.nameWithOctave.replace("-", "b"),
        "dur": float(Fraction(el.quarterLength).limit_denominator(64)),
        "dots": el.duration.dots,
        "tie": tie,
        "fermata": any(isinstance(e, m21.expressions.Fermata) for e in el.expressions),
        "grace": bool(el.duration.isGrace),
        "x": None,
        "y": None,
        "matched": False,
    }


def build(result: HomrResult, song_id: str, source: dict, variant: str) -> dict:
    """Song JSON for one page."""
    score = m21.converter.parseData(result.musicxml, format="musicxml")
    part = score.parts[0]
    clef = _clef(result.symbols)
    events = _events_per_staff(result.symbols)

    measures: list[dict] = []
    flat_notes: list[dict] = []
    key = None
    time = None
    for meas in part.getElementsByClass(m21.stream.Measure):
        ks = meas.getElementsByClass(m21.key.KeySignature)
        if ks and key is None:
            key = ks[0].sharps
        ts = meas.getElementsByClass(m21.meter.TimeSignature)
        mtime = ts[0].ratioString if ts else None
        if time is None and mtime:
            time = mtime
        notes = [_note_dict(el) for el in meas.flatten().notesAndRests]
        flat_notes.extend(notes)
        measures.append({"index": len(measures) + 1, "time": mtime, "notes": notes, "flags": []})

    # Which staff each note is on
    if len(events) == len(flat_notes):
        for (staff_idx, _), note in zip(events, flat_notes):
            note["_staff"] = min(staff_idx, len(result.staffs) - 1)
    else:  # should not happen; fall back to spreading notes evenly
        per = max(1, len(flat_notes) // max(1, len(result.staffs)))
        for i, note in enumerate(flat_notes):
            note["_staff"] = min(i // per, len(result.staffs) - 1)

    bottom = BOTTOM_LINE.get(clef, BOTTOM_LINE["G2"])
    for staff_idx, staff in enumerate(result.staffs):
        on_staff = [n for n in flat_notes if n["_staff"] == staff_idx]
        pitched = [n for n in on_staff if n["pitch"] and not n["grace"]]
        expected = [diatonic(n["pitch"]) - bottom + 1 for n in pitched]
        for note, head_idx, pos in zip(pitched, _align(expected, staff.noteheads), expected):
            if head_idx is not None:
                head = staff.noteheads[head_idx]
                note["x"], note["y"], note["matched"] = head.x, head.y, True
            note["y"] = note["y"] if note["y"] is not None else _y_for_position(staff, pos)
        _fill_missing_x(on_staff, staff)
        for n in on_staff:
            if n["y"] is None:
                n["y"] = _y_for_position(staff, 5 if n["pitch"] is None else diatonic(n["pitch"]) - bottom + 1)

    for n in flat_notes:
        n["system"] = n.pop("_staff")
        n["x"], n["y"] = round(n["x"], 1), round(n["y"], 1)

    _measure_boxes(measures, result.staffs)
    return {
        "schema": SCHEMA_VERSION,
        "id": song_id,
        "source": source,
        "engine": {"name": "homr", "variant": variant},
        "status": "recognized",
        "clef": clef,
        "key": key or 0,
        "time": time,
        "systems": [
            {
                "lines": [round(y, 1) for y in s.lines],
                "x0": round(s.x0, 1),
                "x1": round(s.x1, 1),
                "unit": round(s.unit, 2),
            }
            for s in result.staffs
        ],
        "measures": measures,
    }


def _measure_boxes(measures: list[dict], staffs: list[StaffInfo]) -> None:
    """A rectangle around each bar on the scan, from the notes it holds."""
    for k, meas in enumerate(measures):
        notes = meas["notes"]
        if not notes:
            meas["system"], meas["box"] = None, None
            continue
        sys_idx = notes[0]["system"]
        staff = staffs[sys_idx]
        prev = measures[k - 1]["notes"][-1] if k > 0 and measures[k - 1]["notes"] else None
        nxt = measures[k + 1]["notes"][0] if k + 1 < len(measures) and measures[k + 1]["notes"] else None
        x0 = (prev["x"] + notes[0]["x"]) / 2 if prev and prev["system"] == sys_idx else staff.x0
        last = notes[-1]
        x1 = (last["x"] + nxt["x"]) / 2 if nxt and nxt["system"] == last["system"] else staff.x1
        meas["system"] = sys_idx
        meas["box"] = [
            round(x0, 1),
            round(float(staff.lines[0] - 4 * staff.unit), 1),
            round(x1, 1),
            round(float(staff.lines[-1] + 4 * staff.unit), 1),
        ]


def note_tuples(song: dict) -> list[tuple[str | None, float]]:
    """(pitch, duration) for every note and rest, the form the tests compare."""
    return [(n["pitch"], n["dur"]) for m in song["measures"] for n in m["notes"]]


def to_json_bytes(song: dict) -> bytes:
    import json

    buf = io.StringIO()
    json.dump(song, buf, ensure_ascii=False, indent=1)
    return buf.getvalue().encode("utf-8")
