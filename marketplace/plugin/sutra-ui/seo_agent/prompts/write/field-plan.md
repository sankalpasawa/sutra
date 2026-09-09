You are deciding what to type into Reddit's search box to find what real practitioners say about this
article's subject.

THE ARTICLE
- Title: {{TITLE}}
- Distinct angle (what it is built to deliver): {{ANGLE}}
- What it argues (the spine): {{SPINE}}
- Written for: {{PERSONA}}

ITS SECTIONS, and what each one must deliver:
{{SECTIONS}}

════════════════════════════════════════════════════════════════════════
WHERE THIS COMPANY'S PEOPLE ACTUALLY ARE

Every subreddit below has been checked against Reddit and is live. **You may only name subreddits from
this list.** Anything else is thrown out before it is searched.

{{FIELD_SOURCES}}

════════════════════════════════════════════════════════════════════════
HOW TO WRITE A QUERY. This decides whether any of this works.

**Type what a person types, not what the industry calls it.** Nobody sits down and searches "cost per
hire" or "structured interview validity". They search the thing that happened to them.
  - the article says "cost per hire understates the true cost"
    -> a recruiter types "lost the candidate waiting on approval"
  - the article says "take-home assessments filter out good candidates"
    -> a candidate types "take home assignment 8 hours"

**Three to six words.** These are plain keyword searches. No operators, no quotes, no exclusions. A long
query returns nothing at all.

**Aim each query at a section's job**, so what comes back can be used rather than just admired.

**Make each query find what the others will not.** Six queries returning the same threads are one query.
Vary the angle: the complaint, the defence, the workaround, the number, the horror story.

**Send each query to the right rooms.** A query about running a process goes to the subreddits where
people run it. A query about how it feels goes to the ones where it is done to them. Naming every
subreddit for every query wastes searches and returns noise.

════════════════════════════════════════════════════════════════════════
Return ONLY this JSON:

{"reddit": {"queries": [{"q": "<3-6 words>",
                         "subreddits": ["<from the checked list only>"],
                         "serves": "<section number, or 'angle'>",
                         "why": "<one line: what you expect this to surface>"}]}}

Four to six queries. No more.
