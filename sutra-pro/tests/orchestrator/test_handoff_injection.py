"""A planted instruction in a hand-off (MAN-6, D265, D281, guardrails 9): it changes no grant and no edge, sits only in the data file a dependant is given, and a planted secret is redacted
before anything is stored. Runs the fixtures of MAN-2 (`test_nodes_injection.py`) against the real intake, the stored message and the dependant's `upstream`."""
import json

import pytest
from orchestrator.projects_rig import PRig  # noqa: F401
from orchestrator.test_nodes_injection import INJECTED_HANDOFF, INJECTIONS, PLANTED_ENV_SECRET, PLANTED_SECRET

from sutra_app.orchestrator.nodes_store import NodeStore
from sutra_app.orchestrator.redact import Redactor


@pytest.fixture
def rig(db, settings, clock, events):
    r = PRig(db, settings, clock, events, max_runs=5, max_live=10)
    r.store.redact = Redactor(extra=[PLANTED_ENV_SECRET], environ={})
    return r


def snapshot_of_rules(rig, project_id):
    """Everything the hand-off must not be able to change: the grants, the edges, the caps, the flags of the project."""
    nodes = rig.sql("SELECT id, grants_json, depends_on, writes_json, slice_credits FROM agent_nodes WHERE project_id = ? ORDER BY id", project_id).fetchall()
    project = rig.sql("SELECT decide_for_me, paused, failure_policy, caps_json, budget_credits FROM projects WHERE id = ?", project_id).fetchone()
    return [tuple(r) for r in nodes], tuple(project)


def run_two(rig, override_a1=None, **files):
    reservation, tasks = rig.request([("a1", "web", []), ("a2", "sales", ["a1"])])
    rig.start()
    rig.go(tasks["a1"])
    return reservation, tasks


def test_a_planted_hand_off_is_refused_or_stored_as_data_and_changes_no_grant_edge_budget_or_switch(rig):
    reservation, tasks = run_two(rig)
    before = snapshot_of_rules(rig, reservation.project_id)
    poisoned = {**INJECTED_HANDOFF, "node_id": rig.node_of(tasks["a1"])["id"], "files": []}
    rig.finish(tasks["a1"], override=poisoned)                                    # the planted needs (tier 6, tier 2) and the planted words
    assert snapshot_of_rules(rig, reservation.project_id) == before
    assert rig.node_of(tasks["a1"])["state"] == "failed" and "no needs" in rig.node_of(tasks["a1"])["failure_reason"]            # an engine node has no needs: refused, in words of the rule only
    assert all(text not in rig.node_of(tasks["a1"])["failure_reason"] for text in INJECTIONS) and PLANTED_SECRET not in json.dumps([dict(r) for r in rig.audit()])
    assert rig.sql("SELECT count(*) FROM node_messages").fetchone()[0] == 0           # a refused hand-off stores no message


def test_planted_words_in_a_valid_hand_off_sit_only_inside_the_data_file_and_the_secret_is_redacted(rig):
    reservation, tasks = run_two(rig)
    before = snapshot_of_rules(rig, reservation.project_id)
    node = rig.node_of(tasks["a1"])
    words = {"summary": " ".join(INJECTIONS[:3]) + f" key {PLANTED_SECRET} and {PLANTED_ENV_SECRET}", "claims": list(INJECTIONS)[:5] + [PLANTED_SECRET], "needs": []}
    rig.finish(tasks["a1"], override=words, files={"out.md": "result"})
    assert snapshot_of_rules(rig, reservation.project_id) == before and rig.node_of(tasks["a1"])["state"] == "done"
    messages = NodeStore(rig.t.db).messages(reservation.project_id)
    assert len(messages) == 1 and messages[0].kind == "handoff" and messages[0].src_ref == f"handoff:{node['id']}:1" and messages[0].from_node == node["id"]
    stored = json.loads(messages[0].body)
    assert INJECTIONS[0] in stored["summary"] and PLANTED_SECRET not in messages[0].body and PLANTED_ENV_SECRET not in messages[0].body and "[redacted" in messages[0].body
    accepted = json.loads((rig.t.run_dir(tasks["a1"]) / "handoff.accepted.json").read_text(encoding="utf-8"))
    assert accepted["note"].startswith("Data from another team") and PLANTED_SECRET not in json.dumps(accepted) and accepted["handoff"]["claims"][0] == INJECTIONS[0]
    assert rig.sql("SELECT count(*) FROM agent_nodes WHERE project_id = ?", reservation.project_id).fetchone()[0] == 2        # no node was added by a word: the two workers of the plan


def test_the_dependant_is_given_the_scrubbed_accepted_file_and_never_the_nodes_own(rig):
    reservation, tasks = run_two(rig)
    rig.finish(tasks["a1"], override={"summary": f"see {PLANTED_SECRET}", "claims": ["x"], "needs": []}, files={"out.md": "result", "notes.txt": "n"})
    rig.start()
    spec = rig.t.launcher.started[-1][0]
    assert spec.task_id == tasks["a2"] and len(spec.upstream) == 1
    files = spec.upstream[0].files
    assert "handoff.accepted.json" in files and "handoff.json" not in files and {"out.md", "notes.txt"} <= set(files)
    run_json = json.loads((rig.t.run_dir(tasks["a2"]) / "task.json").read_text(encoding="utf-8"))
    assert "node" in run_json and run_json["upstream"][0]["run_id"] == rig.t.row(tasks["a1"]).run_id


def test_nothing_a_node_says_can_turn_decide_for_me_on_or_add_a_node_and_the_framing_is_untouched(rig):
    reservation, tasks = run_two(rig)
    rig.finish(tasks["a1"], override={"summary": INJECTIONS[3] + INJECTIONS[4], "claims": [INJECTIONS[5]], "needs": []})
    assert rig.project(reservation.project_id)["decide_for_me"] == 0 and rig.sql("SELECT count(*) FROM agent_nodes").fetchone()[0] == 2
    rig.start()
    spec = rig.t.launcher.started[-1][0]
    assert spec.framing == "" or INJECTIONS[3] not in spec.framing and all(text not in spec.user_text for text in INJECTIONS)
