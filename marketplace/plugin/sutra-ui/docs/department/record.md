# The record

| Field | Value |
|---|---|
| **status** | v1, 2026-09-29, RECORD of the code (Sutra Desktop v2.306.19-desktop) |
| Code | `website_dept.py` (`home`, `ddir`, `create`, `dept`, `save_dept`, `versions`, `latest`, `read_files`, `add_version`, `runs`, `_put_run`, `asks`, `requests`, `status`, `health`, `engine_view`, `trace`, `map_view`), `engine_runtime.py` (`board`, `threads`, `step_rows`, `steps_view`, `ideas`, `coordination`, `_verdicts`, `ladder`), `artifacts.py` (`get`, `check`, `faults`, `view`), `artifact-templates/*.json` |

## Where a record lives

`home()` is the records home: `~/.sutra-ui/native` for the stable app, `~/.sutra-ui-beta/native` for the Beta, `SUTRA_NATIVE_DEPT_HOME` when set (a test binds a temp folder; the default home is refused under a test runner). One directory per department, `ddir(ref)`:

| File | Holds |
|---|---|
| `dept.json` | the record: name, kind, goal, rules, owner, control, `engines`, `artifacts`, `envelopes`, `windows`, `host`, `stopped`, `root`, `runtime` (2 for the engine runtime), `publish_asks_from`, `looked_up` |
| `board.jsonl` | every post: n, src, dst, msg_type, thread, at, payload, about |
| `runs.json` | run rows (line.md) |
| `steps.jsonl` | step rows, gate rows, mark rows (`_append`) |
| `asks.json`, `requests.json`, `ideas.json` | the asks, the owner's requests, the parked ideas |
| `coordination.json`, `verdicts.json`, `ladder.json`, `exchanges.json` | Coordination's table, the gate verdicts, the ladder numbers per step, the exchanges |
| `artifacts/<slug>/v<n>/` | each version's files; `live/` the served site |
| `_library/` (beside the departments, under the home) | the engine templates born in this app's records (engines-and-library.md) |

## Artifacts and versions

Every artifact on the record has a template (`artifact-templates/<slug>.json`: kind, files, checks, `written_by`, `operations`); an artifact the department names that the Library lacks takes the Default template (`artifact/default`, kind text). `add_version` writes the files, `made_from` (the input version or the ask that caused it), the run id and the check; `artifacts.check(name, files, default)` runs the template's checks; `latest`, `versions`, `read_files` read them; `trace(ref, art, v)` walks `made_from` back to the owner's words.

| Template | Kind | Files | Checks | Written by | Operations |
|---|---|---|---|---|---|
| brief | text | brief.md | is_text | the owner, Identity | Plan, Do |
| site-plan | plan | site-plan.json | plan_has_pages | Plan | Write |
| pages | pages | *.html | pages_have_html | Write | Check |
| build | build | index.html, *.html | has_index_html | Check | Publish |
| live-site | site | index.html, *.html | has_index_html | Publish | Adaptation, Audit |
| request | text | request.md | is_text | Identity | Setup |
| department | record | department.md | names_a_ref | Setup | - |
| result | text | result.md | is_text | Do | - |
| default | text | * | is_text | - | - |
| human-sutra | app | - | - | - | - |

## What the map shows (`map_view`)

Name, goal, done words, rules, owner, control, stopped; the five systems with their last run; each engine's card (`engine_view`: reads, writes, runs as, state Running / Waits / Stopped / Idle / Missing, the envelope and what was spent today, the window, the last run); each artifact with its version count and latest; the status (`status`: pending asks, escalated asks, what waits and why, what runs, the next thing due or why nothing is); health; the last ten runs; the requests; whether the site is live.

## Health (`health`)

| Check | Blocks or warns when |
|---|---|
| Motor | the last tick is older than 15 s (warn) or 90 s (block) |
| Slots | a slot ran twice |
| Versions | a version has no run or no check |
| Stuck | an ask is waiting (warn), or older than `STALE_ASK_S` (30 min) |
| Front door | the owner's words wait or were lost at a bound |
| Awake | all five functions run as engines (runtime 2) |
| Budget | an engine is over its envelope |
| Library | an engine on the record has no template in this app's Library ("say its idea again to shape it anew") |
| Done | the kind's done words: the last artifact's latest version passed its check |

`never` lists the invariants the record keeps: a run with no slot, a version with no run, a slot run twice, an uncounted retry, a hidden exchange, a silent skip.

provenance: {author: claude, session: 17842ce0, date: 2026-09-29, inputs: [website_dept.py: home, ddir, create, add_version, status, health, engine_view, trace, map_view; artifact-templates/*.json; artifacts.py], review: none by a second model, confidence: high}
