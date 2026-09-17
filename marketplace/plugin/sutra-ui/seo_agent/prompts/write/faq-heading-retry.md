You wrote the FAQ for an article for {{BRAND}}. Some of the questions were dropped: each one turned
out to be the same question as a heading already in the article, so a search engine would lift the
same sentence twice for no reason.

EVERY HEADING ALREADY IN THIS ARTICLE. Do not write a question that is the same question as any of
these, in other words or from another angle:
{{HEADINGS}}

THE QUESTIONS THAT WERE DROPPED, because they restated one of the headings above:
{{DROPPED}}

QUESTIONS ALREADY KEPT IN THE FAQ. Do not write one of these again either:
{{KEPT}}

Write replacement questions, up to the number that were dropped. Each one must still pass every
test you were given the first time:
- A real question a reader would type into a search box, specific enough to have a real answer: a
  number, a threshold, a method, a verdict.
- Not the same question as a heading above, and not the same question as one already kept.
- Answered in {{FAQ_WORDS}} words or fewer, counted.

Fewer replacements than were dropped is fine, and none at all is fine too, if you cannot find a
real question that passes every test. A short FAQ beats a padded one.

════════════════════════════════════════════════════════════════════════
THE USER'S STANDING RULES. They were set by the person publishing this and they win over any
rule above that they contradict. "(none)" means there are none.
{{MEMORY}}

Return ONLY this JSON, nothing else:
{"faq": [{"question": "<the replacement question>", "answer": "<{{FAQ_WORDS}} words or fewer>",
          "origin": "added"}]}
