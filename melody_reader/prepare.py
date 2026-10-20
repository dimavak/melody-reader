"""Turn an uploaded file (PNG, JPG or PDF) into page images ready for homr."""

from __future__ import annotations

import os
from dataclasses import dataclass

from PIL import Image

UPSCALE = 2
PDF_DPI = 300


@dataclass
class Page:
    """One page: the original image and its upscaled copy, both written to disk."""

    name: str
    original: str
    upscaled: str
    width: int
    height: int


def _save_pair(img: Image.Image, name: str, workdir: str) -> Page:
    img = img.convert("L")
    original = os.path.join(workdir, f"{name}.png")
    upscaled = os.path.join(workdir, f"{name}@2x.png")
    img.save(original)
    img.resize((img.width * UPSCALE, img.height * UPSCALE), Image.LANCZOS).save(upscaled)
    return Page(name, original, upscaled, img.width, img.height)


def scaled_copy(page: Page, factor: int) -> str:
    """Another upscaled copy of a page (for the third, tie-breaking homr run)."""
    path = page.original.replace(".png", f"@{factor}x.png")
    with Image.open(page.original) as img:
        img.resize((img.width * factor, img.height * factor), Image.LANCZOS).save(path)
    return path


def load_pages(path: str, workdir: str) -> list[Page]:
    """Split the input into pages. A PDF gives one page per PDF page, an image gives one."""
    os.makedirs(workdir, exist_ok=True)
    base = os.path.splitext(os.path.basename(path))[0]
    if path.lower().endswith(".pdf"):
        import fitz  # PyMuPDF

        pages = []
        with fitz.open(path) as doc:
            for i, pdf_page in enumerate(doc):
                pix = pdf_page.get_pixmap(dpi=PDF_DPI, colorspace=fitz.csGRAY)
                img = Image.frombytes("L", (pix.width, pix.height), pix.samples)
                name = base if len(doc) == 1 else f"{base}_p{i + 1}"
                pages.append(_save_pair(img, name, workdir))
        return pages
    with Image.open(path) as img:
        return [_save_pair(img, base, workdir)]
