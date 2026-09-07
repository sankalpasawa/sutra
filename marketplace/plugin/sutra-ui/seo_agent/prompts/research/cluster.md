You are grouping research "cards" into the sections of ONE article.

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
You are given cards as "id: gloss" lines. Group them by MEANING: cards about the same sub-topic
belong together, even when they came from different sources or use different words.

THE RULES:
- COMPLETE — every card id is placed in exactly one cluster. Leave none out.
- NON-OVERLAPPING — no card id appears in two clusters.
- COHERENT — each cluster is ONE clear sub-topic that could stand alone as a section a reader
  could name.
- ON-SPINE — each cluster advances, supports, or tests the spine above.

HOW MANY: as many as the material honestly needs. There is no target number — do not aim for one.
Every cluster must earn its place by passing all four rules above.

MERGE NEAR-DUPLICATES. If two clusters would cover the same ground, they are one cluster. Several
clusters circling the same idea in different wording is the most common mistake here — before you
finish, read your own labels back and merge any that overlap.

Output STRICT JSON, nothing else:
{ "clusters": [ { "label": "<short subtopic label>", "card_ids": [1, 2, 3] } ] }

--- CARDS (id: gloss) ---
{{CARDS}}
