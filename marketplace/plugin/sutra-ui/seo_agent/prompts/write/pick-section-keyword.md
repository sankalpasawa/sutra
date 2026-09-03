Pick the ONE keyword this section should target, from the real search data below — or none.

THIS SECTION
- Working heading: {{HEADING}}
- Its job: {{JOB}}
- What it is really about (from its evidence): {{WHY}}

ARTICLE CONTEXT
- The spine: {{SPINE}}
- What this article is NOT about: {{NOT_ABOUT}}
- WHO THIS ARTICLE IS FOR:
{{PERSONA}}
- The primary keyword (the H1's): {{PRIMARY}}

CANDIDATES (keyword | monthly volume | difficulty):
{{CANDIDATES}}

────────────────────────────────────────────────────────────────────────
CHOOSE by fit first, volume second:

- It must name what THIS section delivers. A bigger number for a phrase the section does not answer is
  worth nothing — the page ranks and the reader bounces.
- Reject a phrase searched by the wrong person. A keyword the other side of the table types brings a
  visitor this article was not written for, and a high-volume one does that at scale.
- Reject anything from the NOT ABOUT world, whatever its volume. A phrase that matches our words but
  belongs to another field is the most damaging pick available here.
- Do not pick the primary or a reword of it. The H1 owns that.

RETURNING NOTHING IS A GOOD ANSWER. If no candidate genuinely names this section, return null and say
why. Do not stretch.

Return ONLY this JSON, nothing else:
{"keyword": "<the phrase, or null>", "volume": <n or null>, "kd": <n or null>,
 "why": "<one line: why this fits, or why nothing did>"}
