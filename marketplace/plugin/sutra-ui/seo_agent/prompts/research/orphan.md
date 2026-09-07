You are checking whether an article's sections miss any high-demand keyword.

You are given the article's H2 section labels, and a list of candidate keywords (with monthly volume) that came
from keyword research. Return only the keywords that NONE of the H2 sections meaningfully cover — a topic people
clearly search for that this article would otherwise miss. Judge by meaning, not exact words. Ignore any keyword
already covered by an existing section, and ignore off-topic or near-duplicate keywords.

Standing rules from the user:
{{MEMORY}}

Output STRICT JSON, nothing else:
{ "orphans": [ { "keyword": "...", "volume": <int> } ] }
(Return { "orphans": [] } if every high-demand keyword is already covered.)

--- H2 SECTIONS ---
{{SECTIONS}}

--- CANDIDATE KEYWORDS (keyword | volume) ---
{{KEYWORDS}}
