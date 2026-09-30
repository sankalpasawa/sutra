# The line: how anything starts and runs

| Field | Value |
|---|---|
| **status** | v1, 2026-09-29, RECORD of the code (Sutra Desktop v2.306.19-desktop) |
| Code | `engine_runtime.py` (`next_due`, `ready`, `_on_version`, `_on_post`, `_on_timer`, `blocked`, `coord_pick`, `coord_busy`, `run_engine`, `run_step`, `_run_row`, `WAITS`), `website_dept.py` (`due`, `motor_tick`, `working_now`, `_chain_of`, `CHAIN_LIMIT`, `TICK_S`, `MODEL_TIMEOUT_S`) |

## The motor

`motor_tick` runs every `TICK_S` (3 s) in the app's process: for each department it asks `due(ref)`, which on the engine runtime is `next_due(ref)`: Coordination's `coord.pick` (`_run_rule`), and starts at most one run per department per tick (`run_slot` → `run_engine`). A panel read asks the same with `peek=True`: it writes no row, no ask, and never calls the model.

## Triggers (`ready`)

An engine's definition names its start: `on` (triggers) and `unless` (blockers). `ready(ctx, name)` walks the triggers:

| Kind | Code | Live when |
|---|---|---|
| version | `_on_version` | a version of what the engine reads that it has not run on yet (`checked: true` needs the version's check to have passed); the slot is `<engine>@<artifact>.v<n>` |
| post | `_on_post` | a post on the board addressed to the engine that no handler ran yet, oldest first; a post no step of the engine reads is skipped with a row |
| timer | `_on_timer` | one start per period of `every_s` |

An engine the Library no longer defines has no trigger (`ready` returns None; engines-and-library.md). A slot already held back (`_held_back`: waiting on the model, asked, interrupted) is skipped or reported as the reason.

## Blockers (`blocked`)

For each id in `unless`, in order: the gate's code runs (`CODE[g["code"]]`); on a rung other than code, an `admit` by code is put to the function to judge (`_ask_rule(... "coord.verdict")`, a verdict row) and the engine waits until the verdict is in; every answer is a gate row (`_gate_row`). The work engines' blockers, in order: `identity.wait_engine`, `identity.gate`, `priority.envelope`, `coord.chain` (functions.md).

## Who goes first (`coord_pick`)

`coord.busy` first: one run at a time in a department. Then Coordination's table (`coordination.json`, `{"order": ["posts", "line", "functions"], "line": [...], "functions": [...]}`): the oldest post to a function; else the line in order, where a held engine holds the ones after it; else a function woken by a version. Equal readiness goes to `coord.tie` (a model call, not on a peek).

## One run (`run_engine`)

- A run row (`_run_row`): engine, slot, status running, `what` (the handler's name for a post, else "reading <artifact>"), the chain (`_chain_of`: the Brief version the work descends from), retries.
- Steps in order (`run_step` each): before a step the row's `what` becomes the step's name; a step with `each` runs its items side by side (`side_by_side`) and the row says "page n of m"; a step with `may_end` whose answer is `run: false` ends the run ok with "not needed: …" and files nothing.
- A step's outcome: ok, or `waiting` (the model was away: retried after `WAITS` = 30, 120, 600 s, then the owner is asked), `asked` (the owner's answer is needed), `failed` (a row, never a crash of the motor).
- A work engine's last step `files`: `W.add_version` writes the artifact's new version with `made_from`, the run id and the check; ok when the check passed. The person is told when the kind's last artifact went out ("Live site v1 is live.") and when an engine the owner added filed ("X v1 is filed.") (`_tell`, word live / filed, `link`, `chain`). A build that breaks a stamped rule is sent back to the line with the finding, twice at most (`_send_back`).
- A chain of runs from one owner's ask stops at `CHAIN_LIMIT` (12) (`coord.chain`).

## Every step on a rung (`run_step`)

Each step runs on the rung its record has earned (`rung_of`: ladder numbers per step, `ladder.json`): P person, C0 improvised call (the model, `_soft`), C1 checklist, C2 code (`RESOLVE`). A rung whose answer does not fit (`_fits`) falls to the one below (`BELOW`). Every step writes a row to `steps.jsonl` (rung asked and got, by whom, the rules applied, what it read, the check, cost, ms). A stamped answer stands as the person's (`_stamped`).

## The working line

`working_now(ref)` = the engines whose run rows are still running (not one a dead process left open past twice the model's timeout, `MODEL_TIMEOUT_S` 420 s); the chat's working line and the tree's mark read it (`/depts` carries `working`).

## Stop and Start

`/{ref}/stop` and `/{ref}/resume` set `stopped` on the record; `next_due` returns "stopped"; a running step finishes its call; both are turns of the chat ("Stopped by you: every engine stops where it is." / "Started by you: every engine looks to its own triggers.", `tell_switch`).

provenance: {author: claude, session: 17842ce0, date: 2026-09-29, inputs: [engine_runtime.py: next_due, ready, _on_*, blocked, coord_pick, coord_busy, run_engine, run_step, _run_row, _send_back, tell_switch; website_dept.py: due, motor_tick, working_now, _chain_of, add_version], review: none by a second model, confidence: high}
