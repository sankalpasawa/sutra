#!/usr/bin/env python3
"""Derive the icon of "Sutra Pro Beta" from the stable app's icon: the same picture with an orange corner band that says BETA (D242).

    uv run --no-project --with pillow python scripts/make_beta_icon.py            # writes assets/icon/sutra-pro-beta-1024.png, sutra-pro-beta.icns and the
                                                                                    # Windows pair sutra-pro-beta-windows-1024.png, sutra-pro-beta-windows.ico
    python scripts/make_beta_icon.py --check                                      # stdlib only: exit 1 when a committed file is not a sound beta icon

Both apps can be installed and open on one Mac, so the Dock must tell them apart at a glance. Nothing else of the logo changes: the band is clipped to the
stable icon's own outline. The outputs are committed; this runs only when the stable icon changes (scripts/make_icons.py), and a different Pillow may
draw the letters a pixel differently, which is why --check looks at the structure of the files (an .icns whose 1024 px chunk is the committed PNG, the
sizes a Mac asks for) and not at their pixels.
"""
from __future__ import annotations

import argparse
import struct
import sys
from io import BytesIO
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import make_icons as stable                                                   # noqa: E402  (the .icns reader and the stable icon's paths)

OUT = stable.OUT
BETA_PNG = OUT / "sutra-pro-beta-1024.png"
BETA_ICNS = OUT / "sutra-pro-beta.icns"
WINDOWS_PNG = OUT / "sutra-pro-windows-1024.png"                              # the Windows app's own picture (hand-made, see make_icons.py)
BETA_WINDOWS_PNG = OUT / "sutra-pro-beta-windows-1024.png"
BETA_WINDOWS_ICO = OUT / "sutra-pro-beta-windows.ico"
ICO_SIZES = (16, 24, 32, 48, 64, 128, 256)
ICO_MAGIC = bytes((0, 0, 1, 0))                                               # reserved 0, type 1 (an icon)
# the PNG chunks of an .icns: type -> pixel size (what `iconutil` writes for an iconset, plus the three small ones older systems read)
CHUNKS = {"icp4": 16, "icp5": 32, "icp6": 64, "ic07": 128, "ic08": 256, "ic09": 512, "ic10": 1024,
          "ic11": 32, "ic12": 64, "ic13": 256, "ic14": 512}
ORANGE = (242, 140, 40, 255)
INK = (255, 255, 255, 255)
BAND = (1500, 1790)            # the band covers the points whose x + y lies between these (the corner is 2048)


def band_image(base):
    """`base` (the stable icon, RGBA) with the BETA band across its lower right corner, clipped to the icon's own outline."""
    from PIL import Image, ImageChops, ImageDraw, ImageFont
    size = base.size[0]
    scale = size / 1024
    low, high = BAND[0] * scale, BAND[1] * scale
    layer = Image.new("RGBA", base.size, (0, 0, 0, 0))
    # the strip between the lines x + y = low and x + y = high, which meet the right edge at y = c - size and the bottom edge at x = c - size
    ImageDraw.Draw(layer).polygon([(size, low - size), (size, high - size), (high - size, size), (low - size, size)], fill=ORANGE)
    # the letters are drawn upright on a layer of their own, turned to run along the band (up and to the right), and centred on its middle line
    letters = Image.new("RGBA", (int(460 * scale), int(170 * scale)), (0, 0, 0, 0))
    font = ImageFont.load_default(size=int(118 * scale))
    ImageDraw.Draw(letters).text((letters.width / 2, letters.height / 2), "BETA", font=font, fill=INK, anchor="mm",
                                 stroke_width=max(1, int(4 * scale)), stroke_fill=INK)
    turned = letters.rotate(45, expand=True, resample=Image.BICUBIC)
    middle = (low + high) / 4                                                 # the point of the middle line that lies on the diagonal: x = y = (low + high) / 4
    layer.alpha_composite(turned, (int(middle - turned.width / 2), int(middle - turned.height / 2)))
    layer.putalpha(ImageChops.multiply(layer.getchannel("A"), base.getchannel("A")))     # never past the rounded corner
    result = base.copy()
    result.alpha_composite(layer)
    return result


def icns_of(png_at) -> bytes:
    """An .icns file from `png_at(size)` -> PNG bytes: a header, then a (type, length, data) record per size."""
    body = b""
    for kind, size in CHUNKS.items():
        data = png_at(size)
        body += kind.encode("ascii") + struct.pack(">I", len(data) + 8) + data
    return b"icns" + struct.pack(">I", len(body) + 8) + body


def derive() -> dict[Path, bytes]:
    from PIL import Image
    base = Image.open(stable.MASTER_PNG).convert("RGBA")
    master = band_image(base)

    def png_at(size: int) -> bytes:
        out = BytesIO()
        (master if size == base.size[0] else master.resize((size, size), Image.LANCZOS)).save(out, "PNG", optimize=True)
        return out.getvalue()

    png = png_at(1024)
    windows = band_image(Image.open(WINDOWS_PNG).convert("RGBA"))             # the Windows beta (D432): the band over the Windows picture
    windows_png, ico = BytesIO(), BytesIO()
    windows.save(windows_png, "PNG", optimize=True)
    windows.save(ico, "ICO", sizes=[(size, size) for size in ICO_SIZES])
    return {BETA_PNG: png, BETA_ICNS: icns_of(png_at), BETA_WINDOWS_PNG: windows_png.getvalue(), BETA_WINDOWS_ICO: ico.getvalue()}


def problems(png_path: Path = BETA_PNG, icns_path: Path = BETA_ICNS) -> list[str]:
    """What is wrong with the committed beta icon, as sentences (stdlib only; empty when it is sound)."""
    found: list[str] = []
    for path in (png_path, icns_path):
        if not path.is_file():
            found.append(f"{path.name} is missing: run scripts/make_beta_icon.py")
    if found:
        return found
    png = png_path.read_bytes()
    if png[:8] != stable.PNG_MAGIC or struct.unpack(">II", png[16:24]) != (1024, 1024):
        found.append(f"{png_path.name} is not a 1024 x 1024 PNG")
    try:
        chunks = stable.icns_chunks(icns_path.read_bytes())
    except ValueError as error:
        return found + [f"{icns_path.name}: {error}"]
    missing = sorted(set(CHUNKS) - set(chunks))
    if missing:
        found.append(f"{icns_path.name} lacks the chunks {', '.join(missing)}")
    elif chunks["ic10"] != png:
        found.append(f"{icns_path.name}'s 1024 px chunk is not {png_path.name}")
    for kind, size in CHUNKS.items():
        data = chunks.get(kind, b"")
        if data and (data[:8] != stable.PNG_MAGIC or struct.unpack(">II", data[16:24]) != (size, size)):
            found.append(f"the {kind} chunk of {icns_path.name} is not a {size} px PNG")
    if png == stable.MASTER_PNG.read_bytes():
        found.append("the beta icon is the stable icon: nothing tells the two apps apart in the Dock")
    if png_path == BETA_PNG:                                                  # the committed set: the Windows beta icon as well
        for path in (BETA_WINDOWS_PNG, BETA_WINDOWS_ICO):
            if not path.is_file():
                found.append(f"{path.name} is missing: run scripts/make_beta_icon.py")
        if not found:
            if BETA_WINDOWS_ICO.read_bytes()[:4] != ICO_MAGIC:
                found.append(f"{BETA_WINDOWS_ICO.name} is not an .ico file")
            if BETA_WINDOWS_PNG.read_bytes() == WINDOWS_PNG.read_bytes():
                found.append("the Windows beta icon is the Windows stable icon: nothing tells the two apps apart in the taskbar")
    return found


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Derive the icon of Sutra Pro Beta from the stable icon.")
    parser.add_argument("--check", action="store_true", help="check the committed files (stdlib only) instead of writing them")
    args = parser.parse_args(argv)
    if args.check:
        found = problems()
        for line in found:
            print(f"error: {line}", file=sys.stderr)
        print("beta icon: ok" if not found else f"beta icon: {len(found)} problem(s)")
        return 1 if found else 0
    for path, data in derive().items():
        path.write_bytes(data)
        print(f"wrote {path.relative_to(stable.ROOT)} ({len(data)} bytes)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
