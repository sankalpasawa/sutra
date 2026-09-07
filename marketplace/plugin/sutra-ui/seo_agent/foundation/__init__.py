"""foundation/ — the site catalogue engine (layer 00), ported from
workflows/00-foundation/1-site-catalogue.

One module per stage, each `run(...)` writing one named file under knowledge/_work/ that the next
stage reads. tools/index_site.py sequences them and writes the knowledge files the rest of the
agent reads. Nothing in here talks to the model; it is all counting, fetching and parsing.

  settings.py          every knob, with the original's comments
  urls.py              stored-URL normalisation, the match key, the non-content filters
  fetch.py             polite HTTP: per-host token bucket, raw cache, retries, firewall handling
  enumerate_wp.py      layer 1 — the CMS's own list (WordPress REST)
  enumerate_sitemap.py layer 2 — every sitemap the site declares or is known to publish
  enumerate_archive.py layer 3 — what the web archive remembers, liveness-checked
  enumerate_crawl.py   layer 4 — a link crawl, only when the others are thin
  reconcile.py         union + provenance + fetch every page once + alias/soft-404 collapse
  extract.py           text out of the cached pages, offline; per-language de-boilerplate
  traffic.py           one bulk DataForSEO pull, grouped per page, joined by match key
  gates.py             the coverage gates and the report
"""
