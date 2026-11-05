# Build on a run: design

Branch `build-on-run`, forked from `template-library-fixes` at `2a758d4`. Design only: no code, no AI runs.
Every number below is read from files under `runs/`, `library/` or the code; where a run holds no figure it says
**not recorded**. Token sizes of run files are bytes divided by four and are marked "~".

## Goal

A person opens any finished run (say, a cat website), types a new brief, and a **new** run starts on top of it.
The new run inherits the whole context of the old one: charter and facts, PRD, HLD and LLD, workflows and their
outputs, `site/` (and `backend/` when present), the templates it used, the decisions taken with the Requester,
the done-when items, and the lessons and playbooks it left. The old run is never changed. The new run records
`based_on`.

Two cases drive the design:

- **Extend**: the same business, more of it ("add a shop to the cat site").
- **Rebase**: a new business on the same base ("the same site for a dog groomer").

---

## 1. What exists today, what each piece reuses, and the gap

### 1.1 A run folder

A run is a folder `runs/j2-<YYYYMMDD-HHMMSS>/` written by `J2Run` (`j2.py:2830`). Read back by
`saved_dir` / `saved_snapshot` (`j2.py:2707`, `:2752`), which are read-only and refuse any name that is not a run id.

| File | What it holds | Recorded in |
|---|---|---|
| `goal.json` | the charter: statement, site_name, audience, standards, rules, done_when, business_type, visitor_needs, to_be_confirmed, **facts**, charter_items, core_items | every run |
| `goal.v<k>.json` | the charter before each J2_CHANGE change (`j2.py:4155`) | no run under `runs/` (J2_CHANGE has only mock tests) |
| `realization.json`, `realization.md` | the realization plan (`j2.py:5598`), the base `plan_change` reads | not in the three reference runs (they predate it); not in `j2-20261103-184249` or `j2-20261105-183106` either |
| `change.json` | each change: diff, intents, docs, revise, new, drop, held, left_out, relay objections and rulings | **not recorded** in any run folder |
| `workflows.json` | every workflow of the current stage with atoms, covers, revises, outputs, cost, status | every run (~98k tok in `j2-20261022-123744`) |
| `atoms.json`, `receipts.jsonl`, `outputs.jsonl` | atom/1 views, check receipts, builder outputs | realization-era runs |
| `chat.jsonl` | first line `meta` (run, output, provider, model, mock, j2_fixes); then every message | every run (~65k tok in `j2-20261022-123744`) |
| `calls.jsonl` | every AI call with system, prompt, raw reply, tokens, seconds | live runs since 7 Oct |
| `audits.json`, `conflicts.json`, `conditions.json` | audits with results, rubric, conditions; bargains; necessary conditions | most runs |
| `prd.md`, `hld.md`, `lld.md` (+ `.docx`), `documents.json`, `chain.json`, `stage-<doc>.json`, `sections.json` | the design documents, their agent_output, the requirement → component → LLD section → atom chain, each stage's sections | documents runs (`j2-20261016-160511`, `j2-20261021-141350`, `j2-20261022-123744`, `j2-20261103-184249`, `j2-20261105-183106`) |
| `style.json` | the style guide the first builder wrote | website runs |
| `site/index.html`, `site/v<N>.html`, `site/<doc>-v<N>.md`, `site/shots/` | the page, every version, every document version, screenshots | website runs |
| `templates.json`, `templates/<artifact>/<section>/<slug>@v<N>/{spec,model,schema,meta}.json`, `template_calls.jsonl` | the router's decisions and the run's own copy of every template it used (`save_into_run`, `j2_template_lib.py:791`) | `j2-20261103-184249` (33 decisions, 18 copies), `j2-20261103-161111-3` |
| `backend.json`, `site/server.py`, `backend/check-1.sqlite`, `backend/start-1.log` | backend/1: endpoints, tables, checks, the server file | `j2-20261105-183106` only (mock; tokens not recorded) |
| `summary.json`, `report.json`, `report.md`, `map.json`, `artifacts.json` | the end-of-run summary (ai_calls, cycles, budget, done_when with pass, lessons used/saved, playbooks used/saved, identity_to_requester_facts and decisions, change_requests), the reviewer's report, the map | most finished runs |

The folders `j2-20261103-*` and `j2-20261105-*` are in the main checkout's `runs/` and are not tracked on this
branch; the three reference runs of 16, 21 and 22 October are tracked.

### 1.2 J2_CHANGE: a second prompt on a finished run

`j2_change.py` plus the wiring in `j2.py` (`:5643` to `:5970`). Flow, as the code does it:

1. `user_says` (`j2.py:3399`): a message after `done` is posted with `change: true` and becomes `self.feedback`.
2. `_identity_intake` with `change` (`j2.py:4010`): Identity returns the updated charter, keeping every item word for
   word and adding one item per outcome asked for. `CURRENT CHARTER` is in the prompt.
3. `_fact_problems` (`j2.py:3594`): every charter fact must be a substring of the brief, the change, the intake
   answers and every user message; otherwise the validator rejects the charter once, then code drops the facts.
4. `_start_work` (`j2.py:5651`): `charter_diff(real_base, goal)`. Nothing changed: the run ends. `goal_changed`
   (statement or audience differ): `_replan`, the whole plan is made again. Else `_turn_change`.
5. `_turn_change` (`j2.py:5677`): `plan_change` decides each intent once: removed → A; added with an owner → edit
   the owner and judge (A at ≥ 0.80, size fault → C, else one improvement → B or C); too big or no owner → C (a
   new workflow in a stage of the plan) or D (a new stage). Planning documents the changed workflows read are
   revised first. New workflows below the gate are improved, then broken down, then held with their items left out.
6. `_change_rows` turns the record into fixed workflows Adaptation must propose: documents first, then revisions
   (`revises: <latest id>`, named "<name> (change k)"), then new workflows. The validator refuses anything else.
7. `_change_relay` (`j2.py:5793`): after each revised planning document is built, its readers agree or object
   (two rounds, then Identity rules); affected readers get a revision **registered by code** with
   `carry_checks` (facts-present checks that named a removed charter string are dropped; headings must stay).
8. Audit runs as today; a Done after a change replaces the run's playbook.

Guard (`_change_applies`, `j2.py:5647`): only when `J2_CHANGE=1`, realization is on, the run is **not a document
run and not a blueprint run** (one with an LLD as the spec), and a realization plan exists.

Recorded cost of a change on a finished run (the J2_FIXES path, which the change machinery replaced; the
J2_CHANGE path has no live run on disk):

| Run (main checkout) | Original run | The change "Add a section for visiting hours" |
|---|---|---|
| `j2-20261023-123852`, yoga studio, live | 202 calls, 5.58M input tokens, 265k output, 3,430 model seconds, 12:40 to 15:26 | 15 calls, 430k input, 13.7k output, 189 model seconds, 15:36 to 15:40 |
| `j2-20261025-235138`, boutique, mock | 0 calls before (the run was a change test) | 40 calls, tokens not recorded |

A change on a finished site cost about 7 percent of the calls and tokens of the run it changed.

### 1.3 Lessons and playbooks

`memory/lessons.jsonl` and `memory/playbooks.jsonl` (`j2.py:73`, `:75`) are git-ignored and global to a machine.
Neither file exists in this checkout or the main one: their contents are **not recorded**. Their shapes come from
the code:

- A lesson (`_learn`, `j2.py:9307`): `{id: L-<run>-<n>, problem, cause, fix, run, cycle, versions, workflows, t,
  output?, test?, mock?}`. `relevant_lessons` (`j2.py:2649`) offers at most 5, by word overlap with the current
  gap, same output type only.
- A playbook (`_save_playbook`, `j2.py:9263`): `{id: P-<run>, run, t, business_type, brief[:300], visitor_needs,
  sections, build_order, workflows, costs, what_failed, watch_out, advice, outcome, used_playbook?}`.
  `relevant_playbooks` (`j2.py:2633`) offers at most 2, **same business_type only**, by word overlap with the
  brief, at the first J2.b of a brief or after feedback.
- The run records what it used and saved: `summary.json` → `lessons.used`, `lessons.saved`, `playbooks.used`,
  `playbooks.saved`; the UI shows them in the Lessons and Playbooks tabs.

### 1.4 The template library

`library/` at the repo root (`index.json`, then `<artifact>/<section-slug>/<template-slug>/v<N>/`). Per workflow,
`_route_template` (`j2.py:8318`) builds a need (`make_need`: artifact, section, business_type, the charter facts
behind its items, the fields the facts imply, a fingerprint), scores every stored version (`candidates`,
`j2_template_lib.py:1027`: fingerprint match first, then coverage), and one generator call decides reuse, extend,
create or generic. The decision goes to `templates.json`; the chosen version is copied into the run
(`save_into_run`); `run_templates` reports each decision's source as "from this run", "from library" or
"not recorded". Run `j2-20261103-184249` (Still Point Yoga, live): 33 decisions, 18 template copies, 133 calls,
4.06M input tokens, 18:43 to 19:24.

### 1.5 The server and the run list

`j2_server.py` serves one live `J2Run` and any saved run read-only: `GET /api/runs` (`list_runs`, `j2.py:2737`:
id, status, the first 120 characters of the brief), `GET /api/state?run=<id>` (`saved_snapshot`), `POST /api/say`,
`POST /api/reset` (a new empty run). `j2_ui.html:3207` fills the Run settings picker; `?run=<id>` opens a run
read-only; the Needs-you strip shows one outcome line with "See report" for a finished run.

### 1.6 The gap

| Need | Exists | Missing |
|---|---|---|
| Start a run from another run's files | nothing: `reset()` always starts empty | a fork that fills a new run folder from a parent and records `based_on` |
| Take a new brief on a finished plan | J2_CHANGE, for the live run only, website runs without documents | the same path on an inherited run, and on document and blueprint runs |
| Keep a business's facts, or drop them | `_fact_problems` validates against the brief and answers | an inherited fact source (extend) and an explicit drop with an absence check (rebase) |
| Reuse the parent's plan | playbooks, same business type only | the parent's plan as the base whatever the business type |
| Reuse the parent's templates | the library, scored by fingerprint and coverage | the parent's own copies tried first |
| Share a run with another person | nothing: no login, no mark | a shareable mark, stripping, and who may fork |
| See where a run came from | nothing | ancestry on the child, a diff against the parent |

---

## 2. Fork: copied, referenced, provenance, and the untouched original

### 2.1 The fork call

`POST /api/fork {parent: <run id>, mode: "extend" | "rebase", brief: <text>, keep_style: bool, by: <name>}`.
Code only, no AI call. Refused (409) while a live run is running, as `/api/say` is. Steps:

1. `saved_dir(parent)` must exist and `summary.json` status must start with `done` (done, done_with_open_items).
   An unfinished parent is refused: there is no stable plan to build on.
2. A new `J2Run` folder `runs/j2-<now>/` is made by `reset()` as today.
3. `fork_from(parent_dir, mode, …)` copies what section 2.2 lists, writes `based_on.json`, and sets the in-memory
   state (section 3) so that the new brief runs through J2_CHANGE.
4. The new brief is posted by `user_says` with `change: true`; the run starts.

### 2.2 Copied into the child

| Copied | Into | Why |
|---|---|---|
| `goal.json` | `parent-charter.json`, and loaded as `self.goal` and `self.real_base` | the charter the change is diffed against |
| `realization.json` | same name, loaded as `self.real` | `plan_change` needs the plan; absent in the parent → see 2.5 |
| `workflows.json` (the latest revision of each chain, status done) and the parent's `stage-*.json` workflows | `inherited-workflows.json`, loaded into `past_workflows` with `inherited_from: <parent>`; ids unchanged; the child's new ids start after the parent's highest | `revises`, `covers`, `dependencies` and `owner_index` all key on ids; keeping them keeps the change planner correct |
| `atoms.json` entries of those workflows | `atoms.json` | a revision copies its predecessor's atom and carries its checks |
| `sections.json`, `stage-*.json`, `style.json` | same names | the builders' own sections and the style guide |
| `prd.md`, `hld.md`, `lld.md`, `documents.json`, `chain.json` | same names; `site/<doc>-v1.md` is the parent's final text | documents are revised, not rewritten |
| `site/index.html` | `site/v1.html` and `site/index.html` | the child's first version is the parent's final page; revisions go to v2 onwards |
| `backend.json`, `site/server.py` (when present) | same names | the backend is part of the site |
| `templates.json`, `templates/` | same names, each decision marked `inherited: true` | the parent's templates are tried first (section 8) |
| last entry of `audits.json` | `audits.json` with `inherited: true`, version 1 | what was still failing or accepted carries over as context, never as a pass |
| `summary.json` → `identity_to_requester_facts`, `identity_to_requester_decisions`, `to_be_confirmed`, `dropped_by_requester`, the intake Q and A from `chat.jsonl` | `inherited-answers.json` | Identity does not ask again; the facts validator's source (extend only) |
| `summary.json` → `lessons.saved`, `playbooks.saved` ids | `based_on.json` | offered first from memory (section 1.3), never copied |

Documents and the page are copied once each; `.docx` files are not copied, they are exported again at the end.

### 2.3 Referenced, not copied

`chat.jsonl`, `calls.jsonl`, `receipts.jsonl`, `outputs.jsonl`, `conflicts.json`, `report.*`, `map.json`,
`artifacts.json`, `site/v<N>.html` versions, `site/shots/`, `backend/*.sqlite` and logs. They are the parent's
evidence, not context. `based_on.json` lists them under `referenced`, and the UI links to them on the parent
(`?run=<parent>`).

### 2.4 Provenance: `based_on.json` (schema `based-on/1`)

```json
{"schema": "based-on/1", "parent": "j2-20261022-123744", "mode": "extend", "forked_at": "2026-11-06T10:00:00",
 "forked_by": "not recorded", "chain": ["j2-20261016-160511", "j2-20261022-123744"],
 "parent_status": "done_with_open_items", "parent_business_type": "coffee shop", "parent_site_name": "Brew Lab",
 "copied": [{"from": "goal.json", "to": "parent-charter.json", "sha256": "…"}],
 "referenced": ["chat.jsonl", "calls.jsonl"],
 "dropped_facts": [], "kept_style": true, "shareable": false,
 "parent_lessons": ["L-20261022-123744-1"], "parent_playbook": "P-20261022-123744"}
```

`chain` is the parent's chain plus the parent, oldest first; a fork of a fork has two ancestors. The first line of
the child's `chat.jsonl` (meta) gains `based_on: <parent>`, `summary.json` and `report.json` gain `based_on` and
`chain`, and `list_runs` returns `based_on` so the picker can show it. Every copied file's sha256 is recorded, so the
diff view (section 7) can tell "kept as copied" from "changed" without reading the parent.

### 2.5 The original is never changed

- The fork opens parent files with `open(..., "r")` and `shutil.copyfile` only; nothing under the parent is opened
  for writing, renamed or removed. The parent path comes from `saved_dir`, which already refuses anything that is
  not a run id inside `RUNS_DIR`.
- The child is a new folder; `self.dir` never points at the parent. `save()` writes only under `self.dir`.
- Memory is global: `save_playbook` replaces only a playbook with the same id, and the child's id is its own, so
  the parent's `P-<parent>` stays. Lessons are append-only.
- The template library's `mark_used` writes `used_by` into `library/.../meta.json`, not into any run.
- `based_on.json` records the parent's file hashes. A mock test (section 9) hashes every parent file before and
  after a fork and after the child finishes; the UI's diff view re-hashes the parent on demand and shows
  "parent changed since the fork" if any hash differs (it should never).
- A parent without `realization.json` (every run on disk today) still forks: the inherited workflows give the owner
  index, and `plan_change` gets a plan rebuilt by code from them (`name`, `stage: build` for page workflows and the
  document's stage for document workflows, `delivers = covers`, `inputs_from = dependencies`). The record says
  `plan_source: "rebuilt from workflows"`. It is not judged again.

---

## 3. The new brief through the J2_CHANGE machinery

No new planner. The child starts in the state a finished run is in when a second prompt arrives:

| State at fork | Value |
|---|---|
| `self.goal`, `self.real_base` | the parent charter (rebase: its skeleton, section 4.2) |
| `self.real` | the parent's realization plan, or the rebuilt one |
| `self.past_workflows` | the inherited workflows; `self.workflows` empty |
| `self.sites`, `self.sections`, `self.style`, `self.docs`, `self.chain`, `self.docset`, `self.stages` | from the copied files; `stage_i` at the last stage |
| `self.done = True`, `self.stamped = True`, `self.audits = [inherited]` | so `user_says` treats the brief as a change and `_start_work` runs the diff |
| `self.intake` | the inherited answers (extend) or empty (rebase) |

Then, exactly the flow of section 1.2:

1. Identity updates the charter with the change prompt that already exists (keep every item word for word, add one
   item per outcome). For a fork the prompt adds one sentence: "This run is built on an earlier run; the items and
   facts below are that run's." No new reply format.
2. `charter_diff` on charter numbers. The intents are the J2_CHANGE intents: removed → A (the owner lets go, a
   workflow left with nothing is dropped and its section removed from the page); added → owner edit and judge → A
   or B, or C and D placements; planning documents first; Relay to the readers; audit.
3. One addition for forks, **refresh intents**: an item whose text differs from the parent's only by facts (the
   skeleton texts are equal, section 4.2) is neither added nor removed. Code registers a revision of its owner with
   the task "replace these facts: old → new", exactly as Relay registers revisions for affected readers
   (`carry_checks` with the old facts as `gone`, plus the new facts as facts-present). No judge call. This is what
   makes rebase cheap.

What is rebuilt and what is kept:

| Part of the parent | Extend | Rebase |
|---|---|---|
| Workflows whose items are unchanged | kept; their sections copied byte for byte into the new page | refresh revision when their section holds a dropped fact; else kept |
| Owners of edited items | A or B revision through the planner | the same |
| Planning documents read by a changed or new workflow | revised first, then Relay | revised first (a refresh revision when only facts change), then Relay |
| New items | C or D: new workflows, new sections | the same |
| Style guide | kept | kept when `keep_style`, else the first builder writes a new one |
| Templates | parent's first | parent's first; usually "extend" because the fingerprint's facts differ |
| Audit | full audit of the assembled page and every document, as after any change | the same, plus the absence checks of section 4.2 |

The guard `_change_applies` is widened for forks: a run with `based_on` may be a document run or a blueprint run
(the cat site with PRD, HLD and LLD is one). The documents' own change path is the same relay the planning
documents already use: a revised PRD section is a document workflow revision, its readers (HLD sections, then LLD
sections, then page builders) answer in `relay_waves` order. Today's non-fork guard is unchanged, so a run without
`based_on` behaves exactly as today (the `plain_unchanged` test keeps proving it).

`goal_changed` is the one rule that changes. Today a different statement or audience means a full re-plan. For a
fork the compare is made on the skeletons (facts replaced by slots): extend keeps the statement; rebase changes the
business name in it, which is a slot, so the goal is the same and the plan is kept. A statement that changes in its
words beyond the slots is still a full re-plan, as today, and the record says so.

---

## 4. Two cases

### 4.1 Extend: "add a shop to the cat site"

- `mode: extend`. Business type, site name and every fact carry over. The facts validator's source is the parent
  brief, the parent's answers (`inherited-answers.json`), the new brief and the new answers, so Identity may copy
  any parent fact into a new item without a rejection.
- Identity's charter keeps the parent's items 1 to n and adds the shop's items (n+1 onwards). Shop facts the brief
  does not give (prices, how to pay, delivery) are asked once, as J2.a does, or go to `to_be_confirmed`.
- `charter_diff`: added only. The match call asks every inherited workflow whether the item is its job; a shop is
  usually too big for the page's product section, so items go C (new workflows in the build stage; the product
  plan and engineering documents are revised first) or D when a new kind of thinking is needed (for payments,
  `security` from `stages.json`; for stock, `data`). Nothing else is rebuilt.
- The page: inherited sections kept, new sections appended in `run_order`; Audit checks the whole page.
- Playbook: the parent's playbook has the same business type, so `relevant_playbooks` already offers it; the fork
  puts `parent_playbook` first in the offer.

### 4.2 Rebase: "the same site for a dog groomer"

The problem is the parent's facts: "Brew Lab", "12, 100 Feet Road, Indiranagar, Bengaluru 560038",
"hello@brewlab.example", seven menu items with prices (the ten facts in `runs/j2-20261022-123744/goal.json`).
They sit in the charter items, every document, every section and the page. Left in, Identity would copy them into
the new charter and `_fact_problems` would reject them (they are not in the new brief), and Audit's D-5, P4, L6
and the no-invented-facts rules would fail the documents and the page.

Design:

1. **Fact slots.** At fork, code reads the parent's `facts` list and classifies each with `fact_fields`
   (`j2_template_lib.py:947`, which already turns facts into typed fields: name, address, email, phone, list items
   with prices). Each fact becomes a slot `⟨name⟩`, `⟨address⟩`, `⟨email⟩`, `⟨menu item 1⟩` … The parent charter
   with every fact replaced by its slot is the **skeleton charter**, saved as `parent-charter.skeleton.json`.
   Facts that `fact_fields` cannot type keep a generic slot `⟨fact k⟩` with the kind "not recorded".
2. **Facts dropped.** The child's `goal.facts` starts empty; `based_on.dropped_facts` lists every parent fact with
   its slot. `inherited-answers.json` is not loaded: the parent's answers are the old business's. The facts
   validator's source is the new brief and the new answers only, so a parent fact that leaks into the new charter
   is rejected exactly as an invented one.
3. **Identity fills the slots.** The change prompt carries the skeleton charter, not the parent's: "This run is
   built on an earlier run for a different business. Every ⟨slot⟩ is a fact of that business, now dropped. Fill
   each slot from the new brief; ask for the ones it does not give; a slot the Requester cannot fill goes to
   to_be_confirmed." The reply is the same charter JSON as today. The intake rounds are today's J2.a.
4. **The diff on skeletons.** `charter_diff` compares the new charter's items, each with its new facts replaced
   by their slots, against the skeleton. An item that differs only in facts is a refresh intent (section 3): its
   owner is revised by code with "old → new" per fact. Items that differ in words are added or removed as today.
   The statement and audience are compared the same way, so "the same site for a dog groomer" keeps the plan;
   "a booking system for a dog groomer" is a full re-plan.
5. **Absence checks.** Every revised workflow, every document revision and the final audit get one check per
   dropped fact: `facts-absent` on the fact's exact text (a new check type next to `facts-present`, run by the same
   substring code with `expect: false`). "Brew Lab" surviving anywhere fails that workflow's checks before Audit
   sees it. A dropped fact that the new brief repeats (two shops on the same road) is not checked for absence;
   `based_on.dropped_facts` records it as `kept_by_new_brief`.
6. **Business type and playbooks.** `business_type` comes from Identity's new charter. The parent's playbook is a
   coffee shop's, so `relevant_playbooks` does not offer it; the inherited plan is the base instead, which is the
   point of the fork. A dog groomer playbook in memory is offered as today.
7. **Style.** `keep_style` (default on): the parent's `style.json` is copied and the first builder does not write
   a new one. Off: the first builder writes one as in a fresh run. The fork dialog asks once.
8. **Templates.** The need's fingerprint changes (business type and facts), so the parent's specialised templates
   rarely match by fingerprint; they match by fields, and the recorded router behaviour on `j2-20261103-184249`
   (extend when the fields fit but the facts differ) is what to expect.

What carries over in rebase: the plan, the stage order, the document structure and headings, every section's
layout and markup, the style guide, the templates, the lessons, the checks, the done-when items as skeletons.
What does not: the facts, the Requester's answers, the playbook, the business type.

---

## 5. Context budget: what each agent receives from the parent

### 5.1 What a call costs today

Recorded input tokens per call (`calls.jsonl`, `tokens.input`, which for the Claude CLI counts cache reads):

| Run | Calls | Input tokens | Output tokens | Builder avg in | Coordination | Identity | Adaptation | Audit | Priority |
|---|---|---|---|---|---|---|---|---|---|
| `j2-20261016-160511` | 113 | 3.22M | 194k | 27.9k | 27.4k | 28.8k | 30.0k | 33.6k | 27.0k |
| `j2-20261021-141350` | 130 | 3.55M | 155k | 26.1k | 27.3k | 25.6k | 27.5k | 37.7k | 26.6k |
| `j2-20261022-123744` | 198 | 5.96M | 285k | 27.8k | 28.3k | 31.0k | 30.5k | 39.2k | 29.4k |
| `j2-20261103-184249` | 133 | 4.06M | 173k | 28.1k | 30.9k | 32.0k | 29.7k | 35.9k | 29.0k |

Each prompt starts with `STATE` (brief, feedback, charter, workflows, findings, the chat summarised) which in the
largest builder call of `j2-20261022-123744` is ~10k tokens before the chat and ~27k with it. A fork must not add
the parent's chat to the child's chat: the child starts with one meta line and one system line, so its first
calls are smaller than the parent's last ones.

### 5.2 Sizes of what a parent holds (`j2-20261022-123744`, ~ tokens)

| File | ~tokens | | File | ~tokens |
|---|---|---|---|---|
| `goal.json` | 950 | | `prd.md` | 1,260 |
| `style.json` | 320 | | `hld.md` | 3,560 |
| `chain.json` | 410 | | `lld.md` | 4,070 |
| `documents.json` | 2,300 | | `site/index.html` | 4,160 |
| `audits.json` (whole) | 8,280 | | `summary.json` | 8,140 |
| `workflows.json` | 98,250 | | `chat.jsonl` | 65,520 |
| `atoms.json` | 61,260 | | `receipts.jsonl` | 26,600 |

The four files on the right-hand bottom rows are never put in a prompt.

### 5.3 What each agent gets, and only when its task touches it

| Agent | From the parent | ~tokens added | Not given |
|---|---|---|---|
| Identity (intake of the new brief) | the parent charter or its skeleton; in extend, the inherited answers | 1,000 to 1,500 | chat, documents, workflows |
| Adaptation (the change planner, `plan_change`) | the base charter, the plan (names, stage, delivers, inputs_from; ~150 tokens per workflow, 10 workflows ~1,500), the inherited owners' names | 2,500 to 3,000 | atoms, sections, the page, audits |
| Adaptation (proposing the rows) | the change rows as today | 0 extra | |
| Priority | the rows plus each revised workflow's recorded `cost` (the change cost rule, `_change_cost`) | under 500 | |
| Coordination | the rows' `after` and the inherited ids they name | under 500 | |
| A builder revising an inherited section | its own section (`sections.json`, 500 to 2,000), its atom (~1,000), its LLD slice (500 to 1,000), the HLD summary (~300), `style.json` (~320), the manifest of other sections (~500), its template spec (~1,000) | 4,000 to 6,000 | the parent page as a whole, other sections' text, the chat |
| A new builder | the same minus the section; the manifest lists the inherited sections' anchors and selectors | 3,000 to 4,500 | |
| A document reviser (artifact workflow) | the document file it revises (prd 1,260; hld 3,560; lld 4,070), the artifacts it reads at 6,000 characters each (`_artifact_context`, ~1,500 each) | 3,000 to 7,000 | |
| Relay readers | the revised document and their own output, as today | as today | |
| Audit | the new page (up to `SITE_LIMIT` 150,000 characters, ~37k; recorded page 4,160), the documents, the charter, the inherited audit's results (~1,000 from the last entry) | as today plus ~1,000 | the parent's earlier audits |

Rule: a prompt never carries more than one inherited section, one document and one audit entry. A parent file that
is not on the row of the agent's task is not read. `j2_replay_size.py` (estimates prompt size from a saved run)
is the tool for the test in section 9 that proves the budget.

Expected whole-run cost, from the recorded change on `j2-20261023-123852` (15 calls and 430k input tokens for one
new section against 202 calls and 5.58M for the run it extended): an extend fork with two or three new sections
should take 25 to 50 calls and 0.8M to 1.5M input tokens; a rebase of a ten-section site with refresh revisions
and one audit, 40 to 70 calls and 1.2M to 2.0M. These are estimates to be measured by the live runs of section 9,
not recorded figures.

---

## 6. Sharing between people

The prototype has no login (`docs/j2-handoff.md`, "no login"). Sharing is designed for the current state: one
machine, several people, and a copy of a run moved to another machine.

- **The mark.** `POST /api/runs/<id>/share {shareable: true|false, by: <name>, scope: "extend" | "rebase"}`
  writes `runs/_shares.json` (a sidecar at `RUNS_DIR` level, keyed by run id, never inside the run folder, so the
  run stays as it was). `list_runs` returns `shareable` and `share_scope`. The owner is the `by` name recorded when
  the run was started (`J2_USER`, or the name typed in Run settings; "not recorded" for every run on disk today).
- **Who can fork.** The owner: always, both modes. Anyone else: only a run marked shareable, and only in the scope
  the mark allows. The default scope is `rebase` (facts dropped), because the facts are the owner's business.
  A `by` name that is not the owner and no mark: 403 with the reason.
- **What is stripped on a fork by someone else.** The fork copies nothing personal by construction: `chat.jsonl`,
  `calls.jsonl`, `receipts.jsonl` and `outputs.jsonl` are referenced, never copied. In `rebase` scope the facts and
  the Requester's answers are dropped (section 4.2). In `extend` scope the facts stay, but contact facts (anything
  `fact_fields` types as email or phone, and anything matching the fake-phone rule `+91 00000`) are replaced by
  slots and listed in `based_on.stripped_facts`, so the second person asks for their own.
- **What blocks a fork.** Before any copy, every text file to be copied is run through the server's `secrets()`
  values (`j2_server.py:29`: every `.env` value and any credential-looking variable). A hit refuses the fork and
  names the file, not the value. A parent whose `receipts.jsonl` records a live send (`J2_SEND_MODE=live` with a
  confirmed recipient) is refused for others: its deed outputs name real recipients.
- **What stays shared anyway.** `memory/` and `library/` are global on a machine; a lesson, a playbook or a
  template written by one person's run is offered to the next person's run today. The fork does not change this;
  the risk is noted in section 10.
- **Moving a run between machines** (a zipped run folder dropped into `runs/`) is out of scope; the design only
  needs `saved_dir` to find it.

---

## 7. UI

- **"Build on this run."** On the Needs-you strip's outcome line of a finished run (next to "See report"), on the
  Report tab, and in Run settings beside the saved-run picker. It opens one dialog: the new brief (textarea), the
  mode as two plain choices ("Add to this business" / "Same site, new business"), "Keep the look" (on), and the
  name of the person. Submit → `POST /api/fork` → the page reloads on the live run. Disabled with a reason while a
  run is running or when the mark forbids it. The Simple view gets the same button under the finished-run message
  with the same two choices; the words follow the Simple view's rules (no internal terms).
- **Ancestry on the child.** Under the header: "Built on `j2-20261022-123744` (Brew Lab, coffee shop), which was
  built on …", each ancestor a link to `?run=<id>`. Run details gets a Lineage table (run, mode, business type,
  forked at, by, facts dropped). The Map puts a `parent` node above the Charter, drawn as a run chip (hollow when
  the parent folder is missing), with Open → the parent. The run picker shows "↳ built on <parent>" after the
  brief.
- **Diff vs parent.** A "Changes vs parent" view under Internals, code only:
  - Charter: items added, removed, refreshed (old fact → new fact) and kept, from `change.json`'s diff and
    `based_on.dropped_facts`.
  - Workflows: kept (inherited, no revision, section sha equal), revised (revises an inherited id; before and after
    of the section text from `sections.json`), new, dropped.
  - Documents: headings added, removed and kept (`headings_of`), and a line diff of each revised document against
    `site/<doc>-v1.md`.
  - Page: the section list before and after, and the parent's last screenshot next to the child's.
  - Templates: each decision's source: "from parent run <id>", "from this run", "from library", "not recorded".
  - Cost: the child's calls and credits next to the parent's, from the two `summary.json` files.
- **Diff of two runs** generalises to any pair later; this version shows only parent and child.

---

## 8. Template library interaction

- `candidates(need)` gains a second source: the parent's `templates/` copies. Each folder `load_dir`s
  (`j2_template_lib.py:756`) and is scored like a library version, with `from_parent: <run id>`. Sort order: a
  fingerprint match first as today, then **parent before library on an equal score**, then version, then name.
- The router's prompt lists the parent candidate as "the template this site was built with". Reuse and extend
  then behave as recorded: `j2-20261103-184249` routed the Problem section to "extended" from a v1 whose fields fit
  and whose facts differed, which is the rebase case exactly.
- A decision that picked a parent copy is recorded with `source: "from parent run <id>"` (`_source` gets a fourth
  value) and the copy is saved into the child by `save_into_run` as today, so a fork of the fork finds it.
- The library stays the store of record: an extended template is written to `library/` by `store` as today.
  Nothing is written into the parent's `templates/`.
- With `J2_TEMPLATE_LIBRARY=0` the fork still works; `templates.json` is copied for the record and the builders
  fill nothing.

---

## 9. Tests

### 9.1 Mock first (`j2_flow_test.py --fast`, `STUDIO_MOCK=1`; the J2_CHANGE scripts in `change_test.py`)

| Test | Proves |
|---|---|
| `fork_leaves_parent_untouched` | sha256 of every parent file is equal before the fork, after it, and after the child ends Done; `based_on.json` holds the chain and the copied hashes |
| `fork_extend_adds_only` | brief "add a visiting hours section" on a mock finished site: `change.json` has one added intent routed C; every inherited section is byte-equal in the child's page; one new section; Audit passes; outcome Done |
| `fork_rebase_drops_facts` | the child's `goal.facts` holds no parent fact; a scripted Identity reply that repeats a parent fact is rejected by `_fact_problems`; the skeleton diff yields refresh intents only; every refresh revision carries `facts-absent` checks; a scripted builder that leaves "Brew Lab" in fails its check |
| `fork_rebase_asks_for_slots` | a brief that gives the name but not the address: Identity's intake asks for the address once; unanswered, it is `to_be_confirmed` |
| `fork_goal_changed_replans` | a brief that changes the statement beyond the slots still triggers `_replan`, as today |
| `fork_documents_run` | a parent with PRD, HLD and LLD: the PRD revision comes first, Relay walks HLD then LLD then the builders in `relay_waves` order |
| `fork_chain_of_two` | a fork of a fork: `chain` has two ancestors; the ancestry line names both |
| `fork_templates_parent_first` | with `J2_TEMPLATE_LIBRARY=1`, a parent copy with the same score as a library version is chosen; its source reads "from parent run" |
| `fork_share_rules` | a non-owner fork without a mark → 403; with a rebase mark → facts dropped; an extend mark → contact facts replaced by slots and listed; a parent with a secret in a copied file → refused |
| `fork_context_budget` | `j2_replay_size.py` over the child's `calls.jsonl`: no prompt contains a line of the parent's chat; a reviser's prompt carries one section and one document; the per-agent additions stay under the figures of section 5.3 |
| `fork_ui_render` | `j2_ui_render.js`: the button appears only on a finished run; the ancestry line and the Changes-vs-parent view render from a saved child |
| `plain_unchanged` | unchanged: a run without `based_on` produces identical prompts, page and outcome |

### 9.2 Two live runs, each against building from scratch

No run on disk is a cat website, so the parent is made first and doubles as the scratch baseline for the extend
case. Four live runs, same provider and model, `J2_CHANGE=1`, `J2_TEMPLATE_LIBRARY=1`, memory on:

| Run | Brief | Compared with |
|---|---|---|
| P0 (parent and baseline) | a cat website with PRD, HLD and LLD: name, address, services and prices, a contact form | — |
| L1 (extend fork of P0) | "add a shop: three products with prices, a basket, pay at pickup" | S1, from scratch: the P0 brief plus the shop |
| L2 (rebase fork of P0) | "the same site for a dog groomer": new name, address, services, email | S2, from scratch: the dog groomer brief |

Measured for each, all from the run's own files:

| Measure | Source |
|---|---|
| AI calls | `summary.json` `ai_calls`; `calls.jsonl` row count |
| Input and output tokens | `calls.jsonl` `tokens` summed, per agent |
| Minutes | first and last `t` in `chat.jsonl` (wall clock, Requester waits included); `seconds` summed in `calls.jsonl` (model time) |
| Done-when met | `summary.json` `done_when[].pass` count over total; `workable` |
| Credits | `summary.json` `budget.used` |
| Templates | `templates.json` actions: reuse, extend, create, generic; sources |
| Invented-fact flags | audits' D-5, P4, H5, L6 results and `rejections` with `charter_facts` |
| Facts dropped (L2) | `based_on.dropped_facts`; `facts-absent` receipts |

Pass lines: L1 and L2 end Done or Done with open items with at least the same done-when pass count as S1 and S2;
L1 uses fewer than half of S1's calls and tokens; L2 uses fewer than S2's; no parent fact in L2's page or documents;
P0's hashes unchanged after both forks. Each result goes into this document's section 9.3 with the run ids; a
measure a run does not hold is written "not recorded".

### 9.3 Results

Not run yet.

---

## 10. Phases, risks, out of scope

### 10.1 Phases (one developer, mock tests in each phase)

| Phase | Work | Estimate |
|---|---|---|
| 1. Fork core | `fork_from`, `based_on.json`, the copy list, the read-only guard and hash test, `POST /api/fork`, the extend path through J2_CHANGE on a website run, `list_runs` with `based_on` | 2 days |
| 2. Documents and blueprint runs | widen `_change_applies` for `based_on` runs; the document revision through Relay; `stage_i` at the last stage; the rebuilt plan when `realization.json` is missing | 1.5 days |
| 3. Rebase | fact slots from `fact_fields`, the skeleton charter and diff, refresh intents registered by code, `facts-absent` checks, Identity's slot prompt, `keep_style` | 2 days |
| 4. Templates first and context budget | parent candidates in `candidates`, the fourth source, the budget test with `j2_replay_size.py` | 1 day |
| 5. UI | the button and dialog in both views, the ancestry line, Run details lineage, the Map's parent chip, Changes vs parent | 2 days |
| 6. Sharing | `_shares.json`, owner and scope rules, stripping, the secrets and live-send refusals | 1 day |
| 7. Live runs | P0, L1, S1, L2, S2 and the table in 9.3 | 0.5 day of work plus about 4 hours of model time (the reference runs took 30 to 60 minutes each) |

Total about 10 working days. Phases 1 and 3 are the ones the owner should see before the rest is built.

### 10.2 Risks

| Risk | Where it bites | Mitigation |
|---|---|---|
| `_change_applies` excludes document and blueprint runs, which is every documents parent on disk | phase 2 | the widening is behind `based_on`; non-fork runs keep today's guard; `plain_unchanged` guards the plain path |
| `goal_changed` forces a full re-plan, which would throw the plan away on every rebase | phase 3 | the skeleton compare; a statement that changes beyond its slots still re-plans, as today |
| The judge scores an unedited inherited owner low (the 30 Oct live test in the spec: nearly everything went to B) | phase 1 | owners are edited before they are judged, as `plan_change` already does; refresh intents skip the judge |
| False invented-fact flags (open issue 2 in the handoff: "This PRD" read as a name) will fire more in rebase, where every document is revised | phase 3 | the absence checks are exact strings; the P4 name detector's false flag is a separate fix the owner has not approved |
| Workflow id collisions between inherited and new workflows | phase 1 | ids kept; the child numbers from the parent's highest id plus one; a test asserts uniqueness across `_all_wfs()` |
| Cycle and budget caps: a refresh of ten sections is ten fixes at 8 credits (`rates.json`), and `J2_MAX_CYCLES` is 6 | phase 3 | refresh revisions are registered in one cycle like Relay's; the fork dialog shows the least cost (`_change_cost`) before the run starts |
| "Given is not used" (open issue 1): a reviser may rewrite its section instead of editing it | phases 1 and 3 | the refresh task names the exact old and new strings and the checks compare the section's other text to the inherited one (a `text-kept` check on the section's headings and selectors) |
| Memory and the library are global: a parent's lessons, playbook and templates reach another person's run even without a mark | phase 6 | recorded as a limit; a per-person memory needs the login that does not exist |
| The inherited audit is read as a pass | phase 1 | it is marked `inherited` and counts for context only; the first audit of the child is full |
| Two people fork the same parent at the same second | phase 1 | `reset()` already suffixes a second folder |

### 10.3 Out of scope

- Forking an unfinished run, or forking in the middle of a run.
- Merging two parents, or rebasing a child onto a newer parent.
- Editing the parent in any way, including adding files to its folder.
- Login, accounts, or moving runs between machines (the sidecar mark is per machine).
- Live sends from a forked run; `J2_SEND_MODE` stays `dry-run` or `mock`.
- A general two-run diff beyond parent and child.
- Per-person memory and library.
- Backend data: `backend/*.sqlite` is never copied; a forked backend starts with empty tables.
