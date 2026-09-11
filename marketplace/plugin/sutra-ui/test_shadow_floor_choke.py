"""Acceptance fixture for PRD R8's floor clause, on the DIRECT say path.

JOURNEY-TESTS.md section 3a: floor_check had exactly ONE caller
(mission_engine.py:331, the mission loop), so `_validated_say` -- reachable by
Shadow itself via the MCP shadow_session_say tool -> POST /api/sessions/{sid}/say
-- queued floor-tripping payloads with no gate at all. The three floors that
SHADOW.md section 2 declares never ledger-overridable (D52-gated git ops, D33
client repos, irreversible external sends) had no enforcement on that path.

This is an ACCEPTANCE fixture, not a unit test of floor_check. It drives the
real `_validated_say` with a real MissionStore and asserts the refusal. It is
written to FAIL if the floor call in _validated_say is removed -- that property
is the whole point, and JOURNEY-TESTS.md T1-T4 record what happens without it:
21 PRD-named fixtures did not exist, and 85 green unit tests coexisted with four
features broken in production.

Run on the app's own interpreter (3.11):
  /Applications/Sutra.app/Contents/Resources/payload/python/bin/python3 \
      test_shadow_floor_choke.py
"""
import os
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

# Isolate every store this test touches BEFORE app import, so the founder's
# real ~/.sutra-ui/shadow is never written (JOURNEY-TESTS.md W4: test fixtures
# leaking into the live watch store is itself a filed defect).
_TMP = tempfile.mkdtemp(prefix="floor-choke-")
os.environ["SUTRA_SHADOW_HOME"] = _TMP
os.environ["SUTRA_SHADOW_ENABLED"] = "1"

import app as appmod                      # noqa: E402
import mission_engine as me               # noqa: E402
import providers                          # noqa: E402
import shadow_egress                      # noqa: E402
from fastapi import HTTPException         # noqa: E402


class _Queue:
    """Minimal TurnQueue stand-in: records what actually got queued."""

    def __init__(self):
        self.accepted = []

    def put(self, payload, source=None, dedupe_key=None):
        self.accepted.append(payload)
        return True

    def __len__(self):
        return len(self.accepted)


class _Runtime:
    def __init__(self):
        self.turn_queue = _Queue()

        class _Ev:
            def set(self):
                pass
        self.queue_event = _Ev()


SID = "floor-choke-session"

# One per floor family in shadow_egress._FLOOR_PATTERNS. If a pattern set
# changes and one of these stops tripping, this fixture must fail loudly
# rather than silently prove less than it claims.
FLOORED = [
    "git push --force to origin main",
    "run git reset --hard HEAD~3",
    "send the email to the client now",
]

CLEAN = "summarise the last three test failures and stop"


class TestFloorChokePoint(unittest.TestCase):

    def setUp(self):
        self._real_lookup = appmod.lookup_runtime
        self._real_enabled = providers.shadow_enabled
        providers.shadow_enabled = lambda: True
        self.rt = _Runtime()
        appmod.lookup_runtime = lambda sid: self.rt if sid == SID else None

        store = me.MissionStore()
        m = store.create(objective="floor choke fixture", template="fix",
                         target_mode="existing", target_session=SID,
                         done_when=[{"tier": "founder_confirm",
                                     "check": "founder says so"}])
        self.mid = m["id"]
        m = store.load(self.mid)
        m["state"] = "running"
        m["target_session"] = SID
        store.save(m)

    def tearDown(self):
        appmod.lookup_runtime = self._real_lookup
        providers.shadow_enabled = self._real_enabled

    def test_01_patterns_still_trip(self):
        """Guard the guard: every sample must actually trip a floor."""
        for text in FLOORED:
            self.assertTrue(shadow_egress.floor_check(text),
                            "sample no longer trips any floor: %r" % text)
        self.assertEqual(shadow_egress.floor_check(CLEAN), [])

    def test_02_direct_say_refuses_every_floor(self):
        """THE acceptance assertion. Fails if the floor call is removed."""
        for text in FLOORED:
            with self.assertRaises(HTTPException) as cm:
                appmod._validated_say(SID, self.mid, text)
            self.assertEqual(cm.exception.status_code, 403,
                             "expected 403 for %r" % text)
            self.assertIn("floor", str(cm.exception.detail).lower())

    def test_03_nothing_floored_reaches_the_queue(self):
        """A refusal that still queued the payload would be worthless."""
        for text in FLOORED:
            try:
                appmod._validated_say(SID, self.mid, text)
            except HTTPException:
                pass
        self.assertEqual(self.rt.turn_queue.accepted, [],
                         "a floored payload was queued anyway")

    def test_04_clean_say_still_passes(self):
        """The floor must not become a blanket block."""
        out = appmod._validated_say(SID, self.mid, CLEAN)
        self.assertTrue(out.get("queued"))
        self.assertEqual(len(self.rt.turn_queue.accepted), 1)
        self.assertIn(self.mid, self.rt.turn_queue.accepted[0]["message"])

    def test_05_floor_names_only_never_the_message(self):
        """403 detail must not echo the payload back."""
        secret = "git push --force with token sk-live-abc123"
        with self.assertRaises(HTTPException) as cm:
            appmod._validated_say(SID, self.mid, secret)
        detail = str(cm.exception.detail)
        self.assertNotIn("sk-live-abc123", detail)
        self.assertNotIn("--force", detail)

    def test_06_floor_precedes_scrub(self):
        """Raw-before-scrub (codex): scrub is confidentiality, not safety.

        A floored message carrying a secret must be refused, not scrubbed and
        then queued.
        """
        with self.assertRaises(HTTPException):
            appmod._validated_say(SID, self.mid,
                                  "send the email containing sk-live-xyz")
        self.assertEqual(self.rt.turn_queue.accepted, [])

    def test_07_tool_gate_contract_names_the_floor(self):
        """The declared contract must not understate what the path enforces."""
        gate = shadow_egress.TOOL_GATES["shadow_session_say"]["gate"]
        self.assertIn("FLOOR", gate)


if __name__ == "__main__":
    unittest.main(verbosity=2)
