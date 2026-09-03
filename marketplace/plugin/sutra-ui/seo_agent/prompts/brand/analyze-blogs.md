Analyze how these {{BRAND}} blog articles are actually written, to inform a style guide.

Report ONLY what you OBSERVE across these blogs (not opinions). One answer per signal:
- headline_case: how titles/H2s are cased — "Title Case" or "Sentence case" (whichever dominates)
- brand_naming: how the company + its products are written (capitalization)
- industry_terms: recurring industry terms + their spelling/casing (list)
- oxford_comma: "Yes" or "No" (which dominates)
- em_dash_usage: how em dashes / hyphens are used
- quote_style: "single", "double", or "curly" (which dominates)
- ellipses: how often / how used
- number_style: how numbers are written (spell out vs numerals; %, $, measurements)
- acronyms: industry acronyms that appear, worth defining on first use (list)
- preferred_words: consistent word choices worth keeping (list)
- avoided_words: hype/filler/AI-cliché words that appear and should be cut (list)

Return ONLY JSON:
{"headline_case": "...", "brand_naming": "...", "industry_terms": ["..."], "oxford_comma": "...",
 "em_dash_usage": "...", "quote_style": "...", "ellipses": "...", "number_style": "...",
 "acronyms": ["..."], "preferred_words": ["..."], "avoided_words": ["..."]}

THE BLOGS (title, URL, full text each):
{{BLOGS}}
