"""\"Running at once\" -- the founder-set concurrency cap, end to end.

The setting was a static number on the settings page: the UI printed
mission_engine.MAX_RUNNING and the stepper beside it was drawn dead. This
lane covers the feature that replaced it, at the three levels it has to be
true at or it is not a setting at all:

  STORE      mission_engine.max_running() prefers a persisted value over the
             default, clamps into [MIN_RUNNING, RUNNING_CEILING], survives a
             restart, and NEVER raises -- a corrupt file must cost the
             default, not an admission.
  ADMISSION  MissionScheduler reads the setting at decision time, so a cap
             changed between two starts is honoured by the second. The
             SCHEDULER is the seam: it is the only admitter, and every other
             cap check in the app defers to the same resolver.
  ROUTE      GET /api/shadow/settings reports the live cap; POST
             /api/shadow/settings/tasks writes it, refuses junk, drains the
             queue when the cap goes UP, and does not kill work when it goes
             DOWN.

Run: ./run-tests.sh test_shadow_run_limit.py
"""
import asyncio
import json
import os
import tempfile
import unittest
from pathlib import Path

os.environ["SUTRA_SHADOW_HOME"] = tempfile.mkdtemp(prefix="shadow-cap-test-")

from fastapi.testclient import TestClient      # noqa: E402

import app as app_module                       # noqa: E402
import mission_engine                          # noqa: E402
import providers                               # noqa: E402
import shadow_runner                           # noqa: E402
from mission_engine import MissionStore, MissionScheduler  # noqa: E402

HDR = {"X-Sutra-Panel": app_module.PANEL_TOKEN,
       "Origin": "http://127.0.0.1:8330"}
TASKS = "/api/shadow/settings/tasks"


class Base(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app_module.app, base_url="http://127.0.0.1")

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        os.environ["SUTRA_SHADOW_HOME"] = self.tmp.name
        self._orig = providers.SETTINGS_PATH
        p = Path(self.tmp.name) / "providers-settings.json"
        p.write_text(json.dumps({"shadow.enabled": True}))
        providers.SETTINGS_PATH = p
        self.store = MissionStore()

    def tearDown(self):
        providers.SETTINGS_PATH = self._orig
        self.tmp.cleanup()

    def mission(self, objective="fix the EMI rounding", template="fix"):
        m = self.store.create(objective, template, target_mode="new")
        self.store.transition(m["id"], "brief_confirm", "proposed")
        return self.store.load(m["id"])


# ------------------------------------------------------------------ STORE --
class TestTheStore(Base):

    def test_01_unset_is_the_default(self):
        """An install nobody has configured runs at MAX_RUNNING -- and the
        file is not created merely by asking."""
        self.assertEqual(mission_engine.max_running(),
                         mission_engine.MAX_RUNNING)
        self.assertFalse(os.path.exists(mission_engine.limits_path()),
                         "a READ must not create the store")

    def test_02_set_then_read_across_a_fresh_resolver(self):
        """Persistence, not memory: the value is read back off disk, which is
        what makes it survive an app restart."""
        self.assertEqual(mission_engine.set_max_running(3), 3)
        self.assertEqual(mission_engine.max_running(), 3)
        on_disk = json.loads(Path(mission_engine.limits_path()).read_text())
        self.assertEqual(on_disk["running_at_once"], 3)

    def test_03_out_of_band_numbers_clamp(self):
        """A stepper held past an end stops at the end. 0 is NOT a pause
        switch -- Shadow has stop/pause for that."""
        self.assertEqual(mission_engine.set_max_running(0),
                         mission_engine.MIN_RUNNING)
        self.assertEqual(mission_engine.max_running(),
                         mission_engine.MIN_RUNNING)
        self.assertEqual(mission_engine.set_max_running(9999),
                         mission_engine.RUNNING_CEILING)
        self.assertEqual(mission_engine.set_max_running(-4),
                         mission_engine.MIN_RUNNING)

    def test_04_junk_is_refused_not_guessed(self):
        """A write that cannot be understood says so. Storing a plausible
        number for an unparseable one is the failure this prevents."""
        for junk in ("five", None, {}, [], "3.5.1"):
            with self.assertRaises(ValueError, msg=repr(junk)):
                mission_engine.set_max_running(junk)
        self.assertFalse(os.path.exists(mission_engine.limits_path()),
                         "a refused write must leave no file behind")

    def test_05_a_corrupt_store_costs_the_default_not_an_exception(self):
        """max_running() is on every admission path. It degrades."""
        Path(mission_engine.limits_path()).write_text("{not json")
        self.assertEqual(mission_engine.max_running(),
                         mission_engine.MAX_RUNNING)
        Path(mission_engine.limits_path()).write_text(
            json.dumps({"running_at_once": "banana"}))
        self.assertEqual(mission_engine.max_running(),
                         mission_engine.MAX_RUNNING)

    def test_06_other_keys_in_the_store_survive_a_write(self):
        """Read-modify-write, so a future limit sharing this file is not
        erased by a cap change."""
        import json_store
        json_store.write_json(mission_engine.limits_path(),
                              {"something_else": 7})
        mission_engine.set_max_running(2)
        on_disk = json.loads(Path(mission_engine.limits_path()).read_text())
        self.assertEqual(on_disk["something_else"], 7)
        self.assertEqual(on_disk["running_at_once"], 2)

    def test_07_the_store_lives_under_the_shadow_home(self):
        """Redirecting the home redirects the limits -- the property that
        keeps a test from writing a cap into the operator's install."""
        self.assertTrue(
            os.path.realpath(mission_engine.limits_path()).startswith(
                os.path.realpath(self.tmp.name) + os.sep))


# -------------------------------------------------------------- ADMISSION --
class TestAdmission(Base):

    def test_10_the_cap_is_what_queues(self):
        """The whole feature, at the only admitter: with the cap at 2 the
        third task WAITS rather than running."""
        mission_engine.set_max_running(2)
        sched = MissionScheduler(self.store)
        states = [sched.start(self.mission("task %d" % i)["id"])["state"]
                  for i in range(3)]
        self.assertEqual(states, ["running", "running", "queued"])

    def test_11_the_cap_is_read_at_decision_time(self):
        """A scheduler built before the change still honours it. This is the
        regression the property on MissionScheduler exists for: the old
        `max_running=MAX_RUNNING` default bound the cap at construction."""
        mission_engine.set_max_running(1)
        sched = MissionScheduler(self.store)
        self.assertEqual(sched.start(self.mission("a")["id"])["state"],
                         "running")
        self.assertEqual(sched.start(self.mission("b")["id"])["state"],
                         "queued")
        mission_engine.set_max_running(3)
        self.assertEqual(sched.max_running, 3, "the SAME scheduler re-reads")
        self.assertEqual(sched.start(self.mission("c")["id"])["state"],
                         "running")

    def test_12_an_explicit_cap_still_pins(self):
        """Tests build two-slot worlds by passing max_running=. That must
        keep overriding the setting, or every such fixture becomes a lie."""
        mission_engine.set_max_running(5)
        sched = MissionScheduler(self.store, max_running=1)
        self.assertEqual(sched.max_running, 1)
        self.assertEqual(sched.start(self.mission("a")["id"])["state"],
                         "running")
        self.assertEqual(sched.start(self.mission("b")["id"])["state"],
                         "queued")

    def test_13_raising_the_cap_promotes_the_oldest_first(self):
        """FIFO is not disturbed by where the free slot came from."""
        mission_engine.set_max_running(1)
        sched = MissionScheduler(self.store)
        sched.start(self.mission("running one")["id"])
        first = self.mission("waited longest")
        second = self.mission("waited less")
        sched.start(first["id"])
        sched.start(second["id"])
        mission_engine.set_max_running(2)
        promoted = sched.on_terminal(None)
        self.assertEqual(promoted["id"], first["id"])
        self.assertEqual(self.store.load(second["id"])["state"], "queued")

    def test_14_lowering_the_cap_does_not_stop_running_work(self):
        """The founder asked for a queueing rule, not a kill switch. The
        overflow drains as work ends; nothing is transitioned here."""
        mission_engine.set_max_running(3)
        sched = MissionScheduler(self.store)
        ids = [self.mission("task %d" % i)["id"] for i in range(3)]
        for mid in ids:
            sched.start(mid)
        mission_engine.set_max_running(1)
        self.assertEqual(
            [self.store.load(i)["state"] for i in ids],
            ["running", "running", "running"])
        # and the NEXT one waits, which is the half that must change
        self.assertEqual(sched.start(self.mission("next")["id"])["state"],
                         "queued")

    def test_15_over_cap_promotes_nothing(self):
        """on_terminal must not admit a fourth while three run under a cap
        of 1 -- `<` not `<=`, checked because lowering makes it reachable."""
        mission_engine.set_max_running(3)
        sched = MissionScheduler(self.store)
        for i in range(3):
            sched.start(self.mission("task %d" % i)["id"])
        sched.start(self.mission("queued one")["id"])
        mission_engine.set_max_running(1)
        self.assertIsNone(sched.on_terminal(None))


# ----------------------------------------------------------------- DRAIN ---
class TestDrainQueue(Base):
    """Raising the cap frees SEVERAL slots at once; one promotion would leave
    tasks queued behind a limit that no longer exists."""

    def setUp(self):
        super().setUp()
        self.launched = []
        self._real_launch = shadow_runner._launch
        shadow_runner._launch = lambda mid, *a, **k: self.launched.append(mid)

    def tearDown(self):
        shadow_runner._launch = self._real_launch
        super().tearDown()

    def test_20_every_freed_slot_is_filled(self):
        mission_engine.set_max_running(1)
        sched = MissionScheduler(self.store)
        sched.start(self.mission("the one running")["id"])
        waiting = [self.mission("waiting %d" % i)["id"] for i in range(4)]
        for mid in waiting:
            sched.start(mid)
        mission_engine.set_max_running(4)
        promoted = asyncio.new_event_loop().run_until_complete(
            shadow_runner.drain_queue(lambda *a, **k: None,
                                      store=self.store))
        self.assertEqual(promoted, waiting[:3], "oldest three, in order")
        self.assertEqual(self.store.load(waiting[3])["state"], "queued",
                         "the fourth is still over the new cap")
        self.assertEqual(self.launched, waiting[:3],
                         "a promoted mission is LAUNCHED, not just relabelled")

    def test_21_an_empty_queue_drains_to_nothing(self):
        mission_engine.set_max_running(5)
        promoted = asyncio.new_event_loop().run_until_complete(
            shadow_runner.drain_queue(lambda *a, **k: None,
                                      store=self.store))
        self.assertEqual(promoted, [])
        self.assertEqual(self.launched, [])

    def test_22_a_full_cap_drains_to_nothing(self):
        mission_engine.set_max_running(1)
        sched = MissionScheduler(self.store)
        sched.start(self.mission("running")["id"])
        queued = self.mission("waiting")
        sched.start(queued["id"])
        promoted = asyncio.new_event_loop().run_until_complete(
            shadow_runner.drain_queue(lambda *a, **k: None,
                                      store=self.store))
        self.assertEqual(promoted, [])
        self.assertEqual(self.store.load(queued["id"])["state"], "queued")


# ----------------------------------------------------------------- ROUTE ---
class TestTheRoute(Base):

    def setUp(self):
        super().setUp()
        self._real_launch = shadow_runner._launch
        shadow_runner._launch = lambda mid, *a, **k: None
        # The SCHEDULING hook is stubbed, not the drain itself. Stubbing the
        # coroutine would make the assertion depend on whether the background
        # task happened to have run by the time TestClient returned -- a
        # timing race in a test suite. The hook is called synchronously by
        # the route, so "was the drain scheduled" is a deterministic fact.
        # TestDrainQueue covers what the drain then does.
        self.drained = []
        self._real_drain = app_module._drain_queue_in_background
        app_module._drain_queue_in_background = self.drained.append

    def tearDown(self):
        app_module._drain_queue_in_background = self._real_drain
        shadow_runner._launch = self._real_launch
        super().tearDown()

    def get_tasks(self):
        r = self.client.get("/api/shadow/settings", headers=HDR)
        self.assertEqual(r.status_code, 200, r.text)
        return r.json()["tasks"]

    def test_30_get_reports_the_live_cap_and_its_band(self):
        mission_engine.set_max_running(4)
        t = self.get_tasks()
        self.assertEqual(t["running_at_once"], 4)
        self.assertEqual(t["running_at_once_min"], mission_engine.MIN_RUNNING)
        self.assertEqual(t["running_at_once_max"],
                         mission_engine.RUNNING_CEILING)

    def test_31_get_reports_the_counts_the_cap_is_read_against(self):
        """The number alone cannot explain a lower cap beside live work."""
        mission_engine.set_max_running(1)
        sched = MissionScheduler(self.store)
        sched.start(self.mission("running")["id"])
        sched.start(self.mission("waiting")["id"])
        t = self.get_tasks()
        self.assertEqual(t["running_now"], 1)
        self.assertEqual(t["queued_now"], 1)

    def test_32_post_writes_what_the_engine_then_enforces(self):
        r = self.client.post(TASKS, json={"running_at_once": 2}, headers=HDR)
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.json()["running_at_once"], 2)
        self.assertEqual(mission_engine.max_running(), 2,
                         "the route and the admitter must read one store")
        self.assertEqual(self.get_tasks()["running_at_once"], 2)

    def test_33_post_clamps_and_says_what_it_stored(self):
        for sent, kept in ((0, mission_engine.MIN_RUNNING),
                           (999, mission_engine.RUNNING_CEILING)):
            r = self.client.post(TASKS, json={"running_at_once": sent},
                                 headers=HDR)
            self.assertEqual(r.status_code, 200, r.text)
            self.assertEqual(r.json()["running_at_once"], kept)

    def test_34_post_refuses_junk_and_a_missing_field(self):
        for body in ({"running_at_once": "five"}, {"running_at_once": None},
                     {}, {"turn_budget": {"fix": 99}}):
            r = self.client.post(TASKS, json=body, headers=HDR)
            self.assertEqual(r.status_code, 400, "%r -> %s" % (body, r.text))
        self.assertEqual(mission_engine.max_running(),
                         mission_engine.MAX_RUNNING, "nothing was stored")

    def test_35_the_turn_budget_is_not_settable_through_this_route(self):
        """It is chosen by the KIND of work. A route that silently ignored a
        sent budget would read as accepting one."""
        before = self.get_tasks()["turn_budget"]
        r = self.client.post(TASKS, json={"running_at_once": 3,
                                          "turn_budget": {"fix": 999}},
                             headers=HDR)
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(self.get_tasks()["turn_budget"], before)

    def test_36_raising_the_cap_schedules_the_drain(self):
        """The queue must not sit behind a limit that no longer exists. What
        is asserted is the SCHEDULE, not the promotion: a promoted mission
        can still have to spawn, which takes minutes, so the route cannot
        await it (the second-flight lesson). TestDrainQueue above covers what
        the drain then does."""
        mission_engine.set_max_running(1)
        sched = MissionScheduler(self.store)
        sched.start(self.mission("running")["id"])
        for i in range(2):
            sched.start(self.mission("waiting %d" % i)["id"])
        r = self.client.post(TASKS, json={"running_at_once": 3}, headers=HDR)
        self.assertEqual(r.status_code, 200, r.text)
        body = r.json()
        self.assertEqual(body["starting"], 2, "both free slots are claimed")
        self.assertEqual(body["over_cap"], 0)
        self.assertEqual(self.drained, [3],
                         "the drain is scheduled once, for the new cap")

    def test_36b_starting_is_bounded_by_the_queue_and_by_free_slots(self):
        """`starting` is a count the route can stand behind: never more than
        are waiting, never more than there is room for, never negative."""
        sched = MissionScheduler(self.store, max_running=99)
        for i in range(2):
            sched.start(self.mission("running %d" % i)["id"])
        mission_engine.set_max_running(1)
        for i in range(4):
            sched2 = MissionScheduler(self.store)
            sched2.start(self.mission("waiting %d" % i)["id"])
        # 2 running, 4 queued. Cap 3 -> ONE free slot, not four.
        b = self.client.post(TASKS, json={"running_at_once": 3},
                             headers=HDR).json()
        self.assertEqual(b["starting"], 1)
        # cap 10 -> four free slots but only four waiting
        b = self.client.post(TASKS, json={"running_at_once": 10},
                             headers=HDR).json()
        self.assertEqual(b["starting"], 4)
        # cap 1 with 2 running -> nothing starts, and no drain is scheduled
        self.drained = []
        b = self.client.post(TASKS, json={"running_at_once": 1},
                             headers=HDR).json()
        self.assertEqual(b["starting"], 0)
        self.assertEqual(self.drained, [], "a full cap schedules no drain")

    def test_37_lowering_the_cap_reports_the_overflow_instead_of_killing_it(self):
        mission_engine.set_max_running(3)
        sched = MissionScheduler(self.store)
        ids = [self.mission("task %d" % i)["id"] for i in range(3)]
        for mid in ids:
            sched.start(mid)
        r = self.client.post(TASKS, json={"running_at_once": 1}, headers=HDR)
        self.assertEqual(r.status_code, 200, r.text)
        body = r.json()
        self.assertEqual(body["running_at_once"], 1)
        self.assertEqual(body["over_cap"], 2, "the founder is told, not lied to")
        self.assertEqual(body["starting"], 0)
        self.assertEqual([self.store.load(i)["state"] for i in ids],
                         ["running"] * 3, "nothing in flight was stopped")

    def test_38_the_write_is_ledgered(self):
        """Every Shadow write leaves an audit row; a limit change is one."""
        import shadow_ledger
        self.client.post(TASKS, json={"running_at_once": 2}, headers=HDR)
        rows = shadow_ledger.read("actions", 50)
        self.assertTrue(
            any("running_at_once set to 2" in (r.get("summary") or "")
                for r in rows), rows)

    def test_39_the_route_is_flag_gated_like_every_other_shadow_write(self):
        providers.SETTINGS_PATH.write_text(json.dumps({"shadow.enabled":
                                                       False}))
        r = self.client.post(TASKS, json={"running_at_once": 2}, headers=HDR)
        self.assertEqual(r.status_code, 403, r.text)

    def test_40_a_cross_origin_write_is_refused_without_the_panel_token(self):
        r = self.client.post(TASKS, json={"running_at_once": 2},
                             headers={"Origin": "http://127.0.0.1:8330"})
        self.assertEqual(r.status_code, 403, r.text)


# ------------------------------------------------- THE SLOT A STOP FREES --
class TestStopFreesTheSlot(Base):
    """Stopping a running task must actually START a queued one.

    WHY THIS IS NOT TestDrainQueue AGAIN. Those tests call the promotion
    helper directly, which assumes the thing in question: that something
    calls it. This lane asserts the REAL runner loop, ended by a REAL
    founder_stop, reaches the promotion by itself. After the stop the test
    does nothing but let the event loop turn -- no second task is submitted,
    no sweep is poked, no helper is called by hand. If a queued task only
    moves because an unrelated tick happened to nudge the funnel, this fails.

    THE LOOP IS REAL. `make_bindings` is replaced so no session, delegate or
    model call is needed, but `_launch` itself, `run_mission` itself and the
    `run()` wrapper that owns the promotion are all the shipped code.
    """

    def setUp(self):
        super().setUp()
        self._real_bindings = shadow_runner.make_bindings
        self._real_decider = shadow_runner.DEFAULT_DECIDER["fn"]
        # no decider: the historical template path, so the loop needs no model
        shadow_runner.DEFAULT_DECIDER["fn"] = None

    def tearDown(self):
        shadow_runner.make_bindings = self._real_bindings
        shadow_runner.DEFAULT_DECIDER["fn"] = self._real_decider
        for t in list(shadow_runner.RUNNING.values()):
            t.cancel()
        shadow_runner.RUNNING.clear()
        super().tearDown()

    def _bind(self, on_wait):
        async def sayer(mission, text):
            return True

        async def waiter(mission):
            on_wait(mission)
            return True

        def reader(mission):
            return ""
        shadow_runner.make_bindings = lambda vs: (sayer, waiter, reader)

    def _launch_only(self, mid):
        """Run the REAL loop for `mid`, and record-without-running every
        other launch. Returns the list the spy appends to.

        WHY THE PROMOTED MISSION'S LOOP IS NOT RUN. It is not what is under
        test, and letting it run hides the result: with a stub sayer its
        template says are identical, so it trips the ping-pong guard and
        lands in `stopped` within microseconds. The first draft of this test
        asserted the promoted mission's state AFTER that had happened, read
        'stopped' != 'running', and looked exactly like a product bug. The
        launch under test -- the one that has to reach the promotion by
        itself -- is still entirely real.
        """
        launched = []
        real = shadow_runner._launch

        def spy(m, say, ver):
            launched.append(m)
            if m == mid:
                return real(m, say, ver)
        shadow_runner._launch = spy
        self.addCleanup(setattr, shadow_runner, "_launch", real)
        return launched

    def _stop(self, mid):
        """The act route's own call, not a bare transition -- `ended_by` is
        what makes it a founder decision rather than machine trouble."""
        return mission_engine.MissionEngine(
            self.store, None, None, None).founder_stop(mid,
                                                       "founder stop (home)")

    def test_50_stopping_a_running_task_starts_the_queued_one(self):
        """N+1 tasks at limit N: stop the running one, the waiting one runs."""
        mission_engine.set_max_running(1)
        sched = MissionScheduler(self.store)
        m1, m2 = self.mission("the one that runs"), self.mission("the waiter")
        self.assertEqual(sched.start(m1["id"])["state"], "running")
        self.assertEqual(sched.start(m2["id"])["state"], "queued")

        stopped = []

        def on_wait(mission):
            # the founder clicks Stop while the delegate is mid-turn
            if mission["id"] == m1["id"] and not stopped:
                stopped.append(self._stop(m1["id"])["id"])
        self._bind(on_wait)
        launched = self._launch_only(m1["id"])

        async def go():
            shadow_runner._launch(m1["id"], object(), None)
            # the task is popped from RUNNING before the promotion runs, so
            # the handle is taken now; awaiting it awaits the whole wrapper
            await shadow_runner.RUNNING[m1["id"]]
        asyncio.run(go())

        self.assertEqual(stopped, [m1["id"]], "the stop under test happened")
        self.assertEqual(self.store.load(m1["id"])["state"], "stopped")
        self.assertEqual(self.store.load(m1["id"]).get("ended_by"), "founder")
        self.assertEqual(
            self.store.load(m2["id"])["state"], "running",
            "the slot the stop freed must start the queued task, with no "
            "further action of any kind")
        self.assertEqual(launched, [m1["id"], m2["id"]],
                         "promotion launches the task it promoted")

    def test_51_a_stop_with_nothing_queued_promotes_nothing(self):
        """The mirror: promotion is not a reflex, it is a free slot meeting a
        queue. Nothing waiting must mean nothing started."""
        mission_engine.set_max_running(1)
        sched = MissionScheduler(self.store)
        m1 = self.mission("alone")
        self.assertEqual(sched.start(m1["id"])["state"], "running")
        self._bind(lambda mission: self._stop(mission["id"]))

        async def go():
            shadow_runner._launch(m1["id"], object(), None)
            await shadow_runner.RUNNING[m1["id"]]
        asyncio.run(go())
        self.assertEqual(self.store.load(m1["id"])["state"], "stopped")
        self.assertEqual(self.store.list(states=("running",)), [])

    def test_52_the_finish_path_frees_the_slot_the_same_way(self):
        """The founder asked whether the finish path shares the dependency.
        It does -- one wrapper owns both exits -- so it is pinned here beside
        the stop rather than left to be assumed."""
        mission_engine.set_max_running(1)
        sched = MissionScheduler(self.store)
        m1, m2 = self.mission("finishes"), self.mission("waits")
        self.assertEqual(sched.start(m1["id"])["state"], "running")
        self.assertEqual(sched.start(m2["id"])["state"], "queued")

        def on_wait(mission):
            if mission["id"] == m1["id"]:
                # the worker's turn lands and the mission completes on its
                # own -- no founder anywhere in this one
                self.store.transition(m1["id"], "done", "objective met")
        self._bind(on_wait)
        self._launch_only(m1["id"])

        async def go():
            shadow_runner._launch(m1["id"], object(), None)
            await shadow_runner.RUNNING[m1["id"]]
        asyncio.run(go())

        self.assertEqual(self.store.load(m1["id"])["state"], "done")
        self.assertEqual(self.store.load(m2["id"])["state"], "running",
                         "a finish frees the slot exactly as a stop does")


if __name__ == "__main__":
    unittest.main()
