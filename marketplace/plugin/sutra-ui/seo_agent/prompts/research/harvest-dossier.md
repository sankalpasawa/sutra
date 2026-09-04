You are breaking ONE section of a research dossier into small "cards", one atomic idea per card, so a later
step can cluster them into an article's sections.

You are given a section title and the section's full text. The text carries inline citation markers like [5];
keep them exactly where they are.

For EACH distinct idea, fact, definition, metric, or claim in the section, output one card:
- "gloss": ONE short line describing what this card is about. Write it after reading the whole chunk, in your
  own words. This is only an index for grouping, keep it plain and specific.
- "verbatim": the exact sentence(s) from the section that carry this idea, COPIED WORD FOR WORD, including any
  [n] markers. Do not paraphrase, summarise, fix, or shorten the quote. It must appear verbatim in the text above.

Rules:
- Be EXHAUSTIVE. One card per distinct idea. Too many is fine (duplicates get merged later); missing one is not.
- Never invent. If it isn't in the text, it isn't a card.
- The verbatim must be an exact substring of the section text (so we can verify it).

Output STRICT JSON, nothing else — an array of cards:
[
  { "gloss": "...", "verbatim": "..." }
]

--- SECTION TITLE ---
{{SECTION_TITLE}}

--- SECTION TEXT ---
{{SECTION_TEXT}}

════════════════════════════════════════════════════════════════════════════════════════════════════════════════════════════════════════════
THE USER'S STANDING RULES. They were set by the person publishing this and they win over any
rule above that they contradict. "(none)" means there are none.
{{MEMORY}}
