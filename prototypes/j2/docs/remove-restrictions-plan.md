# remove-restrictions: plan and status

Branch `remove-restrictions`. Written 2026-11-13 so a new session can pick up. The original plan was in a session
that ended on a login error; steps 0–4 are recovered from commits, steps 5–9 and the standing rules are the founder's.

## Test cadence (founder, 2026-11-13)

| When | Run |
|---|---|
| After each step | `python3 j2_flow_test.py --fast --skip map_focus,graph_map,left_bar_toggle,artifacts_groups,warm_ui,map_motion` |
| After step 5 (UI) and before the final commit | `--fast --browser` with the same skips, **not piped through `tail`** (20+ min; progress must show) |
| After step 5 | Live release check: `python3 tools/release_check.py` (cap $60 across all checks; ledger `runs/release/ledger.json`) |

The six skips read local saved runs and fail on the base commit already.

Release check pass rule (`43bc2095`): a brief passes only on an outcome starting `Done:` (workable).
"Done with open items" fails.

## Done

| Step | Commit | What | Release check |
|---|---|---|---|
| 0 | `374bf9ef` | `tools/release_check.py`: the three release briefs live, each in its own process, ledger against the cap | Baseline only |
| 1 | `2092553c` | Builders get Claude's built-in tools and the network; reads fenced to their folder; limits default in code (`j2.AGENT_DEFAULTS`, listed commented in `.env.example`) | Mock 3/3; live smoke $0.09 |
| 2 | `b9d336a2` | One general path: every builder writes files with its tools; folder stage deleted; check bundles warn | Live: policy Done, script Done, coffee shop Done with open items (no facts in the old brief). $10.83 of $60 |
| 3 | `d2bb7f6d` | A guess warns, never blocks; "Assumptions to confirm" only when the template asks | Mock 3/3 |
| 4 | `4ca95c96` | A missing capability becomes a planned script with its own test (`templates/atom_rules.md`); realization planner may search the web with tools on | `--fast` only |
| — | `43bc2095` | Release check: coffee shop brief gives its facts (Bean There, 12 Park Road, hours, menu with prices); only `Done:` passes | Mock 3/3 |
| 5 | (this commit) | UI: one artifact view (no Documents tab), every output-folder file with its maker, Template line, conditions with the sandboxed test, warnings apart from failures, runs by type label | Live 3/3 Done, $2.12 (total $12.95 of $60); `--fast` and `--fast --browser` pass |

## Step 5: UI

| # | Change | Impact | Effort |
|---|---|---|---|
| 5a | One artifact view everywhere: Summary, Agent-readable, Human-readable, and a "Template" line naming the template that made it. Remove the separate document viewer and its extra buttons. | High | L |
| 5b | The artifact shows every file a tools builder wrote in the run's output folder (`out/`), not only the page or main document. Clicking a file in the list shows it: code as text, images as images. | High | M |
| 5c | The test result (the sandboxed rerun) shows in the artifact's Summary. | Med | S |
| 5d | Advisory-check warnings and `guess_warning` rows show as warnings, apart from failed checks. | Med | S |
| 5e | Scripts built for a missing capability (step 4), with their tests, show as reusable artifacts of the run. | Med | S |
| 5f | The run list labels a run by its type's label (e.g. "Script"), not "website" or "document". | Med | S |
| 5g | Start page: remove any forced choice of type or form; the prompt alone decides. | Med | S |

Out of scope: the Library tab and RTSCOPES (Kaivan owns them). Do not change them.

After step 5: `--fast --browser` (no `tail`) and the live release check.

## Step 6: library

Folder and workspace runs save and reuse through Kaivan's `run_template_from_run` and `save_run_template`; no second
store. Do not edit Kaivan's files: `j2_template_lib.py`, `library/`, `templates/`, `j2_agent_views.py`,
`j2_artifact_models.py`, the Library tab. If `decision_group` or anything there must change, write exactly what is
needed as a note for the founder to send him. After: `--fast`, mock release check.

## Step 7: run for real

When a brief asks to act on real files, the workflow states the command and the folder. The Requester approves in
chat. Code, not an agent, checks that exact approval. Then the command runs with write access to that one folder
only, with a receipt in `receipts.jsonl`. After: `--fast`, live release check.

## Step 8: delete dead code

Delete page/document code the general path no longer uses, plus tests that only checked it, each listed in the
commit message. After: `--fast`, mock release check.

## Step 9: SETUP.md for teammates

claude-cli and Node versions, installs, every `.env` line (including `J2_SANDBOX_CMD` and the limit defaults),
tested from a fresh clone. After: `--fast`, `--fast --browser`, live release check.

## Standing rules

| Rule | Detail |
|---|---|
| No new names in code | No new type, form, tool or keyword names in code |
| `--fast` | After every step |
| `--fast --browser` | Only after steps 5 and 9 (no `tail`) |
| Live release check | Only after steps 5, 7 and 9 |
| Mock release check | After steps 6 and 8 |
| Spend | Hard $60 cap across all live checks (`runs/release/ledger.json`) |
