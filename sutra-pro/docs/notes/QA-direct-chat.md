# QA direct-chat: seven bugs found on 2ae63d11, all fixed, one part left open

QA drove the direct chat (Home "Ask directly", the node panel's "Ask the model") against a real app, the fake CLIs and a headless Chrome. Each bug below was
reproduced first (the unit tests below fail on 2ae63d11), then fixed at its cause. No J2 file, prompt, route or golden is touched (`engine/j2*.py`, `engine/llm.py`,
`engine/port.py`, `ui/pages/j2_ui.html`); none of the bugs is in J2's own code.

An end-to-end harness (a real `python -m sutra_app` process, the fake claude, headless Chrome through `tests/ui/cdp.py`) played each scenario on 2ae63d11 and on this
branch. Before: no Stop after a reload and a team message accepted mid-turn; a Stop that stays forever after a SIGKILL and a restart; a double-click that stops its own
turn; a streaming row of 205 characters (one attempt's 103, twice); "The request was refused" and a draft cut to 8000 on reload. After: every one of those is as
the owner would expect (details per bug).

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

## Left alone, noticed on the way
- The staged team route (`POST /api/chats/{sid}/messages`, `ChatPost`, same 8000 cap) still answers a too-long message with the generic "The request was refused"; the bug is about
  the direct route and the two have separate models and a fake backend that pins the team route's words.
- `team_find.js` runs a search on any Enter, also the one that confirms an IME candidate (same class as bug 2; not a composer).
- The Home browser tests (`SUTRA_BROWSER=1`) fail or error in 59 places on 2ae63d11 already (the fake backend has no `/api/notes` route); the set is the same on this branch.
