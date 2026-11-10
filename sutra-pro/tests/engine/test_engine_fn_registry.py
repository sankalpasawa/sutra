"""The verify registry (WP E8, engine design 4.3a, function-nodes.md section 4): the 14 pure checks, the evidence they read,
the fixture cases (`fixtures/fn_registry/<check>/<case>.json` = {args, evidence, expect}), purity, and parity with the
vendored J2 code the checks are ports of. The mutation tests are in test_engine_fn_mutations.py and reuse the helpers here.

A fixture's `evidence` is partial: the turn gets defaults from the check's CheckSpec, `outcome` and `call` are merged over
defaults, and everything else is passed to `Evidence` as it is. The case file name says what it must show: `pass*` ok with
nothing else, `fail*` not ok, `na*` does not apply, `recovered*` ok with `changed`, `waived*` ok and waived."""
import builtins
import contextlib
import copy
import importlib
import io
import itertools
import json
import os
import socket
import sys
import time
import types
from pathlib import Path

import pytest
from pydantic import ValidationError

from sutra_app.engine.fnodes import evidence as evidence_module
from sutra_app.engine.fnodes import registry as registry_module
from sutra_app.engine.fnodes.evidence import RECORD_NAMES, Evidence, merge_records, read_records
from sutra_app.engine.fnodes.registry import (AGENT_CONTENT, GATE, J2_STRINGS, NOT_CHECKABLE, REGISTRY, USER_CONTENT, J2_ROUTES, CheckArgsError,
                                               Outcome, UnknownCheck, stamp_check, workable_problems)
from sutra_app.library.atom import CHECK_NAMES, REGISTRY_CHECKS, check_arity

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "fn_registry"
ENGINE = "sutra_app.engine"

# which kinds of case each check must have (function-nodes.md section 9: pass, fail, and na / override / recovered / waived where they apply)
REQUIRED = {
    "reply-valid": {"pass", "fail", "na"}, "turn-posted": {"pass", "fail"}, "charter-stamp": {"pass", "fail", "na", "waived"},
    "workable": {"pass", "fail", "recovered"}, "audience-split": {"pass", "fail", "na", "recovered"},
    "atom-rules": {"pass", "fail", "na", "recovered"}, "judge-gate": {"pass", "fail", "na", "waived"},
    "price-kept": {"pass", "fail", "recovered"}, "within-budget": {"pass", "fail", "na", "recovered"},
    "order-registered": {"pass", "fail", "na", "recovered"}, "finding-per-item": {"pass", "fail", "recovered"},
    "pass-needs-proof": {"pass", "fail", "recovered"}, "code-measure-wins": {"pass", "fail", "na"}, "answer-recorded": {"pass", "fail"},
}
CASE_FILES = sorted(p for p in FIXTURES.glob("*/*.json"))


# ---- helpers shared with test_engine_fn_mutations.py ---------------------------------------------------------------------

def build_evidence(check: str, raw: dict) -> Evidence:
    """An Evidence from a partial fixture dict (see the module docstring)."""
    spec = REGISTRY[check]
    raw = copy.deepcopy(raw)
    turn = {"run_id": "j2-test", "dept_id": "web", "turn_no": 1, "function": spec.functions[0] if spec.functions else "priority",
            "kind": spec.task_kinds[0] if spec.task_kinds else "intake", "step": 1, "step_label": "J2.x test", "cycle": 1,
            "task": "test", "context": [], **raw.get("turn", {})}
    out = {**raw, "turn": turn}
    if "outcome" in raw:
        out["outcome"] = {"result": "ok", **raw["outcome"]}
    if "call" in raw:
        out["call"] = {"call_no": 1, "function": turn["function"], "step": 1, "purpose": "agent_turn", "seconds": 0.1, "inputs": [], **raw["call"]}
    return Evidence(**out)


def load_case(path: Path) -> tuple[str, tuple[str, ...], dict, dict]:
    body = json.loads(path.read_text(encoding="utf-8"))
    return path.parent.name, tuple(body["args"]), body["evidence"], body["expect"]


def mismatches(outcome: Outcome, expect: dict) -> list[str]:
    """Where an Outcome differs from a fixture's `expect` (an empty list means it matches)."""
    out = []
    want = {"na": False, "waived": False, "changed": [], **expect}
    if outcome.ok != want["ok"]:
        out.append(f"ok {outcome.ok} != {want['ok']}")
    if outcome.na != want["na"]:
        out.append(f"na {outcome.na} != {want['na']}")
    if outcome.waived != want["waived"]:
        out.append(f"waived {outcome.waived} != {want['waived']}")
    if list(outcome.changed) != want["changed"]:
        out.append(f"changed {list(outcome.changed)} != {want['changed']}")
    if "evidence" in want and outcome.evidence != want["evidence"]:
        out.append(f"evidence {outcome.evidence!r} != {want['evidence']!r}")
    for part in want.get("evidence_has", []):
        if part not in outcome.evidence:
            out.append(f"evidence {outcome.evidence!r} lacks {part!r}")
    return out


def run_case(path: Path, fn=None) -> list[str]:
    check, args, raw, expect = load_case(path)
    ev = build_evidence(check, raw)
    outcome = fn(ev, args) if fn else REGISTRY.run(check, ev, args)
    return mismatches(outcome, expect)


# ---- the registry itself -------------------------------------------------------------------------------------------------

def test_the_registry_holds_the_librarys_fourteen_names_in_order():
    assert REGISTRY.names() == tuple(REGISTRY_CHECKS) and len(REGISTRY) == 14
    assert set(REGISTRY_CHECKS) <= set(CHECK_NAMES)
    assert all(name in REGISTRY for name in REGISTRY_CHECKS) and "file-exists" not in REGISTRY


def test_every_check_has_a_sentence_phases_and_tries():
    for name in REGISTRY:
        spec = REGISTRY[name]
        assert spec.name == name and spec.text.endswith(".") and 1 <= spec.tries <= 3
        assert spec.phases and set(spec.phases) <= {"reply", "turn", "event"} and spec.kind in ("gate", "override")
        assert len(spec.text) <= 300                         # Check.text is Text300
    assert REGISTRY.for_phase("reply") == ("reply-valid", "audience-split")
    assert REGISTRY.for_phase("event") == ("answer-recorded",)
    assert "reply-valid" not in REGISTRY.for_phase("turn") and "turn-posted" in REGISTRY.for_phase("turn")


def test_the_registry_cannot_be_changed_after_import():
    with pytest.raises(AttributeError):
        REGISTRY._specs = {}
    with pytest.raises(TypeError):
        REGISTRY._specs["x"] = None
    with pytest.raises(AttributeError):
        REGISTRY.new_attribute = 1
    assert not hasattr(REGISTRY, "register") and not hasattr(REGISTRY, "__setitem__")


def test_an_unknown_name_and_wrong_argument_counts_are_refused():
    ev = build_evidence("turn-posted", {})
    with pytest.raises(UnknownCheck):
        REGISTRY.run("file-exists", ev, ("x",))
    with pytest.raises(UnknownCheck):
        REGISTRY["nope"]
    with pytest.raises(CheckArgsError, match="reply-valid takes 2 to 2"):
        REGISTRY.run("reply-valid", ev, ("only-one",))
    with pytest.raises(CheckArgsError, match="turn-posted takes 0 to 0"):
        REGISTRY.run("turn-posted", ev, ("extra",))
    with pytest.raises(CheckArgsError):
        REGISTRY.run("answer-recorded", ev, ())


def test_the_argument_rules_are_the_librarys():
    for name in REGISTRY:
        assert check_arity(name) is not None
    assert check_arity("reply-valid") == (2, 2) and check_arity("answer-recorded") == (1, 1)


# ---- Outcome ------------------------------------------------------------------------------------------------------------

def test_outcome_flags_must_fit_together():
    assert Outcome(ok=True).exit_code == 0 and Outcome(ok=False).exit_code == 1 and Outcome(ok=True, na=True).exit_code == 0
    with pytest.raises(ValidationError):
        Outcome(ok=False, na=True)
    with pytest.raises(ValidationError):
        Outcome(ok=False, waived=True)
    with pytest.raises(ValidationError):
        Outcome(ok=False, changed=("x",))
    with pytest.raises(ValidationError):
        Outcome(ok=True, na=True, waived=True)
    with pytest.raises(ValidationError):
        Outcome(ok=True, waived=True, changed=("x",))
    with pytest.raises(ValidationError):
        Outcome(ok=True, surplus=1)


def test_outcome_evidence_is_cut_at_2000_characters_and_the_object_is_frozen():
    o = Outcome(ok=False, evidence="x" * 5000)
    assert len(o.evidence) == 2000 and o.evidence.endswith("…")
    with pytest.raises(ValidationError):
        o.ok = True


# ---- Evidence and the run-folder reader ----------------------------------------------------------------------------------

def test_evidence_is_closed_and_frozen_and_the_latest_reply_is_the_default():
    ev = build_evidence("turn-posted", {"replies": [{"a": 1}, {"b": 2}]})
    assert ev.reply == {"b": 2}
    assert build_evidence("turn-posted", {"replies": [{"a": 1}], "reply": {"z": 0}}).reply == {"z": 0}
    with pytest.raises(ValidationError):
        ev.prompt = "x"
    with pytest.raises(ValidationError):
        build_evidence("turn-posted", {"surplus": 1})


def test_saved_names_are_given_or_derived_from_what_changed_since_turn_start():
    same, other = {"a": 1}, {"a": 2}
    ev = build_evidence("turn-posted", {"records": {"goal.json": same, "audits.json": other, "workflows.json": []},
                                        "before": {"goal.json": same, "audits.json": same}})
    assert ev.saved_names == {"audits.json", "workflows.json"}
    given = build_evidence("turn-posted", {"records": {"goal.json": same}, "before": {"goal.json": same}, "saved": ["goal.json"]})
    assert given.saved_names == {"goal.json"}


def test_last_audit_skips_board_rechecks():
    ev = build_evidence("workable", {"records": {"audits.json": [{"n": 1}, {"n": 2}, {"kind": "recheck"}]}})
    assert ev.last_audit() == {"n": 2}
    assert build_evidence("workable", {"records": {"audits.json": [{"kind": "recheck"}]}}).last_audit() is None
    assert build_evidence("workable", {}).last_audit() is None


def test_merge_records_prefers_what_was_saved_this_turn():
    assert merge_records({"a": 1, "b": 2}, {"b": 3, "c": 4}) == {"a": 1, "b": 3, "c": 4}


def test_read_records_reads_the_five_files_and_changes_nothing(tmp_path):
    (tmp_path / "goal.json").write_text('{"statement": "s"}', encoding="utf-8")
    (tmp_path / "audits.json").write_text("[1]", encoding="utf-8")
    (tmp_path / "chat.jsonl").write_text("not a record", encoding="utf-8")
    before = sorted((p.name, p.stat().st_mtime_ns, p.read_bytes()) for p in tmp_path.iterdir())
    problems: list[str] = []
    assert read_records(tmp_path, problems=problems) == {"goal.json": {"statement": "s"}, "audits.json": [1]}
    assert problems == []
    assert sorted((p.name, p.stat().st_mtime_ns, p.read_bytes()) for p in tmp_path.iterdir()) == before
    assert RECORD_NAMES == ("goal.json", "workflows.json", "audits.json", "realization.json", "conflicts.json")


def test_read_records_reports_what_it_cannot_use_and_never_raises(tmp_path):
    (tmp_path / "goal.json").write_text("{broken", encoding="utf-8")
    outside = tmp_path / "elsewhere"
    outside.mkdir()
    (outside / "x.json").write_text("[]", encoding="utf-8")
    run = tmp_path / "run"
    run.mkdir()
    (run / "workflows.json").symlink_to(outside / "x.json")
    (run / "audits.json").write_text("[]", encoding="utf-8")
    problems: list[str] = []
    got = read_records(run, ("workflows.json", "audits.json", "../x.json", "goal.json"), problems=problems)
    assert got == {"audits.json": []}
    assert any("workflows.json: a link that leaves the run folder" in p for p in problems)
    assert any("../x.json: not a record" in p for p in problems)
    bad: list[str] = []
    assert read_records(tmp_path / "goal.json", problems=bad) == {} and bad            # not a folder
    assert read_records(tmp_path / "missing", problems=bad) == {} and "run folder" in bad[-1]
    (tmp_path / "goal.json").write_text("{broken", encoding="utf-8")
    only: list[str] = []
    assert read_records(tmp_path, ("goal.json",), problems=only) == {} and "goal.json: JSONDecodeError" in only[0]


def test_read_records_refuses_a_file_over_the_size_limit(tmp_path, monkeypatch):
    (tmp_path / "goal.json").write_text("{}", encoding="utf-8")
    monkeypatch.setattr(evidence_module, "MAX_RECORD_BYTES", 1)
    problems: list[str] = []
    assert read_records(tmp_path, ("goal.json",), problems=problems) == {} and "larger than 1 bytes" in problems[0]


# ---- fixture cases -------------------------------------------------------------------------------------------------------

def test_every_check_has_its_required_kinds_of_case_and_nothing_else_is_there():
    assert sorted(p.name for p in FIXTURES.iterdir()) == sorted(REGISTRY.names())
    for check, kinds in REQUIRED.items():
        have = {p.stem.split("_")[0] for p in (FIXTURES / check).glob("*.json")}
        assert kinds <= have, f"{check} lacks {kinds - have}"
        assert have <= {"pass", "fail", "na", "recovered", "waived"}


@pytest.mark.parametrize("path", CASE_FILES, ids=lambda p: f"{p.parent.name}/{p.stem}")
def test_fixture_case(path):
    assert run_case(path) == []


@pytest.mark.parametrize("path", CASE_FILES, ids=lambda p: f"{p.parent.name}/{p.stem}")
def test_case_name_says_what_it_shows(path):
    _, _, _, expect = load_case(path)
    kind = path.stem.split("_")[0]
    flags = {"ok": expect["ok"], "na": expect.get("na", False), "waived": expect.get("waived", False), "changed": bool(expect.get("changed"))}
    assert flags == {
        "pass": {"ok": True, "na": False, "waived": False, "changed": False}, "fail": {"ok": False, "na": False, "waived": False, "changed": False},
        "na": {"ok": True, "na": True, "waived": False, "changed": False}, "recovered": {"ok": True, "na": False, "waived": False, "changed": True},
        "waived": {"ok": True, "na": False, "waived": True, "changed": False}}[kind]


# ---- purity --------------------------------------------------------------------------------------------------------------

@contextlib.contextmanager
def forbidden_world():
    """Open, clocks and sockets raise while a check runs."""
    def refuse(name):
        def raiser(*a, **k):
            raise AssertionError(f"a check used {name}")
        return raiser
    class NoSocket:
        def __init__(self, *a, **k):
            raise AssertionError("a check used a socket")
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(builtins, "open", refuse("open"))
        mp.setattr(io, "open", refuse("io.open"))
        mp.setattr(os, "open", refuse("os.open"))
        for clock in ("time", "monotonic", "perf_counter", "sleep", "time_ns"):
            mp.setattr(time, clock, refuse(f"time.{clock}"))
        mp.setattr(socket, "socket", NoSocket)
        mp.setattr(socket, "create_connection", refuse("socket.create_connection"))
        yield


def test_checks_use_no_file_clock_or_socket_and_leave_their_input_untouched():
    for path in CASE_FILES:
        check, args, raw, expect = load_case(path)
        ev = build_evidence(check, raw)
        snapshot = copy.deepcopy(ev.model_dump())
        with forbidden_world():
            outcome = REGISTRY.run(check, ev, args)
        assert ev.model_dump() == snapshot, f"{path} changed its evidence"
        assert mismatches(outcome, expect) == []


def test_a_check_gives_the_same_answer_on_a_deep_copy():
    for path in CASE_FILES:
        check, args, raw, _ = load_case(path)
        ev = build_evidence(check, raw)
        assert REGISTRY.run(check, ev, args) == REGISTRY.run(check, copy.deepcopy(ev), args) == REGISTRY.run(check, ev, list(args))


def test_the_forbidden_world_really_forbids():
    with forbidden_world():
        for attempt in (lambda: open(__file__), time.time, lambda: socket.socket(), lambda: time.sleep(0)):
            with pytest.raises(AssertionError):
                attempt()


# ---- parity with the vendored J2 -----------------------------------------------------------------------------------------

@contextlib.contextmanager
def fresh_j2(base: Path):
    """The vendored J2 imported anew in mock mode with its paths under `base`; the modules are put back afterwards."""
    from sutra_app.engine import llm
    package = importlib.import_module(ENGINE)
    names = ("j2", "j2_agent", "j2_agent_models", "j2_agent_views", "j2_artifact_models", "j2_artifacts", "j2_board", "j2_change", "j2_check",
             "j2_map", "j2_realization", "j2_rules", "j2_schema", "j2_send", "j2_story", "j2_studio", "j2_template_lib", "rehydrate")
    saved = {name: (sys.modules.pop(f"{ENGINE}.{name}", None), package.__dict__.pop(name, None)) for name in names}
    with pytest.MonkeyPatch.context() as mp:
        for name in list(os.environ):
            if name.startswith(("J2_", "STUDIO_")):
                mp.delenv(name)
        for key, value in {"STUDIO_MOCK": "1", "J2_MEMORY": "0", "J2_REALIZATION": "0", "J2_MEMORY_FILE": str(base / "lessons.jsonl"),
                           "J2_PLAYBOOK_FILE": str(base / "playbooks.jsonl"), "J2_RUNS_DIR": str(base / "runs"),
                           "J2_LIBRARY_DIR": str(base / "library")}.items():
            mp.setenv(key, value)
        mp.setattr(llm, "MOCK", True)
        try:
            yield importlib.import_module(f"{ENGINE}.j2")
        finally:
            for name, (old, attr) in saved.items():
                sys.modules.pop(f"{ENGINE}.{name}", None)
                package.__dict__.pop(name, None)
                if old is not None:
                    sys.modules[f"{ENGINE}.{name}"] = old
                if attr is not None:
                    package.__dict__[name] = attr


@pytest.fixture(scope="module")
def j2(tmp_path_factory):
    with fresh_j2(tmp_path_factory.mktemp("j2-env")) as mod:
        yield mod


@pytest.fixture
def run(j2, tmp_path, llm_reset):
    llm_reset.configure(mock=True)
    counter = itertools.count(1)
    return lambda: j2.J2Run(run_dir=tmp_path / "runs" / f"j2-20261104-1000{next(counter):02d}-7f3a")


def test_the_three_regexes_are_j2s_own(j2):
    for mine, theirs in ((NOT_CHECKABLE, j2.J2Run.NOT_CHECKABLE), (AGENT_CONTENT, j2.AGENT_CONTENT), (USER_CONTENT, j2.USER_CONTENT)):
        assert (mine.pattern, mine.flags) == (theirs.pattern, theirs.flags)


STAMP_GOALS = [
    None, {}, {"statement": "s"}, {"statement": "s", "done_when": ["a", "b"]}, {"statement": "s", "done_when": ["a", "b", "c"]},
    {"statement": "s", "done_when": ["a", "b", "Requester signs off"]}, {"statement": "s", "done_when": ["x", "y", "Site is verified"]},
    {"statement": "s", "done_when": ["a", "b", "Footer shows 'sample, replace before launch'"]},
    {"statement": "s", "done_when": ["a", "b", 'Banner says "go live soon" in quotes', "Audit passes", "Menu — “approved” label"]},
    {"statement": "s", "done_when": ["a", "b", "It goes live Monday", "Launch is planned"]},
    {"statement": "", "done_when": ["a", "b", "c"]},
]


@pytest.mark.parametrize("goal", STAMP_GOALS, ids=lambda g: json.dumps(g)[:50])
def test_stamp_check_equals_j2s_stamp_check(j2, goal):
    stand_in = types.SimpleNamespace(goal=goal, NOT_CHECKABLE=j2.J2Run.NOT_CHECKABLE)
    assert stamp_check(goal) == j2.J2Run._stamp_check(stand_in)


def _row(i, verdict="PASS", **kw):
    return {"id": f"F-{i}", "item": i, "criterion": f"Item {i}", "verdict": verdict, "pass": verdict.startswith("PASS"), "note": "n", **kw}


def _mech(**kw):
    return {"available": True, "phone": {"width": 360, "overflow_px": 0}, "desktop": {"width": 1280, "overflow_px": 0}, "js_errors": [],
            "broken_in_page_links": [], "form_results": [], **kw}


AUDITS = [
    None, {}, {"results": [_row(1), _row(2)], "mechanical": _mech()},
    {"results": [_row(1), _row(2, "NEEDS_REVISION")], "mechanical": _mech()},
    {"results": [_row(1), _row(2, "NEEDS_REVISION")], "accepted": ["Item 2"], "mechanical": _mech()},
    {"results": [_row(1)], "rubric": [{"id": "R-1", "verdict": "NEEDS_REVISION", "criterion": "Contrast", "pass": False}], "mechanical": _mech()},
    {"results": [_row(1)], "rubric": [{"id": "R-1", "verdict": "NEEDS_REVISION", "criterion": "Contrast", "pass": False}], "accepted": ["R-1"], "mechanical": _mech()},
    {"results": [_row(1)], "conditions": [{"id": "NC-1", "text": "t", "evidence": "e", "met": False}], "mechanical": _mech()},
    {"results": [_row(1)], "conditions": [{"id": "NC-1", "text": "t", "evidence": "e", "met": False, "severity": "warn"}], "mechanical": _mech()},
    {"results": [_row(1)], "conditions": [{"id": "NC-1", "text": "t", "evidence": "e", "met": False}], "accepted": ["NC-1"], "mechanical": _mech()},
    {"results": [_row(1)], "mechanical": {"available": False, "note": "no Chrome"}},
    {"results": [_row(1)], "mechanical": _mech(js_errors=["boom"], broken_in_page_links=["menu"], phone={"width": 360, "overflow_px": 12})},
    {"results": [_row(1)], "mechanical": _mech(form_results=[{"index": 1, "has_submit": False, "errors_during": [], "submitted": False, "invalid": [], "ok": False}])},
    {"output": "prd", "results": [_row(1, "NEEDS_REVISION")], "rubric": [{"id": "D-1", "verdict": "NEEDS_REVISION", "criterion": "x", "pass": False}],
     "conditions": [{"id": "NC-2", "text": "t", "evidence": "e", "met": False}]},
    {"output": "hld", "results": [_row(1)], "rubric": [], "conditions": []},
]


@pytest.mark.parametrize("audit", AUDITS, ids=lambda a: json.dumps(a)[:50])
def test_workable_problems_equal_j2s_workable(j2, audit):
    assert workable_problems(audit) == j2.workable(audit)


def test_design_problems_are_j2_checks_own_function(j2):
    assert registry_module.j2_check.design_problems.__name__ == "design_problems"
    frame = lambda low=0, h1=1, skipped=0, alt=(): {"contrast": {"low_count": low, "low": ["a on b"] * low}, "headings": {"h1": h1, "skipped_levels": skipped},
                                                    "images_without_alt": list(alt), "small_tap_targets": {"count": 2, "min_px": 44, "examples": ["a", "b"]}}
    for design in ({}, {"phone": frame(), "desktop": frame()}, {"phone": frame(low=3), "desktop": frame(h1=2, skipped=1, alt=["x.png"])}):
        assert registry_module.j2_check.design_problems({"design": design}) == j2.j2_check.design_problems({"design": design})
    assert j2.j2_check.design_problems({}) == {} == registry_module.j2_check.design_problems({})


def test_the_dispute_routes_are_j2s_routes(j2):
    assert {fn: tuple(to) for fn, to in J2_ROUTES.items()} == {fn: tuple(j2.ROUTES[fn]) for fn in J2_ROUTES}


def test_the_gate_is_the_judges_threshold(j2):
    assert GATE == j2.j2_realization.THRESHOLD == 0.80


def test_the_texts_j2_posts_are_still_what_the_checks_read(j2):
    source = Path(j2.__file__).read_text(encoding="utf-8")
    for text in J2_STRINGS:
        if text in (registry_module.NO_FINDING_NOTE, registry_module.NO_EVIDENCE_NOTE, registry_module.MEASURED_NOTE,
                    registry_module.REJECTED_PREFIX, registry_module.KEPT_PRICE, registry_module.KEPT_PRICE_TAIL):
            continue                                # built from pieces or by behaviour: the tests below run J2
        assert text in source, f"j2.py no longer holds {text!r}"


def test_a_rejection_j2_posts_is_what_atom_rules_reads(run):
    r = run()
    r._reject("Build menu", "missing completion_check")
    m = r.chat[-1]
    assert m["who"] == "system" and m["rejected"] == "Build menu" and m["text"].startswith(registry_module.REJECTED_PREFIX)
    assert registry_module._reason_of(m) == "missing completion_check"
    assert registry_module._is_atom_rejection(m)


def test_the_kept_price_note_j2_posts_is_what_price_kept_reads(run):
    r = run()
    table = [{"id": "P-1", "name": "Build menu", "cost": 12, "envelope": {"money_limit": 12}}]
    r._kept_price([{"id": "P-1", "name": "Build menu", "cost": None, "envelope": {}}], table)
    note = r.chat[-1]["text"]
    assert registry_module.KEPT_PRICE in note and registry_module.KEPT_PRICE_TAIL in note
    assert registry_module._kept_prices([note]) == {"Build menu": 12}


def test_the_audit_notes_j2_writes_are_what_the_audit_checks_read(run):
    r = run()
    r.goal = {"done_when": ["Menu is shown", "Hours are shown"], "charter_items": ["Menu is shown", "Hours are shown"]}
    results, _ = r._audit_findings([{"id": "F-1", "item": 1, "criterion": "Menu is shown", "verdict": "PASS", "evidence": ""}], r.goal["done_when"])
    assert results[0]["note"].startswith(registry_module.NO_EVIDENCE_NOTE) and results[0]["verdict"] == "BLOCKED_BY_EVIDENCE"
    assert results[1]["note"] == registry_module.NO_FINDING_NOTE and results[1]["item"] == 2
    rubric = r._audit_rubric([{"id": "R-2", "verdict": "PASS", "evidence": "fine"}], {"R-2": ["contrast is low"]})
    row = next(x for x in rubric if x["id"] == "R-2")
    assert row["verdict"] == "NEEDS_REVISION" and row["note"].startswith(registry_module.MEASURED_NOTE)


def test_the_over_budget_and_envelope_lines_are_in_j2s_posts(j2):
    source = Path(j2.__file__).read_text(encoding="utf-8")
    assert "exceeds the remaining budget ({remaining})" in source
    assert 'envelope="allowed"' in source and 'envelope="hold"' in source and 'envelope="over limit"' in source
    assert registry_module._BUDGET_USED_RE.search("Budget 40/100 used. Runs now.")
