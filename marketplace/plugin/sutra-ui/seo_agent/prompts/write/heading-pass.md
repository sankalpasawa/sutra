Every heading in this article was written by a different writer, and each of them saw only their own
section. Nobody has yet read the headings as a set. That is your job, and it is the only way to catch
what none of them could: numbering that does not run, one thing called two names, half the article in
Title Case and half in sentence case, eight headings in a row built to the same template.

You are reading them as a reader will — as a list, top to bottom, before they read a single word of
the body.

ONE THING ONLY YOU CAN SEE. Is there a topic this article clearly covers that no heading names in
the words a reader would search for? A section can answer a question perfectly and still be
invisible, because its heading was written cleverly instead of plainly. If you find one, the
section covering it should say so in its own words.

THE ARTICLE
- Title: {{TITLE}}
- Distinct angle: {{ANGLE}}
- The spine — what this article argues, for whom, what the reader can do at the end:
  {{SPINE}}
- WHO THIS ARTICLE IS FOR:
{{PERSONA}}
- Primary keyword (the H1 targets this): {{PRIMARY}}

THE HEADINGS, in order. Each shows the section's JOB (what it must deliver) and, where research
bought one, a LOCKED keyword:
{{HEADINGS}}

────────────────────────────────────────────────────────────────────────
TWO THINGS YOU MAY NEVER CHANGE:

1. A LOCKED KEYWORD. Where a heading is marked LOCKED, that phrase stays in it, word for word. It was
   chosen from real search data. You may move it within the heading, reword everything around it, and
   rewrite the rest freely — and you may change its capitalisation to match the rest of the list — but
   not one word of it changes, and nothing is added inside it. Code checks every locked phrase; a
   heading that lost one is thrown out and the original put back.

   THE ONE EXCEPTION IS A HEADING MARKED **OVER-USED**. Every heading above was written on its own, by
   a writer who could not see the others, so each was offered the same keyword and each accepted it.
   Nobody counted. You are the first to see the result:

{{OVERUSED}}

   A phrase repeated across most of the headings makes the page read as written for a search engine
   rather than a person, and the H1 already carries the article's main keyword. So for each phrase
   above: decide which {{KEYWORD_CAP}} headings genuinely earn it — the ones where someone typing that
   phrase would be satisfied landing on THAT section, not merely where it fits — and TAKE IT OUT of
   every other one.

   TAKE THE PHRASE OUT, DO NOT REBUILD THE HEADING. Change the fewest words that remove it and leave a
   heading that still reads well and still matches its job. You are removing a repetition, not
   rewriting from scratch, and a heading you rebuild is a heading you can break.

   Code enforces the other side of this: each of those phrases must still appear in at least
   {{KEYWORD_CAP}} headings when you are done. Strip it from too many and the whole pass is thrown
   away, so do not overshoot.

2. THE JOB. A heading promises what its section delivers. Rewrite the promise however you like, but
   after your edit it must still be a promise that section can keep. Never point a heading at
   something the section does not do.

Everything else is yours. You may not add, remove or reorder sections — same headings, same count,
same order, in and out.

────────────────────────────────────────────────────────────────────────
FIRST DUTY — fix what only the whole set reveals. These are the real reason this step exists:

- NUMBERING THAT DOES NOT RUN. If some headings are numbered, they run 1, 2, 3 with nothing skipped
  and nothing repeated. "Step 1 … Step 5, Step 16" is broken. Fix it one of two ways, never a third:
  RENUMBER when the article really is a procedure the reader works through in order — the numbers are
  telling them where they are, and that is worth keeping. DROP the numbers from every heading when
  only a handful of sections are steps and the rest are not; a short numbered run inside a mostly
  unnumbered article promises a sequence the article does not have. Never leave a partial sequence.
- ONE NAME PER THING. If section 4 says "BARS" and section 9 says "behaviorally anchored rating
  scale", the reader thinks they are two topics. Pick the form that serves each spot — the full name
  where it is first explained, the short one later — but never two names with no signal they are the
  same thing.
- ONE CASE. All Title Case, or all sentence case. Whichever most of the headings already use, make
  the rest match. A mixed list looks unproofed before a word is read.
- BREAK THE TEMPLATE. When four or more headings in a row open with the same construction — "Why X
  is Y", "How to X", "The X of Y" — the list reads as generated. Vary the ones that can carry a
  different shape without losing what they say. Do not vary for the sake of it; a run of three is
  fine.

- TOO MANY NUMBERS IN THE LIST. This is the one you are most likely to find, and only you can see it.
  Every heading above was written by someone holding a pile of statistics, alone, with no idea what
  the others were doing. Each reached for their best figure. Nobody counted. Code has:

{{FIGURE_HEAVY}}

  A list of headings that is mostly percentages and years reads as a spreadsheet, not an article. The
  reader came for the subject. So decide which headings genuinely EARN their figure — the ones whose
  whole job is to settle, date or demolish that specific number, where the number IS the subject —
  and TAKE THE FIGURE OUT of the rest, leaving a heading that names what the section is actually
  about. At most {{FIGURE_CAP}} headings may keep one.

    Earns it:      "The 75% ATS Rejection Rate Was a 2012 Sales Pitch"   ← demolishing that number
    Does not:      "Recruiter Time Spent Reading a Resume: 6 Seconds, or 1 Minute 34?"
    becomes:       "How Long Recruiters Actually Spend on a Resume"
    Does not:      "Resume Lying: 32% in 2021, 44% and 64.2% in 2025"
    becomes:       "Who Lies on a Resume, and About What"

  The figures do not disappear — they are in the body, where a reader meets them in context. And a
  heading you strip must still name its section's subject; do not leave a vague one behind.
  A LOCKED keyword still survives this. Take out the number, keep the phrase.
- A HEADING AIMED AT THE WRONG PERSON. Read the list as that reader. A heading written for the other
  side of the table — "How to Answer X" in an article for the people ASKING X — tells them this page
  is not for them, and one is enough to lose them. You cannot delete the section, but you can turn
  the heading round to face the right reader.
- NO TWO HEADINGS THAT PROMISE THE SAME THING. If two headings would send a reader to the same
  answer, sharpen each so the difference between them is visible in the words.

SECOND DUTY — improve any heading that is weak on its own:

- A LABEL IS NOT A HEADING. "How we compiled these figures" files the section away. "Which figures we
  kept apart, and why" tells the reader what they get. Name the actual thing: the number, the role,
  the question someone would ask out loud, the decision being made.
- SPECIFIC, NEVER GENERIC. "Overview", "Key considerations", "Things to know", "Best practices",
  "Understanding X" say nothing, and they are what an AI reaches for by default.
- NEVER TRADE A PLAIN HEADING FOR AN ABSTRACT ONE. "Score how AI was used, not whether it was used"
  beats "Scoring AI Collaboration Quality" — the first is a sentence a person would say, the second
  names a concept. When your edit swaps everyday words for a noun phrase, you have made it worse.
  Leave it as it was.
- UNDER 60 CHARACTERS where you can. Longer gets cut off in search results and skimmed past on the
  page. Go over only when the shorter version genuinely says less — when trimming would cost the
  specific thing that makes the heading worth reading. Reading them as a set, you can also see when
  one heading is three times the length of its neighbours; even those out.
- LEAVE A GOOD HEADING ALONE. Most of them will already be right. Changing a heading that works is a
  cost with no gain, and it buries the changes that matter. Return it unchanged and say so.

────────────────────────────────────────────────────────────────────────
Return EVERY heading, in the same order, changed or not.

════════════════════════════════════════════════════════════════════════
THE USER'S STANDING RULES. They were set by the person publishing this and they win over any
rule above that they contradict. "(none)" means there are none.
{{MEMORY}}

Return ONLY this JSON, nothing else:
{"headings": [{"n": <the number shown above>,
               "heading": "<the final heading — unchanged, or your edit>",
               "changed": true | false,
               "why": "<one short line, only when changed; empty string when not>"}],
 "notes": "<one or two lines: what you found across the set, or empty if nothing needed fixing>"}
