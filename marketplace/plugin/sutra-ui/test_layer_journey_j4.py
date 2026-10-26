"""test_layer_journey_j4.py -- J4, a rule, run end to end with a stubbed model (PRD amendment A3.7.4).

TestJ4Walks has the walk: a directive becomes a rule on the owner's stamp, reaches every agent's card, is read against every
page, and a build that breaks it is sent back twice and never goes live (steps 1 to 6). It reads only what the words wrote after
a mark taken before them, asserts journeys.walk.follows returns [], and shows the walk is not vacuous: a changed bind of any
step makes it fail, naming that step. TestJ4Edges holds the edges the row tests lacked: a rule the department already has (J4.1),
and a department's rule that is looser than one it inherits (J4.4).

J4.4 is the one behaviour A3 builds in the journeys (BL-2): layers/identity/tighten.py compares a rule with the rules the
ancestors hold, by normalised line, when the rule is asked for (engine_runtime._rule_ask) and again when it is stamped
(identity_apply). It is built at the strength the code can prove and its row stays partly built (BL-2b): matching is by line and
not by meaning, and Root's own born rules are always and go, so the check reaches a rule an ancestor stamped. The unit tests of
normalise, rank and rule_faults are at the end.

The classes subclass test_engine_runtime.Base (imported by name, so no other test class is collected twice) and so reuse its
scripted Model, `live()`, `ask()`, `stamp()`, `idle()` and `rows()`.
"""
import copy
import importlib
import json
import re

import journeys
import layer_schema as S
import test_engine_runtime as T
from journeys import walk
from layers.identity import tighten
from test_engine_runtime import REF, Base
from test_j2_identity import j2  # noqa: F401 -- the fixture of a founded structure with the J2 cycle on, for the one test that needs it

#: the line an ancestor holds in the J4.4 tests, and the words that ask for it
LINE = "Never publish prices"
WORDS = "From now on, never publish prices"
SAID = "a department's rules can only tighten it"


def journey(jid):
    """The journey as its file holds it now (read afresh: the journeys folder is data, and a test does not cache it). One file,
    so a fault in another package's journey is that package's test to report, not this one's."""
    return json.loads((journeys.FOLDER / (jid + ".json")).read_text(encoding="utf-8"))


def copy_rules(rules):
    return [dict(r) for r in rules]


class Ruling(Base):
    """What a rule scenario needs beyond the runtime's Base: a mark before the words, the trace of what they wrote since, and
    the walk asserted."""

    structure = T.TestTheFrontDoor.structure                       # a Root with one department of its own, in a registry of its own
    _unstructure = T.TestTheFrontDoor._unstructure

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

    def reads_as(self, line, tag):
        """The scripted model reads the directive that holds `line` as a rule of this tag (it tags by the word never otherwise)."""
        model = self.M.answer

        def answer(sid, prompt):
            if sid == "identity.rule" and line.lower() in prompt.lower():
                return {"tag": tag, "line": line, "scope": "standing"}, 0.01, "model"
            return model(sid, prompt)

        self.M.answer = answer


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

    # ---- J4.4: a department's rule can only tighten an inherited one ---------------------------------------------------
    def inherit(self, root, rule):
        """An ancestor's rule: set in the organisation's charter sidecar, as test_j1 does for a rule Setup meets."""
        import placement_engine as E
        org = self.W.dept(root)["org"]["ref"]
        charter = E.charters_for(org)[0]
        sidecar = E.load_sidecar(charter["id"])
        sidecar["rules"] = [rule]
        E.save_sidecar(charter["id"], sidecar)

    def say(self, ref, words):
        self.W.owner_ask(ref, words)
        self.W.run_until_idle(ref, limit=200)

    def stamp_in(self, ref, kind="rule"):
        a = next(a for a in self.W.asks(ref) if a["kind"] == kind and a["status"] == "pending")
        self.W.decide_ask(ref, a["id"], True)
        self.W.run_until_idle(ref, limit=200)
        return a

    def told_tighten(self, ref, since):
        """What Identity told the owner on the department's board after post `since` about rules only tightening."""
        return [p for p in self.R.board(ref)[since:] if p["src"] == "Identity" and p["dst"] == ["Owner"] and p["msg_type"] == "inform"
                and SAID in str(p["payload"].get("done"))]

    def kept(self, ref):
        return [(r["tag"], r["line"]) for r in self.W.dept(ref)["rules"]]

    def test_j4_4_a_looser_tag_on_an_inherited_line_is_refused(self):
        """J4.4: an ancestor holds `refuse: Never publish prices`, and the same line is asked for with a lower tag. Identity says a
        department's rules can only tighten it: no ask is filed, nothing is kept, and a row on the record says so. The same rule
        reaching the stamp by an ask filed before the ancestor's rule changed writes nothing either. (The scripted model tags a
        directive ask; a `go` rule is asked for in the last step of this test, by the call the directive's tag goes through.)"""
        W, R = self.W, self.R
        root, child = self.structure()
        self.reads_as(LINE, "ask")
        # the stale ask: filed while no ancestor held the line, stamped after one does
        self.say(child, WORDS)
        stale = next(a for a in W.asks(child) if a["kind"] == "rule" and a["status"] == "pending")
        self.assertEqual((stale["tag"], stale["line"]), ("ask", LINE))
        self.inherit(root, {"tag": "refuse", "line": LINE})
        kept, runs, posts, rooted = self.kept(child), len(W.runs(child)), len(R.board(child)), len(R.board(root))
        self.stamp_in(child)
        self.assertEqual(self.kept(child), kept, "the stamp wrote nothing: the rule would loosen one the department inherits")
        told = self.told_tighten(child, posts)
        self.assertEqual(len(told), 1, told)
        self.assertEqual(told[0]["payload"]["word"], "request")
        self.assertIn("Root's rule stands: " + SAID, told[0]["payload"]["done"])
        self.assertIn(LINE, told[0]["payload"]["done"], "and it names the rule that stands")
        rows = [r for r in W.runs(child)[runs:] if "loosens one it inherits" in r["what"]]
        self.assertEqual([(r["engine"], r["system"]) for r in rows], [("Identity", True)], "a row on the record says Identity said no to it")
        self.assertIn(LINE, rows[0]["what"])
        self.assertEqual(len(self.told_tighten(root, rooted)), 1, "and Root's board carries the words too, for the owner who speaks there")
        # asked for now, the same words are not put to the owner at all
        asks, posts, runs = len(W.asks(child)), len(R.board(child)), len(W.runs(child))
        self.say(child, WORDS)
        self.assertEqual(len(W.asks(child)), asks, "no ask is filed: the owner is never asked to stamp a rule that would be turned down")
        self.assertEqual(self.kept(child), kept)
        told = self.told_tighten(child, posts)
        self.assertEqual(len(told), 1, told)
        self.assertEqual([p for p in R.board(child)[posts:] if p["msg_type"] == "request" and p["payload"].get("word") == "rule"], [],
                         "and no request for a stamp is posted")
        self.assertEqual(len([r for r in W.runs(child)[runs:] if "loosens one it inherits" in r["what"]]), 1, "a row for this one too")
        # a `go` rule on that line is turned down the same way, whoever asks (the call every restated rule goes through)
        asks, runs = len(W.asks(child)), len(W.runs(child))
        self.assertIsNone(R._rule_ask(child, "slot", LINE, "go", WORDS, None, "A rule, as understood"))
        self.assertEqual(len(W.asks(child)), asks)
        self.assertEqual(len([r for r in W.runs(child)[runs:] if "loosens one it inherits" in r["what"]]), 1)
        self.assertEqual(self.kept(child), kept)

    def test_j4_4_a_stricter_or_unrelated_rule_is_written(self):
        """J4.4: the same line tagged `refuse` is as strict as the ancestor's: asked for and written. An unrelated line tagged
        `ask` is written. And with no rule above the department, the check does nothing: a `go` rule is asked for and written."""
        W, R = self.W, self.R
        root, child = self.structure()
        self.inherit(root, {"tag": "refuse", "line": LINE})
        self.reads_as(LINE, "refuse")
        self.say(child, WORDS)
        self.assertEqual([(a["tag"], a["line"]) for a in self.rule_asks(child)], [("refuse", LINE)], "asked for")
        self.stamp_in(child)
        self.assertIn(("refuse", LINE), self.kept(child), "and written")
        other = "Check the opening hours with the clinic"
        self.reads_as(other, "ask")
        self.say(child, "From now on, " + other.lower())
        self.assertEqual([(a["tag"], a["line"]) for a in self.rule_asks(child) if a["status"] == "pending"], [("ask", other)])
        self.stamp_in(child)
        self.assertIn(("ask", other), self.kept(child), "an unrelated line, tagged ask, is written")
        self.assertEqual(self.told_tighten(child, 0), [], "and Identity said nothing about tightening")

    def test_j4_4_with_no_rule_above_the_check_does_nothing(self):
        """A department with no registry above it inherits nothing, so a rule on any line, at any tag, is asked for and written."""
        W, R = self.W, self.R
        self.live()
        self.assertEqual(R._inherited_rules(REF, W.dept(REF)), [])
        self.reads_as(LINE, "ask")
        self.ask(WORDS)
        self.assertEqual([(a["tag"], a["line"]) for a in self.rule_asks()], [("ask", LINE)], "asked for")
        self.stamp("rule")
        self.idle()
        self.assertIn(("ask", LINE), self.kept(REF), "and written")
        # a `go` rule too (the scripted model never tags one; the ask is changed on the record): asked for, stamped and written
        other = "Show the phone number"
        self.reads_as(other, "ask")
        self.ask("From now on, " + other.lower())
        ask = self.rule_asks()[-1]
        W._put_ask(REF, dict(ask, tag="go"))
        self.stamp("rule")
        self.idle()
        self.assertIn(("go", other), self.kept(REF))

    def test_j4_4_a_departments_own_rules_are_not_the_rules_it_inherits(self):
        """The copy of a department's own rules that its charter keeps is not inherited: the owner may loosen a rule of the
        department's own, and the check reaches only a rule an ancestor holds."""
        W, R = self.W, self.R
        root, child = self.structure()
        d = W.dept(child)
        own = next(r for r in d["rules"] if r["tag"] == "refuse")
        copies = [r for r in R._effective_rules(child, d) if r.get("id") and r["line"] == own["line"]]
        self.assertEqual([r["tag"] for r in copies], ["refuse"], "the department's charter does keep a copy, under a charter's id")
        self.assertEqual([r for r in R._inherited_rules(child, d) if r["line"] == own["line"]], [], "and it is not inherited")
        self.assertEqual(R._loosens(child, d, own["line"], "ask"), [], "so a looser rule on its own line is not turned down")

    def test_j4_4_the_rules_a_department_inherits_are_its_ancestors_alone(self):
        """_inherited_rules: Root's born rules and the organisation's, never the department's own or the copy of them."""
        W, R = self.W, self.R
        root, child = self.structure()
        self.inherit(root, {"tag": "refuse", "line": LINE})
        above = [(r["tag"], r["line"]) for r in R._inherited_rules(child, W.dept(child))]
        self.assertIn(("refuse", LINE), above, "the organisation's rule")
        self.assertIn(("always", "A child's rules can only tighten this one's"), above, "and Root's born rule")
        for own in W.dept(child)["rules"]:
            self.assertNotIn((own["tag"], own["line"]), above)
        self.assertEqual(R._loosens(child, W.dept(child), LINE, "ask"), ["The rule above says: Never publish prices (it never does this)."])
        self.assertEqual(R._loosens(child, W.dept(child), LINE, "refuse"), [])
        self.assertEqual(R._loosens(child, W.dept(child), "Show the phone number", "go"), [])
        self.assertEqual(R._loosens(child, W.dept(child), "A child's rules can only tighten this one's", "go"), [],
                         "Root's born rule is a positive always rule, which no tag loosens (BL-2b)")


def test_j4_4_an_answer_to_identitys_own_question_that_would_loosen_a_rule_is_turned_down_and_the_question_is_asked_again(j2, monkeypatch):
    """The same check where a rule given as the answer to Identity's own question on the rules is restated (_rule_answered): the
    owner is told, no rule ask is filed, nothing is kept, and the question stands open again."""
    W, R, J, founding, _ = j2
    import placement_engine as E
    root = founding.found_structure("Bakery Co", owner="Sankalp")["root"]
    W.owner_ask(root, "a site for my bakery in Pune")
    W.run_until_idle(root, limit=300)
    ref = next(d for d in W.list_depts() if d.get("parent") == root)["ref"]
    W.run_until_idle(ref, limit=300)
    charter = E.charters_for(W.dept(root)["org"]["ref"])[0]
    sidecar = E.load_sidecar(charter["id"])
    sidecar["rules"] = [{"tag": "refuse", "line": LINE}]
    E.save_sidecar(charter["id"], sidecar)
    d = W.dept(ref)
    d["rules"] = [{"id": "r1", "line": "Work inside the record"}]           # a rule with no tag: Identity's question is on the rules
    W.save_dept(ref, d)
    R.identity_next(ref)
    asked = J.status(ref)["open_question"]
    assert asked and asked["missing"] == "rules"
    monkeypatch.delenv("SUTRA_WEBSITE_OFFLINE", raising=False)
    monkeypatch.setattr(R, "MODEL", lambda prompt, step: (({"tag": "ask", "line": LINE, "scope": "standing"}, 0.01, "model")
                                                          if step["id"] == "identity.rule" else (None, 0.0, "offline")))
    posts = len(R.board(ref))
    W.owner_ask(ref, LINE)
    W.run_until_idle(ref, limit=300)
    said = [(p["msg_type"], p["payload"].get("word"), str(p["payload"].get("done") or "")) for p in R.board(ref)[posts:] if p["src"] == "Identity"]
    assert any(SAID in done for _, _, done in said), said
    assert [a for a in W.asks(ref) if a["kind"] == "rule"] == [], "no rule ask is filed"
    assert W.dept(ref)["rules"] == [{"id": "r1", "line": "Work inside the record"}], "and nothing is kept"
    again = J.status(ref)["open_question"]
    assert again and again["missing"] == "rules" and again["id"] != asked["id"], "Identity's question is asked again"


# ---- the pure module: layers/identity/tighten.py --------------------------------------------------------------------------
class TestTighten:
    """normalise, rank and rule_faults: no runtime, no record."""

    def test_normalise_takes_off_the_lead_the_punctuation_and_the_case(self):
        same = ["Never publish prices", "never publish prices.", "  NEVER   Publish, prices!  ", "Do not publish prices", "Don't publish prices",
                "Don\u2019t publish prices", "Always publish prices", "publish prices", "- Never: publish prices;"]
        assert {tighten.normalise(s) for s in same} == {"publish prices"}
        assert tighten.normalise("Never publish a build whose check failed") == "publish a build whose check failed"
        assert tighten.normalise("Neverland is closed") == "neverland is closed", "a lead is a word, not the start of one"
        assert tighten.normalise("") == "" and tighten.normalise(None) == ""

    def test_rank_orders_go_ask_refuse_and_a_prohibition_tagged_always_is_refuse(self):
        assert [tighten.rank(t, "Publish prices") for t in ("go", "ask", "refuse")] == [0, 1, 2]
        assert tighten.rank("always", "Never publish prices") == 2, "an always rule that forbids something ranks as refuse does"
        assert tighten.rank("always", "Do not publish prices") == 2 and tighten.rank("always", "Don't publish prices") == 2
        assert tighten.rank("always", "Every page ends with: Call 108.") is None, "a positive always rule has no rank"
        assert tighten.rank("always", "Always show the phone number") is None
        assert tighten.rank("goal", "Never publish prices") is None and tighten.rank("goal", "A new goal") is None
        assert tighten.rank("sometimes", "Never publish prices") is None and tighten.rank(None, None) is None

    def test_rule_faults_name_each_stricter_inherited_rule_on_the_same_line(self):
        above = [{"id": "c:rule:1", "tag": "refuse", "line": "Never publish prices."},
                 {"id": "c:rule:2", "tag": "ask", "line": "Publish prices"},
                 {"id": "c:rule:3", "tag": "refuse", "line": "Never email patients"}]
        faults = tighten.rule_faults(above, "never publish PRICES", "go")
        assert len(faults) == 2, faults
        assert "Never publish prices" in faults[0] and "it never does this" in faults[0]
        assert "Publish prices" in faults[1] and "it asks you first" in faults[1]
        assert len(tighten.rule_faults(above, "Never publish prices", "ask")) == 1, "ask is looser than refuse and not looser than ask"
        assert tighten.rule_faults(above, "Never publish prices", "refuse") == [], "as strict is not looser"
        assert tighten.rule_faults(above, "Never email the doctors", "go") == [], "an unrelated line"
        assert tighten.rule_faults([], "Never publish prices", "go") == [] and tighten.rule_faults(None, "Never publish prices", "go") == []

    def test_rule_faults_never_compare_what_has_no_rank(self):
        above = [{"tag": "always", "line": "Never publish prices"}, {"tag": "always", "line": "Show the phone number"},
                 {"tag": "goal", "line": "Never publish prices"}, {"tag": "ask", "line": "Publish prices"}]
        assert len(tighten.rule_faults(above, "Never publish prices", "go")) == 2, "the prohibition tagged always, and the ask rule"
        assert tighten.rule_faults(above, "Show the phone number", "go") == [], "a positive always rule above is not compared"
        assert tighten.rule_faults(above, "Never publish prices", "always") == [], "an always rule has the rank of its line, and none is higher"
        assert tighten.rule_faults(above, "Publish prices", "goal") == [], "a goal is never compared"
        assert tighten.rule_faults([None, "x", {}], "Never publish prices", "go") == [], "a row that is not a rule is skipped"
        assert tighten.rule_faults(above, "", "go") == [], "an empty line matches nothing"

    def test_the_sentences_are_plain_words_for_the_owner(self):
        for tag in ("go", "ask", "refuse", "always"):
            for sentence in tighten.rule_faults([{"tag": tag, "line": "Never publish prices"}], "Never publish prices", "go"):
                assert not re.search(S.TEMPLATE_BANNED, sentence, re.I), sentence
                assert "(%s)" % tag not in sentence, "the owner is never shown a tag: " + sentence
