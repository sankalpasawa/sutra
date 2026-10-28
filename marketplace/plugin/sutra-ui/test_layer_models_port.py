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
