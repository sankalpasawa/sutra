"""test_layer_journey_j4.py -- J4, a rule, run end to end with a stubbed model (PRD amendment A3.7.4).

TestJ4Walks has the walk: a directive becomes a rule on the owner's stamp, reaches every agent's card, is read against every
page, and a build that breaks it is sent back twice and never goes live (steps 1 to 6). It reads only what the words wrote after
a mark taken before them, asserts journeys.walk.follows returns [], and shows the walk is not vacuous: a changed bind of any
step makes it fail, naming that step. TestJ4Edges holds the edge the row tests lacked: a rule the department already has (J4.1).

The classes subclass test_engine_runtime.Base (imported by name, so no other test class is collected twice) and so reuse its
scripted Model, `live()`, `ask()`, `stamp()`, `idle()` and `rows()`.
"""
import copy
import importlib

import journeys
from journeys import walk
from test_engine_runtime import REF, Base


def journey(jid):
    """The journey as the files hold it now (a fresh load: the journeys folder is data, and tests do not cache it)."""
    return journeys.load()[jid]


def copy_rules(rules):
    return [dict(r) for r in rules]


class Ruling(Base):
    """What a rule scenario needs beyond the runtime's Base: a mark before the words, the trace of what they wrote since, and
    the walk asserted."""

    def mark(self, *refs):
        """How much each department's record holds now: its board, its step rows and its ledger."""
        J = importlib.import_module("j2_runtime")
        return {ref: (len(self.R.board(ref)), len(self.R.step_rows(ref)), len(J.events(ref))) for ref in refs}

    def trace_since(self, mark):
        """The trace (journeys.walk.trace) of what was written after `mark`, the departments in the order the mark holds them."""
        J = importlib.import_module("j2_runtime")
        out = {"board": [], "steps": [], "events": [], "asks": []}
        for ref, (board, steps, events) in mark.items():
            got = walk.trace(self.W, self.R, J, ref)
            out["board"] += got["board"][board:]
            out["steps"] += got["steps"][steps:]
            out["events"] += got["events"][events:]
            out["asks"] += got["asks"]
        return out

    def assertFollowed(self, jid, mark, walks):
        """The journey was followed for the steps in `walks`, and the walk is not vacuous: a copy of the journey whose bind
        of a step is changed to something that never happened makes the walk fail, and the fault names that step."""
        j, trace = journey(jid), self.trace_since(mark)
        self.assertEqual(walk.follows(j, trace, walks=walks), [], "the journey %s was not followed" % jid)
        for n in walks:
            step = next(s for s in j["steps"] if s["n"] == n)
            bind = next((b for b in step.get("binds") or [] if b["kind"] in walk.TRACED and not b.get("optional")), None)
            if bind is None:
                continue
            broken = copy.deepcopy(j)
            mutated = next(s for s in broken["steps"] if s["n"] == n)
            for key in ("id", "action", "word"):
                if key in bind:
                    next(b for b in mutated["binds"] if b.get("kind") == bind["kind"] and b.get(key) == bind[key])[key] = "never-happened"
                    break
            faults = walk.follows(broken, trace, walks=[n])
            self.assertTrue(faults and ("step %s" % n) in faults[0], "a changed bind of step %s must fail the walk, and name it: %s" % (n, faults))

    def rule_asks(self, ref=REF):
        return [a for a in self.W.asks(ref) if a["kind"] == "rule"]


class TestJ4Walks(Ruling):
    def test_walk_a_rule_is_born_kept_read_and_enforced(self):
        """Steps 1 to 6: 'every page ends with: Call 108.' is restated and put back (1, 2), kept on the owner's stamp (3), shown to
        every agent's card (4), read against every page by Check (5), and a build that breaks it is sent back twice, never goes
        live, and the owner is told (6). The end of step 6 is a tell: M9.5 makes it an options ask (BL-4)."""
        W, R = self.W, self.R
        self.live()
        mark = self.mark(REF)
        # 1, 2: the directive is restated as one rule with a tag, and put back for the stamp
        self.ask("From now on, every page ends with: Call 108.")
        ask = self.rule_asks()[-1]
        self.assertEqual((ask["status"], ask["tag"], ask["line"]), ("pending", "always", "Every page ends with: Call 108."))
        self.assertTrue(ask["text"].startswith("A rule, as understood"), ask["text"])
        self.assertEqual(self.rows("identity.recognise")[-1]["answer"], "directive")
        self.assertNotIn(ask["line"], [r["line"] for r in W.dept(REF)["rules"]], "nothing is kept before the stamp")
        # 3: the stamp puts it on the record, with its id, tag and line, and the Brief says so
        self.stamp("rule")
        self.idle()
        kept = W.dept(REF)["rules"][-1]
        self.assertEqual((kept["tag"], kept["line"]), ("always", "Every page ends with: Call 108."))
        self.assertTrue(kept["id"], "a rule has an id")
        self.assertIn("A rule, from now on: Every page ends with: Call 108.",
                      W.read_files(REF, "Brief", W.latest(REF, "Brief")["v"])["brief.md"])
        # 4: every agent step's card carries it, and the row shows it was applied
        page = [p for sid, p in self.M.prompts if sid == "write.page"][-1]
        self.assertIn("The department's rules, which you follow:", page)
        self.assertIn("(always) Every page ends with: Call 108.", page)
        self.assertEqual(self.rows("write.page")[-1]["applied"], [kept["id"]])
        # 5: Check lists the rules that apply, reads each page against them, and a broken rule fails the build
        live = len(W.versions(REF, "Live site"))
        self.assertEqual(live, 2, "the rule's own rerun went live: the harness meets the rule")
        self.assertTrue(self.rows("check.rules", status="ok"), "Check asked its agent to hold the pages to the rule")
        self.M.broken = [{"rule": "Every page ends with: Call 108.", "pages": ["about", "contact"], "why": "no 108"}]
        self.ask("Add a page on parking.")
        self.idle()
        for step in ("check.rules_of", "check.rules", "check.build"):
            self.assertTrue(self.rows(step), "the line ran " + step)
        failed = [v for v in W.versions(REF, "Build") if not v["check"]["ok"]]
        self.assertIn("breaks the rule 'Every page ends with: Call 108.' on about, contact", failed[-1]["check"]["notes"])
        # 6: sent back to Write with the finding, twice at most; then the owner is told, and nothing went live
        self.assertEqual(len(failed), 3, "three builds filed failed: the one, and two rewrites")
        self.assertEqual(len(W.versions(REF, "Live site")), live, "nothing went live while the rule was broken")
        said = [t["line"] for t in R.chat_view(REF)["turns"] if t["word"] == "broken"]
        self.assertEqual(len(said), 3, said)
        self.assertEqual(len([s for s in said if s.endswith("Sent back to be rewritten.")]), 2)
        self.assertIn("two rewrites did not mend it. Say the rule another way, or drop it.", said[-1])
        self.assertFollowed("J4", mark, ["1", "2", "3", "4", "5", "6"])


class TestJ4Edges(Ruling):
    def test_j4_1_a_rule_the_department_already_has_is_said_back_and_not_added(self):
        """J4.1: the same directive said again is answered 'the department already has this rule', and nothing is added or asked."""
        W, R = self.W, self.R
        self.live()
        words = "From now on, never state a number the brief does not give"
        self.ask(words)
        self.stamp("rule")
        self.idle()
        rules, asks = copy_rules(W.dept(REF)["rules"]), len(W.asks(REF))
        self.assertEqual(len(self.rule_asks()), 1)
        posts = len(R.board(REF))
        self.ask(words)
        told = [p for p in R.board(REF)[posts:] if p["src"] == "Identity" and p["dst"] == ["Owner"] and p["payload"].get("word") == "request"]
        self.assertEqual([p["payload"]["done"] for p in told], ["the department already has this rule"], "Identity says it has the rule")
        self.assertEqual(told[0]["msg_type"], "inform")
        self.assertEqual(copy_rules(W.dept(REF)["rules"]), rules, "the rules are as they were")
        self.assertEqual(len(self.rule_asks()), 1, "and no second ask of kind rule was made")
        self.assertEqual(len(W.asks(REF)), asks, "nor any other")
