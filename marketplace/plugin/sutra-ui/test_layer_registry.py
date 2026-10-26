"""The registry and the seam (PRD amendment A1.18, A1.19; W1-CORE K1, steps C1 and C2).

C1  layers/__init__.py: available, load, pins, impl, layer_of, resolve, names, call and view. With every module holding
    empty dicts the registry returns the legacy function; a module that provides a name is the one that runs it; a
    ref_to delegate reaches the reloaded engine_runtime; and nothing imports engine_runtime when `layers` is imported.
C2  engine_runtime's seam: every code, prompt, draft and check lookup goes through R._resolve, a gate resolves its code
    and its check with its own function as the engine (a start asks them in blocked(), a rule in _ask_rule and
    _gate_row), step and gate rows carry `impl`, and validate() holds the definitions to the interface (edges,
    handlers, checks).

A test that meets a fault of the interface fails (conftest.py); a deliberate one is wrapped in S.expect_refused().
"""
import copy
import importlib
import subprocess
import sys
import types
from pathlib import Path

import pytest

import layers
import layers.contract as C
import layer_schema as S

HERE = Path(__file__).resolve().parent


@pytest.fixture
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("SUTRA_NATIVE_DEPT_HOME", str(tmp_path / "departments"))
    monkeypatch.setenv("SUTRA_NATIVE_HOME", str(tmp_path / "registry"))
    monkeypatch.setenv("SUTRA_UI_PROPOSALS", str(tmp_path / "proposals"))
    monkeypatch.setenv("SUTRA_WEBSITE_OFFLINE", "1")
    monkeypatch.setenv("J2_FLOW_V1", "0")
    monkeypatch.delenv("SUTRA_ENGINE_RUNTIME", raising=False)
    monkeypatch.setattr(layers, "_TOLD", set())
    return tmp_path / "departments"


def modules():
    import engine_runtime as R
    import website_dept as W
    return W, R


@pytest.fixture
def empty_modules(monkeypatch):
    """Wave 0's state, which these tests describe: every layer's module holds empty dicts. From wave 1 a layer's package fills
    its own, so the registry serves empty stubs in their place and the real modules are not consulted."""
    for layer, impl_id in S.DEFAULT_PINS.items():
        monkeypatch.setitem(layers._LOADED, impl_id, types.SimpleNamespace(
            LAYER=layer, VERSION=1, IMPLEMENTS=S.SCHEMA_VERSION, CODE={}, PROMPT={}, DRAFT={}, CHECK={}, WORDS={}, LAYOUT={}))


# ---- C1 · the registry -----------------------------------------------------------------------------------------------
def test_c1_available_lists_the_versions_on_disk_in_layer_order():
    assert layers.available() == {layer: ["%s/v1" % layer] for layer in S.LAYER_NAMES}
    assert layers.available() == {layer: [impl] for layer, impl in S.DEFAULT_PINS.items()}


def test_c1_load_imports_checks_and_caches_a_module():
    m = layers.load("identity/v1")
    assert (m.LAYER, m.VERSION, m.IMPLEMENTS) == ("identity", 1, S.SCHEMA_VERSION)
    assert layers.load("identity/v1") is m and layers._LOADED["identity/v1"] is m
    assert layers.load("identity/v2") is None, "no such file"
    assert layers.load("marketing/v1") is None and layers.load("identity") is None and layers.load(None) is None, "not an implementation id"
    assert layers.load("../layer_schema") is None


def test_c1_load_refuses_a_module_whose_layer_version_or_schema_do_not_match(monkeypatch):
    for attr, value in (("IMPLEMENTS", S.SCHEMA_VERSION + 1), ("VERSION", 2), ("LAYER", "audit")):
        monkeypatch.delitem(layers._LOADED, "identity/v1")
        real = importlib.import_module("layers.identity.v1")
        monkeypatch.setattr(real, attr, value)
        assert layers.load("identity/v1") is None, attr
        monkeypatch.undo()                                   # the attribute and the cache entry come back
        assert layers.load("identity/v1") is real


def test_c1_load_runs_nothing_from_a_module_that_does_not_import(monkeypatch):
    monkeypatch.delitem(layers._LOADED, "audit/v1", raising=False)
    real = importlib.import_module
    monkeypatch.setattr(layers.importlib, "import_module",
                        lambda name, *a: (_ for _ in ()).throw(SyntaxError("broken")) if name == "layers.audit.v1" else real(name, *a))
    assert layers.load("audit/v1") is None


def test_c1_pins_are_the_default_pins_and_a_record_naming_another_gets_one_row(home):
    W, R = modules()
    ref = C.fixture_department(home)
    assert layers.pins() == S.DEFAULT_PINS and layers.pins(ref) == S.DEFAULT_PINS and layers.pins(ref, W.dept(ref)) == S.DEFAULT_PINS
    assert layers.pins() is not S.DEFAULT_PINS, "a copy: a caller cannot change the release's choice"
    assert not [r for r in W.runs(ref) if "per-department" in str(r.get("what"))], "the default pins are no news"
    d = dict(W.dept(ref), layers=dict(S.DEFAULT_PINS, identity="identity/v2", audit="audit/v1"))
    for _ in range(3):
        assert layers.pins(ref, d) == S.DEFAULT_PINS
    rows = [r for r in W.runs(ref) if "per-department" in str(r.get("what"))]
    assert [(r["engine"], r["what"]) for r in rows] == [("Identity", "runs the default: per-department versions come in wave 3")]
    layers.pins(ref, dict(d, layers=dict(d["layers"], priority="priority/v7")))
    assert [r["engine"] for r in W.runs(ref) if "per-department" in str(r.get("what"))] == ["Identity", "Priority"]


def test_c1_pins_with_no_department_to_write_to_say_nothing(home):
    assert layers.pins("dref-nobody", {"layers": {"identity": "identity/v9"}}) == S.DEFAULT_PINS


def test_c1_impl_is_the_module_the_pin_names(monkeypatch):
    assert layers.impl(None, "identity") is layers.load("identity/v1")
    assert layers.impl(None, "root") is layers.load("root/v1")
    stub = types.SimpleNamespace(LAYER="identity", VERSION=1, IMPLEMENTS=1, CODE={})
    monkeypatch.setitem(layers._LOADED, "identity/v1", stub)
    assert layers.impl("dref-x", "identity", {}) is stub
    monkeypatch.delitem(layers._LOADED, "identity/v1")
    monkeypatch.setattr(layers, "pins", lambda ref=None, d=None: dict(S.DEFAULT_PINS, identity="identity/v9"))
    assert layers.impl(None, "identity") is layers.load("identity/v1"), "a pin that does not load runs the layer's default version"
    assert layers.impl(None, "audit") is layers.load("audit/v1")


def test_c1_layer_of_names_the_layer_of_a_function_and_of_setup_and_nothing_else():
    assert {e: layers.layer_of(e) for e in ("Identity", "Adaptation", "Priority", "Coordination", "Audit", "Setup")} == \
           {"Identity": "identity", "Adaptation": "adaptation", "Priority": "priority", "Coordination": "coordination",
            "Audit": "audit", "Setup": "root"}
    assert layers.layer_of("Plan") is None and layers.layer_of("Write") is None and layers.layer_of(None) is None


def test_c1_with_empty_modules_resolve_returns_the_legacy_function(home, empty_modules):
    W, R = modules()
    for kind, legacy in (("code", R.CODE), ("prompt", R.PROMPT), ("draft", R.DRAFT), ("check", R.CHECK)):
        for engine in ("Identity", "Adaptation", "Priority", "Coordination", "Audit", "Setup", "Plan", None):
            for name in list(legacy)[:6]:
                assert layers.resolve("dref-x", engine, kind, name, legacy) is legacy[name]
    with pytest.raises(KeyError):
        layers.resolve(None, "Identity", "code", "no_such_body", R.CODE)


def test_c1_a_stub_holding_a_name_is_what_resolve_returns_for_that_layers_engine(monkeypatch):
    W, R = modules()
    f = lambda ctx, step, item: {"stub": True}
    m = layers.load("identity/v1")
    monkeypatch.setitem(m.CODE, "identity_read", f)
    assert layers.resolve("dref-x", "Identity", "code", "identity_read", R.CODE) is f
    assert layers.resolve("dref-x", "Priority", "code", "identity_read", R.CODE) is R.CODE["identity_read"], "another layer's engine"
    assert layers.resolve("dref-x", "Plan", "code", "identity_read", R.CODE) is R.CODE["identity_read"], "a work engine has no layer"
    assert layers.resolve("dref-x", "Identity", "code", "plan_read", R.CODE) is R.CODE["plan_read"], "a name it does not hold"
    other = lambda *a: 1
    assert layers.resolve("dref-x", "Identity", "check", "identity_read", {"identity_read": other}) is other, "another kind"
    # each kind is its own dict
    for kind in ("prompt", "draft", "check"):
        monkeypatch.setitem(getattr(m, kind.upper()), "a_name", f)
        assert layers.resolve("dref-x", "Identity", kind, "a_name", {"a_name": None}) is f


def test_c1_resolve_serves_a_stub_the_test_puts_in_the_registry(monkeypatch, empty_modules):
    W, R = modules()
    f = lambda ctx, step, item: {}
    stub = types.SimpleNamespace(LAYER="identity", VERSION=1, IMPLEMENTS=1, CODE={"identity_read": f}, PROMPT={}, DRAFT={}, CHECK={})
    # the names the other layers' own packages hold already: a layer fills its dicts in its own package
    others = {n for layer, ids in layers.available().items() if layer != "identity" for i in ids for n in layers.load(i).CODE}
    monkeypatch.setitem(layers._LOADED, "identity/v1", stub)
    assert layers.resolve(None, "Identity", "code", "identity_read", R.CODE) is f
    assert layers.names("code") == others | {"identity_read"}


def test_c1_names_are_what_any_implementation_provides(monkeypatch):
    held = {kind: {n for ids in layers.available().values() for i in ids for n in getattr(layers.load(i), kind.upper())} for kind in layers.KINDS}
    assert all(layers.names(kind) == held[kind] for kind in layers.KINDS), "what the layers' own packages hold, and nothing else"
    monkeypatch.setitem(layers.load("priority/v1").CHECK, "answer_has_its_price", lambda *a: {})
    monkeypatch.setitem(layers.load("audit/v1").CHECK, "has_a_verdict", lambda *a: {})
    assert layers.names("check") == held["check"] | {"answer_has_its_price", "has_a_verdict"} and layers.names("code") == held["code"]


def test_c1_call_is_the_pinned_implementations_attribute_else_engine_runtimes(monkeypatch):
    W, R = modules()
    m = layers.load("identity/v1")
    assert layers.call(None, "identity", "_sha", "x") == R._sha("x")
    monkeypatch.setattr(m, "_sha", lambda x: "the layer's own " + x, raising=False)
    assert layers.call(None, "identity", "_sha", "x") == "the layer's own x"
    monkeypatch.setattr(m, "_adds", lambda a, b, *, c=0: a + b + c, raising=False)
    assert layers.call(None, "identity", "_adds", 1, 2, c=3) == 6


def test_c1_view_is_the_layers_view_or_none(home, monkeypatch):
    W, R = modules()
    assert layers.view("dref-x", "root", {}, [], []) is None, "Root has no pane"
    monkeypatch.setattr(layers.load("audit/v1"), "view", lambda ref, d, events, asks: {"stub": [ref, d, events, asks]})
    assert layers.view("dref-x", "audit", {"k": 1}, ["e"], ["a"]) == {"stub": ["dref-x", {"k": 1}, ["e"], ["a"]]}
    ref = C.fixture_department(home)
    got = layers.view(ref, "identity", W.dept(ref), [], W.asks(ref))
    assert S.validate_view("identity", got) == []


def test_c1_a_ref_to_delegate_reaches_the_reloaded_engine_runtime(monkeypatch):
    import engine_runtime as R
    delegate = layers.ref_to("identity_read")
    monkeypatch.setitem(layers.load("identity/v1").CODE, "identity_read", delegate)
    got = layers.resolve("dref-x", "Identity", "code", "identity_read", R.CODE)
    assert got is delegate and delegate.legacy == ("engine_runtime", "identity_read")
    old = R.identity_read
    R2 = importlib.reload(R)
    try:
        assert R2.identity_read is not old, "a reloaded module holds new functions"
        monkeypatch.setattr(R2, "identity_read", lambda ctx, step, item: "the reloaded one")
        assert layers.resolve("dref-x", "Identity", "code", "identity_read", R2.CODE)(None, None, None) == "the reloaded one"
    finally:
        monkeypatch.undo()
        importlib.reload(R2)


def test_c1_importing_layers_imports_no_engine_runtime():
    out = subprocess.run([sys.executable, "-c", "import sys, layers, layers.contract; "
                          "assert 'engine_runtime' not in sys.modules and 'website_dept' not in sys.modules, sorted(sys.modules)"],
                         cwd=str(HERE), capture_output=True, text=True)
    assert out.returncode == 0, out.stderr


def test_c1_the_forwarders_reach_the_prompt_compiler():
    assert layers.prompt.__module__ == "layers" and layers.words.__module__ == "layers"


# ---- C2 · the seam ---------------------------------------------------------------------------------------------------
REF = "dref-seam0001"


@pytest.fixture
def dept(home):
    """A website department on the runtime with a brief, and the model that is never there: each soft step runs its draft."""
    W, R = modules()
    importlib.reload(W)
    importlib.reload(R)
    W.create(REF, "City Care Hospital Website", None)
    W.add_version(REF, "Brief", {"brief.md": "# City Care Hospital Website\n\nA website for City Care Hospital.\n"},
                  [{"ask": "a website", "at": "2026-10-23T10:00:00+05:30"}], "owner", {"ok": True, "notes": ["the owner's goal"]})
    yield W, R, REF
    R._DEFS.clear()


def test_c2_resolve_is_the_registry_and_the_engine_argument_names_whose_step_it_is(dept, monkeypatch):
    W, R, ref = dept
    ctx = {"ref": ref, "dept": W.dept(ref), "engine": "Identity"}
    for kind, legacy in (("code", R.CODE), ("prompt", R.PROMPT), ("draft", R.DRAFT), ("check", R.CHECK)):
        name = sorted(legacy)[0]
        assert R._resolve(ctx, kind, name) is legacy[name]
    f = lambda c, s, i: "stub"
    monkeypatch.setitem(layers.load("coordination/v1").CODE, "coord_busy", f)
    assert R._resolve(ctx, "code", "coord_busy") is R.CODE["coord_busy"], "Identity's engine: not Coordination's body"
    assert R._resolve(ctx, "code", "coord_busy", engine="Coordination") is f
    assert R._resolve(dict(ctx, engine="Write"), "code", "coord_busy", engine="Coordination") is f
    assert R._resolve(dict(ctx, engine="Coordination"), "code", "coord_busy") is f
    assert R._resolve({"ref": ref}, "code", "coord_busy") is R.CODE["coord_busy"], "no engine, no layer"


def test_c2_every_lookup_in_the_runtime_goes_through_the_seam():
    """The four registry literals are the fallback _resolve reads; no step, gate or rule is looked up in them directly.
    coord_pick is Coordination's own region, which W1-COORD moves to the seam."""
    import ast
    tree = ast.parse((HERE / "engine_runtime.py").read_text(encoding="utf-8"))
    sites = set()
    for fn in [n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)]:
        for node in ast.walk(fn):
            if isinstance(node, ast.Subscript) and getattr(node.value, "id", None) in ("CODE", "PROMPT", "DRAFT", "CHECK"):
                sites.add(fn.name)
    assert sites <= {"coord_pick"}, sites


def test_c2_a_stub_identity_body_is_called_by_a_real_identity_run(dept, monkeypatch):
    W, R, ref = dept
    called = []

    def identity_read(ctx, step, item):
        called.append((ctx["engine"], step["id"]))
        return R.CODE["identity_read"](ctx, step, item)
    monkeypatch.setitem(layers.load("identity/v1").CODE, "identity_read", identity_read)
    W.owner_ask(ref, "Which page lists the doctors?")
    W.run_until_idle(ref, limit=200)
    assert ("Identity", "identity.read") in called
    assert [r["step"] for r in R.step_rows(ref) if r["step"] == "identity.read"], "and the run went on to its row"


def test_c2_a_gate_is_resolved_with_its_function_as_the_engine_and_its_row_names_the_version(dept, monkeypatch):
    W, R, ref = dept
    asked = []

    def wait_engine(ctx, step, item):
        asked.append((ctx["engine"], step["id"]))
        return "wait", "the stub says wait"
    monkeypatch.setitem(layers.load("identity/v1").CODE, "identity_wait_engine", wait_engine)
    got = R.admit(ref, W.dept(ref), "Write", {"v": 1}, "Write@seam")
    assert got == ("wait", "the stub says wait") and asked == [("Write", "identity.wait_engine")], \
        "Write's start asks Identity's gate, and Identity's module answers it"
    row = next(r for r in R.step_rows(ref) if r["step"] == "identity.wait_engine")
    assert (row["mode"], row["engine"], row["impl"], row["answer"]) == ("gate", "Identity", "identity/v1", "wait")


def test_c2_a_gates_check_is_resolved_with_its_function_as_the_engine_when_a_start_is_asked(dept, monkeypatch):
    """The gate's covering (M2.4) is its function's too: Write's start asks Identity's gates, and the check that reads their
    answers is the one Identity's pinned module provides, not the legacy body that a lookup for the work engine would find."""
    W, R, ref = dept
    asked = []
    own = {"ok": True, "notes": ["Identity's own check ran"]}

    def check(ctx, step, item, out):
        asked.append((ctx["engine"], step["id"], out["answer"]))
        return own
    monkeypatch.setitem(layers.load("identity/v1").CHECK, "gate_answer_is_known", check)
    assert R.admit(ref, W.dept(ref), "Write", {"v": 1}, "Write@seamcheck") == ("admit", None)
    assert asked == [("Write", "identity.wait_engine", "admit"), ("Write", "identity.gate", "admit")], \
        "each of Identity's two gates in Write's start reads its answer through Identity's module, and no other gate does"
    rows = {r["step"]: r for r in R.step_rows(ref) if r["mode"] == "gate"}
    assert rows["identity.wait_engine"]["check"] == own and rows["identity.gate"]["check"] == own
    assert rows["priority.envelope"]["check"] != own and rows["coord.chain"]["check"] != own, "Priority's and Coordination's gates keep their own"


def test_c2_a_check_of_the_gates_layer_can_hold_the_start_it_does_not_cover(dept, monkeypatch):
    W, R, ref = dept
    held = {"ok": False, "notes": ["Identity's own check refused it"]}
    monkeypatch.setitem(layers.load("identity/v1").CHECK, "gate_answer_is_known", lambda ctx, step, item, out: held)
    got = R.admit(ref, W.dept(ref), "Write", {"v": 1}, "Write@seamhold")
    assert got == ("wait", "Identity's own check refused it"), "the covering is code: a gate whose check fails never lets a start through"
    row = next(r for r in R.step_rows(ref) if r["step"] == "identity.wait_engine")
    assert (row["answer"], row["check"], row["status"]) == ("wait", held, "failed")


def test_c2_a_rules_check_is_resolved_with_its_function_as_the_engine_when_it_is_asked(dept, monkeypatch):
    """_ask_rule writes the row of a rule of Coordination from a work engine's context; the row's covering is Coordination's
    pinned module's check, found with no context but the ref and the function."""
    W, R, ref = dept
    asked = []
    own = {"ok": True, "notes": ["Coordination's own check ran"]}

    def check(ctx, step, item, out):
        asked.append((step["id"], out["answer"]))
        return own
    monkeypatch.setitem(layers.load("coordination/v1").CHECK, "one_run_at_a_time", check)
    ctx = dict(R._coord_ctx(ref), engine="Write")
    assert R._ask_rule(ref, "coord.busy", key="Write@seamcheck|coord.busy", ctx=ctx) == ("admit", None)
    assert asked == [("coord.busy", "admit")]
    row = next(r for r in R.step_rows(ref) if r["step"] == "coord.busy")
    assert (row["engine"], row["impl"], row["check"]) == ("Coordination", "coordination/v1", own)
    # and the gate row alone, written with no context, finds the same
    _, busy = R.step_def("coord.busy")
    R._gate_row(ref, "Write@seamrow", "Coordination", busy, "C2", "wait", "a run runs")
    assert asked[-1] == ("coord.busy", "wait")
    assert [r["check"] for r in R.step_rows(ref) if r["slot"] == "Write@seamrow"] == [own]


def test_c2_a_rule_is_resolved_with_its_function_as_the_engine_in_a_run_and_in_an_ask(dept, monkeypatch):
    W, R, ref = dept
    seen = []

    def busy(ctx, step, item):
        seen.append(ctx["engine"])
        return "wait", "the stub says wait"
    monkeypatch.setitem(layers.load("coordination/v1").CODE, "coord_busy", busy)
    ctx = dict(R._coord_ctx(ref), engine="Write")
    assert R._run_rule(ctx, "coord.busy") == ("wait", "the stub says wait")
    assert R._ask_rule(ref, "coord.busy", key="Write@seam|coord.busy", ctx=ctx) == ("wait", "the stub says wait")
    assert seen == ["Write", "Write"]
    row = next(r for r in R.step_rows(ref) if r["step"] == "coord.busy")
    assert (row["engine"], row["impl"], row["mode"]) == ("Coordination", "coordination/v1", "gate")


def test_c2_every_step_and_gate_row_carries_the_implementation_that_made_it(dept, monkeypatch):
    W, R, ref = dept
    W.owner_ask(ref, "Which page lists the doctors?")
    W.owner_ask(ref, "From now on, every page names the phone line.")
    W.run_until_idle(ref, limit=300)
    rows = R.step_rows(ref)
    assert rows and all("impl" in r for r in rows)
    seen = {r["engine"]: r["impl"] for r in rows if r["engine"] in S.ENGINE_LAYER}
    assert seen and all(impl == S.DEFAULT_PINS[S.ENGINE_LAYER[engine]] for engine, impl in seen.items()), seen
    assert {r["impl"] for r in rows if r["engine"] == "Identity"} == {"identity/v1"}
    assert {r["mode"] for r in rows} >= {"slot"}
    # a work engine is no layer's: its rows say so with None
    assert R._impl({"ref": ref, "engine": "Write"}) is None and R._impl({"ref": ref, "engine": "Audit"}) == "audit/v1"
    assert R._impl({"ref": ref}, "Priority") == "priority/v1"


def test_c2_validate_accepts_a_name_a_layer_module_provides(monkeypatch):
    W, R = modules()
    d = copy.deepcopy(R.defs())
    assert R.validate(d) == []
    steps = {x["id"]: x for x in d["engines"]["Identity"]["on"][1]["steps"]}
    m = layers.load("identity/v1")
    # (kind, the step, its field, the fault while no one provides the name)
    for kind, sid, field, fault in (
            ("code", "identity.file", "code", "Identity, identity.file: no function named a_name_only_a_layer_holds ships with the app"),
            ("prompt", "identity.take", "prompt", "Identity, identity.take: no prompt named a_name_only_a_layer_holds ships with the app"),
            ("draft", "identity.take", "draft", "Identity, identity.take: a soft step names a plain draft")):
        was = steps[sid][field]
        steps[sid][field] = "a_name_only_a_layer_holds"
        assert R.validate(d) == [fault], kind
        monkeypatch.setitem(getattr(m, kind.upper()), "a_name_only_a_layer_holds", lambda *a: {})
        assert R.validate(d) == [], kind
        monkeypatch.delitem(getattr(m, kind.upper()), "a_name_only_a_layer_holds")
        steps[sid][field] = was
    # a check's name is the interface's: a layer may provide the body, but the name must be one the layer or all may use
    was = steps["identity.take"]["check"]
    steps["identity.take"]["check"] = "a_name_only_a_layer_holds"
    assert R.validate(d) == ["Identity, identity.take: no check named a_name_only_a_layer_holds ships with the app"]
    monkeypatch.setitem(m.CHECK, "a_name_only_a_layer_holds", lambda *a: {})
    assert R.validate(d) == ["Identity, identity.take: the check a_name_only_a_layer_holds is neither Identity's nor shared, in the interface"]
    steps["identity.take"]["check"] = was
    assert R.validate(d) == []


def test_c2_validate_holds_the_definitions_edges_to_the_interfaces():
    W, R = modules()
    d = copy.deepcopy(R.defs())
    assert d["edges"] == S.edges() and R.validate(d) == []
    d["edges"]["Priority"]["propose"] = ["Owner"]
    assert R.validate(d) == ["edges, Priority: the definitions let it propose to ['Owner'], and the interface says ['Adaptation']"]
    d["edges"]["Priority"]["propose"] = ["Adaptation"]
    d["edges"]["Audit"]["cancel"] = ["Identity"]
    assert R.validate(d) == ["edges, Audit: the definitions let it cancel to ['Identity'], and the interface says None"]
    del d["edges"]["Audit"]["cancel"]
    d["edges"]["Weather"] = {"inform": ["Owner"]}
    assert R.validate(d) == ["edges, Weather: the interface knows no such actor"]
    del d["edges"]["Weather"]
    d["edges"]["Owner"] = {"request": ["Identity"]}
    assert len(R.validate(d)) == 3 and all(f.startswith("edges, Owner: ") for f in R.validate(d)), "an act the definitions dropped is a fault too"


def test_c2_a_definitions_copy_with_a_handler_outside_hears_is_refused_with_a_named_fault():
    W, R = modules()
    d = copy.deepcopy(R.defs())
    handler = copy.deepcopy(d["engines"]["Priority"]["on"][0])
    handler.update(name="Hear the weather", when={"msg_type": "inform", "word": "weather"})
    d["engines"]["Priority"]["on"].append(handler)
    assert R.validate(d) == ["Priority, Hear the weather: the handler hears inform/weather, which is no row of what Priority hears"]
    handler["when"] = {"msg_type": "request"}                    # a word the engine takes any of is its own row only where HEARS says so
    assert R.validate(d) == ["Priority, Hear the weather: the handler hears request/(any), which is no row of what Priority hears"]
    d["engines"]["Priority"]["on"].pop()
    # the same handler on a work engine is the definitions' own business, not the interface's
    d["engines"]["Write"]["on"] = [dict(handler, name="Hear the weather", steps=[])]
    assert not [f for f in R.validate(d) if "which is no row" in f]


def test_c2_a_function_step_whose_check_is_neither_its_layers_nor_shared_is_refused():
    W, R = modules()
    d = copy.deepcopy(R.defs())
    step = d["engines"]["Priority"]["on"][0]["steps"][0]
    was = step["check"]
    assert was in S.CHECKS["priority"] or was in S.SHARED_CHECKS
    step["check"] = "verdict_is_known"                          # Identity's check: it exists, but not for Priority
    assert R.validate(d) == ["Priority, %s: the check verdict_is_known is neither Priority's nor shared, in the interface" % step["id"]]
    step["check"] = "no_such_check"
    assert R.validate(d) == ["Priority, %s: no check named no_such_check ships with the app" % step["id"]]
    step["check"] = was
    assert R.validate(d) == []
    # a gate of a function is held to its layer's checks as a step is
    gate = d["engines"]["Identity"]["gates"][0]
    gate["check"] = "answer_has_its_price"
    assert R.validate(d) == ["Identity, identity.gate: the check answer_has_its_price is neither Identity's nor shared, in the interface"]


def test_c2_the_shipped_definitions_are_clean_and_load():
    W, R = modules()
    assert R.validate(R.defs()) == []
