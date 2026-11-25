# Implementation: the centre panel shows any output, not only websites

Branch: `sut-27-output-agnostic-result`. Commands run from `sutra-pro/`.

## Steps

| step | status | commit |
|---|---|---|
| T1 pure core and fixtures | done | `SUT-27: D450 the pure core of result_view.js and a script-run fixture, not loaded by the page yet` |
| T1 follow-up | done | `SUT-27: D450 the real-run result is read from the receipt row's own result and run_output keys` |
| Q-4 docs | done | `SUT-27: D450 Copy share link is hidden with no main file or a real-run result (Q-4, docs)` |
| T2-T6 | not started | |

### T1

| file | what |
|---|---|
| `sutra_app/ui/static/js/result_view.js` (new) | IIFE, one global `ResultView` (node: `module.exports`), avatars.js shape. `isPageRun`, `done`, `realRun`, `named`, `mainResult`, `viewerFor`, `summaryOf`, `filesOfPart`, `table`, `jsonTable`, `label`, `WORDS`, `MAX_ROWS`; `adopt` is a stub returning false. Not in `MODULES`, so the page does not load it yet. |
| `tests/ui/js/result_view.test.js` (new) | 13 node tests over the pure core (AC-5, AC-10, AC-11, FR-7/8 parse, FR-17 wording, FR-20) |
| `tests/ui/fixtures/result_view/state-script.json` (new) | hand-built done script run: output `env_report` (form `agent`, file `env_report/*`), W-1 plan, W-2 with `real_run.result: "report.txt"`, one W-2 message "@Coordination I wrote env_report/report.py. It prints the environment." |
| `tests/ui/fixtures/result_view/artifacts-script.json` (new) | two `env_report` rows (`report.py`, `report.txt`), `workflows: ["W-2"]`, same `name` |
| `tests/ui/fixtures/result_view/real-runs-script.json` (new) | W-2 real_run receipt row in two shapes: `today` (stdout tail in `output`, no `run_output`) and `p45` (the same plus top-level `run_output`, `result`, `created`/`changed`/`deleted`/`files_truncated` and a `dry_run`) |
| `docs/ai/...` | analysis.md and the task folder added; spec.md, architecture.md, plan.md amended for the plan-review decisions (change-log lines in spec and architecture) |

## Deviations

| what | why |
|---|---|
| Main-result step 1 rebuilt as `realRun(s, runs)`; `mainResult` takes a third argument `runs` and can return `{kind: "real-run", workflow, result, link}` | owner decision at plan review (Q-1): `real_run.result` is a path in the user's folder, never matched against outputs; its text comes from P45's `run_output/<id>.json`, linked as the receipt row's `run_output` (owner update; `output`, today's 1,500-char stdout tail, is never read as a link). Strict link regex `^run_output/\w[\w.-]*\.json$`. The workflow's last receipt row decides (a later tail row hides an earlier link). `named(s)` now returns only the concrete entry file (string), not a list. |
| Owner update during T1: the link key is `run_output` on the receipt row, not `output` | `realRun` reads only `run_output`; a unit case pins that a link-shaped `output` is ignored; spec, architecture, request (plan-review section) and plan updated. Folded into the single T1 commit (unpushed, amended) |
| P45 confirmed (second commit): step 1 reads the receipt row's own `result` and `run_output`; each workflow's last row, the last in plan order, rows for workflows not in the plan ignored; `workflows[].real_run.result` no longer read | owner update. Confirmed keys: `run_output` (`run_output/<receipt-id>.json`), `result` (from the proposal, else the entry_file fallback, resolved by the engine), and the real run's own `created` / `changed` / `deleted` / `files_truncated` in the `dry_run.*` format; `output` stays the 1,500-char tail (pending Kaivan's final key list once built) |
| No `folderChanges(row)` reader | the coordinator preferred documenting; architecture.md Later names the keys. The "dry_run has created, top level none" case is covered by `realRun` returning only `{workflow, result, link}` and a unit case where `dry_run`/`expect` carry a `result` that is not read |
| `files_truncated: false` in the p45 fixture | `dry_run` has no such key today (j2.py:974-977, `_tree_diff` gives only created/deleted/changed); a boolean is assumed |
| Third fixture `real-runs-script.json` (plan named two) | the coordinator asked for fixtures holding both receipt-row shapes (today's and P45's) |
| `label` returns "result" before done on a non-page run, "no files" when done with zero outputs | the spec names only "the main file's name, or files"; these two cases had no string |
| `WORDS.showing(n, total)` is a function | the row counts are part of the string |
| request.md: "Approved by <name>" → "Approved by the owner" | no owner names in committed files |
| plan.md T4 text: share URL is now the main file's `/view` link | Q-3 answered at plan review; plan said "unchanged" |

## Tests

| command | result |
|---|---|
| `node --test tests/ui/js/result_view.test.js` | 13 tests, 13 pass, 0 fail |
| `scripts/py -m pytest tests/test_ownership.py tests/ui/test_node_suite.py -q` | 10 passed (the node suite runs every `tests/ui/js/*.test.js`, the new file included) |

Not run (owner rule): `scripts/gate.sh`, `scripts/live_smoke.py`, browser tests, beta install.

## Known gaps

- `realRun` never hits today: the `/api/artifacts/groups` `real_runs` projection (j2_artifacts.py:774-793) carries none of the P45 keys, and P45 lands after SUT-28. Hook only; how the text is fetched from `run_output/<id>.json` is decided when P45 lands.
- Q-4 answered by the owner (docs commit): Copy share link is hidden with no main file or a real-run result; built in T4.
