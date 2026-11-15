# Library: the reuse order, for Adaptation

For Sankalp and Rubak. Two functions in `j2_template_lib.py` answer "what can this piece of work start from?".
They only list candidates with reasons. Nothing is chosen, stored or changed, and Adaptation is not edited: it can
call them when it is ready.

The order is: a finished artifact first, then a template.

| Function | Returns | Read from |
|---|---|---|
| `find_artifact(need)` | Finished artifacts of the same type, best first | the saved runs (`runs/`, or `J2_RUNS_DIR`) |
| `find_template(need)` | Templates that could be filled, best first | `library/` |
| `find(need)` | `{"order": ["artifact", "template"], "artifacts": [...], "templates": [...]}` | both |

## The need

```python
need = {
    "artifact": "prd",                 # the type, as artifacts/types.json names it (required)
    "section": "Requirements",         # optional: one section of it
    "business_type": "yoga studio",    # optional: the charter's business_type
    "site": "Still Point Yoga",        # optional: the charter's site_name
    "text": "the brief, or the done-when items, as one text",
    "facts": ["..."],                  # optional: the charter's facts
    "done_when": ["..."],              # optional: used for run templates
}
```

## A candidate

```python
{"kind": "artifact", "ref": "j2-20261111-211339/prd", "run": "j2-20261111-211339", "type": "prd",
 "score": 0.62, "reasons": ["a finished Product requirements of run j2-20261111-211339",
                            "another business type (fitness studio)",
                            "9 of 37 of the need's words are in its charter",
                            "6 of 6 workflows finished", "a live run made it"],
 "section_template": "prd/requirements/iron-grove-fitness-requirements/v1"}   # only when the need names a section

{"kind": "template", "ref": "Still Point Yoga Requirements@3",
 "key": "prd/requirements/still-point-yoga-requirements/v3",
 "score": 1.0, "similarity": 1.0, "reasons": ["covers 8 of 8 facts and 3 of 3 fields", "the same need made it"]}

{"kind": "run-template", "ref": "still-point-yoga-prd-hld-and-lld", "key": "rt/still-point-yoga-prd-hld-and-lld",
 "score": 0.7, "reasons": ["stages 1.00, business 0.50, covers 0.67", "its first stage is the one asked for"]}
```

`ref` is what the library's page opens: `/library?view=artifacts&open=<ref>` for an artifact,
`/library?view=templates&open=<key>` for a section template, `/library?view=templates&rt=<ref>` for a run template.

## How each is scored

| Candidate | Score | Notes |
|---|---|---|
| Artifact | 0.5 x same business + 0.5 x words | Same business is 1 when the charters recorded the same `business_type` (compared whole) or the same name, else 0. Words is the share of the need's words found in that run's charter statement and done-when items. |
| Section template (need has a `section`) | coverage of the need's facts and fields, as `route` scores it | Ties are ordered by how near the fields are (`nearest_ranked`). The generic template is always last, with score 0. |
| Run template (need has no `section`) | `run_template_match` | 0.4 x stages + 0.3 x business + 0.3 x covers. `why_not` is among the reasons when the template cannot be picked. |

The word list and the routing numbers are in `templates/library-settings.json`.

## What is not decided here

- Whether a finished artifact is good enough to copy from. The reasons include its checks and whether a mock run made it, so the agent can judge.
- Which candidate is used. `route` still picks section templates for a builder; these functions do not call it.
- Folder outputs have no section templates. `find_template` returns the run template that holds the folder's file list (`outputs`).
