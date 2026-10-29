# Release notes: amendment A5, for the next minor version (after 2.307.0)

| Field | Value |
|---|---|
| **status** | Draft for the release, 2026-10-29. The version number and the changelog entry are the release script's (`marketplace/plugin/CHANGELOG.md` is written from the commit subjects; nothing here bumps a version surface) |
| Design | [PRD-FIVE-FUNCTIONS-A5.md](PRD-FIVE-FUNCTIONS-A5.md), its Build status table |

## What the owner sees

- Every department opens the J2 page: a default, an organic and a Root department, as a website department does. Its words say "department" and what the department does; a website department's page reads as before.
- Shadow's Home has a Graph button. The graph shows Shadow, its tasks, the goals and conversations they came from, their task chats and workers, and the departments a task uses (a solid line, tagged "uses") or made (a dashed line with a plus, tagged "spawned"), each with the reason in words. Each node opens the chat or page it names.
- The Shadow chat has a Details button: one task's screen with the decision (used, made or none, why, how sure, who decided), the departments, the chats, the workers, what it cost, and what happened when.
- For any task, an agent decides whether to use a department the organisation already has, make a new one, or use none. Code covers the answer (rules DR-1 to DR-8: a stopped department is never started, a new department under a Root's ask rule waits for the owner's yes, creates are rate limited, a duplicate becomes a use). **Link-only is the default**: the decision is recorded and drawn, the department is not messaged, and the worker runs the task as before.
- Root's own chat stays the classic chat (`J2_ROOT_DEFAULT` is false). Its J2 page is one click away. The flip waits for a real Setup conversation walked in the page (`A5_REAL_SETUP=1 qa/walks/a5-e2e.sh`).

## What changed underneath

- The interface is at **schema version 2**: 17 new closed models (`page.words`, `shadow.*`, `dept.*`; 147 definitions in all), listed by the Models editor as read-only built-ins. The migration from 1 to 2 is a no-op: `migrate()` returns a copy stamped 2 and changes nothing else. `INTERFACE_SHA[1]` is unchanged; `schemas/layers/interface.v2.json` is new.
- New routes: `GET /api/shadow/graph`, `GET /api/shadow/graph/task/{mid}`, `POST /api/shadow/tasks/{mid}/department`, `GET /api/native/_departments`, `POST /api/native/{root}/departments`; `GET /j2ui/{ref}/api/state` has a 57th key, `words`.
- Missions carry two optional keys, `department_decision` and `department_ref`; a department's `dept.json` may carry `founding.decision`. A record made before A5 is read unchanged.

## If this release is rolled back (read-shim note)

A build of 2.307.0 (schema version 1) reading a record that A5 wrote:

- A record stamped `schema_version` 2 is read as it is. `migrate()` only steps up while the record's version is below the build's, so a newer stamp passes through, and it never writes.
- The two mission keys and `founding.decision` are plain keys of JSON files that 2.307.0 does not name; they are kept in the file and ignored. Nothing in 2.307.0 validates a stored mission or `dept.json` against a closed model on read.
- A task that was decided under A5 has no department node in 2.307.0 (there is no graph); its worker, its chat and its conversation are untouched, because link-only never moved them.
- A department that A5 made (`spawned`) is an ordinary department made through `founding.spawn`: it stays, and the rollback does not remove it.
- No stored record needs rewriting in either direction, and rolling forward again reads every record as it was.

## How it was checked

`qa/walks/a5-e2e.sh` (a seeded record of its own; 43 browser and route claims), `test_a5_verify.py` (the graph read on 300 tasks: 28 ms cold; each of the 17 models against the oracle, 0 differences in 46,022 inputs; schema version 2; link-only), screenshots in `qa/shots/a5/` at 1280 and 390, `sync_j2_ui.py --check` and `--check-latest`, `test_j2ui_verbatim.py`, and the gate.

## Known, for the next release

- A candidate that the task did not use is named by its ref in the decision's "Looked at" list.
- On the phone list, the "uses" and "spawned" tags sit over the department's name.
- A Root's J2 page shows its child departments' questions in its own chat.
- `SUTRA_SHADOW_DEPT_EXECUTE` (a department running the task, `hand_words`, `follow()`) is a later package (A5-9).
