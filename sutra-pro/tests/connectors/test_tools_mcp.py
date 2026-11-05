"""The MCP server, the tool profiles and the read-only Sutra tools (work package CN-8, connectors design 3.9, CD14)."""
from __future__ import annotations

import json
import os
import sqlite3
import stat
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

from sutra_app.connectors.claude import ClaudeConnector
from sutra_app.connectors.codex import CodexConnector
from sutra_app.connectors.env import is_secret_name
from sutra_app.connectors.models import ConnectorConfig
from sutra_app.connectors.tools import mcp_server, profiles, sutra_tools
from sutra_app.connectors.tools.mcp_server import McpServer, encode_result, serve
from sutra_app.connectors.tools.profiles import ToolError, ToolSpec, validate_args
from sutra_app.orchestrator.schema import DDL_V1

REPO = Path(__file__).resolve().parents[2]


# ---- helpers -------------------------------------------------------------------------------------------------------------------

def rpc(method, id=1, params=None):
    msg = {"jsonrpc": "2.0", "method": method, "id": id}
    if params is not None:
        msg["params"] = params
    return msg


def call(name, arguments=None, id=1):
    return rpc("tools/call", id, {"name": name, "arguments": arguments or {}})


def payload(response):
    """The decoded JSON text of a tools/call result, and its isError flag."""
    result = response["result"]
    assert len(result["content"]) == 1 and result["content"][0]["type"] == "text"
    return json.loads(result["content"][0]["text"]), result["isError"]


def echo_tool():
    schema = {"type": "object", "properties": {"n": {"type": "integer", "minimum": 1, "maximum": 5}}, "required": ["n"],
              "additionalProperties": False}
    return ToolSpec("echo", "Echo n.", schema, lambda a: {"n": a["n"]})


def run_server(lines, *args, env=None, timeout=60):
    """Run the real server as a subprocess; -> (list of decoded stdout lines, stderr, returncode)."""
    text = "".join(line if isinstance(line, str) else json.dumps(line) + "\n" for line in lines)
    base = {"PATH": os.environ["PATH"], "HOME": os.environ.get("HOME", "/tmp"), "PYTHONPATH": str(REPO)}
    base.update(env or {})
    proc = subprocess.run([sys.executable, "-m", "sutra_app.connectors.tools.mcp_server", *args], input=text, capture_output=True,
                          text=True, timeout=timeout, env=base, cwd="/tmp")
    return [json.loads(x) for x in proc.stdout.splitlines()], proc.stderr, proc.returncode


def make_db(path: Path) -> Path:
    """A WAL-mode database with the orchestrator's real schema and a small chart, graph and atom."""
    conn = sqlite3.connect(path)
    conn.execute("PRAGMA journal_mode=WAL")
    for statement in DDL_V1:
        conn.execute(statement)
    conn.execute("INSERT INTO meta VALUES ('graph_version', '7')")
    conn.execute("INSERT INTO org_charts VALUES (1, '{}', 'x', 1), (2, '{}', 'y', 2)")
    nodes = [("root", "root", "Acme", "the company", "active"), ("eng", "department", "Engineering", "builds", "active"),
             ("web", "division", "Web", "sites", "active"), ("ops", "department", "Operations", "runs", "active"),
             ("old", "department", "Old", "gone", "archived")]
    for node_id, kind, name, purpose, state in nodes:
        conn.execute("INSERT INTO org_nodes (id, kind, name, purpose, state, created_rev, ts) VALUES (?,?,?,?,?,1,1)",
                     (node_id, kind, name, purpose, state))
    conn.executemany("INSERT INTO org_edges VALUES (?,?,?)", [("root", "eng", 0), ("root", "ops", 1), ("root", "old", 2), ("eng", "web", 0)])
    conn.execute("INSERT INTO departments VALUES ('eng', 'departments/eng', '{}', 'x', 1)")
    conn.execute("INSERT INTO tasks (id, dept_id, title, user_text, status, created_at) VALUES ('t1','eng','Site','make a site','running',1)")
    for node_id, kind, state, task in (("g1", "department", "running", None), ("g2", "identity", "idle", None), ("g3", "step", "done_unchecked", "t1")):
        conn.execute("INSERT INTO graph_nodes (id, kind, department_id, state, label, task_id, step_ref, body, sha256, ts) "
                     "VALUES (?,?,?,?,?,?,?,'{}','x',1)", (node_id, kind, "eng", state, f"label {node_id}", task, "s1" if task else None))
    conn.execute("INSERT INTO graph_edges (id, kind, from_id, to_id, body) VALUES ('e1','handoff','g1','g2','{}')")
    conn.execute("INSERT INTO graph_edges (id, kind, from_id, to_id, body) VALUES ('e2','step','g2','g3','{}')")
    body = json.dumps({"goal": "make a site", "task": "pick the colours", "context": {"brand": "teal"}})
    conn.execute("INSERT INTO atoms (id, schema, node_id, state, display, attempt, goal, body, sha256, ts_open) "
                 "VALUES ('a1','work-atom/0.3','g2','open','open',0,'make a site',?, 'x', 5)", (body,))
    conn.commit()
    conn.close()
    return path


@pytest.fixture
def db(tmp_path):
    return make_db(tmp_path / "sutra.db")


# ---- the protocol, in process ----------------------------------------------------------------------------------------------------

def test_initialize_echoes_the_client_protocol_version():
    server = McpServer([echo_tool()])
    for version in ("2025-11-25", "2025-06-18"):
        out = server.handle(rpc("initialize", 0, {"protocolVersion": version, "capabilities": {}}))
        assert out["result"]["protocolVersion"] == version
        assert out["result"]["capabilities"] == {"tools": {"listChanged": False}}
        assert out["result"]["serverInfo"]["name"] == "sutra"
    assert server.handle(rpc("initialize", 0, {}))["result"]["protocolVersion"] == mcp_server.DEFAULT_PROTOCOL


def test_notifications_are_ignored_and_ping_answers():
    server = McpServer([echo_tool()])
    assert server.handle({"jsonrpc": "2.0", "method": "notifications/initialized"}) is None
    assert server.handle({"jsonrpc": "2.0", "method": "no/such/notification"}) is None
    assert server.handle(rpc("ping", 9)) == {"jsonrpc": "2.0", "id": 9, "result": {}}


def test_server_discover_and_unknown_methods_are_32601():
    server = McpServer([echo_tool()])
    for method in ("server/discover", "resources/list", "whatever"):
        out = server.handle(rpc(method, "k"))
        assert out["id"] == "k" and out["error"]["code"] == -32601


def test_tools_list_marks_every_tool_read_only():
    out = McpServer([echo_tool()]).handle(rpc("tools/list"))
    [tool] = out["result"]["tools"]
    assert tool["name"] == "echo" and tool["inputSchema"]["required"] == ["n"]
    assert tool["annotations"] == {"readOnlyHint": True}


def test_tools_call_wraps_the_result_as_json_text():
    out = McpServer([echo_tool()]).handle(call("echo", {"n": 3}))
    assert payload(out) == ({"n": 3}, False)


def test_tool_error_is_a_result_with_is_error():
    def boom(a):
        raise ToolError("not_found", "no such thing")
    server = McpServer([ToolSpec("boom", "x", {"type": "object", "properties": {}}, boom)])
    assert payload(server.handle(call("boom"))) == ({"error": {"code": "not_found", "message": "no such thing"}}, True)


def test_bad_arguments_are_a_tool_error_naming_the_argument():
    server = McpServer([echo_tool()])
    for args, fragment in (({}, "missing required argument 'n'"), ({"n": "3"}, "must be an integer"), ({"n": True}, "must be an integer"),
                           ({"n": 9}, "must be from"), ({"n": 1, "x": 1}, "unknown argument 'x'")):
        body, is_error = payload(server.handle(call("echo", args)))
        assert is_error and body["error"]["code"] == "invalid_arguments" and fragment in body["error"]["message"]


def test_unknown_tool_and_bad_params_are_32602():
    server = McpServer([echo_tool()])
    assert server.handle(call("nope"))["error"]["code"] == -32602
    assert server.handle(rpc("tools/call", 1, {"arguments": {}}))["error"]["code"] == -32602
    assert server.handle(rpc("tools/call", 1, "x"))["error"]["code"] == -32602


def test_a_crashing_tool_does_not_end_the_server(capsys):
    def crash(a):
        raise RuntimeError("secret detail")
    server = McpServer([ToolSpec("crash", "x", {"type": "object", "properties": {}}, crash), echo_tool()])
    body, is_error = payload(server.handle(call("crash")))
    assert is_error and body["error"]["code"] == "internal" and "secret detail" not in json.dumps(body)
    assert payload(server.handle(call("echo", {"n": 1})))[1] is False


def test_malformed_input_gets_the_right_error_and_serving_continues(tmp_path):
    import io
    out = io.StringIO()
    lines = ["{not json\n", "\n", "42\n", json.dumps({"jsonrpc": "2.0", "id": True, "method": "ping"}) + "\n", json.dumps(rpc("ping", 5)) + "\n"]
    serve(McpServer([]), io.StringIO("".join(lines)), out)
    answers = [json.loads(x) for x in out.getvalue().splitlines()]
    assert [a.get("error", {}).get("code") for a in answers] == [-32700, -32600, -32600, None]
    assert answers[0]["id"] is None and answers[-1] == {"jsonrpc": "2.0", "id": 5, "result": {}}


def test_a_result_over_the_limit_is_cut_and_still_valid_json():
    big = {"text": "x" * 500}
    cut = json.loads(encode_result(big, limit=100))
    assert cut["truncated"] is True and cut["limit"] == 100 and len(cut["text"]) == 100
    assert json.loads(encode_result(big, limit=10_000)) == big


def test_tools_are_resolved_lazily_and_once():
    seen = []

    def source():
        seen.append(1)
        return [echo_tool()]
    server = McpServer(source)
    assert seen == []
    server.handle(rpc("tools/list"))
    server.handle(call("echo", {"n": 1}))
    assert seen == [1]


# ---- the argument checker -----------------------------------------------------------------------------------------------------------

def test_validate_args_string_rules():
    schema = {"properties": {"s": {"type": "string", "pattern": "[a-z]+", "maxLength": 5, "enum": ["abc", "de"]}}}
    assert validate_args(schema, {"s": "abc"}) == {"s": "abc"}
    for bad in (1, "ABC", "abcdef", "zz", "a\0"):
        with pytest.raises(ToolError):
            validate_args(schema, {"s": bad})
    with pytest.raises(ToolError):
        validate_args(schema, [])
    assert validate_args(schema, None) == {}


# ---- the real server, as a subprocess ---------------------------------------------------------------------------------------------

@pytest.mark.parametrize("script,version", [("claude_client_requests.jsonl", "2025-11-25"), ("codex_client_requests.jsonl", "2025-06-18")])
def test_captured_client_scripts_replay(fixtures, db, script, version):
    lines = [json.dumps(x) + "\n" if isinstance(x, dict) else x + "\n" for x in fixtures.lines(f"mcp/{script}")]
    answers, stderr, code = run_server(lines, "--profile", "sutra", "--db", str(db))
    assert code == 0
    by_id = {a["id"]: a for a in answers}
    assert by_id[0]["result"]["protocolVersion"] == version
    names = {t["name"] for t in by_id[1]["result"]["tools"]}
    assert {"sutra_chart_read", "sutra_atom_read", "sutra_graph_read"} <= names
    if script.startswith("claude"):
        assert by_id["server-discover-probe-1"]["error"]["code"] == -32601
    assert len(answers) == (3 if script.startswith("claude") else 2)       # the notification gets no answer


def test_server_survives_a_malformed_line_and_keeps_stdout_clean(db):
    answers, stderr, code = run_server(["garbage\n", rpc("ping", 7)], "--profile", "sutra", "--db", str(db))
    assert code == 0
    assert [a.get("error", {}).get("code") for a in answers] == [-32700, None] and answers[1]["id"] == 7


def test_server_reads_the_database_named_in_the_environment(db):
    answers, _, _ = run_server([call("sutra_atom_read", {"atom_id": "a1"})], "--profile", "sutra", env={"SUTRA_DB_RO": str(db)})
    body, is_error = payload(answers[0])
    assert not is_error and body["goal"] == "make a site" and body["body"]["task"] == "pick the colours"


def test_server_exits_2_for_a_bad_profile_and_a_missing_database():
    for args in (["--profile", "mongo"], ["--profile", "sutra"], ["--profile", "sutra", "--readmodel", "nocolon"]):
        answers, stderr, code = run_server([], *args)
        assert code == 2 and "mcp_server" in stderr and answers == []
    assert run_server([], "--profile", "sutra")[2] == 2
    _, stderr, code = run_server([], "--bogus")
    assert code == 2 and "usage" in stderr.lower()


def test_profile_none_serves_no_tools():
    answers, _, code = run_server([rpc("tools/list")], "--profile", "none")
    assert code == 0 and answers[0]["result"]["tools"] == []


# ---- the Sutra tools over the read-only database ----------------------------------------------------------------------------------

def test_chart_whole_tree_skips_archived_and_orders_children(db):
    out = sutra_tools.SqliteReadModel(db).chart(None, None)
    assert out["revision"] == 2
    root = out["root"]
    assert root["id"] == "root" and [c["id"] for c in root["children"]] == ["eng", "ops"]
    assert root["children"][0]["children"][0]["id"] == "web"


def test_chart_department_and_depth(db):
    rm = sutra_tools.SqliteReadModel(db)
    assert rm.chart("eng", None)["root"]["children"][0]["name"] == "Web"
    top = rm.chart(None, 0)["root"]
    assert "children" not in top and top["children_hidden"] == 2
    one = rm.chart(None, 1)["root"]
    assert one["children"][0]["children_hidden"] == 1 and "children_hidden" not in one["children"][1]


def test_chart_unknown_or_archived_department_is_not_found(db):
    for bad in ("nope", "old"):
        with pytest.raises(ToolError) as info:
            sutra_tools.SqliteReadModel(db).chart(bad, None)
        assert info.value.code == "not_found"


def test_graph_summary_filter_and_edges(db):
    rm = sutra_tools.SqliteReadModel(db)
    whole = rm.graph(None)
    assert whole["node_count"] == 3 and whole["graph_version"] == "7" and whole["truncated"] is False
    assert whole["states"] == {"running": 1, "idle": 1, "done_unchecked": 1}
    assert {(e["from"], e["to"]) for e in whole["edges"]} == {("g1", "g2"), ("g2", "g3")}
    one_task = rm.graph("t1")
    assert [n["id"] for n in one_task["nodes"]] == ["g3"] and one_task["edges"] == []
    assert rm.graph("eng")["node_count"] == 3
    with pytest.raises(ToolError) as info:
        rm.graph("zzz")
    assert info.value.code == "not_found"


def test_graph_node_list_is_capped(db, monkeypatch):
    monkeypatch.setattr(sutra_tools, "MAX_NODES", 2)
    out = sutra_tools.SqliteReadModel(db).graph(None)
    assert out["truncated"] is True and out["node_count"] == 3 and len(out["nodes"]) == 2
    assert all(e["from"] in {"g1", "g2"} and e["to"] in {"g1", "g2"} for e in out["edges"])


def test_atom_read_parses_the_body_and_reports_a_missing_one(db):
    atom = sutra_tools.SqliteReadModel(db).atom("a1")
    assert atom["display"] == "open" and atom["body"]["context"] == {"brand": "teal"} and atom["ts_closed"] is None
    with pytest.raises(ToolError) as info:
        sutra_tools.SqliteReadModel(db).atom("a9")
    assert info.value.code == "not_found"


def test_a_missing_database_is_a_tool_error_not_a_crash(tmp_path):
    with pytest.raises(ToolError) as info:
        sutra_tools.SqliteReadModel(tmp_path / "none.db").atom("a1")
    assert info.value.code == "no_data"
    broken = tmp_path / "bad.db"
    broken.write_text("this is not a database")
    with pytest.raises(ToolError) as info:
        sutra_tools.SqliteReadModel(broken).atom("a1")
    assert info.value.code == "read_failed"


def test_the_database_is_opened_read_only_even_in_wal_mode(db):
    assert sqlite3.connect(db).execute("PRAGMA journal_mode").fetchone()[0] == "wal"
    conn = sutra_tools.SqliteReadModel(db)._open()
    try:
        assert conn.execute("SELECT count(*) FROM atoms").fetchone()[0] == 1
        with pytest.raises(sqlite3.OperationalError):
            conn.execute("INSERT INTO meta VALUES ('x', 'y')")
        with pytest.raises(sqlite3.OperationalError):
            conn.execute("DELETE FROM atoms")
    finally:
        conn.close()
    conn = sutra_tools.SqliteReadModel(db)._open()               # the file mode alone must refuse a write too
    try:
        conn.execute("PRAGMA query_only = OFF")
        with pytest.raises(sqlite3.OperationalError):
            conn.execute("INSERT INTO meta VALUES ('x', 'y')")
    finally:
        conn.close()
    assert sqlite3.connect(db).execute("SELECT count(*) FROM meta").fetchone()[0] == 1


def test_model_tools_list_names_and_schemas():
    rm = sutra_tools.default_readmodel("/nonexistent/sutra.db")
    names = rm.model_names()
    assert "atom" in names and names == sorted(names)
    assert isinstance(rm.model_schema("atom"), dict)
    with pytest.raises(ToolError) as info:
        rm.model_schema("not_a_model")
    assert info.value.code == "not_found"


def test_tool_specs_follow_what_the_readmodel_supports(db):
    class Partial:
        def chart(self, department_id, depth):
            return {"root": None}

        def atom(self, atom_id):
            return {"id": atom_id}
    assert [s.name for s in sutra_tools.tool_specs(Partial())] == ["sutra_chart_read", "sutra_atom_read"]
    assert [s.name for s in sutra_tools.tool_specs(None)] == list(sutra_tools.TOOL_METHODS)
    full = sutra_tools.tool_specs(sutra_tools.default_readmodel(db))
    assert [s.name for s in full] == list(sutra_tools.TOOL_METHODS)
    assert all(s.read_only for s in full)


def test_tool_handlers_pass_their_arguments_to_the_readmodel():
    seen = {}

    class Spy:
        def chart(self, department_id, depth):
            seen["chart"] = (department_id, depth)
            return {}

        def graph(self, workflow_id):
            seen["graph"] = workflow_id
            return {}

        def atom(self, atom_id):
            seen["atom"] = atom_id
            return {}

        def model_names(self):
            return ["b", "a"]

        def model_schema(self, name):
            seen["schema"] = name
            return {}
    server = McpServer(sutra_tools.tool_specs(Spy()))
    server.handle(call("sutra_chart_read", {"department_id": "eng", "depth": 2}))
    server.handle(call("sutra_graph_read", {"workflow_id": "t1"}))
    server.handle(call("sutra_atom_read", {"atom_id": "a1"}))
    server.handle(call("sutra_model_schema", {"name": "atom"}))
    assert seen == {"chart": ("eng", 2), "graph": "t1", "atom": "a1", "schema": "atom"}
    assert payload(server.handle(call("sutra_models_list")))[0] == {"models": ["b", "a"]}


def test_tool_arguments_refuse_odd_ids_and_depth():
    server = McpServer(sutra_tools.tool_specs(sutra_tools.default_readmodel("/nonexistent")))
    for name, args in (("sutra_atom_read", {"atom_id": "../etc"}), ("sutra_atom_read", {}), ("sutra_chart_read", {"depth": 99}),
                       ("sutra_chart_read", {"depth": -1}), ("sutra_model_schema", {"name": "a b"})):
        assert payload(server.handle(call(name, args)))[0]["error"]["code"] == "invalid_arguments"


def test_a_custom_readmodel_factory_is_loaded(tmp_path, monkeypatch):
    (tmp_path / "cn8_rm.py").write_text(textwrap.dedent("""
        class RM:
            def __init__(self, path):
                self.path = path
            def atom(self, atom_id):
                return {"id": atom_id, "path": self.path}
        def factory(path):
            return RM(path)
    """))
    monkeypatch.syspath_prepend(str(tmp_path))
    model = sutra_tools.load_readmodel("cn8_rm:factory", "/some/db")
    assert model.atom("z") == {"id": "z", "path": "/some/db"}
    assert [s.name for s in sutra_tools.tool_specs(model)] == ["sutra_atom_read"]
    answers, _, _ = run_server([rpc("tools/list")], "--profile", "sutra", "--readmodel", "cn8_rm:factory", "--db", "/x",
                               env={"PYTHONPATH": f"{tmp_path}{os.pathsep}{REPO}"})
    assert [t["name"] for t in answers[0]["result"]["tools"]] == ["sutra_atom_read"]


def test_load_readmodel_refuses_a_bad_spec_and_no_database():
    with pytest.raises(ValueError):
        sutra_tools.load_readmodel("nocolon", "/x")
    with pytest.raises(ValueError):
        sutra_tools.load_readmodel(None, None)


def test_every_sutra_tool_is_served_end_to_end_read_only(db):
    lines = [rpc("tools/list", 1), call("sutra_chart_read", {"depth": 1}, 2), call("sutra_graph_read", {}, 3),
             call("sutra_models_list", {}, 4), call("sutra_model_schema", {"name": "atom"}, 5), call("sutra_atom_read", {"atom_id": "zz"}, 6)]
    answers, _, code = run_server(lines, "--profile", "sutra", "--db", str(db))
    assert code == 0
    tools = answers[0]["result"]["tools"]
    assert len(tools) == 5 and all(t["annotations"]["readOnlyHint"] for t in tools)
    assert payload(answers[1])[0]["root"]["id"] == "root"
    assert payload(answers[2])[0]["node_count"] == 3
    assert "atom" in payload(answers[3])[0]["models"] and payload(answers[4])[1] is False
    assert payload(answers[5]) == ({"error": {"code": "not_found", "message": "no atom 'zz'"}}, True)


# ---- profiles ---------------------------------------------------------------------------------------------------------------------

@pytest.fixture
def cfg(tmp_path):
    return ConnectorConfig(data_dir=tmp_path / "data", work_root=tmp_path / "work", python="/usr/bin/pyx")


def test_profile_names():
    assert profiles.PROFILES == ("none", "sutra", "sutra+github")
    assert profiles.profile_name(()) == "none" and profiles.profile_name(("none",)) == "none"
    assert profiles.profile_name(("sutra",)) == "sutra"
    assert profiles.profile_name(("sutra", "github")) == profiles.profile_name(("sutra+github",)) == "sutra+github"


def test_mcp_servers_entry_is_golden(cfg, tmp_path):
    entry = profiles.mcp_servers(cfg, ("sutra", "github"))
    assert entry == {"sutra": {"command": "/usr/bin/pyx",
                               "args": ["-m", "sutra_app.connectors.tools.mcp_server", "--profile", "sutra,github"],
                               "env": {"PYTHONPATH": str(REPO), "SUTRA_DB_RO": str(tmp_path / "data" / "db.sqlite3")}}}
    assert profiles.mcp_servers(cfg, ("none",)) == {} and profiles.mcp_servers(cfg, ()) == {}
    assert profiles.mcp_servers(cfg, ("sutra",))["sutra"]["args"][-1] == "sutra"


def test_mcp_env_holds_a_path_and_nothing_secret(cfg, monkeypatch):
    monkeypatch.setenv("GITHUB_TOKEN", "ghp_secret")
    env = profiles.mcp_servers(cfg, ("sutra", "github"))["sutra"]["env"]
    assert sorted(env) == ["PYTHONPATH", "SUTRA_DB_RO"]
    assert not any(is_secret_name(k) for k in env) and "ghp_secret" not in json.dumps(profiles.mcp_servers(cfg, ("sutra", "github")))


def test_gh_exe_and_readmodel_appear_only_when_set(tmp_path):
    cfg = ConnectorConfig(data_dir=tmp_path, gh_exe="/opt/fakes/gh")
    args = profiles.mcp_servers(cfg, ("sutra", "github"), readmodel="pkg.mod:make")["sutra"]["args"]
    assert args[-4:] == ["--gh-exe", "/opt/fakes/gh", "--readmodel", "pkg.mod:make"]
    assert "--gh-exe" not in profiles.mcp_servers(cfg, ("sutra",))["sutra"]["args"]
    assert "--readmodel" not in profiles.mcp_servers(ConnectorConfig(data_dir=tmp_path), ("sutra",))["sutra"]["args"]


def test_same_entry_as_the_connectors_own_default(cfg):
    for tools in (("sutra",), ("sutra", "github")):
        assert ClaudeConnector(cfg).mcp_servers(tools) == profiles.mcp_servers(cfg, tools)
        assert CodexConnector(cfg).mcp_servers(tools) == profiles.mcp_servers(cfg, tools)
        assert CodexConnector(cfg)._mcp_flags(tools) == profiles.codex_mcp_flags(cfg, tools)


def test_claude_config_text_and_file(cfg, tmp_path):
    text = profiles.claude_mcp_config(cfg, ("sutra",))
    assert json.loads(text) == {"mcpServers": profiles.mcp_servers(cfg, ("sutra",))}
    with profiles.claude_mcp_file(cfg, ("sutra",), parent=tmp_path) as path:
        assert path.read_text() == text and path.name == "mcp.json"
        assert stat.S_IMODE(path.stat().st_mode) == 0o600 and stat.S_IMODE(path.parent.stat().st_mode) == 0o700
        directory = path.parent
    assert not directory.exists()


def test_claude_config_file_is_deleted_when_the_call_fails(cfg, tmp_path):
    with pytest.raises(RuntimeError):
        with profiles.claude_mcp_file(cfg, ("sutra",), parent=tmp_path) as path:
            raise RuntimeError("call failed")
    assert not path.exists() and list(tmp_path.glob("sutra-mcp-*")) == []


def test_codex_flags_are_golden(cfg, tmp_path):
    root = json.dumps(str(REPO))
    assert profiles.codex_mcp_flags(cfg, ("sutra",)) == [
        "-c", 'mcp_servers.sutra.command="/usr/bin/pyx"',
        "-c", 'mcp_servers.sutra.args=["-m","sutra_app.connectors.tools.mcp_server","--profile","sutra"]',
        "-c", f'mcp_servers.sutra.env={{PYTHONPATH={root},SUTRA_DB_RO={json.dumps(str(tmp_path / "data" / "db.sqlite3"))}}}']
    assert profiles.codex_mcp_flags(cfg, ()) == []


def test_tool_catalog_lists_ten_read_only_tools_or_fewer_by_profile():
    everything = profiles.tool_catalog("sutra+github")
    assert [t["name"] for t in everything] == list(sutra_tools.TOOL_METHODS) + [
        "github_repo_get", "github_pr_list", "github_pr_get", "github_issue_get", "github_file_get"]
    assert all(t["read_only"] is True and t["description"] for t in everything)
    assert len(profiles.tool_catalog("sutra")) == 5 and profiles.tool_catalog("none") == []


def test_tools_status_follows_gh_auth(fake, tmp_path):
    cfg = ConnectorConfig(**fake.config_kwargs(tmp_path))
    assert profiles.tools_status(cfg, env=fake.process_env()) == {"sutra": True, "github": True}
    fake.auth(gh="signed_out")
    assert profiles.tools_status(cfg, env=fake.process_env())["github"] is False
