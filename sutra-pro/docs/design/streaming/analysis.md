# Streaming chat: analysis of the current system

Status: analysis only, no code changed. Paths are relative to `sutra-pro/sutra_app` unless noted.
Source: five layer reports (provider, backend, transport, state/rendering, tools/persistence), merged and spot-checked against the code.

Evidence labels used below:

- **Fact**: read in code, and for the items listed under "Verified in this merge", re-read by the lead.
- **Hypothesis (H)**: reasoned from code, not run. Nothing in this document is runtime-measured. No real CLI or browser was driven, so timings are unmeasured. The layer reports ran 177 node unit tests (all passed) and 121 Python tests (all passed); those pin current behaviour, not live behaviour.

Verified in this merge (re-read in code): `PARTIAL_EVERY_CHARS = 60` and the three-branch `_answer` loop (`orchestrator/api/chat_v2.py:57,319-328`); Codex `partials=False` and `stream()` forcing it (`connectors/codex.py:392,488-495`); Codex handles only `_on_item_completed` (no `item.started`); `ClaudeParser._on_stream_event` consumes only `content_block_delta` with `text_delta` and `input_json_delta` (`connectors/claude.py:167-181`); `ChatPort.stream` swallows `started` (`connectors/chat_port.py:234`); `ChatMessageOut.blocks` capped at 500 (`orchestrator/models.py:409`); `MAX_SHOWN = 4000` (`ui/static/js/chat_pill.js:37`); cancel ladder SIGINT 5 s, SIGTERM 5 s, SIGKILL 2 s, with SIGINT skipped on Windows (`connectors/process.py:47-50`); stored text is `result.result` (`connectors/claude.py:241`).

## 1. Architecture overview

There is no streaming HTTP response for a chat reply. "Direct streamed chat" is two pieces:

1. `POST /api/chats/{sid}/direct` returns 202 `{message_id, turn:"started"}` after the owner's line is stored and grounding (`system.txt`) is written. The turn runs on a worker thread (`run_blocking(_answer, ...)`).
2. Reply pieces travel as `chat.partial` control events on the single global SSE stream `GET /api/events` (FastAPI `EventSourceResponse`; browser `EventSource` in `ui/static/js/sutra_events.js`). Pieces are never stored, never replayed, have seq 0 and no offset. Every page receives every chat's pieces and filters by `session_id` in JS.

```
Browser                               Server (FastAPI, one process)                      Provider CLI
-------                               -----------------------------                      ------------
chat_composer.ask()
  turn.active=true (text "")  ---POST /direct--> chat_v2.direct: store owner line,
                                                 _ground, direct_running.begin, 202
                              <--202 {message_id}
                                                 worker thread: _answer
                                                   RouterChatPort.stream (chat_port.py)
                                                     Router.chat_stream -> _chat -> _drive -> _chat_turn
                                                       connector.stream(partials=True)
                                                         base._turn/_spawn: ONE CLI PER TURN ----> claude -p stream-json
                                                         process._pump_out (bufsize=0) <------------ stdout lines
                                                         parser.feed(line) -> ConnectorEvent
                                                     ChatPort._map -> ChatEvent
                                                       partial | block | restart | usage | switched | turn_done
                                                   _answer keeps ONLY partial/restart/turn_done
                                                     coalesce to >=60 chars, redact, bus.publish_one(chat.partial)
sutra_events.js <---SSE chat.partial {session_id,message_id,delta,reset?}---
home.js / node_panel.js onEvent -> composer.partial -> ChatPill.partial (append, cap 4000)
  onChange wrapped in Fluid.frame -> paintStreamRow -> Fluid.paintStream (settled blocks kept, tail redrawn)
                                                   turn_done: _post_all(finished(...)) ONE stored message + blocks
                              <---SSE chat.message---- ; client refetches (150 ms coalesce), reconcile() ends turn
Stop: POST /direct/stop -> Router.chat_stop -> connector.stop -> process cancel ladder -> CallCancelledError -> stopped()
```

Other live paths, all separate from the direct route:

- **AI workers in J2 runs and agent chats.** The vendored engine's `AgentLiveCapability` rewrites `<run>/agent_live.json` at most 4 times a second (last 4000 chars, last tool title only). `RunWatcher._live_tick` (`orchestrator/runs.py`, 400 ms poll) publishes `chat.partial` with `reset:true`, the whole text so far, a `tool` string and `message_id` 0. The client repaints the whole row as escaped plain text (`agent_chats.js livePartial/liveRow`). This is a polled snapshot, not provider streaming.
- **Engine seam.** `connectors/engine_port.py` calls `Router.complete`; `router._progress` converts events into J2 cumulative snapshots `{"chars","text"}` plus `{"tool": title}`. JSON/schema calls are never partial. This contract is vendored and must not change.
- **Org chat staged path** (`POST /api/chats/cs_org/messages`, `agent/runner.py`) and `agent_ask.py` are one-shot structured calls. Their `chat.turn` phase events come from real code stages and are honest, but are not model streaming.
- **Stub provider and `ScriptedPort`** emit delay-based chunks. That is simulated chunking, for offline demos and tests only. It proves nothing about real streaming.

### Where the stream is genuine and where it is not

| Segment | Verdict |
|---|---|
| Claude CLI stdout to `ConnectorEvent(text_delta)` (`--include-partial-messages`, `bufsize=0`, line queue) | Genuine, incremental, no buffering until the end |
| Generator chain `_spawn` to `ChatPort.stream` to `_answer` | Genuine, no buffering |
| `_answer` 60-char coalescing | Quantised, no timer; short or pre-tool text withheld |
| Bus to SSE frame (no-cache, `X-Accel-Buffering: no`, pure-ASGI middleware, no gzip) | Genuine |
| Browser: `ChatPill.partial` + `Fluid.frame` + `paintStream` | Genuine, append-only for settled blocks, one repaint per frame |
| Codex text | Not streamed: one `text` event per completed `agent_message` |
| Tool use, tool results, thinking (direct chat) | Not live: stored blocks appear only after the turn ends |
| Agent/J2 worker live view | Polled snapshot (about 4 Hz file + 400 ms poll) |

## 2. Message lifecycle table

Sync/async: S = synchronous inside the request, T = worker thread, G = generator (pull, no buffering), Q = queue thread, E = event loop, B = browser.

| # | Stage | Module / function | Data | Sync / async | Events emitted | Events consumed / notes |
|---|---|---|---|---|---|---|
| 1 | Send pressed | `ui/static/js/chat_composer.js` `create().send()`, `ask()` | `state.turn={active:true,text:"",messageId:null}` | B, sync | none | Row shows "<provider> is writing..." immediately, before any server acknowledgement (dishonest label, no sending/connecting state). No optimistic owner bubble in direct mode. |
| 2 | Request | `chat_v2.py` `direct` | body, attachment refs | E, S | none | Token check, session/kind checks, `direct_running.begin` (409 if busy), `_store_user_line` (`src_ref direct-ask:<random16>`, no idempotency key), `_ground` writes `system.txt` |
| 3 | Accept | `chat_v2.py` `direct` | `{message_id, turn:"started"}` | E | HTTP 202; owner line emits `chat.message` | Client then refetches messages (round trip) before the owner bubble shows |
| 4 | Worker start | `asyncio.create_task(run_blocking(_answer,...))` | turn args | T | none | Task reference not kept (H: GC risk) |
| 5 | Plan | `Router._chat`, `_drive`, `_chat_turn`, `_new_session`, `render_carry_over` | provider choice, session state | T, G | `started` (internal) | Retry/fallback loop; `_chat_busy`, `_chat_stop_early` set here (a Stop before this point can return `stopped:false`, H) |
| 6 | Spawn | `connectors/base.py` `_turn`, `_spawn`; `claude.py build_command` | `claude -p --output-format stream-json --verbose --include-partial-messages`, prompt on stdin | T | none | One new process per turn: cold start, `--resume`, MCP init every message |
| 7 | Pump | `connectors/process.py` `_pump_out`, `RunningProcess.lines()` | raw stdout chunks to lines to queue | Q + G | none | Genuinely incremental; `_last_activity` reset per line; idle timeout 120 s armed only when `partials=True` (Claude only) |
| 8 | Parse | `claude.py ClaudeParser.feed` (`_on_system`, `_on_stream_event`, `_on_assistant`, `_on_user`, `_on_result`) | JSON line to `ConnectorEvent` | G | `started`, `text_delta{kind:text\|json}`, `text`, `tool_call{id,name,input}`, `tool_result` (2000-char cap), `quota`, `notice` | Discards: `thinking_delta`, `signature_delta`, `content_block_start/stop`, `message_start/delta/stop`, non-init system subtypes. Codex: `codex.py CodexParser` handles `thread.started`, `item.completed`, `error`, `turn.*` only |
| 9 | Map | `connectors/chat_port.py` `stream`, `_map` | `ConnectorEvent` to `ChatEvent` | G | `partial`, `block` (tool_use/tool_result with kind/title via `tool_kinds`), `usage`, `switched`, `restart`, `turn_done{blocks}` | `started` swallowed (the only early liveness signal); `kind:json` deltas dropped; a whole `text` becomes a single `block` only if no partial was seen (Codex path); thinking never mapped |
| 10 | Relay | `chat_v2.py` `_answer` | `buffered` string | T | `chat.partial {session_id,message_id,delta,reset?}` via `bus.publish_one` | Handles only `partial`, `restart`, `turn_done`; drops `block`, `usage`, `switched`. Flush when `len(buffered)>=60`, on restart, at end, on error; per-chunk `services.redact` |
| 11 | Bus | `orchestrator/events.py` `_deliver`, `CONTROL_TYPES` | frame | T to E via `call_soon_threadsafe` | SSE frame | `chat.partial` is control: seq 0, not in the 1000-event ring, not replayed; slow subscriber gap at 2000 pending |
| 12 | SSE | `orchestrator/api/events.py`; `_frame` runs `services.redact.scrub` | `event: chat.partial` | E | wire | `: ping` comment every 15 s (invisible to the page); store events replay by `Last-Event-ID`/`?after=` |
| 13 | Client intake | `sutra_events.js connect` | named listeners (fixed `TYPES`) | B | calls handler | Auto-retry, backoff 1/2/4/8/15 s, polling fallback after 3 errors (polling refetches state, never partials) |
| 14 | Route | `home.js onEvent` (org chat only: `session_id===ORG`); `node_panel.js live()` (own `SE.connect`) | event | B | `composer.partial(d)` | Each open panel and each of home/dept_ext/console_view adds its own EventSource (H: HTTP/1.1 six-connection pressure) |
| 15 | Apply | `chat_composer.partial` guards (session, active, message_id), `chat_pill.partial` | `bounded(prev+delta)`; `reset:true` clears | B, sync | `onChange` | Cap 4000 chars, cut at head; no sequence/offset, so a lost event is undetectable |
| 16 | Paint | `Fluid.frame` (one job per key per animation frame), `chat_composer.paintStreamRow`, `fluid.js paintStream`/`splitStream`/`streamParts`, `chat_markdown.js render(...,{streaming:true})` + `hold()` | settled blocks appended once; tail rewritten | B | DOM | Row `#sstream`/`chatRefs.stream` sits outside the scroller. `streamParts` resets when `!text.startsWith(done)` (happens after head truncation) |
| 17 | Scroll | `chat_scroll.js`; `keepFollowing` in `home.js`, `node_panel.js` | reader intent | B | pill "N new messages below" | Follows unless parked; stream growth outside scroller does not count for the pill |
| 18 | Stop | `chat_composer.stop` to `POST /direct/stop` to `Router.chat_stop` (`_chat_stop_early` or `connector.stop`) to `process._terminate` | SIGINT 5 s, SIGTERM 5 s, SIGKILL 2 s on the process group | B to E to T | `CallCancelledError`, `stopped(user_message_id, shown)` | Real kill. Button shows "Stopping..." until the stored reply arrives; partials arriving meanwhile are still appended. Claude exits on SIGINT in about 1.3 s (documented, not re-measured). `stopped()` stores `blocks=[]` |
| 19 | Finish | `_answer` `turn_done`; `direct_turns.finished/stopped/failed`; `_post_all` | one transaction: reply (`text`, `meta_json.blocks`), notes, errors; `src_ref direct:<id>` etc. | T | `chat.message` (full message incl. blocks) | Stored text is `result.result` (H: last assistant message only, so streamed narration can differ from stored text). `ChatMessageOut.blocks` max 500 (H: a turn with more than 500 blocks fails to store and degrades to an error) |
| 20 | Settle | `home.js` `chat.message` handler / `node_panel.js refreshMessages`; `chat_composer.reconcile`; `chat_view.transcriptItems`; `ChatMarkdown`; `ChatFold.fold` | refetch (150 ms coalesce); turn ends when agent message `turn===messageId` | B | none | Panel reconciles and paints in one step. Home draws the stored bubble in the `chat.message` handler but reconciles only in `fetchMessages` (H: stream row and stored bubble both visible for about 150 ms plus a GET). Stream row to bubble is a DOM move (outside to inside scroller) with no continuity |
| 21 | Recover | `GET /api/chats/{sid}` `direct_turn` (memory only); `composer.resync`, `rejoin`; `chat_v2.recover_interrupted` at start (`wiring.py:238`) | in-memory turn registry; SQL on missing `direct:<id>` | B / T | server adds "Interrupted: the app closed..." line | Reload or second tab shows Stop with empty text; `rejoin()` clears text; partial text and tools of a crashed turn are lost |
| 22 | AI-worker live | `engine/capabilities/agents.py` to `runs.live_partials` to `agent_chats.js` | whole text snapshot, one `tool` string | engine thread, 400 ms poll, B | `chat.partial reset:true` | Final line stored later via `Projector._on_say` (`src_ref <run>#chat:<id>`) |

## 3. Root causes of the one-shot behaviour

Ranked by how much of "feels one-shot" each explains. All are Fact unless marked H.

**RC1. The relay discards everything except text deltas.** `_answer` handles `partial`, `restart`, `turn_done` only (`chat_v2.py:319-328`). `ChatPort` already classifies tools and builds typed `block` events, plus `usage` and `switched`, but they only leave the process inside `turn_done.blocks` and are drawn after the turn settles. Result: the owner sees a label and (for Claude) text, never "reading file X", "running command", or "thinking". For a tool-heavy turn the page is a single sentence until the end, then a fold of tool calls appears. The data exists in the pipeline; the transport drops it.

**RC2. Codex has no incremental text and a nameless tool trail.** `Capabilities(partials=False)`, `stream()` and `call_text` force it (`codex.py:392,488-495`), and the parser handles only `item.completed` (`agent_message` becomes one `text` event; other items become `tool_call{type,id}` with no command, output or exit code). `item.started`/`item.updated` fall through `getattr(self,'_on_'+...)` to `[]`. Fixtures show `item.completed` carrying `command`, `aggregated_output`, `exit_code` (`tests/fixtures/connectors/derived/codex_unknown_item_type.jsonl`), all dropped. (H, to verify with a real `codex exec --json` run: Codex 0.146.0 emits `item.started` for command items, which would give honest live "running <command>"; the CLI may never emit `agent_message` token deltas at all. Do not promise Codex token streaming.)

**RC3. Server coalescing by character count with no timer.** `PARTIAL_EVERY_CHARS = 60`; the first visible text is the 60th character, a reply under 60 chars never streams, and a short narration before a long tool call ("Let me look at that.") stays buffered. Redaction runs per chunk, so a secret split at the boundary can show live while the stored text is redacted whole (H on exposure).

**RC4. Claude tool, thinking and early-liveness signals are dropped at the parser and the mapper.** `_on_stream_event` ignores everything but `content_block_delta`: `content_block_start` (the tool_use name arrives early), `thinking_delta`, `message_start` are lost; `input_json_delta` is parsed then dropped by `_map` (`kind:json`); `tool_call` is only emitted from the complete assistant message. `started` (session id, model, tools; the first honest "connected" signal) is swallowed at `chat_port.py:234`. Long thinking is dead air.

**RC5. The client has no state richer than `{active, text}`, and claims "writing" too early.** `turn.active` is set before the POST, so "X is writing..." shows before the server accepted anything and before the provider produced anything. No distinct sending, connecting, thinking, tool, stalled or "live updates paused" states. No optimistic owner bubble, so the owner's own line waits a POST plus a GET.

**RC6. Fragile display-side continuity.** Head truncation at 4000 chars makes long replies lose their top mid-stream (and forces `streamParts` resets); the stream row lives outside the transcript scroller and is replaced, not promoted, at settle; pieces carry no sequence number so a dropped or reconnect-gapped event is silent loss.

**RC7. Nothing in flight is persisted.** One insert at `turn_done`. A refresh, second tab, crash or restart loses streamed text and tool activity; `chat_messages.state` allows `pending` but nothing writes it.

Contributing latency (H, unmeasured): one CLI process per turn (D32 rejected a long-lived stream-input process for lifecycle cost), so time to first token includes spawn, `--resume` and MCP init.

Not a cause (checked): process pipe, generator chain, middleware, SSE headers and `Fluid.paintStream` are all genuinely incremental. No GZip, no response buffering, no `StreamingResponse` in app code. The fix is not "make the pipe stream"; it is "stop discarding and stop batching".

## 4. UI and animation inventory

| Element | File | Behaviour today | Notes |
|---|---|---|---|
| Streaming row | `fluid.js paintStream`; `home.html` `#sstream`; `chatRefs.stream` in `node_panel.js` | `<small>X is writing...</small>` plus `.cstream-text` (hidden until first node); settled blocks kept, tail re-rendered | Outside scroller; no max-height; role=status aria-live=polite (H: chatter on appends) |
| Typing/progress affordance | none | No caret, dots, shimmer, elapsed time, `@keyframes` for the stream row | |
| Frame batching | `Fluid.createFrames/frame` | One repaint per animation frame, last job per key wins | Home keys by the repaint fn; panel by `frameKey` |
| Block splitter | `fluid.js splitStream/streamParts` | Fence/list/table aware; reset when text no longer extends settled prefix | |
| Markdown | `chat_markdown.js render(...,{streaming:true})`, `hold()` | Open fence renders as code; unfinished table rows withheld; no links/images/HTML by design (ui.md 4.3); no syntax highlighting | Same renderer for stored reply |
| Head cap | `chat_pill.js MAX_SHOWN=4000`, `bounded()` | Keeps last 4000 chars, cut at line break, fence re-opened | Stored message has all text |
| Scroll | `chat_scroll.js` (intent state machine, ResizeObserver `pin`, `remember/restore`, pill, `behavior()` for reduced motion) | Follows unless parked; touchmove parks | Pill does not count stream growth |
| Transcript diff | `Fluid.patchList/diffList`; `chat_view.transcriptItems` (key `"m"+id`) | Adds `nmsg-in` class to new lines | No `.nmsg-in` keyframes found in the CSS files read (H: class only) |
| Tool fold | `chat_fold.js fold(blocks,{settled})` | Returns "" until settled; one `<details>` summary "12 tool calls: 8 read, 3 run"; client already knows kinds read/edit/run/search/web/other | Only live-capable consumer waiting for data |
| Stop/Send button | `chat_composer.button/stop`, `stopPress` guard | Send becomes Stop; "Stopping..." disabled until reconcile | No local freeze of the row |
| Retry | `chat_view.retryOf`, `retry()` | Only on a failed direct line while the owner's newest | No copy, regenerate or edit; no `clipboard.writeText` anywhere in `ui/static/js` |
| Provider pill / switch notice | `chat_pill.js` `switchNotice`, provider pill | Shown after turn end | Fallback note is engine-path only |
| Agent live row | `agent_chats.js livePartial/liveRow`, `node_panel.js paintLive` | Whole row repaint via `innerHTML`, escaped text, `<br/>`, one `tool` string | Shares `chatRefs.stream` with the direct row (clobber risk) |
| Motion tokens | `sutra-panel.css` (about L468) `--dur-fast/base/slow`, `--ease-out`; reduced-motion kill rules | Zeroed under `prefers-reduced-motion` | Reuse for any new motion |
| Scripts availability | `home.html` loads the chat stack; `j2_ui.html` and `console.html` do not | Callers check for each global and fall back | Dual export pattern (global + node `require`) must be kept |
| Tests | `tests/ui/js/chat_composer.test.js` (43), `fluid.test.js` (27), `chat_pill.test.js` (18), `chat_scroll`, `chat_view`; `tests/e2e/test_browser_chat_composer.py` (not read) | 177 node tests pass; fake api/DOM, no real layout | Layout/flicker findings below are unreproduced |

## 5. Gap table

Severity: H high, M medium, L low. "(H)" in a cell means hypothesis.

| Area | Current | Limitation | Required change |
|---|---|---|---|
| Provider: Claude | `--include-partial-messages`; only `text_delta`/`input_json_delta` parsed | Thinking, tool_use start, message boundaries dropped; `tool_call` arrives after the input finishes; `thinking` ChatBlock type exists but is never produced | Parse `content_block_start` (tool_use name/id, thinking start), `thinking_delta` (as a presence signal, not text unless product decides to show it), `message_start/stop`; new `ConnectorEvent` kinds; gate on `plan.partials`. Parser-only change; update `test_claude_parse.py` and fixtures (H) |
| Provider: Codex | `partials=False`; whole `agent_message`; nameless `tool_call{type,id}` | One-piece reply; no honest live activity | Handle `item.started`/`item.updated`, keep command/path/exit code/output (capped) on completed; run a real `codex exec --json` to learn what is really emitted before designing; where the CLI gives no deltas, show an honest "working" state only. Never chunk the final text |
| Provider: startup | One CLI process per turn | First-token latency includes spawn/resume/MCP init (H, unmeasured) | Measure first; then consider an honest "connecting" state from `started`, prewarm, or reuse; D32 rejected a long-lived stream-input process, so any change needs a new decision and touches `_spawn`, `_procs[key]`, busy/stop tracking |
| Provider: fallback | `restart` + `reset:true` discard what was shown | Jarring, unexplained; fallback note only on engine path | Carry a `switched`/restart reason to the page; clear any live activity state on restart |
| Backend: relay | `_answer` forwards only partial/restart/turn_done | Blocks, usage, switched, started dropped | Relay typed live events (turn phase, tool start/end, thinking, usage) through `publish_one`; accumulate blocks in `_answer` so stop/failure endings can keep them |
| Backend: coalescing | 60-char threshold, no timer | First text delayed; short/pre-tool text withheld; per-chunk redaction can split a secret (H) | Time-bound flush (first delta immediately, then per-frame cadence); redact on a running buffer holding back a short tail; keep stored text equal to what was shown on stop |
| Backend: request path | Sequential blocking steps before 202; no event before first partial | No signal that the turn is accepted/connecting | Publish a turn-phase event (accepted, connecting, first byte) from real stages; return as soon as the line is stored |
| Backend: stop | Ladder blocks inside `run_blocking`; `chat_stop` may return `stopped:false` between `direct_running.begin` and `_chat_busy.add` (H) | Perceived stop latency bounded by SIGINT exit (about 1.3 s documented); early Stop can be lost | Mark the turn stopping immediately; close the early window (register busy at `begin`); never claim stopped before the server confirms |
| Backend: stored text | `result.result` as final text | Streamed interim narration can disagree with stored text (H); order text/tool/text lost; Codex duplicates message text in a text block | Decide the stored-turn shape (ordered segments or accept the current one) and document it; verify with a real multi-step capture |
| Backend: idempotency | Owner line `src_ref` random per request | A double POST after turn end makes a second turn | Client idempotency key (low priority) |
| Transport | Global SSE, `chat.partial` control event, no seq, no replay, `: ping` invisible | Silent gaps; reload/second tab cannot catch up; polling fallback shows nothing; no liveness visible to page | Add `seq` and optionally cumulative `offset` to the payload; per-turn catch-up (current text and activity on `direct_turn`, held in `direct_running`); a visible heartbeat/liveness event tied to the turn; keep it a control event or give it its own ring (putting it in the 1000-event ring would force `gap` resyncs for every topic); add new names to `sutra_events.js TYPES` and the events.py type check |
| Transport: connections | One EventSource per mounted view plus one per open panel | H: HTTP/1.1 six-connection limit competes with POST/GET | Share one connection per page, or measure first; a fetch-stream endpoint would add a long-lived connection and is not recommended on this evidence |
| State (client) | `turn {active, stopping, text, messageId}` | No phase, activity, tool list, elapsed, seq; `rejoin` clears text; `reconcile` ends on any agent row with `turn===id` regardless of `state` | Additive fields (phase, activity lines, lastSeq); honest labels per real phase; local-optimistic owner bubble keyed to message_id, removed/marked failed on refusal (reuse Home `S.pending`; panel has no equivalent); `reconcile`/`resync` and `recover_interrupted` must change together if a `pending` row is ever introduced |
| Rendering | Stream row outside scroller; separate DOM from final bubble; head cap 4000 | Layout jump at settle, squeezed viewport on long replies (H), top of long replies vanishes, Home duplicate window (H) | Promote the stream row to a transcript item with a stable id tied to message_id (or hold height and cross-fade at settle); raise or remove the head cap with a check of `bounded` and scroll anchoring; make Home reconcile and paint in one step as the panel does; apply in both Home and panel and test both |
| Animation | Label only; `nmsg-in` class without keyframes (H) | No sense of liveness between send and first token; no caret | Presence indicator driven by real events, using `--dur-*` tokens and inside `prefers-reduced-motion: no-preference`; optional client-side pacing only to reveal already-received real text, never to invent it |
| Tools / activity | Visible only as stored blocks after the turn; agent path shows one `tool` string at 4 Hz | No live "reading X / running Y"; tool errors invisible until the end | Live activity lines from real `tool_use` start and `tool_result` events (Claude `content_block_start`; Codex `item.started`); extend `ChatFold` to render live blocks; no counts or percentages the wire does not carry |
| Persistence | Single insert at `turn_done`; `stopped()`/`failed()` use `blocks=[]`; crash loses partial text | Refresh and crash lose in-flight work; tools that changed files are not recorded on non-success endings | Keep partial text and blocks on every ending; consider persisting in-flight text throttled or in a side store (the `chat_search_msg_au` FTS trigger re-indexes on every `UPDATE OF text`, so do not update `text` per delta); `post` returns None on an existing `src_ref` and emits `chat.message` on every insert, so a placeholder row needs its own update path |
| Persistence: limits | `ChatMessageOut.blocks` max 500; store/ChatPort uncapped | H: more than 500 blocks fails the store transaction; the turn degrades to "The model could not answer." | Cap or fold blocks at the producer (with a truncated marker), or lift the read-model cap with a recorded decision; add a test |
| Reusable abstractions | See section 6 | | Extend, do not rewrite |
| J2 / agent / engine | `engine/` vendored; 4 Hz snapshot; cumulative `{"chars","text"}` | Three partial contracts (deltas, cumulative snapshot, polled snapshot) | Leave engine and J2 progress contract untouched; add the new event model only on the direct-chat route; unify later on the Sutra side only |

## 6. Reusable abstractions (extend, do not replace)

- `connectors/process.py` pump and cancel ladder: already incremental and process-group safe. No change needed to stream.
- `ClaudeParser._on_stream_event`: already sees every stream line, so new kinds are parser-only.
- `ChatEvent` vocabulary (`chat_models.py`, `EVENT_KINDS` already include `block`, `usage`, `switched`) and `ChatPort._map`: the single seam where new honest events are added once and reach every surface; `restart` already voids earlier attempts.
- `orchestrator/events.py CONTROL_TYPES`, `publish_one`, `_frame` redaction: the non-ringed channel for live events.
- `direct_running` (`begin/attach/end/turn_of`) and `GET /api/chats/{sid}` `direct_turn`: the place to hold a catch-up marker.
- `Router.chat_stop`, `_chat_stop_early`, `CallCancelledError` to `stopped()`: real, race-aware cancel with tests.
- Client: `Fluid.frame/paintStream/splitStream/patchList`, `ChatComposer` controller (fully injectable), `ChatPill.partial` with `reset`, `ChatMarkdown.render({streaming:true})`, `ChatScroll`, `ChatFold`, `SutraEvents.connect`, `chat_view.transcriptItems`, motion tokens.
- Schema: `chat_messages.state='pending'` allowed; `chat_view.js` already folds with `settled: state !== 'pending'`; `ChatTranscripts` excludes non-`ok` rows from carry-over; `ChatBlock` already has `thinking` type, kind, `is_error`, `truncated`.
- `chat_v2.recover_interrupted` (`direct-ask:` / `direct:<id>` convention) could restore a persisted partial instead of only an error line.
- Tests to extend: `tests/orchestrator/test_api_chat_v2.py`, `test_events_sse.py`, `test_events_bus.py`, `test_direct_turn_endings.py`, `test_direct_recovery.py`, `tests/connectors/test_chat_port.py`, `test_claude_parse.py`, `test_chat_restart.py`, `tests/ui/js/*`.
- The stub and `ScriptedPort` are for offline UI and tests only; they cannot be evidence for real streaming.

## 7. Risks

1. **Vendored engine.** `engine/llm.py`, `engine/capabilities/agents.py` and the J2 progress shape must stay byte-for-byte (except recorded patches). All work belongs in `connectors/`, `orchestrator/`, `ui/static`. Faster agent live view than 4 Hz would need a recorded vendoring patch.
2. **Honesty.** Only show states backed by wire events. No fabricated tool lines, percentages, token drip, or Codex chunking. Claude `content_block_start` tool names are real; Codex `item.started` is unverified.
3. **Redaction.** Per-chunk redaction can split secrets. Any change to flush size or timing changes exposure; new live events must pass `redact` like `_frame`. Add a hold-back tail or running-buffer redaction before shrinking chunks.
4. **Ring pressure.** Making chat events replayable in the shared 1000-event ring would trigger `gap` resyncs for all topics.
5. **Event rate.** Per-token SSE frames raise render cost and can hit the 2000-pending slow-subscriber gap on a stalled tab; client already frame-batches, but verify no starvation/double paint (Home keys by repaint fn).
6. **Restart/fallback.** Any live activity state must be cleared on `restart` or a failed attempt's lines remain on screen.
7. **Pending-row hazards.** A `pending` placeholder would end the turn early in `reconcile`/`resync`, hide the turn from `recover_interrupted`, make `post` return None for the final write, and churn FTS if text is updated per delta.
8. **Two paint paths.** Home and panel share `ChatComposer` but settle differently; every UI change must be done and tested in both. `paintLive` and `paintBar` both write `chatRefs.stream`.
9. **Stop semantics.** What is stored on stop must equal what the owner saw; a faster visual stop must keep the `stopped:false` to `resync` path.
10. **Escaping.** All new wire strings go through `esc`/`safeText`/`ChatMarkdown`. Fixtures must pass `scripts/ownership-audit.sh` (no owner name or home paths).
11. **Persistent process change** touches `_spawn`, session state, busy/stop tracking, D32.
12. **Unverified layout claims** (duplicate window on Home, settle jump, squeezed viewport) are hypotheses until reproduced in a browser or e2e run.

## 8. Breaking-change list (what existing code or tests would notice)

| Change | Who breaks |
|---|---|
| New `ConnectorEvent` kinds from `ClaudeParser` | `tests/connectors/test_claude_parse.py` and recorded fixtures (pin current behaviour); `ChatPort._map` must ignore unknown kinds safely for engine paths |
| Codex parser keeping command/output/exit code, handling `item.started` | Codex parser tests and fixture expectations; `title_of` output (currently just `command_execution`) |
| `_answer` relaying blocks, new SSE event names | `sutra_events.js TYPES` (fixed list), events.py type check, contract tests, `home.js`/`node_panel.js onEvent`; `EventSource` delivers only named listeners |
| `chat.partial` payload gains `seq`/`offset` | Additive for the page; `test_api_chat_v2.py`/`test_events_sse.py` payload assertions; composer guards |
| Removing/replacing the 60-char coalesce | `tests/orchestrator/test_api_chat_v2.py` and `test_direct_turn_endings.py` assertions about partial boundaries (to confirm) |
| Changing `MAX_SHOWN` or stream row DOM | `fluid.test.js` (4f-4i), `chat_pill.test.js`, `chat_composer.test.js` |
| Moving the stream row into the scroller | `home.html #sstream`, `home.js renderChat/renderBar/keepFollowing`, `node_panel.js paintMessages/paintBar`, CSS `.ccstream` |
| Optimistic owner bubble | Home `S.pending` flow; panel has none; `reconcile`/`retry` and failure cleanup |
| `pending` message rows or in-flight persistence | `chat_composer.reconcile/resync`, `recover_interrupted` SQL, `ChatStore.post` semantics, FTS triggers, `ChatTranscripts` |
| Lifting/enforcing the 500-block cap | `models.py:409` and any API serialisation tests |
| Adding fields to `turn` state | Additive, but `chat_composer.test.js` asserts `state().turn` shape |
| Anything touching `engine/` | Vendoring check; needs a recorded patch and D-id |
| New decisions | Next free id is after D200 in `docs/DECISIONS.md`; design notes under `docs/design/streaming/` |

## 9. Unverified items to settle before design is frozen

1. What `codex exec --json` really emits (item.started/updated, any message deltas) on the installed version.
2. Whether Claude's `result.result` equals only the final assistant message on multi-step turns, and what the stored vs streamed text looks like.
3. Real time to first token and Stop latency (no measurements exist).
4. Home duplicate window, settle jump, and long-reply layout in a real browser.
5. Whether a more than 500-block turn really fails to store end to end.
6. Whether per-chunk redaction can actually leak a split secret (depends on `services.redact` needing cross-chunk context).
7. Connection-budget effect of multiple EventSources.
