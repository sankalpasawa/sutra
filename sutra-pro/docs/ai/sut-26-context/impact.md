# SUT-26 impact: a new run picks up an earlier, unrelated run's context; a restart loses or mixes up the brief
Task slug: `sut-26-context`. Analysed 2026-11-26 on the working tree of `remove-real-run-gates` (HEAD 12927a31 plus uncommitted edits). Read only.

Baseline: local `main` is stale (86a89fb4); `origin/main` is 6c79a1db, the merge base of this branch. Against `origin/main`, of every file cited below only `sutra_app/engine/j2.py` differs, and that diff touches no line of the continuation path (no hit for rehydrate, user_says, seed, upstream or "Earlier the team" in `git diff origin/main -- .../j2.py`). J2 line numbers on `origin/main` are given beside the working-tree ones.

## 1. How a new run decides it continues an earlier one (answer: code, except one path)

There are two ways a team gets a new task. Only the org-chat path lets an agent decide.

| # | Entry | Who decides "continue" | Evidence |
|---|---|---|---|
| A | Owner writes in the **team chat** with no live task | **Code.** Always the team's newest run that still has a folder; only the owner's "+ New run" reset marker stops it | `orchestrator/tasks.py:906-959` (`deliver_to_department`, falls through to `_follow_up` at :954); `_follow_up` :1016-1052: newest run with a folder :1022-1027, reset marker :1028-1032 |
| B | Owner writes in the **org chat**; the chat agent assigns work | **Agent** (the chat agent's `follows` field). It sees only `last: <title (status) task id>` per team, and its prompt says when `follows` is allowed (an id listed for that team), not when to use it | `orchestrator/agent/templates/decide.md:5`, `assign.md:7`; digest `orchestrator/chart_rules.py:184-203`; `follows` taken at `agent/runner.py:707-729` → `TaskService.create` → `_insert` :563-570 sets `seed_run` and parent |
| C | `POST /api/tasks` with `follows`; retry | Caller passes it; a retry never seeds | `orchestrator/api/tasks.py:85`; `tasks.py:1158-1190` (`seed_run=None` :1188) |

What path A copies in (all code, no agent):

| Carried | Set where | Read/posted where |
|---|---|---|
| `seed_from` = newest run with a folder (any status, any subject) | `tasks.py:1022-1027, 1043`; stored as `_seed_from` in `settings_json` (`tasks.py:78, 173-176`) | `task.json` via `_run_spec` `tasks.py:775` |
| framing `"Earlier the team asked the owner: <q>"` = the **newest unanswered question of any ended task of the team**, not necessarily the seed run's | `tasks.py:1033-1040`; only that one question is marked answered (:1050-1051), older open ones stay and come back on later follow-ups | posted as `"Context from the team lead: ..."` by `engine/host/loop.py:664-665` |
| previous run's output type (`followup` rule) | `loop.py:335-354` (`_seed_output`: reads the seed's chat header or summary, no status check) → `capabilities/select.py:87-88` | `loop.py:356-378`, `output.json` |
| rehydrate (state copied, next message is a change request), else fresh + `upstream/<old run>/` copy | `loop.py:537-553` → `engine/rehydrate.py:295-334` (`check_source`: refuses stopped/crashed :303-305, non-continuable types :309-317) | lines `continuing_line`/`fresh_line` `rehydrate.py:76-96`; copy `loop.py:575-595`, files `loop.py:68-71` |
| earlier `project.md` report into the system prompt of Identity, Audit and every builder (project output only) | `capabilities/project.py:129-167` (`earlier_report`: own folder, else `upstream/`) | `project.py:169-, 300-304` (`addendum`) |
| team memory (D451): owner requests and outcomes of past runs, every agent call | `orchestrator/run_inputs.py:109-129` (`given_for`), `tasks.py:716` | `node_context.json`, `engine/hooks.py:167-225`, `loop.py:471` |

Path B (`create`) gets seed and parent only; it neither adds nor closes an orphan question (`tasks.py:514-523`), so open questions pile up for path A.

## 2. Why the bakery brief was treated as a continuation (beta data, `~/.sutra-pro-beta`, read only)

Run `software-engineering/runs/j2-20261126-075844-f516`, task `tsk_5ba6da7847f9`, `request_id` empty → path A.

| Step | Evidence | Cause |
|---|---|---|
| 1. Seed = `j2-20261124-054123-c196` (a stopped project-work run on another subject) | `task.json` `seed_from`, `parent_run_id`; db `tasks.settings_json` `_seed_from` | code picks the newest run with a folder, `tasks.py:1022-1027`; no relatedness check, no agent |
| 2. Framing = question 1047 from run `j2-20261118-110800-0c75` (a file-sorting script, 8 days and 5 runs earlier) | db `chat_messages` 1047 open until answered by 3259 (the bakery line); 1081 from the same run was consumed the same way by c196 (answered_by 2019) | `tasks.py:1034-1040` takes the newest open question of ANY ended task; path-B tasks in between never closed it |
| 3. Output forced to `project` (`rule: followup`) | `output.json`, `trace.jsonl` seq 1 | `_seed_output` reads c196's type although c196 was stopped (`loop.py:335-354`) → `select.py:87-88`. Overlap with the other dev's followup ticket |
| 4. Rehydrate refused ("stopped before it finished") → fresh, c196 files copied to `upstream/` | `trace.jsonl` seq 2; `upstream/j2-20261124-054123-c196/` (goal, summary, workflows, project.md, report.md, site/) | `rehydrate.py:303-305`, `loop.py:546-552` |
| 5. Chat lines 1-3: fresh line, "Treating this as project work ... no working folder", "Context from the team lead: Earlier the team asked the owner: ..." | `chat.jsonl` | `loop.py:658-670` |
| 6. Identity call 1: the three lines in its prompt, and c196's `project.md` as `<earlier-report>` in its system text | `calls.jsonl` row 1 (`fn: identity`): prompt offsets 426 / 850; system `## Project work` 11206, `<earlier-report` 12046 | `project.py:129-167, 300-304`; memory block from step 1 table too |
| 7. Identity asked the owner for a working folder for a bakery page | `chat.jsonl` line 5, question 3264 | consequence of step 3 |

Blue Wave case (found): `web-design/runs/j2-20261125-130356-6c20`, task `tsk_3733b6e6279c`, owner line "Option 2" in the team chat (path A).

| Step | Evidence |
|---|---|
| Seed = Blue Wave run `j2-20261123-105434-7d93` (done, website) → **rehydrated** | `chat.jsonl` line 54 "Continuing from run ..."; no `seed.refused` in `trace.jsonl`; `output.json` rule `followup` website |
| Framing = question 1695 from the Sunny Side Bakery run `j2-20261123-104305-6e2e` (task done, question never answered) | `chat.jsonl` line 55; db `chat_messages` 1695 answered_by 3171 (the "Option 2" line) |
| Result: a bakery answer ("Option 2") applied as a change request to the swim school site, with the bakery question as "team lead" context | J2 marks the first line `change` because `done` is true after rehydrate: `j2.py:5077-5098` (origin/main :5263) |

Root cause in one line: path A decides continuation in code with no check that the new words relate to the seed run, and it picks the framing question independently of the seed (different runs in the Blue Wave case).

## 3. The brief on restart

| Event | What happens | Evidence |
|---|---|---|
| App closes with a live or waiting team | every live task is stopped "the app was closed" | `tasks.py:1197-1217` (`shutdown`) |
| App died (no clean close) | next start marks the task crashed "the app was closed while it ran"; no engine run is resumed | `orchestrator/runs.py:578-626` (`reconcile`) |
| Owner then answers the question in the team chat | there is no live task, so the answer becomes a **new follow-up task** (path A) whose `user_text` is only the answer ("Option 1"), framing = the open question | `tasks.py:946-954, 1016-1052` |
| Seed is stopped/crashed | rehydrate refused → fresh run; the original brief is NOT given to the agents, only "files are in upstream/<id>/ for reference"; `chat.jsonl` (where the brief was) is not copied (`SEED_FILES` `loop.py:69`) | `rehydrate.py:303-305`; `loop.py:575-595` |
| New run's recorded brief | `summary.json.brief` = `self.request` = the answer text; the chain's brief is overwritten | `j2.py:13375` (origin/main :13735); beta `web-design/.../j2-20261118-073623-7f80/summary.json` brief "Option 1" while its upstream `summary.json` holds the real 138-character brief |
| Seed is done (rehydrate) | `run.request = summary.brief` of the OLD run, plus whatever question framing path A picked → mix | `rehydrate.py:400`; Blue Wave case above |

The brief is stored in three places: `tasks.user_text` (db, owner's words of THAT task only), `task.json.user_text`, and J2's `summary.json.brief` / first `user` line of `chat.jsonl`. Nothing re-reads the earlier task's `user_text` on a follow-up. Evidence chain Bean There (`web-design`): 17e1 stopped → 7f80 "Option 1" (fresh, brief lost, Identity asks again) → 600d, 06e8 ... each seeded from the previous stopped run.

## 4. Every site that carries earlier-run context (where one shared fix can live)

| # | Site | Kind | Fix candidate |
|---|---|---|---|
| 1 | `tasks.py:1016-1052` `_follow_up` (seed + orphan question framing) | decision + carrier | **the one shared decision point for path A**; framing should come from the seed run only, or not at all when not continuing |
| 2 | `agent/runner.py:707-729` + `decide.md:5`/`assign.md:7` (`follows`) | agent decision | already agent-decided; prompt gives no guidance on relatedness |
| 3 | `tasks.py:563-570` `_insert(follows=…)` → `seed_from` | carrier | common sink of 1 and 2 |
| 4 | `tasks.py:774-775` `_run_spec` → `task.json` (`framing`, `seed_from`, `parent_run_id`) | carrier | none needed if 1/3 are right |
| 5 | `loop.py:335-354` `_seed_output` → `select.py:87-88` | carrier (output type) | other dev's ticket; note it ignores the seed's status |
| 6 | `loop.py:537-553, 575-595` `_seed`, `_copy_seed_files` | carrier (state / upstream) | none needed if no seed |
| 7 | `loop.py:664-665` framing line, labelled "team lead" | carrier | label is misleading for an old question |
| 8 | `capabilities/project.py:129-167, 300-304` `earlier_report` | carrier (system prompt) | keyed on `seed_from`; follows 3 |
| 9 | `rehydrate.py:385-418` | carrier | keyed on `seed_from` |
| 10 | `run_inputs.py:109-129` D451 memory | carrier, by design per team | out of scope unless the owner says otherwise (open question) |

Every engine-side carrier (5-9) keys on `task.seed_from`. So one correct `seed_from` (and framing) decided before `task.json` is written fixes 5-9 without touching the engine or J2.

## 5. Tests

| Area | Tests | Note |
|---|---|---|
| path A seed, reset, orphan framing | `tests/orchestrator/test_tasks.py:387-541` (`test_followup_seed_from_is_the_latest_run_that_has_a_folder` :403, `test_orphaned_question_framing` :519, reset :431-495, `test_retry_has_no_seed` :497) | :403 and :519 encode today's behaviour and will change |
| path B `follows` | `test_tasks.py:170`; chat agent `tests/orchestrator/test_api_agent.py`, `test_scripted_conversation.py` (not read in detail) | |
| host seed / framing / upstream | `tests/engine/test_engine_host.py:624-710` | |
| rehydrate | `tests/engine/test_engine_rehydrate.py`, `test_engine_rehydrate_chain.py`, `test_rehydrate_any_output.py`, `test_named_project_two_runs.py` | |
| earlier report | `tests/engine/test_engine_project_followup.py:54-195` | |
| end to end | `tests/e2e/test_scenario_followup.py:90-190` (:166 asserts the stopped-run follow-up framing), `test_scenario_restart_stop.py:49-210` | |
| run spec golden | `tests/orchestrator/test_run_spec_golden.py`, `test_project_context_golden.py:25-29` | |

Gaps: no test for an unrelated brief after a finished run; none for an orphan question from a different run than the seed; none that the brief survives a stop/restart follow-up; none that `_seed_output` ignores a stopped seed.

Command (ran once, 2026-11-26, working tree): `scripts/py -m pytest tests/orchestrator/test_tasks.py tests/engine/test_engine_host.py tests/engine/test_engine_project_followup.py tests/engine/test_engine_rehydrate.py tests/engine/test_rehydrate_any_output.py tests/e2e/test_scenario_followup.py -q` → 189 passed. Full gate: `scripts/gate.sh` (foreground, about 15 min; not run). Tests failing on main: not checked (no main checkout made; none fail in this subset).

## 6. Constraints for later stages

| # | Constraint |
|---|---|
| 1 | An agent decides continue vs fresh; code only carries the decision. No keyword or overlap rule, no hard-coded subjects (the founder's "agents decide, code validates", `select.py:9-11`). |
| 2 | Unrelated brief → clean start: no seed, no upstream copy, no earlier report, no orphan question. Real continuation (incl. answering a question after a stop or restart) keeps context, and the original brief must reach the new run. |
| 3 | Smaller, not bigger: one decision point before `task.json` (site 1/3), engine carriers untouched. Reuse an existing agent call where possible (the chat agent already decides `follows` for path B). |
| 4 | No Pulse- or bakery-specific logic. |
| 5 | Do not touch the `followup` output rule beyond noting it: another dev's ticket. Coordinate: if `seed_from` is cleared, that rule stops firing for unrelated briefs anyway (`loop.py:340`). |
| 6 | J2 (`engine/j2.py`) is vendored: any change there is a P patch in `scripts/vendor_j2.py`; `remove-real-run-gates` rewrites j2.py and merges first. The fix as scoped needs no J2 patch and no page edit (E). |
| 7 | Never touch `~/.sutra-pro`; no home paths or owner names in tracked files (`tests/test_ownership.py`). |
| 8 | Record a decision amending D21 (follow-up seeding, `docs/DECISIONS.md:156`) and touching D429, D135; `docs/diagram/decisions.json` entry needed (`tests/test_diagram_decisions.py`). |

## 7. Record numbers

| Kind | Lives in | Highest found | Next free |
|---|---|---|---|
| D (decision) | `docs/DECISIONS.md` `## D<n> — title` + `docs/diagram/decisions.json` | D452 (remove-real-run-gates, also origin/sutra-runs-own-code), D453 (live-view) | **D454** |
| P (J2 patch) | `scripts/vendor_j2.py` `Edit("P<n>", ...)` + `sutra_app/engine/VENDORED.md` | P46 (remove-real-run-gates); P45 origin/sutra-runs-own-code | **P47** |
| E (page edit) | `scripts/port_j2_ui.py` edit table, checked by `tests/ui/test_port_edits.py` | E31 (remove-real-run-gates), E32 (live-view) | **E33** |

Scanned every local and remote-tracking branch with `git show <ref>:<file>`; no `git fetch` was run, so remote refs are as of the last fetch (unverified against GitHub). The local branch `sut-26-context` exists and equals origin/main (no commits).

## Ownership
No CODEOWNERS. `_follow_up` last changed in 751f6b0a (D451) and aed5038e (reset marker, 2026-11-07); `rehydrate.py`/`project.py` in 6709ff6f (D429).

## Open questions
1. Which agent decides for path A (team chat)? Options: (a) reuse the chat agent's decision (it already emits `follows`), (b) one small model call in `_follow_up`, (c) let J2's Identity decide in the first turn (needs a J2 patch; rehydrate must happen before any line, `rehydrate.py:38-40`, so harder). (b) or (a) keeps the engine untouched.
2. An answer to an orphan question after a stop/restart: should that skip the agent (it is a continuation by construction) and pass the original brief (old task `user_text`) along with the answer?
3. Should the orphan question be limited to the seed run's own task (it is not today), and should older open questions be closed when a newer task starts?
4. D451 team memory carries earlier requests into every run by design. Keep for unrelated briefs, or drop when the agent says "fresh"? Owner decision.
5. Path B: does the chat agent's prompt need a sentence on when to set `follows`, or is it acceptable as is? (software-engineering shows it chained sort-files → gmail reader → Pulse.)
6. Label "Context from the team lead" for an old question (`loop.py:665`): reword? Text change only, but goldens may shift.
