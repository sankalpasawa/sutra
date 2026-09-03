You are deriving keyword SEEDS for a {{BRAND}} research brief, from an article's anchors. Seeds come ONLY
from the anchors below — no free brainstorm.

CONTEXT
- Article title (verbatim): {{ASSET_TOPIC}}
- Distinct angle (what THIS article covers, verbatim): {{DISTINCT_ANGLE}}
- What this article IS about: {{ABOUT}}
- What this article is NOT about: {{NOT_ABOUT}}

THE COMPANY'S NICHE (what counts as on-angle for this brand): {{NICHE_DEFINITION}}

STANDING RULES FROM THE USER:
{{MEMORY}}

DERIVE:
- head_seeds: the pillar phrase from the article title + 1-2 close variants (form illustration — for an
  article titled "Recruiting Metrics Benchmark" these would be "recruiting metrics", "recruitment metrics",
  "recruiting metrics benchmark"). These are the article's spine.

- sibling_seeds: the specific sub-topics the DISTINCT ANGLE names. One seed per distinct sub-topic. If no
  angle is given, the sub-topics the title itself plainly names.

- hygiene: one line flagging any AMBIGUOUS seed that will pull off-topic junk in a keyword-suggestions net.
  Read the NOT ABOUT line above: where a seed word ALSO means something in one of those other worlds, say
  so here by name (form illustration: a seed containing "CV" also means "coefficient of variation" in
  statistics; "assessment" also means clinical or academic testing). This note is passed to the keyword
  scorer downstream, so name the wrong-world meaning explicitly.
  Seed it PLAIN anyway — the scorer drops the stragglers on relevance, and qualifying the seed here
  starves the core long-tails. If nothing is ambiguous, say so.

RETURN JSON only:
{ "head_seeds": ["...", ...], "sibling_seeds": ["...", ...], "hygiene": "one line" }
