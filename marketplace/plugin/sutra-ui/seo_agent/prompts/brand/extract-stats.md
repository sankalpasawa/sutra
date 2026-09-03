You are reading ONE page from {{BRAND}}'s own website ({{NICHE}}). Your only job: find claims that are
NUMBERS ABOUT THE COMPANY ITSELF — its scale, its results, its credibility.

KEEP (a number about {{BRAND}}):
- scale: customers/users/tests/roles/integrations/countries/languages ("3,500+ tests", "1,500+ teams")
- results: measured outcomes it claims for customers ("55% faster time-to-hire", "6x efficiency")
- credibility: ratings, review counts, certifications ("4.7 on G2", "ISO 27001")

DROP (not a company stat):
- generic industry numbers not about {{BRAND}} ("74% of employers report mis-hires")
- prices, dates, page counts, reading times, product limits presented as configuration
- numbers about a CUSTOMER's business that are not an outcome {{BRAND}} claims credit for

Rules:
- copy the value EXACTLY as written (keep "+", "%", "x", ranges); never round, never combine
- `stat` = a short plain label of what the number measures
- `bucket` = one of: "scale" | "results" | "credibility"
- `quote` = the shortest fragment of page text carrying the number (verbatim)
- if the page has no company stats, return []

Return ONLY JSON:
[{"stat": "...", "value": "...", "bucket": "scale|results|credibility", "quote": "..."}]

PAGE URL: {{URL}}
PAGE TITLE: {{TITLE}}
PAGE TEXT:
{{BODY}}
