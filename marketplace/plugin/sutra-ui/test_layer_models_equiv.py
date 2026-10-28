"""A4-CORE C6: the equivalence harness (qa/a4_equiv.py, qa/a4_record.py) on the six trial definitions."""
import io
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
from pydantic import TypeAdapter

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE / "qa"))
import a4_equiv as Q                                             # noqa: E402
import a4_trial as TR                                            # noqa: E402
import layer_schema as S                                         # noqa: E402
from layer_models.faults import sentences                        # noqa: E402

SIX = sorted(TR.TRIAL)
SEED = 20261027


@pytest.fixture(scope="module")
def reports():
    return Q.check(only=SIX, fuzz_n=500, seed=SEED, out=io.StringIO())


def test_the_samples_of_the_trial_definitions_agree():
    samples = json.loads((HERE / "test_fixtures" / "models" / "trial" / "samples.json").read_text(encoding="utf-8"))
    assert set(samples) == set(TR.EXPORTED)
    for name, pair in samples.items():
        ad = TypeAdapter(TR.EXPORTED[name])
        assert S.validate(name, pair["good"]) == [] == sentences(ad, pair["good"])
        assert S.validate(name, pair["failing"]) != [] and sentences(ad, pair["failing"]) == S.validate(name, pair["failing"])


def test_p1_p2_the_trial_definitions_match_the_oracle(reports):
    assert sorted(reports) == SIX
    for name, rep in reports.items():
        assert rep["inputs"] > 1000 and rep["rejected"] > 500, (name, rep["inputs"], rep["rejected"])
        assert rep["verdict"] == 0, "%s: %s" % (name, rep["first"])
        assert rep["sentences"] == 0, "%s: %s" % (name, rep["first"])
    total = sum(r["inputs"] for r in reports.values())
    assert total > 10000                                          # the trial's own figure was 20,941 over the six


def test_p4_every_keyword_is_hit(reports):
    for name, rep in reports.items():
        assert rep["missed"] == [], "%s has keywords no rejecting input reached: %s" % (name, rep["missed"])
        assert Q.uses(name), name


def test_a_wrong_port_is_caught_with_the_sentences():
    from typing import Annotated
    from layer_models.types import Str

    class Typo(TR.DoneItem):                                      # the bound of `text` is 299, not 300 (a slip of the port)
        __def__ = None
        text: Annotated[str, Str(299, 1)]
    ad = TypeAdapter(Typo)

    def wrong(name, v):
        return sentences(ad, v)
    seed_values = Q.seeds()["identity.done_item"]
    rep = Q.compare("identity.done_item", Q.oracle, wrong, Q.inputs("identity.done_item", seed_values, __import__("random").Random(SEED), 0))
    assert rep["sentences"] > 0                                   # P2 sees the typo; the verdict (P1) is the same but for 300
    first = rep["first"][0]
    assert first["oracle"] != first["port"] and first["value"]    # both lists are in the report
    assert any("longer than 300" in s for f in rep["first"] for s in f["oracle"])
    assert any("longer than 299" in s for f in rep["first"] for s in f["port"])
    assert Q.compare("identity.done_item", Q.oracle, Q.port, [seed_values[0]])["sentences"] == 0


def test_a_port_that_raises_is_a_difference_not_a_crash(monkeypatch):
    monkeypatch.setitem(Q._ADAPTERS, "envelope", type("Boom", (), {"validate_python": lambda self, v: 1 / 0})())
    out = Q.port("envelope", {"calls": 1, "usd": 1})
    assert out and out[0].startswith("EXCEPTION ZeroDivisionError")


def test_the_recorder_writes_what_a_test_validated(tmp_path):
    t = tmp_path / "test_probe.py"
    t.write_text("import layer_schema as S\n"
                 "def test_it():\n"
                 "    assert S.validate('envelope', {'calls': 1, 'usd': 0.5}) == []\n"
                 "    assert S.validate('envelope', {'calls': 1, 'usd': 0.5}) == []\n"
                 "    assert S.faults(S.DEFS['option'], {'id': 'x'}) != []\n"
                 "    assert S.validate('envelope', {'calls': -1}) != []\n"
                 "    S.check('envelope', {'calls': 2, 'usd': 1})\n", encoding="utf-8")
    dest = tmp_path / "rec"
    env = dict(os.environ, PYTHONPATH=os.pathsep.join([str(HERE / "qa"), str(HERE)]))
    env.pop("PYTEST_ADDOPTS", None)
    r = subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", "-p", "a4_record", "--a4-record-dir", str(dest), str(t)],
                       cwd=str(tmp_path), env=env, capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr
    rows = [json.loads(l) for l in (dest / "envelope.jsonl").read_text(encoding="utf-8").splitlines()]
    assert sorted(map(json.dumps, rows)) == sorted(map(json.dumps, [{"calls": 1, "usd": 0.5}, {"calls": -1}, {"calls": 2, "usd": 1}]))
    assert json.loads((dest / "option.jsonl").read_text(encoding="utf-8").strip()) == {"id": "x"}


def test_the_recorder_caps_a_definition_and_a_value(tmp_path):
    import a4_record as R
    R._state["seen"] = {}
    for i in range(R.PER_DEFINITION + 50):
        R._note("envelope", {"calls": i})
    R._note("envelope", {"calls": "x" * (R.MAX_BYTES + 1)})
    assert len(R._state["seen"]["envelope"]) == R.PER_DEFINITION
    R._state["seen"] = {}


def _golden(dirpath, hashseed):
    env = dict(os.environ, PYTHONHASHSEED=str(hashseed))
    r = subprocess.run([sys.executable, str(HERE / "qa" / "a4_equiv.py"), "--write-golden", str(dirpath), "--only", "envelope,identity.done_item,workflow.check"],
                       cwd=str(HERE), env=env, capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    return r.stdout.strip().split()[-1]


def test_the_golden_writer_is_deterministic_and_the_sha_is_stable(tmp_path):
    a, b = _golden(tmp_path / "a", 1), _golden(tmp_path / "b", 2)
    assert a == b and len(a) == 64
    assert (tmp_path / "a" / "CORPUS.sha").read_text(encoding="utf-8").strip() == a
    for f in ("envelope", "identity.done_item", "workflow.check"):
        pa, pb = tmp_path / "a" / (f + ".jsonl"), tmp_path / "b" / (f + ".jsonl")
        assert pa.read_text(encoding="utf-8") == pb.read_text(encoding="utf-8")
        lines = pa.read_text(encoding="utf-8").splitlines()
        assert 30 <= len(lines) <= 150
        row = json.loads(lines[0])
        assert row["faults"] == S.validate(f, row["value"])
    # each sentence template once, in the lines that are not the seeded ones
    seen = set()
    for l in (tmp_path / "a" / "identity.done_item.jsonl").read_text(encoding="utf-8").splitlines()[:-30]:
        fresh = {Q.template(s) for s in json.loads(l)["faults"]} - seen
        assert fresh, "a line that shows no template the earlier lines did not: %s" % l[:120]
        seen |= fresh
    # the golden corpus moves with the oracle
    sha_before = Q.write_golden(tmp_path / "c", names=["envelope"])
    assert sha_before == Q.write_golden(tmp_path / "d", names=["envelope"])
    assert sha_before != Q.write_golden(tmp_path / "e", names=["option"])


def test_templates_take_out_places_and_numbers():
    assert Q.template("$.a.b[2]: shorter than 3") == Q.template("$.x: shorter than 12") == "shorter than N"
    assert Q.template("$.a: is not one of a, b, c") == Q.template("$.a: is not one of x, y") == "is not one of _"
    assert Q.template("$.a: fits none of its shapes (below 0)") == "fits none of its shapes (_)"


def test_mixins_lists_a_repeated_field():
    rows = Q.mixins()
    found = {f: ds for f, _, ds in rows}
    assert "at" in found and len(found["at"]) >= 3
    assert all(len(ds) >= 3 for _, _, ds in rows)
    sch = next(s for f, s, _ in rows if f == "at")
    assert all(S.DEFS[d]["properties"]["at"] == sch for d in found["at"])
    assert rows == sorted(rows, key=lambda r: (-len(r[2]), r[0]))


def test_the_benchmark_reports_the_ratio():
    out = io.StringIO()
    res = Q.bench(only=["identity.ask", "workflow"], n=300, out=out)
    assert set(res) == {"identity.ask", "workflow"} and "ratio" in out.getvalue()
    assert sum(p for _, p in res.values()) < sum(o for o, _ in res.values()), out.getvalue()      # P6: not slower


def test_the_cli_runs_check_and_exits_clean():
    r = subprocess.run([sys.executable, str(HERE / "qa" / "a4_equiv.py"), "--check", "--only", "envelope,option", "--fuzz", "50"],
                       cwd=str(HERE), capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "TOTAL inputs" in r.stdout and "differences 0" in r.stdout


# ---- A4-PORT: the definitions of layer_models against the frozen oracle (A4.3.7: P1 to P4) ------------------------------
import layer_models                                               # noqa: E402
import layer_models.legacy as LEGACY                              # noqa: E402
from layer_models import defs as DEFS_PORTED                       # noqa: E402

PORTED = list(DEFS_PORTED.NAMES)
GOLDEN = HERE / "test_fixtures" / "models" / "corpus" / "golden"
WRITERS = HERE / "test_fixtures" / "models" / "corpus" / "writers"


@pytest.fixture(scope="module")
def ported_reports():
    return Q.check(only=PORTED, fuzz_n=500, seed=SEED, out=io.StringIO())


def test_p1_p2_every_ported_definition_gives_the_oracles_verdict_and_sentences(ported_reports):
    assert sorted(ported_reports) == sorted(PORTED)
    for name, rep in ported_reports.items():
        assert rep["inputs"] > 100 and rep["rejected"] > 20, (name, rep["inputs"], rep["rejected"])
        assert rep["verdict"] == 0, "%s: %s" % (name, rep["first"])
        assert rep["sentences"] == 0, "%s: %s" % (name, rep["first"])


def test_p4_every_keyword_of_every_ported_definition_is_hit(ported_reports):
    for name, rep in ported_reports.items():
        assert rep["missed"] == [], "%s has keywords no rejecting input reached: %s" % (name, rep["missed"])


@pytest.mark.parametrize("name", PORTED)
def test_p3_the_export_is_the_literal_definition(name):
    assert json.loads(json.dumps(layer_models.export_all()[name])) == json.loads(json.dumps(LEGACY.LEGACY_DEFS[name]))


def test_export_all_keeps_the_interfaces_order():
    assert list(layer_models.export_all()) == [n for n in LEGACY.LEGACY_DEFS if n in set(PORTED)]


def test_the_golden_corpus_goes_through_the_classes_to_the_same_sentences():
    n = 0
    for name in PORTED:
        for line in (GOLDEN / (name + ".jsonl")).read_text(encoding="utf-8").splitlines():
            row = json.loads(line)
            assert layer_models.validate(name, row["value"]) == row["faults"], (name, row["value"])
            n += 1
    assert n >= len(PORTED) * 5


def test_the_writers_values_go_through_the_classes_to_the_oracles_answers():
    n = 0
    for name in PORTED:
        for line in (WRITERS / (name + ".jsonl")).read_text(encoding="utf-8").splitlines():
            if line.strip():
                v = json.loads(line)
                assert layer_models.validate(name, v) == LEGACY.oracle(name, v), (name, v)
                n += 1
    assert n >= len(PORTED)


def test_no_error_type_is_left_without_a_sentence(ported_reports):
    from layer_models import faults
    assert faults.UNMAPPED == set()


def test_an_unknown_name_is_answered_as_the_walker_answers():
    assert layer_models.validate("no.such", {}) == LEGACY.oracle("no.such", {}) == ["$: no definition named no.such"]
