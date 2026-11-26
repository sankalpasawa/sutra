# T2 spike: does a run's framing line reach J2's calls?
_Date: 2026-11-26 · Base: origin/main e59d3ea0 · Test: tests/engine/test_project_context_channel.py (3 tests, all pass on 0.8.3) · No production code changed_

## Question
Architecture 6.2 puts the project block (instructions, memory, file digest) in a run's framing, which the host posts as the one system chat line "Context from the team lead: ...".
Does J2 show that line to the agents that do the work?

## Finding (read out of vendored `engine/j2.py`, then confirmed by the tests)
| Call | Sees the chat line? | Why |
|---|---|---|
| The five function agents (identity, adaptation, priority, coordination, audit) | Yes, while the chat is short | `context(fn)` = STATE + `CHAT` (`chat_view`) |
| The same agents in a long chat (over `J2_CHAT_FULL_CHARS`, 60,000 characters) | No | the first lines are replaced by a model's 12-bullet summary; the framing line is message 1 |
| A builder (`W-n`) in a real run (`J2_SLIM` on, the default, not mock) | **No** | `context()` returns `builder_state` only: brief, charter, the Requester's answers, style guide, section map, findings to fix. No chat |
| Any agent call, through `call()` | Yes, anything in the host's `system_addendum(fn)` | P9: `call()` appends it to the system prompt of every agent call; the host reads `<run>/node_context.json` |

So a block in the framing never reaches a builder in a real run, and can be summarised away from the function agents in a long run. Mock runs hide this (a mock builder gets the full context),
which is why the test sets `llm.MOCK = False` to read a real builder's context.

## Decision for T5 (the architecture's own fallback, A9)
The project block and the digest of the request's files go through the **system addendum**, not the framing:

1. The server writes `<run>/node_context.json` = `{"*": "<project block>\n\n<attached digest>"}` when the run has anything to say (and nothing at all otherwise: byte-equal to 0.8.3).
2. `engine/hooks.py` `EventHooks.system_addendum(fn)` (host side; `j2.py` and every J2 prompt golden are untouched) appends the `"*"` text, under its own heading "## Project context", to every
   agent call, builders and function agents alike, after the function's own text if the file has one. A file with no `"*"` key behaves exactly as before. The agent-chat API that rewrites a
   function's note keeps the other keys, so `"*"` survives it.
3. The framing keeps only what the owner and the function agents need to know that files exist: a short pointer line naming the files in `inputs/knowledge/` and `inputs/attached/`.
   The rules block is unchanged (guidance, as before).

Cost note: the block is in the system prompt once per call instead of in the chat once per call for function agents (the same repeat count), and now also reaches builders. The block is capped
at 8,000 characters (instructions 2,500, memory 1,500, digest 4,000) plus 6,000 for the request's own files.

Confidence: high for the table (read from the code and pinned by tests); moderate that a real builder obeys the block (T17's check of a real call is the owner's beta step).
