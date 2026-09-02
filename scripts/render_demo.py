from __future__ import annotations

import math
import shutil
import subprocess
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs"
FRAMES = ROOT / ".data" / "demo-frames"
W, H = 1280, 720
BG = (14, 14, 14)
GOLD = (212, 160, 23)
CREAM = (238, 238, 238)
MUTED = (154, 154, 154)
CARD = (22, 22, 22)
LINE = (42, 42, 42)
FPS = 12
SECONDS = 12


def font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    for path in (
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
    ):
        if Path(path).exists():
            return ImageFont.truetype(path, size)
    return ImageFont.load_default()


def lerp(a: float, b: float, t: float) -> float:
    t = max(0.0, min(1.0, t))
    return a + (b - a) * t


def fade(t0: float, t1: float, t: float) -> float:
    if t < t0:
        return 0.0
    if t > t1:
        return 1.0
    return (t - t0) / (t1 - t0)


def mix(c: tuple[int, int, int], a: float) -> tuple[int, int, int]:
    return tuple(int(lerp(BG[i], c[i], a)) for i in range(3))  # type: ignore[return-value]


def card(draw: ImageDraw.ImageDraw, xy: tuple[int, int], w: int, h: int, title: str, label: str, a: float, selected: bool = False) -> None:
    x, y = xy
    stroke = GOLD if selected else LINE
    draw.rounded_rectangle((x, y, x + w, y + h), 10, fill=mix(CARD, a), outline=mix(stroke, a), width=2)
    draw.text((x + w / 2, y + 22), title, fill=mix(MUTED, a), font=font(14), anchor="mm")
    draw.text((x + w / 2, y + 52), label, fill=mix(CREAM, a), font=font(22), anchor="mm")


def edge(draw: ImageDraw.ImageDraw, a: tuple[float, float], b: tuple[float, float], name: str, t: float) -> None:
    if t <= 0:
        return
    x1, y1 = a
    x2, y2 = b
    x2 = lerp(x1, x2, t)
    y2 = lerp(y1, y2, t)
    draw.line((x1, y1, x2, y2), fill=GOLD, width=2)
    if t > 0.85:
        mx, my = (a[0] + b[0]) / 2, (a[1] + b[1]) / 2 - 10
        draw.text((mx, my), name, fill=GOLD, font=font(13), anchor="mm")


def frame(t: float) -> Image.Image:
    img = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(img)
    d.text((64, 40), "quinovo", fill=CREAM, font=font(28), anchor="lt")
    d.text((64, 76), "operational ontology", fill=GOLD, font=font(16), anchor="lt")

    pkg = (160, 250)
    person = (560, 140)
    company = (560, 360)
    product = (160, 470)

    a_pkg = fade(0.6, 1.4, t)
    a_person = fade(1.2, 2.0, t)
    a_co = fade(1.6, 2.4, t)
    a_prod = fade(2.0, 2.8, t)
    card(d, pkg, 220, 88, "Package", "1Z999", a_pkg, selected=t > 6)
    card(d, person, 220, 88, "Person", "Bob", a_person)
    card(d, company, 220, 88, "Company", "Amazon", a_co)
    card(d, product, 220, 88, "Product", "lipstick-1", a_prod)

    c_pkg = (pkg[0] + 220, pkg[1] + 44)
    c_person = (person[0], person[1] + 44)
    c_co = (company[0], company[1] + 44)
    c_prod = (product[0] + 110, product[1])
    c_pkg_b = (pkg[0] + 110, pkg[1] + 88)

    edge(d, c_pkg, c_person, "destined_for", fade(3.0, 4.2, t))
    edge(d, c_pkg, c_co, "shipped_by", fade(3.4, 4.6, t))
    edge(d, c_pkg_b, c_prod, "contains", fade(3.8, 5.0, t))

    panel_a = fade(5.4, 6.4, t)
    if panel_a:
        x, y, w, h = 860, 160, 360, 400
        d.rectangle((x, y, x + w, y + h), fill=mix(CARD, panel_a), outline=mix(LINE, panel_a))
        d.text((x + 24, y + 28), "INFERENCE", fill=mix(MUTED, panel_a), font=font(13), anchor="lt")
        d.text((x + 24, y + 70), "late → at_risk", fill=mix(CREAM, panel_a), font=font(22), anchor="lt")
        pending = "pending  HITL  < 80%" if t < 8.2 else "asserted"
        d.text((x + 24, y + 110), pending, fill=mix((201, 162, 39) if t < 8.2 else GOLD, panel_a), font=font(16), anchor="lt")
        d.text((x + 24, y + 170), "RECOMMENDED ACTION", fill=mix(MUTED, panel_a), font=font(13), anchor="lt")
        d.text((x + 24, y + 210), "notify_buyer → Bob", fill=mix(CREAM, panel_a), font=font(20), anchor="lt")
        btn_a = fade(8.4, 9.2, t)
        if btn_a:
            d.rectangle((x + 24, y + 270, x + 336, y + 322), fill=mix(GOLD, btn_a))
            d.text((x + 180, y + 296), "apply_action", fill=mix(BG, btn_a), font=font(18), anchor="mm")
            d.text((x + 24, y + 350), "audited write  ·  no PATCH  ·  no SQL", fill=mix(MUTED, btn_a), font=font(13), anchor="lt")

    pulse = 0.5 + 0.5 * math.sin(t * 3)
    d.ellipse((W - 48, 36, W - 32, 52), fill=mix(GOLD, 0.4 + 0.6 * pulse))
    return img


def main() -> None:
    if FRAMES.exists():
        shutil.rmtree(FRAMES)
    FRAMES.mkdir(parents=True)
    total = FPS * SECONDS
    for i in range(total):
        t = i / FPS
        frame(t).save(FRAMES / f"f{i:03d}.png")
    mp4 = OUT / "demo.mp4"
    gif = OUT / "demo.gif"
    OUT.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [
            "ffmpeg", "-y", "-framerate", str(FPS), "-i", str(FRAMES / "f%03d.png"),
            "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "22", str(mp4),
        ],
        check=True,
        capture_output=True,
    )
    palette = FRAMES / "palette.png"
    subprocess.run(
        [
            "ffmpeg", "-y", "-i", str(mp4), "-vf", "fps=10,scale=960:-1:flags=lanczos,palettegen",
            str(palette),
        ],
        check=True,
        capture_output=True,
    )
    subprocess.run(
        [
            "ffmpeg", "-y", "-i", str(mp4), "-i", str(palette),
            "-filter_complex", "fps=10,scale=960:-1:flags=lanczos[x];[x][1:v]paletteuse",
            str(gif),
        ],
        check=True,
        capture_output=True,
    )
    shutil.rmtree(FRAMES)
    print(mp4, mp4.stat().st_size)
    print(gif, gif.stat().st_size)


if __name__ == "__main__":
    main()
