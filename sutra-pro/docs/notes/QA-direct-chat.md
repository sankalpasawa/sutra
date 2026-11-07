# QA direct-chat: eighteen bugs found on 2ae63d11 (one P1, six P2, eleven P3 of which ten are fixed), one part of two skipped

QA drove the direct chat (Home "Ask directly", the node panel's "Ask the model") against a real app, the fake CLIs and a headless Chrome. Each bug below was
reproduced first (the tests below fail on 2ae63d11), then fixed at its cause. No J2 file, prompt, route or golden is touched (`engine/j2*.py`, `engine/llm.py`,
`engine/port.py`, `ui/pages/j2_ui.html`); none of the bugs is in J2's own code.

An end-to-end harness (a real `python -m sutra_app` process, the fake claude, headless Chrome through `tests/ui/cdp.py`) played each P2 scenario on 2ae63d11 and on this
branch. Before: no Stop after a reload and a team message accepted mid-turn; a Stop that stays forever after a SIGKILL and a restart; a double-click that stops its own
turn; a streaming row of 205 characters (one attempt's 103, twice); "The request was refused" and a draft cut to 8000 on reload. After: every one of those is as
the owner would expect (details per bug). The P3 fixes are covered by unit tests (Python and node) that fail on 2ae63d11; they were not replayed in a browser.

| # | Sev | Bug | Result |
|---|-----|-----|--------|
| 1 | P1 | every Sutra instance shares one provider-session folder | fixed |
| 2 | P2 | Enter that confirms an IME candidate sends the line | fixed |
| 3 | P2 | after a reload or in a second tab a running turn is invisible, cannot be stopped | fixed |
| 4 | P2 | server crash mid-turn: page stuck on Stop, dangling owner line | fixed, the orphaned CLI child skipped |
| 5 | P2 | a turn that fails after several attempts glues the attempts' texts | fixed |
| 6 | P2 | a double-click on Send sends and stops | fixed |
| 7 | P2 | a message over 8000 characters is refused with "The request was refused" | fixed |
| 8 | P3 | the pill keeps "can be chosen after your next message" after the turn that switched | fixed |
| 9 | P3 | the switch note counts the new message as "carried" | fixed |
| 10 | P3 | archive then unarchive leaves one more empty "Earlier chat" each time | fixed |
| 11 | P3 | a second tab keeps an archived chat live; the refusal says nothing of why | refusal worded, the live follow skipped |
| 12 | P3 | the model sees attachments under their content-hash names; the PDF refusal quotes the hash | fixed |
| 13 | P3 | text attachments cut at 40,000 characters and only the model is told; the file text can close its fence | fence fixed, the limit told on the box, the per-message notice skipped |
| 14 | P3 | non-ASCII file names are flattened to underscores | fixed |
| 15 | P3 | "reply was cut off (partial text in detail)" is jargon | fixed |
| 16 | P3 | a CLI that cannot start is reported as "does not accept a needed flag" | fixed |
| 17 | P3 | offline demo: "Ask directly" offered but disabled with advice that cannot work | wording fixed, the toggle stays |
| 18 | P3 | a failed send leaves "The app is not responding." after the app is back | fixed |
| 19 | P3 | the first line of a pasted message loses its leading indentation | skipped (see below) |

## 1. A data folder owns its provider sessions (P1)
- **Cause.** `ConnectorConfig.resolved_work_root()` defaulted to `<tempdir>/sutra-app-<uid>/work` for every data folder of the machine, and nothing passed `work_root`.
  Session ids repeat (`cs_org` is the org chat of all of them), so a fresh folder resumed another instance's `session.json` (with a real Claude: another folder's
  conversation), two instances overwrote each other's `session.json` and `system.txt`, and a first turn could read "Switched stub to Claude".
- **Fix.** `connectors/workroot.py`: the default root is `<tempdir>/sutra-app-<uid>/work-<key>`, `key` = first 16 hex of sha256(realpath of the data folder + a random id kept
  in `<data>/connectors/work-id`, mode 0600, made when the folder exists and has none or a damaged one). The path separates two folders; the id separates a folder deleted and
  made again at the same path (the owner who deletes their data to start again no longer resumes the old provider session) and a copy. The root stays under the OS temp
  root, outside any checkout (CD9: a data folder inside a repo must not make the CLIs read its CLAUDE.md). A folder that cannot be written to is keyed by its path alone.
- **Chosen over** a root inside the data folder: the default data folder in a checkout is `<project>/data`, which is inside the repo CD9 keeps the work dirs out of.
  Chosen over validating `session.json` against the app's row: the file is authoritative by design (S1-contracts-08), and validation could not stop two instances writing
  each other's `system.txt`.
- **One-time cost.** The first turn of each existing chat after this change starts a new provider session with the carry-over of the app's transcript (the provider session is
  a cache of it); the old `work` folder under the temp root is left to the OS.
- **Files.** `connectors/workroot.py` (new), `connectors/models.py` (`resolved_work_root`, two unused imports), `docs/design/connectors.md`.
- **Tests.** `tests/connectors/test_work_root_isolation.py` (7: a fresh folder does not `--resume` another's session, system text and session file are separate, delete and
  recreate at the same path, same folder same root across restarts, under the temp root and outside the data folder, explicit root unchanged and no data folder made, id
  file private and repaired); `tests/connectors/test_models.py` (the old default-root test now asserts `work-<16 hex>` per folder).

## 2. Enter that confirms an IME candidate sent the half-written line (P2)
- **Cause.** `home.js` sent on `Enter && !Shift`; the panel also checked `isComposing`.
- **Fix.** One shared `ChatComposer.sendKey(e)`: Enter, no Shift, no `isComposing`, and `keyCode !== 229` (Safari ends the composition first and reports 229 on that Enter).
  Home and the panel both use it.
- **Files.** `ui/static/js/chat_composer.js`, `home.js`, `node_panel.js`.
- **Tests.** `chat_composer.test.js` (sendKey); `tests/ui/test_home.py::test_enter_that_confirms_an_ime_candidate_sends_nothing_until_the_second_enter` (browser, a real
  `Input.imeSetComposition`; fails on the old handler: one POST).

## 3. After a reload or in a second tab a running direct turn was invisible and could not be stopped (P2)
- **Cause.** The turn lived only in the memory of the page that started it; the server's `_running` set was private to the route and not in `GET /api/chats/{sid}`
  (phase `ready`), and the team route did not look at it.
- **Fix.** `orchestrator/direct_running.py` is the one registry (`api.chat_v2._running` is its set, so old callers and tests see the same object, plus the owner's line the turn
  answers). `GET /api/chats` and `/api/chats/{sid}` carry `direct_turn` (int or null). `POST /api/chats/{sid}/messages` is 409 `busy` ("This chat is already answering") while
  a direct turn answers. `ChatComposer.resync()` reads the session: a turn the page does not know is shown in direct mode with the streaming row and Stop (not when its reply is
  already stored). Home calls it after every full load (so after a resync event too), the panel when a chat's composer is made and on resync.
- **Files.** `orchestrator/direct_running.py` (new), `orchestrator/models.py` (`ChatSessionOut.direct_turn`), `orchestrator/chats.py`, `orchestrator/api/chat_v2.py`,
  `orchestrator/api/agent.py`, `chat_composer.js`, `home.js`, `node_panel.js`, `docs/design/orchestrator.md`.
- **Tests.** `test_api_chat_v2.py` (the session names the running turn and drops it; a real route with a waiting port; the old set is the same set), `test_api_agent.py`
  (team route 409 for the org chat and for a team chat, open again after), `test_api_chat_read.py` (the new key), `chat_composer.test.js` (resync: adoption, no adoption when the
  reply is stored, quiet cases, a second tab, a newer turn replacing an ended one).

## 4. Server crash mid-turn: the page stayed on Stop and the lost turn left no marker (P2, one part open)
- **Cause.** Page: `stop()` on `stopped:false` only cleared "stopping", so the turn never ended; nothing re-read the server after a restart. Server: nothing looked for owner
  lines whose turn the dead process never finished.
- **Fix.** Page: `resync()` also ends a turn the server no longer runs, judged by the id the page had BEFORE the read (a POST still in flight, or a turn that began while the read
  travelled, is never ended by an older answer); `stop()` that finds nothing running calls it, so Stop is not a button that does nothing. Server: the owner's line of a direct turn
  carries `src_ref = direct-ask:<random>`; `start_services` calls `chat_v2.recover_interrupted`, which gives every such line without an ending (`direct:<id>` is the first message
  of every ending) the error line "Interrupted: the app closed before the model answered." (the page offers Retry as for any failed direct turn). The team route's lines carry no
  mark and are never touched; a second start adds nothing.
- **Not fixed: the orphaned CLI child after a hard kill.** A child of a SIGKILLed server keeps running until it next writes to its closed pipe (or its own limit). Ending it
  needs a parent-death mechanism that is OS specific (no PDEATHSIG on macOS, a job object on Windows) or a watchdog process per child; neither is small or local. The fake claude
  of the QA harness lived on until its 120 s limit; a real Claude should stop at its next write to the closed pipe, but that was not checked.
- **Files.** `orchestrator/chat_v2.py` (`DIRECT_ASK`, `INTERRUPTED`, `recover_interrupted`), `orchestrator/api/chat_v2.py` (`_store_user_line`), `orchestrator/wiring.py`,
  `chat_composer.js`.
- **Tests.** `tests/orchestrator/test_direct_recovery.py` (6, one is two real starts on one data folder through `TestClient`); `chat_composer.test.js` (a lost turn ends, the
  race guards, Stop on a turn the server does not run).

## 5. A turn that failed after several streamed attempts stored the attempts glued together (P2)
- **Cause.** The router retries a chat turn and every attempt's `text_delta` pieces went into one `shown` buffer.
- **Fix.** `RouterChatPort.stream` treats the second `started` event of a turn as a new attempt: it forgets that attempt's text and blocks and yields a new `restart` event
  (`ChatEvent`, `EVENT_KINDS`). `chat_v2._answer` empties its buffers and, when something was shown, publishes one `chat.partial` with `reset: true` and an empty delta; `ChatPill.partial`
  starts the streaming row again. The stored partial reply of a failed or stopped turn is the last attempt's text only (a fallback to the other provider restarts the same way).
- **Files.** `connectors/chat_models.py`, `connectors/chat_port.py`, `orchestrator/api/chat_v2.py`, `ui/static/js/chat_pill.js`.
- **Tests.** `tests/connectors/test_chat_restart.py` (6: scripted events, the real retry loop with a connector that dies after text, the real Claude connector over the fake CLI
  with three dying attempts); `test_direct_turn_endings.py` (4: the stored text is one attempt, the reset event, no reset when nothing was shown, a Stop after a restart);
  `chat_pill.test.js`, `chat_composer.test.js` (reset).

## 6. A double-click on Send sent the message and stopped it (P2)
- **Cause.** The label turns into "Stop" synchronously under the pointer, so the second click is a Stop.
- **Fix.** `ChatComposer.stopPress(e)` is false for a click whose count (`detail`) is above one; Home's Send/Stop button and the panel's `composer-stop` use it. A single click, a
  keyboard press and Esc still stop. (A timer in the controller would have been testable too, but every existing Stop test would have needed a clock and a deliberate press right
  after Send would have been swallowed at random.)
- **Files.** `chat_composer.js`, `home.js`, `node_panel.js`.
- **Tests.** `chat_composer.test.js` (stopPress). Verified end to end with real `Input.dispatchMouseEvent` clicks 120 ms apart (clickCount 1 then 2): the reply is stored, no stop note.

## 7. A direct message over 8000 characters was refused with "The request was refused" (P2)
- **Cause.** pydantic's `max_length=8000` gave the generic 422; the box had no check and the draft store cut a draft to 8000 on save.
- **Fix.** The route checks the cap itself ("Messages can be up to 8000 characters; this one has 8500.", 422 `validation` with the violation on `text`; characters, not bytes; the model
  now only bounds what the store holds, 200 000). `ChatComposer.send` says the same before anything is sent, counting code points as the server does, and the box keeps its text.
  The draft store keeps 32 000 characters, so a pasted log over the cap survives a reload and Send says why it cannot go.
- **Files.** `orchestrator/api/chat_v2.py`, `chat_composer.js`, `chat_draft.js`.
- **Tests.** `test_api_chat_v2.py` (3), `chat_composer.test.js` (2), `chat_draft.test.js` (1).

## 1b. The working-folder rule and the directory checks still hold with the per-folder root (part of bug 1)
- `connectors/workdir.py` (GAP3-workdir, still on its own branch, not in this tree) takes `cfg.resolved_work_root()` as the root it refuses, so it refuses the root of THIS data
  folder. Checked against that branch's real `check_folder`: the data folder, a folder in it, the work root and a session folder in it are all refused ("belongs to Sutra
  itself"). `test_work_root_isolation.py::test_the_working_folder_rule_still_refuses_...` pins it with `importorskip`: it skips here and runs once the module is merged.
- The modes are unchanged: the work root and every session folder are made `0700` (`base.py`, `chat_port.py`), `session.json` and `system.txt` `0600`, the new `work-id` file
  `0600` with its folder `0700` (asserted on POSIX only).
- **For the merge of GAP3-workdir (not done here, the file is not in this tree).** Because every data folder now has its own `work-<key>` beside the others under
  `<tempdir>/sutra-app-<uid>/`, that rule refuses this folder's root but not a SIBLING root or the shared parent: an owner who types the path of another instance's work folder
  (or `<tempdir>/sutra-app-<uid>`) gets it accepted, and the read-only file tools could then list that instance's `session.json` and `system.txt`. One line in `check_folder`
  closes it: add `os.path.dirname(os.path.realpath(work_root))` to `own`. Before this change the single shared root was refused by the same rule.

## 8. The provider pill kept "can be chosen after your next message" after the turn that switched (P3)
- **Cause.** The pill data was read when the chat was opened or the owner chose; nothing read it again when the turn that moved the chat to the other model ended.
- **Fix.** `ChatComposer.create` takes `onTurnEnd`, called once when a turn that ran is over (its stored reply arrived, or `resync` found the server lost it; not on a refused send).
  Home reads the pill again (keeping what it shows until the answer comes); the panel forgets which chat its pill was read for, so the next paint reads it.
- **Files.** `chat_composer.js`, `home.js`, `node_panel.js`. **Tests.** `chat_composer.test.js` (2).

## 9. The switch note counted the new message as carried (P3)
- **Cause.** `RouterChatPort.stream` computed the plan with `plan_switch` after the turn, when the owner's new line is already stored; the router drops that line from the
  carry-over (it goes as "New message") but the plan counted it: "carried 3 messages" for 2 that went, and "carried 1 message" instead of "nothing to carry".
- **Fix.** The plan is computed from the stored transcript without that line, the same drop as `Router._transcript` (`_carried`, `_plan`; `plan_switch` is as it was).
- **Files.** `connectors/chat_port.py`. **Tests.** `test_chat_port.py` (2: 2 then 4 carried, and only the new line stored gives tier none).
- Noticed, not changed: with attachments the router's drop compares the stored line (`text` + the "(attached: ...)" record) with the sent text (`text` + the files' text), so
  the line is not dropped and a switching turn with files carries it twice (as history and as the new message). Not in the bug list; the plan counts what the router carries.

## 10. Archive then unarchive left an empty archived chat each time (P3)
- **Cause.** Archiving starts an empty replacement chat (I1: every node has one active chat); bringing the old chat back sets the unused replacement aside as `archived`, and
  "Earlier chats" listed every archived chat of the node, all titled the same, 6 of 7 with nothing in them.
- **Fix.** `GraphStore.node` lists the node's own archived chats that have at least one message (chats filed under the node, merged away, are listed as before). The empty
  rows are kept (archive is a mark, never a delete: the FTS title rows, segments and the ledger point at them), so they accumulate harmlessly, one per cycle.
- **Files.** `orchestrator/graph.py`, `docs/design/orchestrator.md`. **Tests.** `test_chat_v2.py` (4 cycles, then one real archive); the older "lists the owner archived chat"
  test posts a message first (an empty chat the owner archives has nothing to show).

## 11. A second tab keeps an archived chat live (P3, half done)
- **Fixed.** The refusal says why: "This chat was archived. Open the team's current chat to write." (`POST /direct` on an archived chat, 403 `read_only`; a chat that is live but
  not for the model keeps "This chat cannot be asked directly"). **Test.** `test_api_chat_v2.py`.
- **Skipped: the tab following the chat by itself.** `chat.archived` is emitted by the server but the page's `SutraEvents` listens to a fixed list of 15 event names (an
  EventSource only delivers names it registered; `events.test.js` pins the 15), so the panel never receives it. Adding the name is a change of the events contract and of the
  panel's reopen logic, not a small guard. The text stays in the box and the owner now reads the cause.

## 12. The model saw attachments under hash names (P3)
- **Cause.** `/direct` built each `AttachmentRef` from the stored file's name (`<sha256>.<ext>`); the owner's names went only to the record line.
- **Fix.** The ref carries the owner's cleaned name (`names` in order, as `attached_line` reads them), else `attachment-<n><ext>`; the model's prompt reads "[Attached file: note.txt; ...]".
  The PDF refusal for Codex reads "codex cannot take a PDF: paper.pdf. Choose Claude for this chat to send it."
- **Files.** `orchestrator/api/chat_v2.py`, `connectors/attachments.py`. **Tests.** `test_direct_turn_endings.py` (names and the plain fallback), `test_attachments.py` (the refusal).

## 13. Text attachments: the fence, and the cut (P3, half done)
- **Fixed: the fence.** The file text sat in a fixed three-backtick fence, so a line of ``` in the file ended the data block and what followed read as instructions. The fence is now
  one backtick longer than the longest run in the file (at least three). **Fixed: the owner is told the limit** on the box: "...The model reads the first 40,000 characters of a text
  file." (`chat_search.js` `limitsNote`; a test pins the number to `INLINE_CHARS`).
- **Skipped: a notice per message** that "only the first 40,000 of 105,000 characters were sent". The cut is made at delivery, after the owner's line is stored, and the line's
  record has no field for it; the model is still told (`[cut: ...]`). The limit on the box is the part that was cheap and safe.
- **Files.** `connectors/attachments.py`, `chat_search.js`. **Tests.** `test_attachments.py` (hostile fence, ordinary fence, a run of nine), `chat_search.test.js`.

## 14. Non-ASCII file names were flattened (P3)
- **Cause.** Two copies of the rule `[^A-Za-z0-9 ._()-]` -> `_` (`direct_turns.clean_name`, `attachments._clean_name`).
- **Fix.** One rule, `connectors/attachments.clean_name`: letters, digits and combining accents of any script and emoji are kept; control, bidi, zero-width and other format
  characters, brackets, quotes and separators are still `_`; 80 characters. `direct_turns.clean_name` calls it. 'weird 日本語 😀.txt' and 'résumé.pdf' stay readable.
- **Files.** `connectors/attachments.py`, `orchestrator/direct_turns.py`. **Tests.** `test_attachments.py` (names, a stored file), `test_direct_turn_endings.py` (the record line).

## 15. "reply was cut off (partial text in detail)" (P3)
- **Fix.** `ReplyTruncatedError.user_message` is "The reply was cut off because it reached the model's length limit."; the direct chat adds "Ask for a shorter answer, or say
  \"continue\"." (the connector's sentence is also used by structured calls, where that advice would not fit). The streamed part was already kept as the reply.
- **Files.** `connectors/errors.py`, `orchestrator/api/chat_v2.py`, `docs/design/connectors.md`. **Tests.** `test_errors.py` (table), `test_direct_turn_endings.py`.

## 16. A CLI that cannot start was reported as "does not accept a needed flag" (P3)
- **Cause.** `probe_flags` read the output of `--help`; a help that never ran (exit 127, "fatal: cannot start") lists nothing, so every required flag counted as missing and the
  provider went into the `flag` cooldown. The pill and the box then said "does not accept a needed flag" and "Sign in...".
- **Fix.** `ModelConnector._help_flags` (both connectors use it): no flag listed and a non-zero exit raises a `ProviderError` with the CLI's words ("claude --help gave no usable
  answer (exit 127): ..."); `_probe_flags` already treats a `ConnectorError` as "not probed" and degrades nothing. A help that ran and lacks a flag still degrades.
  With a CLI that cannot start the providers now read as ready; the first send runs it and the error line carries the real failure.
- **Files.** `connectors/base.py`, `claude.py`, `codex.py`. **Tests.** `test_factory.py` (2).

## 17. Offline demo: "Ask directly" offered with advice that cannot work (P3, wording)
- **Fix.** `ChatComposer.askBlock([])` (the server listed no provider at all: the offline demo) says "This is the offline demo: there is no Claude or Codex to ask directly. Plan with
  Sutra (or tell the team) works here." A list of providers none of which is ready keeps the sign-in sentence; unreadable data keeps it too.
- **Not done.** Hiding the toggle, or offering the stub as a pill choice: the stub is not a choosable provider (`PROVIDERS`, `Literal['claude','codex']` in the choice contract), and
  the demo's documented limits are the owner's decision. **Files.** `chat_composer.js`. **Tests.** `chat_composer.test.js`.

## 18. "The app is not responding." stayed after the app was back (P3)
- **Fix.** The composer remembers the note a transport failure put up (`ApiError.code === "network"`); when the page reads the session again successfully (`resync`, which both pages call
  after a reconnect) and the box still shows exactly that note, it is cleared. A refusal of any other kind (busy, too long) stays until the owner acts.
- **Files.** `chat_composer.js`. **Tests.** `chat_composer.test.js` (2).

## 19. The first line of a pasted message loses its leading indentation (P3, skipped)
- **Why skipped.** Three layers trim: the composer (`.trim()`), `DirectIn` (the library `Value` base strips every string) and the stored `ChatMessage` (also a `Value`: every message text
  of the app is stripped on its way into the store). Keeping the indentation in the route and the box alone would make the sent text differ from the stored line, and the router drops
  the owner's new line from a carry-over by comparing the two, so a switching turn would carry the line twice. Making `ChatMessage.text` unstripped changes the stored text of every
  message of the app (replies, cards, team messages) and is a library rule, not a one-line guard. Later lines already keep their spaces; only the first line's are lost.

## Left alone, noticed on the way
- The staged team route (`POST /api/chats/{sid}/messages`, `ChatPost`, same 8000 cap) still answers a too-long message with the generic "The request was refused"; the bug is about
  the direct route and the two have separate models and a fake backend that pins the team route's words.
- `team_find.js` runs a search on any Enter, also the one that confirms an IME candidate (same class as bug 2; not a composer).
- The Home browser tests (`SUTRA_BROWSER=1`) fail or error in 59 places on 2ae63d11 already (the fake backend has no `/api/notes` route); the set is the same on this branch.
- Noticed, not changed: `scripts/py` forces `TMPDIR=/tmp`, so every instance started through it keeps its work folder as `/tmp/sutra-app-<uid>/work-<key>` (a different folder per data
  folder now); the old shared `/tmp/sutra-app-<uid>/work` is orphaned and may be deleted by hand.

## Verified end to end (a real app, the fake claude, private ports and data folders)
Two instances started through `scripts/py` (the `TMPDIR=/tmp` of the bug) on two empty data folders: the second one's first `claude` call has no `--resume` and its chat holds only its own
turn (on 2ae63d11 it resumed the first one's session). An attachment named 'weird 日本語 😀.txt' is recorded as such, reaches the model as "[Attached file: weird 日本語 😀.txt; ...]" (no hash
anywhere in the prompt), and a file that holds ``` lines is delivered inside a four-backtick fence. A 8500-character message is refused with "Messages can be up to 8000 characters; this one has 8500."

## Tests run on this branch (final)
- `node --test tests/ui/js/*.test.js`: 984 tests, 982 pass, 0 fail, 2 skipped.
- `scripts/py -m pytest tests/connectors tests/orchestrator tests/ui tests/test_docs.py tests/test_traceability.py tests/test_ownership.py tests/test_layout.py` (without
  `test_env_process.py`): 3673 passed, 219 skipped (the browser, slow and live markers), 0 failed.
- `tests/connectors/test_env_process.py` on its own, in the foreground: 67 passed. `tests/library` on its own: 2347 passed, 4 skipped (the known registry test did not fail in this run).
  `tests/integration`: 23 passed.
