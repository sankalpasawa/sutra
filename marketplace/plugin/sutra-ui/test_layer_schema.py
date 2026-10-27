"""The interface schema layer itself (PRD amendment A1): its types and validator, its modes, its tables against the code
they are bound to, its rulings, its public functions, and the JSON Schema files generated from it.

A test here that meets a fault on purpose does so inside S.expect_refused(); any other fault fails the test through
the conftest fixture, which is the rule every test of the app now keeps (A1.20).
"""
import copy
import hashlib
import json
import re
from pathlib import Path

import pytest

import layer_schema as S


ENVELOPE = S.obj({"calls": S.integer(0), "usd": S.number(0)}, required=("calls", "usd"))


@pytest.fixture
def envelope(monkeypatch):
    """A definition of the test's own, so the modes are tested apart from the tables."""
    monkeypatch.setitem(S.DEFS, "test.envelope", ENVELOPE)
    monkeypatch.setitem(S.DEFS, "test.flag", S.boolean())
    return "test.envelope"


@pytest.fixture
def home(tmp_path, monkeypatch):
    """A records home of the test's own, as test_j2's fixture makes one, with no model."""
    monkeypatch.setenv("SUTRA_NATIVE_DEPT_HOME", str(tmp_path / "departments"))
    monkeypatch.setenv("SUTRA_NATIVE_HOME", str(tmp_path / "registry"))
    monkeypatch.setenv("SUTRA_UI_PROPOSALS", str(tmp_path / "proposals"))
    monkeypatch.setenv("SUTRA_WEBSITE_OFFLINE", "1")
    monkeypatch.delenv("SUTRA_ENGINE_RUNTIME", raising=False)
    import website_dept as W
    return W


def _f(schema, value):
    return S.faults(schema, value)


# ---- S1: one test per keyword ----------------------------------------------------------------------------------------
def test_s1_type_and_a_bool_is_not_a_whole_number():
    assert _f(S.integer(), 3) == [] and _f(S.integer(), 3.0) == []
    assert _f(S.integer(), True) == ["$: is not a whole number"]
    assert _f(S.number(), True) == ["$: is not a number"] and _f(S.number(), 2.5) == []
    assert _f(S.boolean(), 0) == ["$: is not true or false"]
    assert _f(S.text(10), 5) == ["$: is not a string"]
    assert _f({"type": "null"}, None) == [] and _f(S.items(S.text(3)), "x") == ["$: is not a list"]
    assert _f(S.obj({}), []) == ["$: is not an object"]


def test_s1_enum_and_const():
    assert _f(S.enum("a", "b"), "a") == [] and _f(S.enum("a", "b"), "c") == ["$: is not one of a, b"]
    assert _f(S.enum(1, 2), True) != [], "True is not 1"
    assert _f(S.const("Adaptation"), "Adaptation") == [] and _f(S.const("Adaptation"), "Root") == ["$: is not Adaptation"]
    assert _f(S.const(False), 0) != []


def test_s1_min_length_and_max_length():
    assert _f(S.text(5, 2), "a") == ["$: shorter than 2"]
    assert _f(S.text(5), "abcdef") == ["$: longer than 5"]
    assert _f(S.text(5, 1), "abc") == []


def test_s1_pattern_is_searched():
    assert _f(S.word(S.ITEM_RE, 3), "D2") == [] and _f(S.word(S.ITEM_RE, 3), "D0") == ["$: does not match %s" % S.ITEM_RE]
    assert _f({"type": "string", "pattern": "b"}, "abc") == [], "re.search, not a full match"


def test_s1_minimum_and_maximum():
    assert _f(S.integer(0, 1440), -1) == ["$: below 0"]
    assert _f(S.integer(0, 1440), 1441) == ["$: above 1440"]
    assert _f(S.number(0, 1), 0.5) == []


def test_s1_items_min_items_max_items_and_unique_items():
    sch = S.items(S.text(3), 2, 1, unique=True)
    assert _f(sch, ["a"]) == []
    assert _f(sch, []) == ["$: fewer than 1 items"]
    assert _f(sch, ["a", "b", "c"]) == ["$: more than 2 items"]
    assert _f(sch, ["a", "a"]) == ["$: holds an item twice"]
    assert _f(sch, ["a", "abcd"]) == ["$[1]: longer than 3"]


def test_s1_properties_required_and_additional_properties():
    closed = S.obj({"id": S.text(4, 1), "n": S.integer()}, required=("id",), open=False)
    assert _f(closed, {"id": "a1", "n": 2}) == []
    assert _f(closed, {"n": 2}) == ["$.id: is missing"]
    assert _f(closed, {"id": "a1", "colour": "red"}) == ["$.colour: is not a field here"]
    assert _f(closed, {"id": "a1", "n": "2"}) == ["$.n: is not a whole number"]
    assert _f(S.obj({"id": S.text(4)}), {"id": "x", "colour": "red"}) == [], "open: an unknown key passes"
    typed = S.map_of(S.integer(0, 1440))
    assert _f(typed, {"Plan": 15}) == [] and _f(typed, {"Plan": "15"}) == ["$.Plan: is not a whole number"]


def test_s1_property_names_pattern():
    sch = S.map_of(S.items(S.text(40)), keys=S.ITEM_RE)
    assert _f(sch, {"D1": ["Publish"]}) == []
    assert _f(sch, {"X1": []}) == ["$.X1: the key does not match %s" % S.ITEM_RE]


def test_s1_any_of_and_nullable():
    sch = S.nullable(S.text(3))
    assert _f(sch, None) == [] and _f(sch, "ab") == []
    got = _f(sch, "abcd")
    assert len(got) == 1 and got[0].startswith("$: fits none of its shapes")


def test_s1_ref_into_defs(monkeypatch):
    monkeypatch.setitem(S.DEFS, "name", S.word(S.NAME_RE, 40))
    assert _f(S.ref("name"), "Site plan") == []
    assert _f(S.ref("nowhere"), "x") == ["$: no definition named nowhere"]
    assert _f(S.items(S.ref("name")), ["Plan", "/etc/x"])[0].startswith("$[1]: does not match")


def test_s1_unknown_keywords_are_ignored():
    assert _f({"type": "string", "x-owner": "identity", "format": "email", "description": "x"}, "anything") == []


def test_s1_x_say_refuses_control_characters_but_keeps_newline_and_tab():
    assert _f(S.say(40), "two\nlines\tand a tab") == []
    assert _f(S.say(40), "a bell \x07") == ["$: holds a control character"]


def test_s1_field_refuses_markers_return_only_and_a_newline_when_not_multiline_while_text_takes_them():
    one = S.field(200)
    assert _f(one, "Judge one request from the owner.") == []
    assert any("'{{' or '}}'" in f for f in _f(one, "fill {{goal}} here"))
    assert any("'{{' or '}}'" in f for f in _f(one, "a stray }} brace"))
    assert any("Return ONLY" in f for f in _f(one, "Return ONLY a JSON object: {}"))
    assert _f(one, "two\nlines") == ["$: holds a line break"]
    assert _f(S.field(200, multiline=True), "two\nlines") == []
    assert _f(one, "a tab\tis fine") == [] and _f(one, "a bell \x07") == ["$: holds a control character"]
    assert _f(S.field(200), "") == ["$: shorter than 1"]
    assert _f(S.text(200), 'pasted {"a": {"b": 1}} and a template }}') == [], "text() has no content rule"


# ---- S1: the modes -----------------------------------------------------------------------------------------------------
def test_s1_warn_mode_a_fault_is_a_row_and_a_count_and_nothing_raises(home, envelope, monkeypatch):
    monkeypatch.setattr(S, "MODE", "warn")      # this test is about warn mode: a fault is a row and the write goes through
    W = home
    W.create("t-warn", "Acme", None)
    runs = len(W.runs("t-warn"))
    before = S.REFUSED["count"]
    with S.expect_refused(envelope) as met:
        assert S.check(envelope, {"calls": -1, "usd": 1.0}, ref="t-warn", owner="priority") == {"calls": -1, "usd": 1.0}
        assert S.REFUSED["count"] == before + 1, "REFUSED grows in warn mode"
    assert met == ["$.calls: below 0"]
    rows = W.runs("t-warn")[runs:]
    assert len(rows) == 1 and rows[0]["engine"] == "Priority" and rows[0]["system"]
    assert rows[0]["what"].startswith("kept a record that does not fit the interface: test.envelope: $.calls: below 0")
    assert S.REFUSED["count"] == before, "expect_refused takes what it met off REFUSED"


def test_s1_refuse_mode_raises_after_the_row_and_except_value_error_does_not_catch_it(home, envelope, monkeypatch):
    W = home
    W.create("t-refuse", "Acme", None)
    monkeypatch.setattr(S, "MODE", "refuse")
    runs = len(W.runs("t-refuse"))
    with S.expect_refused() as met:
        with pytest.raises(S.SchemaFault) as got:
            try:
                S.check(envelope, {"calls": 1}, ref="t-refuse", owner="priority")
            except ValueError:                                   # pragma: no cover -- the point: it is not one
                pytest.fail("SchemaFault was caught as a ValueError")
    assert not isinstance(got.value, ValueError)
    assert got.value.name == envelope and got.value.faults == ["$.usd: is missing"]
    assert str(got.value) == "test.envelope: $.usd: is missing"
    assert met == ["$.usd: is missing"]
    rows = W.runs("t-refuse")[runs:]
    assert len(rows) == 1 and rows[0]["what"].startswith("refused a write that does not fit the interface: test.envelope")
    # never-refuse: the owner's Stop lands in refuse mode too, and its fault is a row only
    with S.expect_refused():
        assert S.check("test.flag", "yes", ref="t-refuse", never_refuse=True) == "yes"


def test_s1_refused_never_raises_and_a_ref_with_no_department_writes_no_row(home):
    W = home
    with S.expect_refused() as met:
        S.refused("no-such-dept", "envelope", ["$.calls: below 0"])
        S.refused(None, "envelope", ["$.usd: is missing"])
    assert met == ["$.calls: below 0", "$.usd: is missing"]
    assert not (W.home() / "no-such-dept").exists(), "a fault never makes a department folder"


def test_s1_mode_is_a_code_constant_never_an_environment_variable():
    src = (S.HERE / "layer_schema.py").read_text(encoding="utf-8")
    assert S.MODE == "refuse" and S.OWNERSHIP_MODE == "refuse"      # 'A1 interface: refuse', and the ownership of a key (W3-PROOF X2)
    assert "os.environ" not in src and "getenv" not in src


# ---- S2: every definition takes a sample that fits and refuses one that does not (M2.1's done check) ------------------
# One row per DEFS name: (good, bad), the bad one the good one with one thing wrong, so the fault is the one meant. The
# department's keys are covered through the department record: DEPARTMENT holds every key, DEPARTMENT_BAD one wrong value
# for each. A name added to DEFS (an 'A1 interface:' commit) adds its row here, or test_s2_the_samples_name_every_definition
# fails naming it. The writers' own outputs are test_layer_writers.py's; these are the definitions as A1 types them.
def _but(d, **changes):
    out = json.loads(json.dumps(d))
    out.update(changes)
    return out


NOW = "2026-10-26T10:00:00"
LINE = ["Plan", "Write", "Check", "Publish"]
FIVE = ["Identity", "Adaptation", "Priority", "Coordination", "Audit"]
OPTION = {"id": "leave:D2", "label": "Leave D2 out", "cost": "The site goes live without the booking page."}
DONE_ITEM = {"id": "D1", "text": "The home page says what the clinic does", "how": "by eye", "level": "outcome", "confirm": ""}
RULE = {"id": "r-1", "tag": None, "line": "Never publish on a Sunday", "since": NOW, "from": None, "scope": "standing"}
PINS = dict(S.DEFAULT_PINS)
CHECK_ROW = {"check": "names_an_engine", "passed": True, "why": "it names four engines"}
WF_ENGINE = {"name": "Write", "does": "writes the pages", "reads": "Site plan", "writes": "Pages", "covers": ["D1", "D2"],
             "internet": False, "start": {}, "check": "pages_are_html", "envelope": {"calls": 40, "usd": 0.5}, "made_by": "library",
             "required": False, "fit": "", "level": 1, "confidence": 0.9, "doubt": ""}
REGISTRATION = {"version": 1, "engines": LINE, "source": "library", "registered": NOW, "by": "Root", "checks": [CHECK_ROW],
                "covers": {"D1": ["Write"]}, "fit": {}, "deliverable": "Live site", "left_out": []}
SLOT = {"engine": "Write", "on": "after Site plan v1", "of": "Site plan", "checked": False, "window_min": 30, "since": NOW}
LEFT_OUT = {"engine": "Check", "in_line": False, "since": NOW}
ESTIMATE = {"calls": 12, "usd": 0.3, "basis": "median", "runs": 4,
            "per_engine": {"Write": {"calls": 8, "usd": 0.2, "basis": "median", "runs": 4}}}
CEILING = {"rounds": 6, "calls": 200, "usd": 5.0, "start": {"rounds": 6, "calls": 200, "usd": 5.0}, "raised": [], "at": NOW}
READING_ITEM = {"id": "D2", "subject": "Live site, the booking page", "claim": "a visitor can book a doctor",
                "evidence": "the form posts to /book", "method": "code", "verdict": "met", "severity": "low"}
FINDING = {"id": "F1", "severity": "high", "claim": "the booking form has no button", "where": "Live site, the booking page",
           "item": "D2", "went_to": "Identity", "ask": None, "at": NOW}
QUESTION = {"schema": "board/1", "id": "Q-1", "asked_by": "Write", "to": "Plan", "about": "the booking page",
            "question": "Which doctors take bookings?", "answer": None, "answered_by": None, "status": "open", "reason": None,
            "artifact_update": None, "used_by": [], "cycle": None, "slot": "Plan after Brief v1", "attempt": 1, "run": None}
INSTRUCTIONS = {"schema_version": 1, "values": {"identity": {"take": {"take": {"task": {"value": "Judge it.", "at": NOW, "ask": "a-1"}}}}}}
TT_ROW = {"engine": "Write", "on": "after Site plan v1", "starts": "when Site plan v1 lands", "window_min": 30, "since": NOW,
          "state": "turn", "word": "its turn", "why": None, "at": None, "last": None}
VIEW_COORDINATION = {"line": LINE, "registered": 1, "timetable": [TT_ROW], "left_out": [{"engine": "Check", "since": NOW}],
                     "holds": [], "handoffs": [{"art": "Site plan", "v": 1, "by": "Plan", "says": "the plan", "readers": ["Write"]}],
                     "chain": {"of": None, "used": 0, "limit": 12, "share": 0}, "alarms": [], "ties": [], "questions": []}
VIEW_ENGINE_CARD = {"engine": "Write", "head": {"state": "quiet", "word": None, "why": None, "at": None, "round": None},
                    "motor": {"slot": "after Site plan v1", "starts": "when Site plan v1 lands", "once": False,
                              "says": "waits for Site plan", "window_min": 30, "today": 0},
                    "five": [{"fn": fn, "state": "ok", "says": "nothing to say", "at": None, "share": None} for fn in FIVE]}
VIEW_IDENTITY = {"standard": {"met": False, "missing": ["goal"],
                              "rows": [{"id": "goal", "says": "a goal in your words", "state": "not_met", "note": "no goal yet"}]},
                 "goal": None, "done": None,
                 "done_items": [{"id": "D1", "text": "The home page says what the clinic does", "how": "by eye", "level": "outcome",
                                 "confirm": None}],
                 "rules": [{"tag": None, "line": "Never publish on a Sunday", "by": "yours", "since": NOW}],
                 "open_question": None, "conflicts": []}

SAMPLES = {
    # common (A1.5)
    "name": ("Site plan", "/etc/site plan"),
    "id.item": ("D12", "D0"),
    "id.finding": ("F120", "F0"),
    "impl": ("identity/v1", "identity/v0"),
    "envelope": ({"calls": 40, "usd": 0.5}, {"calls": -1, "usd": 0.5}),
    "option": (OPTION, _but(OPTION, label="")),
    "check.verdict": ({"ok": True, "notes": []}, {"ok": "yes", "notes": []}),
    # Identity's records (A1.6, A1.8)
    "identity.done_item": (DONE_ITEM, _but(DONE_ITEM, colour="red")),
    "identity.rule": (RULE, {"tag": "ask"}),
    "identity.ask": ({"id": "a-1", "kind": "blocked", "status": "pending", "text": "Write cannot run: the plan has no pages.",
                      "created": NOW, "decided": None, "by": None, "engine": "Write", "thread": None, "options": [OPTION],
                      "chosen": None, "items": [DONE_ITEM], "cycle_id": None},
                     {"id": "a-1", "kind": "blocked", "status": "maybe"}),
    # Root's records (A1.6, A1.7)
    "root.pins": (PINS, _but(PINS, identity="identity/v0")),
    "engine.template": ({"id": "engine/translate", "name": "Translate", "version": 1, "use_case": "Translate the pages into Hindi",
                         "description": "translates the pages", "instruction": "Translate every page.", "reads": "Brief",
                         "writes": "Translate", "made_by": {"by": "Adaptation", "dept": "dref-acme0001", "at": NOW, "idea": ""},
                         "start": {"on": [{"kind": "version", "of": "Brief"}], "unless": []}, "steps": [{"id": "translate.read"}],
                         "needs": [], "kind": "work"},
                        {"id": "engine/translate", "name": "Translate", "use_case": "Translate the pages into Hindi",
                         "made_by": {"by": "Root"}}),
    # the workflow schema (A1.14)
    "workflow.engine": (WF_ENGINE, {"name": "Write", "reads": "Site plan"}),
    "workflow": ({"schema_version": 1, "version": 1, "kind": "website", "source": "library", "engines": [WF_ENGINE],
                  "deliverable": "Pages", "covers": {"D1": ["Write"]}, "covers_by": "adaptation", "left_out": [], "checks": [CHECK_ROW],
                  "why": "", "at": NOW, "by": "Root"},
                 {"engines": [WF_ENGINE], "source": "copied"}),
    "workflow.check": (CHECK_ROW, _but(CHECK_ROW, check="looks_nice")),
    "workflow.registration": (REGISTRATION, _but(REGISTRATION, version=0)),
    # Coordination's records (A1.11)
    "coordination.slot": (SLOT, _but(SLOT, window_min=1441)),
    "coordination.left_out": (LEFT_OUT, _but(LEFT_OUT, in_line=True)),
    "coordination.table": ({"schema_version": 1, "order": ["posts", "line", "functions"], "functions": FIVE, "line": LINE,
                            "edges": {}, "left_out": [LEFT_OUT], "grown": [], "registered": 1, "timetable": [SLOT],
                            "by": "Coordination", "since": NOW, "why": "Root registered the plan"},
                           {"order": ["posts", "line", "functions"], "line": LINE, "by": "Root"}),
    # Adaptation's open records (A1.9)
    "adaptation.idea": ({"id": "i-0a1b2c", "words": "a page in Hindi", "reflected": "the site in Hindi too", "question": None,
                         "shapes": ["a second language", "a Hindi page"], "state": "parked", "at": NOW}, "a page in Hindi"),
    "adaptation.ladder": ({"engine": "Write", "step": "write.page", "rung": "C0", "form": None, "since": NOW, "held": False,
                           "pending": None, "trial": None, "history": []}, ["C0"]),
    # the records and acts waves 1 to 3 write first (A1.13b)
    "priority.estimate": (ESTIMATE, _but(ESTIMATE, basis="guess")),
    "priority.price": ({"schema_version": 1, "id": "p-1", "at": NOW, "cycle_id": None, "round": None, "thread": "t-1",
                        "proposal": "line", "engines": LINE, "estimate": ESTIMATE, "room": {"calls": 100, "usd": 2.0},
                        "remaining": {"calls": 88, "usd": 1.7}, "answer": "counter", "keep": ["Plan", "Write", "Publish"],
                        "why": "three engines fit today's room",
                        "indices": {"spend_per_run": {"Write": 0.05}, "checks": {"Write": "ok"}}},
                       {"at": NOW, "proposal": "line", "estimate": ESTIMATE, "room": {"calls": 100, "usd": 2.0}, "answer": "grant",
                        "why": "it fits"}),
    "priority.ceiling": (CEILING, _but(CEILING, rounds=100)),
    "audit.reading_item": (READING_ITEM, _but(READING_ITEM, method="by eye")),
    "audit.finding": (FINDING, _but(FINDING, severity="critical")),
    "audit.reading": ({"schema_version": 1, "id": "r-0a1b2c3d", "v": 2, "artifact": "Live site", "cycle_id": None, "round": 1,
                       "read": True, "why_not_read": None, "items": [READING_ITEM], "findings": [FINDING], "at": NOW},
                      {"id": "reading-1", "v": 2, "artifact": "Live site", "read": True, "items": [], "at": NOW}),
    "adaptation.round": ({"schema_version": 1, "round": 2, "at": NOW, "cycle_id": None, "correction": "add the booking button",
                          "fixes": ["F1"], "covers": ["D2"], "estimate": ESTIMATE, "status": "proposed", "reading": "r-0a1b2c3d",
                          "brief_v": 1},
                         {"round": 2, "correction": "add the booking button", "covers": ["D2"], "status": "applied"}),
    "coordination.question": (QUESTION, _but(QUESTION, schema="board/2")),
    "audit.spot_check": ({"schema_version": 1, "id": "s-1", "at": NOW, "minute": 600,
                          "checks": [{"check": "spot_check_reads_only", "ok": True, "why": "it wrote nothing"}], "findings": [FINDING]},
                         {"id": "s-1", "at": NOW, "minute": 1440, "checks": [], "findings": []}),
    "option.raise": ({"what": "envelope", "engine": "Write", "calls": 20, "usd": 0.5, "rounds": 0},
                     {"what": "budget", "engine": "Write"}),
    "option.words": ({"words": "Make the site in Hindi too"}, {"words": ""}),
    "option.pin": ({"layer": "audit", "impl": "audit/v2"}, {"layer": "audit", "impl": "audit/2"}),
    # the board's acts (A1.13, A1.13b)
    "act.any": ({"word": "alarm"}, {"what": "an alarm"}),
    "act.words": ({"word": "request", "words": 'Make the site; pasted {"a": {"b": 1}} and a template }}', "may_read": ["Brief"]},
                  {"word": "hello", "words": "Make the site"}),
    "act.stamp": ({"word": "engine", "ask": "a-3"}, {"word": "engine", "ask": 3}),
    "act.tell": ({"word": "department", "done": "Done when:\n\tD1 The home page says what the clinic does", "card": "c-1"},
                 {"word": "department", "done": "a bell \x07"}),
    "act.ask": ({"word": "publish", "objective": "Put Live site v2 on the web?", "output": "Live site", "may_read": ["Site plan"],
                 "boundaries": "the site only"},
                {"word": "publish", "may_read": ["x" * 61]}),
    "act.verdict": ({"word": "verdict", "answer": "admit", "why": None}, {"word": "verdict", "answer": "grant"}),
    "act.line_request": ({"word": "line", "words": "Build a website for the clinic", "objective": "a line for the Brief", "faults": [],
                          "practices": {"rules": [], "engines": LINE, "artifacts": [], "required": [], "taken": []}},
                         {"word": "line", "faults": ["x" * 601]}),
    "act.line": ({"word": "line", "engines": ["Plan", WF_ENGINE], "source": "shaped", "words": "Build a website", "for": "a-1",
                  "covers": {"D1": ["Write"]}, "doubt": "", "confidence": 0.8, "fit": {"Write": "short pages"}, "keep": ["Plan"],
                  "why": "two engines cover the Brief"},
                 {"word": "line", "engines": ["Plan"], "confidence": 1.5}),
    "act.conflict": ({"word": "conflict", "engines": ["Plan", "Write"], "source": "library", "words": None,
                      "why": "Priority asked for less", "bound": "hops", "for": None, "options": [OPTION]},
                     {"word": "conflict", "options": [OPTION] * 4}),
    "act.finding": ({"word": "finding", "claim": "the booking form has no button", "severity": "high", "where": "Live site",
                     "page": "book.html", "item": "D2", "v": 2, "findings": [{}]},
                    {"word": "finding", "severity": "critical"}),
    "act.born": ({"word": "born", "engines": LINE, "version": 1, "full": True, "grow": "", "before": None},
                 {"word": "born", "full": "yes"}),
    "act.doubt": ({"word": "doubt", "engine": "Translate", "doubt": "no engine in the Library translates",
                   "fallback": "Write writes both languages", "confidence": 0.4,
                   "cannot": {"engine": "Translate", "items": ["D3"], "why": "no engine can"}},
                  {"word": "doubt", "engine": "Translate"}),
    "act.reading": ({"word": "reading", "reading": "r-0a1b2c3d", "artifact": "Live site", "v": 2, "read": True, "met": ["D1"],
                     "not_met": ["D2"], "to_confirm": [], "findings": ["F1"], "high": True},
                    {"word": "reading", "reading": "r-0a1b2c3d", "artifact": "Live site", "v": 2, "read": True, "met": ["X1"],
                     "not_met": [], "to_confirm": []}),
    "act.next": ({"word": "next", "items": ["D2"], "reading": "r-0a1b2c3d", "findings": ["F1"], "round": 2},
                 {"word": "next", "items": [], "reading": "r-0a1b2c3d"}),
    "act.round": ({"word": "round", "round": 2, "correction": "add the booking button", "fixes": ["F1"], "covers": ["D2"],
                   "estimate": ESTIMATE, "why": "D2 is not met", "ceiling": CEILING},
                  {"word": "round", "round": 100}),
    "act.question": ({"word": "question", "entry": QUESTION}, {"word": "question"}),
    "act.answer": ({"word": "answer", "entry": _but(QUESTION, answer="Dr Rao and Dr Sen", answered_by="Plan", status="answered")},
                   {"word": "answer", "entry": _but(QUESTION, status="pending")}),
    # prompt fields and the owner's values (A1.16)
    "field.task": ("Judge one request from the owner.\nSay what you did.", "Judge {{words}} from the owner."),
    "field.guidance": ("", "Return ONLY yes or no."),
    "field.text": ("Judge one request", "two\nlines"),
    "field.note": ("", "x" * 4001),
    "field.items": (["judge a request against the goal"], []),
    "instructions": (INSTRUCTIONS, {"schema_version": 1, "values": {"identity": {"take": {"take": {"task": {"at": NOW}}}}}}),
    # settings (A1.8 to A1.12)
    "setting.windows": ({"Plan": 15, "Write": 30}, {"Plan": 1441}),
    "setting.make": (False, "false"),
    "setting.order": (["posts", "line", "functions"], ["posts", "posts"]),
    "setting.spot_every_s": (86400, 60),
    # the pane views (A1.17)
    "view.identity": (VIEW_IDENTITY, _but(VIEW_IDENTITY, rules=[{"tag": "ask", "line": "Ask before publishing", "by": "Root"}])),
    "view.adaptation": ({"proposal": {"workflow": ["Plan", "Write"], "source": "shaped", "at": NOW},
                         "root_checks": [{"summary": "met every standard", "at": NOW, "passed": True}], "rounds": []},
                        {"proposal": None, "root_checks": [{"passed": "yes"}], "rounds": []}),
    # one round of the current cycle (W2-ADAPT, M9.6): rounds.jsonl folded by round number, the latest status winning
    "view.adaptation.round": ({"round": 2, "correction": "Put right D2: every page names the phone line", "covers": ["D2"], "fixes": ["F1"],
                               "status": "granted", "said": "Priority said yes", "estimate": {"calls": 9, "usd": 0.36}, "at": NOW, "reading": "r-0123abcd",
                               "brief_v": None},
                              {"round": 2, "correction": "Put right D2", "covers": ["D2"], "status": "done"}),
    "view.priority": ({"bargains": [{"said": "asked for less", "summary": "kept three engines of four", "at": NOW}],
                       "envelopes": [{"engine": "Write", "calls": 3, "usd": 0.1, "calls_limit": 40, "usd_limit": 0.5, "share": 0.2}]},
                      {"bargains": [{"said": "COUNTER", "summary": None, "at": None}], "envelopes": []}),
    "view.coordination": (VIEW_COORDINATION, _but(VIEW_COORDINATION, timetable=[_but(TT_ROW, state="late")])),
    "view.engine_card": (VIEW_ENGINE_CARD, _but(VIEW_ENGINE_CARD, five=VIEW_ENGINE_CARD["five"][:4])),
    "view.audit": ({"readings": [{"summary": "read Live site v2", "at": NOW}], "findings": [{"text": "F1: no button", "at": NOW}],
                    "spot_checks": []},
                   {"readings": [], "findings": []}),
}

#: a department record holding every key A1.6 names, and one value per key that the key's definition refuses
DEPARTMENT = {
    "schema_version": 1, "kind": "website", "ref": "dref-acme0001", "name": "Acme clinic site", "parent": "dref-root0001",
    "created": NOW, "runtime": 2, "control": "granted", "stopped": False, "engines": LINE,
    "artifacts": ["Brief", "Site plan", "Pages", "Check report", "Live site"], "workflows": [REGISTRATION], "layers": PINS,
    "org": {"name": "Acme"}, "root": "dref-root0001", "template_ref": {"id": "setup", "version": 1},
    "templates": {"Plan": "engine/plan"}, "founding": {"operation_id": "op-1", "checkpoints": ["made", "told"]},
    "events": [{"kind": "born", "at": NOW}], "pending_final_tell": {"text": "Your department is ready."},
    "goal": "A website for City Care clinic", "done": "Done when the site is live", "done_items": [DONE_ITEM],
    "to_be_confirmed": [{"item": "D1", "why": "a person reads it"}], "rules": [RULE], "owner": "Sankalp",
    "windows": {"Plan": 15, "Write": 30, "Check": 15, "Publish": 15}, "identity_revision": 1, "initial_goal_context": {},
    "publish_asks_from": 0, "goals": [{"goal": "A website for City Care clinic", "at": NOW}],
    "looked_up": ["City Care clinic: three doctors"], "host": "citycare.example", "ladders": {"Write": {"calls": 3}},
    "ladder": {"Write": 2}, "bounds": {"hops": 4, "seconds": 900, "usd": 0.5}, "envelopes": {"Write": {"calls": 40, "usd": 0.5}},
    "ceiling": CEILING,
}
DEPARTMENT_BAD = {
    "schema_version": -1, "kind": 5, "ref": "", "name": "", "parent": 3, "created": "yesterday", "runtime": 3, "control": "x" * 41,
    "stopped": "no", "engines": ["Plan", "Plan"], "artifacts": ["/etc/passwd"], "workflows": [{"version": 1}],
    "layers": _but(PINS, identity="identity/v0"), "org": [], "root": 5, "template_ref": 5, "templates": {"Plan": 5},
    "founding": {"operation_id": 5}, "events": [{"kind": 5}], "pending_final_tell": "Your department is ready.",
    "goal": "x" * 2001, "done": "x" * 4001, "done_items": [_but(DONE_ITEM, id="D0")], "to_be_confirmed": [{"why": "a person reads it"}],
    "rules": [{"tag": "ask"}], "owner": 5, "windows": {"Plan": -1}, "identity_revision": 0, "initial_goal_context": [],
    "publish_asks_from": -1, "goals": ["A website"], "looked_up": [5], "host": 5, "ladders": {"Write": 2},
    "ladder": {"Write": "2"}, "bounds": {"hops": -1}, "envelopes": {"Write": {"calls": 40}}, "ceiling": {"rounds": 6},
}
SAMPLES["department"] = (DEPARTMENT, _but(DEPARTMENT, colour="red"))
# the A3 definitions' samples (PRD amendment A3: the templates at every level) live beside their fixtures, a (good, bad) pair each
SAMPLES.update({k: tuple(v) for k, v in json.loads((S.HERE / "test_fixtures" / "templates" / "samples.json").read_text(encoding="utf-8")).items()})


def test_s2_the_samples_name_every_definition():
    assert set(DEPARTMENT) == set(DEPARTMENT_BAD) == set(S.DEPARTMENT_KEYS), "every department key, and only those"
    named = set(SAMPLES) | {"department." + k for k in DEPARTMENT}
    missing, extra = sorted(set(S.DEFS) - named), sorted(named - set(S.DEFS))
    assert not missing, "DEFS names with no sample: add a (good, bad) row to SAMPLES: %s" % missing
    assert not extra, "samples of no definition: %s" % extra


@pytest.mark.parametrize("name", sorted(SAMPLES))
def test_s2_every_definition_takes_its_sample_and_refuses_the_bad_one(name):
    good, bad = SAMPLES[name]
    assert S.validate(name, good) == []
    assert S.validate(name, bad) != [], "%s takes %r" % (name, bad)


@pytest.mark.parametrize("key", sorted(DEPARTMENT))
def test_s2_every_department_key_takes_its_sample_and_refuses_the_bad_one_through_the_record(key):
    name = "department." + key
    assert S.validate(name, DEPARTMENT[key]) == []
    assert S.validate(name, DEPARTMENT_BAD[key]) != [], "%s takes %r" % (name, DEPARTMENT_BAD[key])
    got = S.validate("department", _but(DEPARTMENT, **{key: DEPARTMENT_BAD[key]}))
    assert got and all(re.match(r"^\$\.%s(?=[.:\[])" % re.escape(key), f) for f in got), got


# ---- S3: the tables, against the code they are bound to -------------------------------------------------------------
import ast  # noqa: E402

import engine_runtime as R  # noqa: E402
import functions_view as FV  # noqa: E402
import j2_runtime as J  # noqa: E402
import website_dept as W  # noqa: E402


def _steps(e):
    return list(e.get("gates") or []) + list(e.get("rules") or []) + list(e.get("steps") or []) + \
        [s for h in e.get("on") or [] for s in h.get("steps") or []]


def _function_engines():
    return {name: R.defs()["engines"][name] for name in S.ENGINE_LAYER if name in R.defs()["engines"]}


def test_s3_edges_are_engine_defs_edges_in_their_order():
    assert S.edges() == R.defs()["edges"]


def test_s3_every_handler_of_the_five_is_a_hears_row_and_every_row_has_its_handler():
    for name, e in _function_engines().items():
        if name == "Setup":
            continue
        layer = S.ENGINE_LAYER[name]
        rows = {(r["act"], r["word"]): r for r in S.hears(layer)}
        handlers = {(h["when"]["msg_type"], h["when"].get("word", S.ANY)): h["name"] for h in e.get("on") or []}
        assert set(handlers) == set(rows), "%s: %s" % (name, set(handlers) ^ set(rows))
        for pair, handler in handlers.items():
            assert rows[pair]["handler"] == handler
            assert rows[pair]["payload"] in S.DEFS and rows[pair]["via"] in ("board", "call")
            assert set(rows[pair]["from"]) <= set(S.ACTORS)


# the sites: every post() and _tell() call of engine_runtime and j2_runtime, with what it sends
def _consts(node, fn):
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return {node.value}
    if isinstance(node, ast.IfExp):
        a, b = _consts(node.body, fn), _consts(node.orelse, fn)
        return a | b if a is not None and b is not None else None
    if (isinstance(node, ast.Name) and node.id == "OWNER") or (isinstance(node, ast.Attribute) and node.attr == "OWNER"):
        return {"Owner"}
    if isinstance(node, ast.Name) and fn is not None:
        vals = [n.value for n in ast.walk(fn) if isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id == node.id for t in n.targets)]
        got = set()
        for v in vals:
            c = _consts(v, None)
            if c is None:
                return None
            got |= c
        return got or None
    return None


def _payload(node, fn):
    if isinstance(node, ast.Dict):
        return node
    if isinstance(node, ast.Call) and getattr(node.func, "id", None) == "dict" and node.args and isinstance(node.args[0], ast.Dict):
        return node.args[0]
    if isinstance(node, ast.Name) and fn is not None:
        vals = [n.value for n in ast.walk(fn) if isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id == node.id for t in n.targets)]
        if len(vals) == 1:
            return _payload(vals[0], None)
    return None


def _word(node, fn):
    d = _payload(node, fn) if node is not None else None
    if d is None:
        return S.ANY
    for k, v in zip(d.keys, d.values):
        if isinstance(k, ast.Constant) and k.value == "word":
            got = _consts(v, fn)
            return got if got is not None else S.ANY
    return S.ANY


def _post_sites(module):
    tree = ast.parse((S.HERE / (module + ".py")).read_text(encoding="utf-8"))
    out = []
    for fn in [n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)]:
        for node in ast.walk(fn):
            if not isinstance(node, ast.Call):
                continue
            f = node.func
            name = f.id if isinstance(f, ast.Name) else (f.attr if isinstance(f, ast.Attribute) and getattr(f.value, "id", None) == "R" else None)
            if name not in ("post", "_tell") or (name == "post" and fn.name == "_tell") or len(node.args) < 4:
                continue                      # _tell's own post is the wrapper: its callers are the sites
            a = node.args
            if name == "post":
                src, act, pl = _consts(a[1], fn), _consts(a[3], fn), a[4] if len(a) > 4 else None
            else:
                src, act, pl = {"Identity"}, _consts(a[3], fn), a[4] if len(a) > 4 else None
            out.append({"where": "%s:%d %s" % (module, node.lineno, fn.name), "src": src, "act": act, "word": _word(pl, fn)})
    return out


def test_s3_every_post_site_is_a_sends_row():
    sites = _post_sites("engine_runtime") + _post_sites("j2_runtime")
    assert len(sites) > 60, "the scan finds the sites"
    for site in sites:
        assert site["act"], "%s: its act is a literal" % site["where"]
        for src in site["src"] or ():         # a sender named by a variable is read below
            for act in site["act"]:
                rows = [r for r in S.SENDS[src] if r["act"] == act]
                assert rows, "%s: %s sends no %s" % (site["where"], src, act)
                if site["word"] == S.ANY:
                    assert any(r["words"] == S.ANY for r in rows), "%s: a word that is not a literal needs an (any) row" % site["where"]
                else:
                    for w in site["word"]:
                        assert any(r["words"] == S.ANY or w in r["words"] for r in rows), \
                            "%s: %s %s %r is not in SENDS" % (site["where"], src, act, w)
    named = [s for s in sites if s["src"] is None]
    assert named, "the scan reads the sites whose sender is a variable (_line_conflict's)"
    for site in named:                        # each act word a variable sender posts is some actor's row
        for act in site["act"]:
            for w in ([] if site["word"] == S.ANY else site["word"]):
                assert any(r["act"] == act and (r["words"] == S.ANY or w in r["words"]) for a in S.SENDS for r in S.SENDS[a]), site


def test_s3_every_sends_row_names_known_acts_actors_and_payloads():
    assert set(S.SENDS) == set(S.ACTORS)
    for actor, rows in S.SENDS.items():
        for r in rows:
            assert r["act"] in S.ACTS and set(r["to"]) <= set(S.ACTORS) and r["payload"] in S.DEFS
            assert r["words"] == S.ANY or (isinstance(r["words"], tuple) and r["words"])


_COORDINATIONS_OWN = ("coord.edge", "coord.bounds", "coord.alarm", "coord.verdict")


def test_s3_every_cross_layer_ask_rule_is_a_calls_row():
    tree = ast.parse((S.HERE / "engine_runtime.py").read_text(encoding="utf-8"))
    found = []
    for fn in [n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)]:
        for node in ast.walk(fn):
            if isinstance(node, ast.Call) and getattr(node.func, "id", None) == "_ask_rule" and len(node.args) >= 2 \
                    and isinstance(node.args[1], ast.Constant):
                found.append((fn.name, node.args[1].value))
    assert found
    calls = {(c["site"], c["what"]): c for c in S.calls()}
    for site, sid in found:
        owner = R.step_def(sid)[0]
        if sid in _COORDINATIONS_OWN:
            assert owner == "Coordination", "Coordination's own rule calls stay inside its layer"
            continue
        assert (site, sid) in calls, "%s asks %s's %s in place, and CALLS does not say so" % (site, owner, sid)
        assert calls[(site, sid)]["to"] == owner
    assert all(c["from"] in S.TITLE.values() and c["to"] in S.TITLE.values() for c in S.calls())


def test_s3_every_soft_steps_out_keys_are_named_in_its_parts_returns():
    readers = {}
    for layer, groups in S.PROMPTS.items():
        for group, parts in groups.items():
            for part, p in parts.items():
                rb = p["read_by"]
                for sid in (rb if isinstance(rb, tuple) else (rb,) if rb else ()):
                    readers.setdefault(sid, []).append(p)
    soft = [s for e in _function_engines().values() for s in _steps(e) if s.get("prompt")]
    assert len(soft) >= 14
    for s in soft:
        assert s["id"] in readers, "%s reads no part" % s["id"]
        for p in readers[s["id"]]:
            for key in s.get("out") or {}:
                assert '"%s"' % key in p["returns"], "%s: %s is not in its part's returns" % (s["id"], key)


def test_s3_prompts_are_the_retired_files_parts_and_the_returns_byte_for_byte():
    """The interface's prompts are the parts of the .md files the words came from (their text is kept in
    test_fixtures/retired-prompt-parts.json since the files were retired, W3-PROOF X1), with each part's returns, inputs and
    fields; a part a later step added (S.ADDED_PARTS) is in none of them."""
    retired = __import__("test_function_prompts").RETIRED
    for fn, files in R.INSTRUCTIONS.items():
        assert list(S.PROMPTS[fn]) == list(files) and list(S.GROUPS[fn]) == list(files) == list(retired["leads"][fn])
        for file, parts in files.items():
            assert S.GROUPS[fn][file] == retired["leads"][fn][file]
            got = retired["parts"][fn].get(file, {})
            if not [p for p in parts if (fn, file, p) not in S.ADDED_PARTS]:
                assert [p for p in S.PROMPTS[fn][file] if (fn, file, p) not in S.ADDED_PARTS] == ["note"], \
                    "a file no step reads is its note (A1.16 rule 7)"
                continue
            # a part a later step added to the interface (A1.16, 'Parts added by later steps') is in no file of the retired bundle
            assert [p for p in S.PROMPTS[fn][file] if (fn, file, p) not in S.ADDED_PARTS] == [p for p in parts if (fn, file, p) not in S.ADDED_PARTS]
            for part, slots in parts.items():
                if (fn, file, part) in S.ADDED_PARTS:
                    assert part not in got
                    continue
                p = S.PROMPTS[fn][file][part]
                assert p["inputs"] == tuple(slots)
                assert p["returns"] is None or p["returns"] in got[part], "%s.%s.%s: returns byte for byte" % (fn, file, part)
                assert p["returns"] is not None or "Return ONLY" not in got[part]
                assert all(d in S.DEFS and d.startswith("field.") for d in p["fields"].values())


def test_s3_roots_returns_are_its_inline_builders_byte_for_byte():
    got = {"setup.read": {"words": "w", "conversation": {"messages": []}, "named": None,
                          "facts": {"kinds": "website", "use_cases": "website: a site", "existing": "none"}}}
    ctx = {"bag": got, "dept": {"name": "Acme Root", "org": {"name": "Acme"}}, "ref": None}
    assert S.PROMPTS["root"]["setup"]["converse"]["returns"] in R.p_setup_converse(ctx, None, None)
    assert S.PROMPTS["root"]["setup"]["shape"]["returns"] in R.p_setup_shape(ctx, None, None)


def test_s3_roots_converse_part_has_one_owner_field_and_the_examples_are_an_input():
    """A1-15 (A1-D20): the examples are the Library's Setup template's questions, joined on one line by the code, so they are
    an input; an 'items' field would print as lines and could not be the same words. The settled shape stands in the
    interface, the generated files and the field check."""
    converse = S.PROMPTS["root"]["setup"]["converse"]
    assert converse["fields"] == {"task": "field.task"} and converse["inputs"] == ("examples", "library", "existing", "conversation")
    assert S.PROMPTS["root"]["setup"]["shape"]["fields"] == {}
    assert S.validate_field("root", "setup", "converse", "task", "Ask what you need to know.") == []
    assert S.validate_field("root", "setup", "converse", "items", ["x"]) != [], "the examples are not the owner's to change"
    interface = json.loads((S.HERE / "schemas" / "layers" / "interface.v1.json").read_text(encoding="utf-8"))
    assert interface["prompts"]["root"]["setup"]["converse"]["fields"] == {"task": "field.task"}
    instructions = json.loads((S.HERE / "schemas" / "layers" / "instructions.schema.json").read_text(encoding="utf-8"))
    assert instructions["x-fields"]["root"]["setup"]["converse"] == {"task": "field.task"}
    ctx = {"bag": {"setup.read": {"words": "w", "conversation": {"messages": []}, "named": None,
                                  "facts": {"kinds": "website", "use_cases": "website: a site", "existing": "none"}}},
           "dept": {"name": "Acme Root", "org": {"name": "Acme"}}, "ref": None}
    questions = R._converse_examples()
    assert questions and " | ".join(questions) in R.p_setup_converse(ctx, None, None), "the examples reach the words as the one input"


def _added_checks(layer):
    """The covering checks a layer's default version holds in its own CHECK dict (A1.10: 'added', beyond the ones its recipe's
    steps name, which still serve from the legacy registry): the body is the layer's, not engine_runtime's."""
    return set(importlib.import_module("layers.%s.v1" % layer).CHECK) if layer != "root" else set()


def _body_of(check):
    if check in R.CHECK:
        return R.CHECK[check]
    return next(importlib.import_module("layers.%s.v1" % layer).CHECK[check] for layer in S.FUNCTION_LAYERS
                if check in importlib.import_module("layers.%s.v1" % layer).CHECK)


def test_s3_checks_are_every_check_a_function_step_names():
    for name, e in _function_engines().items():
        layer = S.ENGINE_LAYER[name]
        named = {s["check"] for s in _steps(e)}
        if name == "Setup":
            named |= {s["check"] for s in _steps(R.engine_def("Setup"))}
        assert named <= set(S.CHECKS[layer]) | set(S.SHARED_CHECKS), "%s: %s" % (name, named - set(S.CHECKS[layer]) - set(S.SHARED_CHECKS))
        assert set(S.CHECKS[layer]) <= named | _added_checks(layer), "%s: %s" % (name, set(S.CHECKS[layer]) - named)
    assert all(c in R.CHECK or c in _added_checks(layer) for layer in S.CHECKS for c in S.CHECKS[layer])
    assert all(c in R.CHECK for c in S.SHARED_CHECKS)


def test_s3_contract_samples_hold_against_the_bodies_on_main():
    for check, samples in S.CONTRACT_SAMPLES.items():
        for out in samples["good"]:
            assert _body_of(check)(None, None, None, out)["ok"] is True, (check, out)
        for out in samples["bad"]:
            assert _body_of(check)(None, None, None, out)["ok"] is False, (check, out)


def test_s3_outputs_are_the_step_outputs_read_outside_the_layer():
    src = (S.HERE / "functions_view.py").read_text(encoding="utf-8") + (S.HERE / "j2_runtime.py").read_text(encoding="utf-8")
    ids = {s["id"] for e in R.defs()["engines"].values() for s in _steps(e)}
    read = {i for i in ids if '"%s"' % i in src or "'%s'" % i in src}
    assert read == set(S.OUTPUTS)


def test_s3_layers_carry_the_function_pages_verbatim():
    """The pages are the interface's (A1 C8: functions_view.PAGES moved here and was deleted), word for word as the pane
    printed them (test_fixtures/function-pages.snapshot.json, taken from functions_view.PAGES before it went); each
    function's journeys, which the interface does not hold, stay with the view that reads them from the record."""
    snap = json.loads((S.HERE / "test_fixtures" / "function-pages.snapshot.json").read_text(encoding="utf-8"))
    assert not hasattr(FV, "PAGES") and set(FV.JOURNEYS) == set(snap) == {S.TITLE[layer] for layer in S.FUNCTION_LAYERS}
    for layer in S.FUNCTION_LAYERS:
        for k in ("vsm", "line", "holds", "hands_to", "keeps", "v1"):
            assert S.LAYERS[layer][k] == snap[S.TITLE[layer]][k], (layer, k)
    assert set(S.LAYERS) == set(S.LAYER_NAMES) and S.LAYERS["identity"]["view"] == "view.identity"


def test_s3_settings_defaults_are_the_codes():
    assert S.SETTINGS["priority"]["envelope"]["default"] == R.engine_def("Priority")["template"]["envelope"]
    assert S.SETTINGS["coordination"]["order"]["default"] == R.defs()["coordination"]["order"]
    assert all(s["def"] in S.DEFS for layer in S.SETTINGS for s in S.SETTINGS[layer].values())


def test_s3_the_constants_and_field_tuples_equal_the_codes():
    assert S.BOUNDS == R.BOUNDS and S.CHAIN_LIMIT == W.CHAIN_LIMIT and S.REPAIRS == J.REPAIRS
    assert S.OPTIONS_MAX == W.OPTIONS_MAX and S.DONE_ITEMS_MAX == W.DONE_ITEMS_MAX and S.STANDARD == R.STANDARD
    assert S.ACTS == R.ACTS and S.RULE_TAGS == W.RULE_TAGS and (S.DONE_HOW, S.DONE_LEVELS) == (W.DONE_HOW, W.DONE_LEVELS)
    assert S.TABLE_FIELDS == R.TABLE_FIELDS and S.SLOT_FIELDS == R.SLOT_FIELDS and S.LEFT_OUT_FIELDS == R.LEFT_OUT_FIELDS
    assert S.COORDINATION_FIELDS == FV.COORDINATION_FIELDS and S.TIMETABLE_ROW == FV.TIMETABLE_ROW
    assert S.ENGINE_CARD_FIELDS == FV.ENGINE_CARD_FIELDS and S.ENGINE_FIVE_ROW == FV.ENGINE_FIVE_ROW
    assert S.BORN_FIELDS == R.BORN_FIELDS and S.SLOT_STATES == tuple(FV.TT_WORDS)
    assert set(S.DEFS["coordination.table"]["properties"]) == set(S.TABLE_FIELDS) | {"schema_version"}
    assert tuple(S.DEFS["coordination.slot"]["properties"]) == S.SLOT_FIELDS
    assert tuple(S.DEFS["coordination.left_out"]["properties"]) == S.LEFT_OUT_FIELDS
    assert tuple(S.DEFS["view.coordination"]["properties"]) == S.COORDINATION_FIELDS
    assert tuple(S.DEFS["view.coordination"]["properties"]["timetable"]["items"]["properties"]) == S.TIMETABLE_ROW
    assert tuple(S.DEFS["view.engine_card"]["properties"]) == S.ENGINE_CARD_FIELDS
    assert tuple(S.DEFS["view.engine_card"]["properties"]["five"]["items"]["properties"]) == S.ENGINE_FIVE_ROW
    assert tuple(S.DEFS["act.born"]["properties"])[1:] == S.BORN_FIELDS
    assert S.VERDICTS["identity"]["journey"] == R.JOURNEYS
    assert set(S.ASK_KINDS) >= {"blocked", "j2_identity", "done_items", "instructions", "engine", "line"}


# ---- S3: the rulings, kept as interface tests (A1.25) ----------------------------------------------------------------
def test_s3_ruling_only_identity_speaks_to_the_owner():
    for actor, rows in S.SENDS.items():
        if any("Owner" in r["to"] for r in rows):
            assert actor == "Identity", actor


def test_s3_ruling_priority_prices_and_holds_and_never_orders():
    assert {d for r in S.SENDS["Priority"] for d in r["to"]} == {"Adaptation"}
    assert not any("order" in w for r in S.SENDS["Priority"] if r["words"] != S.ANY for w in r["words"])
    for p in (S.HERE / "function-templates" / "priority").glob("*.json"):
        low = p.read_text(encoding="utf-8").lower()
        assert "what runs next" not in low and " order" not in low.replace("in order", ""), p.name


def test_s3_ruling_root_makes_the_department_and_never_an_engine():
    assert not any(r["act"] == "propose" for r in S.SENDS["Root"])
    assert S.DEFS["engine.template"]["properties"]["made_by"]["properties"]["by"] == {"const": "Adaptation"}


def test_s3_ruling_adaptation_proposes_and_never_applies():
    assert not [k for k, (owner, _) in S.DEPARTMENT_KEYS.items() if owner == "adaptation"]
    assert {r["act"] for r in S.SENDS["Adaptation"]} == {"propose", "inform"}


def test_s3_ruling_the_checker_is_never_the_writer():
    assert not [k for k, (owner, _) in S.DEPARTMENT_KEYS.items() if owner == "audit"]
    assert not R.engine_def("Audit").get("writes"), "Audit owns no artifact"
    assert "function's" in dict((s[0], s[1]) for s in S.WORKFLOW_STANDARDS)["names_unique"]


def test_s3_ruling_threads_are_bounded_and_no_engine_is_mandatory_unless_its_kind_says_so():
    assert S.BOUNDS == R.BOUNDS and S.CHAIN_LIMIT == W.CHAIN_LIMIT and S.REPAIRS == J.REPAIRS
    assert "required_kept" in [s[0] for s in S.WORKFLOW_STANDARDS]
    for kind, k in R.defs()["kinds"].items():
        assert R.required_engines({"kind": kind}) == list(k.get("required") or [])


def test_s3_the_tables_name_only_known_definitions_and_layers():
    for layer, kinds in S.RECORDS.items():
        assert layer in S.LAYER_NAMES and all(k["def"] in S.DEFS for k in kinds.values())
    assert all(name in S.DEFS for name in S.VIEWS.values()) and all(name in S.DEFS for name in S.SINK.values())
    assert all(name in S.DEFS for name in S.SINK_JOURNALS.values())
    assert all(o["params"] is None or o["params"] in S.DEFS for o in S.OPTION_KINDS.values())
    assert all(o["layer"] in S.LAYER_NAMES for o in S.OPTION_KINDS.values())
    assert all(set(st) <= set(S.STAGES) and set(src) <= set(S.SOURCES) for _, _, src, st in S.WORKFLOW_STANDARDS)
    assert S.owner_of_key("goal") == "identity" and S.owner_of_key("envelopes") == "priority" and S.owner_of_key("colour") is None


# ---- S4: the public functions ----------------------------------------------------------------------------------------
FIXTURES = S.HERE / "schemas" / "layers" / "fixtures"


def test_s4_migrate_reads_a_v0_department_as_v1_and_never_writes():
    v0 = json.loads((FIXTURES / "department.v0.json").read_text(encoding="utf-8"))
    v1 = json.loads((FIXTURES / "department.v1.json").read_text(encoding="utf-8"))
    kept = json.dumps(v0, sort_keys=True)
    assert S.migrate("department", v0) == v1
    assert json.dumps(v0, sort_keys=True) == kept, "a read returns a copy and changes nothing"
    assert v1["schema_version"] == 1 and v1["layers"] == S.DEFAULT_PINS
    assert v1["done_items"] == [{"id": "D1", "text": v0["done"], "how": "code", "level": "outcome"}]
    assert v1["an_older_key"] == "kept on read", "unknown keys are kept on read"
    assert S.validate("department", {k: v for k, v in v1.items() if k != "an_older_key"}) == []
    assert S.migrate("department", v1) == v1, "a v1 record reads as it is"


def test_s4_migrate_maps_an_older_tables_writer_to_coordination_keeping_its_why():
    t = {"order": ["posts", "line", "functions"], "line": ["Plan"], "by": "Root", "why": "the plan Root registered"}
    got = S.migrate("coordination.table", t)
    assert (got["by"], got["why"], got["schema_version"]) == ("Coordination", "the plan Root registered", 1)
    assert S.migrate("coordination.table", dict(t, by="born"))["by"] == "born"
    assert S.validate("coordination.table", got) == []


def test_s4_as_workflow_gives_the_deliverable_and_default_covers():
    d = {"kind": "website", "done_items": [{"id": "D1", "text": "Every page checked and live", "how": "code", "level": "outcome"},
                                           {"id": "D2", "text": "Pages read well", "how": "model", "level": "target"}]}
    wf = S.as_workflow(["Plan", "Write", "Check", "Publish"], "library", d)
    assert wf["deliverable"] == "Live site" and wf["covers_by"] == "default"
    assert wf["covers"] == {"D1": ["Publish"], "D2": ["Publish"]}
    assert [e["reads"] for e in wf["engines"]] == ["Brief", "Site plan", "Pages", "Build"]
    assert S.validate("workflow", wf) == []
    shaped = S.as_workflow([{"name": "Facts", "does": "finds the facts", "reads": "Brief", "writes": "Facts", "internet": True, "covers": ["D1"]},
                            {"name": "Inventory", "reads": "Facts", "writes": "Inventory", "covers": ["D1", "D2"]}], "shaped", d)
    assert shaped["covers"] == {"D1": ["Facts", "Inventory"], "D2": ["Inventory"]} and shaped["covers_by"] == "adaptation"
    assert shaped["deliverable"] == "Inventory" and S.validate("workflow", shaped) == []


def test_s4_validate_workflow_returns_the_shape_rows_until_roots_standards_are_code():
    wf = S.as_workflow(["Plan", "Write", "Check", "Publish"], "library", {"kind": "website"})
    rows = S.validate_workflow(wf, "registration")
    assert rows[0] == {"check": "workflow_meets_standards", "passed": True, "why": "the workflow fits the workflow schema"}
    assert S.workflow_faults(wf) == []
    bad = S.validate_workflow({"engines": [{"name": "Bad/Name"}], "source": "shaped"})
    assert bad[0]["passed"] is False and S.workflow_faults({"engines": "x"})[0].startswith("workflow_meets_standards: ")
    for r in rows:
        assert S.validate("workflow.check", r) == []


def test_s4_first_input_and_deliverable():
    assert S.first_input("root") == "Request" and S.first_input("website") == "Brief" and S.first_input("organic") == "Brief"
    assert S.deliverable({"kind": "website"}) == "Live site" and S.deliverable({"kind": "default"}) == "Result"
    assert S.deliverable({"kind": "organic"}) is None
    assert S.deliverable({"kind": "website", "workflows": [{"version": 1, "engines": ["Plan", "Write"], "source": "library"}]}) == "Pages"


def test_s4_validate_act_holds_the_edges_the_words_and_the_payload():
    assert S.validate_act("Priority", "Owner", "inform", {"word": "said"}) != [], "only Identity speaks to the owner"
    assert S.validate_act("Owner", "Identity", "request", {"word": "request", "words": 'my {"a": 1} }}'}) == []
    assert S.validate_act("Adaptation", ["Priority"], "propose", {"word": "trial", "step": "write.page"}) == []
    assert S.validate_act("Adaptation", "Priority", "propose", {"word": "grant"})[0].startswith("$.word: Adaptation does not propose")
    assert S.validate_act("Priority", "Adaptation", "propose", {"word": "order the line"}) == ["$.word: Priority prices and holds; it never orders"]
    assert S.validate_act("Audit", "Identity", "inform", {"word": "finding", "severity": "dire"}) == ["$.severity: is not one of high, medium, low"]
    assert S.validate_act("Plan", "Identity", "inform", {"word": "x"}) == ["$: Engine sends no inform"]
    assert S.validate_act("Identity", "Owner", "inform", {"word": "said", "done": "Line 1."}) == [], "an (any) row takes a stored tell"
    assert S.validate_act("Identity", ["Coordination"], "inform", {"word": "born"}) == []
    assert S.validate_act("Identity", "Coordination", "agree", {"word": "verdict", "answer": "maybe"}) == ["$.answer: is not one of admit, wait, refuse"]


def test_s4_check_act_is_a_row_in_warn_mode_and_a_refusal_in_refuse_mode(monkeypatch):
    monkeypatch.setattr(S, "MODE", "warn")      # this test is about warn mode: a fault is a row and the write goes through
    with S.expect_refused("act") as met:
        assert S.check_act("Priority", "Owner", "inform", {"word": "said"}) == {"word": "said"}
    assert met == ["Priority inform to Owner: $: Priority sends no inform"]
    monkeypatch.setattr(S, "MODE", "refuse")
    with S.expect_refused("act"):
        with pytest.raises(S.SchemaFault):
            S.check_act("Priority", "Owner", "inform", {"word": "said"})


def test_s4_check_department_checks_only_the_changed_keys_and_stamps_the_version(monkeypatch):
    monkeypatch.setattr(S, "MODE", "warn")      # this test is about warn mode: a fault is a row and the write goes through
    before = {"kind": "website", "ref": "r", "name": "Acme", "colour": "an old key", "windows": {"Plan": "fifteen"}}
    d = dict(before, goal="A live site")
    assert S.check_department(dict(d), before=before)["schema_version"] == 1, "a legacy fault never blocks a later save"
    with S.expect_refused("department") as met:
        S.check_department(dict(d, colour="red"), before=before)
    assert met == ["$.colour: is not a field here"]
    with S.expect_refused("department") as met:
        S.check_department(dict(d, done_items=[{"id": "D2", "text": "x"}], to_be_confirmed=[{"item": "D9"}]), before=before)
    assert met == ["$.done_items: the ids do not run D1 to D1 in order", "$.to_be_confirmed: D9 names no done-when item"]
    with S.expect_refused("department") as met:
        S.check_department(dict(d, kind="spaceship"), before=before)
    assert met == ["$.kind: spaceship is no kind in the definitions"]
    with S.expect_refused("department") as met:
        S.check_department(dict(d, goal="Mine now"), before=before, by="Priority")
    assert met == ["$.goal: is Identity's, and Priority wrote it"], "ownership is a row in warn mode"
    monkeypatch.setattr(S, "MODE", "refuse")
    with S.expect_refused("department") as met:
        S.check_department(dict(d, stopped="yes"), before=before)       # the owner's Stop always lands
    assert met == ["$.stopped: is not true or false"]
    with S.expect_refused("department"):
        with pytest.raises(S.SchemaFault):
            S.check_department(dict(d, colour="red"), before=before)


def test_s4_a_new_workflows_entry_is_a_registration_and_meets_the_write_stage():
    base = {"kind": "website", "ref": "r", "name": "Acme"}
    reg = {"version": 1, "engines": ["Plan", "Write", "Check", "Publish"], "source": "library", "registered": "2026-10-26", "by": "Root"}
    S.check_department(dict(base, workflows=[reg]), before=base)
    with S.expect_refused("department") as met:
        with pytest.raises(S.SchemaFault):
            S.check_department(dict(base, workflows=[reg, {"version": 2, "engines": ["Plan"], "source": "copied"}]),
                               before=dict(base, workflows=[reg]))
    assert "$.workflows[1].registered: is missing" in met and "$.workflows[1].source: is not one of library, shaped, fitted, made" in met
    assert not [f for f in met if f.startswith("$.workflows[0]")], "the entry already on the record is not read again"


def test_s4_validate_field_instructions_view_and_record():
    assert S.validate_field("identity", "take", "take", "task", "Judge one request from the owner.") == []
    assert S.validate_field("identity", "take", "take", "task", "Judge {{words}}") != []
    assert S.validate_field("identity", "take", "take", "returns", "x") == ["$: take.take has no field returns the owner may change"]
    assert S.validate_field("identity", "take", "nowhere", "task", "x") == ["$: Identity has no part take.nowhere"]
    assert S.validate_field("identity", "goal", "skills", "items", ["judge a request against the goal"]) == []
    good = {"schema_version": 1, "values": {"identity": {"take": {"take": {"task": {"value": "Judge it.", "at": "2026-10-26", "ask": "a-1"}}}}}}
    assert S.validate_instructions(good) == []
    bad = json.loads(json.dumps(good))
    bad["values"]["identity"]["take"]["take"]["task"]["value"] = "Return ONLY yes"
    assert S.validate_instructions(bad) == ["$.values.identity.take.take.task: holds 'Return ONLY': the answer's shape belongs to the app"]
    assert S.validate_view("identity", {}) != [] and S.validate_view("root", {}) == ["$: root has no view"]
    assert S.validate_record("identity", "rule", {"line": "x"}) == []
    assert S.validate_record("identity", "colour", {}) == ["$: Identity keeps no record named colour"]


def test_s4_describe_is_the_whole_interface_as_json():
    got = S.describe()
    assert json.loads(json.dumps(got)) == got
    for k in ("layers", "records", "department_keys", "hears", "sends", "edges", "calls", "verdicts", "checks", "shared_checks",
              "contract_samples", "outputs", "settings", "groups", "prompts", "option_kinds", "workflow_standards", "views",
              "sink", "sink_journals", "defs", "template_levels", "ask_forms", "ledger_actions", "recognitions", "steps"):
        assert got[k], k
    assert got["edges"] == R.defs()["edges"] and got["schema_version"] == S.SCHEMA_VERSION


# ---- S6: the generated JSON Schema files ------------------------------------------------------------------------------
FILES = ("department.schema.json", "workflow.schema.json", "records.schema.json", "acts.schema.json",
         "instructions.schema.json", "views.schema.json", "templates.schema.json", "journeys.schema.json", "interface.v1.json")


def test_s6_the_files_on_disk_are_what_the_definitions_generate():
    got = S.json_schemas()
    assert tuple(got) == FILES
    for name, doc in got.items():
        on_disk = (S.SCHEMA_FOLDER / name).read_text(encoding="utf-8")
        assert on_disk == S._dump(doc), "%s differs from layer_schema.py: run `python layer_schema.py --write`" % name


def test_s6_a_changed_definition_without_write_fails_the_check(monkeypatch):
    monkeypatch.setitem(S.DEFS, "envelope", S.obj({"calls": S.integer(0), "usd": S.number(0), "day": S.text(10)}))
    got = S.json_schemas()["department.schema.json"]
    assert S._dump(got) != (S.SCHEMA_FOLDER / "department.schema.json").read_text(encoding="utf-8")


def test_s6_each_file_is_draft_2020_12_with_its_id_and_holds_every_definition_it_reaches():
    for name, doc in S.json_schemas().items():
        if name == "interface.v1.json":
            assert doc == S.describe()
            continue
        assert doc["$schema"] == "https://json-schema.org/draft/2020-12/schema"
        assert doc["$id"] == "https://sutra.asawa.co/schemas/layers/" + name
        text = json.dumps(doc)
        for ref in set(__import__("re").findall(r'"\$ref": "#/\$defs/([^"]+)"', text)):
            assert ref in doc["$defs"], "%s: %s is reached and not held" % (name, ref)
    dept = S.json_schemas()["department.schema.json"]["$defs"]["department"]["properties"]
    assert {k: v["x-owner"] for k, v in dept.items()} == {k: owner for k, (owner, _) in S.DEPARTMENT_KEYS.items()}


def test_s6_the_readme_points_at_every_layer_and_says_the_files_are_generated():
    readme = (S.SCHEMA_FOLDER / "README.md").read_text(encoding="utf-8")
    assert "never edited by hand" in readme and "python layer_schema.py --write" in readme
    for layer in S.LAYER_NAMES:
        assert "| %s |" % S.TITLE[layer] in readme and "LAYERS['%s']" % layer in readme
    for name in FILES:
        assert "`%s`" % name in readme


# ---- S7: the layer package and the recipes in it ---------------------------------------------------------------------
import importlib  # noqa: E402

import layers  # noqa: E402

BASE = S.HERE / "test_fixtures" / "function-engines.base.json"


def test_s7_defs_assembles_each_function_from_its_layers_recipe_as_the_file_held_it():
    base = json.loads(BASE.read_text(encoding="utf-8"))
    engines = R.defs()["engines"]
    assert list(engines)[:5] == list(base) == ["Identity", "Priority", "Coordination", "Adaptation", "Audit"]
    for fn, obj in base.items():
        assert engines[fn] == obj, fn
        p = S.HERE / "layers" / S.ENGINE_LAYER[fn] / "v1.json"
        assert p.read_text(encoding="utf-8") == json.dumps(obj, indent=1, ensure_ascii=False) + "\n", "%s: byte for byte" % fn
    assert layers.recipes() == base


def test_s7_website_json_keeps_the_kinds_the_edges_the_table_and_the_journeys_with_no_engine():
    raw = json.loads((S.HERE / "engine_defs" / "website.json").read_text(encoding="utf-8"))
    assert raw["engines"] == {} and raw["kinds"] and raw["edges"] and raw["coordination"] and raw["journeys"]
    assert "layers/<layer>/v1.json" in raw["comment"]
    assert R.validate(R.defs()) == [], "the definitions lane prints clean"


def test_s7_a_missing_recipe_refuses_the_definitions_load_with_a_named_fault(tmp_path, monkeypatch):
    for layer in layers.RECIPE_ORDER:
        (tmp_path / layer).mkdir()
        if layer != "audit":
            (tmp_path / layer / "v1.json").write_text((S.HERE / "layers" / layer / "v1.json").read_text(encoding="utf-8"), encoding="utf-8")
    monkeypatch.setattr(layers, "HERE", tmp_path)
    monkeypatch.setattr(R, "_DEFS", {})
    with pytest.raises(ValueError) as got:
        R.defs()
    assert str(got.value) == "the engine definitions are refused: Audit's recipe (audit/v1) is missing"
    (tmp_path / "audit" / "v1.json").write_text("{not json", encoding="utf-8")
    with pytest.raises(ValueError) as got:
        layers.recipes()
    assert str(got.value).startswith("the engine definitions are refused: Audit's recipe (audit/v1) is not JSON")


def test_s7_a_ref_to_delegate_calls_the_reloaded_modules_function(monkeypatch):
    names = layers.ref_to("_names")
    assert names.legacy == ("engine_runtime", "_names") and names(["Plan", "Write"]) == "Plan and Write"
    importlib.reload(R)
    monkeypatch.setattr(R, "_names", lambda xs: "the reloaded one")
    assert names(["Plan"]) == "the reloaded one"
    assert layers.R.engine_def("Identity")["kind"] == "function", "the lazy proxy reaches the reloaded module"


def test_s7_nothing_in_the_layer_package_imports_the_runtime_at_import_time():
    src = (S.HERE / "layers" / "__init__.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    top = [n for n in tree.body if isinstance(n, (ast.Import, ast.ImportFrom))]
    assert not [n for n in top for a in n.names if a.name in ("engine_runtime", "website_dept", "j2_runtime", "functions_view")]
    for layer in S.LAYER_NAMES:
        m = importlib.import_module("layers.%s.v1" % layer)
        assert (m.LAYER, m.VERSION, m.IMPLEMENTS) == (layer, 1, S.SCHEMA_VERSION)
        # wave 0 held empty stubs; from wave 1 a layer's package fills its dicts (a callable each, by reference or a body of
        # its own) and its words, and the module holds nothing beyond them
        assert all(isinstance(x, dict) for x in (m.CODE, m.PROMPT, m.DRAFT, m.CHECK, m.WORDS, m.LAYOUT))
        assert all(callable(v) for x in (m.CODE, m.PROMPT, m.DRAFT, m.CHECK) for v in x.values())
        assert getattr(m, "RECIPE_TEMPLATE" if layer == "root" else "RECIPE") == ("Setup" if layer == "root" else "v1.json")
        assert (S.HERE / "layers" / layer / "__init__.py").read_text(encoding="utf-8") == ""


# ---- X2: strict and frozen (W3-PROOF, PRD M2.10 and M10.5) -------------------------------------------------------------------------
def test_x2_the_interface_is_frozen_at_schema_version_1():
    """interface_sha() is the sha256 of describe() as sorted JSON, INTERFACE_SHA[1] is that, and nothing about it is a guess: it is the hash
    of the bytes of schemas/layers/interface.v1.json. A change to anything describe() holds fails here; the way out is not a new hash for
    this version but schema version 2 and a migration (A1.21)."""
    assert set(S.INTERFACE_SHA) == {S.SCHEMA_VERSION} == {1}
    assert S.INTERFACE_SHA[1] == S.interface_sha(), "the interface changed after the freeze: it needs schema version 2 and a migration"
    assert S.interface_sha() == hashlib.sha256((S.SCHEMA_FOLDER / "interface.v1.json").read_bytes()).hexdigest()
    assert S.interface_sha() == hashlib.sha256(S._dump(S.describe()).encode("utf-8")).hexdigest() == S.interface_sha(), "and it is stable"
    assert re.fullmatch(r"[0-9a-f]{64}", S.INTERFACE_SHA[1])


def test_x2_the_hash_moves_with_the_interface_and_with_nothing_else(monkeypatch):
    """A frozen hash that no change could move would freeze nothing. A constant, a definition or a table of the interface moves it; the
    modes (which are the app's, not the interface's) do not."""
    frozen = S.interface_sha()
    monkeypatch.setitem(S.DEFS, "test.flag", S.boolean())
    assert S.interface_sha() != frozen, "a definition added"
    monkeypatch.delitem(S.DEFS, "test.flag")
    assert S.interface_sha() == frozen
    monkeypatch.setattr(S, "ROUNDS_DEFAULT", S.ROUNDS_DEFAULT + 1)
    assert S.interface_sha() != frozen, "a constant changed"
    monkeypatch.undo()
    monkeypatch.setattr(S, "MODE", "warn")
    monkeypatch.setattr(S, "OWNERSHIP_MODE", "warn")
    assert S.interface_sha() == frozen, "the modes are not the interface"


def test_x2_the_generated_files_equal_json_schemas_and_each_is_a_json_schema():
    got = S.json_schemas()
    assert sorted(p.name for p in S.SCHEMA_FOLDER.glob("*.json")) == sorted(got), "no file is missing and none is left over"
    for name, doc in got.items():
        assert (S.SCHEMA_FOLDER / name).read_text(encoding="utf-8") == S._dump(doc), "%s is what the interface generates (python layer_schema.py --write)" % name
    jsonschema = pytest.importorskip("jsonschema")
    schemas = [name for name in got if name.endswith(".schema.json")]
    assert len(schemas) == len(got) - 1 and "interface.v1.json" not in schemas, "every file but describe() itself is a JSON Schema"
    for name in schemas:
        jsonschema.Draft202012Validator.check_schema(got[name])


def test_x2_a_save_that_changes_a_key_another_layer_owns_is_refused_with_one_row(home):
    """OWNERSHIP_MODE is 'refuse': Priority saving the goal, which is Identity's, is refused after one row (REFUSED and the department's
    runs), and the record is as it was; the same save of a key Priority owns, and a save that names no layer, go through."""
    W = home
    ref = "dref-ownership01"
    W.create(ref, "Ownership Website", None)
    before = copy.deepcopy(W.dept(ref))
    d = W.dept(ref)
    d["goal"] = "a goal Priority has no business writing"
    rows, runs = len(S.REFUSED["rows"]), len(W.runs(ref))
    with S.expect_refused("department") as met:
        with pytest.raises(S.SchemaFault) as cm:
            W.save_dept(ref, d, by="priority")
    assert met == ["$.goal: is Identity's, and Priority wrote it"] and cm.value.faults == met
    assert len(met.rows) == 1 and met.rows[0]["owner"] == "priority" and met.rows[0]["kept"] is False, "one row, and the write was refused, not kept"
    new = W.runs(ref)[runs:]
    assert len(new) == 1 and new[0]["what"] == "refused a write that does not fit the interface: department: $.goal: is Identity's, and Priority wrote it"
    assert W.dept(ref).get("goal") == before.get("goal"), "nothing was written"
    # a key the layer owns, and a save that names no layer, are not refused
    d = W.dept(ref)
    d["envelopes"]["Plan"] = {"calls": 3, "usd": 0.5}
    W.save_dept(ref, d, by="priority")
    d = W.dept(ref)
    d["goal"] = "a goal the owner changed"
    W.save_dept(ref, d)
    assert W.dept(ref)["goal"] == "a goal the owner changed" and W.dept(ref)["envelopes"]["Plan"] == {"calls": 3, "usd": 0.5}


def test_x2_the_owners_stop_and_control_still_land_whoever_saves_them(home):
    """NEVER_REFUSE keys are never refused for a fault of their own; ownership is refused for the keys that have an owner, and Stop has none
    to fight over (the department saves it as the owner's)."""
    W = home
    ref = "dref-ownership02"
    W.create(ref, "Ownership Website Two", None)
    d = W.dept(ref)
    d["stopped"] = True
    W.save_dept(ref, d)
    assert W.dept(ref)["stopped"] is True


# ---- X2: the validator against jsonschema, on 40 cases ---------------------------------------------------------------------------
def _real_cases():
    """Real values of the interface's definitions, from the app's own data, each with one thing broken as a second case: a kind, a step, an
    artifact template and a journey's status document (A3)."""
    import engine_runtime as R
    kind = R.defs()["kinds"]["website"]
    step = R.engine_def("Plan")["steps"][0]
    template = json.loads((S.HERE / "artifact-templates" / "brief.json").read_text(encoding="utf-8"))
    status = json.loads((S.HERE / "journeys" / "status" / "J1.json").read_text(encoding="utf-8"))
    out = [("kind", kind), ("step", step), ("artifact.template", template), ("journey.status", status)]
    out += [("kind", {k: v for k, v in kind.items() if k != "artifacts"}), ("step", dict(step, nature="dream")),
            ("artifact.template", dict(template, counts_after="never")), ("journey.status", dict(status, state="astonishing"))]
    return out


def _cases():
    """40 cases (name of a definition, a value): good and bad, over every keyword the validator supports -- type, enum, const, lengths, pattern,
    bounds, items, required, additionalProperties, propertyNames and anyOf -- each on a definition the interface really has."""
    ok = {"id": "D1", "text": "The site is live"}
    est = {"calls": 4, "usd": 0.2}
    return [
        ("impl", "identity/v1"), ("impl", "audit/v12"), ("impl", "identity/v0"), ("impl", "nobody/v1"), ("impl", "identity/v1 "), ("impl", 7),
        ("id.item", "D1"), ("id.item", "D12"), ("id.item", "D0"), ("id.item", "d1"), ("id.item", "D123"), ("id.item", ["D1"]),
        ("name", "Booking"), ("name", "Facts 2"), ("name", "-x"), ("name", ""), ("name", "x" * 41), ("name", None),
        ("identity.done_item", ok), ("identity.done_item", dict(ok, how="code")), ("identity.done_item", {"id": "D1"}),
        ("identity.done_item", dict(ok, colour="red")), ("identity.done_item", dict(ok, text="")), ("identity.done_item", dict(ok, text="x" * 301)),
        ("envelope", {"calls": 3, "usd": 0.5}), ("envelope", {"calls": 3, "usd": 0}), ("envelope", {"calls": 3}), ("envelope", {"calls": 3.5, "usd": 1}),
        ("envelope", {"calls": True, "usd": 1}), ("envelope", {"calls": -1, "usd": 1}), ("envelope", {"calls": 3, "usd": 1, "note": "extra keys pass"}),
        ("priority.estimate", est), ("priority.estimate", dict(est, basis="median", runs=3)), ("priority.estimate", dict(est, basis="guess")),
        ("priority.estimate", dict(est, per_engine={"Plan": {"calls": 1, "usd": 0.1, "basis": "prior"}})),
        ("priority.estimate", dict(est, per_engine={"Plan": {"calls": 1, "usd": 0.1, "basis": "line"}})),
        ("coordination.slot", {"engine": "Plan", "on": "version"}), ("coordination.slot", {"engine": "Plan", "on": "version", "window_min": 2000}),
        ("coordination.slot", {"engine": "Plan", "on": "version", "colour": "red"}), ("coordination.slot", {"engine": "Plan"}),
        ("audit.finding", {"id": "F1", "severity": "high", "claim": "x", "where": "index"}), ("audit.finding", {"id": "F1", "severity": "grave", "claim": "x", "where": "index"}),
        ("audit.finding", {"id": "F1", "severity": "low", "claim": "x", "where": "index", "went_to": None}),
        ("audit.finding", {"id": "F1", "severity": "low", "claim": "x", "where": "index", "went_to": "Priority"}),
        ("audit.finding", {"id": "F1", "severity": "low", "claim": "x", "where": "index", "item": "D2"}),
        ("setting.windows", {"Plan": 30}), ("setting.windows", {"Plan": 2000}), ("setting.windows", {"Plan": "soon"}),
        ("check.verdict", {"ok": True, "notes": []}), ("check.verdict", {"ok": "yes", "notes": []}), ("check.verdict", {"ok": True, "notes": ["x" * 2001]}),
    ] + _real_cases()


def test_x2_the_validator_agrees_with_jsonschema_on_40_cases():
    """The built-in validator (no third-party import: A1-D2) and jsonschema agree on whether a value fits a definition, over forty cases, with
    the schema taken from the generated files other tools read. (jsonschema is an optional import: the test is for where it is there.)"""
    jsonschema = pytest.importorskip("jsonschema")
    docs = {name: json.loads((S.SCHEMA_FOLDER / name).read_text(encoding="utf-8")) for name in S.json_schemas()}

    def held_in(name):
        return next(doc["$defs"] for doc in docs.values() if name in doc.get("$defs", {}))

    cases = _cases()
    assert len(cases) >= 40
    seen = {"fits": 0, "fails": 0}
    for name, value in cases:
        schema = {"$schema": "https://json-schema.org/draft/2020-12/schema", "$ref": "#/$defs/" + name, "$defs": held_in(name)}
        theirs = jsonschema.Draft202012Validator(schema).is_valid(value)
        mine = S.validate(name, value) == []
        assert mine == theirs, "%s %s: the validator says %s and jsonschema says %s (%s)" % (
            name, json.dumps(value, default=str)[:120], mine, theirs, S.validate(name, value)[:1])
        seen["fits" if mine else "fails"] += 1
    assert seen["fits"] >= 15 and seen["fails"] >= 15, seen


def test_x2_the_validator_is_stricter_than_jsonschema_only_where_the_interface_has_a_keyword_of_its_own():
    """x-say and x-field are the interface's (A1.4, A1.16): a control character in words the owner reads, a '{{' in a prompt field. Plain
    JSON Schema cannot say them, so jsonschema passes what the validator refuses; these are the only places the two differ."""
    jsonschema = pytest.importorskip("jsonschema")
    docs = {name: json.loads((S.SCHEMA_FOLDER / name).read_text(encoding="utf-8")) for name in S.json_schemas()}
    differ = []
    for name, value in (("field.task", "Judge {{words}} kindly"), ("field.task", "Return ONLY yes"), ("option", {"id": "words", "label": "Say\x07 it", "cost": "free"})):
        defs = next(doc["$defs"] for doc in docs.values() if name in doc.get("$defs", {}))
        theirs = jsonschema.Draft202012Validator({"$ref": "#/$defs/" + name, "$defs": defs}).is_valid(value)
        mine = S.validate(name, value) == []
        if mine != theirs:
            differ.append((name, mine, theirs))
    assert differ == [("field.task", False, True), ("field.task", False, True), ("option", False, True)], differ
