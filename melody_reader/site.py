"""Song JSON -> melodies.js of the songs site (dimavak/muzhchynskija-pesni).

melodies.js holds `window.MELODIES = {"<image>.png": {"ev": [...], "st": [...], "seq": [...]}}`:
- ev: one event per note or rest, [midi (-1 for a rest), duration in quarters,
  x and y of the notehead as fractions of the image size, staff index, flags];
  flag 2 marks a fermata (the site holds such a note longer), flag 4 a note in a
  bar the pipeline marked as doubtful;
- st: for each staff, [x0, x1, top line y, bottom line y] as fractions;
- seq: playing order of the events when the tune has repeats.
"""

from __future__ import annotations

import json

import music21 as m21

FERMATA = 2
DOUBTFUL = 4


def _midi(pitch: str | None) -> int:
    if pitch is None:
        return -1
    return m21.pitch.Pitch(pitch.replace("b", "-") if len(pitch) > 2 else pitch).midi


def entry(song: dict) -> dict:
    """The melodies.js value for one song."""
    w, h = song["source"]["width"], song["source"]["height"]
    ev: list[list] = []
    bar_of_event: list[int] = []
    for k, meas in enumerate(song["measures"]):
        doubtful = bool(meas["flags"])
        for n in meas["notes"]:
            if n.get("grace"):
                continue
            midi = _midi(n["pitch"])
            prev = ev[-1] if ev else None
            # a tied note continues the previous one: the site plays it as one longer note
            if n.get("tie") in ("stop", "continue") and prev and prev[0] == midi:
                prev[1] = round(prev[1] + n["dur"], 4)
                continue
            flags = (FERMATA if n.get("fermata") else 0) | (DOUBTFUL if doubtful else 0)
            ev.append([midi, round(n["dur"], 4), round(n["x"] / w, 4), round(n["y"] / h, 4), n["system"], flags])
            bar_of_event.append(k)
    st = [
        [round(s["x0"] / w, 4), round(s["x1"] / w, 4), round(s["lines"][0] / h, 4), round(s["lines"][-1] / h, 4)]
        for s in song["systems"]
    ]
    out = {"ev": ev, "st": st}
    seq = play_order(song["measures"], bar_of_event)
    if seq is not None:
        out["seq"] = seq
    return out


def play_order(measures: list[dict], bar_of_event: list[int]) -> list[int] | None:
    """Event order with repeats played twice, or None when the tune has no repeat sign."""
    if not any(m.get("repeat_end") for m in measures):
        return None
    bars: list[int] = []
    start = 0
    for k, meas in enumerate(measures):
        if meas.get("repeat_start"):
            start = k
        bars.append(k)
        if meas.get("repeat_end"):
            bars.extend(range(start, k + 1))
            start = k + 1
    events_in_bar: dict[int, list[int]] = {}
    for i, k in enumerate(bar_of_event):
        events_in_bar.setdefault(k, []).append(i)
    return [i for k in bars for i in events_in_bar.get(k, [])]


def carry_seq(old: dict, new: dict) -> list[int] | None:
    """Move the repeat order of an old entry onto the events of a new one.

    The old `seq` is split into runs of consecutive events; each run's first and
    last event is found again in the new entry by staff and position on the image.
    """
    if "seq" not in old or not new["ev"]:
        return None
    runs: list[list[int]] = []
    for i in old["seq"]:
        if runs and runs[-1][1] + 1 == i:
            runs[-1][1] = i
        else:
            runs.append([i, i])

    def nearest(i: int) -> int:
        e = old["ev"][i]
        return min(range(len(new["ev"])), key=lambda j: (new["ev"][j][4] != e[4], abs(new["ev"][j][2] - e[2])))

    seq: list[int] = []
    for a, b in runs:
        a2, b2 = nearest(a), nearest(b)
        # the ends of the tune stay the ends, even if a note was added or dropped there
        if a == 0:
            a2 = 0
        if b == len(old["ev"]) - 1:
            b2 = len(new["ev"]) - 1
        seq.extend(range(a2, b2 + 1))
    return seq


def merge(old: dict | None, song: dict) -> dict:
    """New melodies.js entry for a recognised song; the old one is kept if nothing was read."""
    new = entry(song)
    if not any(e[0] >= 0 for e in new["ev"]):
        return old if old is not None else new
    # homr finds the end sign of a repeat but often misses its start, so on the site
    # only the repeats already marked there are kept
    new.pop("seq", None)
    seq = carry_seq(old, new) if old is not None else None
    if seq is not None:
        new["seq"] = seq
    return new


def read_melodies(path: str) -> dict:
    text = open(path, encoding="utf-8").read()
    return json.loads(text[text.index("{") : text.rindex("}") + 1])


def write_melodies(melodies: dict, path: str) -> None:
    body = json.dumps(melodies, ensure_ascii=False, separators=(",", ":"))
    with open(path, "w", encoding="utf-8") as f:
        f.write("window.MELODIES = " + body + ";\n")
