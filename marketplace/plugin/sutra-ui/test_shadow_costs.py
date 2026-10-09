"""What Shadow's work costs, and the monthly spending limit (founder,
2026-10-08, from Paperclip).

  DELTAS    total_cost_usd is cumulative per process (measured): a turn costs
            the new total minus the last; a new process counts from zero.
  RUNTIME   SessionRuntime.on_cost is called on every result, success or
            error, with the session id; a chat pane sets none and is untouched.
  WHO       a worker Shadow made counts on its task; the founder's own chat
            does not count at all; the Now chat counts toward the month only.
  LIMIT     none by default; set / clear / refuse junk; ok -> warn at 80% ->
            over at 100%; over blocks new starts with the reason and pauses
            a running task before its next step.
  ROUTES    GET/POST /api/shadow/budget; the missions list carries cost_usd.

Run: sutra/marketplace/plugin/sutra-ui/run-tests.sh test_shadow_costs.py
"""
import asyncio
import json
import os
import tempfile
import unittest

os.environ["SUTRA_SHADOW_HOME"] = tempfile.mkdtemp(prefix="shadow-costs-")

from fastapi.testclient import TestClient      # noqa: E402

import app as app_module                       # noqa: E402
import mission_engine                          # noqa: E402
import providers                               # noqa: E402
import session_runtime                         # noqa: E402
import shadow_costs as sc                      # noqa: E402

HDR = {"X-Sutra-Panel": app_module.PANEL_TOKEN,
       "Origin": "http://127.0.0.1:8330"}


class Base(unittest.TestCase):
    def setUp(self):
        for p in (sc._path(),):
            if os.path.exists(p):
                os.remove(p)
        sc._LAST.clear()
        sc._CACHE.update(path=None, size=-1, rows=[])
        sc.set_budget(None)
        self.store = mission_engine.MissionStore()

    def tearDown(self):
        sc.set_budget(None)
        for m in self.store.list():
            self.store.delete(m["id"])


class Deltas(Base):
    def test_01_cumulative_totals_become_per_turn_costs(self):
        self.assertAlmostEqual(sc.record("s1", "m1", 0.10, "worker", 1), 0.10)
        self.assertAlmostEqual(sc.record("s1", "m1", 0.25, "worker", 1), 0.15)
        self.assertAlmostEqual(sc.record("s1", "m1", 0.25, "worker", 1), 0.0,
                               msg="the same total twice is nothing new")
        self.assertAlmostEqual(sc.by_mission()["m1"], 0.25)

    def test_02_a_new_process_counts_from_zero(self):
        sc.record("s1", "m1", 0.40, "worker", 1)
        self.assertAlmostEqual(sc.record("s1", "m1", 0.05, "worker", 2), 0.05,
                               msg="a resume is a new process")
        self.assertAlmostEqual(sc.record("s1", "m1", 0.03, "worker", 2), 0.03,
                               msg="a lower total is a restart, counted whole")

    def test_03_junk_is_not_a_cost(self):
        for v in (None, "", "abc", 0, -1):
            self.assertEqual(sc.record("s1", "m1", v, "worker", 1), 0.0)
        self.assertEqual(sc.by_mission(), {})

    def test_04_the_month_adds_every_kind(self):
        sc.record("s1", "m1", 0.10, "worker", 1)
        sc.record("s2", "m1", 0.02, "shadow", 2)
        sc.record("s3", None, 0.01, "now", 3)
        self.assertAlmostEqual(sc.month_spent(), 0.13)
        self.assertAlmostEqual(sc.by_mission()["m1"], 0.12)
        self.assertEqual(sc.month_spent("1999-01"), 0)


class Limit(Base):
    def test_10_no_limit_by_default(self):
        self.assertIsNone(sc.budget())
        self.assertEqual(sc.status()["level"], "none")
        sc.record("s1", "m1", 999, "worker", 1)
        self.assertFalse(sc.spent_up(), "no limit never stops anything")

    def test_11_set_clear_and_refuse(self):
        self.assertEqual(sc.set_budget(10), 10.0)
        self.assertIsNone(sc.set_budget(0))
        self.assertIsNone(sc.set_budget(""))
        for bad in ("ten", -5, 10 ** 7):
            with self.assertRaises(ValueError):
                sc.set_budget(bad)

    def test_12_ok_warn_over(self):
        sc.set_budget(10)
        sc.record("s1", "m1", 7.9, "worker", 1)
        self.assertEqual(sc.status()["level"], "ok")
        sc.record("s1", "m1", 8.0, "worker", 1)
        self.assertEqual(sc.status()["level"], "warn")
        self.assertEqual(sc.status()["pct"], 80)
        sc.record("s1", "m1", 10.0, "worker", 1)
        self.assertEqual(sc.status()["level"], "over")
        self.assertTrue(sc.spent_up())
        self.assertIn("$10.00", sc.spent_up_reason())

    def test_13_the_limit_lives_beside_the_other_task_limits(self):
        mission_engine.set_max_running(4)
        sc.set_budget(25)
        limits = mission_engine._read_limits()
        self.assertEqual(limits["monthly_budget_usd"], 25)
        self.assertEqual(limits["running_at_once"], 4,
                         "setting the limit keeps the other task limits")

    def test_14_over_the_limit_a_task_does_not_start(self):
        sc.set_budget(1)
        sc.record("s1", None, 2, "now", 1)
        self.assertIn("spending limit", app_module._shadow_start_precheck({}))

    def test_15_the_engine_pauses_before_the_next_step(self):
        self.assertFalse(mission_engine._budget_spent_up())
        sc.set_budget(1)
        sc.record("s1", None, 2, "now", 1)
        self.assertTrue(mission_engine._budget_spent_up())
        src = open(mission_engine.__file__, encoding="utf-8").read()
        i = src.index("hold = None if approved else self._autonomy_hold")
        j = src.index('held["pause_reason"] = "budget_spent"')
        self.assertLess(i, j, "after the floor and autonomy holds")
        self.assertLess(j - i, 900, "and right after them, before the say")


class FakeStdout:
    def __init__(self, lines):
        self.lines = [json.dumps(x).encode() + b"\n" for x in lines]

    async def readline(self):
        return self.lines.pop(0) if self.lines else b""


class FakeProc:
    def __init__(self, lines):
        self.stdout = FakeStdout(lines)


class Runtime(Base):
    def turn(self, rt, result):
        rt.proc = FakeProc([{"type": "system", "session_id": "sess-1"}, result])

        async def emit(frame):
            return None
        return asyncio.run(rt.demux_turn(emit, None))

    def test_20_every_result_reports_its_total(self):
        rt = session_runtime.SessionRuntime()
        got = []
        rt.on_cost = lambda total, sid: got.append((total, sid))
        self.turn(rt, {"type": "result", "subtype": "success",
                       "total_cost_usd": 0.5, "session_id": "sess-1"})
        self.turn(rt, {"type": "result", "subtype": "error_during_execution",
                       "is_error": True, "total_cost_usd": 0.7,
                       "session_id": "sess-1"})
        self.assertEqual(got, [(0.5, "sess-1"), (0.7, "sess-1")],
                         "an errored turn still costs")

    def test_21_a_chat_pane_is_untouched(self):
        rt = session_runtime.SessionRuntime()
        self.assertIsNone(rt.on_cost)
        self.turn(rt, {"type": "result", "subtype": "success",
                       "total_cost_usd": 0.5, "session_id": "sess-1"})
        self.assertEqual(sc.month_spent(), 0)

    def test_22_a_broken_callback_never_breaks_a_turn(self):
        rt = session_runtime.SessionRuntime()

        def boom(*a):
            raise RuntimeError("no")
        rt.on_cost = boom
        out = self.turn(rt, {"type": "result", "subtype": "success",
                             "total_cost_usd": 0.5, "session_id": "sess-1"})
        self.assertTrue(out[2], "the turn still got its result")


class Who(Base):
    def mission(self, sid, mode):
        m = self.store.create("o", "feature", target_mode=mode, done_when=[])
        m["target_session"] = sid
        self.store.save(m)
        return m["id"]

    def test_30_a_worker_counts_on_its_task(self):
        mid = self.mission("w-1", "new")
        sc.hook(object(), "worker")(0.3, "w-1")
        self.assertAlmostEqual(sc.by_mission()[mid], 0.3)

    def test_31_the_founders_own_chat_is_not_counted(self):
        self.mission("f-1", "existing")
        sc.hook(object(), "worker")(0.3, "f-1")
        self.assertEqual(sc.month_spent(), 0)

    def test_32_an_unknown_worker_still_counts_toward_the_month(self):
        sc.hook(object(), "worker")(0.3, "nobody")
        self.assertAlmostEqual(sc.month_spent(), 0.3)
        self.assertEqual(sc.by_mission(), {})

    def test_33_shadows_own_chats_say_their_task(self):
        sc.hook(object(), "shadow", "m-x")(0.2, "sh-1")
        sc.hook(object(), "now")(0.1, "now-1")
        self.assertEqual(set(sc.by_mission()), {"m-x"})
        self.assertAlmostEqual(sc.month_spent(), 0.3)

    def test_34_every_shadow_runtime_is_hooked(self):
        import shadow_runner
        import shadow_session
        import shadow_task_chat
        self.assertEqual(open(shadow_runner.__file__, encoding="utf-8")
                         .read().count("shadow_costs.attach("), 4)
        self.assertIsNotNone(shadow_session.ShadowSession().rt.on_cost)
        chat = shadow_task_chat.TaskChat("m-hook")
        self.assertIsNotNone(chat._runtime().on_cost)


class Routes(Base):
    def setUp(self):
        super().setUp()
        self.client = TestClient(app_module.app, base_url="http://127.0.0.1")
        self.saved = providers.shadow_enabled
        providers.shadow_enabled = lambda: True

    def tearDown(self):
        providers.shadow_enabled = self.saved
        super().tearDown()

    def test_40_read_and_set(self):
        self.assertEqual(self.client.get("/api/shadow/budget").json()["level"],
                         "none")
        r = self.client.post("/api/shadow/budget", json={"monthly_usd": 20},
                             headers=HDR)
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.json()["budget_usd"], 20.0)
        r = self.client.post("/api/shadow/budget", json={"monthly_usd": "x"},
                             headers=HDR)
        self.assertEqual(r.status_code, 400)
        r = self.client.post("/api/shadow/budget", json={"monthly_usd": None},
                             headers=HDR)
        self.assertIsNone(r.json()["budget_usd"])

    def test_41_the_list_carries_each_tasks_cost(self):
        a = self.store.create("costly", "feature", target_mode="new",
                              done_when=[])
        b = self.store.create("free", "feature", target_mode="new",
                              done_when=[])
        sc.record("s1", a["id"], 0.42, "worker", 1)
        got = {m["id"]: m for m in
               self.client.get("/api/shadow/missions").json()["missions"]}
        self.assertEqual(got[a["id"]]["cost_usd"], 0.42)
        self.assertNotIn("cost_usd", got[b["id"]])
        self.assertNotIn("cost_usd", self.store.load(a["id"]),
                         "computed per read, never stored on the task")


if __name__ == "__main__":
    unittest.main()
