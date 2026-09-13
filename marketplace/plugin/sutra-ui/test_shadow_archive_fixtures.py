"""test_shadow_archive_fixtures.py -- the one-shot cleanup moves only debris."""
import json
import os
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import mission_engine  # noqa: E402
import shadow_archive_fixtures as arc  # noqa: E402
import shadow_ledger  # noqa: E402


class Archive(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.home = self.tmp.name
        os.environ["SUTRA_SHADOW_HOME"] = self.home
        store = mission_engine.MissionStore()
        self.floor = store.create("floor choke fixture", "fix",
                                  target_mode="existing",
                                  target_session="floor-choke-session")
        self.fake = store.create("orphan", "fix", target_mode="new",
                                 target_session="delegate-fake-4242")
        self.real = store.create("Fix the fixture loader in tests", "fix",
                                 target_mode="existing",
                                 target_session="5668c353-real")
        with open(os.path.join(self.home, "watches.json"), "w") as h:
            json.dump(["5668c353-real", "fake-24807", "fake-29125"], h)
        with open(os.path.join(self.home, "unwatched.json"), "w") as h:
            json.dump(["fake-2466"], h)
        shadow_ledger.append("actions", {"kind": "stop", "mission_id": None,
                                         "summary": "unwatch fake-2466"})

    def tearDown(self):
        os.environ.pop("SUTRA_SHADOW_HOME", None)
        self.tmp.cleanup()

    def test_10_plan_names_only_the_debris(self):
        p = arc.plan(self.home)
        ids = sorted(m["id"] for m in p["missions"])
        self.assertEqual(ids, sorted([self.floor["id"], self.fake["id"]]))
        self.assertEqual(p["lists"]["watches.json"]["drop"],
                         ["fake-24807", "fake-29125"])
        self.assertEqual(p["lists"]["watches.json"]["keep"], ["5668c353-real"])
        self.assertEqual(p["lists"]["unwatched.json"]["drop"], ["fake-2466"])
        self.assertGreaterEqual(p["ledger_fixture_rows"]["actions"], 1)
        # dry run: nothing moved
        self.assertEqual(len(mission_engine.MissionStore().list()), 3)

    def test_11_a_real_mission_mentioning_fixtures_is_not_debris(self):
        self.assertFalse(arc.is_fixture_mission(self.real))
        self.assertTrue(arc.is_fixture_mission(self.floor))
        self.assertTrue(arc.is_fixture_mission(self.fake))

    def test_12_apply_moves_and_rewrites_and_deletes_nothing(self):
        p = arc.plan(self.home)
        out = arc.apply(p, ts="20260913T000000Z")
        self.assertEqual(len(out["moved"]), 2)
        listed = mission_engine.MissionStore().list()
        self.assertEqual([m["id"] for m in listed], [self.real["id"]])
        adir = os.path.join(self.home, "missions", "archive", "20260913T000000Z")
        self.assertEqual(sorted(os.listdir(adir)),
                         sorted([self.floor["id"] + ".json",
                                 self.fake["id"] + ".json"]))
        with open(os.path.join(self.home, "watches.json")) as h:
            self.assertEqual(json.load(h), ["5668c353-real"])
        self.assertTrue(os.path.exists(
            os.path.join(self.home, "watches.json.bak-20260913T000000Z")))
        with open(os.path.join(self.home, "unwatched.json")) as h:
            self.assertEqual(json.load(h), [])
        notes = [r["note"] for r in shadow_ledger.read("missions", 50)
                 if r.get("mission_id") == self.floor["id"]]
        self.assertTrue(any(n.startswith("archived fixture row") for n in notes))
        # the append-only ledger is untouched
        rows = shadow_ledger.read("actions", 50)
        self.assertTrue(any("unwatch fake-2466" in r.get("summary", "")
                            for r in rows))
        # idempotent
        self.assertEqual(arc.plan(self.home)["missions"], [])


if __name__ == "__main__":
    unittest.main()
