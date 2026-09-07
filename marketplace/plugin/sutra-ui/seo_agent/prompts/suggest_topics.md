You are finding article topics for {{COMPANY}}.

## What this company sells, and to whom

{{VOICE}}

## A competitor, {{COMPETITOR}}, and the keywords their pages already rank for

{{RIVAL_KEYWORDS}}

## What {{COMPANY}} already covers

{{OWN_PAGES}}

## Your job

Pick six topics this company could own. Each one must be sparked by a real keyword from
the competitor list above, and each must take an angle that competitor has NOT taken.

Rules:
- Do not propose a topic that duplicates a page the company already has.
- The angle is the whole point. "Same article but better" is not an angle. A different
  reader, a different decision, a narrower slice, a harder question, real operating
  detail the rival skipped: those are angles.
- why_us must connect to something this company actually sells or knows. If you cannot
  make that connection, drop the topic and pick another.
- est_volume and est_difficulty are your rough estimates, not measured numbers. Base the
  estimate on the competitor keyword it came from. Keep est_difficulty between 0 and 100.

{{WRITING_RULES}}

Reply with JSON only:

{"topics": [{
  "id": "t1",
  "topic": "the article topic, as a phrase not a headline",
  "sparked_by": "the exact competitor keyword it came from",
  "angle": "what the competitor has not done, in one or two sentences",
  "why_us": "what this company sells or knows that makes this theirs to write",
  "est_volume": 0,
  "est_difficulty": 0
}]}
