#!/usr/bin/env python3
"""Genera assets/scadenze-ps.ico (croce verde su bianco) in formato ICO multi-size."""

from __future__ import annotations

import struct
from io import BytesIO
from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "assets" / "scadenze-ps.ico"


def make_cross(size: int) -> Image.Image:
    img = Image.new("RGBA", (size, size), (255, 255, 255, 255))
    d = ImageDraw.Draw(img)
    green = (31, 143, 116, 255)
    arm = size * 0.22
    cx = cy = size / 2
    r = max(1, int(arm / 4))
    d.rounded_rectangle(
        [cx - arm / 2, size * 0.18, cx + arm / 2, size * 0.82], radius=r, fill=green
    )
    d.rounded_rectangle(
        [size * 0.18, cy - arm / 2, size * 0.82, cy + arm / 2], radius=r, fill=green
    )
    return img


def image_to_png_bytes(img: Image.Image) -> bytes:
    buf = BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def write_ico(path: Path, sizes: list[int]) -> None:
    """ICO con PNG embedded (supportato da Windows Vista+)."""
    images = [make_cross(s) for s in sizes]
    pngs = [image_to_png_bytes(im) for im in images]

    # Header: reserved, type=1 (icon), count
    header = struct.pack("<HHH", 0, 1, len(pngs))
    # Directory entries: 16 bytes each
    offset = 6 + 16 * len(pngs)
    entries = b""
    for size, data in zip(sizes, pngs):
        w = 0 if size >= 256 else size
        h = 0 if size >= 256 else size
        entries += struct.pack("<BBBBHHII", w, h, 0, 0, 1, 32, len(data), offset)
        offset += len(data)

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(header + entries + b"".join(pngs))
    print(f"Creato {path} ({path.stat().st_size} bytes) sizes={sizes}")


if __name__ == "__main__":
    write_ico(OUT, [16, 24, 32, 48, 64, 128, 256])
