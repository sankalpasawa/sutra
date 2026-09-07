You are deciding whether any of this company's OWN material belongs in this article, and if so, where.

THE DEFAULT ANSWER IS NONE. Most articles take nothing from this pool. You are looking for the rare case
where a piece of our own material is genuinely the best evidence for a point the article is already
making. You are not looking for places to fit us in.

────────────────────────────────────────────────────────────────────────
THE ARTICLE
- Title: {{TITLE}}
- Distinct angle (what this article is built to deliver): {{ANGLE}}
- What this whole piece argues (the spine): {{SPINE}}
- Who it is written for: {{PERSONA}}

────────────────────────────────────────────────────────────────────────
THE SECTIONS, and the facts each one ALREADY has.

A section with good evidence does not need ours. Read what is already there before you decide anything
is missing.

{{SECTIONS}}

────────────────────────────────────────────────────────────────────────
OUR MATERIAL — two kinds, and they are NOT judged the same way.

KIND A — RESEARCH FINDINGS. Original research we ran. This is neutral market data: it describes the
industry, not us. A reader gains from it whether or not they ever buy anything.

{{RESEARCH_CARDS}}

KIND B — CUSTOMER RESULTS. What a named company achieved using our product. Every one of these is a
proof point for us. Useful, but it is our own evidence about ourselves.

{{RESULT_CARDS}}

────────────────────────────────────────────────────────────────────────
THE LIMITS. Code enforces every one of these, so going over means your answer is thrown out.

- RESEARCH FINDINGS: at most {{RESEARCH_CAP}} in the whole article, and at most
  {{RESEARCH_PER_SECTION}} in any one section.
- CUSTOMER RESULTS: at most {{RESULT_CAP}} in the whole article. Usually the right number is zero.
- Combined, everything you place should be worth a few lines of the finished article. Not a paragraph
  each, not a section. If what you are placing would need its own paragraph to land, it is too much.

────────────────────────────────────────────────────────────────────────
PLACE A CARD ONLY IF ALL FOUR ARE TRUE:

1. THE SECTION IS ALREADY MAKING THIS POINT. The card is evidence for an argument the section already
   has, not a new argument you are adding to it. If placing it would change what the section is about,
   do not place it.
2. IT IS NOT A REPEAT. The section does not already have a fact that says the same thing. Our number
   does not get to replace a perfectly good existing one.
3. IT IS THE BEST AVAILABLE EVIDENCE, not merely relevant. Relevant is not the bar. If a reader would
   learn just as much without it, leave it out.
4. IT SURVIVES THE READER TEST. Read the section as the reader, not as the company. Does this land as
   useful information, or as the moment the article starts selling? If you hesitate, that is a no.

A CUSTOMER RESULT HAS A FIFTH TEST: the section must be about how something is DONE, where a real
company's outcome shows it working. A section explaining a concept, defining a term, or laying out the
state of the market never takes one.

────────────────────────────────────────────────────────────────────────
WHERE A CARD GOES

Place it in an existing section, and inside that section either in the opening or under one of its
existing sub-headings, by exact name.

NEVER create a heading. NEVER create a sub-heading. If there is no existing place a card fits, that
means it does not belong in this article.

────────────────────────────────────────────────────────────────────────
Return ONLY this JSON:

{"placements": [
   {"card_id": <the id, exactly as shown above>,
    "kind": "research" | "result",
    "section": <the section number>,
    "goes_to": "opening" | "<the exact sub-heading text>",
    "why": "<one line: which point in that section this is evidence FOR>"}],
 "notes": "<one line on what you saw, or why you placed nothing. Empty is fine.>"}

Return an empty placements array when nothing earns its place. That is a normal, good answer, and it is
the answer we expect most of the time.
