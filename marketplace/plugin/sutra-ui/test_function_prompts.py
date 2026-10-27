"""test_function_prompts.py -- each function's version 1: one agent, its instructions as typed fields (PRD M2, S-28, A1.16).

Named claims:
  M2.1a  every function prompt renders, for the fixtures, byte for byte what the inline builders rendered before the
         move (test_fixtures/function-prompts.snapshot.json was written from them, before the move)
  M2.1b  each function's groups are the ones its page names, each with its plain first line and the parts its steps read; a
         prompt is made of the layer's words, so the words held are the words sent (the .md files they came from are retired,
         W3-PROOF X1: test_fixtures/retired-prompt-parts.json keeps their text, and no folder of them ships)
  M2.1c  a part with no words, or words the interface cannot serve, refuses the definitions load
  M2.2a  the owner's change is one typed field, filed as an ask Identity puts to the owner, and nothing changes until the
         stamp; a stamped value is the department's own, in its records home, and the next run is sent its words
  M2.2b  a refused change leaves nothing
  M2.2c  an update of the app that changes the shipped words keeps the owner's value; a field the owner never changed reads
         the update; the shipped words again take the owner's value away
  M2.2d  the field's type and the interface's rules: words that cannot serve the function are refused at the ask, and again
         at the stamp ('{{' and 'Return ONLY' among them)
  M2.2e  a part no run reads (Adaptation's decide note: the code makes that choice in this version) is kept as the owner's
         note on the stamp, and the ask, the tell and the field all say so, never that the next run uses it
  M2.2f  a whole-file change made before fields were typed is kept as the owner's note, with one tell; no run reads it

No test reaches a model, the live records home or the network: the prompts are rendered, or sent to a model that is a
function and answers offline, so every step runs its draft.

The snapshot is rendered through the registry (A1.19, R._resolve), so it tests what really runs; a words-migration commit
passes it unchanged, and a prompt changed on purpose regenerates it in a commit of its own, 'snapshot: <reason>'.

Run: python test_function_prompts.py   (or pytest). To take a new snapshot after a prompt is changed on purpose:
     FUNCTION_PROMPTS_SNAPSHOT=write python test_function_prompts.py
"""
import copy
import importlib
import json
import os
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

REF = "dref-prompts0001"
SNAP = Path(__file__).parent / "test_fixtures" / "function-prompts.snapshot.json"
#: the text of every part the retired .md bundle held (W3-PROOF X1), {"leads": {layer: {group: first line}}, "parts": {layer: {group:
#: {part: text}}}}: what the layers' words are held to byte for byte. A part that came after the bundle (S.ADDED_PARTS) has none.
RETIRED = json.loads((Path(__file__).parent / "test_fixtures" / "retired-prompt-parts.json").read_text(encoding="utf-8"))


def retired(layer, group, part):
    """The text of a part as the retired .md file said it, its inputs still in {{name}} markers (KeyError for an added part)."""
    return RETIRED["parts"][layer][group][part]
KEYS = ("SUTRA_NATIVE_DEPT_HOME", "SUTRA_NATIVE_HOME", "SUTRA_WEBSITE_OFFLINE", "SUTRA_ENGINE_RUNTIME", "SUTRA_MOTOR",
        "SUTRA_ALLOW_DEFAULT_HOME_IN_TESTS", "J2_FLOW_V1", "J2_ADAPT_MAKE")
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

    def holds(self, fn, group, part, field, old, new):
        """One word of a layer's own words changed until the test ends. `old` is a piece of a text field's value, or an item
        of a list field's."""
        import layers
        module = layers.load("%s/v1" % fn)
        words = copy.deepcopy(module.WORDS)
        value = words[group][part][field]
        words[group][part][field] = [new if x == old else x for x in value] if isinstance(value, list) else value.replace(old, new)
        self.assertNotEqual(words[group][part][field], value, "%s's %s.%s holds %r" % (fn, group, part, old))
        patch = mock.patch.object(module, "WORDS", words)
        patch.start()
        self.addCleanup(patch.stop)

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
        # the Library's own line, fitted to the goal (M5.2): the line as the Library has it, the required engine marked
        out["adapt.fit"] = self.render("adapt.fit", self.ctx("Adaptation", {"word": "line", "words": "A guide to the night clinic"}), ("adapt.source",))
        # the make setting on (M6.4): a website's line Root sent back is made, with the practices in place read by adapt.source
        os.environ["J2_ADAPT_MAKE"] = "1"
        try:
            out["adapt.line:shape"] = self.render("adapt.line", self.ctx("Adaptation", {"word": "line", "words": "A guide to the night clinic",
                                                                                        "faults": ["the plan leaves out D1"]}), ("adapt.source",))
        finally:
            os.environ.pop("J2_ADAPT_MAKE", None)
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
        # the next round (M9.1), last: a reading that found D1 not met, then the same ask once a round for it has run and the reading
        # still finds it not met. Both are written to the fixture's records for the renders and taken away after them, so the
        # records are as they were and a second call of this method renders what the first did
        journals = [W.ddir(REF) / "readings.jsonl", W.ddir(REF) / "rounds.jsonl"]
        for journal in journals:
            journal.unlink(missing_ok=True)
        try:
            W.append_row(REF, "readings.jsonl", {
                "schema_version": 1, "id": "r-0a1b2c3d", "v": 1, "artifact": "Live site", "cycle_id": None, "round": None, "read": True,
                "why_not_read": None,
                "items": [{"id": "D1", "subject": "Live site", "claim": "the doctors page does not carry the phone line",
                           "evidence": "doctors.html has no number", "method": "model", "verdict": "not_met", "severity": "high"}],
                "findings": [{"id": "F1", "severity": "high", "claim": "the doctors page does not carry the phone line", "where": "doctors",
                              "item": "D1", "went_to": "Identity"}], "at": "2026-10-23T10:10:00+05:30"})
            ask = {"word": "next", "items": ["D1"], "reading": "r-0a1b2c3d", "findings": ["F1"]}
            out["adapt.next"] = self.render("adapt.next", self.ctx("Adaptation", ask), ("adapt.hearnext",))
            W.append_row(REF, "rounds.jsonl", {
                "schema_version": 1, "round": 1, "at": "2026-10-23T10:12:00+05:30", "cycle_id": None, "correction": "Put the phone line on every page",
                "fixes": ["F1"], "covers": ["D1"], "estimate": {"calls": 8, "usd": 0.36}, "status": "granted", "reading": "r-0a1b2c3d"})
            out["adapt.next:repeat"] = self.render("adapt.next", self.ctx("Adaptation", ask), ("adapt.hearnext",))
        finally:
            for journal in journals:
                journal.unlink(missing_ok=True)
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
            "p_identity_close", "p_adapt_shape", "p_coord_tie", "p_audit_judge")


class TestTheWords(Fixture):
    def test_m2_1b_each_function_has_the_groups_its_page_names_and_its_prompts_are_made_of_its_words(self):
        R = self.R
        import layers
        self.assertEqual({fn: list(files) for fn, files in R.INSTRUCTIONS.items()}, PAGES, "the groups its page names, in its order")
        self.assertEqual(R.prompt_faults(), [])
        self.assertFalse((Path(__file__).parent / "function-prompts").exists(), "no folder of .md files ships: the words are the layers'")
        self.assertFalse(hasattr(R, "PROMPTS_DIR") or hasattr(R, "_instruction"), "and the runtime reads none")
        for fn, files in PAGES.items():
            for f in files:
                first = R.layer_schema.GROUPS[fn][f]
                self.assertTrue(first and first[0].isupper() and first.endswith("."), "%s/%s says first what it is for" % (fn, f))
                self.assertNotRegex(first.lower(), r"charter|internal system", "%s/%s keeps the screen's words" % (fn, f))
                for part in R.layer_schema.PROMPTS[fn][f]:
                    sent = layers.prompt(None, fn, f, part, **layers.prompts.sample_inputs(fn, f, part))
                    self.assertNotRegex(sent.lower(), r"charter|internal system", "%s/%s, %s keeps the screen's words" % (fn, f, part))
        # what a function does and its skills are its goal's: the same words its definition holds, as shipped
        for fn in PAGES:
            e = R.engine_def(fn.title())
            self.assertEqual(R._goal_of(REF, fn.title()), (e["description"], e["skills"]), fn)
        # no builder holds a function's words any more: each fills the slots of its part
        import inspect
        for name in BUILDERS:
            self.assertNotIn("Return ONLY", inspect.getsource(getattr(R, name)), name + " still holds its words inline")
        for fn in R.layer_schema.FUNCTION_LAYERS:            # and the builders a layer's version holds of its own (the ones it took over)
            for name, body in layers.load(R.layer_schema.DEFAULT_PINS[fn]).PROMPT.items():
                if not hasattr(body, "legacy"):
                    self.assertNotIn("Return ONLY", inspect.getsource(body), "%s's %s still holds its words inline" % (fn, name))
        # the words held are the words sent: Identity holds all of its own (A1.16), so change one of them, and the next prompt
        # carries the change
        self.holds("identity", "take", "take", "task", "Judge one request from the owner.", "Judge one request from the owner, kindly.")
        c = self.ctx("Identity", {"word": "request", "words": "Add a page about parking."})
        self.assertIn("Judge one request from the owner, kindly.\nTHE GOAL: ", self.render("identity.take", c, ("identity.read",)))
        self.holds("identity", "goal", "skills", "items", "put a question to the owner", "put one question at a time to the owner")
        c = self.ctx("Identity", {"word": "request", "words": "Add a page about parking."})
        self.assertIn("gate an effect by rule; put one question at a time to the owner.\n", self.render("identity.take", c, ("identity.read",)))
        self.assertEqual(R.steps_view(REF, "Identity")["skills"][-1], "put one question at a time to the owner", "the screen shows the same words")

    def test_m2_1c_a_part_with_no_words_or_words_that_cannot_serve_refuses_the_definitions_load(self):
        R = self.R
        import layers
        self.assertEqual(R.validate(R.defs()), [], "as shipped the definitions load")

        def refused(layer, edit):
            """The definitions load with `edit` laid over the layer's words and layout: the ValueError it raises, said."""
            module = layers.load("%s/v1" % layer)
            words, layout = copy.deepcopy(module.WORDS), copy.deepcopy(module.LAYOUT)
            edit(words, layout)
            with mock.patch.object(module, "WORDS", words), mock.patch.object(module, "LAYOUT", layout):
                R._DEFS.clear()
                try:
                    with self.assertRaises(ValueError) as cm:
                        R.defs()
                finally:
                    R._DEFS.clear()
            return str(cm.exception)
        # words the app cannot fill: a layout that asks for an input nothing supplies
        got = refused("identity", lambda w, l: l["take"].update(gate=l["take"]["gate"].replace("{{engine}}", "{{engine}} {{budget}}")))
        self.assertIn("Identity's take instructions, gate: the layout holds {{budget}} and the app fills no such input", got)
        got = refused("audit", lambda w, l: l["judge"].update(judge=l["judge"]["judge"].replace("{{pages}}", "{{pages}} {{findings}}")))
        self.assertIn("Audit's judge instructions, judge: the layout holds {{findings}} and the app fills no such input", got)
        # a part of the interface the layer holds no words for (the typed form of a file gone, or missing a part a step reads)
        got = refused("priority", lambda w, l: (w["bargain"].pop("cost"), l["bargain"].pop("cost")))
        self.assertIn("Priority's bargain instructions, cost: the version holds no words for it", got)
        got = refused("identity", lambda w, l: (w.pop("take"), l.pop("take")))
        self.assertIn("Identity's take instructions, gate: the version holds no words for it", got)
        # words for a part the interface does not name
        got = refused("priority", lambda w, l: (w["bargain"].update(costs={"task": "x"}), l["bargain"].update(costs="{task}")))
        self.assertIn("Priority's bargain instructions, costs: Priority has no part bargain.costs", got)
        self.assertEqual(R.validate(R.defs()), [], "and as shipped again")


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

    def change(self, fn, group, part, field, value):
        return self.c.post("/api/native/%s/instructions" % REF, json={"fn": fn, "group": group, "part": part, "field": field, "value": value})

    def groups(self, fn, ref=REF):
        return self.c.get("/api/native/%s/steps/%s" % (ref, fn.title())).json()["instructions"]

    def row(self, fn, group, part):
        return next(p for g in self.groups(fn) if g["group"] == group for p in g["parts"] if p["part"] == part)

    def field(self, fn, group, part, name):
        return next(f for f in self.row(fn, group, part)["fields"] if f["field"] == name)

    def stored(self, ref=None):
        p = self.W.ddir(ref or REF) / "instructions.json"
        return json.loads(p.read_text(encoding="utf-8")) if p.is_file() else None

    def shipped(self, fn, group, part, name):
        return self.R.layers.prompts.defaults(REF, fn, group, part)[name]

    def update_shipped(self, fn, group, part, name, old, new):
        """An update of the app that changes the words a part ships with: in the layer's WORDS, which hold every part."""
        R = self.R
        module = R.layers.prompts._module(REF, fn, group, part)
        self.assertIsNotNone(module, "%s holds %s.%s" % (fn, group, part))
        words = copy.deepcopy(module.WORDS)
        self.assertIn(old, words[group][part][name])
        words[group][part][name] = words[group][part][name].replace(old, new)
        patch = mock.patch.object(module, "WORDS", words)
        patch.start()
        self.addCleanup(patch.stop)

    def stamp(self, ask):
        self.W.decide_ask(REF, ask["id"], True)
        self.W.run_until_idle(REF, limit=200)

    def tells(self):
        return [str(p["payload"]["done"]) for p in self.R.board(REF) if p["payload"].get("word") == "instructions" and p["payload"].get("done")]

    def test_m2_2a_a_stamped_value_is_used_by_the_next_run(self):
        R, W = self.R, self.W
        shipped = self.shipped("identity", "take", "recognise", "task")
        mine = shipped.replace("Recognise what kind of words the owner has given.", "Recognise, in plain words, what kind of words the owner has given.")
        r = self.change("identity", "take", "recognise", "task", mine)
        self.assertEqual(r.status_code, 200, r.text)
        a = r.json()["ask"]
        self.assertEqual((a["kind"], a["fn"], a["group"], a["part"], a["field"], a["status"]),
                         ("instructions", "identity", "take", "recognise", "task", "pending"))
        self.assertEqual(a["text"], "Change Identity's recognise task to your words")
        # nothing changes until the stamp: no value of its own, the shipped words read, the field says it waits
        self.assertIsNone(self.stored())
        f = self.field("identity", "take", "recognise", "task")
        self.assertEqual((f["value"], f["as_shipped"], f["waits"]["ask"]), (shipped, True, a["id"]))
        # the group's line in the owner's words (PRD M1.7: go, ask or stop); the field's own words, which the owner changes, as they are
        self.assertEqual(next(g for g in self.groups("identity") if g["group"] == "take")["lead"], "How to judge a request: go, ask or stop.")
        self.assertIsNone(self.field("identity", "take", "take", "task")["waits"], "only the field changed waits")
        # Identity put it to the owner, on the board, in its own thread
        asked = [p for p in R.board(REF) if p["thread"] == a["thread"]]
        self.assertEqual([(p["src"], p["dst"], p["msg_type"], p["payload"]["word"]) for p in asked], [("Identity", ["Owner"], "request", "instructions")])
        # one change waits per field; another field of the same part is its own change
        r = self.change("identity", "take", "recognise", "task", mine.replace("plain words", "few words"))
        self.assertEqual(r.status_code, 400)
        self.assertIn("already waits for your stamp", r.json()["detail"])
        other = self.change("identity", "take", "take", "guidance", "go: do it. ask: it reaches outside. refuse: it breaks a rule.")
        self.assertEqual(other.status_code, 200, other.text)
        W.decide_ask(REF, other.json()["ask"]["id"], False)
        # the stamp: the typed value, in the department's records home, read by the next run
        self.stamp(a)
        doc = self.stored()
        self.assertEqual(doc["values"]["identity"]["take"]["recognise"]["task"]["value"], mine)
        self.assertEqual(doc["values"]["identity"]["take"]["recognise"]["task"]["ask"], a["id"])
        self.assertTrue(str(R.layers.prompts.values_path(REF)).startswith(str(W.ddir(REF))), "kept in the records home")
        f = self.field("identity", "take", "recognise", "task")
        self.assertEqual((f["value"], f["as_shipped"], f["waits"]), (mine, False, None))
        self.assertIn("Identity's recognise task now reads as you changed it; the next run uses it.", self.tells(), "Identity says it is in place")
        self.assertTrue(self.row("identity", "take", "recognise")["read"], "a run reads recognise")
        self.M.prompts.clear()
        W.owner_ask(REF, "Which page lists the doctors?")
        W.run_until_idle(REF, limit=200)
        sent = [p for sid, p in self.M.prompts if sid == "identity.recognise"]
        self.assertTrue(sent, "the next run recognised the words")
        self.assertIn("\n" + mine + "\nTHE GOAL: ", sent[-1])
        # another department keeps the shipped words
        W.create("dref-prompts0002", "Second Website", None)
        self.assertEqual(R.layers.words("dref-prompts0002", "identity", "take", "recognise")["task"], shipped)

    def test_m2_2b_a_refused_change_leaves_nothing(self):
        R, W = self.R, self.W
        shipped = self.shipped("audit", "judge", "judge", "guidance")
        r = self.change("audit", "judge", "judge", "guidance", shipped.replace("At most eight findings.", "At most three findings."))
        self.assertEqual(r.status_code, 200, r.text)
        a = r.json()["ask"]
        W.decide_ask(REF, a["id"], False)
        W.run_until_idle(REF, limit=200)
        self.assertEqual(next(x for x in W.asks(REF) if x["id"] == a["id"])["status"], "refused")
        self.assertIsNone(self.stored(), "nothing is written")
        self.assertFalse((W.ddir(REF) / "prompts").exists())
        self.assertEqual(self.shipped("audit", "judge", "judge", "guidance"), shipped)
        f = self.field("audit", "judge", "judge", "guidance")
        self.assertEqual((f["value"], f["as_shipped"], f["waits"]), (shipped, True, None))
        self.assertNotIn("At most three findings.", self.render("audit.judge", self.ctx("Audit", inp={"v": 1}), ("audit.pick",)))

    def test_m2_2c_an_update_keeps_the_value_and_the_shipped_words_again_take_it_away(self):
        R, W = self.R, self.W
        shipped = self.shipped("audit", "judge", "judge", "guidance")
        mine = shipped.replace("At most eight findings.", "At most three findings.")
        self.stamp(self.change("audit", "judge", "judge", "guidance", mine).json()["ask"])
        before = self.stored()
        # an update: the app ships other words for the part (its guidance, and its task, which the owner never changed)
        self.update_shipped("audit", "judge", "judge", "guidance", "At most eight findings.", "At most ten findings.")
        self.update_shipped("audit", "judge", "judge", "task", "Check what the department made", "Look at what the department made")
        self.assertEqual(self.stored(), before, "the records home is untouched")
        sent = self.render("audit.judge", self.ctx("Audit", inp={"v": 1}), ("audit.pick",))
        self.assertIn("At most three findings.", sent, "the owner's value, not the update's")
        self.assertNotIn("At most ten findings.", sent)
        self.assertIn("Look at what the department made", sent, "a field the owner never changed reads the update")
        # the shipped words again take the owner's value away, so the next update reaches the department
        new = self.shipped("audit", "judge", "judge", "guidance")
        self.assertIn("At most ten findings.", new)
        self.stamp(self.change("audit", "judge", "judge", "guidance", new).json()["ask"])
        self.assertIsNone(self.stored(), "the value is gone, and the file with it")
        self.assertTrue(self.field("audit", "judge", "judge", "guidance")["as_shipped"])
        self.assertIn("Audit's judge guidance now reads as shipped; the next run uses it.", self.tells())

    def test_m2_2d_words_that_cannot_serve_the_function_are_refused_at_the_ask_and_at_the_stamp(self):
        R, W = self.R, self.W
        take = self.shipped("identity", "take", "take", "task")
        for fn, group, part, field, value, why in (
                ("marketing", "goal", "does", "text", "x", "no function named marketing"),
                ("identity", "voice", "take", "task", "x", "Identity has no instructions named voice"),
                ("identity", "take", "nowhere", "task", "x", "Identity's take instructions have no part nowhere"),
                ("identity", "take", "take", "colour", "x", "has no colour you may change"),
                ("identity", "take", "take", "task", "   ", "task is empty"),
                ("identity", "take", "take", "task", take, "these are the words Identity's take task holds now"),
                ("identity", "take", "take", "task", "Judge {{words}} kindly", "task cannot hold '{{' or '}}'"),
                ("identity", "take", "take", "task", "Judge it.}}", "task cannot hold '{{' or '}}'"),
                ("identity", "take", "take", "task", "Judge it. Return ONLY yes", "task cannot hold 'Return ONLY'"),
                ("identity", "take", "take", "task", "x" * 1201, "task is longer than 1200 characters"),
                ("identity", "take", "take", "task", 5, "task has to be words"),
                ("identity", "goal", "does", "text", "line one\nline two", "text must be one line"),
                ("identity", "goal", "skills", "items", [], "items needs at least 1 of them"),
                ("identity", "goal", "skills", "items", ["ok"] * 13, "items can hold at most 12 of them"),
                ("identity", "goal", "skills", "items", ["ok", "x" * 161], "items (item 2) is longer than 160 characters"),
                ("identity", "goal", "skills", "items", "not a list", "items has to be a list")):
            r = self.change(fn, group, part, field, value)
            self.assertEqual(r.status_code, 400, (fn, group, part, field, why))
            self.assertIn(why, r.json()["detail"])
        self.assertEqual([a for a in W.asks(REF) if a["kind"] == "instructions"], [], "none of them was filed")
        os.environ["SUTRA_ENGINE_RUNTIME"] = "1"
        try:
            W.create("dref-prompts0003", "Old Website", None)
        finally:
            os.environ.pop("SUTRA_ENGINE_RUNTIME", None)
        body = {"fn": "identity", "group": "take", "part": "take", "field": "task", "value": take + " Kindly."}
        self.assertEqual(self.c.post("/api/native/dref-prompts0003/instructions", json=body).status_code, 404)
        # the old body names no part and no field
        r = self.c.post("/api/native/%s/instructions" % REF, json={"fn": "identity", "file": "take", "text": "Judge it."})
        self.assertEqual((r.status_code, r.json()["detail"]), (400, "say which part and which field"))
        # filed when it served, stamped after the interface asks for less: not written, and the owner hears why
        a = self.change("identity", "take", "take", "task", take + " Kindly.").json()["ask"]
        S = self.R.layer_schema
        was = S.DEFS["field.task"]
        S.DEFS["field.task"] = S.field(10, multiline=True)
        self.addCleanup(S.DEFS.__setitem__, "field.task", was)
        self.stamp(a)
        self.assertIsNone(self.stored())
        self.assertTrue(any("Identity's take task was not put in place: task is longer than 10 characters" in t for t in self.tells()))
        # filed by a hand that skipped the ask, '{{' and 'Return ONLY' are refused at the stamp too
        S.DEFS["field.task"] = was
        for n, bad in enumerate(("Judge {{words}}", "Judge it. Return ONLY yes")):
            row = {"id": "a-bad0000%d" % n, "kind": "instructions", "engine": "Identity", "fn": "identity", "group": "take", "part": "take",
                   "field": "task", "value": bad, "text": "x", "status": "pending", "created": W.now(), "thread": None}
            out = R._apply_instructions(REF, W.dept(REF), row)
            self.assertIn("could not put the owner's change", out["said"])
        self.assertIsNone(self.stored(), "neither was written")

    def test_m2_2e_a_part_no_run_reads_is_kept_as_the_owners_note_and_the_owner_is_told_so(self):
        R, W = self.R, self.W
        # which parts a run reads: every one but Adaptation's decide note, which no step reads, and a function's own done, which
        # only its page reads (A3.4.6)
        for fn, groups in R.INSTRUCTIONS.items():
            for group, parts in groups.items():
                for part in parts:
                    self.assertEqual(self.row(fn, group, part)["read"], (fn, group, part) != ("adaptation", "decide", "note") and (group, part) != ("goal", "done"),
                                     (fn, group, part))
        row = self.row("adaptation", "decide", "note")
        self.assertEqual((row["read"], row["read_by"], row["inputs"], row["answers"]), (False, [], [], []))
        mine = self.shipped("adaptation", "decide", "note", "text") + " Prefer a checklist to code when both would serve."
        r = self.change("adaptation", "decide", "note", "text", mine)
        self.assertEqual(r.status_code, 200, r.text)
        a = r.json()["ask"]
        asked = [p for p in R.board(REF) if p["thread"] == a["thread"]]
        self.assertEqual(len(asked), 1)
        self.assertEqual(asked[0]["payload"]["objective"], "Change Adaptation's decide note to your words? In this version the code makes this "
                         "choice, so no run reads these words yet: stamp to keep them as your note, or say no to keep them as they are.")
        self.stamp(a)
        self.assertEqual(self.stored()["values"]["adaptation"]["decide"]["note"]["text"]["value"], mine, "kept as the owner wrote it")
        self.assertEqual([t for t in self.tells() if t.startswith("Adaptation")],
                         ["Adaptation's decide note now reads as you changed it, kept as your note; in this version the code makes this "
                          "choice, so no run reads it yet."], "the owner is told the truth")
        f = self.field("adaptation", "decide", "note", "text")
        self.assertEqual((f["value"], f["as_shipped"], f["waits"], self.row("adaptation", "decide", "note")["read"]), (mine, False, None, False))

    def test_m2_2f_an_earlier_whole_file_change_is_kept_as_the_owners_note_with_one_tell(self):
        R, W = self.R, self.W
        before = R._prompt("identity", "take", "recognise", REF, goal="G", words="W", facts="F")
        old = W.ddir(REF) / "prompts" / "identity" / "take.md"
        old.parent.mkdir(parents=True)
        old.write_text("How to judge a request: go, ask or stop.\n\n## take\n\nJudge one request from the owner.\n\nPrefer short answers.\n", encoding="utf-8")
        said = "Your earlier change to Identity's take is kept as a note; change the field again in Settings to use it."
        self.assertEqual(self.tells(), [], "a read of nothing says nothing")
        groups = self.groups("identity")
        self.assertEqual(self.tells(), [said], "the first read of the department's instructions says it")
        self.groups("identity")
        self.groups("adaptation")
        self.assertEqual(self.tells(), [said], "and says it once")
        self.assertEqual([g["group"] for g in groups if g["kept"]], ["take"])
        self.assertTrue(groups[2]["kept"]["at"])
        self.assertIn("at", self.stored()["kept"]["identity/take"])
        self.assertEqual(self.stored()["values"], {}, "it is not made into fields")
        # no run reads it: the words sent are the shipped words, and the file is as the owner left it
        self.assertEqual(R._prompt("identity", "take", "recognise", REF, goal="G", words="W", facts="F"), before)
        self.assertTrue(old.read_text(encoding="utf-8").endswith("Prefer short answers.\n"))
        # the owner changes the field again, and that is read
        mine = self.shipped("identity", "take", "recognise", "task") + " Be brief."
        self.stamp(self.change("identity", "take", "recognise", "task", mine).json()["ask"])
        self.assertIn(mine + "\nTHE GOAL: G", R._prompt("identity", "take", "recognise", REF, goal="G", words="W", facts="F"))
        self.assertIn("identity/take", self.stored()["kept"], "the note stays recorded beside the value")
        self.assertEqual(self.tells().count(said), 1)


if __name__ == "__main__":
    unittest.main()
