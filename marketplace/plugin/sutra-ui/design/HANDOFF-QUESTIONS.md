# HANDOFF-QUESTIONS.md

Needs that came out of the "does it ask the right questions?" pass (2026-09-10) and that do NOT
belong to the brief or to `loop.py`.

## An idea accepted in the chat never gets ticked off the sheet

`save_to_library` ticks an idea only when the run's state carries `idea_id`, and the only thing
that ever writes `idea_id` is the send route in `agents_api.py` (~line 197), from the chip on the
Asset ideas tab. That is the right design: the id travels as data and the model never has to read
one out of prose.

But the brief now (correctly) has the agent OFFER the next open idea in the chat whenever nobody
named a topic, and the ordinary way to accept that offer is to type "yes". A run started that way
has no `idea_id`, so the article is saved and the idea stays `open` for ever, and the very next
turn offers the same idea again. The sheet slowly fills with ideas that have already been written.

This cannot be fixed in the brief: the model has no tool that sets `idea_id`, and matching a
finished article back to an open idea by meaning was ruled out on 2026-09-09 for good reasons (see
the comment in `loop.save_to_library`).

Two ways out, both outside my files:

1. The answer to a topic checkpoint carries the id. When the agent's `ask_user` offer is accepted,
   the front end sends `idea` alongside the answer the same way the chip does, and the resume
   route patches `idea_id` onto the run. Exact provenance, no matching.
2. The offer is not a chat question at all: the agent's "shall I write a1001" renders as the same
   chip the Asset ideas tab uses, so accepting it goes down the existing path.

Option 1 is smaller. Either way the ticking stays a fact about how the run was started, never a
judgement made afterwards.

## `CLI_TOOL_RULE` caps a tool-calling turn at one sentence, and two rules now need more

`seo_agent/llm.py` builds the CLI system prompt and ends it with:

    "Reply with text and zero or more tool_calls. When you call tools, keep
     text to one short sentence. When you have nothing more to do, return an
     empty tool_calls list."

Two things now collide with that, and both were seen live on 2026-09-10.

1. **Context before the offer.** The brief asks the opening turn to give two or three short
   sentences of context and THEN make the offer. The offer is an `ask_user` call, so the turn is a
   tool-calling turn, and this rule says one sentence. On a state with plenty to report the model
   broke the cap and gave proper context; on a tidy one it obeyed and opened with "Putting the top
   idea to you." followed by a question, which is close to the thing the owner objected to.
2. **The third-person status turn** (confused-user finding 6): a whole turn comes back as a status
   line with no tool call at all. Same sentence is the suspect.

The fix is a clause, not a rewrite: keep the cap, exempt the opening turn of a run. `llm.py` is
not owned by the question-quality job, so it is written here rather than changed.

## While I was in `agents_api.py`

Fixed there and listed for the record: the `_work/merge/methods.json` shape crash in
`_assets_payload` (two writers, two shapes, one reader), `assets` added to `GET /health` as
`{built, total, open, next}` for the hero chip, and the send route now records an idea id the
person TYPED, not only one the chip carried. The JS half of the hero chip is still to do.
