"""J2's wire documents (library design 2 and 10, work package L9): map/1, board/1, story/1, agent/1, artifacts/1,
artifacts-tree/1, the realization record and its plan (realization/1), and the run summary with its budget.

Two kinds of test. The REAL ones run the vendored J2 engine in mock mode in a child process (its module state and
environment flags must not touch this one) and push every wire document it wrote or served through the gate: what the
page reads is what the models accept, and `wire()` gives it back unchanged. The HAND-BUILT ones take a minimal valid
document and break one rule at a time."""
import copy
import json
import os
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

from sutra_app.library import wire as W
from sutra_app.library.base import aliased_fields, unbounded_fields
from sutra_app.library.gate import GATE, GateError
from sutra_app.library.registry import REGISTRY

REPO = Path(__file__).resolve().parents[2]

# ---- the real documents: one child process per scenario ------------------------------------------------------------------
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
    for key, value in env.items():
        os.environ[key] = str(value)
    from sutra_app.engine import llm
    llm.configure(mock=True)
    from sutra_app.engine import j2, j2_realization, views
    rec.fake_chrome(j2.j2_check)
    if scenario == "plan":
        goal = {"statement": "A one-page website for Brew Lab", "business_type": "cafe",
                "done_when": ["menu with prices", "opening hours"], "constraints": [], "to_be_confirmed": []}
        (out / "realization.json").write_text(json.dumps(j2_realization.plan_goal(goal, web=False, log=lambda m: None)))
        sys.exit(0)
    run = j2.J2Run(run_dir=base / "runs" / "j2-20261104-100004-7f3a")
    brief = rec.BREW_LAB
    if scenario == "prd":
        run.set_output("prd")
        brief = "Write a PRD for QuickQueue, a mobile app that lets clinic patients join a waiting line remotely. Users: patients at small clinics and the front-desk staff who manage the line. Problem: patients wait 45 minutes on average in crowded waiting rooms. Must-have features: join the queue from a phone, live position updates, SMS alert when 2 patients are ahead, staff dashboard to call the next patient. Constraints: works on low-end Android phones; no patient health data stored. Success: average in-room wait under 10 minutes; 60% of patients join remotely within 3 months."
    assert run.user_says(brief) is True
    end = time.time() + 60
    while run.status != "waiting":
        assert time.time() < end, "the run did not stop"
        time.sleep(0.003)
    d = Path(run.dir)
    for name in ("summary.json", "map.json", "board.json", "artifacts.json"):
        if (d / name).is_file():
            shutil.copy(d / name, out / name)
    paths = views.MemoryPaths(str(base / "memory" / "lessons.jsonl"), str(base / "memory" / "playbooks.jsonl"))
    snap, live = views.live_state(run)
    contexts = {"live": views.RunCtx("live", d.name, run.dir, str(base / "runs"), d.name, paths, snap=snap, extras=live),
                "saved": views.RunCtx("saved", d.name, run.dir, str(base / "runs"), d.name, paths)}
    def body(reply):
        return reply.body if isinstance(reply.body, str) else reply.body.decode()
    for mode, ctx in contexts.items():
        for view in ("map", "board", "story", "artifacts_tree"):
            (out / f"{view}.{mode}.json").write_text(body(views.VIEWS[view](ctx, {})))
    for who in ("identity", "adaptation", "priority", "coordination", "audit", "W-1", "no-such-agent"):
        (out / f"agent.{who}.json").write_text(body(views.VIEWS["agent"](contexts["saved"], {"who": who})))
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
def runs(tmp_path_factory) -> dict[str, Path]:
    base = tmp_path_factory.mktemp("wire")
    return {name: run_scenario(name, base / name) for name in ("site", "prd", "board", "plan")}


def load(folder: Path, name: str):
    return json.loads((folder / name).read_text(encoding="utf-8"))


def trimmed(value):
    """What the models keep of a string: the config strips whitespace."""
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, list):
        return [trimmed(v) for v in value]
    if isinstance(value, dict):
        return {k: trimmed(v) for k, v in value.items()}
    return value


def passes(name: str, data):
    checked = GATE.check(name, data)
    assert checked.model.wire() == trimmed(data), f"{name}: wire() must give J2's JSON back"
    return checked.model


def shape_errors(name: str, data) -> list[tuple[str, str]]:
    with pytest.raises(GateError) as error:
        GATE.check(name, data)
    assert error.value.stage == "shape"
    return [(v.path, v.message) for v in error.value.violations]


def says(errors, *words) -> bool:
    return any(all(w in message for w in words) for _, message in errors)


# ---- real J2 output ------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("scenario", ["site", "prd", "board"])
def test_the_map_j2_wrote_and_served_is_accepted_and_comes_back_unchanged(runs, scenario):
    folder = runs[scenario]
    for name in ("map.json", "map.live.json", "map.saved.json"):
        doc = passes("map", load(folder, name))
        assert doc.nodes and doc.edges and doc.status.checks.run >= 0


def test_a_site_run_map_has_the_function_row_the_teams_and_the_constellations(runs):
    doc = passes("map", load(runs["site"], "map.saved.json"))
    assert [n.id for n in doc.nodes if n.kind == "function"] == [f"fn:{f}" for f in W.FUNCS]
    assert doc.teams and doc.constellations and doc.workflows
    assert any(e.kind == "speaks_to" and e.source.file == "chat.jsonl" for e in doc.edges)


@pytest.mark.parametrize("scenario", ["site", "prd", "board"])
def test_the_artifacts_the_run_listed_and_the_tree_it_served_are_accepted(runs, scenario):
    folder = runs[scenario]
    rows = passes("artifacts", load(folder, "artifacts.json")).rows
    assert any(r.deliverable for r in rows)
    for name in ("artifacts_tree.live.json", "artifacts_tree.saved.json"):
        tree = passes("artifacts_tree", load(folder, name))
        assert [g.id for g in tree.groups] == ["plan", "specs", "deliverables", "proof"]


def test_the_tree_keeps_nested_children_to_any_depth(runs):
    tree = passes("artifacts_tree", load(runs["site"], "artifacts_tree.saved.json"))
    deliverable = next(g for g in tree.groups if g.id == "deliverables").items[0]
    sections = next(c for c in deliverable.children if c.name == "Sections")
    assert sections.count == len(sections.children) > 0 and sections.children[0].code.section


@pytest.mark.parametrize("scenario", ["site", "prd", "board"])
def test_the_summary_j2_wrote_is_accepted_and_carries_the_budget(runs, scenario):
    summary = passes("run_summary", load(runs[scenario], "summary.json"))
    assert summary.budget.start <= summary.budget.granted and summary.budget.used >= 0
    assert summary.status == "done"


def test_a_document_run_summary_has_the_export_and_the_design_documents(runs):
    summary = passes("run_summary", load(runs["prd"], "summary.json"))
    assert summary.export is not None and summary.design_documents is not None


@pytest.mark.parametrize("scenario", ["site", "prd", "board"])
def test_every_agent_card_j2_served_is_accepted_even_for_an_agent_it_never_heard_of(runs, scenario):
    folder = runs[scenario]
    for who in ("identity", "adaptation", "priority", "coordination", "audit", "W-1"):
        doc = passes("agent", load(folder, f"agent.{who}.json"))
        assert doc.found and doc.summary.calls == len(doc.thinking) > 0
    stranger = passes("agent", load(folder, "agent.no-such-agent.json"))
    assert not stranger.found and stranger.thinking == [] and stranger.summary.calls == 0


def test_the_board_a_run_with_questions_wrote_and_its_story_are_accepted(runs):
    folder = runs["board"]
    board = passes("board", load(folder, "board.json"))
    assert board.entries and all(e.status == "answered" for e in board.entries)
    story = passes("story", load(folder, "story.saved.json"))
    assert story.has_board and story.numbers.questions == len(board.entries)
    assert [e.id for e in story.entries] == [e.id for e in board.entries]


def test_a_run_without_a_board_has_an_empty_one_and_a_story_that_says_so(runs):
    assert passes("board", load(runs["site"], "board.live.json")).entries == []
    story = passes("story", load(runs["site"], "story.live.json"))
    assert not story.has_board and story.steps == list(W.STORY_STEPS)


def test_the_planning_record_j2_wrote_in_mock_mode_is_accepted(runs):
    record = passes("realization", load(runs["plan"], "realization.json"))
    assert record.plan.workflows and record.rounds[-1].round == len(record.rounds) - 1
    assert GATE.check("realization_plan", load(runs["plan"], "realization.json")["plan"]).model == record.plan


# ---- registration --------------------------------------------------------------------------------------------------------
def test_the_nine_documents_are_registered_as_payloads_of_version_one():
    assert set(W.WIRE_PAYLOADS) == {"map", "board", "story", "agent", "artifacts", "artifacts_tree", "realization", "realization_plan",
                                    "run_summary"}
    for name, cls in W.WIRE_PAYLOADS.items():
        assert REGISTRY.versions(name) == [1] and REGISTRY.kinds(name)  # a payload lists its one class
        assert REGISTRY.json_schema(name)["type"] == "object"


def test_the_file_and_schema_tables_point_at_registered_payloads():
    assert set(W.WIRE_FILES.values()) <= set(REGISTRY.families())
    assert set(W.WIRE_SCHEMAS.values()) <= set(REGISTRY.families())
    assert W.WIRE_SCHEMAS["artifacts-tree/1"] == "artifacts_tree" and W.WIRE_FILES["summary.json"] == "run_summary"
    assert {cls.SCHEMA for cls in W.WIRE_PAYLOADS.values() if cls.SCHEMA} == {s for s in W.WIRE_SCHEMAS if s != "realization/1"}


def test_every_string_and_list_is_bounded_and_the_only_alias_is_schema():
    for name, cls in W.WIRE_PAYLOADS.items():
        assert unbounded_fields(cls) == [], name
        assert {alias for _, alias in aliased_fields(cls)} <= {"schema"}, name


def test_the_models_are_closed_a_key_j2_does_not_write_is_refused(runs):
    data = load(runs["site"], "map.saved.json")
    data["nodes"][0]["colour"] = "red"
    assert says(shape_errors("map", data), "Extra inputs") or any("colour" in p for p, _ in shape_errors("map", data))
    data = load(runs["site"], "summary.json")
    data["surprise"] = 1
    assert any("surprise" in p for p, _ in shape_errors("run_summary", data))


def test_wire_leaves_out_a_key_nobody_set_and_puts_schema_first():
    doc = W.BoardDoc.model_validate({"schema": "board/1", "entries": []})
    assert doc.wire() == {"schema": "board/1", "entries": []}
    built = W.BoardDoc(entries=[])
    assert list(built.wire()) == ["schema", "entries"]
    summary = GATE.check("run_summary", SUMMARY).model
    assert "realization" not in summary.wire() and list(summary.wire())[0] == "run"


# ---- map/1 ---------------------------------------------------------------------------------------------------------------
def node(**kw):
    return {"id": "work:site", "kind": "work", "row": "work", "label": "Site", "status": "filed", **kw}


def edge(**kw):
    return {"from": "work:charter", "to": "step:charter>site", "kind": "step", "label": None, "n": 1, "basis": "recorded",
            "source": {"file": "goal.json", "field": "charter"}, **kw}


MAP = {"schema": "map/1", "run": "j2-1", "live": False,
       "status": {"state": "Done", "state_status": "idle", "checks": {"passed": 1, "run": 2}},
       "nodes": [node()], "edges": [edge()], "legend": [{"key": "work", "label": "work", "drawn": True}],
       "built_from": ["artifacts.json"], "not_recorded": []}


def changed(base, **changes):
    out = copy.deepcopy(base)
    out.update(changes)
    return out


def test_a_minimal_map_and_the_empty_map_of_a_run_that_is_not_there_are_valid():
    doc = passes("map", MAP)
    assert doc.teams == [] and doc.constellations == {} and doc.edges[0].from_ == "work:charter"
    empty = {"schema": "map/1", "run": None, "live": False, "status": {"state": "not started", "state_status": "idle",
                                                                         "checks": {"passed": 0, "run": 0}},
             "nodes": [], "edges": [], "legend": [], "built_from": [], "not_recorded": ["run not found"]}
    assert passes("map", empty).run is None


def test_the_map_refuses_a_wrong_schema_string_and_an_unknown_status_or_kind():
    assert shape_errors("map", changed(MAP, schema="map/2"))
    assert shape_errors("map", changed(MAP, nodes=[node(status="working")]))
    assert shape_errors("map", changed(MAP, nodes=[node(kind="knowledge")]))
    assert shape_errors("map", changed(MAP, nodes=[node(row="attic")]))


def test_the_nine_status_words_of_the_map_are_accepted():
    for word in ("idle", "running", "waiting", "waiting_on_you", "fault", "filed", "done_unchecked", "left_open", "not_made"):
        passes("map", changed(MAP, nodes=[node(status=word)]))


def test_two_boxes_with_one_id_are_refused():
    assert says(shape_errors("map", changed(MAP, nodes=[node(), node()])), "unique", "work:site")


def test_a_function_box_must_be_fn_colon_a_function():
    assert says(shape_errors("map", changed(MAP, nodes=[node(id="fn:poet", kind="function", row="functions")])), "fn:<function>")
    passes("map", changed(MAP, nodes=[node(id="fn:audit", kind="function", row="functions", tab="audit", calls=3, seconds=1.5,
                                          tokens={"input": 4, "output": 5}, wait_on=None)]))


def test_seconds_and_counts_cannot_be_negative_and_checks_cannot_pass_more_than_ran():
    assert shape_errors("map", changed(MAP, nodes=[node(kind="function", id="fn:audit", row="functions", seconds=-1)]))
    bad = changed(MAP, status={"state": "Done", "state_status": "idle", "checks": {"passed": 3, "run": 2}})
    assert says(shape_errors("map", bad), "3 checks passed but only 2 ran")


def test_a_line_needs_a_record_and_a_known_kind_and_keeps_from_as_its_key():
    no_source = edge()
    del no_source["source"]
    assert shape_errors("map", changed(MAP, edges=[no_source]))
    assert shape_errors("map", changed(MAP, edges=[edge(kind="made")]))
    assert shape_errors("map", changed(MAP, edges=[edge(basis="guessed")]))
    wire = GATE.check("map", changed(MAP, edges=[edge(kind="handoff", readers=["W-1"], sources=[{"file": "x.json"}])])).model.wire()
    assert wire["edges"][0]["from"] == "work:charter" and "from_" not in wire["edges"][0]


def test_a_source_value_may_be_text_a_number_a_flag_or_nothing():
    for value in ("W-1.a1", 3, True, None):
        passes("map", changed(MAP, edges=[edge(source={"file": "atoms.json", "workflow": "W-2", "field": "depends_on", "value": value})]))


def test_the_team_graph_and_the_constellation_are_closed_too():
    team = {"id": "stage:Dev", "label": "Dev", "workflows": ["W-1"], "columns": 2,
            "nodes": [{"id": "W-1", "kind": "wf", "label": "One", "col": 1, "row": 0}],
            "edges": [{"from": "W-1", "to": "work:site", "kind": "makes", "loop": False}], "unresolved": [], "cycles": [["W-1"]], "loops": []}
    passes("map", changed(MAP, teams=[team]))
    assert shape_errors("map", changed(MAP, teams=[{**team, "edges": [{**team["edges"][0], "kind": "owns"}]}]))
    assert shape_errors("map", changed(MAP, teams=[{**team, "nodes": [{**team["nodes"][0], "kind": "person"}]}]))
    cons = {"work:site": {"id": "work:site", "label": "Site", "slots": [{"section": None, "label": None, "builder": "W-1", "fixes": [],
                                                                          "empty": True}],
                          "workflows": {"W-1": {"name": "One", "role": "builder", "section": None, "rank": 0, "t": None, "ran": False,
                                                "status": "done", "output": False, "reads": []}}, "inputs": []}}
    passes("map", changed(MAP, constellations=cons))
    cons["work:site"]["workflows"]["W-1"]["role"] = "boss"
    assert shape_errors("map", changed(MAP, constellations=cons))


# ---- board/1 and story/1 -------------------------------------------------------------------------------------------------
def entry(**kw):
    base = {"id": "Q-1", "asked_by": "W-2", "atom": "W-2.a1", "to": "W-1.a1", "about": "data attributes", "question": "Which attribute?",
            "answer": "data-id", "answered_by": "W-1", "status": "answered", "artifact_update": None, "used_by": ["audit"], "cycle": 1,
            "attempt": 1, "asked_by_role": "builder", "answered_from": {"workflow": "W-1", "version": 1}, "impact": []}
    return {**base, **kw}


def board(*entries):
    return {"schema": "board/1", "entries": list(entries)}


def test_an_answered_entry_carries_the_answer_and_who_gave_it():
    passes("board", board(entry()))
    assert says(shape_errors("board", board(entry(answer=None))), "answered question carries the answer")
    assert says(shape_errors("board", board(entry(answered_by=None))), "answered question carries the answer")


def test_an_open_entry_has_no_answer_and_a_refused_one_may_keep_its_text():
    open_entry = entry(status="open", answer=None, answered_by=None, answered_from=None)
    passes("board", board(open_entry))
    assert says(shape_errors("board", board({**open_entry, "answer": "early"})), "open question has no answer")
    passes("board", board(entry(status="refused")))
    passes("board", board(entry(status="routed to Identity", answer=None, answered_by=None)))
    assert shape_errors("board", board(entry(status="pending")))


def test_board_ids_are_unique_and_the_roles_and_results_are_closed_lists():
    assert says(shape_errors("board", board(entry(), entry())), "unique")
    assert shape_errors("board", board(entry(asked_by_role="robot")))
    assert shape_errors("board", board(entry(impact=[{"atom": "W-3.a1", "result": "maybe"}])))
    passes("board", board(entry(impact=[{"atom": "W-3.a1", "result": "passed"}, {"atom": "W-4.a1", "result": "failed"}],
                                artifact_update={"doc": "hld", "section": "Goals", "from_version": 1, "to_version": 2},
                                sent_to_identity={"doc": "prd", "section": "Goals", "reason": "not recorded"})))


def story_entry(**kw):
    atom = {"atom": "W-2.a1", "name": "Core", "workflow": "W-2", "deliverable": "website", "tag": "Site"}
    base = {"id": "Q-1", "status": "answered", "cycle": 1, "doubt": {**atom, "role": "builder", "asked_by": "W-2"},
            "ask": {**atom, "about": "x", "question": "q"},
            "answer": {"text": "a", "by": "W-1", "from": {"workflow": "W-1", "version": 1}, "updated_own_section": False,
                       "sent_to_identity": None},
            "change": None, "recheck": {"atoms": 1, "passed": 1, "failed": 0, "receipts": 0},
            "impact": [{**atom, "result": "passed"}], "reused_by": [{"id": "audit", **{k: None for k in atom}}]}
    return {**base, **kw}


STORY = {"schema": "story/1", "run": "j2-1", "has_board": True, "entries": [story_entry()],
         "numbers": {"questions": 1, "rechecked": 1, "receipts": 0, "duplicate_edges": 0},
         "facts": {"run": "j2-1", "status": "Done", "cycles": 2, "versions": {"website": 6}, "has_board": True, "questions": 1},
         "flags": {"mock": True, "provider": None, "model": None, "force_question": "adaptation"},
         "steps": list(W.STORY_STEPS), "not_recorded": []}


def test_a_story_with_one_question_is_valid_and_its_answer_is_read_from_the_key_from():
    doc = passes("story", STORY)
    assert doc.entries[0].answer.from_.workflow == "W-1"


def test_the_story_of_a_run_that_is_not_there_has_empty_facts_flags_and_numbers():
    gone = {"schema": "story/1", "run": None, "has_board": False, "entries": [], "numbers": {}, "facts": {}, "flags": {},
            "steps": list(W.STORY_STEPS), "not_recorded": ["the run folder"]}
    assert passes("story", gone).numbers.questions == 0


def test_the_story_derives_has_board_and_its_numbers_from_the_entries():
    assert says(shape_errors("story", changed(STORY, has_board=False)), "has_board is true exactly when")
    assert says(shape_errors("story", changed(STORY, numbers={**STORY["numbers"], "questions": 2})), "numbers.questions")
    assert says(shape_errors("story", changed(STORY, numbers={**STORY["numbers"], "rechecked": 0})), "numbers.rechecked")
    assert says(shape_errors("story", changed(STORY, steps=["ask", "doubt", "answer", "change", "recheck"])), "steps are")


def test_a_story_entry_recheck_counts_must_match_its_impact():
    wrong = story_entry(recheck={"atoms": 2, "passed": 1, "failed": 1, "receipts": 0})
    assert says(shape_errors("story", changed(STORY, entries=[wrong], numbers={**STORY["numbers"], "rechecked": 2})), "recheck counts")
    unbalanced = story_entry(recheck={"atoms": 1, "passed": 0, "failed": 0, "receipts": 0})
    assert says(shape_errors("story", changed(STORY, entries=[unbalanced])), "recheck counts")


# ---- agent/1 -------------------------------------------------------------------------------------------------------------
def card(**kw):
    base = {"id": 2, "step": 2, "cycle": 1, "t": "18:46:46", "seconds": 0.0, "model": None, "tokens": None, "atom": None,
            "given": [["charter", "Brew Lab"]], "reason": "because", "reply": {"text": ["hello"], "fields": [["act", "PROPOSE"]],
                                                                               "reason": None, "note": None},
            "technical": {"system": "s", "prompt": "p", "raw": "r"}}
    return {**base, **kw}


AGENT = {"schema": "agent/1", "who": "adaptation", "found": True, "names": {"W-1": "Scaffold"},
         "summary": {"calls": 1, "seconds": 0.0, "models": [], "tokens": {"input": 0, "output": 0}, "messages": 1,
                     "most": {"with": "priority", "count": 1}},
         "conversations": [{"with": "priority", "count": 1, "messages": [{"id": 3, "t": "18:46:46", "step": 1, "from": "adaptation",
                                                                         "to": ["priority"], "text": "hi", "sent": True}]}],
         "thinking": [card()]}


def test_an_agent_card_is_valid_and_keeps_with_and_from_as_its_keys():
    wire = GATE.check("agent", AGENT).model.wire()
    assert wire["conversations"][0]["with"] == "priority" and wire["conversations"][0]["messages"][0]["from"] == "adaptation"


def test_an_agent_of_a_run_that_is_not_there_is_who_and_found_false_alone():
    assert passes("agent", {"schema": "agent/1", "who": "", "found": False}).thinking is None
    assert says(shape_errors("agent", {"schema": "agent/1", "who": "audit", "found": True}), "found agent carries")


def test_the_parts_of_an_agent_come_together_or_not_at_all():
    partial = {k: v for k, v in AGENT.items() if k != "names"}
    assert says(shape_errors("agent", partial), "come together")


def test_an_agent_summary_counts_its_cards_and_found_means_it_did_something():
    assert says(shape_errors("agent", changed(AGENT, summary={**AGENT["summary"], "calls": 2})), "summary.calls is 2")
    idle = changed(AGENT, thinking=[], conversations=[], summary={**AGENT["summary"], "calls": 0, "most": None})
    assert says(shape_errors("agent", idle), "found is true exactly when")
    passes("agent", changed(idle, found=False))


def test_a_conversation_count_is_the_number_of_its_messages():
    talk = copy.deepcopy(AGENT["conversations"][0])
    talk["count"] = 4
    assert says(shape_errors("agent", changed(AGENT, conversations=[talk])), "count is 4")
    talk["count"] = 1
    talk["with"] = None
    passes("agent", changed(AGENT, conversations=[talk]))


def test_a_call_may_report_only_one_token_count_and_a_card_pair_has_two_items():
    passes("agent", changed(AGENT, thinking=[card(tokens={"input": 7, "output": None})]))
    assert shape_errors("agent", changed(AGENT, thinking=[card(given=[["only one"]])]))
    assert shape_errors("agent", changed(AGENT, thinking=[card(reply={"text": [], "fields": [["a", "b", "c"]]})]))
    assert shape_errors("agent", changed(AGENT, thinking=[card(technical={"system": "x" * 40_001, "prompt": "", "raw": ""})]))


# ---- artifacts/1 and artifacts-tree/1 ------------------------------------------------------------------------------------
def row(**kw):
    base = {"name": "Website", "type": "website", "kind": "type", "form": "page", "file": "site/index.html", "deliverable": True,
            "workflows": ["W-1"], "depends_on": [], "version": 6, "sha256": "a" * 64, "time": "2026-11-04T18:46:47"}
    return {**base, **kw}


def test_a_row_may_carry_the_board_marks_and_a_deliverable_depends_only_on_what_was_built():
    passes("artifacts", {"schema": "artifacts/1", "rows": [row(changed_by=["Q-1"], rechecked_after=["Q-1"]),
                                                          row(name="PRD", type="prd", depends_on=["website"])]})
    assert says(shape_errors("artifacts", {"schema": "artifacts/1", "rows": [row(depends_on=["prd"])]}), "did not build")


def test_a_row_needs_a_real_hash_and_a_known_kind():
    assert shape_errors("artifacts", {"schema": "artifacts/1", "rows": [row(sha256="abc")]})
    assert shape_errors("artifacts", {"schema": "artifacts/1", "rows": [row(kind="thing")]})
    passes("artifacts", {"schema": "artifacts/1", "rows": [row(sha256=None, version=None, time=None)]})


def group(id_="plan", items=None, **kw):
    items = [{"name": "Charter", "file": "goal.json", "made_by": {"function": "Client Lead"}, "status": "filed", "size": 10,
              "open": "text"}] if items is None else items
    return {"id": id_, "label": id_.title(), "count": len(items), "collapsed": False, "items": items, **kw}


def test_a_tree_group_counts_its_items_and_a_group_comes_once():
    passes("artifacts_tree", {"schema": "artifacts-tree/1", "groups": [group(), group("proof")]})
    assert says(shape_errors("artifacts_tree", {"schema": "artifacts-tree/1", "groups": [group(count=5)]}), "count is 5")
    assert says(shape_errors("artifacts_tree", {"schema": "artifacts-tree/1", "groups": [group(), group()]}), "only once")
    assert shape_errors("artifacts_tree", {"schema": "artifacts-tree/1", "groups": [group("extras")]})
    passes("artifacts_tree", {"schema": "artifacts-tree/1", "groups": []})


def test_a_tree_item_may_hold_children_and_carry_a_team_or_a_function_as_its_maker():
    folder = {"name": "Sections", "count": 1, "collapsed": True, "children": [
        {"name": "Core", "file": None, "status": "filed", "size": 4, "made_by": {"persona": "Web Developer", "workflows": ["W-1"]},
         "open": "code", "code": {"deck": "work:website", "section": "W-1"}, "section": "W-1", "rewritten": {"by": "W-2", "name": "x"}}]}
    passes("artifacts_tree", {"schema": "artifacts-tree/1", "groups": [group("deliverables", [folder])]})
    folder["children"][0]["made_by"] = {"robot": "x"}
    assert shape_errors("artifacts_tree", {"schema": "artifacts-tree/1", "groups": [group("deliverables", [folder])]})


# ---- realization/1 and the planning record -------------------------------------------------------------------------------
def factor(**kw):
    return {"name": "Mobile first", "source": "brief", "quote": "work well on a phone", "citation": None, "why": "most visitors", "stages": ["build"], **kw}


def pworkflow(**kw):
    base = {"name": "Plan", "stage": "product", "certainty": "analyze", "certainty_signals": ["mock"], "approach": "Weigh options.",
            "goal": "One plan", "done_test": "Every item has a place", "delivers": [], "informs": [1, 2], "inputs_from": [],
            "experiment": None, "research": None}
    return {**base, **kw}


def plan(**kw):
    base = {"factors": [factor()], "unplaced": [], "stages": [{"id": "product", "thinking": "t", "tiers": ["strategy"], "goal": "g",
                                                                 "done_test": "d", "method": None, "owns_factors": [], "inputs_from": []}],
            "workflows": [pworkflow()], "open_facts": [], "not_ready": [], "changes": [], "deferred": []}
    return {**base, **kw}


def test_a_plan_is_valid_and_optional_parts_may_be_left_out():
    passes("realization_plan", plan())
    passes("realization_plan", plan(analysis={"options": [{"option": "a"}], "chosen": "a", "why": "w", "assumptions": []},
                                    certainty_assessment={"zone": "analyze", "rationale": "r", "signals": {
                                        k: {"answer": "yes", "evidence": "e"} for k in
                                        ("broken", "reaction", "facts_given", "known_pattern", "open_choices")}}))


def test_a_factor_from_the_brief_quotes_it_a_research_factor_cites_it_and_a_budget_factor_has_no_stage():
    assert says(shape_errors("realization_plan", plan(factors=[factor(quote="  ")])), "quotes the brief")
    assert says(shape_errors("realization_plan", plan(factors=[factor(source="research", quote=None)])), "research factor cites")
    assert shape_errors("realization_plan", plan(factors=[factor(source="research", citation="notes.md")]))
    assert says(shape_errors("realization_plan", plan(factors=[factor(source="budget", quote=None)])), "belongs to no stage")
    passes("realization_plan", plan(factors=[factor(source="research", quote=None, citation="research.md#R-1"),
                                             factor(source="budget", quote=None, stages=[]), factor(source="general", quote=None)]))


def test_a_research_workflow_delivers_nothing_and_is_not_a_build_workflow():
    research = {"question": "q", "feeds": "f", "min_sources": 3, "output": "research.md#R-1"}
    passes("realization_plan", plan(workflows=[pworkflow(research=research)]))
    assert says(shape_errors("realization_plan", plan(workflows=[pworkflow(research=research, delivers=[1])])), "delivers no done-when")
    assert says(shape_errors("realization_plan", plan(workflows=[pworkflow(research=research, stage="build")])), "not in the build stage")
    assert shape_errors("realization_plan", plan(workflows=[pworkflow(research={**research, "min_sources": 2})]))


def test_an_experiment_workflow_carries_its_four_parts_and_the_certainty_is_one_of_four_zones():
    experiment = {"hypothesis": "h", "signal": "s", "fails_if": "f", "limit": "l"}
    passes("realization_plan", plan(workflows=[pworkflow(certainty="experiment", experiment=experiment)]))
    assert shape_errors("realization_plan", plan(workflows=[pworkflow(certainty="experiment", experiment={"hypothesis": "h"})]))
    assert shape_errors("realization_plan", plan(workflows=[pworkflow(certainty="chaos")]))
    assert shape_errors("realization_plan", plan(workflows=[pworkflow(hold="paused")]))
    passes("realization_plan", plan(workflows=[pworkflow(hold="waiting_on_identity")]))


def test_workflow_names_are_unique_and_inputs_must_name_a_workflow_of_the_plan():
    assert says(shape_errors("realization_plan", plan(workflows=[pworkflow(), pworkflow()])), "names must be unique")
    assert says(shape_errors("realization_plan", plan(workflows=[pworkflow(inputs_from=["Ghost"])])), "reads Ghost")
    passes("realization_plan", plan(workflows=[pworkflow(), pworkflow(name="Build", inputs_from=["Plan"])]))


def test_a_stage_needs_a_tier_a_not_ready_row_a_score_between_zero_and_one_and_a_known_route():
    stage = plan()["stages"][0]
    assert shape_errors("realization_plan", plan(stages=[{**stage, "tiers": []}]))
    assert shape_errors("realization_plan", plan(stages=[{**stage, "tiers": ["roof"]}]))
    nr = {"workflow": "Plan", "score": 0.5, "weakest": "method", "stop_reason": "r", "route": "identity"}
    passes("realization_plan", plan(not_ready=[nr]))
    assert shape_errors("realization_plan", plan(not_ready=[{**nr, "score": 1.5}]))
    assert shape_errors("realization_plan", plan(not_ready=[{**nr, "route": "nowhere"}]))
    assert shape_errors("realization_plan", plan(not_ready=[{**nr, "weakest": "luck"}]))


def score(**kw):
    return {"score": 0.95, "weakest": None, "capped": False, "checks": {"inputs": "yes"}, "missing": [], "failed": [], "compare": "better", **kw}


def record(**kw):
    p = plan()
    base = {"goal": "Brew Lab", "web": False, "provider": None, "model": None, "mock": True, "checklist": [{"id": "K1", "item": 1}],
            "plan": p, "scores": {"Plan": score()}, "history": {"Plan": [0.95]}, "rounds": [{"round": 0, "plan": p, "plan_faults": [],
                                                                                           "changes": [], "scores": {"Plan": score()},
                                                                                           "judge_faults": []}],
            "not_ready": [], "held": {}, "waiting_on_identity": [{"workflow": "Plan", "score": None, "ask": ["ask: the hours"]}],
            "stages": {"product": {"confidence": 0.95, "zone": "analyze"}}, "plan_confidence": 0.95, "plan_faults": [], "calls": 3,
            "seconds": 0.0}
    return {**base, **kw}


def test_a_planning_record_is_valid():
    doc = passes("realization", record())
    assert doc.plan_confidence == 0.95 and doc.waiting_on_identity[0].score is None


def test_the_rounds_are_numbered_from_zero_and_the_last_one_gives_the_plan_faults():
    two = [record()["rounds"][0], {**record()["rounds"][0], "round": 2}]
    assert says(shape_errors("realization", record(rounds=two)), "numbered 0, 1, 2")
    assert says(shape_errors("realization", record(plan_faults=["R1: x"])), "last round's plan_faults")
    assert shape_errors("realization", record(rounds=[]))
    passes("realization", record(plan_faults=["R1: x"], rounds=[{**record()["rounds"][0], "plan_faults": ["R1: x"]}]))


def test_a_score_for_a_workflow_the_plan_does_not_have_is_refused():
    assert says(shape_errors("realization", record(scores={"Ghost": score()})), "Ghost")
    assert shape_errors("realization", record(scores={"Plan": score(score=1.2)}))
    assert shape_errors("realization", record(held={"Plan": "sulking"}))
    assert shape_errors("realization", record(plan_confidence=-0.1))
    passes("realization", record(held={"Plan": "not_ready"}))


# ---- summary.json --------------------------------------------------------------------------------------------------------
SUMMARY = {
    "run": "20261104-100004-7f3a", "output_type": "website", "j2_fixes": 0, "provider": None, "sections": ["W-1", {"heading": "Intro", "words": 40}],
    "conditions": {"met": 1, "total": 2, "warnings": 0, "list": [{"id": "N1", "met": True, "evidence": "e"}, {"id": "N2", "met": False}]},
    "necessary_conditions": None, "force_audit_fail": None, "test_lessons": False, "force_question": None, "has_board": False,
    "model": None, "mock": True, "brief": "A site", "change_requests": [], "status": "done", "outcome": "Done: the site is workable.",
    "budget": {"start": 100, "granted": 100, "used": 88, "raises": []}, "ai_calls": 28, "cycles": 2, "links": {"identity->adaptation": 2},
    "verification": {"passed": 4, "failed": 0, "escalated": 1, "could_not_run": 0, "checks_run": 32},
    "identity_to_requester_decisions": 0, "identity_to_requester_facts": 0, "priority_rulings": {"grant": 1, "counter": 2, "refuse": 0},
    "questions_to_user": [], "conflicts": [], "validator_rejections": [{"cycle": 1, "workflow": "Stories", "reason": "r"}], "holds": [],
    "audits": [{"cycle": 1, "version": 4, "all_pass": False, "verdicts": [{"id": "F-1", "item": 1, "verdict": "PASS"},
                                                                          {"id": "R-1", "item": "R-1", "verdict": "PASS"}]}],
    "site_versions": 6, "workable": [], "to_be_confirmed": [], "dropped_by_requester": [], "workflow_agents": [
        {"id": "W-1", "agent": "W-1 Builder", "section": "W-1", "revises": None, "status": "done", "calls": 1, "retries": 0}],
    "limits_hit": [], "lessons": {"memory": False, "saved": [], "used": []}, "playbooks": {"saved": None, "used": []},
    "business_type": "cafe", "style_guide": True, "rubric": [{"id": "R-1", "pass": True, "verdict": "PASS"}],
    "done_when": [{"item": 1, "criterion": "Menu", "pass": None}], "route_check_violations": [],
}


def test_a_minimal_summary_is_valid_and_pass_is_read_from_the_key_pass():
    doc = passes("run_summary", SUMMARY)
    assert doc.rubric[0].pass_ is True and doc.done_when[0].pass_ is None
    assert doc.wire()["rubric"][0]["pass"] is True


def budget(**kw):
    return changed(SUMMARY, budget={**SUMMARY["budget"], **kw})


def test_the_budget_has_its_four_parts_and_each_must_be_a_whole_number():
    assert shape_errors("run_summary", {**SUMMARY, "budget": {"start": 100, "granted": 100, "used": 88}})
    assert shape_errors("run_summary", budget(used=-1))
    assert shape_errors("run_summary", budget(used=1.5))
    assert shape_errors("run_summary", budget(start="100"))


def test_a_raise_goes_up_and_the_last_raise_ends_at_the_granted_amount():
    up = {"cycle": 1, "asked": 20, "from": 100, "to": 120, "why": "more"}
    passes("run_summary", budget(granted=120, raises=[up]))
    assert says(shape_errors("run_summary", budget(granted=130, raises=[up])), "last raise ends at 120")
    assert says(shape_errors("run_summary", budget(granted=100, raises=[{**up, "to": 90}])), "raise goes up")
    assert says(shape_errors("run_summary", budget(granted=90)), "below the start")
    assert passes("run_summary", budget(granted=120, raises=[up])).budget.raises[0].from_ == 100


def test_a_rehydrated_run_may_start_above_its_start_with_no_raise_of_its_own():
    passes("run_summary", budget(granted=140, used=130))


def test_the_status_and_the_outcome_sentence_agree():
    assert says(shape_errors("run_summary", changed(SUMMARY, status="stopped", outcome="Done: fine")), "status stopped")
    assert says(shape_errors("run_summary", changed(SUMMARY, status="done_with_open_items", outcome="Done: fine")), "Done with open items")
    assert says(shape_errors("run_summary", changed(SUMMARY, status="crashed", outcome="Stopped.")), "Crashed")
    passes("run_summary", changed(SUMMARY, status="stopped", outcome="Stopped: the budget is used up."))
    passes("run_summary", changed(SUMMARY, status="crashed", outcome="Crashed: the model call failed."))
    assert shape_errors("run_summary", changed(SUMMARY, status="finished"))


def test_the_condition_tally_matches_its_list():
    bad = changed(SUMMARY, conditions={"met": 2, "total": 2, "warnings": 0, "list": SUMMARY["conditions"]["list"]})
    assert says(shape_errors("run_summary", bad), "number of entries that are met")
    short = changed(SUMMARY, conditions={"met": 1, "total": 3, "warnings": 0, "list": SUMMARY["conditions"]["list"]})
    assert says(shape_errors("run_summary", short), "length of the list")
    assert passes("run_summary", changed(SUMMARY, conditions=None)).conditions is None


def test_the_realization_and_document_parts_are_optional_but_closed():
    passes("run_summary", {**SUMMARY, "realization": {"applied": True, "plan_confidence": 0.9, "stages": ["build"], "workflows": 3,
                                                       "rounds": 1, "plan_faults": [], "calls": 4, "seconds": 0.5, "proposal_brief": [{"x": 1}]}})
    passes("run_summary", {**SUMMARY, "design_documents": {"requested": ["prd"], "stages": ["prd"], "files": {"prd": "prd.md"}},
                           "export": {"file": "prd.docx", "written": True, "note": None}})
    assert shape_errors("run_summary", {**SUMMARY, "realization": {"applied": True, "mood": "ok"}})
    assert shape_errors("run_summary", {**SUMMARY, "export": {"file": "prd.docx"}})


def test_a_summary_missing_a_key_j2_always_writes_is_refused():
    for key in ("budget", "status", "verification", "priority_rulings", "done_when"):
        broken = {k: v for k, v in SUMMARY.items() if k != key}
        assert any(key in p for p, _ in shape_errors("run_summary", broken)), key


def test_the_summary_budget_is_the_model_l3_points_at():
    budget_model = W.SummaryBudget.model_validate({"start": 100, "granted": 100, "used": 5, "raises": []})
    assert budget_model.model_dump() == {"start": 100, "granted": 100, "used": 5, "raises": []}
