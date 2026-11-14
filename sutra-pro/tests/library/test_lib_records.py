"""The J2 record catalogue and `gate_record` (library design section 10, flow F6, decision D47; work package L8), the full
registry (`sutra_app.library.all`) and the checks that need every module at once.

Three kinds of test. The GOLDEN ones run the vendored J2 engine in mock mode in a child process (its module state and J2_*
flags must not touch this process) and push every JSON file of the run folder through `gate_record` in STRICT mode: what J2
writes is what the catalogue accepts, per-run template copies included (J2 sync 33aeeda). The HAND-BUILT ones break one rule
of one file at a time. The REGISTRY ones sweep every library class for the design rules 3 and 7 and prove that the function
specs were really verified."""
import ast
import copy
import json
import logging
import os
import subprocess
import sys
import textwrap
from pathlib import Path
from types import SimpleNamespace

import pytest
from factories_atom import fields as atom_fields
from factories_atom import opened
from factories_node import function_dict, stored_edge
from factories_org import make_chart

import sutra_app.library.all as library
from sutra_app.engine import hooks
from sutra_app.library import records as R
from sutra_app.library.base import aliased_fields, unbounded_fields
from sutra_app.library.chat import BASE_KEYS, META_KEYS
from sutra_app.library.gate import GATE, Checked, GateError
from sutra_app.library.node import load_function_specs
from sutra_app.library.registry import REGISTRY, RegistryError
from sutra_app.library.wire import WIRE_FILES, WIRE_PAYLOADS
from sutra_app.library.workflow import registered_from_j2

REPO = Path(__file__).resolve().parents[2]

# ---- the golden runs: one child process per scenario -------------------------------------------------------------------------
HARNESS = textwrap.dedent(r'''
    import importlib.util, json, os, shutil, sys, time
    from pathlib import Path
    repo, out, scenario = Path(sys.argv[1]), Path(sys.argv[2]), sys.argv[3]
    spec = importlib.util.spec_from_file_location("rec", repo / "scripts" / "record_api_shapes.py")
    rec = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(rec)
    base = out / "work"
    shutil.copytree(repo / "sutra_app" / "engine" / "seed" / "library", base / "library")
    for name in list(os.environ):
        if name.startswith(("J2_", "STUDIO_")):
            del os.environ[name]
    env = {**rec.SCENARIO_ENV, "J2_RUNS_DIR": base / "runs", "J2_MEMORY_FILE": base / "memory" / "lessons.jsonl",
           "J2_PLAYBOOK_FILE": base / "memory" / "playbooks.jsonl", "J2_LIBRARY_DIR": base / "library"}
    if scenario == "board":
        env["J2_FORCE_QUESTION"] = "identity,adaptation,priority,coordination,audit,W-2,W-3,W-4,W-5,hours,menu"
    if scenario == "late":      # realization on and a forced audit failure: the late judge scores the fix Priority is shown (sync 4, D145)
        env.update(J2_REALIZATION="1", J2_FORCE_AUDIT_FAIL="1")
        del env["J2_FORCE_QUESTION"]
    if scenario == "auto":      # Decide for me answers the questions a vague brief raises, in the Requester's name (sync 4)
        env.update(J2_DECIDE_FOR_ME="1")
        del env["J2_FORCE_QUESTION"]
    for key, value in env.items():
        os.environ[key] = str(value)
    from sutra_app.engine import llm
    llm.configure(mock=True)
    from sutra_app.engine import j2, j2_template_lib
    rec.fake_chrome(j2.j2_check)
    run = j2.J2Run(run_dir=base / "runs" / "j2-20261104-100004-7f3a")
    brief = rec.BREW_LAB
    if scenario == "prd":
        run.set_output("prd")
        brief = "Write a PRD for QuickQueue, a mobile app that lets clinic patients join a waiting line remotely. Users: patients at small clinics and the front-desk staff who manage the line. Problem: patients wait 45 minutes on average in crowded waiting rooms. Must-have features: join the queue from a phone, live position updates, SMS alert when 2 patients are ahead, staff dashboard to call the next patient. Constraints: works on low-end Android phones; no patient health data stored. Success: average in-room wait under 10 minutes; 60% of patients join remotely within 3 months."
    if scenario == "auto":
        brief = "a website for my cafe"
    assert run.user_says(brief) is True
    end = time.time() + 90
    while run.status != "waiting" or run.lock.locked():      # the lock is held while Decide for me answers and goes on
        assert time.time() < end, "the run did not stop"
        time.sleep(0.003)
    reviewer = getattr(run, "review_thread", None)      # J2 writes the report and artifacts.json after "waiting" from a thread (sync 6): wait as the host does (D179)
    if reviewer is not None:
        reviewer.join(60)
    shutil.copytree(run.dir, out / "run")
    (out / "run_templates.json").write_text(json.dumps(j2_template_lib.run_templates(str(run.dir))))
''')


def run_scenario(scenario: str, folder: Path) -> Path:
    folder.mkdir(parents=True)
    env = {k: v for k, v in os.environ.items() if not k.startswith(("J2_", "STUDIO_", "SUTRA_"))}
    env["PYTHONPATH"] = f"{REPO}{os.pathsep}{env['PYTHONPATH']}" if env.get("PYTHONPATH") else str(REPO)
    done = subprocess.run([sys.executable, "-c", HARNESS, str(REPO), str(folder), scenario], env=env, cwd=folder,
                          capture_output=True, text=True, timeout=120)
    assert done.returncode == 0, done.stderr[-3000:]
    return folder


@pytest.fixture(scope="module")
def golden(tmp_path_factory) -> dict[str, Path]:
    base = tmp_path_factory.mktemp("records")
    return {name: run_scenario(name, base / name) for name in ("site", "prd", "board", "late", "auto")}


def documents(run_dir: Path):
    """(relative name, document) for every JSON file and JSON line of a run folder; None for any other file."""
    for path in sorted(run_dir.rglob("*")):
        if not path.is_file():
            continue
        name = path.relative_to(run_dir).as_posix()
        if name.endswith(".jsonl"):
            for line in path.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    yield name, json.loads(line)
        elif name.endswith(".json"):
            yield name, json.loads(path.read_text(encoding="utf-8"))
        else:
            yield name, None


def first(run_dir: Path, name: str):
    return next(doc for n, doc in documents(run_dir) if n == name)


def lines(run_dir: Path, name: str) -> list:
    return [doc for n, doc in documents(run_dir) if n == name]


def mutated(doc, *path_and_value):
    """A deep copy of `doc` with the value at the path replaced (the last argument is the value)."""
    *path, value = path_and_value
    out = copy.deepcopy(doc)
    node = out
    for part in path[:-1]:
        node = node[part]
    node[path[-1]] = value
    return out


def rejected(name: str, data) -> R.RecordRejected:
    with pytest.raises(R.RecordRejected) as info:
        R.gate_record(name, data, mode="strict")
    return info.value


def says(error: R.RecordRejected, path: str, *words: str) -> bool:
    return any(v.path == path and all(w in v.message for w in words) for v in error.violations)


# ============================================ the golden runs ===============================================================
def test_every_json_file_of_a_mock_run_is_accepted_in_strict_mode(golden):
    seen_routes, checked = set(), 0
    for scenario, folder in golden.items():
        for name, doc in documents(folder / "run"):
            route = R.route_for(name)
            if route is None:
                assert R.is_unchecked(name), f"{scenario}: {name} is a J2 file that the catalogue does not know"
                continue
            R.gate_record(name, doc, mode="strict")           # raises RecordRejected on the first violation
            seen_routes.add(route.label)
            checked += 1
    assert checked > 400
    assert {"goal.json, goal.v<N>.json", "workflows.json", "atoms.json", "audits.json", "conflicts.json", "conditions*.json",
            "style.json", "receipts.jsonl", "chat.jsonl", "calls.jsonl", "templates.json", "map.json", "board.json",
            "artifacts.json", "summary.json", "chain.json", "documents.json", "sections.json", "stage-<kind>.json",
            "report.json", "settings.json", "realization.json", "<kind>.json, site/<kind>-v<N>.json",
            "templates/<artifact>/<section>/<slug>@v<N>/spec.json", "templates/<artifact>/<section>/<slug>@v<N>/meta.json",
            "templates/<artifact>/<section>/<slug>@v<N>/schema.json"} <= seen_routes


LATE_KEYS = {"workflow", "revises", "t", "cycle", "calls", "seconds", "score", "weakest", "missing", "rounds", "ready", "zone", "stage", "note"}


def test_a_forced_failure_run_with_the_late_judge_is_accepted_in_strict_mode_and_really_holds_the_new_records(golden):
    """D145: with realization on, the fix a forced audit failure brings is scored by the late judge. The strict test above passed every file
    and line of this run; this one proves the run holds what strict mode used to refuse: `late`, the chat line that names it with `judge`,
    and the workflow row with `judge`, `stage_from`, `certainty` and `certainty_from`."""
    run = golden["late"] / "run"
    real = first(run, "realization.json")
    assert real["late"] and all(set(entry) == LATE_KEYS for entry in real["late"])
    judged = [m for m in lines(run, "chat.jsonl") if "judge" in m]
    assert [m["judge"] for m in judged] == [e["workflow"] for e in real["late"]] and all(m["who"] == "system" for m in judged)
    rows = first(run, "workflows.json")
    row = next(w for w in rows if w["name"] == real["late"][0]["workflow"])
    assert row["judge"]["score"] == real["late"][0]["score"] and {"stage_from", "certainty", "certainty_from"} <= set(row)
    assert R.gate_record("workflows.json", rows, mode="strict") is None
    assert [r["version"] for r in rows if r["name"] == "Plan"] == [0], "the Plan workflow makes no site version"


def test_a_registered_late_row_is_accepted_and_keeps_the_keys_the_workflow_model_has(golden):
    """`registered_from_j2` copies named keys only: J2's judge, stage_from and certainty_from are its own record of the placement and are not
    part of the library's workflow, but the row passes, with its stage, version and what it revises."""
    run = golden["late"] / "run"
    rows = first(run, "workflows.json")
    row = next(w for w in rows if "judge" in w)
    kept = registered_from_j2(row)
    assert (kept.id, kept.stage, kept.version, kept.revises) == (row["id"], row["stage"], row["version"], row["revises"])
    assert not {"judge", "stage_from", "certainty_from"} & set(kept.model_dump())
    plan = registered_from_j2(next(w for w in rows if w["name"] == "Plan"))
    assert plan.version == 0, "version 0 is the Plan workflow of a realization run"


def test_a_workflow_version_may_be_zero_and_never_negative(golden):
    row = next(w for w in first(golden["late"] / "run", "workflows.json") if w["name"] == "Plan")
    assert registered_from_j2({**row, "version": 0}).version == 0
    with pytest.raises(Exception) as error:
        registered_from_j2({**row, "version": -1})
    assert "version" in str(error.value)


def test_decide_for_me_leaves_settings_json_and_flagged_answers_that_strict_mode_accepts(golden):
    """Sync 4: switched on, Decide for me writes settings.json and posts the Requester's answers with `auto` and `auto_label`."""
    run = golden["auto"] / "run"
    assert first(run, "settings.json") == {"decide_for_me": True}
    route = R.route_for("settings.json")
    assert route.family == "run_file.object" and route.label == "settings.json"
    assert R.gate_record("settings.json", {"decide_for_me": True}, mode="strict").family == "run_file.object"
    assert R.gate_record("settings.json", {"decide_for_me": False}, mode="strict").family == "run_file.object"
    answers = [m for m in lines(run, "chat.jsonl") if m.get("who") == "user" and m.get("auto")]      # `auto` is older: code's own system lines carry it too
    assert answers and all(m.get("auto_label") for m in answers)
    for line in answers:
        assert R.gate_record("chat.jsonl", line, mode="strict").family == "run_message"


def test_a_run_without_decide_for_me_writes_no_settings_file(golden):
    assert not (golden["site"] / "run" / "settings.json").exists() and not (golden["late"] / "run" / "settings.json").exists()


def test_the_first_chat_line_is_a_run_header_and_every_other_line_a_run_message(golden):
    chat = lines(golden["site"] / "run", "chat.jsonl")
    assert chat[0].get("meta") is True and all("who" in line for line in chat[1:])
    assert R.gate_record("chat.jsonl", chat[0], mode="strict").family == "run_header"           # the run header, not a message
    assert R.gate_record("chat.jsonl", chat[1], mode="strict").family == "run_message"


def test_a_run_keeps_its_own_copy_of_every_template_it_used(golden):
    run = golden["site"] / "run"
    decisions = first(run, "templates.json")["decisions"]
    saved = [d["saved"] for d in decisions]
    assert saved and all(isinstance(s, str) and s.startswith("templates/") for s in saved)
    for rel in saved:
        for file in ("spec.json", "meta.json", "schema.json"):
            assert R.route_for(f"{rel}/{file}") is not None and (run / rel / file).is_file()
        assert R.is_unchecked(f"{rel}/model.py")
    kinds = {R.gate_record(f"{rel}/spec.json", json.loads((run / rel / "spec.json").read_text()), mode="strict").kind
             for rel in saved}
    assert kinds == {"generic", "specialised"}


def test_a_decision_may_have_no_saved_key_or_a_null_one(golden):
    doc = first(golden["site"] / "run", "templates.json")
    older = {**doc, "decisions": [{k: v for k, v in d.items() if k != "saved"} for d in doc["decisions"]]}
    nulled = {**doc, "decisions": [{**d, "saved": None} for d in doc["decisions"]]}
    assert R.gate_record("templates.json", older, mode="strict") is not None
    assert R.gate_record("templates.json", nulled, mode="strict") is not None


def test_a_saved_path_that_leaves_the_run_or_names_another_version_is_refused(golden):
    doc = first(golden["site"] / "run", "templates.json")
    for index, bad in enumerate(("../outside", "/abs/templates/x", "templates/website/section/other@v9")):
        error = rejected("templates.json", mutated(doc, "decisions", index, "saved", bad))
        assert [(v.code, v.path) for v in error.violations] == [("saved_mismatch", f"decisions.{index}.saved")]
    nodecision = mutated(mutated(doc, "decisions", 0, "version", None), "decisions", 0, "saved", "../outside")
    assert says(rejected("templates.json", nodecision), "decisions.0.saved", "pattern")      # no version: the model's pattern judges


def test_the_run_templates_api_rows_pass_the_template_run_family(golden):
    rows = json.loads((golden["site"] / "run_templates.json").read_text())
    assert rows and {r["source"] for r in rows} <= {"from this run", "from library", "not recorded"} and "from this run" in {r["source"] for r in rows}
    for row in rows:
        assert GATE.check("template.run", row).model.source == row["source"]
    with pytest.raises(GateError):
        GATE.check("template.run", mutated(rows[0], "source", "from somewhere"))


def test_a_template_file_with_the_old_schema_string_is_refused(golden):
    doc = first(golden["site"] / "run", "templates.json")
    assert says(rejected("templates.json", mutated(doc, "schema", "template-library/0")), "", "schema must be")


# ============================================ the catalogue =================================================================
SPEC_FILES = ["settings.json", "goal.json", "goal.v2.json", "workflows.json", "atoms.json", "audits.json", "conflicts.json", "conditions.json",
              "conditions-prd.json", "style.json", "memory/lessons.jsonl", "receipts.jsonl", "realization.json", "map.json",
              "board.json", "artifacts.json", "summary.json", "chat.jsonl", "calls.jsonl", "templates.json",
              "templates/website/section/brew-lab-core@v2/spec.json", "templates/website/section/brew-lab-core@v2/meta.json",
              "templates/website/section/brew-lab-core@v2/schema.json", "prd.json", "site/website-v3.json", "chain.json",
              "documents.json", "sections.json", "stage-prd.json", "report.json", "change.json", "./goal.json",
              "timing.json", "autofix.json", "deliverables.json", "input_cuts.json", "stage-business_report.json",
              "business_report.json", "site/business_report-v2.json"]


@pytest.mark.parametrize("name", SPEC_FILES)
def test_the_catalogue_knows_the_file(name):
    assert R.route_for(name) is not None


@pytest.mark.parametrize("name", ["", "Other.json", "../goal.json", "a/../goal.json", "/tmp/goal.json", "goal.json.bak",
                                  "templates/website/section/x/spec.json", "templates/website/section/x@v1/model.json"])
def test_the_catalogue_does_not_know_the_file(name):
    assert R.route_for(name) is None


def test_a_windows_style_path_is_read_as_a_path_inside_the_run():
    assert R.route_for("templates\\website\\section\\x@v1\\spec.json") is R.route_for("templates/website/section/x@v1/spec.json")


def test_a_name_of_the_shape_of_a_type_file_is_a_type_file_only_when_it_says_so():
    """The type names are data (D172): `<name>.json` is checked as a type's data file when it carries the schema key of
    one, and is otherwise a file the catalogue does not know (left alone in log mode, refused in strict mode)."""
    assert R.route_for("other.json").family == "artifact_data"
    assert R.check_record("other.json", {"a": 1}) is None
    assert R.gate_record("other.json", {"a": 1}, mode="log") is None
    assert rejected("other.json", {"a": 1}).violations[0].code == "unknown_file"


def test_every_wire_file_is_in_the_catalogue_with_its_payload():
    for file, family in WIRE_FILES.items():
        assert R.route_for(file).family == family and family in WIRE_PAYLOADS


def test_every_family_of_the_catalogue_is_registered():
    names = set()
    for route in R.ROUTES:
        names.add(route.family.split(" ")[0].split(":")[0])
    assert names <= set(REGISTRY.families()), names - set(REGISTRY.families())
    assert set(R.RECORD_FAMILIES) == {r.label for r in R.ROUTES} and len(R.RECORD_FAMILIES) == len(R.ROUTES)


def test_the_files_nobody_models_are_listed_with_a_reason():
    assert [why for _, why in R.UNCHECKED] and all(why for _, why in R.UNCHECKED)
    for name in ("outputs.jsonl", "template_calls.jsonl", "board.jsonl", "report.md", "site/v1.html", "prd.docx",
                 "templates/website/section/x@v1/model.py"):
        assert R.route_for(name) is None and R.is_unchecked(name), name


# ============================================ gate_record: the modes ========================================================
def test_a_good_record_returns_its_checked_document_in_both_modes(golden):
    goal = first(golden["site"] / "run", "goal.json")
    for mode in ("log", "strict"):
        checked = R.gate_record("goal.json", goal, mode=mode)
        assert isinstance(checked, Checked) and checked.family == "goal" and checked.kind == "site" and len(checked.sha256) == 64


def test_log_mode_turns_a_rejection_into_warnings_and_lets_the_write_go_on(golden, caplog):
    bad = mutated(first(golden["site"] / "run", "goal.json"), "statement", "")
    with caplog.at_level(logging.WARNING, logger="sutra.library"):
        warnings = R.gate_record("goal.json", bad, mode="log")
    assert isinstance(warnings, list) and warnings and warnings[0].startswith("record_rejected goal.json: ")
    assert any("record_rejected goal.json" in r.getMessage() and r.levelno == logging.WARNING for r in caplog.records)


def test_log_mode_names_three_violations_and_counts_the_rest():
    warnings = R.gate_record("goal.json", {"statement": "", "business_type": "", "done_when": [], "constraints": 1,
                                           "to_be_confirmed": 2, "x": 1, "y": 2}, mode="log")
    assert len(warnings) == 4 and warnings[-1].endswith("more violations")


def test_strict_mode_raises_a_fatal_record_rejected(golden):
    bad = mutated(first(golden["site"] / "run", "goal.json"), "statement", "")
    error = rejected("goal.json", bad)
    assert error.name == "goal.json" and error.fatal is True and error.violations and "goal.json refused" in str(error)
    assert hooks.is_fatal(error)                      # P8 stops the run on this exact class name


def test_an_unknown_file_is_left_alone_in_log_mode_and_refused_in_strict_mode():
    assert R.gate_record("mystery.json", {"a": 1}, mode="log") is None
    error = rejected("mystery.json", {"a": 1})
    assert error.violations[0].code == "unknown_file"
    assert R.gate_record("outputs.jsonl", {"atom": "W-1.a1"}, mode="strict") is None       # listed, so not unknown


def test_the_mode_comes_from_the_argument_then_the_environment_then_log(monkeypatch):
    monkeypatch.delenv("SUTRA_RECORDS", raising=False)
    assert R.record_mode() == "log" and R.record_mode("STRICT") == "strict"
    monkeypatch.setenv("SUTRA_RECORDS", "strict")
    assert R.record_mode() == "strict" and R.record_mode("log") == "log"
    with pytest.raises(R.RecordRejected):
        R.gate_record("mystery.json", {})
    monkeypatch.setenv("SUTRA_RECORDS", "loud")
    with pytest.raises(RegistryError) as info:
        R.record_mode()
    assert info.value.code == "bad_mode"


def test_a_list_file_checks_every_row_and_names_the_row_in_the_path(golden):
    rows = first(golden["site"] / "run", "workflows.json")
    assert R.gate_record("workflows.json", rows, mode="strict") is None            # a list passes as None, never one Checked
    assert len(R.check_record("workflows.json", rows)) == len(rows) > 1
    assert R.gate_record("workflows.json", rows[:1], mode="strict") is None            # a one-row list is still a list
    broken = mutated(rows, 1, "name", "")
    error = rejected("workflows.json", broken)
    assert error.violations and all(v.path.startswith("1.") or v.path == "1" for v in error.violations)


def test_a_file_of_the_wrong_outer_shape_is_refused():
    assert rejected("workflows.json", {"id": "W-1"}).violations[0].code == "not_a_list"
    assert rejected("goal.json", ["x"]).violations[0].code == "not_an_object"
    assert rejected("change.json", {"a": 1}).violations[0].code == "not_a_list"


def test_what_j2_wrote_is_read_after_a_json_round_trip():
    row = {"id": "N1", "text": "t", "check": "page-parses", "met": True, "evidence": "ok"}
    assert R.gate_record("conditions.json", [row], mode="strict") is None
    assert R.check_record("conditions.json", [row, row])[1].model.id == "N1"
    with pytest.raises(R.RecordRejected) as info:
        R.check_record("report.json", {"x": float("nan")})
    assert info.value.violations[0].code == "not_json"
    with pytest.raises(R.RecordRejected) as info:
        R.check_record("report.json", {"x": object()})
    assert info.value.violations[0].code == "not_json"


def test_a_tuple_in_a_record_is_a_list_in_the_file():
    assert R.check_record("report.json", {"x": (1, 2)})[0].model.content == {"x": [1, 2]}


def test_the_engine_hook_gets_the_library_validator_and_traces_a_rejection(monkeypatch):
    monkeypatch.delenv("SUTRA_RECORDS_HOOK", raising=False)
    traced = []
    writer = SimpleNamespace(trace=lambda t, data=None: traced.append((t, data)), emit=lambda event: None)
    for mode, expect_raise in (("log", False), ("strict", True)):
        validator = hooks.load_validator({"SUTRA_RECORDS": mode})
        assert callable(validator)
        h = hooks.EventHooks(writer, lambda: None, validator=validator)
        if expect_raise:
            with pytest.raises(R.RecordRejected):
                h.record_saved("goal.json", {"statement": ""})
        else:
            warnings = h.record_saved("goal.json", {"statement": "", "business_type": "x", "done_when": ["a"], "constraints": [],
                                                    "to_be_confirmed": []})
            assert warnings and warnings[0].startswith("record_rejected goal.json")
    assert any(t == "record.warning" and d["name"] == "goal.json" for t, d in traced)
    assert hooks.DEFAULT_RECORDS_HOOK == "sutra_app.library.records:gate_record"


# ============================================ one rule of one file at a time ================================================
def test_goal_json_is_a_site_or_a_document_charter_by_its_product_name(golden):
    assert R.gate_record("goal.json", first(golden["site"] / "run", "goal.json"), mode="strict").kind == "site"
    charter = first(golden["prd"] / "run", "goal.json")
    assert "product_name" in charter and R.gate_record("goal.v2.json", charter, mode="strict").kind == "doc"


def test_a_charter_with_no_done_when_is_refused(golden):
    assert rejected("goal.json", mutated(first(golden["site"] / "run", "goal.json"), "done_when", [])).violations


def test_atoms_json_is_an_envelope_of_atom_views(golden):
    doc = first(golden["site"] / "run", "atoms.json")
    assert len(R.check_record("atoms.json", doc)) == len(doc["atoms"]) > 0
    assert says(rejected("atoms.json", {**doc, "schema": "atom/2"}), "schema", "atom/1")
    assert rejected("atoms.json", {**doc, "extra": 1}).violations[0].code == "extra_forbidden"
    assert says(rejected("atoms.json", {**doc, "warnings": [1]}), "warnings")
    assert rejected("atoms.json", mutated(doc, "atoms", 0, "status", "weird")).violations[0].path.startswith("0.")


def test_audits_json_rows_are_results_or_rechecks_by_their_trigger(golden):
    rows = first(golden["site"] / "run", "audits.json")
    assert {c.kind for c in R.check_record("audits.json", rows)} == {"result"}
    recheck = {"trigger": "Q-1", "doc": "prd", "version": 2, "t": "2026-11-04T10:00:00",
               "results": [{"atom": "W-1.a1", "check": "c", "pass": True, "evidence": "ok"}]}
    assert R.check_record("audits.json", [recheck])[0].kind == "recheck"
    assert rejected("audits.json", [{**recheck, "doc": ""}]).violations
    assert rejected("audits.json", mutated(rows, 0, "all_pass", True)).violations[0].path.startswith("0.")


def test_conflicts_and_conditions_are_checked_row_by_row(golden):
    run = golden["site"] / "run"
    assert R.check_record("conflicts.json", first(run, "conflicts.json"))
    assert rejected("conflicts.json", mutated(first(run, "conflicts.json"), 0, "topic", "gossip")).violations
    assert R.check_record("conditions-prd.json", first(run, "conditions.json"))
    assert rejected("conditions.json", mutated(first(run, "conditions.json"), 0, "id", "n1")).violations


def test_style_json_is_the_design_style_guide(golden):
    style = first(golden["site"] / "run", "style.json")
    assert R.gate_record("style.json", style, mode="strict").family == "run_file.object"        # a type's style guide is data (D171)
    assert rejected("style.json", ["not", "an", "object"]).violations


LESSON = {"id": "L-j2-20261104-100004-7f3a-1", "problem": "No menu: the menu is missing", "cause": "The first build left it out",
          "fix": "Menu section", "run": "j2-20261104-100004-7f3a", "cycle": 2, "versions": [1, 2], "workflows": ["W-3"],
          "t": "2026-11-04 10:00:00"}


def test_a_lesson_line_has_no_kind_and_the_catalogue_supplies_it():
    assert R.gate_record("memory/lessons.jsonl", LESSON, mode="strict").kind == "lesson"
    assert R.gate_record("lessons.jsonl", {**LESSON, "output": "prd", "test": True, "mock": True}, mode="strict") is not None
    assert rejected("memory/lessons.jsonl", {**LESSON, "versions": [1]}).violations


def test_receipts_are_check_receipts_output_receipts_or_a_send_record(golden):
    lines_ = lines(golden["site"] / "run", "receipts.jsonl")
    check = next(r for r in lines_ if "check" in r)
    output = next(r for r in lines_ if "expected" in r)
    assert R.gate_record("receipts.jsonl", check, mode="strict").kind == "receipt"
    assert R.gate_record("receipts.jsonl", output, mode="strict").kind == "receipt"
    send = {"atom": "W-9.a1", "type": "deed-send-record", "deed": "milestone_email", "sent": False, "t": "2026-11-04T10:00:00", "by": "code"}
    assert R.check_record("receipts.jsonl", send)[0].family == "run_file.object"
    both = {**check, "expected": "x", "checks": [], "met": True, "kind": "file"}
    assert rejected("receipts.jsonl", both).violations
    assert rejected("receipts.jsonl", {k: v for k, v in check.items() if k not in ("evidence", "check", "type", "pass")}).violations
    assert rejected("receipts.jsonl", {**check, "by": "model"}).violations
    assert rejected("receipts.jsonl", {**output, "check": "c"}).violations


def test_calls_jsonl_lines_carry_the_call_and_its_texts(golden):
    call = lines(golden["site"] / "run", "calls.jsonl")[0]
    assert R.gate_record("calls.jsonl", call, mode="strict").kind == "call_log"
    assert rejected("calls.jsonl", {**call, "fn": ""}).violations
    assert rejected("calls.jsonl", {**call, "surprise": 1}).violations


def test_artifact_data_is_checked_by_shape_for_any_type(golden):
    prd = first(golden["prd"] / "run", "prd.json")
    assert R.gate_record("prd.json", prd, mode="strict").family == "artifact_data"
    assert R.gate_record("site/prd-v6.json", prd, mode="strict") is not None
    assert says(rejected("prd.json", {**prd, "schema": "artifact-schema/9"}), "", "schema must be")
    assert R.gate_record("prd.json", mutated(prd, "sections", "Mystery", {"a": 1}), mode="strict") is not None      # a section is a name: the type's template is J2's
    assert rejected("prd.json", {**prd, "artifact": "Site"}).violations                                           # the kind is a name by shape
    assert rejected("prd.json", mutated(prd, "sections", "Problem", "not an object")).violations
    assert rejected("prd.json", {**prd, "sections": {"": {"a": 1}}}).violations


def test_a_document_of_a_type_that_is_not_one_of_the_first_three_is_accepted_everywhere(golden):
    """A type J2 reads from data (here `business_report`): its data file, its site copy and its stage file are checked."""
    prd = first(golden["prd"] / "run", "prd.json")
    report = {**prd, "template": "Report/1", "artifact": "business_report", "sections": {"Summary": {"text": "t", "assumptions": []}}}
    assert R.gate_record("business_report.json", report, mode="strict").family == "artifact_data"
    assert R.gate_record("site/business_report-v2.json", report, mode="strict") is not None
    assert R.gate_record("stage-business_report.json", {"kind": "business_report", "sections": []}, mode="strict").family == "run_file.object"


def test_the_four_files_a_run_of_sync_5_writes_are_accepted_in_strict_mode():
    timing = {"total_seconds": 12.5, "steps": [{"fn": "identity", "step": 1, "seconds": 1.2, "tokens": {"in": 10, "out": 5}}]}
    assert R.gate_record("timing.json", timing, mode="strict").family == "run_file.object"
    deliverables = {"deliverables": ["a_type"], "reason": "the brief asks for one document", "new": []}
    assert R.gate_record("deliverables.json", deliverables, mode="strict").family == "run_file.object"
    fixes = [{"cycle": 1, "workflow": "W-1", "kind": "heading_list", "detail": "work atom 1: a heading list was repaired"}]
    assert R.check_record("autofix.json", fixes)[0].family == "run_file.list"
    cuts = [{"call": 3, "workflow": "W-2", "input": "the requirements document", "kept": 20000, "chars": 31000}]
    assert R.check_record("input_cuts.json", cuts)[0].family == "run_file.list"
    for name, bad in (("timing.json", [1]), ("deliverables.json", [1]), ("autofix.json", {"a": 1}), ("input_cuts.json", {"a": 1})):
        assert rejected(name, bad).violations, name
    assert R.check_record("autofix.json", []) is not None and R.check_record("input_cuts.json", []) is not None


def test_a_document_file_and_its_site_copy_have_the_same_shape(golden):
    run = golden["site"] / "run"
    assert first(run, "website.json") == first(run, "site/website-v6.json")


def test_chain_rows_name_requirement_component_section_and_atoms(golden):
    chain = first(golden["prd"] / "run", "chain.json")
    assert len(R.check_record("chain.json", chain)) == len(chain) > 0
    assert rejected("chain.json", mutated(chain, 0, "atoms", ["nope"])).violations
    assert rejected("chain.json", mutated(chain, 0, "stray", 1)).violations


def test_the_open_files_are_bounded_json_of_the_right_outer_shape(golden):
    run = golden["prd"] / "run"
    assert R.check_record("documents.json", first(run, "documents.json"))[0].family == "run_file.object"
    assert R.check_record("change.json", [{"id": "CH-1"}])[0].family == "run_file.list"
    assert R.check_record("settings.json", {"decide_for_me": True})[0].family == "run_file.object"
    deep = {}
    node = deep
    for _ in range(40):
        node["x"] = {}
        node = node["x"]
    assert rejected("report.json", deep).violations


def test_the_wire_files_are_checked_as_their_wire_documents(golden):
    run = golden["site"] / "run"
    for name, family in WIRE_FILES.items():
        if (run / name).is_file():
            assert R.gate_record(name, first(run, name), mode="strict").family == family
    summary = first(run, "summary.json")
    assert rejected("summary.json", mutated(summary, "budget", "granted", -1)).violations


# ============================================ the library as a whole ========================================================
def test_all_imports_every_module_and_registers_the_catalogue_payloads():
    families = set(library.families())
    for name in ("org_chart", "chart_change", "goal", "department", "evaluation", "identity", "adaptation", "priority",
                 "coordination", "audit", "conflict", "lesson", "atom", "atom_ledger_row", "atom_view", "node", "edge", "workflow",
                 "template", "function_specs", "run_message", "map", "board", "story", "agent", "artifacts", "artifacts_tree",
                 "realization", "run_summary", "receipt", "call_log", "condition_result", "artifact_data", "chain_row",
                 "run_file.object", "run_file.list", "template.file", "template.meta", "template.decision", "template.run"):
        assert name in families, name
    assert not [f for f in families if f.startswith("artifact.")]               # the section models are retired (D171)


def test_all_does_not_freeze_the_registry_and_freeze_closes_it():
    assert library.REGISTRY is REGISTRY and library.GATE is GATE
    assert not REGISTRY.frozen
    from sutra_app.library.registry import ModelRegistry
    mine = ModelRegistry()
    mine.freeze()
    assert mine.frozen
    with pytest.raises(RegistryError) as info:
        mine.register_payload("late", 1, R.RunObject)
    assert info.value.code == "frozen"


def test_all_freeze_closes_the_apps_registry(monkeypatch):
    calls = []
    monkeypatch.setattr(REGISTRY, "freeze", lambda: calls.append("freeze"))
    library.freeze()
    assert calls == ["freeze"]


def library_classes():
    seen = {}
    for family in REGISTRY.families():
        for version in REGISTRY.versions(family):
            for cls in REGISTRY.kinds(family, version).values():
                if cls.__module__.startswith("sutra_app.library"):          # the orchestrator registers families of its own
                    seen[cls] = (family, version)
    return seen


def test_every_library_string_and_list_is_bounded():
    classes = library_classes()
    assert len(classes) > 55
    assert {name: unbounded_fields(cls) for cls, _ in classes.items() if unbounded_fields(cls) for name in [cls.__name__]} == {}


def test_only_python_keywords_and_the_j2_schema_key_are_aliased():
    allowed = {(cls.__name__, "schema") for cls in [*WIRE_PAYLOADS.values()]} | {("AtomView", "schema")}
    found = {tuple(a) for cls in library_classes() for a in aliased_fields(cls)}
    assert found and found <= allowed, found - allowed


def test_the_function_specs_were_verified_against_the_full_registry():
    specs = load_function_specs()
    references = [(s.function, t.name, ref.name) for s in specs.specs.values() for t in s.atom_templates for ref in t.checks]
    kinds = [(s.function, k.kind) for s in specs.specs.values() for k in s.task_kinds if k.reply_family]
    assert len(specs.specs) == 5 and len(references) >= 20 and len(kinds) >= 10
    arity_calls = []
    from sutra_app.library.atom import check_arity

    def spy(name):
        arity_calls.append(name)
        return check_arity(name)
    assert REGISTRY.verify_refs(check_arity=spy) == [] and len(arity_calls) == len(references)
    assert library.verify() == []


def test_a_broken_reply_reference_is_found_by_the_full_registry_check():
    specs = load_function_specs()
    broken = copy.deepcopy(specs.model_dump())
    first_kind = next(k for s in broken["specs"].values() for k in s["task_kinds"] if k["reply_family"])
    first_kind["reply_family"] = "no_such_family"
    from sutra_app.library.node import FunctionSpecs
    found = REGISTRY.verify_refs(FunctionSpecs.model_validate(broken))
    assert [v.code for v in found] == ["unknown_reply_family"]


# ============================================ the shipped cross rules on the real families ==================================
class Store(dict):
    def get(self, family, id):
        return super().get((family, id))


def test_an_edge_needs_both_of_its_nodes_in_the_store():
    edge = stored_edge().model_dump(mode="json")
    with pytest.raises(GateError) as info:
        GATE.check("edge", edge, ctx=Store())
    assert info.value.stage == "cross" and [v.code for v in info.value.violations] == ["unknown_node", "unknown_node"]
    nodes = Store({("node", "sales.priority"): object(), ("node", "sales.coordination"): object()})
    assert GATE.check("edge", edge, ctx=nodes).kind == "depends_on"


def test_a_node_names_a_stored_department():
    data = function_dict()
    with pytest.raises(GateError) as info:
        GATE.check("node", data, ctx=Store())
    assert [v.code for v in info.value.violations] == ["unknown_department"]
    with pytest.raises(GateError) as info:
        GATE.check("node", data, ctx=Store({("node", "sales"): SimpleNamespace(kind="division")}))
    assert [v.code for v in info.value.violations] == ["not_a_department"]
    assert GATE.check("node", data, ctx=Store({("node", "sales"): SimpleNamespace(kind="department")})).kind == "priority"


def test_a_department_record_needs_the_chart_to_hold_that_department():
    record = {"kind": "department", "id": "sales", "home_dir": "departments/sales", "ts_created": 1}
    with pytest.raises(GateError) as info:
        GATE.check("department", record, ctx=Store())
    assert [v.code for v in info.value.violations] == ["no_chart"]
    chart = make_chart({"web": {}})
    with pytest.raises(GateError) as info:
        GATE.check("department", record, ctx=Store({("org_chart", "chart"): chart}))
    assert [v.code for v in info.value.violations] == ["department_not_in_chart"]
    assert GATE.check("department", {**record, "id": "web", "home_dir": "departments/web"}, ctx=Store({("org_chart", "chart"): chart})).kind == "department"


def test_an_atom_supersedes_only_an_abandoned_atom():
    atom = atom_fields(opened(), supersedes="a-3f9a1c2b7d-02")
    with pytest.raises(GateError) as info:
        GATE.check("atom", atom, ctx=Store())
    assert [v.code for v in info.value.violations] == ["unknown_atom"]
    with pytest.raises(GateError) as info:
        GATE.check("atom", atom, ctx=Store({("atom", "a-3f9a1c2b7d-02"): SimpleNamespace(state="open")}))
    assert [v.code for v in info.value.violations] == ["supersedes_not_abandoned"]
    assert GATE.check("atom", atom, ctx=Store({("atom", "a-3f9a1c2b7d-02"): SimpleNamespace(state="abandoned")})).kind == "atom"


# ============================================ the chat meta keys ============================================================
def test_every_meta_key_j2_attaches_to_a_message_is_in_message_meta():
    tree = ast.parse((REPO / "sutra_app" / "engine" / "j2.py").read_text(encoding="utf-8"))
    params = {n.name: {a.arg for a in n.args.args + n.args.kwonlyargs} for n in ast.walk(tree)
              if isinstance(n, ast.FunctionDef) and n.name in {"post", "_say", "_reply", "_ask_user"}}
    used = set()
    for n in ast.walk(tree):
        if (isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and n.func.attr in params
                and isinstance(n.func.value, ast.Name) and n.func.value.id == "self"):
            used |= {k.arg for k in n.keywords if k.arg and (k.arg in META_KEYS or k.arg not in params[n.func.attr])}
    assert len(used) > 40, "the scan found too few calls: it is not looking at the right code"
    assert used - set(META_KEYS) - set(BASE_KEYS) == set(), "J2 attaches a meta key that MessageMeta does not know"
