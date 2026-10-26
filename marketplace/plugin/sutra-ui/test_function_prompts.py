"""test_function_prompts.py -- each function's version 1: one agent, its instructions as .md files (PRD M2, S-28).

Named claims:
  M2.1a  every function prompt renders, for the fixtures, byte for byte what the inline builders rendered before the
         move (test_fixtures/function-prompts.snapshot.json was written from them, before the move)
  M2.1b  each function's files are the ones its page names, each in the bundle with its plain first line and the parts
         its steps read; a prompt is read from the file, so the words on disk are the words sent
  M2.1c  a file gone from the bundle, or one missing a part a step reads, refuses the definitions load
  M2.2a  the owner's change is filed as an ask Identity puts to the owner, and nothing changes until the stamp; a
         stamped change is the department's own copy, in its records home, and the next run is sent its words
  M2.2b  a refused change leaves nothing
  M2.2c  replacing the bundle keeps the change: the department's copy wins, a part only the new bundle has is the
         bundle's, and the shipped words again take the department's copy away
  M2.2d  the ask's covering check: words that cannot serve the function are refused at the ask, and again at the stamp
  M2.2e  a file no run reads (Adaptation's decide: the code makes that choice in this version) is kept as the owner's
         note on the stamp, and the ask, the tell and the row all say so, never that the next run uses it

No test reaches a model, the live records home or the network: the prompts are rendered, or sent to a model that is a
function and answers offline, so every step runs its draft.

The snapshot is rendered through the registry (A1.19, R._resolve), so it tests what really runs; a words-migration commit
passes it unchanged, and a prompt changed on purpose regenerates it in a commit of its own, 'snapshot: <reason>'.

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
        named in `fill` run first, as they do in the run, to fill the bag the prompt reads.

        THE SNAPSHOT RULE (PRD A1.16). A name is looked up through R._resolve, with the fixture department's pins and the
        step's own function as the engine, never in R.CODE or R.PROMPT, so what is compared is what a run would send,
        whichever layer's version holds the words. A commit that moves a layer's words into its module must pass the
        snapshot unchanged. A prompt changed on purpose regenerates test_fixtures/function-prompts.snapshot.json only in a
        commit of its own, named 'snapshot: <reason>', whose diff the integrator reviews."""
        R = self.R
        for sid in fill:
            fn, s = R.step_def(sid)
            c["bag"][sid] = R._resolve(c, "code", s["code"], engine=fn)(c, s, None)
        fn, step = R.step_def(step_id)
        return R.card(c) + R._resolve(c, "prompt", step["prompt"], engine=fn)(c, step, None)

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
        # a file whose words the layer holds as typed fields needs none (Audit's, A1.16), so a slot the app does not fill is
        # refused where Audit's words are: a bundle file is read for the layers that have not moved theirs
        self.bundle(edit=("coordination/tie", "{{waiting}}", "{{waiting}} {{findings}}"))
        with self.assertRaises(ValueError) as cm:
            R.defs()
        self.assertIn("tie, tie: the app fills no {{findings}}", str(cm.exception))
        self.bundle()
        self.assertEqual(R.validate(R.defs()), [], "the bundle as shipped loads")


class Offline:
    """The model, as a function that is never there: each step runs its draft, and every prompt it was sent is kept."""

    def __init__(self):
        self.prompts = []

    def __call__(self, prompt, step):
        self.prompts.append((step["id"], prompt))
        return None, 0.0, "offline"


class TestTheOwnersChange(Fixture):
    def setUp(self):
        super().setUp()
        self.R.WAITS = (0, 0, 0)
        self.M = self.R.MODEL = Offline()
        import website_api
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        app = FastAPI()
        app.include_router(website_api.router)
        self.c = TestClient(app)

    def tearDown(self):
        self.R.MODEL = None
        super().tearDown()

    def change(self, fn, file, text):
        return self.c.post("/api/native/%s/instructions" % REF, json={"fn": fn, "file": file, "text": text})

    def row(self, fn, file):
        rows = self.c.get("/api/native/%s/steps/%s" % (REF, fn.title())).json()["instructions"]
        return next(x for x in rows if x["file"] == file)

    def test_m2_2a_a_stamped_change_is_used_by_the_next_run(self):
        R, W = self.R, self.W
        take = R._instruction("identity", "take")
        mine = take.replace("Recognise what kind of words the owner has given.", "Recognise, in plain words, what kind of words the owner has given.")
        r = self.change("identity", "take", mine)
        self.assertEqual(r.status_code, 200, r.text)
        a = r.json()["ask"]
        self.assertEqual((a["kind"], a["fn"], a["file"], a["status"]), ("instructions", "identity", "take", "pending"))
        self.assertEqual(a["text"], "Change Identity's take instructions to your words")
        # nothing changes until the stamp: no copy of its own, the shipped words read, the row says it waits
        self.assertFalse(R._own(REF, "identity", "take").exists())
        self.assertEqual(R._instruction("identity", "take", REF), take)
        row = self.row("identity", "take")
        self.assertTrue(row["as_shipped"])
        self.assertEqual(row["waits"]["ask"], a["id"])
        # the row's line in the owner's words (PRD M1.7: go, ask or stop); the file's own text, which the owner changes, as it is
        self.assertEqual(row["lead"], "How to judge a request: go, ask or stop.")
        self.assertTrue(row["text"].startswith("How to judge a request: go, ask or refuse."), row["text"][:60])
        self.assertIsNone(self.row("identity", "goal")["waits"], "only the file changed waits")
        # Identity put it to the owner, on the board, in its own thread
        asked = [p for p in R.board(REF) if p["thread"] == a["thread"]]
        self.assertEqual([(p["src"], p["dst"], p["msg_type"], p["payload"]["word"]) for p in asked], [("Identity", ["Owner"], "request", "instructions")])
        # one change waits per file
        r = self.change("identity", "take", mine.replace("plain words", "few words"))
        self.assertEqual(r.status_code, 400)
        self.assertIn("already waits for your stamp", r.json()["detail"])
        # the stamp: the department's own copy, read by the next run
        W.decide_ask(REF, a["id"], True)
        W.run_until_idle(REF, limit=200)
        self.assertEqual(R._own(REF, "identity", "take").read_text(encoding="utf-8"), mine)
        self.assertTrue(str(R._own(REF, "identity", "take")).startswith(str(W.ddir(REF))), "kept in the records home")
        row = self.row("identity", "take")
        self.assertFalse(row["as_shipped"])
        self.assertIsNone(row["waits"])
        self.assertEqual(row["text"], mine)
        self.assertTrue(any("Identity's take now reads as you changed it; the next run uses it." == str(p["payload"].get("done")) for p in R.board(REF)),
                        "Identity says it is in place")
        self.assertTrue(row["read"], "a run reads take")
        self.M.prompts.clear()
        W.owner_ask(REF, "Which page lists the doctors?")
        W.run_until_idle(REF, limit=200)
        sent = [p for sid, p in self.M.prompts if sid == "identity.recognise"]
        self.assertTrue(sent, "the next run recognised the words")
        self.assertIn("\n\nRecognise, in plain words, what kind of words the owner has given. There are five kinds", sent[-1])
        # another department keeps the shipped words
        W.create("dref-prompts0002", "Second Website", None)
        self.assertEqual(R._instruction("identity", "take", "dref-prompts0002"), take)

    def test_m2_2b_a_refused_change_leaves_nothing(self):
        R, W = self.R, self.W
        judge = R._instruction("audit", "judge")
        r = self.change("audit", "judge", judge.replace("At most eight findings.", "At most three findings."))
        self.assertEqual(r.status_code, 200, r.text)
        a = r.json()["ask"]
        W.decide_ask(REF, a["id"], False)
        W.run_until_idle(REF, limit=200)
        self.assertEqual(next(x for x in W.asks(REF) if x["id"] == a["id"])["status"], "refused")
        self.assertFalse((W.ddir(REF) / "prompts").exists(), "nothing is written")
        self.assertEqual(R._instruction("audit", "judge", REF), judge)
        row = self.row("audit", "judge")
        self.assertTrue(row["as_shipped"])
        self.assertIsNone(row["waits"])
        self.assertNotIn("At most three findings.", self.render("audit.judge", self.ctx("Audit", inp={"v": 1}), ("audit.pick",)))

    def tie_ctx(self):
        c = self.R._coord_ctx(REF)
        c.update({"slot": "Coordination@tie.fixture", "run": None, "inp": {"v": 0}, "post": None, "bag": {}, "how": {},
                  "spend": {"calls": 0, "usd": 0.0}, "ready": ["Audit", "Identity", "Adaptation"]})
        return c

    def test_m2_2c_replacing_the_bundle_keeps_the_change(self):
        """Run on Coordination's tie: Audit holds its words as typed fields (A1.16), which a department's whole-file copy
        does not reach, so the file-for-file change this test is about is the one a layer that has not moved its words keeps."""
        R, W = self.R, self.W
        tie = R._instruction("coordination", "tie")
        mine = tie.replace("Say who goes first.", "Say who goes first, in few words.")
        a = self.change("coordination", "tie", mine).json()["ask"]
        W.decide_ask(REF, a["id"], True)
        W.run_until_idle(REF, limit=200)
        # an update: a new bundle in the old one's place, its own words for tie and a part the old one did not have
        tmp = Path(tempfile.mkdtemp(prefix="function-prompts-update-"))
        self.addCleanup(shutil.rmtree, tmp, True)
        shutil.copytree(self.bundled, tmp / "b")
        p = tmp / "b" / "coordination" / "tie.md"
        p.write_text(p.read_text(encoding="utf-8").replace("Say who goes first.", "Say who goes first, and why.")
                     + "\n## again\n\nRead it again, slowly.\n", encoding="utf-8")
        R.PROMPTS_DIR = tmp / "b"
        R.INSTRUCTIONS["coordination"]["tie"]["again"] = ()
        self.addCleanup(R.INSTRUCTIONS["coordination"]["tie"].pop, "again", None)
        R._DEFS.clear()
        self.assertEqual(R.validate(R.defs()), [], "the new bundle loads")
        self.assertEqual(R._own(REF, "coordination", "tie").read_text(encoding="utf-8"), mine, "the records home is untouched")
        sent = self.render("coord.tie", self.tie_ctx(), ("coord.ready",))
        self.assertIn("Say who goes first, in few words.", sent, "the owner's words, not the update's")
        self.assertNotIn("Say who goes first, and why.", sent)
        self.assertEqual(R._prompt("coordination", "tie", "again", REF), "Read it again, slowly.", "a part only the new bundle has is the bundle's")
        # the shipped words again take the department's copy away, so the next bundle's words reach it
        a = self.change("coordination", "tie", R._instruction("coordination", "tie")).json()["ask"]
        W.decide_ask(REF, a["id"], True)
        W.run_until_idle(REF, limit=200)
        self.assertFalse(R._own(REF, "coordination", "tie").exists())
        self.assertTrue(self.row("coordination", "tie")["as_shipped"])

    def test_m2_2d_words_that_cannot_serve_the_function_are_refused_at_the_ask_and_at_the_stamp(self):
        R, W = self.R, self.W
        take = R._instruction("identity", "take")
        for fn, file, text, why in (("marketing", "goal", take, "no function named marketing"),
                                    ("identity", "voice", take, "Identity has no instructions named voice"),
                                    ("identity", "take", "   ", "say what the instructions should be"),
                                    ("identity", "take", take, "the words Identity's take holds now"),
                                    ("identity", "take", take.replace("## gate", "## gates"), "take has no part gate"),
                                    ("identity", "take", take.replace("{{engine}}", "{{engine}} {{budget}}"), "the app fills no {{budget}}"),
                                    ("identity", "take", "## take\n\nJudge it.\n", "take does not say first, in a line, what it is for"),
                                    ("identity", "take", "x" * (R.INSTRUCTIONS_MAX + 1), "too long")):
            r = self.change(fn, file, text)
            self.assertEqual(r.status_code, 400, (fn, file, why))
            self.assertIn(why, r.json()["detail"])
        self.assertEqual([a for a in W.asks(REF) if a["kind"] == "instructions"], [], "none of them was filed")
        os.environ["SUTRA_ENGINE_RUNTIME"] = "1"
        try:
            W.create("dref-prompts0003", "Old Website", None)
        finally:
            os.environ.pop("SUTRA_ENGINE_RUNTIME", None)
        self.assertEqual(self.c.post("/api/native/dref-prompts0003/instructions", json={"fn": "identity", "file": "take", "text": take}).status_code, 404)
        # filed when they served, stamped after the bundle asks for more: not written, and the owner hears why
        a = self.change("identity", "take", take.replace("Judge one request from the owner.", "Judge one request.")).json()["ask"]
        R.INSTRUCTIONS["identity"]["take"]["enough"] = ()
        self.addCleanup(R.INSTRUCTIONS["identity"]["take"].pop, "enough", None)
        W.decide_ask(REF, a["id"], True)
        W.run_until_idle(REF, limit=200)
        self.assertFalse(R._own(REF, "identity", "take").exists())
        self.assertTrue(any("was not put in place: take has no part enough" in str(p["payload"].get("done")) for p in R.board(REF)))

    def test_m2_2e_a_file_no_run_reads_is_kept_as_the_owners_note_and_the_owner_is_told_so(self):
        R, W = self.R, self.W
        import inspect
        # which files a run reads: every one but Adaptation's decide, which holds no part and which no call reads
        for fn, files in PAGES.items():
            for f in files:
                self.assertEqual(self.row(fn, f)["read"], (fn, f) != ("adaptation", "decide"), (fn, f))
        self.assertEqual(R.INSTRUCTIONS["adaptation"]["decide"], {})
        self.assertNotIn('_prompt("adaptation", "decide"', inspect.getsource(R))
        decide = R._instruction("adaptation", "decide")
        mine = decide + "\nPrefer a checklist to code when both would serve.\n"
        r = self.change("adaptation", "decide", mine)
        self.assertEqual(r.status_code, 200, r.text)
        a = r.json()["ask"]
        asked = [p for p in R.board(REF) if p["thread"] == a["thread"]]
        self.assertEqual(len(asked), 1)
        self.assertEqual(asked[0]["payload"]["objective"], "Change Adaptation's decide instructions to your words? In this version the code "
                         "makes this choice, so no run reads these words yet: stamp to keep them as your note, or say no to keep them as they are.")
        W.decide_ask(REF, a["id"], True)
        W.run_until_idle(REF, limit=200)
        self.assertEqual(R._own(REF, "adaptation", "decide").read_text(encoding="utf-8"), mine.rstrip("\n") + "\n", "kept as the owner wrote it")
        told = [str(p["payload"]["done"]) for p in R.board(REF) if p["payload"].get("word") == "instructions" and p["payload"].get("done")]
        self.assertEqual(told, ["Adaptation's decide now reads as you changed it, kept as your note; in this version the code makes this "
                                "choice, so no run reads it yet."], "the owner is told the truth")
        row = self.row("adaptation", "decide")
        self.assertEqual((row["as_shipped"], row["read"], row["waits"]), (False, False, None))


if __name__ == "__main__":
    unittest.main()
