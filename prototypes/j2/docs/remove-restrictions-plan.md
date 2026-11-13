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
| 5 | `fb430a31` | UI: one artifact view (no Documents tab), every output-folder file with its maker, Template line, conditions with the sandboxed test, warnings apart from failures, runs by type label | Live 3/3 Done, $2.12 (total $12.95 of $60); `--fast` and `--fast --browser` pass |
| 5 follow-up | `16ae61f7` | Group by what the run made, Preview its main output, final-attempt failures, C2 evidence says code reran the test, code names not flagged as facts, Template line first | `--fast`, `--fast --browser` |

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

## Step 6a: a folder output gets a type that names what was made (plan, not started)

**Why it goes before step 6.** Step 6 saves and reuses runs by their type. Done first, a saved script run is
reused as a "Copy script", not as any folder output under the generic "Agent".

**Finding.** Adaptation can already make a new type in any form: `types_text` (`j2_realization.py`) says "when no
type fits, make a new one", `j2_types.create()` accepts a form without sections, and `J2Run` creates it
(`j2.py`, the `new_types` loop after `plan_goal`). The file-copy run (j2-20261113-164130) picked the built-in type
`agent` instead, because that type is in the list and fits any folder. The rubric, conditions, test runner,
builder text, charter format and mock all sit on the agent *form* (`artifacts/types.json` `forms.agent`), not on
the type, so a new type in that form gets all of them.

| # | Change | File (owner) | Impact | Effort |
|---|---|---|---|---|
| 6a.1 | Delete the built-in `agent` type entry; keep `forms.agent`. With no folder type in the list, the planner makes one in the agent form (e.g. `copy_script`, label "Script") through the existing `create()` path | `artifacts/types.json` (Disha) | High | S |
| 6a.2 | A new folder type is stored in `artifacts/types.local.json` (gitignored; no template, so nothing goes to `library/`), reused by later runs, promoted with `python3 j2_types.py --promote <name>`. No code change | `j2_types.py` (Disha), read only | n/a | 0 |
| 6a.3 | The planner's type text: say that a folder form is a form, not a type, so a folder output always names its own type. Wording only, no type names | `j2_realization.py` `types_text` (Disha) | Med | S |
| 6a.4 | Mock path: the offline deliverables mock picks a named type or the page type. For a folder brief it must propose a new type in the agent form, driven by the form's `mock` data, with no keyword matching. Release check brief 3 (mock) must still end `Done:` | `j2.py` `J2Run._deliverables` offline mock, `j2_realization.deliverable_mocks` (Disha) | Med | M |
| 6a.5 | Saved runs whose type was `agent`: `j2_types.recorded()` keeps a deleted type's label only for planner-made types. Old agent runs would show the raw name. Fall back to the run's `summary.json` or `artifacts.json` label, else the form's label | `j2_types.py` `recorded` (Disha), `j2_server.run_row` (Disha) | Low | S |
| 6a.6 | Tests that call `set_output("agent")` (3 in `j2_flow_test.py`), plus `guesses_warn`, `general_path`, `missing_capabilities` and `one_artifact_view`, make a folder type with `j2_types.create(..., form="agent")` in a temp types file | `j2_flow_test.py` (Disha) | Med | M |

Not touched: `templates/agent/` (under `templates/`, which step 6's rule reserves), `conditions/agent.json` beyond C2's
title, the Library tab, `j2_template_lib.py`. Risk: a live planner may still choose a page or document type for a
script brief; the release check's script brief shows it (its outcome names the type). After: `--fast`, mock release
check; a live check only with step 7.

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
