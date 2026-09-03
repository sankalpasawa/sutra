You are choosing the ONE reader persona for a {{BRAND}} article, to steer research depth and the write phase.
Apply the rules that ALREADY live in the persona doc below — don't invent new ones.

ARTICLE
- Title: {{ASSET_TITLE}}
- Angle (what it specifically covers): {{ANGLE}}

STANDING RULES FROM THE USER:
{{MEMORY}}

PERSONA DOC (has a "How to pick one per article" section — follow it exactly):
{{PERSONA_DOC}}

Pick the ONE best-fit persona using the doc's "How to pick" rules. If it could fit two, pick the one who
DECIDES or ACTS on the topic. (This sets depth + angle only — the persona is NEVER named in the article.)

RETURN JSON only:
{ "name": "<exact persona name from the doc>",
  "lens": "<one line: who they are + what they need from THIS article — used to score cards + write>",
  "why":  "one line tying them to the topic/intent" }
