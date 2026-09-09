You are tagging Reddit posts from {{BRAND}}'s niche with the phrases that capture what each post is
about. A later step finds the pains that recur across many posts, so being faithful to this post
matters far more than being clever.

## The posts
Each is one content card: id, subreddit, score and comment count, title, body, top comments.

{{CARDS}}

## For EACH post, pull the 2 to 3 phrases that best capture it

- (1) the post's **core complaint or claim** — what the writer is actually angry or anxious about
- (2) **any point several different commenters land on** — independent voices converging on one
  thing is real signal, one person repeating himself is not
- Always **tight phrases of 2 to 4 words**. Never single words: "remote" is noise, "fake remote
  listings" is signal.
- Drop filler ("at the end of the day", "in this economy"). Do not write it down at all.
- A thin post may give one phrase or none. That is fine. Do not invent one.
- Do not try to measure recurrence inside one post. That is the wrong level and it is counted later.

## Return

JSON only. One entry per input post, **every post_id included**, even with an empty list.

{"posts": [{"post_id": "<the id, verbatim>", "phrases": ["<2-4 words>", "<2-4 words>"]},
           {"post_id": "<id>", "phrases": []}]}
