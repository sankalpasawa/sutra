# Artifact Library Reuse Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or
> superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** When a run follows a run template and the source run's section was written from exactly this workflow's
inputs, restore that section's structured data from the source run, validate, rule-check, render and receipt it as
a built one, and skip the model call. A near fit hands the builder the source data as a draft inside the normal
attempt loop. Anything else builds as today. Nothing new is stored: the source is the run the template was made
from.

**Architecture:** Pure logic in a new module `j2_artifact_lib.py` (no import of `j2`; reads the runs folder through
`j2_template_lib.runs_root` and the run template through `get_run_template`). `j2.py` gets one hook `_route_content`
beside `_route_template` (j2.py:9500) and one served attempt in the builder loop. Flag `J2_ARTIFACT_LIBRARY=1`, off
by default, implies `J2_AUTO_REUSE=1`; needs `J2_ARTIFACT_SCHEMA=1`.

**Tech Stack:** Python 3.14, J2 (`j2.py`, `j2_template_lib.py`, `j2_artifact_models.py`, `j2_rules.py`), `STUDIO_MOCK=1`,
`J2_LIBRARY_DIR` and `J2_RUNS_DIR` set to copies in every test.

**Spec:** `docs/superpowers/specs/2026-11-13-artifact-library-reuse-design.md` (revision 4)

## Global Constraints

- Branch `artifact-library`, on `origin/main` e283bef0.
- Windows: run Python with `PYTHONUTF8=1`.
- Baseline: `python realization_test.py` passes; flow tests by name: `auto_reuse`, `run_templates`, `reuse_display`,
  `folder_reuse`, `sutra_library`, `library_cleanup`, and always `plain_unchanged`.
- Flag off = byte-identical behaviour to main. Flag on never makes more builder calls than flag off for the same brief.
- No stage, document or workflow name in code or prompts; no earlier business's name in a prompt (:8133 rule).
- A source run that cannot be read records `unknown`, never `none`. Lookup failure never blocks a run.
- Zero-call reuse is certain on exact fingerprint and template equality, and tried (then verified) when the router
  reused the shape for another client (founder 13 Nov: cross-client yes for now). Never on `extended`, `created`
  or `generic`.
- A served reuse that passes refunds the workflow's charge (`charged = False`, `_recalc_spent`); nothing else does.
- The seven "needs owner review" commits are reviewed (founder 13 Nov); this plan lands on top of them.
- The unit restored is the structured section data (`<kind>.json` `sections`), never rendered text.
- Nothing is written into `library/` or into any run folder other than this run's. The only source-side write is
  `mark_run_template_used`.
- Tests: `python artifact_lib_test.py`, `python realization_test.py` pass; `python j2_flow_test.py --fast` no new failures.

## Review Focus

1. Same brief twice: run 2 auto-picks run 1's template, 0 builder calls on document sections, four receipt layers
   present and passing, audit passes.
2. Pilates-from-yoga: each document section is `reuse` (cross) with all checks passing, or `adapt` with the failing
   receipt named; no yoga word in any final section or prompt; calls <= flag off; refunds only on `reuse` rows.
3. Source data broken against this run's PRD ids: `reuse` fails at artifact-rules with a receipt, then `adapt`, then `build`; calls <= flag off.
4. Source run folder absent: every door `unknown`, run equals main. Flag off: no `reuse.json`. Flag on alone: the implied paths are on.

| # | Task | Impact | Effort |
|---|---|---|---|
| 0 | Branch and baseline | enables the rest | 0.5 h |
| 1 | `j2_artifact_lib.py`: `source_section` (locate and read the source run's section) | the content can be found | 1.5 h |
| 2 | `door(need, rec, source)`: exact-fingerprint reuse, action-gated adapt | the decision itself | 1 h |
| 3 | `j2.py`: `_route_content`, the served attempt through validate -> data -> render -> receipts, the draft prompt | the run skips or shortens the build inside today's budget | 5 h |
| 4 | Runs pushed to Git: `.gitignore`, post-run push behind `J2_PUSH_RUNS=1`, author in the run meta, SETUP rows | what Disha builds, Rubak can reuse | 2 h |
| 5 | Chat line, `reuse.json`, Library tab content column, Artifacts tab badge | founder can see what was reused | 1.5 h |
| 6 | Flow tests (eight scenarios incl. flag implication and call ceilings) | proves the four review points | 3.5 h |
| 7 | Docs: README, SETUP rows (also the two missing ones), RELEASES | versioned per Key Rules | 1.5 h |

Total about 16.5 h (revision 3 was 18 h; the separate store and per-stage registration are gone, the runs-pushing
task is new and decided).

---

### Task 0: Branch and baseline

- [ ] `git fetch origin && git switch -c artifact-library origin/main`
- [ ] Record `python realization_test.py` count and that the named flow tests pass on main. Record builder call
  counts of the pilates and yoga mock runs with the flag off (the ceilings for Task 6).
- [ ] Commit "Artifact library: spec and plan".

### Task 1: `j2_artifact_lib.py`: locate the source section (code)

**Files:** create `j2_artifact_lib.py`, `artifact_lib_test.py` (`ok()` style of `realization_test.py:1-30`).
Pattern source: `j2_template_lib.py` `runs_root` :2674, `get_run_template` (:2550 area), `run_artifacts` :2875
(how it reads `templates.json`, `summary.json`, `workflows.json` of a run), `_read` :730.

- `enabled()`: `J2_ARTIFACT_LIBRARY == "1"`; when on, `j2_template_lib.auto_reuse()` returns True.
- `SourceUnreadable(Exception)` with a reason.
- `source_section(run_tpl_id, key, kind, section, root=None)` -> `{data, fingerprint, template, facts, audit,
  receipts_passed, run, workflow, sha}` or `None` when the row has no `made_from` or the source wrote no such
  section; raises `SourceUnreadable` when the run folder or a needed file is missing or broken.
  - `rt = get_run_template(run_tpl_id)`; row by `key`; `src_run = rt.made_from_run`; `src_wf = row.made_from`.
  - decision: the last entry of `<src_run>/templates.json` `decisions` with `workflow == src_wf` and
    `artifact == kind` (a finished revision stands for its original, as `run_template_from_run` does).
  - data: `<src_run>/<kind>.json` `sections[section]`; `sha = sha_of(data)`.
  - audit: `<src_run>/stage-<kind>.json` audits or `summary.json` status; `receipts_passed` from `receipts.jsonl`
    for `src_wf`'s last attempt.
- [ ] Tests on a fixture run folder under `fixtures/` (copy of a mock document run with `prd.json`, `templates.json`,
  `receipts.jsonl`, `summary.json`): found; row without `made_from` -> `None`; folder missing -> `SourceUnreadable`;
  broken JSON -> `SourceUnreadable`; `enabled()` on -> `auto_reuse()`, `run_templates_on()`, template library
  `enabled()` all True. Commit.

### Task 2: the door (code)

**Files:** `j2_artifact_lib.py`, `artifact_lib_test.py`.

- `door(need, rec, source)` -> `{"door": reuse|adapt|build|unknown, "rule": str, "reason": str, "source": {...}|None}`:

| source | condition | door | rule |
|---|---|---|---|
| `SourceUnreadable` | any | unknown | 0 |
| present, audit pass | `source["fingerprint"] == need["fingerprint"]` and `source["template"] == f"{rec['template']}@{rec['version']}"` | reuse | same |
| present, audit pass | `rec["action"] == "reused"`, fingerprint differs | reuse (verified) | cross |
| present | `rec["action"] == "extended"` | adapt | near |
| present | `rec["action"] in ("created", "generic")` | build | new |
| `None` | any | build ("no source section") | none |

- [ ] One test per row, plus: router `reused` under rule a/b/s with a different fingerprint -> reuse with rule
  `cross`, not `same`; `None` `first` -> build ("no run template"). Commit.

### Task 3: `j2.py` hook, the served attempt, the draft (code)

**Files:** `j2.py` (`_turn_workflow_agent` :8094, attempt loop :8200-8352, validate/render block :9690-9732,
`_artifact_receipts` :9783, `_run_checks` :9965, `_doc_prompt` :9471, `_route_template` :9500, `_run_tpl_first` :3388).

- `self.art_lib = j2_artifact_lib.enabled()` beside `self.tpl_lib` (:3123).
- `_route_content(w, rec, need, first)`: once per workflow (cache like `tpl_routes`); `source_section` -> `door`;
  record in `self.content_decisions`; save `reuse.json` (`{"schema": "artifact-reuse/1", "decisions": [...]}`); one
  `self.post("system", ...)` line.
- Served attempt: when the door is `reuse` and `attempt == 1`, skip `one_call()`; `reply = {"section": source["data"]}`;
  run the existing validate -> `art_data` -> `render_section` block; then `_run_checks` + `_artifact_receipts`
  (:8334-8336). No `calls_used` increment. All pass -> normal "done" path, `mark_run_template_used`, and the refund:
  `w["charged"] = False; self._recalc_spent()` (the held-work pattern at :8014-8015), `reuse.json` row gets
  `refunded: w["cost"]`. Any failure -> `evidence` as today, door recorded `adapt`, loop continues, no refund.
- Draft: when the door is `adapt`, `_doc_prompt` carries `source["data"]` as `DRAFT` (neutral label) for one model
  attempt; after it fails the draft is dropped and the door is recorded `build`. `limit` and `MAX_CHECK_ATTEMPTS`
  untouched.
- Document workflows only (`self.doc`); page workflows record `build` with reason "pages: phase 2".
- [ ] Flow test `content_reuse_same_brief`: one brief twice into copies of `library/` and `runs/` with the flag; run 2
  auto-picks run 1's template; assert door `reuse` rule `same` on every document workflow, `calls_used == 0`,
  receipts for artifact-schema, artifact-rules, artifact-render and the atom checks present and passing, audit
  passes, and `self.spent` drops by each reused workflow's cost (Priority's budget line shows it).
- [ ] Flow test `content_cross_client`: the pilates brief over the yoga template; for each document workflow assert
  the door is `reuse` rule `cross` when the restored section passes every check, else `adapt` with the failing
  receipt named (`no-invented-facts` or artifact-rules); no yoga word in any final section or prompt; calls <= the
  Task 0 ceiling; refunds only on the `reuse` rows.
- [ ] Flow test `content_failed_rules`: alter the source run's `prd.json` so a section cites ids this run's PRD does
  not have; assert artifact-rules fails on the served attempt, chain `reuse -> adapt -> build`, calls <= ceiling.
- [ ] Commit.

### Task 4: Runs pushed to Git (config and one post-run step; decided 13 Nov)

**Files:** `.gitignore` (the `runs/` rule), `SETUP.md`, `j2.py` (the Done path near `_write_summary` :10646).

- [ ] `.gitignore`: remove `runs/`; keep `memory/`, `_backup/`, `projects/`, `*.log`. Everything in a run folder
  travels for now (founder: "push everything, segregation later"); note the large files (`calls.jsonl`,
  `site/shots/*.png`) in SETUP so the decision to trim them later is a one-line change.
- [ ] Post-run push behind `J2_PUSH_RUNS=1`: after `_write_summary`, `git add runs/<id> && git commit -m "run <id>
  (<provider>, <business>)" && git pull --rebase && git push`, each step in a try/except that posts one system line
  on failure and never stops the run. Off by default in tests (`plain_unchanged` must not touch git).
- [ ] The run's author: `chat.jsonl` meta line gets `by` (git `user.name`) so the shelf can segregate later.
- [ ] SETUP: rows for `J2_RUNS_DIR` (the shelf and the content check read it) and `J2_PUSH_RUNS`.
- [ ] Test: a mock run with `J2_PUSH_RUNS=1` in a throwaway git repo leaves one commit containing the run folder;
  with the flag off, no commit.
- [ ] Commit.

### Task 5: Visibility (code)

**Files:** `j2.py`, `j2_template_lib.py` (`reuse_rows`, `reuse_counts` :939), `j2_artifacts.py` (`rows` :125),
`j2_server.py`, `j2_ui.html` (grep only).

- Chat line: `W-3: served <section> from run <run> (receipts 4 of 4 passed, 0 model calls)` /
  `W-3: drafting <section> from run <run>` / `W-3: source run unreadable (<reason>); built`.
- `reuse_rows` and `reuse_counts` take `reuse.json` too: a `content` column beside the template kind, so the
  Library tab's chips count both.
- `j2_artifacts.rows` adds `reused_from: {run_template, key, run}` when `reuse.json` names the row; Artifacts tab
  badge; Shelf 1 entry of the source artifact shows `used_by` the new run (through `mark_run_template_used`).
- [ ] Test: `reuse_counts` on a fixture with both files; `rows()` carries `reused_from`. Commit.

### Task 6: Flow tests, the remaining spec scenarios (tests)

- [ ] `plain_unchanged` with flag off: no `reuse.json`, call counts equal main.
- [ ] `content_flag_implies`: with only `J2_ARTIFACT_LIBRARY=1`, the implied paths are on inside a mock run.
- [ ] `content_source_missing`: delete the source run folder mid-run; every decision `unknown`; run completes.
- [ ] `content_one_item_changed`: sections covering the changed item are `adapt`, others `reuse`.
- [ ] `content_no_template`: the law-firm PRD -> all `build`, reason "no run template".
- [ ] Commit.

### Task 7: Docs and version (docs)

- [ ] README: replace "Here every workflow is custom" (README.md:635) with plan, shape and content reuse and their
  flags; one line on `find` as the plan-time search that Adaptation will call.
- [ ] SETUP.md: rows for `J2_RUN_TEMPLATES`, `J2_AUTO_REUSE` (missing today) and `J2_ARTIFACT_LIBRARY`.
- [ ] RELEASES.md: entry under the next version (protocol change: reuse-before-build).
- [ ] Commit; open PR `artifact-library` -> `main`.
