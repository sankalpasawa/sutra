"""Tests for teamsutra.py — the durable task store.

What is pinned here, in order of importance:
1. creation is INERT (files at draft; a draft is never claimable)
2. a schema mismatch REFUSES rather than half-interprets
3. ordering is created_ms, never glob order, deterministic on ties
4. one corrupt file never halts a listing or a sweep
5. illegal transitions raise instead of corrupting
6. concurrent writers do not tear records (atomic tmp+replace)
"""
import concurrent.futures
import json
import os
import shutil
import stat
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


class TestTeamsutraStore(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix=".sutra-test-", dir=os.path.expanduser("~"))
        self._env = dict(os.environ)
        os.environ["SUTRA_UI_TEAMSUTRA"] = os.path.join(self.tmp, "teamsutra")
        import teamsutra
        self.T = teamsutra

    def tearDown(self):
        os.environ.clear()
        os.environ.update(self._env)
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _body(self, **kw):
        b = {"title": "panel: routines card misrenders",
             "body": "steps: open routines screen; expected a card; got raw id",
             "kind": "bug",
             "source": {"selection": "raw id renders", "screen": "routines",
                        "domain_ref": None}}
        b.update(kw)
        return b

    # ---- creation is inert ------------------------------------------------
    def test_create_files_at_draft(self):
        rec = self.T.create(self._body())
        self.assertEqual(rec["status"], "draft")
        self.assertEqual(rec["attempts"], 0)
        self.assertIsNone(rec["diff"])

    def test_a_draft_is_never_claimable(self):
        """The security argument for the unauthenticated port: an agent-filed
        record must have no effect until an operator acts."""
        self.T.create(self._body())
        self.assertEqual(self.T.claimable(), [])

    def test_queued_is_the_only_claimable_status(self):
        r = self.T.create(self._body())
        self.T.set_status(r["id"], "queued")
        ids = [t["id"] for t in self.T.claimable()]
        self.assertEqual(ids, [r["id"]])

    # ---- validation up front ----------------------------------------------
    def test_missing_title_refused(self):
        with self.assertRaises(ValueError):
            self.T.validate_new(self._body(title=""))

    def test_oversized_title_refused(self):
        with self.assertRaises(ValueError):
            self.T.validate_new(self._body(title="x" * 201))

    def test_unknown_kind_refused(self):
        with self.assertRaises(ValueError):
            self.T.validate_new(self._body(kind="feature"))

    def test_trivial_verify_refused(self):
        with self.assertRaises(ValueError):
            self.T.validate_new(self._body(verify="works"))

    def test_selection_is_capped_not_refused(self):
        rec = self.T.validate_new(self._body(
            source={"selection": "y" * 10_000}))
        self.assertEqual(len(rec["source"]["selection"]), self.T.SELECTION_MAX)

    def test_department_stays_null_when_absent(self):
        """Null, never guessed — a wrong address is the failure the placement
        layer exists to remove."""
        rec = self.T.create(self._body(source={"selection": "s"}))
        self.assertIsNone(rec["source"]["domain_ref"])
        self.assertIsNone(rec["source"]["domain_name"])

    # ---- schema gate -------------------------------------------------------
    def test_schema_mismatch_refuses(self):
        rec = self.T.create(self._body())
        p = self.T._path(rec["id"])
        raw = json.loads(p.read_text())
        raw["schema"] = 99
        p.write_text(json.dumps(raw))
        with self.assertRaises(ValueError) as cm:
            self.T.load(rec["id"])
        self.assertIn("Refusing to half-interpret", str(cm.exception))

    # ---- ordering ----------------------------------------------------------
    def test_ordering_is_created_ms_not_glob(self):
        a = self.T.create(self._body(title="first"))
        b = self.T.create(self._body(title="second"))
        c = self.T.create(self._body(title="third"))
        # Force created_ms out of any filename correlation
        for tid, ms in ((c["id"], 100), (a["id"], 200), (b["id"], 300)):
            p = self.T._path(tid)
            raw = json.loads(p.read_text())
            raw["created_ms"] = ms
            p.write_text(json.dumps(raw))
        titles = [r["title"] for r in self.T.listing()]
        self.assertEqual(titles, ["third", "first", "second"])

    def test_tie_breaks_on_id_deterministically(self):
        a = self.T.create(self._body())
        b = self.T.create(self._body())
        for tid in (a["id"], b["id"]):
            p = self.T._path(tid)
            raw = json.loads(p.read_text())
            raw["created_ms"] = 500
            p.write_text(json.dumps(raw))
        first = [r["id"] for r in self.T.listing()]
        second = [r["id"] for r in self.T.listing()]
        self.assertEqual(first, second)
        self.assertEqual(first, sorted(first))

    # ---- corruption --------------------------------------------------------
    def test_one_corrupt_file_never_halts_the_listing(self):
        good = self.T.create(self._body())
        bad = self.T.store_dir() / "t-deadbeef.json"
        bad.write_text("{ not json")
        rows = self.T.listing()
        ids = {r["id"] for r in rows}
        self.assertIn(good["id"], ids)
        self.assertIn("t-deadbeef", ids)
        corrupt = [r for r in rows if r["id"] == "t-deadbeef"][0]
        self.assertEqual(corrupt["status"], "corrupt")

    def test_corrupt_records_are_excluded_from_the_queue(self):
        r = self.T.create(self._body())
        self.T.set_status(r["id"], "queued")
        (self.T.store_dir() / "t-deadbeef.json").write_text("{ not json")
        self.assertEqual([t["id"] for t in self.T.claimable()], [r["id"]])

    # ---- transitions -------------------------------------------------------
    def test_illegal_transition_raises(self):
        r = self.T.create(self._body())
        with self.assertRaises(ValueError):
            self.T.set_status(r["id"], "needs_review")   # draft -> needs_review

    def test_done_is_terminal(self):
        r = self.T.create(self._body())
        self.T.set_status(r["id"], "queued")
        self.T.set_status(r["id"], "claimed")
        self.T.set_status(r["id"], "needs_review")
        self.T.set_status(r["id"], "done")
        with self.assertRaises(ValueError):
            self.T.set_status(r["id"], "queued")

    def test_claim_increments_attempts(self):
        r = self.T.create(self._body())
        self.T.set_status(r["id"], "queued")
        rec = self.T.set_status(r["id"], "claimed")
        self.assertEqual(rec["attempts"], 1)

    # ---- permissions -------------------------------------------------------
    def test_store_dir_0700_and_records_0600(self):
        rec = self.T.create(self._body())
        d_mode = stat.S_IMODE(os.stat(self.T.store_dir()).st_mode)
        f_mode = stat.S_IMODE(os.stat(self.T._path(rec["id"])).st_mode)
        self.assertEqual(d_mode, 0o700)
        self.assertEqual(f_mode, 0o600)

    # ---- concurrency (codex fold) ------------------------------------------
    def test_concurrent_creates_all_land_untorn(self):
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as ex:
            recs = list(ex.map(lambda i: self.T.create(self._body(title="t%d" % i)),
                               range(24)))
        self.assertEqual(len({r["id"] for r in recs}), 24)
        rows = self.T.listing()
        self.assertEqual(len(rows), 24)
        self.assertTrue(all(r["status"] == "draft" for r in rows))

    def test_concurrent_status_writes_leave_a_parseable_record(self):
        r = self.T.create(self._body())
        self.T.set_status(r["id"], "queued")
        def flip(i):
            try:
                self.T.set_status(r["id"], "claimed" if i % 2 else "queued")
            except (ValueError, FileNotFoundError):
                pass          # illegal transitions may race; tearing may not
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as ex:
            list(ex.map(flip, range(32)))
        rec = self.T.load(r["id"])   # must parse and pass the schema gate
        self.assertIn(rec["status"], self.T.STATUSES)


class TestApplyResult(unittest.TestCase):
    """record_apply_result (APPLY-DESIGN v1.1 D-A1): allowlisted provenance
    fields land WITHOUT a transition; anything else is refused loudly. This is
    the failure path of task.apply, so the guard here is what keeps a failed
    apply from ever moving or corrupting a task."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix=".sutra-test-", dir=os.path.expanduser("~"))
        self._env = dict(os.environ)
        os.environ["SUTRA_UI_TEAMSUTRA"] = os.path.join(self.tmp, "teamsutra")
        import teamsutra
        self.T = teamsutra

    def tearDown(self):
        os.environ.clear()
        os.environ.update(self._env)
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _task(self):
        return self.T.create({"title": "t", "body": "b", "kind": "bug",
                              "source": {"selection": None, "screen": "x",
                                         "domain_ref": None}})

    def test_allowlisted_fields_land_without_transition(self):
        rec = self._task()
        out = self.T.record_apply_result(rec["id"], pr_url="https://github.com/x/y/pull/1",
                                         pr_state="open", applied_at="2026-08-19")
        self.assertEqual(out["pr_url"], "https://github.com/x/y/pull/1")
        again = self.T.load(rec["id"])
        self.assertEqual(again["status"], "draft")      # status untouched
        self.assertEqual(again["pr_state"], "open")
        self.assertEqual(again["attempts"], 0)          # no claim side-effect

    def test_apply_error_persists_and_status_stays(self):
        rec = self._task()
        self.T.record_apply_result(rec["id"], apply_error="push: denied")
        again = self.T.load(rec["id"])
        self.assertEqual(again["apply_error"], "push: denied")
        self.assertEqual(again["status"], "draft")

    def test_protected_keys_refused(self):
        rec = self._task()
        for bad in ({"status": "done"}, {"id": "t-00000000"}, {"attempts": 9},
                    {"pr_url": "x", "diff": "stolen"}):
            with self.assertRaises(ValueError):
                self.T.record_apply_result(rec["id"], **bad)
        again = self.T.load(rec["id"])
        self.assertEqual(again["status"], "draft")
        self.assertNotIn("apply_error", again)

    def test_unknown_task_raises(self):
        with self.assertRaises(FileNotFoundError):
            self.T.record_apply_result("t-deadbeef", apply_error="x")


if __name__ == "__main__":
    unittest.main()
