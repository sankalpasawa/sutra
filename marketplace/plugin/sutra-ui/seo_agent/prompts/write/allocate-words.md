You are budgeting an article's length across its sections.

THE COMPANY publishing this article: {{BRAND}} — {{ABOUT}}

THE ARTICLE:
- Asset title: {{TITLE}}
- Distinct angle: {{ANGLE}}
- The spine: {{SPINE}}

WHO THIS ARTICLE IS FOR:
{{PERSONA}}

TOTAL LENGTH TO DISTRIBUTE: {{TARGET}} words (the body only).

THE SECTIONS — each with its job, what it covers, and the facts it actually holds:
{{SECTIONS}}

────────────────────────────────────────────────────────────────────────
Decide what SHARE of the article each section deserves, as a percentage. Work it in two passes, in
this order — they answer different questions and the order is what keeps the answer honest.

PASS 1 — IMPORTANCE SETS THE NUMBER.
Read the spine, then read each section's job. How much does this section matter to the argument, and
how much does THE READER ABOVE need from it? A section that would matter enormously to somebody else
— the other side of the table, a different seniority, a specialist — earns little here.

That, and only that, sets the first number. The section carrying the article's central claim earns
the most words even when it is thinly evidenced. A section that sets up, bridges or hands off earns
few even when it is stacked with facts.

ONE THING IS ALREADY PART-DECIDED FOR YOU: THE SUB-HEADINGS.
The step before this one either split a section into sub-headings or left it whole, based on how much
distinct ground its material actually covers. That count is real information, so use it. A section
with 2 sub-headings is carrying three separate stretches of ground — the opening plus each
sub-heading — and needs the words to cover them.

Every stretch needs about {{MIN_WORDS_PER_SUBHEAD}} words to be worth its heading. So a section with
N sub-headings needs at least (N + 1) x {{MIN_WORDS_PER_SUBHEAD}} words. A section with none has no
such floor and can be as short as its importance deserves.

This does NOT override importance. A section unimportant to the argument stays small even when it was
split — the split only tells you it cannot go below its floor without its sub-headings becoming
labels on single paragraphs. If you genuinely cannot give a split section its floor without starving
a more important one, give the important one its words and say so in the split section's reason.

WHEN THE ARTICLE IS A LIST, THE ITEMS ARE PARALLEL AND SHARE EVENLY.
Sections marked [LIST ITEM] below are the entries of a list, and a reader reads them side by side and
compares them. So they get ROUGHLY EQUAL shares. One item is not three times more important than
another because the research happened to turn up more material about it — that is an accident of
what was available, and letting it set the length makes the list read as though half the entries were
an afterthought.

Work it in this order when items are present: decide what share the ITEM BLOCK AS A WHOLE deserves
against the supporting sections, then divide that block evenly across the items. Vary by a little
where one genuinely needs more room, never by more than about a quarter either way.

Importance still ranks the supporting sections against each other, and ranks the item block against
them. It does NOT rank items against items.

PASS 2 — THE EVIDENCE IS A CEILING, NEVER A CLAIM.
Now read the facts each section actually holds, and ask ONE question of each: can this section be
WRITTEN to the length pass 1 just gave it, from this material, without padding? If it cannot, cut it
back to what the material honestly supports and move those words to a section that can use them.

The evidence only ever takes words away. It never earns them.

A long list of facts is not a claim on length. It is often the same point restated by twelve sources,
and it compresses into two sentences. So judge what is DISTINCT in the list, not how long the list
is: five facts that each say something new carry more words than forty that agree with each other.
Some sections show only their first {{CARD_CAP}} facts with a note saying how many more there are —
that note is there for honesty, not as an argument for a bigger share.

Rules:
- The shares must add up to 100.
- No section below 4 — anything that small should not be its own section.
- Give one short reason per section. Where pass 2 cut a section back, say so in that reason.

Return ONLY this JSON, nothing else:
{"allocation": [{"section": <index as listed>, "share": <percent>, "why": "<one short line>"}]}
