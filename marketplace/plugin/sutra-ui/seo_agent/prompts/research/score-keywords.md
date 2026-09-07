You are scoring keyword candidates for a {{BRAND}} blog article. Goal: choose ONE primary keyword and a set of
DISTINCT secondary keywords (no fixed cap — follows article type: pillar 8–15, narrow 3–5), plus variations and spokes.

CONTEXT
- Article topic: {{ASSET_TOPIC}}
- Distinct angle (what THIS article specifically covers): {{DISTINCT_ANGLE}}
- What this article IS about: {{ABOUT}}
- What this article is NOT about: {{NOT_ABOUT}}
- Ambiguity warning from the seed step (wrong-world meanings to watch for): {{HYGIENE}}
- {{BRAND}} angle (what we sell): {{BRAND_ONELINER}}
- Standing rules from the user:
{{MEMORY}}
- Candidates (keyword | volume | KD | intent):
{{CANDIDATE_TABLE}}

Work in three steps.

STEP 1 — Score each candidate 0–10 on three QUALITY axes (ignore volume here):
- relevance    : how directly it matches the article topic AND its distinct angle. 10 = dead on (a sub-topic /
                 benchmark / formula the angle covers); 0 = off-topic noise (a keyword about an unrelated
                 subject that merely shares a word with the topic).
                 CHECK IT AGAINST THE "NOT ABOUT" LIST. A keyword whose searchers belong to one of those
                 other worlds scores 0, however well its words match ours.
- distinctness : is it its own sub-topic, or just the seed/primary + a filler word ("...guide", "...2024")?
                 Score it on its own merit — two genuine siblings CAN both score high; dropping actual
                 near-duplicates is the judge's job. 10 = a distinct sub-topic / sibling; 0 = a suffix-modifier.
- brand_fit    : does writing on it let us naturally use the {{BRAND}} angle? 10 = strong; 0 = none.

Also set, for each candidate:
- split_world  : true if the SAME phrase is searched by people in a DIFFERENT field (so its volume is only
                 partly reachable by us). Use the ambiguity warning above. Example shape: a phrase where one
                 word is a common abbreviation in another discipline. Otherwise false.

STEP 2 — Shortlist on quality only. Drop off-topic rows (relevance ≤2) and weak ones; keep the relevant,
distinct, good-fit candidates. Do NOT look at volume yet.

STEP 3 — Assign roles using VOLUME. From the shortlist only, now bring in volume + KD (the 3 scores break ties):
- "primary"   : exactly ONE — the strongest head term for the pillar; good volume, clears KD.
                Prefer an UNAMBIGUOUS phrase: where two candidates are close, the one with split_world=false wins.
- "variation" : a REWORD / synonym of the primary — SAME intent + SAME topic, clears KD ceiling + volume floor.
                Woven into the wording in-body; NO section of its own. (A genuinely different sub-topic is a "secondary".)
- "secondary" : EVERY distinct, section-worthy sub-topic — NO fixed cap (pillar 8–15; narrow 3–5). Each a genuinely
                different concept; the judge dedupes near-duplicates.
- "spoke"     : a strong DISTINCT head with different intent that deserves its OWN future article, not this one.
- "drop"      : off-topic, weak, or belonging to a world in the NOT ABOUT list.

RETURN a JSON array, one object per candidate, sorted by relevance desc:
{ "keyword": "...", "relevance": 0-10, "distinctness": 0-10, "brand_fit": 0-10, "split_world": true|false,
  "reason": "one line", "role": "primary" | "variation" | "secondary" | "spoke" | "drop" }
Return ONLY the JSON array.
