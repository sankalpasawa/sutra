You are deciding which sections of an article should target a search keyword — and which should not.

Most sections should NOT. An article has one main search target (its H1) and a handful of sections that
answer a real search of their own. The rest exist to carry the argument: they set up, they connect, they
conclude. Giving those a keyword produces a forced heading and wastes a paid lookup.

THE ARTICLE
- Title: {{TITLE}}
- Distinct angle: {{ANGLE}}
- The spine — what this article argues, for whom, and what the reader can do at the end:
  {{SPINE}}
- What this article IS about: {{ABOUT}}
- What this article is NOT about: {{NOT_ABOUT}}
- The primary keyword (the H1 already targets this): {{PRIMARY}}
- WHO THIS ARTICLE IS FOR:
{{PERSONA}}

THE SECTIONS, in order:
{{SECTIONS}}

────────────────────────────────────────────────────────────────────────
For EACH section answer one question: would THE READER ABOVE type this section's subject into Google
as their own search? Not anyone — that reader. A phrase the other side of the table searches for
(the candidate rather than the recruiter, the employee rather than the manager) brings the wrong
visitor to the page, and they leave.

Say YES when:
- the section answers a question someone would ask on its own, outside this article
- it names a thing people look up: a method, a number, a comparison, a cost, a process
- someone could land on this section from a search and be satisfied

Say NO when:
- it only makes sense inside this article's argument
- it sets up, bridges, concludes or summarises
- its subject is the primary keyword again, just from a different side — the H1 already owns that
- it is about our own product or the closing pitch

Expect roughly a third to a half of the sections to be YES. If you are saying yes to nearly all of them,
you are being too generous — go back and cut to the ones a stranger would genuinely search for.

Return ONLY this JSON, nothing else:
{"sections": [{"n": <number>, "hunt": true|false, "why": "<one short line>"}]}
