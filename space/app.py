"""Recognition server for the Melody reader web app (runs as a Hugging Face Space).

The browser posts a scan or a photo to /jobs and gets a job id back, then asks
/jobs/<id> every few seconds until the notes are ready. homr takes a minute or
two per page on the free CPU, longer than a single HTTP request should wait, and
only one job runs at a time so that two uploads do not share the two CPU cores.
"""

from __future__ import annotations

import base64
import json
import os
import queue
import tempfile
import threading
import time
import uuid

from fastapi import FastAPI, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from PIL import Image, ImageOps

from melody_reader import pipeline

MAX_BYTES = 20 * 1024 * 1024
MAX_SIDE = 2400  # phone photos are bigger than homr needs; scans are ~1400 px wide
KEEP_SECONDS = 3600
EXTENSIONS = (".png", ".jpg", ".jpeg", ".pdf")
ORIGINS = os.environ.get("ALLOWED_ORIGINS", "*").split(",")

app = FastAPI(title="melody-reader")
app.add_middleware(CORSMiddleware, allow_origins=ORIGINS, allow_methods=["GET", "POST"], allow_headers=["*"])

jobs: dict[str, dict] = {}
waiting: queue.Queue[str] = queue.Queue()
lock = threading.Lock()


def _name(filename: str) -> tuple[str, str]:
    """A safe file name for the upload and its extension."""
    base, ext = os.path.splitext(os.path.basename(filename or "scan.png"))
    base = "".join(c if c.isalnum() or c in "-_" else "_" for c in base)[:60] or "scan"
    return base, ext.lower()


def _prepare_image(path: str) -> str:
    """Save a photo upright (EXIF), in grey and at most MAX_SIDE px long, as PNG."""
    with Image.open(path) as img:
        img = ImageOps.exif_transpose(img).convert("L")
    if max(img.size) > MAX_SIDE:
        img.thumbnail((MAX_SIDE, MAX_SIDE), Image.LANCZOS)
    png = os.path.splitext(path)[0] + ".png"
    img.save(png)
    if png != path:
        os.remove(path)
    return png


def recognize(path: str) -> list[dict]:
    """Run the stage 1 pipeline on one upload and return what the browser needs per page."""
    out = []
    with tempfile.TemporaryDirectory() as work:
        songs_dir, export_dir, pages_dir = (os.path.join(work, d) for d in ("songs", "export", "pages"))
        for song_file in pipeline.recognize_file(path, songs_dir, export_dir, pages_dir):
            with open(song_file, encoding="utf-8") as f:
                song = json.load(f)
            name = song["id"]
            with open(os.path.join(export_dir, name + ".musicxml"), encoding="utf-8") as f:
                musicxml = f.read()
            item = {"song": song, "musicxml": musicxml}
            page_image = os.path.join(pages_dir, name + ".png")
            if os.path.exists(page_image):  # PDF page: the browser has no image of it
                with open(page_image, "rb") as f:
                    item["image"] = "data:image/png;base64," + base64.b64encode(f.read()).decode()
                song["source"]["file"] = name + ".png"
            else:
                song["source"]["file"] = os.path.basename(path)
            out.append(item)
    return out


def _worker() -> None:
    while True:
        job_id = waiting.get()
        job = jobs.get(job_id)
        if not job:
            continue
        job.update(status="running", started=time.time())
        try:
            job["pages"] = recognize(job["path"])
            job["status"] = "done"
        except Exception as e:  # report any failure to the browser instead of hanging
            job.update(status="failed", error=f"{type(e).__name__}: {e}")
        finally:
            job["finished"] = time.time()
            try:
                os.remove(job["path"])
            except OSError:
                pass


def _forget_old() -> None:
    now = time.time()
    with lock:
        for job_id in [k for k, j in jobs.items() if now - j.get("finished", now) > KEEP_SECONDS]:
            del jobs[job_id]


threading.Thread(target=_worker, daemon=True).start()
UPLOADS = tempfile.mkdtemp(prefix="uploads-")


@app.get("/")
def health() -> dict:
    return {"ok": True, "service": "melody-reader", "queue": waiting.qsize()}


@app.post("/jobs")
async def create_job(file: UploadFile) -> dict:
    base, ext = _name(file.filename)
    if ext not in EXTENSIONS:
        raise HTTPException(415, "Патрэбны PNG, JPG або PDF")
    data = await file.read(MAX_BYTES + 1)
    if len(data) > MAX_BYTES:
        raise HTTPException(413, "Файл большы за 20 МБ")
    _forget_old()
    job_id = uuid.uuid4().hex
    folder = os.path.join(UPLOADS, job_id)
    os.makedirs(folder)
    path = os.path.join(folder, base + ext)
    with open(path, "wb") as f:
        f.write(data)
    if ext != ".pdf":
        try:
            path = _prepare_image(path)
        except Exception:
            raise HTTPException(415, "Не атрымалася адкрыць выяву")
    jobs[job_id] = {"status": "queued", "path": path, "created": time.time()}
    waiting.put(job_id)
    return {"id": job_id, "status": "queued", "ahead": waiting.qsize() - 1}


@app.get("/jobs/{job_id}")
def get_job(job_id: str) -> dict:
    job = jobs.get(job_id)
    if not job:
        raise HTTPException(404, "Заданне не знойдзена")
    out = {"id": job_id, "status": job["status"]}
    if job["status"] == "queued":
        out["ahead"] = list(waiting.queue).index(job_id) if job_id in waiting.queue else 0
    if "started" in job:
        out["seconds"] = round(job.get("finished", time.time()) - job["started"])
    if job["status"] == "done":
        out["pages"] = job["pages"]
    if job["status"] == "failed":
        out["error"] = job["error"]
    return out
