"""Build the web app for GitHub Pages: python web/build.py _site --verovio path/to/verovio-toolkit-wasm.js

Copies web/ and the recognised songs (songs/, export/ and their images) into the
output folder and writes data/index.json, the list the app shows. The address
of the recognition server (SERVER_URL) goes to config.json.
"""

from __future__ import annotations

import argparse
import glob
import hashlib
import json
import os
import shutil
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WEB = os.path.join(ROOT, "web")


def server_url() -> str:
    return os.environ.get("SERVER_URL", "").rstrip("/")


def songs(out: str) -> list[dict]:
    entries = []
    for path in sorted(glob.glob(os.path.join(ROOT, "songs", "*.json"))):
        with open(path, encoding="utf-8") as f:
            song = json.load(f)
        sid = song["id"]
        xml = os.path.join(ROOT, "export", sid + ".musicxml")
        image = os.path.join(ROOT, song["source"]["file"])
        if not (os.path.exists(xml) and os.path.exists(image)):
            print(f"skip {sid}: no MusicXML or image", file=sys.stderr)
            continue
        image_name = sid + os.path.splitext(image)[1].lower()
        shutil.copyfile(path, os.path.join(out, "data", "songs", sid + ".json"))
        shutil.copyfile(xml, os.path.join(out, "data", "export", sid + ".musicxml"))
        shutil.copyfile(image, os.path.join(out, "data", "img", image_name))
        entries.append({
            "id": sid,
            "title": song.get("title"),
            "notes": sum(len(m["notes"]) for m in song["measures"]),
            "doubtful": sum(1 for m in song["measures"] if m.get("flags")),
            "image": "img/" + image_name,
        })
    return entries


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("out")
    parser.add_argument("--verovio", required=True, help="verovio-toolkit-wasm.js from the verovio npm package")
    args = parser.parse_args()

    out = args.out
    shutil.rmtree(out, ignore_errors=True)
    shutil.copytree(WEB, out, ignore=shutil.ignore_patterns("build.py", "__pycache__"))
    for d in ("data/songs", "data/export", "data/img", "vendor"):
        os.makedirs(os.path.join(out, d), exist_ok=True)
    shutil.copyfile(args.verovio, os.path.join(out, "vendor", "verovio-toolkit-wasm.js"))

    entries = songs(out)
    with open(os.path.join(out, "data", "index.json"), "w", encoding="utf-8") as f:
        json.dump(entries, f, ensure_ascii=False)
    with open(os.path.join(out, "config.json"), "w", encoding="utf-8") as f:
        json.dump({"server": server_url()}, f)

    # A new service worker version whenever the app's own files change
    digest = hashlib.sha256()
    for name in sorted(os.listdir(WEB)):
        if os.path.isfile(os.path.join(WEB, name)):
            with open(os.path.join(WEB, name), "rb") as f:
                digest.update(f.read())
    sw = os.path.join(out, "sw.js")
    with open(sw, encoding="utf-8") as f:
        text = f.read().replace("__VERSION__", digest.hexdigest()[:12])
    with open(sw, "w", encoding="utf-8") as f:
        f.write(text)
    open(os.path.join(out, ".nojekyll"), "w").close()
    print(f"{len(entries)} songs -> {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
