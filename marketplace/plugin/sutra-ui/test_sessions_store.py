"""Contract for Sutra-owned sessions.

The load-bearing claim is that a conversation survives a change of provider.
Most of these tests exist to hold that claim to account.
"""

import json
import os
import shutil
import tempfile
import unittest

import sessions_store as ss


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="sutra-sessions-")
        self._old = os.environ.get("SUTRA_UI_SESSIONS")
        os.environ["SUTRA_UI_SESSIONS"] = self.tmp

    def tearDown(self):
        if self._old is None:
            os.environ.pop("SUTRA_UI_SESSIONS", None)
        else:
            os.environ["SUTRA_UI_SESSIONS"] = self._old
        shutil.rmtree(self.tmp, ignore_errors=True)


class TestIdentity(Base):
    def test_created_without_any_provider(self):
        """The inversion this module exists for: a session before a model runs."""
        m = ss.create(title="planning", cwd="/w")
        self.assertTrue(ss.is_sutra_id(m["id"]))
        self.assertEqual(m["handles"], {})
        self.assertEqual(m["turns"], 0)
        self.assertIsNotNone(ss.read(m["id"]))

    def test_ids_are_prefixed_and_distinct_from_provider_uuids(self):
        import uuid as _u
        raw = _u.uuid4().hex
        self.assertFalse(ss.is_sutra_id(raw))
        self.assertTrue(ss.new_id().startswith(ss.ID_PREFIX))
        self.assertNotEqual(ss.new_id(), ss.new_id())

    def test_path_traversal_refused(self):
        for bad in ("s_../../etc", "s_a/b", "../x", "s_a\\b", "s_..", "/etc/passwd"):
            with self.assertRaises(ValueError, msg=bad):
                ss._dir_for(bad)
            # and the public reader refuses it quietly rather than escaping
            self.assertIsNone(ss.read(bad), bad)

    def test_foreign_id_is_refused_not_silently_created(self):
        with self.assertRaises(ValueError):
            ss.create(sid="9f8e7d6c-1234-4321-abcd-000000000000")


class TestHandles(Base):
    def test_bind_and_read_back(self):
        m = ss.create(provider="claude")
        ss.bind_handle(m["id"], "claude", "claude-uuid-1")
        self.assertEqual(ss.handle_for(m["id"], "claude"), "claude-uuid-1")
        self.assertIsNone(ss.handle_for(m["id"], "deepseek"))

    def test_second_provider_does_not_clobber_first(self):
        """The reason handles is a dict and update() merges it."""
        m = ss.create(provider="claude")
        ss.bind_handle(m["id"], "claude", "c-1")
        ss.bind_handle(m["id"], "deepseek", "d-1")
        self.assertEqual(ss.handle_for(m["id"], "claude"), "c-1")
        self.assertEqual(ss.handle_for(m["id"], "deepseek"), "d-1")

    def test_update_merges_handles_rather_than_replacing(self):
        m = ss.create()
        ss.update(m["id"], handles={"claude": "c-1"})
        ss.update(m["id"], title="renamed")
        self.assertEqual(ss.handle_for(m["id"], "claude"), "c-1")
        self.assertEqual(ss.read(m["id"])["title"], "renamed")

    def test_empty_handle_is_not_recorded(self):
        m = ss.create()
        ss.bind_handle(m["id"], "claude", "")
        self.assertEqual(ss.read(m["id"])["handles"], {})


class TestResumePlan(Base):
    def test_native_when_provider_has_a_handle(self):
        m = ss.create(provider="claude")
        ss.bind_handle(m["id"], "claude", "c-1")
        self.assertEqual(ss.resume_plan(m["id"], "claude"), ("native", "c-1"))

    def test_replay_when_switching_provider_mid_conversation(self):
        """The case the whole module is for."""
        m = ss.create(provider="claude")
        ss.bind_handle(m["id"], "claude", "c-1")
        ss.append_turn(m["id"], "user", "hello", provider="claude")
        kind, ref = ss.resume_plan(m["id"], "deepseek")
        self.assertEqual(kind, "replay")
        self.assertEqual(ref, m["id"])

    def test_fresh_when_nothing_to_replay(self):
        m = ss.create()
        self.assertEqual(ss.resume_plan(m["id"], "deepseek"), ("fresh", m["id"]))

    def test_unknown_session_is_fresh_not_an_exception(self):
        self.assertEqual(ss.resume_plan("s_doesnotexist", "claude")[0], "fresh")


class TestTranscript(Base):
    def test_append_and_read_in_order(self):
        m = ss.create()
        ss.append_turn(m["id"], "user", "one")
        ss.append_turn(m["id"], "assistant", "two")
        got = [(t["role"], t["text"]) for t in ss.transcript(m["id"])]
        self.assertEqual(got, [("user", "one"), ("assistant", "two")])
        self.assertEqual(ss.read(m["id"])["turns"], 2)

    def test_torn_line_does_not_destroy_history(self):
        """Power loss mid-append must cost the last turn, not the conversation."""
        m = ss.create()
        ss.append_turn(m["id"], "user", "kept")
        p = os.path.join(self.tmp, m["id"], "transcript.jsonl")
        with open(p, "a", encoding="utf-8") as fh:
            fh.write('{"schema":1,"role":"assist')     # torn, no newline
        got = [t["text"] for t in ss.transcript(m["id"])]
        self.assertEqual(got, ["kept"])

    def test_survives_unicode(self):
        m = ss.create()
        ss.append_turn(m["id"], "user", "नमस्ते 🌍 “quoted”")
        self.assertEqual(ss.transcript(m["id"])[0]["text"], "नमस्ते 🌍 “quoted”")

    def test_concurrent_appends_do_not_interleave_within_a_line(self):
        """O_APPEND single-write: every line must still parse."""
        import threading
        m = ss.create()
        def worker(n):
            for i in range(25):
                ss.append_turn(m["id"], "user", "w%d-%d %s" % (n, i, "x" * 200))
        ts = [threading.Thread(target=worker, args=(n,)) for n in range(4)]
        [t.start() for t in ts]
        [t.join() for t in ts]
        p = os.path.join(self.tmp, m["id"], "transcript.jsonl")
        with open(p, encoding="utf-8") as fh:
            lines = [l for l in fh.read().split("\n") if l.strip()]
        self.assertEqual(len(lines), 100)
        for l in lines:
            json.loads(l)          # raises if a line was torn by interleaving

    def test_concurrent_appends_keep_an_accurate_turn_count(self):
        """turns is incremented inside the meta lock. Read-modify-write from the
        caller counted 25 of 100."""
        import threading
        m = ss.create()
        def w(n):
            for i in range(25):
                ss.append_turn(m["id"], "user", "x%d-%d" % (n, i))
        ts = [threading.Thread(target=w, args=(n,)) for n in range(4)]
        [t.start() for t in ts]
        [t.join() for t in ts]
        self.assertEqual(ss.read(m["id"])["turns"], 100)

    def test_concurrent_handle_binds_lose_nothing(self):
        """Measured 135/160 lost before update() took a lock."""
        import threading
        m = ss.create()
        provs = ["p%d" % i for i in range(8)]
        ts = [threading.Thread(target=ss.bind_handle, args=(m["id"], p, "h-" + p))
              for p in provs]
        [t.start() for t in ts]
        [t.join() for t in ts]
        self.assertEqual(len(ss.read(m["id"])["handles"]), 8)

    def test_stale_lock_is_broken_not_waited_on(self):
        """A crashed writer must not wedge a session forever."""
        import time as _t
        m = ss.create()
        lockp = os.path.join(self.tmp, m["id"], "meta.json.lock")
        open(lockp, "w").close()
        os.utime(lockp, (0, 0))                      # ancient => abandoned
        t0 = _t.time()
        ss.update(m["id"], title="through")
        self.assertLess(_t.time() - t0, 2.0, "waited on a stale lock")
        self.assertEqual(ss.read(m["id"])["title"], "through")


class TestListing(Base):
    def test_newest_first_and_corrupt_record_skipped(self):
        a = ss.create(title="a")
        b = ss.create(title="b")
        ss.update(b["id"], title="b2")
        ids = [r["id"] for r in ss.listing()]
        self.assertEqual(ids[0], b["id"])
        # corrupt one record -> the OTHER must still list
        with open(os.path.join(self.tmp, a["id"], "meta.json"), "w") as fh:
            fh.write("{not json")
        ids = [r["id"] for r in ss.listing()]
        self.assertEqual(ids, [b["id"]])

    def test_empty_store_is_empty_list_not_error(self):
        self.assertEqual(ss.listing(), [])

    def test_stray_directory_ignored(self):
        os.mkdir(os.path.join(self.tmp, "not-a-session"))
        ss.create(title="real")
        self.assertEqual(len(ss.listing()), 1)


class TestDurability(Base):
    def test_meta_write_is_atomic(self):
        """No .tmp left behind, and the file always parses."""
        m = ss.create(title="x")
        for i in range(20):
            ss.update(m["id"], title="t%d" % i)
        files = os.listdir(os.path.join(self.tmp, m["id"]))
        self.assertNotIn(True, [f.endswith(".tmp") or ".tmp" in f for f in files], files)
        self.assertEqual(ss.read(m["id"])["title"], "t19")

    def test_delete_removes_sutra_record_only(self):
        m = ss.create()
        self.assertTrue(ss.delete(m["id"]))
        self.assertIsNone(ss.read(m["id"]))
        self.assertFalse(ss.delete(m["id"]))

    def test_store_dir_is_private(self):
        m = ss.create()
        mode = os.stat(os.path.join(self.tmp, m["id"])).st_mode & 0o777
        self.assertEqual(mode & 0o077, 0, "session dir is group/world readable")


if __name__ == "__main__":
    unittest.main(verbosity=2)
