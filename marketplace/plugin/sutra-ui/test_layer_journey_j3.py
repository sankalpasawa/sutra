"""test_layer_journey_j3.py -- J3, words after go-live, run end to end with a stubbed model (PRD amendment A3.7.3).

TestJ3Walks has one method for each thing Identity can recognise the words as (task, query, directive, feedback, new idea) and
one for the words said on Root's chat. Each drives the real flows with test_engine_runtime's scripted model, reads only the
record afterwards, and asks one question: did the journey happen the way journeys/J3.json says (journeys.walk.follows)? The
record read is what the words wrote and no more: a mark is taken before they are said, so the first words that took the
department live cannot stand in for a step.

TestJ3Edges holds the three tests the edges lacked: a take that says no (J3.2) and the chip off on Root's chat (J3.4). Each
asserts the effect the row's `code_does` states.

The classes subclass test_engine_runtime.Base (imported by name, so no other test class is collected twice) and so reuse its
scripted Model, `live()`, `ask()`, `stamp()`, `idle()` and `rows()`.
"""
import copy
import importlib
import json

import journeys
import test_engine_runtime as T
from journeys import walk
from test_engine_runtime import REF, Base


def journey(jid):
    """The journey as its file holds it now (read afresh: the journeys folder is data, and a test does not cache it). One file,
    so a fault in another package's journey is that package's test to report, not this one's."""
    return json.loads((journeys.FOLDER / (jid + ".json")).read_text(encoding="utf-8"))


class Walking(Base):
    """What a scenario needs beyond the runtime's Base: a mark taken before the words, the trace of what they wrote since,
    and the walk asserted, with the proof that the walk is not vacuous."""

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
                    next(b for b in mutated["binds"] if b is not None and b.get("kind") == bind["kind"] and b.get(key) == bind[key])[key] = "never-happened"
                    break
            faults = walk.follows(broken, trace, walks=[n])
            self.assertTrue(faults and ("step %s" % n) in faults[0], "a changed bind of step %s must fail the walk, and name it: %s" % (n, faults))

    def said(self, ref, word, since=0, src="Identity", msg_type="inform"):
        """What the board of `ref` said under a topic word after its post number `since` (a mark), the latest first."""
        return [p for p in reversed(self.R.board(ref)[since:]) if p["src"] == src and p["msg_type"] == msg_type and p["payload"].get("word") == word]

    def recognised(self):
        return self.rows("identity.recognise")[-1]


class TestJ3Walks(Walking):
    """J3 steps 1 to 5, one method for each way the words can go."""

    def test_walk_a_task(self):
        """4a: 'Add a Careers page' said inside the live department is recognised as a task, filed in the Brief and run by the
        line, and the function's chat keeps it (steps 1, 3, 4a, 5)."""
        W, R = self.W, self.R
        self.live()
        briefs, lives, asks = len(W.versions(REF, "Brief")), len(W.versions(REF, "Live site")), len(W.asks(REF))
        mark = self.mark(REF)
        self.ask("Add a Careers page")
        got = self.recognised()
        self.assertEqual((got["answer"], got["facts"]["cue"]), ("task", "task"))
        self.assertEqual(len(W.versions(REF, "Brief")), briefs + 1, "filed in the Brief")
        self.assertEqual(len(W.versions(REF, "Live site")), lives + 1, "and the line ran it")
        self.assertEqual(len(W.asks(REF)), asks, "a task the rules let through asks nothing")
        told = self.said(REF, "request", mark[REF][0])
        self.assertEqual((told[0]["dst"], told[0]["payload"]["done"]), (["Owner"], "filed in the Brief"))
        chat = [t for t in R.fn_chat_view(REF, "identity")["turns"] if not t["think"]]
        lines = [(t["src"], t["line"]) for t in chat]
        self.assertIn(("Owner", "Add a Careers page"), lines, "the function's chat keeps the words")
        self.assertIn(("Identity", "filed in the Brief"), lines, "and what came of them")
        self.assertFollowed("J3", mark, ["1", "3", "4a", "5"])

    def test_walk_through_roots_chat(self):
        """Steps 1, 2, 3: the same words said on Root's chat with the department's chip. Root hands them to the department's
        Identity as a post from Root, the department recognises them, and the answer comes back onto Root's board."""
        W, R = self.W, self.R
        root, child = self.structure()
        name = W.dept(child)["name"]
        mark = self.mark(root, child)
        briefs = len(W.versions(child, "Brief"))
        words = "Add a Careers page for nurses who want to join."
        W.owner_ask(root, words, about=child)
        W.run_until_idle(root, limit=200)
        W.run_until_idle(child, limit=200)
        board = lambda ref: [(p["src"], p["dst"][0], p["msg_type"], p["payload"].get("word")) for p in R.board(ref)[mark[ref][0]:]]   # noqa: E731
        self.assertEqual(board(root)[:2], [("Owner", "Identity", "request", "front"), ("Identity", "Owner", "inform", "request")],
                         "on Root's board: the words, then where they went")
        self.assertEqual(board(child)[0], ("Root", "Identity", "request", "request"), "on the department's: Root handed them to its Identity")
        handed = R.board(child)[mark[child][0]]
        self.assertEqual(handed["payload"]["words"], words)
        told = self.said(root, "request", mark[root][0])
        self.assertEqual(told[-1]["payload"]["done"], "handed to %s" % name)
        self.assertEqual(len(W.versions(child, "Brief")), briefs + 1, "the department took them")
        answer = told[0]
        self.assertEqual((answer["payload"]["done"], answer["about"]["name"]), ("filed in the Brief", name),
                         "and its answer came back onto Root's board, about the department")
        rows = {r["step"]: r["by"] for r in R.step_rows(root)[mark[root][1]:] if r["step"].startswith("identity.")}
        self.assertEqual(rows, {"identity.front": "code", "identity.route": "code", "identity.hand": "code"}, "Root's front door is code")
        self.assertEqual([r["answer"] for r in R.step_rows(child)[mark[child][1]:] if r["step"] == "identity.recognise"], ["task"],
                         "the department's Identity recognised them")
        self.assertFollowed("J3", mark, ["1", "2", "3"])

    def test_walk_a_query(self):
        """4b: a question is answered with its source and confidence, and changes nothing (steps 1, 3, 4b)."""
        W, R = self.W, self.R
        self.live()
        before = (len(W.versions(REF, "Brief")), len(W.versions(REF, "Live site")), len(W.asks(REF)))
        mark = self.mark(REF)
        self.ask("How many pages are live?")
        self.assertEqual(self.recognised()["answer"], "query")
        p = self.said(REF, "answer", mark[REF][0])[0]
        self.assertEqual((p["src"], p["dst"], p["msg_type"]), ("Identity", ["Owner"], "inform"))
        self.assertEqual((p["payload"]["answer"], p["payload"]["source"], p["payload"]["confidence"]),
                         ("Five pages are live.", "pages in the plan", "high"))
        self.assertEqual((len(W.versions(REF, "Brief")), len(W.versions(REF, "Live site")), len(W.asks(REF))), before,
                         "a query files nothing and asks nothing")
        self.assertFollowed("J3", mark, ["1", "3", "4b"])

    def test_walk_a_directive(self):
        """4c: a standing directive is restated as one rule and put to the owner as an ask of kind rule; nothing is kept
        before the stamp (steps 1, 3, 4c). Everything after the ask is J4's."""
        W = self.W
        self.live()
        rules = len(W.dept(REF)["rules"])
        mark = self.mark(REF)
        self.ask("From now on, never state a number the brief does not give")
        self.assertEqual(self.recognised()["answer"], "directive")
        asks = [a for a in W.asks(REF) if a["kind"] == "rule"]
        self.assertEqual(len(asks), 1)
        self.assertTrue(asks[0]["text"].startswith("A rule, as understood"), asks[0]["text"])
        self.assertEqual(len(W.dept(REF)["rules"]), rules, "nothing is kept before the owner stamps it")
        asked = self.said(REF, "rule", mark[REF][0], msg_type="request")[0]
        self.assertEqual(asked["dst"], ["Owner"])
        self.assertFollowed("J3", mark, ["1", "3", "4c"])

    def test_walk_feedback(self):
        """4d: a correction is weighed: the work is corrected now, the owner's word is a mark against the step that made the
        page, and the Brief carries the correction (steps 1, 3, 4d)."""
        W = self.W
        self.live()
        mark = self.mark(REF)
        self.ask("The contact page is too long")
        self.assertEqual(self.recognised()["answer"], "feedback")
        marks = [r for r in self.rows("write.page") if r["mode"] == "mark"]
        self.assertEqual([(m["item"], m["by"]) for m in marks], [("contact", "the owner")], "a mark on the step that wrote the page")
        self.assertIn("Correct this on Contact", W.read_files(REF, "Brief", W.latest(REF, "Brief")["v"])["brief.md"])
        self.assertFollowed("J3", mark, ["1", "3", "4d"])

    def test_walk_a_new_idea(self):
        """4e: an idea goes to Adaptation, which shapes it and gives it back; Identity tells the owner; nothing is built
        (steps 1, 3, 4e). Everything after the parked idea is J5's."""
        W, R = self.W, self.R
        self.live()
        before = (len(W.versions(REF, "Brief")), len(W.versions(REF, "Live site")))
        mark = self.mark(REF)
        self.ask("What if patients could book a visit on the site")
        self.assertEqual(self.recognised()["answer"], "new-idea")
        self.assertEqual([(p["src"], p["dst"][0], p["msg_type"]) for p in R.board(REF)[mark[REF][0]:] if p["payload"].get("word") == "idea"],
                         [("Identity", "Adaptation", "request"), ("Adaptation", "Identity", "inform"), ("Identity", "Owner", "inform")])
        self.assertEqual((len(W.versions(REF, "Brief")), len(W.versions(REF, "Live site"))), before, "no build before the owner commits")
        self.assertEqual(R.ideas(REF)[-1]["state"], "parked")
        self.assertFollowed("J3", mark, ["1", "3", "4e"])


class TestJ3Edges(Walking):
    """The edges J3 had no test for: the take says no (J3.2) and the chip is off (J3.4)."""

    def test_j3_2_a_refused_take_tells_the_owner_why_and_files_nothing(self):
        """J3.2: when Identity's take says no, the owner is told why, in a refuse from Identity, and nothing is filed or asked."""
        W, R = self.W, self.R
        self.live()
        words = "Publish the private phone numbers of every doctor"
        why = "it would publish the private numbers of the doctors"
        model = self.M.answer

        def take_says_no(sid, prompt):
            if sid == "identity.take" and words in prompt:
                return {"verdict": "refuse", "why": why, "needs": [], "unsure": [], "rule": None, "thin": False}, 0.01, "model"
            return model(sid, prompt)

        self.M.answer = take_says_no
        briefs, asks, lives = len(W.versions(REF, "Brief")), len(W.asks(REF)), len(W.versions(REF, "Live site"))
        posts = len(R.board(REF))
        self.ask(words)
        self.assertEqual(self.recognised()["answer"], "task")
        refused = [p for p in R.board(REF)[posts:] if p["src"] == "Identity" and p["msg_type"] == "refuse"]
        self.assertEqual([(p["dst"], p["payload"]["word"], p["payload"]["why"]) for p in refused], [(["Owner"], "request", why)],
                         "Identity said no to the owner and gave the reason")
        self.assertEqual(len(W.versions(REF, "Brief")), briefs, "nothing was filed in the Brief")
        self.assertEqual(len(W.versions(REF, "Live site")), lives, "and the line did not run")
        self.assertEqual(len(W.asks(REF)), asks, "and nothing was asked")

    def test_j3_4_chip_off_goes_to_the_only_department(self):
        """J3.4: with no chip and no name in the words, a Root with one department hands the words to it, and says so."""
        W, R = self.W, self.R
        root, child = self.structure()
        name = W.dept(child)["name"]
        mark = self.mark(root, child)
        briefs = len(W.versions(child, "Brief"))
        words = "Add a parking page for visitors."
        W.owner_ask(root, words)
        W.run_until_idle(root, limit=200)
        W.run_until_idle(child, limit=200)
        handed = [p for p in R.board(child)[mark[child][0]:] if p["src"] == "Root"]
        self.assertEqual([(p["dst"], p["msg_type"], p["payload"]["word"], p["payload"]["words"]) for p in handed],
                         [(["Identity"], "request", "request", words)], "the words reached the only department as a post from Root")
        told = [p for p in R.board(root)[mark[root][0]:] if p["src"] == "Identity" and p["payload"].get("word") == "request"]
        self.assertEqual(told[0]["payload"]["done"], "handed to %s" % name, "and Root says where they went")
        self.assertEqual(len(W.versions(child, "Brief")), briefs + 1, "the department took them")
        self.assertEqual(len([d for d in W.list_depts() if d.get("parent") == root]), 1, "and no department was made")

    def test_j3_4_chip_off_with_two_departments_says_which(self):
        """J3.4: with no chip, no name, and two departments, Root asks which, listing both, and files nothing."""
        W, R = self.W, self.R
        root, child = self.structure()
        W.owner_ask(root, "Start a new department: a second website for Meadow Clinic, for its pharmacy.")
        W.run_until_idle(root, limit=200)
        kids = [d for d in W.list_depts() if d.get("parent") == root]
        self.assertEqual(len(kids), 2)
        for kid in kids:
            W.run_until_idle(kid["ref"], limit=200)
        refs = [root] + [kid["ref"] for kid in kids]
        mark = self.mark(*refs)
        briefs = {kid["ref"]: len(W.versions(kid["ref"], "Brief")) for kid in kids}
        W.owner_ask(root, "Add a parking page for visitors.")
        W.run_until_idle(root, limit=200)
        for kid in kids:
            W.run_until_idle(kid["ref"], limit=200)
        told = [p for p in R.board(root)[mark[root][0]:] if p["src"] == "Identity" and p["payload"].get("word") == "request"]
        self.assertEqual(len(told), 1)
        said = told[0]["payload"]["done"]
        self.assertTrue(said.startswith("Say which department:"), said)
        for kid in kids:
            self.assertIn(kid["name"], said, "it lists every department")
        for kid in kids:
            self.assertEqual(R.board(kid["ref"])[mark[kid["ref"]][0]:], [], "nothing was handed to any department")
            self.assertEqual(len(W.versions(kid["ref"], "Brief")), briefs[kid["ref"]], "and nothing was filed")
        self.assertEqual(len([d for d in W.list_depts() if d.get("parent") == root]), 2, "and no department was made")
