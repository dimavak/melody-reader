"""Find bars that a person should look at.

Two sources of doubt:
- the two homr runs (original and 2x) disagree on the bar;
- simple musical rules fail (bar length vs time signature, a fermata over a dotted
  note, a note far outside the song's range).
"""

from __future__ import annotations

from fractions import Fraction
from statistics import median

import music21 as m21

RANGE_SEMITONES = 14


def _content(measure: dict) -> list[tuple]:
    return [(n["pitch"], n["dur"]) for n in measure["notes"]]


def _align_measures(a: list[dict], b: list[dict]) -> list[int | None]:
    """For each bar of `a`, the index of the matching bar of `b` (edit-distance alignment)."""
    n, m = len(a), len(b)
    ca = [_content(x) for x in a]
    cb = [_content(x) for x in b]
    cost = [[0] * (m + 1) for _ in range(n + 1)]
    for i in range(n + 1):
        cost[i][0] = i
    for j in range(m + 1):
        cost[0][j] = j
    for i in range(1, n + 1):
        for j in range(1, m + 1):
            sub = 0 if ca[i - 1] == cb[j - 1] else 1
            cost[i][j] = min(cost[i - 1][j - 1] + sub, cost[i - 1][j] + 1, cost[i][j - 1] + 1)
    result: list[int | None] = [None] * n
    i, j = n, m
    while i > 0 and j > 0:
        sub = 0 if ca[i - 1] == cb[j - 1] else 1
        if cost[i][j] == cost[i - 1][j - 1] + sub:
            result[i - 1] = j - 1
            i, j = i - 1, j - 1
        elif cost[i][j] == cost[i - 1][j] + 1:
            i -= 1
        else:
            j -= 1
    return result


def _add_flag(measure: dict, flag: str) -> None:
    if flag not in measure["flags"]:
        measure["flags"].append(flag)


def compare(primary: dict, other: dict) -> None:
    """Mark bars of `primary` where `other` reads something different; keep its version as `alt`."""
    pairs = _align_measures(primary["measures"], other["measures"])
    for meas, j in zip(primary["measures"], pairs):
        if j is None:
            _add_flag(meas, "disagree")
            meas["alt"] = None
            continue
        alt = other["measures"][j]
        if _content(meas) != _content(alt):
            _add_flag(meas, "disagree")
            meas["alt"] = [{k: n[k] for k in ("pitch", "dur", "dots", "tie", "fermata", "grace")} for n in alt["notes"]]


def _bar_length(time: str) -> Fraction:
    num, den = time.split("/")
    return Fraction(int(num) * 4, int(den))


def _total(measure: dict) -> Fraction:
    return sum((Fraction(n["dur"]).limit_denominator(64) for n in measure["notes"] if not n["grace"]), Fraction(0))


def apply_rules(song: dict) -> None:
    measures = song["measures"]
    time = song.get("time")
    midis = [m21.pitch.Pitch(n["pitch"]).midi for m in measures for n in m["notes"] if n["pitch"]]
    center = median(midis) if midis else None
    for k, meas in enumerate(measures):
        time = meas.get("time") or time
        notes = meas["notes"]
        if time:
            total = _total(meas)
            full = _bar_length(time)
            # A short first bar is a pickup; a short last bar is fine only when it completes the pickup.
            short_ok = k == 0 or (k == len(measures) - 1 and k > 0 and _total(measures[0]) < full)
            if total > full or (total < full and not short_ok):
                _add_flag(meas, "duration")
        for n in notes:
            if n["fermata"] and n["dots"]:
                _add_flag(meas, "fermata-dot")
            if n["pitch"] and center is not None:
                if abs(m21.pitch.Pitch(n["pitch"]).midi - center) > RANGE_SEMITONES:
                    _add_flag(meas, "range")


def doubtful(song: dict) -> list[dict]:
    return [m for m in song["measures"] if m["flags"]]
