# HANDOFF — layer 00 (foundation), 2026-09-10

Changes layer 00 needs in files it does not own. Each one is written out exactly, with the reason,
so whoever owns the file can apply it without re-deriving anything.

One job produced this list: **finding 8.11** — a failed catalogue gate now STOPS the run.

`index_site.run()` gained a keyword argument, `accept_failed_checks=False`. When a counting gate
fails (enumeration accounting, response integrity, extraction coverage) the tool now saves
`catalogue-report.json` and raises `index_site.CatalogueNotTrusted`, a `RuntimeError` subclass, so
the loop turns it into a plain message the way it does every other tool refusal. Nothing is
written to `site_index.json` / `content-database.jsonl` / `brand/company.json`, which is the whole
point: the brand pack can no longer be built on a catalogue that failed its own checks.

The refusal message ends with "run index_site again with accept_failed_checks set" — and today the
model **cannot**, because the argument is not in the tool's schema. Until the change below is
applied, the escape hatch exists in code and is unreachable from chat.

---

## 1. `seo_agent/registry.py` — expose the escape hatch (REQUIRED) — **APPLIED 2026-09-10**

The `index_site` entry, `input_schema.properties`:

```python
        "input_schema": {"type": "object", "properties": {
            "domain": {"type": "string", "description": "The site, e.g. example.com"},
            "max_pages": {"type": "integer", "description": "Cap on pages read. Default 3000."},
        }, "required": ["domain"]},
```

becomes

```python
        "input_schema": {"type": "object", "properties": {
            "domain": {"type": "string", "description": "The site, e.g. example.com"},
            "max_pages": {"type": "integer", "description": "Cap on pages read. Default 3000."},
            "accept_failed_checks": {"type": "boolean", "description":
                "Save the catalogue even though it failed its own coverage checks. Only ever "
                "after the person has read WHY it failed and said to go ahead anyway; never on "
                "your own initiative, and never as a retry for the same failure."},
        }, "required": ["domain"]},
```

Two notes for whoever applies it:

- The `max_pages` description is wrong today and unrelated to this job: the default is **0, no
  cap**, not 3000. Worth fixing in the same pass — a model that believes 3000 is the default will
  cap a big site and now get a refusal it cannot explain.
- The `description` for the tool itself could gain one sentence, so the model is not surprised by
  the refusal: *"If the catalogue fails its own coverage checks it is NOT saved and the tool says
  what failed — read that to the user and fix the cause before running it again."*

## 2. `seo_agent/prompts/system.md` — optional, one line — **APPLIED 2026-09-10**

Nothing breaks without it. If the system prompt lists how tools refuse, add index_site to that
list: a refused catalogue is not an error to route around, it is a finding to read to the user.

---

## Fixed since, in layer 00's own files — nothing to hand off

The drop-bucket bug this file used to flag (a refresh counting reconcile's dropped addresses as
NEW, and re-adding alias addresses as duplicate rows) is fixed in `seo_agent/tools/refresh_site.py`,
along with two things found while fixing it: a source that FAILED could make live pages read as
gone, and a refresh was overwriting the full read's stage files in `_work/` (it now writes to
`_work/refresh/`). All four are pinned by tests in `seo_agent/tests/test_foundation.py`.
