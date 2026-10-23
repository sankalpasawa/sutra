"""test_function_prompts.py -- each function's version 1: one agent, its instructions as .md files (PRD M2, S-28).

Named claims:
  M2.1a  every function prompt renders, for the fixtures, byte for byte what the inline builders rendered before the
         move (test_fixtures/function-prompts.snapshot.json was written from them, before the move)
  M2.1b  each function's files are the ones its page names, each in the bundle with its plain first line and the parts
         its steps read; a prompt is read from the file, so the words on disk are the words sent
  M2.1c  a file gone from the bundle, or one missing a part a step reads, refuses the definitions load

No test reaches a model, the live records home or the network: the prompts are rendered, never sent.

Run: python test_function_prompts.py   (or pytest). To take a new snapshot after a prompt is changed on purpose:
     FUNCTION_PROMPTS_SNAPSHOT=write python test_function_prompts.py
"""
import importlib
import json
import os
import shutil
import tempfile
import unittest
from pathlib import Path

REF = "dref-prompts0001"
SNAP = Path(__file__).parent / "test_fixtures" / "function-prompts.snapshot.json"
KEYS = ("SUTRA_NATIVE_DEPT_HOME", "SUTRA_NATIVE_HOME", "SUTRA_WEBSITE_OFFLINE", "SUTRA_ENGINE_RUNTIME", "SUTRA_MOTOR",
        "SUTRA_ALLOW_DEFAULT_HOME_IN_TESTS", "J2_FLOW_V1")
PLAN = {"site_name": "City Care Hospital", "tagline": "Care, every day", "palette": {"primary": "#0f5e7a", "accent": "#c4956a"},
        "pages": [{"slug": "index", "title": "Home", "purpose": "the front door", "sections": ["welcome"]},
                  {"slug": "doctors", "title": "Doctors", "purpose": "who treats you", "sections": ["list"]}]}
LIVE = {"index.html": "<main><h1>City Care Hospital</h1><p>Open every day. Call 044 2345 6789 to book.</p></main>",
        "doctors.html": "<main><h1>Doctors</h1><p>Dr. Rao has led the heart unit since 1998.</p></main>"}
LINE = [{"name": "Facts", "does": "finds the clinic's hours, each with its source", "reads": "Brief", "writes": "Facts", "internet": True},
        {"name": "Site", "does": "writes the pages from the facts", "reads": "Facts", "writes": "Live site", "internet": False}]


class Fixture(unittest.TestCase):
    """A website department with a brief, a plan, a live site, rules and an ask waiting: everything a function prompt
    reads, on a records home of its own."""

    def setUp(self):
        self.home = tempfile.mkdtemp(prefix="function-prompts-")
        self.prior = {k: os.environ.get(k) for k in KEYS}
        for k in KEYS:
            os.environ.pop(k, None)
        os.environ["SUTRA_NATIVE_DEPT_HOME"] = os.path.join(self.home, "native")
        os.environ["SUTRA_NATIVE_HOME"] = os.path.join(self.home, "registry")
        os.environ["J2_FLOW_V1"] = "0"
        import website_dept
        self.W = importlib.reload(website_dept)
        import engine_runtime
        self.R = importlib.reload(engine_runtime)
        self.bundled = self.R.PROMPTS_DIR
        import function_templates
        self.T, self.picked = function_templates, function_templates.picked
        # the card's template lines are the function templates' words, not the function's instructions: left out, so
        # this snapshot is of what moved into the files alone
        function_templates.picked = lambda ref: {}
        W = self.W
        W.create(REF, "City Care Hospital Website", None)
        d = W.dept(REF)
        d["rules"] = [{"id": "u-1", "tag": "always", "line": "Every page names the phone line"},
                      {"id": "u-2", "tag": "refuse", "line": "Never state a price"},
                      {"id": "u-3", "tag": "ask", "line": "Ask before a new page goes live"}]
        W.save_dept(REF, d)
        W.add_version(REF, "Brief", {"brief.md": "# City Care Hospital Website\n\nA website for City Care Hospital: departments, doctors, how to book.\n"},
                      [{"ask": "a website", "at": "2026-10-23T10:00:00+05:30"}], "owner", {"ok": True, "notes": ["the owner's goal"]})
        W.add_version(REF, "Site plan", {"site-plan.json": json.dumps(PLAN)}, [{"art": "Brief", "v": 1}], "r-plan", {"ok": True, "notes": []})
        W.add_version(REF, "Live site", dict(LIVE), [{"art": "Build", "v": 1}], "r-pub", {"ok": True, "notes": []})
        W._put_ask(REF, {"id": "a-fixture1", "kind": "publish", "engine": "Publish", "text": "Publish: go live for the first time",
                         "status": "pending", "created": "2026-10-23T10:05:00+05:30"})

    def tearDown(self):
        self.T.picked = self.picked
        self.R.PROMPTS_DIR = self.bundled
        self.R._DEFS.clear()
        for k, v in self.prior.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        shutil.rmtree(self.home, ignore_errors=True)

    def ctx(self, engine, payload=None, **more):
        R, W = self.R, self.W
        c = {"ref": REF, "dept": W.dept(REF), "engine": engine, "def": R.engine_def(engine), "slot": engine + "@fixture",
             "inp": {"v": 1}, "post": None if payload is None else {"n": 1, "thread": "x-fixture", "src": "Owner", "msg_type": "request",
                                                                    "payload": payload},
             "run": None, "bag": {}, "how": {}, "spend": {"calls": 0, "usd": 0.0}}
        c.update(more)
        return c

    def render(self, step_id, c, fill=()):
        """The prompt a step sends, as _soft builds it: the engine's card, then the step's own prompt. The code steps
        named in `fill` run first, as they do in the run, to fill the bag the prompt reads."""
        R = self.R
        for sid in fill:
            _, s = R.step_def(sid)
            c["bag"][sid] = R.CODE[s["code"]](c, s, None)
        _, step = R.step_def(step_id)
        return R.card(c) + R.PROMPT[step["prompt"]](c, step, None)

    def prompts(self):
        """Every function prompt, for the fixtures: each journey of Identity, each word Priority bargains on, a line with
        and without Root's refusal, a tie and a reading."""
        R, W = self.R, self.W
        out = {}
        said = lambda words: {"word": "request", "words": words}
        for name, words in (("directive", "From now on, every page names the phone line."),
                            ("task", "Add a page about the night clinic, and email the list to the board."),
                            ("query", "Which page lists the doctors?"),
                            ("feedback", "The doctors page is too long."),
                            ("thin", "make it")):
            out["identity.recognise:" + name] = self.render("identity.recognise", self.ctx("Identity", said(words)), ("identity.read",))
            out["identity.take:" + name] = self.render("identity.take", self.ctx("Identity", said(words)), ("identity.read",))
        out["identity.answer"] = self.render("identity.answer", self.ctx("Identity", said("Which page lists the doctors?")), ("identity.read",))
        out["identity.rule"] = self.render("identity.rule", self.ctx("Identity", said("From now on, every page names the phone line.")), ("identity.read",))
        out["identity.weigh"] = self.render("identity.weigh", self.ctx("Identity", said("The doctors page is too long.")), ("identity.read",))
        out["identity.gate"] = self.render("identity.gate", self.ctx("Identity", {"word": "verdict", "engine": "Write", "slot": "Write@pages.v1"}))
        out["identity.judge"] = self.render("identity.judge", self.ctx("Identity", {"word": "verdict", "engine": "Publish", "gate": "identity.gate"}))
        out["identity.close"] = self.render("identity.close", self.ctx("Identity", {"word": "conflict", "engines": LINE, "for": "x-line",
                                                                                     "words": "A guide to the night clinic",
                                                                                     "why": "the envelope has room for one workflow"}))
        out["identity.close:bare"] = self.render("identity.close", self.ctx("Identity", {"word": "conflict"}))
        out["adapt.shape"] = self.render("adapt.shape", self.ctx("Adaptation", {"word": "idea", "words": "what about a patient portal"}))
        out["adapt.line"] = self.render("adapt.line", self.ctx("Adaptation", {"word": "line", "words": "A guide to the night clinic"}))
        out["adapt.line:refused"] = self.render("adapt.line", self.ctx("Adaptation", {"word": "line", "words": "A guide to the night clinic",
                                                                                      "faults": ["Facts is already an engine", "Site reads nothing"]}))
        out["adapt.line:goal"] = self.render("adapt.line", self.ctx("Adaptation", {"word": "line"}))
        for name, pl in (("line:shaped", {"word": "line", "source": "shaped", "engines": LINE}),
                         ("line:library", {"word": "line", "source": "library", "engines": LINE}),
                         ("line:over", {"word": "line", "source": "shaped", "engines": [dict(LINE[0], name="E%d" % i) for i in range(8)]}),
                         ("engine:shaped", {"word": "engine", "engine": "Booking",
                                            "offer": {"shape": {"name": "Booking", "does": "takes a booking for a clinic", "needs": ["internet"]}}}),
                         ("engine:picked", {"word": "engine", "offer": {"pick": "Do", "use_case": "does one thing the owner asks"}}),
                         ("rung", {"word": "rung", "engine": "Write", "step": "write.page", "cost": "a trial of twenty runs beside the model"})):
            out["priority.bargain:" + name] = self.render("priority.bargain", self.ctx("Priority", pl), ("priority.read",))
        c = R._coord_ctx(REF)
        c.update({"slot": "Coordination@tie.fixture", "run": None, "inp": {"v": 0}, "post": None, "bag": {}, "how": {},
                  "spend": {"calls": 0, "usd": 0.0}, "ready": ["Audit", "Identity", "Adaptation"]})
        out["coord.tie"] = self.render("coord.tie", c, ("coord.ready",))
        out["audit.judge"] = self.render("audit.judge", self.ctx("Audit", inp={"v": 1}), ("audit.pick",))
        return out


class TestByteForByte(Fixture):
    def test_m2_1a_every_function_prompt_renders_as_the_inline_builders_did(self):
        got = self.prompts()
        if os.environ.get("FUNCTION_PROMPTS_SNAPSHOT") == "write":
            SNAP.parent.mkdir(parents=True, exist_ok=True)
            SNAP.write_text(json.dumps(got, indent=1, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")
        want = json.loads(SNAP.read_text(encoding="utf-8"))
        self.assertEqual(sorted(got), sorted(want), "the same prompts, for the same fixtures")
        for k in sorted(want):
            self.assertEqual(got[k], want[k], "%s renders as it did before the move" % k)
        self.assertGreaterEqual(len(want), 25)


#: Each function's files, as its page names them (PRD M2.1).
PAGES = {"identity": ["goal", "completeness", "take"], "adaptation": ["goal", "sense", "decide", "make"],
         "priority": ["goal", "bargain"], "coordination": ["goal", "tie"], "audit": ["goal", "judge"]}
BUILDERS = ("p_identity_recognise", "p_identity_take", "p_identity_answer", "p_identity_rule", "p_identity_weigh", "p_identity_gate",
            "p_identity_close", "p_adapt_shape", "p_adapt_line", "p_priority_bargain", "p_coord_tie", "p_audit_judge")


class TestTheFiles(Fixture):
    def bundle(self, drop=None, edit=None):
        """A copy of the shipped bundle the app reads from instead of its own: one file left out, or one file's words changed."""
        tmp = Path(tempfile.mkdtemp(prefix="function-prompts-bundle-"))
        shutil.copytree(self.bundled, tmp / "b")
        if drop:
            (tmp / "b" / (drop + ".md")).unlink()
        if edit:
            path, old, new = edit
            p = tmp / "b" / (path + ".md")
            text = p.read_text(encoding="utf-8")
            self.assertIn(old, text)
            p.write_text(text.replace(old, new), encoding="utf-8")
        self.addCleanup(shutil.rmtree, tmp, True)
        self.R.PROMPTS_DIR = tmp / "b"
        self.R._DEFS.clear()
        return tmp / "b"

    def test_m2_1b_each_function_has_the_files_its_page_names_and_its_prompts_are_read_from_them(self):
        R = self.R
        self.assertEqual({fn: list(files) for fn, files in R.INSTRUCTIONS.items()}, PAGES, "the files its page names, in its order")
        self.assertEqual(R.bundle_faults(), [])
        on_disk = sorted(str(p.relative_to(R.PROMPTS_DIR)) for p in R.PROMPTS_DIR.rglob("*.md"))
        self.assertEqual(on_disk, sorted("%s/%s.md" % (fn, f) for fn, files in PAGES.items() for f in files), "no other file ships")
        for fn, files in PAGES.items():
            for f in files:
                text = (R.PROMPTS_DIR / fn / (f + ".md")).read_text(encoding="utf-8")
                first = text.split("\n", 1)[0]
                self.assertTrue(first and first[0].isupper() and first.endswith("."), "%s/%s says first what it is for" % (fn, f))
                self.assertNotRegex(text.lower(), r"charter|internal system", "%s/%s keeps the screen's words" % (fn, f))
        # what a function does and its skills are its goal file's: the same words its definition holds, as shipped
        for fn in PAGES:
            e = R.engine_def(fn.title())
            self.assertEqual(R._goal_of(REF, fn.title()), (e["description"], e["skills"]), fn)
        # no builder holds a function's words any more: each fills the slots of its file
        import inspect
        for name in BUILDERS:
            self.assertNotIn("Return ONLY", inspect.getsource(getattr(R, name)), name + " still holds its words inline")
        # the words on disk are the words sent: change one file, and the next prompt carries the change
        self.bundle(edit=("identity/take", "Judge one request from the owner.", "Judge one request from the owner, kindly."))
        c = self.ctx("Identity", {"word": "request", "words": "Add a page about parking."})
        self.assertIn("Judge one request from the owner, kindly.\nTHE GOAL: ", self.render("identity.take", c, ("identity.read",)))
        self.bundle(edit=("identity/goal", "- put a question to the owner", "- put one question at a time to the owner"))
        c = self.ctx("Identity", {"word": "request", "words": "Add a page about parking."})
        self.assertIn("gate an effect by rule; put one question at a time to the owner.\n", self.render("identity.take", c, ("identity.read",)))
        self.assertEqual(R.steps_view(REF, "Identity")["skills"][-1], "put one question at a time to the owner", "the screen shows the same words")

    def test_m2_1c_a_file_gone_from_the_bundle_refuses_the_definitions_load(self):
        R = self.R
        self.bundle(drop="identity/take")
        with self.assertRaises(ValueError) as cm:
            R.defs()
        self.assertIn("Identity's take instructions are missing from the bundle", str(cm.exception))
        self.bundle(edit=("priority/bargain", "## cost\n", "## costs\n"))
        with self.assertRaises(ValueError) as cm:
            R.defs()
        self.assertIn("bargain has no part cost", str(cm.exception))
        self.assertIn("bargain, costs: no step reads this part", str(cm.exception))
        self.bundle(edit=("audit/judge", "{{pages}}", "{{pages}} {{findings}}"))
        with self.assertRaises(ValueError) as cm:
            R.defs()
        self.assertIn("judge, judge: the app fills no {{findings}}", str(cm.exception))
        self.bundle()
        self.assertEqual(R.validate(R.defs()), [], "the bundle as shipped loads")


if __name__ == "__main__":
    unittest.main()
