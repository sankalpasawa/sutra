# Handoff — research (03) and write (04) layers

Written by the agent that built 8.18, 8.19, 8.20, 8.2, 8.7 and 8.8. Everything below is either a
change made outside the files that agent owned, or a fault it found and did not fix.

## Changes made in files outside the owned list

### `seo_agent/tests/_fixture.py` — the stubbed dossier had to get longer

The dossier health gate (8.19) refuses a dossier under 1,500 words. The fixture's
`write-dossier-section` stub returned three sentences, so every suite that drives a real run was
refused: test_tools, test_endtoend, test_wordcount, test_research, test_credit_guard, test_stations.
The fixture was the thing at fault — a real section runs to hundreds of words — so the fixture was
fixed rather than the floor lowered.

The change is two things and nothing else:

* a module constant `_DOSSIER_BULK`, a block of filler prose, repeated 25 times;
* `+ _DOSSIER_BULK` appended to the stub's return value.

The three cited sentences that were already there are untouched and still come first. **Every filler
sentence is under thirty characters**, which is the bar the fixture's own `harvest-dossier` stub uses
(`len(x.strip()) > 30`), so no filler sentence can become a card. Cards, card counts, card ids and
every assertion that reads them are byte-for-byte what they were; only the dossier's word count moved
(about 96 words to about 3,400). If that constant is ever edited, keep every sentence under thirty
characters or the card counts in six suites will move.

## Faults found and NOT fixed (they live in files the agent did not own)

### `seo_agent/checks/draft_checks.py::check_internal_links` reads `site_urls()` wrongly

`checks/__init__.py::site_urls(ctx)` returns a **tuple**, `(set_of_urls, domain)`.
`draft_checks.check_internal_links` (line ~119) does:

```python
known = site_urls(ctx)
...
if norm_url(url, domain) not in known:
```

`known` is the tuple, not the set, so `not in known` is true for every URL and the check reports
every internal link as pointing at a page that does not exist. `if not known:` is also always false
(a two-item tuple is truthy), so the "no site index on file" warn path is unreachable.

The exact fix:

```python
    known, _domain = site_urls(ctx)
```

placed where `known = site_urls(ctx)` is now. `domain` is already read from `site_index(ctx)` on the
line above, so nothing else changes. It was left alone because it is unrelated to the six findings
this agent was given, and the change flips a check from always-failing to actually-checking, which
deserves its own review.
