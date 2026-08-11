"""Unit tests for the live-Activity backend (app.api_activity + session_reader).

WHY A SEPARATE FILE
-------------------
test_app.py spawns a real uvicorn subprocess (via .venv/bin/python) and drives
the HTTP surface. These tests want the OPPOSITE: no server, no network, no
extra deps -- just the endpoint function and the reader, called in-process
against a fabricated ~/.claude/projects tree. That makes them runnable under
the SHIPPED interpreter (electron/payload/python/bin/python3), which carries
fastapi/starlette/uvicorn but NOT httpx/pytest -- so starlette's TestClient
(needs httpx) is off the table and calling api_activity() directly is the only
dependency-free way in. stdlib unittest only.

Run (bundled interpreter, no pytest):
    electron/payload/python/bin/python3 test_activity.py -v
Run (dev venv, same as the rest of the suite):
    .venv/bin/python -m unittest test_activity -v

The endpoint's liveness/title/agent semantics all come from session_reader,
whose PROJECTS constant is the single root every helper globs against. Every
test repoints session_reader.PROJECTS at a fresh tempdir, writes transcript
files with controlled mtimes, and restores it -- so a run never reads (or
writes) the operator's real ~/.claude/projects.
"""
import json
import os
import shutil
import sys
import tempfile
import time
import unittest
from pathlib import Path

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

# importing app has import-time banners (org_api) but no server side effects.
import app  # noqa: E402
import session_reader as sr  # noqa: E402


def _write(path: Path, records, mtime=None):
    """Write a .jsonl transcript from a list of dict records (or raw strings for
    garbage lines), then optionally stamp its mtime."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for r in records:
            fh.write((r if isinstance(r, str) else json.dumps(r)) + "\n")
    if mtime is not None:
        os.utime(path, (mtime, mtime))


class _PatchedProjects(unittest.TestCase):
    """Base: give each test a fresh, isolated PROJECTS root and restore it."""

    def setUp(self):
        self._saved_projects = sr.PROJECTS
        self.root = Path(tempfile.mkdtemp(prefix="sutra-test-activity-"))
        sr.PROJECTS = self.root
        # app referenced the SAME module object (import session_reader as sr),
        # so this one rebind is seen by api_activity's sr.index()/head_meta().
        self.assertIs(app.sr, sr, "app must share the session_reader module")

    def tearDown(self):
        sr.PROJECTS = self._saved_projects
        shutil.rmtree(self.root, ignore_errors=True)


class TestActivityEndpoint(_PatchedProjects):
    """app.api_activity() -- the /api/activity handler, called directly."""

    def test_response_shape_and_count_arithmetic(self):
        """count == len(turns)+len(agents); every turn/agent carries the exact
        keys the drawer renders (10-activity.js reads sid/title/cwd/elapsed_s and
        parent_sid/id/label/elapsed_s by name)."""
        now = time.time()
        proj = self.root / "-Users-x-proj"
        _write(proj / "sess-active.jsonl",
               [{"type": "user", "cwd": "/Users/x/proj",
                 "message": {"content": "build the feature"}}],
               mtime=now)

        out = app.api_activity()

        # top-level contract
        self.assertEqual(set(out.keys()), {"turns", "agents", "count"})
        self.assertIsInstance(out["turns"], list)
        self.assertIsInstance(out["agents"], list)
        self.assertIsInstance(out["count"], int)
        self.assertEqual(out["count"], len(out["turns"]) + len(out["agents"]),
                         "count must be the sum of the two lists, never a guess")

        self.assertEqual(len(out["turns"]), 1)
        turn = out["turns"][0]
        self.assertEqual(set(turn.keys()), {"sid", "title", "cwd", "elapsed_s"})
        self.assertEqual(turn["sid"], "sess-active")
        self.assertEqual(turn["title"], "build the feature")
        self.assertEqual(turn["cwd"], "/Users/x/proj")
        self.assertIsInstance(turn["elapsed_s"], int)
        self.assertGreaterEqual(turn["elapsed_s"], 0)

    def test_a_session_is_a_turn_iff_it_is_active(self):
        """The whole point of the panel: only work happening RIGHT NOW shows.
        `active` == liveness == "active" == transcript written within ACTIVE_S.
        Build one active + one idle session (no subagents, so each session's own
        mtime decides) and require exactly the active one to surface."""
        now = time.time()
        proj = self.root / "-Users-x-proj"
        _write(proj / "live.jsonl",
               [{"type": "user", "cwd": "/w/live", "message": {"content": "now"}}],
               mtime=now)                      # age ~0 -> active
        idle_mtime = now - (sr.ACTIVE_S + 120)  # comfortably past the 45s window
        _write(proj / "idle.jsonl",
               [{"type": "user", "cwd": "/w/idle", "message": {"content": "later"}}],
               mtime=idle_mtime)

        # sanity: the helper the endpoint reuses agrees with the fixture design
        self.assertEqual(sr.liveness(now, now), "active")
        self.assertEqual(sr.liveness(idle_mtime, now), "idle")

        out = app.api_activity()
        sids = [t["sid"] for t in out["turns"]]
        self.assertIn("live", sids, "the active session must appear as a turn")
        self.assertNotIn("idle", sids,
                         "an idle session is not a running turn -- it must NOT appear")
        self.assertEqual(out["agents"], [])
        self.assertEqual(out["count"], 1)

    def test_agents_include_only_running_ones_with_the_right_shape(self):
        """agents[] lists ONLY subagents whose transcript is live (running==True).
        A parent with one running + one idle agent must yield exactly the running
        one, keyed to its parent, with the drawer's field set."""
        now = time.time()
        proj = self.root / "-Users-x-proj"
        # parent transcript itself is idle; index() folds the live agent's mtime
        # onto it, which (correctly) also makes the parent a running turn.
        _write(proj / "parent.jsonl",
               [{"type": "user", "cwd": "/w/p", "message": {"content": "orchestrate"}}],
               mtime=now - (sr.ACTIVE_S + 120))
        sub = proj / "parent" / "subagents"
        _write(sub / "agent-run.jsonl",
               [{"type": "user", "message": {"content": "do the research task"}}],
               mtime=now)                              # running
        _write(sub / "agent-old.jsonl",
               [{"type": "user", "message": {"content": "a finished task"}}],
               mtime=now - (sr.ACTIVE_S + 300))        # NOT running

        out = app.api_activity()

        self.assertEqual(out["count"], len(out["turns"]) + len(out["agents"]))
        self.assertEqual(len(out["agents"]), 1,
                         "exactly the running agent -- the idle one is excluded")
        ag = out["agents"][0]
        self.assertEqual(set(ag.keys()), {"parent_sid", "id", "label", "elapsed_s"})
        self.assertEqual(ag["parent_sid"], "parent")
        self.assertEqual(ag["id"], "agent-run")
        self.assertEqual(ag["label"], "do the research task")
        self.assertIsInstance(ag["elapsed_s"], int)

        ids = [a["id"] for a in out["agents"]]
        self.assertNotIn("agent-old", ids, "an idle agent must never be reported running")
        # the bumped parent is a live turn (the live agent's write counts as the
        # session being written) -- assert that folding actually happened rather
        # than leave it implicit.
        self.assertIn("parent", [t["sid"] for t in out["turns"]])

    def test_no_live_work_is_an_empty_but_well_formed_response(self):
        """Nothing active anywhere -> both lists empty, count 0, shape intact.
        The drawer renders "No active work" off exactly this."""
        proj = self.root / "-Users-x-proj"
        _write(proj / "stale.jsonl",
               [{"type": "user", "message": {"content": "old"}}],
               mtime=time.time() - (sr.IDLE_S + 3600))  # stale
        out = app.api_activity()
        self.assertEqual(out, {"turns": [], "agents": [], "count": 0})

    def test_empty_projects_dir_does_not_raise(self):
        out = app.api_activity()
        self.assertEqual(out, {"turns": [], "agents": [], "count": 0})


class TestHeadMeta(_PatchedProjects):
    """session_reader.head_meta -- title precedence, cwd, and fail-soft."""

    def _seed(self, sid, records):
        _write(self.root / "-proj" / (sid + ".jsonl"), records)

    def test_custom_title_wins_over_ai_title_and_first_message(self):
        self._seed("s1", [
            {"type": "user", "cwd": "/w/one", "message": {"content": "first prompt text"}},
            {"type": "ai-title", "aiTitle": "AI Suggested Name"},
            {"type": "custom-title", "customTitle": "Operator Chosen"},
        ])
        meta = sr.head_meta("s1")
        self.assertEqual(meta["title"], "Operator Chosen")
        self.assertEqual(meta["cwd"], "/w/one")

    def test_ai_title_wins_over_first_message_when_no_custom(self):
        self._seed("s2", [
            {"type": "user", "cwd": "/w/two", "message": {"content": "first prompt text"}},
            {"type": "ai-title", "aiTitle": "AI Suggested Name"},
        ])
        meta = sr.head_meta("s2")
        self.assertEqual(meta["title"], "AI Suggested Name")
        self.assertEqual(meta["cwd"], "/w/two")

    def test_first_user_message_is_the_last_resort_title(self):
        self._seed("s3", [
            {"type": "user", "cwd": "/w/three", "message": {"content": "just the first message"}},
        ])
        meta = sr.head_meta("s3")
        self.assertEqual(meta["title"], "just the first message")
        self.assertEqual(meta["cwd"], "/w/three")

    def test_missing_session_fails_soft_to_blanks(self):
        meta = sr.head_meta("does-not-exist-anywhere")
        self.assertEqual(meta, {"title": "", "cwd": ""})

    def test_path_traversal_id_is_refused_softly(self):
        meta = sr.head_meta("../../etc/passwd")
        self.assertEqual(meta, {"title": "", "cwd": ""})

    def test_garbage_transcript_yields_no_prompt_not_an_exception(self):
        # non-JSON lines, and a user record whose text is an attachment stub
        # (starts with "<", which the reader skips) -> no usable title.
        _write(self.root / "-proj" / "s4.jsonl",
               ["this is not json {{{{",
                "",
                json.dumps({"type": "user", "message": {"content": "<attachment>"}})])
        meta = sr.head_meta("s4")
        self.assertEqual(meta["title"], "(no prompt)")
        self.assertEqual(meta["cwd"], "")


if __name__ == "__main__":
    # Plain-python entry point so the SHIPPED interpreter (no pytest) can run
    # this directly: electron/payload/python/bin/python3 test_activity.py -v
    unittest.main()
