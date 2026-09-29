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
        self.tie, self.kind = None, None
        self.holes = False                               # a page that admits what nobody told it (test_69)
        self.broken = []                                 # what Check's rules step reports broken (test_72)
        self.refuse_engines = set()                      # engines Priority's agent refuses when offered (test_94)
        self.same_name = False                           # Setup's agent names a department that already exists (test_95)
        self.rules = {}                                  # words Identity's take reads as a standing rule (test_102)
        self.need = True                                 # whether a born engine's need step says the words ask for its work (test_103)

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
            hole = "<p>Phone: to be confirmed.</p>" if self.holes else ""
            return {"title": page["title"], "body_html": "<section><h1>%s</h1><p>%s</p>%s</section>" % (page["title"], "What a patient needs to know. " * 3, hole)}, 0.03, "model"
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
            idea = prompt.split("THE IDEA: ", 1)[1].split("\n", 1)[0].lower()
            pick = "Do" if "written answer" in idea else None
            hint = ({"name": "Talks List", "does": "keeps the list of my talks up to date", "needs": []} if "talks" in idea else
                    {"name": "Web Facts", "does": "finds on the internet what the hospital does and who its doctors are", "needs": ["internet"]}
                    if "internet" in idea else None)
            return {"reflected": "Let a patient book a visit on the site", "question": "Who confirms the booking?",
                    "shapes": ["a page with the phone number to book", "a form that sends a request", "a live calendar"],
                    "pick": pick, "engine": None if pick else hint}, 0.02, "model"
        if sid.endswith(".make") and sid != "write.page":
            brief = prompt.split("(the Brief):\n", 1)[1].split("\n\nDo it", 1)[0]
            return {"text": "Done, in words: " + " ".join(brief.split())[:160]}, 0.01, "model"
        if sid.endswith(".need"):
            return {"run": bool(self.need), "why": "the words ask for it" if self.need else "the words ask for no new search"}, 0.01, "model"
        if sid == "identity.take":
            words = prompt.split("THE REQUEST: ", 1)[1].split("\n", 1)[0]
            v = self.verdicts.get(words) or ("ask" if "email" in words.lower() else "go")
            unsure = [u.strip() for u in words.split("not sure of:", 1)[1].split(".", 1)[0].split(";")] if "not sure of:" in words else []
            low = words.lower()
            needs = ["internet"] if "internet" in low and any(w in low for w in ("find", "look", "search")) else []
            return {"verdict": v, "why": "judged", "needs": needs, "unsure": unsure, "rule": self.rules.get(words)}, 0.01, "model"
        if sid == "identity.judge":
            return {"verdict": "admit", "why": "the rules allow it"}, 0.01, "model"
        if sid == "priority.bargain":
            if any(("THE ENGINE: %s\n" % n) in prompt for n in self.refuse_engines):
                return {"answer": "reject", "why": "no room for another engine today"}, 0.01, "model"
            return {"answer": "accept", "why": "the envelope has room"}, 0.01, "model"
        if sid == "coord.tie":
            ready = prompt.split("READY NOW: ", 1)[1].split("\n", 1)[0].split(", ")
            return {"answer": self.tie or ready[0], "why": "picked among equals"}, 0.01, "model"
        if sid == "setup.shape":
            words = prompt.split("THE OWNER'S WORDS: ", 1)[1].split("\n", 1)[0]
            org = prompt.split("The owner of ", 1)[1].split(" asks Root", 1)[0]
            kind = self.kind or "website"
            name = org + (" Website" if kind == "website" else " Desk")
            existing = prompt.split("DEPARTMENTS THIS ROOT ALREADY HAS: ", 1)[1].split("\n", 1)[0] if "ALREADY HAS: " in prompt else ""
            if name in existing and not self.same_name:
                name += " 2"                                  # a new department takes a name none of the existing ones has
            return {"name": name, "kind": kind, "goal": words}, 0.02, "model"
        if sid == "audit.judge":
            return {"ok": not self.findings, "findings": list(self.findings)}, 0.02, "model"
        if sid == "check.rules":
            return {"broken": [dict(b) for b in self.broken]}, 0.02, "model"
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

    def test_83_the_work_engines_are_library_templates_and_a_bad_one_is_refused(self):
        """TPL-1 (founder, 2026-09-29): engines come from templates in the Library, one file each with a use case; the
        definitions are assembled from them; a kind names its use case and its functions' template; a template without
        a use case, or a kind naming a template a function lacks, is a fault; a file that is no template refuses the load."""
        R = self.R
        self.assertEqual(sorted(p.name for p in R.TEMPLATES_DIR.glob("*.json")), ["check.json", "do.json", "plan.json", "publish.json", "setup.json", "write.json"])
        e = R.defs()["engines"]
        self.assertEqual(e["Plan"]["from_template"], "engine/plan")
        self.assertTrue(all(e[n].get("use_case") for n in ("Plan", "Write", "Check", "Publish", "Setup", "Do")))
        raw = json.loads((R.Path(R.__file__).parent / "engine_defs" / "website.json").read_text(encoding="utf-8"))
        self.assertNotIn("Plan", raw["engines"], "the file holds the functions, the kinds, the edges and the table; the work engines are the Library's")
        self.assertEqual({k: v["functions_template"] for k, v in raw["kinds"].items()}, {"website": "product-build", "root": "default", "default": "default"})
        bad = copy.deepcopy(R.defs())
        del bad["engines"]["Plan"]["use_case"]
        self.assertIn("Plan: an engine template names its use case", R.validate(bad))
        bad = copy.deepcopy(R.defs())
        bad["kinds"]["website"]["functions_template"] = "nowhere"
        self.assertIn("kinds, website: functions_template names a Library template every function has", R.validate(bad))
        tmp = R.Path(tempfile.mkdtemp(prefix="engine-templates-"))
        (tmp / "plan.json").write_text(json.dumps({"id": "engine/plan", "name": "Plan"}), encoding="utf-8")
        prior = R.TEMPLATES_DIR
        R.TEMPLATES_DIR, R._DEFS["d"] = tmp, None
        R._DEFS.clear()
        try:
            with self.assertRaises(ValueError) as cm:
                R.defs()
            self.assertIn("names an id, a name and a use case", str(cm.exception))
        finally:
            R.TEMPLATES_DIR = prior
            R._DEFS.clear()
            shutil.rmtree(tmp, ignore_errors=True)

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
        soft = {"identity.take", "plan.pages", "write.page", "audit.judge", "coord.tie"}
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

    def test_07_a_department_born_the_old_way_still_runs_the_old_way(self):
        W = self.W
        os.environ["SUTRA_ENGINE_RUNTIME"] = "1"          # the first build's way, kept for departments born before 2026-09-28
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
        for other in ("plan.pages", "write.page", "audit.judge", "priority.bargain", "identity.recognise", "coord.tie"):
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

    def test_69_a_site_that_says_to_be_confirmed_makes_identity_ask_the_owner_for_the_facts_not_a_stamp(self):
        """Found live 2026-09-28 (Human Simulation run 1): twelve 'to be confirmed' on four pages went live and nobody
        asked. Audit names each hole; Identity asks the person for the facts in the chat; a stamp puts nothing right."""
        W, R = self.W, self.R
        self.M.holes = True
        self.M.findings = [{"page": "index.html", "claim": "the page names a founding year", "severity": "high"}]
        self.live()
        facts = [p for p in R.board(REF) if p["src"] == "Identity" and (p.get("payload") or {}).get("word") == "facts"]
        self.assertEqual(len(facts), 1, [(p["src"], (p.get("payload") or {}).get("word")) for p in R.board(REF)])
        line = facts[0]["payload"]["done"]
        self.assertTrue(line.startswith("The site says it does not know 5 things: on "), line)
        self.assertIn("the page says 'Phone: to be confirmed'", line)
        self.assertTrue(line.endswith("Tell me here and I will put them in."), line)
        self.assertEqual(facts[0]["payload"]["holes"], 5, "one hole a page")
        turn = next(t for t in R.chat_view(REF)["turns"] if t["word"] == "facts")
        self.assertEqual(turn["line"], line, "the question is a turn of the chat, whole")
        a = next(a for a in W.asks(REF) if a["kind"] == "finding")
        self.assertIn("names a founding year", a["text"], "what Audit judged still asks for a stamp")
        self.assertNotIn("to be confirmed", a["text"], "a hole is a question, never a stamp")
        self.assertEqual(len([a for a in W.asks(REF) if a["kind"] == "finding"]), 1)
        self.assertIn("asked the owner for 5 facts the site lacks; put a finding to the owner: on Index, the page names a founding year",
                      [r["what"] for r in W.runs(REF)])
        holes = R.placeholders({"a.html": "<p>Opening hours: TBD</p>", "b.html": "<p>Fine.</p>", "c.md": "TBA"})
        self.assertEqual([h["page"] for h in holes], ["a.html"], "every phrase a page uses to say it does not know; not a .md")

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
        self.assertEqual([s["mode"] for s in f["steps"]][:3], ["gate", "gate", "slot"])
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
        self.assertEqual(a["text"], "Your words reach outside the site: an email address, so people will write, call or come. "
                                    "Put them on the site as said? Stamp to go ahead, Refuse to leave them out. Email the new site to every patient",
                         "in the person's words: what reaches outside, and what a stamp does (finding 13)")

    def test_82_a_functions_chat_exists_from_birth_and_is_its_turns_and_thinking(self):
        """Founder, 2026-09-29: a click on a function's Chat "should not start a new chat. It should just show the
        existing chat there." The chat is read from the record: the function's posts, the person's words to it, its
        step rows as thinking. Nothing starts it; a name that is not a function is refused."""
        W, R = self.W, self.R
        self.live()
        ident = R.fn_chat_view(REF, "identity")
        self.assertEqual(ident["fn"], "Identity")
        said = [t for t in ident["turns"] if not t["think"]]
        self.assertEqual(said[0]["src"], "Owner", "the person's goal opens Identity's chat")
        self.assertFalse(ident["turns"][0]["think"], "the words come first, then the thinking they set off, even within one second")
        self.assertEqual(said[0]["line"], GOAL)
        self.assertTrue([t for t in said if t["src"] == "Identity" and "Owner" in t["dst"]], "and Identity answered in it")
        self.assertTrue([t for t in said if t["msg_type"] == "accept-proposal"], "the publish stamp is a turn of it")
        thought = [t for t in ident["turns"] if t["think"]]
        self.assertTrue(thought and all(t["src"] == "Identity" for t in thought), "its own steps are its thinking, nobody else's")
        self.assertEqual([t["at"] for t in ident["turns"]], sorted(t["at"] for t in ident["turns"]), "in time order")
        pr = R.fn_chat_view(REF, "priority")
        self.assertTrue(pr["any"] and all(t["think"] for t in pr["turns"]), "Priority has said nothing to the person: its chat is its thinking")
        W.owner_ask(REF, "Could the careers page come first?", about="fn:priority")
        self.idle()
        pr = R.fn_chat_view(REF, "priority")
        mine = [t for t in pr["turns"] if not t["think"]]
        self.assertEqual((mine[0]["src"], mine[0]["line"]), ("Owner", "Could the careers page come first?"), "words said in Priority's chat are in it")
        self.assertTrue([t for t in mine if t["src"] != "Owner"], "and what came of them, in the same thread")
        self.assertIn("Could the careers page come first?", [t["line"] for t in R.chat_view(REF)["turns"]], "one record: the department's chat has them too")
        with self.assertRaises(ValueError):
            R.fn_chat_view(REF, "board")
        with self.assertRaises(ValueError):
            W.owner_ask(REF, "words", about="fn:board")

    def test_85_the_agents_brief_carries_the_template_the_settings_tab_picked(self):
        """SIM-2 finding 20: a pick on a function's Settings tab reached the screen and never the agent, which read the
        birth copy on the record. The brief reads the pick on the registry, so the next step runs the template picked."""
        W, R = self.W, self.R
        reg = tempfile.mkdtemp(prefix="engine-runtime-picks-")
        prior = os.environ.get("SUTRA_NATIVE_HOME")
        os.environ["SUTRA_NATIVE_HOME"] = reg
        import placement_engine as E
        importlib.reload(E)
        import function_templates as FT
        try:
            ctx = {"ref": REF, "dept": W.dept(REF), "engine": "Priority", "def": R.engine_def("Priority")}
            self.assertNotIn("customer and bank items", R.card(ctx), "born on the Default")
            FT.write_pick(REF, "priority", "priority/money-movement")
            self.assertIn("customer and bank items", R.card(ctx), "the brief follows the pick, not the birth copy")
        finally:
            if prior is None:
                os.environ.pop("SUTRA_NATIVE_HOME", None)
            else:
                os.environ["SUTRA_NATIVE_HOME"] = prior
            importlib.reload(E)
            shutil.rmtree(reg, ignore_errors=True)

    def test_86_an_engine_added_to_a_live_department_runs_on_its_own_trigger(self):
        """TPL-1 slice 2: add_engine, the one write behind the owner's stamp (Identity) and the org.engine ask: a Library
        engine by name on the record, its artifact with it, an envelope, a window, Coordination's line grown; a function
        or an unknown name refused; twice refused; the engine then runs on the next version it reads."""
        W, R = self.W, self.R
        self.live()
        with self.assertRaises(ValueError):
            W.add_engine(REF, "Priority")
        with self.assertRaises(ValueError):
            W.add_engine(REF, "Nowhere")
        out = W.add_engine(REF, "Do")
        d = W.dept(REF)
        self.assertEqual((out["engines"], d["engines"]), (["Do", "Plan", "Write", "Check", "Publish"],) * 2, "it reads the Brief, so it goes first: what it files, the line reads")
        self.assertEqual(d["artifacts"][:2], ["Brief", "Result"], "its artifact right after what it reads; the Live site stays last")
        self.assertIn("Do", d["envelopes"])
        self.assertEqual(R.coordination(REF)["line"][0], "Do", "Coordination's line, on the record, grew")
        with self.assertRaises(ValueError):
            W.add_engine(REF, "Do")
        self.ask("Add a careers page")
        self.assertTrue(W.versions(REF, "Result"), "Do ran on the next Brief and filed a Result")
        self.assertIn("added the engine Do", " ".join(r["what"] for r in W.runs(REF) if r["engine"] == "Identity"))

    def test_87_an_idea_that_fits_a_library_template_becomes_that_engine_on_the_owners_stamp(self):
        """TPL-1 slice 2 (founder, 2026-09-29: "the engines are supposed to be created by the five functions"): an idea is
        shaped and parked by Adaptation, which offers the Library engine whose use case fits to Priority; Priority prices
        it; Identity puts it to the owner in the owner's words; nothing is added before the stamp; on it the engine is on
        the record and runs."""
        W, R = self.W, self.R
        self.live()
        self.ask("What if each ask were answered in one written answer, filed as a result.")
        a = next(x for x in W.asks(REF) if x["kind"] == "engine" and x["status"] == "pending")
        self.assertEqual(a["engine"], "Do")
        self.assertTrue(a["text"].startswith("Add the engine Do to City Care Hospital Website? What it does: reads the brief"), a["text"])
        board = R.board(REF)
        self.assertTrue([p for p in board if p["src"] == "Adaptation" and "Priority" in p["dst"] and p["payload"].get("word") == "engine"], "offered to Priority first")
        self.assertTrue([p for p in board if p["src"] == "Priority" and p["msg_type"] == "accept-proposal" and p["payload"].get("word") == "engine"], "Priority priced it")
        self.assertNotIn("Do", W.dept(REF)["engines"], "nothing is added before the stamp")
        self.stamp("engine")
        self.idle()
        self.assertIn("Do", W.dept(REF)["engines"])
        idea = R.ideas(REF)[-1]
        self.assertEqual((idea.get("engine"), idea.get("state")), ("Do", "built"))
        self.ask("Add a careers page")
        self.assertTrue(W.versions(REF, "Result"), "the added engine runs on the next Brief")

    def test_88_an_idea_that_fits_no_template_is_shaped_from_do_and_born_into_the_library_on_the_stamp(self):
        """TPL-1 slice 2, "created on the fly": no Library engine fits the idea, so Adaptation shapes one from Do with the
        idea as its instruction (the model names it); nothing is born before the stamp; on it the template is in the
        Library with made_by, the definitions still validate, and the engine runs, filing under the Default template."""
        W, R = self.W, self.R
        lib = R.Path(tempfile.mkdtemp(prefix="engine-templates-"))
        shutil.rmtree(lib)
        shutil.copytree(R.TEMPLATES_DIR, lib)
        prior = R.TEMPLATES_DIR
        R.TEMPLATES_DIR = lib
        R._DEFS.clear()
        try:
            self.live()
            self.ask("What if the department kept a list of my talks, updated whenever I give one.")
            a = next(x for x in W.asks(REF) if x["kind"] == "engine" and x["status"] == "pending")
            self.assertEqual(a["engine"], "Talks List", "named by the model")
            self.assertIn("What it does: keeps the list of my talks up to date.", a["text"])
            self.assertFalse((lib / "talks-list.json").exists(), "nothing born before the stamp")
            self.stamp("engine")
            self.idle()
            t = json.loads((lib / "talks-list.json").read_text(encoding="utf-8"))
            self.assertEqual((t["name"], t["reads"], t["writes"], t["made_by"]["dept"]), ("Talks List", "Brief", "Talks List", REF))
            self.assertEqual([s["id"] for s in t["steps"]], ["talks-list.read", "talks-list.need", "talks-list.make", "talks-list.file"])
            need = next(s for s in t["steps"] if s["id"] == "talks-list.need")
            self.assertEqual((need["only_if"], need["may_end"]), ("talks-list.read.previous", True), "the condition follows the ids")
            self.assertIn("Talks List", R.defs()["engines"])
            self.assertEqual(R.validate(R.defs()), [])
            d = W.dept(REF)
            self.assertIn("Talks List", d["engines"])
            self.assertIn("Talks List", d["artifacts"])
            self.ask("Add a careers page")
            v = W.versions(REF, "Talks List")
            self.assertTrue(v and v[-1]["check"]["ok"], "the shaped engine ran on the next Brief and filed under the Default template")
            self.assertIn("THIS ENGINE'S INSTRUCTION", [p for s, p in self.M.prompts if s == "talks-list.make"][-1])
        finally:
            R.TEMPLATES_DIR = prior
            R._DEFS.clear()
            shutil.rmtree(lib, ignore_errors=True)

    def test_89_words_that_ask_for_the_internet_get_an_engine_that_reaches_it_and_the_line_builds_from_what_it_filed(self):
        """Founder, 2026-09-29: "I want the data to be fetched from the internet by the department, not that we give it";
        "obey the prompts so it builds everything as a user, as a product". As a user: the words ask for the internet;
        no engine reaches it, so Identity hands them to Adaptation instead of filing an ask that Write cannot meet; the
        engine shaped from the idea carries the model's web tools; on the stamp it runs on the Brief at once, files under
        its own name, and the person is told; the next words make Plan and Write build from what it filed."""
        W, R = self.W, self.R
        lib = R.Path(tempfile.mkdtemp(prefix="engine-templates-"))
        shutil.rmtree(lib)
        shutil.copytree(R.TEMPLATES_DIR, lib)
        prior = R.TEMPLATES_DIR
        R.TEMPLATES_DIR = lib
        R._DEFS.clear()
        try:
            self.live()
            briefs = len(W.versions(REF, "Brief"))
            self.ask("Find on the internet what the hospital does and who its doctors are, and build only from that.")
            self.assertEqual(len(W.versions(REF, "Brief")), briefs, "words no engine can meet are not filed as an ask")
            lines = [t["line"] for t in R.chat_view(REF)["turns"]]
            self.assertTrue(any("no engine of mine reaches the internet yet" in line for line in lines), lines[-3:])
            a = next(x for x in W.asks(REF) if x["kind"] == "engine" and x["status"] == "pending")
            self.assertEqual(a["engine"], "Web Facts")
            self.stamp("engine")
            self.idle()
            t = json.loads((lib / "web-facts.json").read_text(encoding="utf-8"))
            make = next(s for s in t["steps"] if s.get("prompt"))
            self.assertEqual((make["tools"], make["timeout_s"]), (["WebSearch", "WebFetch"], 600), "the idea asks for the internet: the engine reaches it")
            self.assertEqual(W.dept(REF)["engines"][0], "Web Facts", "it reads the Brief, so it goes first")
            v = W.versions(REF, "Web Facts")
            self.assertTrue(v, "it ran on the Brief at once, without new words")
            self.assertIn("You have web search and web fetch", [p for s, p in self.M.prompts if s == "web-facts.make"][-1])
            lines = [t["line"] for t in R.chat_view(REF)["turns"]]
            self.assertIn("Web Facts v1 is filed.", lines, "the person is told what their engine filed")
            self.ask("Build the site from what you found.")
            plan = [p for s, p in self.M.prompts if s == "plan.pages"][-1]
            self.assertIn("WHAT THE DEPARTMENT'S OWN ENGINES FILED", plan)
            self.assertIn("Web Facts (v", plan)
            page = [p for s, p in self.M.prompts if s == "write.page"][-1]
            self.assertIn("WHAT THE DEPARTMENT'S OWN ENGINES FILED", page)
            self.assertEqual(t["needs"], ["internet"], "what the agent said it needs is on the template; code mapped it to tools")
        finally:
            R.TEMPLATES_DIR = prior
            R._DEFS.clear()
            shutil.rmtree(lib, ignore_errors=True)

    def test_91_what_the_person_is_not_sure_of_stays_out_and_is_asked_about_before_anything_is_built_from_it(self):
        """Run 1 finding 22 (2026-09-29): two facts the person said they were not sure of became a page and went live; the
        question came after. Identity's own take step names them; the Brief carries them as not confirmed; the person is
        asked in the chat at once; their answer is the facts (finding 16's flow) and the line builds with them."""
        W, R = self.W, self.R
        W.give_goal(REF, GOAL + " The internet also says two things I am not sure of: Angel One; a University of Tokyo profile.")
        self.idle()
        brief = W.read_files(REF, "Brief", 1).get("brief.md", "")
        self.assertIn("Not confirmed (the owner is not sure; leave these out until the owner confirms them): Angel One; a University of Tokyo profile.", brief)
        turns = R.chat_view(REF)["turns"]
        asked = [t for t in turns if t.get("word") == "facts"]
        self.assertTrue(asked and asked[0]["line"].startswith("You said you are not sure of: Angel One; a University of Tokyo profile. Say which are right"), [t["line"] for t in turns])
        self.assertLess([i for i, t in enumerate(turns) if t.get("word") == "facts"][0], len(turns), "asked before the first publish ask, not after the site is live")
        self.assertIn("Not confirmed", [p for s, p in self.M.prompts if s == "plan.pages"][-1], "Plan is told what stays out")
        self.assertFalse([t for t in turns if t.get("word") == "publish" and t["n"] < asked[0]["n"]], "the question came before the publish ask")

    def test_92_the_same_thought_twice_in_a_row_is_one_line_of_a_functions_chat(self):
        """Run 1 finding 26: 'Gate the effect by rule: admit' three times in a row in Identity's chat. Identical neighbouring
        thinking lines fold into one, the last one's time; different ones, and the person's words, are untouched."""
        W, R = self.W, self.R
        self.live()
        self.ask("Add a careers page")
        turns = R.fn_chat_view(REF, "identity")["turns"]
        thinks = [t["line"] for t in turns if t["think"]]
        self.assertTrue(any("Gate the effect by rule" in x for x in thinks), "the gate rows are there")
        for a, b in zip(turns, turns[1:]):
            self.assertFalse(a["think"] and b["think"] and a["line"] == b["line"], "twice in a row: " + a["line"])
        raw = [r for r in R.step_rows(REF) if r["engine"] == "Identity" and r.get("mode") == "gate" and r.get("answer") == "admit"]
        self.assertGreater(len(raw), len([x for x in thinks if x == "Gate the effect by rule: admit"]), "the record keeps every row; the chat folds")

    def test_93_a_stamp_on_an_ask_that_needs_the_internet_shapes_the_engine_and_files_no_brief_ask(self):
        """Run 2 finding 29 (2026-09-29): Identity's agent said the words reach outside the site and asked for a stamp;
        the stamp filed them as a Brief ask and the site came back 'to be confirmed'. What the ask needs rides on the
        ask row, the ask says what a stamp does here, and the stamp hands the words to Adaptation."""
        W, R = self.W, self.R
        self.live()
        words = "Find on the internet what the hospital does and who its doctors are, and build only from that."
        self.M.verdicts[words] = "ask"
        briefs = len(W.versions(REF, "Brief"))
        self.ask(words)
        a = next(x for x in W.asks(REF) if x["kind"] == "request" and x["status"] == "pending")
        self.assertEqual(a["needs"], ["internet"], "what the ask needs is on its row")
        self.assertTrue(a["text"].startswith("Your words need internet, which no engine of mine reaches"), a["text"])
        self.assertIn("Stamp to have one shaped and put to you", a["text"])
        self.assertNotIn("Put them on the site as said", a["text"], "not the email wording (finding 30)")
        self.stamp("request")
        self.idle()
        self.assertEqual(len(W.versions(REF, "Brief")), briefs, "the stamp filed no Brief ask")
        lines = [t["line"] for t in R.chat_view(REF)["turns"]]
        self.assertTrue(any("no engine of mine reaches internet yet; Adaptation is shaping one" in line for line in lines), lines[-3:])
        e = next(x for x in W.asks(REF) if x["kind"] == "engine" and x["status"] == "pending")
        self.assertEqual(e["engine"], "Web Facts", "and the engine ask followed")

    def test_94_priority_is_shown_the_engine_offer_and_its_refusal_is_told(self):
        """Run 2 findings 32 and 33: Priority's agent was shown an engine offer as a rung proposal's empty fields and
        refused it; the refusal stayed on the board. The bargain prompt carries the offer; a refusal is a turn of the chat."""
        W, R = self.W, self.R
        self.live()
        self.ask("What if the department kept a list of my talks, updated whenever I give one.")
        prompt = [p for s, p in self.M.prompts if s == "priority.bargain"][-1]
        for line in ("THE ENGINE: Talks List\n", "WHAT IT DOES: keeps the list of my talks up to date", "WHAT IT NEEDS: nothing beyond the model", "WHAT IT COSTS: "):
            self.assertIn(line, prompt)
        self.assertTrue([x for x in W.asks(REF) if x["kind"] == "engine"], "shown the offer, Priority granted it and the ask followed")
        self.M.refuse_engines = {"Web Facts"}
        self.ask("What if you found on the internet what the hospital does and who its doctors are.")
        prompt = [p for s, p in self.M.prompts if s == "priority.bargain"][-1]
        self.assertIn("WHAT IT NEEDS: internet", prompt)
        lines = [t["line"] for t in R.chat_view(REF)["turns"]]
        self.assertTrue(any(line.startswith("Priority refused the engine Web Facts: no room for another engine today. The idea stays parked") for line in lines), lines[-3:])
        self.assertFalse([x for x in W.asks(REF) if x["kind"] == "engine" and x["engine"] == "Web Facts"], "nothing put to the owner")
        self.assertEqual(R.ideas(REF)[-1].get("priced"), "refused")

    def test_90_a_step_with_tools_hands_them_to_the_model_and_nothing_else(self):
        """The model reaches the internet through its own web tools and nothing else: a step names them, model_json passes
        exactly those, and a name outside the closed list is dropped; a step naming an unknown tool refuses the load."""
        W, R = self.W, self.R
        import types
        seen = {}

        def fake(args, **kw):
            seen["args"] = list(args)
            return types.SimpleNamespace(stdout=json.dumps({"result": "{\"text\": \"ok\"}", "total_cost_usd": 0.01}), returncode=0)

        real = W.subprocess.run
        W.subprocess.run = fake
        try:
            out, usd, how = W.model_json("say ok", timeout=5, tools=["WebSearch", "WebFetch", "Bash"])
            self.assertEqual((out, how), ({"text": "ok"}, "model"))
            a = seen["args"]
            self.assertEqual(a[a.index("--tools") + 1:a.index("--tools") + 3], ["WebSearch", "WebFetch"])
            self.assertEqual(a[a.index("--allowedTools") + 1:a.index("--allowedTools") + 3], ["WebSearch", "WebFetch"])
            self.assertNotIn("Bash", a)
            W.model_json("say ok", timeout=5)
            self.assertNotIn("--tools", seen["args"], "a step with no tools hands the model none")
        finally:
            W.subprocess.run = real
        bad = copy.deepcopy(R.defs())
        bad["engines"]["Do"]["steps"][1]["tools"] = ["Bash"]
        self.assertTrue(any("tools are a list of WebSearch, WebFetch" in f for f in R.validate(bad)))


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


class TestTheRulingsOfTheAfternoon(Base):
    """The founder's rulings of 2026-09-28, 13:35, each as a check that can fail: the host is asked; the limits come
    from Priority's template and the owner sets a department's own; record and versions are one core deployed per
    thing; Coordination has its own agent and its steps."""

    def test_54_the_first_publish_asks_where_the_site_is_served_from_and_keeps_the_answer(self):
        W = self.W
        W.give_goal(REF, GOAL)
        self.idle()
        a = next(x for x in W.asks(REF) if x["kind"] == "publish" and x["status"] == "pending")
        self.assertIn("served from", a["text"])
        self.assertIn(W.HOST_DEFAULT, a["text"], "the ask names the default")
        W.set_host(REF, "https://cityclinic.example")
        self.stamp("publish")
        self.idle()
        self.assertEqual(W.dept(REF)["host"], "https://cityclinic.example", "the answer stays on the record")
        self.assertIn("cityclinic.example", " ".join(W.latest(REF, "Live site")["check"]["notes"]), "and Publish read it")
        self.assertTrue(any(r["engine"] == "Identity" and "served from" in (r.get("what") or "") for r in W.runs(REF)), "the answer is a row")
        ref2 = "dref-host0002"
        W.create(ref2, "Second Website", None)
        W.give_goal(ref2, GOAL)
        W.run_until_idle(ref2, limit=200)
        a2 = next(x for x in W.asks(ref2) if x["kind"] == "publish" and x["status"] == "pending")
        W.decide_ask(ref2, a2["id"], True)
        W.run_until_idle(ref2, limit=200)
        self.assertEqual(W.dept(ref2)["host"], W.HOST_DEFAULT, "a plain stamp takes the default")
        self.assertIn(W.HOST_DEFAULT, " ".join(W.latest(ref2, "Live site")["check"]["notes"]))

    def test_55_the_limits_come_from_priorities_template_and_the_owner_sets_a_departments_own(self):
        W, R = self.W, self.R
        t = R.priority_template()
        self.assertEqual(set(t), {"calls", "usd", "work_calls"}, "the template names the two limits and the work factor")
        d = W.dept(REF)
        self.assertEqual(d["envelopes"]["Identity"], {"calls": t["calls"], "usd": t["usd"]})
        self.assertEqual(d["envelopes"]["Write"], {"calls": t["work_calls"] * t["calls"], "usd": t["usd"]})
        self.assertTrue(all(d["envelopes"][s] == {"calls": t["calls"], "usd": t["usd"]} for s in W.SYSTEMS))
        env = W.set_envelope(REF, "Write", usd=0.0)
        self.assertEqual(env, {"calls": t["work_calls"] * t["calls"], "usd": 0.0}, "one number changed, the other kept")
        self.assertEqual(W.dept(REF)["envelopes"]["Write"]["usd"], 0.0)
        with self.assertRaises(ValueError):
            W.set_envelope(REF, "Nobody", calls=1)
        self.assertTrue(any(r["engine"] == "Priority" and "set Write's envelope" in (r.get("what") or "") for r in W.runs(REF)), "the change is a row")
        W.give_goal(REF, GOAL)
        self.idle()
        self.assertEqual(W.versions(REF, "Pages"), [], "Write never ran")
        self.assertTrue(any(a["kind"] == "envelope" and a["engine"] == "Write" for a in W.asks(REF)), "Priority's gate holds Write at the owner's limit and asks")
        v = R.steps_view(REF, "Priority")
        self.assertEqual({x["engine"] for x in v["limits"]}, {e[0] for e in W.ENGINES} | set(W.SYSTEMS), "the card reads every engine's limits")
        self.assertEqual(next(x for x in v["limits"] if x["engine"] == "Write")["usd"], 0.0)

    def test_56_record_and_versions_are_one_core_deployed_per_thing_and_a_new_kind_needs_no_new_code(self):
        W, R = self.W, self.R
        import record
        import versions as VERS
        names = [e[0] for e in W.ENGINES] + list(W.SYSTEMS) + list(W.ARTIFACTS)
        for mod in (record, VERS):
            src = Path(mod.__file__).read_text(encoding="utf-8")
            for word in names:
                self.assertNotRegex(src, r"\b%s\b" % re.escape(word), "%s names %s" % (mod.__name__, word))
        row = W.add_version(REF, "Newsletter", {"issue-1.md": "# Issue 1"}, [{"art": "Brief", "v": 0}], "r-new", {"ok": True, "notes": []})
        self.assertEqual(row["v"], 1)
        self.assertEqual(W.latest(REF, "Newsletter")["v"], 1)
        self.assertEqual(W.read_files(REF, "Newsletter", 1), {"issue-1.md": "# Issue 1"})
        self.assertTrue((W.ddir(REF) / "artifacts" / "newsletter" / "versions.json").is_file(), "kept with the thing, in its own folder")
        R._append(REF, "steps.jsonl", {"id": "s-new", "engine": "Digest", "step": "digest.write", "by": "code", "status": "ok"})
        self.assertEqual([r["engine"] for r in R.step_rows(REF) if r["id"] == "s-new"], ["Digest"], "a new engine's row, through the core alone")
        self.live()
        for art in W.ARTIFACTS:
            self.assertTrue(W.versions(REF, art), art)
            for v in W.versions(REF, art):
                self.assertEqual(set(v), {"v", "at", "made_from", "run", "check", "note"}, "%s reads the same as every other thing" % art)

    def test_57_coordination_has_its_own_agent_and_its_steps(self):
        W, R = self.W, self.R
        e = R.engine_def("Coordination")
        steps = R.all_steps("Coordination")
        self.assertGreaterEqual(len(steps), 8, "various steps")
        self.assertEqual({s["id"].split(".")[0] for s in steps}, {"coord"})
        self.assertTrue(R.card({"def": e, "dept": W.dept(REF), "engine": "Coordination"})
                        .startswith("You are the agent of Coordination, one engine of the department"), "its own agent")
        v = R.steps_view(REF, "Coordination")
        self.assertEqual(len(v["steps"]), len(steps))
        self.assertIn("What engines share", v["hears"])
        soft = [s["id"] for s in v["steps"] if s["soft"]]
        self.assertEqual(soft, ["coord.tie"], "one step is its agent's: who goes first among equals; the rest are code")
        self.assertTrue(all(s["rung"] == "C2" for s in v["steps"] if s["id"] != "coord.tie"))


class TestOrganicRootAndShape(Base):
    """The founder's rulings of 2026-09-28, ~15:00: no department is born the old way; one Root for one structure, and
    Root spawns every department; every unit starts and ends with code; Coordination has an agent."""

    def test_58_a_department_is_born_on_the_runtime_with_no_switch(self):
        W = self.W
        os.environ.pop("SUTRA_ENGINE_RUNTIME", None)
        ref = "dref-organic001"
        d, _ = W.create(ref, "Organic Website", None)
        self.assertEqual(d["runtime"], 2, "organic only: the runtime, with nothing set")
        self.assertIsNotNone(W._runtime(ref))
        self.assertTrue((W.ddir(ref) / "coordination.json").is_file(), "born with Coordination's table")
        self.assertEqual(W.engines_of(d), (("Plan", "Brief", "Site plan", "model"), ("Write", "Site plan", "Pages", "model"),
                                           ("Check", "Pages", "Build", "model"), ("Publish", "Build", "Live site", "code")),
                         "Check is code around one model step, which runs only when the person has stamped a rule (finding 12)")
        os.environ["SUTRA_ENGINE_RUNTIME"] = "1"
        with self.assertRaises(ValueError):
            W.create("dref-organic002", "Old Root", None, kind="root")       # only a website department is born the old way

    def test_59_every_unit_starts_and_ends_with_code_and_one_that_does_not_is_refused(self):
        R = self.R
        d = R.defs()
        for name, e in d["engines"].items():
            units = [("steps", e.get("steps") or [])] + [(h["name"], h["steps"]) for h in e.get("on") or []]
            for uname, steps in units:
                if not steps:
                    continue
                for s in (steps[0], steps[-1]):
                    self.assertEqual((s["born"], bool(s.get("code")), bool(s.get("prompt"))), ("C2", True, False), "%s, %s: %s" % (name, uname, s["id"]))
        self.assertEqual([s["id"] for s in next(h for h in d["engines"]["Identity"]["on"] if h["name"] == "Give a verdict")["steps"]],
                         ["identity.hear", "identity.judge", "identity.verdict"])
        self.assertEqual([s["id"] for s in d["engines"]["Coordination"]["steps"]], ["coord.ready", "coord.tie", "coord.record"])
        bad = json.loads(json.dumps(d))
        bad["engines"]["Priority"]["on"][0]["steps"].pop(0)              # the unit would start with its agent
        faults = R.validate(bad)
        self.assertTrue(any("Priority, Answer a proposal: a unit starts with a step by code" in f for f in faults), faults)
        bad = json.loads(json.dumps(d))
        bad["kinds"]["root"]["line"] = ["Identity"]
        self.assertTrue(any("kinds, root: Identity is not a work engine" in f for f in R.validate(bad)))

    def test_60_coordinations_agent_says_who_goes_first_when_several_are_ready(self):
        W, R = self.W, self.R
        self.M.tie = "Audit"
        self.live()                                       # after the live site, Adaptation and Audit are ready at once
        ties = [r for r in self.rows("coord.tie")]
        self.assertTrue(ties, "Coordination's agent was asked")
        self.assertEqual({r["by"] for r in ties}, {"model"})
        self.assertEqual({r["agent"] for r in ties}, {"Coordination"}, "by its own agent")
        self.assertTrue(all(r["answer"] == "Audit" for r in ties), "and its word was taken")
        ready_rows = self.rows("coord.ready")
        self.assertTrue(all(r["by"] == "code" for r in ready_rows) and all(r["by"] == "code" for r in self.rows("coord.record")),
                        "the unit starts and ends with code")
        runs = [r for r in W.runs(REF) if r["engine"] in ("Adaptation", "Audit") and r.get("slot", "").endswith("live-site.v1")]
        self.assertEqual(runs[0]["engine"], "Audit", "Audit went first, as the agent said")
        v = R.steps_view(REF, "Coordination")
        tie = next(s for s in v["steps"] if s["id"] == "coord.tie")
        self.assertEqual((tie["rung"], tie["soft"], tie["last"]["by"]), ("C0", True, "model"))

    def test_61_root_spawns_a_department_from_the_owners_words_an_ask_and_a_stamp(self):
        W, R = self.W, self.R
        reg = tempfile.mkdtemp(prefix="engine-runtime-registry-")
        prior = {k: os.environ.get(k) for k in ("SUTRA_NATIVE_HOME", "SUTRA_UI_PROPOSALS")}
        os.environ["SUTRA_NATIVE_HOME"] = os.path.join(reg, "registry")
        os.environ["SUTRA_UI_PROPOSALS"] = os.path.join(reg, "proposals")
        try:
            import founding                               # puts the plugin's lib on the path
            import placement_engine as E
            importlib.reload(E)
            import proposals
            importlib.reload(proposals)
            importlib.reload(founding)
            if not E.active_roots(E.load_domains()):
                E.mint_domain(None, "Sutra", ["Sutra"], "T-local", origin="operator-request")
            out = founding.found_structure("Meadow Clinic")
            root = out["root"]
            rd = W.dept(root)
            self.assertEqual((rd["kind"], rd["runtime"], out["created"]), ("root", 2, True))
            self.assertEqual(W.engines_of(rd), (("Setup", "Request", "Department", "model"),))
            self.assertEqual(R.coordination(root)["line"], ["Setup"], "Coordination's table is born with Root's line")
            self.assertEqual(founding.found_structure("Meadow Clinic")["root"], root, "one Root for one structure")
            self.assertFalse(founding.found_structure("Meadow Clinic")["created"])
            other = founding.found_structure("Harbor Dental")
            self.assertNotEqual(other["root"], root, "two structures, two Roots")
            self.assertEqual(len(founding.roots()), 2)
            words = "Start a website department for Meadow Clinic: what we treat, our doctors, how to book."
            W.owner_ask(root, words)
            W.run_until_idle(root, limit=200)
            self.assertEqual(len(W.versions(root, "Request")), 1, "Identity filed the request")
            a = next(x for x in W.asks(root) if x["kind"] == "setup" and x["status"] == "pending")
            self.assertIn("Set up a department", a["text"])
            self.assertEqual(W.versions(root, "Department"), [], "nothing is set up before the stamp: Root's rule")
            W.decide_ask(root, a["id"], True)
            W.run_until_idle(root, limit=200)
            dep = W.latest(root, "Department")
            self.assertIsNotNone(dep, "Root's engine filed the department")
            child = next(d for d in W.list_depts() if d.get("parent") == root)
            self.assertEqual((child["kind"], child["runtime"], child["name"]), ("website", 2, "Meadow Clinic Website"))
            self.assertEqual(child["root"], root)
            self.assertEqual(child["templates"]["identity"], "identity/product-build", "its functions' templates from the Library")
            W.run_until_idle(child["ref"], limit=200)
            self.assertTrue(W.versions(child["ref"], "Site plan"), "the child ran its goal")
            self.assertTrue(any(x["kind"] == "publish" for x in W.asks(child["ref"])), "and asks before its first publish")
            rows = {r["step"]: r["by"] for r in R.step_rows(root) if r["engine"] == "Setup"}
            self.assertEqual(rows, {"setup.read": "code", "setup.shape": "model", "setup.make": "code", "setup.file": "code"})
            acts = [(p["src"], p["dst"][0], p["msg_type"]) for p in R.board(root)]
            self.assertEqual(acts[:4], [("Owner", "Identity", "request"), ("Identity", "Owner", "inform"),
                                        ("Identity", "Owner", "request"), ("Owner", "Identity", "accept-proposal")])
            self.assertEqual(R.steps_view(root, "Setup")["steps"][1]["last"]["by"], "model")
        finally:
            for k, v in prior.items():
                if v is None:
                    os.environ.pop(k, None)
                else:
                    os.environ[k] = v
            shutil.rmtree(reg, ignore_errors=True)


class TestOperableArtifacts(Base):
    """Founder, 2026-09-28: artifacts are operable: a template in the Library with its own checks, its writer, when it
    counts, and its operations; a version filed runs the artifact's own check; apps are templates too."""

    def test_62_every_artifact_has_a_template_the_check_runs_at_filing_and_a_stranger_is_refused(self):
        W, R = self.W, self.R
        import artifacts as A
        d = R.defs()
        named = {a for k in d["kinds"].values() for a in k["artifacts"]} | {e[key] for e in d["engines"].values() for key in ("reads", "writes") if e.get(key)}
        self.assertEqual(named - set(A.templates()), set(), "every artifact the definitions name has a template")
        self.assertEqual({t["kind"] for t in A.apps()}, {"app"})
        self.assertEqual([t["name"] for t in A.apps()], ["Human Sutra"], "an app is a template too")
        for t in A.templates().values():
            self.assertTrue(t.get("checks") or t["kind"] == "app", t["name"])
            for op in t.get("operations") or []:
                self.assertIn(op, d["engines"], "%s names an engine that exists" % t["name"])
        self.assertEqual(A.get("Live site")["counts_after"], "stamp")
        self.assertEqual(A.get("Live site")["operations"], ["Adaptation", "Audit"], "the artifact's own actions are engines it names")
        # an artifact the Library has no template of its own for gets the Default, text checked as text (TPL-1, founder
        # 2026-09-29: "there is a default one for artifacts also"); it used to be refused
        bad = json.loads(json.dumps(d))
        bad["engines"]["Plan"]["writes"] = "Sitemap"
        self.assertFalse(any("Sitemap" in f for f in R.validate(bad)), R.validate(bad))
        self.assertIsNone(A.get("Sitemap"), "no template of its own")
        self.assertEqual(A.check("Sitemap", {"sitemap.xml": "<urlset/>"}, default=True)["ok"], True, "an artifact the department names: the Default")
        self.assertEqual(A.check("Sitemap", {"sitemap.xml": " "}, default=True)["ok"], False, "the Default still checks: text")
        bad = json.loads(json.dumps(d))
        bad["engines"]["Audit"]["start"]["on"] = [{"kind": "version", "of": "Pages", "checked": True}]
        self.assertTrue(any("Audit: runs on a new Pages" in f for f in R.validate(bad)))
        # the artifact's own check at filing: a good version passes, a bad one is filed and never read as passed
        good = W.add_version(REF, "Site plan", {"site-plan.json": json.dumps({"pages": [{"slug": "index"}]})}, [], "r-t", {"ok": True, "notes": ["by the engine"]})
        self.assertTrue(good["check"]["ok"])
        self.assertIn("every page has a slug", good["check"]["notes"])
        badv = W.add_version(REF, "Site plan", {"site-plan.json": json.dumps({"pages": []})}, [], "r-t", {"ok": True, "notes": ["by the engine"]})
        self.assertFalse(badv["check"]["ok"], "the artifact refused what the engine passed")
        self.assertEqual(W.latest(REF, "Site plan", passed=True)["v"], good["v"], "the failed version is never read as passed")
        self.assertEqual(len(W.versions(REF, "Site plan")), 2, "but it is filed")
        self.assertIsNone(A.check("Table: identity.take", {"table.json": "{}"}), "a thing with no template has no artifact check")
        self.live()
        for art in ("Brief", "Site plan", "Pages", "Build", "Live site"):
            self.assertTrue(W.latest(REF, art)["check"]["ok"], art + " passes its own check in a real run")
        v = A.view("Site plan")
        self.assertEqual((v["written_by"], v["operations"], v["counts_after"]), (["Plan"], ["Write"], "filing"))


class TestTheFrontDoor(Base):
    """The person speaks with Root (founder, 2026-09-28): Root's Identity hands his words to the department they are about,
    the department's answers come back onto Root's board, and a stamp, Stop and Start go the same way."""

    def test_84_root_sets_up_a_department_for_any_goal_the_default_line_when_no_kind_fits(self):
        """TPL-1 (founder, 2026-09-29): the words to Root pick the kind whose use case fits; words that fit no kind get
        the default kind: one Do engine that files a Result for each ask, the default function templates; the record
        carries the line and the artifacts, and everything reads the record."""
        W, R = self.W, self.R
        root, child = self.structure()
        import function_templates as FT
        self.assertEqual(W.dept(child)["engines"], ["Plan", "Write", "Check", "Publish"], "a website goal: the website line, on the record")
        self.assertEqual(FT.picked(child)["priority"], "priority/product-build")
        self.M.kind = "default"                              # Setup's agent picks the kind by use case; the harness stands in for it
        W.owner_ask(root, "Start a new department: answer the letters patients send about our fees, in plain words, every day.")
        W.run_until_idle(root, limit=200)
        a = next(x for x in W.asks(root) if x["kind"] == "setup" and x["status"] == "pending")
        W.decide_ask(root, a["id"], True)                  # Root's rule: a new department is stamped by the owner
        W.run_until_idle(root, limit=200)
        kids = [d for d in W.list_depts() if d.get("parent") == root]
        self.assertEqual(len(kids), 2, "a second department under the same Root")
        other = [d for d in kids if d["ref"] != child][0]
        self.assertEqual((other["kind"], other["engines"], other["artifacts"]), ("default", ["Do"], ["Brief", "Result"]))
        self.assertEqual(FT.picked(other["ref"])["priority"], "priority/default", "the default kind runs the default function templates")
        self.assertEqual([e[0] for e in W.engines_of(other)], ["Do"], "the line is read from the record")
        self.assertEqual(R.coordination(other["ref"])["line"], ["Do"], "and so is Coordination's table")
        W.run_until_idle(other["ref"], limit=200)
        self.assertTrue(W.versions(other["ref"], "Result"), "Do answered the Brief and filed the Result")
        lines = [t["line"] for t in R.chat_view(other["ref"])["turns"]]
        self.assertTrue(any(line.startswith("Result v1 is filed") for line in lines), lines)
        self.assertFalse(any("live" in line for line in lines), "nothing went live: a Result is filed")

    def test_95_a_second_department_takes_a_new_name_and_an_existing_name_is_said_back_with_the_words_handed_on(self):
        """Run 2 finding 28 (2026-09-29): a second department was stamped, Setup shaped the name of the one that existed,
        made nothing and said nothing. Setup's agent is told which names this Root has; when it names one anyway, the
        person is told and the words go to that department."""
        W, R = self.W, self.R
        root, child = self.structure()
        W.owner_ask(root, "Start a new department: a second website for Meadow Clinic, for its pharmacy.")
        W.run_until_idle(root, limit=200)
        a = next(x for x in W.asks(root) if x["kind"] == "setup" and x["status"] == "pending")
        self.assertTrue(a["text"].startswith("Set up a department for: Start a new department: a second website for Meadow Clinic, for its pharmacy."), a["text"])
        W.decide_ask(root, a["id"], True)
        W.run_until_idle(root, limit=200)
        kids = [d for d in W.list_depts() if d.get("parent") == root]
        self.assertEqual(sorted(d["name"] for d in kids), ["Meadow Clinic Website", "Meadow Clinic Website 2"], "told the names it has, the agent gave a new one")
        self.assertIn("Meadow Clinic Website", [p for s, p in self.M.prompts if s == "setup.shape"][-1].split("ALREADY HAS: ", 1)[1])
        self.M.same_name = True
        before = len(R.board(child))
        W.owner_ask(root, "Start a new department: a third website for Meadow Clinic.")
        W.run_until_idle(root, limit=200)
        a = next(x for x in W.asks(root) if x["kind"] == "setup" and x["status"] == "pending")
        W.decide_ask(root, a["id"], True)
        W.run_until_idle(root, limit=200)
        self.assertEqual(len([d for d in W.list_depts() if d.get("parent") == root]), 2, "no third department: the name exists")
        lines = [t["line"] for t in R.chat_view(root)["turns"]]
        self.assertTrue(any(line.startswith("Meadow Clinic Website already exists; your words were handed to it") for line in lines), lines[-3:])
        handed = [p for p in R.board(child)[before:] if p["src"] == "Root" and "Identity" in p["dst"]]
        self.assertTrue(handed and "a third website" in (handed[-1]["payload"].get("words") or ""), "and the words reached that department")

    def structure(self, org="Meadow Clinic"):
        reg = tempfile.mkdtemp(prefix="engine-runtime-front-")
        self.prior_front = {k: os.environ.get(k) for k in ("SUTRA_NATIVE_HOME", "SUTRA_UI_PROPOSALS")}
        os.environ["SUTRA_NATIVE_HOME"] = os.path.join(reg, "registry")
        os.environ["SUTRA_UI_PROPOSALS"] = os.path.join(reg, "proposals")
        self.addCleanup(self._unstructure, reg)
        import founding
        import placement_engine as E
        importlib.reload(E)
        import proposals
        importlib.reload(proposals)
        importlib.reload(founding)
        if not E.active_roots(E.load_domains()):
            E.mint_domain(None, "Sutra", ["Sutra"], "T-local", origin="operator-request")
        root = founding.found_structure(org)["root"]
        self.W.owner_ask(root, "Start a website department for %s: what we treat, our doctors, how to book." % org)
        self.W.run_until_idle(root, limit=200)
        a = next(x for x in self.W.asks(root) if x["kind"] == "setup" and x["status"] == "pending")
        self.W.decide_ask(root, a["id"], True)
        self.W.run_until_idle(root, limit=200)
        child = next(d for d in self.W.list_depts() if d.get("parent") == root)
        self.W.run_until_idle(child["ref"], limit=200)
        return root, child["ref"]

    def _unstructure(self, reg):
        for k, v in self.prior_front.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        shutil.rmtree(reg, ignore_errors=True)

    def said(self, root):
        return [(p["src"], p["dst"][0], p["msg_type"], str((p.get("payload") or {}).get("done") or (p.get("payload") or {}).get("words") or ""),
                 (p.get("about") or {}).get("name") if isinstance(p.get("about"), dict) else None) for p in self.R.board(root)]

    def test_63_the_person_speaks_with_root_and_root_hands_the_words_to_the_department(self):
        W, R = self.W, self.R
        root, child = self.structure()
        child_name = W.dept(child)["name"]
        before = len(W.versions(child, "Brief"))
        # a task, with the department named in the words
        W.owner_ask(root, "On %s, add a Careers page for nurses who want to join." % child_name)
        W.run_until_idle(root, limit=200)
        s = self.said(root)
        self.assertIn(("Owner", "Identity", "request", "On %s, add a Careers page for nurses who want to join." % child_name, None), s)
        self.assertIn(("Identity", "Owner", "inform", "handed to %s" % child_name, child_name), s, "Root says where it went, about the department")
        posts = [(p["src"], p["dst"][0], (p.get("payload") or {}).get("words")) for p in R.board(child)]
        self.assertIn(("Root", "Identity", "add a Careers page for nurses who want to join."), posts, "the words reached the department as a post from Root")
        W.run_until_idle(child, limit=200)
        self.assertEqual(len(W.versions(child, "Brief")), before + 1, "the department took them")
        self.assertIn(("Identity", "Owner", "inform", "filed in the Brief", child_name), self.said(root), "and its answer came back onto Root's board")
        rows = {r["step"]: r["by"] for r in R.step_rows(root) if r["step"].startswith("identity.") and r["engine"] == "Identity"}
        self.assertEqual({rows.get("identity.front"), rows.get("identity.route"), rows.get("identity.hand")}, {"code"}, "the front door is code, code, code")
        # the chip: the department the person stood in, no name in the words
        W.owner_ask(root, "Which page lists the doctors?", about=child)
        W.run_until_idle(root, limit=200)
        W.run_until_idle(child, limit=200)
        s = self.said(root)
        self.assertTrue(any(x[0] == "Identity" and x[2] == "inform" and x[4] == child_name and "Five pages" in x[3] for x in s), "the answer, about the department: %s" % s[-3:])
        # a stamp at the front door reaches the department's ask
        pend = [x for x in W.asks(child) if x["kind"] == "publish" and x["status"] == "pending"]
        self.assertTrue(pend, "the department asks before its first publish")
        a = pend[-1]                                   # the latest: a stamp at the front door takes the ask the person just saw
        W.owner_ask(root, "Stamp")
        W.run_until_idle(root, limit=200)
        self.assertEqual(next(x for x in W.asks(child) if x["id"] == a["id"])["status"], "stamped")
        W.run_until_idle(child, limit=200)
        self.assertTrue(W.versions(child, "Live site"), "and the site went live")
        # Stop and Start by name
        W.owner_ask(root, "Stop %s." % child_name)
        W.run_until_idle(root, limit=200)
        self.assertTrue(W.dept(child)["stopped"])
        self.assertIn(("Identity", "Owner", "inform", "%s is Off" % child_name, child_name), self.said(root))
        W.owner_ask(root, "Start %s" % child_name)
        W.run_until_idle(root, limit=200)
        self.assertFalse(W.dept(child)["stopped"])
        # the chat, whole and scoped
        whole = R.chat_view(root)
        self.assertEqual(whole["root"], root)
        self.assertTrue(all(t["src"] == "Owner" or "Owner" in t["dst"] for t in whole["turns"]), "the chat is the owner's turns and what came back")
        self.assertEqual([c["ref"] for c in whole["departments"]], [child])
        scoped = R.chat_view(child)
        self.assertEqual(scoped["about"], child)
        self.assertTrue(scoped["turns"] and all(t["dept"] == child for t in scoped["turns"]), "inside the department, only its turns")
        self.assertLess(len(scoped["turns"]), len(whole["turns"]), "the setup request and its answer are Root's own")
        # a department born before Root spoke still hears Root: its table learns the new speaker
        t = R.coordination(child)
        self.assertIn("Root", t["edges"])

    def test_65_words_never_lost_a_front_post_nobody_answers_in_time_is_said_back_and_shows_as_waiting(self):
        """ER-9 (found live 2026-09-28): the first words at the front door died at the thread's bound unseen."""
        W, R = self.W, self.R
        root, child = self.structure()
        child_name = W.dept(child)["name"]
        d = W.dept(root)
        d["bounds"] = {"hops": 4, "seconds": 0.5, "usd": 0.5}  # the next thread on Root is out of time at the first tick
        W.save_dept(root, d)
        W.owner_ask(root, "On %s, add a page on parking." % child_name)
        # nobody runs Root: the words sit unanswered
        R.FRONT_WAIT_S, keep = 0, R.FRONT_WAIT_S
        try:
            fs = R.front_state(root)
            self.assertEqual([w["words"] for w in fs["waiting"]], ["On %s, add a page on parking." % child_name])
            self.assertIn("your words wait: On %s, add a page on parking." % child_name, [w["why"] for w in W.status(root)["waits"]])
            self.assertEqual(next(c for c in W.health(root)["checks"] if c["name"] == "Front door")["line"], "Your words are waiting")
        finally:
            R.FRONT_WAIT_S = keep
        R.sweep(root)                                          # the clock: the thread closes at its bound
        th = next(t for t in R.threads(root) if t["opened_by"] == "Owner" and t["state"] == "canceled")
        self.assertEqual(th["outcome"]["which"], "seconds")
        self.assertEqual(next(c for c in W.health(root)["checks"] if c["name"] == "Front door")["line"], "A request was lost at its bound")
        W.run_until_idle(root, limit=200)                     # Identity hears the lost request and says it back
        said = [t for t in R.chat_view(root)["turns"] if t["word"] == "lost"]
        self.assertEqual(len(said), 1, self.said(root)[-4:])
        self.assertEqual(said[0]["line"], "I could not act on this in time: On %s, add a page on parking. Say it again." % child_name)
        self.assertEqual(said[0]["dept"], child, "about the department the words named")
        self.assertEqual(next(c for c in W.health(root)["checks"] if c["name"] == "Front door")["line"], "Every request answered")
        rows = [r for r in R.step_rows(root) if r["step"] == "identity.lost"]
        self.assertEqual([r["by"] for r in rows], ["code"], "one code step")
        # said again, it goes through
        d = W.dept(root)
        d.pop("bounds", None)
        W.save_dept(root, d)
        W.owner_ask(root, "On %s, add a page on parking." % child_name)
        W.run_until_idle(root, limit=200)
        self.assertIn(("Identity", "Owner", "inform", "handed to %s" % child_name, child_name), self.said(root))

    def test_66_one_place_to_read_the_departments_own_asks_and_answers_sit_in_its_chat_beside_roots(self):
        """ER-10: inside a department the publish ask and its stamp are turns of the same chat; nothing counted twice."""
        W, R = self.W, self.R
        root, child = self.structure()
        child_name = W.dept(child)["name"]
        scoped = R.chat_view(child)
        own = [t for t in scoped["turns"] if t.get("own")]
        self.assertTrue(any(t["src"] == "Identity" and t["word"] == "publish" and "served from" in t["line"] for t in own),
                        "the department's own publish ask is a turn: %s" % [(t["src"], t["word"], t["line"][:40]) for t in scoped["turns"]])
        self.assertTrue(all(t["dept"] == child and t["name"] == child_name for t in own))
        a = [x for x in W.asks(child) if x["kind"] == "publish" and x["status"] == "pending"][-1]
        W.decide_ask(child, a["id"], True)
        W.run_until_idle(child, limit=200)
        scoped = R.chat_view(child)
        self.assertTrue(any(t["src"] == "Owner" and t["msg_type"] == "accept-proposal" and t.get("own") for t in scoped["turns"]), "the stamp is a turn")
        # through Root: handed on, answered, and the answer appears once, not once per board (the department's own goal
        # filing at birth is its own "filed in the Brief" and stays)
        filed = lambda v: sum(1 for t in v["turns"] if t["line"] == "filed in the Brief")  # noqa: E731
        before_s, before_w = filed(R.chat_view(child)), filed(R.chat_view(root))
        W.owner_ask(root, "On %s, add a Careers page." % child_name)
        W.run_until_idle(root, limit=200)
        W.run_until_idle(child, limit=200)
        scoped = R.chat_view(child)
        self.assertEqual(filed(scoped), before_s + 1, "one turn for one answer")
        self.assertEqual(sum(1 for t in scoped["turns"] if t["line"].startswith("handed to")), 1)
        ats = [str(t["at"]) for t in scoped["turns"]]
        self.assertEqual(ats, sorted(ats), "in time order across the two boards")
        whole = R.chat_view(root)
        self.assertTrue(any(t.get("own") and t["dept"] == child and t["word"] == "publish" for t in whole["turns"]), "on Root, the child's own ask with its chip")
        self.assertEqual(filed(whole), before_w + 1)
        # the Map's Say on the department itself is its own turn too
        W.owner_ask(child, "Which page lists the therapists?")
        W.run_until_idle(child, limit=200)
        scoped = R.chat_view(child)
        self.assertTrue(any(t["src"] == "Owner" and t.get("own") and t["line"] == "Which page lists the therapists?" for t in scoped["turns"]))
        self.assertTrue(any(t["src"] == "Identity" and t.get("own") and t["word"] == "answer" for t in scoped["turns"]))

    def test_67_a_step_not_needed_this_time_never_fails_a_run(self):
        """Found live 2026-09-28 (Human Simulation run 1): a task said in several sentences made the skipped step
        'Restate it as a rule' fail its one-line check, and the whole request failed unseen."""
        W, R = self.W, self.R
        root, child = self.structure()
        child_name = W.dept(child)["name"]
        before = len(W.versions(child, "Brief"))
        words = ("The emergency number is 108. Our doctors: Dr. Meera Rao (cardiology), Dr. Arjun Nair (orthopaedics). "
                 "We treat heart, bone and children's illnesses. Put the emergency number 108 on every page instead of 'to be confirmed'.")
        W.owner_ask(root, "On %s, %s" % (child_name, words))
        W.run_until_idle(root, limit=200)
        W.run_until_idle(child, limit=200)
        failed = [r for r in W.runs(child) if r["status"] == "failed"]
        self.assertEqual(failed, [], "no run failed: %s" % [(r["engine"], r.get("what")) for r in failed])
        rows = [r for r in R.step_rows(child) if r["engine"] == "Identity" and r["by"] == R.SKIPPED]
        self.assertTrue(rows, "some steps were not needed")
        self.assertTrue(all(r["status"] == "ok" and r["check"]["notes"] == [R.SKIPPED] for r in rows), "and none of them failed")
        self.assertEqual(len(W.versions(child, "Brief")), before + 1, "the words were taken")
        self.assertIn(("Identity", "Owner", "inform", "filed in the Brief", child_name), self.said(root)[-2:])

    def test_68_a_request_whose_handling_failed_is_said_back_and_health_counts_it(self):
        """A handed-on request that a failed run could not carry is a turn from Root, about the department, asking
        for the words again; Health's Front door counts a Root-handed request too."""
        W, R = self.W, self.R
        root, child = self.structure()
        child_name = W.dept(child)["name"]
        real = R.CODE["identity_file"]                     # a model that answers nothing steps down and asks; a broken

        def boom(ctx, step, item):                         # code step is the failure a person never sees
            raise RuntimeError("the file step broke")
        R.CODE["identity_file"] = boom
        try:
            W.owner_ask(root, "On %s, add a page on parking." % child_name)
            W.run_until_idle(root, limit=200)
            W.run_until_idle(child, limit=200)
        finally:
            R.CODE["identity_file"] = real
        failed = [r for r in W.runs(child) if r["status"] == "failed" and r["engine"] == "Identity"]
        self.assertTrue(failed, "the handling failed, as arranged")
        said = [t for t in R.chat_view(root)["turns"] if t["word"] == "lost"]
        self.assertEqual(len(said), 1, self.said(root)[-4:])
        self.assertTrue(said[0]["line"].startswith("I could not act on this:") and said[0]["line"].endswith("Say it again, or say it differently."))
        self.assertEqual(said[0]["dept"], child, "about the department")
        scoped = [t for t in R.chat_view(child)["turns"] if t["word"] == "lost"]
        self.assertEqual(len(scoped), 1, "once inside the department, not twice")
        fs = R.front_state(child)
        self.assertEqual(fs["lost"], [], "said back, so not lost")
        self.assertEqual(next(c for c in W.health(child)["checks"] if c["name"] == "Front door")["line"], "Every request answered")

    def test_70_when_the_site_goes_live_the_chat_says_so_with_the_way_to_it_inside_and_on_root(self):
        """Found live 2026-09-28 (Human Simulation run 1): after the publish stamp the chat said nothing, and the person
        did not know the site was up. The last artifact of the kind going out is a turn with the way to it."""
        W, R = self.W, self.R
        root, child = self.structure()
        a = next(x for x in W.asks(child) if x["kind"] == "publish" and x["status"] == "pending")
        self.assertEqual([t for t in R.chat_view(child)["turns"] if t["word"] == "live"], [], "nothing is live before the stamp")
        W.decide_ask(child, a["id"], True)
        W.run_until_idle(child, limit=200)
        W.run_until_idle(root, limit=200)
        inside = [t for t in R.chat_view(child)["turns"] if t["word"] == "live"]
        self.assertEqual(len(inside), 1, "said once inside")
        self.assertEqual((inside[0]["line"], inside[0]["link"], inside[0]["dept"]), ("Live site v1 is live.", "Live site", child))
        on_root = [t for t in R.chat_view(root)["turns"] if t["word"] == "live"]
        self.assertEqual(len(on_root), 1, self.said(root)[-4:])
        self.assertEqual((on_root[0]["link"], on_root[0]["dept"]), ("Live site", child), "on Root the turn carries the department and the way")
        self.assertTrue(all(t.get("link") is None for t in R.chat_view(root)["turns"] if t["word"] != "live"), "no other turn carries a link")

    # ---- what the person found on Sutra Beta 2.306.10 (Human Simulation run 2, 2026-09-28), fixed ----------------
    def test_71_a_panel_read_writes_nothing_and_never_asks_the_model(self):
        """Finding 11: the panel stood still for 25 s at a publish, waiting on Coordination's tie inside a read. A read
        peeks: no row, no ask, no post, no model call, while the motor still runs the line between the reads."""
        W, R = self.W, self.R
        self.live()
        W.owner_ask(REF, "Add a page on parking.")
        for _ in range(60):
            before = (len(self.M.calls), len(R.step_rows(REF)), len(W.asks(REF)), len(R.board(REF)), len(W.runs(REF)))
            W.status(REF)
            W.map_view(REF)
            after = (len(self.M.calls), len(R.step_rows(REF)), len(W.asks(REF)), len(R.board(REF)), len(W.runs(REF)))
            self.assertEqual(before, after, "a read left the record and the model alone")
            if not W.run_until_idle(REF, limit=1):
                break
        self.assertGreaterEqual(len(W.versions(REF, "Live site")), 2, "the line still ran to a second live version between the reads")
        self.assertIn("coord.tie", self.M.calls, "the tie was asked by the motor, never by a read")

    def test_72_a_rule_the_person_stamped_is_a_check_the_line_runs_and_a_build_that_breaks_it_never_goes_live(self):
        """Finding 12: with 'every page ends with 108' stamped, two versions went live with four pages breaking it.
        Check holds every page to the person's rules; a build that breaks one is filed failed, sent back to be
        rewritten with the finding, twice at most, and the person is told each time."""
        W, R = self.W, self.R
        self.live()
        self.ask("From now on, every page ends with: Call 108.")
        self.stamp("rule")
        self.idle()
        live = len(W.versions(REF, "Live site"))
        self.assertEqual(live, 2, "the rule's own rerun went live: the harness meets every rule")
        self.assertIn("check.rules", self.M.calls, "Check asked its agent to hold the pages to the rule")
        self.M.broken = [{"rule": "Every page ends with: Call 108.", "pages": ["about", "contact"], "why": "no 108"}]
        self.ask("Add a page on parking.")
        self.idle()
        self.assertEqual(len(W.versions(REF, "Live site")), live, "nothing went live while the rule was broken")
        failed = [v for v in W.versions(REF, "Build") if not v["check"]["ok"]]
        self.assertEqual(len(failed), 3, "three builds filed failed: the one, and two rewrites")
        self.assertIn("breaks the rule 'Every page ends with: Call 108.' on about, contact", failed[-1]["check"]["notes"])
        said = [t["line"] for t in R.chat_view(REF)["turns"] if t["word"] == "broken"]
        self.assertEqual(len(said), 3, said)
        self.assertTrue(said[0].startswith("Build v") and said[0].endswith("Sent back to be rewritten."), said[0])
        self.assertIn("two rewrites did not mend it. Say the rule another way, or drop it.", said[-1])
        brief = W.read_files(REF, "Brief", W.latest(REF, "Brief")["v"])["brief.md"]
        self.assertEqual(brief.count(R.SEND_BACK), 2, "the finding went to the line twice, as a correction")
        self.M.broken = []
        self.ask("Add a page on visiting hours.")
        self.idle()
        self.assertEqual(len(W.versions(REF, "Live site")), live + 1, "with the rule met, the line goes live again")
        drafted = R.d_check_rules({"bag": {"check.rules_of": {"rules": ["Every page ends with: Call 108."],
                                                                "pages": [{"slug": "a", "text": "In doubt, call 108."}, {"slug": "b", "text": "Nothing here"}]}}}, None, None)
        self.assertEqual(drafted, {"broken": [{"rule": "Every page ends with: Call 108.", "pages": ["b"], "why": "the page does not carry 'call 108'"}]},
                         "and code's own reading of an every-page rule is the floor under the agent")

    def test_73_a_stamp_on_an_ask_inside_the_department_is_a_turn_of_the_chat_inside_and_on_root(self):
        """Finding 14: a stamp on a go-ahead ask inside the department left no turn (the publish stamp did). The person's
        own act in a thread Root opened lives on the department's board alone, so the chat shows it once, and Root's
        chat shows it with the department."""
        W, R = self.W, self.R
        root, child = self.structure()
        child_name = W.dept(child)["name"]
        W.owner_ask(root, "On %s, email the new site to every patient." % child_name)
        W.run_until_idle(root, limit=200)
        W.run_until_idle(child, limit=200)
        a = next(x for x in W.asks(child) if x["kind"] == "request" and x["status"] == "pending")
        self.assertTrue(a["text"].startswith("Your words reach outside the site: an email address, so people will write, call or come. Put them on the site as said?"), a["text"])
        W.decide_ask(child, a["id"], True)
        W.run_until_idle(child, limit=200)
        W.run_until_idle(root, limit=200)
        inside = [t for t in R.chat_view(child)["turns"] if t["src"] == "Owner" and t["msg_type"] == "accept-proposal"]
        self.assertEqual(len(inside), 1, "the stamp is a turn inside the department")
        on_root = [t for t in R.chat_view(root)["turns"] if t["src"] == "Owner" and t["msg_type"] == "accept-proposal" and t.get("dept") == child]
        self.assertEqual(len(on_root), 1, "and on Root's chat, about the department")

    def test_74_stop_and_start_are_turns_of_the_chat(self):
        """Finding 15: the person stopped the department from the Map and the chat said nothing. Stop and Start are
        the person's own acts: a turn inside, and on Root about the department."""
        W, R = self.W, self.R
        root, child = self.structure()
        W.set_stopped(child, True)
        W.set_stopped(child, False)
        words = [t["line"] for t in R.chat_view(child)["turns"] if t["word"] in ("stopped", "started")]
        self.assertEqual(words, ["Stopped by you: every engine stops where it is.", "Started by you: every engine looks to its own triggers."])
        on_root = [(t["word"], t.get("dept")) for t in R.chat_view(root)["turns"] if t["word"] in ("stopped", "started")]
        self.assertEqual(on_root, [("stopped", child), ("started", child)])
        W.set_stopped(REF, True)
        self.assertEqual([t["word"] for t in R.chat_view(REF)["turns"] if t["word"] == "stopped"], ["stopped"], "a department with no Root: its own chat")

    def test_75_an_answer_to_the_departments_facts_question_is_the_facts_not_a_rule(self):
        """Finding 16: the hours, said in answer to 'Tell me here and I will put them in', came back as a rule to stamp.
        When the department's last word was its facts question and the answer carries no rule cue, it is a task."""
        W, R = self.W, self.R
        self.M.holes = True
        root, child = self.structure()
        child_name = W.dept(child)["name"]
        a = next(x for x in W.asks(child) if x["kind"] == "publish" and x["status"] == "pending")
        W.decide_ask(child, a["id"], True)
        W.run_until_idle(child, limit=200)
        W.run_until_idle(root, limit=200)
        self.assertTrue([t for t in R.chat_view(child)["turns"] if t["word"] == "facts"], "the department asked for the facts")
        answer = "Appointments are Monday to Saturday, 9 am to 6 pm."
        for key in (answer, "On %s, %s" % (child_name, answer), "on %s, %s" % (child_name, answer)):
            self.M.journeys[key] = "directive"                 # the agent misreads the answer as a rule
        before = len(W.versions(child, "Brief"))
        W.owner_ask(root, "On %s, %s" % (child_name, answer))
        W.run_until_idle(root, limit=200)
        W.run_until_idle(child, limit=200)
        self.assertEqual([x for x in W.asks(child) if x["kind"] == "rule"], [], "no rule was put to the person")
        self.assertEqual(len(W.versions(child, "Brief")), before + 1, "the answer was filed as the facts")
        self.assertIn(answer, W.read_files(child, "Brief", W.latest(child, "Brief")["v"])["brief.md"])

    def test_76_what_reaches_outside_is_named_in_the_persons_words(self):
        """Finding 13: the person's own address, phone and email came back as 'This reaches outside the site'."""
        R = self.R
        self.assertEqual(R._reaches("Our address is 14 Lake Road, Nashik 422001. Phone 0253-2571108, email care@parasthi.in"),
                         "an email address, a phone number, an address, so people will write, call or come")
        self.assertEqual(R._reaches("Post it to our Instagram", "it names another site"), "it names another site")
        self.assertEqual(R._reaches("Post it to our Instagram", "it reaches outside the site"), "", "the judge's stock reason adds nothing")

    def test_77_the_goal_is_said_once_on_the_whole_chat_and_opens_the_departments_own(self):
        """Finding 3: the goal was echoed on Root's chat as the person's turn again at the department's birth."""
        W, R = self.W, self.R
        root, child = self.structure()
        words = R.board(child)[0]["payload"]["words"]          # what Root handed at the birth: the person's words
        self.assertTrue(words.startswith("Start a website department for"), words)
        whole = [t for t in R.chat_view(root)["turns"] if t["src"] == "Owner" and t["line"] == words]
        self.assertEqual(len(whole), 1, "the person's words stand once on the whole chat: the front turn")
        scoped = R.chat_view(child)["turns"]
        self.assertEqual((scoped[0]["src"], scoped[0]["line"], scoped[0].get("birth")), ("Owner", words, True), "and open the department's own chat")

    def test_78_plan_tells_the_person_which_pages_it_planned_whenever_they_change(self):
        """Finding 8: three pages the goal never named went live unasked. Plan says its pages, once per change."""
        W, R = self.W, self.R
        self.live()
        plans = [t["line"] for t in R.chat_view(REF)["turns"] if t["word"] == "plan"]
        self.assertEqual(plans, ["Planned 5 pages: Index, About, Doctors, Contact, Book. Say which to drop or add."])
        self.ask("Change the tagline to something warmer.")
        self.idle()
        self.assertEqual(len([t for t in R.chat_view(REF)["turns"] if t["word"] == "plan"]), 1, "the same pages: not said again")
        self.ask("Add a parking page.")
        self.idle()
        plans = [t["line"] for t in R.chat_view(REF)["turns"] if t["word"] == "plan"]
        self.assertEqual(len(plans), 2, plans)
        self.assertIn("Parking", plans[-1])

    def test_80_the_run_row_says_how_far_along_a_step_of_many_is(self):
        """The chat's working line reads the run row's what: 'page 3 of 5' while Write writes the pages."""
        W = self.W
        whats = []
        real = W._put_run

        def spy(ref, row):
            whats.append(row.get("what"))
            return real(ref, row)
        W._put_run = spy
        try:
            self.live()
        finally:
            W._put_run = real
        self.assertEqual([w for w in whats if w and w.startswith("page ")], ["page %d of 5" % i for i in range(1, 6)])

    def test_81_the_persons_front_turn_carries_the_department_it_reached(self):
        """The person names the department in their words and no chip is on the box: Root's hand-over says where the
        words went, and the person's own turn carries it too (run 2: a turn without the chip)."""
        W, R = self.W, self.R
        root, child = self.structure()
        W.owner_ask(root, "On %s, add a parking page." % W.dept(child)["name"])
        W.run_until_idle(root, limit=200)
        mine = [t for t in R.chat_view(root)["turns"] if t["src"] == "Owner" and t["word"] == "front" and "parking" in t["line"]]
        self.assertEqual([(t.get("dept"), t.get("name")) for t in mine], [(child, W.dept(child)["name"])])

    def test_79_a_quoted_hole_never_starts_mid_word(self):
        R = self.R
        holes = R.placeholders({"book.html": "<p>Write to care@parasthihospital.in or call. Appointment Availability: appointment availability is to be confirmed</p>"})
        self.assertEqual(len(holes), 1)
        self.assertTrue(re.match(r"the page says '[A-Za-z]", holes[0]["claim"]), holes[0]["claim"])
        self.assertNotIn("l.in", holes[0]["claim"])
        self.assertTrue(holes[0]["claim"].endswith("is to be confirmed'"), holes[0]["claim"])

    def test_64_each_function_has_its_own_ladder_numbers_from_its_settings(self):
        """Founder, 2026-09-28: each of the five functions has a Settings tab with its own updates; an engine too."""
        W, R = self.W, self.R
        self.assertEqual(R.numbers(REF, "Write")["runs"], R.LADDER["runs"])
        out = R.set_numbers(REF, "Write", {"runs": 12, "trial": "6"})
        self.assertEqual((out["runs"], out["trial"], out["misses"]), (12, 6, R.LADDER["misses"]))
        self.assertEqual(R.numbers(REF, "Plan")["runs"], R.LADDER["runs"], "Plan's own are untouched")
        self.assertEqual(R.steps_view(REF, "Write")["numbers"]["runs"], 12, "the card reads the function's own")
        for bad in ({"runs": 0}, {"hops": 5}, {"misses": "many"}):
            with self.assertRaises(ValueError):
                R.set_numbers(REF, "Write", bad)
        with self.assertRaises(ValueError):
            R.set_numbers(REF, "Nobody", {"runs": 5})
        self.assertTrue(any(r["engine"] == "Identity" and "Write's ladder" in (r.get("what") or "") for r in W.runs(REF)), "the setting is a row")


class TestActivation(Base):
    """Founder, 2026-09-28: every engine has its own start, a trigger and blockers; Start is a signal to all; "the rest
    is in coordination"; once started each has its own agency. One rule for the five internal systems and the four
    work engines, declared as data, refused if missing, read by one piece of code."""

    ALL = ("Plan", "Write", "Check", "Publish", "Setup", "Do", "Identity", "Adaptation", "Priority", "Coordination", "Audit")    # eleven: Setup is a Root's, Do the default line's (TPL-1)

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
        self.assertEqual(sorted(R.defs()["engines"]), sorted(self.ALL))
        for name in self.ALL:
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
            for name in self.ALL:
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
                         [("Identity", R.step_def("identity.wait_engine")[1]["name"]), ("Identity", R.step_def("identity.gate")[1]["name"]),
                          ("Priority", R.step_def("priority.envelope")[1]["name"]), ("Coordination", "Stop a chain at its limit")])
        self.assertEqual(R.steps_view(REF, "Publish")["start"]["on"], ["a new Build that passed its check"])
        self.assertEqual(R.steps_view(REF, "Adaptation")["start"]["on"], ["a post addressed to it", "a new Live site that passed its check"])
        c = R.steps_view(REF, "Coordination")
        self.assertEqual(c["hears"][0], "What engines share")
        shared = [s["name"] for s in c["steps"] if s["under"] == "What engines share"]
        self.assertEqual(shared, ["Keep one run at a time", "Say who goes first, when several are ready", "Say who may post what to whom",
                                  "Ask a function for its verdict", "Close a thread at its bound",
                                  "Raise an alarm for a run past its window"])
        pick = next(s for s in c["steps"] if s["id"] == "coord.pick")
        self.assertEqual((pick["mode"], pick["rung_name"], pick["ran"], pick["evidence"]["pass"]), ("rule", "Code", True, 1.0))
        self.assertEqual(c["table"]["line"], ["Plan", "Write", "Check", "Publish"])
        self.assertIn({"from": "Owner", "act": "request", "to": ["Identity"]}, c["table"]["may_post"])

    def test_53_what_the_screen_reads_says_function_never_internal_system(self):
        """Founder, 2026-09-28: "the internal word is 'internal system' only. It is just for the users. They are
        called functions." """
        R, W = self.R, self.W
        self.live()
        self.ask("What if patients could book a visit on the site")
        read = {name: R.steps_view(REF, name) for name in self.ALL}
        read.update({"the board": R.board_view(REF), "the map": W.map_view(REF), "the ideas": R.ideas(REF)})
        for what, view in read.items():
            self.assertNotIn("internal system", json.dumps(view).lower(), "the inside word reached the screen, in " + what)
        self.assertEqual(read["Coordination"]["table"]["first"][2], "A function woken by new work")
        self.assertEqual([k for k in self.ALL if read[k]["kind"] == "function"], ["Identity", "Adaptation", "Priority", "Coordination", "Audit"])


class TestRunThree(Base):
    """Human Simulation run 3 (2026-09-29, Beta 2.306.15, the founder as the user, 'Best dermatologists in Bangalore'):
    findings 34-46, each a test before its fix (qa/sim/TEST-STRATEGY.md)."""

    WEB = "Find on the internet what the hospital does and who its doctors are, and build only from that."

    def lib_copy(self):
        lib = self.R.Path(tempfile.mkdtemp(prefix="engine-templates-"))
        shutil.rmtree(lib)
        shutil.copytree(self.R.TEMPLATES_DIR, lib)
        self._prior_lib = self.R.TEMPLATES_DIR
        self.R.TEMPLATES_DIR = lib
        self.R._DEFS.clear()
        return lib

    def tearDown(self):
        if getattr(self, "_prior_lib", None):
            self.R.TEMPLATES_DIR = self._prior_lib
            self.R._DEFS.clear()
        super().tearDown()

    def web_engine(self):
        """As the user: the words ask for the internet, the engine is stamped, it files on the Brief at once."""
        self.ask(self.WEB)
        self.stamp("engine")
        self.idle()
        self.assertEqual(len(self.W.versions(REF, "Web Facts")), 1)

    def test_96_the_line_waits_while_an_engine_ask_the_goal_needs_is_pending_and_says_so(self):
        """Finding 34: the goal was filed and Plan and Write built a site of 'to be confirmed' while the engine ask waited;
        its publish ask came the second the engine filed. The line waits for the stamp, and the person is told once."""
        W, R = self.W, self.R
        self.lib_copy()
        W.give_goal(REF, self.WEB)
        self.idle()
        self.assertTrue([x for x in W.asks(REF) if x["kind"] == "engine" and x["status"] == "pending"], "the engine ask is up")
        self.assertEqual(W.versions(REF, "Site plan"), [], "nothing planned from a Brief whose need is unmet")
        name, _, why = R.next_due(REF, peek=True)
        self.assertEqual((name, why), (None, "waits for the stamp on Web Facts"))
        lines = [t["line"] for t in R.chat_view(REF)["turns"]]
        waits = [x for x in lines if x.startswith("The line waits for your stamp on Web Facts")]
        self.assertEqual(len(waits), 1, lines[-4:])
        self.stamp("engine")
        self.idle()
        self.assertTrue(W.versions(REF, "Web Facts"), "after the stamp the engine ran")
        self.assertTrue(W.versions(REF, "Site plan"), "and the line followed")

    def test_97_the_working_line_follows_the_engines_step(self):
        """Finding 35: 'Source Reader is working: reading Brief' for the whole 90 s search. The run row's what is the step's name."""
        W, R = self.W, self.R
        self.lib_copy()
        seen, real = {}, R.run_step

        def spy(ctx, step, item):
            row = next((r for r in W.runs(REF) if r["id"] == ctx["run"]), {})
            seen.setdefault(step["id"], row.get("what"))
            return real(ctx, step, item)

        R.run_step = spy
        try:
            self.live()
            self.web_engine()
        finally:
            R.run_step = real
        self.assertEqual(seen.get("web-facts.make"), "Do what it asks", seen)
        self.assertEqual(seen.get("plan.pages"), "Propose the pages", seen)

    def test_98_an_address_on_a_page_is_a_link(self):
        """Finding 40: 'Address as read: https://...' as text. write_file links a bare address and leaves a link alone."""
        R = self.R
        body = '<p>Read more at https://example.com/x/y?z=1. <a href="https://kept.org/">kept</a> and (https://paren.org).</p>'
        ctx = {"bag": {"write.list": {"plan": {"pages": [{"slug": "about", "title": "About"}]}, "pages": ["about"]},
                       "write.page": [{"title": "About", "body_html": body}]}, "how": {}}
        out = R.write_file(ctx, {"id": "write.file"}, None)
        html = json.loads(out["files"]["about.html"])["body_html"]
        self.assertIn('<a href="https://example.com/x/y?z=1">https://example.com/x/y?z=1</a>.', html)
        self.assertIn('<a href="https://paren.org">https://paren.org</a>)', html)
        self.assertEqual(html.count('href="https://kept.org/"'), 1, html)
        self.assertNotIn('<a href="<a', html)

    def test_99_audit_reads_what_the_engines_filed_and_the_holes_go_to_the_engine_that_reaches_the_internet(self):
        """Finding 41: Audit read the Brief only and asked to 'put right' sourced facts; the facts question asked the person for
        fees an engine could find. The judge reads the filed artifacts; the holes are put to the web engine, once."""
        W, R = self.W, self.R
        self.lib_copy()
        self.live()
        self.web_engine()
        self.M.holes = True
        self.ask("Build the site from what you found.")
        judge = [p for s, p in self.M.prompts if s == "audit.judge"][-1]
        self.assertIn("WHAT THE DEPARTMENT'S OWN ENGINES FILED", judge)
        self.assertIn("Web Facts (v", judge)
        lines = [t["line"] for t in R.chat_view(REF)["turns"]]
        facts = [x for x in lines if x.startswith("The site says it does not know")]
        self.assertTrue(facts, lines[-4:])
        self.assertTrue(any("I have asked Web Facts to look them up" in x for x in facts), facts)
        self.assertFalse(any("Tell me here" in x for x in facts[:1]), facts[0])
        look = [v for v in W.versions(REF, "Brief") if "Look up:" in W.read_files(REF, "Brief", v["v"]).get("brief.md", "")]
        self.assertEqual(len(look), 1, "the holes are put to the engine once, not on every audit")

    def test_100_what_came_of_words_said_to_a_function_lands_in_its_chat(self):
        """Finding 43: 'Put the top three first.' said to Priority; the plan and the live tells landed only in the department
        chat. A tell of the line carries its chain, and the function's chat shows the tells of the chains its words started."""
        W, R = self.W, self.R
        self.live()
        W.owner_ask(REF, "Put the top three first.", about="fn:priority")
        self.idle()
        turns = R.fn_chat_view(REF, "priority")["turns"]
        words = [t["word"] for t in turns if not t["think"]]
        self.assertIn("request", words, "the words and 'filed in the Brief'")
        self.assertIn("live", words, [t["line"] for t in turns][-6:])
        other = R.fn_chat_view(REF, "audit")["turns"]
        self.assertNotIn("live", [t["word"] for t in other if not t["think"]], "a chain another function's words started stays out")

    def test_101_the_hole_reader_skips_the_navigation_and_the_links(self):
        """Finding 44 (27 again): 'the page says Top 5 List How the Order Was Chosen Sources Still To Be Confirmed': the nav's
        link text read as a gap."""
        R = self.R
        nav = '<nav><a href="a.html">Sources</a> <a href="b.html">Still To Be Confirmed</a></nav><header><h1>Doctors</h1></header>'
        self.assertEqual(R.placeholders({"a.html": nav + "<main><p>All good here.</p></main>"}), [])
        holes = R.placeholders({"a.html": nav + "<main><p>Fees and timings are to be confirmed.</p></main>"})
        self.assertEqual(len(holes), 1, holes)
        self.assertIn("Fees and timings are to be confirmed", holes[0]["claim"])

    def test_102_words_identitys_take_calls_a_rule_are_filed_as_a_rule_not_as_a_request(self):
        """Finding 45: 'Nothing goes on the site without a source line under it.' was asked for with 'Put them on the site as
        said?' and, stamped, went into the Brief under Asked since; the map's rules never changed."""
        W, R = self.W, self.R
        self.live()
        words = "Nothing goes on the site without a source line under it."
        line = "Nothing goes on the site without a source line under it"
        self.M.rules[words] = {"line": line, "tag": "always"}
        briefs = len(W.versions(REF, "Brief"))
        self.ask(words)
        a = next(x for x in W.asks(REF) if x["kind"] == "rule" and x["status"] == "pending")
        self.assertEqual(a["text"], "A rule, as understood: " + line)
        self.assertFalse([x for x in W.asks(REF) if x["kind"] == "request" and x["status"] == "pending"], "no request ask on a rule")
        self.assertEqual(len(W.versions(REF, "Brief")), briefs, "a rule is not an ask of the line")
        self.stamp("rule")
        self.idle()
        self.assertIn(line, [r["line"] for r in W.dept(REF)["rules"]])

    def test_103_an_engine_that_reads_the_brief_runs_again_only_when_the_words_ask_for_its_work(self):
        """Finding 38: four web searches in one run, one asked for. A born engine's need step reads whether the new words ask
        for its work; the first run asks nothing, having nothing filed yet."""
        W, R = self.W, self.R
        self.lib_copy()
        self.live()
        self.web_engine()
        self.assertEqual([s for s, _ in self.M.prompts if s == "web-facts.need"], [], "the first run had nothing to weigh the words against")
        self.M.need = False
        plans = len(W.versions(REF, "Site plan"))
        self.ask("Put the top three first.")
        self.assertEqual(len(W.versions(REF, "Web Facts")), 1, "no second search for words about order")
        row = [r for r in W.runs(REF) if r["engine"] == "Web Facts"][-1]
        self.assertEqual(row["status"], "ok", row)
        self.assertTrue(str(row.get("what")).startswith("not needed: "), row)
        self.assertGreater(len(W.versions(REF, "Site plan")), plans, "the line went on and Plan read the last filing")
        self.assertEqual(len([s for s, _ in self.M.prompts if s == "web-facts.need"]), 1)

    def test_104_a_search_that_runs_again_reads_what_it_filed_last_time(self):
        """Finding 46: each re-run replaced the record; v4 of the site drew on three sources where v1 had four. The make step
        is shown the last result and told to keep what holds, add what is new and name what it dropped."""
        W, R = self.W, self.R
        self.lib_copy()
        self.live()
        self.web_engine()
        self.ask("Find their fees too.")
        self.assertEqual(len(W.versions(REF, "Web Facts")), 2)
        make = [p for s, p in self.M.prompts if s == "web-facts.make"][-1]
        self.assertIn("WHAT YOU FILED LAST TIME (v1):", make)
        self.assertIn("Done, in words:", make, "the last result's text is in the prompt")
        self.assertIn("under a line 'Dropped'", make)
        first = [p for s, p in self.M.prompts if s == "web-facts.make"][0]
        self.assertNotIn("WHAT YOU FILED LAST TIME", first)


if __name__ == "__main__":
    unittest.main(verbosity=1)
