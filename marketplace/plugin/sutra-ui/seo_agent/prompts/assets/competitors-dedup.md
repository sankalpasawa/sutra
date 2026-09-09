You are cleaning up a small CLUSTER of proposed content-asset ideas for {{BRAND}} that a similarity
search flagged as possibly overlapping. Decide, for this cluster only, what to do with them. Be
CONSERVATIVE — when unsure, keep ideas separate (we would rather keep more specific ideas than lose one).

## The cluster (each is one idea: id · asset title · format · distinct angle)
{{CLUSTER}}

## Your THREE possible actions

**1. SAME — they are literally the same build.**
Two ideas are SAME only if they are *the same thing to build*, just worded differently ("Python Skills
Test" and "Coding Assessment (Python)"; "Foundation cert" and "Advanced cert" of the same program). NOT
merely the same topic or related. A skill-gap diagnostic for managers and a self-assessment tool for
candidates are **different** — keep them apart.
*Head-noun + format rule (for the near-twins):* if two ideas share the **same core deliverable noun AND
the same format** — two "State of the Industry" *reports*, two "Candidate Experience Scorecards", two
"Pricing" comparisons — treat them as SAME, UNLESS their angle is genuinely different (a different
audience, or a different core mechanic — e.g. a static *report* vs an interactive *scorecard* are
different formats, keep apart). Two versions of the same report/tool worded differently are SAME.
When SAME: pick the id whose title is clearest to KEEP; the others are deleted and their proof
is pooled into it. **Do not edit any text.**

**2. COMBINE — two (or more) DIFFERENT but complementary ideas that, built as ONE, make a MUCH richer
asset than either alone.**
Only when the combined asset is genuinely stronger — e.g. "Interview Question Bank" + "Scoring Rubric"
→ one "Interview Kit: Question Bank + Scoring Rubric". NOT just to shrink the count. When you COMBINE, you
WRITE a new `new_title` and a new `new_angle` for the combined idea (this is the one case you may
write text), and all the originals are deleted into it. Use this sparingly and only when it clearly wins.

**3. SEPARATE — genuinely different builds, or not clearly richer combined.** Leave them alone. This is
the default. Most ideas in a cluster will be SEPARATE.

## Output — ONLY strict JSON, nothing else
```
{"groups": [
   {"action": "same",    "ids": [<id>, <id>, ...], "keep": <id>},
   {"action": "combine", "ids": [<id>, <id>, ...], "new_title": "<new title>", "new_angle": "<new one-line angle>"}
]}
```
Rules:
- List a group ONLY for ids you are acting on. Any id not listed stays as its own SEPARATE idea.
- `same`: `keep` must be one of its own ids; never edit text; never invent an id.
- `combine`: write real `new_title` + `new_angle`; only when genuinely richer than the parts.
- When unsure between SAME/COMBINE/SEPARATE, choose SEPARATE. Keep more, not less.
