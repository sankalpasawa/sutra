You are merging provisional subtopic labels into the final sections of ONE article. The labels came from
several batches of the same card pile, so many are duplicates or near-duplicates of the same subtopic.

THE ARTICLE
- Title: {{ASSET}}
- Distinct angle (what this article specifically does): {{ANGLE}}
- The spine — what this article argues, for whom, and what the reader can do at the end:
  {{SPINE}}
- What this article IS about: {{ABOUT}}
- What this article is NOT about: {{NOT_ABOUT}}

Published by {{BRAND}}.

Standing rules from the user:
{{MEMORY}}

WHO READS IT — the article will be read by one of these readers:
{{PERSONAS}}

The one it is written FOR: {{PERSONA}}

────────────────────────────────────────────────────────────────────────
You are given provisional labels as "index: label" lines. Group the indices that cover the SAME (or
clearly the same) subtopic into one final theme. Every index must go into exactly one theme.

HOW MANY: as many as the material honestly needs. There is no target number — do not aim for one.
But note what you are looking at: labels from SEVERAL batches of the SAME card pile, so the same
subtopic almost always appears more than once under different wording. MERGE ON MEANING: if two labels
would produce sections a reader could not tell apart, they are one theme. Returning roughly one theme
per label means you have not merged at all.

STAY ON THE SPINE. A theme must advance, support, or test the spine above. Where a label belongs to the
NOT ABOUT list — a neighbouring world, or the same topic seen from the wrong side (for example advising
the READER'S SUBJECT rather than the reader) — do not build a theme around it. Fold those indices into
the nearest on-spine theme instead, so nothing is lost and nothing off-spine gets its own section.

Output STRICT JSON, nothing else:
{ "themes": [ { "label": "<final subtopic label>", "member_indices": [0, 3, 7] } ] }

--- PROVISIONAL LABELS (index: label) ---
{{LABELS}}
