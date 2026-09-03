You are breaking ONE web page into small "cards", one atomic idea per card, so a later step can cluster
them into an article's sections.

You are given the page's title, its URL, and its text (or a run of passages from it).

For EACH distinct idea, fact, definition, metric, or claim in the text, output one card:
- "gloss": ONE short line describing what this card is about. Write it after reading the whole text, in your
  own words. This is only an index for grouping, keep it plain and specific.
- "verbatim": the exact sentence(s) from the text that carry this idea, COPIED WORD FOR WORD. Do not
  paraphrase, summarise, fix, or shorten the quote. It must appear verbatim in the text below.

Rules:
- Be EXHAUSTIVE. One card per distinct idea. Too many is fine (duplicates get merged later); missing one is not.
- Never invent. If it isn't in the text, it isn't a card.
- The verbatim must be an exact substring of the page text (so we can verify it).
- Skip navigation, cookie notices, author boxes, related-post lists and calls to action. Only the page's
  own content is evidence.

Output STRICT JSON, nothing else — an array of cards:
[
  { "gloss": "...", "verbatim": "..." }
]

--- PAGE TITLE ---
{{PAGE_TITLE}}

--- PAGE URL ---
{{PAGE_URL}}

--- PAGE TEXT ---
{{PAGE_TEXT}}
