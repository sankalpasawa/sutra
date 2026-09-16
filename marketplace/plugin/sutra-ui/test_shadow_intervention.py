"""Founder interventions: one typed question, one generic answer.

WHAT IS ASSERTED, in the priority order the work was done in:

  1. NOTHING EXISTING MOVED. ask_founder without an intervention still
     returns exactly what it always returned, confirm_check still works, and
     a mission that never sees an intervention is byte-identical.
  2. The request schema validates (and refuses what it cannot ask).
  3. Every answerable field type validates its value.
  4. The /act route answers, retires, resumes -- on the SAME delegate.
  5. Stale and duplicate submissions are safe.

Run: .venv/bin/python -m unittest test_shadow_intervention -v
"""
import json
import os
import tempfile
import unittest
from pathlib import Path

os.environ["SUTRA_SHADOW_HOME"] = tempfile.mkdtemp(prefix="shadow-iv-")

from fastapi.testclient import TestClient  # noqa: E402

import app as app_module  # noqa: E402
import mission_engine  # noqa: E402
import providers  # noqa: E402
import shadow_feed  # noqa: E402
import shadow_intervention as siv  # noqa: E402
import shadow_runner  # noqa: E402
from mission_engine import MissionStore  # noqa: E402

HDR = {"X-Sutra-Panel": app_module.PANEL_TOKEN,
       "Origin": "http://127.0.0.1:8330"}
MIS = "/api/shadow/missions"


def field(key="region", ftype="choice", **kw):
    f = {"key": key, "type": ftype, "label": key}
    if ftype in ("choice", "multi_choice", "ranking"):
        f["options"] = [{"value": "a", "label": "A"},
                        {"value": "b", "label": "B"}]
    f.update(kw)
    return f


_OMITTED = object()


def request(fields=_OMITTED, **kw):
    """`fields=[]` must mean an EMPTY form, not an omitted argument -- the
    empty case is one of the things under test."""
    r = {"question": "Which region?", "context": "two configs disagree",
         "fields": [field()] if fields is _OMITTED else fields}
    r.update(kw)
    return r


# =====================================================  1. NOTHING MOVED  ==
class ExistingDecisionBehaviourIsUnchanged(unittest.TestCase):
    """The validator was extended, not replaced."""

    def test_ask_founder_without_an_intervention_is_byte_identical(self):
        got = mission_engine.validate_decision(
            {"action": "ask_founder", "reason": "I need the founder"})
        self.assertEqual(got, {"action": "ask_founder",
                               "reason": "I need the founder",
                               "instruction": ""},
                         "a prose-only ask_founder must not gain a key")
        self.assertNotIn("intervention", got)

    def test_continue_is_untouched(self):
        got = mission_engine.validate_decision(
            {"action": "continue", "instruction": "do the thing"})
        self.assertEqual(got, {"action": "continue", "reason": "",
                               "instruction": "do the thing"})

    def test_a_malformed_intervention_degrades_to_prose(self):
        """The founder still gets asked; they just do not get a form."""
        got = mission_engine.validate_decision(
            {"action": "ask_founder", "reason": "help",
             "intervention": {"question": "", "fields": []}})
        self.assertNotIn("intervention", got)
        self.assertEqual(got["action"], "ask_founder")

    def test_an_intervention_survives_validation(self):
        got = mission_engine.validate_decision(
            {"action": "ask_founder", "reason": "help",
             "intervention": request()})
        self.assertIn("intervention", got)
        self.assertEqual(got["intervention"]["fields"][0]["key"], "region")
        self.assertTrue(got["intervention"]["id"].startswith("iv-"))

    def test_the_action_vocabulary_did_not_grow(self):
        self.assertEqual(mission_engine.DECISION_ACTIONS,
                         ("continue", "ask_founder"))

    def test_no_new_mission_state(self):
        for s in ("draft", "brief_confirm", "running", "queued", "paused",
                  "blocked", "done", "failed", "stopped"):
            self.assertIn(s, mission_engine.STATES)
        self.assertEqual(len(mission_engine.STATES), 9)

    def test_the_feed_contract_gained_exactly_one_optional_field(self):
        self.assertIn("intervention_id", shadow_feed.OPTIONAL)
        self.assertEqual(shadow_feed.REQUIRED,
                         ("item_id", "producer", "kind", "title", "deep_link",
                          "dedupe_key", "state"))


# =====================================================  2. REQUEST SCHEMA ==
class TheRequestSchema(unittest.TestCase):
    def test_a_good_request_normalises(self):
        r = siv.validate_request(request())
        self.assertEqual(r["schema_version"], siv.SCHEMA_VERSION)
        self.assertEqual(r["submit_label"], "Send to Shadow")
        self.assertEqual(len(r["fields"]), 1)

    def test_a_question_is_mandatory(self):
        self.assertIsNone(siv.validate_request(request(question="")))

    def test_at_least_one_field_is_mandatory(self):
        self.assertIsNone(siv.validate_request(request(fields=[])))

    def test_a_bad_key_invalidates_the_form(self):
        self.assertIsNone(siv.validate_request(
            request(fields=[field(key="Not A Key")])))

    def test_duplicate_keys_invalidate_the_form(self):
        self.assertIsNone(siv.validate_request(
            request(fields=[field(key="a"), field(key="a")])))

    def test_an_unknown_type_invalidates_the_form(self):
        self.assertIsNone(siv.validate_request(
            request(fields=[field(ftype="hologram")])))

    def test_a_DEFERRED_type_is_refused_not_silently_accepted(self):
        """A form the founder cannot complete would block a mission with no
        way out -- worse than Shadow asking in prose."""
        for t in siv.DEFERRED_FIELD_TYPES:
            self.assertIsNone(siv.validate_request(
                request(fields=[field(ftype=t)])), t)

    def test_a_choice_needs_at_least_two_options(self):
        self.assertIsNone(siv.validate_request(
            request(fields=[field(options=[{"value": "only"}])])))

    def test_evidence_is_carried_and_bounded(self):
        r = siv.validate_request(request(evidence=[
            {"kind": "quote", "ref": "cfg.yaml:14", "text": "region: eu"},
            "a plain note"]))
        self.assertEqual(len(r["evidence"]), 2)
        self.assertEqual(r["evidence"][1]["kind"], "note")

    def test_the_type_vocabulary_is_the_extension_point(self):
        self.assertEqual(set(siv.FIELD_TYPES), set(siv.ACTIVE_FIELD_TYPES))
        self.assertEqual(len(siv.ACTIVE_FIELD_TYPES), 13)


# =======================================================  3. FIELD TYPES  ==
class EveryAnswerableType(unittest.TestCase):
    def ok(self, ftype, value, expect, **kw):
        r = siv.validate_request(request(fields=[field("f", ftype, **kw)]))
        clean, errors = siv.validate_values(r, {"f": value})
        self.assertEqual(errors, {}, "%s rejected %r" % (ftype, value))
        self.assertEqual(clean["f"], expect)

    def bad(self, ftype, value, **kw):
        r = siv.validate_request(request(fields=[field("f", ftype, **kw)]))
        _clean, errors = siv.validate_values(r, {"f": value})
        self.assertIn("f", errors, "%s accepted %r" % (ftype, value))

    def test_boolean(self):
        self.ok("boolean", True, True)
        self.ok("boolean", "yes", True)
        self.ok("boolean", "no", False)
        self.bad("boolean", "perhaps")

    def test_boolean_as_approval(self):
        self.ok("boolean", True, True, constraints={"must_be_true": True})
        self.bad("boolean", False, constraints={"must_be_true": True})

    def test_choice(self):
        self.ok("choice", "a", "a")
        self.bad("choice", "z")

    def test_multi_choice(self):
        self.ok("multi_choice", ["a", "b"], ["a", "b"])
        self.ok("multi_choice", ["a", "a"], ["a"])          # deduped
        self.bad("multi_choice", ["a", "z"])
        self.bad("multi_choice", ["a"], constraints={"min_select": 2})
        self.bad("multi_choice", ["a", "b"], constraints={"max_select": 1})

    def test_text(self):
        self.ok("text", "  hello ", "hello")
        self.bad("text", "x" * 600)
        self.bad("text", "ab", constraints={"min_len": 3})
        self.ok("text", "AB12", "AB12", constraints={"pattern": r"[A-Z]{2}\d{2}"})
        self.bad("text", "nope", constraints={"pattern": r"[A-Z]{2}\d{2}"})

    def test_long_text(self):
        self.ok("long_text", "x" * 5000, "x" * 5000)
        self.bad("long_text", "x" * 20001)

    def test_number(self):
        self.ok("number", 42, 42)
        self.ok("number", "42", 42)
        self.ok("number", "3.5", 3.5)
        self.bad("number", "not a number")
        self.bad("number", True)                            # bool is not a number
        self.bad("number", 5, constraints={"min": 10})
        self.bad("number", 50, constraints={"max": 10})

    def test_currency(self):
        self.ok("currency", "1200.5", 1200.5,
                constraints={"currency_code": "USD"})
        self.ok("currency", "1200.456", 1200.46, constraints={"decimals": 2})
        self.bad("currency", "free")

    def test_percent(self):
        self.ok("percent", 25, 25)
        self.bad("percent", 120)                            # implicit 0..100
        self.bad("percent", -1)

    def test_date(self):
        self.ok("date", "2026-09-14", "2026-09-14")
        self.bad("date", "14/09/2026")

    def test_datetime(self):
        self.ok("datetime", "2026-09-14T10:30", "2026-09-14T10:30")
        self.ok("datetime", "2026-09-14T10:30:00Z", "2026-09-14T10:30:00+00:00")
        self.bad("datetime", "tomorrow")

    def test_url(self):
        self.ok("url", "https://example.com/x", "https://example.com/x")
        self.bad("url", "example.com")
        self.bad("url", "javascript:alert(1)")

    def test_email(self):
        self.ok("email", "a@b.co", "a@b.co")
        self.bad("email", "a@b")

    def test_ranking(self):
        self.ok("ranking", ["b", "a"], ["b", "a"])
        self.bad("ranking", ["a"])                          # must rank all
        self.bad("ranking", ["a", "z"])

    def test_required_and_optional(self):
        r = siv.validate_request(request(fields=[
            field("must", "text", required=True),
            field("may", "text", required=False)]))
        _c, errors = siv.validate_values(r, {})
        self.assertIn("must", errors)
        self.assertNotIn("may", errors)
        clean, errors = siv.validate_values(r, {"must": "here"})
        self.assertEqual(errors, {})
        self.assertEqual(clean, {"must": "here"})

    def test_a_default_fills_an_omitted_field(self):
        r = siv.validate_request(request(fields=[
            field("f", "text", default="fallback")]))
        clean, _e = siv.validate_values(r, {})
        self.assertEqual(clean["f"], "fallback")

    def test_many_fields_are_one_response(self):
        r = siv.validate_request(request(fields=[
            field("region", "choice"),
            field("cap", "currency"),
            field("when", "date"),
            field("agree", "boolean", constraints={"must_be_true": True})]))
        clean, errors = siv.validate_values(r, {
            "region": "a", "cap": "500", "when": "2026-10-01", "agree": True})
        self.assertEqual(errors, {})
        self.assertEqual(len(clean), 4)

    def test_an_unknown_submitted_key_is_ignored_not_fatal(self):
        r = siv.validate_request(request())
        clean, errors = siv.validate_values(r, {"region": "a", "ghost": 1})
        self.assertEqual(errors, {})
        self.assertNotIn("ghost", clean)


# ==========================================================  4/5. THE API ==
class Base(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app_module.app, base_url="http://127.0.0.1")

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        os.environ["SUTRA_SHADOW_HOME"] = self.tmp.name
        self._orig = providers.SETTINGS_PATH
        self.settings = Path(self.tmp.name) / "settings.json"
        self.settings.write_text(json.dumps({"shadow.enabled": True}))
        providers.SETTINGS_PATH = self.settings
        self.store = MissionStore()
        self.launched = []
        self._real_launch = shadow_runner._launch
        shadow_runner._launch = lambda mid, *a, **k: self.launched.append(mid)

    def tearDown(self):
        shadow_runner._launch = self._real_launch
        providers.SETTINGS_PATH = self._orig
        self.tmp.cleanup()

    def blocked_with(self, req=None):
        """A mission exactly as ask_founder leaves it."""
        m = self.store.create("ship it", "fix", target_mode="new",
                              target_session="sess-keep", done_when=[])
        mid = m["id"]
        self.store.transition(mid, "brief_confirm", "proposed")
        self.store.transition(mid, "running", "admitted")
        eng = mission_engine.MissionEngine(self.store, None, None, None)
        decision = mission_engine.validate_decision(
            {"action": "ask_founder", "reason": "which region?",
             "intervention": req or request()})
        blocked = self.store.block(mid, "needs_founder", decision["reason"])
        if decision.get("intervention"):
            blocked["intervention"] = decision["intervention"]
            self.store.save(blocked)
        del eng
        return mid, self.store.load(mid).get("intervention")

    def act(self, mid, action, **body):
        return self.client.post("%s/%s/act" % (MIS, mid),
                                json=dict(body, action=action), headers=HDR)


class TheInterveneAction(Base):
    def test_a_valid_answer_resumes_the_mission(self):
        mid, iv = self.blocked_with()
        r = self.act(mid, "intervene", intervention_id=iv["id"],
                     values={"region": "a"})
        self.assertEqual(r.status_code, 200, r.text)
        m = self.store.load(mid)
        self.assertEqual(m["state"], "running")

    def test_the_SAME_delegate_continues(self):
        mid, iv = self.blocked_with()
        before = self.store.load(mid)["target_session"]
        self.act(mid, "intervene", intervention_id=iv["id"],
                 values={"region": "a"})
        after = self.store.load(mid)
        self.assertEqual(after["target_session"], before,
                         "answering must not respawn a worker")
        self.assertEqual(self.launched, [mid],
                         "the EXISTING launch path drives the same session")

    def test_the_intervention_is_retired(self):
        mid, iv = self.blocked_with()
        self.act(mid, "intervene", intervention_id=iv["id"],
                 values={"region": "a"})
        self.assertIsNone(self.store.load(mid).get("intervention"))

    def test_the_response_is_persisted(self):
        mid, iv = self.blocked_with()
        self.act(mid, "intervene", intervention_id=iv["id"],
                 values={"region": "a"})
        fr = self.store.load(mid)["founder_response"]
        self.assertEqual(fr["intervention_id"], iv["id"])
        self.assertEqual(fr["values"], {"region": "a"})
        self.assertTrue(fr["summary"])

    def test_the_answer_reaches_shadows_NEXT_decision_context(self):
        mid, iv = self.blocked_with()
        self.act(mid, "intervene", intervention_id=iv["id"],
                 values={"region": "a"})
        eng = mission_engine.MissionEngine(self.store, None, None, None)
        ctx = eng._decision_context(self.store.load(mid), "worker said stuff")
        self.assertIn("founder_response", ctx)
        self.assertEqual(ctx["founder_response"]["values"], {"region": "a"})
        self.assertNotIn("region", ctx["last_response"],
                         "the answer must not be folded into worker output")

    def test_a_mission_with_no_answer_has_no_such_key(self):
        mid, _iv = self.blocked_with()
        eng = mission_engine.MissionEngine(self.store, None, None, None)
        ctx = eng._decision_context(self.store.load(mid), "")
        self.assertNotIn("founder_response", ctx)

    def test_invalid_values_leave_the_mission_blocked(self):
        mid, iv = self.blocked_with()
        r = self.act(mid, "intervene", intervention_id=iv["id"],
                     values={"region": "nonsense"})
        self.assertEqual(r.status_code, 422, r.text)
        self.assertIn("region", r.json()["detail"]["errors"])
        m = self.store.load(mid)
        self.assertEqual(m["state"], "blocked")
        self.assertIsNotNone(m.get("intervention"))
        self.assertEqual(self.launched, [], "nothing may be launched")

    def test_missing_required_values_leave_the_mission_blocked(self):
        mid, iv = self.blocked_with(
            request(fields=[field("f", "text", required=True)]))
        r = self.act(mid, "intervene", intervention_id=iv["id"], values={})
        self.assertEqual(r.status_code, 422)
        self.assertEqual(self.store.load(mid)["state"], "blocked")

    def test_a_STALE_id_is_refused(self):
        mid, iv = self.blocked_with()
        r = self.act(mid, "intervene", intervention_id="iv-somethingelse",
                     values={"region": "a"})
        self.assertEqual(r.status_code, 409, r.text)
        self.assertEqual(self.store.load(mid)["state"], "blocked",
                         "a late answer must never satisfy a newer question")

    def test_a_DUPLICATE_submission_is_a_safe_no_op(self):
        mid, iv = self.blocked_with()
        first = self.act(mid, "intervene", intervention_id=iv["id"],
                         values={"region": "a"})
        self.assertEqual(first.status_code, 200)
        second = self.act(mid, "intervene", intervention_id=iv["id"],
                          values={"region": "b"})
        self.assertEqual(second.status_code, 200, second.text)
        self.assertEqual(self.store.load(mid)["founder_response"]["values"],
                         {"region": "a"},
                         "the second press must not overwrite the answer")
        self.assertEqual(self.launched, [mid], "and must not relaunch")

    def test_answering_a_mission_with_no_intervention_is_refused(self):
        m = self.store.create("plain", "fix", target_mode="new", done_when=[])
        self.store.transition(m["id"], "brief_confirm", "proposed")
        r = self.act(m["id"], "intervene", intervention_id="iv-x", values={})
        self.assertEqual(r.status_code, 409)

    def test_an_unknown_mission_is_a_404(self):
        r = self.act("m-nope", "intervene", intervention_id="iv-x", values={})
        self.assertEqual(r.status_code, 404)


class ExistingFounderFlowsStillWork(Base):
    def test_confirm_check_is_untouched(self):
        m = self.store.create("x", "fix", target_mode="new", done_when=[
            {"tier": "founder_confirm", "check": "the memo reads well"}])
        mid = m["id"]
        self.store.transition(mid, "brief_confirm", "proposed")
        got = self.store.confirm_check(mid, 0)
        self.assertTrue(got["done_when"][0]["met"])
        self.assertEqual(got["done_when"][0]["confirmed_by"], "founder")

    def test_a_prose_only_ask_founder_still_blocks_with_no_form(self):
        m = self.store.create("y", "fix", target_mode="new", done_when=[])
        mid = m["id"]
        self.store.transition(mid, "brief_confirm", "proposed")
        self.store.transition(mid, "running", "admitted")
        blocked = self.store.block(mid, "needs_founder", "I need you")
        self.assertEqual(blocked["state"], "blocked")
        self.assertEqual(blocked["block_reason"], "needs_founder")
        self.assertIsNone(blocked.get("intervention"))

    def test_resume_still_works_on_a_blocked_mission(self):
        mid, _iv = self.blocked_with()
        r = self.act(mid, "resume")
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(self.store.load(mid)["state"], "running")


# ==========================================  6. WHAT THE DECIDER IS TOLD  ==
class TheDeciderPrompt(unittest.TestCase):
    """The prompt is documentation the model acts on, so it is tested like
    code: the example it shows must actually validate."""

    def _examples(self):
        import re
        return re.findall(r"```json\s*\n(.*?)```",
                          shadow_runner._DECIDE_PROMPT, re.S)

    def test_the_example_payload_the_prompt_shows_actually_validates(self):
        """The drift guard. If someone edits the prompt's example into
        something validate_decision would reject, this fails."""
        found = None
        for block in self._examples():
            if '"intervention"' in block:
                found = json.loads(block)
                break
        self.assertIsNotNone(found, "the prompt must show an intervention")
        got = mission_engine.validate_decision(found)
        self.assertIn("intervention", got,
                      "the documented payload must survive validation")
        self.assertEqual(got["intervention"]["fields"][0]["type"], "choice")
        self.assertEqual(len(got["intervention"]["fields"][0]["options"]), 2)

    def test_every_other_example_still_validates(self):
        """...EXCEPT the placeholder instruction, which is now refused on
        purpose (a9910db8). A live decider answered with this very block --
        instruction "<what to send into the chat next>" -- and the runner
        said the placeholder INTO the delegate chat twice, tripping the
        ping-pong guard one second after a restart had rescued the mission.
        So the prompt still SHOWS the shape, and validate_decision still
        refuses the shape when it comes back as an answer. Every other
        example must keep validating, which is what this walks."""
        placeholders = 0
        for block in self._examples():
            raw = json.loads(block)
            got = mission_engine.validate_decision(raw)
            if mission_engine._is_template_echo(raw.get("instruction") or ""):
                placeholders += 1
                self.assertIsNone(
                    got, "the prompt's own placeholder must not validate as "
                         "a decision: %r" % (raw,))
                continue
            self.assertIsNotNone(got,
                                 "prompt example is not a valid decision: %r"
                                 % (raw,))
        self.assertTrue(placeholders,
                        "the prompt should still SHOW the continue example")

    def test_the_prompt_names_every_answerable_type(self):
        for t in siv.ACTIVE_FIELD_TYPES:
            self.assertIn(t, shadow_runner._DECIDE_PROMPT,
                          "the decider cannot use a type it is not told about")

    def test_the_prompt_says_to_try_first_and_ask_small(self):
        p = shadow_runner._DECIDE_PROMPT
        self.assertIn("resolve it YOURSELF first", p)
        self.assertIn("SMALLEST question", p)
        self.assertIn("comes back to YOU, not to the chat", p)

    def test_the_intervention_key_is_documented_as_optional(self):
        self.assertIn("OPTIONAL", shadow_runner._DECIDE_PROMPT)

    def test_the_existing_two_actions_are_still_the_only_ones_offered(self):
        p = shadow_runner._DECIDE_PROMPT
        self.assertIn('"action": "continue"', p)
        self.assertIn('"action": "ask_founder"', p)
        for absent in ("undecided", "stop", "done"):
            self.assertNotIn('"action": "%s"' % absent, p)


class TheAnswerReachesTheDecider(unittest.TestCase):
    """_decision_context carries it; the prompt has to render it."""

    def test_the_prompt_renders_without_an_answer(self):
        """Every mission that was never asked anything -- the KeyError case."""
        self.assertEqual(shadow_runner._founder_answer_text(None), "(none)")
        self.assertEqual(shadow_runner._founder_answer_text({}), "(none)")

    def test_the_answer_renders_as_labelled_lines(self):
        text = shadow_runner._founder_answer_text({
            "question": "Which region?",
            "summary": [{"key": "region", "label": "Default region",
                         "value": "eu-west-1"},
                        {"key": "cap", "label": "Budget cap", "value": "500"}]})
        self.assertIn("You asked: Which region?", text)
        self.assertIn("- Default region: eu-west-1", text)
        self.assertIn("- Budget cap: 500", text)

    def test_a_malformed_answer_degrades_to_none(self):
        for bad in ("a string", 7, {"summary": "not a list"},
                    {"summary": ["not a dict"]}):
            self.assertEqual(shadow_runner._founder_answer_text(bad), "(none)")

    def test_the_prompt_template_has_a_slot_for_it(self):
        self.assertIn("%(founder_response)s", shadow_runner._DECIDE_PROMPT)
        self.assertIn("WHAT THE FOUNDER TOLD YOU",
                      shadow_runner._DECIDE_PROMPT)

    def test_the_template_formats_with_a_context_that_has_no_answer(self):
        """The substitution dict must not KeyError on an old-shaped context."""
        ctx = {"outcome": "x", "checks": [], "turns_used": 1, "max_turns": 20,
               "last_instruction": "go", "last_response": "ok"}
        # Through the ONE renderer (v4: render_decide_prompt is what both the
        # one-shot decider and a task chat send), so a slot added to the
        # template later can never KeyError this test again.
        rendered = shadow_runner.render_decide_prompt(ctx)
        self.assertIn("(none)", rendered)
        self.assertIn("WHAT THE FOUNDER TOLD YOU", rendered)


if __name__ == "__main__":
    unittest.main()
