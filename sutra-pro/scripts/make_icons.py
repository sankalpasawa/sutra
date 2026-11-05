#!/usr/bin/env python3
"""Derive every Sutra Pro icon from the old Sutra's: the logo is the same (D106). The outputs are committed; this runs only when the old icon changes.

    uv run --no-project --with pillow python scripts/make_icons.py            # writes assets/icon/ and sutra_app/assets/icon.png
    uv run --no-project --with pillow python scripts/make_icons.py --check    # exit 1 when a committed file is not what this derives

The old product's icon is `marketplace/plugin/sutra-ui/electron/build/Sutra.icns` (the file inside the installed Sutra.app): a black rounded
square with the gold lotus mark. Nothing is redrawn here:

    assets/icon/sutra-pro.icns       the old file, byte for byte (what the Mac app and the DMG carry)
    assets/icon/sutra-pro-1024.png   its 1024 px chunk (`ic10`), byte for byte
    assets/icon/sutra-pro.ico        that PNG at 16, 24, 32, 48, 64, 128 and 256 px (what the Windows exe, installer and shortcuts carry)
    sutra_app/assets/icon.png        that PNG at 256 px (the window and tray icon of the apps)

Outside this repository (an sdist) the old icon is not there; the committed `sutra-pro.icns` is then the source, so the derived files can
still be checked. With the old icon present, `--check` also fails when `sutra-pro.icns` differs from it: the two products keep one logo.
"""
from __future__ import annotations

import argparse
import struct
import sys
from io import BytesIO
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "assets" / "icon"
ICNS = OUT / "sutra-pro.icns"
MASTER_PNG = OUT / "sutra-pro-1024.png"
ICO = OUT / "sutra-pro.ico"
TRAY = ROOT / "sutra_app" / "assets" / "icon.png"
OLD_LOGO = ROOT.parent / "marketplace" / "plugin" / "sutra-ui" / "electron" / "build" / "Sutra.icns"
MASTER_CHUNK = "ic10"                       # the 1024 x 1024 PNG (512 pt at 2x) inside an .icns
MASTER = 1024
TRAY_SIZE = 256
ICO_SIZES = (16, 24, 32, 48, 64, 128, 256)
PNG_MAGIC = b"\x89PNG\r\n\x1a\n"


def icns_chunks(data: bytes) -> dict[str, bytes]:
    """The chunks of an .icns file by their four-letter type: a header (`icns`, the total length), then (type, length incl. 8, data) records."""
    if data[:4] != b"icns" or len(data) < 8 or struct.unpack(">I", data[4:8])[0] != len(data):
        raise ValueError("not an .icns file (bad header or length)")
    chunks: dict[str, bytes] = {}
    position = 8
    while position + 8 <= len(data):
        kind = data[position:position + 4].decode("ascii", "replace")
        length = struct.unpack(">I", data[position + 4:position + 8])[0]
        if length < 8 or position + length > len(data):
            raise ValueError(f"the {kind!r} chunk has a bad length")
        chunks[kind] = data[position + 8:position + length]
        position += length
    return chunks


def master_png(icns: bytes) -> bytes:
    """The 1024 px PNG of the icon, as stored (not re-encoded)."""
    png = icns_chunks(icns).get(MASTER_CHUNK, b"")
    if png[:8] != PNG_MAGIC or struct.unpack(">II", png[16:24]) != (MASTER, MASTER):
        raise ValueError(f"the icon has no {MASTER} px PNG chunk ({MASTER_CHUNK})")
    return png


def derive(icns: bytes) -> dict[Path, bytes]:
    """Every file this script owns, by path, as bytes (the .icns itself included)."""
    from PIL import Image                                       # only here: reading and checking the committed files needs no Pillow
    png = master_png(icns)
    image = Image.open(BytesIO(png)).convert("RGBA")
    ico = BytesIO()
    image.save(ico, "ICO", sizes=[(size, size) for size in ICO_SIZES])
    tray = BytesIO()
    image.resize((TRAY_SIZE, TRAY_SIZE), Image.LANCZOS).save(tray, "PNG", optimize=True)
    return {ICNS: icns, MASTER_PNG: png, ICO: ico.getvalue(), TRAY: tray.getvalue()}


def same_pixels(path: Path, data: bytes) -> bool:
    """True when the committed image file shows the same picture as `data` (an encoder may order bytes differently; the pictures must match)."""
    from PIL import Image
    try:
        committed, derived = Image.open(path), Image.open(BytesIO(data))
        if path.suffix == ".ico":
            if sorted(committed.ico.sizes()) != sorted(derived.ico.sizes()):
                return False
            return all(committed.ico.getimage(s).convert("RGBA").tobytes() == derived.ico.getimage(s).convert("RGBA").tobytes()
                       for s in committed.ico.sizes())
        return committed.size == derived.size and committed.convert("RGBA").tobytes() == derived.convert("RGBA").tobytes()
    except (OSError, ValueError):
        return False


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Derive the Sutra Pro icons from the old Sutra icon.")
    parser.add_argument("--check", action="store_true", help="compare with the committed files instead of writing")
    args = parser.parse_args(argv)
    if OLD_LOGO.is_file():
        source, where = OLD_LOGO.read_bytes(), str(OLD_LOGO.relative_to(ROOT.parent))
    elif ICNS.is_file():
        source, where = ICNS.read_bytes(), str(ICNS.relative_to(ROOT))
    else:
        print(f"no source icon: neither {OLD_LOGO} nor {ICNS} exists", file=sys.stderr)
        return 1
    try:
        produced = derive(source)
    except ValueError as error:
        print(f"{where}: {error}", file=sys.stderr)
        return 1
    if args.check:
        stale = []
        for path, data in produced.items():
            if not path.is_file():
                stale.append(path)
            elif path in (ICNS, MASTER_PNG):
                if path.read_bytes() != data:
                    stale.append(path)
            elif not same_pixels(path, data):
                stale.append(path)
        for path in stale:
            print(f"stale or missing: {path.relative_to(ROOT)} (derived from {where})")
        return 1 if stale else 0
    for path, data in produced.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        print("wrote", path.relative_to(ROOT), f"({len(data)} bytes)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
