# HANDOFF — the front end to the engine, 2026-09-09

Changes the SEO Writer screen needed in `seo_agent/`, which it does not own.

**Both items were applied by the engine team the same day, and both stand-ins have been deleted.**
This file is kept as the record of what was asked for, what landed, and what is now guarded — not
as an open list. Section 3 is the "do not go looking" note and is still current.

---

## STATUS

| # | Ask | Landed | Stand-in |
|---|-----|--------|----------|
| 1 | `registry.LABELS` for the three unnamed tools | yes, exact strings | `AG_TOOL_NAMES` / hand-rolled `agToolName` — **deleted** |
| 2 | `filled` on `pack.inputs()` rows | yes, via `features.untouched()` | none was possible — the screen now branches on it |

Guarded both sides so neither can come back: `test_endtoend.py` (engine) requires a `LABELS` row
for every work tool; `test_agents_api.py::test_22` asserts no tool reaches the screen under its own
function name; `test_agents.js` → "no tool is listed under its function name" reads the REAL
registry rather than fixtures; `test_agents_api.py::test_24b` asserts `words` and `filled` move
independently.

---

## 1. `seo_agent/registry.py` — three tools have no plain name (owner finding 1.6)

APPLIED. `LABELS` covered eight of the eleven work tools (twelve now, with `find_prompt`). For the other three, `label()` falls back to the
function name with its underscores taken out, so the Tools tab drew

    3. Refresh site
    4. Import traffic
    7. Build assets

between "Learning the brand" and "Writing the article" — three rows out of eleven reading as code.

**Line 364, `LABELS`** — add three rows:

```python
LABELS = {
    "index_site": "Reading the website",
    "build_page_index": "Indexing the pages by meaning",
    "refresh_site": "Catching up on what changed",          # ADD
    "import_traffic": "Loading a traffic file you already have",  # ADD
    "onboard": "Asking the setup questions",
    "learn_brand": "Learning the brand",
    "build_assets": "Working out what is worth writing",    # ADD
    "suggest_topics": "Finding topic ideas",
    ...
}
```

These are the exact strings the screen is showing today, so applying this changes nothing visible
and moves the value to where it belongs. `LABELS` is also the run log's fallback line, so the log
gets the same improvement.

**Stand-in deleted.** `static/js/17-agents.js` carried `AG_TOOL_NAMES` plus a `agToolName()` that
reproduced the engine's fallback to detect it. Both are gone; `agToolName()` is now one line that
returns the engine's label, with a de-underscored name as a last resort so a tool added upstream
before its label is written still draws a row.

**One knock-on, found applying this.** `find_prompt` was appended as the twelfth tool, and the
Tools lead used to end "the last four run for every article". That was true only by an accident of
ordering, and false the day `find_prompt` landed — it is a support tool, not a per-article step. A
positional claim about a list another team owns cannot be kept true, so it is gone. The sentence
now carries exactly one number, the derived total, and says "the writing steps run again for every
article" instead. `test_agents.js` → "the tools lead makes no claim about which rows are the
per-article ones" holds that.

---

## 2. `seo_agent/brand/pack.py` — `inputs()` cannot say whether anybody has written in the file

APPLIED, exactly as specified. Proved on real data: the blank form reads `words 205, filled False`,
and one typed line makes it `words 211, filled True`.

`pricing.md` is the first knowledge file a person is expected to TYPE INTO rather than review, and
the known failure mode is the old seed file: it shipped blank, looked like something that had not
been built yet, and stayed blank for months.

The screen now draws it as an ask. What it cannot draw is the difference between **the blank form**
and **a filled-in file**, because `_row()` returns only `words` — and the blank form is real text on
disk (`cm.template("pricing")`), so its word count is not zero. The engine already knows the answer:
`features.untouched(text)`.

**`inputs()`, line 103** — carry the flag:

```python
def inputs():
    """The typed-in files, for the screen. `filled` is the difference between the blank form and
    a file somebody has actually written in; `words` alone cannot tell them apart, because the
    blank form is real text on disk."""
    from . import features
    rows = []
    for n in INPUTS:
        r = _row(n)
        r["filled"] = bool(r["exists"]) and not features.untouched(_text(n))
        rows.append(r)
    return rows
```

With that, the screen settles a written file back into an ordinary row and keeps the invitation
for the one still waiting. `agInputsHtml` now branches on `filled` and never on `words`; a row
whose payload lacks the field keeps asking rather than assuming, because asking twice costs far
less than never asking.

---

## 3. Not needed — recorded so nobody goes looking

- **`/knowledge/refresh` and `/knowledge/traffic` are both healthy.** Both were reported as doing
  nothing. Both were verified end to end against the owner's own catalogue on 2026-09-09:
  `refresh_site.run(preview=True)` returned `3 new, 0 gone, 0 changed, 11656 unchecked` with its
  markdown report, and `traffic_import.apply` imported and matched from both a path and pasted
  text. The failure was entirely in the browser — `agAction` had no arm for either button, so the
  click reached `default: break`. No engine change is owed.
- **The traffic IMPORTER stays.** Only its button is gone (owner, 2026-09-09). `POST
  /knowledge/traffic` and the `import_traffic` tool are untouched, so the agent can still offer it
  in the chat when an account runs dry, which is the only moment it makes sense.
- **`voices.md` needed no UI special case.** The Knowledge tab renders `built_from` and `extras`
  generically from `pack.py`, so the "Who writes" section left with the file. The one hand edit was
  the brand-pack panel's hardcoded file list (`AG_BRAND_FILES`), which would otherwise have kept a
  row saying "not built yet" for ever.
