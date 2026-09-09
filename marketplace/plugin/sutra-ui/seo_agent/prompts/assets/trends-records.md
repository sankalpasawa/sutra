You are writing the judgment fields for each tension in {{BRAND}}'s niche. The counts (posts,
upvotes, comments, which subreddits) are worked out mechanically elsewhere. You only write what has
to be read.

## The tensions, each with its phrases and a sample of the posts under it

{{TENSIONS}}

## For EACH tension, produce these fields

- **core_pain** — what is actually hurting people, one line. Read the phrases and name the hurt
  *under* them. The tension is the conflict; the core pain is why it stings.
- **audience** — who is speaking: one of {{AUDIENCES}}. **Do not default to "both".** Pick "both"
  only when both sides genuinely argue inside this pile. People in the trade venting about the
  people they serve is not "both".
- **emotion** — exactly one of: {{EMOTIONS}}. No free text. Map anything else to the nearest of
  those (frustration to anger, despair to anxiety, contempt to ridicule).
- **best_example** — the single post_id from this tension's own list that most clearly embodies it.
- **representative_quotes** — 2 or 3 vivid **verbatim** quotes from the posts or comments, in the
  real language people used. Copy them, do not paraphrase.
- **sub_questions** — the distinct questions people **actually argue about** in these posts, in
  their own neutral words. These are evidence, not proposals.
  **Never use any of these words or phrases here:** {{BANNED}}. A question that names a product,
  a tool, or a fix is a later step leaking backwards into the evidence.
- **implied_data_point** — the measurable number this tension is begging for, for example "the share
  of listings advertised as remote that turn out to be onsite".

## Return

JSON only. One entry per tension, using the code exactly as shown.

{"records": [{"tension_id": "<code, e.g. T01>", "core_pain": "...",
              "audience": "<one of the closed set>", "emotion": "<one of the closed set>",
              "best_example": "<post_id>", "representative_quotes": ["...", "..."],
              "sub_questions": ["...", "..."], "implied_data_point": "..."}]}
