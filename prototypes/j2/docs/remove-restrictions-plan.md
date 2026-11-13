# remove-restrictions: plan and status

Branch `remove-restrictions`. Written 2026-11-13 so a new session can pick up. The original plan was in a session
that ended on a login error; steps 0–5 below are recovered from commits and the founder's answers. **Steps 6–9:
scope not recovered. Ask the founder before starting them; do not guess.**

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

## Steps 6–9

Scope not recovered. Ask the founder.
