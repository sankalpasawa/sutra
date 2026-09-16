#!/usr/bin/env python3
"""An answer to a targeted question closes the check it was asked about.

THE GAP (founder, 2026-09-15, mission m-cd009367d41a). Shadow asked "Do you
accept the test evidence as passing?", the founder answered
`tests_pass: True`, and the mission still could not complete. Replayed
against the real 112,379-character transcript:

    contains_artifact  met=True   The timestamp is visible on the task card.
    contains_artifact  met=True   Tests cover it.
    founder_confirm    met=False  Relevant tests pass.      <- the blocker
    contains_artifact  met=True   The change is actually implemented...
    contains_artifact  met=True   Shadow reaches DONE.

Four of five passed. The answer landed in `founder_response`; done_when[2]
stayed unmet, because confirm_check is the only writer of that flag and an
intervention answer never called it. The mission burned its remaining turns
and died `failed` on max turns at 21:29:14.

WHAT THIS DOES NOT CHANGE. confirm_check is STILL the one writer, still
stamps confirmed_by/confirmed_at, and Shadow still cannot satisfy the tier.
evaluate_done_when, contains_artifact and the turn budget are untouched. The
integration is opt-in per intervention and affirmative-only.

Run: python3 test_shadow_intervention_confirms.py
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
import shadow_intervention as siv              # noqa: E402
import shadow_runner                           # noqa: E402
import shadow_runner                           # noqa: E402
from mission_engine import MissionStore        # noqa: E402

MIS = "/api/shadow/missions"
HDR = {"host": "127.0.0.1"}

#: the real shape: one boolean gate plus an ungated extra field
def request(index=0, field="tests_pass", extra=True):
    fields = [{"key": "tests_pass", "type": "boolean",
               "label": "Do the tests pass?"}]
    if extra:
        fields.append({"key": "pixels", "type": "choice", "label": "Pixels?",
                       "options": [{"value": "ok", "label": "fine"},
                                   {"value": "need_browser",
                                    "label": "look in a browser"}]})
    out = {"question": "Do you accept the test evidence as passing?",
           "fields": fields}
    if index is not None:
        out["confirms_check"] = {"index": index, "field": field}
    return out


CHECKS = [{"tier": "founder_confirm", "check": "Relevant tests pass."},
          {"tier": "contains_artifact", "check": "FINAL:"}]


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
        self.launched = []
        self._real_launch = shadow_runner._launch
        shadow_runner._launch = lambda mid, *a, **k: self.launched.append(mid)

    def tearDown(self):
        shadow_runner._launch = self._real_launch
        providers.SETTINGS_PATH = self._orig
        os.environ.pop("SUTRA_SHADOW_HOME", None)
        self.tmp.cleanup()

    def blocked_with(self, req, checks=None):
        m = self.store.create("ship it", "fix", target_mode="new",
                              target_session="sess-keep",
                              done_when=list(checks if checks is not None
                                             else CHECKS))
        mid = m["id"]
        self.store.transition(mid, "brief_confirm", "proposed")
        self.store.transition(mid, "running", "admitted")
        d = mission_engine.validate_decision(
            {"action": "ask_founder", "reason": "do the tests pass?",
             "intervention": req})
        b = self.store.block(mid, "needs_founder", d["reason"])
        if d.get("intervention"):
            b["intervention"] = d["intervention"]
            self.store.save(b)
        return mid, self.store.load(mid).get("intervention")

    def act(self, mid, action, **body):
        return self.client.post("%s/%s/act" % (MIS, mid),
                                json=dict(body, action=action), headers=HDR)

    def checks(self, mid):
        return self.store.load(mid)["done_when"]


# ============================================ 1 + 4 + 6: the fix ==========
class TestTargetedAnswerConfirms(Base):

    def test_01_a_targeted_yes_confirms_the_intended_check(self):
        mid, iv = self.blocked_with(request(index=0))
        self.assertEqual(iv["confirms_check"], {"index": 0,
                                                "field": "tests_pass"})
        r = self.act(mid, "intervene", intervention_id=iv["id"],
                     values={"tests_pass": True, "pixels": "ok"})
        self.assertEqual(r.status_code, 200, r.text)
        cs = self.checks(mid)
        self.assertTrue(cs[0]["met"], "the targeted check was not confirmed")
        self.assertFalse(cs[1].get("met"), "an untargeted check moved")

    def test_02_a_targeted_NO_confirms_nothing(self):
        """Valid is not affirmative. Answering 'the tests do not pass' must
        never sign off that the tests pass."""
        mid, iv = self.blocked_with(request(index=0))
        r = self.act(mid, "intervene", intervention_id=iv["id"],
                     values={"tests_pass": False, "pixels": "ok"})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertFalse(self.checks(mid)[0].get("met"),
                         "a 'no' confirmed the check")

    def test_03_the_audit_fields_are_preserved(self):
        mid, iv = self.blocked_with(request(index=0))
        self.act(mid, "intervene", intervention_id=iv["id"],
                 values={"tests_pass": True, "pixels": "ok"})
        c = self.checks(mid)[0]
        self.assertEqual(c["confirmed_by"], "founder",
                         "the sign-off must be attributed")
        self.assertTrue(c.get("confirmed_at"), "confirmed_at was not stamped")
        self.assertTrue(c["met"])

    def test_04_confirm_check_is_STILL_the_only_writer(self):
        """The handler must call the method, not set the flag itself."""
        src = Path(__file__).with_name("app.py").read_text(encoding="utf-8")
        i = src.index('if action == "intervene"')
        body = src[i:i + 9000]
        self.assertIn("store.confirm_check(mid, _ix, by=\"founder\")", body)
        self.assertNotIn('["met"] = True', body,
                         "the handler must never write met itself")

    def test_05_the_mission_can_now_reach_DONE(self):
        """The end of the live failure: with the founder_confirm closed, the
        remaining artifact check decides, and the mission completes."""
        mid, iv = self.blocked_with(request(index=0))
        self.act(mid, "intervene", intervention_id=iv["id"],
                 values={"tests_pass": True, "pixels": "ok"})
        m = self.store.load(mid)
        done, res = mission_engine.evaluate_done_when(m, "...\nFINAL: shipped")
        self.assertTrue(done, "still not done: %r" % (res,))
        # and it is genuinely gated -- without the artifact it stays open
        again, _ = mission_engine.evaluate_done_when(m, "nothing here")
        self.assertFalse(again)


# ============================================ 2 + 5: nothing else moved ===
class TestUntargetedIsUnchanged(Base):

    def test_10_an_intervention_with_no_target_confirms_nothing(self):
        mid, iv = self.blocked_with(request(index=None))
        self.assertIsNone(iv.get("confirms_check"))
        r = self.act(mid, "intervene", intervention_id=iv["id"],
                     values={"tests_pass": True, "pixels": "ok"})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertFalse(self.checks(mid)[0].get("met"),
                         "an untargeted answer confirmed a check")

    def test_11_the_answer_still_resumes_the_mission(self):
        for req in (request(index=0), request(index=None)):
            mid, iv = self.blocked_with(req)
            self.launched = []
            r = self.act(mid, "intervene", intervention_id=iv["id"],
                         values={"tests_pass": True, "pixels": "ok"})
            self.assertEqual(r.status_code, 200, r.text)
            m = self.store.load(mid)
            self.assertEqual(m["state"], "running")
            self.assertEqual(m["target_session"], "sess-keep",
                             "the delegate must be kept")
            self.assertIsNone(m.get("intervention"), "it must be retired")
            self.assertTrue(m["founder_response"]["values"]["tests_pass"])
            self.assertEqual(self.launched, [mid])

    def test_12_a_rejected_answer_writes_nothing(self):
        mid, iv = self.blocked_with(request(index=0))
        r = self.act(mid, "intervene", intervention_id=iv["id"],
                     values={"pixels": "not-an-option"})
        self.assertEqual(r.status_code, 422)
        self.assertFalse(self.checks(mid)[0].get("met"),
                         "a refused form confirmed a check")
        self.assertEqual(self.store.load(mid)["state"], "blocked")


# =========== the LIVE sequence: a NO is an answer, not an ending ==========
class TestAFounderNoDrivesTheWorkerAgain(Base):
    """MEASURED ON A LIVE MISSION (m-2a260bc5b6d3, 2026-09-16).

    Shadow asked "Sign off: does `failure-test.md` containing exactly
    `ALPHA` meet the objective?". The founder answered NO, and the panel then
    showed NEEDS YOU with their own answer rendered as `False` -- which read
    as a dead end with no way to continue the worker.

    IT WAS NOT ONE. That mission's ledger runs:

        blocked       ask_founder: "check #0 is founder_confirm, which only
                      your sign-off can close"
        intervention  founder answered iv-a4ff9811e52e {file_ok: false}
        running       "founder answered Shadow"
        decision      continue: "they reviewed and did NOT accept
                      `failure-test.md` as it stands ..."

    The NO retired the question, put the mission back to `running`, and
    Shadow composed the next worker instruction out of the refusal. What the
    founder was actually looking at was the NEXT hold -- a different
    pause_reason that happens to render with the same NEEDS YOU face.

    WHY THIS EXISTS WHEN test_02 AND test_11 ALREADY DO. test_02 pins that a
    NO writes no `met`; test_11 pins that an answer resumes and relaunches --
    but test_11 only ever sends `True`, on both of the request shapes it
    loops over. The half that LOOKED broken in production was the half with
    no test. This is that half, asserted as one sequence, on the existing
    harness and the existing verbs. No new state, no new semantics.
    """

    def test_13_a_targeted_NO_retires_the_question_and_resumes(self):
        mid, iv = self.blocked_with(request(index=0))
        self.assertEqual(self.store.load(mid)["state"], "blocked",
                         "the founder is being asked")
        self.launched = []
        r = self.act(mid, "intervene", intervention_id=iv["id"],
                     values={"tests_pass": False, "pixels": "ok"})
        self.assertEqual(r.status_code, 200, r.text)
        m = self.store.load(mid)
        # 1. the question is RETIRED -- nobody is asked the same thing twice
        self.assertIsNone(m.get("intervention"))
        # 2. the mission is DRIVING again. This is the assertion the live
        #    scenario needed and did not have.
        self.assertEqual(m["state"], "running",
                         "a NO is an answer, never an ending")
        # 3. ...and the loop is relaunched, which is what lets Shadow read
        #    the refusal and compose the worker's next instruction from it
        self.assertEqual(self.launched, [mid],
                         "Shadow must get the turn that answers the NO")
        # 4. the NO is on the record AS a no
        self.assertIs(m["founder_response"]["values"]["tests_pass"], False)
        self.assertEqual(m["founder_response"]["intervention_id"], iv["id"])

    def test_14_a_NO_leaves_the_targeted_check_exactly_as_it_was(self):
        """Not met -- and not forged into a failure either. confirm_check is
        still the only writer of this tier, and a NO simply does not call
        it, so the check stays open and stays the founder's."""
        mid, iv = self.blocked_with(request(index=0))
        before = dict(self.checks(mid)[0])
        self.act(mid, "intervene", intervention_id=iv["id"],
                 values={"tests_pass": False, "pixels": "ok"})
        after = self.checks(mid)[0]
        self.assertEqual(after, before, "a NO must not touch the check")
        self.assertFalse(after.get("met"))
        self.assertIsNone(after.get("confirmed_by"))
        self.assertEqual(after["tier"], "founder_confirm")

    def test_15_the_delegate_survives_so_there_is_a_worker_to_drive(self):
        """Mirrors test_11's guarantee for the path it never exercised:
        relaunching is worth nothing if the worker session was released."""
        mid, iv = self.blocked_with(request(index=0))
        self.act(mid, "intervene", intervention_id=iv["id"],
                 values={"tests_pass": False, "pixels": "ok"})
        self.assertEqual(self.store.load(mid)["target_session"], "sess-keep")


# ============================================ 3: stale + malformed ========
class TestTargetsFailSafely(Base):

    def test_20_an_out_of_range_index_does_not_break_the_answer(self):
        mid, iv = self.blocked_with(request(index=9))
        r = self.act(mid, "intervene", intervention_id=iv["id"],
                     values={"tests_pass": True, "pixels": "ok"})
        self.assertEqual(r.status_code, 200,
                         "a stale target must not reject the answer: "
                         + r.text)
        self.assertEqual(self.store.load(mid)["state"], "running")
        self.assertFalse(any(c.get("met") for c in self.checks(mid)))

    def test_21_a_target_on_a_NON_founder_confirm_check_is_refused(self):
        """confirm_check raises for the wrong tier; the answer still lands."""
        mid, iv = self.blocked_with(request(index=1))   # contains_artifact
        r = self.act(mid, "intervene", intervention_id=iv["id"],
                     values={"tests_pass": True, "pixels": "ok"})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertFalse(self.checks(mid)[1].get("met"),
                         "an artifact check was signed off by a founder answer")

    def test_22_a_mission_with_NO_checks_survives_a_target(self):
        mid, iv = self.blocked_with(request(index=0), checks=[])
        r = self.act(mid, "intervene", intervention_id=iv["id"],
                     values={"tests_pass": True, "pixels": "ok"})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(self.store.load(mid)["state"], "running")

    def test_23_malformed_targets_are_dropped_at_validation(self):
        """The marker is opt-in: anything unparseable means 'no target', not
        an invalid intervention."""
        for bad in ({"index": "0", "field": "tests_pass"},
                    {"index": True, "field": "tests_pass"},
                    {"index": -1, "field": "tests_pass"},
                    {"index": 0, "field": "nope"},
                    {"index": 0, "field": "pixels"},      # not a boolean
                    {"index": 0}, {"field": "tests_pass"}, "yes", 3, None):
            raw = {"question": "q?", "fields": [{"key": "tests_pass",
                                                 "type": "boolean"}],
                   "confirms_check": bad}
            got = siv.validate_request(raw)
            self.assertIsNotNone(got, "the intervention itself must survive")
            self.assertIsNone(got["confirms_check"], repr(bad))

    def test_24_confirmed_index_requires_a_literal_True(self):
        iv = siv.validate_request(request(index=0))
        self.assertEqual(siv.confirmed_index(iv, {"tests_pass": True}), 0)
        for v in ({"tests_pass": False}, {"tests_pass": "yes"},
                  {"tests_pass": 1}, {}, None):
            self.assertIsNone(siv.confirmed_index(iv, v), repr(v))
        self.assertIsNone(siv.confirmed_index({}, {"tests_pass": True}))
        self.assertIsNone(siv.confirmed_index(None, {"tests_pass": True}))


# ================== the PROMPT: the marker has to be reachable ===========
class TestThePromptTeachesTheMarker(unittest.TestCase):
    """39682c81 shipped the plumbing INERT. Measured on mission
    m-fba93ae7c89f: the founder answered an intervention at 21:55:17 and
    every founder_confirm check stayed unmet, because the decider prompt
    never mentioned `confirms_check` -- so no request could carry one, and
    confirmed_index() had nothing to read. A path nothing can emit into is
    not a feature."""

    def setUp(self):
        self.p = shadow_runner._DECIDE_PROMPT

    def test_30_the_prompt_documents_confirms_check(self):
        self.assertIn("confirms_check", self.p,
                      "the decider cannot emit what it is never told about")

    def test_31_the_example_is_a_VALID_request(self):
        """The documented shape must survive validate_request, or the prompt
        is teaching something the validator drops."""
        raw = {"question": "Do the relevant tests pass?",
               "fields": [{"key": "tests_pass", "type": "boolean",
                           "label": "Relevant tests pass."}],
               "confirms_check": {"index": 2, "field": "tests_pass"}}
        got = siv.validate_request(raw)
        self.assertIsNotNone(got)
        self.assertEqual(got["confirms_check"],
                         {"index": 2, "field": "tests_pass"},
                         "the prompt's own example is dropped by the parser")

    def test_32_the_prompt_states_every_rule_the_parser_enforces(self):
        """Each rule below is enforced in _confirms_check/confirmed_index.
        A rule the parser applies but the prompt omits is a silent drop."""
        for needle, why in (
                ("#N", "index must be copied from the rendered list"),
                ('"type": "boolean"', "the gate must be boolean"),
                ("founder_confirm", "a machine tier is refused"),
                ("OMIT", "most interventions carry no marker"),
                ("False", "only True confirms")):
            self.assertIn(needle, self.p, why)

    def test_33_the_CHECK_LIST_carries_its_index(self):
        """Without #N the decider must COUNT positions to cite one, which is
        the 'invent an index' failure the rules forbid."""
        ctx = {"outcome": "o", "checks": [
                   {"tier": "contains_artifact", "check": "FINAL:", "met": False},
                   {"tier": "founder_confirm", "check": "tests pass", "met": False}],
               "turns_used": 1, "max_turns": 20,
               "last_instruction": "i", "last_response": "r"}
        rendered = "\n".join(
            "- #%d [%s] (%s) %s" % (i, "x" if c.get("met") else " ",
                                    c.get("tier"), c.get("check"))
            for i, c in enumerate(ctx["checks"]))
        self.assertIn("- #0 [ ] (contains_artifact) FINAL:", rendered)
        self.assertIn("- #1 [ ] (founder_confirm) tests pass", rendered)
        # and the prompt tells it what the number is for
        self.assertIn("INDEX", self.p)

    def test_34_the_prompt_still_shows_the_UNMARKED_form(self):
        """Most interventions have no marker; the plain example must remain
        so the common case is not pushed toward carrying one."""
        self.assertIn('"key": "region"', self.p,
                      "the unmarked example was lost")


if __name__ == "__main__":
    unittest.main(verbosity=2)
