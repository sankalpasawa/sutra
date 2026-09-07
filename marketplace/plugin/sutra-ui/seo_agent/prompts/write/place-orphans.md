You are placing orphan sub-sections (H3s) into an article's surviving sections. Each orphan came from a
section that was cut; the orphan itself is valuable and must be kept. Pick the ONE best surviving section
(H2) for each orphan.

THE ARTICLE:
- Asset title: {{TITLE}}
- Distinct angle: {{ANGLE}}
- The spine — what this article argues, for whom, and what the reader can do at the end:
  {{SPINE}}
- What this article is NOT about: {{WORLD_NOT_ABOUT}}

THE SURVIVING SECTIONS (index · H2 · its kept H3 titles):
{{SURVIVORS}}

THE ORPHANS (index · H3 title · its tags · sample evidence · the cut section it came from):
{{ORPHANS}}

Rules:
- Place EVERY orphan into exactly one surviving section — the one where its content fits most naturally.
- Judge by topic fit against the SPINE, not by shared words. An orphan whose section was cut is often
  cut for a reason; the right home is the section whose argument it actually advances.
- An orphan's tags tell you what it contributes — use them to break a tie between two plausible homes.
- If an orphan belongs to the NOT ABOUT world, it still has to go somewhere (nothing is dropped here),
  so put it where it does least damage and say so in "note".

Return ONLY this JSON, nothing else:
{"placements": [{"orphan": <orphan index>, "into": <survivor index>, "note": "<one line, only when the fit is poor>"}, ...]}
