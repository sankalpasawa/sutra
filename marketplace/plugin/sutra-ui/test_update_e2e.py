"""test_update_e2e.py -- the shipped update pipeline, end to end, against fixture releases.

Until this file existed no test ran the pipeline. test_update_swap_nesting.py
slices one shell block out of the helper; every other updater test mocks
install_desktop so the detached /bin/bash helper never spawns, and none of
them fetches anything, mounts anything, or calls codesign. The 2026-09-24
nesting incident shipped through that gap, and a delta lane -- which rebuilds
the bundle the helper installs -- must not be able to.

WHAT RUNS FOR REAL HERE: the `updates_cli` subprocess exactly as the Electron
shell spawns it (check / stage / arm --wait-pid / resolve), the HTTP download
with Range resume, the manifest and pack fetch, updates_delta reconstruction,
`codesign --verify --deep --strict`, the detached helper waiting on a real pid,
`hdiutil attach`, the TeamIdentifier / bundle-id / version gates, the
copy-beside-and-rename swap, install-result.json, and `resolve` clearing the
stage. Bundles are real ad-hoc-signed .app directories whose main executable
is a Mach-O; disk images are real UDZO DMGs from hdiutil.

WHAT IS SHIMMED, and only this: `spctl` (notarization needs Apple; an ad-hoc
bundle is rejected, so the shim answers 0 and records the call) and `open`
(so a relaunch is observed, not performed). Both are PATH shims, because
updates.py resolves tools through PATH and the helper inherits the environment.
The release server is a local HTTP server that speaks the two GitHub shapes
the updater uses: /repos/<repo>/releases/latest and the per-tag download URL.

Scenarios: the full-image path; the delta path; the delta lane falling back
to the image when the installed bundle was modified, when a pack blob is
tampered, and when the release is for another bundle id (which then also
proves the helper's bundle-id gate on the image); a two-hop chain; a dropped
pack download resuming with a Range request; resolve clearing everything.

macOS only (hdiutil, codesign). Run:
  marketplace/plugin/sutra-ui/run-tests.sh test_update_e2e.py
"""
import hashlib
import http.server
import json
import os
import plistlib
import random
import shutil
import socketserver
import stat
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import updates_delta as ud  # noqa: E402

IS_MAC = sys.platform == "darwin" and shutil.which("hdiutil") and shutil.which("codesign")
RND = random.Random(9)
BIG = bytes(RND.getrandbits(8) for _ in range(2_000_000))
LIB = bytes(RND.getrandbits(8) for _ in range(400_000))
V1, V2, V3 = "9.0.1", "9.0.2", "9.0.3"
BUNDLE_ID = "os.sutra.e2e"
REPO = "test/sutra"


def sha256_file(p):
    return ud.sha256_file(p)


# ------------------------------------------------------------- fixtures ----

def make_app(dest, version, bundle_id, payload):
    """A real bundle: Info.plist, a Mach-O main executable, a payload tree."""
    dest = Path(dest)
    if dest.exists():
        shutil.rmtree(dest)
    (dest / "Contents" / "MacOS").mkdir(parents=True)
    (dest / "Contents" / "Resources" / "payload").mkdir(parents=True)
    # copyfile, not copy2: copy2 would also copy /bin/sleep's restricted
    # flags (chflags), which is not permitted outside the system volume.
    shutil.copyfile("/bin/sleep", dest / "Contents" / "MacOS" / "Sutra")
    os.chmod(dest / "Contents" / "MacOS" / "Sutra", 0o755)
    with open(dest / "Contents" / "Info.plist", "wb") as fh:
        plistlib.dump({"CFBundleExecutable": "Sutra", "CFBundleIdentifier": bundle_id,
                       "CFBundleShortVersionString": version, "CFBundleVersion": version,
                       "CFBundlePackageType": "APPL", "CFBundleName": "Sutra"}, fh)
    for rel, data in payload.items():
        p = dest / "Contents" / "Resources" / "payload" / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(data, tuple) and data[0] == "link":
            os.symlink(data[1], p)
        else:
            p.write_bytes(data)
            if rel.endswith(".sh"):
                os.chmod(p, 0o755)
    subprocess.run(["codesign", "-s", "-", "--force", "--deep", str(dest)],
                   check=True, capture_output=True)
    subprocess.run(["codesign", "--verify", "--deep", "--strict", str(dest)],
                   check=True, capture_output=True)
    return dest


def payload_v1():
    return {"big.bin": BIG, "lib.so": LIB + b"SIG-1", "tool.sh": b"#!/bin/sh\necho 1\n",
            "notes.txt": b"v1\n", "link": ("link", "big.bin")}


def payload_v2():
    p = payload_v1()
    p["lib.so"] = LIB + b"SIG-2-LONGER"
    p["tool.sh"] = b"#!/bin/sh\necho 2\n"
    p["notes.txt"] = b"v2\n"
    p["added.txt"] = b"new\n"
    return p


def payload_v3():
    p = payload_v2()
    p["lib.so"] = LIB + b"SIG-3"
    p["notes.txt"] = b"v3\n"
    return p


def make_dmg(app, out):
    subprocess.run(["hdiutil", "create", "-quiet", "-srcfolder", str(app), "-volname", "Sutra",
                    "-format", "UDZO", "-ov", str(out)], check=True, capture_output=True)
    return Path(out)


def sidecar(path):
    p = Path(str(path) + ".sha256")
    p.write_text("%s  %s\n" % (sha256_file(path), Path(path).name))
    return p


# ------------------------------------------------------- release server ----

class _Handler(http.server.BaseHTTPRequestHandler):
    def log_message(self, *a):        # quiet
        pass

    def do_GET(self):
        srv = self.server
        srv.log.append((self.path, self.headers.get("Range")))
        if self.path == "/repos/%s/releases/latest" % REPO:
            body = json.dumps(srv.latest_json()).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        for prefix in ("/dl/", "/%s/releases/download/" % REPO):
            if self.path.startswith(prefix):
                tag, _, name = self.path[len(prefix):].partition("/")
                path = srv.files.get(tag, {}).get(name)
                if not path:
                    self.send_error(404)
                    return
                self._serve(Path(path), name)
                return
        self.send_error(404)

    def _serve(self, path, name):
        size = path.stat().st_size
        start = 0
        rng = self.headers.get("Range")
        if rng and rng.startswith("bytes="):
            start = int(rng[6:].rstrip("-"))
            if start >= size:
                self.send_response(416)
                self.end_headers()
                return
            self.send_response(206)
            self.send_header("Content-Range", "bytes %d-%d/%d" % (start, size - 1, size))
        else:
            self.send_response(200)
        drop = self.server.drop_once.pop(name, None)
        length = size - start
        self.send_header("Content-Length", str(length))
        self.end_headers()
        with open(path, "rb") as fh:
            fh.seek(start)
            remaining = length if drop is None else min(drop, length)
            while remaining > 0:
                chunk = fh.read(min(65536, remaining))
                if not chunk:
                    break
                self.wfile.write(chunk)
                remaining -= len(chunk)
        if drop is not None:
            self.wfile.flush()
            self.connection.close()


class ReleaseServer(socketserver.ThreadingMixIn, http.server.HTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self):
        super().__init__(("127.0.0.1", 0), _Handler)
        self.log = []
        self.files = {}          # tag -> {asset name: path}
        self.latest_tag = None
        self.drop_once = {}
        self.thread = threading.Thread(target=self.serve_forever, daemon=True)
        self.thread.start()

    @property
    def base(self):
        return "http://127.0.0.1:%d" % self.server_address[1]

    def publish(self, tag, assets, latest=True):
        self.files[tag] = {Path(p).name: str(p) for p in assets}
        if latest:
            self.latest_tag = tag

    def latest_json(self):
        tag = self.latest_tag
        return {"tag_name": tag, "html_url": self.base + "/rel/" + tag, "prerelease": False,
                "assets": [{"name": n, "size": Path(p).stat().st_size,
                            "browser_download_url": "%s/dl/%s/%s" % (self.base, tag, n)}
                           for n, p in self.files[tag].items()]}

    def hits(self, name):
        return [(p, r) for (p, r) in self.log if p.endswith("/" + name)]

    def close(self):
        self.shutdown()
        self.server_close()


# --------------------------------------------------------------- harness ---

@unittest.skipUnless(IS_MAC, "needs macOS: hdiutil and codesign")
class EndToEnd(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root = Path(tempfile.mkdtemp(prefix="sutra-e2e-"))
        cls.python = sys.executable
        cls.v1 = make_app(cls.root / "v1" / "Sutra.app", V1, BUNDLE_ID, payload_v1())
        cls.v2 = make_app(cls.root / "v2" / "Sutra.app", V2, BUNDLE_ID, payload_v2())
        cls.v3 = make_app(cls.root / "v3" / "Sutra.app", V3, BUNDLE_ID, payload_v3())
        cls.other = make_app(cls.root / "other" / "Sutra.app", V2, "os.sutra.other", payload_v2())
        cls.arch = subprocess.run(["uname", "-m"], capture_output=True, text=True).stdout.strip()
        cls.arch = "arm64" if cls.arch in ("arm64", "aarch64") else "x86_64"
        a = cls.arch
        cls.assets = {}
        for ver, app, prev_app, prev in ((V2, cls.v2, cls.v1, V1), (V3, cls.v3, cls.v2, V2)):
            d = cls.root / ("release-" + ver)
            d.mkdir()
            dmg = make_dmg(app, d / ("Sutra-%s.dmg" % a))
            man = ud.build_manifest(app, ver, a, "stable", BUNDLE_ID, tag="v%s-desktop" % ver,
                                    previous_version=prev)
            mp = d / ("Sutra-%s.manifest.json" % a)
            mp.write_text(json.dumps(man, sort_keys=True, separators=(",", ":")))
            pk = d / ("Sutra-%s.delta.tar.xz" % a)
            ud.build_pack(prev_app, app, man, pk, from_version=prev)
            cls.assets[ver] = {"dmg": dmg, "manifest": mp, "pack": pk,
                               "sidecars": [sidecar(dmg), sidecar(mp), sidecar(pk)], "man": man}
        d = cls.root / "release-other"
        d.mkdir()
        dmg = make_dmg(cls.other, d / ("Sutra-%s.dmg" % a))
        man = ud.build_manifest(cls.other, V2, a, "stable", "os.sutra.other", previous_version=V1)
        mp = d / ("Sutra-%s.manifest.json" % a)
        mp.write_text(json.dumps(man, sort_keys=True, separators=(",", ":")))
        pk = d / ("Sutra-%s.delta.tar.xz" % a)
        ud.build_pack(cls.v1, cls.other, man, pk, from_version=V1)
        cls.assets["other"] = {"dmg": dmg, "manifest": mp, "pack": pk,
                               "sidecars": [sidecar(dmg), sidecar(mp), sidecar(pk)], "man": man}
        # PATH shims: spctl says yes and records; open records.
        cls.shim = cls.root / "shim"
        cls.shim.mkdir()
        cls.shim_log = cls.root / "shim.log"
        for tool in ("spctl", "open"):
            s = cls.shim / tool
            s.write_text('#!/bin/sh\necho "%s $*" >> "%s"\nexit 0\n' % (tool, cls.shim_log))
            s.chmod(0o755)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.root, ignore_errors=True)

    def setUp(self):
        self.case = Path(tempfile.mkdtemp(prefix="case-", dir=str(self.root)))
        self.apps = self.case / "Applications"
        self.apps.mkdir()
        self.installed = self.apps / "Sutra.app"
        subprocess.run(["cp", "-R", str(self.v1), str(self.installed)], check=True)
        self.stage = self.case / "updates"
        self.server = ReleaseServer()
        self.shim_log.write_text("")

    def tearDown(self):
        self.server.close()

    # ---- helpers
    def env(self):
        env = dict(os.environ)
        env.update({
            "SUTRA_UI_RELEASE_API": self.server.base,
            "SUTRA_UI_RELEASE_DOWNLOAD": self.server.base,
            "SUTRA_UI_DESKTOP_REPO": REPO,
            "SUTRA_UPDATE_DIR": str(self.stage),
            "SUTRA_UI_APP_BUNDLE": str(self.installed),
            "PATH": "%s:/usr/bin:/bin:/usr/sbin:/sbin" % self.shim,
            "PYTHONDONTWRITEBYTECODE": "1",
        })
        return env

    def cli(self, *args, expect=0):
        p = subprocess.run([self.python, "-m", "updates_cli", *args], cwd=HERE,
                           env=self.env(), capture_output=True, text=True, timeout=600)
        self.assertEqual(p.stdout.count("\n"), 1, "one JSON line:\n" + p.stdout + p.stderr)
        out = json.loads(p.stdout)
        if expect is not None:
            self.assertEqual(p.returncode, expect, out)
        return out

    def publish(self, ver, delta=True, latest=True, tag=None):
        a = self.assets[ver]
        files = [a["dmg"], a["sidecars"][0]]
        if delta:
            files += [a["manifest"], a["pack"], a["sidecars"][1], a["sidecars"][2]]
        self.server.publish(tag or "v%s-desktop" % (a["man"]["version"]), files, latest=latest)

    def pending(self):
        p = self.stage / "pending-update.json"
        return json.loads(p.read_text()) if p.exists() else None

    def installed_version(self):
        with open(self.installed / "Contents" / "Info.plist", "rb") as fh:
            return plistlib.load(fh)["CFBundleShortVersionString"]

    def arm_and_wait(self, relaunch=False):
        waiter = subprocess.Popen(["sleep", "300"])
        try:
            args = ["arm", "--wait-pid", str(waiter.pid)] + (["--relaunch"] if relaunch else [])
            out = self.cli(*args)
            self.assertTrue(out.get("scheduled"), out)
            self.assertEqual(self.pending()["state"], "installing")
        finally:
            waiter.kill()
            waiter.wait()
        result = self.stage / "install-result.json"
        for _ in range(240):
            if result.exists():
                break
            time.sleep(0.5)
        self.assertTrue(result.exists(), "the helper never reported back; log: %s"
                        % self._helper_log())
        return json.loads(result.read_text())

    def relaunch_seen(self, wait=5.0):
        """The helper writes its result BEFORE `open -a`, so give the relaunch
        a moment to land in the shim log before asserting either way."""
        deadline = time.time() + wait
        while time.time() < deadline:
            if "open -a" in self.shim_log.read_text():
                return True
            time.sleep(0.2)
        return False

    def _helper_log(self):
        logs = sorted(Path(tempfile.gettempdir()).glob("sutra-installer-*/install.log"),
                      key=lambda p: p.stat().st_mtime)
        return logs[-1].read_text()[-2000:] if logs else "(no log)"

    # ---- scenarios
    def test_full_image_path_end_to_end(self):
        self.publish(V2, delta=False)
        state = self.cli("check")
        self.assertTrue(state["desktop"]["update_available"], state)
        self.assertFalse(state["desktop"].get("delta"))
        out = self.cli("stage")
        self.assertTrue(out["staged"], out)
        man = self.pending()
        self.assertEqual((man["state"], man["version"], man["artifact_kind"]), ("staged", V2, "dmg"))
        self.assertTrue(Path(man["dmg"]).is_file())
        self.assertTrue(self.server.hits("Sutra-%s.dmg" % self.arch))
        self.assertIn("spctl", self.shim_log.read_text())
        res = self.arm_and_wait(relaunch=True)
        self.assertEqual((res["ok"], res["stage"], res["version"]), (True, "installed", V2), res)
        self.assertEqual(self.installed_version(), V2)
        subprocess.run(["codesign", "--verify", "--deep", "--strict", str(self.installed)], check=True)
        self.assertTrue(self.relaunch_seen(), self.shim_log.read_text())
        self.assertIn("open -a %s" % self.installed, self.shim_log.read_text())
        self.assertFalse(list(self.apps.glob("*.old-*")) + list(self.apps.glob("*.new-*")))
        out = self.cli("resolve", "--installed", V2)
        self.assertEqual(out, {"pending": False, "applied": V2})
        self.assertFalse(list(self.stage.glob("*.dmg")))

    def test_delta_path_end_to_end(self):
        self.publish(V2, delta=True)
        state = self.cli("check")
        self.assertTrue(state["desktop"].get("delta"), state)
        out = self.cli("stage")
        self.assertTrue(out["staged"], out)
        self.assertEqual(out["artifact_kind"], "app")
        man = self.pending()
        self.assertEqual(man["artifact_kind"], "app")
        staged = Path(man["dmg"])
        self.assertTrue(staged.is_dir() and staged.suffix == ".app")
        self.assertEqual(ud.verify_tree(staged, self.assets[V2]["man"]), [])
        self.assertFalse(self.server.hits("Sutra-%s.dmg" % self.arch), "the image was never downloaded")
        self.assertTrue(self.server.hits("Sutra-%s.delta.tar.xz" % self.arch))
        self.assertEqual(man["delta"]["hops"], 1)
        self.assertLess(self.assets[V2]["pack"].stat().st_size, 200_000)
        res = self.arm_and_wait(relaunch=False)
        self.assertEqual((res["ok"], res["stage"], res["version"]), (True, "installed", V2), res)
        self.assertEqual(self.installed_version(), V2)
        self.assertEqual(ud.verify_tree(self.installed, self.assets[V2]["man"]), [])
        subprocess.run(["codesign", "--verify", "--deep", "--strict", str(self.installed)], check=True)
        self.assertFalse(self.relaunch_seen(wait=2.0), "no relaunch after a user quit")
        self.assertFalse(list(self.apps.glob("*.old-*")) + list(self.apps.glob("*.new-*")))
        out = self.cli("resolve", "--installed", V2)
        self.assertEqual(out, {"pending": False, "applied": V2})
        self.assertFalse(list(self.stage.glob("*.app")) + list(self.stage.glob("*.manifest.json")))

    def test_modified_base_falls_back_to_the_image(self):
        self.publish(V2, delta=True)
        (self.installed / "Contents/Resources/payload/big.bin").write_bytes(b"user modified")
        out = self.cli("stage")
        self.assertTrue(out["staged"], out)
        self.assertEqual(out["artifact_kind"], "dmg")
        self.assertIn("delta update not possible", out.get("note") or "")
        self.assertTrue(self.server.hits("Sutra-%s.dmg" % self.arch))
        self.assertFalse(list(self.stage.glob("*.app")), "nothing half-built is left behind")

    def test_tampered_pack_falls_back_and_never_stages_it(self):
        a = self.assets[V2]
        d = self.case / "tampered"
        d.mkdir()
        ud.unpack_to_dir(a["pack"], d / "u")
        blob = sorted((d / "u" / "blobs").iterdir())[0]
        blob.write_bytes(b"\0" * 64)
        import tarfile, io
        tp = d / ("Sutra-%s.delta.tar.xz" % self.arch)
        with tarfile.open(tp, "w:xz") as tar:
            for member in [d / "u" / "index.json"] + sorted((d / "u" / "blobs").iterdir()):
                data = member.read_bytes()
                ti = tarfile.TarInfo("index.json" if member.name == "index.json" else "blobs/" + member.name)
                ti.size = len(data)
                tar.addfile(ti, io.BytesIO(data))
        files = [a["dmg"], a["sidecars"][0], a["manifest"], a["sidecars"][1], tp, sidecar(tp)]
        self.server.publish("v%s-desktop" % V2, files)
        out = self.cli("stage")
        self.assertTrue(out["staged"], out)
        self.assertEqual(out["artifact_kind"], "dmg")
        self.assertIn("delta update not possible", out.get("note") or "")
        self.assertFalse(list(self.stage.glob("*.app")))

    def test_other_bundle_id_is_refused_by_the_delta_lane_and_the_helper(self):
        self.publish("other", delta=True, tag="v%s-desktop" % V2)
        out = self.cli("stage")
        self.assertTrue(out["staged"], out)
        self.assertEqual(out["artifact_kind"], "dmg", "the delta lane refuses another bundle id up front")
        self.assertIn("bundle", out.get("note") or "")
        res = self.arm_and_wait()
        self.assertEqual((res["ok"], res["stage"]), (False, "bundle-id"), res)
        self.assertEqual(self.installed_version(), V1, "/Applications untouched")
        subprocess.run(["codesign", "--verify", "--deep", "--strict", str(self.installed)], check=True)
        out = self.cli("resolve", "--installed", V1)
        self.assertEqual(out.get("action"), "arm")
        self.assertEqual(out.get("retry_after_failure"), res["error"])

    def test_two_hop_chain_from_v1_to_v3(self):
        self.publish(V2, delta=True, latest=False)
        self.publish(V3, delta=True, latest=True)
        out = self.cli("stage")
        self.assertTrue(out["staged"], out)
        self.assertEqual(out["artifact_kind"], "app")
        man = self.pending()
        self.assertEqual((man["version"], man["delta"]["hops"]), (V3, 2))
        self.assertEqual(ud.verify_tree(Path(man["dmg"]), self.assets[V3]["man"]), [])
        self.assertTrue(self.server.hits("Sutra-%s.delta.tar.xz" % self.arch))
        chain_hits = [p for (p, _) in self.server.log if "/releases/download/v%s-desktop/" % V2 in p]
        self.assertTrue(chain_hits, "the v2 hop was fetched by its deterministic tag URL")
        self.assertFalse(self.server.hits("Sutra-%s.dmg" % self.arch))
        res = self.arm_and_wait()
        self.assertEqual((res["ok"], res["version"]), (True, V3), res)
        self.assertEqual(self.installed_version(), V3)

    def test_dropped_pack_download_resumes_with_a_range_request(self):
        self.publish(V2, delta=True)
        name = "Sutra-%s.delta.tar.xz" % self.arch
        self.server.drop_once[name] = self.assets[V2]["pack"].stat().st_size // 2
        out = self.cli("stage")
        self.assertTrue(out["staged"], out)
        self.assertEqual(out["artifact_kind"], "app")
        ranges = [r for (_, r) in self.server.hits(name) if r]
        self.assertTrue(ranges and ranges[0].startswith("bytes="), self.server.hits(name))

    def test_delta_disabled_by_env_takes_the_image(self):
        self.publish(V2, delta=True)
        env = self.env()
        env["SUTRA_UPDATE_DELTA"] = "0"
        p = subprocess.run([self.python, "-m", "updates_cli", "stage"], cwd=HERE, env=env,
                           capture_output=True, text=True, timeout=600)
        out = json.loads(p.stdout)
        self.assertEqual((p.returncode, out["artifact_kind"]), (0, "dmg"), out)
        self.assertFalse(self.server.hits("Sutra-%s.delta.tar.xz" % self.arch))


if __name__ == "__main__":
    unittest.main()
