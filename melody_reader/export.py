"""Song JSON -> MusicXML."""

from __future__ import annotations

import music21 as m21

CLEFS = {"G2": m21.clef.TrebleClef, "F4": m21.clef.BassClef, "C3": m21.clef.AltoClef, "C4": m21.clef.TenorClef}


def to_score(song: dict) -> m21.stream.Score:
    score = m21.stream.Score()
    score.metadata = m21.metadata.Metadata(title=song.get("title") or song["id"])
    part = m21.stream.Part()
    for k, meas in enumerate(song["measures"]):
        m = m21.stream.Measure(number=meas["index"])
        if k == 0:
            m.append(CLEFS.get(song.get("clef"), m21.clef.TrebleClef)())
            m.append(m21.key.KeySignature(song.get("key") or 0))
        time = meas.get("time") or (song.get("time") if k == 0 else None)
        if time:
            m.append(m21.meter.TimeSignature(time))
        for n in meas["notes"]:
            if n["pitch"] is None:
                el = m21.note.Rest(quarterLength=n["dur"])
            else:
                el = m21.note.Note(n["pitch"].replace("b", "-") if len(n["pitch"]) > 2 else n["pitch"])
                el.quarterLength = n["dur"]
                if n.get("tie"):
                    el.tie = m21.tie.Tie(n["tie"])
            if n.get("fermata"):
                el.expressions.append(m21.expressions.Fermata())
            if n.get("grace"):
                el = el.getGrace()
            m.append(el)
        part.append(m)
    score.append(part)
    return score


def to_musicxml(song: dict, path: str) -> None:
    to_score(song).write("musicxml", fp=path)
