"""The tool-call audit (MAN-14, D325, D327): what a node's tool calls leave in the audit is a name, a kind and a file's base name, never an input; the router tells the node's host only for a call whose
tag names a node; the host's `tools.jsonl` is small, limited and best effort; the Conductor turns it into audit rows when the node ends, whatever way it ends."""
import json

import pytest
from orchestrator.projects_rig import PRig  # noqa: F401

from sutra_app.connectors import tool_audit
from sutra_app.engine.host import toollog


# ---- what is kept ------------------------------------------------------------------------------------------------------------------------------
def test_a_read_or_an_edit_keeps_the_base_name_of_its_file_and_nothing_of_the_path():
    assert tool_audit.facts({"name": "Read", "input": {"file_path": "/Users/someone/work/site/index.html"}}) == ("Read", "read", "index.html")
    assert tool_audit.facts({"name": "Edit", "input": {"file_path": "C:\\work\\site\\style.css"}}) == ("Edit", "edit", "style.css")
    assert tool_audit.facts({"name": "Write", "input": {"path": "docs/readme.md"}}) == ("Write", "edit", "readme.md")


def test_a_command_a_query_a_url_and_the_arguments_of_an_app_tool_are_never_kept():
    secret = "ghp_" + "a" * 36
    assert tool_audit.facts({"name": "Bash", "input": {"command": f"curl -H 'token: {secret}' https://x.example/a"}}) == ("Bash", "run", "")
    assert tool_audit.facts({"name": "Grep", "input": {"pattern": "password", "path": "/home/x/secret"}}) == ("Grep", "search", "")
    assert tool_audit.facts({"name": "WebFetch", "input": {"url": "https://x.example/private?k=1"}}) == ("WebFetch", "web", "")
    assert tool_audit.facts({"name": "mcp__sutra__github_repo_get", "input": {"owner": "me", "repo": "private"}}) == ("mcp__sutra__github_repo_get", "github", "")
    assert tool_audit.facts({"name": "mcp__sutra__sutra_chart_read", "input": {"department_id": "web"}}) == ("mcp__sutra__sutra_chart_read", "sutra", "")


def test_a_name_that_is_not_a_tool_is_skipped_and_a_hostile_name_is_made_safe():
    assert tool_audit.facts({"name": "StructuredOutput", "input": {}}) is None
    for bad in (None, 5, [], {}, {"name": ""}, {"name": "   "}):
        assert tool_audit.facts(bad) is None
    name, kind, target = tool_audit.facts({"name": "X" * 200 + "\n<script>", "input": {"file_path": "/a/" + "y" * 300}})
    assert len(name) <= tool_audit.NAME_MAX and "<" not in name and "\n" not in name and kind == "other" and target == ""
    assert tool_audit.facts({"name": "Read", "input": {"file_path": "/a/" + "y" * 300}})[2] == "y" * tool_audit.TARGET_MAX
    assert tool_audit.facts({"type": "command_execution", "id": "x"}, "codex") == ("command_execution", "run", "")             # Codex names the kind only


# ---- the router's hook ---------------------------------------------------------------------------------------------------------------------------
class Tag:
    def __init__(self, node_id=""):
        self.node_id = node_id
        self.node_role = "worker" if node_id else ""


def watched(node_id, hook, on_event=None, provider="claude"):
    """Drive `Router._watched` the way `_text_call` does: it is the one place the hook is wired, so a test of it is a test of the wiring without a model."""
    from sutra_app.connectors.models import ConnectorEvent
    from sutra_app.connectors.router import Router
    router = Router.__new__(Router)
    router.on_tool = hook
    wrapped = router._watched(Tag(node_id), provider, on_event)
    return wrapped, ConnectorEvent


def test_the_hook_is_told_names_and_kinds_for_a_node_and_for_no_other_call():
    told = []
    wrapped, Event = watched("nd_0123456789ab", lambda tag, name, kind, target: told.append((tag.node_id, name, kind, target)))
    wrapped(Event(kind="tool_call", data={"id": "1", "name": "Read", "input": {"file_path": "/w/a.txt"}}))
    wrapped(Event(kind="text", data={"text": "hello"}))
    wrapped(Event(kind="tool_call", data={"id": "2", "name": "StructuredOutput", "input": {}}))
    assert told == [("nd_0123456789ab", "Read", "read", "a.txt")]
    other = []
    same, _Event = watched("", lambda *a: other.append(a), on_event=None)
    assert same is None and other == []                                                    # no node in the tag: the call is untouched, not even wrapped
    keep = lambda event: None                                                              # noqa: E731
    same, _Event = watched("", lambda *a: other.append(a), on_event=keep)
    assert same is keep
    off, _Event = watched("nd_0123456789ab", None, on_event=keep)
    assert off is keep                                                                     # no hook set: the very same object


def test_the_progress_of_the_page_still_gets_every_event_and_a_hook_that_fails_stops_nothing():
    seen = []

    def boom(*args):
        raise RuntimeError("the hook is broken")

    wrapped, Event = watched("nd_0123456789ab", boom, on_event=seen.append)
    wrapped(Event(kind="tool_call", data={"name": "Bash", "input": {"command": "ls"}}))
    wrapped(Event(kind="text", data={"text": "x"}))
    assert [e.kind for e in seen] == ["tool_call", "text"]


# ---- the host's file ------------------------------------------------------------------------------------------------------------------------------
def test_the_log_is_one_small_line_for_each_call_and_reads_back_whole(tmp_path):
    where = toollog.log_path(tmp_path, "j2-20261104-100000-bbbb")
    log = toollog.ToolLog(where, clock=lambda: 1_700_000_000.9)
    log(Tag("nd_0123456789ab"), "Read", "read", "a.txt")
    log(Tag("nd_0123456789ab"), "Bash", "run", "")
    lines = where.read_text().splitlines()
    assert where == tmp_path / "nodes" / "tools" / "j2-20261104-100000-bbbb.jsonl"                 # outside every run folder (PB-6)
    assert json.loads(lines[0]) == {"at": 1_700_000_000, "name": "Read", "kind": "read", "target": "a.txt"}
    assert toollog.read_log(where) == [{"name": "Read", "kind": "read", "target": "a.txt"}, {"name": "Bash", "kind": "run", "target": ""}]


def test_the_log_stops_at_its_limit_and_a_damaged_or_missing_file_is_no_rows(tmp_path):
    where = tmp_path / toollog.TOOLS_FILE
    log = toollog.ToolLog(where)
    for _ in range(toollog.MAX_LINES + 50):
        log(Tag("n"), "Read", "read", "a.txt")
    assert len(toollog.read_log(where)) == toollog.MAX_LINES
    where.write_text('not json\n{"name": 5, "kind": "read"}\n{"name": "Read", "kind": "launch"}\n[1]\n{"name": "Edit", "kind": "edit", "target": 7}\n')
    assert toollog.read_log(where) == [{"name": "Edit", "kind": "edit", "target": ""}]
    assert toollog.read_log(tmp_path / "nowhere") == []
    where.write_text('{"name": "<b>Rm</b>\\n -rf", "kind": "run", "target": "a\\u0007b.txt"}\n{"name": "", "kind": "run"}\n')              # PB-6: the host's file is made safe again when it is read
    assert toollog.read_log(where) == [{"name": "b_Rm_b_-rf", "kind": "run", "target": "ab.txt"}]
    link = tmp_path / "link.jsonl"
    link.symlink_to(where)
    assert toollog.read_log(link) == []                                                                                  # a link is never followed


def test_a_log_that_cannot_be_written_never_stops_a_call(tmp_path):
    blocker = tmp_path / "blocked"
    blocker.write_text("a file where the folder should be")
    log = toollog.ToolLog(blocker / "x.jsonl")
    log(Tag("n"), "Read", "read", "a.txt")
    log(Tag("n"), "Read", "read", "a.txt")                                                # the second call does not even try
    assert toollog.read_log(blocker / "x.jsonl") == []


def test_calls_are_grouped_in_the_order_they_first_happened_and_what_does_not_fit_is_counted():
    rows = [{"name": n, "kind": "read", "target": t} for n, t in (("Read", "a"), ("Read", "b"), ("Read", "a"), ("Bash", ""), ("Read", "a"))]
    groups, left = toollog.summarize(rows)
    assert groups == [("Read", "read", "a", 3), ("Read", "read", "b", 1), ("Bash", "read", "", 1)] and left == 0
    groups, left = toollog.summarize(rows, limit=1)
    assert groups == [("Read", "read", "a", 3)] and left == 2


# ---- the Conductor's import ----------------------------------------------------------------------------------------------------------------------
@pytest.fixture
def rig(db, settings, clock, events, tmp_path):
    return PRig(db, settings, clock, events, max_runs=6, max_live=12, owner="edit")


def write_tools(rig, task_id, calls):
    row = rig.t.row(task_id)
    log = toollog.ToolLog(toollog.log_path(rig.projects.settings.data_dir, row.run_id))
    for name, kind, target in calls:
        log(Tag("n"), name, kind, target)


def started(rig):
    reservation, tasks = rig.request([("a1", "web", []), ("a2", "sales", [])])
    rig.start()
    for ref in ("a1", "a2"):
        rig.go(tasks[ref])
    return reservation, tasks


def test_a_node_that_ends_well_leaves_one_row_for_each_tool_with_its_kind_and_count(rig):
    reservation, tasks = started(rig)
    write_tools(rig, tasks["a1"], [("Read", "read", "a.txt"), ("Read", "read", "a.txt"), ("Write", "edit", "out.md"), ("Bash", "run", ""), ("mcp__sutra__github_repo_get", "github", "")])
    rig.finish(tasks["a1"], files={"out.md": "done"})
    rows = rig.audit("tool.used")
    assert [(r["target"], r["reason"]) for r in rows] == [("Read", "read a.txt, 2 times"), ("Write", "edit out.md, 1 time"), ("Bash", "run, 1 time"), ("mcp__sutra__github_repo_get", "github, 1 time")]
    assert {r["actor"] for r in rows} == {"node"} and {r["role"] for r in rows} == {"worker"} and {r["node_id"] for r in rows} == {rig.node_of(tasks["a1"])["id"]}
    assert not any("ghp_" in json.dumps(r) or "/" in r["reason"] for r in rows)                  # a name and a kind: no path, no input
    ended = [r["seq"] for r in rig.audit() if r["action"] in ("node.done", "tool.used") and r["node_id"] == rig.node_of(tasks["a1"])["id"]]
    assert ended == sorted(ended)


def test_a_node_that_made_no_tool_call_leaves_no_row_and_a_run_with_no_node_none_either(rig):
    reservation, tasks = started(rig)
    rig.finish(tasks["a1"], files={"out.md": "done"})
    assert rig.audit("tool.used") == []


def test_a_node_that_fails_still_leaves_what_it_did_and_an_attempt_leaves_only_its_own(rig):
    reservation, tasks = started(rig)
    write_tools(rig, tasks["a2"], [("Bash", "run", ""), ("Edit", "edit", "x.py")])
    rig.finish(tasks["a2"], status="crashed", outcome="Something broke", handoff=False)
    node_id = rig.sql("SELECT id FROM agent_nodes WHERE plan_ref = 'a2'").fetchone()["id"]
    mine = [r for r in rig.audit("tool.used") if r["node_id"] == node_id]               # the node was tried again: the attempt that ended is on the record
    assert [r["target"] for r in mine] == ["Bash", "Edit"]


def test_a_node_ended_before_the_file_could_be_read_ahead_is_read_at_its_end(rig):
    reservation, tasks = started(rig)
    write_tools(rig, tasks["a1"], [("Grep", "search", "")])
    rig.projects.conductor._tools.pop(tasks["a1"], None)                                     # nothing was read ahead (a restart, or a task that ended at once)
    rig.finish(tasks["a1"], files={"out.md": "done"})
    assert [r["target"] for r in rig.audit("tool.used")] == ["Grep"]


def test_many_different_tools_are_capped_and_the_rest_are_counted(rig):
    reservation, tasks = started(rig)
    write_tools(rig, tasks["a1"], [(f"Tool{i}", "other", "") for i in range(toollog.MAX_KINDS + 5)])
    rig.finish(tasks["a1"], files={"out.md": "done"})
    rows = rig.audit("tool.used")
    assert len(rows) == toollog.MAX_KINDS + 1 and rows[-1]["target"] == "more" and rows[-1]["reason"] == "5 more calls of other tools"


def test_a_node_that_fails_for_good_leaves_what_it_did_once(rig):
    reservation, tasks = started(rig)
    rig.sql("UPDATE projects SET caps_json = json_set(caps_json, '$.retries', 0) WHERE id = ?", reservation.project_id)
    write_tools(rig, tasks["a1"], [("Bash", "run", ""), ("Bash", "run", "")])
    rig.finish(tasks["a1"], status="crashed", outcome="it crashed", handoff=False)
    node_id = rig.sql("SELECT id FROM agent_nodes WHERE plan_ref = 'a1'").fetchone()["id"]
    assert rig.sql("SELECT state FROM agent_nodes WHERE id = ?", node_id).fetchone()["state"] == "failed"
    assert [(r["target"], r["reason"]) for r in rig.audit("tool.used") if r["node_id"] == node_id] == [("Bash", "run, 2 times")]
