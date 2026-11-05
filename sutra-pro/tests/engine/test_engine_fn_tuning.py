"""Reply classes and write scope tuned on the golden run (work package GAP-TUNE, gap G14, function-nodes.md 5.4 and 9).

The recorded Brew Lab mock run ended nine of 31 function atoms `verify_failed` (all by `reply-valid`) and logged twelve
`layer.touches_miss` lines for records J2 saves legitimately. The design says to loosen the reply class, never the check and
never a J2 prompt. What is pinned here:

  * each of the nine refused J2 replies (trimmed from the run's own calls) is now read, and what is still wrong is still refused;
  * the exported schemas do not change (the loosening is in validators only);
  * the three new `FunctionSpec.writes` terms name the records, `SUTRA_NODES=enforce` stays reserved (G18);
  * the mock run has no `verify_failed` atom that is not in ALLOWED_VERIFY_FAILED with a reason, and no `touches_miss`;
  * the table of `docs/notes/GAP-TUNE.md` (check, atoms judged, failed, recovered, waived) is made by `check_report`;
    `scripts/py tests/engine/test_engine_fn_tuning.py` prints it for the golden events.
"""
import copy
import importlib.util
import json
import sys
from pathlib import Path

import pytest

import sutra_app.library.functions  # noqa: F401  (registers the reply families)
from sutra_app.engine.events import EventWriter
from sutra_app.engine.fnodes.layer import WRITE_TERMS, factory, writable_records
from sutra_app.library.node import load_function_specs
from sutra_app.library.registry import REGISTRY
from sutra_app.library.replies import ReplyInvalid, ReplyParser

REPO = Path(__file__).resolve().parents[2]
GOLD = REPO / "tests" / "engine" / "golden"
PARSER = ReplyParser()

# A verify_failed function atom the mock run may end with, by (function, failing check) -> why it is intended. The run has none
# today: every reply of J2's mock is read. An entry is added only for a refusal or an abandon that the scenario is MEANT to show.
ALLOWED_VERIFY_FAILED: dict[tuple[str, str], str] = {}


def _load_recorder():
    spec = importlib.util.spec_from_file_location("record_fn_golden", REPO / "scripts" / "record_fn_golden.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


rec = _load_recorder()


# ---- what is asked of a run's events (also the table of the notes) -------------------------------------------------------
def final_atoms(events: list[dict]) -> dict[str, dict]:
    """The last `atom` event of every function atom, by atom id."""
    return {e["atom"]["id"]: e for e in rec.function_atom_events(events)}


def unexplained_failures(events: list[dict], allowed: dict = ALLOWED_VERIFY_FAILED) -> list[str]:
    """`<function>/<check> <atom id>` for each atom that ended `verify_failed` and is not in `allowed`."""
    bad = []
    for atom_id, e in final_atoms(events).items():
        if e["atom"]["body"].get("abandon_code") != "verify_failed" and e["outcome"] != "verify_failed":
            continue
        function = e["node"].rpartition(".")[2]
        check = rec.failing_check(e["atom"]["reason"]) or "?"
        if (function, check) not in allowed:
            bad.append(f"{function}/{check} {atom_id}")
    return bad


def check_report(events: list[dict]) -> list[dict]:
    """One row per check template: the atoms it judged, how many of them ended failed, recovered and waived (the evidence of the
    check's last result in the atom's final body says which: `RECOVERED: ` / `WAIVED: `)."""
    rows: dict[str, dict] = {}
    for e in final_atoms(events).values():
        for check in e["atom"]["body"]["verify"]["checks"]:
            if not check["results"]:
                continue
            last = check["results"][-1]
            row = rows.setdefault(check["template"], {"check": check["template"], "judged": 0, "failed": 0, "recovered": 0, "waived": 0})
            row["judged"] += 1
            row["failed"] += last["exit_code"] != 0
            row["recovered"] += last["evidence"].startswith("RECOVERED: ")
            row["waived"] += last["evidence"].startswith("WAIVED: ")
    return sorted(rows.values(), key=lambda r: r["check"])


def render_report(rows: list[dict]) -> str:
    lines = ["| check | atoms judged | failed | recovered | waived |", "|---|---:|---:|---:|---:|"]
    lines += [f"| {r['check']} | {r['judged']} | {r['failed']} | {r['recovered']} | {r['waived']} |" for r in rows]
    return "\n".join(lines)


# ---- J2's own words (trimmed from the calls of the recorded run) ---------------------------------------------------------
J2_ATOM = {
    "goal": "viewport meta tag present", "constraints": ["Other workflows' sections stay unchanged"], "context": ["finding F-7"],
    "how": {"kind": "AI", "agent": "Builder", "steps": "Write the workflow's section of index.html"},
    "expected_output": [{"text": "The site file index.html", "kind": "file", "target": "index.html"}],
    "verification": [{"text": "The site file index.html exists after the build.", "type": "file-exists", "target": "index.html",
                      "expect": True}]}
ENVELOPE = {"money_limit": 15, "model_call_limit": 2, "time_limit_minutes": 10, "retry_limit": 1, "stop_loss": "stop if the build fails twice"}


def j2_workflow(**over):
    """A workflow as J2's WF_FMT words it: `atoms`, no `id`."""
    return {"name": "Viewport fix", "goal_gap": "Layout works on a phone", "parts": ["fix"], "fixes": ["F-7"], "outputs": ["index.html"],
            "completion_check": "viewport meta tag present", "atoms": [copy.deepcopy(J2_ATOM)], **over}


def j2_grant(**over):
    return j2_workflow(estimate=0, cost=15, envelope=copy.deepcopy(ENVELOPE), **over)


J2_CHARTER = {   # no `kind`: J2's goal.json has none
    "statement": "A one-page website for Brew Lab", "site_name": "Brew Lab", "audience": "Local customers, mostly on phones",
    "standards": ["Warm, modern feel"], "rules": ["Plain HTML/CSS/JS in one file"],
    "done_when": ["The menu with prices is shown", "Opening hours are listed", "Layout works on a phone"], "core": [True, True, False],
    "to_be_confirmed": [], "dropped_from_brief": [], "facts": ["Brew Lab"], "business_type": "cafe", "visitor_needs": ["Menu with prices"]}
J2_INTAKE = {"to_requester": "Thanks, I have everything I need.", "to_agents": "@Adaptation Charter recorded.", "enough": True,
             "next": "Adaptation", "goal": J2_CHARTER}
J2_PROPOSE = {"say": "@Priority Proposal for cycle 1.", "act": "PROPOSE", "next": "Priority", "workflows": [j2_workflow()]}
J2_RESPOND = {"say": "@Priority I can shrink them to two.", "act": "REVISE", "next": "Priority", "workflows": [j2_workflow()]}
J2_PRICE = {"say": "@Adaptation Granted (18 of 30 left).", "decision": "GRANT", "next": "Adaptation", "workflows": [j2_grant()]}
J2_VERDICT = {"say": "@Coordination The build is wrong: the section misses what the check asks for.", "verdict": "BUILD_WRONG",
              "atom": "W-2.a1", "affordable": True}


def parse(family, kind, reply):
    return PARSER.parse(family, json.dumps(reply), kind=kind).model


def refused(family, kind, reply):
    with pytest.raises(ReplyInvalid) as exc:
        PARSER.parse(family, json.dumps(reply), kind=kind)
    return " | ".join(f"{v.path}: {v.message}" for v in exc.value.violations)


# ---- 1. Identity's intake: the charter has no `kind` (verify_failed a-...-03, "Unable to extract tag using discriminator") ----
def test_an_intake_charter_without_kind_is_a_site_charter():
    goal = parse("identity", "intake", J2_INTAKE).goal
    assert goal.kind == "site" and goal.site_name == "Brew Lab"


def test_an_intake_charter_that_names_a_product_is_a_document_charter():
    doc = {**J2_CHARTER, "product_name": "QuickQueue"}
    assert parse("identity", "intake", {**J2_INTAKE, "goal": doc}).goal.kind == "doc"


def test_an_intake_charter_that_says_its_kind_keeps_it():
    assert parse("identity", "intake", {**J2_INTAKE, "goal": {**J2_CHARTER, "kind": "site"}}).goal.kind == "site"
    assert "kind" in refused("identity", "intake", {**J2_INTAKE, "goal": {**J2_CHARTER, "kind": "poster"}})


def test_an_intake_charter_without_kind_is_still_checked_for_its_fields():
    said = refused("identity", "intake", {**J2_INTAKE, "goal": {"statement": "s", "done_when": ["a"]}})
    assert "site_name: Field required" in said                                           # read as a site charter, then refused for what it lacks


# ---- 2. Adaptation's proposal and revision, Priority's price: J2 words a workflow with `atoms` and no `id` ------------------
def test_a_proposal_in_j2_words_is_read_as_proposed_workflows():
    reply = parse("adaptation", "propose", J2_PROPOSE)
    [w] = reply.workflows
    assert (w.id, w.kind, w.name, [s.id for s in w.steps]) == ("P-1", "proposed", "Viewport fix", ["a1"])
    assert w.steps[0].atom.goal == "viewport meta tag present" and w.fixes == ["F-7"]


def test_workflows_are_numbered_by_their_place_and_a_given_id_is_kept():
    two = parse("adaptation", "propose", {**J2_PROPOSE, "workflows": [j2_workflow(), j2_workflow(id="P-9", name="Second")]})
    assert [w.id for w in two.workflows] == ["P-1", "P-9"]
    plain = {k: v for k, v in j2_workflow().items() if k != "atoms"}
    plain["steps"] = [{"kind": "ai", "id": "a1", "name": "Build", "atom": {"goal": "g", "work": {"dispatch_kind": "llm", "how_kind": "AI"}}}]
    assert [w.id for w in parse("adaptation", "propose", {**J2_PROPOSE, "workflows": [plain, dict(plain)]}).workflows] == ["P-1", "P-2"]
    assert [w.id for w in parse("adaptation", "propose", {**J2_PROPOSE, "workflows": [j2_workflow(), j2_workflow()]}).workflows] == ["P-1", "P-2"]


def test_a_revision_in_j2_words_is_read():
    assert parse("adaptation", "respond", J2_RESPOND).workflows[0].id == "P-1"


def test_a_grant_in_j2_words_carries_its_envelope_and_drops_the_keys_the_class_lacks():
    [w] = parse("priority", "price", J2_PRICE).workflows
    assert w.envelope.money_limit == 15 and w.id == "P-1"                     # `estimate` and `cost` are J2's, not the class's


def test_a_counter_and_a_refusal_in_j2_words():
    assert parse("priority", "price", {**J2_PRICE, "decision": "COUNTER"}).decision == "COUNTER"
    assert parse("priority", "price", {**J2_PRICE, "decision": "REFUSE", "workflows": []}).workflows == []


def test_a_workflow_that_says_steps_but_no_id_gets_one_and_loses_what_the_class_lacks():
    library = {k: v for k, v in j2_workflow().items() if k != "atoms"}
    library["steps"] = [{"kind": "ai", "id": "a1", "name": "Build", "atom": {"goal": "g", "work": {"dispatch_kind": "llm", "how_kind": "AI"}}}]
    [w] = parse("adaptation", "propose", {**J2_PROPOSE, "workflows": [{**library, "cost": 9}]}).workflows
    assert w.id == "P-1" and w.steps[0].id == "a1"


def test_a_j2_workflow_that_is_wrong_is_refused_at_its_place():
    bad = j2_workflow(outputs=[])
    said = refused("adaptation", "propose", {**J2_PROPOSE, "workflows": [j2_workflow(), bad]})
    assert "workflows.1.outputs" in said and "workflows.0" not in said
    assert "Value error" not in said                                          # pydantic's wrapper is not repeated in the message


def test_a_grant_in_j2_words_without_money_is_still_refused():
    said = refused("priority", "price", {**J2_PRICE, "workflows": [j2_workflow()]})
    assert "workflows.0.envelope" in said and "money_limit" in said


def test_a_workflow_with_neither_steps_nor_atoms_and_a_workflow_that_is_no_object_are_refused():
    assert "workflows.0.steps" in refused("adaptation", "propose", {**J2_PROPOSE, "workflows": [{"name": "x"}]})
    assert "workflows.0" in refused("adaptation", "propose", {**J2_PROPOSE, "workflows": ["W-1"]})
    assert "workflows" in refused("adaptation", "propose", {**J2_PROPOSE, "workflows": "none"})


def test_more_than_twenty_workflows_are_still_too_many():
    assert "workflows" in refused("adaptation", "propose", {**J2_PROPOSE, "workflows": [j2_workflow() for _ in range(21)]})


def test_the_act_rules_still_apply_to_the_read_workflows():
    assert "PROPOSE needs at least one workflow" in refused("adaptation", "propose", {**J2_PROPOSE, "workflows": []})
    assert "PARK carries no workflows" in refused("adaptation", "respond", {**J2_RESPOND, "act": "PARK"})


# ---- 3. Adaptation's verdict: BUILD_WRONG without build_wrong_reason (J2:9021 defaults it, its mock says it in `say`) ---------
def test_a_build_wrong_verdict_may_say_what_the_build_lacks_in_its_message():
    assert parse("adaptation", "atom_verdict", J2_VERDICT).verdict == "BUILD_WRONG"


def test_a_build_wrong_verdict_with_no_words_at_all_is_still_refused():
    assert "BUILD_WRONG needs build_wrong_reason" in refused("adaptation", "atom_verdict", {**J2_VERDICT, "say": "  "})
    assert parse("adaptation", "atom_verdict", {**J2_VERDICT, "say": "", "build_wrong_reason": "no submit button"}).verdict == "BUILD_WRONG"
    assert "affordable" in refused("adaptation", "atom_verdict", {k: v for k, v in J2_VERDICT.items() if k != "affordable"})


# ---- the schemas the model is asked for do not change -----------------------------------------------------------------------
@pytest.mark.parametrize("family,kind", [("adaptation", "propose"), ("adaptation", "respond"), ("priority", "price")])
def test_the_transport_schema_still_asks_for_steps_and_an_id(family, kind):
    schema = REGISTRY.transport_schema(family, kind=kind)
    assert schema["properties"]["workflows"] == {"items": {"$ref": "#/definitions/ProposedWorkflow"}, "type": "array"}
    workflow = schema["definitions"]["ProposedWorkflow"]
    assert {"id", "steps"} <= set(workflow["required"]) and "atoms" not in workflow["properties"]


# ---- write scope ------------------------------------------------------------------------------------------------------------
SPECS = load_function_specs()


def test_the_new_write_terms_name_the_records_j2_saves():
    assert WRITE_TERMS["conflict positions"] == ("conflicts.json",) and WRITE_TERMS["split registrations"] == ("workflows.json",)
    for function in ("adaptation", "priority"):
        assert "conflicts.json" in writable_records(SPECS.specs[function].writes), function
    assert "workflows.json" in writable_records(SPECS.specs["identity"].writes)


def test_the_new_terms_do_not_widen_the_other_functions():
    assert writable_records(SPECS.specs["audit"].writes) == {"audits.json", "conflicts.json"}
    assert "workflows.json" not in writable_records(SPECS.specs["audit"].writes)
    assert "conflicts.json" not in writable_records(SPECS.specs["adaptation"].writes) - writable_records(["conflict positions"])
    assert "conflict positions" not in SPECS.specs["identity"].writes and "split registrations" not in SPECS.specs["priority"].writes


def test_enforce_stays_reserved(tmp_path):
    writer = EventWriter(tmp_path)
    with pytest.raises(ValueError, match="reserved"):
        factory(writer, lambda: None, environ={"SUTRA_NODES": "enforce"})
    writer.close()


# ---- the golden run ---------------------------------------------------------------------------------------------------------
@pytest.fixture(scope="module")
def run(tmp_path_factory):
    return rec.run_scenario(tmp_path_factory.mktemp("fn-tuning"), "on")


def test_the_mock_run_has_no_unexplained_verify_failed_atom(run):
    assert unexplained_failures(run["events"]) == []
    assert len(final_atoms(run["events"])) == 31
    assert {e["outcome"] for e in final_atoms(run["events"]).values()} == {"closed"}


def test_the_mock_run_logs_no_touches_miss(run):
    assert [t["data"] for t in run["trace"] if t["type"] == "layer.touches_miss"] == []


def test_the_recorded_golden_has_neither(run):
    golden = json.loads((GOLD / rec.ATOMS_FILE).read_text(encoding="utf-8"))
    assert golden["touches_miss"] == {} and {a["failing_check"] for a in golden["atoms"]} == {None}
    assert rec.atoms_golden(run["events"], run["trace"])["atoms"] == golden["atoms"]
    recorded = [json.loads(line) for line in (GOLD / rec.EVENTS_FILE).read_text(encoding="utf-8").splitlines()]
    assert unexplained_failures(recorded) == []


def test_every_check_of_the_run_judged_some_atoms_and_none_failed(run):
    rows = {r["check"]: r for r in check_report(run["events"])}
    assert {"reply-valid", "turn-posted", "charter-stamp"} <= set(rows)
    assert rows["reply-valid"]["judged"] == 21 and sum(r["failed"] for r in rows.values()) == 0
    assert all(r["judged"] >= 1 for r in rows.values())


# ---- the guard itself: a failure that nobody listed fails the test ---------------------------------------------------------
def failed_event(function="adaptation", check="reply-valid", atom_id="a-x-01"):
    body = {"abandon_code": "verify_failed", "verify": {"checks": [
        {"template": check, "results": [{"attempt": 1, "evidence": "bad", "exit_code": 1, "ts": 1}]}]}}
    atom = {"schema": "work-atom/0.3", "id": atom_id, "reason": f"verify failed: {check}: goal: nope", "body": body}
    return {"t": "atom", "node": f"web.{function}", "outcome": "abandoned", "atom": atom}


def test_a_verify_failed_atom_that_is_not_listed_is_found():
    assert unexplained_failures([failed_event()]) == ["adaptation/reply-valid a-x-01"]


def test_a_listed_verify_failed_atom_is_not_reported_and_a_neighbour_still_is():
    allow = {("adaptation", "reply-valid"): "the scenario shows a refusal"}
    assert unexplained_failures([failed_event()], allow) == []
    assert unexplained_failures([failed_event(), failed_event("priority", "within-budget", "a-y-01")], allow) == [
        "priority/within-budget a-y-01"]


def test_the_allow_list_gives_a_reason_for_each_entry():
    assert all(isinstance(why, str) and len(why) > 10 for why in ALLOWED_VERIFY_FAILED.values())


def test_the_report_counts_failed_recovered_and_waived_atoms_per_check():
    def event(atom_id, check, evidence, code=0):
        body = {"verify": {"checks": [{"template": check, "results": [{"attempt": 1, "evidence": evidence, "exit_code": code, "ts": 1}]},
                                      {"template": "never-run", "results": []}]}}
        return {"t": "atom", "node": "web.audit", "outcome": "closed",
                "atom": {"schema": "work-atom/0.3", "id": atom_id, "reason": None, "body": body}}
    rows = check_report([event("a1", "judge-gate", "ok"), event("a2", "judge-gate", "RECOVERED: kept", 0),
                         event("a3", "judge-gate", "WAIVED: accepted", 0), event("a4", "judge-gate", "no", 1)])
    assert rows == [{"check": "judge-gate", "judged": 4, "failed": 1, "recovered": 1, "waived": 1}]
    assert render_report(rows).splitlines()[2] == "| judge-gate | 4 | 1 | 1 | 1 |"


if __name__ == "__main__":
    events = [json.loads(line) for line in (GOLD / rec.EVENTS_FILE).read_text(encoding="utf-8").splitlines()]
    print(render_report(check_report(events)))
    sys.exit(1 if unexplained_failures(events) else 0)
