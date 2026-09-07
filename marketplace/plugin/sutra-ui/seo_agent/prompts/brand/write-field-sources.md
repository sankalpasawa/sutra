You are writing the short reference file that tells a later step where this company's audience talks,
and what to expect from each place.

THE COMPANY: {{BRAND}}
WHAT IT DOES: {{NICHE}}

## How the three sources work

This is the fixed capability list. Do not restate it in full; the file you write is a companion to it,
not a replacement.

{{SOURCES}}

## The subreddits, already checked against Reddit

Each was proposed, then searched. `posts` and `comments` are what the check actually found in the last
year. Nothing here is a guess.

KEPT:
{{KEPT}}

REJECTED:
{{REJECTED}}

UNVERIFIED (Reddit could not be reached for these, so nothing is known about their activity):
{{UNVERIFIED}}

## Write the file

```markdown
# Field sources — {{BRAND}}
Niche: {{NICHE}}
Verified: {{TODAY}}

## Reddit
The planner may ONLY name subreddits from this table.

| Subreddit | Who is in there | Activity |
|---|---|---|
| ... | ... | ... |

Rejected: ...

## Teamblind
[Two or three lines: it has no filters, so a query is all you get. What this company's audience would
be doing on it, and which side of the table shows up there.]

## LinkedIn
[Two or three lines: no filters, and posts are written for an audience, so it shows the prevailing take
rather than a complaint.]
```

## How to fill it

- **The table is the point.** Every kept subreddit gets a row. `Who is in there` is one short line
  naming the actual people, in plain words, so a later step can aim a query at the right room.
- **Activity** is `very active`, `active` or `moderate`, decided from the numbers you were given.
  Do not invent a number and do not print the raw counts.
- **Rejected** is one line, naming them with a two-word reason each. It exists so that when a search
  returns nothing later, somebody can tell "we checked and dropped it" from "we never looked".
- An **unverified** subreddit gets a row too, with Activity `unverified`, so a later step can still aim at it
  and a person can check it by hand. Never present it as checked.
- Where a subreddit is one-sided or angry, **say so in its row**. That is the most useful thing you can
  record about it.
- The Teamblind and LinkedIn sections carry **no settings**, because neither has any. They say what to
  expect, so nobody writes a query assuming a filter that does not exist.
- Simple English, short sentences. This is a reference file somebody reads in twenty seconds.

Output ONLY the markdown file. No preamble.
