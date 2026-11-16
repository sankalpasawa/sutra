# Streaming chat: what the real CLIs emit (capture notes)

Work package STR-1. Captured on 2026-11-14 on macOS with `claude` 2.1.308 and `codex-cli` 0.146.0, through the product's own connectors, by
`SUTRA_LIVE=1 scripts/py scripts/capture_connector_fixtures.py --stream` (four model calls: one tool turn and one Stop turn per CLI). Fixtures:
`tests/fixtures/connectors/claude/stream_partials_tool_ok.jsonl`, `codex/exec_tool_items_ok.jsonl`, `timing/stream_timing.json` (arrival time and type of
each line, never content). The facts below are asserted by `tests/connectors/test_stream_fixtures.py`, so a new CLI version that changes one fails a test.
Everything here is one macOS run; nothing is claimed for Windows or for any other CLI version.

## How the capture is made, and kept clean

The script builds the product's `ClaudeConnector` or `CodexConnector` (the real `build_command`, flags, environment allowlist, parser) and swaps its
`runner` for a recording subclass that keeps every stdout line of the turn with its arrival time. The turn runs in a scratch folder holding one file
(`notes.txt`), read-only tools. Scrubbing: the home directory, the scratch path, the account identity, and streamed values split across deltas (a path cut in
the middle of a delta is joined, scrubbed and cut again into the same number of pieces; the first real capture had a scratch path in six pieces that a
per-string scrub would have missed). A file is written only when the audit finds nothing, on the joined deltas as well as on each line: no identifier
of `scripts/ownership-audit.sh` (the pattern is read from that script, so this script does not carry it), no home or user path, no scratch path.
`--plan` shows the steps without running a model.

## Claude (`claude -p --output-format stream-json --verbose --include-partial-messages`)

Order of the lines of one tool turn (the real one, two assistant messages):

| Step | Lines |
|---|---|
| start | `system/init`, `system/status requesting` |
| message 1 | `stream_event message_start`, `content_block_start` (index 0, `tool_use`, `id` `toolu_...`, `name` `Read`, `input {}`), `content_block_delta input_json_delta` x6 (a burst; the first is empty), then the complete `assistant` message (the whole `tool_use` with its full input), **then** `content_block_stop`, `message_delta`, `message_stop` |
| tool | `rate_limit_event`, `user` (a `tool_result` with the same `tool_use_id`) |
| message 2 | `system/status`, `message_start`, `content_block_start` (index 0, `text`), `text_delta` x4 (a burst), the complete `assistant` text message, then `content_block_stop`, `message_delta`, `message_stop` |
| end | `result` (its `result` is the text of the final message only) |

What the design needs from this, now known and no longer assumed:

1. **The `assistant` message arrives before `content_block_stop`.** The design (architecture.md, "ConnectorEvent kinds" and `block.update`) had the tool
   title and target computed at `content_block_stop` from the buffered `input_json_delta`. In the real stream the whole input is already in the `assistant`
   message's `tool_use`, so the existing `tool_call` event carries it first. The `BlockAccumulator` matches that `tool_call` to the open block by `tool_id`
   and emits `block.update` then; `content_block_stop` only ends the block. The `input_json_delta` buffer is still bounded and never sent, and is the fallback when no
   `assistant` message comes (a stream cut short).
2. Block `index` restarts at 0 in every assistant message (both messages above use index 0): state is keyed by (message ordinal, index), as designed.
3. The same text arrives twice, as deltas and then as the whole `assistant` text message: the whole message is dropped when deltas were seen (per message), as designed.
4. A short answer's deltas arrive in one burst (the four `text_delta` lines within 3 ms); the text is real but not paced like typing. The view must not invent a pace.
5. No `thinking` block appeared (effort low, this model). Thinking handling stays presence-only and untested against a real capture here.
6. The `tool_result` content is a numbered listing of the file; the design never shows tool output live.

## Codex (`codex exec --json`)

| Step | Lines |
|---|---|
| start | `thread.started`, `turn.started` |
| a command | `item.started` (`command_execution`, `command` text present, `status in_progress`, `aggregated_output ""`, `exit_code null`), then `item.completed` (`exit_code`, `aggregated_output`) |
| the answer | `item.completed` `agent_message` with the whole text |
| end | `turn.completed` with `usage` |

1. An `agent_message` is only ever `item.completed`: **the answer is never chunked**. `stream_mode` for Codex is `activity` (commands stream as items, the text arrives whole).
2. `item.started` exists for commands only and already carries the command text. No `item.updated` was seen. A first capture of the same prompt also began with a
   short `agent_message` preamble before the command; the second did not, so a preamble is possible and the accumulator must accept an `agent_message` between tools.
3. The connector today ignores `item.started` and shows a command only when it has completed (a `tool_call` event with just `type` and `id`). STR-5 parses
   `item.started` and keeps `command`, `exit_code` and a capped `aggregated_output`.
4. Codex has no `--include-partial-messages` equivalent: `CodexConnector.stream` already forces `partials=False`.

## Latency (one run each, wall clock, seconds)

| | First output | Whole turn | Stop to end of stream |
|---|---|---|---|
| Claude, tool turn | 3.4 to 3.6 (the first `message_start`; 2.0 for `init`) | 6.1 to 6.4 | 0.83 to 0.89 (Stop sent at the first `text_delta` of a long answer; ended `cancelled`) |
| Codex, tool turn | 4.8 to 4.9 (first item) | 7.1 to 7.4 | 0.32 to 0.40 (Stop sent at the first item; ended `cancelled`) |

These are single local measurements, not a benchmark; they show the order of magnitude the UI must be honest about (a few seconds before anything arrives, under a second to stop).

## Open items that this capture did not settle

- The exact text of the idle-timeout error (no idle timeout was provoked); STR-5 asserts it from the code and a fake-CLI scenario.
- The shape of a `thinking` block and of `item.updated`: never seen; both stay tolerated-but-unrendered.
- Windows: not captured, not claimed.
