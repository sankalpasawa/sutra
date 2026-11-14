# The shared Sutra library: design, ownership and next engineering steps

_Status: Proposed · Date: 2026-11-13 · Branch: `lane/s6-library-docs` · Version context: Sutra Pro 0.4.0, J2 pin `cut-off/2026-11-12`, moving to J2 main `1adb8ecd` in sync 6 · Decisions: D194 to D200 · Companions: `docs/design/j2-sync-6.md` (D176 to D193), `docs/design/library.md` (the Interface library), `docs/design/memory-evaluation.md`, `docs/design/external-software-plan.md`_

The owner's task: lead the shared Sutra library design with the shared-library maintainer, who is already working on parts of the library; coordinate with them; define the next engineering steps and ownership. Team members appear below as roles only (the owner, the shared-library maintainer, the J2 library maintainers, the app team). One assumption could not be read from the repository and is made explicit: which parts the shared-library maintainer is already working on. Step 0 of section 9 asks them to list those parts; the split in section 6 is written so that a part they already hold moves to the "J2 library maintainers" column without changing anything else.

Paths are relative to `sutra-pro/` unless they start with `prototypes/`. Sizes: S about a day, M about a week, L two to three weeks (the scale of the external software plan; estimates, not commitments).

## 1. Summary

- **What it is.** "The shared library" is J2's library: the files under `prototypes/j2/library` and its seed, the section templates, the run templates, the two shelves (Artifacts, Artifact templates) and the content door, together with the data that drives them (`artifacts/types.json`, `templates/<type>/generic.json`, `templates/library-settings.json`). It is shared because the J2 prototype and Sutra Pro run the same files and the same rules. It is data first: the app reads it, and changes it only through the engine J2 wrote.
- **What Sutra Pro adds around it** (and keeps out of it): team scoping, scrubbing, the working folder, the atom log, the usage ledger, a library lock, closed models behind one write gate, the seed sync, and the finish steps. Two new stores are proposed beside it, not inside it: a memory provider and an external software catalogue.
- **The line.** J2's library folder stays J2's: nothing of the app's records is written into it, so a sync can merge it without touching the app. The app's stores live in the data folder next to it and are reached through the Interface library's gate.
- **The contract.** A short, testable agreement (section 7): which files and keys the app reads, which settings it exposes, what J2 promises about the seed, what the app never does. It is a document plus a machine-readable file plus a test, so a sync fails loudly when either side moves.
- **Ownership by role** (section 6): the J2 library maintainers own the data and the J2 code; the app team owns vendoring, settings, scope, records, seed sync, UI and the two new stores; the shared-library maintainer owns the contract text and the design of sharing beyond a team; the owner approves what becomes shared.
- **Next steps** (section 9): ship sync 6 with the reuse flags off; write the contract file and test; ask J2 for a pin tag and three small seams; spike the memory provider; build the external catalogue's record and reference-only list; add "save this run as a run template"; then design the publish gate that shares finished work across teams; then decide with real-model data whether any reuse flag becomes a default.
- **Nothing is shared across teams by default.** Templates are one store (D26); finished artifacts are per team (D184); sharing a finished artifact or a run template with another team is a later, owner-triggered step with scrubbing (D197).

## 2. Four things called "library"

| Name | What it is | Lives in | Owner (role) | Status |
|---|---|---|---|---|
| Interface library | closed pydantic models, the registry, `GATE.check`, the record catalogue, the schema export (`docs/design/library.md`) | `sutra_app/library/`, `docs/schemas/` | app team | built |
| J2 library (the shared library of this document) | section templates in versions, run templates, the shelves, the content door, the settings file; the seed | `library/` of J2 (`sutra_app/engine/seed/library/` in the app, `<data>/library` at run time), `templates/`, `artifacts/types.json` | J2 library maintainers (data, code), app team (the copy and the patches) | built (flags off) |
| Memory provider | facts and experience: lessons, playbooks, notes, as gated, scoped, expiring records recalled under a budget (`memory-evaluation.md`) | a table in the app's SQLite, a registered family | app team | proposal |
| External software catalogue | a closed, owner-approved list of outside software (MCP connectors, libraries, CLI tools, skills) and the rules for using each (`external-software-plan.md`) | a table in the app's SQLite, a registered family | app team | proposal |

The first two are the "Interface" and the "Template" library of the memory evaluation; the evaluation's rule stands: memory and the catalogue do not live in the template library, and the template library does not hold facts.

```mermaid
flowchart LR
  subgraph J2["J2 (maintainers)"]
    JL["library/ seed + templates/ + types.json + library-settings.json"]
    JC["j2_template_lib.py, j2_artifact_lib.py (vendored, patches P10 etc.)"]
  end
  subgraph APP["Sutra Pro (app team)"]
    SEED["seed sync (doctor): add, never overwrite (D144, D185)"]
    LIBF["data/library: ONE global store, file lock (D26, D181)"]
    RUNS["data/departments/ID/runs: finished runs, PER TEAM (D184)"]
    GATE["Interface library: closed models + GATE.check"]
    DB[("db.sqlite3: atoms, usage ledger, memory_item, external_software")]
  end
  JL -->|tagged pin, vendor_j2.py| SEED --> LIBF
  JC -->|vendored copy| RUNS
  RUNS -->|finish step: collect (D142)| LIBF
  LIBF -->|router, run templates, auto-reuse| RUNS
  RUNS -->|Artifacts shelf, content door| RUNS
  GATE --> DB
  DB -.->|recall block, addendum| RUNS
  DB -.->|enabled entries per node| RUNS
```

## 3. J2's library at `1adb8ecd` (what is shared)

| Part | What it does | Where | Switch |
|---|---|---|---|
| Section templates | a template per artifact and section, in immutable versions `v<N>` (`meta.json`, `model.py`, `schema.json`, `spec.json`); the router reuses, extends or creates one for each need; the generator decides, code checks | `library/<artifact>/<section>/<slug>/vN/`, `index.json` `templates` | `J2_TEMPLATE_LIBRARY` (setting `template_library`) |
| Library cleanup | types, stop words, the business-type blacklist, slot fields, `fact_fields`, routing numbers are read from data, not code | `templates/library-settings.json` | none (always) |
| Run templates | a named bundle of all workflows of one finished run; a new run starts from a name, whole or with selected workflows | `library/run-templates/<id>/{template.json,schema.json}`, `index.json` `run_templates` | `J2_RUN_TEMPLATES` |
| Auto-reuse | after the first charter, the best run template at or above `AUTO_MIN` 0.6 is taken as if chosen; the router adapts the nearest section template before it creates one; an adapted template is a new family named for the run's business; `move_versions` moves versions between families | `j2_template_lib.py`, `j2.py` | `J2_AUTO_REUSE` (implies the two above) |
| Shelves | Shelf 1, Artifacts: whole finished artifacts read from the runs folder; Shelf 2, Artifact templates: run templates, then each type's sections as structure with slots (no business value); `find_artifact`, `find_template` give the reuse order (`library-reuse-order.md`): a finished artifact first, then a template | `shelf_artifacts`, `shelf_templates`, `catalog_view` | none (read-only views) |
| Content door | before a document section's builder runs, serve the section of the source run with no model call, check it, refund the cost | `j2_artifact_lib.py`, `reuse.json` | `J2_ARTIFACT_LIBRARY` (implies auto-reuse) |
| Runs on Git | the finished run folder is committed and pushed | `J2Run._push_run` | `J2_PUSH_RUNS` (fixed off in the app) |

Measured at the new pin: 81 families, 107 versions (67 with `renamed_from` or `adapted_from`), 11 runs, 4 run templates (2 made by live runs, 2 by mock runs), 437 seed files, 2.2 MB (157 files and 0.8 MB at the old pin). Flag-off behaviour is byte-neutral: the seven prompt goldens differ in `j2_commit` only.

## 4. What Sutra Pro adds (and why none of it goes into J2's files)

| Addition | What it is | Where | Decision |
|---|---|---|---|
| Team scoping | the template library is one global store; finished runs, hence the Artifacts shelf and the content door, are per team | `views._library`, `DataPaths` | D26, D141, D184 |
| Scrubbing | the egress scan of every prompt (`SHAPES`, the Redactor, `.env` values), the shelf's slots instead of business values, no secret field anywhere in settings | the Router (`sutra_app/connectors`), `library/templates.py` | D109, D149, D157 |
| Working folder | the owner's folder, read by agents through file tools and watched by git; a type (`project`) that works in it | `capabilities/workspace.py`, `project.py`, `host/folder_watch.py` | D127, D164 |
| Atom log | each function-node turn is an atom with checks; the node layer closes it from the turn events | `fnodes/`, `library/atom.py` | D60, `docs/design/function-nodes.md` |
| Usage ledger | one row per model call, with provider, tokens and cost, charged to a function and step | the router, `engine/llm.py` tags (P7) | D37, D159 |
| Library lock | one `flock` on `<library>/.lock` around every read-modify-write of the index (P10, extended in sync 6) | `j2_template_lib.py` patches | D26, D181 |
| Seed sync | a new install gets the whole seed; an existing one gets what is new, never an overwrite | `ops/doctor.py` | D144, D185 |
| Finish steps | a run that ended well is collected into the catalog and its agent views are built, under the lock | `host/finish.py` | D142, D143 |
| Closed models and strict mode | every J2 file and every record is a closed model behind `GATE.check`; unknown files and keys are refused in strict mode | `library/records.py`, `templates.py` | D47, D172, D186 |
| Settings | the flags are Engine settings with implied flags computed once; the push flag and the author are fixed | `engine/spec.py`, `paths.py` | D177, D178 |
| Backup | the library folder and the runs are in the backup tarballs | `ops/backup.py` | D26 |

None of these needs to be in J2's folder, and none is: J2's `library/` holds J2's data and nothing else, so the seed sync, a re-vendor and a J2 maintainer's own checkout can all merge it by rules.

## 5. How memory and the external catalogue connect

The three proposals share a vocabulary and a write path, and stay separate in storage.

| | Template library (J2) | Artifact shelf / content door (J2) | Memory provider (proposal) | External software catalogue (proposal) |
|---|---|---|---|---|
| Holds | structure of sections, run plans | finished documents of one team's runs | facts and experience (lessons, playbooks, notes) | references to outside software |
| Written by | the engine (generator proposes, code checks), the finish step | the run | an agent proposes, code validates, the owner edits | an agent or a sync proposes, code checks, the owner approves |
| Scope | global (D26) | team (D184) | chart node, department, function, `org_wide` | chart NodeIds (`enabled_for`) |
| Read by | the router, the page | the shelf, the content door | the prompt, through a recall block (budgeted) | a run, only entries enabled for its node |
| Store | `<data>/library` | `<data>/departments/<id>/runs` | table `memory_item` (+ FTS5) in `db.sqlite3` | table `external_software` in `db.sqlite3` |
| Gate | J2's own checks plus `gate_record` on every file | `gate_record` | `GATE.check` on a closed `memory_item/1` | `GATE.check` on a closed `external_software/1` |

Rules that make them one design:

1. **One write path.** Models propose; code validates through `GATE.check`, scrubs, and writes. No model has a write or a query path of its own (memory Decision D, catalogue 3.1). J2's generator and router follow the same rule inside the engine ("generator decides, code checks").
2. **One scope vocabulary.** Memory scopes and catalogue enablement key on the chart's NodeIds, so a merge, move or archive carries them through `carry_links` and the alias map. Run scoping is by team (a department is a node). The template library stays global because it holds structure.
3. **One retrieval order for a run's need**, extending J2's `library-reuse-order.md`: a finished artifact of the team first (the content door, flag), then a run template (flag), then a section template (the router), and, beside that order and not in it, the memory recall block and the enabled external entries, which add facts and tools to the prompt rather than content to the artifact. Memory never serves a section; the content door never recalls a fact.
4. **Seams that already exist.** Lessons and playbooks already take explicit paths (P5, `J2_MEMORY_FILE`, `J2_PLAYBOOK_FILE`); the recall block reaches a prompt through the capability addendum and the node-context file (P9), not through a J2 edit; the catalogue's enabled entries reach a run through the engine host, not through J2.
5. **Separate storage on purpose.** The library folder is J2's data; memory and the catalogue are app records (tables, closed families, sha256, drift test). A sync of the library cannot lose a memory item, and a memory migration cannot corrupt a template.
6. **The `template` kind of external software** (catalogue open question 7) stays a plain catalogue row in v1: no routing, no matching. A template from outside the repository enters the library only through the seed path (a maintainer reviews it, the contract test accepts it). Reuse of the router for external templates is a later question for the J2 library maintainers (D199).
7. **Provenance everywhere.** Every record in all three says who wrote it (owner, agent function, system), when, from which run, and whether it is a mock (mock entries never reach a live run: the library already flags mock templates, `mock: true`, and the router's `live` rule excludes them from a live run).

## 6. Ownership by role

| Area | J2 library maintainers | App team | Shared-library maintainer | Owner |
|---|---|---|---|---|
| J2 library data: families, versions, run templates, seed content quality (live over mock) | **owns** | reads, syncs | reviews shape | approves what ships as seed |
| `library-settings.json`, `types.json`, `templates/<type>/generic.json` | **owns** | vendors byte-identical | reviews | |
| J2 code: `j2_template_lib.py`, `j2_artifact_lib.py`, `j2.py` | **owns** | vendors with numbered patches only | | |
| Flags and their defaults in J2 | **owns** | exposes as settings, off by default | | decides defaults for the app |
| Pin tags, "needs owner review" commits | **owns** | asks, carries inert | | |
| Hard-coded behaviour inside J2 (the 547-row inventory) | **owns** | reports, never patches (D189) | | |
| `vendor_j2.py`, `VENDORED.md`, patches P1 to P19 | informed | **owns** | | |
| Settings, wire, views, page, fixtures, goldens | informed | **owns** | | |
| Scope (team), lock, seed sync, records, closed models, schemas | reviews contract impact | **owns** | reviews shape | |
| Memory provider (`memory_item`, store, import, recall) | consulted (P5 seam) | **owns** | reviews family and scope vocabulary | approves defaults (expiry, budget) |
| External software catalogue | consulted (`template` kind) | **owns** | reviews family and the shared vocabulary of capabilities and permissions | approves what enters and what a team enables |
| The contract (section 7): text, contract file, contract test | reviews | writes the file and the test | **owns the text and the decisions** | |
| Sharing beyond a team (publish gate, scrub rules, provenance) | consulted | builds | **owns the design** | **approves each publication** |
| Quality of reuse (is auto-reuse good enough to be a default) | provides the metrics hooks | runs the evaluation | co-signs | **decides** |

Working rules between the columns: the J2 side never edits the app's files and the app never edits J2's text except through a patch recorded in `VENDORED.md`; a change to the contract needs a line in the contract document, the contract file and the contract test in the same change; the app team announces a sync (pin, patch table, contract report) and the J2 maintainers answer within the sync; a part the shared-library maintainer already works on is assigned to the J2 column on Step 0 and listed in the contract document.

## 7. The contract

### 7.1 What is data in J2, not code

| Data | File | Read by the app for |
|---|---|---|
| Types, forms, their sections | `artifacts/types.json`, `templates/<type>/generic.json` | output choices, section lists, views (D161, D166, D168) |
| Library settings | `templates/library-settings.json` (stop words, minimum word length, `no_business_type`, slots, `fact_fields`, `routing` numbers and the rules the generator is told) | nothing directly; the engine reads it; the app's parity and contract tests read it |
| The seed library | `library/index.json` (`schema`, `templates`, `runs`, `run_templates`), `library/<artifact>/<section>/<slug>/vN/*`, `library/run-templates/<id>/*` | the seed sync (D144, D185), the catalog views |
| Run files | `templates.json`, `reuse.json`, `report.json`, `artifacts.json` and the rest of the record catalogue | strict mode (`records.py`), views |

Still in J2's code, and asked to move into `library-settings.json` (D200): `AUTO_MIN` 0.6, `AUTO_WEIGHTS`, `VAGUE_TYPES`, the `style.json` lookup, `run_slots` and `_noun`. Until then they are J2's behaviour, read-only for the app.

### 7.2 What the app reads, and from where

| What | Through | Consumer |
|---|---|---|
| the template library | `j2_template_lib.library_view`, `template_view`, `catalog_view` (with `J2_LIBRARY_DIR` and `J2_RUNS_DIR` set per call) | `GET /api/library`, `/api/library/...`, `/api/catalog` |
| one run template | `run_template_view`, `run_template_use`, `reuse_rows` | `GET /api/run-template`, `/api/run-templates` |
| run template scores | `templates.json` `auto_reuse` | the page, the by-hand checks |
| finished artifacts | `shelf_artifacts` over the team's runs folder | `GET /api/catalog` `artifacts` |
| a served section | `reuse.json`, receipts `door` | records, usage (no model call) |
| types | `j2_types.names()`, `info()`, `FORMS` | settings, views, rehydrate, `engine/forms.py` |
| library lock | `<library>/.lock` through `oslayer` | the engine (patches), the finish step, the seed sync |

### 7.3 Settings the app exposes (D177, D178)

`template_library`, `run_templates`, `auto_reuse`, `artifact_library` (all default off; implied flags are shown as implied), `artifact_schema`; the reviewer pair is not a library setting. `J2_PUSH_RUNS` and `J2_RUN_BY` are fixed by the host and are not settings.

### 7.4 What the app never does

Edit a J2 file except by a numbered patch; rename, move or renumber a template folder or a version of the library; overwrite the owner's library from the seed; write app records into `library/`; push a run folder; read another team's finished runs for a shelf or a door; make a model write to a store.

### 7.5 What J2 is asked to promise

1. The seed is additive: versions are never renumbered; a renamed family keeps `renamed_from` on its versions; keys of `index.json` are added, not renamed or removed.
2. Every template version and run template has its own `schema.json`, and every new run file is named in J2's `docs/` before it is written.
3. Flag-off behaviour does not change between pins except through a note; any commit that does is labelled.
4. A pin is a tag (`cut-off/<date>`), with the list of commits that need the owner's review.
5. Three seams (D200): a runs-folder argument for `catalog_view` and the shelves; a public way to wait for the reviewer thread; an argument in place of `os.environ` for `GET /api/run-template`'s `enabled`.

### 7.6 The contract, as a file and a test

`docs/design/library-contract.json` (new, step 2) lists, per file kind, the keys the app reads and the keys it tolerates; `tests/library/test_j2_library_contract.py` (new) checks the vendored seed, `library-settings.json` and the run files of three mock runs (flags off, on, door on) against it and fails on a key it does not know, a removed key, a renumbered version, or a missing `schema.json`. It is the one place where "what the app reads" is written as data.

## 8. The sync procedure and its checks

Per J2 pin, in this order; each step has a check that fails loudly.

| # | Step | Who | Check |
|---|---|---|---|
| 1 | J2 maintainers tag the pin and list the commits that need review | J2 | the tag exists; the list is in the sync note |
| 2 | Extract with `git archive <commit> prototypes/j2` into a new folder (never the working tree) | app | `vendor_j2.py` refuses a folder that is not a clean extraction |
| 3 | Vendor with the numbered patches | app | `vendor_j2.py --check` (an anchor moved: it stops); `VENDORED.md` regenerated; P15 finds exactly the known home paths |
| 4 | Account for every file | app | `j2_diff_of_record.py --check`: 0 undecided |
| 5 | Contract check | app, reviewed by the shared-library maintainer | `test_j2_library_contract.py` on the seed and the mock runs |
| 6 | Seed sync on a copy of a real data folder | app | `tests/ops/test_seed_sync.py` plus the manual copy: nothing lost, second sync changes nothing |
| 7 | Flag-off neutrality | app | the recorders' `--check` and the golden diff (only `j2_commit` moves) |
| 8 | Flags on: three mock runs and one real-model run | app | strict mode accepts every file; by-hand checks of the sync design |
| 9 | Gate, node, slow, browser suites | app | `scripts/gate.sh`, `node --test`, the slow and browser runs |
| 10 | As-built note, decisions, reported upstream items | app | the note names every patch verdict and every item sent to J2 |

Cadence: at each tag, not on a calendar; a pin that holds only flag-gated work can wait. Who triggers: the J2 maintainers announce, the app team runs, the shared-library maintainer reads the contract report.

## 9. Next engineering steps, in order

| Step | What | Size | Owner (role) | Depends on |
|---|---|---|---|---|
| 0 | Confirm this split and the contract table with the shared-library maintainer; they list the library parts they already hold; walk `library-reuse-order.md` together | S | owner, shared-library maintainer | none |
| 1 | Ship J2 sync 6 (0.5.0): flags as settings, reviewer join, team-scoped shelf, run-template carrier, seed sync, P1 to P19 | M | app team | none (`j2-sync-6.md`) |
| 2 | `library-contract.json` and `test_j2_library_contract.py` | S | app team writes, J2 maintainers review | step 1 (it checks the new pin) |
| 3 | J2 side: tag the pin; add the three seams of 7.5; move `AUTO_MIN`, `AUTO_WEIGHTS`, `VAGUE_TYPES` into `library-settings.json`; review the seven commits that need review | M | J2 library maintainers | none (parallel to 1) |
| 4 | Memory provider spike: read agentrecall-db, decide vendor or own table (memory-evaluation Day 1), register `memory_item/1`, table with FTS5, import lessons and playbooks, recall into Adaptation only | M | app team (family reviewed by the shared-library maintainer) | step 2 for the scope vocabulary |
| 5 | External catalogue phases 1 and 2: `external_software/1`, licence policy function, local store, FTS5 search, seven hand-checked starter entries, read-only list in the UI | M | app team (shape reviewed by the shared-library maintainer) | step 2 |
| 6 | "Save this run as a run template": an owner action over J2's `run_template_from_run`, scrub check (business names, slots), provenance, shows on the shelf | M | app team with J2 maintainers (the function must be safe to call from the engine) | steps 1, 3 |
| 7 | The publish gate: an owner-triggered step that shares a finished artifact or a run template with other teams (later, other installs): scrub rules, approval, provenance, record family `shared_item/1` | L | shared-library maintainer designs, app team builds, owner approves each item | steps 2, 6 |
| 8 | Evaluation with a real model: reuse rate, rework, cost, wrong reuse, for `auto_reuse` and the content door; calibrate the thresholds with J2's maintainers; owner decides whether any flag becomes a default | L | app team runs, J2 maintainers advise, owner decides | steps 1, 3 |
| 9 | Connect the stores: the recall block and the enabled entries in one prompt-assembly path, one budget; catalogue phases 3 and up as in the external plan | L | app team | steps 4, 5 |

Critical path: 1, then 2, then 4 and 5 in parallel with 3; 6 and 8 follow 1 and 3; 7 follows 6. Steps 4 and 5 need no J2 change.

## 10. Decisions

## D194 — The shared library is J2's library data plus the contract; the app's stores sit beside it, not in it
- Sources: D26, D141, D144, D161, `docs/design/library.md`, `memory-evaluation.md`, `external-software-plan.md`.
- Decided: "shared library" names J2's `library/` (seed and run-time), `templates/**`, `artifacts/types.json` and the rules that drive them, shared between the J2 prototype and Sutra Pro. App records (memory items, catalogue entries, atoms, usage) are never written into `library/`. The Interface library keeps its own meaning (closed models and the gate).
- Why: one name for four things caused the "two meanings of library" confusion the memory evaluation already warns about; a library folder that holds only J2's data can be merged by rules at every sync.
- Rejected: a new top-level "shared library" folder in the app (a second copy of J2's tree); putting memory and catalogue tables in `library/index.json` (J2's file, J2's keys).
- Diagram: label "shared library = J2 data + contract", pill on Template library.

## D195 — Ownership is split by role, the contract is a document, a file and a test, and its text belongs to the shared-library maintainer
- Sources: the owner's task, section 6, `docs/design/j2-sync-6.md` D189.
- Decided: the J2 library maintainers own J2's data, code, flags, pin tags and hard-coded behaviour; the app team owns vendoring, settings, scope, records, seed sync, UI and the two new stores; the shared-library maintainer owns the contract text and the design of sharing beyond a team; the owner approves what is shared and decides defaults. A change to what the app reads from J2 changes the contract document, `library-contract.json` and `test_j2_library_contract.py` in one change.
- Why: two people working on the same library need one place that says who may change what and what the other side can rely on; a test makes the promise cheaper than a meeting.
- Rejected: ownership by file path only (the paths overlap at the seed and the patches); a shared-library maintainer who owns the app's vendoring (the app team already carries the goldens and the patch table).
- Diagram: label "library ownership by role", pill on Template library.

## D196 — Memory and the external catalogue are separate app-side stores behind the gate, with one write path and one scope vocabulary
- Sources: `memory-evaluation.md` Decisions A to E, `external-software-plan.md` Decisions C and D, D7, D26.
- Decided: `memory_item/1` and `external_software/1` are closed families in the Interface library, stored as tables in the app's SQLite, never in J2's `library/`. Models propose, `GATE.check` and the scrub admit, the owner edits and approves. Both key their scope on chart NodeIds. Memory is recalled into a run through the capability addendum and the node-context file (P9), the lessons and playbooks seam stays P5, and the catalogue's enabled entries reach a run through the engine host. Neither serves content into an artifact.
- Why: one write path and one scope vocabulary mean one set of tests and one backup; separate storage means a library sync cannot lose a memory and a memory migration cannot corrupt a template.
- Rejected: memory as a J2 library kind (it holds facts, not structure); the catalogue inside the template library (it holds references to software, not section specs); a third-party memory layer with its own write path.
- Diagram: label "memory + catalogue: app stores, one gate", pill on Interface library.

## D197 — Nothing is shared beyond a team by default; sharing is a later, owner-triggered publish step with scrubbing
- Sources: D184, D26, `docs/design/j2-sync-6.md` section 10 (business names in family names), the owner's rule that nothing is pushed unless asked.
- Decided: finished artifacts and run folders stay in the team that made them; the content door and the Artifacts shelf read the team's own runs. Templates are one store because they are structure, with business values replaced by slots on the shelf. A "publish" step (step 7) is designed by the shared-library maintainer: the owner picks one item, the scrub removes business names and any secret shape, the record keeps provenance, and the item enters a shared place that other teams may read; nothing is published by a flag or a schedule.
- Why: a finished document holds the business's own facts; a family name can carry a business name; sharing must be a visible act.
- Rejected: a global shelf with a filter (disclosure one click away); automatic sharing of run templates made by live runs.
- Diagram: label "no sharing without publish", pill on Template library.

## D198 — The sync follows one procedure of ten steps, each with a check that fails loudly
- Sources: D136, D154, D160, D176, D190, section 8.
- Decided: the procedure of section 8 is the sync's definition of done; a J2 tag starts it, the app team runs it, the shared-library maintainer reads the contract report; the as-built note names every patch verdict and every item reported upstream.
- Why: sync 5 and sync 6 both found, by running the checks, what the analysis did not say; a fixed list keeps the next sync from skipping one.
- Rejected: syncing on a calendar (a pin of flag-gated work can wait); a sync without the contract test (the contract would be prose).
- Diagram: label "sync procedure, 10 checks", pill on Template library.

## D199 — The `template` kind of external software stays a plain catalogue row in v1
- Sources: `external-software-plan.md` open question 7, D194.
- Decided: an external entry of kind `template` is listed, described and approved like any other, and gives no routing or matching; a template from outside enters the J2 library only by a maintainer's review through the seed path and the contract test. Whether the router may reuse external templates is a later question for the J2 library maintainers.
- Why: the router's matching is J2's and flag-gated; a second way into the library would bypass the contract.
- Rejected: importing external templates at run time (a write into the global library from a catalogue entry).
- Diagram: label "external template: row only", pill on Interface library.

## D200 — The J2 library maintainers are asked to move the remaining constants into data and to add three seams
- Sources: D188, D189, `j2-sync-6.md` section 11, J2 `docs/hardcoding-inventory.md`.
- Decided: `AUTO_MIN`, `AUTO_WEIGHTS`, `VAGUE_TYPES`, the `style.json` lookup, `run_slots` and `_noun` move into `templates/library-settings.json` (they are decisions and numbers about reuse, which the library's cleanup already moved for 11 of 13 rows); a runs-folder argument for `catalog_view` and the shelves; a public way to wait for the reviewer thread; an argument for `enabled` in the run-template view. The app does not patch any of it; it adopts the data when a pin contains it.
- Why: the owner's refactoring rule applied to the library: decisions in data with one owner; the app's per-call environment switching is a workaround the seams remove.
- Rejected: patching the copy (two truths); leaving the constants in code (the app cannot show or tune them).
- Diagram: label "J2 asked: constants to data, 3 seams", pill on Template library.

## 11. Risks and open questions

| Risk | Effect | Mitigation |
|---|---|---|
| Library lock | a non-reentrant `flock`; a new J2 writer not wrapped loses an index row; a nested take waits 30 s | P10 covers four writers (D181); the contract test greps the writers; each sync re-runs it |
| Seed growth | 157 to 437 files, 0.8 to 2.2 MB, every existing install syncs once | measured in sync 6; the sync is under the lock, writes once, marker-gated; watch it at each pin |
| Family renames | an adapted template is a new family named for the business; `move_versions` moves versions; the seed then holds the family under a new name | additive sync (D185); the report names both; J2's resolver follows `renamed_from`; the contract requires `renamed_from` |
| Business names in names | family and run-template names carry the business of the run that made them, visible to every team | structure with slots on the shelf; the publish gate (D197) is where names are scrubbed; until then an owner who shares a machine between businesses should know it |
| Flags | three experimental flags, seven J2 commits "needs owner review" | off by default, project forced off, evaluation before any default (step 8) |
| Two people on one library | duplicated or conflicting work | step 0 lists the parts each holds; the contract is the one place where a change is announced |
| Memory scope vs team | a memory item scoped to a node outlives a merge unless re-pointed | `repoint` through `carry_links` (memory evaluation section 5) |
| Licences of external entries | a copyleft entry vendored by mistake | licence policy function and gate rules before any entry (external plan Decision E) |
| This design rests on the repository | the maintainer's parts of the library are not visible here | Step 0 |

Open questions for the owner and the shared-library maintainer (none blocks sync 6): which library parts the maintainer holds (Step 0); whether the contract file lives in this repository or next to J2's data; who tags the J2 pin; when the evaluation of step 8 is worth a real-model budget.

## 12. Change log

- 2026-11-13: first version, written with `docs/design/j2-sync-6.md` after reading the two proposals (memory, external software) and the J2 library at `1adb8ecd`.
