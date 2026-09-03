You are checking one finished article for coverage. You are not editing it. You are not scoring its
quality. You answer one question per item: does this article genuinely cover this, yes or no.

────────────────────────────────────────────────────────────────────────
WHAT COUNTS AS COVERED

Covered means a reader looking for this would find it answered here, in the article's own words.

  · It does NOT have to use the wording of the item. An article that says "cost per hire is what you
    spend to source, assess and hire one person, divided by the hires you made" covers "Definition of
    cost per hire" perfectly, without ever using the word "definition".
  · It does NOT need its own heading. Covered inside another section still counts.
  · One passing mention is NOT coverage. "Agency fees also matter" does not cover agency fees.
    A reader has to come away knowing the thing.

Judge what is on the page. Do not give credit for what the article implies, gestures at, or could
reasonably be assumed to mean.

────────────────────────────────────────────────────────────────────────
LIST ONE — THE TOPICS EVERY RANKING PAGE COVERS

{{TABLE_STAKES}}

────────────────────────────────────────────────────────────────────────
LIST TWO — GOOGLE'S OWN ANSWER FOR THIS SEARCH

This is the AI Overview: the answer Google itself writes at the top of the results page. It is one
block of prose, and it names a set of things.

{{AI_OVERVIEW}}

FIRST, ONE QUESTION ABOUT IT: is Google's answer even about the same subject as this article?

Usually it is. Sometimes it is not, because the search phrase has a second meaning and Google picked
the wrong one — "CV" is a curriculum vitae to a recruiter and the coefficient of variation to a
statistician, and Google's answer may be entirely about the second. When that happens the AI Overview
tells us nothing about what this article should contain, and judging the article against it would mark
it down for not explaining an unrelated subject.

So set "ai_overview_on_topic" to false when Google's answer is about a genuinely different subject,
and return an EMPTY "ai_overview" list. Do not judge the article against it at all.

A partial overlap is still on topic. Set it false only for a different subject entirely.

When it IS on topic, break it into the separate things it names. Keep them short, one idea each, in
the order they appear. Expect somewhere between four and ten. Then judge each one against the article.

────────────────────────────────────────────────────────────────────────
THE ARTICLE

{{ARTICLE}}

────────────────────────────────────────────────────────────────────────
Return JSON, nothing else:

{"table_stakes": [{"topic": "<copied exactly from list one>", "covered": true, "where": "<the heading it is covered under, or a few words of the sentence that covers it>"}],
 "ai_overview_on_topic": true,
 "ai_overview_subject": "<only when false: what Google's answer is actually about, in a few words>",
 "ai_overview":  [{"element": "<the thing Google names, in your own short words>", "covered": false, "where": ""}]}

Every item in list one gets exactly one row, copied exactly as written. Leave "where" empty when
covered is false.
