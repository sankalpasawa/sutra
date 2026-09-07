You are naming the Reddit communities where a particular company's audience talks to each other.

THE COMPANY: {{BRAND}}
WHAT IT DOES: {{NICHE}}

WHO ITS CONTENT IS WRITTEN FOR:
{{PERSONA}}

## What you are looking for

Subreddits where **the people described above** post. Not subreddits about the company, and not
subreddits about the industry in the abstract. Rooms where the actual humans complain, argue, ask each
other for help, and describe what happened at work.

Name up to {{N}} candidates. **Every one you name will be checked against Reddit**, and the dead ones
and the invented ones will be thrown out, so it costs nothing to include one you are unsure about. It
costs a lot to miss a good one.

## Cover all four of these

1. **The job itself.** Where people who do this work talk shop.
2. **The other side of the table.** Whoever this audience acts upon, deals with, or sells to. Their
   complaints are the same events seen from the other end, and that contrast is worth more than either
   side alone.
3. **The tier below.** Where people do this job WITHOUT a dedicated function or budget: small business
   owners, solo operators, people who inherited the task. They speak plainly because they have no
   professional vocabulary to hide behind.
4. **The adjacent trade.** The specialists this audience has to work with, who see its failures from
   outside.

## Rules

- **Real names only, exactly as spelled on Reddit.** No `r/` prefix. Case matters.
- Prefer a **specific** community over a giant general one. A giant one buries the topic.
- Include the **venting** communities. They are one-sided, and that is fine: the honest complaint is
  still data, and a later step knows to discount the mood.
- Do NOT include communities that are mostly job adverts, mostly memes, or mostly self-promotion.

## Return ONLY this JSON

{"subreddits": [
  {"name": "<exact subreddit name, no r/ prefix>",
   "who": "<one short line: who posts there>",
   "covers": "the job" | "the other side" | "the tier below" | "the adjacent trade"}]}
