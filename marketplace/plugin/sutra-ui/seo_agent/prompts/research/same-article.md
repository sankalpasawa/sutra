You are checking ONE thing before an article's research begins: is the keyword we are about to
build on actually about the article we are writing?

THE ARTICLE WE ARE WRITING
- Working title: {{TOPIC}}
- What it is about: {{ABOUT}}
- What it is NOT about: {{NOT_ABOUT}}

THE KEYWORD WE ARE ABOUT TO BUILD ON: {{KEYWORD}}

THE PAGES GOOGLE ACTUALLY RANKS FOR THAT KEYWORD — titles and addresses, exactly as returned:
{{RANKING_PAGES}}

────────────────────────────────────────────────────────────────────────
WHY THIS CHECK EXISTS, in one real case.

An article titled "Skills Assessment: From Resume Claim to Cut Score" was given the keyword
"behavioral interview questions", because that phrase had 12,100 searches a month and the keyword
was picked on volume. The pages ranking for it were all "30 behavioral interview questions to ask"
listicles. Everything downstream then studied those listicles: what readers expect, what the format
should be, where the openings were. None of it had anything to do with cut scores. The whole run,
and the money it spent, was research into a different article.

ASK ONE QUESTION AND NOTHING ELSE.

If somebody clicked these ranking pages expecting what they searched for, and then landed on OUR
article instead, would they feel they had found the right kind of page, or the wrong one?

  SAME ARTICLE   the ranking pages and our article answer the same need. They may be worse than
                 ours, narrower, older, aimed at a slightly different level. That is competition,
                 not a mismatch, and it is what we want.
  DIFFERENT      the ranking pages are a different kind of page about a different question. Our
                 article would be an odd result for this search however well it is written.

BE SLOW TO SAY DIFFERENT. Most keywords are fine, and rejecting a good keyword costs a better one.
Say DIFFERENT only when you can name the mismatch in a few plain words. Sharing a subject area is
not a mismatch. Sharing an audience is not a mismatch. Answering a different question is.

If the pages list is empty or unreadable, answer SAME: we cannot prove a mismatch from nothing, and
a check that cannot run must not be the reason a run stops.

Return ONLY this JSON, nothing else:
{"same_article": true|false,
 "why": "<one short plain line: what the ranking pages are about, and whether that is us>"}
