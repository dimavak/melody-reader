"""Ask Claude which reading of a doubtful bar matches the scan.

Claude only picks between the two homr readings (or says it cannot tell); it never
writes notes of its own. Its answer is stored as a hint, the bar stays flagged
for the person in the editor.
"""

from __future__ import annotations

import base64
import io
import json
import os

from PIL import Image

MODEL = "claude-opus-5-5"

SCHEMA = {
    "type": "object",
    "properties": {
        "choice": {"type": "string", "enum": ["A", "B", "unknown"]},
        "reason": {"type": "string"},
    },
    "required": ["choice", "reason"],
    "additionalProperties": False,
}

PROMPT = """The image shows one bar of a single-line folk melody from a printed songbook \
(treble clef unless the image shows otherwise; key signature: {key}; time signature: {time}).
Two optical music recognition runs read this bar differently:

A: {a}
B: {b}

Durations are in quarter notes (1 = quarter, 0.5 = eighth, 1.5 = dotted quarter, 2 = half).
Look at the noteheads, stems, beams, flags, dots and fermatas in the image and decide which \
reading matches the printed bar exactly. A dot above or below a note under a fermata is part \
of the fermata, not an augmentation dot. If neither matches, or the image is unclear, answer \
"unknown". Give a one-sentence reason."""


def _describe(notes: list[dict] | None) -> str:
    if not notes:
        return "(no notes)"
    parts = []
    for n in notes:
        name = n["pitch"] or "rest"
        extra = " fermata" if n.get("fermata") else ""
        extra += " grace" if n.get("grace") else ""
        parts.append(f"{name} {n['dur']:g}{extra}")
    return ", ".join(parts)


def _crop(image_path: str, box: list[float], unit: float) -> str:
    """Base64 PNG of the bar, with a little of the neighbouring bars for context."""
    with Image.open(image_path) as img:
        x0, y0, x1, y1 = box
        pad = 2 * unit
        region = img.convert("L").crop(
            (max(0, x0 - pad), max(0, y0), min(img.width, x1 + pad), min(img.height, y1))
        )
        if region.height < 400:  # small scans: enlarge so dots and flags are visible
            k = 400 / region.height
            region = region.resize((int(region.width * k), 400), Image.LANCZOS)
        buf = io.BytesIO()
        region.save(buf, format="PNG")
    return base64.standard_b64encode(buf.getvalue()).decode("ascii")


def available() -> bool:
    return bool(os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN"))


def check_bar(client, image_path: str, song: dict, measure: dict) -> dict:
    """Returns {"choice": "A" | "B" | "unknown", "reason": str}. A is the primary (2x) reading."""
    unit = song["systems"][measure["system"]]["unit"]
    prompt = PROMPT.format(
        key=f"{song['key']} sharps" if song["key"] >= 0 else f"{-song['key']} flats",
        time=measure.get("time") or song.get("time") or "unknown",
        a=_describe(measure["notes"]),
        b=_describe(measure.get("alt")),
    )
    response = client.beta.messages.create(
        model=MODEL,
        max_tokens=4000,
        betas=["server-side-fallback-2026-07-01"],
        fallbacks="default",
        output_config={"effort": "medium", "format": {"type": "json_schema", "schema": SCHEMA}},
        messages=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": "image/png",
                            "data": _crop(image_path, measure["box"], unit),
                        },
                    },
                    {"type": "text", "text": prompt},
                ],
            }
        ],
    )
    if response.stop_reason == "refusal":
        return {"choice": "unknown", "reason": "model declined"}
    text = "".join(b.text for b in response.content if b.type == "text")
    try:
        answer = json.loads(text)
    except json.JSONDecodeError:
        return {"choice": "unknown", "reason": "unreadable answer"}
    return {"choice": answer.get("choice", "unknown"), "reason": answer.get("reason", "")}


def check_song(image_path: str, song: dict, client=None) -> int:
    """Adds an "llm" hint to every doubtful bar that has two readings. Returns how many were checked."""
    if client is None:
        import anthropic

        client = anthropic.Anthropic()
    checked = 0
    for measure in song["measures"]:
        if "disagree" not in measure["flags"] or not measure.get("box") or measure.get("alt") is None:
            continue
        try:
            measure["llm"] = check_bar(client, image_path, song, measure)
        except Exception as e:  # network or API error: leave the bar to the person
            measure["llm"] = {"choice": "unknown", "reason": f"error: {type(e).__name__}"}
        checked += 1
    return checked
