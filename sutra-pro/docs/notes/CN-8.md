# CN-8 as built: tool connectors

## Built (`sutra_app/connectors/tools/`, tests in `tests/connectors/`, connectors.md 3.9, CD14-CD16)
- `profiles.py`: `ToolSpec`, `ToolError`, `validate_args` (flat JSON-Schema checker used for every tool call); `mcp_servers(cfg, tools, readmodel=)` is THE MCP entry
  (`{"sutra": {command, args, env{PYTHONPATH, SUTRA_DB_RO}}}`), `claude_mcp_config`/`claude_mcp_file` (0600 file in a private dir, removed in `finally`),
  `codex_mcp_flags` (`-c mcp_servers.sutra.*`), `profile_name`, `tool_catalog(profile)` (for `GET /api/connectors/tools`), `tools_status(cfg)` (`{"sutra","github"}`).
- `mcp_server.py`: `python -m ...mcp_server --profile sutra[,github|+github] [--db] [--readmodel pkg.mod:factory] [--gh-exe]`; `McpServer.handle` (no I/O), `serve`, `build_server`.
- `sutra_tools.py`: `ReadModel` Protocol, `SqliteReadModel` (`mode=ro` URI plus `query_only`), five tools; `load_readmodel`, `tool_specs(rm)` lists only what `rm` supports.
- `github_tools.py`: `GithubTools` (five tools, each `gh api -X GET <template>`), `gh_available`, `gh_env`, `wrap_untrusted`.
- `mediated.py`: `MediatedConnectors.snapshot()/refresh()`, `parse_claude_mcp_list`, `RefreshTooSoon`, closed models `MediatedItem`/`MediatedReport`.
- 105 tests, about 5 s. Mutation self-check, one pass: 23 breakages in a /tmp copy; 3 survived (a `mode=ro` replaced while `query_only` still held: test added that
  turns `query_only` off; the 20 KB cut boundary: test added; a redundant `chmod 0700` after `mkdtemp`: line removed). Re-run of those: all killed.

## Deviations from the specification
1. `claude.py`/`codex.py` (CN-3/CN-4) already carry a minimal `mcp_servers()`; I cannot edit them. `profiles.mcp_servers` returns the identical entry for a default config (a test
   compares all three), so CN-9's factory can wire either; only `--gh-exe` and `--readmodel` (appended when set) go beyond them.
2. The server accepts `--db` (default `$SUTRA_DB_RO`) and `--gh-exe` in addition to `--profile`/`--readmodel`: the fake `gh` and tests need a way to name the executable.
3. A tool failure is a `tools/call` result with `isError: true` and `{"error": {"code", "message"}}`; only an unknown tool or missing `params.name` is -32602. A bug in a tool is also an `isError` result (code `internal`, detail on stderr only).
4. `tools/list` answers also carry `annotations.readOnlyHint` (MCP standard) and the server is lazy: the `gh auth status` probe runs at the first `tools/list`/`tools/call`, once.
5. Mediated: item names are `Gmail`, `Google Drive`, `Slack`; `refresh()` raises `RefreshTooSoon(retry_after_s)` (CN-9 maps it to 429). `snapshot()` is the "cache only" read.

## Decisions
- The GitHub tools return trimmed fields, not the raw API body (no urls/ids noise); every string is inside `{"untrusted": true, "source": "github", "note", "truncated", "data"}`. The data's JSON is cut at 20,000 bytes;
  a file's `content` is shortened until the whole data fits, so the answer stays valid JSON; a cut list becomes a JSON-text string with `truncated: true`.
- `owner`/`repo` of `.` or `..` are refused although the pattern allows dots; paths refuse `..`, `.`, empty segments, backslash, control characters, `?`, `#`; the path is percent-encoded.
- gh errors are mapped to `not_found | rate_limited | unauthorized | github_error | gh_failed | gh_missing | timeout | bad_output`; the stderr text is never passed on (except a 300-character summary for `gh_failed`).
- `gh` runs under the project allowlist (`child_env`) plus `GH_PROMPT_DISABLED`, `GH_NO_UPDATE_NOTIFIER`, `NO_COLOR`; 30 s timeout, own process group, SIGKILL of the group on timeout.
- The default ReadModel maps: chart = `org_nodes`+`org_edges` of the active head chart; graph = `graph_nodes`/`graph_edges` (`workflow_id` = task id, department id or node id; at most 300 nodes); atom = `atoms` row with `body` parsed;
  models = `REGISTRY.families()` / `json_schema(name)` (library modules are imported one by one when `sutra_app.library.all` does not exist yet).
- A failed `claude mcp list` also starts the 60 s interval (it probed anyway). Rows count as proof of fetch if the line merely starts with `claude.ai `.

## Known limits
- Importing `sutra_app.connectors` loads pydantic, so server start-up is about 0.3 s; the transport itself is standard library only.
- The `claude mcp list` format is the hand-written sample (UNVERIFIED against 2.1.308); a real model calling a tool is UNVERIFIED (test_live, CN-9).
- The server is single-threaded: a slow `gh` call (up to 30 s) delays a `ping` behind it.

## Follow-ups for other packages
- CN-9: `/api/connectors/tools` = `tool_catalog("sutra+github")`, status `tools` = `tools_status(cfg)`; mediated routes call `MediatedConnectors.snapshot()/refresh()` (429 on `RefreshTooSoon`); pass `readmodel=` when a section ships one.
- Data-owning sections may ship a `ReadModel` factory (`factory(db_path)`); until then the default SQLite one serves the orchestrator schema.
