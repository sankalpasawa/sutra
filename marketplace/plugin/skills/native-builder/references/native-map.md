# Where everything in Native lives

**status**: v1, 2026-09-23 · **owner**: Native Builder · **read when**: you know what you are building and need to know which file, store or page owns it.

Short names below are relative to the repo root unless stated. Nothing here is a guess: each row was read on 2026-09-23.

## The four homes

| Home | What it holds | How it is written | How it is read |
|---|---|---|---|
| **The registry** | departments, their rules records, filed work | the placement engine's own verbs, nothing else | the engine's readers; the app's read-only API |
| **The app store** | engines (routines) and their runs, tasks, proposals | the app's own writers, behind asks | the app's readers and the run ledger |
| **The site** | the model: what is designed, decided and proposed | authored pages plus the manifest and sidebar | a reader, and the two guards |
| **The plans** | programs, requirements, decisions, journeys | plain files in a program folder | whoever picks the program up next |

## The paths that matter

| # | Path | What it is |
|---|---|---|
| 1 | `sutra/marketplace/plugin/lib/placement_engine.py` | the record engine: mint, charter, place, retire, unretire, disposition |
| 2 | `sutra/marketplace/plugin/sutra-ui/proposals.py` | an ask: recorded, applies nothing on its own |
| 3 | `sutra/marketplace/plugin/sutra-ui/org2_api.py`, `org2_apply.py` | the org asks, their checks and the one applier |
| 4 | `sutra/marketplace/plugin/sutra-ui/org_api.py` | the decide route; its apply dispatch must know every kind |
| 5 | `sutra/marketplace/plugin/sutra-ui/routines.py` | engines: the record, the calendar job, the run rows |
| 6 | `sutra/marketplace/plugin/sutra-ui/dept_api.py` | every read the department screen makes |
| 7 | `sutra/marketplace/plugin/sutra-ui/static/js/20-dept.js` | the department screen itself |
| 8 | `sutra/marketplace/plugin/sutra-ui/function-templates/` | the fifteen function templates and their law |
| 9 | `holding/website/native/platform/model/` | the model pages: the vocabulary, the life cycle, the walks |
| 10 | `holding/website/native/manifest.json`, `_sidebar.html`, `_sidebar.py`, `_manifest-check.py` | how a page registers, and the two guards |
| 11 | `holding/plans/department-lifecycle/` | the life cycle: requirements, the runnable journey, its runner |
| 12 | `holding/plans/department-screen/` | the screen program: requirements, decisions, the run of a real department |

## The rules that are already enforced

| Rule | Where it bites |
|---|---|
| A proposal applies nothing until it is stamped | the decide route takes an explicit yes; there is no automatic path |
| The desktop back end may never mint or retire a department | a test proves the negative by scanning for the calls |
| A retire is refused while anything under it lacks a successor | the disposition report, before the verb runs |
| The root domain can never be retired | the retire verb itself |
| A derived function template may add or tighten, never drop | the template suite, 59 checks |
| Every new file brings its domain, charter, placement and kind | the creation guard, at write time and at stop |

## The three checks to run before shipping anything

```
cd holding/website/native && python3 _sidebar.py --check && python3 _manifest-check.py
python3 holding/plans/department-lifecycle/run-journey.py        # the model still walks
<the suite for whatever you touched>                             # named, not "the tests"
```

---
provenance: {author: claude, date: 2026-09-23, session: 8e2713c3, inputs: [the code and pages read while building the life cycle work of 2026-09-23], review: none by a second model, confidence: high; every path was opened on the day}
