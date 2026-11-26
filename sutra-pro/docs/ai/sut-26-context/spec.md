# Spec: A new run in a team starts clean unless an agent decides it continues an earlier run
Status: Refined   |   Task: sut-26-context (SUT-26)   |   Date: 2026-11-26

Inputs: `docs/ai/sut-26-context/impact.md` (stage 1), owner decisions of 2026-11-26 (binding, marked "Owner" below), owner rulings on the open questions (2026-11-26, after the first draft). Code citations are from the working tree of `remove-real-run-gates`; `remove-real-run-gates` (D452/P46/E31) and `live-view` (D453/E32) merge before this work. `sutra_app/engine/j2.py` changes heavily on `remove-real-run-gates`, so J2 behaviour is described by function, not by line.

## Problem
When the owner writes in a team's chat and the team has no live task, code makes the new task continue the team's newest run, whatever its subject. It also adds, as "Context from the team lead", the newest unanswered question of any ended task of the team, which can belong to a different run than the one being continued. Two observed results (beta data, described generically):

| Case | What happened |
|---|---|
| Unrelated brief | An owner asked for a new page for a small food business. The run was seeded from a stopped run on another subject, framed with an 8-day-old question from a third run, forced to that run's output type, and asked the owner for a working folder. |
| Answer to the wrong run | An owner's reply ("Option 2") to a question from one business's run was applied as a change request to another business's finished website, with the first business's question as framing. |

After a stop or an app restart, the owner's answer to an open question becomes a new task whose brief is the answer alone ("Option 1"). When the earlier run was stopped, the new run never sees the original brief and asks for it again.

## Goals
| # | Goal |
|---|---|
| G-1 | A new, unrelated brief starts a clean run: no seed, no parent run, no framing from an earlier question. |
| G-2 | A real continuation keeps its context: the run it continues, that run's own question, and the original brief plus the new words. |
| G-3 | Whether a team-chat message continues an earlier run is decided by an agent (the chat agent's `follows` decision); code only carries the decision. |
| G-4 | The fix stays small, at one fix point before `task.json` is written. |

## Non-goals
| # | Not in this work | Why |
|---|---|---|
| NG-1 | D451 team memory (`run_inputs.py:109-129` `given_for`) | Owner: unchanged. See R-1. |
| NG-2 | `_seed_output` not checking the seed's status (`engine/host/loop.py:335-354`) and the `followup` output rule (`capabilities/select.py:87-88`) | Owner: another developer's ticket. Overlap: when FR-3 clears `seed_from`, `_seed_output` returns None (`loop.py:338-340`), so the rule no longer fires for unrelated briefs. |
| NG-3 | Rehydrate rules (which statuses and output types can be continued, `rehydrate.py:295-334`) | Unchanged; a stopped or crashed seed still starts fresh with `upstream/` files. |
| NG-4 | Answers to a task that is still live (`tasks.py:938-948`: waiting answer, override, Busy) | Already go to the right task; no model call is added there. |
| NG-5 | Retry (`tasks.py:1158-1190`, never seeds) and `POST /api/tasks` with an explicit `follows` | The caller decides; unchanged. |
| NG-6 | Keyword, word-overlap, time-window or subject rules; anything specific to one product (for example Pulse) | Owner: no hard coding. |
| NG-7 | The org-chat digest (`chart_rules.py:184-203`) | Q-4: unchanged; only the prompt sentence of FR-5 changes. |
| NG-8 | The "Context from the team lead" label (`loop.py:665`) | Q-8: unchanged, no golden shifts. |

## User scenarios
| # | Given | Owner does | Expected |
|---|---|---|---|
| S-1 | Team finished a website for business A | Writes a brief for an unrelated page for business B in the team chat | Clean run. No `upstream/`, no earlier report, no "Context from the team lead" line. |
| S-2 | Team finished a website | Writes "make the header blue" | Agent picks that run: continues it (rehydrate), as today. |
| S-3 | Run R1 stopped while waiting on a question (owner pressed Stop or the app closed) | Answers the question in the team chat | New run continues R1 only: framing is R1's question, brief is R1's brief plus the answer. |
| S-4 | Run R1 (business A) ended with an unanswered question; later run R2 (business B) finished | Replies to R1's question | Continues R1, not R2. Framing is R1's question. If the agent cannot tell, clean run. |
| S-5 | Agent cannot tell whether the words relate to any earlier run | Writes something short or ambiguous | Clean run. |
| S-6 | R1 stopped, R2 continued R1 with an answer and also stopped | Answers R2's question | R3's brief still contains R1's original brief. |

## Current behaviour
| # | Behaviour | Evidence |
|---|---|---|
| C-1 | Team chat with no live task and no queued task → `_follow_up` | `orchestrator/tasks.py:938-954` |
| C-2 | Seed = newest task of the team whose run folder exists, any status, any subject. No agent involved. | `tasks.py:1021-1027` |
| C-3 | Owner's "+ New run" reset marker: a seed at or before `page.json.since_run` is dropped (no seed, no parent, no framing) | `tasks.py:1028-1032`, `_reset_marker` `tasks.py:1054-` |
| C-4 | Framing = newest unanswered question of ANY ended task of the team, not tied to the seed; only that one question is marked answered | `tasks.py:1033-1040`, `:1050-1051` |
| C-5 | Parent = the team's latest task (`latest_in`), independent of the seed | `tasks.py:1020`, `:1044` |
| C-6 | Framing reaches the run as the system line `Context from the team lead: ...` | `engine/host/loop.py:664-665` |
| C-7 | Org-chat path: the chat agent sets `follows` per assignment; a `follows` that fails validation is dropped and the task starts fresh | `agent/runner.py:707-729`; `_insert` sets seed and parent `tasks.py:563-570` |
| C-8 | The chat agent sees per team only `last: <title> (<status>) <task id>`; its prompt says which ids `follows` may name, not when to use it | `chart_rules.py:184-203`, `_last_text` `:260-261`; `agent/templates/decide.md:5`, `assign.md:1` |
| C-9 | Org-chat `create` neither adds nor closes an orphan question, so open questions pile up for C-4 | `tasks.py:514-523` |
| C-10 | Every engine-side carrier of earlier context keys on `task.seed_from`: output rule, rehydrate or `upstream/` copy, earlier report | `loop.py:335-354`, `:537-553`, `:575-595`; `capabilities/project.py:129-167` |
| C-11 | The host hands `task.user_text` to J2 as the first owner line; J2 sets its brief from the first owner line when it has no charter | `loop.py:675`; `j2.py` `J2Run` intake branch (`self.request = last_user`, working tree `j2.py:5263`) |
| C-12 | Seed stopped or crashed → rehydrate refused, fresh run with `upstream/<id>/`; the earlier `chat.jsonl` (where the brief was) is not copied, so the brief is lost | `rehydrate.py:303-305`; `loop.py:546-552`, `SEED_FILES` `loop.py:69` |
| C-13 | Seed finished → rehydrate: the new run's brief = the earlier `summary.json` brief, the answer becomes a change request | `rehydrate.py:400`; e2e `tests/e2e/test_scenario_followup.py` asserts `change_requests` |
| C-14 | Verified (Q-7): J2 builds `summary.json` in `J2Run._metrics` with `brief: self.request` and saves it through `_save_report` into the NEW run's own folder. A rehydrated run copies the earlier `summary.json` into the new folder (`rehydrate.py:171-185`) and later replaces that copy. Nothing writes the earlier run's folder; the bug is that `self.request` can be the answer alone (C-11, C-12). | `j2.py` `_metrics`, `_save_report`; `rehydrate.py:171-185`; D21 "the old folder is never written again" `docs/DECISIONS.md:156` |
| C-15 | Needs-you lists every unanswered question of a team chat, of any task status | `orchestrator/chats.py:404-423` |
| C-16 | The engine's `/api/say` reaches `deliver_to_department` from a worker thread (`run_in_threadpool`) | `engine/api/commands.py:207-208`, `:120` |

## Functional requirements
| ID | Requirement |
|---|---|
| FR-1 | When the owner writes in a team's chat and the team has no live, blocked or queued task, the decision whether the new task continues an earlier run of that team is made by the chat agent's `follows` decision (Owner decision 1). Code does not choose a seed, by recency or otherwise. |
| FR-2 | Code carries only what the agent decided: the chosen task's run becomes `seed_from` and that task becomes the parent (`parent_task_id`, hence `parent_run_id`). Code validates the choice (one of the candidates of FR-4, re-checked inside the write transaction) and adds no rule of its own. |
| FR-3 | When the agent sets no `follows`, names a task that is not a candidate, or its call fails, times out or raises anything, the new task starts clean: `seed_from` empty, `parent_task_id` empty, no framing from an earlier question. The owner's words still become the task (never lost). |
| FR-4 | For a team-chat message, the agent sees: the owner's new words, and for each candidate earlier run: task id, title, status, the brief that run worked on (FR-11), and that task's own newest unanswered question, if any. It sees no files, outputs or reports of those runs. Candidates are the team's ended tasks (status done, done_with_open_items, stopped, crashed or cancelled) that have a run id and a run folder, made after the reset marker (C-3); the newest 5. |
| FR-5 | The decision instructions say: set `follows` only when the owner's words continue that run or answer its question; when not sure, leave it empty. The same sentence goes into the org-chat assignment prompts (`decide.md`, `assign.md`). |
| FR-6 | The framing of a continuation is the seed task's own newest unanswered question ("Earlier the team asked the owner: <q>", wording unchanged), and only that. A question of any other task is never used as framing (Owner decision 2). A clean task has no question framing. |
| FR-7 | Only the seed task's open questions are marked answered by the owner's line. A clean start the agent judged (no pick, or a failed call) marks no question answered. Exception (owner ruling Q-10): after the owner's reset ('+ New run') with no run made since, the line closes the newest open question of an ended task, as it does today, without carrying it as framing. |
| FR-8 | An answer to a question of an ended run (stopped, crashed, done, done with open items, cancelled) continues that run only, when the agent picks it: seed = that run, framing = that run's question. |
| FR-9 | A continuation's brief, both as given to the run's agents and as recorded in the new run's `summary.json`, contains the seed run's brief and the owner's new words. It is never the new words alone (Owner decision 4). Concretely: when the seed task ended stopped, crashed or cancelled, the new task's `user_text` (and so `task.json.user_text`, J2's first owner line and its recorded brief) is the seed's brief, a blank line, `The owner now writes: `, then the owner's words; the seed's brief is clipped to 20,000 characters. When the seed ended done or done_with_open_items, `user_text` is the owner's words: rehydrate keeps the seed's brief as the recorded brief and the words become a change request (C-13). |
| FR-10 | FR-9 holds whether the seed was stopped or crashed (fresh start with `upstream/`) or finished (rehydrate). For a finished seed the new words may be recorded as a change request (C-13) as long as the seed's brief is the recorded brief. (Owner: kept as written; the answer may live in `brief` or `change_requests`.) |
| FR-11 | The seed run's brief used in FR-4 and FR-9 is the seed task's stored `user_text`. For a seed that was itself a continuation of a stopped run this already holds the earlier brief (FR-9), so a chain (S-6) keeps the first brief. |
| FR-12 | No file in the earlier run's folder, including `summary.json`, is created, changed or deleted by the continuation (Owner decision 4; D21). Kept as a regression test: C-14 found no such write. |
| FR-13 | The reset marker keeps its effect: a run at or before `page.json.since_run` is not a candidate (C-3). |
| FR-14 | A team with no candidate run starts clean without asking the agent. |
| FR-15 | The owner's line in the team chat is the owner's words alone (plus the attached-files line, as today); the combined brief of FR-9 is never shown as the owner's line. |
| FR-16 | Record D454 in `docs/DECISIONS.md` (amends D21 at `DECISIONS.md:156`: `seed_from` from a team-chat follow-up is the agent's choice; framing is the seed's own question; the brief is carried) and add it to `docs/diagram/decisions.json`. No J2 patch (P47) and no page edit (E33) are needed by this design. |

## Non-functional requirements
| ID | Requirement | Check |
|---|---|---|
| NFR-1 | At most 1 model call per team-chat follow-up, no retry; 0 when FR-14 applies. Answers to a live waiting task, overrides and Busy refusals make no call. | test counts connector calls |
| NFR-2 | Agent call failure, timeout or invalid output → clean start within the existing chat agent timeout (`settings.chat_timeout`, plus the agent's 10 s grace); the owner's line is stored and the task created. | test with a failing scripted connector |
| NFR-3 | No keyword, word-overlap, time-window or subject-name logic decides continuation; no product-specific strings. | code review; grep of the diff for subject literals |
| NFR-4 | Small: one decision point on the orchestrator side before `task.json` is written. Engine host, `rehydrate.py`, `capabilities/*` and J2 unchanged. Net non-test source lines in `sutra_app/` reported in `implementation.md` (aim: no net growth; reported, not enforced). | diff stat in `implementation.md` |
| NFR-5 | The agent's input under FR-4 is bounded: at most 5 candidates; each brief and question clipped to 1,000 characters. | unit test on the prompt |
| NFR-6 | Tests use synthetic data only: no beta run data, no real mail, no home paths or names (`tests/test_ownership.py`). | `tests/test_ownership.py` |
| NFR-7 | Existing run folders and database rows stay readable; no change to the layout of `task.json` fields `seed_from`, `parent_run_id`, `framing`. | `tests/orchestrator/test_run_spec_golden.py` |
| NFR-8 | The model call runs outside the database write transaction. | code review; test that a second message during the call gets Busy |

## Acceptance criteria
Each AC is one test with synthetic data and a scripted agent. Tests failing on `main` before this work are ignored (plan T0 records them).

| AC | Given / When / Then | Maps to |
|---|---|---|
| AC-1 | Given a team whose last run finished on subject A, when the owner writes an unrelated brief and the agent sets no `follows`, then the task has no `seed_from`, no `parent_task_id`, no framing, and the run folder has no `upstream/` | FR-1, FR-2, FR-3, G-1 |
| AC-2 | Given a finished run, when the agent's call fails, times out, raises, or returns an id that is not a candidate (another team's task, an unknown id), then the task starts clean, the owner's line is stored, and exactly 1 call was made | FR-3, NFR-1, NFR-2 |
| AC-3 | Given a finished run with no open question, when the agent sets `follows` to it, then `seed_from` is that run, parent is that task, framing is empty, `user_text` is the owner's words | FR-2, FR-6, FR-9 |
| AC-4 | Given R1 ended with question Q1 and R2 ended with Q2, when the agent picks R1, then framing is Q1 only, Q1 is marked answered and Q2 stays open | FR-6, FR-7, FR-8 |
| AC-5 | Given R1 ended with Q1 and a later R2 finished, when the agent picks R2 (or none), then the framing never contains Q1 and Q1 stays open | FR-6, FR-7 |
| AC-6 | Given a team chat message and 6 candidate runs, when the agent is asked, then its prompt lists the newest 5 with id, title, status, brief and own open question, each brief and question at most 1,000 characters, and contains no run files or reports | FR-4, NFR-5 |
| AC-7 | `follows.md`, `decide.md` and `assign.md` contain the "only when continuing or answering; when not sure, leave it empty" instruction | FR-5 |
| AC-8 | Given R1 stopped while waiting on Q1 (owner Stop, and app shutdown via `TaskService.shutdown`), when the owner answers and the agent picks R1, then the new run's `task.json.user_text` holds R1's brief and the answer, its `summary.json` `brief` contains both texts, the team chat line is the answer alone, and R1's folder is byte-identical before and after | FR-9, FR-10, FR-12, FR-15 |
| AC-9 | Given R1 finished with an open question, when the owner answers and the agent picks R1, then the rehydrated run's `summary.json` `brief` equals R1's brief, the answer is in `brief` or `change_requests`, framing is R1's question, and R1's folder is byte-identical | FR-9, FR-10, FR-12 |
| AC-10 | Given R1 stopped, R2 continued R1 and stopped, when the owner answers R2's question and the agent picks R2, then R3's `user_text` contains R1's original brief text | FR-11 |
| AC-11 | Given a reset marker at R1, when the owner writes, then R1 is not a candidate, no call is made and the task starts clean | FR-13, FR-14 |
| AC-12 | Given a team with no run, when the owner writes, then no model call is made and the task is clean | FR-14, NFR-1 |
| AC-13 | Given a team waiting on the owner, when the owner answers, then no model call is made | NFR-1 |
| AC-14 | Given the agent call is in flight, when a second team-chat message arrives and the first creates its task, then the second gets Busy | NFR-8 |
| AC-15 | `tests/test_diagram_decisions.py` passes with D454 in both files | FR-16 |

Existing tests that encode today's behaviour and will change:

| Test | Today asserts | After |
|---|---|---|
| `tests/orchestrator/test_tasks.py:387` `test_no_live_task_makes_a_follow_up_that_continues_from_the_old_run` | continues the newest run, chosen by code | continues only with a scripted pick |
| `tests/orchestrator/test_tasks.py:403` `test_followup_seed_from_is_the_latest_run_that_has_a_folder` | seed = newest run with a folder, chosen by code | becomes "a run without a folder is not a candidate" (AC-6 area) |
| `tests/orchestrator/test_tasks.py:444`, `:478` (reset covers only earlier runs; unusable page file) | the later run is continued by code | the later run is a candidate; continued with a scripted pick |
| `tests/orchestrator/test_tasks.py:485` `test_a_question_left_open_by_a_reset_is_closed_but_not_carried_into_the_fresh_run` | the reset's orphan question is marked answered | unchanged (owner ruling Q-10); also asserts no agent call |
| `tests/orchestrator/test_tasks.py:519` `test_orphaned_question_framing` | newest orphan question of any task becomes framing | framing from the chosen seed's question only (AC-4, AC-5); `user_text` combined (FR-9) |
| `tests/e2e/test_scenario_followup.py` `chain_of_tasks` (:46) and the document-chain follow-up (:144) | follow-up after Done continues by code | the scripted connector is pushed a `follows` reply first |
| `tests/e2e/test_scenario_followup.py:166` stopped-run follow-up | framing and fresh start after a stopped run, decided by code | scripted pick; adds the AC-8 brief and byte-identical checks |
| `tests/e2e/test_scenario_restart_stop.py:127` | the open question is answered by the next team-chat line | scripted pick of the stopped task, so it is still answered |

## Assumptions
| # | Assumption |
|---|---|
| A-1 | Whether the owner's words are an answer to an old question or a new brief is part of the same agent decision; no separate classifier. |
| A-2 | Resolved by FR-11: the seed's brief is its task row's `user_text`, which exists for every task, including crashed runs that never wrote `summary.json`. |
| A-3 | The org-chat path's behaviour stays as is apart from FR-5; its digest keeps `last:` per team (Q-4). |
| A-4 | A queued or blocked task still makes a team-chat message Busy (`tasks.py:951-952`). |
| A-5 | A task whose status is done or done_with_open_items has a `summary.json` J2 can rehydrate from in the normal case; when rehydrate refuses such a seed, the brief is only in `upstream/<id>/summary.json` (R-6). |

## Risks
| # | Risk | Note |
|---|---|---|
| R-1 | D451 team memory (`run_inputs.py:109-129`) still puts earlier owner requests and outcomes into every agent call of every run, so a clean run can still see an unrelated earlier request | Owner decision 3: left unchanged; owner will check with Kaivan. |
| R-2 | Overlap with Kaivan's ticket on `_seed_output` and the `followup` rule (NG-2) | Both touch the seeded path; merge order to agree. |
| R-3 | A model call in the team-chat path adds latency (the owner's line is stored only after the decision, typically seconds, at worst the chat timeout) and cost per follow-up | NFR-1 bounds the count. Owner ruling: post the line first if that is a small change; developer found it is not (implementation.md), so the design stands and the owner checks the delay in the beta. |
| R-4 | The agent may wrongly continue (false positive) or miss a continuation (false negative, e.g. a bare "Option 2") | FR-5 instruction, FR-3 default, the candidate's own question in the prompt; no code rule backs it up by design. |
| R-5 | Record numbers collide with parallel branches | D454 checked 2026-11-26; re-check after fetch (plan T0). |
| R-6 | A done seed that rehydrate refuses (no page, no chain, missing files) starts fresh with the owner's words alone as brief | Rare; the earlier brief is in `upstream/<id>/summary.json`. Accepted to keep change requests free of the old brief. |
| R-7 | Offline demo (`--offline`) and tests whose scripted connector has no reply for the new call start team-chat follow-ups clean | FR-3 by design; affected tests push a reply (plan T4, T5). |
| R-8 | Unanswered questions of runs that are never continued stay in Needs-you (C-15) | Q-10. |

## Open questions
| Q | Question | Answer / status |
|---|---|---|
| Q-1 | How the team-chat path reaches the chat agent's `follows` decision | Answered (architect): a narrow template `follows.md` run through the chat agent's existing `_stage` with the existing `chat_turn`/`assignments` reply schema (no new reply family), one attempt. The full `decide` call would also decide chart changes and teams, which a team chat must not do. See architecture D-1. |
| Q-2 | Where the model call goes and how a second message during it is handled | Owner: decide before the write transaction, re-check inside it, Busy otherwise (FR-2, NFR-8). |
| Q-3 | Candidate count and clip sizes | Owner: up to 5 earlier runs, brief and question clipped to 1,000 characters each (FR-4, NFR-5). |
| Q-4 | Should the org-chat digest also show briefs | Answered (architect): no. The digest is the whole chart under a 6,000-character cap (`ports.py` `DIGEST_CHARS`); FR-5 alone. NG-7. |
| Q-5 | Where the combined brief is built | Owner: orchestrator side before `task.json`, no J2 patch (FR-9). |
| Q-6 | NFR-4 line target | Owner: not a requirement; reported only. |
| Q-7 | Does any path write the earlier run's `summary.json` | Owner-verified, confirmed by reading: no (C-14). FR-12 stays as a regression test. |
| Q-8 | Label "Context from the team lead" for an old question | Answered (architect): keep; NG-8. The framing text itself starts "Earlier the team asked the owner:", which already says it is old. |
| Q-9 | Open questions of tasks never continued stay open | Answered (architect): leave them open; they are shown to the agent only with their own run, and answering one later can still continue that run while it is among the newest 5. |
| Q-10 | (owner, not blocking) Q-9 means a question the owner moved past stays in Needs-you and its count (C-15), including after "+ New run" (today the next line closes it). Should a clean start close the team's older open questions instead? | Owner ruling: "+ New run" keeps closing what it closes today; an agent-judged clean start leaves them open (FR-7). Tests: `test_a_question_left_open_by_a_reset_is_closed_but_not_carried_into_the_fresh_run` (kept), `test_another_runs_question_is_never_the_framing_and_stays_open`. |

## Change log
| Date | Change |
|---|---|
| 2026-11-26 | First draft from impact.md and owner decisions 1-5. |
| 2026-11-26 | solution-architect: Status Refined. Applied owner rulings Q-2, Q-3, Q-5, Q-6 (NFR-4 now reports, does not target), Q-7 (C-14 rewritten as verified: J2 writes only the new run's folder; FR-12 kept as regression test), FR-10 kept as written. Answered Q-1, Q-4, Q-8, Q-9 with evidence; added Q-10 for the owner (not blocking). |
| 2026-11-26 | solution-architect: FR-4 tightened (candidate statuses, newest 5, the task's newest open question). FR-9 made testable: combined `user_text` format and 20,000-character clip; combined only for a stopped, crashed or cancelled seed, because a finished seed is rehydrated and J2 already keeps its brief (adding it again would put the old brief into the change request and break C-13). FR-10 still holds; R-6 added for the rare refused-done case. |
| 2026-11-26 | solution-architect: FR-11 changed from "the brief that run recorded (summary.json)" to "the seed task's stored user_text": same text for every run J2 recorded from it, also present for crashed runs with no summary (resolves A-2), no file read. Chains still keep the first brief. |
| 2026-11-26 | developer, owner rulings after the plan: Q-10 (reset keeps closing its question; agent-judged clean start leaves questions open; FR-7 amended), R-3 (post the line first only if small; it is not, see implementation.md), FR-3 confirmed (a failed, erroring or timed-out call starts clean, tested), live-test steps a to d added to plan T8. |
| 2026-11-26 | solution-architect: NFR-1 adds "no retry"; FR-3 adds "raises anything" (a connector double that raises a non-connector error must not break delivery); added FR-15 (team chat shows the owner's words alone), NFR-8 (call outside the transaction), AC-13, AC-14, C-15, C-16, NG-7, NG-8, R-6 to R-8. FR-15 (records) renumbered FR-16 and states P47/E33 are not needed. Existing-test table extended with test_tasks.py :387, :444, :478, :485 and two e2e tests found by reading. |
