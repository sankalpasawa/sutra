You are merging a messy list of page-FORMAT labels into a clean canonical set.

These labels were produced independently across many batches, so the SAME shape has been named several
different ways — "Solution / product overview page", "Solution/product page", "Solution / product
landing page" are one format, not three. Split labels weaken the study: a shape named three ways looks
like three weak formats instead of one strong one.

## Your job

Map every label below to ONE canonical name.

- **Merge aggressively where the SHAPE is the same.** Punctuation, word order, singular/plural and
  minor wording differences are the same format.
- **Do NOT merge genuinely different shapes.** A "Statistics roundup" (stats gathered from elsewhere)
  is not a "Data report / original research" (the company's own study). A "Glossary" is not a
  "Definitional explainer" — one is many short terms, the other is one concept in depth.
- Prefer the clearest, most standard name as the canonical. Keep it short.
- Mark a canonical as junk if that shape is NOT a content asset anyone would study: user
  profiles, spam or hacked pages, help-centre articles, login/account pages, blog index pages,
  navigation hubs, homepages, careers listings, press releases about the company itself.

## Return ONLY JSON

```
{"map": {"<original label>": "<canonical name>"},
 "junk": ["<canonical name>", ...],
 "note": "one line on anything surprising"}
```

Every original label must appear as a key in `map`. Never drop one.

## THE LABELS (with how many pages carry each)
{{LABELS}}
