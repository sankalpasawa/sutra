"""Each task works in its own copy of the project (founder, 2026-10-08,
option B: auto-keep when the checks pass). Real git, in throwaway repos.

  COPY      a snapshot of the founder's folder NOW: uncommitted edits and new
            files included; the founder's working tree, index and stash are
            untouched; a project subfolder maps to the same subfolder.
  KEEP      a finished task's changes land in the founder's folder, beside
            the founder's own uncommitted edits; a clash applies NOTHING.
  END       done -> kept automatically; ended unfinished with changes ->
            the founder decides; no changes -> the copy just goes.
  CHECKS    a task's checks read its own copy.
  WIRING    the worker starts in the copy and is told so; delete removes it;
            not a git folder, or copies off -> exactly as before.

Run: sutra/marketplace/plugin/sutra-ui/run-tests.sh test_shadow_workspace.py
"""
import asyncio
import os
import shutil
import subprocess
import tempfile
import unittest

os.environ["SUTRA_SHADOW_HOME"] = tempfile.mkdtemp(prefix="shadow-ws-")

from fastapi.testclient import TestClient      # noqa: E402

import app as app_module                       # noqa: E402
import mission_engine                          # noqa: E402
import providers                               # noqa: E402
import shadow_workspace as sw                  # noqa: E402

HDR = {"X-Sutra-Panel": app_module.PANEL_TOKEN,
       "Origin": "http://127.0.0.1:8330"}


def git(cwd, *args):
    p = subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t",
                        "-c", "core.autocrlf=false"] + list(args), cwd=cwd,
                       capture_output=True, text=True)
    return p.stdout.strip()


def write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", newline="\n") as fh:
        fh.write(text)


def read(path):
    with open(path) as fh:
        return fh.read()


class Base(unittest.TestCase):
    def setUp(self):
        self.repo = tempfile.mkdtemp(prefix="founder-")
        git(self.repo, "init", "-q")
        git(self.repo, "config", "core.autocrlf", "false")
        write(os.path.join(self.repo, "app", "a.txt"), "one\ntwo\nthree\n")
        write(os.path.join(self.repo, "b.txt"), "bee\n")
        write(os.path.join(self.repo, ".gitignore"), "*.log\n")
        git(self.repo, "add", "-A")
        git(self.repo, "commit", "-q", "-m", "start")
        self.store = mission_engine.MissionStore()
        self.saved_env = os.environ.pop("SUTRA_SHADOW_TASK_COPIES", None)

    def tearDown(self):
        for m in self.store.list():
            ws = m.get("workspace")
            if ws:
                sw.discard(ws)
            self.store.delete(m["id"])
        shutil.rmtree(self.repo, ignore_errors=True)
        if self.saved_env is not None:
            os.environ["SUTRA_SHADOW_TASK_COPIES"] = self.saved_env

    def task(self, state=None):
        m = self.store.create("edit the files", "feature", target_mode="new",
                              done_when=[])
        return m

    def copy(self, m, base=None):
        ws = sw.prepare(m, base or self.repo)
        self.assertIsNotNone(ws)
        m = self.store.load(m["id"])
        m["workspace"], m["workdir"] = ws, ws["cwd"]
        self.store.save(m)
        return ws

    def end(self, mid, state):
        m = self.store.load(mid)
        for st in {"done": ("brief_confirm", "running", "done"),
                   "stopped": ("stopped",),
                   "failed": ("brief_confirm", "running", "failed")}[state]:
            m = self.store.transition(mid, st, "test")
        return sw.finish(mid)


class Copy(Base):
    def test_01_the_copy_is_the_folder_as_it_is_now(self):
        write(os.path.join(self.repo, "b.txt"), "bee, edited\n")       # tracked edit
        write(os.path.join(self.repo, "new.txt"), "brand new\n")       # untracked
        write(os.path.join(self.repo, "noise.log"), "ignored\n")       # ignored
        before = git(self.repo, "status", "--porcelain")
        ws = self.copy(self.task())
        self.assertEqual(read(os.path.join(ws["cwd"], "b.txt")), "bee, edited\n")
        self.assertEqual(read(os.path.join(ws["cwd"], "new.txt")), "brand new\n")
        self.assertFalse(os.path.exists(os.path.join(ws["cwd"], "noise.log")))
        self.assertEqual(git(self.repo, "status", "--porcelain"), before,
                         "the founder's folder is untouched")
        self.assertEqual(git(self.repo, "stash", "list"), "", "and no stash")
        self.assertTrue(ws["path"].startswith(sw.copies_dir()))
        self.assertEqual(sw.changes(ws)[0], [], "nothing changed yet")

    def test_02_a_project_subfolder_maps_to_the_same_subfolder(self):
        ws = self.copy(self.task(), base=os.path.join(self.repo, "app"))
        self.assertEqual(os.path.basename(ws["cwd"]), "app")
        self.assertTrue(os.path.isfile(os.path.join(ws["cwd"], "a.txt")))

    def test_03_not_a_git_folder_or_copies_off_means_as_before(self):
        plain = tempfile.mkdtemp(prefix="plain-")
        self.assertIsNone(sw.prepare(self.task(), plain))
        os.environ["SUTRA_SHADOW_TASK_COPIES"] = "0"
        try:
            self.assertIsNone(sw.prepare(self.task(), self.repo))
        finally:
            del os.environ["SUTRA_SHADOW_TASK_COPIES"]

    def test_04_a_prepared_copy_is_reused_after_a_restart(self):
        m = self.task()
        ws = self.copy(m)
        again = sw.prepare(self.store.load(m["id"]), self.repo)
        self.assertEqual(again["path"], ws["path"])

    def test_05_the_worker_is_told_where_to_work(self):
        ws = self.copy(self.task())
        note = sw.note_for_worker(ws)
        self.assertIn(ws["cwd"], note)
        self.assertIn("never in", note)
        self.assertEqual(sw.note_for_worker(None), "")


class Keep(Base):
    def test_10_a_finished_task_lands_beside_the_founders_own_edits(self):
        m = self.task()
        ws = self.copy(m)
        write(os.path.join(ws["cwd"], "app", "a.txt"), "one\nTWO\nthree\n")
        write(os.path.join(ws["cwd"], "made.txt"), "from the task\n")
        # the founder edits a different file meanwhile
        write(os.path.join(self.repo, "b.txt"), "bee, mine\n")
        out = self.end(m["id"], "done")
        self.assertEqual(out["state"], "kept")
        self.assertEqual(out["kept_by"], "auto")
        self.assertEqual(sorted(out["files"]), ["app/a.txt", "made.txt"])
        self.assertEqual(read(os.path.join(self.repo, "app", "a.txt")),
                         "one\nTWO\nthree\n")
        self.assertEqual(read(os.path.join(self.repo, "made.txt")),
                         "from the task\n")
        self.assertEqual(read(os.path.join(self.repo, "b.txt")), "bee, mine\n",
                         "the founder's own edit is still there")
        self.assertFalse(os.path.exists(ws["path"]), "the copy is gone")
        self.assertNotIn(ws["branch"], git(self.repo, "branch"))

    def test_11_a_clash_applies_nothing_and_waits_for_the_founder(self):
        m = self.task()
        ws = self.copy(m)
        write(os.path.join(ws["cwd"], "app", "a.txt"), "one\nTASK\nthree\n")
        write(os.path.join(ws["cwd"], "other.txt"), "also from the task\n")
        write(os.path.join(self.repo, "app", "a.txt"), "one\nFOUNDER\nthree\n")
        out = self.end(m["id"], "done")
        self.assertEqual(out["state"], "clash")
        self.assertEqual(read(os.path.join(self.repo, "app", "a.txt")),
                         "one\nFOUNDER\nthree\n")
        self.assertFalse(os.path.exists(os.path.join(self.repo, "other.txt")),
                         "all or nothing: no half-applied task")
        self.assertTrue(os.path.isdir(ws["path"]), "the copy is kept for later")
        # the founder sorts it out, then tries again
        write(os.path.join(self.repo, "app", "a.txt"), "one\ntwo\nthree\n")
        again = sw.decide(m["id"], "keep")
        self.assertEqual(again["state"], "kept")
        self.assertEqual(again["kept_by"], "founder")
        self.assertEqual(read(os.path.join(self.repo, "other.txt")),
                         "also from the task\n")

    def test_12_crlf_files_in_the_founders_folder_still_take_the_change(self):
        with open(os.path.join(self.repo, "app", "a.txt"), "wb") as fh:
            fh.write(b"one\r\ntwo\r\nthree\r\n")
        git(self.repo, "add", "-A")
        git(self.repo, "commit", "-q", "-m", "crlf")
        m = self.task()
        ws = self.copy(m)
        with open(os.path.join(ws["cwd"], "app", "a.txt"), "wb") as fh:
            fh.write(b"one\r\ntwo\r\nthree\r\nfour\r\n")
        self.assertEqual(self.end(m["id"], "done")["state"], "kept")
        self.assertIn(b"four", open(os.path.join(self.repo, "app", "a.txt"),
                                    "rb").read())


class End(Base):
    def test_20_unfinished_with_changes_is_the_founders_call(self):
        m = self.task()
        ws = self.copy(m)
        write(os.path.join(ws["cwd"], "half.txt"), "half done\n")
        out = self.end(m["id"], "stopped")
        self.assertEqual(out["state"], "pending")
        self.assertFalse(os.path.exists(os.path.join(self.repo, "half.txt")))
        gone = sw.decide(m["id"], "discard")
        self.assertEqual(gone["state"], "discarded")
        self.assertFalse(os.path.exists(ws["path"]))
        with self.assertRaises(ValueError):
            sw.decide(m["id"], "keep")

    def test_21_no_changes_and_the_copy_just_goes(self):
        m = self.task()
        ws = self.copy(m)
        self.assertEqual(self.end(m["id"], "failed")["state"], "empty")
        self.assertFalse(os.path.exists(ws["path"]))

    def test_22_a_running_task_is_left_alone(self):
        m = self.task()
        self.copy(m)
        self.assertEqual(sw.finish(m["id"])["state"], "active")

    def test_23_the_boot_sweep_ends_what_ended_while_the_app_was_down(self):
        m = self.task()
        ws = self.copy(m)
        write(os.path.join(ws["cwd"], "late.txt"), "x\n")
        self.store.transition(m["id"], "stopped", "while down")
        self.assertEqual(sw.sweep(), [m["id"]])
        self.assertEqual(self.store.load(m["id"])["workspace"]["state"],
                         "pending")


class Checks(Base):
    def test_30_a_tasks_checks_read_its_own_copy(self):
        m = self.task()
        ws = self.copy(m)
        write(os.path.join(ws["cwd"], "report.md"), "done\n")
        m = self.store.load(m["id"])
        m["done_when"] = [{"tier": "verify", "check": "the report exists",
                           "probe": {"kind": "file_exists",
                                     "path": "report.md"}}]
        results = mission_engine.evaluate_done_when(m, "")
        self.assertIs(results[0], True,
                        "found in the copy, where the worker wrote it")
        self.assertFalse(os.path.exists(os.path.join(self.repo, "report.md")))


class Wiring(Base):
    def setUp(self):
        super().setUp()
        self.saved = app_module._shadow_workdir_for_delegates
        app_module._shadow_workdir_for_delegates = lambda: self.repo

    def tearDown(self):
        app_module._shadow_workdir_for_delegates = self.saved
        super().tearDown()

    def test_40_a_new_task_gets_its_copy_stamped(self):
        m = self.task()
        got = asyncio.run(app_module._prepare_task_copy(m))
        self.assertEqual(got["workdir"], got["workspace"]["cwd"])
        self.assertEqual(self.store.load(m["id"])["workdir"], got["workdir"])
        self.assertEqual(app_module._brief_facts(got)["repo"], got["workdir"],
                         "the brief names the copy, not the founder's folder")

    def test_41_the_founders_own_chat_gets_no_copy(self):
        m = self.store.create("o", "feature", target_mode="existing",
                              done_when=[])
        got = asyncio.run(app_module._prepare_task_copy(m))
        self.assertNotIn("workspace", got)

    def test_42_the_spawn_starts_in_the_copy(self):
        src = open(app_module.__file__, encoding="utf-8").read()
        self.assertIn('mission.get("workdir") or _shadow_workdir_for_delegates(),'
                      "\n        _shadow_workspace.note_for_worker(", src)
        i = src.index("mission = await _prepare_task_copy(mission)")
        j = src.index("mission = await _compose_brief(mission)")
        self.assertLess(i, j, "the copy is made before the brief is written")

    def test_43_the_route_keeps_and_throws_away(self):
        client = TestClient(app_module.app, base_url="http://127.0.0.1")
        saved = providers.shadow_enabled
        providers.shadow_enabled = lambda: True
        try:
            m = self.task()
            ws = self.copy(m)
            write(os.path.join(ws["cwd"], "k.txt"), "keep me\n")
            self.end(m["id"], "stopped")
            r = client.post("/api/shadow/tasks/%s/workspace" % m["id"],
                            json={"action": "keep"}, headers=HDR)
            self.assertEqual(r.status_code, 200, r.text)
            self.assertEqual(r.json()["workspace"]["state"], "kept")
            self.assertTrue(os.path.exists(os.path.join(self.repo, "k.txt")))
            r = client.post("/api/shadow/tasks/%s/workspace" % m["id"],
                            json={"action": "keep"}, headers=HDR)
            self.assertEqual(r.status_code, 400, "nothing left to decide")
        finally:
            providers.shadow_enabled = saved


if __name__ == "__main__":
    unittest.main()
