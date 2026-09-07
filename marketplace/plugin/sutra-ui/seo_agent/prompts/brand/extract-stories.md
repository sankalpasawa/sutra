You are reading ONE page from {{BRAND}}'s own website ({{NICHE}}) — a success story, press release, or
podcast page. Your only job: extract the ANECDOTE it tells, if it tells one worth retelling in an article.

A story worth keeping has:
- a real actor (a named or clearly-described customer/person/team)
- a change (before → after, a problem → what happened)
- ideally a NUMBER carried by the page itself

Rules:
- write `story` in 2-4 plain sentences, faithful to the page — NEVER add facts the page doesn't state
- `point` = the one thing this story proves (why a writer would tell it)
- `number` = the exact figure the page ties to the story, or "" if none
- a page that is really a feature list / marketing copy with no actor or change: return {"none": true}

Return ONLY JSON:
{"title": "...", "story": "...", "point": "...", "number": "..."}
or {"none": true} if there is no real story on this page.

PAGE URL: {{URL}}
PAGE TITLE: {{TITLE}}
PAGE TEXT:
{{BODY}}
