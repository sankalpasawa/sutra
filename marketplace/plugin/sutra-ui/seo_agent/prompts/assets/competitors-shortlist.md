You are building the competitor shortlist for **{{BRAND}}**. {{ONELINER}}

What this company is about: {{NICHE}}

# Your job

From the candidate list below, pick the **{{N}}** competitors worth studying, and split them into two
groups. The list came from a keyword-overlap tool, so it is full of sites that are not competitors at
all: big publishers, dictionaries, universities, job boards and general media that happen to rank for
similar words. Throwing those out is the first half of the job.

# The two groups

- **DIRECT**: sells the same kind of product to the same buyer. If a buyer could realistically pick
  them INSTEAD of {{BRAND}}, they are direct. Aim for about two thirds of the list.
- **ADJACENT**: does not sell the product but owns the audience: the authority sites, industry
  bodies and content leaders this buyer already reads and links to. They matter because their pages
  show which SHAPES of page earn links in this world. Aim for about one third.

# Hard exclusions, whatever they rank for

A site in any of these classes is out even if it is famous, authoritative and all about this
industry. Being about the industry is not the same as being a competitor or a content leader.

- General business and management media (Harvard Business Review, Forbes, Inc., Fast Company,
  Business Insider, Entrepreneur, and anything of that kind). They publish on every industry. They do
  not own THIS audience. One of these slipped through on 2026-07-20; do not repeat it.
- News and consumer media of any kind.
- Reference, encyclopedia, dictionary and academic sites, and universities.
- Software review and directory sites (G2, Capterra, TrustRadius, GetApp, SoftwareAdvice). They list
  the category; they are not in it. One of these slipped through too.
- Document sharing, question-and-answer, forum, course and general e-learning platforms.
- Job boards and general career sites, unless the company genuinely sells against them.
- Anything whose overlap is clearly incidental: it ranks for a shared word, not a shared business.

An ADJACENT pick has to own this specific buyer's attention: a professional body, a specialist
publication, a training academy, or a vendor whose content library this exact buyer reads. If you
cannot name that relationship in one line, it is not adjacent, it is excluded.

# How to work, and the order matters

1. **Sweep the whole list for DIRECT competitors first and take every one you find.** Be thorough.
   Do not stop early because a candidate sits low down: the list is ranked by keyword overlap, not by
   how directly a company competes, so real rivals turn up deep in it. Measured on 2026-07-20, four
   genuine direct rivals sat at ranks 52, 100, 120 and 134 and were missed.
2. Only then fill the remaining slots with the strongest ADJACENT sites.
3. If the direct competitors alone come to more than {{N}}, return them all. Going over is fine.
   Missing a direct rival is not.

Read each candidate's description where there is one. It is what the company says about itself, so
trust it over what the domain name suggests.

# Rules

- Pick from the candidate list only.
- **One company, one row.** Some companies appear twice under a brand domain and a legacy one.
  Return the company once.
- Say plainly when you are not sure rather than inventing a detail.
- If there are fewer than {{N}} genuine competitors in the list, return fewer. Never pad with
  publishers to reach a number.

# Before you answer, audit your own list

Re-read every row you are about to return and delete any that fails:

1. Does it break a hard exclusion above? Delete it.
2. Is it the same company as another row? Merge them.
3. For an adjacent row: can you name in one line why this buyer reads it? If not, delete it.
4. For a direct row: would a buyer really choose it instead of {{BRAND}}? If not, move it to
   adjacent if it owns the audience, or delete it.

A shorter, cleaner list is the goal. A junk competitor pollutes every step after this one.

# Return

JSON only.

```
{"competitors": [
   {"domain": "example.com", "group": "DIRECT",
    "why": "one short line: what they sell, or whose audience they own"}],
 "excluded_notable": ["domain: why it was thrown out (only the ones that ranked high and might surprise a reader)"],
 "note": "one line on anything worth knowing, for example a competitor you expected and could not find"}
```

# The candidates

{{CANDIDATES}}
