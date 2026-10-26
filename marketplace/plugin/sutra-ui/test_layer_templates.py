"""The templates at every level (PRD amendment A3): the step, kind, engine and artifact templates, the user journey,
the levels and the ask forms, and the function template's constants -- each definition held against the shipped files
and against the runtime it describes.

A template is an interface is a base class: layer_schema.py holds the definitions, template_checks.py the rules a type
cannot say, and the files that conform are the children. Each test here is one rule of A3.1 (ST-1 to ST-9, K-1, E-1, AR-1,
AS-1, FT-1 ...), with a failing example where the rule has one. A test that meets a fault of the interface on purpose does
so inside S.expect_refused(); any other fault fails the test through the conftest fixture.
"""
import ast
import collections
import copy
import importlib
import json

import pytest

import layer_schema as S
import template_checks as T

HERE = S.HERE


# ---- the shipped files every level is held against -----------------------------------------------------------------
def _read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def _recipes():
    """Every recipe of every version of every layer, and every shipped engine template: (path, document)."""
    paths = sorted(HERE.glob("layers/*/v*.json")) + sorted(HERE.glob("engine-templates/*.json"))
    return [(p.relative_to(HERE).as_posix(), _read(p)) for p in paths]


def _steps_of(doc):
    """(group, step) for every gate, rule, step and handler step of a recipe or a template."""
    for group in ("gates", "rules", "steps"):
        for s in doc.get(group) or []:
            yield group, s
    for h in doc.get("on") or []:
        for s in h.get("steps") or []:
            yield "steps", s


def _all_steps():
    return [(p, g, s) for p, doc in _recipes() for g, s in _steps_of(doc)]


def _step(step_id):
    return next(copy.deepcopy((g, s)) for _, g, s in _all_steps() if s["id"] == step_id)


def _first_of(kind):
    return next(copy.deepcopy((g, s)) for _, g, s in _all_steps() if S.step_kind(s, g) == kind)


# ---- a department that has really run (the pattern of test_j2.py's fixture, copied) ----------------------------------
WEBSITE = "Build a website that teaches algebra to Class 8 students"


@pytest.fixture
def j2(tmp_path, monkeypatch):
    monkeypatch.setenv("SUTRA_NATIVE_DEPT_HOME", str(tmp_path / "departments"))
    monkeypatch.setenv("SUTRA_NATIVE_HOME", str(tmp_path / "registry"))
    monkeypatch.setenv("SUTRA_UI_PROPOSALS", str(tmp_path / "proposals"))
    monkeypatch.setenv("SUTRA_WEBSITE_OFFLINE", "1")
    monkeypatch.setenv("J1_FLOW_V1", "1")
    monkeypatch.setenv("J2_FLOW_V1", "1")
    monkeypatch.delenv("SUTRA_ENGINE_RUNTIME", raising=False)

    import website_dept as W
    import founding
    import placement_engine as E
    import org2_apply
    import engine_runtime as R
    import j2_runtime as J

    for module in (E, W, org2_apply, founding, R, J):
        importlib.reload(module)
    if not E.active_roots(E.load_domains()):
        E.mint_domain(None, "Sutra", ["Sutra"], "T-local", origin="operator-request")
    return W, R, J, founding


def _born(j2, words=WEBSITE, org="Acme Learning"):
    """A department as a person makes one: found the organisation, say the words, Root sets it up, and it runs to idle."""
    W, _, _, founding = j2
    root = founding.found_structure(org, owner="Sankalp")["root"]
    W.owner_ask(root, words)
    W.run_until_idle(root, limit=300)
    child = next(d for d in W.list_depts() if d.get("parent") == root)
    W.run_until_idle(child["ref"], limit=300)
    return child["ref"]


# ---- C1: the step (L4) ----------------------------------------------------------------------------------------------
def test_st1_every_step_of_every_recipe_and_template_fits_the_definition():
    steps = _all_steps()
    assert len(steps) >= 93, "the recipes and templates held 93 steps when this was written; a package adds steps, never drops one"
    bad = {"%s: %s" % (p, s.get("id")): T.step_faults(s, g) for p, g, s in steps if T.step_faults(s, g)}
    assert not bad, bad
    print("steps that fit DEFS['step']:", len(steps))


def test_st3_every_step_has_exactly_one_kind():
    steps = _all_steps()
    split = collections.Counter(S.step_kind(s, g) for _, g, s in steps)
    print("steps by kind:", dict(split), "of", len(steps))
    assert sum(split.values()) == len(steps), "every step is counted once, under one kind"
    assert set(split) <= set(S.STEP_KINDS)
    for _, g, s in steps:
        kind = S.step_kind(s, g)
        assert (g == "gates") == (kind == "gate") and (g == "rules") == (kind == "rule"), "%s: %s is held in %s" % (s["id"], kind, g)
        assert not (kind in ("ai", "person") and s.get("code")), "%s is by code and by an AI" % s["id"]
        assert kind != "person" or s.get("born") == "P"
    assert split["code"] and split["ai"] and split["gate"] and split["rule"], "each kind the recipes use has a step"


def test_st3_a_step_has_one_kind_by_its_group_its_rung_and_its_prompt():
    assert S.step_kind({"born": "C2", "code": "x"}) == "code"
    assert S.step_kind({"born": "C0", "prompt": "x"}) == "ai"
    assert S.step_kind({"born": "P", "prompt": "x", "by_hand": "y"}) == "person"
    assert S.step_kind({"born": "C2", "code": "x"}, "gates") == "gate" and S.step_kind({"born": "C2", "code": "x"}, "rules") == "rule"
    assert S.step_kind({"born": "C2", "code": "x", "prompt": "y"}, "gates") == "gate", "a gate that has gone soft is still a gate"
    with pytest.raises(ValueError, match="gates, rules or steps"):
        S.step_kind({}, "handlers")


def test_st4_each_kind_has_the_body_it_keeps():
    # every kind's real step passes, and a failing example for each kind says what it lacks
    for kind in S.STEP_KINDS:
        if kind == "person":
            continue                                   # none is born so: the example is built below
        group, step = _first_of(kind)
        assert T.step_faults(step, group) == [], (kind, step["id"])
    group, ai = _first_of("ai")
    no_draft = {k: v for k, v in ai.items() if k != "draft"}
    assert any("plain draft" in f for f in T.step_faults(no_draft, group)), "an AI step with no draft"
    no_out = {k: v for k, v in ai.items() if k != "out"}
    assert any("shape of its answer" in f for f in T.step_faults(no_out, group)), "an AI step with no shape of answer"
    assert any("C0 or C1" in f for f in T.step_faults(dict(ai, born="C2"), group)), "an AI step is born below code"
    group, code = _first_of("code")
    both = dict(code, prompt="adapt_shape")            # a code step with a prompt, born C2
    assert any("never both" in f for f in T.step_faults(both, group)), "a step by code and by an AI"
    assert any("born on code" in f for f in T.step_faults(dict(code, born="C1"), group)), "a code step is born C2"
    assert any("no draft" in f for f in T.step_faults(dict(code, draft="x_draft"), group)), "a code step has no draft"
    assert any("by_hand is for a step with a prompt" in f for f in T.step_faults(dict(code, by_hand="Do it."), group))
    person = dict(ai, born="P", by_hand="Say what the page should hold.")
    assert T.step_faults(person, group) == [], "a person step is born P with by_hand, a draft and the shape of its answer"
    no_hand = {k: v for k, v in person.items() if k != "by_hand"}
    assert any("by_hand" in f and "person step" in f for f in T.step_faults(no_hand, group)), "a person step with no by_hand"
    group, gate = _first_of("gate")
    no_code = {k: v for k, v in gate.items() if k != "code"}
    assert any("gate has its rule in code" in f for f in T.step_faults(no_code, "gates")), "a gate with no code"
    group, rule = _first_of("rule")
    assert any("rule has its rule in code" in f for f in T.step_faults({k: v for k, v in rule.items() if k != "code"}, "rules"))
    assert any("a rule is code only" in f for f in T.step_faults(dict(rule, prompt="x_prompt", draft="x_draft", out={"a": "str"}), "rules"))


def test_st1_a_step_with_an_unknown_field_is_refused():
    group, step = _first_of("code")
    got = T.step_faults(dict(step, colour="red"), group)
    assert got == ["$.colour: is not a field here"] == S.validate("step", dict(step, colour="red"))
    assert T.step_faults({k: v for k, v in step.items() if k != "check"}, group) == ["$.check: is missing"]
    assert T.step_faults("not a step") == ["$: is not an object"]
    assert S.validate("step", dict(step, born="C3")) == ["$.born: is not one of P, C0, C1, C2"]


def test_st2_every_property_is_classified():
    props = S.DEFS["step"]["properties"]
    assert len(props) == 23, "the twenty-three fields of A3.3: a new one is a decision for the law, classified in the same commit"
    unclassified = [k for k, v in props.items() if v.get("x-law") not in ("fixed", "free")]
    assert not unclassified, "classify %s in layer_schema.py DEFS['step']: fixed (the parent's value holds) or free (a child may change it)" % unclassified
    fixed, free = T.step_law()
    assert not set(fixed) & set(free) and set(fixed) | set(free) | {"id"} == set(props)
    assert "id" not in fixed + free, "id names the step; a child never changes it, and the lists of the law do not hold it"
    assert "may_end" in fixed and "side_by_side" in free, "the two fields A2-LAW's lists leave out (A2.12, rule 6)"


def test_st2_the_classification_equals_the_law():
    path = HERE / "layers" / "lineage.py"
    if not path.exists():
        reason = "layers/lineage.py does not exist on this main (A2-LAW has not merged): its STEP_FIXED and STEP_FREE are held to DEFS['step'] when it does"
        print("skipped:", reason)
        pytest.skip(reason)
    lineage = importlib.import_module("layers.lineage")
    fixed, free = T.step_law()
    for field in set(fixed) ^ set(lineage.STEP_FIXED):
        pytest.fail("%s is %s in layer_schema.py and %s in layers/lineage.py: make them agree (the definition is the source)"
                    % (field, "fixed" if field in fixed else "not fixed", "fixed" if field in lineage.STEP_FIXED else "not fixed"))
    for field in set(free) ^ set(lineage.STEP_FREE):
        pytest.fail("%s is %s in layer_schema.py and %s in layers/lineage.py: make them agree (the definition is the source)"
                    % (field, "free" if field in free else "not free", "free" if field in lineage.STEP_FREE else "not free"))
    assert set(lineage.STEP_FIELDS) == set(S.DEFS["step"]["properties"])


def _row_keys_the_runtime_writes():
    """The keys of every line of steps.jsonl, read from the three writers of engine_runtime (run_step, a gate's decision, the
    owner's mark): the dict literals they write, the keywords of run_step's end(...) and the keys it sets after."""
    tree = ast.parse((HERE / "engine_runtime.py").read_text(encoding="utf-8"))
    keys = set()

    def dict_keys(node):
        return {k.value for k in node.keys if isinstance(k, ast.Constant) and isinstance(k.value, str)}

    for fn in (n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name in ("run_step", "_gate_row", "_mark")):
        for node in ast.walk(fn):
            if isinstance(node, ast.Assign) and isinstance(node.value, ast.Dict) and any(isinstance(t, ast.Name) and t.id == "row" for t in node.targets):
                keys |= dict_keys(node.value)
            if isinstance(node, ast.Assign):
                keys |= {t.slice.value for t in node.targets if isinstance(t, ast.Subscript) and isinstance(t.value, ast.Name)
                         and t.value.id == "row" and isinstance(t.slice, ast.Constant)}
            if isinstance(node, ast.Call):
                name = node.func.id if isinstance(node.func, ast.Name) else None
                if name == "end":
                    keys |= {k.arg for k in node.keywords if k.arg}
                if name == "_append" and len(node.args) == 3 and isinstance(node.args[1], ast.Constant) \
                        and node.args[1].value == "steps.jsonl" and isinstance(node.args[2], ast.Dict):
                    keys |= dict_keys(node.args[2])
                if isinstance(node.func, ast.Attribute) and node.func.attr == "update" and isinstance(node.func.value, ast.Name) \
                        and node.func.value.id == "row" and node.args and isinstance(node.args[0], ast.Dict):
                    keys |= dict_keys(node.args[0])
    return keys


def test_constants_equal_the_runtimes():
    import engine_runtime as R
    import website_dept as W
    assert S.RUNGS == R.RUNGS and S.NATURES == R.NATURES and S.MODEL_TOOLS == W.MODEL_TOOLS
    assert S.GATE_ANSWERS == S.VERDICTS["identity"]["gate"] == S.VERDICTS["coordination"]["gate"]
    for answer in S.GATE_ANSWERS:                      # what a gate's covering accepts is what the interface names
        assert R.c_gate_answer_is_known(None, None, None, {"answer": answer})["ok"] is True, answer
        assert R.c_gate_verdict_is_known(None, None, None, {"verdict": answer})["ok"] is True, answer
    assert R.c_gate_answer_is_known(None, None, None, {"answer": "grant"})["ok"] is False
    assert set(S.STEP_KINDS) == {"code", "ai", "person", "gate", "rule"}
    written = _row_keys_the_runtime_writes()
    assert written == set(S.STEP_ROW), ("S.STEP_ROW and the writers of steps.jsonl differ: only in the interface %s, only in the runtime %s"
                                        % (sorted(set(S.STEP_ROW) - written), sorted(written - set(S.STEP_ROW))))
    assert len(S.STEP_ROW) == len(set(S.STEP_ROW))


def test_st8_a_row_a_run_wrote_fits_the_row_definition(j2):
    W, R, J, _ = j2
    ref = _born(j2)
    R._mark(ref, None, "the owner did not like this page")           # the owner's mark adds a row of its own
    rows = R.step_rows(ref)
    modes = collections.Counter(r.get("mode") for r in rows)
    print("rows by mode:", dict(modes))
    assert modes["slot"] and modes["gate"] and modes["mark"] == 1, modes
    bad = {r["id"]: S.validate("step.row", r) for r in rows if S.validate("step.row", r)}
    assert not bad, "a row a writer wrote does not fit DEFS['step.row']: widen the definition, never the writer: %s" % bad
    assert not [(r["id"], k) for r in rows for k in r if k not in S.STEP_ROW], "a row holds a key the interface does not name"
    assert {r["mode"] for r in rows} <= {"slot", "gate", "mark"}, "a rule is written as a slot row or a gate row, never as a mode of its own"
    assert next(r for r in rows if r["mode"] == "mark")["run"] is None
    # the definition refuses what no writer writes
    assert S.validate("step.row", {"id": "s-1", "engine": "Write", "step": "write.page"}) == ["$.status: is missing"]
    assert S.validate("step.row", dict(rows[0], mode="rule")) == ["$.mode: is not one of slot, gate, mark"]
    assert S.validate("step.row", dict(rows[0], engine=None)) != []


def test_ctx_keys_are_closed(j2, monkeypatch):
    W, R, J, _ = j2
    seen, original = collections.Counter(), R._resolve

    def recorder(ctx, kind, name, engine=None):
        seen.update((ctx or {}).keys())
        return original(ctx, kind, name, engine=engine)

    monkeypatch.setattr(R, "_resolve", recorder)
    _born(j2)
    assert seen, "the run resolved no step"
    outside = sorted(set(seen) - set(S.STEP_CTX))
    assert not outside, "a context was handed %s, which S.STEP_CTX does not name: add it to layer_schema.py STEP_CTX" % outside
    # set only on a path this offline run does not take: the tie of two functions that are ready at once sets ready, and the
    # fan-out item travels as the body's third argument on main, so no context carries it yet
    not_taken = {"ready": "the tie of two ready engines", "item": "the fan-out item is the body's third argument, not a context key"}
    unseen = set(S.STEP_CTX) - set(seen)
    assert unseen <= set(not_taken), "no context of the run held %s: drop it from S.STEP_CTX, or name the path that sets it here" % sorted(unseen - set(not_taken))
    print("context keys seen:", sorted(seen), "| not seen:", sorted(unseen))


def _starts():
    out = []
    for path, doc in _recipes():
        if doc.get("start"):
            out.append((path, doc["start"]))
    return out


def test_engine_start_fits():
    import engine_runtime as R
    starts = _starts()
    assert len(starts) >= 11, "five function recipes and six engine templates start"
    for path, start in starts:
        assert S.validate("engine.start", start) == [], path
    on_deliverable = sorted(p for p, st in starts if any(t.get("of") == "$deliverable" for t in st["on"]))
    assert [p.split("/")[1] for p in on_deliverable] == ["adaptation", "audit"], "Adaptation and Audit start on the department's deliverable"
    engines = R.defs()["engines"]
    for name, e in engines.items():
        assert R.start_faults(name, e, engines) == [], name
        assert S.validate("engine.start", e["start"]) == [], name
    # the same start through both laws: the definition is the shape, start_faults the law, and they agree on what they both say
    wrong = [{"on": [{"kind": "cron", "every_s": 60}]}, {"on": []}, {"unless": []}, {"on": [{"kind": "timer", "every_s": 0}]},
             {"on": [{"kind": "version", "of": "Brief"}], "when": "noon"}]
    for start in wrong:
        assert S.validate("engine.start", start) != [], start
    assert R.start_faults("X", {"start": wrong[0]}, {}) != [] and R.start_faults("X", {"start": wrong[1]}, {}) != []
    ok = {"on": [{"kind": "version", "of": "$deliverable"}]}
    assert S.validate("engine.start", ok) == [] and R.start_faults("X", {"start": ok}, {}) == []


# ---- C2: the kind, the engine and the artifact (L1, L3, L5) ------------------------------------------------------------
def _kinds():
    return _read(HERE / "engine_defs" / "website.json")["kinds"]


def _kind_faults_of_the_runtime(R, name, mutate):
    """What engine_runtime.validate says of the department kind `name` once `mutate` has changed a copy of it."""
    d = copy.deepcopy(R.defs())
    mutate(d["kinds"][name])
    return [f for f in R.validate(d) if f.startswith("kinds, %s:" % name)]


def test_k1_every_kind_fits_and_agrees_with_validate():
    import engine_runtime as R
    kinds = _kinds()
    assert sorted(kinds) == ["default", "organic", "root", "website"], "the four kinds of engine_defs/website.json"
    for name, kind in kinds.items():
        assert T.kind_faults(name, kind) == [], name
        assert _kind_faults_of_the_runtime(R, name, lambda k: None) == [], "validate says nothing against %s as it ships" % name
    # a kind with required outside its line: the definition's rule and the runtime's law refuse the same copy of a kind
    website = copy.deepcopy(kinds["website"])
    website["line"].remove("Check")
    mine = T.kind_faults("website", website)
    assert mine and "required names engines of its own line" in mine[0] and "Check is not in it" in mine[0], mine
    theirs = _kind_faults_of_the_runtime(R, "website", lambda k: k["line"].remove("Check"))
    assert any("required names engines of its own line" in f for f in theirs), theirs
    # and the same bad copy of a kind through both, field by field: what the shape law refuses, the definition law refuses too
    for what, mutate in (("no goal", lambda k: k.pop("goal")), ("no rules", lambda k: k.pop("rules")), ("no use case", lambda k: k.pop("use_case")),
                         ("no artifacts", lambda k: k.pop("artifacts")), ("no functions template", lambda k: k.pop("functions_template"))):
        bad = copy.deepcopy(kinds["website"])
        mutate(bad)
        assert T.kind_faults("website", bad) != [], what
        assert _kind_faults_of_the_runtime(R, "website", mutate) != [], what
    # a rule's tag is one of the four, and a kind names no field the template does not
    bad = copy.deepcopy(kinds["website"])
    bad["rules"][0]["tag"] = "maybe"
    assert any("$.rules[0].tag: is not one of go, ask, refuse, always" in f for f in T.kind_faults("website", bad))
    assert any("$.colour: is not a field here" in f for f in T.kind_faults("website", dict(kinds["website"], colour="red")))
    # the definition is the shape; whether the Library has the template a kind names is the runtime's to look up
    assert T.kind_faults("website", dict(kinds["website"], functions_template="nothing-like-it")) == []
    assert _kind_faults_of_the_runtime(R, "website", lambda k: k.update(functions_template="nothing-like-it")) != []
    assert T.kind_faults("website", "not a kind") == ["kinds, website: $: is not an object"]


def _engine_templates():
    return [(p.relative_to(HERE).as_posix(), _read(p)) for p in sorted(HERE.glob("engine-templates/*.json"))]


def test_e1_every_shipped_engine_template_fits():
    import engine_runtime as R
    shipped = _engine_templates()
    assert len(shipped) >= 6, "plan, write, check, publish, do and setup"
    for path, t in shipped:
        assert S.validate("engine.library", t) == [], path
        assert [S.validate("step", s) for s in t["steps"]] == [[]] * len(t["steps"]), path
    assert {t["name"] for _, t in shipped} <= set(R.engine_templates()), "the runtime loads every file the definition fits"
    # the definition refuses what a template must name
    name, t = shipped[0]
    for key in ("use_case", "start", "steps", "reads", "writes", "description", "id"):
        assert S.validate("engine.library", {k: v for k, v in t.items() if k != key}) == ["$.%s: is missing" % key], key
    assert S.validate("engine.library", dict(t, kind="function")) == ["$.kind: is not work"]
    assert S.validate("engine.library", dict(t, id="Engine/Plan")) != []
    assert S.validate("engine.library", dict(t, steps=[dict(t["steps"][0], colour="red")])) == ["$.steps[0].colour: is not a field here"]
    # open on purpose: Setup carries its own converse_instruction and clarification_questions
    setup = dict(next(t for _, t in shipped if t["name"] == "Setup"))
    assert "converse_instruction" in setup and S.validate("engine.library", setup) == []


def test_e1_engine_template_is_the_born_child(j2):
    """engine.template (A1.7) is the Library template with a required made_by: the engine Adaptation shaped on the owner's stamp."""
    import engine_runtime as R
    made_by = {"by": "Adaptation", "dept": "dref-acme0001", "at": "2026-10-26T09:00:00", "idea": None}
    for path, t in _engine_templates():
        born = dict(t, made_by=made_by)
        assert S.validate("engine.template", born) == [], "%s with a made_by fits engine.template" % path
        assert S.validate("engine.library", born) == [], "and still fits engine.library, which is open"
        assert S.validate("engine.template", t) == ["$.made_by: is missing"], "%s without a made_by does not fit engine.template" % path
        assert S.validate("engine.library", t) == [], "but fits engine.library"
    # a template Adaptation really births is both: the child of the base
    W, _, _, _ = j2
    R.born_template("Translate", {"does": "translates the pages", "use_case": "Translate the pages into Hindi", "reads": "Brief"}, "dref-acme0001")
    born = _read(R.user_templates_dir() / "translate.json")
    assert born["made_by"]["by"] == "Adaptation"
    assert S.validate("engine.template", born) == [] and S.validate("engine.library", born) == []
    assert all(T.step_faults(s) == [] for s in born["steps"]), "a born template's steps are steps of the step template"
    assert S.validate("engine.library", {k: v for k, v in born.items() if k != "made_by"}) == []


def test_e2_a_start_with_a_cron_trigger_is_refused():
    import engine_runtime as R
    _, t = _engine_templates()[0]
    cron = dict(t, start={"on": [{"kind": "cron", "every_s": 3600}]})
    assert S.validate("engine.library", cron) == ["$.start.on[0].kind: is not one of version, post, timer"]
    assert R.start_faults("Plan", cron, {}) == ["Plan, start: 'cron' is not a kind of trigger"], "the runtime refuses the same start"
    assert S.validate("engine.library", dict(t, start={"on": [], "unless": []})) == ["$.start.on: fewer than 1 items"]
    assert S.validate("engine.library", dict(t, start={"unless": []})) == ["$.start.on: is missing"]
    # a blocker is a gate: the shape names a gate's id, and start_faults looks the gate up
    engines = R.defs()["engines"]
    gates = {g["id"] for e in engines.values() for g in e.get("gates") or []}
    assert gates == {"identity.gate", "identity.wait_engine", "coord.chain", "priority.envelope"}
    for path, shipped in _engine_templates():
        assert set(shipped["start"].get("unless") or []) <= gates, path
    nowhere = dict(t["start"], unless=["identity.no_such_gate"])
    assert S.validate("engine.start", nowhere) == [] and R.start_faults("Plan", {"start": nowhere}, engines) != []


def _artifact_templates():
    return [(p.relative_to(HERE).as_posix(), _read(p)) for p in sorted(HERE.glob("artifact-templates/*.json"))]


def test_ar1_every_artifact_template_fits():
    import artifacts
    shipped = _artifact_templates()
    assert len(shipped) >= 10, "the Default, the website kind's five, Request, Department, Result and the app Human Sutra"
    for path, t in shipped:
        assert T.artifact_faults(t) == [], path
    assert any(t["kind"] == "app" for _, t in shipped), "the app template is one of them"
    assert S.DEFS["artifact.template"]["properties"]["kind"]["enum"] == list(artifacts.KINDS)
    assert {t["name"] for _, t in shipped} == set(artifacts.templates()), "the loader reads the files the definition fits"
    _, brief = next((p, t) for p, t in shipped if t["name"] == "Brief")
    assert S.validate("artifact.template", dict(brief, counts_after="later")) == ["$.counts_after: is not one of filing, stamp"]
    assert S.validate("artifact.template", dict(brief, id="brief")) != []
    assert S.validate("artifact.template", {k: v for k, v in brief.items() if k != "use_case"}) == ["$.use_case: is missing"]
    assert S.validate("artifact.template", dict(brief, kind="pdf")) != []
    _, app = next((p, t) for p, t in shipped if t["kind"] == "app")
    assert T.artifact_faults({k: v for k, v in app.items() if k != "screen"}) == ["Human Sutra: an app template names its screen, and this one names none"]
    assert T.artifact_faults(dict(app, reads=[])) == ["Human Sutra: an app template names its reads, and this one names none"]
    assert S.validate("artifact.template", dict(brief, form="a" * 61)) != [], "form is the key W2-CHECKS adds, bounded"
    assert S.validate("artifact.template", dict(brief, form="pages")) == []


def test_ar2_every_check_a_template_names_ships(monkeypatch):
    import artifacts
    import engine_runtime as R
    engines = set(R.defs()["engines"])
    for path, t in _artifact_templates():
        missing = [c for c in t.get("checks") or [] if c not in artifacts.CHECKS]
        assert not missing, "%s names %s, which artifacts.CHECKS does not ship" % (path, missing)
        assert set(t.get("operations") or []) <= engines, "%s: an operation is an engine" % path
    assert artifacts.faults(R.defs()) == []
    # a template that names a check that ships nowhere, and an operation that is no engine
    broken = copy.deepcopy(artifacts.templates())
    broken["Brief"]["checks"] = ["is_text", "reads_well"]
    broken["Brief"]["operations"] = ["Plan", "Daydream"]
    monkeypatch.setitem(artifacts._CACHE, "t", broken)
    got = artifacts.faults({})
    assert got == ["artifact Brief: no check named reads_well ships with the app"], got
    assert "Daydream" not in engines and not set(broken["Brief"]["operations"]) <= engines


def test_the_definitions_of_c2_take_their_samples():
    """The (good, bad) pair of each lives in test_fixtures/templates/samples.json, and test_layer_schema runs it."""
    samples = _read(HERE / "test_fixtures" / "templates" / "samples.json")
    for name in ("kind", "engine.library", "artifact.template"):
        good, bad = samples[name]
        assert S.validate(name, good) == [] and S.validate(name, bad) != [], name
