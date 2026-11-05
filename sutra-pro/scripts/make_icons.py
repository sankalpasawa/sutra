#!/usr/bin/env python3
"""Draw the Sutra Pro icon and write every size the apps need (D102). The outputs are committed; this runs only when the drawing changes.

    uv run --no-project --with pillow python scripts/make_icons.py            # writes assets/icon/ and sutra_app/assets/icon.png
    uv run --no-project --with pillow python scripts/make_icons.py --check    # exit 1 when the committed files are not what this draws

The icon is a thread (sutra means thread) that makes an S through three nodes, on a rounded square: the app is a chat on top of an
org chart whose nodes are joined by threads. The drawing is deterministic: the same Pillow gives the same bytes for the PNG, and the
.icns is made from those PNGs with macOS `iconutil` when it exists (a Mac); elsewhere an existing .icns is left alone.
"""
from __future__ import annotations

import argparse
import math
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "assets" / "icon"
TRAY = ROOT / "sutra_app" / "assets" / "icon.png"
MASTER = 1024
SUPER = 2                                   # draw at 2x and shrink: smooth edges without a vector library
ICO_SIZES = (16, 24, 32, 48, 64, 128, 256)
ICONSET = {"icon_16x16.png": 16, "icon_16x16@2x.png": 32, "icon_32x32.png": 32, "icon_32x32@2x.png": 64, "icon_128x128.png": 128,
           "icon_128x128@2x.png": 256, "icon_256x256.png": 256, "icon_256x256@2x.png": 512, "icon_512x512.png": 512,
           "icon_512x512@2x.png": 1024}
TOP, BOTTOM = (46, 38, 132), (124, 77, 255)         # deep indigo to violet
THREAD, NODE = (255, 255, 255), (255, 214, 102)


def draw_master() -> Image.Image:
    size = MASTER * SUPER
    # the background: a vertical gradient, then rounded to the macOS-style squircle-ish radius
    gradient = Image.new("RGB", (size, size))
    px = gradient.load()
    for y in range(size):
        t = y / (size - 1)
        row = tuple(round(TOP[i] + (BOTTOM[i] - TOP[i]) * t) for i in range(3))
        for x in range(size):
            px[x, y] = row
    mask = Image.new("L", (size, size), 0)
    margin = round(size * 0.06)
    ImageDraw.Draw(mask).rounded_rectangle((margin, margin, size - margin, size - margin), radius=round(size * 0.225), fill=255)
    canvas = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    canvas.paste(gradient, (0, 0), mask)

    # the thread: x = 0.5 + 0.2 cos(1.5 pi t) while y runs from 0.24 to 0.76 makes an S, a node at each end and one in the middle
    draw = ImageDraw.Draw(canvas)
    points = []
    steps = 2400
    for i in range(steps + 1):
        t = i / steps
        points.append((size * (0.5 + 0.2 * math.cos(3 * math.pi * t)), size * (0.24 + 0.52 * t)))
    width = round(size * 0.075)
    for x, y in points:                                       # a round brush stamped along the path: a smooth stroke, round caps
        draw.ellipse((x - width / 2, y - width / 2, x + width / 2, y + width / 2), fill=THREAD)
    for x, y in (points[0], points[steps // 2], points[-1]):  # the nodes
        r = size * 0.058
        draw.ellipse((x - r, y - r, x + r, y + r), fill=NODE, outline=THREAD, width=round(size * 0.012))
    return canvas.resize((MASTER, MASTER), Image.LANCZOS)


def files(master: Image.Image, work: Path) -> dict[Path, bytes]:
    """Every file this script owns, by path, as bytes, except the .icns (iconutil writes that one)."""
    out: dict[Path, bytes] = {}
    from io import BytesIO

    def png(img: Image.Image) -> bytes:
        buf = BytesIO()
        img.save(buf, "PNG", optimize=True)
        return buf.getvalue()

    out[OUT / "sutra-pro-1024.png"] = png(master)
    ico = BytesIO()
    master.save(ico, "ICO", sizes=[(s, s) for s in ICO_SIZES])
    out[OUT / "sutra-pro.ico"] = ico.getvalue()
    out[TRAY] = png(master.resize((256, 256), Image.LANCZOS))
    iconset = work / "sutra-pro.iconset"
    iconset.mkdir(parents=True)
    for name, px_size in ICONSET.items():
        (iconset / name).write_bytes(png(master.resize((px_size, px_size), Image.LANCZOS)))
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Draw the Sutra Pro icon.")
    parser.add_argument("--check", action="store_true", help="compare with the committed files instead of writing")
    args = parser.parse_args(argv)
    master = draw_master()
    with tempfile.TemporaryDirectory() as tmp:
        work = Path(tmp)
        produced = files(master, work)
        icns = OUT / "sutra-pro.icns"
        built_icns = None
        if shutil.which("iconutil"):
            built_icns = work / "sutra-pro.icns"
            subprocess.run(["iconutil", "-c", "icns", str(work / "sutra-pro.iconset"), "-o", str(built_icns)], check=True)
        if args.check:
            stale = [str(p.relative_to(ROOT)) for p, data in produced.items() if not p.is_file() or p.read_bytes() != data]
            if not icns.is_file():
                stale.append(str(icns.relative_to(ROOT)))
            for name in stale:
                print(f"stale or missing: {name}")
            return 1 if stale else 0
        for path, data in produced.items():
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
            print("wrote", path.relative_to(ROOT), f"({len(data)} bytes)")
        if built_icns is not None:
            shutil.copyfile(built_icns, icns)
            print("wrote", icns.relative_to(ROOT), f"({icns.stat().st_size} bytes)")
        elif not icns.is_file():
            print("no iconutil here and no committed .icns: run this on a Mac", file=sys.stderr)
            return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
