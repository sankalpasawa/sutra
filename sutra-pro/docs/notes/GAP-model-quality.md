# GAP-model-quality as built: a grounded direct chat, a retry that is told what happened, a receipt on the done card

Three verified gaps of the old-app comparison, built once each (the retry's attempt number and the receipt overlap: the receipt shows it).

## 1. The direct chat is grounded in its node's own record

- What the owner gets: "Ask directly" (org chat) and "Ask the model" (a team or division chat) now answer knowing where they are: the team's name
  and purpose, its divisions, its latest tasks (status, end time, outcome), the question the team waits on, the other teams by name, and what
  this chat may not do (no chart change, no start, stop or message to a team; "Plan with Sutra" or "Tell the team" instead). The org chat gets
  every team with its purpose and latest task status and the teams that wait for an answer. Rules carried over from the old task chat:
  never speak for the team, never narrate the machinery, answer from the record or say it does not know.
- Where: new `sutra_app/orchestrator/chat_ground.py` (`ChatGround(db, scrub).text(sid)`, `ground(services, sid)`; at most 3 000 characters,
  whole record lines cut first with a note, the rules always kept). `RouterChatPort.set_system(sid, text)` in `connectors/chat_port.py`
  (also on the `ChatPort` protocol) writes `<workdir>/system.txt` 0600 by temp file and rename; an empty text removes it.
  `orchestrator/api/chat_v2.py`: `/direct` calls `_ground` after storing the owner's line, every turn, so the text is current.
- Isolation: every read is scoped by the node id in SQL (a department's tasks by `dept_id`, a division's by `scope_node_id`, the question by
  the session id); another team appears in a team's text by name only. Scrubbing: each record line goes through the app's redactor and the
  egress credential shapes (`scan(replace=True)`) before it is fitted, so a replacement never pushes the rules out.
- Seams used as they were: the Router already re-reads `system.txt` when it starts a provider session (`_new_session`), Claude's connector
  re-reads it on every turn (`base._session_system`, `--system-prompt`), Codex puts it in front of the first prompt of a thread.
- A grounding that cannot be built or written is logged and the turn runs; it never fails the turn.

## 2. A retry is told how the earlier attempts ended

- What the owner gets: "Try again" on a crashed, stopped, cancelled or left-open task (the existing `POST /api/tasks/{id}/retry`) no longer
  starts blind. The new run's framing (posted by the engine host as "Context from the team lead: ...") ends with a fixed-template brief:
  "This is attempt 2 of this request. It starts fresh ... Attempt 1 crashed: <outcome>", the done-when items its audit met and did not meet
  or check, limits hit, what was left to confirm with the owner, its closed and unfinished atoms, a crash's error-log tail, and "None of it
  counts as done or checked in this run."
- Where: new `sutra_app/orchestrator/attempts.py` (`chain`, `brief`, `attempt_of`, `attempt_in`, `ATTEMPT_KEY = "_attempt"`).
  `TaskService.retry` (tasks.py) builds framing = the FIRST attempt's own framing + the brief (so briefs never pile up), clipped to the
  20 000-character framing cap (the brief itself at most 4 000, newest attempt filled first), and stores the attempt number under
  `_attempt` in `settings_json` beside `_seed_from` (readers drop underscore keys; `TaskStore.insert` and `_settings_json` take it).
  `seed_from` stays None: a retry still starts fresh.
- Facts only: the task row, the run folder's `summary.json` (J2's `_write_summary`, code only; read tolerantly, a missing or broken file is
  skipped), the atoms table, `run.stderr.log`. No chat line is read. Every text goes through the redactor and the egress shapes.
- The chain is the parents with the same department and the same words, each a retry (`_attempt` at least 2); a follow-up (new words)
  starts its own chain. The engine never reads `parent_run_id`, so "it starts fresh" is literally true and the brief says so.

## 3. The done card carries a receipt

- What the owner gets: under the outcome of a done card in the org chat, one evidence line: "Attempt 2 · Took 6 min · about $0.42 ·
  7 of 8 items passed their checks". No dollars under half a cent (the old rule; then the tokens, which is what a Codex-only task shows),
  "about" because the ledger's figure is a floor, no checks part when the team recorded no atoms, the attempt only for a retry.
- Where: `DoneReceipt` and `DoneCard.receipt` in `orchestrator/models.py` (closed, additive; a card without one dumps without the key, so
  every stored card keeps its wire shape); `Projector._receipt` fills it inside `_finish` from `UsageStore._task_total` (stub rows left out),
  `ended_at - started_at`, `atoms` by display (closed = passed; open function atoms were abandoned just before) and `attempts.attempt_in`.
  `chat_view.js` `doneCard` draws `p.creceipt` (escaped, numbers only); one rule `.ncard .creceipt` in `css/sutra-panel.css` (`--muted`).
  The replayed drain posts nothing new (the card's `src_ref` `<run>#done` is unique).

## Tests (all green)

- `tests/orchestrator/test_chat_ground.py` 13: team, division and org texts; rules; short form; an answered question is gone; the old
  context-isolation test re-expressed (A's task and secret never in B's text); a credential and an app secret arrive redacted; a long record
  is cut by whole lines; a function or unknown session gets the rules alone; the route grounds the turn and rebuilds it on the next; the org
  chat is grounded; a broken grounding does not fail the turn.
- `tests/connectors/test_chat_port.py` +4: `set_system` writes 0600, replaces, removes, refuses a path id, leaves no temp file; one session's
  text is never another's; it survives a quota switch to Codex; the real `claude` (fake CLI) gets it on `--system-prompt` and the real
  `codex` in front of its first prompt.
- `tests/orchestrator/test_attempts.py` 11: no brief on a first attempt; a long first framing is cut, never the brief; a summary of the
  wrong shape or broken JSON is skipped; attempt 2 lists the summary's met and unmet items, limits, the
  left-to-confirm list and the atoms; attempt 3 lists both earlier attempts once and the base framing once; a crash with no summary still
  says how it ended and its stderr tail is scrubbed; no chat line is promoted; a check named in the framing is listed met only when the audit
  said so; a follow-up starts its own chain; the cap fills the newest attempt first; `attempt_of` takes whole numbers only.
- `tests/orchestrator/test_done_receipt.py` 6: usd, tokens, seconds and atom counts; Codex-only tokens; no atoms no checks; a replayed drain
  changes nothing; a retry's card names attempt 2; an old card keeps its exact wire shape.
- `tests/orchestrator/test_tasks.py::test_retry_has_no_seed` gains one assertion (the framing now carries the brief; `seed_from` still None).
- `tests/ui/js/chat_view.test.js` +4: the receipt line, the half-cent and no-atoms rules, a card without a receipt is byte for byte the old
  markup, hostile receipt values are escaped and only numbers are used.

## Docs changed

`docs/design/orchestrator.md` (the `done` card shape; the retry sentence in 5.5 and the route table), `docs/design/ui.md` (the done card
row), `docs/TROUBLESHOOTING.md` F7 (what Retry now tells the new run), `docs/design/absorb-old-sutra.md` (row 32 and risk 8). Row 35 (cost
per task REPLACED) is left as it is because the attention package edits the same row (presence); it should say "shown on the done card"
after the merge.

## Not done, and why

- No new row in `docs/DECISIONS.md`: other packages are being built in parallel and a new D-number would collide at the merge. The three
  decisions are: the direct chat's system text is built from the node's own record every turn (refines D115); a retry is told, never seeded;
  the done card shows an evidence-only receipt. They belong in one D-row when the packages are merged.
- No `GET /api/tasks/{id}/attempts` route: the chain is visible where the owner already looks (each attempt's done card says "Attempt N" and
  its own "X of Y items passed their checks"), so a route with no page to read it would add surface without an owner-visible change.
- A resumed Codex thread keeps the system text of its first turn (Codex has no per-turn system flag); a switch or a new thread picks up the
  current text. Claude reads it every turn.
- The receipt is not stamped on the team panel's task list and the fake backend's org chat fixture has no receipt; the card itself and its
  tests carry it. The `stopped` direct turn, Retry on a direct error line and the provider-switch note (the chat-comfort package's item in
  `chat_v2._answer`) are not touched here: `_answer` itself is unchanged, and the grounding call sits in the route before the turn starts,
  so the two edits do not overlap.
- No J2 file, prompt, route or golden was changed.
