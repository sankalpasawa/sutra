# Raw AI chat (debugger view)

What it shows, where it lives, and the one thing it does not show yet.

## What ships

| Piece | File | What it does |
|---|---|---|
| Reader | `sutra_app/engine/rawchat.py` | Reads a run's `calls.jsonl` as list rows (metadata and 160-character previews, no full text) and `agent_live.json` as the live tail. |
| Routes | `sutra_app/engine/api/rawchat.py` | `GET /api/calls?dept=&run=&offset=&limit=&q=` (at most 500 rows a page; `q` searches the full system prompt, prompt and raw reply) and `GET /api/agent-live?dept=&run=`. Same scope rules and redaction as every engine GET. The full text of one call stays J2's `GET /api/call?dept=&run=&id=`. |
| View | `sutra_app/ui/static/js/raw_chat.js`, styles at the end of `sutra-panel.css` | List of calls on the left; the picked call as a chat on the right: SYSTEM PROMPT (folded), PROMPT (user turn), RAW REPLY (assistant turn), PARSED REPLY, REASON. Copy buttons, search with marks, live tail while the run is going (polls every 2 s). |
| Entry | `dept_ext.js` adds the script; `/d/{team}/raw[?run=]` in `sutra_app/ui/routes.py` | A "Raw AI chat" button on the team page when `localStorage["sutra:level"] === "debug"`; the direct URL opens it full screen at any level. |

## Not there yet: the exact Claude Code stream (tool calls)

`calls.jsonl` holds the text the engine sent and the final text it got back. When the provider is `claude -p`, the turn in between (tool calls, tool results, thinking blocks, retries) arrives as `--output-format stream-json` lines that `ClaudeParser.feed` (`sutra_app/connectors/claude.py`) reads in memory and drops.

How to keep them, in Sutra's own code only:

1. In the connector's turn loop, the same place that calls `parser.feed(line)`, append each raw line to `<run>/raw/call-<n>.jsonl`. `<n>` is `tag.call_no`, which `J2Run._ask_tag` already sets to the `calls.jsonl` id (0 means J2 does not log that call, so skip it). The run folder reaches the connector through the engine port's request tag or the engine host's environment.
2. Pass every line through the app's `redact` before writing, open the file with mode 0600, and stop writing a call's file at a cap (for example 2 MB) with a final `{"type":"sutra_truncated"}` line.
3. Add `GET /api/call-stream?dept=&run=&id=` next to `/api/calls`, reading that file back as a list of events.
4. In `raw_chat.js`, show a "Stream" section under RAW REPLY that folds tool_use and tool_result blocks the way `chat_fold.js` already does for agent chats.
5. Tests: a fake `claude` binary (the e2e harness's `FakeCliBin`) emitting tool_use lines; assert the file exists, is redacted, is capped, and that a codex or mock run writes nothing.

This was left out of the first cut because the connector runs in the engine process and does not know the run folder today. Wiring that through is a change to the port contract, not a small local edit.

## Known gaps

- Calls that J2 does not log to `calls.jsonl` (`call_no` 0: the planner and judge sessions, the chat summary) are missing from the list. That is why call ids can jump, for example from #2 to #8.
- In mock (`--offline`) runs, model, tokens and cost are empty. The list shows character counts instead.
