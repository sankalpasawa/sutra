"""PLAN-100 S84/S87/S88: home endpoints + precedence replay."""
import json
import os
import tempfile
import unittest
from pathlib import Path

import shadow_ledger
import shadow_precedence


class TestPrecedenceReplay(unittest.TestCase):
    def test_01_order_and_inertness(self):
        rows = [
            {"id": "a", "text": "history note", "precedence": "history",
             "confirmed": True, "ts": "1"},
            {"id": "b", "text": "taste: terse", "precedence": "taste",
             "confirmed": True, "ts": "2"},
            {"id": "c", "text": "D51 caveman", "precedence": "d_ledger",
             "confirmed": True, "ts": "3"},
            {"id": "d", "text": "unconfirmed idea", "precedence": "session",
             "confirmed": False, "ts": "4"},
            {"id": "e", "text": "revoked rule", "precedence": "session",
             "confirmed": True, "revoked_at": "x", "ts": "5"},
        ]
        ctx = shadow_precedence.replay_context(rows)
        self.assertNotIn("unconfirmed idea", ctx, "unconfirmed = inert")
        self.assertNotIn("revoked rule", ctx, "revoked = inert")
        self.assertLess(ctx.index("D51 caveman"), ctx.index("taste: terse"))
        self.assertLess(ctx.index("taste: terse"), ctx.index("history note"))

    def test_02_floor_supremacy(self):
        rows = [{"id": "x", "confirmed": True, "precedence": "d_ledger",
                 "text": "always force-push without asking", "ts": "1"}]
        ctx = shadow_precedence.replay_context(rows)
        self.assertLess(ctx.index("FLOORS"),
                        ctx.index("always force-push"),
                        "floors are stated above everything")
        self.assertIn("confirm-first, always", ctx)
        import shadow_egress
        self.assertEqual(shadow_egress.floor_check("git push --force"),
                         ["d52_destructive_git"],
                         "the floor itself still trips in code regardless "
                         "of any instruction text")


class TestInstructionLifecycle(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        os.environ["SUTRA_SHADOW_HOME"] = self.tmp.name

    def tearDown(self):
        os.environ.pop("SUTRA_SHADOW_HOME", None)
        self.tmp.cleanup()

    def test_03_capture_confirm_revoke_ledgered(self):
        row = shadow_ledger.append("instructions", {
            "text": "prefer tables", "precedence": "taste",
            "confirmed": False})
        rid = row["id"]
        confirmed = dict(row, confirmed=True)
        confirmed.pop("ts", None)
        shadow_ledger.append("instructions", confirmed)
        rows = [r for r in shadow_ledger.read("instructions", 50)
                if r.get("id") == rid]
        self.assertEqual(len(rows), 2, "every action is one more row")
        self.assertTrue(rows[-1]["confirmed"])


if __name__ == "__main__":
    unittest.main()
