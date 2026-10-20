"""Scan -> song JSON + MusicXML, the whole first stage in one function."""

from __future__ import annotations

import json
import os
import shutil
import tempfile
import time

from melody_reader import checks, export, omr, prepare, song


def recognize_page(page: prepare.Page, source_name: str) -> dict:
    started = time.time()
    primary_raw = omr.run(page.upscaled, scale_to_original=0.5)
    other_raw = omr.run(page.original, scale_to_original=1.0)
    source = {"file": source_name, "width": page.width, "height": page.height}
    primary = song.build(primary_raw, page.name, source, "2x")
    other = song.build(other_raw, page.name, source, "1x")
    checks.compare(primary, other)
    checks.apply_rules(primary)
    if any("disagree" in m["flags"] for m in primary["measures"]):
        # A third homr run (3x) votes between the two readings
        third_raw = omr.run(prepare.scaled_copy(page, 3), scale_to_original=1 / 3)
        checks.vote(primary, song.build(third_raw, page.name, source, "3x"))
    primary["stats"] = {
        "notes": sum(len(m["notes"]) for m in primary["measures"]),
        "doubtful_bars": len(checks.doubtful(primary)),
        "seconds": round(time.time() - started, 1),
    }
    return primary


def recognize_file(
    path: str, songs_dir: str, export_dir: str, pages_dir: str
) -> list[str]:
    """Recognise every page of `path`.

    Writes <songs_dir>/<name>.json and <export_dir>/<name>.musicxml. PDF pages are
    also saved as <pages_dir>/<name>.png, since the editor shows an image.
    Paths stored in the JSON are as given, so run this from the repository root.
    """
    os.makedirs(songs_dir, exist_ok=True)
    os.makedirs(export_dir, exist_ok=True)
    written = []
    with tempfile.TemporaryDirectory() as work:
        for page in prepare.load_pages(path, work):
            image_file = path
            if path.lower().endswith(".pdf"):
                os.makedirs(pages_dir, exist_ok=True)
                image_file = os.path.join(pages_dir, page.name + ".png")
                shutil.copyfile(page.original, image_file)
            result = recognize_page(page, image_file.replace(os.sep, "/"))
            out = os.path.join(songs_dir, page.name + ".json")
            with open(out, "w", encoding="utf-8") as f:
                json.dump(result, f, ensure_ascii=False, indent=1)
            export.to_musicxml(result, os.path.join(export_dir, page.name + ".musicxml"))
            written.append(out)
    return written
