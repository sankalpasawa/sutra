"""What a task made (founder, 2026-10-09, from Paperclip's results tab).

  LIST    own copy (not kept): the files changed in the copy; kept: the files
          added to the project; no copy: the files the task's checks named.
          Thrown away / no changes: a plain note, no files.
  OPEN    only a listed file, only inside the task's folder; text (even
          .html) as plain text, an image as itself, anything else as a
          download; too big is refused.
  ROUTES  GET /results and /results/file, with nosniff.

Run: sutra/marketplace/plugin/sutra-ui/run-tests.sh test_shadow_results.py
"""
import os
import shutil
import subprocess
import tempfile
import unittest

os.environ["SUTRA_SHADOW_HOME"] = tempfile.mkdtemp(prefix="shadow-results-")

from fastapi.testclient import TestClient      # noqa: E402

import app as app_module                       # noqa: E402
import mission_engine                          # noqa: E402
import providers                               # noqa: E402
import shadow_results as sr                    # noqa: E402
import shadow_workspace as sw                  # noqa: E402

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 16


def write(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as fh:
        fh.write(data if isinstance(data, bytes) else data.encode())


class Base(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="proj-")
        self.store = mission_engine.MissionStore()

    def tearDown(self):
        for m in self.store.list():
            if m.get("workspace"):
                sw.discard(m["workspace"])
            self.store.delete(m["id"])
        shutil.rmtree(self.root, ignore_errors=True)

    def task(self, probes=(), state="running", **extra):
        m = self.store.create("make things", "feature", target_mode="new",
                              done_when=[])
        m["workdir"] = self.root
        m["done_when"] = [{"tier": "verify", "check": "c%d" % i,
                           "probe": {"kind": "file_exists", "path": p}}
                          for i, p in enumerate(probes)]
        m.update(extra)
        m["state"] = state
        self.store.save(m)
        return self.store.load(m["id"])


class ListNoCopy(Base):
    def test_01_the_files_its_checks_named_with_sizes(self):
        write(os.path.join(self.root, "out", "report.md"), "hello")
        got = sr.results(self.task(["out/report.md", "missing.txt"]))
        self.assertEqual(got["where"], "project")
        by = {f["path"]: f for f in got["files"]}
        self.assertEqual(by["out/report.md"]["bytes"], 5)
        self.assertEqual(by["out/report.md"]["folder"], "out")
        self.assertEqual(by["out/report.md"]["kind"], "text")
        self.assertFalse(by["missing.txt"]["exists"])

    def test_02_nothing_named_says_so(self):
        got = sr.results(self.task(state="done"))
        self.assertEqual(got["files"], [])
        self.assertIn("didn't leave any files", got["note"])

    def test_03_a_path_out_of_the_folder_is_never_resolved(self):
        got = sr.results(self.task(["../../etc/passwd"]))
        self.assertFalse(got["files"][0]["exists"])


class ListWithCopy(Base):
    def setUp(self):
        super().setUp()
        git = ["git", "-c", "user.name=t", "-c", "user.email=t@t"]
        subprocess.run(git + ["init", "-q"], cwd=self.root)
        write(os.path.join(self.root, "a.txt"), "a\n")
        subprocess.run(git + ["add", "-A"], cwd=self.root)
        subprocess.run(git + ["commit", "-q", "-m", "s"], cwd=self.root)

    def test_10_its_copys_changes_before_it_is_kept(self):
        m = self.task()
        ws = sw.prepare(m, self.root)
        write(os.path.join(ws["cwd"], "new", "made.md"), "made")
        m["workspace"] = ws
        got = sr.results(m)
        self.assertEqual(got["where"], "copy")
        self.assertEqual([f["path"] for f in got["files"]], ["new/made.md"])
        self.assertTrue(got["files"][0]["exists"])
        media, blob, _d = sr.open_file(m, "new/made.md")
        self.assertEqual(blob, b"made")

    def test_11_kept_reads_the_project(self):
        write(os.path.join(self.root, "kept.md"), "kept")
        m = self.task(state="done", workspace={"state": "kept",
                                               "repo": self.root,
                                               "files": ["kept.md"]})
        got = sr.results(m)
        self.assertEqual((got["where"], got["files"][0]["bytes"]), ("project", 4))

    def test_12_thrown_away_and_empty_say_so(self):
        for state, words in (("discarded", "Thrown away"),
                             ("empty", "didn't change any files")):
            got = sr.results(self.task(state="stopped",
                                       workspace={"state": state}))
            self.assertEqual(got["files"], [])
            self.assertIn(words, got["note"])


class Open(Base):
    def test_20_text_even_html_is_plain_text(self):
        write(os.path.join(self.root, "page.html"), "<script>x</script>")
        m = self.task(["page.html"])
        media, blob, download = sr.open_file(m, "page.html")
        self.assertTrue(media.startswith("text/plain"))
        self.assertIsNone(download)

    def test_21_an_image_is_itself_and_binary_downloads(self):
        write(os.path.join(self.root, "shot.png"), PNG)
        write(os.path.join(self.root, "data.bin"), b"\x00\x01\x02")
        m = self.task(["shot.png", "data.bin"])
        self.assertEqual(sr.open_file(m, "shot.png")[0], "image/png")
        media, _b, download = sr.open_file(m, "data.bin")
        self.assertEqual((media, download), ("application/octet-stream",
                                             "data.bin"))

    def test_22_only_listed_files_inside_the_folder(self):
        write(os.path.join(self.root, "secret.txt"), "no")
        m = self.task(["ok.txt"])
        for bad in ("secret.txt", "../secret.txt", "ok.txt"):
            with self.assertRaises(LookupError, msg=bad):
                sr.open_file(m, bad)

    def test_23_too_big_is_refused(self):
        write(os.path.join(self.root, "big.txt"), "x" * 100)
        m = self.task(["big.txt"])
        saved = sr.OPEN_MAX_BYTES
        sr.OPEN_MAX_BYTES = 10
        try:
            with self.assertRaises(ValueError):
                sr.open_file(m, "big.txt")
        finally:
            sr.OPEN_MAX_BYTES = saved


class Routes(Base):
    def setUp(self):
        super().setUp()
        self.client = TestClient(app_module.app, base_url="http://127.0.0.1")
        self.saved = providers.shadow_enabled
        providers.shadow_enabled = lambda: True

    def tearDown(self):
        providers.shadow_enabled = self.saved
        super().tearDown()

    def test_30_list_and_open(self):
        write(os.path.join(self.root, "r.md"), "result")
        m = self.task(["r.md"])
        got = self.client.get("/api/shadow/tasks/%s/results" % m["id"]).json()
        self.assertEqual(got["files"][0]["path"], "r.md")
        r = self.client.get("/api/shadow/tasks/%s/results/file" % m["id"],
                            params={"path": "r.md"})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.text, "result")
        self.assertEqual(r.headers["x-content-type-options"], "nosniff")

    def test_31_refusals(self):
        m = self.task(["r.md"])
        base = "/api/shadow/tasks/%s/results/file" % m["id"]
        self.assertEqual(self.client.get(base, params={"path": "r.md"})
                         .status_code, 404, "listed but not there")
        self.assertEqual(self.client.get(base, params={"path": "../x"})
                         .status_code, 404)
        self.assertEqual(self.client.get("/api/shadow/tasks/m-nope/results")
                         .status_code, 404)


if __name__ == "__main__":
    unittest.main()
