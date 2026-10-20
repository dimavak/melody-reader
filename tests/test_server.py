"""The recognition server (space/app.py) with homr replaced by a stub."""

import os
import sys
import time

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "space"))

from fastapi.testclient import TestClient  # noqa: E402

import app as server  # noqa: E402


def test_job_returns_song_and_musicxml(monkeypatch, tmp_path):
    seen = {}

    def fake_recognize_file(path, songs_dir, export_dir, pages_dir):
        seen["path"] = path
        os.makedirs(songs_dir)
        os.makedirs(export_dir)
        with open(os.path.join(songs_dir, "x.json"), "w") as f:
            f.write('{"id": "x", "source": {"file": "/tmp/whatever/x.png"}, "measures": []}')
        with open(os.path.join(export_dir, "x.musicxml"), "w") as f:
            f.write("<score-partwise/>")
        return [os.path.join(songs_dir, "x.json")]

    monkeypatch.setattr(server.pipeline, "recognize_file", fake_recognize_file)
    from PIL import Image

    photo = tmp_path / "Photo 1.jpg"
    Image.new("RGB", (3000, 1000), "white").save(photo)
    client = TestClient(server.app)
    with open(photo, "rb") as f:
        job = client.post("/jobs", files={"file": ("Photo 1.jpg", f, "image/jpeg")}).json()
    for _ in range(50):
        res = client.get(f"/jobs/{job['id']}").json()
        if res["status"] in ("done", "failed"):
            break
        time.sleep(0.1)
    assert res["status"] == "done", res
    page = res["pages"][0]
    assert page["musicxml"] == "<score-partwise/>"
    assert page["song"]["source"]["file"] == "Photo_1.png"
    assert seen["path"].endswith("Photo_1.png")


def test_rejects_other_files():
    client = TestClient(server.app)
    assert client.post("/jobs", files={"file": ("notes.txt", b"hello")}).status_code == 415
    assert client.get("/jobs/nope").status_code == 404
