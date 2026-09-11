"""test_modules_pkg.py -- the Apps import/export trust boundary (APPS-THREATS.md
X-1..X-10; program steps 47, 59, 60). Every test here FAILS until the
endpoints exist (program steps 59-60); the flag test is the one that passes
first, because 404-with-hint is the contract while the flag is off.

Temp homes are set BEFORE importing the app (test_modules_api precedent) so
nothing touches the operator's real folders.
"""
import hashlib
import io
import json
import os
import shutil
import tarfile
import tempfile
import unittest
from pathlib import Path

MOD_HOME = tempfile.mkdtemp(prefix="pkg-test-")
os.environ["SUTRA_MODULES_HOME"] = MOD_HOME
os.environ["SUTRA_NATIVE_HOME"] = tempfile.mkdtemp(prefix="pkg-native-")
os.environ["SEO_AGENT_DATA"] = tempfile.mkdtemp(prefix="pkg-seo-")
os.environ["SEO_AGENT_NO_CLI"] = "1"
os.environ.setdefault("SUTRA_SHADOW_HOME", tempfile.mkdtemp(prefix="pkg-shadow-"))

from fastapi.testclient import TestClient  # noqa: E402

import app as app_module  # noqa: E402
import providers  # noqa: E402

HDR = {"X-Sutra-Panel": app_module.PANEL_TOKEN, "Origin": "http://127.0.0.1:8330"}
BASE = "/api/modules"

MANIFEST = {"schema": 2, "id": "imported-one", "name": "Imported one", "kind": "page", "status": "ready",
            "version": 1, "surface": {"entry": "index.html"}, "guard": {},
            "publish": {"version": "1.0.0", "author": "test", "license": "MIT"}}


def _tar(members):
    """members: list of (arcname, bytes | ('symlink', target))."""
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as t:
        for arc, data in members:
            if isinstance(data, tuple) and data[0] == "symlink":
                ti = tarfile.TarInfo(arc); ti.type = tarfile.SYMTYPE; ti.linkname = data[1]
                t.addfile(ti)
            else:
                ti = tarfile.TarInfo(arc); ti.size = len(data)
                t.addfile(ti, io.BytesIO(data))
    return buf.getvalue()


def _good_tar(mid="imported-one"):
    m = dict(MANIFEST, id=mid)
    return _tar([(mid + "/module.json", json.dumps(m).encode()),
                 (mid + "/index.html", b"<h1>hi</h1>")])


class TestModulesPkg(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app_module.app, base_url="http://127.0.0.1")

    def setUp(self):
        os.environ["SUTRA_MODULES_HOME"] = MOD_HOME      # per-test, not just at import (shared pytest process)
        for name in os.listdir(MOD_HOME):
            shutil.rmtree(os.path.join(MOD_HOME, name), ignore_errors=True)
        self._settings = providers.SETTINGS_PATH
        tmp = Path(tempfile.mkdtemp(prefix="pkg-settings-")) / "settings.json"
        tmp.write_text(json.dumps({"flags": {"apps_publish": True}}), encoding="utf-8")
        providers.SETTINGS_PATH = tmp

    def tearDown(self):
        providers.SETTINGS_PATH = self._settings

    def _import(self, blob, sha=None, mid="imported-one", replace=False):
        # the tarball is the raw body; id / sha256 / replace are query params
        # (no multipart dependency in the server -- codex F-pre P2)
        sha = sha or hashlib.sha256(blob).hexdigest()
        q = "?id=%s&sha256=%s%s" % (mid, sha, "&replace=1" if replace else "")
        return self.client.post(BASE + "/import" + q, content=blob,
                                headers=dict(HDR, **{"Content-Type": "application/gzip"}))

    # ---- the gate that passes first ------------------------------------------

    def test_00_flag_off_answers_404_with_the_hint(self):
        tmp = Path(tempfile.mkdtemp(prefix="pkg-settings-off-")) / "settings.json"
        tmp.write_text(json.dumps({"flags": {"apps_publish": False}}), encoding="utf-8")
        providers.SETTINGS_PATH = tmp
        r = self.client.post(BASE + "/imported-one/export", headers=HDR)
        self.assertEqual(r.status_code, 404)
        self.assertIn("apps_publish", r.json()["detail"])              # the hint, not a route miss (codex R2 P2)

    # ---- fail until steps 59-60 ------------------------------------------------

    def test_07_import_refuses_a_manifest_whose_id_differs_from_the_target(self):
        # X-2: manifest id must equal the target folder name
        r = self._import(_good_tar(mid="other-id"), mid="imported-one")
        self.assertEqual(r.status_code, 400, r.text)
        self.assertIn("id", r.json()["detail"].lower())
        self.assertFalse((Path(MOD_HOME) / "imported-one").exists())

    def test_08_import_refuses_members_outside_the_whitelist(self):
        # X-3: module.json, index.html, assets/** only; anything else is a refusal, not a skip
        bad = _tar([("imported-one/module.json", json.dumps(MANIFEST).encode()),
                    ("imported-one/run.sh", b"#!/bin/sh\necho no")])
        r = self._import(bad)
        self.assertEqual(r.status_code, 400, r.text)
        self.assertIn("whitelist", r.json()["detail"].lower())
        self.assertFalse((Path(MOD_HOME) / "imported-one").exists())

    def test_09_import_refuses_too_many_members(self):
        # X-5: 200-member cap, enforced while streaming
        members = [("imported-one/module.json", json.dumps(MANIFEST).encode())]
        members += [("imported-one/assets/f%d.txt" % i, b"x") for i in range(201)]
        r = self._import(_tar(members))
        self.assertEqual(r.status_code, 413, r.text)
        self.assertFalse((Path(MOD_HOME) / "imported-one").exists())

    def test_10_import_refuses_an_existing_folder_unless_replace_is_explicit(self):
        # X-6: no silent overwrite; explicit two-phase replace keeps a backup
        self.assertEqual(self._import(_good_tar()).status_code, 201)
        r = self._import(_good_tar())
        self.assertEqual(r.status_code, 409, r.text)
        r = self._import(_good_tar(), replace=True)
        self.assertEqual(r.status_code, 201, r.text)
        self.assertTrue(r.json()["replaced"])

    def test_11_import_appends_an_event_for_ok_and_for_refusal_and_overwrites_origin(self):
        # X-8 + X-9: every outcome is an app.imported row; manifest-supplied origin/publish are overwritten
        m = dict(MANIFEST, origin={"created_by": "app", "session_id": "forged"}, publish={"version": "9.9.9", "state": "published"})
        blob = _tar([("imported-one/module.json", json.dumps(m).encode()), ("imported-one/index.html", b"<p>x</p>")])
        self.assertEqual(self._import(blob).status_code, 201)
        raw = json.loads((Path(MOD_HOME) / "imported-one" / "module.json").read_text(encoding="utf-8"))
        self.assertEqual(raw["origin"]["created_by"], "marketplace")
        self.assertEqual(raw["publish"]["state"], "imported")
        self._import(_good_tar(mid="second"), sha="0" * 64, mid="second")     # a refusal
        lines = [json.loads(l) for l in (Path(MOD_HOME) / ".events.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
        results = [(e["app_id"], e["result"]) for e in lines if e["event"] == "app.imported"]
        self.assertIn(("imported-one", "ok"), results)
        self.assertIn(("second", "failed_verification"), results)

    def test_01_export_returns_a_tarball_and_its_sha256(self):
        self.client.post(BASE, json={"name": "Exportable", "kind": "page", "html": "<p>x</p>"}, headers=HDR)
        r = self.client.post(BASE + "/exportable/export", headers=HDR)
        self.assertEqual(r.status_code, 200, r.text)
        j = r.json()
        self.assertEqual(len(j["sha256"]), 64)
        self.assertTrue(j["artifact_path"].endswith(".tgz"))
        blob = Path(j["artifact_path"]).read_bytes()
        self.assertEqual(hashlib.sha256(blob).hexdigest(), j["sha256"])
        with tarfile.open(fileobj=io.BytesIO(blob)) as t:
            self.assertEqual(sorted(t.getnames()), ["exportable/index.html", "exportable/module.json"])

    def test_02_import_refuses_path_traversal_and_nothing_lands(self):
        bad = _tar([("imported-one/module.json", json.dumps(MANIFEST).encode()),
                    ("../escape.html", b"<h1>no</h1>")])
        r = self._import(bad)
        self.assertEqual(r.status_code, 400, r.text)
        self.assertIn("traversal", r.json()["detail"].lower())        # the reason, not a generic 400
        self.assertFalse((Path(MOD_HOME) / "imported-one").exists())
        self.assertFalse((Path(MOD_HOME).parent / "escape.html").exists())

    def test_03_import_refuses_symlinks(self):
        bad = _tar([("imported-one/module.json", json.dumps(MANIFEST).encode()),
                    ("imported-one/index.html", ("symlink", "/etc/passwd"))])
        r = self._import(bad)
        self.assertEqual(r.status_code, 400, r.text)
        self.assertIn("symlink", r.json()["detail"].lower())
        self.assertFalse((Path(MOD_HOME) / "imported-one").exists())

    def test_04_import_refuses_oversized_members(self):
        bad = _tar([("imported-one/module.json", json.dumps(MANIFEST).encode()),
                    ("imported-one/assets/big.bin", b"\0" * (5 * 1024 * 1024 + 1))])
        r = self._import(bad)
        self.assertEqual(r.status_code, 413, r.text)
        self.assertFalse((Path(MOD_HOME) / "imported-one").exists())

    def test_05_import_refuses_a_sha256_mismatch_before_opening_the_archive(self):
        r = self._import(_good_tar(), sha="0" * 64)
        self.assertEqual(r.status_code, 409, r.text)
        self.assertFalse((Path(MOD_HOME) / "imported-one").exists())

    def test_06_import_lands_atomically_with_marketplace_origin(self):
        r = self._import(_good_tar())
        self.assertEqual(r.status_code, 201, r.text)
        raw = json.loads((Path(MOD_HOME) / "imported-one" / "module.json").read_text(encoding="utf-8"))
        self.assertEqual(raw["origin"]["created_by"], "marketplace")     # X-9: set by the installer
        self.assertEqual(raw["publish"]["state"], "imported")
        self.assertFalse((Path(MOD_HOME) / ".quarantine").exists() and any((Path(MOD_HOME) / ".quarantine").iterdir()))


if __name__ == "__main__":
    unittest.main()
