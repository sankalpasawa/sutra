#!/usr/bin/env python3
"""END TO END: a real intervention payload reaches the browser quoting its check.

WHAT THE UNIT SUITES CANNOT SEE. test_shadow_intervention_ui.js builds its own
`intervention` objects, so it proves the renderer is self-consistent -- not
that the renderer agrees with the server. A field the validator renames, a
`confirms_check` the store drops on save, a tier the wire spells differently:
every one of those passes the node suite and paints nothing in the app.

So this test never writes an intervention by hand. It goes:

    validate_decision  ->  MissionStore.block/save  ->  GET /api/shadow/missions
        ->  qa/shadow-signs-render.js (the SHIPPED renderer)  ->  assert

and then answers the question through the real POST /act, re-reads the record,
and renders it again -- so the whole loop the founder actually walks is
exercised, not the half of it before the click.

Run: ./run-tests.sh test_shadow_signs_e2e.py
"""

import json
import os
import subprocess
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

HERE = Path(__file__).resolve().parent
DRIVER = HERE / "qa" / "shadow-signs-render.js"
MIS = "/api/shadow/missions"
HDR = {"host": "127.0.0.1"}

#: the exact check the live failure (m-cd009367d41a) died on
CHECK = "Relevant tests pass."
CHECKS = [{"tier": "contains_artifact", "check": "FINAL:"},
          {"tier": "founder_confirm", "check": CHECK}]

REQUEST = {
    "question": "Do you accept the test evidence as passing?",
    "fields": [{"key": "tests_pass", "type": "boolean",
                "label": "Do the tests pass?"},
               {"key": "pixels", "type": "choice", "label": "Pixels?",
                "options": [{"value": "ok", "label": "fine"},
                            {"value": "look", "label": "look in a browser"}]}],
    "confirms_check": {"index": 1, "field": "tests_pass"},
}


def node_missing():
    try:
        subprocess.run(["node", "--version"], capture_output=True, check=True)
    except Exception:
        return True
    return False


@unittest.skipIf(node_missing(), "node is not on PATH")
class TestSignsEndToEnd(unittest.TestCase):

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
        # the delegate must not really be spawned; the record is the subject
        self._real_launch = shadow_runner._launch
        shadow_runner._launch = lambda mid, *a, **k: None

    def tearDown(self):
        shadow_runner._launch = self._real_launch
        providers.SETTINGS_PATH = self._orig
        os.environ.pop("SUTRA_SHADOW_HOME", None)
        self.tmp.cleanup()

    # ------------------------------------------------------------ helpers --
    def blocked(self, request, checks=None):
        """A mission blocked on a REAL validated intervention."""
        m = self.store.create("ship it", "fix", target_mode="new",
                              target_session="sess-keep",
                              done_when=json.loads(json.dumps(
                                  CHECKS if checks is None else checks)))
        mid = m["id"]
        self.store.transition(mid, "brief_confirm", "proposed")
        self.store.transition(mid, "running", "admitted")
        d = mission_engine.validate_decision(
            {"action": "ask_founder", "reason": "do the tests pass?",
             "intervention": json.loads(json.dumps(request))})
        self.assertIsNotNone(d, "the decider refused its own example")
        b = self.store.block(mid, "needs_founder", d["reason"])
        if d.get("intervention"):
            b["intervention"] = d["intervention"]
            self.store.save(b)
        return mid

    def wire(self, mid):
        """The record EXACTLY as the panel receives it, over HTTP."""
        r = self.client.get(MIS, headers=HDR)
        self.assertEqual(r.status_code, 200, r.text)
        body = r.json()
        rows = body if isinstance(body, list) else body.get("missions", [])
        for row in rows:
            if row.get("id") == mid:
                return row
        self.fail("mission %s not in %s" % (mid, MIS))

    def render(self, record):
        """The SHIPPED renderer, over that record."""
        f = Path(self.tmp.name) / "mission.json"
        f.write_text(json.dumps(record))
        p = subprocess.run(["node", str(DRIVER), str(f)],
                           capture_output=True, text=True)
        self.assertEqual(p.returncode, 0, p.stderr)
        return p.stdout

    def form(self, html):
        """The intervention form alone -- the card's flat 'done when' row
        prints every check, so a whole-card search cannot tell the new row
        apart from that summary."""
        i = html.find('<div class="shiv" ')
        j = html.find("data-shivsend")
        self.assertNotEqual(i, -1, "no intervention form was rendered")
        return html[i:j]

    # -------------------------------------------------------------- tests --
    def test_01_the_real_payload_carries_the_target_over_the_wire(self):
        """Before any rendering: the server really does ship confirms_check."""
        iv = self.wire(self.blocked(REQUEST)).get("intervention")
        self.assertIsNotNone(iv, "the panel never saw an intervention")
        self.assertEqual(iv.get("confirms_check"),
                         {"index": 1, "field": "tests_pass"})

    def test_02_the_browser_never_shows_the_check(self):
        """REVERSED 2026-09-23. This asserted the opposite: that the literal
        criterion reached the browser, quoted, under a "Yes signs off" row.
        The founder's ruling -- "Remove the YES SIGNS OFF line and the
        internal acceptance criterion entirely" -- makes that the bug.

        The BINDING is untested here and untouched: test_05 below still
        drives the whole loop and still asserts the answer moves the check.
        What this pins now is that the founder is not shown the bookkeeping
        on the way."""
        html = self.render(self.wire(self.blocked(REQUEST)))
        form = self.form(html)
        self.assertNotIn("shivsigns", form, "the sign-off row is gone")
        self.assertNotIn("Yes signs off", form, "and its label with it")
        self.assertNotIn(CHECK, form,
                         "the internal criterion never reaches the browser")
        self.assertIn("Do the tests pass?", form,
                      "while the question the founder must answer stands")

    def test_03_an_untargeted_intervention_renders_the_old_form(self):
        req = dict(REQUEST)
        req.pop("confirms_check")
        form = self.form(self.render(self.wire(self.blocked(req))))
        self.assertNotIn("shivsigns", form, "a row appeared with no target")
        self.assertNotIn(CHECK, form, "and quoted a check it was not given")
        self.assertIn("Do the tests pass?", form, "the form still renders")

    def test_04_a_stale_target_paints_nothing_and_still_answers(self):
        """The server fails safe on a moved index; the card must not promise
        a sign-off that confirm_check will decline to write."""
        req = dict(REQUEST, confirms_check={"index": 9, "field": "tests_pass"})
        mid = self.blocked(req)
        self.assertNotIn("shivsigns", self.form(self.render(self.wire(mid))))
        iv = self.wire(mid)["intervention"]
        r = self.client.post("%s/%s/act" % (MIS, mid), headers=HDR,
                             json={"action": "intervene",
                                   "intervention_id": iv["id"],
                                   "values": {"tests_pass": True,
                                              "pixels": "ok"}})
        self.assertEqual(r.status_code, 200,
                         "a stale target must not reject the answer: " + r.text)

    def test_05_answering_YES_closes_the_check_behind_the_question(self):
        """The whole loop, which is the part that matters: answer the
        question, and the check bound to it moves. The form no longer quotes
        that check (2026-09-23) -- so what is asserted before the answer is
        that the QUESTION is there to answer, not the bookkeeping."""
        mid = self.blocked(REQUEST)
        self.assertIn("Do the tests pass?",
                      self.form(self.render(self.wire(mid))))
        iv = self.wire(mid)["intervention"]
        r = self.client.post("%s/%s/act" % (MIS, mid), headers=HDR,
                             json={"action": "intervene",
                                   "intervention_id": iv["id"],
                                   "values": {"tests_pass": True,
                                              "pixels": "ok"}})
        self.assertEqual(r.status_code, 200, r.text)
        after = self.wire(mid)
        self.assertTrue(after["done_when"][1].get("met"),
                        "the quoted check did not close")
        self.assertEqual(after["done_when"][1].get("confirmed_by"), "founder")
        self.assertFalse(after["done_when"][0].get("met"),
                         "an untargeted check moved")
        # and the form is gone from the card, because the question is answered
        html = self.render(after)
        self.assertNotIn("shivsigns", html, "the answered form still paints")
        self.assertIsNone(after.get("intervention"), "it must be retired")

    def test_06_a_NO_leaves_the_quoted_check_open(self):
        """Valid is not affirmative -- the row says 'Yes signs off' and only
        a yes may."""
        mid = self.blocked(REQUEST)
        iv = self.wire(mid)["intervention"]
        r = self.client.post("%s/%s/act" % (MIS, mid), headers=HDR,
                             json={"action": "intervene",
                                   "intervention_id": iv["id"],
                                   "values": {"tests_pass": False,
                                              "pixels": "ok"}})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertFalse(self.wire(mid)["done_when"][1].get("met"),
                         "a 'no' signed off the check the row promised a "
                         "'yes' would")


if __name__ == "__main__":
    unittest.main(verbosity=2)
