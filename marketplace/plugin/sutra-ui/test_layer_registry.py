"""The registry and the seam (PRD amendment A1.18, A1.19; W1-CORE K1, steps C1 and C2).

C1  layers/__init__.py: available, load, pins, impl, layer_of, resolve, names, call and view. With every module holding
    empty dicts the registry returns the legacy function; a module that provides a name is the one that runs it; a
    ref_to delegate reaches the reloaded engine_runtime; and nothing imports engine_runtime when `layers` is imported.
C2  engine_runtime's seam: every code, prompt, draft and check lookup goes through R._resolve, a gate resolves with
    its own function as the engine, step and gate rows carry `impl`, and validate() holds the definitions to the
    interface (edges, handlers, checks).

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


def test_c1_with_empty_modules_resolve_returns_the_legacy_function(home):
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
    assert layers.resolve("dref-x", "Identity", "code", "identity_route", R.CODE) is R.CODE["identity_route"], "a name it does not hold"
    other = lambda *a: 1
    assert layers.resolve("dref-x", "Identity", "check", "identity_read", {"identity_read": other}) is other, "another kind"
    # each kind is its own dict
    for kind in ("prompt", "draft", "check"):
        monkeypatch.setitem(getattr(m, kind.upper()), "a_name", f)
        assert layers.resolve("dref-x", "Identity", kind, "a_name", {"a_name": None}) is f


def test_c1_resolve_serves_a_stub_the_test_puts_in_the_registry(monkeypatch):
    W, R = modules()
    f = lambda ctx, step, item: {}
    stub = types.SimpleNamespace(LAYER="identity", VERSION=1, IMPLEMENTS=1, CODE={"identity_read": f}, PROMPT={}, DRAFT={}, CHECK={})
    monkeypatch.setitem(layers._LOADED, "identity/v1", stub)
    assert layers.resolve(None, "Identity", "code", "identity_read", R.CODE) is f
    assert layers.names("code") == {"identity_read"}


def test_c1_names_are_what_any_implementation_provides(monkeypatch):
    assert all(layers.names(kind) == set() for kind in layers.KINDS)
    monkeypatch.setitem(layers.load("priority/v1").CHECK, "answer_has_its_price", lambda *a: {})
    monkeypatch.setitem(layers.load("audit/v1").CHECK, "has_a_verdict", lambda *a: {})
    assert layers.names("check") == {"answer_has_its_price", "has_a_verdict"} and layers.names("code") == set()


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
