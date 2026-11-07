"""The logo of Sutra Pro is the logo of the old Sutra (D117): every icon is derived from the old product's `Sutra.icns`, none is redrawn.

The files are checked by their bytes (no Pillow needed); `scripts/make_icons.py --check` compares the pictures when Pillow is there.
"""
import importlib.util
import struct
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
ICONS = ROOT / "assets" / "icon"
TRAY = ROOT / "sutra_app" / "assets" / "icon.png"
OLD_LOGO = ROOT.parent / "marketplace" / "plugin" / "sutra-ui" / "electron" / "build" / "Sutra.icns"
SCRIPT = ROOT / "scripts" / "make_icons.py"
PNG = b"\x89PNG\r\n\x1a\n"

_spec = importlib.util.spec_from_file_location("make_icons", SCRIPT)
make_icons = importlib.util.module_from_spec(_spec)
sys.modules["make_icons"] = make_icons
_spec.loader.exec_module(make_icons)


def test_the_mac_icon_is_the_old_sutra_icon_byte_for_byte():
    if not OLD_LOGO.is_file():
        pytest.skip("the old product's icon is not in this checkout (an sdist)")
    assert (ICONS / "sutra-pro.icns").read_bytes() == OLD_LOGO.read_bytes(), "run scripts/make_icons.py: the two products keep one logo"


def test_the_large_png_is_the_1024_chunk_of_that_icns():
    chunks = make_icons.icns_chunks((ICONS / "sutra-pro.icns").read_bytes())
    master = (ICONS / "sutra-pro-1024.png").read_bytes()
    assert master == chunks["ic10"] and master[:8] == PNG and struct.unpack(">II", master[16:24]) == (1024, 1024)


def test_the_windows_icon_holds_every_size_the_shell_asks_for():
    ico = (ICONS / "sutra-pro.ico").read_bytes()
    reserved, kind, count = struct.unpack("<HHH", ico[:6])
    assert (reserved, kind) == (0, 1)
    sizes = set()
    for index in range(count):
        width, height = struct.unpack("<BB", ico[6 + 16 * index:8 + 16 * index])
        sizes.add((width or 256, height or 256))              # 0 means 256 in an ICO directory
    assert sizes == {(s, s) for s in make_icons.ICO_SIZES}


def test_the_window_icon_is_the_256_px_png_of_the_same_picture():
    data = TRAY.read_bytes()
    assert data[:8] == PNG and struct.unpack(">II", data[16:24]) == (256, 256)


def test_the_icns_reader_refuses_what_is_not_an_icns_and_a_chunk_that_overruns():
    with pytest.raises(ValueError):
        make_icons.icns_chunks(b"not an icns file")
    good = (ICONS / "sutra-pro.icns").read_bytes()
    with pytest.raises(ValueError):
        make_icons.icns_chunks(good[:-1])                      # the declared length no longer matches
    broken = bytearray(b"icns" + struct.pack(">I", 16) + b"ic10" + struct.pack(">I", 999))
    with pytest.raises(ValueError):
        make_icons.icns_chunks(bytes(broken))                  # a chunk longer than the file
    with pytest.raises(ValueError):
        make_icons.master_png(b"icns" + struct.pack(">I", 8))   # no ic10 chunk at all


def test_every_derived_file_is_what_the_script_derives():
    pytest.importorskip("PIL")
    done = subprocess.run([sys.executable, str(SCRIPT), "--check"], capture_output=True, text=True, timeout=120)
    assert done.returncode == 0, done.stdout + done.stderr
