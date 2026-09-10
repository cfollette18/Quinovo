"""Rasterize the Quinovo mark to PNGs using the same geometry as logo.svg.

Uses Pillow (already in the environment). No SVG renderer is available, so we
re-draw the mark with PIL primitives at the target sizes. This keeps the
rasters pixel-identical to the hand-authored SVG geometry.
"""
from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw

NAVY = (27, 49, 57, 255)        # #1B3139
RED = (255, 54, 33, 255)        # #FF3621
OAT = (249, 247, 244, 255)      # #f9f7f4
TRANSPARENT = (0, 0, 0, 0)

ASSETS = Path(__file__).resolve().parent


def _scale(size: int) -> float:
    return size / 64.0


def _draw_mark(draw: ImageDraw.ImageDraw, size: int, *, ring: tuple, focal: tuple,
               tail: tuple, ring_w: float = 3.5, tail_w: float = 4.0) -> None:
    """Draw the Quinovo knot-Q mark in a `size`x`size` canvas (64-unit geometry)."""
    s = _scale(size)
    # Ring of edges (diamond).
    pts = [(32, 14), (50, 32), (32, 50), (14, 32), (32, 14)]
    scaled = [(round(x * s), round(y * s)) for x, y in pts]
    for i in range(len(scaled) - 1):
        draw.line([scaled[i], scaled[i + 1]], fill=ring, width=max(1, round(ring_w * s)))
    # Nodes (10x10 squares centered on the diamond points).
    nodes = [
        (27, 9, focal),    # top -- red focal
        (45, 27, ring),    # right
        (27, 45, ring),    # bottom
        (9, 27, ring),     # left
    ]
    for x, y, col in nodes:
        draw.rectangle([round(x * s), round(y * s),
                        round((x + 10) * s), round((y + 10) * s)], fill=col)
    # Q-tail.
    draw.line([(round(40 * s), round(40 * s)), (round(56 * s), round(56 * s))],
              fill=tail, width=max(1, round(tail_w * s)))


def make_plain(path: Path, size: int) -> None:
    img = Image.new("RGBA", (size, size), TRANSPARENT)
    _draw_mark(ImageDraw.Draw(img), size, ring=NAVY, focal=RED, tail=NAVY)
    img.save(path)


def make_tile(path: Path, size: int) -> None:
    """Favicon / apple-touch style: navy rounded tile, oat mark, red focal."""
    img = Image.new("RGBA", (size, size), TRANSPARENT)
    draw = ImageDraw.Draw(img)
    s = _scale(size)
    radius = round(12 * s)
    draw.rounded_rectangle([0, 0, size - 1, size - 1], radius=radius, fill=NAVY)
    _draw_mark(draw, size, ring=OAT, focal=RED, tail=OAT)
    img.save(path)


if __name__ == "__main__":
    make_plain(ASSETS / "logo.png", 512)
    make_tile(ASSETS / "favicon-32.png", 32)
    make_tile(ASSETS / "apple-touch-icon.png", 180)
    print("wrote logo.png, favicon-32.png, apple-touch-icon.png")
