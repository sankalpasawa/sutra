# The field sources — what each one is, and how you search it

The same for every company. This is the capability list: three places where people who care about a
subject talk about it in public. Nothing here is about WHEN to use a source. All three are searched
every time, and the article's own probe decides what was worth reading.

Adding a fourth source later means adding a section here and one adapter file.

---

## Reddit

**What it is.** Topic communities called subreddits. The people who do a job talking to each other about
doing it: what broke, what they tried, what their leadership asked for.

**What you must give it.** A query **and the subreddits to search in**. There is no useful site-wide
search, so the subreddit list is a required input. That is the whole reason a per-company step exists.

**How its search behaves.**
- Plain keyword matching inside one subreddit. No operators, no quotes, no exclusions.
- One page of results per search.
- Sorted by relevance, not by date. A `t=year` window is the only time control.

**How to shortlist.** Rank by **comment count, not upvotes**. Upvotes mean people agreed. Comments mean
people argued, and the argument is what we came for. A thread with 60 upvotes and 220 comments is worth
more than one with 2,000 upvotes and 30 comments.

**Cost.** Free through `old.reddit.com` HTML. It rate-limits an IP that scrapes hard and starts serving
a login page instead of results, at which point the paid endpoint takes over. Roughly one credit per
search and one per comment fetch.

**Its weakness.** Some subreddits are overwhelmingly one mood. A venting community will make any
complaint look universal. Read the subreddit's description before trusting how widespread something is.

---

## Teamblind

**What it is.** Anonymous posts from people at named employers. **Every poster carries a verified
company**, which nothing else in this list gives you. Both sides are here: people being hired, and
people doing the hiring.

**What you must give it.** A query. That is all there is.

**How its search behaves.**
- Searches the whole site. **No date filter, no channel filter, no operators.**
- 20 results per query, and pagination does not work.
- Channels exist and are visible on each result, but you cannot search inside one.

**How to shortlist.** Because 20 is the hard ceiling, use **several narrow queries rather than one broad
one**. Each query finds a different corner. Then rank by comment count, same as Reddit.

**Cost.** Free. Public pages, no account, no login.

**Its weakness.** It skews heavily to large tech employers. A pattern that is real at a 50,000-person
company may say nothing about a 50-person one.

---

## LinkedIn

**What it is.** Public posts, written by people building a professional reputation. This is the polished
version of an opinion, not the raw one.

**What you must give it.** A query.

**How its search behaves.**
- Keyword search over posts indexed publicly. No operators.
- A recency window is the only control.
- Comments come back with some posts, not all.

**How to shortlist.** Do not look for complaints here, there are none. Look for **what the prevailing
take already is**, so an article can push against it or avoid repeating it as if it were new.

**Cost.** One credit per search.

**Its weakness.** Much of it is marketing. A post from a vendor whose only comment is that vendor
linking its own blog is an advertisement, not a view. Treat an unusually tidy insight as a warning that
it is already a platitude.

---

## What holds across all three

- **Comments over upvotes.** Every time.
- **Several narrow queries beat one broad query.** Broad queries match the topic word and return
  whatever else happens to use it.
- **Search the experience, not the industry term.** People type what happened to them. Nobody searches
  their own field's vocabulary.
- **A zero-result search is ambiguous.** It can mean the query was wrong, the community was wrong, or
  nobody discusses it. Never read it as the last one without checking the first two.
