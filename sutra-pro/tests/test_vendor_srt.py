"""The vendored srt (D462): scripts/vendor_srt.py extracts safely, patches by anchor (S1, S2) and checks offline."""
import io
import sys
import tarfile
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))
import vendor_srt  # noqa: E402
from vendor_j2 import VendorError  # noqa: E402


def tgz(members):
    """An in-memory .tgz: members are (name, bytes) for a file, (name, None, linkname) for a symlink."""
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as t:
        for m in members:
            info = tarfile.TarInfo(m[0])
            if m[1] is None:
                info.type, info.linkname = tarfile.SYMTYPE, m[2]
                t.addfile(info)
            else:
                info.size, info.mode = len(m[1]), (m[2] if len(m) > 2 else 0o644)
                t.addfile(info, io.BytesIO(m[1]))
    return buf.getvalue()


HTTP = b"a\n            upstream.on('close', () => socket.destroy());\nb\n"
SOCKS = b"c\n            upstream.on('close', () => conn.socket.destroy());\nd\n"


def fake_registry(monkeypatch, http=HTTP):
    srt = tgz([("package/LICENSE", b"Apache-2.0\n"), ("package/dist/cli.js", b"main()\n", 0o755),
               ("package/dist/sandbox/http-proxy.js", http), ("package/dist/sandbox/socks-proxy.js", SOCKS)])
    dep = tgz([("package/index.js", b"x\n"), ("package/.github/ci.yml", b"y\n")])
    blobs = {"u:srt": srt, "u:dep": dep}
    monkeypatch.setattr(vendor_srt, "PINS", ((vendor_srt.SRT, "0.0.83", "u:srt", vendor_srt.integrity(srt)),
                                             ("dep", "1.0.0", "u:dep", vendor_srt.integrity(dep))))
    monkeypatch.setattr(vendor_srt, "fetch", blobs.__getitem__)


def test_extract_refuses_dotdot_and_links_and_drops_dot_paths():
    with pytest.raises(VendorError, match=r"\.\."):
        vendor_srt.extract(tgz([("package/../evil", b"x")]), "t")
    with pytest.raises(VendorError, match="not a regular file"):
        vendor_srt.extract(tgz([("package/link", None, "/etc/passwd")]), "t")
    with pytest.raises(VendorError, match="absolute"):
        vendor_srt.extract(tgz([("/package/x", b"x")]), "t")
    files, dropped = vendor_srt.extract(tgz([("package/a.js", b"1", 0o755), ("package/.github/x", b"2")]), "t")
    assert files == {"a.js": (b"1", 0o755)} and dropped == [".github/x"]


def test_write_then_check_is_clean_and_names_what_changes(tmp_path, monkeypatch):
    fake_registry(monkeypatch)
    dest = tmp_path / "srt"
    vendor_srt.write(dest)
    assert vendor_srt.check(dest) == []
    md = (dest / "VENDORED.md").read_text()
    assert "`node_modules/dep/.github/ci.yml`" in md and "Home paths in upstream bytes" in md
    assert "if (!upstream.readableEnded) socket.destroy()" in (dest / vendor_srt.HTTP_PROXY).read_text()
    # a changed byte, an extra file, a missing one
    (dest / "node_modules/dep/index.js").write_bytes(b"z\n")
    (dest / "node_modules/dep/extra.js").write_bytes(b"")
    (dest / "NOTICE").unlink()
    problems = vendor_srt.check(dest)
    assert any(p.startswith("node_modules/dep/index.js: sha256 differs") for p in problems)
    assert "node_modules/dep/extra.js: extra file" in problems
    assert any(p.startswith("NOTICE:") for p in problems)


def test_check_names_the_patch_when_its_text_is_gone(tmp_path, monkeypatch):
    fake_registry(monkeypatch)
    dest = tmp_path / "srt"
    vendor_srt.write(dest)
    f = dest / vendor_srt.SOCKS_PROXY
    f.write_text(f.read_text().replace("readableEnded", "destroyed"))
    assert any(vendor_srt.SOCKS_PROXY in p and "S2" in p for p in vendor_srt.check(dest))


def test_a_moved_anchor_stops_the_write(tmp_path, monkeypatch):
    fake_registry(monkeypatch, http=b"a\n  upstream.on('close', () => socket.destroy());\n")
    with pytest.raises(VendorError, match="S1 expects its anchor"):
        vendor_srt.write(tmp_path / "srt")


def test_a_tarball_with_another_sha512_is_refused(tmp_path, monkeypatch):
    fake_registry(monkeypatch)
    pins = list(vendor_srt.PINS)
    pins[1] = pins[1][:3] + ("sha512-AAAA",)
    monkeypatch.setattr(vendor_srt, "PINS", tuple(pins))
    with pytest.raises(VendorError, match="sha512"):
        vendor_srt.write(tmp_path / "srt")


# ---- the real tree in this checkout (T2) ------------------------------------------------------------------------------------
BUNDLE = REPO / vendor_srt.DEST


def test_the_bundle_is_upstream_plus_s1_and_s2():
    assert vendor_srt.check(BUNDLE) == []


def test_the_license_ships_unchanged_and_the_changes_are_noticed():
    rows = {m[1]: (m[2], m[3]) for m in vendor_srt.ROW.finditer((BUNDLE / "VENDORED.md").read_text())}
    up, vend = rows[f"node_modules/{vendor_srt.SRT}/LICENSE"]
    assert up == vend
    for e in vendor_srt.EDITS:
        assert f"Modified by Sutra (patch {e.patch}" in (BUNDLE / e.file).read_text()
    notice = (BUNDLE / "NOTICE").read_text()
    assert vendor_srt.HTTP_PROXY in notice and vendor_srt.SOCKS_PROXY in notice


def test_the_launcher_drops_the_electron_flag_and_imports_the_cli():
    text = (BUNDLE / "srt.mjs").read_text()
    assert "delete process.env.ELECTRON_RUN_AS_NODE;" in text and f"import('./{vendor_srt.CLI}')" in text
    assert (BUNDLE / vendor_srt.CLI).is_file()


def test_vendored_md_states_the_home_path_exemption():
    assert "## Home paths in upstream bytes" in (BUNDLE / "VENDORED.md").read_text()
