"""A4-PORT: the 130 definitions as classes behind the facade, with the frozen oracle and the proof (PRD amendment A4, A4.3).

P0 the old picture (facade names, writers' values, golden corpus), P1 the constants, P2 the frozen oracle, then the swap."""
import hashlib
import json
import os
import subprocess
import sys
import types
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE / "qa"))
import layer_schema as S                                                      # noqa: E402

MODELS = HERE / "test_fixtures" / "models"
GOLDEN = MODELS / "corpus" / "golden"
WRITERS = MODELS / "corpus" / "writers"


def _rows(path):
    return [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]


def _kind(v):
    if isinstance(v, types.ModuleType):
        return "module"
    if isinstance(v, type):
        return "class"
    if callable(v):
        return "function"
    if isinstance(v, bool):
        return "bool"
    if isinstance(v, (int, float)):
        return "number"
    if isinstance(v, str):
        return "str"
    if isinstance(v, dict):
        return "dict"
    if isinstance(v, tuple):
        return "tuple"
    if isinstance(v, list):
        return "list"
    return "other"


# ---- P0 -------------------------------------------------------------------------------------------------------------------
def test_corpus_sha():
    """CORPUS.sha is re-derived from the files, in definition order, the way qa/a4_equiv.write_golden writes it."""
    h = hashlib.sha256()
    names = sorted(p.name[:-6] for p in GOLDEN.glob("*.jsonl"))
    assert len(names) == 130
    for name in names:
        h.update(name.encode("utf-8") + b"\n" + (GOLDEN / (name + ".jsonl")).read_text(encoding="utf-8").encode("utf-8"))
    sha = h.hexdigest()
    assert sha == (MODELS / "CORPUS.sha").read_text(encoding="utf-8").strip() == (GOLDEN / "CORPUS.sha").read_text(encoding="utf-8").strip()


def test_the_golden_corpus_covers_every_definition_and_the_oracle_gives_its_answers():
    assert sorted(p.name[:-6] for p in GOLDEN.glob("*.jsonl")) == sorted(S.DEFS)
    for path in sorted(GOLDEN.glob("*.jsonl")):
        name = path.name[:-6]
        for row in _rows(path):
            assert S.validate(name, row["value"]) == row["faults"], (name, row["value"])


def test_every_recorded_value_has_the_verdict_it_was_recorded_with():
    verdicts = json.loads((MODELS / "corpus" / "writers.verdicts.json").read_text(encoding="utf-8"))
    assert set(verdicts) == {p.name[:-6] for p in WRITERS.glob("*.jsonl")}
    total = rejected = 0
    for name, marks in verdicts.items():
        rows = _rows(WRITERS / (name + ".jsonl"))
        assert len(rows) == len(marks), name
        for row, mark in zip(rows, marks):
            assert (S.validate(name, row) == []) == (mark == "1"), (name, row)
        total += len(rows)
        rejected += marks.count("0")
    assert total > 4000 and rejected > 300


def test_the_writers_values_cover_every_definition():
    have = {p.name[:-6] for p in WRITERS.glob("*.jsonl")}
    assert sorted(set(S.DEFS) - have) == []                      # every one of the 130 has a recorded value


def test_facade_names():
    """Every public name of layer_schema as it was before A4-PORT is still there, of the same kind (P0's snapshot): the facade
    grows, it never loses a name."""
    snap = json.loads((MODELS / "facade_names.json").read_text(encoding="utf-8"))
    assert len(snap) > 200
    lost = [n for n in snap if not hasattr(S, n)]
    assert lost == []
    moved = {n: (k, _kind(getattr(S, n))) for n, k in snap.items() if _kind(getattr(S, n)) != k}
    assert moved == {}


# ---- P1 -------------------------------------------------------------------------------------------------------------------
def test_describe_is_byte_for_byte_what_it_was():
    sha = hashlib.sha256(json.dumps(S.describe(), sort_keys=True).encode("utf-8")).hexdigest()
    assert sha == (MODELS / "describe.sha").read_text(encoding="utf-8").strip()


def _fresh(code):
    env = dict(os.environ)
    env.pop("PYTEST_ADDOPTS", None)
    return subprocess.run([sys.executable, "-c", code], cwd=str(HERE), env=env, capture_output=True, text=True)


@pytest.mark.parametrize("order", [("layer_consts", "layer_models", "layer_schema"), ("layer_consts", "layer_schema", "layer_models"),
                                   ("layer_models", "layer_consts", "layer_schema"), ("layer_models", "layer_schema", "layer_consts"),
                                   ("layer_schema", "layer_consts", "layer_models"), ("layer_schema", "layer_models", "layer_consts")])
def test_import_in_both_orders(order):
    r = _fresh("; ".join("import " + m for m in order) + "; import layer_schema as S, layer_consts as K; assert S.LAYER_NAMES is K.LAYER_NAMES")
    assert r.returncode == 0, r.stderr


def test_layer_consts_imports_nothing_of_the_app():
    r = _fresh("import sys; import layer_consts; app = [m for m in sys.modules if m in ('layer_schema', 'website_dept', 'engine_runtime', "
               "'j2_runtime', 'functions_view', 'layers')]; assert not app, app")
    assert r.returncode == 0, r.stderr


def test_the_constants_that_stay_stay_in_layer_schema():
    import layer_consts as K
    for name in ("MODE", "OWNERSHIP_MODE", "NEVER_REFUSE", "REFUSED", "ANY", "SCHEMA_VERSION", "HERE", "INTERFACE_SHA"):
        assert name in vars(S)
        assert not hasattr(K, name), name
    for name in K.__all__:
        assert getattr(S, name) is getattr(K, name), name


# ---- P2 -------------------------------------------------------------------------------------------------------------------
LEGACY_SHA = "b9ccb1740dc22f6c30b5edf1c4c745ccd58a10cfa004b7010520fe66fbe4374e"


def test_the_oracle_is_frozen():
    import layer_models.legacy as L
    assert hashlib.sha256(json.dumps(L.LEGACY_DEFS, sort_keys=True).encode("utf-8")).hexdigest() == LEGACY_SHA
    assert len(L.LEGACY_DEFS) == 130


def test_the_oracle_gives_the_walkers_answers():
    import layer_models.legacy as L
    n = 0
    for path in sorted(GOLDEN.glob("*.jsonl")):
        name = path.name[:-6]
        for row in _rows(path):
            assert L.oracle(name, row["value"]) == row["faults"]
            n += 1
    assert n > 4500


def test_faults_resolves_a_ref_in_the_defs_it_is_given():
    other = {"thing": S.text(3)}
    assert S.faults(S.ref("thing"), "abcd", defs=other) == ["$: longer than 3"]
    assert S.faults(S.ref("thing"), "abc", defs=other) == []
    assert S.faults(S.ref("name"), "x y", defs=other) == ["$: no definition named name"]       # not DEFS when `defs` is given
    assert S.faults(S.ref("name"), "?") != []                                                   # DEFS when it is not


# ---- P5: the department record and the views --------------------------------------------------------------------------------
def test_every_department_key_has_one_owner_and_one_adapter():
    import layer_models
    from layer_models import department as D, registry
    import layer_models.legacy as L
    layer_models.load()
    want = {k: v["x-owner"] for k, v in L.LEGACY_DEFS["department"]["properties"].items()}
    assert D.OWNERS == want and len(want) == 38
    for key, owner in want.items():
        assert owner in S.LAYER_NAMES
        name = "department." + key
        assert name in registry.DEF_CLASS or name in registry.DEF_TYPE, name       # its own definition
        assert registry.adapter(name) is registry.adapter(name)                     # one adapter, built once
    assert len({id(registry.adapter("department." + k)) for k in want}) == 38        # and each key has its own


def test_a_department_key_is_checked_alone_against_its_own_definition():
    import layer_models
    assert layer_models.validate("department.goal", "x" * 2001) == ["$: longer than 2000"]
    assert layer_models.validate("department.goal", "fine") == []
    assert layer_models.validate("department.layers", {"identity": "identity/v1"}) == []
    assert layer_models.validate("department.layers", {"identity": "nope"}) == ["$.identity: does not match " + S.IMPL_RE]
