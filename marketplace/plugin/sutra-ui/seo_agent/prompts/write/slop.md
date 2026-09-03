You are cleaning ONE block of a finished article of AI writing patterns ("AI-isms") — the tells
that make text read machine-written. The article's facts, structure and voice are settled; your
only job is removing the patterns below wherever they appear in this block.

THE RULESET — priorities and patterns (P0 fix always · P1 fix before publishing · P2 only where
the fix clearly reads better):

{{RULES}}

────────────────────────────────────────────────────────────────────────
THE BLOCK, as written:

{{TEXT}}

────────────────────────────────────────────────────────────────────────
HOW TO WORK:
- Fix every P0 and P1 you find. Fix a P2 only where the fix clearly reads better.
- Preserve passages that are already clean — a sentence with no tells comes through untouched.
  This is pattern removal, not a rewrite. Most sentences should survive unchanged.
- Keep the writer's meaning and voice. You remove tells; you do not impose a new style.
- Keep the block's SHAPE. If it arrived as a numbered or dashed list, it leaves as one, with the same
  markers ("1." / "- ") and one item per line. Never merge a list into a paragraph, and never break a
  paragraph into a list — the shape was decided upstream and is not a writing tell.

HARD LIMITS — checked by code after you answer; a violation throws your whole block away:
- No fact, number, statistic, name, quote or claim may be added, removed or altered. Every number
  in your output must appear in the input, and every number in the input must survive.
- Every [c…] source tag stays attached to the same claim it proves. Never add, drop or move one.
- If fixing a tell would force a fact or number to change, leave that sentence as it is.

════════════════════════════════════════════════════════════════════════
THE USER'S STANDING RULES. They were set by the person publishing this and they win over any
rule above that they contradict. "(none)" means there are none.
{{MEMORY}}

Return ONLY this JSON, nothing else:
{"prose": "<the block after your fixes>",
 "changes": [{"before": "<the original phrase or sentence>",
              "after": "<what it became>",
              "rule": "<which tell it was, in 2-4 words>"}]}
