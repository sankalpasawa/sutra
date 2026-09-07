You are checking which options have enough material to earn their own section in a comparison article.

THE COMPANY publishing this article: {{BRAND}} — {{ABOUT}}

THE ARTICLE (what we are building):
- Asset title: {{TITLE}}
- Distinct angle (what this article is built to deliver): {{ANGLE}}
- What this article IS about: {{WORLD_ABOUT}}
- What this article is NOT about: {{WORLD_NOT_ABOUT}}

THE OPTIONS:
{{ENTITIES}}

THE YARDSTICKS every option is measured on:
{{YARDSTICKS}}

THE MATERIAL (the planned sections — H2s, their H3s, and the evidence cards under each):
{{PAGES_NOTE}}{{MATERIAL}}

FIRST, name the category in one line: what kind of thing is this article's reader actually choosing
between? It might be software, agencies, providers, courses, accounts, methods or anything else.
Then remove from consideration any option that is not that kind of thing, however well covered it is
— a component of the category, an integration with it, or a supplier to it is not a competitor
within it. Remove anything belonging to the NOT ABOUT world for the same reason.

THEN, for EACH remaining option, go through the cards and SHOW YOUR WORK: list which yardsticks the
material has real information about for THIS option. Then decide: KEEP the option if it has
information for at least {{MIN_PCT}}% of the yardsticks; DROP it otherwise.

Sanity rules:
- RANK CHECK, before you answer: sort every option by its card count. If any option you DROPPED has more
  cards than any option you KEPT, you have misread the material — recount that pair and name the yardstick
  you found for the better-covered one, or move it back into keep.
- {{BRAND}} is the company publishing this article. When it appears among the options, NEVER drop
  it — it always keeps its place, evaluated on the material it has.
- Judge from the cards only; never from your own knowledge of these options.

Return ONLY this JSON, nothing else:
{"category": "<the kind of thing the reader is choosing between>",
 "keep": [{"name": "<option>", "yardsticks_covered": ["<yardstick>", ...]}],
 "dropped": [{"name": "<option>", "yardsticks_covered": ["<yardstick>", ...]}]}
