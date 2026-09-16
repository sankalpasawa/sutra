"""PLAN-100 S38/S39/S41: verify tool, mission_update, feed contract stub."""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = os.path.dirname(os.path.abspath(__file__))

import shadow_feed
import shadow_ledger


def _item(**over):
    base = {"item_id": "f-1", "producer": "shadow", "kind": "needs_decision",
            "title": "Mission m-1 needs a yes", "deep_link": "sutra://shadow/t-1",
            "dedupe_key": "m-1:brief", "state": "new"}
    base.update(over)
    return base


class TestFeedContract(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        os.environ["SUTRA_SHADOW_HOME"] = self.tmp.name

    def tearDown(self):
        os.environ.pop("SUTRA_SHADOW_HOME", None)
        self.tmp.cleanup()

    def test_01_valid_item_accepted_once(self):
        ok, problems = shadow_feed.emit(_item())
        self.assertTrue(ok, problems)
        ok, problems = shadow_feed.emit(_item())
        self.assertFalse(ok)
        self.assertIn("duplicate dedupe_key", problems)

    def test_02_missing_required_field_rejected(self):
        bad = _item()
        del bad["deep_link"]
        ok, problems = shadow_feed.emit(bad)
        self.assertFalse(ok)
        self.assertTrue(any("deep_link" in p for p in problems))

    def test_03_unknown_fields_rejected(self):
        ok, problems = shadow_feed.emit(_item(surprise="x"))
        self.assertFalse(ok)

    def test_04_unknown_state_rejected(self):
        ok, problems = shadow_feed.emit(_item(state="vibing"))
        self.assertFalse(ok)


class _Store:
    """The two MissionStore reads live_items() makes, over a dict."""
    def __init__(self, missions):
        self.m = {x["id"]: x for x in missions}

    def load(self, mid):
        return self.m.get(mid)

    def list(self, states=None):
        return [x for x in self.m.values()
                if states is None or x["state"] in states]


def _mission(mid, state, **over):
    base = {"id": mid, "state": state, "version": 1,
            "objective": "task " + mid, "target_session": None}
    base.update(over)
    return base


def _rows():
    """Read the feed file back as a list of rows."""
    with open(shadow_feed._feed_path(), encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


class TestFeedRelevance(unittest.TestCase):
    """Founder 2026-09-16: "a lot of tasks in my Now, but they are not
    relevant". A card lives only while its task exists and waits on the
    founder; one card per task; delete retires; rows carry ts."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        os.environ["SUTRA_SHADOW_HOME"] = self.tmp.name

    def tearDown(self):
        os.environ.pop("SUTRA_SHADOW_HOME", None)
        self.tmp.cleanup()

    def test_07_emit_stamps_ts(self):
        ok, _ = shadow_feed.emit(_item())
        self.assertTrue(ok)
        row = _rows()[0]
        self.assertIsInstance(row.get("ts"), float)
        # a producer that brings its own ts keeps it
        ok, _ = shadow_feed.emit(_item(item_id="f-2", dedupe_key="k2", ts=5.0))
        self.assertTrue(ok)
        self.assertEqual(_rows()[1]["ts"], 5.0)

    def test_08_live_items_keeps_only_what_waits_on_the_founder(self):
        now = 1_000_000.0
        store = _Store([
            _mission("m-blocked", "blocked"),
            _mission("m-done", "done"),
            _mission("m-fresh-fail", "failed"),
            _mission("m-old-fail", "failed"),
            _mission("m-legacy-fail", "failed"),
            _mission("m-took-over", "paused", pause_reason="founder_intervened"),
            _mission("m-restart", "paused", pause_reason="app_restart"),
            _mission("m-held", "paused", pause_reason="floor_confirm",
                     pending_say="may I?"),
            _mission("m-running", "running", target_session="s-live"),
            _mission("m-stalled-blocked", "blocked"),
            _mission("m-ended", "failed", target_session="s-dead"),
        ])
        emit = shadow_feed.emit

        def mrow(mid, kind="needs_decision", **over):
            base = {"item_id": "f-%s" % mid, "producer": "shadow", "kind": kind,
                    "mission_id": mid, "title": "task " + mid,
                    "deep_link": "sutra://shadow/mission/%s" % mid,
                    "dedupe_key": "k-" + mid, "state": "new", "ts": now}
            base.update(over)
            return base
        self.assertTrue(emit(mrow("m-blocked"))[0])
        self.assertTrue(emit(mrow("m-done", kind="info"))[0])
        self.assertTrue(emit(mrow("m-gone"))[0])
        self.assertTrue(emit(mrow("m-fresh-fail", ts=now - 3600))[0])
        self.assertTrue(emit(mrow("m-old-fail", ts=now - 90_000))[0])
        # a row from before ts existed cannot come through emit() (it
        # stamps one); it is what the founder's feed holds today
        legacy = mrow("m-legacy-fail")
        del legacy["ts"]
        with open(shadow_feed._feed_path(), "a", encoding="utf-8") as out:
            out.write(json.dumps(legacy) + "\n")
        self.assertTrue(emit(mrow("m-took-over"))[0])
        self.assertTrue(emit(mrow("m-restart"))[0])
        self.assertTrue(emit(mrow("m-held"))[0])
        # stall rows carry no mission_id, only the deep link
        self.assertTrue(emit({
            "item_id": "stall-m-running", "producer": "shadow",
            "kind": "needs_decision", "title": "stalled",
            "deep_link": "sutra://shadow/mission/m-running",
            "dedupe_key": "stall:m-running", "state": "new"})[0])
        self.assertTrue(emit({
            "item_id": "stall-m-stalled-blocked", "producer": "shadow",
            "kind": "needs_decision", "title": "stalled",
            "deep_link": "sutra://shadow/mission/m-stalled-blocked",
            "dedupe_key": "stall:m-stalled-blocked", "state": "new"})[0])
        # rescue rows are keyed to a session, not a mission
        self.assertTrue(emit({
            "item_id": "rescue-s-live", "producer": "shadow",
            "kind": "needs_decision", "title": "Session s-live hit an error",
            "deep_link": "sutra://shadow/session/s-live",
            "dedupe_key": "rescue:s-live", "state": "new"})[0])
        self.assertTrue(emit({
            "item_id": "rescue-s-dead", "producer": "shadow",
            "kind": "needs_decision", "title": "Session s-dead hit an error",
            "deep_link": "sutra://shadow/session/s-dead",
            "dedupe_key": "rescue:s-dead", "state": "new"})[0])
        # a row from another producer, about nothing Shadow owns: kept
        self.assertTrue(emit(_item(item_id="f-other", producer="coach",
                                   dedupe_key="coach:1"))[0])
        # an already-handled row stays handled and is never served
        self.assertTrue(emit(mrow("m-blocked", item_id="f-m-blocked-old",
                                  dedupe_key="k-old", state="handled"))[0])

        live = shadow_feed.live_items(store, now=now)
        self.assertEqual(
            sorted(it["item_id"] for it in live),
            sorted(["f-m-blocked", "f-m-fresh-fail", "f-m-restart",
                    "f-m-held", "stall-m-running", "rescue-s-live",
                    "f-other"]))
        # the rows that failed the rule are persisted as expired ...
        states = {r["item_id"]: r["state"] for r in _rows()}
        for iid in ("f-m-done", "f-m-gone", "f-m-old-fail",
                    "f-m-legacy-fail", "f-m-took-over",
                    "stall-m-stalled-blocked", "rescue-s-dead"):
            self.assertEqual(states[iid], "expired", iid)
        # ... handled stays handled, live stays new
        self.assertEqual(states["f-m-blocked-old"], "handled")
        self.assertEqual(states["f-m-blocked"], "new")
        # ... and an expired dedupe_key still blocks a re-emit
        self.assertFalse(emit(mrow("m-gone"))[0])
        # a second read is a pure read: nothing changes
        before = _rows()
        shadow_feed.live_items(store, now=now)
        self.assertEqual(before, _rows())

    def test_09_retire_by_mission_keeps_the_named_card(self):
        for n in (1, 2, 3):
            shadow_feed.emit(_item(item_id="f-%d" % n, mission_id="m-9",
                                   dedupe_key="m-9:%d" % n))
        shadow_feed.emit(_item(item_id="f-x", mission_id="m-x",
                               dedupe_key="m-x:1"))
        self.assertEqual(shadow_feed.retire(mission_id="m-9",
                                            keep_item_id="f-3"), 2)
        states = {r["item_id"]: r["state"] for r in _rows()}
        self.assertEqual(states, {"f-1": "expired", "f-2": "expired",
                                  "f-3": "new", "f-x": "new"})
        # idempotent
        self.assertEqual(shadow_feed.retire(mission_id="m-9"), 1)
        self.assertEqual(shadow_feed.retire(mission_id="m-9"), 0)

    def test_10_retire_by_session_covers_rescue_rows(self):
        shadow_feed.emit({
            "item_id": "rescue-s-1", "producer": "shadow",
            "kind": "needs_decision", "title": "Session s-1 hit an error",
            "deep_link": "sutra://shadow/session/s-1",
            "dedupe_key": "rescue:s-1:a", "state": "new"})
        shadow_feed.emit(_item(item_id="f-1", dedupe_key="k1"))
        self.assertEqual(shadow_feed.retire(session_id="s-1"), 1)
        states = {r["item_id"]: r["state"] for r in _rows()}
        self.assertEqual(states, {"rescue-s-1": "expired", "f-1": "new"})

    def test_11_one_card_per_task_from_the_mission_emitter(self):
        import mission_engine
        m = _mission("m-1", "paused", pause_reason="app_restart")
        self.assertTrue(mission_engine.emit_mission_feed(
            m, "needs_decision", "app_restart")[0])
        m = dict(m, state="blocked", version=2)
        self.assertTrue(mission_engine.emit_mission_feed(
            m, "needs_decision", "needs_founder")[0])
        states = {r["item_id"]: r["state"] for r in _rows()}
        self.assertEqual(states, {"f-m-1-paused-v1": "expired",
                                  "f-m-1-blocked-v2": "new"})
        # a duplicate emit retires nothing
        self.assertFalse(mission_engine.emit_mission_feed(
            m, "needs_decision", "needs_founder")[0])
        self.assertEqual({r["item_id"]: r["state"] for r in _rows()},
                         states)

    def test_13_foreign_producer_ids_are_not_shadow_shapes(self):
        # a coach row whose id happens to start with stall- is about
        # nothing Shadow owns: kept, never judged against the store
        store = _Store([])
        self.assertTrue(shadow_feed.emit(_item(
            item_id="stall-coach-1", producer="coach",
            deep_link="sutra://coach/1", dedupe_key="c:1"))[0])
        self.assertTrue(shadow_feed.emit(_item(
            item_id="rescue-coach-1", producer="coach",
            deep_link="sutra://coach/2", dedupe_key="c:2"))[0])
        self.assertEqual(
            sorted(it["item_id"] for it in shadow_feed.live_items(store)),
            ["rescue-coach-1", "stall-coach-1"])

    def test_14_emitter_retire_spares_another_producers_card(self):
        import mission_engine
        self.assertTrue(shadow_feed.emit(_item(
            item_id="coach-m-1", producer="coach", mission_id="m-1",
            dedupe_key="coach:m-1"))[0])
        m = _mission("m-1", "paused", pause_reason="app_restart")
        self.assertTrue(mission_engine.emit_mission_feed(
            m, "needs_decision", "app_restart")[0])
        m = dict(m, state="blocked", version=2)
        self.assertTrue(mission_engine.emit_mission_feed(
            m, "needs_decision", "needs_founder")[0])
        states = {r["item_id"]: r["state"] for r in _rows()}
        self.assertEqual(states, {"coach-m-1": "new",
                                  "f-m-1-paused-v1": "expired",
                                  "f-m-1-blocked-v2": "new"})
        # delete retires every producer's card: the task is gone
        self.assertEqual(shadow_feed.retire(mission_id="m-1"), 2)

    def test_12_mission_of_reads_field_then_link_then_id(self):
        self.assertEqual(shadow_feed.mission_of({"mission_id": "m-a"}), "m-a")
        self.assertEqual(shadow_feed.mission_of(
            {"deep_link": "sutra://shadow/mission/m-b"}), "m-b")
        self.assertEqual(shadow_feed.mission_of(
            {"item_id": "stall-m-c", "deep_link": "", "producer": "shadow"}),
            "m-c")
        # the id shape is Shadow's own: no producer, no meaning
        self.assertIsNone(shadow_feed.mission_of(
            {"item_id": "stall-m-c", "deep_link": ""}))
        self.assertIsNone(shadow_feed.mission_of(
            {"item_id": "rescue-s-1", "producer": "shadow",
             "deep_link": "sutra://shadow/session/s-1"}))
        self.assertEqual(shadow_feed.session_of(
            {"item_id": "rescue-s-1", "producer": "shadow",
             "deep_link": "sutra://shadow/session/s-1"}), "s-1")


class TestMissionUpdateAndVerify(unittest.TestCase):
    def _run(self, code, flag=True):
        with tempfile.TemporaryDirectory() as tmp:
            settings = Path(tmp) / "settings.json"
            settings.write_text(json.dumps({"shadow.enabled": flag}))
            env = dict(os.environ, SUTRA_UI_SETTINGS=str(settings),
                       SUTRA_MCP_SHADOW="1", SUTRA_SHADOW_HOME=tmp)
            out = subprocess.run([sys.executable, "-c", code],
                                 capture_output=True, text=True,
                                 cwd=HERE, env=env)
            self.assertEqual(out.returncode, 0, out.stderr)
            return out.stdout.strip().splitlines()[-1]

    def test_05_mission_update_appends_and_validates(self):
        line = self._run("; ".join([
            "import json, sutra_mcp",
            "t = sutra_mcp.BY_NAME['shadow_mission_update']",
            "print(json.dumps(t['fn']({'mission_id': 'm-9', 'state': 'running'})))",
        ]))
        self.assertIn("m-9", line)
        line = self._run("; ".join([
            "import json, sutra_mcp",
            "t = sutra_mcp.BY_NAME['shadow_mission_update']",
            "print(json.dumps(t['fn']({'mission_id': 'm-9', 'state': 'flying'})))",
        ]))
        self.assertIn("refused", line)

    def test_06_verify_ledger_has(self):
        line = self._run("; ".join([
            "import json, sutra_mcp",
            "u = sutra_mcp.BY_NAME['shadow_mission_update']",
            "u['fn']({'mission_id': 'm-7', 'state': 'done'})",
            "v = sutra_mcp.BY_NAME['shadow_verify']",
            "print(json.dumps(v['fn']({'mode': 'ledger_has', 'kind': 'missions', 'needle': 'm-7'})))",
        ]))
        self.assertIn("true", line.lower())


if __name__ == "__main__":
    unittest.main()
