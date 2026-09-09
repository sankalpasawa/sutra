You are assigning Reddit posts to the tension whose pain they most embody, for {{BRAND}}'s niche.

## The tensions
Assign each post to ONE of these, by its code.

{{TENSIONS}}

## The posts

{{CARDS}}

## Rules

- Pick by the **dominant pain**, not by surface words or an incidental detail. A post about a
  marathon interview that also mentions pay belongs in the interview-rounds tension. Do not let the
  passing salary mention drag it into a pay pile.
- One **primary** tension per post. You may note one secondary code as a cross-reference; it does not
  move the post.
- There is **no off-brand or ignore bucket here.** Whether a tension suits this company is decided
  later, in writing. Every coherent pain gets its real tension.
- Use `misc` **only** for a post that shares no pain with any tension. It is not a dump for posts
  that are coherent but off-brand.

## Return

JSON only. One entry per input post, every post_id included. `tension_id` is one of the codes above
or `misc`.

{"assignments": [{"post_id": "<id>", "tension_id": "<code, e.g. T01, or misc>",
                  "secondary_id": "<a code, or empty>"}]}
