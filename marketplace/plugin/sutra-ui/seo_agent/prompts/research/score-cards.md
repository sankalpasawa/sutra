You are curating research "cards" for ONE article. Decide, for each card, whether it belongs in this
article.

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
Judge every card through this reader's eyes first; the others may still land on the page.

────────────────────────────────────────────────────────────────────────
THE ONE TEST: does this card serve the SPINE?

A card earns its place by advancing, supporting, or testing the article's argument. It does NOT earn
its place by being interesting, well-sourced, or useful to the brand. A true, well-sourced fact about
a neighbouring topic is still out. Anything belonging to the NOT ABOUT list is out, however well it
reads.

Each card is given as:   id | tag | source | text

The source is there so you can see where a fact came from. Where a subject shares a word with a
different field, the source is often the only thing that reveals it — a fact lifted from the wrong
field reads perfectly sensible and is still wrong for these readers.

────────────────────────────────────────────────────────────────────────
For EACH card, return:

- relevance: integer 0-5 — how directly does this card serve the spine?
  5 = the article cannot make its argument without it (a number, threshold, benchmark, or rule the
      spine promises to deliver)
  3 = genuinely supports the spine (real context, a mechanism, a worked example)
  1 = general knowledge about the wider field; the spine does not need it
  0 = does not serve the spine at all, or belongs to the NOT ABOUT list

- protected: true ONLY if the card carries HARD data the article promises — a number / % /
  coefficient / threshold / statistic, OR a concrete sample/example item, OR it ties a SPECIFIC named
  option to a case or outcome. Otherwise false. (Do NOT mark protected just because it contains a year.)

- reason: one short line. When a card is off-spine, say which part of the spine or the NOT ABOUT list
  it fails against.

Return STRICT JSON, nothing else:
{"scores":[{"id":1,"relevance":0,"protected":false,"reason":"..."}]}

CARDS
{{CARDS}}
