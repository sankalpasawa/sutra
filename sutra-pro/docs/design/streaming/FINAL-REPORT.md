# Streaming chat: final report

Branch `feat/sutra-pro-streaming` (cut from `origin/main`), 44 commits ahead (`git log origin/main..HEAD`), 105 files changed, about 13,000 lines added and 221 removed. Nothing is pushed, tagged or released. The design is in `analysis.md` and `architecture.md` beside this file; real-capture facts are in `capture-notes.md`; decisions are D201 to D238 in `docs/DECISIONS.md` (mirrored in `docs/diagram/decisions.json`).

The goal: the direct chat feels instant, fluid, informative and real. That means provider streaming end to end with no simulated chunking, activity lines that say only what the wire said, a Stop that really cancels the process, and no regression for departments, connectors, AI workers, J2 runs, non-streaming providers or old chats.

## A. Repository analysis

Full text in `analysis.md`. The short version:

- **The pipe was already genuine.** Claude CLI stdout to `ConnectorEvent(text_delta)`, the generator chain, the SSE frame (no-cache, no buffering, no gzip) and the browser's append-only paint were all incremental. The fix was not "make it stream".
- **Why it felt one-shot (ranked):**
  1. The relay kept only text deltas; tool, thinking and liveness signals were dropped.
  2. Codex has no incremental text and a nameless tool trail.
  3. The server joined text in 60-character chunks with no timer, so a short reply never streamed.
  4. Claude `content_block_start` and tool names were ignored at the parser.
  5. The client state was `{active, text}` and claimed "writing" before the server had accepted the turn.
  6. Display continuity was fragile: head truncation at 4,000 characters, and a stream row outside the transcript scroller.
  7. Nothing in flight was stored, so a refresh, second tab or crash lost the turn.
- **Stop was not truthful.** There was no single owner of cancellation for a turn, and the retry back-off could not be interrupted.
- **Reusable parts kept:** `ChatPort`, `Router`, `base._spawn`, `tool_kinds`, the event bus, `Fluid`, `ChatScroll`, `ChatComposer`, the stored `chat_messages` table. The vendored J2 engine is untouched (`git diff origin/main..HEAD -- sutra_app/engine` is empty).

## B. Architecture changes

Backend (STR-1 to STR-7):

- **One Stop owner.** A per-turn `CancelToken` goes from the route through `ChatPort`, `Router` and `base._spawn` to the process, and the back-off waits on it. The route answers Stop at once and cancels the process in the background (D225, D226).
- **Attempts and idempotency.** Retries get `.N` refs; a reply carries `client_id`, `attempt`, `superseded`, `ordered`. A repeated `client_id` returns `{duplicate: true}`. Superseded replies stay out of the model's history (D219, D220).
- **Typed blocks.** A single `BlockAccumulator` turns provider events (text, thinking, tool call, tool result) into blocks. A tool line's title is set at the `tool_call` event, because real Claude sends the complete `assistant` message before `content_block_stop` (D223). Route events `route.plan / attempt / failed` say which provider tries what. The live kinds are opt-in (`acc=`, `routes=True`), so older callers see the same events as before (D224).
- **`LiveTurn`.** Sequence numbers, accumulator and publish under one lock; a coalescer (33 ms, the first piece of a block never delayed); a 5 s heartbeat; a snapshot; a checkpoint store (migration v5) so a crash keeps what was written; the `chat.live` control event (D222, D224, D237).
- **Hold-back redactor.** `live_redact.py` holds back only a tail that could still grow into a secret (D216).
- **Routes behind `SUTRA_LIVE_V1`:** idempotent send, instant Stop, snapshot, retry, ordered store with an "earlier try" note, checkpoint recovery. With the flag off, payloads are unchanged.
- **Event white space (D232).** `Event` stripped whitespace from every string in `data`, so a piece like `"the "` arrived as `"the"`. Fixed in `orchestrator/models.py`.
- **Stored `via` (D236).** A reply stores `{provider, model}` beside its meta, exposed as additive `ChatMessageOut.via`.

Frontend (STR-8 to STR-14):

- **Four client layers (D227):** `chat_live_events.js` (intake: validate, dedupe, gaps, snapshot catch-up), `chat_live_store.js` (pure state machine), `chat_live_client.js` (snapshot, reconnect, polling, timer), `chat_live_view.js` / `chat_live_activity.js` (drawing). The page keeps its own EventSource handle, so the browser frames the bytes; there is no byte-level SSE parser of ours.
- **Live composer only when asked (D228):** `ChatComposer.create({live:true})`; the older 43 composer tests pass unmodified.
- **One reply node (D229):** key `turn:<id>:<try>`, painted from a live or a stored model by the same code; historical messages go through the same model.
- **Append-only text (D230):** `Fluid.paintText`; each code fence is one `<pre>` that survives settle and is highlighted once, on settle.
- **Honest activity (D231):** only what the wire said; no invented tool calls or percentages.
- **Stop and Retry in the reply (D233),** motion and scroll rules (D234), default on with `SUTRA_LIVE_V1=0` as the way back (D235), terminal frame, Stop, mode and width rules (D238).
- **Not changed:** the AI-worker chat keeps its own `AgentChats` row and is not read through the adapter; `fromPartial` serves only the direct chat's flag-off path (D235 narrows D221).

## C. Implementation summary

New = A, modified = M. Source files only; tests are listed after the table. Line counts are in `git diff --stat origin/main..HEAD`.

| File (under `sutra-pro/`) | | What |
|---|---|---|
| `sutra_app/connectors/cancel.py` | new | `CancelToken` |
| `sutra_app/connectors/chat_blocks.py` | new | `BlockAccumulator`, block kinds |
| `sutra_app/connectors/base.py`, `process.py` | mod | token bound to the process group right after tracking; back-off waits on the token |
| `sutra_app/connectors/claude.py`, `codex.py` | mod | block-start, tool and thinking events (Claude); command and item events (Codex) |
| `sutra_app/connectors/chat_port.py`, `router.py`, `chat_models.py`, `models.py`, `errors.py` | mod | live stream, route events, token, block models, `not_retryable` |
| `sutra_app/connectors/tool_kinds.py` | mod | `describe(folder)` |
| `sutra_app/orchestrator/live_turn.py` | new | `LiveTurn` |
| `sutra_app/orchestrator/live_checkpoint.py` | new | checkpoint store |
| `sutra_app/orchestrator/live_redact.py` | new | hold-back redactor |
| `sutra_app/orchestrator/api/chat_v2.py`, `chat_v2.py`, `chats.py`, `direct_running.py`, `direct_turns.py` | mod | idempotent send, Stop, snapshot, retry, ordered store, recovery, attempt refs |
| `sutra_app/orchestrator/events.py`, `models.py`, `records.py`, `errors.py`, `schema.py` | mod | `chat.live` type, whitespace fix, `via`, migration v5 |
| `sutra_app/config.py` | mod | `live_v1`, `live_heartbeat_s`, `live_coalesce_ms`, `live_checkpoint_s` |
| `sutra_app/ui/static/js/chat_live_events.js`, `chat_live_store.js`, `chat_live_client.js`, `chat_live_view.js`, `chat_live_activity.js` | new | client layers |
| `sutra_app/ui/static/js/chat_composer.js`, `chat_draft.js`, `chat_view.js`, `chat_scroll.js`, `fluid.js`, `sutra_events.js`, `home.js`, `node_panel.js`, `dept_ext.js` | mod | live composer, one reply node, `paintText`, scroll anchoring, `chat.live` type, wiring |
| `sutra_app/ui/pages/home.html`, `ui/static/css/sutra-panel.css` | mod | script tags; motion tokens, pill, 901 to 1150 px height rule (not in the frozen `j2-shell.css`) |
| `scripts/capture_connector_fixtures.py` | mod | `--stream` capture with scrub and audit |
| `docs/design/streaming/{analysis,architecture,capture-notes}.md`, `screens/*.png` | new | design, capture notes, 13 screenshots |
| `docs/DECISIONS.md`, `docs/diagram/decisions.json`, `docs/ENVIRONMENT.md`, `docs/TROUBLESHOOTING.md`, `docs/design/ui.md` | mod | D201 to D238, env vars, `not_retryable`, UI notes |

Tests: 26 new files and 15 modified under `tests/`. New: connector and orchestrator tests (`test_cancel_token`, `test_direct_attempts`, `test_live_redact`, `test_capture_stream`, `test_stream_fixtures`, `test_chat_blocks`, `test_chat_live_port`, `test_live_turn`, `test_api_live_chat`, `test_live_chat_real_router`, `test_event_whitespace`), fixtures (`claude/stream_partials_tool_ok.jsonl`, `codex/exec_tool_items_ok.jsonl`, `timing/stream_timing.json`), JS tests (`chat_live_events`, `chat_live_store`, `chat_live_client`, `chat_composer_live`, `fluid_text`, `chat_live_view`, `chat_view_shell`, additions to `chat_scroll`, `helpers/fake_dom.js`) and `tests/e2e/test_browser_live_chat.py`, `stream_fixtures.py`, `test_real_provider_live_chat.py`.

Existing tests changed because the change was inherent: `test_tool_kinds` (asks the accumulator, not private `_map`), `test_schema` and `test_events_bus` (new table, control type), `test_records` (new code), `test_fakes` (two fake scenarios), `events.test.js` (17 to 18 type names), `test_browser_chat_composer.py` (the reply node replaces the old "is writing" row), `tests/orchestrator/conftest.py` (sets `live_v1=False` so legacy-path tests still exercise the legacy path), `test_env_process.py` (SIGINT test made load-proof).

## D. UX improvements

- A visible state appears at Send, before the first token, and says only what is known (accepted, which provider, waiting).
- Text appears as the provider sends it (33 ms joining at most), including very short replies and text before a tool call. Codex streams its commands, not its answer, because it never chunks the answer (a real-capture finding); the page does not pretend otherwise.
- Tool lines and thinking appear in a timeline from the wire, with the real target (folder-aware). A tool running at Stop reads "Interrupted".
- The reply is one node: no card swap at settle, no layout jump (browser-tested), code blocks keep their node and height, highlight once on settle.
- Stop and Retry sit in the reply; Stop answers at once ("Stopping") and the process is really gone shortly after. Retry warns first if the try may have changed files; a replaced try collapses under "Earlier try".
- "Still working" copy states the real idle limit; a heartbeat distinguishes quiet from dead.
- Survives reload, second tab, network drop and a lost terminal event (snapshot catch-up, reconnect, polling fallback); a crash keeps the checkpointed text.
- The reader's place is kept when scrolled up (a "Reply in progress" pill returns them); motion tokens drop to 0 under reduced motion.
- Header shows "via Claude <model>" live, settled and after reload. Ask directly / Plan with Sutra is remembered per chat. Phone width: 40 px targets. The chat column reaches the bottom of the window at 901 to 1150 px.
- Measured once on one macOS run with the real CLIs: first output about 3.4 s (Claude) and 4.8 s (Codex), dominated by the CLI start; Stop to end of stream about 0.85 s (Claude) and 0.35 s (Codex). These are one sample, not a budget.

## E. Test results

Only what was executed. Counts as printed by the runs.

Re-run by the engineering lead on the final head (before this report was committed):

| Check | Result |
|---|---|
| `scripts/gate.sh`, first run | 11,516 passed, 364 skipped, 1 failed: `tests/engine/test_engine_patches.py::test_p14_a_single_output_returns_before_the_planner_call` (an unexpected review request reached the test's captured port). `gate.sh` stopped there. |
| That file solo, 3 runs | 13 passed each time |
| `scripts/gate.sh`, second run, same head | 11,517 passed, 364 skipped, 0 failed, 12 min 50 s, `gate: ok` |
| `node --test tests/ui/js/*.test.js` | 1,414 tests, 1,412 pass, 2 skipped, 0 fail |
| `scripts/ownership-audit.sh` | 0 hits under `sutra-pro/`; fails repo-wide on 12 hits in `marketplace/plugin/sutra-ui` (not touched here) |
| `git diff origin/main..HEAD -- sutra_app/engine` | empty (vendored J2 untouched) |

The gate has no `tests/js` folder, so its node step does not run; the UI node tests run inside pytest (`tests/ui/test_node_suite.py`) and again directly above. The 364 skips include the browser tests (`SUTRA_BROWSER` unset), the real-CLI tests (`SUTRA_LIVE` unset) and platform-gated tests. The engine test failed once and passed in the next full run and in three solo runs; the engine directory is unchanged by this branch and I did not find the cause or compare it against the base commit, so call it a suspected order- or load-dependent flake, not a proven one.

Earlier runs by the build agents (not repeated by me, so treat as reported): `tests/connectors` 1,863 passed; `tests/orchestrator` plus `tests/contracts` 1,890 passed; all of `tests/ui/js` (node) 1,402 tests, 1,400 pass, 2 skipped; Chrome (headless, CDP) `tests/e2e/test_browser_live_chat.py` all pass (17 tests at STR-13, 20 after the review fixes), plus the older composer, resync and abs-chat browser suites; a combined browser run once gave 1,252 passed, 2 skipped and 1 failed (`test_view_graph.py` sliver pointer test, passed in isolation). After the last review commit only the new and affected browser tests were re-run, not the whole browser file.

Real capture: `scripts/capture_connector_fixtures.py --stream` ran against real `claude` 2.1.308 and `codex-cli` 0.146.0 (4 real model calls: a tool turn and a Stop turn each). `scripts/ownership-audit.sh` reports no hits under `sutra-pro/`; it fails repo-wide on hits in `marketplace/`, which this branch did not touch.

Limitations:
- The browser tests are skipped inside the gate (`SUTRA_BROWSER` unset); they need Chrome and are run separately.
- `tests/e2e/test_real_provider_live_chat.py` is written but has never been run. It needs `SUTRA_LIVE=1 SUTRA_BROWSER=1` and spends plan usage.
- Nothing ran on Windows; nothing is claimed for it.
- The "Still working, no output for N s" copy is covered by node tests only. The real idle-timeout error text is asserted from code; no idle timeout was provoked against a real CLI.
- A Claude `thinking` block and a Codex `item.updated` were never seen in a capture; they are tolerated but not rendered.
- The Stop-mid-tool "Interrupted" check is a JS unit test only, with no browser test.
- Timing tests (the SIGINT test in `test_env_process.py`, and the engine test named below) have shown load-dependent failures; see the gate notes.

## F. Remaining work

- Run the real-provider test with the owner's go-ahead and record the numbers beside the fixture timing.
- Provoke a real idle timeout and a real `thinking` block; add fixtures and render thinking text if wanted.
- Add the browser test that stops mid-tool and asserts "Interrupted".
- Windows: process-group cancel, path handling and the browser tests.
- Codex: answer text is not chunked by the CLI; revisit if a streaming mode appears.
- Move the AI-worker chat onto the live adapter (deliberately left out, D235).
- Decide the retention of `chat_live` checkpoint rows and the extra `via` and earlier-tries note stored on each fallback reply.
- Find the cause of the load-dependent engine test failure (below) before the branch is the merge gate.
- Push, PR and release are the owner's step.

## G. Developer handoff

Run it (checkout, from `sutra-pro/`): `scripts/run.sh` (checks setup, starts the server, opens the browser; `--port 9000 --no-browser` to vary). Python is always `scripts/py`.

Environment variables (full table in `docs/ENVIRONMENT.md`):

| Variable | Default | Meaning |
|---|---|---|
| `SUTRA_LIVE_V1` | `1` | `0` goes back to the older `chat.partial` path; nothing stored changes |
| `SUTRA_LIVE_HEARTBEAT_S` | `5` | seconds of provider silence before the turn says it is alive (0.2 to 60) |
| `SUTRA_LIVE_COALESCE_MS` | `33` | longest a text piece waits to be joined (0 to 1000; first piece of a block never waits) |
| `SUTRA_LIVE_CHECKPOINT_S` | `1.5` | how often a streaming turn is saved (0.05 to 60) |
| `SUTRA_LIVE` | `0` | `1` allows tests that call the real CLIs |
| `SUTRA_BROWSER` | unset | `1` runs the Chrome tests under `tests/e2e` |
| `SUTRA_SHOTS` | unset | `1` rewrites `docs/design/streaming/screens/` |

Local streaming test, no model and no plan usage (fake CLI replaying the captured stream, real Chrome, real app, router, connector and process group):

```
SUTRA_BROWSER=1 scripts/py -m pytest tests/e2e/test_browser_live_chat.py -q
scripts/py -m pytest tests/orchestrator/test_live_chat_real_router.py tests/orchestrator/test_api_live_chat.py -q
node tests/ui/js/chat_live_store.test.js          # any file under tests/ui/js runs alone with node
```

Turn builder for new scenarios: `tests/e2e/stream_fixtures.py` (`Text`, `Think`, `Tool`, `Fail`, `write_turn`); the shared fake CLI is `tests/fakes/fake_cli.py`.

Real-provider test (owner's go-ahead first; it makes two short calls on the signed-in `claude`):

```
SUTRA_LIVE=1 SUTRA_BROWSER=1 scripts/py -m pytest tests/e2e/test_real_provider_live_chat.py -q -s
```

It prints time to the first visible state, first word, and Stop to process gone. To refresh the fixtures: `scripts/py scripts/capture_connector_fixtures.py --stream` (real model calls; it scrubs, audits and refuses to write a file on a hit; notes in `capture-notes.md`).

Debugging:
- Flag the problem first: `SUTRA_LIVE_V1=0` tells you whether it is the live path.
- Page: `GET` the snapshot route for the turn to see the server's view; the page compares `seq` and offsets (in code points) and re-reads the snapshot on a hole, a duplicate-with-gap or an offset mismatch. A page that re-reads at every piece points at lost white space (D232).
- Stop: the route answers at once; the process is cancelled in the background through the `CancelToken` (SIGINT, then SIGTERM, then SIGKILL on the group). If a process outlives Stop, look at `connectors/cancel.py` and `process.py`, and at `tests/orchestrator/test_live_chat_real_router.py`.
- A reply that stored fewer words than were shown: check the checkpoint row and `recover_interrupted`; the stored ending (Stopped note or error beside the reply) decides how a reload reads it (D236).
- A failed turn with no card is by design (D236); the error line is the ending.
- Error codes: `docs/TROUBLESHOOTING.md` (`not_retryable` is new).
- The frozen `j2-shell.css` and `sutra_app/engine/` must stay as pinned; put CSS in `sutra-panel.css`.
