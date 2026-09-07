Pick the {{MIN}}-{{MAX}} pages of {{BRAND}}'s website ({{NICHE}}) worth learning the brand VOICE from.

The rule (from the brand-voice recipe): take the **top-traffic winners** (the proven voice), then
**deliberately add** the commercial and positioning pages even if their traffic is low or zero —
homepage, pricing, plan comparison, "why us", competitor/"alternatives"/"vs" pages, product and
integration pages. Voice matters most exactly there, and raw traffic alone misses them.

Cover the page types: every Type in the candidate table should be represented if it plausibly carries
brand voice (blog posts, product/test pages, glossaries, interview/Q&A pages, tools, templates). Skip
types that are pure data (author archives, machine pages).

Group your picks into buckets (rename buckets to fit this company):
A. positioning/commercial · B. money/product pages · C. top blogs · D. tools/calculators ·
E-F. glossaries · G. interview/Q&A · H. templates

Rules:
- pick ONLY from the candidate table below; copy URLs exactly
- for each pick: bucket letter · URL · traffic (from the table) · a short reason (a few words)
- respect the {{MIN}}-{{MAX}} total band

Return ONLY JSON:
{"picks": [{"bucket": "A", "bucket_name": "Positioning / commercial", "url": "...", "traffic": 0, "note": "..."}]}

CANDIDATE TABLE (Type · Traffic · URL · Title):
{{CANDIDATES}}
