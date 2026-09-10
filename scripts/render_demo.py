from __future__ import annotations

import shutil
import subprocess
import urllib.request
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs"
FRAMES = ROOT / ".data" / "demo-frames"
FONT_DIR = ROOT / ".data" / "fonts"
W, H = 1280, 720
FPS = 12
SECONDS = 12

LAVA = (255, 54, 33)
NAVY = (27, 49, 57)
NAVY_600 = (27, 81, 98)
NAVY_700 = (20, 61, 74)
NAVY_900 = (11, 32, 38)
OAT = (249, 247, 244)
OAT_MID = (238, 237, 233)
WHITE = (255, 255, 255)
MUTED = (144, 165, 177)
BORDER = (228, 226, 221)
WARNING = (186, 123, 35)
BLUE = (34, 114, 180)
GREEN = (0, 169, 114)
SUCCESS = (70, 130, 84)
LINE = (196, 204, 214)

FONT_URLS = {
    "DMSans-Regular.ttf": "https://github.com/googlefonts/dm-fonts/raw/main/Sans/fonts/ttf/DMSans-Regular.ttf",
    "DMSans-Medium.ttf": "https://github.com/googlefonts/dm-fonts/raw/main/Sans/fonts/ttf/DMSans-Medium.ttf",
    "DMSans-Bold.ttf": "https://github.com/googlefonts/dm-fonts/raw/main/Sans/fonts/ttf/DMSans-Bold.ttf",
    "DMMono-Regular.ttf": "https://github.com/googlefonts/dm-fonts/raw/main/Mono/fonts/ttf/DMMono-Regular.ttf",
}


def ensure_fonts() -> None:
    FONT_DIR.mkdir(parents=True, exist_ok=True)
    for name, url in FONT_URLS.items():
        dest = FONT_DIR / name
        if dest.exists() and dest.stat().st_size > 1000:
            continue
        try:
            urllib.request.urlretrieve(url, dest)
        except OSError:
            continue


def font(size: int, weight: str = "regular") -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    names = {
        "regular": "DMSans-Regular.ttf",
        "medium": "DMSans-Medium.ttf",
        "bold": "DMSans-Bold.ttf",
        "mono": "DMMono-Regular.ttf",
    }
    path = FONT_DIR / names.get(weight, names["regular"])
    if path.exists():
        return ImageFont.truetype(str(path), size)
    for fallback in (
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
    ):
        if Path(fallback).exists():
            return ImageFont.truetype(fallback, size)
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


def mix(c: tuple[int, int, int], a: float, bg: tuple[int, int, int] = NAVY_900) -> tuple[int, int, int]:
    return tuple(int(lerp(bg[i], c[i], a)) for i in range(3))  # type: ignore[return-value]


def bricks(draw: ImageDraw.ImageDraw, x: int, y: int, scale: float = 1.0, a: float = 1.0, bg: tuple[int, int, int] = NAVY_900) -> None:
    w, h, gap = 18 * scale, 7 * scale, 2.5 * scale
    color = mix(LAVA, a, bg)
    draw.rectangle((x, y, x + w, y + h), fill=color)
    draw.rectangle((x + 6 * scale, y + h + gap, x + 6 * scale + w, y + 2 * h + gap), fill=color)
    draw.rectangle((x, y + 2 * (h + gap), x + w, y + 3 * h + 2 * gap), fill=color)


def card(
    draw: ImageDraw.ImageDraw,
    xy: tuple[float, float],
    w: int,
    h: int,
    kind: str,
    label: str,
    a: float,
    *,
    bg: tuple[int, int, int],
    selected: bool = False,
    swatch: tuple[int, int, int] = LAVA,
) -> None:
    x, y = xy
    fill = mix(WHITE, a, bg)
    stroke = mix(LAVA if selected else BORDER, a, bg)
    draw.rectangle((x, y, x + w, y + h), fill=fill, outline=stroke, width=2 if selected else 1)
    draw.rectangle((x, y, x + 5, y + h), fill=mix(swatch, a, bg))
    draw.text((x + 16, y + 12), kind, fill=mix(MUTED, a, bg), font=font(12), anchor="lt")
    draw.text((x + 16, y + 32), label, fill=mix(NAVY, a, bg), font=font(16, "medium"), anchor="lt")


def edge(
    draw: ImageDraw.ImageDraw,
    a: tuple[float, float],
    b: tuple[float, float],
    name: str,
    t: float,
    *,
    bg: tuple[int, int, int],
) -> None:
    if t <= 0:
        return
    x1, y1 = a
    x2, y2 = b
    x2 = lerp(x1, x2, t)
    y2 = lerp(y1, y2, t)
    draw.line((x1, y1, x2, y2), fill=mix(LINE, min(1.0, t * 1.2), bg), width=2)
    if t > 0.85:
        mx, my = (a[0] + b[0]) / 2, (a[1] + b[1]) / 2 - 10
        draw.text((mx, my), name, fill=mix(MUTED, t, bg), font=font(12, "mono"), anchor="mm")


def workspace_chrome(draw: ImageDraw.ImageDraw, pack: str) -> None:
    draw.rectangle((0, 0, 56, H), fill=OAT_MID)
    draw.line((56, 0, 56, H), fill=BORDER)
    bricks(draw, 14, 14, scale=0.85, a=1.0, bg=OAT_MID)
    for i, y in enumerate((56, 104, 152, 200)):
        box = (8, y, 48, y + 40)
        if i == 0:
            draw.rectangle(box, fill=WHITE)
            draw.rectangle((8, y, 11, y + 40), fill=LAVA)
        draw.rectangle((18, y + 12, 38, y + 28), outline=NAVY, width=1)
    draw.rectangle((56, 0, W, 48), fill=WHITE)
    draw.line((56, 48, W, 48), fill=BORDER)
    draw.text((72, 24), "quinovo", fill=NAVY, font=font(18, "medium"), anchor="lm")
    draw.rectangle((320, 10, 900, 38), fill=OAT, outline=BORDER)
    draw.text((340, 24), "Query type, id, or label", fill=MUTED, font=font(13), anchor="lm")
    draw.text((W - 86, 24), pack, fill=MUTED, font=font(12), anchor="rm")
    draw.ellipse((W - 44, 10, W - 16, 38), fill=NAVY)
    draw.text((W - 30, 24), "L", fill=WHITE, font=font(11, "medium"), anchor="mm")
    draw.rectangle((56, 48, W, 140), fill=WHITE)
    draw.line((56, 140, W, 140), fill=BORDER)
    draw.text((80, 68), "Workspace", fill=MUTED, font=font(12), anchor="lt")
    draw.text((154, 68), "Graph", fill=NAVY, font=font(12), anchor="lt")
    draw.text((80, 96), "Graph", fill=NAVY, font=font(22, "medium"), anchor="lt")
    draw.rectangle((W - 280, 96, W - 168, 128), fill=WHITE, outline=BORDER)
    draw.text((W - 224, 112), "Extend graph", fill=NAVY, font=font(12), anchor="mm")
    draw.rectangle((W - 156, 96, W - 24, 128), fill=LAVA)
    draw.text((W - 90, 112), "Run inference", fill=WHITE, font=font(12, "medium"), anchor="mm")
    draw.line((80, 138, 124, 138), fill=LAVA, width=2)
    draw.rectangle((884, 140, W, H), fill=WHITE)
    draw.line((884, 140, 884, H), fill=BORDER)


def demo_frame(t: float) -> Image.Image:
    img = Image.new("RGB", (W, H), OAT)
    d = ImageDraw.Draw(img)
    workspace_chrome(d, "Example commerce")

    pkg = (140, 280)
    person = (500, 200)
    company = (500, 410)
    product = (140, 500)
    bg = OAT

    card(d, pkg, 200, 64, "Package", "1Z999", fade(0.2, 0.9, t), bg=bg, selected=t > 5.5, swatch=LAVA)
    card(d, person, 200, 64, "Person", "Bob", fade(0.6, 1.3, t), bg=bg, swatch=BLUE)
    card(d, company, 200, 64, "Company", "Amazon", fade(1.0, 1.7, t), bg=bg, swatch=GREEN)
    card(d, product, 200, 64, "Product", "lipstick-1", fade(1.3, 2.0, t), bg=bg, swatch=NAVY_600)

    c_pkg = (pkg[0] + 200, pkg[1] + 32)
    c_person = (person[0], person[1] + 32)
    c_co = (company[0], company[1] + 32)
    c_prod = (product[0] + 100, product[1])
    c_pkg_b = (pkg[0] + 100, pkg[1] + 64)

    edge(d, c_pkg, c_person, "destined_for", fade(2.2, 3.4, t), bg=bg)
    edge(d, c_pkg, c_co, "shipped_by", fade(2.6, 3.8, t), bg=bg)
    edge(d, c_pkg_b, c_prod, "contains", fade(3.0, 4.2, t), bg=bg)

    x, y = 884, 140
    if t < 5.4:
        d.text((x + 24, y + 28), "INSPECTOR", fill=MUTED, font=font(11, "medium"), anchor="lt")
        d.text((x + 24, y + 56), "Select a node or run a query.", fill=MUTED, font=font(13), anchor="lt")
        d.text((x + 24, y + 80), "Types and links come from the pack.", fill=MUTED, font=font(13), anchor="lt")
    else:
        d.text((x + 24, y + 28), "PACKAGE", fill=MUTED, font=font(11, "medium"), anchor="lt")
        d.text((x + 24, y + 52), "1Z999", fill=NAVY, font=font(20, "medium"), anchor="lt")
        d.text((x + 24, y + 110), "INFERENCE", fill=MUTED, font=font(11, "medium"), anchor="lt")
        d.text((x + 24, y + 136), "late  →  at_risk", fill=NAVY, font=font(16), anchor="lt")
        pending = "pending  HITL  < 80%" if t < 8.0 else "asserted"
        d.text((x + 24, y + 168), pending, fill=WARNING if t < 8.0 else SUCCESS, font=font(14), anchor="lt")
        d.text((x + 24, y + 220), "RECOMMENDED ACTION", fill=MUTED, font=font(11, "medium"), anchor="lt")
        d.text((x + 24, y + 248), "notify_buyer  →  Bob", fill=NAVY, font=font(16), anchor="lt")
        if t >= 8.2:
            d.rectangle((x + 24, y + 300, x + 372, y + 344), fill=LAVA)
            d.text((x + 198, y + 322), "apply_action", fill=WHITE, font=font(15, "medium"), anchor="mm")
            d.text((x + 24, y + 372), "audited write  ·  no PATCH  ·  no SQL", fill=MUTED, font=font(12), anchor="lt")
    return img


def hero() -> Image.Image:
    img = Image.new("RGB", (W, H), NAVY_900)
    d = ImageDraw.Draw(img)
    for x in range(0, W, 48):
        d.line((x, 0, x, H), fill=NAVY, width=1)
    for y in range(0, H, 48):
        d.line((0, y, W, y), fill=NAVY, width=1)
    d.ellipse((-120, -80, 420, 360), outline=NAVY_600)
    d.ellipse((780, 280, 1480, 980), outline=NAVY_700)
    bricks(d, 64, 48, scale=1.2, a=1.0, bg=NAVY_900)
    d.text((108, 64), "quinovo", fill=OAT, font=font(22, "medium"), anchor="lt")
    d.text((64, 130), "One ontology for agents,", fill=OAT, font=font(40, "medium"), anchor="lt")
    d.text((64, 180), "apps and actions", fill=OAT, font=font(40, "medium"), anchor="lt")
    d.text(
        (64, 250),
        "Typed objects, named links, inference, and governed writes.",
        fill=MUTED,
        font=font(18),
        anchor="lt",
    )
    d.text((64, 278), "Agents may only apply_action.", fill=MUTED, font=font(18), anchor="lt")

    cards = [
        ((70, 360), "Data", "Objects + links", LAVA),
        ((340, 400), "Logic", "Typed inference", BLUE),
        ((610, 360), "Action", "Governed writes", GREEN),
        ((880, 420), "Security", "Call-time policy", (152, 16, 42)),
    ]
    for (x, y), kind, label, swatch in cards:
        d.rectangle((x + 6, y + 8, x + 246, y + 128), fill=(8, 24, 28))
        d.rectangle((x, y, x + 240, y + 120), fill=OAT)
        d.rectangle((x, y, x + 6, y + 120), fill=swatch)
        d.text((x + 20, y + 28), kind, fill=NAVY, font=font(20, "medium"), anchor="lt")
        d.text((x + 20, y + 64), label, fill=MUTED, font=font(16), anchor="lt")
        if kind == "Action":
            d.rectangle((x + 20, y + 86, x + 150, y + 108), fill=LAVA)
            d.text((x + 85, y + 97), "apply_action", fill=WHITE, font=font(11, "medium"), anchor="mm")

    d.line((310, 420, 340, 450), fill=LINE, width=2)
    d.line((580, 420, 610, 410), fill=LINE, width=2)
    d.line((850, 420, 880, 470), fill=LINE, width=2)
    d.rectangle((64, 620, 220, 660), fill=LAVA)
    d.text((142, 640), "Start with a pack", fill=WHITE, font=font(14, "medium"), anchor="mm")
    d.text((240, 640), "quinovo init ./my-world", fill=MUTED, font=font(14, "mono"), anchor="lm")
    return img


def primitives() -> Image.Image:
    img = Image.new("RGB", (1200, 640), NAVY_900)
    d = ImageDraw.Draw(img)
    bricks(d, 48, 28, scale=1.0, a=1.0, bg=NAVY_900)
    d.text((78, 36), "quinovo", fill=OAT, font=font(18, "medium"), anchor="lt")
    d.text((60, 84), "The ontology is four primitives", fill=OAT, font=font(28, "medium"), anchor="lt")
    d.text((60, 118), "If any one is missing, it is a different product.", fill=MUTED, font=font(15), anchor="lt")
    cols = [
        ("Data", "Objects, properties,\nnamed links, series.", "The digital twin.", "Without it: a wiki.", LAVA),
        ("Logic", "Rules, functions,\nforecasts, inference.", "Typed conclusions.", "Without it: pretty CRUD.", BLUE),
        ("Action", "Named transactions.\nThe only legal writes.", "Agents never PATCH.", "Without it: a semantic layer.", GREEN),
        ("Security", "Type, row, property.\nEvaluated at call time.", "Humans and agents.", "Without it: root.", (152, 16, 42)),
    ]
    for i, (title, body, punch, missing, swatch) in enumerate(cols):
        x = 48 + i * 282
        y = 160
        d.rectangle((x, y, x + 258, y + 440), fill=OAT)
        d.rectangle((x, y, x + 6, y + 440), fill=swatch)
        d.text((x + 24, y + 28), title, fill=NAVY, font=font(20, "medium"), anchor="lt")
        yy = y + 64
        for line in body.split("\n"):
            d.text((x + 24, yy), line, fill=MUTED, font=font(14), anchor="lt")
            yy += 20
        if title == "Action":
            d.rectangle((x + 54, y + 188, x + 204, y + 232), fill=LAVA)
            d.text((x + 129, y + 210), "apply_action", fill=WHITE, font=font(14, "medium"), anchor="mm")
        d.text((x + 24, y + 340), punch, fill=NAVY, font=font(13), anchor="lt")
        d.text((x + 24, y + 372), missing, fill=MUTED, font=font(12), anchor="lt")
    return img


def inference() -> Image.Image:
    img = Image.new("RGB", (1200, 640), NAVY_900)
    d = ImageDraw.Draw(img)
    bricks(d, 48, 24, scale=1.0, a=1.0, bg=NAVY_900)
    d.text((78, 32), "quinovo", fill=OAT, font=font(18, "medium"), anchor="lt")
    d.text((60, 80), "Inference on the twin", fill=OAT, font=font(26, "medium"), anchor="lt")
    d.text((60, 112), "Forecasts become facts. Facts plus links become recommended actions.", fill=MUTED, font=font(15), anchor="lt")
    card(d, (80, 180), 200, 72, "Package", "1Z999", 1.0, bg=NAVY_900, selected=True, swatch=LAVA)
    card(d, (500, 140), 200, 72, "Person", "Bob", 1.0, bg=NAVY_900, swatch=BLUE)
    card(d, (500, 300), 200, 72, "Company", "Amazon", 1.0, bg=NAVY_900, swatch=GREEN)
    card(d, (80, 380), 200, 72, "Product", "lipstick-1", 1.0, bg=NAVY_900, swatch=NAVY_600)
    edge(d, (280, 216), (500, 176), "destined_for", 1.0, bg=NAVY_900)
    edge(d, (280, 230), (500, 336), "shipped_by", 1.0, bg=NAVY_900)
    edge(d, (180, 252), (180, 380), "contains", 1.0, bg=NAVY_900)
    x, y = 800, 160
    d.rectangle((x, y, x + 340, y + 360), fill=OAT)
    d.text((x + 28, y + 28), "INFERENCE", fill=MUTED, font=font(12, "medium"), anchor="lt")
    d.text((x + 28, y + 64), "late forecast  →  at_risk", fill=NAVY, font=font(16), anchor="lt")
    d.text((x + 28, y + 96), "confidence < 0.8  →  pending HITL", fill=WARNING, font=font(14), anchor="lt")
    d.text((x + 28, y + 150), "RECOMMENDED ACTION", fill=MUTED, font=font(12, "medium"), anchor="lt")
    d.text((x + 28, y + 184), "notify_buyer  →  Bob", fill=NAVY, font=font(16), anchor="lt")
    d.rectangle((x + 28, y + 230, x + 312, y + 274), fill=LAVA)
    d.text((x + 170, y + 252), "apply_action", fill=WHITE, font=font(15, "medium"), anchor="mm")
    d.text((x + 28, y + 310), "Audited. No SQL. No PATCH.", fill=MUTED, font=font(12), anchor="lt")
    return img


def encode_demo(frames_dir: Path) -> None:
    mp4 = OUT / "demo.mp4"
    gif = OUT / "demo.gif"
    subprocess.run(
        [
            "ffmpeg", "-y", "-framerate", str(FPS), "-i", str(frames_dir / "f%03d.png"),
            "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "22", str(mp4),
        ],
        check=True,
        capture_output=True,
    )
    palette = frames_dir / "palette.png"
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
    print(mp4, mp4.stat().st_size)
    print(gif, gif.stat().st_size)


def main() -> None:
    ensure_fonts()
    OUT.mkdir(parents=True, exist_ok=True)
    hero().save(OUT / "hero.png")
    primitives().save(OUT / "four-primitives.png")
    inference().save(OUT / "inference.png")
    print(OUT / "hero.png")
    print(OUT / "four-primitives.png")
    print(OUT / "inference.png")

    if FRAMES.exists():
        shutil.rmtree(FRAMES)
    FRAMES.mkdir(parents=True)
    total = FPS * SECONDS
    for i in range(total):
        t = i / FPS
        demo_frame(t).save(FRAMES / f"f{i:03d}.png")
    encode_demo(FRAMES)
    shutil.rmtree(FRAMES)


if __name__ == "__main__":
    main()
