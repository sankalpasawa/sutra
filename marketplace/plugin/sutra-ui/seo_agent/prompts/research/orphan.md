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
STAY INSIDE OUR WORLD. Read these two lines before you name anything.

- What this article IS about: {{ABOUT}}
- What this article is NOT about: {{NOT_ABOUT}}

A keyword belonging to the NOT ABOUT list is NEVER an orphan, whatever its volume. It is not a gap
in our article; it is a different article. The keywords below are sorted by volume, and a
neighbouring world is precisely where the big numbers sit, so this is the mistake to expect rather
than an unlikely one. Naming one sends the article somewhere it has already decided not to go.

{{SECTIONS}}

--- CANDIDATE KEYWORDS (keyword | volume) ---
{{KEYWORDS}}
