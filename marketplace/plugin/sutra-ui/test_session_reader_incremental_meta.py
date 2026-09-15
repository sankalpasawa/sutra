"""2.278.8: the incremental title/head scan behind _claude_session_meta and
head_meta (a transcript that only grew costs its appended bytes, and the
answer always equals the whole-file scan 2.278.7 shipped), and the stat-first
live_agents behind /api/activity (only a live agent file is opened, and only
as far as its first user record).

stdlib unittest, in-process, against a fabricated ~/.claude/projects tree --
the same shape as test_activity.py, so the SHIPPED interpreter can run it.

Run: .venv/bin/python -m pytest -q test_session_reader_incremental_meta.py
 or: electron/payload/python/bin/python3 test_session_reader_incremental_meta.py -v
"""
import json
import os
import shutil
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import app  # noqa: E402
import session_reader as sr  # noqa: E402


def _line(d):
    return json.dumps(d) + "\n"


def _bump(p):
    """Make sure mtime moves even when two writes land in the same tick."""
    st = os.stat(p)
    os.utime(p, ns=(st.st_atime_ns, st.st_mtime_ns + 1_000_000))


def _reference_meta(p):
    """The whole-file scan exactly as 2.278.7 wrote it: title precedence and
    the `i <= 40` head window. The scanner must never disagree with it."""
    first_msg = cwd = branch = custom_title = ai_title = ""
    with p.open(encoding="utf-8", errors="replace") as fh:
        for i, line in enumerate(fh):
            head = i <= 40
            titley = "customTitle" in line or "aiTitle" in line
            if not head and not titley:
                continue
            try:
                d = json.loads(line)
            except ValueError:
                continue
            if titley:
                if d.get("type") == "custom-title" and isinstance(d.get("customTitle"), str):
                    custom_title = d["customTitle"].strip() or custom_title
                elif d.get("type") == "ai-title" and isinstance(d.get("aiTitle"), str):
                    ai_title = d["aiTitle"].strip() or ai_title
            if head:
                cwd = cwd or d.get("cwd", "")
                branch = branch or d.get("gitBranch", "")
                if not first_msg and d.get("type") == "user":
                    msg = d.get("message", {})
                    if isinstance(msg, dict) and not sr._is_tool_result(msg.get("content")):
                        t = sr._strip_injected(sr._text_of(msg.get("content")))
                        t = t.strip().replace("\n", " ")
                        if t and not t.startswith("<"):
                            first_msg = t[:90]
    return {"cwd": cwd, "branch": branch, "first_msg": first_msg,
            "custom_title": custom_title, "ai_title": ai_title}


class _Tmp(unittest.TestCase):
    def setUp(self):
        self._saved = sr.PROJECTS
        self.root = Path(tempfile.mkdtemp(prefix="sutra-test-incmeta-"))
        sr.PROJECTS = self.root
        sr._SCAN_CACHE.clear()
        sr._PROMPT_CACHE.clear()
        sr._META_CACHE.clear()

    def tearDown(self):
        sr.PROJECTS = self._saved
        shutil.rmtree(self.root, ignore_errors=True)


class TestScanMeta(_Tmp):
    def test_append_reads_only_the_tail_and_matches_the_full_scan(self):
        p = self.root / "-proj" / "s1.jsonl"
        p.parent.mkdir(parents=True)
        p.write_text(_line({"type": "user", "cwd": "/w/one", "gitBranch": "main",
                            "message": {"content": "first prompt"}})
                     + _line({"type": "assistant", "message": {"content": [{"type": "text", "text": "hi"}]}}),
                     encoding="utf-8")
        a = sr._scan_meta(p)
        self.assertEqual(a, _reference_meta(p))
        self.assertEqual(a["first_msg"], "first prompt")
        off1 = sr._SCAN_CACHE[str(p)]["offset"]
        self.assertEqual(off1, p.stat().st_size)
        with p.open("a", encoding="utf-8") as fh:
            fh.write(_line({"type": "ai-title", "aiTitle": "Auto Name"}))
            fh.write(_line({"type": "custom-title", "customTitle": "Chosen Name"}))
        _bump(p)
        b = sr._scan_meta(p)
        self.assertEqual(b, _reference_meta(p))
        self.assertEqual((b["custom_title"], b["ai_title"]), ("Chosen Name", "Auto Name"))
        st = sr._SCAN_CACHE[str(p)]
        self.assertEqual(st["offset"], p.stat().st_size)
        self.assertGreater(st["offset"], off1)
        self.assertEqual(st["lines_seen"], 4, "the head window counts lines across appends")
        # unchanged: the same answer, from the memo
        self.assertEqual(sr._scan_meta(p), b)

    def test_head_window_is_41_lines_across_appends(self):
        # a first prompt on line index 40 counts; on index 41 it does not (as before)
        for idx, expect in ((40, "late prompt"), (41, "")):
            p = self.root / "-proj" / ("h%d.jsonl" % idx)
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text("".join(_line({"type": "progress", "n": i}) for i in range(30)), encoding="utf-8")
            sr._scan_meta(p)
            with p.open("a", encoding="utf-8") as fh:
                for i in range(30, idx):
                    fh.write(_line({"type": "progress", "n": i}))
                fh.write(_line({"type": "user", "cwd": "/w/h", "message": {"content": "late prompt"}}))
            _bump(p)
            got = sr._scan_meta(p)
            self.assertEqual(got["first_msg"], expect, "line index %d" % idx)
            self.assertEqual(got, _reference_meta(p))

    def test_shrink_or_rewrite_rescans_from_zero(self):
        p = self.root / "-proj" / "s2.jsonl"
        p.parent.mkdir(parents=True)
        p.write_text(_line({"type": "user", "cwd": "/w/a", "message": {"content": "alpha"}})
                     + _line({"type": "custom-title", "customTitle": "Old"}), encoding="utf-8")
        sr._scan_meta(p)
        p.write_text(_line({"type": "user", "cwd": "/w/b", "message": {"content": "beta"}}), encoding="utf-8")
        _bump(p)                                          # shrunk
        got = sr._scan_meta(p)
        self.assertEqual((got["cwd"], got["first_msg"], got["custom_title"]), ("/w/b", "beta", ""))
        # rewritten LARGER from byte zero: the anchor no longer matches -> rescan
        p.write_text(_line({"type": "user", "cwd": "/w/c",
                            "message": {"content": "gamma rewritten with many more bytes than before"}})
                     + _line({"type": "ai-title", "aiTitle": "New"}), encoding="utf-8")
        _bump(p)
        got = sr._scan_meta(p)
        self.assertEqual(got, _reference_meta(p))
        self.assertEqual((got["cwd"], got["ai_title"]), ("/w/c", "New"))

    def test_unterminated_last_record_is_provisional(self):
        p = self.root / "-proj" / "s3.jsonl"
        p.parent.mkdir(parents=True)
        p.write_text(_line({"type": "user", "cwd": "/w/t", "message": {"content": "one"}})
                     + json.dumps({"type": "custom-title", "customTitle": "NoNewline"}), encoding="utf-8")
        got = sr._scan_meta(p)
        self.assertEqual(got["custom_title"], "NoNewline", "the whole-file scan saw it, so must this")
        self.assertEqual(got, _reference_meta(p))
        self.assertEqual(sr._SCAN_CACHE[str(p)]["custom_title"], "", "provisional only: not committed")
        with p.open("a", encoding="utf-8") as fh:
            fh.write("\n" + _line({"type": "ai-title", "aiTitle": "After"}))
        _bump(p)
        got = sr._scan_meta(p)
        self.assertEqual((got["custom_title"], got["ai_title"]), ("NoNewline", "After"))
        self.assertEqual(got, _reference_meta(p))
        self.assertEqual(sr._SCAN_CACHE[str(p)]["lines_seen"], 3, "no record counted twice")

    def test_readers_use_the_scanner_and_keep_their_shape(self):
        p = self.root / "-proj" / "s4.jsonl"
        p.parent.mkdir(parents=True)
        p.write_text(_line({"type": "user", "cwd": "/w/r", "gitBranch": "dev",
                            "message": {"content": "hello there"}}), encoding="utf-8")
        row = sr._claude_session_meta(p)
        self.assertEqual((row["title"], row["cwd"], row["branch"], row["title_source"], row["id"]),
                         ("hello there", "/w/r", "dev", "prompt", "s4"))
        self.assertEqual(sr.head_meta("s4"), {"title": "hello there", "cwd": "/w/r"})
        with p.open("a", encoding="utf-8") as fh:
            fh.write(_line({"type": "custom-title", "customTitle": "Renamed"}))
        _bump(p)
        self.assertEqual(sr.head_meta("s4")["title"], "Renamed")
        self.assertEqual(sr._claude_session_meta(p)["title_source"], "custom")
        self.assertEqual(sr.head_meta("nope"), {"title": "", "cwd": ""})


class TestLiveAgents(_Tmp):
    def _seed(self, now):
        proj = self.root / "-proj"
        proj.mkdir(parents=True, exist_ok=True)
        parent = proj / "parent.jsonl"
        parent.write_text(_line({"type": "user", "cwd": "/w/p", "message": {"content": "orchestrate"}}),
                          encoding="utf-8")
        os.utime(parent, (now - 600, now - 600))
        sub = proj / "parent" / "subagents"
        sub.mkdir(parents=True)
        files = {}
        for name, text, age in (("agent-live", "do the research task", 0),
                                ("agent-old", "a finished task", sr.ACTIVE_S + 300),
                                ("agent-older", "another finished task", sr.ACTIVE_S + 900)):
            f = sub / (name + ".jsonl")
            f.write_text(_line({"type": "user", "message": {"content": text}})
                         + _line({"type": "user", "message": {"content": "second user record must not win"}})
                         + _line({"type": "assistant", "message": {"content": [{"type": "text", "text": "ok"}]}}),
                         encoding="utf-8")
            os.utime(f, (now - age, now - age))
            files[name] = f
        return files

    def test_only_live_files_are_opened_and_never_fully_parsed(self):
        now = time.time()
        self._seed(now)
        opened = []
        real_open = Path.open

        def spy(self_, *a, **k):
            if str(self_).endswith(".jsonl"):
                opened.append(os.path.basename(str(self_)))
            return real_open(self_, *a, **k)

        def boom(*a, **k):
            raise AssertionError("a full parse must not run for the activity poll")

        saved = (sr._parse_transcript, sr._parent_tasks)
        sr._parse_transcript, sr._parent_tasks = boom, boom
        try:
            with mock.patch.object(Path, "open", spy):
                got = sr.live_agents("parent")
        finally:
            sr._parse_transcript, sr._parent_tasks = saved
        self.assertEqual([a["id"] for a in got], ["agent-live"])
        self.assertEqual(got[0]["label"], "do the research task")
        self.assertEqual(set(got[0].keys()), {"id", "label", "mtime"})
        self.assertEqual(opened, ["agent-live.jsonl"], "idle agent files are never opened")

    def test_prompt_memo_reuses_and_invalidates_on_rewrite(self):
        now = time.time()
        f = self._seed(now)["agent-live"]
        first = sr.live_agents("parent")[0]["label"]
        self.assertIn(str(f), sr._PROMPT_CACHE)
        with f.open("a", encoding="utf-8") as fh:        # append: memo reused
            fh.write(_line({"type": "assistant", "message": {"content": [{"type": "text", "text": "more"}]}}))
        os.utime(f, (now, now))
        self.assertEqual(sr.live_agents("parent")[0]["label"], first)
        # truncate-and-rewrite with a different prompt: same inode, larger size
        f.write_text(_line({"type": "user", "message": {"content": "a completely different spawning prompt with more bytes"}})
                     + _line({"type": "user", "message": {"content": "x"}}), encoding="utf-8")
        os.utime(f, (now, now))
        self.assertEqual(sr.live_agents("parent")[0]["label"],
                         "a completely different spawning prompt with more bytes")

    def test_api_activity_uses_live_agents(self):
        now = time.time()
        self._seed(now)
        saved = sr.list_agents

        def boom(*a, **k):
            raise AssertionError("/api/activity must not list every agent")

        sr.list_agents = boom
        try:
            out = app.api_activity()
        finally:
            sr.list_agents = saved
        self.assertEqual([a["id"] for a in out["agents"]], ["agent-live"])
        self.assertEqual(set(out["agents"][0].keys()), {"parent_sid", "id", "label", "elapsed_s"})
        self.assertEqual(out["count"], len(out["turns"]) + len(out["agents"]))


if __name__ == "__main__":
    unittest.main()
