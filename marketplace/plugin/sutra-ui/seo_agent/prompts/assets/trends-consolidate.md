You are grouping Reddit phrases into **tensions** for {{BRAND}}'s niche.

A **tension is ONE sentence stating a specific shared pain**: who is frustrated with what. Never a
topic label.

- Theme, too vague: "fake remote jobs"
- Tension, usable: "Candidates apply for roles advertised as remote that turn out to be onsite."

## The rule: group by SHARED PAIN, never by shared topic

Two phrases belong together only if *one honest conflict sentence* describes the pain behind both,
the same who-is-frustrated-with-what. If describing them truthfully needs two different sentences,
they are two tensions.

- Yes: "fake remote listings" + "secretly onsite" + "remote then RTO" are one tension. Different
  words, one conflict: a remote promise against an onsite reality.
- No: "ghosted after interview" (the pain is silence) and "endless interview rounds" (the pain is
  process length) are TWO tensions, even though both are about interviews. Merging them under the
  topic "interviews" blurs what an asset would have to say.

Do not lean on a stretch-word (broken, doesn't work, unfair, outdated, is a mess, struggles with)
to hold one sentence over unrelated phrases. That is a topic. Split it.

## The phrases, each with the post ids it came from

{{PHRASES}}

## Return

JSON only. Every tension sentence must name a real conflict, never a category verdict like
"interviews are broken". A phrase that fits no clear shared pain goes in `orphans`. Do not force it.

{"tensions": [{"tension": "<one specific shared-pain sentence>",
               "phrases": [{"phrase": "<phrase, copied verbatim>", "post_ids": ["<id>"]}]}],
 "orphans": [{"phrase": "<phrase>", "post_ids": ["<id>"]}]}
