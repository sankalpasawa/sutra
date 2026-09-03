You are turning ONE cluster of research cards into a section of an article: a working H2 label, one line on
the job the section does for the reader, plus H3 sub-sections if the cluster covers several distinct sub-points.

THE ARTICLE THIS SECTION BELONGS TO
- Title: {{ASSET}}
- Distinct angle (what this article specifically does): {{ANGLE}}
- What this article IS about: {{ABOUT}}
- What this article is NOT about: {{NOT_ABOUT}}

Standing rules from the user:
{{MEMORY}}

READ THE TITLE BEFORE YOU NAME ANYTHING. It tells you what shape the heading takes, and getting that
wrong is the single most expensive mistake at this step. A heading written in the wrong shape survives
every later stage and reaches the reader, because nothing downstream knows what the shape should have
been.

Name the section the way this article's title implies:

- A title promising a GLOSSARY or a set of DEFINED TERMS wants the term itself as the heading.
  "Cut score". "Adverse impact". "Norm group". Not "How do you set a cut score?"
- A title promising a RANKING or a COMPARISON of named things wants the thing as the heading.
  "Pymetrics". "HireVue". Not "How does one AI hiring tool's bias audit work?"
- A title promising STATISTICS, DATA or NUMBERS wants the claim or the figure as the heading.
  "The six-second scan was revised to 7.4 seconds". Not "Is the six-second scan still true?"
- A title promising a HOW-TO, a PROCESS or a GUIDE is the one case where a question heading fits.
  Use one there, and only there.

If the title does not clearly imply a shape, write a plain descriptive label. When in doubt, prefer a
noun phrase over a question: a question heading is the default this step used to reach for, and it
turned glossaries and rankings into Q&A guides.

You are given the cluster's cards as "id: gloss" lines.

Do this:
- Write a working H2 label, in the shape the title implies. It is a DRAFT, not final polished wording
  (final wording is decided later by the writer).
- Write "job": one plain line on what this section does for the reader, built only from the cards below.
- If the cluster clearly splits into 2+ distinct sub-points, create H3s and assign EACH card id to exactly one
  H3. If the cluster is one tight idea, use no H3s and list all card ids directly under the H2.
- Every card id you were given must appear exactly once, either directly under the H2 or under one H3.

Output STRICT JSON, nothing else:
{
  "h2": "<working H2 label>",
  "job": "<one line: what this section does for the reader>",
  "h3": [ { "h3": "<working H3 label>", "card_ids": [1, 2] } ],
  "card_ids": [3, 4]
}
(`h3` is [] if there's no split; `card_ids` is the cards that sit directly under the H2.)

--- CLUSTER CARDS (id: gloss) ---
{{CARDS}}
