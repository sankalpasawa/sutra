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
| Live release check | After batches 1, 2, 3 and 4: `python3 tools/release_check.py --cap 100` (3 added by the founder) |
| Spend cap | $100 across all live checks in `runs/release/ledger.json` (raised from $60 by the founder, 2026-11-14, after batch 1b; $41.05 spent then) |
| Push | Not until the founder says |

## Batches

| # | Scope | Status |
|---|---|---|
| 1 | Identity: the Requester persona becomes a plain-words style rule (audience only from the brief and the Requester's answers); Identity's other forced decisions. Rows: inventory "Group C: status", batch 1 | done; live check below |
| 1b | The stage answer (`_stage_decision`) and `parse_decision`: Identity reads the Requester's answer instead of code's word matching. Rows: inventory "Group C: status", batch 1b | done (no live check: not in the cadence) |
| 2 | Coordination: no rules written into its task as if it chose them; it may name several ready workflows (the engine runs one at a time, and says so). Founder rule: no workflow, type or file names in its task or code; readiness only from dependencies and what each writes. Rows: inventory "Group C: status", batch 2 | done; live check below |
| 3c | Founder's fix: at registration a dependency that matches no workflow of the run (and no finished earlier stage) is refused back to Adaptation, by exact name only. Committed on its own | done |
| 3 | Priority: remove word lists (`BUDGET_TALK`, `item_kind`). 3a: Identity tags each done-when item with a kind from the type's data; 3b: Adaptation's POLICY_QUESTION states what it is about. Live check after batch 3 too (founder), since 3c may refuse plans that used to pass | done; live check below |
| 4 | Audit: remove word matching for findings and duplicates; also `_supersede`, the TBC markers (into the conditions data), the `user_groups` split and the board's `duplicate_of` (asker's `same_as`). Rows: inventory "Group C: status", batch 4 | done; live check below |
| later | Left by the founder (2026-11-14): `facts_to_headings` and `_fix_atoms` (code rewrites Adaptation's atoms by their shape), `j2_change.carry_checks.stale` (a substring of 8+ characters decides a check came from a removed charter string), `j2_schema.CONTENT_EDGES` (regexes on document prompt notes decide which edges carry a change) | planned |
| 5 | Planner thresholds (`THRESHOLD`, `MAX_ROUNDS`, lesson and playbook caps, the judge's scoring numbers): no change; a written proposal for Rubak: `docs/planner-thresholds-proposal.md` | done |
| later | Hidden rewrites: `to_requester` (cuts to 3 statements and 1 question, drops numbered lines), `PLAIN_WORDS`, `requester_words` (drops sentences naming internal ids). Code changes Identity's text without telling it. Also: a J2.g fact question merged into "Please send these" keeps its agent-facing wording (live run j2-20261114-193037: "Does the Requester want the script run on their own real folders...") | planned |

## Batch 1 live check (2026-11-14)

| Run | Result |
|---|---|
| All 4 briefs ($2.81) | 3 pass. File-copy brief fails: without the intake rule "Done-when may not refer to the Requester, ... approval ...", Identity added a real-folder run item the brief never asked for, and the run paused on it (j2-20261114-193037) |
| Fix (founder: option B) | Two lines in `agents/j2/identity.md`, "Real files and real runs": a real-file item only when the brief or answers ask for a run on them; done-when items describe what is delivered, not process steps. The code rule stays removed |
| File-copy brief alone ($0.36) | Pass: `Done:`, 2 done-when items, no real-run item (j2-20261114-195549). Ledger total $41.05 of $60 |

## Batch 2 live check (2026-11-14)

| Run | Result |
|---|---|
| All 4 briefs ($2.59, `--cap 100`) | 4 pass with `Done:`. Coordination named 2 ready once (coffee shop, j2-20261114-210601) and the engine's one-at-a-time line was posted; no workflow refused as ready; no id appended to its order. Ledger total $43.64 of $100 |

## Batch 3 live check (2026-11-14)

| Run | Result |
|---|---|
| All 4 briefs ($3.06, `--cap 100`) | 4 pass with `Done:`. 3c refused no dependency. Identity tagged every item: coffee shop 6 of 6 (page_section, styling), hiring policy 8 of 8 (doc_section); the two folder briefs have one kind, so no tags are asked. No POLICY_QUESTION was asked. Ledger total $46.70 of $100 |

## Batch 4 live check (2026-11-14)

| Run | Result |
|---|---|
| All 4 briefs ($2.39, `--cap 100`) | 4 pass with `Done:`. Every Audit finding named its item (no finding logged as naming none); no workflow was superseded; no board in these runs (`J2_BOARD` off). Ledger total $49.09 of $100 |
