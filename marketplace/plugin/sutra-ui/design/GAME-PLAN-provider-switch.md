# Game plan — mid-chat provider switching

Switch the active AI provider inside one live chat, carrying the whole prior conversation across, with no summarisation anywhere.

- **title**: Mid-chat provider switching (Claude <-> DeepSeek)
- **status**: COMPLETE · all 7 pieces shipped · 388 python + 14 js suites green
- **scope**: `marketplace/plugin/sutra-ui` — chat store, `providers.py`, `acp_runtime.py`, `app.py:ws_chat`, `session_reader.py`, panel JS
- **owner**: Sutra core
- **updated**: 2026-09-02
- **source inputs**: founder decisions 2026-09-02 (this session) · founder comparison table "Method 2: Gossip" · measurements over 24 Claude + 33 DeepSeek transcripts on the founder machine · DeepSeek published pricing · bundled `claude-api` rate reference (cached 2026-06-24)

---

## Verdict

**Decision** — buildable as specified. Method 2 (replay the prior conversation as a prompt) works verbatim at the founder's stated scale of 50 turns. No summariser is required at any point.

| Question | Answer |
|---|---|
| Possible? | Yes |
| Summarisation needed? | No |
| Blocking work before code? | One gate — model-id / context probe |
| Pieces to build | 7 |
| Half the data model already exists? | Yes |

## What already exists

| Capability | State | Evidence |
|---|---|---|
| `provider_history` schema | Now read AND written | `chat_store.py` — format matched to the 2026-09-01 records |
| Reverse map `provider:native_id` -> `sutra_id` | Now maintained | `chat_store.resolve` / `chat_store.index` |
| Cross-provider session listing | Shipped | `session_reader.py:346` |
| DeepSeek transcript parser (3 record shapes, dedup by id) | Shipped | `session_reader.py:155` |
| Claude transcript root | Shipped | `session_reader.py:17` |
| DeepSeek transcript root | Shipped | `session_reader.py:25` |
| DeepSeek adapter registered | Shipped | `providers.py:416` |
| DeepSeek in provider catalog | Shipped | `providers.py:421` |
| Sutra MCP server, ACP-shaped | Shipped | `app.py:272` |

**Open question** — the `provider_history` files match this feature's needs exactly but the string appears in no checkout, no plugin cache version, and not in the app payload. Provenance unknown.

## Measured evidence

### Transcript composition

**Current rule** — every figure below is produced by `transcript_ir.stats()` over the real trees, not by an ad-hoc script. Reproduce with the aggregate in `test_transcript_ir.RealTreeSmokeTest`.

| Measure | Claude | DeepSeek |
|---|---|---|
| Transcripts | 24 | 33 |
| User turns | 126 | 49 |
| Replayable text | 3.47 MB | 0.53 MB |
| Tool I/O | 79.8% | 43.9% |
| Conversation | 20.2% | 8.9% |
| Reasoning | 0.0% | 47.2% |

**Inference** — BOTH providers are tool-I/O dominated. Claude carries no persisted reasoning at all; DeepSeek's reasoning is real but sits on a payload an order of magnitude smaller.

**Migration note** — an earlier revision of this section reported Claude `tool_result` at 86.4% and DeepSeek `thoughts` at 85.0%, and called the two providers "near mirror-images". Both figures measured STORED JSON BYTES, and the DeepSeek one never parsed `toolCalls`. DeepSeek stores reasoning as per-token fragments each carrying a full ISO timestamp, so 91.2% of that field is scaffolding — 4.20 MB stored holds 368 KB of text. The mirror-image claim was an artifact of that and is withdrawn.

### Replay size

| Source | Median chars per user turn | 50 turns |
|---|---|---|
| Claude, everything | 21,871 | ~273k tokens |
| DeepSeek, everything | 3,185 | ~40k tokens |
| DeepSeek, reasoning dropped | ~1,680 | ~21k tokens |

Raw Claude JSONL is 76% scaffolding (uuids, timestamps, `parentUuid`, repeated cwd) that no replay sends. Token figures assume 4 chars/token; `stats()` returns characters because a real count needs a tokenizer the module does not own.

### Context ceilings

| Model | Window |
|---|---|
| DeepSeek V4 (all current) | 1M |
| Claude Opus 5 | 1M |
| Claude Sonnet 5 | 1M |
| Claude Haiku 4.5 | 200K |

**Decision** — the budget check reads the SELECTED MODEL's window, never a per-provider constant. Haiku is the trap: `providers.py:374` offers it and it is 5x smaller than every sibling.

### Cost per switch

Claude -> DeepSeek, 273k input tokens, always a cache miss:

| Model | Off-peak | Peak |
|---|---|---|
| `deepseek-v4-flash` | $0.060 | $0.120 |
| `deepseek-v4-pro` | $0.180 | $0.360 |

DeepSeek -> Claude, 50 turns:

| Model | With reasoning (~40k) | Reasoning dropped (~21k) |
|---|---|---|
| Opus 5 | $0.20 | $0.11 |
| Sonnet 5 | $0.08 | $0.04 |
| Haiku 4.5 | $0.04 | $0.02 |

**Inference** — Opus 5 input is 23x `deepseek-v4-flash` off-peak per token, but the DeepSeek payload is ~7x smaller, so the two directions land within a factor of ~3 of each other in absolute cost. Neither direction is expensive enough for cost to drive a design decision.

### Cache behaviour

DeepSeek transcripts record per-turn usage. One observed sample:

```json
{"input": 48473, "output": 951, "cached": 48384, "thoughts": 0, "tool": 0, "total": 49424}
```

99.8% cache hit on a continuation turn. **Inference** — the replay prefix is cached from the turn after the switch, so the expensive payload subsidises every turn after it. Cache-hit input is $0.007/1M off-peak against $0.22 for a miss.

## Decisions locked

Founder, 2026-09-02, this session.

| # | Decision | Consequence accepted |
|---|---|---|
| D1 | Chat identity is SEGMENTED — one `sutra_id`, N provider sessions | Chat record becomes authoritative over provider-native transcripts |
| D2 | Everything the prior provider used crosses the boundary | Renderer must label tool calls as already-executed |
| D3 | Egress scrub runs SILENTLY, no prompt | A scrubber miss is invisible; an audit log is therefore mandatory |
| D4 | Replay once at switch; turns after send only the new prompt | A lost native session means amnesia, surfaced not repaired |
| D5 | No summariser | Superseded D5-draft (Claude summarises at switch), which failed because the founder's own scenario is Claude being out of credits |

**Migration note** — an earlier draft of this plan carried a rolling-summary tier as an assumption. It is deleted. Measurement showed the summariser was solving a problem that does not exist at 1M context.

## Direction-specific replay rules

**Decision** — the renderer is direction-aware. One format, two filters.

| Direction | Keep | Drop | Rationale |
|---|---|---|---|
| Claude -> DeepSeek | tool I/O | nothing | tool I/O is 79.8% of the transcript and is the substance of the work |
| DeepSeek -> Claude | conversation, tool I/O | reasoning | 47.2% of a small payload; one model's chain of thought is noise to another and would arrive as billed plain text |

Neither filter is summarisation. Nothing is condensed.

**Migration note** — the reasoning filter was originally justified as an 85%-of-volume saving. Corrected: it saves 47.2% of a payload that is already ~7x smaller than the other direction's. The filter is kept because replaying another model's private reasoning is wrong on its own terms, not because it is a material cost lever.

## The verbatim ladder

| Tier | Payload | 50 turns | Breaks at |
|---|---|---|---|
| 1 | everything verbatim | ~273k tokens | ~180 turns |
| 2 | conversation verbatim, tool I/O read on demand | ~41k tokens | ~2,800 turns |

Tier 2 retrieval rides the MCP channel already wired at `app.py:272`. Tier 2 is reached only past tier 1's ceiling.

## The seven pieces

| # | Piece | Impact | Effort | State |
|---|---|---|---|---|
| 1 | Chat record — `chat_store.py`, typed blocks, `provider_history`, reverse index | High | M | **DONE** 2026-09-02, 22 tests |
| 2 | Transcript IR — `transcript_ir.py`, both trees to typed blocks, uncapped, plus `stats()` | High | M | **DONE** 2026-09-02, 24 tests |
| 3 | Replay renderer — `replay.py`, nonce-fenced prompt, tool calls framed as executed | High | S | **DONE** 2026-09-02, 25 tests |
| 4 | Session seeding — `switch.py`, plan/confirm split, fence + argv gates | High | M | **DONE** 2026-09-02, 22 tests |
| 5 | Context budget — `budget.py`, per-model window, tier-2 trigger | Med | S | **DONE** 2026-09-02, 24 tests |
| 6 | Silent scrub + audit log — `switch_egress.py`, `shadow_egress.scrub_detail` | Med | S | **DONE** 2026-09-02, 22 tests |
| 7 | Per-chat provider + UI — `ws_chat` params, composer switcher, thread marker | Med | M | **DONE** 2026-09-02, 6 py + 18 js tests |

### Piece 3 detail — the trust boundary

**Decision** — a replay is an untrusted-content channel, not just a long prompt. The transcript carries file contents and command output that nobody vetted, delivered to a model that will act on what it reads.

| Threat | Defence | Pinned by |
|---|---|---|
| Receiving model reads a record of past mutations as a plan and re-applies them | every tool call rendered past-tense with its result, under a framing block stating the actions already ran against the real filesystem | `test_every_tool_call_is_framed_as_already_executed` |
| Tool output containing "SYSTEM: ignore previous instructions" is read as instruction | transcript wrapped in a fence whose tag carries a per-call `secrets.token_hex` nonce; content cannot close a fence whose name it never saw | `test_injected_instruction_cannot_escape_the_fence` |
| Content happens to carry the live nonce | `fence_is_intact()` counts markers and fails closed; piece 4 must refuse to send a payload that fails it | `test_fence_is_intact_detects_a_leaked_nonce` |

**Decision** — the framing prose never writes the literal marker tags. Naming them in prose put three copies of each in the prompt, which made a forged closing tag indistinguishable from a legitimate mention and made the integrity check inspect the wrong region. Found by the two fence tests on first run.

**Decision** — reasoning is dropped in BOTH directions, not only DeepSeek to Claude. One model's private chain of thought is a fact about that model, not about the session. Claude persists none (0.0% of characters), so the symmetric rule costs nothing and removes a per-direction branch.

**Decision** — an EMPTY dropped block is not an omission and is not announced. Current Claude models default `thinking.display` to `"omitted"`, so thinking blocks arrive with empty text; counting them made a real replay claim "24 blocks of private thinking omitted" when the transcript carried no reasoning at all.

Measured on real transcripts after the fix: Claude source drops 0 blocks; DeepSeek source drops 36 reasoning blocks worth 118 KB; tier 2 takes one real 73-turn transcript from 201,754 to 64,310 characters.

### Piece 4 detail — the two transports

| Provider | Existing primitive | Seeding path |
|---|---|---|
| Claude | `build_agent_args` at `app.py:319` | `session_id=None` (no `--resume`), `stream_input=True`, replay as a stdin frame |
| DeepSeek | `build_acp_args` at `app.py:429` | `new_session(session_id=None)` forces the `session/new` branch (`acp_runtime.py:488`), then `prompt_turn(payload)` |

**Inference** — the founder table's "SYMMETRIC, one code path" cell is one FORMAT with two injection sites, not one code path. Both transports do return the new session id in the same tuple position, though (`app.py:2083` and `app.py:2090`), so recording the segment IS one code path.

**Decision** — `plan()` and `confirm()` are separate calls. A segment records a session that EXISTS; writing it at plan time would leave a `from_turn` pointing at a session the transport may never create (missing binary, `session/new` error, spawn death), and the next reconnect would resume a thread that was never born.

**Decision** — the replay is delivered over STDIN, never argv, and this is not a style preference.

| Fact | Value |
|---|---|
| `ARG_MAX` (measured, this machine) | 1,048,576 bytes |
| 50-turn Claude replay | ~1.09 MB of text |
| argv delivery at that size | fails with E2BIG at exec, before any frame reaches the socket |
| What `ws_chat` already does | `stream_input=True` on both spawn paths (`app.py:2001`, `app.py:2021`) — the live path is safe |
| What `build_agent_args` defaults to | `stream_input=False`, i.e. argv — one forgotten keyword from a size-dependent failure |

`switch.argv_would_fail()` answers this directly and `plan()` returns `argv_unsafe`, because the failure it predicts is silent, late, and only appears on long chats.

**Decision** — every refusal is a reason code plus operator-readable text, not an exception: "no switch happened, and here is why" is the feature's honesty contract, and a traceback is not something the panel shows anyone. Codes: `not-needed`, `no-source-session`, `source-transcript-unreadable`, `fence-integrity-failed`, `over-context-budget`, `unknown-target-provider`.

**Decision** — an unreadable source transcript refuses rather than seeding an empty recording. An empty replay looks to the receiving model like a conversation that never happened, so it would answer turn 51 as if it were turn 1.

Verified end to end against a real 786 KB Claude transcript: tier 1 carried 201,802 characters; a budget of 80,000 dropped to tier 2 automatically at 64,358 characters with 25 calls and 25 results elided; a budget of 5,000 refused with both numbers and sent nothing.

### Piece 5 detail — the budget, and being wrong in the safe direction

**Decision** — the ceiling is keyed on the MODEL, never the provider. `providers.py:374` offers `haiku` and Haiku 4.5 holds 200K where Opus 5 and Sonnet 5 hold 1M, so a provider-keyed budget is five times too generous the moment haiku is selected, and the failure lands at the API after the payload was built and sent.

| Model id in the picker | Window | Budget in characters |
|---|---|---|
| `opus` | 1,000,000 | 2,613,600 |
| `sonnet` | 1,000,000 | 2,613,600 |
| `haiku` | 200,000 | 453,600 |
| `""` (CLI default) | assumed 200,000 | 453,600 |
| DeepSeek V4 (all current) | 1,000,000 | 2,613,600 |

**Decision** — two unknowns, resolved toward degraded success rather than hard failure.

| Unknown | Understating costs | Overstating costs | Choice |
|---|---|---|---|
| Window when no model is selected | a rejected request, no switch at all | one needless tier-2, switch still works | floor, with `window_source: "assumed-floor"` and a note naming the fix |
| Characters per token (no tokenizer available locally) | an overrun | a needless tier-2 | **3.0**, below the prose figure of ~4, because the payload is 79.8% tool I/O and code/JSON tokenize denser |

Reserves: 32,000 tokens for the reply and the turns after it (not the models' 128K/384K output ceilings, which would surrender a third of a 1M window), then a further 10% discount because an estimated token count needs margin of its own.

**Decision** — omitting `budget_chars` from `switch.plan` now DERIVES the budget; `switch.UNBOUNDED` is the explicit opt-out. A plain absent value cannot mean "no ceiling", because absent is what a forgetful caller sends.

**Inference** — the budget guard and the argv guard are independent and both needed: a 1M-token window is 2,613,600 characters, while `ARG_MAX` is 1,048,576. A payload can fit the model and still be unsendable as a positional argument.

Verified on real transcripts, both directions:

| Source | Target | Outcome |
|---|---|---|
| Claude, 786 KB, 73 turns | DeepSeek (1M) | tier 1, 201,754 characters |
| DeepSeek, 2,386 KB, 49 turns | Claude Opus (1M) | tier 1, 69,668 characters, 36 reasoning blocks / 118,140 characters dropped |
| DeepSeek, same | Claude Haiku (200K) | tier 1, fits — the payload is small once reasoning is dropped |
| DeepSeek, same | Claude, no model selected | tier 1, window reported as `assumed-floor` |

### Piece 6 detail — the scrubber, and what it deliberately does not do

**Decision** — one scrubber, extended, not a second one. `shadow_egress` gained `scrub_detail()` returning `{shape: count}`; `scrub()` still returns `(clean, n)` so `app.py:1718`, `sutra_mcp.py:349` and `mission_engine.py:331` are untouched. Two credential pattern lists in one codebase drift, and the one that drifts is the one nobody is looking at.

**Decision** — `bin/peer-review-payload-scrub.sh` was rejected despite covering more shapes: it caps at 512,000 bytes and replay payloads reach 2,613,600, so it would exit 3 on exactly the chats that matter. Its extra credential shapes were ported into `shadow_egress` instead.

| Shape added 2026-09-02 | Why it matters for a replay specifically |
|---|---|
| `jwt` | appears in file content and `env` dumps, never in a one-line Shadow message |
| `pem-private-key` | a whole key block can sit inside one `tool_result` |
| `stripe-key` | same |
| `slack-webhook`, `discord-webhook` | same |
| `db-uri-credentials` | userinfo only — host and database name are kept |
| `private-key-env` | `API_KEY = "..."` shapes from config dumps; the key NAME is kept |

**Decision** — path and PII normalisation are NOT applied. The shell scrubber rewrites `$HOME` and `/tmp` and redacts email and phone because it ships a diff to an outside reviewer. A replay hands the receiving assistant a record of work on real files that it then has to read; normalising those paths would break the handover to protect nothing, since both providers run on the same machine.

**Decision** — order is render, scrub, RE-verify the fence, send. Scrubbing is the last mutation, and a boundary verified before the final mutation is not verified.

**Decision** — the audit row records shape names and counts, never matched values. A log that recorded what it caught would be a second plaintext copy of every secret, in a file that exists precisely because nobody is watching.

First live run against the largest real transcript (7.0 MB, 494 turns, 17 user turns): 383,495 characters rendered, **one `openai-key` shape found and redacted**, fence intact, `sent: true`.

### Piece 7 detail — a switch IS a reconnect

**Decision** — the provider is carried on the socket URL (`?provider=`), not as a message field, and changing it DROPS the socket.

`ws_chat` resolves the provider once per connect and binds the binary AND the runtime type to it — Claude's `stream-json` process and DeepSeek's ACP process are different programs speaking different protocols (`app.py:2001` vs `app.py:2005`). Per-message provider would require rewriting the riskiest function in the panel. But the handshake already does everything a switch needs: resolve the provider, validate the binary, check the DeepSeek key, spawn the right runtime. So a switch is exactly a new connect.

**Inference** — this is the same mechanism `setSessCwd` already uses for the working directory, for the same reason: both are spawn-time properties, and a control that merely relabelled a running pane would claim something the server cannot deliver. The mid-turn guard is copied too — closing while a reply streams would discard it, so that case is refused with a reason.

| Param | Meaning | Absent means |
|---|---|---|
| `?provider=<id>` | run THIS chat on this provider | use the global setting |
| `?sutra=<id>` | the durable chat whose history to carry | no carry-over — the handler behaves exactly as before piece 7 |

**Decision** — the whole server-side feature is gated on those params, so every existing caller is unaffected. `test_no_param_still_resolves_the_global_provider` pins it.

**Decision** — an unknown or unrunnable requested provider is REFUSED at the handshake, never silently swapped for the global one. A pane that answers as Claude after the operator picked DeepSeek is worse than one that says why it cannot.

**Decision** — `switch.confirm` runs after the turn, beside `register_runtime`, not beside `switch.plan`. Both transports return the new session id in the same tuple position, so recording the segment is one code path even though seeding is two.

**Decision** — a failed carry-over never fails the turn. The turn runs without the history and the thread shows a marker saying so, because the alternative is a new provider silently answering turn 51 as though it were turn 1.

## Blocking gate — CLOSED 2026-09-02

**Decision** — cleared before piece 1. The 1M headroom applies; tier 1 is the default path.

| Check | Result |
|---|---|
| Models the account can reach (`GET /models`) | `deepseek-v4-flash`, `deepseek-v4-pro`, `deepseek-v4-flash-vision-exp` |
| `deepseek-chat` / `deepseek-reasoner` served? | No |
| Model recorded in real transcripts | `deepseek-v4-flash`, 255 of 255 turns |
| Latest recorded turn | 2026-09-01T14:29Z |

**Historical context** — the CLI bundle and `test_acp_quota.py:29` both mention `deepseek-chat`, which suggested the integration was pinned to a model retired 2026-07-24. It is not: that string is a stale fixture, and the live CLI reports `deepseek-v4-flash` on every turn.

## Test inventory

Per PROTO-000. **Current rule** — the names below are the tests that exist; run with `.venv/bin/python -m unittest test_chat_store test_transcript_ir test_replay test_switch`.

Shipped, 163 tests across all 7 pieces:

| Test | Piece | Asserts |
|---|---|---|
| `test_provider_history_after_50_turns_and_a_switch` | 1 | 50 Claude turns plus one switch produces exactly two segments with correct `from_turn` |
| `test_legacy_record_upgrades_on_read` | 1 | the 2026-09-01 `{role,text,ts}` records still load, as typed blocks |
| `test_upgrade_does_not_rewrite_the_file` | 1 | a read-time upgrade never touches a record it may have misparsed |
| `test_unsafe_id_never_reaches_the_filesystem` | 1 | `sutra_id` is not a path-traversal parameter |
| `test_tool_result_is_not_truncated` | 2 | no `_RESULT_CAP` in the replay path |
| `test_full_input_is_kept_not_summarised` | 2 | the whole tool input dict survives, not one 600-char key |
| `test_sutra_routing_preamble_is_stripped` | 2 | Sutra's `PLACEMENT:` block is not replayed as operator text |
| `test_last_write_wins_by_id` | 2 | a DeepSeek turn rewritten in place yields one turn, not two |
| `test_every_tool_call_is_framed_as_already_executed` | 3 | risk 1 — past-tense framing plus an explicit do-not-repeat rule |
| `test_injected_instruction_cannot_escape_the_fence` | 3 | risk 8 — hostile tool output cannot close the real fence |
| `test_fence_is_intact_detects_a_leaked_nonce` | 3 | the boundary check fails closed |
| `test_empty_dropped_blocks_are_not_announced` | 3 | no phantom omission notices |
| `test_claude_transport_never_resumes_and_uses_stdin` | 4 | `session_id=None`, `stream_input=True` |
| `test_argv_guard_flags_a_fifty_turn_replay` | 4 | a payload over `ARG_MAX` is flagged, not exec'd |
| `test_confirm_writes_the_segment_only_after_the_session_exists` | 4 | `plan()` alone does not touch `provider_history` |
| `test_unreadable_source_transcript_is_refused_not_seeded_empty` | 4 | a missing transcript refuses instead of seeding an empty recording |
| `test_fence_failure_refuses_rather_than_sending` | 4 | a broken data/instruction boundary sends nothing |
| `test_describe_never_reports_a_switch_that_did_not_happen` | 4 | the operator line cannot claim a refused switch |
| `test_haiku_is_not_given_its_siblings_window` | 5 | the trap: 200K, not 1M |
| `test_cli_default_falls_to_the_floor_and_says_so` | 5 | unknown window assumes the floor and names the fix |
| `test_every_catalogued_model_has_a_window_or_is_the_default` | 5 | a new picker entry cannot inherit a wrong ceiling |
| `test_token_estimate_rounds_up` | 5 | rounding down can pass a payload that does not fit |
| `test_budget_is_derived_when_not_supplied` | 5 | omitting a budget does not mean "no limit" |
| `test_budget_and_argv_guards_are_independent` | 5 | 2.6M-char window vs 1MB ARG_MAX |
| `test_planted_secrets_do_not_reach_the_payload` | 6 | seven credential shapes redacted and counted |
| `test_audit_row_never_contains_the_secret_it_caught` | 6 | the log records shape names, never values |
| `test_real_file_paths_are_not_normalised` | 6 | paths survive; the target has to read them |
| `test_fence_is_reverified_after_scrubbing` | 6 | the boundary is checked after the last mutation |
| `test_broken_fence_after_scrub_refuses_and_logs_not_sent` | 6 | a refused switch is logged as unsent |
| `test_unwritable_log_does_not_stop_a_switch_but_is_reported` | 6 | an audit failure is surfaced, never swallowed |
| `test_unknown_provider_is_refused_by_name` | 7 | no silent fallback to the global provider |
| `test_a_runnable_override_is_honoured_and_labelled_chat` | 7 | source reads `chat`, not the global setting |
| `test_no_param_still_resolves_the_global_provider` | 7 | absent the new params the handshake is unchanged |
| `switching provider DROPS the socket` (js) | 7 | both channels close; it cannot be relabelled |
| `a mid-turn switch is refused with a reason` (js) | 7 | a streaming reply is never discarded |
| `a failed carry-over is surfaced, never swallowed` (js) | 7 | the marker states a refusal |
| `FounderScenarioTest.test_full_round_trip` | 1-4 | 50 Claude turns, plan, confirm, two segments, per-turn ownership |

Still to write, with their pieces:

| Test | Piece | Asserts |
|---|---|---|
| DeepSeek-shaped title derivation | — | `test_app.test_52` skips DeepSeek rows for the title invariant; that shape needs its own test |

## Risk register

| # | Risk | Severity | Mitigation |
|---|---|---|---|
| 1 | Replayed tool I/O reads as instruction; target re-runs a mutation it was only told about | MITIGATED | Piece 3 past-tense framing + explicit do-not-repeat rule; `test_every_tool_call_is_framed_as_already_executed` |
| 8 | **Prompt injection via replayed tool output** — unvetted file contents and command output reach a model that acts on them | MITIGATED | Nonce fence + data-not-instruction framing + `fence_is_intact()` fail-closed; `test_injected_instruction_cannot_escape_the_fence` |
| 2 | Haiku's 200K window treated as 1M | MITIGATED | `budget.py` keys on the model; `test_haiku_is_not_given_its_siblings_window` |
| 3 | Silent scrub miss is undiscoverable | MITIGATED | `switch-egress.jsonl` records shape names and counts per switch, 0600, append-only with flock; `test_audit_row_never_contains_the_secret_it_caught` |
| 4 | Lost native session shows as amnesia | Med | Accepted per D4; surfaced by `test_session_loss_surfaced` |
| 5 | CLI pinned to a retired model id | CLOSED | Gate cleared 2026-09-02: live model is `deepseek-v4-flash` |
| 6 | `provider_history` schema origin unknown; a prior design pass may conflict | Low | Still open. Piece 1 matched the on-disk format byte-for-byte rather than resolving it |
| 7 | My own measurements twice reversed a design conclusion | Med | Numbers now come from `transcript_ir.stats()`, exercised by tests, not from ad-hoc scripts |

## Deferred

| Item | Why not now |
|---|---|
| Stripping Sutra's governance blocks from replayed ASSISTANT turns | **Open question.** `_strip_preamble` removes the `PLACEMENT:` block from operator turns, but an assistant turn's `INBOUND·DIRECT` / `INPUT:` / `TYPE:` / `ROUTE:` / `FIT CHECK:` scaffolding is replayed verbatim, so the receiving model both sees and tends to imitate it. Precedent exists for treating it as chrome — the panel's `parseGov()` already strips it from displayed prose (`static/js/05-chat.js:741`). Founder call: is Sutra's governance output part of the conversation or part of the frame? |
| Auto-repair of a lost native session | Founder declined the variant; cheaper to add than to debug later |
| Cost preview before a switch | Founder chose silent egress; a cost prompt would reintroduce the dialog |
| Provider-aware model catalogue | Needed only once DeepSeek model selection is exposed in the panel |

---

provenance: {author: claude (session ad9c0193), date: 2026-09-02, inputs: [founder decisions 2026-09-02, founder comparison table Method 2 Gossip, transcript_ir.stats() over 24 Claude + 33 DeepSeek transcripts, DeepSeek GET /models live probe, DeepSeek published pricing, bundled claude-api rate reference cached 2026-06-24], review: none, supersedes: v1 same path (composition figures measured stored bytes, not replayable text), confidence: high, gaps: [provider_history schema provenance still unknown; token figures assume 4 chars/token with no tokenizer in the loop; pieces 3-7 unbuilt]}
