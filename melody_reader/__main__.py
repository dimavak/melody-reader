"""Command line: python -m melody_reader recognize scans/*.png"""

from __future__ import annotations

import argparse
import glob
import os
import sys

INPUT_EXTENSIONS = (".png", ".jpg", ".jpeg", ".pdf")


def _inputs(paths: list[str]) -> list[str]:
    files: list[str] = []
    for p in paths:
        if os.path.isdir(p):
            files.extend(sorted(f for f in glob.glob(os.path.join(p, "*")) if f.lower().endswith(INPUT_EXTENSIONS)))
        else:
            files.append(p)
    return files


def _already_done(path: str, songs_dir: str) -> bool:
    base = os.path.splitext(os.path.basename(path))[0]
    return os.path.exists(os.path.join(songs_dir, base + ".json")) or bool(
        glob.glob(os.path.join(songs_dir, base + "_p*.json"))
    )


def _update_site(songs_dir: str, melodies_path: str) -> int:
    import json

    from melody_reader import site

    melodies = site.read_melodies(melodies_path) if os.path.exists(melodies_path) else {}
    for path in sorted(glob.glob(os.path.join(songs_dir, "*.json"))):
        song = json.load(open(path, encoding="utf-8"))
        key = os.path.basename(song["source"]["file"])
        melodies[key] = site.merge(melodies.get(key), song)
    site.write_melodies(dict(sorted(melodies.items())), melodies_path)
    print(f"{melodies_path}: {len(melodies)} melodies")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="melody_reader")
    sub = parser.add_subparsers(dest="command", required=True)
    rec = sub.add_parser("recognize", help="recognise scans or PDFs")
    rec.add_argument("inputs", nargs="+", help="files or folders")
    rec.add_argument("--songs", default="songs", help="where song JSON goes")
    rec.add_argument("--export", default="export", help="where MusicXML goes")
    rec.add_argument("--pages", default="pages", help="where PDF page images go")
    rec.add_argument("--skip-existing", action="store_true", help="skip inputs that already have a song JSON")
    site = sub.add_parser("site", help="update melodies.js of the songs site from song JSON")
    site.add_argument("songs", help="folder with song JSON")
    site.add_argument("melodies", help="melodies.js to update (created if missing)")
    args = parser.parse_args(argv)

    if args.command == "site":
        return _update_site(args.songs, args.melodies)

    from melody_reader import pipeline

    failed = []
    for path in _inputs(args.inputs):
        if args.skip_existing and _already_done(path, args.songs):
            continue
        print(f"== {path}", flush=True)
        try:
            for out in pipeline.recognize_file(path, args.songs, args.export, args.pages):
                print(f"   -> {out}", flush=True)
        except Exception as e:
            print(f"   !! {type(e).__name__}: {e}", flush=True)
            failed.append(path)
    if failed:
        print("Failed:", ", ".join(failed))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
