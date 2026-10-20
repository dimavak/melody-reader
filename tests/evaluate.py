"""Compare recognised songs with the reference melodies (etalon) and report errors.

    python tests/evaluate.py songs/ tests/etalon.json

For every song: note errors (edit distance on (pitch, duration), rests and grace notes ignored),
and whether each error falls in a bar that the pipeline flagged as doubtful.
Songs whose file name is not in the etalon are matched to the closest reference.
"""

from __future__ import annotations

import glob
import json
import os
import sys


def _notes(song: dict) -> list[tuple]:
    """(pitch, dur, bar index) for every pitched note."""
    out = []
    for k, m in enumerate(song["measures"]):
        for n in m["notes"]:
            if n["pitch"] and not n["grace"]:
                out.append((n["pitch"], n["dur"], k))
    return out


def _diff(ref: list[tuple], got: list[tuple]) -> tuple[int, set[int]]:
    """Edit distance, and the bars of `got` that hold an edit."""
    n, m = len(ref), len(got)
    D = [[0] * (m + 1) for _ in range(n + 1)]
    for i in range(n + 1):
        D[i][0] = i
    for j in range(m + 1):
        D[0][j] = j
    for i in range(1, n + 1):
        for j in range(1, m + 1):
            same = ref[i - 1][:2] == got[j - 1][:2]
            D[i][j] = min(D[i - 1][j - 1] + (0 if same else 1), D[i - 1][j] + 1, D[i][j - 1] + 1)
    bars: set[int] = set()
    i, j = n, m
    while i > 0 or j > 0:
        if i > 0 and j > 0:
            same = ref[i - 1][:2] == got[j - 1][:2]
            if D[i][j] == D[i - 1][j - 1] + (0 if same else 1):
                if not same:
                    bars.add(got[j - 1][2])
                i, j = i - 1, j - 1
                continue
        if j > 0 and D[i][j] == D[i][j - 1] + 1:
            bars.add(got[j - 1][2])
            j -= 1
        else:  # a reference note is missing; blame the bar of the neighbour we have
            bars.add(got[min(j, m - 1)][2] if m else 0)
            i -= 1
    return D[n][m], bars


def main(songs_dir: str, etalon_path: str) -> None:
    etalon = {
        k: [tuple(x) for x in v if x[0] != "r"] for k, v in json.load(open(etalon_path, encoding="utf-8")).items()
    }
    total = errors = perfect = 0
    missed_songs = 0
    flagged_bars = all_bars = 0
    rows = []
    for path in sorted(glob.glob(os.path.join(songs_dir, "*.json"))):
        song = json.load(open(path, encoding="utf-8"))
        got = _notes(song)
        name = song["id"]
        if name not in etalon:  # unnamed upload: closest reference
            name = min(etalon, key=lambda k: _diff(etalon[k], got)[0] / max(1, len(etalon[k])))
        ref = etalon[name]
        e, bars = _diff(ref, got)
        flagged = {k for k, m in enumerate(song["measures"]) if m["flags"]}
        missed = bars - flagged
        total += len(ref)
        errors += e
        perfect += e == 0
        missed_songs += bool(missed)
        flagged_bars += len(flagged)
        all_bars += len(song["measures"])
        rows.append((name, song["id"], len(ref), e, sorted(bars), sorted(flagged), sorted(missed)))
    for r in rows:
        mark = "MISSED" if r[6] else ""
        print(f"{r[0]:10s} {r[1]:12s} notes={r[2]:3d} err={r[3]:2d} err_bars={r[4]} flagged={r[5]} {mark}")
    print(
        f"\nsongs={len(rows)} notes={total} note_err={errors / max(1, total):.1%} perfect={perfect}/{len(rows)}"
        f" flagged_bars={flagged_bars}/{all_bars} songs_with_unflagged_errors={missed_songs}"
    )


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "songs", sys.argv[2] if len(sys.argv) > 2 else "tests/etalon.json")
