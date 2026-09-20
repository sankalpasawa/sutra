#!/usr/bin/env python3
"""Deleting a Shadow task stops it for real, and files it instead of erasing it.

THE FOUNDER'S TWO REPORTS (2026-09-19):

  "if we delete a shadow task, the task should stop (the underlying task too
   should do a hard stop) and should be as a separate section as Archived"

WHAT THE X ACTUALLY DID. The delete branch of /api/shadow/missions/{id}/act
performed steps 2 and 4 of the six in `shadow_runner.founder_force_stop`:
MissionEngine.founder_stop (a state write) and release_delegate (the reaper
that needs a live runtime object). The three it skipped are the ones that
decide whether a worker actually dies:

  * the LOOP TASK was never cancelled, so the supervisor could still write a
    verdict about a mission that had just been removed;
  * the LEASE was never released;
  * there was no `_kill_orphan_delegate` fallback -- and DELEGATES is an
    in-memory map, empty for every mission that outlived an app restart. The
    record vanished from the list while the `claude` process it named kept
    running, with nothing left on disk pointing at it.

...and then it erased the record, so the one thing a founder might want after
pressing x -- what the task did -- lived only in the ledger, which the
workspace does not read.

THE SHAPE NOW. First press: founder_force_stop (or cancel_queued for an
attempt that never launched), then `store.archive` -- an additive
`archived_at` stamp, no state transition, record and chat both kept. Second
press: the erasure this branch always performed.

Run: marketplace/plugin/sutra-ui/run-tests.sh test_shadow_delete_archive.py
"""

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from fastapi.testclient import TestClient      # noqa: E402

import app as app_module                       # noqa: E402
import mission_engine                          # noqa: E402
import providers                               # noqa: E402
import shadow_runner                           # noqa: E402
from mission_engine import MissionStore        # noqa: E402

MIS = "/api/shadow/missions"


class Base(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app_module.app, base_url="http://127.0.0.1")

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        os.environ["SUTRA_SHADOW_HOME"] = self.tmp.name
        self._orig = providers.SETTINGS_PATH
        p = Path(self.tmp.name) / "settings.json"
        p.write_text(json.dumps({"shadow.enabled": True}))
        providers.SETTINGS_PATH = p
        self.store = MissionStore()
        self._real_launch = shadow_runner._launch
        shadow_runner._launch = lambda mid, *a, **k: None
        # WHAT THE STOP LADDER DID, recorded rather than performed: these two
        # reach the process table, and a test may not.
        self.forced, self.orphan_killed = [], []
        self._real_force = shadow_runner.founder_force_stop
        self._real_orphan = shadow_runner._kill_orphan_delegate
        self._real_release = shadow_runner.release_delegate

        def _force(mid, note="founder stop"):
            self.forced.append((mid, note))
            return self._real_force(mid, note)

        def _orphan(pid, sid):
            self.orphan_killed.append((pid, sid))
            return False

        shadow_runner.founder_force_stop = _force
        shadow_runner._kill_orphan_delegate = _orphan
        shadow_runner.release_delegate = lambda sid: None

    def tearDown(self):
        shadow_runner._launch = self._real_launch
        shadow_runner.founder_force_stop = self._real_force
        shadow_runner._kill_orphan_delegate = self._real_orphan
        shadow_runner.release_delegate = self._real_release
        providers.SETTINGS_PATH = self._orig
        os.environ.pop("SUTRA_SHADOW_HOME", None)
        self.tmp.cleanup()

    def mission(self, state=None, **fields):
        r = self.client.post(MIS, json={"objective": "Ship the fix.",
                                        "template": "fix",
                                        "target_mode": "new"})
        self.assertEqual(r.status_code, 200, r.text)
        mid = r.json()["id"]
        if state:
            self.store.transition(mid, state, "test")
        if fields:
            m = self.store.load(mid)
            m.update(fields)
            self.store.save(m)
        return mid

    def delete(self, mid):
        return self.client.post("%s/%s/act" % (MIS, mid),
                                json={"action": "delete"})


# ------------------------------------------------------- THE HARD STOP ----
class DeleteStopsTheWorker(Base):
    def test_a_running_task_goes_through_the_runners_force_stop(self):
        """NOT MissionEngine.founder_stop. The difference between them is the
        loop cancel, the lease release and the orphan kill -- i.e. everything
        that makes the stop reach the worker."""
        mid = self.mission("running")
        self.assertEqual(self.delete(mid).status_code, 200)
        self.assertEqual([m for m, _ in self.forced], [mid])

    def test_the_note_says_where_the_stop_came_from(self):
        mid = self.mission("running")
        self.delete(mid)
        self.assertIn("delete", self.forced[0][1])

    def test_a_terminal_task_falls_back_to_the_orphan_kill_by_pid(self):
        """founder_force_stop hands a concluded mission straight back -- a
        stop must never overwrite a completion -- so the reaping for that arm
        is done directly, and the pid fallback is what covers a worker this
        process has no handle on."""
        mid = self.mission("running", delegate_pid=4242,
                           target_session="s-term")
        self.store.transition(mid, "done", "finished")
        self.assertEqual(self.delete(mid).status_code, 200)
        self.assertEqual(self.orphan_killed, [(4242, "s-term")])
        self.assertEqual(self.forced, [], "nothing may re-stop a completion")

    def test_a_queued_task_is_cancelled_not_force_stopped(self):
        """cancel_queued is the one path for an attempt that was admitted and
        never launched; there is no worker to carry a stop to."""
        mid = self.mission("queued")
        self.assertEqual(self.delete(mid).status_code, 200)
        self.assertEqual(self.forced, [])
        self.assertEqual(self.store.load(mid)["state"], "stopped")


# --------------------------------------------------------- THE ARCHIVE ----
class TheFirstPressArchives(Base):
    def test_the_record_survives_and_is_stamped(self):
        mid = self.mission("running")
        body = self.delete(mid).json()
        self.assertTrue(body["archived"])
        self.assertFalse(body["deleted"])
        m = self.store.load(mid)
        self.assertIsNotNone(m, "an archive that erases is a delete")
        self.assertTrue(m["archived_at"])

    def test_archiving_is_not_a_state(self):
        """The stamp is additive. If this fails, every reader of the state
        machine has a new value to learn."""
        mid = self.mission("running")
        self.delete(mid)
        self.assertEqual(self.store.load(mid)["state"], "stopped",
                         "the state is the STOP's, not the archive's")

    def test_the_chat_shadow_made_is_kept(self):
        """The row is still in the list, so `Open the chat` on it must still
        have somewhere to go. Erasing the chat is the second press's job."""
        seen = []
        real = app_module._delete_delegate_chat
        app_module._delete_delegate_chat = lambda m: seen.append(m) or {}
        try:
            self.delete(self.mission("running"))
        finally:
            app_module._delete_delegate_chat = real
        self.assertEqual(seen, [], "an archived task keeps its chat")

    def test_archiving_twice_changes_nothing_before_the_second_press(self):
        mid = self.mission("running")
        self.delete(mid)
        first = self.store.load(mid)["archived_at"]
        self.assertEqual(self.store.archive(mid)["archived_at"], first)


class TheSecondPressErases(Base):
    def test_the_record_and_the_chat_go(self):
        seen = []
        real = app_module._delete_delegate_chat
        app_module._delete_delegate_chat = lambda m: seen.append(m) or {}
        mid = self.mission("running")
        try:
            self.delete(mid)
            body = self.delete(mid).json()
        finally:
            app_module._delete_delegate_chat = real
        self.assertTrue(body["deleted"])
        self.assertFalse(body["archived"])
        self.assertIsNone(self.store.load(mid))
        self.assertEqual(len(seen), 1, "the chat goes with the erasure")

    def test_erasing_does_not_re_stop_an_already_stopped_task(self):
        mid = self.mission("running")
        self.delete(mid)
        self.forced.clear()
        self.delete(mid)
        self.assertEqual(self.forced, [])


class TheStoreVerbStandsAlone(Base):
    def test_archive_refuses_a_mission_that_does_not_exist(self):
        with self.assertRaises(ValueError):
            self.store.archive("m-nope")

    def test_delete_remains_the_only_eraser(self):
        mid = self.mission("running")
        self.store.archive(mid)
        self.assertTrue(self.store.delete(mid))
        self.assertIsNone(self.store.load(mid))


if __name__ == "__main__":
    unittest.main()
