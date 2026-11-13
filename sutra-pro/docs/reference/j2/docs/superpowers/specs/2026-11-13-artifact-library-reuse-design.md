# Artifact library reuse: check the library before a workflow builds

Base: `origin/main` at `e283bef0` (second pull, 13 Nov evening; PRs #199 library cleanup, #200 Sutra library with
two shelves and `find_artifact` / `find_template`, #201). Revision 4. Revision 3 folded in six findings of an
independent code review (**R3**). Revision 4 (**R4**) re-bases on the two-shelf library and drops the separate
section store. Sources: founder call transcripts (30 Oct; 13 Nov "file copier" meeting), `Founder Direction/` PDFs,
J2 code at `j2.py`, `j2_template_lib.py`, `j2_artifact_models.py`, `j2_rules.py`, `j2_artifacts.py`,
`docs/library-reuse-order.md`, `templates/library-settings.json`, `fixtures/folder-run/`.

## Intent

After Adaptation splits the goal into workflows, every workflow today gets its own builder call. The founder's
framing (30 Oct, 60:34-64:16): build it, reuse one the Sutra library already holds, or borrow an outside tool. On
13 Nov he set the homework: build a small software through Sutra, put it in the library, and in the next run with
a similar prompt the graph must *use* it, not make it again.

What the library does on main today, per workflow: it reuses the **plan** (run templates), the **shape** (section
templates) and, since #200, it can **list** finished artifacts a piece of work could start from (`find_artifact`),
with no caller yet. It does not reuse **content**: every builder still writes its section, and the file-copier test
(`folder_reuse`) has the second run write `copy_files.py` again.

This spec adds the content step for document sections: when this run follows a run template and a section of the
source run was written from exactly these inputs, restore that section's data, put it through every check a built
section gets, and skip the model call.

**R3, scope.** This is a narrower first application of door two. The founder's homework (borrow the file copier as
a tool in a later run) needs two more things that are out of this spec: Adaptation calling `find` at plan time
(assigned to Rubak on 13 Nov) and a "use this artifact" workflow kind. The third door (outside tools) stays out.

## What the founder's documents require (and what they forbid)

| Rule | Source | How this design keeps it |
|---|---|---|
| Match after the workflow's success test is known, not from its name | Spec p12; Consolidated App. J | the need is built from `covers_text` and charter facts; the reused section runs every check a built one runs |
| Reuse-first, smallest change: KEEP / REUSE / REPAIR / CREATE-NEW | Spec p4 decision 6; Consolidated p6 | three doors: reuse, adapt (the builder starts from the stored data), build |
| A reused artifact is not a satisfied goal until verified | PRD p2; Consolidated p6 | validated, rule-checked, rendered and receipted exactly as a built one |
| Failed retrieval is not evidence of absence | Spec p12; PRD p9 | a source run that cannot be read records `unknown`, never `none` |
| Prefer reuse with evidence, smaller scope, reversible | Spec §8.1 | only a source run whose stage passed audit counts; the source is read, never changed |
| Applicability: same client facts, type, section | PRD p4; Roadmap p40 | **R3**: exact equality of the need fingerprint; the router's action alone is not enough |
| "Artifact first, then template" | `docs/library-reuse-order.md` (#200) | the content check sits after the shape route but serves the same order: a finished section before a fresh fill |

## What exists (deep dive, origin/main e283bef0)

| Need | Exists | Reuse |
|---|---|---|
| A per-workflow hook before the builder runs | `_route_template` j2.py:9500, called from `_turn_workflow_agent` j2.py:8094 (j2.py unchanged by #199-#201) | same place |
| A need with a fingerprint | `_template_need` j2.py:9554 -> `make_need` :1171, `fingerprint` :1166 (type + section + business type + facts + fields); the fingerprint is recorded in every routing decision (`templates.json`, :1503) | the equality key |
| The router's recorded decision | `route` :1488: `reused` under rules a, b, s, t (:1477 path for an adapted version that already existed), `extended`, `created`, `generic`; numbers now read from `templates/library-settings.json` (`routing()`, `EXTEND_MIN` :1641) | **R3**: gate for `adapt`, not for `reuse` |
| Which template workflow a registered workflow stands for | `_run_tpl_first` j2.py:3388 writes `run_tpl["used"][w["id"]] = key`; each template row has `made_from` (the source run's workflow id) and the template `made_from_run` | **R4**: key -> source run -> source workflow -> source section |
| Structured section data of a stage, saved per stage | validate (j2.py:9690-9701) -> `art_data[kind][section]` -> `render_section` (:9725); `<kind>.json` and `site/<kind>-vN.json` written by `_save_artifact_data` (:9827) with `sections: data` | **R4**: the content to restore is read from the *source run's* `<kind>.json`; no copy is stored |
| The receipts a built section gets | `_run_checks` :9965 plus `_artifact_receipts` :9783 (artifact-schema, artifact-rules against `_artifact_docs` :9733, artifact-render), every attempt at :8336 | **R3**: a reused section takes the same path |
| The builder's budget | `MAX_CHECK_ATTEMPTS` 3 (:336); `model_call_limit` (:8210); evidence to the next attempt (:8348) | **R3**: adapt and build stay inside it |
| **Shelf 1, Artifacts** (#200) | `run_artifacts` :2875, `shelf_artifacts` :2977: one entry per whole artifact a run produced, read from the **runs folder** (`runs_root` :2674: `J2_RUNS_DIR` or `runs/`), with business, checks (workflows done, conditions met, done-when passed, data valid), file shas, the template it was made from, and its sections with the template each filled | **R4**: the catalog of finished work is the runs folder, so this spec reads from it too |
| **Shelf 2, Artifact templates** (#200) | `shelf_templates`, skeletons with charter slots; no business value on the shelf | unchanged |
| **Search** (#200) | `find_artifact` :3132 (score = 0.5 x same business + 0.5 x share of the need's words in the source charter), `find_template` :3166, `find` :3199 ("artifact first, then template"); documented in `docs/library-reuse-order.md` "for Sankalp and Rubak"; **no caller in j2.py or j2_server.py** | plan-time search is Rubak's step; this spec does not call it |
| **Folder outputs** (#199) | a type whose output is a folder of files (`folder_of` :2339, `folder_files` :2346); a run template carries `outputs: {type: {folder, files, test}}` (structure only); `folder_decision` :2622 says `reused` when the second run writes the same file list | the file-copier fixture; content still rewritten |
| Library location | top-level `library` is a path file pointing at `prototypes/j2/library`; `runs/` is gitignored and no run is tracked (`git ls-files runs` is empty) | **R4**: see prerequisite below |

**Gap, after #200.** The shelf can list a finished artifact and say why it is similar; nothing restores one. No
path sets `calls_used` to 0 by reuse. The shelf reads run folders that exist only on the machine that made them.
README and SETUP still have no row for `J2_RUN_TEMPLATES` or `J2_AUTO_REUSE`.

## Decision: runs are pushed to Git (founder, 13 Nov meeting; confirmed 13 Nov evening)

Runs go into the Sutra repo, segregated by who ran them, so that what Disha builds, Rubak can reuse. Shelf 1
already reads the runs folder; this spec reads the same folder. Consequences:
- `.gitignore` stops ignoring `runs/` (today: ignored, zero runs tracked). Every record file this spec and Shelf 1
  read travels: `goal.json`, `workflows.json`, `templates.json`, `<kind>.json`, `site/<kind>-vN.json`,
  `summary.json`, `stage-*.json`, `receipts.jsonl`, `artifacts.json`, `documents.json`, `sections.json`,
  `chat.jsonl` (its first line carries provider and mock, which `run_facts` reads). `calls.jsonl` (full prompts
  and replies) and screenshots are the large files; they are pushed too for now, per the founder ("push
  everything, segregation later").
- A finished run is pushed by default (Task 4: a post-run step behind `J2_PUSH_RUNS=1`, or a git hook).
- A source run that is not present locally (not pulled yet) still records `unknown`, never `none`.
- Segregation by user and a quality gate on what enters the shelf are later problems the founder named as
  secondary; nothing here depends on them.

## Goals

1. For each registered document-section workflow, one content decision after the router's decision and before any
   builder call: `reuse`, `adapt`, `build`, or `unknown` (source run unreadable). Recorded in `reuse.json` and as
   one chat line.
2. A reused section is validated against this run's template, rule-checked against this run's earlier documents,
   rendered by code, and receipted (schema, rules, render, work-atom checks) exactly as a built one. On any failure
   it enters the normal builder loop with the source data as a draft. Never a silent skip.
3. **R3**: the chain `reuse -> adapt -> build` stays inside today's budget. No run makes more builder calls with
   the flag on than with it off.
4. **R4**: nothing new is stored. The source of a section is the run named by the run template (`made_from_run`),
   the workflow named by its row (`made_from`), and that run's `<kind>.json` and `templates.json`. The reuse is
   recorded on the source side only as `used_by` on the run template (existing `mark_run_template_used`).
5. Off by default (`J2_ARTIFACT_LIBRARY=1`, implies `J2_AUTO_REUSE=1`; needs `J2_ARTIFACT_SCHEMA=1`). A run without
   the flag behaves exactly as today. A test proves which paths the flag turns on.
6. No stage, document or workflow name in code or prompts; no earlier business's name reaches a prompt.

## Non-goals

Calling `find` from Adaptation (Rubak). A "use this artifact" workflow kind for folder outputs such as the file
copier. Outside tools. A second similarity formula. Website page sections (phase 2). Reuse of rendered text.

## How it works

### Step 1. Locate the source section (**R4**: read, do not store)

`j2_artifact_lib.source_section(run_tpl, key, kind, section, root=None)`:
- `rt = get_run_template(run_tpl["id"])`; `row = the workflow with key`; `src_run = rt.made_from_run`;
  `src_wf = row.made_from`.
- Read `runs_root(root)/<src_run>/templates.json`: the decision for `src_wf` gives `fingerprint`,
  `template@version`, `facts`. Read `<src_run>/<kind>.json`: `sections[section]` is the data. Read
  `<src_run>/summary.json` and `stage-<kind>.json` for the stage's audit result; `receipts.jsonl` for the passing
  receipts of `src_wf`'s last attempt.
- Returns `{data, fingerprint, template, facts, audit, receipts_passed, run, workflow, sha}` or raises
  `SourceUnreadable` (folder missing, file missing, JSON broken) with the reason.

### Step 2. The door (**R3**: exact fingerprint for reuse)

In `_turn_workflow_agent` j2.py:8129, right after `_route_template` returns and before the builder loop:

```
if self.art_lib and self.doc and first:          # J2_ARTIFACT_LIBRARY=1; first = _run_tpl_first(...)
    door = self._route_content(w, rec, need, first)    # reuse | adapt | build | unknown
```

| Source section for `first["key"]` | Condition | Door |
|---|---|---|
| `SourceUnreadable` | any | `unknown` -> build; reason recorded |
| present, stage audit pass | `source.fingerprint == need.fingerprint` and `source.template == rec.template@version` | `reuse` (same client, same facts: certain) |
| present, stage audit pass | `rec.action == reused` under any rule, fingerprint differs | `reuse`, tried first and verified (**founder 13 Nov: cross-client reuse is a yes for now**) |
| present | `rec.action == extended` | `adapt` |
| present | `rec.action in (created, generic)` | `build` |
| none (row has no `made_from`, or the source workflow wrote no section) | any | `build`; reason "no source section" |

The cross-client row relies on Step 3 to stop another client's facts leaking in: the `no-invented-facts` condition
(j2.py:1434, names and numbers not in this charter) and the artifact-rules receipt (ids that must exist in *this*
run's documents) both run on the restored section. A yoga studio's name in a pilates studio's section fails
there and the door drops to `adapt`, where the neutral-label rule (:8133) keeps the name out of the prompt.

### Step 3. Verify a reused section like a built one (**R3**)

On `reuse`, attempt 1 of the builder loop is served from the source instead of a model call: validate
`source.data` against this workflow's routed template or model (same code as :9690-9701); on success set
`art_data[kind][section]` and `art_state[atom]["data"]`, render with `render_section`, write the section; then
`_run_checks` and `_artifact_receipts` run as for a built section. All pass -> report to Coordination,
`calls_used` stays 0, `mark_run_template_used` records the run. Any failure -> the loop continues as today with
`evidence`, the source data in the prompt as `DRAFT` (door `adapt`); after one failed draft attempt the draft is
dropped (door `build`). Attempts and calls are the existing loop's.

**Refund (founder 13 Nov: yes).** When a served reuse passes, the workflow's charge is released the way held work
is released today: `w["charged"] = False` then `_recalc_spent()` (j2.py:8014-8015, :7952). The Priority screen
shows the budget going back up by the workflow's cost; `reuse.json` records `refunded: <cost>`. An `adapt` or
`build` is not refunded.

On `adapt`, attempt 1 is a model call whose prompt carries `source.data` as `DRAFT` under the neutral-label rule
(:8133). Not promised to take one call.

### Step 4. Audit is unchanged

## Success

| Scenario (offline, mock, library copy, runs copy, `J2_ARTIFACT_SCHEMA=1`) | Expected |
|---|---|
| Same brief run twice, flag on | run 2 auto-picks run 1's template; every document section is `reuse`, 0 builder calls, four receipt layers pass, audit passes |
| Pilates brief, yoga template auto-picked (`auto_reuse` (b)) | every document section `adapt`; `DRAFT` in attempt 1; calls <= flag off; no yoga word in a prompt |
| Same business, one done-when item changed | sections covering that item `adapt`, the rest `reuse` |
| Law-firm PRD, no similar run template (`auto_reuse` (d)) | no `first` -> all `build`; reason "no run template" |
| Source run folder absent (not pulled) | every decision `unknown`, run completes as today |
| Source data hand-broken against this run's PRD ids | artifact-rules receipt fails on the served attempt -> `adapt` -> `build`; calls <= flag off |
| Flag off | no `reuse.json`, call counts equal main (`plain_unchanged`) |
| Flag implication | with only `J2_ARTIFACT_LIBRARY=1`, `auto_reuse()`, `run_templates_on()`, template library `enabled()` and the schema path are on |

Expected reuse, honestly: `reuse` only when the inputs match exactly (a re-run or change request of the same
client). A similar business lands on `adapt`. Unrelated businesses `build`. The file copier is not covered: its
second run still writes the files; borrowing it as a tool is the plan-time step (Rubak) plus a workflow kind this
spec does not add.

## Founder decisions, 13 Nov evening

1. Refund: **yes**. A served reuse that passes releases the workflow's charge (Step 3).
2. Cross-client reuse of content: **yes for now**. A section whose shape the router reused is tried first for any
   client and verified; the invented-facts condition and the rules receipt are the guard (Step 2 table).
3. Phase 2 order: **decide later**. Nothing in phase 1 depends on it.
4. The seven "needs owner review" commits: **reviewed, fine**. This lands on top of them.
5. Runs are pushed to Git. No separate section store.

Expected reuse, revised for decision 2: a similar business (the pilates case) now lands on `reuse` when the shape
fits as it is and the restored section passes every check, and on `adapt` when a check catches the other client's
facts. The test `content_adapt_similar` becomes `content_cross_client`: assert the door chain and that no earlier
business's name reaches the final section or any prompt.
