"""test_engine_runtime.py -- the engine runtime, in plain unittest, with a model that is a function.

Every requirement of holding/plans/engine-runtime/PRD.md section D and every edge case of LLD.md section 10 that this
build covers has a named test here. The model is injected (engine_runtime.MODEL), so every run is the same run; no
test reaches a real model, the live records home, or the network.

Run: python test_engine_runtime.py
"""
import copy
import importlib
import json
import os
import re
import shutil
import tempfile
import threading
import time
import unittest
from pathlib import Path

REF = "dref-runtime0001"
GOAL = "A website for City Care Hospital: departments, doctors, how to book."
KEYS = ("SUTRA_NATIVE_DEPT_HOME", "SUTRA_WEBSITE_OFFLINE", "SUTRA_ENGINE_RUNTIME", "SUTRA_MOTOR", "SUTRA_ALLOW_DEFAULT_HOME_IN_TESTS")


class Model:
    """The model, as a function: the same answer for the same step, every time. It counts what it was asked."""

    def __init__(self):
        self.calls, self.prompts, self.lock = [], [], threading.Lock()
        self.now, self.most = 0, 0
        self.away, self.bad, self.findings, self.verdicts, self.slow = set(), set(), [], {}, 0.0
        self.journeys, self.future = {}, None

    def __call__(self, prompt, step):
        sid = step["id"]
        with self.lock:
            self.calls.append(sid)
            self.prompts.append((sid, prompt))
            self.now += 1
            self.most = max(self.most, self.now)
        try:
            if self.slow:
                time.sleep(self.slow)
            return self.answer(sid, prompt)
        finally:
            with self.lock:
                self.now -= 1

    def answer(self, sid, prompt):
        page = None
        if sid == "write.page":
            page = json.JSONDecoder().raw_decode(prompt.split("THIS PAGE:\n", 1)[1])[0]      # a checklist may follow the page
        key = sid + (":" + page["slug"] if page else "")
        if sid in self.away or key in self.away:
            self.away.discard(key)
            return None, 0.0, "away"
        if sid in self.bad:
            return {"nothing": "asked for"}, 0.01, "model"
        if sid == "plan.pages":
            pages = [{"slug": s, "title": s.title(), "purpose": "about " + s, "sections": [s]} for s in ("index", "about", "doctors", "contact", "book")]
            return {"site_name": "City Care Hospital", "tagline": "Care, every day", "palette": {"primary": "#0f5e7a", "accent": "#c4956a"},
                    "pages": pages}, 0.02, "model"
        if sid == "write.page":
            return {"title": page["title"], "body_html": "<section><h1>%s</h1><p>%s</p></section>" % (page["title"], "What a patient needs to know. " * 3)}, 0.03, "model"
        if sid == "identity.recognise":
            words = prompt.split("THE WORDS: ", 1)[1].split("\n", 1)[0]
            low = words.lower()
            j = self.journeys.get(words) or ("directive" if low.startswith(("from now on", "just this once")) else
                                             "query" if low.endswith("?") else
                                             "feedback" if ("too long" in low or "is wrong" in low) else
                                             "new-idea" if low.startswith("what if") else "task")
            return {"journey": j, "why": "read"}, 0.01, "model"
        if sid == "identity.answer":
            return {"answer": "Five pages are live.", "source": "pages in the plan", "confidence": "high"}, 0.01, "model"
        if sid == "identity.rule":
            words = prompt.split("THE DIRECTIVE: ", 1)[1].split("\n", 1)[0]
            low = words.lower()
            line = words.split(",", 1)[1].strip() if "," in words else words
            return {"tag": "goal" if "the site is for" in low else "refuse" if "never" in low else "always",
                    "line": line[:1].upper() + line[1:], "scope": "one-time" if low.startswith("just this once") else "standing"}, 0.01, "model"
        if sid == "identity.weigh":
            words = prompt.split("THE FEEDBACK: ", 1)[1].split("\n", 1)[0]
            return {"about": "contact" if "contact" in words.lower() else None, "what": "format", "now": "Cut the page to half its length",
                    "future": self.future}, 0.01, "model"
        if sid == "adapt.shape":
            return {"reflected": "Let a patient book a visit on the site", "question": "Who confirms the booking?",
                    "shapes": ["a page with the phone number to book", "a form that sends a request", "a live calendar"]}, 0.02, "model"
        if sid == "identity.take":
            words = prompt.split("THE REQUEST: ", 1)[1].split("\n", 1)[0]
            v = self.verdicts.get(words) or ("ask" if "email" in words.lower() else "go")
            return {"verdict": v, "why": "judged"}, 0.01, "model"
        if sid == "identity.judge":
            return {"verdict": "admit", "why": "the rules allow it"}, 0.01, "model"
        if sid == "priority.bargain":
            return {"answer": "accept", "why": "the envelope has room"}, 0.01, "model"
        if sid == "audit.judge":
            return {"ok": not self.findings, "findings": list(self.findings)}, 0.02, "model"
        raise AssertionError("the model was asked for a step no test expects: " + sid)


class Base(unittest.TestCase):
    runtime = "2"

    def setUp(self):
        self.home = tempfile.mkdtemp(prefix="engine-runtime-")
        self.prior = {k: os.environ.get(k) for k in KEYS}
        for k in KEYS:
            os.environ.pop(k, None)
        os.environ["SUTRA_NATIVE_DEPT_HOME"] = self.home
        if self.runtime:
            os.environ["SUTRA_ENGINE_RUNTIME"] = self.runtime
        import website_dept
        self.W = importlib.reload(website_dept)
        import engine_runtime
        self.R = importlib.reload(engine_runtime)
        self.R.WAITS = (0, 0, 0)
        self.M = self.R.MODEL = Model()
        self.W.create(REF, "City Care Hospital Website", None)

    def tearDown(self):
        self.R.MODEL = None
        for k, v in self.prior.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        shutil.rmtree(self.home, ignore_errors=True)

    # what a person does
    def idle(self):
        return self.W.run_until_idle(REF, limit=200)

    def stamp(self, kind, approve=True):
        a = next(a for a in self.W.asks(REF) if a["kind"] == kind and a["status"] == "pending")
        self.W.decide_ask(REF, a["id"], approve)
        return a

    def live(self, goal=GOAL):
        self.W.give_goal(REF, goal)
        self.idle()
        self.stamp("publish")
        self.idle()

    def ask(self, words):
        self.W.owner_ask(REF, words)
        self.idle()

    def rows(self, step=None, **want):
        out = [r for r in self.R.step_rows(REF) if (step is None or r["step"] == step)]
        return [r for r in out if all(r.get(k) == v for k, v in want.items())]

    def numbers(self, **n):
        d = self.W.dept(REF)
        d["ladder"] = n
        self.W.save_dept(REF, d)


class TestTheDefinitions(Base):
    def test_01_every_step_names_a_check_and_a_definition_without_one_is_refused(self):
        R = self.R
        self.assertEqual(R.validate(R.defs()), [], "the definitions that ship are clean")
        steps = [s for name in R.defs()["engines"] for s in R.all_steps(name)]
        self.assertGreaterEqual(len(steps), 30)
        for s in steps:
            self.assertIn(s["check"], R.CHECK, s["id"])
        bad = copy.deepcopy(R.defs())
        del bad["engines"]["Write"]["steps"][1]["check"]
        self.assertIn("Write, write.page: the step names no check", R.validate(bad))
        bad = copy.deepcopy(R.defs())
        bad["engines"]["Plan"]["steps"][0]["code"] = "rm_rf"
        self.assertTrue(any("no function named rm_rf ships with the app" in f for f in R.validate(bad)),
                        "a definition can name code; it cannot bring any")

    def test_02_a_check_fails_what_it_should_fail(self):
        C = self.R.CHECK
        self.assertFalse(C["page_has_body"](None, None, None, {"title": "T", "body_html": "<p>short</p>"})["ok"])
        self.assertFalse(C["page_has_body"](None, None, None, {"title": "T", "body_html": "<script>x</script>" + "words " * 20})["ok"])
        self.assertTrue(C["page_has_body"](None, None, None, {"title": "T", "body_html": "<p>%s</p>" % ("words " * 20)})["ok"])
        self.assertFalse(C["plan_is_fit"](None, None, None, {"pages": [{"slug": "about"}, {"slug": "index"}]})["ok"])
        self.assertFalse(C["plan_is_fit"](None, None, None, {"pages": [{"slug": "index"}, {"slug": "index"}]})["ok"])
        self.assertFalse(C["verdict_is_known"](None, None, None, {"verdict": "maybe"})["ok"])
        self.assertFalse(C["facts_are_closed"](None, None, None, {"facts": {"kind": "anything at all"}})["ok"])
        self.assertFalse(C["said_what_it_did"](None, None, None, {"said": " "})["ok"])
        self.assertFalse(C["filed_has_files"](None, None, None, {"files": {}, "check": {"ok": True}})["ok"])


class TestOneSkeleton(Base):
    def test_03_a_goal_runs_to_a_live_site_and_every_unit_that_ran_is_an_engine(self):
        W = self.W
        self.live()
        self.assertTrue((W.live_dir(REF) / "index.html").is_file())
        ran = {r["engine"] for r in W.runs(REF) if r.get("runtime") == 2}
        self.assertEqual(ran, {"Identity", "Plan", "Write", "Check", "Publish", "Adaptation", "Audit"})
        gated = {r["engine"] for r in self.rows(mode="gate")}
        self.assertEqual(gated, {"Identity", "Priority", "Coordination"}, "the three gates answered, each as a row")
        for name in ("Plan", "Write", "Check", "Publish"):
            for s in self.R.engine_def(name)["steps"]:
                self.assertTrue(self.rows(s["id"], status="ok"), s["id"] + " has a row")

    def test_04_every_step_row_has_its_rung_and_its_check(self):
        self.live()
        rows = self.rows()
        self.assertGreater(len(rows), 25)
        for r in rows:
            self.assertIn(r["rung"], self.R.RUNGS, r["step"])
            self.assertIsInstance(r["check"].get("ok"), bool, r["step"])
            self.assertTrue(r["check"].get("notes"), r["step"] + " says what its check looked at")

    def test_05_a_step_on_the_code_rung_makes_no_model_call(self):
        self.live()
        soft = {"identity.take", "plan.pages", "write.page", "audit.judge"}
        self.assertEqual(set(self.M.calls), soft)
        for r in self.rows():
            if r["rung"] == "C2":
                self.assertEqual(r["calls"], 0, r["step"])
        self.assertEqual(self.M.calls.count("write.page"), 5, "one call a page")

    def test_06_each_engine_has_its_own_agent(self):
        self.live()
        first = {sid: p for sid, p in reversed(self.M.prompts)}
        self.assertTrue(first["write.page"].startswith("You are the agent of Write, one engine of the department"))
        self.assertTrue(first["identity.take"].startswith("You are the agent of Identity, one engine of the department"))
        self.assertTrue(first["audit.judge"].startswith("You are the agent of Audit"))
        self.assertEqual({r["agent"] for r in self.rows("write.page")}, {"Write"})
        self.assertEqual({r["agent"] for r in self.rows("plan.read")}, {None}, "a code step has no agent")

    def test_07_the_built_path_is_untouched_when_the_switch_is_off(self):
        W = self.W
        os.environ.pop("SUTRA_ENGINE_RUNTIME")
        os.environ["SUTRA_WEBSITE_OFFLINE"] = "1"
        ref = "dref-built0001"
        W.create(ref, "Old Path Website", None)
        self.assertIsNone(W._runtime(ref))
        W.give_goal(ref, GOAL)
        self.assertEqual(W.run_until_idle(ref), 3)
        a = W.status(ref)["asks"][0]
        W.decide_ask(ref, a["id"], True)
        self.assertEqual(W.run_until_idle(ref), 1)
        self.assertTrue((W.live_dir(ref) / "index.html").is_file())
        for f in ("steps.jsonl", "board.jsonl", "exchanges.json", "ladder.json"):
            self.assertFalse((W.ddir(ref) / f).exists(), f)
        self.assertEqual(self.M.calls, [], "and it never reached the runtime's model")


class TestCheckpoints(Base):
    def cut_write_after(self, n):
        """The app closes while Write is on its n-th page: the run row says running, n pages have their rows."""
        W, R = self.W, self.R
        W.give_goal(REF, GOAL)
        for _ in range(2):                               # Identity takes the goal; Plan plans
            name, inp, slot = W.due(REF)
            W.run_slot(REF, name, inp, slot)
        name, inp, slot = W.due(REF)
        self.assertEqual(name, "Write")
        e = R.engine_def("Write")
        run = W._put_run(REF, R._run_row("Write", False, slot, "running", "reading Site plan"))
        ctx = {"ref": REF, "dept": W.dept(REF), "engine": "Write", "def": e, "slot": slot, "inp": inp, "post": None, "run": run["id"],
               "bag": {}, "how": {}, "spend": {"calls": 0, "usd": 0.0}}
        _, ctx["bag"]["write.list"] = R.run_step(ctx, e["steps"][0], None)
        pages = ctx["bag"]["write.list"]["pages"]
        for p in pages[:n]:
            R.run_step(ctx, e["steps"][1], p)
        return slot, pages

    def test_08_a_cut_run_resumes_at_its_first_unfinished_step(self):
        W = self.W
        slot, pages = self.cut_write_after(2)
        self.assertEqual(self.M.calls.count("write.page"), 2)
        W.recover()                                      # the app reopens
        self.assertEqual([r["status"] for r in W.runs(REF) if r.get("slot") == slot], ["interrupted"])
        self.idle()
        self.assertEqual(self.M.calls.count("write.page"), len(pages), "the two written pages were not written again")
        mine = [r for r in W.runs(REF) if r.get("slot") == slot]
        self.assertEqual([r["status"] for r in mine], ["interrupted", "ok"])
        self.assertEqual(mine[1]["retries"], 1)
        self.assertEqual(len(json.loads(W.read_files(REF, "Pages", 1)["_plan.json"])["pages"]), len(pages))
        self.assertEqual(len([k for k in W.read_files(REF, "Pages", 1) if k.endswith(".html")]), len(pages))

    def test_09_the_items_of_a_fan_out_step_run_side_by_side_each_with_its_own_row(self):
        self.M.slow = 0.05
        self.W.give_goal(REF, GOAL)
        self.idle()
        self.assertGreaterEqual(self.M.most, 2, "pages were written side by side")
        self.assertLessEqual(self.M.most, 4, "and never more than the step allows")
        items = [r["item"] for r in self.rows("write.page", status="ok")]
        self.assertEqual(sorted(items), ["about", "book", "contact", "doctors", "index"])

    def test_10_one_item_that_waits_runs_again_alone(self):
        self.M.away.add("write.page:doctors")
        self.W.give_goal(REF, GOAL)
        self.idle()
        self.assertEqual(self.M.calls.count("write.page"), 5 + 1, "five pages, and the one that waited once more")
        self.assertEqual(len(self.rows("write.page", status="waiting")), 1)
        self.assertEqual(len(self.rows("write.page", status="ok")), 5)
        self.assertTrue(self.W.versions(REF, "Pages"))


class TestTheModelIsAway(Base):
    def test_11_a_soft_step_waits_then_asks_the_owner_and_files_nothing(self):
        W = self.W
        def always_away(sid, prompt):
            return None, 0.0, "away"
        self.M.answer = always_away
        W.give_goal(REF, GOAL)
        self.idle()
        mine = [r["status"] for r in W.runs(REF) if r["engine"] == "Identity" and r.get("slot")]
        self.assertEqual(mine, ["waiting"] * 3)
        a = [a for a in W.asks(REF) if a["kind"] == "model"]
        self.assertEqual(len(a), 1)
        self.assertTrue(a[0]["escalated"])
        self.assertEqual(W.versions(REF, "Brief"), [], "nothing was filed on a guess")
        self.assertEqual(self.idle(), 0, "and it waits for the owner")

    def test_12_an_answer_that_does_not_fit_gets_one_more_call_then_goes_down_a_rung(self):
        W = self.W
        self.M.bad.add("identity.take")
        W.give_goal(REF, GOAL)
        self.idle()
        self.assertEqual(self.M.calls.count("identity.take"), 2, "one call, and one more naming the fault")
        r = self.rows("identity.take")[-1]
        self.assertEqual((r["asked_rung"], r["rung"], r["status"], r["miss"]), ("C0", "P", "asked", True))
        self.stamp("step")
        self.M.bad.clear()
        self.idle()
        self.assertEqual(self.rows("identity.take")[-1]["by"], "stamped by the owner")
        self.assertTrue(W.versions(REF, "Brief"))


class TestTheBoard(Base):
    def test_13_a_post_names_who_it_is_for_and_only_an_allowed_edge_passes(self):
        R = self.R
        with self.assertRaises(ValueError):
            R.post(REF, "Audit", [], "inform", {"word": "finding"})
        with self.assertRaises(ValueError):
            R.post(REF, "Audit", "Priority", "inform", {"word": "finding"})
        with self.assertRaises(ValueError):
            R.post(REF, "Adaptation", "Identity", "shout", {})
        with self.assertRaises(ValueError):
            R.post(REF, "Plan", "Identity", "inform", {})
        p = R.post(REF, "Audit", "Identity", "inform", {"word": "finding", "claim": "x", "severity": "low"})
        self.assertEqual((p["n"], p["src"], p["dst"]), (1, "Audit", ["Identity"]))

    def test_14_a_post_wakes_only_those_it_names(self):
        R, W = self.R, self.W
        R.post(REF, "Adaptation", "Priority", "propose", {"word": "trial", "step": "write.page", "engine": "Write", "to": "C1", "cost": "one call"})
        name, inp, slot = W.due(REF)
        self.assertEqual((name, slot), ("Priority", "Priority@board.n1"))
        W.run_slot(REF, name, inp, slot)
        name, inp, slot = W.due(REF)
        self.assertEqual((name, slot), ("Adaptation", "Adaptation@board.n2"), "Priority answered, and only Adaptation is woken")
        self.assertNotIn("Identity", {r["engine"] for r in W.runs(REF) if r.get("slot")})

    def test_15_a_thread_follows_its_protocol_and_ends_in_a_state(self):
        R = self.R
        p = R.post(REF, "Adaptation", "Priority", "propose", {"word": "trial", "step": "write.page"})
        th = R._thread(REF, p["thread"])
        self.assertEqual((th["protocol"], th["state"], th["decider"], th["default"]), ("propose", "submitted", "Priority", "reject-proposal"))
        R.post(REF, "Priority", "Adaptation", "reject-proposal", {"word": "trial", "step": "write.page"}, thread=p["thread"])
        th = R._thread(REF, p["thread"])
        self.assertEqual((th["state"], th["outcome"]["by"]), ("rejected", "reject-proposal"))
        self.assertIsNone(R.post(REF, "Adaptation", "Priority", "propose", {"word": "trial"}, thread=p["thread"]), "a closed thread takes no post")

    def test_16_a_thread_is_closed_at_its_hop_bound_with_the_outcome_it_named(self):
        R = self.R
        p = R.post(REF, "Adaptation", "Priority", "propose", {"word": "trial"})
        sides = [("Priority", "Adaptation"), ("Adaptation", "Priority")]
        got = [p]
        for i in range(6):
            src, dst = sides[i % 2]
            got.append(R.post(REF, src, dst, "propose", {"word": "trial", "round": i}, thread=p["thread"]))
        self.assertEqual([bool(x) for x in got], [True] * 4 + [False] * 3, "four hops, then no more")
        th = R._thread(REF, p["thread"])
        self.assertEqual((th["state"], th["outcome"]), ("canceled", {"by": "bound", "which": "hops", "holds": "reject-proposal"}))

    def test_17_a_thread_past_its_time_is_closed_and_a_stopped_department_freezes_it(self):
        R, W = self.R, self.W
        p = R.post(REF, "Adaptation", "Priority", "propose", {"word": "trial"}, bounds={"hops": 4, "seconds": 5, "usd": 1})
        W.set_stopped(REF, True)
        for _ in range(5):
            R.sweep(REF)
        self.assertEqual(R._thread(REF, p["thread"])["state"], "submitted", "stopped: the thread's clock does not run")
        W.set_stopped(REF, False)
        R.sweep(REF)
        self.assertEqual(R._thread(REF, p["thread"])["state"], "submitted")
        R.sweep(REF)
        th = R._thread(REF, p["thread"])
        self.assertEqual((th["state"], th["outcome"]["which"], th["outcome"]["holds"]), ("canceled", "seconds", "reject-proposal"))

    def test_18_the_owners_posts_always_pass_and_are_not_counted(self):
        R = self.R
        rq, p = R.request(REF, "Add a Careers page")
        for _ in range(6):
            self.assertIsNotNone(R.post(REF, "Owner", "Identity", "request", {"word": "request", "words": "and one more thing"}, thread=p["thread"]))
        self.assertEqual(R._thread(REF, p["thread"])["hops"], 0)

    def test_19_the_owner_reads_the_whole_board(self):
        self.live()
        b = self.R.board_view(REF)
        said = [(p["src"], tuple(p["dst"]), p["msg_type"]) for t in b["threads"] for p in t["posts"]]
        self.assertIn(("Owner", ("Identity",), "request"), said)
        self.assertIn(("Identity", ("Owner",), "inform"), said)
        self.assertIn(("Identity", ("Owner",), "request"), said, "the first publish was put to the owner on the board")
        self.assertIn(("Owner", ("Identity",), "accept-proposal"), said, "and the stamp is a post")
        self.assertTrue(all(t["state"] in ("completed", "rejected", "canceled", "failed") for t in b["threads"]), "no thread is left open")
        lines = [p["line"] for t in b["threads"] for p in t["posts"]]
        topics = {t["topic"] for t in b["threads"]} | {p["word"] for t in b["threads"] for p in t["posts"] if p["word"]}
        self.assertFalse([l for l in lines if l in topics], "a bare topic word is never printed as what a post said")
        self.assertFalse([l for l in lines if re.search(r"\b[a-z]+\.[a-z_]+\b|\ba-[0-9a-f]{6,}\b", l)], "nor a step's id, nor an ask's")
        stamp = next(p for t in b["threads"] for p in t["posts"] if p["msg_type"] == "accept-proposal")
        self.assertEqual(stamp["line"], "", "a stamp says nothing more than its act")


class TestTheLadder(Base):
    def harden(self):
        """Six asks of one kind, by a strict step: a trial by checklist that Priority grants, a move the owner stamps."""
        self.numbers(runs=3, differing=0, trial=2, misses=2)
        for other in ("plan.pages", "write.page", "audit.judge", "priority.bargain", "identity.recognise"):
            self.R.hold(REF, other)                     # one step is watched; the owner holds the others where they are
        self.live()
        for i in range(12):
            self.ask("Add a page for ward %d" % i)
            if any(a["kind"] == "rung" and a["status"] == "pending" for a in self.W.asks(REF)):
                return
        self.fail("no move was put to the owner")

    def test_20_a_step_climbs_one_rung_by_evidence_a_trial_and_a_stamp(self):
        R = self.R
        _, s = R.step_def("identity.take")
        self.harden()
        self.assertEqual(R.rung_of(REF, s), "C0", "nothing moves before the stamp")
        a = self.stamp("rung")
        self.assertEqual((a["from"], a["to"], a["text"]), ("C0", "C1", "Move “Judge it against the goal” from improvised call to checklist"))
        self.assertGreaterEqual(a["evidence"]["runs"], 6, "a strict step needs twice the runs")
        self.assertEqual(a["evidence"]["differing"], 0)
        self.idle()
        e = R.ladder(REF)["identity.take"]
        self.assertEqual(e["rung"], "C1")
        self.assertEqual(e["history"][-1]["by"], "stamp " + a["id"])
        said = [(p["src"], p["dst"][0], p["msg_type"], p["payload"].get("word")) for p in R.board(REF)]
        self.assertIn(("Adaptation", "Priority", "propose", "trial"), said, "the trial costs a call a run, so Priority was asked")
        self.assertIn(("Priority", "Adaptation", "accept-proposal", "trial"), said)
        self.assertIn(("Adaptation", "Identity", "propose", "rung"), said)
        self.ask("Add a page for the pharmacy")
        r = self.rows("identity.take")[-1]
        self.assertEqual((r["rung"], r["by"]), ("C1", "checklist"))

    def test_21_a_refused_move_leaves_the_step_where_it_was(self):
        R = self.R
        self.harden()
        self.stamp("rung", approve=False)
        self.idle()
        e = R.ladder(REF)["identity.take"]
        self.assertEqual((e["rung"], e["history"][-1]["by"], e["pending"]), ("C0", "refused by the owner", None))

    def to_code(self):
        R = self.R
        self.harden()
        self.stamp("rung")
        self.idle()
        for i in range(20):
            self.ask("Add a page for clinic %d" % i)
            if any(a["kind"] == "rung" and a["status"] == "pending" for a in self.W.asks(REF)):
                break
        a = self.stamp("rung")
        self.idle()
        return a

    def test_22_a_decide_step_reaches_code_as_a_table_and_then_the_model_is_bypassed(self):
        R = self.R
        a = self.to_code()
        self.assertEqual((a["from"], a["to"], a["form"]), ("C1", "C2", "table"))
        e = R.ladder(REF)["identity.take"]
        self.assertEqual((e["rung"], e["form"]), ("C2", "table"))
        table = json.loads(self.W.read_files(REF, "Table: identity.take", self.W.latest(REF, "Table: identity.take")["v"])["table.json"])
        self.assertIn({"all": [{"field": "first", "is": False}, {"field": "kind", "is": "add-page"}, {"field": "leaves_site", "is": False}],
                       "then": {"verdict": "go"}}, table["when"])
        before = self.M.calls.count("identity.take")
        self.ask("Add a page for the blood bank")
        r = self.rows("identity.take")[-1]
        self.assertEqual((r["rung"], r["by"], r["calls"], r["miss"]), ("C2", "table", 0, False))
        self.assertEqual(self.M.calls.count("identity.take"), before, "complete codification: the model was not called")

    def test_23_a_code_step_with_no_rule_for_the_input_never_guesses(self):
        self.to_code()
        before = self.M.calls.count("identity.take")
        self.ask("Make the whole site feel calmer in its colours")
        r = self.rows("identity.take")[-1]
        self.assertEqual(r["facts"]["kind"], "style")
        self.assertEqual((r["asked_rung"], r["rung"], r["miss"], r["by"]), ("C2", "C1", True, "checklist"))
        self.assertEqual(self.M.calls.count("identity.take"), before + 1, "that run went one rung down, to the agent")

    def test_24_a_table_changed_by_hand_is_refused(self):
        W = self.W
        self.to_code()
        v = W.latest(REF, "Table: identity.take")["v"]
        p = W.vdir(REF, "Table: identity.take", v) / "table.json"
        t = json.loads(p.read_text())
        t["when"][0]["then"]["verdict"] = "refuse"
        p.write_text(json.dumps(t))
        self.ask("Add a page for the canteen")
        r = self.rows("identity.take")[-1]
        self.assertEqual((r["rung"], r["miss"], r["answer"]), ("C1", True, "go"), "the changed table was not read")

    def test_25_a_step_steps_down_without_a_stamp_when_it_meets_what_it_has_no_rule_for(self):
        R = self.R
        self.to_code()
        for words in ("Make it calmer in colour", "Change the font to something rounder", "Give it a darker look"):
            self.ask(words)
        e = R.ladder(REF)["identity.take"]
        self.assertEqual(e["rung"], "C1")
        self.assertTrue(e["history"][-1]["by"].startswith("evidence: it met inputs it had no rule for"))
        self.assertFalse(any(a["kind"] == "rung" and a["status"] == "pending" for a in self.W.asks(REF)), "no stamp was asked for")

    def test_26_a_held_step_is_left_alone(self):
        R = self.R
        self.numbers(runs=3, differing=0, trial=2, misses=2)
        R.hold(REF, "identity.take")
        self.live()
        for i in range(8):
            self.ask("Add a page for ward %d" % i)
        e = R.ladder(REF)["identity.take"]
        self.assertEqual((e["rung"], e["trial"], e["pending"], e["held"]), ("C0", None, None, True))


class TestTheGates(Base):
    def test_27_a_gate_that_is_not_on_the_code_rung_answers_wait_and_its_function_judges(self):
        R, W = self.R, self.W
        _, g = R.step_def("identity.gate")
        R.move(REF, g, "C1", "a test, to see the wait")
        W.give_goal(REF, GOAL)
        name, inp, slot = W.due(REF)
        W.run_slot(REF, name, inp, slot)                       # Identity takes the goal
        self.assertEqual(W.due(REF), ("Identity", {"post": R.board(REF)[-1], "v": R.board(REF)[-1]["n"]}, "Identity@board.n%d" % R.board(REF)[-1]["n"]))
        self.assertEqual(R.board(REF)[-1]["payload"]["word"], "verdict")
        self.assertNotIn("Plan", {r["engine"] for r in W.runs(REF)}, "Plan waited for the verdict")
        self.idle()
        self.assertIn("Plan", {r["engine"] for r in W.runs(REF)})
        self.assertEqual(self.M.calls.count("identity.judge"), 3, "one verdict for each of Plan, Write and Check")

    def test_28_the_rule_in_code_is_the_floor_a_soft_gate_never_lets_a_first_publish_through(self):
        R, W = self.R, self.W
        _, g = R.step_def("identity.gate")
        R.move(REF, g, "C0", "a test, to see the floor")
        W.give_goal(REF, GOAL)
        self.idle()
        self.assertEqual([a["kind"] for a in W.status(REF)["asks"]], ["publish"])
        self.assertEqual(W.versions(REF, "Live site"), [])
        self.stamp("publish", approve=False)
        self.idle()
        self.assertEqual(W.versions(REF, "Live site"), [], "refused by the owner: never published")
        self.assertEqual([r["what"] for r in W.runs(REF) if r["status"] == "skipped"], ["refused by the owner"])


class TestAuditAndAlarm(Base):
    def test_29_audit_finds_what_nobody_gave_and_the_owner_sends_it_back_to_the_line(self):
        W = self.W
        self.M.findings = [{"page": "contact.html", "claim": "the page gives a phone number the brief does not.", "severity": "high"},
                           {"page": "about.html", "claim": "the page says the hospital is friendly", "severity": "low"},
                           {"page": "index.html", "claim": "the page names a founding year", "severity": "high"}]
        self.live()
        a = next(a for a in W.asks(REF) if a["kind"] == "finding")
        title = {p["slug"]: p["title"] for p in self.R._pages(REF)}
        found = ("on %s, the page gives a phone number the brief does not; on %s, the page names a founding year"
                 % (title["contact"], title["index"]))
        self.assertEqual(a["text"], "Audit found: %s. Stamp to have it put right." % found,
                         "every finding that could mislead, each with its page, and what a stamp does")
        self.assertNotIn("friendly", a["text"], "a low finding is not put to the owner")
        self.M.findings = []
        self.stamp("finding")
        self.idle()
        brief = W.read_files(REF, "Brief", W.latest(REF, "Brief")["v"])["brief.md"]
        self.assertIn("- Correct this: " + found, brief)
        self.assertEqual(len(W.versions(REF, "Live site")), 2, "and the line ran again, to a second live version")

    def test_30_a_low_finding_is_noted_and_asks_nobody(self):
        self.M.findings = [{"page": "about.html", "claim": "the page says the hospital is friendly", "severity": "low"}]
        self.live()
        self.assertFalse([a for a in self.W.asks(REF) if a["kind"] == "finding"])
        self.assertIn("noted a finding: the page says the hospital is friendly", [r["what"] for r in self.W.runs(REF)])

    def test_31_a_run_past_its_window_raises_an_alarm_to_the_owner(self):
        R, W = self.R, self.W
        r = R._run_row("Write", False, "Write@site-plan.v1", "running", "reading Site plan")
        r["started"] = "2026-01-01T00:00:00+00:00"
        W._put_run(REF, r)
        R.sweep(REF)
        R.sweep(REF)
        a = [a for a in W.asks(REF) if a["kind"] == "alarm"]
        self.assertEqual(len(a), 1, "one alarm, however many ticks")
        self.assertEqual((a[0]["text"], a[0]["escalated"]), ("Write has run past its window", True))
        self.assertEqual([(p["src"], p["dst"], p["payload"]["word"]) for p in R.board(REF)], [("Coordination", ["Identity"], "alarm")])


class TestWhatTheOwnerSees(Base):
    def test_32_an_engine_shows_its_steps_each_with_its_rung_its_check_and_its_rows(self):
        self.live()
        v = self.R.steps_view(REF, "Write")
        self.assertEqual([(s["name"], s["rung_name"], s["nature"], s["check"]) for s in v["steps"]],
                         [("List the pages", "Code", "transform", "list_has_pages"),
                          ("Write a page", "Improvised call", "make", "page_has_body"),
                          ("Put the pages together", "Code", "transform", "filed_has_files")])
        page = v["steps"][1]
        self.assertEqual((page["ceiling"], page["each"], page["side_by_side"], page["last"]["ok"]), ("C1", True, 4, True))
        self.assertEqual(page["evidence"]["runs"], 5)
        f = self.R.steps_view(REF, "Identity")
        self.assertEqual(f["kind"], "function")
        self.assertEqual([s["mode"] for s in f["steps"]][:2], ["gate", "slot"])
        self.assertIn("Take a request", f["hears"])
        by = {s["name"]: s["under"] for s in f["steps"]}
        self.assertEqual((by["Read the request"], by["Post the verdict"]), ("Take a request", "Give a verdict"),
                         "each step says which handler it runs under, so the card can group them")
        self.assertIsNone(v["steps"][0]["under"], "a step of the line runs under no handler")
        self.assertEqual(sorted(f["numbers"]), ["differing", "misses", "runs", "trial"], "the ladder's numbers travel with the view")

    def test_32b_the_budget_check_reads_the_departments_own_envelope(self):
        W = self.W
        self.live()
        d = W.dept(REF)
        used = W._today_spend(REF, "Write")[0]
        self.assertGreater(d["envelopes"]["Write"]["calls"], W.ENVELOPE["calls"], "a runtime department's envelope is sized for a call per page")
        budget = next(c for c in W.health(REF)["checks"] if c["name"] == "Budget")
        self.assertLess(used, d["envelopes"]["Write"]["calls"])
        self.assertEqual((budget["state"], budget["line"]), ("ok", "Inside every envelope"))
        d["envelopes"]["Write"]["calls"] = max(1, used)
        W.save_dept(REF, d)
        budget = next(c for c in W.health(REF)["checks"] if c["name"] == "Budget")
        self.assertEqual((budget["state"], budget["line"]), ("warn", "Over: Write"))
        d["envelopes"]["Write"]["calls"] = 10 * used + 10
        d["envelopes"]["Plan"]["usd"] = 0.0
        W.save_dept(REF, d)
        budget = next(c for c in W.health(REF)["checks"] if c["name"] == "Budget")
        self.assertEqual((budget["state"], budget["line"]), ("warn", "Over: Plan"), "money is a limit too, as it is at Priority's gate")

    def test_33_a_request_that_reaches_outside_the_site_is_put_back_to_the_owner(self):
        W = self.W
        self.live()
        self.ask("Email the new site to every patient")
        a = next(a for a in W.asks(REF) if a["kind"] == "request")
        self.assertEqual(self.rows("identity.take")[-1]["facts"], {"kind": "other", "leaves_site": True, "first": False})
        n = len(W.versions(REF, "Brief"))
        self.stamp("request", approve=False)
        self.idle()
        self.assertEqual(len(W.versions(REF, "Brief")), n, "refused: the Brief did not change")
        self.assertEqual(a["text"], "This reaches outside the site: Email the new site to every patient")


class TestTheFiveJourneys(Base):
    """Canon's five journeys (the Native site, products/cos/design-journeys.html). One way in; Identity recognises which."""

    def said(self, word=None):
        return [(p["src"], p["dst"][0], p["msg_type"], p["payload"].get("word")) for p in self.R.board(REF)
                if word is None or p["payload"].get("word") == word]

    def recognised(self):
        return self.rows("identity.recognise")[-1]

    def test_34_the_first_words_are_the_goal_and_need_no_recognising(self):
        self.W.give_goal(REF, GOAL)
        self.idle()
        self.assertNotIn("identity.recognise", self.M.calls)
        self.assertEqual(self.rows("identity.recognise")[-1]["by"], self.R.SKIPPED)
        self.assertEqual(len(self.W.versions(REF, "Brief")), 1)
        self.assertEqual(self.R.evidence(REF, "identity.recognise")["runs"], 0, "a step that was not needed is evidence of nothing")

    def test_35_a_task_goes_to_the_line(self):
        self.live()
        n = len(self.W.versions(REF, "Live site"))
        self.ask("Add a Careers page")
        self.assertEqual((self.recognised()["answer"], self.recognised()["facts"]["cue"]), ("task", "task"))
        self.assertEqual(len(self.W.versions(REF, "Live site")), n + 1)

    def test_36_a_query_is_answered_with_its_source_and_changes_nothing(self):
        W = self.W
        self.live()
        before = (len(W.versions(REF, "Brief")), len(W.versions(REF, "Live site")), len(W.asks(REF)))
        self.ask("How many pages are live?")
        self.assertEqual(self.recognised()["answer"], "query")
        p = [p for p in self.R.board(REF) if p["payload"].get("word") == "answer"][-1]
        self.assertEqual((p["src"], p["dst"], p["msg_type"]), ("Identity", ["Owner"], "inform"))
        self.assertEqual((p["payload"]["answer"], p["payload"]["source"], p["payload"]["confidence"]),
                         ("Five pages are live.", "pages in the plan", "high"))
        self.assertEqual(self.R._thread(REF, p["thread"])["state"], "completed")
        self.assertEqual((len(W.versions(REF, "Brief")), len(W.versions(REF, "Live site")), len(W.asks(REF))), before,
                         "a query changes nothing and asks nothing")
        self.assertNotIn("identity.take", [r["step"] for r in self.rows() if r["run"] == self.recognised()["run"] and r["by"] != self.R.SKIPPED])

    def test_37_a_directive_is_restated_put_back_and_kept_only_on_a_stamp(self):
        W = self.W
        self.live()
        rules = len(W.dept(REF)["rules"])
        self.ask("From now on, never state a number the brief does not give")
        self.assertEqual(self.recognised()["answer"], "directive")
        a = next(a for a in W.asks(REF) if a["kind"] == "rule")
        self.assertEqual(a["text"], "A rule, as understood: Never state a number the brief does not give")
        self.assertEqual(len(W.dept(REF)["rules"]), rules, "nothing is kept before the scope is confirmed")
        self.stamp("rule")
        self.idle()
        kept = W.dept(REF)["rules"][-1]
        self.assertEqual((kept["tag"], kept["line"]), ("refuse", "Never state a number the brief does not give"))
        self.assertIn("A rule, from now on: Never state a number the brief does not give",
                      W.read_files(REF, "Brief", W.latest(REF, "Brief")["v"])["brief.md"])
        page = [p for sid, p in self.M.prompts if sid == "write.page"][-1]
        self.assertIn("The department's rules, which you follow:", page)
        self.assertIn("(refuse) Never state a number the brief does not give.", page, "every engine's agent carries the rule")
        self.assertEqual(self.rows("write.page")[-1]["applied"], [kept["id"]], "and the row shows the rule was applied")

    def test_38_a_directive_for_this_once_is_applied_and_not_kept(self):
        W = self.W
        self.live()
        rules = len(W.dept(REF)["rules"])
        self.ask("Just this once, put the emergency line at the top of every page")
        self.assertEqual(len(W.dept(REF)["rules"]), rules)
        self.assertFalse([a for a in W.asks(REF) if a["kind"] == "rule"])
        self.assertIn("- Just this once, put the emergency line at the top of every page",
                      W.read_files(REF, "Brief", W.latest(REF, "Brief")["v"])["brief.md"])

    def test_39_a_directive_on_the_goal_changes_the_goal_and_the_first_publish_asks_again(self):
        W = self.W
        self.live()
        old = W.dept(REF)["goal"]
        self.ask("From now on, the site is for the new children's wing")
        a = self.stamp("rule")
        self.assertEqual(a["text"], "A new goal, as understood: The site is for the new children's wing")
        self.idle()
        d = W.dept(REF)
        self.assertEqual(d["goal"], "The site is for the new children's wing")
        self.assertEqual(d["goals"][-1]["goal"], old, "the old goal is kept")
        ask = [a for a in W.status(REF)["asks"] if a["kind"] == "publish"]
        self.assertEqual(len(ask), 1, "the first publish under a new goal asks again")
        self.assertEqual(len(W.versions(REF, "Live site")), 1)
        self.stamp("publish")
        self.idle()
        self.assertEqual(len(W.versions(REF, "Live site")), 2)

    def test_40_feedback_corrects_the_work_now_and_counts_against_the_step_that_made_it(self):
        W, R = self.W, self.R
        self.live()
        before = R.evidence(REF, "write.page")
        self.ask("The contact page is too long")
        self.assertEqual(self.recognised()["answer"], "feedback")
        mark = [r for r in self.rows("write.page") if r["mode"] == "mark"]
        self.assertEqual([(m["item"], m["by"], m["check"]["notes"]) for m in mark], [("contact", "the owner", ["the owner: The contact page is too long"])])
        self.assertIn("- Correct this on Contact: Cut the page to half its length", W.read_files(REF, "Brief", W.latest(REF, "Brief")["v"])["brief.md"])
        self.assertEqual(len(W.versions(REF, "Live site")), 2, "the redo landed")
        after = R.evidence(REF, "write.page")
        self.assertEqual((before["pass"], after["marked"]), (1.0, 1))
        self.assertLess(after["pass"], 1.0, "the owner's word is a check, and the step failed it")
        self.assertFalse([a for a in W.asks(REF) if a["kind"] == "rule"], "no forward rule was offered, so none is asked")

    def test_41_feedback_carried_forward_is_a_rule_only_if_the_owner_says_it_sticks(self):
        W = self.W
        self.live()
        self.M.future = "Keep every page under three hundred words"
        self.ask("The contact page is too long")
        a = next(a for a in W.asks(REF) if a["kind"] == "rule")
        self.assertEqual(a["text"], "Carry this forward: Keep every page under three hundred words")
        n = len(W.dept(REF)["rules"])
        self.stamp("rule", approve=False)                      # "just for this one"
        self.idle()
        self.assertEqual(len(W.dept(REF)["rules"]), n)

    def test_42_a_new_idea_is_shaped_and_parked_never_built_and_never_lost(self):
        W, R = self.W, self.R
        self.live()
        before = (len(W.versions(REF, "Brief")), len(W.versions(REF, "Live site")))
        self.ask("What if patients could book a visit on the site")
        self.assertEqual(self.recognised()["answer"], "new-idea")
        idea = R.ideas(REF)[-1]
        self.assertEqual((idea["state"], idea["reflected"], len(idea["shapes"])), ("parked", "Let a patient book a visit on the site", 3))
        self.assertEqual((len(W.versions(REF, "Brief")), len(W.versions(REF, "Live site"))), before, "no build before commit")
        self.assertEqual(self.said("idea"), [("Identity", "Adaptation", "request", "idea"), ("Adaptation", "Identity", "inform", "idea"),
                                             ("Identity", "Owner", "inform", "idea")])
        self.assertTrue(all(t["state"] == "completed" for t in R.threads(REF) if t["topic"] in ("idea", "request")))

    def test_43_words_that_are_none_of_the_five_go_to_the_owner_as_one_question(self):
        W = self.W
        self.live()
        self.M.journeys["Hmm"] = "a sixth kind"
        self.ask("Hmm")
        r = self.recognised()
        self.assertEqual((r["asked_rung"], r["rung"], r["status"]), ("C0", "P", "asked"))
        a = next(a for a in W.asks(REF) if a["kind"] == "step")
        self.assertEqual(a["text"], "Recognise what kind of words these are: by hand")
        self.assertEqual(self.M.calls.count("identity.recognise"), 2, "one call, and one more naming the fault; then the owner")


class TestActivation(Base):
    """Founder, 2026-09-28: every engine has its own start, a trigger and blockers; Start is a signal to all; "the rest
    is in coordination"; once started each has its own agency. One rule for the five internal systems and the four
    work engines, declared as data, refused if missing, read by one piece of code."""

    NINE = ("Plan", "Write", "Check", "Publish", "Identity", "Adaptation", "Priority", "Coordination", "Audit")

    def ctx(self, **more):
        c = self.R._coord_ctx(REF)
        c.update(more)
        return c

    def table(self, **change):
        t = self.R.coordination(REF)
        t.update(change)
        self.W._write(self.W.ddir(REF) / "coordination.json", t)

    def test_44_every_engine_names_its_start_and_one_without_is_refused(self):
        R = self.R
        self.assertEqual(sorted(R.defs()["engines"]), sorted(self.NINE))
        for name in self.NINE:
            st = R.engine_def(name)["start"]
            self.assertTrue(st["on"], name + " names what makes it run")
            self.assertTrue(all(t["kind"] in R.TRIGGER for t in st["on"]), name)

        def faults(change):
            bad = copy.deepcopy(R.defs())
            change(bad["engines"])
            return R.validate(bad)
        self.assertEqual(R.validate(copy.deepcopy(R.defs())), [])
        self.assertIn("Write: the engine names no start: no trigger makes it run", faults(lambda e: e["Write"].pop("start")))
        self.assertIn("Audit: the engine names no start: no trigger makes it run", faults(lambda e: e["Audit"]["start"].update(on=[])))
        self.assertIn("Plan, start: 'whim' is not a kind of trigger", faults(lambda e: e["Plan"]["start"]["on"].append({"kind": "whim"})))
        self.assertIn("Plan, start: a version trigger names what it is a version of",
                      faults(lambda e: e["Plan"]["start"].update(on=[{"kind": "version"}])))
        self.assertIn("Audit, start: it is triggered by a post and no step of it reads one",
                      faults(lambda e: e["Audit"]["start"]["on"].append({"kind": "post"})))
        self.assertIn("Audit, start: a timer names its period in seconds",
                      faults(lambda e: e["Audit"]["start"]["on"].append({"kind": "timer"})))
        self.assertIn("Check, start: the blocker plan.pages is no gate of an internal system",
                      faults(lambda e: e["Check"]["start"]["unless"].append("plan.pages")))

    def test_45_one_piece_of_code_starts_all_nine_and_names_none_of_them(self):
        import inspect
        R, W = self.R, self.W
        for fn in (R.next_due, R.ready, R.blocked, R.coord_pick, R.coord_busy, R.admit):
            src = inspect.getsource(fn)
            for name in self.NINE:
                self.assertNotIn('"%s"' % name, src.replace('"Coordination", s', ""), "%s names %s" % (fn.__name__, name))
        self.live()
        self.ask("Add a page for the pharmacy")
        ran = [r for r in W.runs(REF) if r.get("slot") and r.get("runtime") == 2 and r["status"] in ("ok", "failed")]
        picked = {(r["slot"], r["answer"]) for r in self.rows("coord.pick")}
        self.assertGreaterEqual(len({r["engine"] for r in ran}), 7, "work engines and internal systems alike")
        for r in ran:
            self.assertIn((r["slot"], r["engine"]), picked, "%s started without its start being read" % r["engine"])
        self.assertTrue(all(r["engine"] == "Coordination" and r["check"]["ok"] for r in self.rows("coord.pick")))

    def test_46_start_and_stop_are_one_signal_to_every_engine(self):
        R, W = self.R, self.W
        W.give_goal(REF, GOAL)
        name, _, _ = R.next_due(REF)
        self.assertEqual(name, "Identity", "an internal system, by a post")
        W.set_stopped(REF, True)
        self.assertEqual(R.next_due(REF), (None, None, "stopped"))
        self.assertEqual(self.idle(), 0, "stopped: nothing starts, whatever its trigger")
        W.set_stopped(REF, False)
        self.idle()
        self.assertTrue(W.versions(REF, "Build"), "started: the line ran by its own triggers, with nobody driving")
        said = [r["what"] for r in W.runs(REF) if r["engine"] == "Identity" and "by the owner" in (r.get("what") or "")]
        self.assertEqual(said, ["stopped by the owner: every engine stops",
                                "started by the owner: every engine looks to its own triggers"])

    def test_47_a_blocker_holds_its_own_engine_and_no_other(self):
        R, W = self.R, self.W
        d = W.dept(REF)
        d["envelopes"]["Write"]["calls"] = 0
        W.save_dept(REF, d)
        W.give_goal(REF, GOAL)
        self.idle()
        self.assertTrue(W.versions(REF, "Site plan") and not W.versions(REF, "Pages"))
        got = R.ready(self.ctx(), "Write")
        self.assertEqual(got, (None, None, "Write is out of its envelope"), "a trigger is live, and its own blocker holds it")
        self.assertIsNone(R.ready(self.ctx(), "Check"), "no trigger of Check's is live")
        self.table(order=["line", "posts", "functions"])
        R.request(REF, "Which page lists the doctors")
        self.assertEqual(R.next_due(REF)[0], "Identity", "held at Write, the department still serves what is ready")

    def test_48_who_goes_first_is_coordinations_table_on_the_record(self):
        R, W = self.R, self.W
        t = W._read(W.ddir(REF) / "coordination.json", None)
        self.assertEqual((t["order"], t["line"], t["by"]), (["posts", "line", "functions"], ["Plan", "Write", "Check", "Publish"], "born"))
        self.live()
        cur = W.latest(REF, "Brief")
        W.add_version(REF, "Brief", W.read_files(REF, "Brief", cur["v"]), [{"art": "Brief", "v": cur["v"]}], "owner",
                      {"ok": True, "notes": ["a test's own version"]})
        R.request(REF, "Which page lists the doctors")
        self.assertEqual(R.next_due(REF)[0], "Identity", "born with: a post waiting for its reader goes first")
        self.table(order=["line", "posts", "functions"])
        self.assertEqual(R.next_due(REF)[0], "Plan", "the table on the record was changed, and the order with it")
        self.table(line=["Plan", "Write", "Check", "Nobody"])
        self.assertEqual(R.coordination(REF)["order"], ["posts", "line", "functions"], "a table with a fault is not read")

    def test_49_who_may_post_is_coordinations_table_and_a_refusal_is_a_row(self):
        R = self.R
        self.assertTrue(R.post(REF, "Audit", "Identity", "inform", {"word": "finding", "claim": "a claim", "severity": "low"}))
        edges = R.coordination(REF)["edges"]
        edges.pop("Audit")
        self.table(edges=edges)
        with self.assertRaises(ValueError) as e:
            R.post(REF, "Audit", "Identity", "inform", {"word": "finding", "claim": "a claim", "severity": "low"})
        self.assertEqual(str(e.exception), "Audit may not post inform to Identity")
        rows = [(r["engine"], r["answer"], r["check"]["ok"]) for r in self.rows("coord.edge") if r["slot"] == "Audit>Identity:inform"]
        self.assertEqual(rows, [("Coordination", "admit", True), ("Coordination", "refuse", True)])

    def test_50_a_time_is_a_trigger_too_once_in_each_period(self):
        R = self.R
        d = copy.deepcopy(R.defs())
        d["engines"]["Audit"]["start"]["on"] = [{"kind": "timer", "every_s": 3600}]
        self.assertEqual(R.validate(d), [])
        R._DEFS["d"] = d
        inp, slot, why = R.ready(self.ctx(now=7200.0), "Audit")
        self.assertEqual((inp, slot, why), ({"timer": 2, "v": 2}, "Audit@timer.2", None))
        self.assertIsNone(R.ready(self.ctx(now=7200.0, done={"Audit@timer.2"}), "Audit"), "once in a period")
        self.assertEqual(R.ready(self.ctx(now=10800.0, done={"Audit@timer.2"}), "Audit")[1], "Audit@timer.3", "and again in the next")

    def test_51_a_trigger_is_delivered_when_it_happens(self):
        R, W = self.R, self.W
        kick = W._MOTOR["kick"] = threading.Event()
        try:
            R.request(REF, "A website for the hospital")
            self.assertTrue(kick.is_set(), "a post wakes the motor at once; no engine waits for a tick")
            kick.clear()
            W.set_stopped(REF, True)
            self.assertTrue(kick.is_set(), "and so does the button")
        finally:
            W._MOTOR["kick"] = None
        W.signal()                                       # with no motor in this process, a signal is a no-op

    def test_52_the_owner_sees_each_engines_start_and_coordinations_table(self):
        R = self.R
        self.live()
        w = R.steps_view(REF, "Write")["start"]
        self.assertEqual(w["on"], ["a new Site plan"])
        self.assertEqual([(b["by"], b["name"]) for b in w["unless"]],
                         [("Identity", R.step_def("identity.gate")[1]["name"]), ("Priority", R.step_def("priority.envelope")[1]["name"]),
                          ("Coordination", "Stop a chain at its limit")])
        self.assertEqual(R.steps_view(REF, "Publish")["start"]["on"], ["a new Build that passed its check"])
        self.assertEqual(R.steps_view(REF, "Adaptation")["start"]["on"], ["a post addressed to it", "a new Live site that passed its check"])
        c = R.steps_view(REF, "Coordination")
        self.assertEqual(c["hears"][0], "What engines share")
        shared = [s["name"] for s in c["steps"] if s["under"] == "What engines share"]
        self.assertEqual(shared, ["Keep one run at a time", "Say who goes first, when several are ready", "Say who may post what to whom",
                                  "Ask an internal system for its verdict", "Close a thread at its bound",
                                  "Raise an alarm for a run past its window"])
        pick = next(s for s in c["steps"] if s["id"] == "coord.pick")
        self.assertEqual((pick["mode"], pick["rung_name"], pick["ran"], pick["evidence"]["pass"]), ("rule", "Code", True, 1.0))
        self.assertEqual(c["table"]["line"], ["Plan", "Write", "Check", "Publish"])
        self.assertIn({"from": "Owner", "act": "request", "to": ["Identity"]}, c["table"]["may_post"])


if __name__ == "__main__":
    unittest.main(verbosity=1)
