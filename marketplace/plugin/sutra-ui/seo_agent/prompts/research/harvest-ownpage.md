You are given the numbered sections of ONE of our web pages — each section is a heading and its full text.

Decide which sections are REAL article content, and skip boilerplate: navigation, breadcrumbs, related posts,
author boxes, newsletter/subscribe blocks, generic CTAs, cookie notices, and footers.

For each REAL content section, return its index and a one-line **gloss** describing what it covers — written
after reading the whole section (our headings aren't always self-explanatory, so read the text, don't just
restate the heading).

Return ONLY the real content sections. Do not rewrite or shorten anything else — the section's full text is
kept as-is by the caller; you only judge keep/skip and write the gloss.

Output STRICT JSON, nothing else — an array:
[ { "index": 0, "gloss": "..." } ]

--- SECTIONS (index · heading · text) ---
{{SECTIONS}}
