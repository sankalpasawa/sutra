"""test_a5_verify.py -- amendment A5 proved together (PRD A5.8 P5, steps P5.1 to P5.6): what the seeded walk looks at, how long the graph
takes to read on 300 tasks, the 17 models against the oracle, the schema version, link-only by default, the Root default left classic, and
the documents. The seeder and the graph run in processes of their own (a record of their own under tmp), so no module state or home leaks
into this process; nothing here calls a model."""
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
PY = sys.executable
DESIGN = HERE / "design"

READ = r"""
import json, time
import shadow_graph as G
import mission_engine as ME
t = time.perf_counter(); g = G.build(); cold = time.perf_counter() - t
t = time.perf_counter(); G.build(); warm = time.perf_counter() - t
ms = ME.MissionStore().list()
print(json.dumps({"cold": cold, "warm": warm, "truncated": g["truncated"], "tasks": sum(1 for n in g["nodes"] if n["kind"] == "task"),
                  "edges": [e for e in g["edges"] if e["kind"] in ("uses", "spawned")], "n_missions": len(ms),
                  "decisions": [m["department_decision"] for m in ms if m.get("department_decision")],
                  "executors": sorted({str(m.get("executor")) for m in ms})}))
"""


@pytest.fixture(scope="module")
def seeded(tmp_path_factory):
    rec = tmp_path_factory.mktemp("a5rec")
    env = dict(os.environ, SUTRA_WEBSITE_OFFLINE="1", SUTRA_MOTOR_OFF="1")
    for k in ("SUTRA_SHADOW_DEPT_EXECUTE",):
        env.pop(k, None)
    out = subprocess.run([PY, str(HERE / "qa" / "walks" / "a5_seed.py"), str(rec), "--missions", "300"], cwd=HERE, env=env,
                         capture_output=True, text=True, timeout=300)
    assert out.returncode == 0, out.stderr[-1500:]
    refs = dict(line.split(" ", 1) for line in out.stdout.splitlines())
    env.update(SUTRA_SHADOW_HOME=str(rec / "shadow"), SUTRA_UI_SETTINGS=str(rec / "settings.json"), SUTRA_NATIVE_DEPT_HOME=str(rec / "native"),
               SUTRA_NATIVE_HOME=str(rec / "registry"))
    read = subprocess.run([PY, "-c", READ], cwd=HERE, env=env, capture_output=True, text=True, timeout=120)
    assert read.returncode == 0, read.stderr[-1500:]
    return refs, json.loads(read.stdout.strip().splitlines()[-1])


def test_the_seed_holds_one_department_of_each_kind_and_three_decisions(seeded):
    refs, got = seeded
    assert all(refs[k].startswith("dref-") for k in ("root", "default", "organic", "website"))
    by = {d["mission_id"]: d for d in got["decisions"]}
    assert by[refs["task_use"]]["final_action"] == "use" and by[refs["task_use"]]["final_ref"] == refs["default"]
    assert by[refs["task_spawn"]]["final_action"] == "create" and by[refs["task_spawn"]]["result_ref"]
    assert by[refs["task_none"]]["final_action"] == "none"


def test_link_only_is_the_default(seeded):
    _, got = seeded
    assert got["decisions"] and all(d["mode"] == "link" for d in got["decisions"])
    assert "department" not in got["executors"], "no task is run by a department: the worker still runs"


def test_the_graph_draws_uses_and_spawned_each_with_its_reason(seeded):
    refs, got = seeded
    kinds = {e["kind"]: e for e in got["edges"]}
    assert set(kinds) == {"uses", "spawned"}
    assert all(e["reason"] for e in kinds.values())
    assert kinds["uses"]["target"] == "dept:" + refs["default"]
    assert not any(e["source"] == "task:" + refs["task_none"] for e in got["edges"])


def test_the_graph_reads_300_tasks_inside_a_budget_and_keeps_the_cap(seeded):
    _, got = seeded
    assert got["n_missions"] >= 303
    assert got["tasks"] <= 60 and got["truncated"] is True, "the 60-task cap applies after the read (A5.7 rule 8)"
    assert got["cold"] < 2.0, "a cold read of 300 seeded tasks: %.3f s" % got["cold"]
    assert got["warm"] < 0.05, "a memo hit: %.4f s" % got["warm"]


def test_the_interface_is_at_version_2_with_a_no_op_migration():
    import layer_schema as S
    assert S.SCHEMA_VERSION == 2 and 1 in S.INTERFACE_SHA and 2 in S.INTERFACE_SHA and S.INTERFACE_SHA[1] != S.INTERFACE_SHA[2]
    old = {"schema_version": 1, "ref": "dref-x", "extra_key_kept": 7}
    new = S.migrate("dept.row", old)
    assert new == dict(old, schema_version=2) and old["schema_version"] == 1, "a copy, stamped 2, nothing else touched"
    assert S.migrate("dept.row", dict(old, schema_version=2)) == dict(old, schema_version=2)
    assert S.migrate("dept.row", dict(old, schema_version=3))["schema_version"] == 3, "a newer record is read as it is, never rewritten"


def test_the_17_models_are_built_in_read_only_and_neither_extensible_nor_nestable():
    import layer_models.spec as SP
    import layer_schema as S
    assert len(SP.SEALED_CORE) == 17 and len(set(SP.SEALED_CORE)) == 17
    assert all(n in S.DEFS for n in SP.SEALED_CORE)
    assert not set(SP.SEALED_CORE) & (set(SP.EXTENSIBLE_CORE) | set(SP.NESTABLE_CORE))


def test_each_of_the_17_models_matches_the_oracle():
    import layer_models.spec as SP
    out = subprocess.run([PY, str(HERE / "qa" / "a4_equiv.py"), "--check", "--only", ",".join(SP.SEALED_CORE)], cwd=HERE,
                         capture_output=True, text=True, timeout=600)
    assert out.returncode == 0, (out.stdout + out.stderr)[-1500:]
    assert "differences 0" in out.stdout.splitlines()[-1]
    assert sum(1 for l in out.stdout.splitlines() if "verdict differences 0  sentence differences 0" in l) >= 17


def test_root_keeps_the_classic_chat_until_a_setup_conversation_has_been_walked():
    js = (HERE / "static" / "js" / "25-j2view.js").read_text(encoding="utf-8")
    assert "const J2_ROOT_DEFAULT = false;" in js
    walk = (HERE / "qa" / "walks" / "a5-e2e.sh").read_text(encoding="utf-8")
    assert "A5_REAL_SETUP" in walk and "J2_ROOT_DEFAULT" in walk
    rec = (HERE / "qa" / "shots" / "a5" / "root-setup.txt").read_text(encoding="utf-8")
    assert rec.startswith("root setup in the J2 page: "), "the walk's result is on record, PASS or FAIL"


def test_the_walk_scripts_are_in_place_and_parse():
    for f in ("a5-e2e.sh",):
        assert subprocess.run(["bash", "-n", str(HERE / "qa" / "walks" / f)]).returncode == 0
    assert subprocess.run(["node", "--check", str(HERE / "qa" / "walks" / "a5-walk.js")]).returncode == 0
    shots = sorted(p.name for p in (HERE / "qa" / "shots" / "a5").glob("*.png"))
    for stem in ("graph-overview", "graph-focus", "j2-default", "j2-organic", "j2-root"):
        for w in ("1280", "390"):
            assert "%s-%s.png" % (stem, w) in shots



def test_the_documents_say_what_was_built():
    a5 = (DESIGN / "PRD-FIVE-FUNCTIONS-A5.md").read_text(encoding="utf-8")
    prd = (DESIGN / "PRD-FIVE-FUNCTIONS.md").read_text(encoding="utf-8")
    log = (DESIGN / "PRD-FIVE-FUNCTIONS-DECISIONS.md").read_text(encoding="utf-8")
    assert "Built, merged 2026-10-29" in a5.splitlines()[4]
    assert "## Build status" in a5
    status = prd[prd.index("### M13 "):prd.index("### M13 ") + 1200]
    assert "| **Status** | built" in status
    rows = [l for l in log.splitlines() if l.startswith("| A5-")]
    assert len(rows) == 16 and not [l for l in rows if "not built" in l]
    for f in ("PRD-FIVE-FUNCTIONS-A1.md", "PRD-FIVE-FUNCTIONS-A4.md"):
        assert "schema version 2" in (DESIGN / f).read_text(encoding="utf-8")
    notes = (DESIGN / "RELEASE-NOTES-A5.md").read_text(encoding="utf-8")
    assert "rolled back" in notes and "schema_version" in notes and "link-only" in notes
