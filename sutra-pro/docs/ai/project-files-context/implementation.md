# Implementation: Files and earlier context stay with a project (D451)
_Branch feat/project-files-context, base origin/main e59d3ea0 · nothing pushed, no PR, versions not bumped (0.9.0 is named only in the release note)_

## What was built (per plan step)
| Step | Result |
|---|---|
| T1 | failing tests first (red for the stated reasons: no module, no route, no column) |
| T2 | spike: `channel-spike.md` + 3 characterisation tests. Finding: a run's framing line reaches the five function agents, never a builder in a real run (`J2_SLIM`), and a long chat summarises it away. Decision: the project block goes through the host's `system_addendum` (`node_context.json["*"]`) |
| T3 | schema v10 (`project_files`, `tasks.input_files_json`), `ProjectFiles` |
| T4 | `project_context.py`: pure composition, budgets, whole or excerpts, receipt, signature |
| T5 | files on `/api/say`, `/api/tasks`, team chat messages; `run_inputs.py` (snapshot, copy to `inputs/`, context file); `hooks.py` `"*"` entry; retry keeps files; export ignores `inputs/` |
| T6 | chat path: stable block in the system text, excerpts in the message, `context.sig` and the Codex thread rule, 202 `context` receipt |
| T7 | routes in `api/project_context.py` (files, promote, attachments, instructions, memory, `/context` preview), body limit |
| T8 | `attach_bar.js` extracted from the composer; `TEAM_FILES` removed |
| T9 | `start_files.js`, port edits E30a-d (E25c amended), page regenerated with `port_j2_ui.py` |
| T10 | composer and Attention send team messages with files; the owner's line shows "Given to the team" |
| T11 | panel `project_context_view.js`, project menu entry |
| T12 | Create project: files after create, partial failure kept |
| T13/T14 | instructions and memory (`project_memory.py`), writers in `Projector._finish` and `ChatArchive.archive`, lazy seed |
| T15 | org chat files: planner digest, each task given the files |
| T16 | D451 (+ decisions.json), release note 0.9.0, ENVIRONMENT row, troubleshooting |
| T17 | mutation proof (below), sharded suite |

## Deviations from the architecture
1. Project block goes to `node_context.json["*"]` (system addendum), not the framing (T2 outcome, the architecture's own fallback). The framing carries a pointer line only.
2. New modules not in the plan: `run_inputs.py` (materialiser, snapshot, context file; kept out of the pure `project_context.py`) and `project_delivery.py` (shared read of rows for chat and preview).
3. Stale save is 409 code `busy` with `details.stale` (a new error code would change the pinned list in `test_records`).
4. Contract tests: `tests/contracts/test_contract_world.py` mounts the new router; `tests/engine/test_engine_spec.py` lists `inputs`; `chat_composer`/`front_door`/`project_pick`/`chat_ask` tests that encoded the old refusal or exact menu were replaced (4 composer tests) or amended.
5. E25c was amended (not only E30 added) because port edits may not anchor on each other's output.
6. A file sent with an answer to a waiting team is refused with a sentence (OQ-6: not silently dropped).

## Not done / not exercised
- The chip "3 files · memory on" under the start box and the "Using N files" line (`usingLine` exists and is tested; not placed in a page).
- No browser or desktop run: page behaviour is proven by node tests with stand-ins, source pins, and the regenerated page; `tests/e2e/test_browser_chat_composer.py` was edited to follow the new behaviour and not run (opt-in). The beta checklist and a real builder obeying the block (PRD 9) are the owner's.
- Files on `POST /api/projects` (deferred by decision).
