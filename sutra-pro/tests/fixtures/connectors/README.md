# Connector fixtures

Real output of `claude` 2.1.308 and `codex-cli` 0.146.0 recorded on 2026-11-04, plus derived error cases and a few handwritten files.
`MANIFEST.json` lists every file, how it came about (`origin` captured, derived or handwritten), and what is and is not verified.

- `claude/`, `codex/`, `mcp/`, `cli_errors.json`: **captured**. Scrubbed: e-mail, organisation id and name, local user name and paths, the abandoned device sign-in code. Trimmed: the claude `system/init` event keeps only the keys a connector reads (`tools`, `mcp_servers`, `model`, `session_id`, `permissionMode`, `capabilities`, ...).
- `derived/`: **not live captures**. A captured stream with the listed fields edited. Wording marked UNVERIFIED in the manifest must be re-checked when a live sample exists.
- `handwritten/`: **nothing was captured**. Written by hand from the CLIs' documented or observed formats: version lines, the top-level `codex --help`, `claude mcp list` samples (the command rewrites Claude's state, so it was not run), and the `gh` data the fake `gh` serves (auth text, error bodies, a repository, pull requests, issues, file texts).
- `recorded_after` (manifest): the fixture whose session this one continues. Both CLIs report cumulative counters on a resumed session; the fakes subtract that fixture to get the per-turn amounts.
- The fake executables in `tests/fakes/` replay these files (`tests/fakes/fake_cli.py` lists every `FAKE_*` variable and scenario; `tests/connectors/conftest.py` gives tests a handle on them). No test in the default suite calls a real model.
- Refresh: `SUTRA_LIVE=1 .venv/bin/python scripts/capture_connector_fixtures.py` (a human runs it; it makes at most two small calls per CLI that reach a model). `--plan` prints the steps without running anything. It does not regenerate `derived/` or `handwritten/` files.
