"""Nothing of J2 is lost (work package E1, engine design section 8, ENG-02): every file and symbol of `FEATURES` exists in the
vendored tree, the 8 loop steps and the 17 chips are all there, and every flag is a real engine setting."""
import ast
import functools
from pathlib import Path

import pytest

from sutra_app.engine.features import FEATURES, STEP_IDS, by_id
from sutra_app.engine.spec import EngineSettings

ENGINE = Path(__file__).resolve().parents[2] / "sutra_app" / "engine"


@functools.lru_cache(maxsize=None)
def defined(path: Path) -> frozenset:
    """Names a Python file defines at any depth: defs, classes, assignment targets (J2 constants), methods."""
    names = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names.add(node.name)
        elif isinstance(node, ast.Assign):
            names |= {t.id for t in node.targets if isinstance(t, ast.Name)}
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            names.add(node.target.id)
    return frozenset(names)


def test_the_8_steps_and_the_17_chips_and_the_extras_row_are_present():
    kinds = [f.kind for f in FEATURES]
    assert (kinds.count("step"), kinds.count("chip"), kinds.count("extra")) == (8, 17, 1)
    assert tuple(f.id for f in FEATURES if f.kind == "step") == STEP_IDS == tuple(f"J2.{c}" for c in "abcdefgh")
    assert len(by_id()) == len(FEATURES), "ids are unique"


@pytest.mark.parametrize("feature", FEATURES, ids=lambda f: f.id)
def test_every_file_of_a_feature_exists(feature):
    for rel in feature.files:
        path = ENGINE / rel
        assert (path.is_dir() and any(path.iterdir())) if rel.endswith("/") else path.is_file(), rel


@pytest.mark.parametrize("feature", FEATURES, ids=lambda f: f.id)
def test_every_symbol_of_a_feature_is_defined_in_its_file(feature):
    for file, name in feature.symbols:
        assert file in feature.files, f"{name} is named for {file}, which the feature does not list"
        assert name in defined(ENGINE / file), f"{file} does not define {name}"


def test_the_symbols_of_later_packages_are_marked_as_later():
    later = [(f.id, file) for f in FEATURES for file, _ in f.later]
    assert later == [("extras", "api/reply.py")]


def test_every_flag_is_an_engine_setting():
    fields = set(EngineSettings.model_fields)
    for feature in FEATURES:
        assert set(feature.flags) <= fields, (feature.id, set(feature.flags) - fields)
