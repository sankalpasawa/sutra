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
    assert len(props) >= 23, "the twenty-three fields of A3.3 stay: a package adds a field, classified in the same commit, and drops none"
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


def test_st9_ids_are_unique_and_every_name_a_step_uses_is_registered():
    import engine_runtime as R
    import layers
    steps = _all_steps()
    ids = [s["id"] for _, _, s in steps]
    assert len(ids) == len(set(ids)), "a step id is used once across the engines: %s" % sorted(i for i in set(ids) if ids.count(i) > 1)
    have = {k: set(layers.names(k)) for k in layers.KINDS}
    registry = {"check": R.CHECK, "code": R.CODE, "prompt": R.PROMPT, "draft": R.DRAFT}
    for path, _, s in steps:
        for kind, registered in registry.items():
            name = s.get(kind)
            assert name is None or name in registered or name in have[kind], "%s: %s names the %s %s, which ships nowhere" % (path, s["id"], kind, name)
    # the failing example of ST-9, through the definition law: a check that ships nowhere, and an id used by two engines
    d = copy.deepcopy(R.defs())
    d["engines"]["Plan"]["steps"][0]["check"] = "reads_well"
    assert any("no check named reads_well ships with the app" in f for f in R.validate(d))
    d = copy.deepcopy(R.defs())
    d["engines"]["Write"]["steps"][0]["id"] = d["engines"]["Plan"]["steps"][0]["id"]
    assert any("the id is used by Plan too" in f for f in R.validate(d))
    # and the shape law has no registry in it: the same bad check is a step that fits the definition
    group, step = _first_of("code")
    assert T.step_faults(dict(step, check="reads_well"), group) == [], "the shape law reads no registry; the definition law does"


def _function_steps():
    """(layer, group, step) for every step of the recipes of the functions: layers/<layer>/v<N>.json, and Root's Setup engine, the
    one Library template a function owns (S.ENGINE_LAYER). The work engines (Plan, Write, Check, Do) are no function's."""
    out = []
    for path, doc in _recipes():
        layer = path.split("/")[1] if path.startswith("layers/") else S.ENGINE_LAYER.get(doc.get("name"))
        out += [(layer, g, s) for g, s in _steps_of(doc)] if layer else []
    return out


def test_st6_every_ai_step_of_a_function_has_a_part():
    """ST-6: a function's AI step takes its words from at least one prompt part of its layer (the part names it in read_by), and every
    read_by is a step of that layer's recipes. A step may be read by several parts (adapt.line, priority.bargain), never by none."""
    steps = _function_steps()
    ai = [(layer, s["id"]) for layer, g, s in steps if S.step_kind(s, g) == "ai"]
    print("AI steps of the functions:", len(ai), "of", len(steps), "steps")
    assert len(ai) >= 16 and {layer for layer, _ in ai} == set(S.PROMPTS), "every layer with a prompt has AI steps; a package adds, never drops"
    assert T.part_faults(S.PROMPTS, steps) == []
    readers = collections.Counter(sid for groups in S.PROMPTS.values() for parts in groups.values() for spec in parts.values()
                                  for sid in T.part_readers(spec))
    print("steps read by several parts:", sorted(sid for sid, n in readers.items() if n > 1))
    # the failing examples: an AI step with no part, a part read by a name that is no step, and a step of another layer's
    no_part = copy.deepcopy(S.PROMPTS)
    no_part["coordination"]["tie"]["tie"]["read_by"] = None
    assert T.part_faults(no_part, steps) == [
        "Coordination: the AI step coord.tie is read by no prompt part of Coordination, and a function's AI step takes its words from a part (S.PROMPTS)"]
    group, ai_step = _first_of("ai")
    new_step = dict(ai_step, id="coord.invented")
    assert any("the AI step coord.invented is read by no prompt part of Coordination" in f
               for f in T.part_faults(S.PROMPTS, steps + [("coordination", group, new_step)])), "a new AI step the interface does not read"
    no_step = copy.deepcopy(S.PROMPTS)
    no_step["coordination"]["tie"]["tie"]["read_by"] = ["coord.tie", "coord.nothing"]
    assert T.part_faults(no_step, steps) == ["Coordination: the part tie.tie is read by coord.nothing, which is no step of Coordination"]
    elsewhere = copy.deepcopy(S.PROMPTS)
    elsewhere["priority"]["bargain"]["line"]["read_by"] = "coord.tie"
    assert any("the part bargain.line is read by coord.tie, which is no step of Priority" in f for f in T.part_faults(elsewhere, steps))
    # several parts reading one step is allowed, and a step that is not an AI step needs no part
    twice = copy.deepcopy(S.PROMPTS)
    twice["coordination"]["tie"]["again"] = dict(twice["coordination"]["tie"]["tie"])
    assert T.part_faults(twice, steps) == []
    group, code_step = _first_of("code")
    assert T.part_faults(S.PROMPTS, steps + [("coordination", group, dict(code_step, id="coord.plain"))]) == []


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
    _, R, _, _ = j2
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
    _, R, _, _ = j2
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
    assert {"default", "organic", "root", "website"} <= set(kinds), "the four kinds of engine_defs/website.json"
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
    _, t = shipped[0]
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


# ---- C3: the user journey (L0) --------------------------------------------------------------------------------------
JOURNEYS = HERE / "test_fixtures" / "journeys"


def _journey(name="good", **change):
    doc = copy.deepcopy(_read(JOURNEYS / ("%s.json" % name)))
    doc.update(change)
    return doc


def _with_step(**change):
    doc = _journey()
    doc["steps"][0].update(change)
    return doc


def _faults_of(doc):
    return S.validate("journey", doc)


def test_journey_definition_accepts_the_good_one_and_refuses_each_bad_one():
    good, with_was = _journey("good"), _journey("good-with-was")
    assert len(good["steps"]) == 2 and len(good["edges"]) == 1, "the smallest journey: two steps and one edge"
    assert _faults_of(good) == [] and _faults_of(with_was) == [], "both fixtures fit"
    assert with_was["was"]["steps"][0]["n"] == "0a", "the earlier rows of a journey are kept as was, and step 0a is allowed there"
    # an unknown field: the template is closed, so it cannot grow by accident
    assert _faults_of(_journey(colour="red")) == ["$.colour: is not a field here"]
    assert _faults_of(_with_step(colour="red")) == ["$.steps[0].colour: is not a field here"]
    # a step number x1; and 0a, 4a and 10 are step numbers
    assert _faults_of(_with_step(n="x1")) == ["$.steps[0].n: does not match %s" % S.STEP_N]
    for n in ("0", "0a", "0b", "4a", "4e", "9", "10", "99"):
        assert _faults_of(_with_step(n=n)) == [], n
    for n in ("", "00", "4f", "100", "a1", "1.5", "0aa"):
        assert _faults_of(_with_step(n=n)) != [], n
    # a state word is never in a definition: the row's state is computed, so no field holds one
    assert _faults_of(_with_step(status="proven")) == ["$.steps[0].status: is not a field here"]
    assert _faults_of(_with_step(state="proven")) == ["$.steps[0].state: is not a field here"]
    assert _faults_of(_journey(state="proven")) == ["$.state: is not a field here"]
    assert _faults_of(_with_step(site_status="proven")) != [], "the site's own word for a row is one of the site's words, not a state"
    assert _faults_of(_with_step(site_status="wanted")) == []
    edge = _journey()
    edge["edges"][0]["state"] = "proven"
    assert _faults_of(edge) == ["$.edges[0].state: is not a field here"]
    # a bind kind cron
    bind = _with_step(binds=[{"kind": "cron"}])
    assert _faults_of(bind) == ["$.steps[0].binds[0].kind: is not one of act, step, event, api, ui, person"]
    # a missing lane
    assert _faults_of(_with_step(lane=None)) != []
    missing = _journey()
    del missing["steps"][0]["lane"]
    assert _faults_of(missing) == ["$.steps[0].lane: is missing"]
    # BL-2b is a backlog id and BL-b2 is not
    assert _faults_of(_with_step(backlog="BL-2b")) == [] and _faults_of(_with_step(backlog="BL-2")) == []
    assert _faults_of(_with_step(backlog="BL-b2")) == ["$.steps[0].backlog: fits none of its shapes (does not match %s)" % S.BACKLOG_ID]
    assert _faults_of(_with_step(backlog="BL-0")) != []
    # step 0a is allowed in a step and in the earlier rows
    assert _faults_of(_with_step(n="0a")) == []
    bad_was = _journey("good-with-was")
    bad_was["was"]["steps"][1]["n"] = "0z"
    assert _faults_of(bad_was) == ["$.was.steps[1].n: does not match %s" % S.STEP_N]
    # the rest of what a journey must name
    for key in ("schema_version", "id", "title", "kind", "goal", "lanes", "steps", "edges", "site_ids"):
        doc = _journey()
        del doc[key]
        assert _faults_of(doc) == ["$.%s: is missing" % key], key
    assert _faults_of(_journey(kind="screen")) != [] and _faults_of(_journey(id="J0")) != [] and _faults_of(_journey(id="J100")) != []
    edge = _journey()
    del edge["edges"][0]["trigger"]
    assert _faults_of(edge) == ["$.edges[0].trigger: is missing"]
    assert _faults_of(_journey(site_ids=["step:1", "step:1"])) == ["$.site_ids: holds an item twice"]
    assert _faults_of(_journey(bound_to="marketing")) != [] and _faults_of(_journey(bound_to="audit")) == []
    outcome = _journey()
    outcome["edges"][0]["outcome"]["kind"] = "cry"
    assert _faults_of(outcome) != []
    assert _faults_of(_with_step(tests=["test_j1.py"])) != [] and _faults_of(_with_step(tests=["js:test_website.js#W45"])) == []
    assert _faults_of(_with_step(tests=["test_a.py::Klass::test_b"])) == []
    assert _faults_of(_with_step(same_as="J1/step/3")) == [] and _faults_of(_with_step(same_as="J1/edge/J1.5")) == []
    assert _faults_of(_with_step(same_as="J1/step")) != []


def test_the_journey_grammars_take_the_ids_the_site_uses():
    import re
    take = {
        S.JOURNEY_ID: (["J1", "J7", "J12", "S2", "U1", "FI1", "FA3", "FP1", "FC2", "FAU1"], ["J0", "J", "FX1", "FAU", "F1", "j1", "J1a"]),
        S.EDGE_ID: (["J1.9", "J2.20", "FI1.1", "FAU1.3"], ["J2.0", "J2", "J2.a", "FX1.1", "S1.1"]),
        S.SUB_ID: (["J2.a", "J2.h"], ["J2.1", "J2.A", "J2a"]),
        S.LANE_ID: (["you", "engines", "the_one"], ["You", "1lane", "", "a" * 17]),
        S.SYMBOL: (["identity_file", "j2_runtime.note", "$deliverable", "WS"], ["a b", "a.b.c", "1x", ""]),
        S.STEP_REF: (["J2:6", "J3:4a", "J1:10"], ["J2", "J2:0", "J2:6f", "2:6"]),
        S.RULING_ID: (["S-08", "Q7", "MK-1", "D5", "A1-14", "A3-D10"], ["S", "X-1", "S-08888", "s-08"]),
        S.SAME_AS: (["J1/step/3", "J2/step/4a", "J1/edge/J1.5"], ["J1/step", "J1/edge/J1", "step/3", "J1/step/0"]),
    }
    for pattern, (yes, no) in take.items():
        for x in yes:
            assert re.search(pattern, x), "%s should take %r" % (pattern, x)
        for x in no:
            assert not re.search(pattern, x), "%s should refuse %r" % (pattern, x)


def _enum_words(schema):
    """Every value any enum or const of a definition names."""
    out = set()
    if isinstance(schema, dict):
        for key, value in schema.items():
            if key == "enum":
                out.update(v for v in value if isinstance(v, str))
            elif key == "const" and isinstance(value, str):
                out.add(value)
            else:
                out |= _enum_words(value)
    elif isinstance(schema, list):
        for value in schema:
            out |= _enum_words(value)
    return out


def test_the_journey_enums_are_the_site_s_words_and_a_state_is_never_a_definition_word():
    assert S.ROW_STATES == ("proven", "partly", "failing", "unproven", "wanted", "dropped", "fault")
    assert S.READ_STATES == S.ROW_STATES + ("unknown",) and S.JOURNEY_STATES == S.ROW_STATES + ("declared",)
    assert S.JOURNEY_KINDS == ("person", "system", "function") and S.DISPOSITIONS == ("keep", "change", "drop")
    # the states are computed (A3.6), so a definition's own enums never name one that is not also the site's word: wanted and
    # partly are the site's words too, and a journey's declared flag is a field, not a state it holds
    only_a_state = {"proven", "failing", "unproven", "fault", "dropped", "unknown"}
    for name in (n for n in S.DEFS if n.startswith("journey") and n not in ("journey.status", "journey.row_status")):
        held = _enum_words(S.DEFS[name]) & only_a_state
        assert not held, "%s names %s in an enum: a state is never in a definition" % (name, sorted(held))
    assert not set(S.SITE_STATUS) & only_a_state
    assert only_a_state <= _enum_words(S.DEFS["journey.row_status"]) | _enum_words(S.DEFS["journey.status"]), "the status document names them"


def test_journey_status_document_fits():
    sample = {"schema_version": 1, "id": "J9", "definitions_sha": "ab" * 32, "state": "partly",
              "counts": {"proven": 2, "partly": 1, "wanted": 0},
              "tests": {"test_engine_runtime.py::TestTheFiveJourneys::test_37_a_directive_is_restated_put_back_and_kept_only_on_a_stamp": "passed",
                        "test_layer_journey_j9.py::test_walk": "missing"},
              "rows": {"step:1": {"state": "proven", "proven_by": ["test_j1.py::test_a"], "failing": [], "site": "built", "drift": False},
                       "edge:J9.1": {"state": "wanted", "site": "wanted", "drift": False}},
              "drift": [{"row": "edge:J9.1", "site": "built", "state": "wanted"}]}
    assert S.validate("journey.status", sample) == []
    # one document for each journey, with its own id and its own hash
    for key in ("id", "definitions_sha", "state", "counts", "tests", "rows", "schema_version"):
        assert S.validate("journey.status", {k: v for k, v in sample.items() if k != key}) == ["$.%s: is missing" % key], key
    # an unknown state fails, in the journey, in a row and in the drift list
    assert S.validate("journey.status", dict(sample, state="great")) != []
    assert S.validate("journey.status", dict(sample, rows={"step:1": {"state": "great"}})) != []
    assert S.validate("journey.status", dict(sample, drift=[{"row": "step:1", "site": "built", "state": "great"}])) != []
    assert S.validate("journey.status", dict(sample, tests={"t.py::a": "skipped"})) != []
    assert S.validate("journey.status", dict(sample, colour="red")) == ["$.colour: is not a field here"]
    for state in S.JOURNEY_STATES + ("unknown",):
        assert S.validate("journey.status", dict(sample, state=state)) == [], state
    for state in S.READ_STATES + ("declared",):
        assert S.validate("journey.row_status", {"state": state}) == [], state


def _ledger_literals(source):
    """The dotted words a module writes on its ledger rows, by reading how it calls note(ref, step, actor, recipient, action,
    ...): that fifth argument, what its activity feed returns for a board act (_board_action), and the reason codes a note
    carries. Returns (actions, reason_codes, every_dotted_string_outside_a_docstring)."""
    import re
    tree = ast.parse(source)
    dotted = re.compile(r"^[a-z]+\.[a-z_]+$")
    docs = {id(n.body[0].value) for n in ast.walk(tree) if isinstance(n, (ast.Module, ast.FunctionDef, ast.ClassDef)) and n.body
            and isinstance(n.body[0], ast.Expr) and isinstance(getattr(n.body[0], "value", None), ast.Constant)}

    def strings(node):
        return [n.value for n in ast.walk(node) if isinstance(n, ast.Constant) and isinstance(n.value, str) and dotted.match(n.value)]

    actions, reasons = set(), set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "note" and len(node.args) >= 5:
            if isinstance(node.args[4], ast.Constant) and isinstance(node.args[4].value, str):
                actions.add(node.args[4].value)
            for kw in node.keywords:
                if kw.arg == "reason_codes":
                    reasons.update(strings(kw.value))
        if isinstance(node, ast.FunctionDef) and node.name == "_board_action":
            for ret in (n for n in ast.walk(node) if isinstance(n, ast.Return) and n.value is not None):
                actions.update(strings(ret.value))
    every = {n.value for n in ast.walk(tree) if isinstance(n, ast.Constant) and isinstance(n.value, str)
             and dotted.match(n.value) and id(n) not in docs}
    return actions, reasons, every


def _ledger_gap(actions, reasons, every, listed):
    """The differences between what a module writes and what the interface names, as sentences that name the action and say
    which side to edit."""
    written = set(actions) | set(reasons)
    out = ["j2_runtime.py writes the ledger action %s and S.LEDGER_ACTIONS does not name it: add it to LEDGER_ACTIONS in layer_schema.py, "
           "in the same commit" % a for a in sorted(written - set(listed))]
    out += ["S.LEDGER_ACTIONS names %s and j2_runtime.py never writes it: drop it from LEDGER_ACTIONS in layer_schema.py, or restore the "
            "write in j2_runtime.py" % a for a in sorted(set(listed) - set(every))]
    out += ["j2_runtime.py holds the word %s, which is neither an action nor a reason code this test reads: pass it to note() or to its "
            "reason_codes, or take it out of the dotted words" % a for a in sorted(set(every) - written)]
    return out


def test_ledger_actions_equal_the_ledger_literals():
    actions, reasons, every = _ledger_literals((HERE / "j2_runtime.py").read_text(encoding="utf-8"))
    assert actions and "run.failed" in actions and "check.failed" in reasons, "the scan read note(...) and its reason codes"
    gap = _ledger_gap(actions, reasons, every, S.LEDGER_ACTIONS)
    assert not gap, "\n".join(gap)
    assert len(set(S.LEDGER_ACTIONS)) == len(S.LEDGER_ACTIONS) and all("." in a for a in S.LEDGER_ACTIONS)
    assert set(S.LEDGER_ACTIONS) == set(every), "the interface's list is j2_runtime's dotted words, no more and no less"


def test_the_ledger_scan_reports_both_sides_and_names_the_action():
    source = ('def note(ref, step, actor, recipient, action, state, summary, key, payload=None, **more):\n    pass\n'
              'def _board_action(row):\n    return "proposal.created" if row else "ask.created"\n'
              'def go(ref):\n    "the docstring says a.b and nothing else"\n'
              '    note(ref, 1, "A", "B", "run.started", "x", "s", "k")\n'
              '    note(ref, 1, "A", "B", "run.failed", "x", "s", "k", reason_codes=["check.failed"])\n'
              '    note(ref, 1, "A", "B", "run.vanished", "x", "s", "k")\n')
    actions, reasons, every = _ledger_literals(source)
    assert actions == {"run.started", "run.failed", "run.vanished", "proposal.created", "ask.created"} and reasons == {"check.failed"}
    gap = _ledger_gap(actions, reasons, every, ["run.started", "run.failed", "proposal.created", "ask.created", "check.failed", "run.gone"])
    assert any("run.vanished" in g and "add it to LEDGER_ACTIONS" in g for g in gap), gap
    assert any("run.gone" in g and "drop it from LEDGER_ACTIONS" in g for g in gap), gap
    assert len(gap) == 2, gap
    assert "a.b" not in every, "a docstring is not a ledger word"


def test_recognitions_are_identitys_five():
    import engine_runtime as R
    assert S.RECOGNITIONS == ("task", "query", "directive", "feedback", "new-idea") == S.VERDICTS["identity"]["journey"]
    assert tuple(_read(HERE / "engine_defs" / "website.json")["journeys"]) == S.RECOGNITIONS, "the key `journeys` is not renamed"
    assert set(R.JOURNEYS) == set(S.RECOGNITIONS)
    for word in S.RECOGNITIONS:
        assert R.c_journey_is_known(None, None, None, {"journey": word})["ok"] is True, word
    assert R.c_journey_is_known(None, None, None, {"journey": "J1"})["ok"] is False, "a user journey is not a recognition"
    assert not set(S.RECOGNITIONS) & set(S.JOURNEY_KINDS)


# ---- C4: the levels, the ask forms, the generated schemas ------------------------------------------------------------------
def test_every_level_names_a_base_that_exists(monkeypatch):
    assert T.levels_faults() == []
    levels = S.TEMPLATE_LEVELS
    assert [l["level"] for l in levels] == ["L%d" % i for i in range(7)]
    assert [l["name"] for l in levels] == ["user journey", "department kind", "function", "engine and workflow", "step", "artifact", "ask"]
    for l in levels:
        assert l["base"] in S.DEFS or isinstance(getattr(S, l["base"], None), (dict, tuple)), "%s: %s" % (l["level"], l["base"])
        assert set(l) == {"level", "name", "base", "children", "keeps", "rules"} and l["keeps"].endswith(".")
    assert {l["base"] for l in levels if l["base"] in S.DEFS} == {"journey", "kind", "engine.library", "step", "artifact.template", "identity.ask"}
    # the failing examples: a base that is nothing, a level missing, a rule held twice, a part left out
    def broken(change):
        monkeypatch.setattr(S, "TEMPLATE_LEVELS", change)
        return T.levels_faults()
    assert broken(tuple(dict(l, base="nothing_at_all") if l["level"] == "L4" else l for l in levels)) == [
        "level L4 (step) names the base nothing_at_all, which is neither a definition nor a table of the interface"]
    assert broken(levels[:6])[0].startswith("the levels are L0 to L6, once each and in that order")
    twice = broken(tuple(dict(l, rules=l["rules"] + ("K-1",)) if l["level"] == "L5" else l for l in levels))
    assert twice == ["the rule K-1 is held by L1 and by L5: a rule belongs to one level"]
    assert broken(tuple(dict(l, rules=("X-1",)) if l["level"] == "L6" else l for l in levels)) == [
        "level L6 (ask) names the rule X-1, which is not spelled as the rules of A3.1 are"]
    assert broken(tuple({k: v for k, v in l.items() if k != "keeps"} if l["level"] == "L2" else l for l in levels)) == ["level L2 (function) names no keeps"]
    assert broken(tuple(dict(l, colour="red") if l["level"] == "L0" else l for l in levels))[0].startswith("level L0 (user journey) holds colour")


def test_every_rule_of_a_level_is_a_rule_of_the_a3_document():
    import re
    doc = HERE / "design" / "PRD-FIVE-FUNCTIONS-A3.md"
    if not doc.exists():
        pytest.skip("the A3 document is not in this tree")
    text = doc.read_text(encoding="utf-8")
    ids = [r for l in S.TEMPLATE_LEVELS for r in l["rules"]]
    assert len(ids) == len(set(ids)) == 12 + 2 + 10 + 4 + 9 + 2 + 2
    missing = [r for r in ids if not re.search(r"^\| %s \|" % re.escape(r), text, re.M)]
    assert not missing, "A3 lists no rule %s: the table of levels and the document must name the same rules" % missing
    listed = set(re.findall(r"^\| ((?:JC|K|FT|E|ST|AR|AS)-[1-9][0-9]?) \|", text, re.M))
    assert listed == set(ids), "the document lists rules the table does not: %s" % sorted(listed ^ set(ids))


def test_as1_every_ask_kind_has_a_form_and_its_options_are_known():
    forms = S.ASK_FORMS
    print("ask kinds:", len(S.ASK_KINDS))
    assert set(forms) == set(S.ASK_KINDS) and list(forms) == list(S.ASK_KINDS), "every kind of ask has a form, and only those"
    for kind, form in forms.items():
        assert set(form) == {"by", "options", "lead"}, kind
        assert form["by"] == "identity", "%s: only Identity speaks to the owner, so it files every ask" % kind
        assert len(set(form["options"])) == len(form["options"]) and set(form["options"]) <= set(S.OPTION_KINDS), \
            "%s: a way out the interface does not name" % kind
        assert form["lead"] is None or (isinstance(form["lead"], str) and form["lead"] and "\n" not in form["lead"]), kind
    assert forms["blocked"]["options"] == ("words", "leave", "stop")
    assert set(forms["conflict"]["options"]) >= {"words", "leave", "stop", "raise"} and forms["envelope"]["options"] == ("raise", "leave", "stop")
    assert {k for k, f in forms.items() if f["options"]} == {"blocked", "conflict", "envelope"}, "the rest are stamped yes or no"
    assert {k: f["lead"] for k, f in forms.items() if f["lead"]} == {
        "publish": "Publish: go live for the first time", "rule": "A rule, as understood", "request": "Your words reach outside the site"}
    # a lead is the writer's own first words: it stands in the source of the code that says it
    sources = {"publish": "website_dept.py", "rule": "engine_runtime.py", "request": "engine_runtime.py"}
    for kind, name in sources.items():
        assert forms[kind]["lead"] in (HERE / name).read_text(encoding="utf-8"), "%s: the lead is not in %s" % (kind, name)


def test_as1_the_forms_hold_what_the_writers_attach(j2):
    """Widen the table to what a writer attaches, never narrow a writer: the ways out each writer on main builds are in the form
    of the ask it files."""
    W, R, _, _ = j2
    ref = _born(j2)
    d = copy.deepcopy(W.dept(ref))
    d["done_items"] = [{"id": "D1", "text": "Every page is live", "how": "model", "level": "outcome"},
                       {"id": "D2", "text": "The phone number is shown", "how": "model", "level": "outcome"}]
    ask = R._blocked(ref, d, {"src": W.dept(ref)["name"]}, "Write cannot run: the plan has no pages.", "The plan is blocked.", "Identity", "no pages, D2")
    assert ask["kind"] == "blocked" and len(ask["options"]) == 3
    assert [o["kind"] for o in ask["options"]] == ["words", "leave", "stop"], "the plan's card: change it in my words, leave an item out, stop"
    assert {o["kind"] for o in ask["options"]} <= set(S.ASK_FORMS["blocked"]["options"])
    assert T.ask_faults(ask) == [] and T.ask_faults(next(a for a in W.asks(ref) if a["id"] == ask["id"])) == [], "AS-2: the plan's card fits its form"
    with pytest.raises(ValueError, match="takes one of its options"):
        W.decide_ask(ref, ask["id"], True)                   # an ask with options is answered by choosing one, never stamped
    import layers.adaptation.v1 as A
    cannot = {"engine": "Write", "items": ["D2"], "why": "it has no way to show a phone number"}
    kinds = [o["kind"] for o in A.cannot_options(d, cannot, "a site")]
    assert kinds == ["root_setup", "leave", "stop"] and set(kinds) <= set(S.ASK_FORMS["conflict"]["options"])
    card = W.options_ask("conflict", "Adaptation and Priority do not agree on the plan.", A.cannot_options(d, cannot, "a site"))
    assert T.ask_faults(card) == [], "AS-2: the conflict card Adaptation's options make fits its form"
    # every ask a writer builds with options_ask is cut to OPTIONS_MAX, and each option's kind is the part of its id before ':'
    five = [{"id": "words", "label": "a", "cost": "b"}, {"id": "leave:D1", "label": "c", "cost": "d"}, {"id": "stop", "label": "e", "cost": "f"},
            {"id": "raise", "label": "g", "cost": "h"}, {"id": "root_setup", "label": "i", "cost": "j"}]
    built = W.options_ask("conflict", "x", five)
    assert len(built["options"]) == S.OPTIONS_MAX == W.OPTIONS_MAX == 3 and [o["kind"] for o in built["options"]] == ["words", "leave", "stop"]
    assert all(S.validate("option", o) == [] for o in built["options"])
    assert T.ask_faults(built) == [], "AS-2: the conflict card cut to OPTIONS_MAX fits its form"


def test_as1_a_fourth_option_is_refused():
    option = {"id": "stop", "label": "Stop here", "cost": "the department stops where it is", "kind": "stop"}
    ask = {"id": "a-1", "kind": "blocked", "status": "pending", "text": "Write cannot run.", "options": [option] * S.OPTIONS_MAX}
    assert S.validate("identity.ask", ask) == []
    assert S.validate("identity.ask", dict(ask, options=[option] * (S.OPTIONS_MAX + 1))) == ["$.options: more than %d items" % S.OPTIONS_MAX]
    assert S.validate("identity.ask", dict(ask, kind="colour")) != [] and S.validate("identity.ask", dict(ask, status="maybe")) != []
    assert S.validate("identity.ask", dict(ask, options=[dict(option, kind="teleport")])) != [], "an option is of a known kind"
    # no form offers more kinds of way out than there are kinds, and an ask carries three of them at most
    assert all(len(f["options"]) <= len(S.OPTION_KINDS) for f in S.ASK_FORMS.values())


def _way(kind):
    """One way out of an ask, of the given kind, as website_dept.option builds it."""
    return {"id": kind, "label": "A way out", "cost": "what it costs", "kind": kind}


def _ask(kind, *kinds):
    return {"id": "a-1", "kind": kind, "status": "pending", "text": "An ask the owner answers.", "options": [_way(k) for k in kinds]}


def test_as2_an_ask_offers_only_the_ways_out_its_form_names():
    """AS-2 on the form: ask_faults reads S.ASK_FORMS[kind]['options'], which nothing else checks an ask against. For every kind of
    ask and every kind of way out the interface names, the ask fits exactly when its form names that way out."""
    for kind, form in S.ASK_FORMS.items():
        assert T.ask_faults(_ask(kind)) == [], "%s: an ask with no way out is stamped yes or no, and fits every form" % kind
        for way in S.OPTION_KINDS:
            got = T.ask_faults(_ask(kind, way))
            if way in form["options"]:
                assert got == [], (kind, way)
            else:
                assert len(got) == 1 and ("offers %s" % way) in got[0] and kind in got[0], (kind, way, got)
    # the failing examples, in the words the owner's side of the code would read
    assert T.ask_faults(_ask("rule", "raise")) == ["a-1: a rule ask is stamped yes or no and offers no way out, and this one offers raise"]
    assert T.ask_faults(_ask("blocked", "raise")) == ["a-1: a blocked ask offers only words, leave, stop, and this one offers raise"]
    assert T.ask_faults(_ask("envelope", "words", "raise", "root_setup")) == [
        "a-1: an envelope ask offers only raise, leave, stop, and this one offers words, root_setup"]
    # a way out whose kind is only in its id is read as website_dept.option reads it
    way = {"id": "raise:more", "label": "A way out", "cost": "what it costs"}
    assert T.ask_faults(dict(_ask("rule"), options=[way])) != [] and T.ask_faults(dict(_ask("envelope"), options=[way])) == []
    # a fourth option is the shape law's fault, and the form adds nothing to it
    assert T.ask_faults(_ask("blocked", "words", "leave", "stop", "stop")) == ["$.options: more than %d items" % S.OPTIONS_MAX]
    assert T.ask_faults(_ask("conflict", "words", "leave", "stop")) == []
    # an ask of a kind with no form, an option of a kind nothing names and a row that is no ask are the shape law's, said once
    assert len(T.ask_faults(_ask("colour", "raise"))) == 1 and T.ask_faults(_ask("colour", "raise"))[0].startswith("$.kind: is not one of")
    assert len(T.ask_faults(_ask("blocked", "teleport"))) >= 1 and not any("offers" in f for f in T.ask_faults(_ask("blocked", "teleport")))
    assert T.ask_faults("not an ask") == ["$: is not an object"]


def test_as2_every_ask_a_run_files_fits_its_form(j2):
    """AS-2 on departments that have really run: the offline run files the first publish; the owner's words then file a rule, a
    request that reaches outside the site, and (with Write's envelope spent) Priority's envelope ask. Every ask any department
    holds fits identity.ask and the form of its kind, so the table is held against more kinds than the one a plain run files."""
    W, R, _, _ = j2
    ref = _born(j2)
    d = copy.deepcopy(W.dept(ref))
    d["envelopes"] = dict(d.get("envelopes") or {}, Write={"calls": 0, "usd": 0.0})
    W.save_dept(ref, d)
    for words in ("Add a page about fractions for Class 8 students", "Never state a number the brief does not give",
                  "Email every new student a welcome note"):
        W.owner_ask(ref, words)
        W.run_until_idle(ref, limit=300)
    filed = [a for dept in W.list_depts() for a in W.asks(dept["ref"])]
    kinds = collections.Counter(a["kind"] for a in filed)
    print("asks a run filed, by kind:", dict(kinds))
    assert {"publish", "rule", "request", "envelope"} <= set(kinds), "the run files more than the first publish: %s" % dict(kinds)
    bad = {"%s (%s)" % (a["id"], a["kind"]): T.ask_faults(a) for a in filed if T.ask_faults(a)}
    assert not bad, bad
    # and the same ask, given a way out its kind does not offer, is refused by the same check
    rule = next(a for a in filed if a["kind"] == "rule")
    assert T.ask_faults(dict(rule, options=[_way("raise")])) == [
        "%s: a rule ask is stamped yes or no and offers no way out, and this one offers raise" % rule["id"]]
    envelope = next(a for a in filed if a["kind"] == "envelope")
    assert T.ask_faults(dict(envelope, options=[_way("raise"), _way("leave"), _way("stop"), _way("raise")])) == ["$.options: more than 3 items"]


def test_the_generated_files_equal_json_schemas():
    got = S.json_schemas()
    for name in ("templates.schema.json", "journeys.schema.json"):
        assert name in got, name
        assert (S.SCHEMA_FOLDER / name).read_text(encoding="utf-8") == S._dump(got[name]), \
            "%s differs from layer_schema.py: run `python layer_schema.py --write`" % name
    templates, journeys = got["templates.schema.json"], got["journeys.schema.json"]
    assert {"step", "step.row", "engine.start", "engine.library", "kind", "artifact.template"} <= set(templates["$defs"])
    assert templates["x-levels"] == json.loads(json.dumps(S.TEMPLATE_LEVELS)) and templates["x-ask-forms"] == json.loads(json.dumps(S.ASK_FORMS))
    assert templates["x-steps"]["ctx"] == list(S.STEP_CTX) and templates["x-steps"]["row"] == list(S.STEP_ROW)
    assert {n for n in S.DEFS if n == "journey" or n.startswith("journey.")} == set(journeys["$defs"]), "every journey.* definition, and no other"
    assert journeys["$ref"] == "#/$defs/journey" and journeys["x-ledger-actions"] == list(S.LEDGER_ACTIONS)
    assert journeys["x-recognitions"] == list(S.RECOGNITIONS)
    # a definition changed and not written fails the check, as for every other file
    on_disk = (S.SCHEMA_FOLDER / "templates.schema.json").read_text(encoding="utf-8")
    assert json.loads(on_disk)["$defs"]["step"]["properties"]["may_end"]["x-law"] == "fixed", "the law is in the file"
    assert S.faults(json.loads(on_disk)["$defs"]["step"], {"id": "a.b", "name": "x", "nature": "make", "born": "C0", "check": "c"}) == []


def test_describe_carries_the_a3_tables():
    got = S.describe()
    assert json.loads(json.dumps(got)) == got
    assert got["template_levels"] == json.loads(json.dumps(S.TEMPLATE_LEVELS)) and len(got["template_levels"]) == 7
    assert got["ask_forms"] == json.loads(json.dumps(S.ASK_FORMS)) and set(got["ask_forms"]) == set(S.ASK_KINDS)
    assert got["ledger_actions"] == list(S.LEDGER_ACTIONS) and got["recognitions"] == list(S.RECOGNITIONS)
    assert got["steps"] == {"kinds": list(S.STEP_KINDS), "natures": list(S.NATURES), "rungs": list(S.RUNGS), "gate_answers": list(S.GATE_ANSWERS),
                            "model_tools": list(S.MODEL_TOOLS), "ctx": list(S.STEP_CTX), "row": list(S.STEP_ROW)}
    assert {"step", "step.row", "engine.start", "engine.library", "kind", "artifact.template", "journey", "journey.status"} <= set(got["defs"])
    interface = json.loads((S.SCHEMA_FOLDER / "interface.v1.json").read_text(encoding="utf-8"))
    assert interface["template_levels"] == got["template_levels"] and interface["ask_forms"] == got["ask_forms"]


def test_the_readme_has_the_a3_rows():
    readme = (S.SCHEMA_FOLDER / "README.md").read_text(encoding="utf-8")
    for level in ("L0 User journey", "L1 Department kind", "L2 Function", "L3 Engine and workflow", "L4 Step", "L5 Artifact", "L6 Ask"):
        assert "| %s |" % level in readme, level
    for name in ("templates.schema.json", "journeys.schema.json", "TEMPLATE_LEVELS", "ASK_FORMS", "LEDGER_ACTIONS", "template_checks.py"):
        assert name in readme, name


# ---- C5: the function template's constants (L2) ----------------------------------------------------------------------------
import re  # noqa: E402


def _strings_of(value):
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for v in value.values():
            yield from _strings_of(v)
    elif isinstance(value, (list, tuple)):
        for v in value:
            yield from _strings_of(v)


def _agent_words():
    """Every constant of the function template, as the agent reads it."""
    out = []
    for layer, entry in S.FUNCTION_TEMPLATE.items():
        out += [("%s %s" % (layer, k), x) for k, v in entry.items() if k not in ("in_card",) for x in _strings_of(v)]
    return out + [("agreement %d" % i, line) for i, line in enumerate(S.DEPARTMENT_AGREEMENT, 1)]


def test_ft1_every_function_has_a_sound_template_entry():
    assert set(S.FUNCTION_TEMPLATE) == set(S.FUNCTION_LAYERS) | {"root"}, "every function layer, and Root"
    for layer, entry in S.FUNCTION_TEMPLATE.items():
        assert T.function_template_faults(layer, entry) == [], layer
        assert len(entry["role"]) <= 80 and len(entry["is_not"]) <= 600 and len(entry["hands_on"]) <= 400, layer
        assert 3 <= len(entry["never"]) <= 10 and all(0 < len(x) <= 160 for x in entry["never"]), layer
        assert isinstance(entry["in_card"], bool)
    assert S.FUNCTION_TEMPLATE["root"]["in_card"] is False, "Root's Setup prompts use no card: its template is interface-only"
    assert all(S.FUNCTION_TEMPLATE[l]["in_card"] is True for l in S.FUNCTION_LAYERS)
    assert set(S.FUNCTION_TEMPLATE["root"]) == {"role", "is_not", "never", "hands_on", "in_card"}, "no role words for Root"
    assert "reserved" in S.FUNCTION_TEMPLATE["adaptation"] and not [l for l in S.FUNCTION_LAYERS if l != "adaptation" and "reserved" in S.FUNCTION_TEMPLATE[l]]
    # the failing examples of FT-1
    audit = S.FUNCTION_TEMPLATE["audit"]
    assert T.function_template_faults("audit", {k: v for k, v in audit.items() if k != "never"}) == ["Audit: the template names no never"]
    assert T.function_template_faults("audit", dict(audit, never=audit["never"][:2])) == ["Audit: never holds three to ten lines, and this holds 2"]
    assert T.function_template_faults("audit", dict(audit, never=audit["never"] + ("x",) * 8)) == ["Audit: never holds three to ten lines, and this holds 11"]
    assert T.function_template_faults("audit", dict(audit, role="x" * 81)) == ["Audit: role is 81 characters, and the limit is 80"]
    assert T.function_template_faults("audit", dict(audit, is_not="x" * 601)) == ["Audit: is_not is 601 characters, and the limit is 600"]
    assert T.function_template_faults("audit", dict(audit, hands_on="x" * 401)) == ["Audit: hands_on is 401 characters, and the limit is 400"]
    assert T.function_template_faults("audit", dict(audit, never=("a b c", "x" * 161, "d e f")))[0].startswith("Audit: never line 2")
    assert T.function_template_faults("audit", dict(audit, colour="red")) == ["Audit: colour is not a part of the function template"]
    assert T.function_template_faults("priority", dict(S.FUNCTION_TEMPLATE["priority"], reserved=("learn",))) == [
        "Priority: reserved is not a part of the function template"]
    assert T.function_template_faults("audit", None) == ["Audit has no entry in the function template"]


def test_the_constants_are_the_text_of_the_a3_document():
    """The words are A3.4.5's, character for character: a change to a constant is a change to the document, and the reverse."""
    import ast
    doc = HERE / "design" / "PRD-FIVE-FUNCTIONS-A3.md"
    if not doc.exists():
        pytest.skip("the A3 document is not in this tree")
    text = doc.read_text(encoding="utf-8")
    found = {}
    for block in re.findall(r"```python\n(.*?)```", text, re.S):
        for m in re.finditer(r"^FUNCTION_TEMPLATE\['(\w+)'\] = (\{.*?^\})", block, re.S | re.M):
            found[m.group(1)] = ast.literal_eval(re.sub(r"#[^\n]*", "", m.group(2)))
    assert set(found) == set(S.FUNCTION_LAYERS), sorted(found)
    for layer, entry in found.items():
        assert dict(entry, never=tuple(entry["never"])) == S.FUNCTION_TEMPLATE[layer], "%s differs from A3.4.5" % layer
    agreement = re.search(r"^DEPARTMENT_AGREEMENT = \((.*?)^\)", text, re.S | re.M)
    assert tuple(ast.literal_eval("(" + re.sub(r"#[^\n]*", "", agreement.group(1)) + ")")) == S.DEPARTMENT_AGREEMENT
    assert "ROLE_INPUTS = %r" % (S.ROLE_INPUTS,) in text.replace("  # the inputs of goal.role_block", "")
    assert "ROLE_BLOCK_MAX = %d" % S.ROLE_BLOCK_MAX in text and S.TEMPLATE_BANNED in text and S.TEMPLATE_BANNED_AGENT in text


def test_the_agreement_is_sound():
    assert T.agreement_faults(S.DEPARTMENT_AGREEMENT) == []
    assert 4 <= len(S.DEPARTMENT_AGREEMENT) <= 8 and all(0 < len(x) <= 200 and "\n" not in x for x in S.DEPARTMENT_AGREEMENT)
    assert len(S.DEPARTMENT_AGREEMENT) == 6, "team.md's working rules that the interface cannot say, in six lines"
    # the first line is true of Identity too: the one function that speaks to the owner is not told to tell Identity
    assert S.DEPARTMENT_AGREEMENT[0].startswith("Only Identity speaks to the owner")
    assert T.agreement_faults(S.DEPARTMENT_AGREEMENT[:3]) == ["the working agreement holds four to eight lines, and this holds 3"]
    assert T.agreement_faults(S.DEPARTMENT_AGREEMENT[:5] + ("x" * 201,))[0].startswith("agreement line 6")
    assert T.agreement_faults(("Be kind.",) + S.DEPARTMENT_AGREEMENT[1:]) == [
        "the first line of the working agreement says that only Identity speaks to the owner"]
    assert S.ROLE_INPUTS == ("agreement", "is", "is_not", "may", "never", "procedure", "patterns", "hands_on") and len(S.ROLE_INPUTS) == 8
    assert S.ROLE_INPUTS[-1] == "hands_on" and S.ROLE_BLOCK_MAX == 3600


def test_no_constant_says_a_banned_word():
    for where, line in _agent_words():
        assert not re.search(S.TEMPLATE_BANNED_AGENT, line, re.I), "%s says a banned word: %s" % (where, line)
    # the agent's list is the shorter one: the contract's own words (accept, counter, reject; go, ask, refuse) sit beside an answer
    # shape, so only the screen, which the owner reads, bans them
    assert re.search(S.TEMPLATE_BANNED, "Priority will counter or refuse", re.I)
    assert not re.search(S.TEMPLATE_BANNED_AGENT, "Priority will counter or refuse", re.I)
    for bad in ("the charter", "Charters", "ask the CEO", "the Requester", "an internal system", "Internal Systems"):
        assert re.search(S.TEMPLATE_BANNED_AGENT, bad, re.I), bad
        assert re.search(S.TEMPLATE_BANNED, bad, re.I), bad
    for fine in ("the owner", "chartered flights", "a ceiling", "the requested page", "an internal clock"):
        assert not re.search(S.TEMPLATE_BANNED_AGENT, fine, re.I), fine
    # what the owner may read: the table of levels, and the lead of an ask, keep the screen's list
    owner_reads = [l["keeps"] for l in S.TEMPLATE_LEVELS] + [f["lead"] for f in S.ASK_FORMS.values() if f["lead"]]
    for line in owner_reads:
        assert not re.search(S.TEMPLATE_BANNED, line, re.I), line


def test_priority_says_nothing_about_ordering():
    """S-05: Priority prices and holds the budget; who goes first is Coordination's. No word of Priority's template says it orders."""
    pattern = S.TEMPLATE_NEVER_SAY["priority"]
    for where, line in [w for w in _agent_words() if w[0].startswith("priority ")]:
        assert not re.search(pattern, line, re.I), "%s says Priority orders: %s" % (where, line)
    assert re.search(pattern, "It decides the order of the queue", re.I) and re.search(pattern, "it says what runs next", re.I)
    # Coordination's words may say order: it is Coordination's
    assert any(re.search(pattern, x, re.I) for x in _strings_of(S.FUNCTION_TEMPLATE["coordination"]))
    assert "say which accepted workflow runs first" in S.FUNCTION_TEMPLATE["priority"]["never"]


def test_hands_on_names_only_actors_the_layer_sends_to():
    for layer, entry in S.FUNCTION_TEMPLATE.items():
        assert T.hands_on_faults(layer, entry["hands_on"]) == [], layer
        assert not re.search(r"\bYou\b", entry["hands_on"]), "the owner is 'the owner', never 'You'"
    assert [a for a, _ in T.hands_on_actors(S.FUNCTION_TEMPLATE["identity"]["hands_on"])] == ["Adaptation", "Coordination", "The owner"]
    assert [a for a, _ in T.hands_on_actors(S.FUNCTION_TEMPLATE["root"]["hands_on"])] == ["Identity", "Coordination", "Priority"]
    assert [a for a, _ in T.hands_on_actors(S.FUNCTION_TEMPLATE["audit"]["hands_on"])] == ["Identity"]
    # Identity is the only function that speaks to the owner: no other hands on to the owner
    for layer in S.FUNCTION_LAYERS:
        named = [a for a, _ in T.hands_on_actors(S.FUNCTION_TEMPLATE[layer]["hands_on"])]
        assert ("The owner" in named) == (layer == "identity"), layer
    # the failing example of FT-10, and the others
    assert T.hands_on_faults("audit", "Priority: a finding.") == [
        "Audit hands on to Priority, and the interface gives Audit no row to Priority (S.SENDS) and no call to it (S.CALLS)"]
    assert T.hands_on_faults("audit", "Identity only: readings. The owner: findings.") != []
    assert T.hands_on_faults("identity", "Adaptation: a line. You: questions.")[0].startswith("Identity hands on to the owner, who is 'the owner'")
    assert T.hands_on_faults("identity", "Identity: itself.") == ["Identity hands on to itself"]
    assert T.hands_on_faults("identity", "no one in particular") == ["Identity names no one it hands on to"]
    # an actor reached through another is named as reached through it (Priority, Identity, through Adaptation's conflict)
    assert T.hands_on_faults("priority", "Identity: through Adaptation's conflict, when a limit is hit.") == []
    assert T.hands_on_faults("priority", "Identity: when a limit is hit.") != []
    assert T.hands_on_faults("priority", "Audit: through Adaptation's conflict.") != [], "Adaptation sends nothing to Audit"
    # the calls that are no post: S.CALLS gives Root its callees, and Adaptation runs Root's standards on the line it shapes
    assert {c["to"] for c in S.CALLS if c["from"] == "Root"} >= {"Coordination", "Priority", "Identity"}
    assert "S.validate_workflow(" in (HERE / "layers" / "adaptation" / "v1.py").read_text(encoding="utf-8"), \
        "Adaptation hands on to Root because it calls Root's check in process: if it stopped, drop Root from its hands_on"


def test_reserved_is_the_sites_list():
    reserved = S.FUNCTION_TEMPLATE["adaptation"]["reserved"]
    assert reserved == ("crystallize", "grow", "learn", "compass"), "the four hands the site lists as placeholders"
    # recorded, not built: no prompt group, no step and no recipe of Adaptation is any of them
    assert not set(reserved) & set(S.PROMPTS["adaptation"])
    recipe = _read(HERE / "layers" / "adaptation" / "v1.json")
    assert not [s["id"] for _, s in _steps_of(recipe) if any(r in s["id"] for r in reserved)]
    assert not set(reserved) & set(S.CHECKS["adaptation"]) and not set(reserved) & set(S.VERDICTS["adaptation"].get("move", ()))


#: the parts of the goal group that A3-FUNCTIONS adds (rule FT-2). A3-FUNCTIONS deletes this list in the commit that adds them:
#: until then a part named here is pending, and the test below fails the day one exists and is still listed
PENDING = (("goal", "done"), ("goal", "role_is"), ("goal", "role_may"), ("goal", "role_procedure"), ("goal", "role_patterns"))


def test_template_parts_homes_exist():
    parts = S.TEMPLATE_PARTS
    assert len({p[0] for p in parts}) == len(parts) == 20, "the twenty parts of A3.4.2, once each"
    assert [p[0] for p in parts][:3] == ["goal", "skills", "done"] and ("is", None, "word", ("goal", "role_is")) in parts
    assert ("done", "done", "word", ("goal", "done")) in parts
    assert {p[2] for p in parts} == {"word", "constant", "derived", "version"}
    for part, site, kind, home in parts:
        assert site is None or isinstance(site, str), part
        if kind == "word":
            group, name = home
            for layer in S.FUNCTION_LAYERS:
                exists = name in S.PROMPTS[layer].get(group, {})
                if home in PENDING:
                    assert not exists, ("%s.%s exists in %s now: delete it from PENDING in test_layer_templates.py (A3-FUNCTIONS' to delete)"
                                        % (group, name, layer))
                else:
                    assert exists, "%s: the word %s.%s is no part of S.PROMPTS['%s']" % (part, group, name, layer)
        elif kind == "constant":
            table, key = home
            assert hasattr(S, table), part
            if key:
                assert all(key in S.FUNCTION_TEMPLATE[layer] for layer in S.FUNCTION_TEMPLATE), "%s: %s is no key of every entry" % (part, key)
        elif home[0].isupper():
            assert hasattr(S, home[0]), "%s: the interface has no table %s" % (part, home[0])
            if home[1]:
                assert any(home[1] in (getattr(S, home[0]).get(layer) or {}) for layer in S.FUNCTION_LAYERS), "%s: %s" % (part, home)
        else:
            assert home[0] in ("journeys",), "%s: a home in lower case is a folder of the repository" % part
    # every typed word of A3.4.2 is a part of the table, and every constant it names is a key of the function template
    assert {p[3][1] for p in parts if p[2] == "constant" and p[3][1]} == {"role", "is_not", "never", "hands_on"}
    assert {p[0] for p in parts if p[2] == "word"} == {"goal", "skills", "done", "is", "may", "procedure", "patterns"}
    assert {part for part in (p[0] for p in parts) if part in S.ROLE_INPUTS} == {"is", "is_not", "may", "never", "procedure", "patterns", "hands_on", "agreement"}


def test_the_function_template_is_carried_by_describe():
    got = S.describe()["function_template"]
    assert got["by_layer"] == json.loads(json.dumps(S.FUNCTION_TEMPLATE)) and got["agreement"] == list(S.DEPARTMENT_AGREEMENT)
    assert got["role_inputs"] == list(S.ROLE_INPUTS) and got["role_block_max"] == 3600
    assert got["banned"] == S.TEMPLATE_BANNED and got["banned_agent"] == S.TEMPLATE_BANNED_AGENT and got["never_say"] == S.TEMPLATE_NEVER_SAY
    assert len(got["parts"]) == 20
    levels = {l["level"]: l for l in S.TEMPLATE_LEVELS}
    assert levels["L2"]["base"] == "FUNCTION_TEMPLATE" and isinstance(S.FUNCTION_TEMPLATE, dict)
