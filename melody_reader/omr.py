"""Run homr on one image and keep what its command line throws away.

Besides the MusicXML we need, for every staff, the staff line positions and the
detected noteheads, so that each recognised note can be placed on the scan.
homr crops the page and rescales it to a width of 1920 px before it works; we
record that crop and scale to map coordinates back to the original image.
"""

from __future__ import annotations

import os
import tempfile
from dataclasses import dataclass, field

import numpy as np

import homr.main as hm
from homr.music_xml_generator import XmlGeneratorArguments, generate_xml
from homr.staff_parsing import _ensure_same_number_of_staffs, parse_staff_image
from homr.staff_regions import StaffRegions
from homr.transformer.configs import Config
from homr.transformer.vocabulary import EncodedSymbol, remove_duplicated_symbols

HOMR_WIDTH = 1920


@dataclass
class Notehead:
    x: float
    y: float
    position: int  # staff steps, 1 = bottom line, 9 = top line


@dataclass
class StaffInfo:
    lines: list[float]  # y of the 5 lines at the staff's middle, in original pixels
    x0: float
    x1: float
    unit: float  # distance between two lines, in original pixels
    noteheads: list[Notehead] = field(default_factory=list)


@dataclass
class HomrResult:
    musicxml: str  # MusicXML text
    symbols: list[EncodedSymbol]  # final symbols, staffs separated by "newline"
    staffs: list[StaffInfo]


_weights_ready = False


def _ensure_weights() -> None:
    global _weights_ready
    if not _weights_ready:
        hm.download_weights(False, False, False)
        _weights_ready = True


def _slice_offset(parent: np.ndarray, child: np.ndarray) -> tuple[int, int]:
    """Where a numpy slice `child` starts inside `parent` (autocrop returns a view)."""
    if child is parent or child.base is None:
        return 0, 0
    delta = child.__array_interface__["data"][0] - parent.__array_interface__["data"][0]
    row, rest = divmod(delta, parent.strides[0])
    return int(row), int(rest // parent.strides[1])


def run(image_path: str, scale_to_original: float = 1.0) -> HomrResult:
    """Recognise one page. `scale_to_original` maps input pixels to original pixels (0.5 for 2x)."""
    _ensure_weights()
    crop: dict[str, float] = {}
    original_autocrop = hm.autocrop

    def recording_autocrop(img: np.ndarray) -> np.ndarray:
        out = original_autocrop(img)
        crop["y"], crop["x"] = _slice_offset(img, out)
        crop["w"] = out.shape[1]
        return out

    config = hm.ProcessingConfig(False, False, False, False, -1, False, False, False)
    hm.autocrop = recording_autocrop
    try:
        multi_staffs, image, debug, title_future = hm.detect_staffs_in_image(image_path, config)
    finally:
        hm.autocrop = original_autocrop

    # homr space -> input image -> original image
    k = crop["w"] / HOMR_WIDTH

    def to_orig(x: float, y: float) -> tuple[float, float]:
        return (
            (crop["x"] + x * k) * scale_to_original,
            (crop["y"] + y * k) * scale_to_original,
        )

    multi_staffs = _ensure_same_number_of_staffs(multi_staffs, image)
    regions = StaffRegions(multi_staffs)
    transformer_config = Config()
    transformer_config.use_gpu_inference = False
    transformer_config.use_coreml_encoder = False
    symbols: list[EncodedSymbol] = []
    staffs: list[StaffInfo] = []
    for index, multi in enumerate(multi_staffs):
        staff = multi.staffs[0]  # monophonic melodies: one voice
        found = parse_staff_image(debug, index, staff, image, regions, transformer_config)
        if not found:
            continue
        symbols.extend(found)
        symbols.append(EncodedSymbol("newline"))
        mid = staff.grid[len(staff.grid) // 2]
        lines = [float(to_orig(mid.x, y)[1]) for y in mid.y]
        info = StaffInfo(
            lines=lines,
            x0=float(to_orig(staff.min_x, 0)[0]),
            x1=float(to_orig(staff.max_x, 0)[0]),
            unit=float(staff.average_unit_size) * k * scale_to_original,
        )
        for note in staff.get_notes():
            x, y = to_orig(*note.center)
            info.noteheads.append(Notehead(float(x), float(y), int(note.position)))
        info.noteheads.sort(key=lambda n: n.x)
        staffs.append(info)
    debug.clean_debug_files_from_previous_runs()

    symbols = remove_duplicated_symbols(symbols)
    title = ""
    try:
        title = title_future.result(60)
    except Exception:
        pass
    xml = generate_xml(XmlGeneratorArguments(), [symbols], title)
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "out.musicxml")
        xml.write(path)
        with open(path, encoding="utf-8") as f:
            text = f.read()
    return HomrResult(text, symbols, staffs)
