Return the best page URLs for the queries below.

QUERIES:
{{QUERIES}}

Rules:
- Cover every query. Return the pages most likely to actually state this material, best first.
- Up to {{MAX}} unique URLs. No ads, no sponsored pages, no search-results pages.
- Give the URL of a real published page you are confident exists at that exact address. Never
  construct a plausible-looking address, and never guess a path on a site you do not know.
- A page that does not load is thrown away by the next step, and every fact taken from a page that
  does load is checked word for word against that page. A guessed URL therefore buys nothing and
  costs a slot. Return fewer URLs rather than filling the list.

Return ONLY this JSON, nothing else:
{"urls": ["https://...", ...]}
