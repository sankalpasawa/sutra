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

    def test_08_a_separate_process_reads_back_what_the_route_wrote(self):
        """THE RELOAD-AND-RESTART CLAIM, ASSERTED RATHER THAN CLICKED.

        test_02 proves the value survives a fresh RESOLVER; this proves it
        survives a fresh INTERPRETER, which is what "restart the app" means.
        The distinction is not pedantic: every in-process test would still
        pass if the cap were cached in a module global that happened to be
        warm, and that cache is exactly the bug a founder would meet as
        "I set it to 2 and after a restart it was 5 again".

        So the write goes through the ROUTE (the stepper's own endpoint) and
        the read happens in a subprocess that shares nothing with this one
        but the directory on disk.
        """
        r = self.client.post(TASKS, json={"running_at_once": 3}, headers=HDR)
        self.assertEqual(r.status_code, 200, r.text)

        import subprocess
        import sys
        env = dict(os.environ)
        env["SUTRA_SHADOW_HOME"] = self.tmp.name
        env["PYTHONPATH"] = os.path.dirname(os.path.abspath(__file__))
        out = subprocess.run(
            [sys.executable, "-c",
             "import mission_engine; print(mission_engine.max_running())"],
            capture_output=True, text=True, env=env,
            cwd=os.path.dirname(os.path.abspath(__file__)), timeout=60)
        self.assertEqual(out.returncode, 0,
                         "the fresh process could not even read the cap: %s"
                         % out.stderr[-400:])
        self.assertEqual(out.stdout.strip(), "3",
                         "a new process must read the founder's cap off disk, "
                         "not fall back to the default (stderr: %s)"
                         % out.stderr[-200:])

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

    def test_16_exactly_n_run_and_the_rest_queue_at_every_cap(self):
        """N RUNNING, k QUEUED -- read back off disk, at more than one N.

        test_10 states the rule at a cap of 2 from the values `start`
        RETURNED. This asserts the same rule from the STORE, which is what
        every other reader (the API, the settings counts, admission itself)
        actually consults -- a start that returned "running" and saved
        something else would pass there and fail here.

        Two caps, because a cap of 1 is the degenerate case where "the cap"
        and "one" cannot be told apart: an admitter that accidentally
        hard-coded a single slot would satisfy N=1 and fail N=2.
        """
        for cap, extra in ((1, 2), (2, 3)):
            with self.subTest(cap=cap):
                tmp = tempfile.TemporaryDirectory()
                self.addCleanup(tmp.cleanup)
                os.environ["SUTRA_SHADOW_HOME"] = tmp.name
                store = MissionStore()
                mission_engine.set_max_running(cap)
                sched = MissionScheduler(store)
                made = []
                for i in range(cap + extra):
                    m = store.create("task %d" % i, "fix", target_mode="new")
                    store.transition(m["id"], "brief_confirm", "proposed")
                    sched.start(m["id"])
                    made.append(m["id"])

                fresh = MissionStore()          # re-read, not the same objects
                running = fresh.list(states=("running",))
                queued = fresh.list(states=("queued",))
                self.assertEqual(len(running), cap,
                                 "cap %d must run exactly %d" % (cap, cap))
                self.assertEqual(len(queued), extra,
                                 "the other %d must wait" % extra)
                self.assertEqual(
                    sorted(m["id"] for m in running + queued), sorted(made),
                    "every task is accounted for in exactly one of the two")
                # ...and the queue is the ONES THAT CAME LATER, in order
                self.assertEqual([m["id"] for m in
                                  sorted(queued, key=lambda x: x["created_ns"])],
                                 made[cap:], "FIFO: the overflow, in order")

    def test_17_the_missions_api_serves_the_queued_state_the_ui_reads(self):
        """THE FIELD THE 'Waiting for a free slot' COPY IS DERIVED FROM.

        The renderer keys that line on `m.state === "queued"` and nothing
        else (static/js/16-shadow-home.js; asserted on the JS side by
        test_shadow_home.js blocks 4, 35 and 36). This is the other half of
        that contract: the payload the page actually receives carries
        `queued` for a task held back by the cap. If admission stopped
        queueing, or the list stopped exposing `state`, the copy would
        silently stop appearing and both JS tests would still pass.
        """
        mission_engine.set_max_running(1)
        sched = MissionScheduler(self.store)
        first = self.mission("runs")
        waiting = self.mission("waits for a slot")
        sched.start(first["id"])
        sched.start(waiting["id"])

        r = self.client.get("/api/shadow/missions", headers=HDR)
        self.assertEqual(r.status_code, 200, r.text)
        by_id = {m["id"]: m for m in r.json()["missions"]}
        self.assertEqual(by_id[first["id"]]["state"], "running")
        self.assertEqual(by_id[waiting["id"]]["state"], "queued",
                         "the over-cap task must reach the page AS queued -- "
                         "that string is what the waiting copy is drawn from")
        # and the settings counts the same page reads agree with it
        t = self.client.get("/api/shadow/settings", headers=HDR).json()["tasks"]
        self.assertEqual((t["running_now"], t["queued_now"]), (1, 1))

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
        self.assertEqual(self.drained, ["cap raised to 3"],
                         "the drain is scheduled once, and names its cause")

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


# ---------------------------------------------- EVERY OTHER FREED SLOT --
class TestEveryWayASlotFrees(Base):
    """The queue must advance on EVERY way a slot can free, not just the two
    the runner's own wrapper happens to see.

    TestStopFreesTheSlot above covers the mission that ENDS ITSELF: the loop
    is alive, run_mission returns, and the wrapper promotes. That is one
    shape, and it was the only one wired. Each test here is a way a slot
    frees that the wrapper cannot see or does not reach:

      stop        the act route ends it; the loop may be between turns, or
                  there may be no loop at all (restart adoption, a dead loop)
      take over   running -> paused; the wrapper's paused branch promotes
                  nothing
      delete      the record is gone, so there is nothing left to reload
      abandon     the goal route stops the live attempt one layer up

    WHAT IS ASSERTED IS THE SCHEDULE, for the reason TestTheRoute states: the
    drain is a background task and "has it run yet" is a race, while "was it
    scheduled" is a synchronous fact. test_69 then composes the two halves --
    a real route call followed by the real drain -- so the end-to-end claim
    is not left to inference.
    """

    def setUp(self):
        super().setUp()
        self._real_launch = shadow_runner._launch
        shadow_runner._launch = lambda mid, *a, **k: None
        self.drained = []
        self._real_drain = app_module._drain_queue_in_background
        app_module._drain_queue_in_background = self.drained.append

    def tearDown(self):
        app_module._drain_queue_in_background = self._real_drain
        shadow_runner._launch = self._real_launch
        super().tearDown()

    def act(self, mid, action, **body):
        return self.client.post("/api/shadow/missions/%s/act" % mid,
                                json=dict(action=action, **body), headers=HDR)

    def one_running_one_queued(self):
        """The smallest world where a freed slot has somewhere to go."""
        mission_engine.set_max_running(1)
        sched = MissionScheduler(self.store)
        a, b = self.mission("the one that holds the slot"), self.mission("waits")
        self.assertEqual(sched.start(a["id"])["state"], "running")
        self.assertEqual(sched.start(b["id"])["state"], "queued")
        return a, b

    def test_60_stop_through_the_route_advances_the_queue(self):
        a, b = self.one_running_one_queued()
        r = self.act(a["id"], "stop")
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(self.store.load(a["id"])["state"], "stopped")
        self.assertEqual(self.drained, ["task %s stopped" % a["id"]],
                         "a stop must not wait for a loop to notice")

    def test_61_take_over_advances_the_queue(self):
        """Shadow stepped back from the chat, so it is not running that task
        any more -- whatever the pill says, the SLOT is free."""
        a, b = self.one_running_one_queued()
        r = self.act(a["id"], "take_over")
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(self.store.load(a["id"])["state"], "paused")
        self.assertEqual(self.drained, ["task %s taken over" % a["id"]])

    def test_62_delete_advances_the_queue(self):
        a, b = self.one_running_one_queued()
        r = self.act(a["id"], "delete")
        self.assertEqual(r.status_code, 200, r.text)
        self.assertIsNone(self.store.load(a["id"]), "the record is gone")
        self.assertEqual(self.drained, ["task %s deleted" % a["id"]])

    def test_63_a_freed_slot_with_nothing_waiting_schedules_nothing(self):
        """Promotion is a free slot MEETING a queue. An empty queue must not
        cost a background task on every stop the founder makes."""
        mission_engine.set_max_running(1)
        sched = MissionScheduler(self.store)
        a = self.mission("alone")
        sched.start(a["id"])
        self.assertEqual(self.act(a["id"], "stop").status_code, 200)
        self.assertEqual(self.drained, [])

    def test_64_a_stop_that_frees_no_slot_schedules_nothing(self):
        """THE VERB IS NOT WHAT DECIDES IT -- the free slot is.

        A PAUSED task holds no slot, so stopping one releases nothing: the
        cap is still full of the task that really is running, and a queued
        row still cannot start. The drain is keyed on _free_slots, not on
        "a stop happened", and this is the case that tells the two apart.
        """
        mission_engine.set_max_running(1)
        sched = MissionScheduler(self.store)
        a, b = self.one_running_one_queued()
        paused = self.mission("was never running")
        # paused holds no slot: brief_confirm -> running -> paused
        MissionScheduler(self.store, max_running=99).start(paused["id"])
        mission_engine.MissionEngine(
            self.store, None, None, None).founder_intervened(paused["id"])
        self.drained = []
        # the cap is 1 and `a` still runs, so stopping the paused one frees
        # nothing
        self.assertEqual(self.act(paused["id"], "stop").status_code, 200)
        self.assertEqual(self.drained, [],
                         "no slot freed, so no sweep is scheduled")

    def test_65_abandoning_a_goal_advances_the_queue(self):
        """The goal route stops the live attempt through the same
        founder_stop, so it frees a slot for the same reason."""
        import goal_store
        mission_engine.set_max_running(1)
        gs = goal_store.GoalStore()
        g = gs.create("ship the rounding fix", "sess-goal")
        a, b = self.one_running_one_queued()
        # bind the running mission to the goal the way the lifecycle does
        m = self.store.load(a["id"])
        m["goal_id"] = g["id"]
        self.store.save(m)
        gs.bind_mission(g["id"], a["id"], "the live attempt")
        r = self.client.post("/api/shadow/goals/%s/act" % g["id"],
                             json={"action": "stop"}, headers=HDR)
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(self.store.load(a["id"])["state"], "stopped")
        self.assertEqual(self.drained, ["goal %s abandoned" % g["id"]])

    def test_68_a_pause_frees_the_slot_and_the_loop_says_so(self):
        """THE SHIPPED COMPLETION PATH, and the last exit that was silent.

        The New Task form writes founder_confirm checks; a mission whose
        checks are all founder_confirm pauses for sign-off; and a paused
        mission is not counted in `running`. So the cap has room the moment
        the loop pauses -- and until this was wired, a queued task could
        wait behind a task that had stopped working and was waiting on a
        human.

        Asserted through the REAL loop, like TestStopFreesTheSlot: the pause
        is decided inside run_mission (the founder types in the target chat
        mid-turn, which is the pause this branch was written for), and
        nothing is poked afterwards.
        """
        mission_engine.set_max_running(1)
        sched = MissionScheduler(self.store)
        a, b = self.mission("pauses"), self.mission("waits")
        self.assertEqual(sched.start(a["id"])["state"], "running")
        self.assertEqual(sched.start(b["id"])["state"], "queued")

        real_launch = self._real_launch
        launched = []

        def spy(mid, say, ver):
            launched.append(mid)
            if mid == a["id"]:
                return real_launch(mid, say, ver)
        shadow_runner._launch = spy

        async def sayer(mission, text):
            return True

        async def waiter(mission):
            if mission["id"] == a["id"]:
                mission_engine.MissionEngine(
                    self.store, None, None, None).founder_intervened(a["id"])
            return True

        real_bindings = shadow_runner.make_bindings
        shadow_runner.make_bindings = lambda vs: (sayer, waiter,
                                                  lambda m: "")
        self.addCleanup(setattr, shadow_runner, "make_bindings", real_bindings)
        self.addCleanup(shadow_runner.RUNNING.clear)
        real_decider = shadow_runner.DEFAULT_DECIDER["fn"]
        shadow_runner.DEFAULT_DECIDER["fn"] = None
        self.addCleanup(lambda: shadow_runner.DEFAULT_DECIDER
                        .__setitem__("fn", real_decider))

        async def go():
            shadow_runner._launch(a["id"], object(), None)
            await shadow_runner.RUNNING[a["id"]]
        asyncio.run(go())

        self.assertEqual(self.store.load(a["id"])["state"], "paused")
        self.assertEqual(
            self.store.load(b["id"])["state"], "running",
            "the slot a PAUSE freed must start the waiting task")
        self.assertEqual(launched, [a["id"], b["id"]])

    def test_69_route_then_drain_actually_starts_the_waiting_task(self):
        """END TO END, with the race left out rather than waited on.

        Nothing is stubbed here but the launch: the route is real and the
        drain is real. The ONE thing a test cannot pin is WHEN the background
        task the route scheduled gets its turn on the app's loop -- so this
        asserts the END STATE, and runs the drain by hand only if the
        scheduled one has not landed yet. Either way the claim is the same
        and the assertion is the same: after a stop, with no further founder
        action of any kind, the waiting task is RUNNING and was LAUNCHED.
        """
        app_module._drain_queue_in_background = self._real_drain   # unstub
        launched = []
        shadow_runner._launch = lambda mid, *a, **k: launched.append(mid)
        a, b = self.one_running_one_queued()
        self.assertEqual(self.act(a["id"], "stop").status_code, 200)
        if self.store.load(b["id"])["state"] == "queued":
            asyncio.new_event_loop().run_until_complete(
                shadow_runner.drain_queue(lambda *x, **k: None,
                                          store=self.store))
        self.assertEqual(self.store.load(b["id"])["state"], "running",
                         "the slot the stop freed must start the waiting task")
        self.assertEqual(launched, [b["id"]],
                         "the promoted task is LAUNCHED, not just relabelled")


    def test_66_boot_drains_the_queue(self):
        """A RESTART IS A FREE SLOT NOBODY ASKED FOR.

        recover_on_boot pauses what the app was driving and
        resume_after_restart leaves a delegate paused while its worker may
        still be writing -- so the app can come up with room under the cap
        and tasks waiting for it. Pinned on the startup handler itself,
        because the hole was that nothing on the way in ever looked.
        """
        mission_engine.set_max_running(1)
        sched = MissionScheduler(self.store)
        waiting = [self.mission("first"), self.mission("second")]
        running = self.mission("was driving at shutdown")
        sched.start(running["id"])
        for w in waiting:
            self.assertEqual(sched.start(w["id"])["state"], "queued")
        # ...and the app went down: the driver is paused, the queue is not
        mission_engine.MissionEngine(
            self.store, None, None, None).founder_intervened(running["id"])

        launched = []
        shadow_runner._launch = lambda mid, *a, **k: launched.append(mid)
        promoted = asyncio.new_event_loop().run_until_complete(
            shadow_runner.drain_queue(lambda *x, **k: None, store=self.store))
        self.assertEqual(promoted, [waiting[0]["id"]],
                         "one slot, one promotion, oldest first")
        self.assertEqual(self.store.load(waiting[1]["id"])["state"], "queued",
                         "and the cap still holds for the rest")
        self.assertEqual(launched, [waiting[0]["id"]])

    def test_67_the_startup_handler_actually_calls_the_drain(self):
        """The 2.224.1 lesson the JS suite states in its own words: code that
        nobody calls. test_66 proves the sweep does the right thing; this
        proves the boot path is a caller of it."""
        import inspect
        src = inspect.getsource(app_module._shadow_recover)
        self.assertIn("await shadow_runner.drain_queue(_validated_say)", src,
                      "boot must drain the queue after the restart sweep")
        self.assertLess(src.index("resume_after_restart"),
                        src.index("drain_queue"),
                        "AFTER the restart sweep: a mission it re-admits "
                        "takes its slot back before the queue is offered one")


# ------------------------------------- THE CAP HOLDS ON EVERY WAY IN --
class TestNoDoorPastTheCap(Base):
    """`running_at_once` is only a limit if every door into `running` obeys
    it. These are the two that did not."""

    def setUp(self):
        super().setUp()
        self._real_launch = shadow_runner._launch
        shadow_runner._launch = lambda mid, *a, **k: None

    def tearDown(self):
        shadow_runner._launch = self._real_launch
        super().tearDown()

    def test_70_start_now_on_a_queued_task_at_the_cap_keeps_it_queued(self):
        """THE ONE CONTROL A QUEUED ROW OFFERS MUST NOT DESTROY IT.

        Start now on a queued task used to reach MissionScheduler.start in
        state `queued`, fall through to a queued -> queued transition that is
        not in the table, and raise -- into start_mission_async's rescue
        handler, which marks a failed start `failed`. A task waiting its turn
        was marked failed by the button offered to it.
        """
        mission_engine.set_max_running(1)
        sched = MissionScheduler(self.store)
        a, b = self.mission("holds the slot"), self.mission("waits")
        sched.start(a["id"])
        self.assertEqual(sched.start(b["id"])["state"], "queued")

        again = MissionScheduler(self.store).start(b["id"])
        self.assertEqual(again["state"], "queued",
                         "still waiting is not a new decision")
        self.assertEqual(self.store.load(b["id"])["state"], "queued")

    def test_71_starting_a_queued_task_does_not_jump_the_queue(self):
        """Idempotent means IDEMPOTENT: pressing Start now must not re-stamp
        the row and send it to the back -- or the front -- of the FIFO."""
        mission_engine.set_max_running(1)
        sched = MissionScheduler(self.store)
        a = self.mission("holds the slot")
        sched.start(a["id"])
        waiting = [self.mission("first"), self.mission("second")]
        for w in waiting:
            sched.start(w["id"])
        before = [self.store.load(w["id"]).get("created_ns") for w in waiting]
        MissionScheduler(self.store).start(waiting[1]["id"])   # Start now
        after = [self.store.load(w["id"]).get("created_ns") for w in waiting]
        self.assertEqual(before, after, "the FIFO position is untouched")
        mission_engine.set_max_running(2)
        promoted = MissionScheduler(self.store).on_terminal(None)
        self.assertEqual(promoted["id"], waiting[0]["id"],
                         "the oldest still goes first")

    def test_72_resume_at_the_cap_is_refused_and_says_why(self):
        mission_engine.set_max_running(1)
        sched = MissionScheduler(self.store)
        running = self.mission("holds the slot")
        sched.start(running["id"])
        paused = self.mission("was interrupted")
        MissionScheduler(self.store, max_running=99).start(paused["id"])
        mission_engine.MissionEngine(
            self.store, None, None, None).founder_intervened(paused["id"])

        r = self.client.post("/api/shadow/missions/%s/act" % paused["id"],
                             json={"action": "resume"}, headers=HDR)
        self.assertEqual(r.status_code, 409, r.text)
        detail = r.json()["detail"]
        self.assertTrue(detail.get("at_capacity"))
        self.assertEqual(detail.get("running_now"), 1)
        self.assertEqual(detail.get("running_at_once"), 1)
        self.assertIn("Running at once", detail.get("detail", ""),
                      "the refusal must name the way out")
        self.assertEqual(self.store.load(paused["id"])["state"], "paused",
                         "a refused resume changes nothing")

    def test_73_resume_with_a_free_slot_still_works(self):
        """The mirror. A cap that refuses when there IS room is not a cap,
        it is a bug."""
        mission_engine.set_max_running(2)
        sched = MissionScheduler(self.store)
        running = self.mission("holds one slot")
        sched.start(running["id"])
        paused = self.mission("was interrupted")
        MissionScheduler(self.store, max_running=99).start(paused["id"])
        mission_engine.MissionEngine(
            self.store, None, None, None).founder_intervened(paused["id"])

        r = self.client.post("/api/shadow/missions/%s/act" % paused["id"],
                             json={"action": "resume"}, headers=HDR)
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(self.store.load(paused["id"])["state"], "running")


if __name__ == "__main__":
    unittest.main()
