You are placing INTERNAL LINKS into a finished article published by {{BRAND}}. An internal link
lays a link over words that ALREADY EXIST in the text, pointing to another {{BRAND}} page.

Below is every section of the article, in order. For each one you get what that section must
deliver, its text, and a shortlist of pages found by searching our site for that section's subject
specifically — not the article's subject in general.

Each shortlisted page comes with two things you must actually use:
- A MATCH SCORE from 0 to 1. Higher means our search thought the page was a closer fit. Treat it as
  a hint about where to look first, never as permission: a high score still has to survive your own
  reading below.
- WHAT IS ACTUALLY ON THAT PAGE — the page's real opening text. **Judge on this, not on the URL and
  not on the title.** A title like "Hiring via Job Simulation" can sit on a page that never once
  discusses the thing your section is about. The opening text tells you what is really there. If the
  text does not visibly cover the exact thing the anchor words claim, do not use that page.

{{SECTIONS}}

────────────────────────────────────────────────────────────────────────
THE TEST for every link — value first, always: a reader who clicks it must land on a page that
gives a genuinely deeper or more practical treatment of the exact thing those words talk about.
The link is a promise ("more on this here"); a link that breaks that promise teaches the reader to
stop clicking. When in doubt, do not link.

SAME TOPIC IS NOT ENOUGH. Before accepting any page, run these three checks. Each one has failed a
real article, and "it is broadly about the same subject" is exactly how each slipped through.
- SAME ACTIVITY, not merely the same idea. A section teaching rubric anchors for a HACKATHON was
  linked to a page on scoring VIDEO AND AUDIO INTERVIEWS. Anchored rating scales appear in both, so
  it read as a match. The reader was promised hackathon rubric help and got interview scoring. If
  the page teaches the technique in a different exercise, format or setting, reject it.
- SAME SIDE. A sentence about CANDIDATES using AI was linked to a guide about RECRUITERS using AI.
  Same technology, opposite person. Check who the page is written for and who the sentence is about.
- SAME DIRECTION. A sentence saying the research does NOT use job performance as an outcome was
  linked to a page arguing that a trait model DOES predict job performance. A link on a negative or
  limiting statement must not point at a page that asserts the opposite.

THE RULES:
- {{HOW_MANY_LOW}} to {{HOW_MANY}} links across the WHOLE article — this piece runs {{WORDS}} words, and
  that is the allowance a reader can absorb over that length. It is a target, not a quota: fewer beats
  forced, and if only half that many pages genuinely earn a link, place only those and say why in
  "rejected". Never stretch to reach the number.
- AT MOST ONE link per section. A section with nothing worth linking gets none, and most sections
  will get none — that is the normal outcome, not a failure.
- You are seeing every section at once for a reason: when the same page fits two sections, give it
  to the one whose words are the better home and leave the other alone. Never use one page twice.
- SPREAD THEM. Links bunched in the first three sections are worse than four spread across the piece.
- INCLUDE AT LEAST ONE [PRODUCT] PAGE if any section gives you honest words to hang it on. A product
  page is pricing, a product or feature page, a tool or calculator, a glossary entry, a template.
  The reader who just finished a section about doing the thing is the reader who wants the page
  that helps them do it, and sending them to another blog post instead wastes the moment. If no product page genuinely fits the
  words on the page, say so in "rejected" — never bend a sentence to fit one.

THE ANCHOR — this is where links are usually lost:
- It is a run of words that ALREADY EXISTS VERBATIM in that section's text above. You may not add,
  reword, extend or shorten the article by a single character to make a link fit.
- QUOTE IT EXACTLY: same capitalisation, same spacing, same hyphens, character for character. Copy
  it from the section's text, never from a heading — headings are not linkable. An anchor that does
  not match is thrown away by code and the link is lost.
- 2 to 6 words, and it must NAME THE THING the target page is about — a noun phrase a reader could
  look up. Not a description of what the sentence is doing.
  Good, because each names its target's subject: "cost per hire" · "indirect hiring costs" ·
  "stakeholder management" · "disparate-impact liability" · "work sample test".
  Bad, all of these were really placed and all describe the sentence instead of the destination:
  "A role sitting empty" · "Defending a placement decision later" · "turns to adaptability" ·
  "Candidates are already using AI" · "another judge reviews the evidence independently".
  The test: read the anchor alone, with no sentence around it. If it does not tell you what page it
  opens, it is the wrong anchor. Pick different words from the same section, or place no link.
- Never "click here", never a whole sentence, never a verb phrase.
- No two links may use the same wording.

Return ONLY this JSON, nothing else:
{"links": [{"section": "<the section heading, exactly as given above>",
            "anchor": "<the exact words from that section's text, verbatim>",
            "url": "<the target, from that section's shortlist>",
            "why": "<one line: what deeper value the reader gets by clicking>"}],
 "rejected": [{"url": "<a candidate you did not use>", "why": "<one line>"}]}
