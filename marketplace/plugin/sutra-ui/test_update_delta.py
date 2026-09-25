"""test_update_delta.py -- the delta lane rebuilds the signed bundle EXACTLY, or refuses.

The property this file pins, in one line: for any installed base bundle and
any set of packs, reconstruct(base, manifest, packs) either produces a tree
that verify_tree() cannot distinguish from the released bundle -- every file
hash, mode, symlink target and empty dir, nothing extra -- or raises, leaving
no directory behind. There is no third outcome, because the third outcome is
what a delta updater that "mostly works" ships to every user at once.

Why the codec is shaped the way it is (measured on the real 2.300.0 -> 2.302.0
pair before this file existed): CI re-signs every Mach-O per release, so 1,314
files differ although 26 source files changed. Signature blobs sit at the END
of a thin binary (trim), at the end of EACH slice of a fat binary (fat), a code
directory's special-slot hashes sit near the FRONT of a same-size file
(aligned), a pyc header is the first 16 bytes (trim again), and CodeResources
is a plist where 1,300 of 100k lines change (lines). Each encoder here is
exercised on a synthetic file of that shape, and encode() is required to pick
a delta -- not full -- for it.

Safety pins: a pack is never extracted with tarfile.extract(); members are
streamed and must be named `index.json` or `blobs/<64 hex>`; a manifest path
that climbs, repeats, or sits under a symlink is refused before anything is
created; a tampered blob fails its hash and the whole reconstruction is
discarded; a base file the manifest thought unchanged but which the user
modified is a DeltaMiss (take the DMG), never a silent corruption.

Run: marketplace/plugin/sutra-ui/run-tests.sh test_update_delta.py
"""
import io
import json
import os
import random
import shutil
import struct
import tarfile
import tempfile
import unittest
from pathlib import Path

import updates_delta as ud

RND = random.Random(20260925)


def rand_bytes(n):
    return bytes(RND.getrandbits(8) for _ in range(n))


def fat_binary(slices):
    """A minimal universal binary: fat header + slices at 4 KiB alignment."""
    hdr = struct.pack(">II", 0xCAFEBABE, len(slices))
    off = 4096
    entries = b""
    body = b""
    for i, sl in enumerate(slices):
        entries += struct.pack(">IIIII", 0x0100000C + i, 0, off, len(sl), 12)
        pad = off - (4096 if i == 0 else 4096 + len(body))
        body += b"\0" * max(pad, 0) + sl
        off = 4096 + len(body)
        off = (off + 4095) // 4096 * 4096
    head = hdr + entries
    head += b"\0" * (4096 - len(head))
    return head + body


class Codec(unittest.TestCase):
    def check(self, old, new, expect_kind=None, max_literal=None):
        kind, ops, lit = ud.encode(old, new)
        self.assertEqual(ud.apply_ops(old, ops, lit), new)
        if expect_kind:
            self.assertEqual(kind, expect_kind, "encoder choice")
        if max_literal is not None:
            self.assertLessEqual(len(lit), max_literal)
        return kind, ops, lit

    def test_tail_signature_change_is_a_trim_delta(self):
        body = rand_bytes(200_000)
        old = body + b"SIG-OLD" + rand_bytes(3000)
        new = body + b"SIG-NEW-LONGER" + rand_bytes(3100)
        self.check(old, new, "trim", max_literal=3200)

    def test_pyc_header_change_is_a_small_delta(self):
        body = rand_bytes(50_000)
        old = b"\x0d\x0d\x0d\x0d" + b"\0" * 12 + body
        new = b"\x0d\x0d\x0d\x0d" + b"\x01" * 12 + body
        kind, ops, lit = self.check(old, new, max_literal=16)
        self.assertNotEqual(kind, "full")

    def test_same_size_scattered_change_is_aligned(self):
        old = rand_bytes(300_000)
        new = bytearray(old)
        new[8000:8010] = b"X" * 10          # one block near the front
        new[250_000] ^= 0xFF                 # and one block further on
        new = bytes(new)
        self.check(old, new, "aligned", max_literal=2 * ud.BLOCK)

    def test_fat_binary_per_slice_signature_change(self):
        a, b = rand_bytes(60_000), rand_bytes(90_000)
        old = fat_binary([a + b"SIGA1", b + b"SIGB1"])
        new = fat_binary([a + b"SIGA2-LONGER", b + b"SIGB2"])
        kind, ops, lit = self.check(old, new, max_literal=4096 * 4)
        self.assertIn(kind, ("fat", "trim", "aligned"))
        self.assertLess(len(lit), len(new) // 10)

    def test_text_with_scattered_line_changes(self):
        lines = ["<key>files/%05d</key><data>%s</data>" % (i, rand_bytes(16).hex()) for i in range(3000)]
        old = ("\n".join(lines) + "\n").encode()
        for i in range(0, 3000, 97):
            lines[i] = lines[i].replace("<data>", "<data>Z")
        new = ("\n".join(lines) + "\n").encode()
        kind, ops, lit = self.check(old, new)
        self.assertNotEqual(kind, "full")
        self.assertLess(len(lit), len(new) // 8)

    def test_totally_different_file_is_full(self):
        old, new = rand_bytes(10_000), rand_bytes(12_000)
        kind, ops, lit = self.check(old, new, "full")
        self.assertEqual(lit, new)

    def test_empty_and_identical(self):
        self.check(b"", b"abc")
        self.check(b"abc", b"")
        self.check(b"same", b"same", max_literal=0)

    def test_apply_refuses_bad_ops(self):
        with self.assertRaises(RuntimeError):
            ud.apply_ops(b"abc", [["c", 2, 5]], b"")
        with self.assertRaises(RuntimeError):
            ud.apply_ops(b"abc", [["l", 4]], b"xy")
        with self.assertRaises(RuntimeError):
            ud.apply_ops(b"abc", [["l", 1]], b"xy")    # literal not consumed
        with self.assertRaises(RuntimeError):
            ud.apply_ops(b"abc", [["z", 1]], b"")

    def test_lines_encoder_without_trailing_newline(self):
        old = b"alpha line one\nbeta line two\ngamma line three"
        new = b"alpha line one\nBETA changed\ngamma line three"
        self.check(old, new)
        self.check(old + b"\n", new)
        self.check(old, new + b"\n")


# ---------------------------------------------------------------- bundles ---

def write_bundle(root, spec):
    """spec: {rel: bytes | ("link", target) | ("dir",) | (bytes, mode)}"""
    root = Path(root)
    if root.exists():
        shutil.rmtree(root)
    root.mkdir(parents=True)
    for rel, val in spec.items():
        p = root / rel
        if isinstance(val, tuple) and val and val[0] == "link":
            p.parent.mkdir(parents=True, exist_ok=True)
            os.symlink(val[1], p)
        elif isinstance(val, tuple) and val and val[0] == "dir":
            p.mkdir(parents=True, exist_ok=True)
        else:
            data, mode = (val, 0o644) if isinstance(val, bytes) else val
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes(data)
            os.chmod(p, mode)
    return root


BIG = rand_bytes(1_000_000)
LIB = rand_bytes(300_000)
PLIST = ("\n".join("<key>k%d</key><string>%s</string>" % (i, rand_bytes(12).hex()) for i in range(2000)) + "\n").encode()


def spec_v1():
    return {
        "Contents/Info.plist": b"<plist><dict><key>CFBundleShortVersionString</key><string>1.0.0</string></dict></plist>",
        "Contents/MacOS/App": (b"#!/bin/sh\necho v1\n", 0o755),
        "Contents/Resources/big.bin": BIG,                        # unchanged
        "Contents/Resources/lib.so": LIB + b"SIG-V1",             # tail changes
        "Contents/Resources/mod.pyc": b"HDR1" + rand_bytes(4000), # head changes
        "Contents/Resources/rename-me.txt": b"same content, new name\n",
        "Contents/Resources/gone.txt": b"deleted in v2\n",
        "Contents/Resources/plist.xml": PLIST,
        "Contents/Resources/tool": (b"#!/bin/sh\necho tool\n", 0o644),   # mode flips
        "Contents/Resources/link": ("link", "big.bin"),                    # retargeted
        "Contents/Resources/empty-v1": ("dir",),                            # removed
        "Contents/Frameworks/X.framework/Versions/A/X": rand_bytes(5000),
        "Contents/Frameworks/X.framework/Versions/Current": ("link", "A"),
        "Contents/Frameworks/X.framework/X": ("link", "Versions/Current/X"),
        "Contents/Resources/old-tree/a/b/c.txt": b"whole tree removed\n",
    }


def spec_v2():
    s = spec_v1()
    s["Contents/Info.plist"] = s["Contents/Info.plist"].replace(b"1.0.0", b"1.1.0")
    s["Contents/MacOS/App"] = (b"#!/bin/sh\necho v2\n", 0o755)
    s["Contents/Resources/lib.so"] = LIB + b"SIG-V2-LONGER"
    s["Contents/Resources/mod.pyc"] = b"HDR2" + s["Contents/Resources/mod.pyc"][4:]
    s["Contents/Resources/renamed.txt"] = s.pop("Contents/Resources/rename-me.txt")
    s.pop("Contents/Resources/gone.txt")
    s["Contents/Resources/added.txt"] = b"new in v2\n"
    pl = PLIST.split(b"\n")
    for i in range(0, len(pl), 50):
        pl[i] = pl[i].replace(b"<string>", b"<string>changed")
    s["Contents/Resources/plist.xml"] = b"\n".join(pl)
    s["Contents/Resources/tool"] = (b"#!/bin/sh\necho tool\n", 0o755)
    s["Contents/Resources/link"] = ("link", "lib.so")
    s.pop("Contents/Resources/empty-v1")
    s["Contents/Resources/empty-v2"] = ("dir",)
    s.pop("Contents/Resources/old-tree/a/b/c.txt")
    return s


def spec_v3():
    s = spec_v2()
    s["Contents/Info.plist"] = s["Contents/Info.plist"].replace(b"1.1.0", b"1.2.0")
    s["Contents/Resources/lib.so"] = LIB + b"SIG-V3"
    s["Contents/Resources/added.txt"] = b"new in v2, edited in v3\n"
    return s


class Fixture(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="delta-test-"))
        self.v1 = write_bundle(self.tmp / "v1" / "App.app", spec_v1())
        self.v2 = write_bundle(self.tmp / "v2" / "App.app", spec_v2())
        self.m1 = ud.build_manifest(self.v1, "1.0.0", "arm64", "stable", "os.test.app")
        self.m2 = ud.build_manifest(self.v2, "1.1.0", "arm64", "stable", "os.test.app",
                                    previous_version="1.0.0")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def pack(self, old, man, name="p.tar.xz", from_version=None):
        out = self.tmp / name
        st = ud.build_pack(old, self.tmp / ("v%s" % man["version"][2]) / "App.app"
                           if False else self._app_for(man), man, out, from_version=from_version)
        return out, st

    def _app_for(self, man):
        return {"1.0.0": self.v1, "1.1.0": self.v2}.get(man["version"]) or getattr(self, "v3")

    def unpack(self, pack, name):
        d = self.tmp / name
        ud.unpack_to_dir(pack, d)
        return d


class Manifest(Fixture):
    def test_manifest_records_everything_and_validates(self):
        ud.validate_manifest(self.m2)
        kinds = {e["t"] for e in self.m2["entries"]}
        self.assertEqual(kinds, {"f", "l", "d"})
        by = {e["p"]: e for e in self.m2["entries"]}
        self.assertEqual(by["Contents/Resources/tool"]["m"], 0o755)
        self.assertEqual(by["Contents/Resources/link"]["l"], "lib.so")
        self.assertEqual(by["Contents/Resources/empty-v2"]["t"], "d")
        self.assertNotIn("Contents/Resources/empty-v1", by)
        self.assertEqual(self.m2["tree_sha256"], ud.tree_digest(self.m2))
        self.assertEqual(self.m2["files"], sum(1 for e in self.m2["entries"] if e["t"] == "f"))

    def test_verify_tree_is_exact(self):
        self.assertEqual(ud.verify_tree(self.v2, self.m2), [])
        self.assertTrue(ud.verify_tree(self.v1, self.m2))
        (self.v2 / "Contents/Resources/extra").write_bytes(b"x")
        self.assertIn("extra file Contents/Resources/extra", ud.verify_tree(self.v2, self.m2))

    def test_tampered_manifest_is_refused(self):
        man = json.loads(json.dumps(self.m2))
        man["entries"][0]["h"] = "0" * 64
        with self.assertRaises(RuntimeError):
            ud.validate_manifest(man)
        for bad in ("../x", "/abs", "a//b", "a/./b", "", "a\\b"):
            man = json.loads(json.dumps(self.m2))
            man["entries"].append({"p": bad, "t": "f", "h": "a" * 64, "m": 0o644})
            del man["tree_sha256"]
            with self.assertRaises(RuntimeError, msg=bad):
                ud.validate_manifest(man)
        man = json.loads(json.dumps(self.m2))
        man["entries"].append(dict(man["entries"][0]))
        del man["tree_sha256"]
        with self.assertRaises(RuntimeError):
            ud.validate_manifest(man)

    def test_nothing_may_sit_under_a_symlink(self):
        man = json.loads(json.dumps(self.m2))
        man["entries"].append({"p": "Contents/evil", "t": "l", "l": "/etc"})
        man["entries"].append({"p": "Contents/evil/passwd", "t": "f", "h": "b" * 64, "m": 0o644})
        del man["tree_sha256"]
        with self.assertRaisesRegex(RuntimeError, "under the symlink"):
            ud.validate_manifest(man)


class Pack(Fixture):
    def test_pack_carries_only_what_the_base_lacks(self):
        out, st = self.pack(self.v1, self.m2, from_version="1.0.0")
        self.assertGreater(st["unchanged"], 0)
        self.assertGreater(st["delta"], 0)
        self.assertGreater(st["full"], 0)
        self.assertLess(st["literal_bytes"], 120_000, "the pack must be far smaller than the 1.3 MB bundle")
        with tarfile.open(out, "r:xz") as tar:
            names = tar.getnames()
        self.assertEqual(names[0], "index.json")
        for n in names[1:]:
            self.assertRegex(n, r"^blobs/[0-9a-f]{64}$")
        d = self.unpack(out, "u")
        idx = json.load(open(d / "index.json"))
        by = {e["p"]: e for e in self.m2["entries"] if e["t"] == "f"}
        lib = idx["entries"][by["Contents/Resources/lib.so"]["h"]]
        self.assertNotEqual(lib["kind"], "full")
        self.assertEqual(lib["base"], {e["p"]: e for e in self.m1["entries"]}["Contents/Resources/lib.so"]["h"])
        self.assertEqual(idx["entries"][by["Contents/Resources/added.txt"]["h"]]["kind"], "full")
        self.assertNotIn(by["Contents/Resources/big.bin"]["h"], idx["entries"])
        self.assertNotIn(by["Contents/Resources/renamed.txt"]["h"], idx["entries"], "renamed content is in the base")

    def _craft(self, members):
        buf = io.BytesIO()
        with tarfile.open(fileobj=buf, mode="w:xz") as tar:
            for name, data, kind in members:
                ti = tarfile.TarInfo(name)
                if kind == "link":
                    ti.type = tarfile.SYMTYPE
                    ti.linkname = data
                    tar.addfile(ti)
                    continue
                ti.size = len(data)
                tar.addfile(ti, io.BytesIO(data))
        p = self.tmp / "crafted.tar.xz"
        p.write_bytes(buf.getvalue())
        return p

    def test_unpack_refuses_every_foreign_member(self):
        idx = json.dumps({"schema": ud.SCHEMA, "entries": {}}).encode()
        for bad in (
            [("index.json", idx, "f"), ("blobs/../../escape", b"x", "f")],
            [("index.json", idx, "f"), ("../evil", b"x", "f")],
            [("index.json", idx, "f"), ("blobs/" + "a" * 64, "/etc/passwd", "link")],
            [("index.json", idx, "f"), ("blobs/not-hex", b"x", "f")],
            [("blobs/" + "a" * 64, b"x", "f")],                     # no index
            [("index.json", b"{}", "f")],                            # wrong schema
        ):
            p = self._craft(bad)
            d = self.tmp / "crafted-out"
            shutil.rmtree(d, ignore_errors=True)
            with self.assertRaises((RuntimeError, ValueError), msg=str([m[0] for m in bad])):
                ud.unpack_to_dir(p, d)
            self.assertFalse((self.tmp / "escape").exists())


class Reconstruct(Fixture):
    def test_rebuilds_v2_from_v1_exactly(self):
        pack, st = self.pack(self.v1, self.m2, from_version="1.0.0")
        d = self.unpack(pack, "u")
        dest = self.tmp / "out" / "App.app"
        dest.parent.mkdir()
        stats = ud.reconstruct(self.v1, self.m2, [d], dest)
        self.assertEqual(ud.verify_tree(dest, self.m2), [])
        self.assertEqual(ud.tree_digest(ud.build_manifest(dest, "1.1.0", "arm64", "stable", "os.test.app",
                                                          previous_version="1.0.0")),
                         self.m2["tree_sha256"])
        self.assertGreater(stats["rebuilt"], 0)
        self.assertGreater(stats["kept"], 0)
        self.assertGreaterEqual(stats["removed"], 3)   # gone.txt, empty-v1, old-tree
        self.assertFalse((dest / "Contents/Resources/gone.txt").exists())
        self.assertFalse((dest / "Contents/Resources/old-tree").exists())
        self.assertTrue((dest / "Contents/Resources/empty-v2").is_dir())
        self.assertEqual(os.readlink(dest / "Contents/Resources/link"), "lib.so")
        self.assertEqual((dest / "Contents/Resources/tool").stat().st_mode & 0o777, 0o755)
        self.assertEqual((dest / "Contents/Resources/renamed.txt").read_bytes(), b"same content, new name\n")

    def test_base_junk_is_removed_and_user_modified_base_is_a_miss(self):
        pack, st = self.pack(self.v1, self.m2, from_version="1.0.0")
        d = self.unpack(pack, "u")
        base = write_bundle(self.tmp / "b1" / "App.app", spec_v1())
        (base / "Contents/Resources/junk.txt").write_bytes(b"user added\n")
        dest = self.tmp / "out1.app"
        ud.reconstruct(base, self.m2, [d], dest)
        self.assertEqual(ud.verify_tree(dest, self.m2), [])
        # now corrupt a file the manifest assumes the base has intact
        base = write_bundle(self.tmp / "b2" / "App.app", spec_v1())
        (base / "Contents/Resources/big.bin").write_bytes(b"corrupted")
        dest2 = self.tmp / "out2.app"
        with self.assertRaises(ud.DeltaMiss):
            ud.reconstruct(base, self.m2, [d], dest2)
        self.assertFalse(dest2.exists(), "a miss leaves nothing behind")

    def test_tampered_blob_fails_closed(self):
        pack, st = self.pack(self.v1, self.m2, from_version="1.0.0")
        d = self.unpack(pack, "u")
        blobs = sorted((d / "blobs").iterdir())
        target = blobs[0]
        data = bytearray(target.read_bytes())
        data[0] ^= 0xFF if data else 0
        target.write_bytes(bytes(data) if data else b"x")
        dest = self.tmp / "out.app"
        with self.assertRaises(RuntimeError):
            ud.reconstruct(self.v1, self.m2, [d], dest)
        self.assertFalse(dest.exists())

    def test_chain_of_two_packs_and_a_gap(self):
        self.v3 = write_bundle(self.tmp / "v3" / "App.app", spec_v3())
        m3 = ud.build_manifest(self.v3, "1.2.0", "arm64", "stable", "os.test.app", previous_version="1.1.0")
        p12, _ = self.pack(self.v1, self.m2, "p12.tar.xz", from_version="1.0.0")
        p23 = self.tmp / "p23.tar.xz"
        ud.build_pack(self.v2, self.v3, m3, p23, from_version="1.1.0")
        d12, d23 = self.unpack(p12, "u12"), self.unpack(p23, "u23")
        dest = self.tmp / "out3.app"
        ud.reconstruct(self.v1, m3, [d23, d12], dest)       # newest first
        self.assertEqual(ud.verify_tree(dest, m3), [])
        with self.assertRaises(ud.DeltaMiss):
            ud.reconstruct(self.v1, m3, [d23], self.tmp / "gap.app")
        self.assertFalse((self.tmp / "gap.app").exists())

    def test_destination_must_not_exist(self):
        dest = self.tmp / "exists.app"
        dest.mkdir()
        with self.assertRaises(RuntimeError):
            ud.reconstruct(self.v1, self.m2, [], dest)

    def test_no_packs_needed_when_base_already_matches(self):
        dest = self.tmp / "same.app"
        st = ud.reconstruct(self.v2, self.m2, [], dest)
        self.assertEqual(ud.verify_tree(dest, self.m2), [])
        self.assertEqual(st["rebuilt"], 0)


class Cli(Fixture):
    def test_cli_round_trip(self):
        import subprocess, sys
        here = Path(ud.__file__).resolve().parent
        env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
        def run(*args):
            p = subprocess.run([sys.executable, "-m", "updates_delta", *args], cwd=here,
                               capture_output=True, text=True, env=env)
            self.assertEqual(p.stdout.count("\n"), 1, p.stdout + p.stderr)
            return p.returncode, json.loads(p.stdout)
        rc, out = run("manifest", str(self.v2), "--version", "1.1.0", "--arch", "arm64",
                      "--bundle-id", "os.test.app", "--previous", "1.0.0",
                      "--out", str(self.tmp / "m.json"))
        self.assertEqual((rc, out["ok"]), (0, True))
        rc, out = run("pack", str(self.v1), str(self.v2), "--manifest", str(self.tmp / "m.json"),
                      "--from-version", "1.0.0", "--out", str(self.tmp / "p.tar.xz"))
        self.assertEqual((rc, out["ok"]), (0, True))
        rc, out = run("reconstruct", str(self.v1), "--manifest", str(self.tmp / "m.json"),
                      "--pack", str(self.tmp / "p.tar.xz"), "--dest", str(self.tmp / "cli-out.app"))
        self.assertEqual((rc, out["ok"]), (0, True), out)
        rc, out = run("verify", str(self.tmp / "cli-out.app"), "--manifest", str(self.tmp / "m.json"))
        self.assertEqual((rc, out), (0, {"ok": True, "problems": []}))
        rc, out = run("reconstruct", str(self.v2), "--manifest", str(self.tmp / "m.json"),
                      "--dest", str(self.tmp / "cli-out.app"))
        self.assertEqual(rc, 1, "existing destination is an error, exit 1")


if __name__ == "__main__":
    unittest.main()
