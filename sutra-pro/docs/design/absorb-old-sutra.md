# Absorbing the old Sutra app into Sutra Pro

Status: design, 2026-11-06. Decisions D105 to D115 in `docs/DECISIONS.md`. Work packages `ABS-*` at the end (and in `docs/build-plan.json`).
Nothing in this document changes a vendored J2 file, a J2 prompt, a J2 route path or a golden.

Owner's request (2026-11-06, verbatim): "Now we have the J2 prototype idea, so that idea should remain the same. Now let's combine the old
Sutra into the new Sutra Pro with all the updated ideas, but the basic improvement regarding the chat and everything should be in the J2
provider." No clarification was possible; the readings below are decided (D105) and the owner can veto them.

## 0. What the request means, and the better reading found in the code

1. "The J2 idea stays the same": the vendored engine (`sutra_app/engine/j2*.py`, the 30 views, the five prompts' text, the J2 page port) is
   frozen. Anything absorbed from the old app arrives around it, never inside it. Enforced by the existing `tests/engine/test_engine_vendor.py`
   (sha256 of every vendored file), the prompt goldens `tests/engine/golden/prompts_*.json` and the API shape goldens.
2. "Combine the old Sutra into Sutra Pro": port capabilities, not code. The old app is about 224 k lines of Python and static
   JavaScript (the brief's figure; the top-level modules alone are 88.7 k lines of Python and 48.6 k of JavaScript, the rest is in sub-packages
   such as `layer_models/` and `seo_agent/`, and a bundled runtime and Electron payload that are not counted). Most of it is a second
   implementation of ideas Sutra Pro already has in another shape (one org chart, five function nodes, closed models, a connector router, rows 16
   to 33 below). What is left to bring is a short list, most of it about chat.
3. "The basic improvement regarding the chat ... in the J2 provider": tested against the code. The J2 prototype's own `llm.py` is a provider
   switch (`claude -p`, Anthropic SDK, Gemini, mock); in Sutra Pro it became the single model seam `engine/llm.py -> ModelPort -> connectors
   Router -> claude / codex` (D17). **The reading holds, with one refinement the code forces.** Today there are three separate model paths:
   - the engine's `ModelPort` (one-shot calls for J2's five agents), the seam the request names;
   - the orchestrator's `AsyncConnector.call_json` (the org chat agent's three staged structured calls);
   - the Router's own session API (`chat_start`, `chat_send`, `chat_stream`, `chat_stop`, `chat_pin`; `connectors/router.py` lines 647 to 700,
     and `PUT /api/connectors/sessions/{id}/provider`) which nothing in the app calls (a search of `sutra_app/` finds only the route and tests).
   So the "chat provider" is half built and unused. The refinement: the improvement goes into the **Router and a sibling port to `ModelPort`
   called `ChatPort`**, so that J2's one-shot seam keeps its exact shape (J2's idea) while chat sessions get the old app's chat improvements
   once, below every surface. Section 2 is that design.

The old chat is a coding-agent pane: a chat is one provider session bound to a working directory, with tools and permission modes. Sutra Pro's
chats are the org chat, one chat per node, and the department's lines. We port what makes a chat good (history that outlives a provider,
switching, archive, search, folding of tool noise, attachments, secret scrubbing, the right window per model), not the coding-agent shell.

## 1. Capability inventory of the old app

Source: `marketplace/plugin/sutra-ui/` (read only). Sizes are lines of Python (py) or JavaScript (js), excluding tests, the `.venv` and the
Electron payload. "Pro equivalent" cites files under `sutra-pro/`. Verdicts: **PORT** (build it in Sutra Pro, section 3), **REPLACED**
(Sutra Pro already does it, and better or by an owner rule), **DROP** (not carried; reason given), **LATER** (wanted, no package yet; trigger given).

### 1.1 Chat

| # | Old module(s) | What it does | Size | Pro equivalent | Verdict |
|---|---|---|---|---|---|
| 1 | `chat_store.py` | A chat record that outlives any provider session: `provider_history` segments (`from_turn`), typed blocks (text, thinking, tool_use, tool_result), index by provider session id | 410 py | `orchestrator/chats.py` `ChatStore`: text messages, ONE `connector`/`provider_session_id` per session, no segments, no blocks | **PORT** (segments table, optional `blocks`; the old file format is read only by the importer) |
| 2 | `chat_archive.py` + archive routes | Archive is a mark, never a move; a chat written to again leaves the archive by itself | 103 py | `chat_sessions.status='archived'` exists but only a merge sets it (`chats.py apply_links`, D70) | **PORT** (owner archive and un-archive; never a delete) |
| 3 | chat search (`/api/sessions?q=`, `chatSearchRemote`) | Searches titles, folders and headers across every chat in scope, server side | in `app.py` + `01-state.js` | none | **PORT** (SQLite FTS5 over titles and message text, scoped) |
| 4 | chat scope setting (`test_chat_scope.py`) | Rail lists Sutra's own chats or every Claude transcript on the machine | in `app.py` | scope is a node, a department or all (`GET /api/chats?node_id=`) | **REPLACED** (Pro does not browse other tools' sessions) |
| 5 | `transcript_ir.py`, `session_reader.py` | Full-fidelity and render parsers of Claude's and DeepSeek's own transcript trees; the rail's list of every Claude session | 810 + 1652 py | `connectors/transcript.py` carries over the app's OWN messages (D32), so no provider tree is ever parsed | **DROP** (Pro owns its transcript; the 238 old messages are in the old store, section 4) |
| 6 | `switch.py` | Plans a mid-chat provider switch: replay tier, sizes, guards; `confirm` writes the segment only when the new session exists | 312 py | `Router._chat` + `render_carry_over` already switch and carry over; no dry-run | **REPLACED** (the dry-run `plan_switch` is ABS-1) |
| 7 | `switch_egress.py` | Scrubs credential shapes from a replay payload and appends a count-only audit row | 209 py | `orchestrator/redact.py` hides only known secret VALUES (env, `.env`), no shapes, no audit row on egress | **PORT** |
| 8 | `budget.py` | Characters of replay that fit THIS model's window; unknown model assumes the floor; label "estimate" | 301 py | flat J2 caps in `connectors/transcript.py` (60 000 chars, 40 tail messages, 8 000 digest) | **PORT** (lower-only: J2's caps stay the ceiling, D110) |
| 9 | `session_runtime.py`, `proc_group.py`, `acp_runtime.py`, `codex_runtime.py` | Process transports for Claude (stream-json), ACP (DeepSeek), `codex exec` | 750 + 409 + 890 + 580 py | `connectors/process.py`, `claude.py`, `codex.py` (one process per call or turn, cancel ladder, env allowlist) | **REPLACED** |
| 10 | `static/js/05-chat.js`, `06-render.js`, `07-loaders.js` (activity fold, combined pill, streaming loader, tool cards) | One row per turn instead of a card per tool call; one round pill with governance and runtime; the streaming indicator | 8 616 js in the three files (the chat part of them) | `ui/static/js/chat_view.js` (bubbles, cards; pure string functions), no fold, no pill, no streaming text | **PORT** (fold and streaming indicator; the "governance" half of the pill is Shadow's and is dropped) |
| 11 | `shadow_attachments.py`, `/api/org/attach` | Images, PDFs and text files saved once by id; the model gets content (image block, PDF document block, text cut with the cut said) | 271 py | `Message.images` = PNG paths only (`connectors/models.py`) | **PORT** |
| 12 | `tool_kinds.py` | Classifies a tool call into a kind (read, edit, run, search, web...) for the timeline | 257 py | none | **PORT** (events carry `kind`, so the fold has something to count) |
| 13 | composer "/" palette (`skills_catalog.py`, `skill_categories.py`) | Lists the slash commands the `claude` CLI can resolve | 376 + 227 py | none | **LATER** (when Pro lets a team call a Claude skill) |
| 14 | natural-language provider switch in the composer ("using Codex, ...") | Detects a provider name in the message and switches | in `15-shadow-overlay.js`, `05-chat.js` | none | **LATER** (the pill is the one mechanism, D111; a text detector is a second one that can disagree) |
| 15 | per-chat provider that sticks (`test_chat_local_provider.py`) | A chat on Codex stays on Codex across reconnects; the global default is untouched | in `app.py`, `chat_store.py` | `Router._pins` in memory, lost on restart; `chat_sessions.connector` is written after a call | **PORT** (persist the choice per session; ABS-6, D111) |

### 1.2 Providers, accounts, usage

| # | Old module(s) | What it does | Size | Pro equivalent | Verdict |
|---|---|---|---|---|---|
| 16 | `providers.py`, `provider_adapters.py` | Which CLIs are runnable (installed, configured, driven by us) with the reason; models; permission modes; one adapter per provider | 3949 + 1244 py | `connectors/base.py` `ModelConnector`, `health.py`, `policy.py`, `claude.py`, `codex.py`; `GET /api/connectors` | **REPLACED** (the "runnable, with the reason" rule becomes the pill's data in ABS-1) |
| 17 | `claude_local.py` | Reads plan label and last workdir from Claude's config | 176 py | `ProviderStatus.plan` in `connectors/health.py` | **REPLACED** |
| 18 | `claude_accounts.py` | Resolves which third-party account a Claude-held connector is bound to by reading Claude's own session token | 184 py | none | **DROP** (reads another application's credential; D34: Sutra never reads or stores either login) |
| 19 | `codex_auth.py`, `codex_install.py`, `codex_login.py`, `codex_models.py` | Codex sign-in, a CLI installer, model catalogue | 760 + 620 + 267 + 725 py | `connectors/codex.py` (device-auth sign-in launched by the app, `models()`), D34 | **REPLACED** (the installer is dropped: "Sutra never installs a CLI") |
| 20 | `deepseek_auth.py`, `deepseek_install.py`, `deepseek_session.py`, `deepseek_usage.py` | DeepSeek over ACP with an API key and a pairing code | 1187 py | none | **LATER** (needs the owner to lift D7 "no API keys", or a subscription login; the seam admits a third connector, D112) |
| 21 | `usage.py` | Plan rate-limit windows from the OAuth endpoint, using Claude's token | 741 py | `connectors/usage.py`, `Quota` from `rate_limit_event`, `UsageStore` | **REPLACED** (the token read is dropped, D34) |
| 22 | `connectors_api.py`, `mediated_connectors.py`, composio catalogue | Lists third-party app connectors held by Claude | 355 + 454 py | `connectors/tools/` (Sutra MCP server), `GET /api/connectors/mediated` | **REPLACED** |
| 23 | `models_api.py` + `layer_models/` | The owner's "models" (specs of how a department behaves), compiled | 402 py + 8318 py | `library/` closed models, `engine/fnodes/` | **REPLACED** |

### 1.3 Organisation, departments, functions, runtime

| # | Old module(s) | What it does | Size | Pro equivalent | Verdict |
|---|---|---|---|---|---|
| 24 | `org_api.py`, `org_apply.py`, `org2_api.py`, `org2_apply.py`, `dept_api.py`, `dept_list_api.py`, `dept_read.py`, `founding.py` | Org registry with a Root, departments, charters, placements; read aggregates for the Org and Department screens | about 6 640 py | `library/org_chart.py`, `orchestrator/chart.py`, `chart_rules.py`, `departments.py`: ONE global chart, changed by the chat agent (D26, D42 to D44, D67) | **REPLACED** |
| 25 | `reorg_sim.py` | Simulates a reorganisation before applying it | 450 py | `chart_rules.py` + `ChartChange` + approval cards | **REPLACED** |
| 26 | `project_import.py` | Every project folder worked in becomes a department on install | 746 py | none | **DROP** the automatic mass creation (the chart grows on need, owner rule); chat-led import of one folder is **LATER** |
| 27 | `engine_runtime.py`, `layer_schema.py`, `layer_consts.py`, `layers/` | The old engine of a department: board, five systems, templates | 7151 + 1933 + 231 py | `sutra_app/engine/` (vendored J2) + `engine/fnodes/` | **REPLACED** |
| 28 | `j2_runtime.py`, `j2_api.py`, `j2ui_*.py`, `25-j2view.js` | The adaptor that embeds the J2 prototype page on the old engine | 4890 py | `engine/` is J2 itself; `ui/pages/j2_ui.html` is the page | **REPLACED** |
| 29 | `functions_view.py`, `20-dept.js`, `24-functions.js` | Function and department screens | 1122 py + js | `ui/static/js/fnode_view.js`, `node_panel.js`, `orgchart_view.js`, J2 page | **REPLACED** |
| 30 | `website_dept.py`, `website_api.py` | A department that builds a website with four engines | 1841 + 482 py | J2's website artifact in `engine/` and `library/artifacts/` | **REPLACED** |
| 31 | `seo_agent/`, `agents_api.py` | SEO writer agent and its routes | 3305 py + about 5 660 py | none | **LATER** (as a library template of a team, when the owner asks for one) |
| 32 | `goal_store.py`, `goal_lifecycle.py` | A durable goal that outlives its attempts (missions) | 526 + 484 py | `library/goal.py` (goal of a node), follow-up tasks with `seed_from` (ORCH-6), GAP-E1B | **REPLACED** (the idea "a goal outlives a failed attempt" is a follow-up task; recorded as an open question in section 5) |

### 1.4 Library, templates

| # | Old module(s) | What it does | Size | Pro equivalent | Verdict |
|---|---|---|---|---|---|
| 33 | `library_api.py`, `function_templates.py`, `template_checks.py`, `artifacts.py` | Shelves of templates read from files; template checks | 724 + 132 + 311 + 226 py | `library/templates.py`, J2 template library (`engine/j2_template_lib.py`), `library/artifacts/`, Library tab of the J2 page | **REPLACED** |
| 34 | `function-templates/`, `artifact-templates/` (10 files), `engine-templates/` (6 files) | The old seed templates | data | `library/specs/function_specs.json`, `engine/templates/`, `library/artifacts/` | **PORT** (an audit that lists what the old seeds have that Pro's seeds lack, and seeds the difference: ABS-11) |

### 1.5 Shadow, goals, routines

| # | Old module(s) | What it does | Size | Pro equivalent | Verdict |
|---|---|---|---|---|---|
| 35 | `shadow_*.py` (31 files), `mission_engine.py` | Shadow: a supervisor that reads worker chats, decides, delegates, nudges, keeps a feed, judges completion, quiet hours | 12 642 + 5 660 py | The one org chat agent (`orchestrator/agent/`), departments, `ChatStore.needs_you()`, approval cards, atoms with `verify` | **DROP** as an engine (a second orchestration brain beside the chat agent breaks "talk to one chat"); the salvage is itemised: attachments PORT (row 11), egress PORT (row 7), needs-you and approvals REPLACED, cost per task REPLACED (`atom_ledger`), presence and quiet hours **LATER** (G26: nothing tells the owner a team asked a question) |
| 36 | `routines.py`, `routine_links.py` | Scheduled routines on this machine through launchd | 1298 + 183 py | none (no scheduler; `ops/` has none) | **LATER** (needs a scheduler that survives the app being closed; trigger: the owner asks for scheduled work) |
| 37 | `teamsutra.py`, `proposals.py`, `sutra_mcp.py`, `mcp_allow_hook.py` | A tool surface for the chat agent; mutations are proposals the owner approves; durable task drafts | 252 + 217 + 833 + 76 py | `connectors/tools/` (MCP), approval cards (`ChartChange`, D43), `tasks.py` | **REPLACED** |
| 38 | `optimus_api.py` | Window over an outside daemon's stores | 247 py | none | **DROP** (depends on a daemon CLI that is not part of Sutra Pro) |

### 1.6 Modules, apps, workspace, shell

| # | Old module(s) | What it does | Size | Pro equivalent | Verdict |
|---|---|---|---|---|---|
| 39 | `modules_api.py`, `modules_registry.py`, `modules_pkg.py`, `modules_sign.py`, `modules_events.py` | Registry of finished products ("modules") built inside the app, signed packages | 2556 py | none | **LATER** (no design in Pro; needs the owner's call on distribution) |
| 40 | `APPS-DESIGN.md`, `APPS-EVENTS.md`, `APPS-LIFECYCLE.md`, `APPS-SDLC.md`, `APPS-THREATS.md`, `apps-frameworks/` | Design of an apps platform (documents; no running code) | 5 documents | none | **LATER** (documents only; read when apps are asked for) |
| 41 | `workspace_api.py`, `workspace_corpus.py`, `repo.py`, file editor and git panel | A file workspace over the configured project folder | 879 + 284 + 328 py | The J2 page shows a run's artifacts and documents | **DROP** (an IDE pane is outside the J2 idea and the one-chat model) |
| 42 | `electron/` (main, bridge, bundle scripts) | The desktop shell, a beta channel with its own data namespace | 5982 js | `desktop.py`, the macOS app and the Windows installer (D12, D92, D101, REL-2); `SUTRA_DATA_DIR` | **DROP** (Pro ships its own app bundle; D12 rules out Electron) |
| 43 | `updates.py`, `updates_delta.py`, `updates_cli.py`, `versions.py` | In-app update check, delta download, install swap | 2095 + 913 + 86 + 63 py | releases are tags `sutra-pro-v*`, never "Latest" (D100); no in-app updater | **LATER** (an updater for Pro, from its own release feed; must never read the old product's "Latest") |
| 44 | `app.py` | The FastAPI monolith: every route, the websocket chat | 8360 py | `orchestrator/api/`, `connectors/api.py`, `ui/routes.py`, SSE (D80) | **REPLACED** |
| 45 | `fixture_seed.py`, `shadow_archive_fixtures.py`, `mock/`, `qa/`, `evals/`, journey scripts | Test and demo seeding | about 800 py + data | `--offline` demo (D97), `tests/fixtures/` | **DROP** |
| 46 | the old test suite (404 test files: py, js, sh) | Characterisation of all of the above | n/a | `tests/` | **PORT** only for the chat behaviours of rows 1 to 3, 7, 8, 10 to 12 and 15: each ABS package lists which old test it re-expresses |

The counts are in section 7 (Summary) and were computed from this table.

## 2. The chat design

### 2.1 One provider below every surface

```
  surfaces                       seams                         shared below both                 CLIs
  J2 Simple / Detailed page ---> (J2 agents) engine/llm.ask --> ModelPort ----+
  department chat, node chats -> ChatPort (NEW) ---------------------------->+--> Router  --> ClaudeConnector --> claude
  org chat agent (staged JSON) -> AsyncConnector.call_json ----------------->+   policy, plan,    CodexConnector --> codex
  Settings / pill -------------> providers(), choose() (ChatPort) ---------->+   pins, quota,     (StubConnector, tests)
                                                                                usage rows,
                                                                                EGRESS, BUDGET (NEW)
```

- `ModelPort` and `engine/llm.py` do not change. J2's agents keep one-shot `ask(...)` and J2's own run chat (the owner and Identity inside a
  run) keeps living in the run folder and being served by the engine's routes. That is J2's idea and it stays.
- `ChatPort` is a sibling protocol in `sutra_app/connectors/chat_port.py` (the engine never imports it; the orchestrator and the UI routes do).
  Its implementation, `RouterChatPort`, is a thin layer over the Router's existing `chat_*` methods plus the new capabilities. The org chat
  agent keeps its three staged `call_json` calls (they are structured planning, not conversation); it gains the chat's provider choice because
  every call already carries `RouteContext.session_id` and the Router's plan honours pins.
- The transcript stays the app's own, in `ChatStore` (SQLite, the server is the only writer). The provider's session is a cache of it (D32,
  unchanged). `ChatPort` never writes messages; it reads history through the existing `TranscriptSource` and returns events and results that
  the orchestrator stores.

### 2.2 What `ChatPort` offers

```python
class ChatPort(Protocol):
    def providers(self, session_id: str | None = None) -> list[ProviderPill]       # usable ones, each with ready/why-not (installed, signed in, driven)
    def choose(self, session_id: str, provider: str | None, model: str | None = None) -> Choice   # the pill; persisted per session; None clears
    def plan_switch(self, session_id: str, target: str) -> CarryPlan               # dry run: tier, characters, scrub counts, window source; no process
    def send(self, session_id: str, turn: ChatTurnIn, on_event=None) -> ChatTurnOut
    def stream(self, session_id: str, turn: ChatTurnIn) -> Iterator[ChatEvent]     # partial | block | usage | switched | turn_done
    def stop(self, session_id: str) -> bool
    def close(self) -> None
# ChatTurnIn: text, attachments[AttachmentRef], tag (function, node, purpose); ChatTurnOut: text, blocks, provider, model, usd, switched?
# ChatEvent kinds: partial {delta}, block {type: text|thinking|tool_use|tool_result, kind: read|edit|run|search|web|other, name, text}, usage, switched {from,to,plan}, turn_done
```

Rules the implementation must hold (each has a test in ABS-1 to ABS-3):
1. Per-chat choice, global default untouched: choosing Codex for one chat writes that session's connector, never the policy default; a new chat
   starts from the policy (the old `test_chat_local_provider.py` contract, re-expressed). The choice survives a restart (persisted in
   `chat_sessions`, today only an in-memory pin).
2. Only runnable providers are offered, each with the reason when not (old `providers.py` rule); API-key logins are refused (D7, D34).
3. A switch is `Router._chat` as built: new provider session, the first prompt starts with `render_carry_over`. Additions: the payload passes
   the egress scrub (2.4) and the model budget (2.5) before it is sent, and a `switched` event reports from, to and the plan.
4. Isolation: history, carry-over and the provider workdir are per session id; a session never reads another's messages (old
   `test_channel_isolation.py` and `shadow_context_isolation` re-expressed as "two sessions, one secret, never in the other's prompt").
5. Streaming: `stream()` yields partial text as the connector produces it; the orchestrator coalesces partials into SSE `chat.partial` events
   that are NOT stored and NOT in the replay ring (a reconnect gets the stored message, never half of one); the stored message is written once
   at `turn_done` (the same `state` pending then ok that `ChatMessage` already has).
6. Attachments: `AttachmentRef` points at a file in `<data>/attachments/<sha256>` (never inside a project folder, the old reason for not using
   `/api/org/attach`). Claude gets image and PDF as content blocks, Codex gets images with `-i` and PDFs and text as text cut at 40 000 characters
   with the cut said; a kind the connector cannot take is refused with its name, never dropped silently.
7. Folding ("condense"): the old condense is a presentation fold of tool noise, not a model summary. The port gives every `block` event a `kind`
   (from the ported `tool_kinds`), the store keeps blocks in `meta_json`, and `chat_view.js` draws a settled turn as ONE row ("12 tool calls:
   8 read, 3 run, 1 failed") that opens into the cards. No model call summarises a chat (D32 stays: carry-over is deterministic text).

### 2.3 Which old chat features move into it

| Old feature | Lands in | Package |
|---|---|---|
| provider pill and per-chat choice | `ChatPort.providers/choose`, `chat_sessions.connector` persisted; pill in `chat_view.js` and the J2 page header (injected by `dept_ext.js`) | ABS-1, ABS-6, ABS-9 |
| history that outlives a provider (segments) | `chat_segments` table (session, connector, native id, from message id), `ChatStore.segments()` | ABS-6 |
| typed blocks | optional `blocks` in the closed `ChatMessage`, stored in `meta_json` | ABS-6 |
| archive (a mark, never a delete) | `POST /api/chats/{sid}/archive` and `/unarchive` over the existing `status` and the D70 machinery | ABS-6, ABS-7 |
| search | `GET /api/chats/search?q=&scope=` over FTS5 | ABS-6, ABS-7 |
| scope and isolation | `scope=node:<id>|dept:<id>|all`; per-session history; `SUTRA_DATA_DIR` is the channel | ABS-7, ABS-1 |
| condense | `ChatEvent.kind` + `chat_view.js` fold | ABS-5, ABS-10 |
| attachments | `connectors/attachments.py`, `orchestrator/attachments.py`, upload route | ABS-4, ABS-7, ABS-10 |
| streaming | `RouterChatPort.stream`, SSE `chat.partial`, indicator in `chat_view.js` | ABS-1, ABS-7, ABS-9 |
| egress scrub and its audit row | `connectors/egress.py`, a Router hook for ALL calls | ABS-2 |
| per-model window | `connectors/budget.py`, used by the carry-over | ABS-3 |

### 2.4 Egress scrub (D109)

Old: scrub silently, log shape names and counts, never values. New, in the Router so it covers every port: before a prompt leaves for a CLI,
credential shapes (OpenAI/Anthropic-style keys, `ghp_`/`github_pat_`, AWS access keys, JWTs, bearer headers, private-key blocks, plus the
existing `Redactor` values) are matched. For `ChatPort` and `AsyncConnector` the match is replaced by `[redacted:<shape>]`. For `ModelPort` (J2's
agents) the scrub is **observe only**: it writes the audit row and changes nothing, because J2's prompts are not ours to edit (the same stance as
function nodes in observe mode, D52). The row (`<data>/connectors/egress.jsonl`, append only, 0600) holds time, session, provider, byte count and
shape names with counts; never a payload, never a match.

### 2.5 Model budget (D110)

Old: a replay is sized to the model's window, unknown model assumes the floor, divisor 3.0 characters per token because tool output is dense.
New: `budget.py` holds a table `{provider: {model: window_tokens}}`, `window_source` (`known` or `assumed-floor`) and `fits(chars)`. The carry-over
takes `min(J2 cap, budget)`: J2's `CHAT_FULL_CHARS` 60 000, `CHAT_TAIL` 40 and the 8 000-character digest (`connectors/transcript.py`) remain the
ceiling for every model, so a large window never makes a chat's carry-over bigger than J2's rule; a small one makes it smaller and says so in the
`switched` event.

### 2.6 Without changing J2 (the checklist each package is held to)

- No ABS package owns or edits `sutra_app/engine/j2*.py`, `engine/llm.py`, `engine/port.py` or `ui/pages/j2_ui.html`, except ABS-0 (the J2 sync),
  and ABS-0 changes them only by re-vendoring from the prototype with `scripts/vendor_j2.py` and `scripts/port_j2_ui.py`.
- `llm.ask`'s signature, `ScriptedPort`, `CompletionRequest` and `CompletionResult` are untouched; new fields would be additive and optional, and none is needed.
- The prompt goldens, the J2 API shape goldens and the vendored sha256 list still pass. They are in every ABS acceptance list that touches the Router.
- The scrub on the engine path is observe-only (2.4); the budget never raises a J2 cap (2.5).
- Anything the pill changes for a J2 run goes through `PortSpec.connector` (an existing field: `auto|claude|codex|stub`), set from the team's session
  choice when the run starts (ABS-8). The J2 page itself gets the pill by injection from `dept_ext.js`, not by a new port edit.

## 3. Work packages

The same format as `docs/build-plan.json`: id, title, owns (new paths only), depends_on, acceptance, spec. Edits to files that earlier packages own
(`router.py`, `schema.py`, `chats.py`, `chat_view.js`, route registration) are riders listed in each spec, and two packages never edit the same
existing file at the same time because their dependencies order them. `docs/build-plan.json` carries these rows; this table is the readable form.

| Id | Title | After | Owns (new) | Acceptance (short) |
|---|---|---|---|---|
| ABS-0 | J2 sync 2: the prototype's Run settings (runlist, changes) | E5, UI-9 | `docs/design/j2-sync-2.md` | port script `--check`, engine and prompt goldens, API shapes |
| ABS-1 | `ChatPort` protocol, models and `RouterChatPort` over the Router's `chat_*` | CN-9, E0 | `connectors/chat_port.py`, `connectors/chat_models.py` | `tests/connectors/test_chat_port.py` |
| ABS-2 | Egress scrub and audit row in the Router | ABS-1 | `connectors/egress.py` | `tests/connectors/test_egress.py`, prompt goldens |
| ABS-3 | Per-model window budget for the carry-over (lower-only) | CN-9 | `connectors/budget.py` | `tests/connectors/test_budget.py`, carry-over tests |
| ABS-4 | Attachments: store, kinds, Claude and Codex delivery | ABS-1 | `connectors/attachments.py`, `orchestrator/attachments.py` | `tests/connectors/test_attachments.py`, `tests/orchestrator/test_attachments.py` |
| ABS-5 | Tool-kind classification and typed block events | ABS-4 | `connectors/tool_kinds.py` | `tests/connectors/test_tool_kinds.py` |
| ABS-6 | Chat storage v2: migration, segments, blocks, FTS5, `legacy` kind, persisted choice | ORCH-8, L8 | `orchestrator/chat_v2.py` | `tests/orchestrator/test_chat_v2.py`, migration test |
| ABS-7 | Chat routes v2: search, archive, providers and choose, upload, send and stream through `ChatPort` | ABS-4, ABS-5, ABS-6 | `orchestrator/api/chat_v2.py` | `tests/orchestrator/test_api_chat_v2.py`, `tests/contracts` |
| ABS-8 | One choice for every surface: pins reach the org chat agent and each team's run | ABS-1, ABS-2, ABS-6 | `orchestrator/chat_choice.py` | `tests/orchestrator/test_chat_choice.py` |
| ABS-9 | UI: provider pill, streaming indicator, switch notice | ABS-7, ABS-8 | `ui/static/js/chat_pill.js` | `tests/ui/js/chat_pill.test.js` |
| ABS-10 | UI: fold, search, archive, attachments in the chat | ABS-7, ABS-9 | `ui/static/js/chat_fold.js`, `chat_search.js` | `tests/ui/js/chat_fold.test.js`, `chat_search.test.js` |
| ABS-11 | Library seed audit against the old templates | L7 | `scripts/audit_old_templates.py` | `tests/library/test_audit_old_templates.py` |
| ABS-12 | Import of the old app's chats (`sutra-pro import-old-chats`) | ABS-2, ABS-6, GAP-OPS-1 | `ops/import_old.py` | `tests/ops/test_import_old.py` |
| ABS-13 | End to end: switch, carry-over, search, archive, import with fake CLIs | ABS-9, ABS-10, ABS-12 | `tests/e2e/test_abs_chat.py` | `tests/e2e/test_abs_chat.py` |
| ABS-14 | User and developer documents for the merged app | ABS-13 | `docs/MIGRATING-FROM-SUTRA.md` | `tests/test_docs.py` |
| ABS-15 | UI: the composer of the direct chat (attach, send, stop, streaming row, pill respected) on the node panel and Home | ABS-9, ABS-10, ABS-13 | `ui/static/js/chat_composer.js` | `tests/ui/js/chat_composer.test.js`, `tests/e2e/test_browser_chat_composer.py` |

Order among the ABS packages (the global waves of `scripts/plan_tools.py waves` put them after everything already merged): first ABS-0, ABS-1, ABS-3,
ABS-6, ABS-11 (independent); then ABS-2 and ABS-4; then ABS-5, ABS-8, ABS-12; then ABS-7; then ABS-9; ABS-10; ABS-13; ABS-14. Critical path:
ABS-1, ABS-4, ABS-5, ABS-7, ABS-9, ABS-10, ABS-13, ABS-14. Each package is sized for one developer agent: one module, its tests, its note.

Details that are not in the JSON `spec` strings are in the notes the packages write (`docs/notes/ABS-n.md`). The ones worth fixing here:

- **ABS-1** also exposes `ProviderPill {name, ready, why_not, model, models[], plan, billing}` built from `Router.provider_summary`, and `CarryPlan {tier,
  chars, kept_messages, omitted, scrub, window_source}` from the existing `render_carry_over`. Ports of old tests: `test_provider_detect.py` (a provider
  that cannot run is not offered), `test_chat_local_provider.py` (per-chat choice, global default untouched).
- **ABS-2** ports the shape table of `switch_egress.py` and `test_switch_egress.py`; adds "engine path: observe only, text byte-identical".
- **ABS-3** ports `budget.py` and `test_budget` cases (floor assumed when the model is unknown, label); proves `min(J2 cap, budget)` never exceeds the J2 cap.
- **ABS-4** ports `shadow_attachments.py` and `test_shadow_attachments.py`: stored once by hash, image / PDF / text, the cut said; Claude stream-json
  blocks measured by the old module; Codex `-i` (CN-4 already knows `-i` is variadic and goes before `-m`).
- **ABS-5** ports `tool_kinds.py`; unknown tool name gives kind `other`.
- **ABS-6** migration `MIGRATIONS[n]`: `chat_segments`, `chat_messages_fts` (FTS5 over `text`, kept in step by triggers), `chat_sessions.kind`
  gains `legacy` (a table rebuild: the CHECK cannot be altered; copy, drop, rename, with foreign keys off for the step), `status` gains no new value;
  `ChatMessage.blocks` optional. Acceptance includes upgrading a populated v(n-1) file and a downgrade-refusal check.
- **ABS-7** rides on `orchestrator/api/chat.py` (registration only). Search returns rows `{session_id, message_id, title, snippet, at}`, never more than
  50, scope checked server side, archived only with `include=archived`. Upload accepts at most 20 MB and 10 files per message, token required (D81).
- **ABS-8** `RouteContext.session_id` is already set by `AsyncConnector`; this package makes `Router.plan` read the persisted choice (not only the
  in-memory pin) and makes the run launcher set `PortSpec.connector` from the team session's choice.
- **ABS-9/10** are pure string and DOM-free modules like `chat_view.js` (the UI's own convention), with node tests; they re-express the old
  `test_chat_pill.js`, `test_chat_condense.js`, `test_chat_search.js` and `test_chat_ai_provider.js` (the pill never offers a provider that cannot run).
- **ABS-11** is an audit with a seed step: it reads the old `function-templates/`, `artifact-templates/`, `engine-templates/` as data, prints the
  difference with Pro's seeds and adds the missing seeds through the write gate (log mode first, L8). It touches no old file.

## 4. Migration of existing user data

What exists on a machine that has run the old app (measured here, counts only): `~/.sutra-ui/chats/` holds 49 chat records (`<sutra_id>.json` plus
`_index.json`), 238 messages in all, 46 chats non-empty, the longest 124 messages; their segments are 47 Claude and 3 DeepSeek. Beside them are
`chat-archive.json` (archive marks), `agents/`, `archive/`, `drafts/`, `connectors.json`, `local.json` (settings) and caches. The org registry
lives elsewhere and is not read.

Decision (D113): an explicit, opt-in, one-way import of chats only. Nothing is migrated silently; nothing in the old folder is written,
moved or deleted (D98: the old product is read-only).

- Command: `sutra-pro import-old-chats [--source ~/.sutra-ui/chats] [--apply]`. Dry run by default: prints the number of chats and messages and
  what would be flattened. `--apply` first takes the existing `sutra-pro backup`, refuses while another Sutra Pro instance holds the data lock
  (D94), then writes in one transaction per chat.
- Mapping: one old chat becomes one `chat_sessions` row, id `cs_old_<first 12 of sutra_id>`, `kind='legacy'`, `node_id='legacy'`, `status='archived'`,
  `writable=0`, title kept, note `Imported from old Sutra, folder <last path part of cwd>`, `connector` = the last segment's provider when it is
  `claude` or `codex`, else empty (a DeepSeek chat is history only). Every imported chat is read only and archived, so the "one active session per
  node" index is never touched; it appears under "Older chats" and in search.
- Messages: user to `user`, assistant to `agent` (`who='old Sutra'`), timestamps from `ts`. Typed blocks: `text` is the message; `tool_use` and
  `tool_result` collapse into one `note` message per assistant turn that lists tool names and counts (no tool input or output: size and secrets);
  `thinking` is dropped. A legacy `{role,text,ts}` message is a text message. `src_ref = old:<sutra_id>:<index>` makes a second run change nothing
  (`ChatStore.post` already refuses a stored `src_ref`).
- Scrub: every text goes through `Redactor` and the egress shapes (ABS-2) before it is stored; a count of scrubbed shapes is printed.
- Not imported, and said so by the command: archive marks (everything imported is archived), provider transcripts under `~/.claude` and
  `~/.gemini`, the registry of departments (tell the chat agent what teams you want; it builds the chart), settings, agents, drafts, connectors.
- A newer Sutra Pro opening a data folder from an older one is the ordinary `Database.migrate()` path (ABS-6's migration); there is no
  Pro-to-old export.

## 5. Risks

1. **Router is shared by every surface.** A scrub or budget bug would reach J2's agents. Mitigation: engine path observe-only, J2 caps are a ceiling,
   prompt goldens and the vendored hash list in every acceptance, ABS-2 and ABS-3 land before any UI.
2. **Table rebuild migration (ABS-6).** SQLite cannot alter a CHECK. A mistake loses sessions. Mitigation: copy-drop-rename inside one transaction,
   a test that upgrades a populated database and compares row counts and `last_message_id`, `Database.close()` rules of D104 respected.
3. **D7 versus DeepSeek and Claude usage windows.** Both old features need a key or another application's token. Deferred or dropped, not
   bent. The owner may lift D7; D112 says what that would take (a third connector behind the same seam, no change to `ChatPort`).
4. **Partial text and the event ring.** Streaming text in the replay ring would replay half a message after a reconnect. Rule 5 keeps partials
   out of the ring; a test reconnects mid-turn.
5. **Search leaks scope.** FTS across all chats could return a message from a chat the page is not allowed to show. Scope is applied in SQL, not in the
   page, and tested with an archived and a merged-away session.
6. **Attachment safety.** PDF and text go to a model; a hostile PDF is data, never instructions. Same prompt framing as chat text; size limits; content
   type by sniffing, not by name.
7. **J2 moves again.** The prototype's `prototypes/j2` copy in the old repository is already ahead of the vendored baseline `33aeeda` (two more
   routes, `/api/runlist` and `/api/changes`, and 1,166 changed lines in the page). ABS-0 syncs it; the source of truth is the J2 prototype's own
   repository, the copy is used only if the change has not reached it yet, and `VENDORED.md` records which.
8. **A goal that outlives its attempts (row 32).** Replaced by follow-up tasks, but the old "a failed mission does not end the goal" behaviour has no
   explicit test in Pro. Left as an open question for the owner, not a package.
9. **Scope creep through LATER.** Routines, modules, apps, the updater and DeepSeek are real wants. They are listed with triggers so that none is
   started without the owner's word.
10. **Old repository is read only.** The importer reads `~/.sutra-ui` but nothing under `marketplace/`; a test asserts the old folder's files are
    byte-identical after `--apply`.

## 6. Open decisions for the owner (all have a default, none blocks)

- Lift D7 for a DeepSeek connector? Default: no.
- Does an owner-archived chat keep its node's active slot free (a fresh chat starts), as D70 does for merges? Default: yes.
- Import old chats at first start with a prompt, or only by the command? Default: only by the command.

## 7. Summary of verdicts

46 rows (the inventory groups several old modules into one row where they do one job). Primary verdict per row:

| Verdict | Rows | Which |
|---|---|---|
| PORT | 11 | chat record and segments, owner archive, search, egress scrub, model budget, chat folding and streaming indicator, attachments, tool kinds, per-chat provider that sticks, seed-template audit, the chat tests |
| REPLACED | 19 | provider catalogue and adapters, process transports, Codex sign-in and models, usage windows, mediated connectors, owner models, org and department APIs, reorg simulation, old engine and J2 adaptor, function screens, website department, goals, library shelves, agent tool surface and proposals, the FastAPI monolith, the chat scope setting, the switch planner |
| DROP | 8 | transcript parsers and session browser, Claude account resolver (reads another app's token), Shadow engine and mission engine, daemon window, workspace and git pane, Electron shell, old test seeding; project auto-import (its chat-led form is LATER) |
| LATER | 8 | slash-command palette, text provider switch, DeepSeek (blocked by D7), SEO agent as a template, routines, modules, apps platform, in-app updater |

Secondary verdicts inside rows: row 26 (project import) is DROP for the automatic form and LATER for a chat-led import of one folder; row 35 (Shadow)
names its salvaged parts, which are counted under their own rows (7, 11, 12) or as REPLACED; row 16 is REPLACED with one rule moved into ABS-1.
