You are cleaning three lists Google returned for one article: "People Also Ask" questions, and related
searches. Keep ONLY the entries a reader of THIS specific article would genuinely care about. Off-topic
entries otherwise become fake coverage "holes" that drag unrelated facts into the article.

THE COMPANY publishing this article: {{BRAND}} — {{ABOUT}}

THE ARTICLE:
- Title: {{TITLE}}
- Distinct angle (what this article is built to deliver): {{ANGLE}}
- What this article IS about: {{WORLD_ABOUT}}
- What this article is NOT about: {{WORLD_NOT_ABOUT}}

PEOPLE-ALSO-ASK QUESTIONS:
{{QUESTIONS}}

RELATED SEARCHES:
{{RELATED}}

TOPICS THE RANKING PAGES SHARE (the table stakes — what a reader arriving here already expects):
{{TABLE_STAKES}}

Rules:
- FIRST, THE WORLD TEST. Read the NOT ABOUT line. Google returns these lists for the words in a query,
  not for the audience behind it, so a share of them belong to a neighbouring field that uses the same
  words: a different industry, a student or academic use, a clinical use, a different buyer entirely.
  Those are DROPPED however well they match, because a kept one becomes a coverage "hole" that pulls
  that field's facts into this article.
- KEEP an entry if it is on-topic for this article, or about the article's core subject or its immediate
  family even when broader (e.g. for a "Type D personality" article, keep "what are type A, B, C, D
  personalities?"). Broader is fine. A DIFFERENT WORLD is not, and the two are easy to confuse: broader
  still serves this reader, another world serves someone else.
- DROP the clearly off-topic: celebrity/person trivia, ranking/IQ trivia, an unrelated subject or framework,
  and entries about some OTHER company's brand that this article has no reason to cover.
- Return kept entries VERBATIM, exactly as given.

THE TABLE STAKES ARE JUDGED THE SAME WAY, WITH ONE EXTRA RULE.
- Apply the world test first, exactly as above: a topic every ranking page covers can still belong
  to a neighbouring field, and those go however common they are.
- Then KEEP AT MOST {{MAX_TABLE_STAKES}}, the ones a reader of THIS article would actually expect
  to find. Fewer is fine.
- Rank what you keep by how much a reader would miss it, most-missed first. That order is used
  later to decide what the article covers early, so it carries real weight.
- Drop a topic this article's angle has no reason to touch, even if every competitor covers it.
  A list of ten expected topics turns into a checklist; a short list of real expectations does not.

Return ONLY this JSON, nothing else:
{"keep_questions": ["<verbatim>", ...],
 "keep_related": ["<verbatim>", ...],
 "keep_table_stakes": ["<verbatim, most-missed first>", ...]}
