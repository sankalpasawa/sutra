# remove-group-c: plan and status

Branch `remove-group-c`, from `remove-restrictions` (2026-11-14). Removes group C rows of
`docs/hardcoding-inventory.md`: a choice an agent should make, made by code. One commit per batch.

## Rules (founder, 2026-11-14)

| Rule | Detail |
|---|---|
| What stays in code | Guardrails: safety, budget (code offers only money it can apply), valid replies (fallbacks for a missing or broken reply) |
| What moves | Decisions go to the agent, or to data the agent sees |
| Word lists | No new ones |
| Per batch | List each change with file:line; update the inventory rows; `--fast` with the 8 skips |
| 8 skips | `--skip map_focus,graph_map,left_bar_toggle,artifacts_groups,warm_ui,map_motion,sutra_library,map_tab` |
| Live release check | After batches 1, 2 and 4 only (`python3 tools/release_check.py`) |
| Push | Not until the founder says |

## Batches

| # | Scope | Status |
|---|---|---|
| 1 | Identity: the Requester persona becomes a plain-words style rule (audience only from the brief and the Requester's answers); Identity's other forced decisions. Rows: inventory "Group C: status", batch 1 | done; live check below |
| 1b | The stage answer (`_stage_decision`) and `parse_decision`: Identity reads the Requester's answer instead of code's word matching | planned |
| 2 | Coordination: no rules written into its task as if it chose them; it may name several ready workflows (the engine may still run one at a time, and says so) | planned |
| 3 | Priority: remove word lists (`BUDGET_TALK`, `item_kind`) | planned |
| 4 | Audit: remove word matching for findings and duplicates | planned |
| 5 | Planner thresholds (`THRESHOLD`, `MAX_ROUNDS`, lesson and playbook caps): no change; a written proposal for Rubak | planned |
| later | Hidden rewrites: `to_requester` (cuts to 3 statements and 1 question, drops numbered lines), `PLAIN_WORDS`, `requester_words` (drops sentences naming internal ids). Code changes Identity's text without telling it. Also: a J2.g fact question merged into "Please send these" keeps its agent-facing wording (live run j2-20261114-193037: "Does the Requester want the script run on their own real folders...") | planned |

## Batch 1 live check (2026-11-14)

| Run | Result |
|---|---|
| All 4 briefs ($2.81) | 3 pass. File-copy brief fails: without the intake rule "Done-when may not refer to the Requester, ... approval ...", Identity added a real-folder run item the brief never asked for, and the run paused on it (j2-20261114-193037) |
| Fix (founder: option B) | Two lines in `agents/j2/identity.md`, "Real files and real runs": a real-file item only when the brief or answers ask for a run on them; done-when items describe what is delivered, not process steps. The code rule stays removed |
| File-copy brief alone ($0.36) | Pass: `Done:`, 2 done-when items, no real-run item (j2-20261114-195549). Ledger total $41.05 of $60 |
