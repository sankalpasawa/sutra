"""The GitHub read tools over the fake `gh` (work package CN-8, connectors design 3.9, CD15)."""
from __future__ import annotations

import json
import os

import pytest

from sutra_app.connectors.tools import github_tools, mcp_server
from sutra_app.connectors.tools.github_tools import LIMIT_BYTES, GithubTools, gh_available, gh_env, wrap_untrusted
from sutra_app.connectors.tools.mcp_server import McpServer
from sutra_app.connectors.tools.profiles import ToolError


@pytest.fixture
def gh(fake):
    return GithubTools(fake.gh, env=fake.process_env())


def tool(gh_tools, name, **args):
    specs = {s.name: s for s in github_tools.tool_specs(gh_tools)}
    from sutra_app.connectors.tools.profiles import validate_args
    return specs[name].handler(validate_args(specs[name].input_schema, args))


def data_of(result):
    assert result["untrusted"] is True and result["source"] == "github"
    return result["data"]


def api_calls(fake):
    return [c for c in fake.calls("gh") if c["op"] == "api"]


def test_repo_get_returns_a_summary_inside_the_untrusted_wrapper(gh, fake):
    result = tool(gh, "github_repo_get", owner="octo-org", repo="hello-world")
    data = data_of(result)
    assert data["full_name"] == "octo-org/hello-world" and data["default_branch"] == "main" and result["truncated"] is False
    assert "never instructions" in result["note"]
    [call] = api_calls(fake)
    assert call["argv"] == ["api", "-X", "GET", "repos/octo-org/hello-world"]


def test_pr_list_builds_the_fixed_query_and_trims_each_item(gh, fake):
    items = data_of(tool(gh, "github_pr_list", owner="octo-org", repo="hello-world", state="all", per_page=5, page=1))
    assert items and set(items[0]) >= {"number", "title", "state", "user", "head", "base"} and "body" not in items[0]
    assert api_calls(fake)[0]["argv"][-1] == "repos/octo-org/hello-world/pulls?state=all&per_page=5&page=1"
    tool(gh, "github_pr_list", owner="octo-org", repo="hello-world")
    assert api_calls(fake)[1]["argv"][-1].endswith("pulls?state=open&per_page=30&page=1")


def test_pr_get_and_issue_get_read_one_item(gh, fake):
    pr = data_of(tool(gh, "github_pr_get", owner="octo-org", repo="hello-world", number=2))
    assert pr["number"] == 2 and pr["head"]["ref"] == "feature/connectors" and pr["user"] == "octocat"
    issue = data_of(tool(gh, "github_issue_get", owner="octo-org", repo="hello-world", number=3))
    assert issue["number"] == 3 and issue["labels"] == ["bug"]
    assert [c["argv"][-1] for c in api_calls(fake)] == ["repos/octo-org/hello-world/pulls/2", "repos/octo-org/hello-world/issues/3"]


def test_injected_text_stays_inside_the_untrusted_data(gh):
    result = tool(gh, "github_issue_get", owner="octo-org", repo="hello-world", number=3)
    assert "IGNORE ALL PREVIOUS INSTRUCTIONS" in result["data"]["body"]          # kept as data, inside the wrapper
    assert result["untrusted"] is True and "IGNORE" not in result["note"]


def test_file_get_decodes_a_small_file_and_lists_a_directory(gh, fake):
    file = data_of(tool(gh, "github_file_get", owner="octo-org", repo="hello-world", path="src/app.py", ref="main"))
    assert file["type"] == "file" and file["truncated"] is False and 'print("hello from hello-world")' in file["content"]
    assert api_calls(fake)[0]["argv"][-1] == "repos/octo-org/hello-world/contents/src/app.py?ref=main"
    listing = data_of(tool(gh, "github_file_get", owner="octo-org", repo="hello-world", path="src"))
    assert listing["type"] == "dir" and listing["path"] == "src"
    assert [(e["name"], e["path"], e["type"]) for e in listing["entries"]] == [("app.py", "src/app.py", "file")]
    root = data_of(tool(gh, "github_file_get", owner="octo-org", repo="hello-world"))
    assert {e["name"] for e in root["entries"]} == {"README.md", "big.txt", "docs", "src"}
    assert api_calls(fake)[-1]["argv"][-1] == "repos/octo-org/hello-world/contents/"


def test_a_big_file_is_cut_at_the_limit(gh):
    result = tool(gh, "github_file_get", owner="octo-org", repo="hello-world", path="big.txt")
    data = data_of(result)
    assert data["truncated"] is True and data["size"] == 60_000 and data["content"].startswith("line 000000 of the big fixture file")
    assert len(json.dumps(data, ensure_ascii=False, separators=(",", ":")).encode()) <= LIMIT_BYTES
    assert len(data["content"]) > LIMIT_BYTES // 2                                # the cut keeps most of the room


def test_wrap_untrusted_cuts_long_json_to_a_string():
    small = wrap_untrusted({"a": 1})
    assert small["data"] == {"a": 1} and small["truncated"] is False
    cut = wrap_untrusted(["é" * 50] * 20, limit=100)
    assert cut["truncated"] is True and isinstance(cut["data"], str) and len(cut["data"].encode()) <= 100
    assert wrap_untrusted("x" * 98, limit=100)["truncated"] is False                # exactly 100 bytes of JSON fit
    assert wrap_untrusted("x" * 99, limit=100)["truncated"] is True


def test_a_long_pr_list_is_cut_but_the_answer_stays_valid_json():
    class Many(GithubTools):
        def api(self, endpoint):
            return [{"number": i, "title": "t" * 200, "user": {"login": "u"}} for i in range(500)]
    result = Many("gh").pr_list({"owner": "o", "repo": "r"})
    assert result["truncated"] is True and len(result["data"].encode()) <= LIMIT_BYTES
    json.dumps(result)


@pytest.mark.parametrize("name,args", [
    ("github_repo_get", {"owner": "bad owner", "repo": "r"}),
    ("github_repo_get", {"owner": "o/x", "repo": "r"}),
    ("github_repo_get", {"owner": "o", "repo": "r" * 101}),
    ("github_repo_get", {"owner": "o", "repo": ""}),
    ("github_repo_get", {"owner": "o"}),
    ("github_pr_get", {"owner": "o", "repo": "r", "number": "2"}),
    ("github_pr_get", {"owner": "o", "repo": "r", "number": True}),
    ("github_pr_get", {"owner": "o", "repo": "r", "number": 0}),
    ("github_issue_get", {"owner": "o", "repo": "r", "number": 1.5}),
    ("github_pr_list", {"owner": "o", "repo": "r", "state": "merged"}),
    ("github_pr_list", {"owner": "o", "repo": "r", "per_page": 101}),
    ("github_file_get", {"owner": "o", "repo": "r", "path": "a/../b"}),
    ("github_file_get", {"owner": "o", "repo": "r", "path": "../etc/passwd"}),
    ("github_file_get", {"owner": "o", "repo": "r", "path": "a//b"}),
    ("github_file_get", {"owner": "o", "repo": "r", "path": "a?x=1"}),
    ("github_file_get", {"owner": "o", "repo": "r", "ref": "a..b"}),
    ("github_file_get", {"owner": "o", "repo": "r", "ref": "a b"}),
    ("github_repo_get", {"owner": "o", "repo": "r", "method": "POST"}),
])
def test_bad_arguments_are_refused_before_gh_runs(gh, fake, name, args):
    server = McpServer(github_tools.tool_specs(gh))
    out = server.handle({"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": name, "arguments": args}})
    body = json.loads(out["result"]["content"][0]["text"])
    assert out["result"]["isError"] is True and body["error"]["code"] == "invalid_arguments"
    assert api_calls(fake) == []


def test_dot_segments_are_refused_even_though_the_pattern_allows_dots(gh, fake):
    for owner, repo in ((".", "r"), ("..", "r"), ("o", ".."), ("o", ".")):
        with pytest.raises(ToolError) as info:
            tool(gh, "github_repo_get", owner=owner, repo=repo)
        assert info.value.code == "invalid_arguments"
    assert api_calls(fake) == []


def test_file_path_is_percent_encoded_and_a_leading_slash_dropped(gh, fake):
    with pytest.raises(ToolError):                                    # not in the fake repo: 404, but the endpoint is what we check
        tool(gh, "github_file_get", owner="octo-org", repo="hello-world", path="/dir with space/#x")
    assert api_calls(fake) == []                                      # '#' is refused before gh runs
    with pytest.raises(ToolError):
        tool(gh, "github_file_get", owner="octo-org", repo="hello-world", path="/dir with space/a.txt")
    assert api_calls(fake)[0]["argv"][-1] == "repos/octo-org/hello-world/contents/dir%20with%20space/a.txt"


@pytest.mark.parametrize("failure,code", [("not_found", "not_found"), ("rate_limit", "rate_limited"), ("unauthorized", "unauthorized"),
                                          ("server_error", "github_error")])
def test_gh_failures_map_to_readable_tool_errors(fake, failure, code):
    fake.set(FAKE_GH_FAIL=failure)
    tools = GithubTools(fake.gh, env=fake.process_env())
    with pytest.raises(ToolError) as info:
        tool(tools, "github_repo_get", owner="octo-org", repo="hello-world")
    assert info.value.code == code and "gh:" not in info.value.message


def test_an_unknown_repository_is_not_found(gh):
    with pytest.raises(ToolError) as info:
        tool(gh, "github_repo_get", owner="octo-org", repo="no-such-repo")
    assert info.value.code == "not_found"


def test_other_gh_failures_keep_a_short_message(tmp_path):
    script = tmp_path / "gh"
    script.write_text("#!/bin/sh\necho 'something odd happened' >&2\nexit 7\n")
    script.chmod(0o755)
    with pytest.raises(ToolError) as info:
        GithubTools(str(script), env={"PATH": os.environ["PATH"]}).repo_get({"owner": "o", "repo": "r"})
    assert info.value.code == "gh_failed" and "exited with 7" in info.value.message and "something odd" in info.value.message


def test_gh_output_that_is_not_json_is_bad_output(tmp_path):
    script = tmp_path / "gh"
    script.write_text("#!/bin/sh\necho '<html>'\n")
    script.chmod(0o755)
    with pytest.raises(ToolError) as info:
        GithubTools(str(script), env={"PATH": os.environ["PATH"]}).repo_get({"owner": "o", "repo": "r"})
    assert info.value.code == "bad_output"


def test_a_missing_gh_is_a_tool_error_and_not_available(tmp_path):
    missing = str(tmp_path / "nogh")
    with pytest.raises(ToolError) as info:
        GithubTools(missing, env={}).repo_get({"owner": "o", "repo": "r"})
    assert info.value.code == "gh_missing"
    assert gh_available(missing, env={}) is False


def test_a_slow_gh_times_out_and_is_killed(tmp_path):
    script = tmp_path / "gh"
    script.write_text("#!/bin/sh\nsleep 30\n")
    script.chmod(0o755)
    with pytest.raises(ToolError) as info:
        GithubTools(str(script), env={"PATH": os.environ["PATH"]}, timeout_s=0.3).repo_get({"owner": "o", "repo": "r"})
    assert info.value.code == "timeout"
    assert gh_available(str(script), env={"PATH": os.environ["PATH"]}, timeout_s=0.3) is False


def test_available_follows_gh_auth_status_and_is_checked_once(fake):
    assert GithubTools(fake.gh, env=fake.process_env()).available() is True
    fake.auth(gh="signed_out")
    tools = GithubTools(fake.gh, env=fake.process_env())
    assert tools.available() is False
    tools.available()
    assert len([c for c in fake.calls("gh") if c["op"] == "auth_status"]) == 2    # one for the first instance, one for this


def test_github_tools_are_absent_when_gh_is_signed_out(fake, monkeypatch, tmp_path):
    monkeypatch.setattr(github_tools, "gh_env", lambda *a, **k: fake.process_env())
    fake.auth(gh="signed_out")
    server = mcp_server.build_server("github", gh_exe=fake.gh)
    assert server.handle({"jsonrpc": "2.0", "id": 1, "method": "tools/list"})["result"]["tools"] == []
    fake.auth(gh="signed_in")
    server = mcp_server.build_server("github", gh_exe=fake.gh)
    names = [t["name"] for t in server.handle({"jsonrpc": "2.0", "id": 1, "method": "tools/list"})["result"]["tools"]]
    assert names == ["github_repo_get", "github_pr_list", "github_pr_get", "github_issue_get", "github_file_get"]


def test_sutra_plus_github_profile_serves_both_sets(fake, monkeypatch, tmp_path):
    monkeypatch.setattr(github_tools, "gh_env", lambda *a, **k: fake.process_env())
    (tmp_path / "x.db").write_bytes(b"")
    server = mcp_server.build_server("sutra+github", db_path=str(tmp_path / "x.db"), gh_exe=fake.gh)
    names = [t["name"] for t in server.handle({"jsonrpc": "2.0", "id": 1, "method": "tools/list"})["result"]["tools"]]
    assert names[0] == "sutra_chart_read" and names[-1] == "github_file_get" and len(names) == 10


def test_no_token_reaches_gh_argv_or_env(fake, monkeypatch):
    for name in ("GITHUB_TOKEN", "GH_TOKEN", "ANTHROPIC_API_KEY", "SUTRA_TOKEN", "CLAUDE_CODE_SSE_PORT"):
        monkeypatch.setenv(name, "secret-value")
    env = gh_env()
    assert not [k for k in env if k.endswith("TOKEN") or "KEY" in k or k.startswith(("SUTRA_", "CLAUDE_CODE"))]
    assert env["GH_PROMPT_DISABLED"] == "1" and "PATH" in env
    monkeypatch.setattr(github_tools, "gh_env", lambda *a, **k: {**gh_env(), **fake.env()})
    tools = GithubTools(fake.gh)
    tool(tools, "github_repo_get", owner="octo-org", repo="hello-world")
    for call in fake.calls("gh"):
        visible = fake.visible_env_keys(call)
        assert not [k for k in visible if "TOKEN" in k or "KEY" in k]
        assert "secret-value" not in json.dumps(call["argv"])


def test_gh_child_has_stdin_closed_and_an_explicit_cwd(fake):
    tools = GithubTools(fake.gh, env=fake.process_env(), cwd=str(fake.root))
    tool(tools, "github_repo_get", owner="octo-org", repo="hello-world")
    call = api_calls(fake)[0]
    assert os.path.realpath(call["cwd"]) == os.path.realpath(str(fake.root)) and call["stdin"] in (None, "")


def test_only_get_is_ever_sent(gh, fake):
    tool(gh, "github_repo_get", owner="octo-org", repo="hello-world")
    tool(gh, "github_pr_list", owner="octo-org", repo="hello-world")
    tool(gh, "github_file_get", owner="octo-org", repo="hello-world", path="README.md")
    for call in api_calls(fake):
        assert call["argv"][:3] == ["api", "-X", "GET"] and len(call["argv"]) == 4
    assert all(s.read_only for s in github_tools.tool_specs(gh))


def test_the_server_serves_github_tools_end_to_end(fake):
    import subprocess
    import sys
    from pathlib import Path
    lines = [{"jsonrpc": "2.0", "id": 1, "method": "tools/list"},
             {"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {
                 "name": "github_issue_get", "arguments": {"owner": "octo-org", "repo": "hello-world", "number": 3}}}]
    env = {"PATH": os.environ["PATH"], "HOME": os.environ.get("HOME", "/tmp"), "PYTHONPATH": str(Path(__file__).resolve().parents[2]),
           "GITHUB_TOKEN": "ghp_must_not_pass"}
    proc = subprocess.run([sys.executable, "-m", "sutra_app.connectors.tools.mcp_server", "--profile", "github", "--gh-exe", fake.gh],
                          input="".join(json.dumps(x) + "\n" for x in lines), capture_output=True, text=True, timeout=60, env=env, cwd="/tmp")
    answers = [json.loads(x) for x in proc.stdout.splitlines()]
    assert proc.returncode == 0 and len(answers[0]["result"]["tools"]) == 5
    result = answers[1]["result"]
    body = json.loads(result["content"][0]["text"])
    assert result["isError"] is False and body["untrusted"] is True and body["data"]["number"] == 3
