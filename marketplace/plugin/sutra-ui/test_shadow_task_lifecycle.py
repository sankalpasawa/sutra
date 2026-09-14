"""The Shadow task list's lifecycle, through the real FastAPI app.

Three founder-facing fixes (2026-09-14), one suite, because all three are
about the SAME record -- the mission behind a row in Focus > Shadow -- and
each one's proof is "the store and the endpoint agree with what the list
shows after a reload":

  FIX 1  delete       a task can be removed, the removal is a server-side
                      erase (so a refresh cannot bring it back), a LIVE task
                      is ended through the existing founder paths and its
                      delegate is released before the record goes, and
                      nothing unrelated is touched.
  FIX 2  start state  accepting a start stamps the record, so the UI can stop
                      drawing Start for a task that is already starting --
                      and a stamp the previous process never finished is
                      cleared at boot instead of stranding the task.
  FIX 3  create+start create and the existing start are one founder action:
                      one mission, one start call, and a reload starts
                      nothing a second time.

`start_mission_async` is stubbed throughout -- the route's job is to hand the
right mission to the EXISTING start path, and spawning a real delegate is
test_shadow_delegate.py's seam, not this one. `release_delegate` is NOT
stubbed: it is the reaper the delete path leans on, and a stub would prove
nothing about the orphan case.

Run: .venv/bin/python -m unittest test_shadow_task_lifecycle -v
"""
import json
import os
import tempfile
import unittest
from pathlib import Path

os.environ["SUTRA_SHADOW_HOME"] = tempfile.mkdtemp(prefix="shadow-task-test-")

from fastapi.testclient import TestClient  # noqa: E402

import app as app_module  # noqa: E402
import chat_store  # noqa: E402
import mission_engine  # noqa: E402
import providers  # noqa: E402
import session_runtime  # noqa: E402
import shadow_runner  # noqa: E402
from goal_store import GoalStore  # noqa: E402
from mission_engine import MissionStore  # noqa: E402

HDR = {"X-Sutra-Panel": app_module.PANEL_TOKEN,
       "Origin": "http://127.0.0.1:8330"}
MIS = "/api/shadow/missions"


class _FakeDelegate:
    """What DELEGATES holds: something Shadow can reap. Records the reap so
    the running-delete case can prove the worker was not orphaned."""

    def __init__(self):
        self.killed = False
        self.cleared = False
        self.alive = True

    def kill_group(self):
        self.killed = True

    def clear(self):
        self.cleared = True


class Base(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app_module.app, base_url="http://127.0.0.1")

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        os.environ["SUTRA_SHADOW_HOME"] = self.tmp.name
        # the chat store is isolated for the same reason the mission home is:
        # these tests DELETE chats, and they must never reach the real one
        self.chats = os.path.join(self.tmp.name, "chats")
        os.environ["SUTRA_UI_CHATS"] = self.chats
        self._orig = providers.SETTINGS_PATH
        self.settings = Path(self.tmp.name) / "settings.json"
        self.settings.write_text(json.dumps({"shadow.enabled": True}))
        providers.SETTINGS_PATH = self.settings
        self.store = MissionStore()
        # the start path is stubbed: these tests are about the ROUTE handing
        # the right mission to it, never about provisioning one
        self.started = []
        self._real_start = shadow_runner.start_mission_async
        shadow_runner.start_mission_async = lambda mid, *a, **k: (
            self.started.append(mid)
            or {"accepted": True, "mission_id": mid})

    def tearDown(self):
        shadow_runner.start_mission_async = self._real_start
        providers.SETTINGS_PATH = self._orig
        self.tmp.cleanup()

    # ------------------------------------------------------------ helpers --
    def create(self, objective="fix the EMI rounding", **kw):
        body = {"objective": objective, "template": "fix",
                "target_mode": "new"}
        body.update(kw)
        r = self.client.post(MIS, json=body, headers=HDR)
        self.assertEqual(r.status_code, 200, r.text)
        return r.json()

    def act(self, mid, action, **body):
        return self.client.post("%s/%s/act" % (MIS, mid),
                                json=dict(body, action=action), headers=HDR)

    def listed(self):
        """What the left task list reads on every load -- and on a refresh."""
        r = self.client.get(MIS, headers=HDR)
        self.assertEqual(r.status_code, 200, r.text)
        return [m["id"] for m in r.json()["missions"]]


# ===========================================================  FIX 1: delete ==
class TestDelete(Base):

    def test_01_delete_removes_the_record_and_a_reload_agrees(self):
        keep = self.create("keep me")
        go = self.create("delete me")
        self.assertEqual(sorted(self.listed()), sorted([keep["id"], go["id"]]))

        r = self.act(go["id"], "delete")
        self.assertEqual(r.status_code, 200, r.text)
        self.assertTrue(r.json()["deleted"])

        # THE LIST, RELOADED. This is the founder's refresh: the same GET the
        # page makes on every load, answered by the store on disk.
        self.assertEqual(self.listed(), [keep["id"]],
                         "the deleted task came back on reload")
        # and it is genuinely gone from the store, not filtered by the route
        self.assertIsNone(MissionStore().load(go["id"]),
                          "the record is still on disk")
        self.assertIsNotNone(MissionStore().load(keep["id"]),
                             "an unrelated task was deleted too")

    def test_02_the_files_are_gone_including_the_scaffolding(self):
        go = self.create("delete me")
        home = mission_engine._home()
        path = os.path.join(home, go["id"] + ".json")
        self.assertTrue(os.path.exists(path))
        self.act(go["id"], "delete")
        for suffix in ("", ".tmp", ".lock"):
            self.assertFalse(os.path.exists(path + suffix),
                             "left %s behind" % (path + suffix))

    def test_03_deleting_twice_is_a_404_not_a_500(self):
        go = self.create()
        self.assertEqual(self.act(go["id"], "delete").status_code, 200)
        self.assertEqual(self.act(go["id"], "delete").status_code, 404)

    def test_04_a_running_task_is_stopped_and_its_delegate_released(self):
        """The orphan case. A running mission owns a delegate PROCESS, and
        deleting the record without reaping it would leave that process
        appending to a transcript nothing points at any more."""
        m = self.create()
        sid = "sess-running-1"
        self.store.transition(m["id"], "running", "test")
        rec = self.store.load(m["id"])
        rec["target_session"] = sid
        self.store.save(rec)
        rt = _FakeDelegate()
        shadow_runner.DELEGATES[sid] = rt
        session_runtime.register_runtime(sid, rt)
        try:
            r = self.act(m["id"], "delete")
            self.assertEqual(r.status_code, 200, r.text)
        finally:
            shadow_runner.DELEGATES.pop(sid, None)
            session_runtime.unregister_runtime(sid, rt)
        self.assertTrue(rt.killed, "the delegate process was orphaned")
        self.assertIsNone(MissionStore().load(m["id"]))
        self.assertEqual(self.listed(), [])

    def test_05_a_running_task_is_ended_as_a_FOUNDER_decision(self):
        """founder_stop, not a bare transition: `ended_by` is what stops the
        goal layer reading a founder's delete as machine trouble. Asserted
        through the ledger, because the record itself is then deleted."""
        m = self.create()
        self.store.transition(m["id"], "running", "test")
        self.act(m["id"], "delete")
        import shadow_ledger
        rows = [r for r in shadow_ledger.read("missions", 200)
                if r.get("mission_id") == m["id"]]
        states = [r.get("state") for r in rows]
        self.assertIn("stopped", states,
                      "a live task must be STOPPED before its record goes")
        self.assertLess(states.index("stopped"), states.index("deleted"),
                        "the record was removed before the work was ended")
        self.assertEqual(states[-1], "deleted")

    def test_06_a_queued_task_goes_through_cancel_queued(self):
        """A queued attempt never reached the runner, so `drop` -- not a stop
        of something that is not running -- is its existing end."""
        m = self.create()
        self.store.transition(m["id"], "queued", "cap reached")
        r = self.act(m["id"], "delete")
        self.assertEqual(r.status_code, 200, r.text)
        self.assertIsNone(MissionStore().load(m["id"]))

    def test_07_a_goal_attempt_is_released_before_its_record_goes(self):
        """Otherwise the goal keeps pointing current_mission_id at a file
        that no longer exists."""
        goals = GoalStore()
        g = goals.create("the referral workflow is configured",
                         "sess-goal-1",
                         done_when=[{"tier": "founder_confirm",
                                     "check": "the founder agrees"}])
        m = self.store.create("attempt", "fix", target_mode="new",
                              goal_id=g["id"])
        self.store.transition(m["id"], "brief_confirm", "attempt")
        goals.bind_mission(g["id"], m["id"], "attempt 1")
        self.assertEqual(GoalStore().load(g["id"])["current_mission_id"],
                         m["id"])

        r = self.act(m["id"], "delete")
        self.assertEqual(r.status_code, 200, r.text)
        after = GoalStore().load(g["id"])
        self.assertIsNone(after["current_mission_id"],
                          "the goal still points at a deleted mission")
        self.assertTrue(after["attempts"],
                        "the goal's own attempt history was destroyed")

    def test_08_terminal_tasks_delete_without_being_stopped_again(self):
        for state in ("done", "failed", "stopped"):
            m = self.create("a %s task" % state)
            self.store.transition(m["id"], "running", "test")
            self.store.transition(m["id"], state, "test")
            r = self.act(m["id"], "delete")
            self.assertEqual(r.status_code, 200,
                             "%s: %s" % (state, r.text))
            self.assertIsNone(MissionStore().load(m["id"]))

    def test_09_the_flag_gates_delete_like_every_other_action(self):
        m = self.create()
        self.settings.write_text(json.dumps({"shadow.enabled": False}))
        self.assertEqual(self.act(m["id"], "delete").status_code, 403)
        self.settings.write_text(json.dumps({"shadow.enabled": True}))
        self.assertIsNotNone(MissionStore().load(m["id"]),
                             "a refused delete must not have deleted")


# ====================================================  FIX 2: start / status ==
class TestStartState(Base):

    def test_10_accepting_a_start_stamps_the_record(self):
        """The window the Start button used to survive: /act answers
        immediately and provisions in the background, so the record is still
        brief_confirm. The stamp is what the UI reads to draw the existing
        QUEUED face instead of an actionable Start."""
        m = self.create()
        self.assertNotIn("start_requested_at", m,
                         "a fresh task must not look started")
        r = self.act(m["id"], "start_now")
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(self.started, [m["id"]],
                         "the EXISTING start path must be the one used")

        # the reload the page makes -- this is the whole point: the pressed
        # start survives a refresh
        rec = MissionStore().load(m["id"])
        self.assertTrue(rec.get("start_requested_at"),
                        "a refresh cannot tell the start was taken")
        self.assertEqual(rec["state"], "brief_confirm",
                         "the stamp must not be a state change")

    def test_11_the_stamp_never_overwrites_a_real_state(self):
        """running and queued already SAY they started; the stamp covers only
        the gap, so it must not touch anything that has left brief_confirm."""
        for state in ("running", "queued"):
            m = self.create("a %s task" % state)
            self.store.transition(m["id"], state, "test")
            app_module._mark_start_requested(self.store, m["id"])
            rec = MissionStore().load(m["id"])
            self.assertNotIn("start_requested_at", rec, state)
            self.assertEqual(rec["state"], state, state)

    def test_12_retry_stamps_the_clone_the_server_actually_starts(self):
        m = self.create()
        self.store.transition(m["id"], "running", "test")
        self.store.transition(m["id"], "failed", "out of road")
        r = self.act(m["id"], "retry")
        self.assertEqual(r.status_code, 200, r.text)
        clone = r.json()["mission_id"]
        self.assertNotEqual(clone, m["id"], "retry must clone")
        self.assertTrue(MissionStore().load(clone).get("start_requested_at"),
                        "the clone -- the mission that starts -- is unstamped")
        self.assertIsNone(MissionStore().load(m["id"])
                          .get("start_requested_at"),
                          "the original must not claim to be starting")

    def test_13_boot_clears_a_start_the_last_process_never_finished(self):
        """Admission runs as an app task, so a restart leaves nothing to
        finish it. Without this the task would read QUEUED forever with no
        way to act on it."""
        stranded = self.create("stranded")
        self.act(stranded["id"], "start_now")
        live = self.create("live")
        self.store.transition(live["id"], "running", "test")
        rec = self.store.load(live["id"])
        rec["start_requested_at"] = "2026-09-14T10:00:00Z"
        self.store.save(rec)

        cleared = app_module._clear_stale_start_requests()

        self.assertEqual(cleared, 1)
        self.assertIsNone(MissionStore().load(stranded["id"])
                          .get("start_requested_at"),
                          "the stranded task never got its Start back")
        self.assertEqual(MissionStore().load(stranded["id"])["state"],
                         "brief_confirm")
        self.assertTrue(MissionStore().load(live["id"])
                        .get("start_requested_at"),
                        "boot rewrote a mission that had already moved on")

    def test_14_a_double_start_never_becomes_a_second_launch(self):
        """The UI stops offering Start once the stamp is on, and the server
        keeps its own guard: the second press must not create a second
        mission or a second target."""
        m = self.create()
        self.act(m["id"], "start_now")
        self.act(m["id"], "start_now")
        self.assertEqual(self.listed(), [m["id"]],
                         "a second start created a second task")
        self.assertEqual(self.started, [m["id"], m["id"]],
                         "both presses must go to the same existing path")


# ================================================  FIX 3: create AND start ==
class TestCreateAndStart(Base):

    def test_15_create_then_the_existing_start_is_one_mission_one_launch(self):
        """The two halves the founder's single press now performs. The
        chaining itself is the panel's (test_shadow_home.js 17); what is
        pinned here is that the server side of it creates exactly one
        mission and launches it exactly once, through the path that already
        existed."""
        m = self.create("ship the EMI fix",
                        done_when=[{"tier": "founder_confirm",
                                    "check": "a tested PR is open"}])
        self.assertEqual(m["state"], "brief_confirm")
        self.assertEqual(m["target_mode"], "new")
        self.assertIsNone(m["target_session"],
                          "creation must not provision a chat by itself")

        r = self.act(m["id"], "start_now")
        self.assertEqual(r.status_code, 200, r.text)

        self.assertEqual(self.listed(), [m["id"]], "exactly one task exists")
        self.assertEqual(self.started, [m["id"]], "exactly one launch")
        rec = MissionStore().load(m["id"])
        self.assertEqual(rec["done_when"][0]["check"], "a tested PR is open",
                         "Done When was not preserved")
        self.assertEqual(rec["template"], "fix", "task type was not preserved")
        self.assertEqual(rec["max_turns"],
                         mission_engine.TEMPLATES["fix"]["max_turns"],
                         "the template's budget default was not preserved")

    def test_16_a_reload_creates_nothing_and_starts_nothing(self):
        m = self.create()
        self.act(m["id"], "start_now")
        before = len(self.started)
        for _ in range(3):                      # three refreshes
            self.assertEqual(self.listed(), [m["id"]])
        self.assertEqual(len(self.started), before,
                         "reading the list restarted the worker")
        self.assertEqual(len(MissionStore().list()), 1,
                         "reading the list created another mission")


# ==================================  FIX 1b: the chat goes with the task ==
class TestDeleteTakesTheChat(Base):
    """Deleting a task must not leave its chat behind.

    THE BUG THIS PINS. The delete path ended the mission, released the
    delegate and erased the record -- and deliberately left the chat, on the
    reasoning that a published chat is durable like any other. But a chat
    SHADOW MADE for one task is not like any other: nothing else will ever
    claim it, it is named after the task, and once the task is gone there is
    nothing left that names the chat either. The founder deleted a task and
    the conversation stayed in Chats with no way to tell what it belonged to.

    The ownership line is target_mode, and it is the safety property:
    "new" is a chat Shadow spawned and owns; "existing" is the founder's own
    chat, which Shadow only ever visited, and which must survive.
    """

    def _bind_chat(self, mission, native_id, mode="new"):
        """Publish a chat for a mission the way _publish_delegate_chat does:
        a record, a segment (which is what writes the index row), and the two
        links back onto the mission."""
        rec = chat_store.create(cwd="/tmp", title="Shadow Task")
        chat_store.begin_segment(rec, "claude", native_id)
        chat_store.save(rec)
        m = self.store.load(mission["id"])
        m["target_session"] = native_id
        m["target_chat"] = rec["sutra_id"]
        m["target_mode"] = mode
        self.store.save(m)
        return rec["sutra_id"]

    def test_20_a_shadow_made_chat_is_removed_with_the_task(self):
        m = self.create()
        sutra_id = self._bind_chat(m, "sess-delegate-1")
        self.assertTrue(chat_store.index(), "the chat must exist first")

        r = self.act(m["id"], "delete")
        self.assertEqual(r.status_code, 200, r.text)
        self.assertTrue(r.json()["deleted"])
        self.assertTrue(r.json()["chat_deleted"],
                        "the endpoint must say the chat went too")

        self.assertIsNone(chat_store.resolve("claude", "sess-delegate-1"),
                          "the index row outlived the task")
        self.assertIsNone(chat_store.load(sutra_id),
                          "the chat record outlived the task")
        self.assertEqual(chat_store.index(), {},
                         "an orphan chat was left in Chats")
        self.assertNotIn(m["id"], self.listed())

    def test_21_the_founders_OWN_chat_is_never_deleted(self):
        """target_mode='existing' means Shadow was a visitor. Deleting the
        task must not delete a conversation the founder started."""
        m = self.create(target_mode="existing")
        sutra_id = self._bind_chat(m, "sess-founder-1", mode="existing")

        r = self.act(m["id"], "delete")
        self.assertEqual(r.status_code, 200, r.text)
        self.assertFalse(r.json()["chat_deleted"],
                         "it must not claim to have deleted the chat")
        self.assertEqual(chat_store.resolve("claude", "sess-founder-1"),
                         sutra_id, "the founder's chat was unbound")
        self.assertIsNotNone(chat_store.load(sutra_id),
                             "the founder's chat record was destroyed")
        self.assertNotIn(m["id"], self.listed(),
                         "the task itself must still be gone")

    def test_22_deleting_one_task_leaves_another_tasks_chat_alone(self):
        keep = self.create("keep me")
        keep_chat = self._bind_chat(keep, "sess-keep")
        drop = self.create("drop me")
        drop_chat = self._bind_chat(drop, "sess-drop")
        self.assertEqual(len(chat_store.index()), 2)

        self.act(drop["id"], "delete")

        self.assertIsNone(chat_store.load(drop_chat), "the target chat stayed")
        self.assertIsNotNone(chat_store.load(keep_chat),
                             "an unrelated chat was deleted")
        self.assertEqual(chat_store.resolve("claude", "sess-keep"), keep_chat,
                         "an unrelated index row was dropped")
        self.assertEqual(self.listed(), [keep["id"]])

    def test_23_a_running_task_loses_its_chat_too(self):
        """The orphan case that matters most: a live task deleted mid-flight
        must not leave both a worker AND a chat behind."""
        m = self.create()
        sutra_id = self._bind_chat(m, "sess-live")
        self.store.transition(m["id"], "running", "admitted")
        rt = _FakeDelegate()
        shadow_runner.DELEGATES["sess-live"] = rt
        try:
            r = self.act(m["id"], "delete")
        finally:
            shadow_runner.DELEGATES.pop("sess-live", None)
        self.assertEqual(r.status_code, 200, r.text)
        self.assertTrue(rt.killed, "the worker was orphaned")
        self.assertIsNone(chat_store.load(sutra_id), "the chat was orphaned")
        self.assertNotIn(m["id"], self.listed())

    def test_24_a_task_that_never_got_a_chat_deletes_cleanly(self):
        """Most deletes are this: a task removed before it ever ran."""
        m = self.create()
        r = self.act(m["id"], "delete")
        self.assertEqual(r.status_code, 200, r.text)
        self.assertFalse(r.json()["chat_deleted"])
        self.assertNotIn(m["id"], self.listed())

    def test_25_the_record_is_erased_LAST(self):
        """The mission is the only thing that names the session and the chat,
        so it cannot be erased before they are dealt with. Proved by the
        outcome: both are gone, which is only reachable in that order."""
        m = self.create()
        sutra_id = self._bind_chat(m, "sess-order")
        self.act(m["id"], "delete")
        self.assertIsNone(MissionStore().load(m["id"]))
        self.assertIsNone(chat_store.load(sutra_id))


# =====================================  the eraser the chat store lacked ==
class TestChatStoreDelete(unittest.TestCase):
    """chat_store.delete() on its own terms."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        os.environ["SUTRA_UI_CHATS"] = os.path.join(self.tmp.name, "chats")

    def tearDown(self):
        self.tmp.cleanup()

    def test_30_it_drops_every_row_pointing_at_the_chat(self):
        """A chat can own SEVERAL provider sessions in sequence (that is what
        provider_history is for), so one row is not enough."""
        rec = chat_store.create(cwd="/tmp", title="switched chat")
        chat_store.begin_segment(rec, "claude", "n-1")
        chat_store.save(rec)
        chat_store.begin_segment(rec, "codex", "n-2")
        chat_store.save(rec)
        self.assertEqual(len(chat_store.index()), 2)

        self.assertTrue(chat_store.delete(rec["sutra_id"]))
        self.assertEqual(chat_store.index(), {},
                         "a switched chat left half its rows behind")
        self.assertIsNone(chat_store.load(rec["sutra_id"]))

    def test_31_it_leaves_other_chats_alone(self):
        a = chat_store.create(cwd="/tmp"); chat_store.begin_segment(a, "claude", "a-1")
        chat_store.save(a)
        b = chat_store.create(cwd="/tmp"); chat_store.begin_segment(b, "claude", "b-1")
        chat_store.save(b)
        chat_store.delete(a["sutra_id"])
        self.assertEqual(chat_store.resolve("claude", "b-1"), b["sutra_id"])
        self.assertIsNotNone(chat_store.load(b["sutra_id"]))

    def test_32_it_is_idempotent_and_refuses_nonsense(self):
        rec = chat_store.create(cwd="/tmp")
        chat_store.begin_segment(rec, "claude", "c-1")
        chat_store.save(rec)
        self.assertTrue(chat_store.delete(rec["sutra_id"]))
        self.assertFalse(chat_store.delete(rec["sutra_id"]), "not idempotent")
        self.assertFalse(chat_store.delete("not-a-sutra-id"))
        self.assertFalse(chat_store.delete(None))
        self.assertFalse(chat_store.delete("0" * 32), "unknown id must be False")


if __name__ == "__main__":
    unittest.main()
