You are finding the search phrases to look up for ONE section of an article.

THE ARTICLE
- Title: {{TITLE}}
- The spine: {{SPINE}}
- What this article IS about: {{ABOUT}}
- What this article is NOT about: {{NOT_ABOUT}}
- WHO THIS ARTICLE IS FOR:
{{PERSONA}}
- The primary keyword (the H1's — do not seed this or a reword of it): {{PRIMARY}}

THIS SECTION
- Working heading: {{HEADING}}
- Its job: {{JOB}}
- The evidence it actually holds:
{{CARDS}}

────────────────────────────────────────────────────────────────────────
Write 2 or 3 SEED PHRASES a person would type into Google to find THIS section.

Read the EVIDENCE, not just the heading. A section whose heading says "pricing" but whose evidence is
all commission percentages is a section about commission rates — seed it that way.

Rules:
- KEEP THEM SHORT: 2 or 3 words. This is the single most important rule here. These go into a keyword
  suggestion index that matches on the phrase itself — a 4-or-5-word seed almost always returns NOTHING,
  and the section ends up with no keyword at all. Seed the SHORT head of the idea and let the index find
  the longer phrases around it. Write "hackathon ai policy", not "AI policy for a hiring hackathon".
- Plain search language, not our internal phrasing — the words THAT reader would type, not the words
  the other side of the table would.
- Inside our world. Never seed a phrase belonging to something in the NOT ABOUT list, even when it
  matches our words — those searches come from a different field.
- Seed what this SECTION delivers, not the whole article's subject.
- Vary them. If your seeds are the same words reordered, you get one set of results, not three.

Return ONLY this JSON, nothing else:
{"seeds": ["...", "..."], "why": "<one line: what this section is really about, from its evidence>"}
