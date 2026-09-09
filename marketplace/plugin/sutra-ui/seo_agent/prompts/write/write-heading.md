You are writing the final heading for ONE section of an article.

════════════════════════════════════════════════════════════════════════
BEFORE ANYTHING ELSE — THE LENGTH:
Aim for UNDER 60 CHARACTERS, and count as you write rather than after. Longer gets cut off in search
results and skimmed past on the page, so 60 is the box you write inside by default.
Go over it only when the shorter version genuinely says less — when trimming would cost the specific
thing (the number, the role, the named decision) that makes the heading worth reading. A 64-character
heading that lands beats a 58-character one that says nothing.
════════════════════════════════════════════════════════════════════════

THE ARTICLE
- Title: {{TITLE}}
- Distinct angle: {{ANGLE}}
- The spine — what this article argues, for whom, what the reader can do at the end:
  {{SPINE}}
- WHO THIS ARTICLE IS FOR:
{{PERSONA}}
- Primary keyword (the H1 targets this): {{PRIMARY}}
- Rewords of the primary: {{VARIATIONS}}

YOUR SECTION
- Working heading (a draft — you are replacing or keeping it): {{HEADING}}
- Its job: {{JOB}}
- The keyword researched FOR this section: {{SECTION_KEYWORD}}
- Other researched keywords still unused, if one fits better:
{{COVERS_BLOCK}}
{{POOL}}
- The evidence this section actually holds:
{{CARDS}}

────────────────────────────────────────────────────────────────────────
THE EVIDENCE TELLS YOU WHAT THIS SECTION ACTUALLY BECAME.

Its job was written before the research came back. The evidence is what it really holds now. Where the
two disagree, the evidence wins — a heading that promises what the section cannot deliver is worse than
a plain one.

CHOOSE A KEYWORD, IN THIS ORDER — and it is fine to end with none:
1. The keyword researched for this section. Does it name what this section delivers, and can the heading
   carry it without strain? If yes, use it.
2. If not, is there one in the pool above that fits this section better? Use that instead.
3. If not, would the primary or one of its rewords sit here naturally? It may — but only if it truly
   belongs; the H1 already carries it.
4. If none of them fit, use NO keyword. Write the best heading this section deserves on its own.

A well-researched keyword that does not fit is still a keyword that does not fit. Never force one in.

THE RULES for whatever you write:

- THE HEADING MUST STAND ALONE. It is read by three audiences who have read nothing else: a
  skimmer scanning the page, a searcher on a results page, and an AI agent lifting one section.
  If any of them needs the article's context to understand it, it fails. This is the test the
  last review failed hardest, so run it on every draft:
    Fails:  "The 40-Minute Ceiling: What Drops Off"        ← ceiling of what? drops off of what?
    Passes: "How Long a Skills Assessment Should Take"
    Fails:  "Validated for Whose Job? The Call Center Problem"
    Passes: "Check the Validity Study Covers Your Job Title"

- SIMPLE BEATS CLEVER, EVERY TIME. A heading is a plain promise, not a punchline. Never a
  rhetorical question, never a coinage the article invents, never a colon splicing a hook onto a
  label, never an idiom. If a colleague would ask "meaning what?", rewrite it plainly.

- A PRODUCT SECTION'S HEADING IS THE PRODUCT NAME PLUS A PLAIN DESCRIPTOR. When the section
  reviews one named tool in a list or ranking, the heading states the name and, in neutral
  professional words, the one thing the reader learns about it. No snark, no verdict-as-quip.
    Fails:  "Interviewer.AI's Face Match Is Sold, Not Included"
    Passes: "Interviewer.AI: Face Matching Costs Extra"
    Fails:  "Hireflix: An Invite Link Is Not an Identity Check"
    Passes: "Hireflix: No Built-In Identity Verification"

- USE THE READER'S OWN SEARCH WORDS FOR THE TOPIC. People Google "skills test types", not "the
  five test types" — a count or our own framing is not what anyone types. When the section covers
  a nameable topic, the heading carries that topic's plain name, the way a searcher would word it.

- SPECIFIC, NEVER GENERIC. "Overview", "Key considerations", "Things to know", "Best practices",
  "Understanding X" say nothing, and they are the default an AI reaches for. Name the actual thing: the
  role, the question a reader would ask out loud, the decision being made.
    Weak:   "Interview Question Considerations"
    Strong: "Questions to Ask a Candidate About Failure"
    Weak:   "Understanding Cost Per Hire"
    Strong: "What a Bad Hire Actually Costs You"

- NAME THE SUBJECT, NOT THE STATISTIC. Your default is a heading with NO figure in it. You are holding
  a pile of evidence and the pull towards putting its best number in the heading is strong — resist it.
  Every other section writer is being pulled the same way, none of you can see the others, and an
  article whose headings are a column of percentages reads as a spreadsheet. A reader came for the
  subject; the numbers are what they find when they get there.

  A figure earns a place in the heading ONLY when the figure is itself the subject of the section —
  when the section's whole job is to settle, date or demolish that specific number. If the section
  merely reports a number, the number stays in the body.
    Subject is the time:   "How Long Recruiters Actually Spend on a Resume"
    not                    "Recruiter Time Spent Reading a Resume: 6 Seconds, or 1 Minute 34?"
    Subject is the number: "The 75% ATS Rejection Rate Was a 2012 Sales Pitch"    ← the figure IS the point
    Subject is the trend:  "Who Lies on a Resume, and About What"
    not                    "Resume Lying: 32% in 2021, 44% and 64.2% in 2025"

  Two figures in one heading is never right. A heading opening with a bare number is never right.

- SAY IT THE WAY A PERSON WOULD. If you would not say the heading out loud to a colleague, rewrite it.
  A colon splicing a subject onto a pair of statistics is not something anyone says.

- ONE keyword only, never two. A heading holding two search phrases reads as written for a machine.

- SAY WHAT THE SECTION DELIVERS. After your edit it must still match its job and its evidence.

════════════════════════════════════════════════════════════════════════
THE USER'S STANDING RULES. They were set by the person publishing this and they win over any
rule above that they contradict. "(none)" means there are none.
{{MEMORY}}

Return ONLY this JSON, nothing else:
{"heading": "<the final heading, aiming under 60 characters>",
 "keyword_used": "<the phrase you carried, or null>",
 "why": "<one short line: why this heading, and why that keyword or none>"}
