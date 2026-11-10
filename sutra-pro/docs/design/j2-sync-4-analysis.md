# J2 sync 4: what changed in `prototypes/j2` against the vendored J2 (`9200cf6`), and what it means for Sutra Pro

_Repo Analyst (stage 1 of 5) · read-only analysis: no source file changed, no commit · 2026-11-10 · branch `feat/sutra-pro-j2-sync-4` (cut from `origin/main` `b5dd56f8`) · next readers: solution-architect, then developer_

Legend. **U** = the change is also on J2's own `origin/main` (`dfa44b3`, as last fetched into the J2_Prototype clone; I did not fetch). **S** = it exists only in the sutra copy `prototypes/j2`. "Verified" means I ran it; "not verified" says how to check. Paths are repo-relative; `<J2>` is a J2_Prototype clone, `<scratch>` a throwaway folder.

## 0. Verdict (read this first)

1. **`prototypes/j2` is a strict superset of `9200cf6`.** The only things of 9200cf6 it lacks are `runs/` (1,489 files, 114 saved run folders) and `Claude outputs/` (1 file), which were never carried (they are in its `.gitignore`). Evidence: 1.3.
2. **The delta is small in files, large in lines.** 9 changed + 2 new top-level files (`j2.py` +119/-9, `j2_ui.html` +1601/-360, `j2_flow_test.py` +1389/-266), 5 changed generic templates, 79 seed-library files (27 changed, 52 new) and 4 new docs. 9 of the 14 modules `vendor_j2.py` copies, all 20 `agents/` files, the 4 conditions and `artifacts/types.json` are byte-identical.
3. **Most of the engine-side delta is already on J2's own `origin/main` (`dfa44b3`, 12 commits after 9200cf6: library catalog parts 1-5 and the Adaptation Map).** `j2.py`, `j2_agent.py`, `j2_map.py` and all 157 library files are byte-identical there. Sutra-only (S): `j2_artifacts.py` (+298), the Document generic templates, `j2_template_lib.py` (+49/-16), `j2_agent_models.py` and `j2_agent_views.py`, and nearly all of the page (+1397/-467 over J2's main). Table in 1.4.
4. **No prompt text changed** (no role file, condition or prompt constant in `j2.py`). What changed is when and with what data the prompts run: (a) with realization on (Sutra's default) every workflow registered after the first plan is judged again (1 judge call; 2 more, an improvement and a second judgement, when the score is under the 0.80 gate); (b) workflow rows gain `stage_from`, `certainty`, `certainty_from` (and `judge`), which Coordination and Priority prompts embed; (c) three mock replies gain `estimated_resources`; (d) one new prompt exists (`j2_agent.answer`, reachable only through `POST /api/ask`). Section 3.A.
5. **Sutra's own gates notice.** With the new vendored files overlaid on a scratch copy, 14 tests fail that pass on an untouched copy: 2 of 6 prompt goldens, the function-node goldens, the `/api/library` key paths, the seed-library counts, and one chat meta key (`judge`). Everything else I ran behaved as on an untouched copy (a few tests fail identically there in this sandbox, listed in 4.5), including Sutra's 9200cf6-era legacy flow test against the new engine. Section 4.5.
6. **Anchors.** `vendor_j2.py` stops on one anchor: P1 in `j2_artifacts.py` (`    import j2_map` now occurs 3 times, expected 2). The other 52 code anchors match (8 moved by 1 to 110 lines). `port_j2_ui.py` stops on 13 of 29 page anchors (E2, E5, E6a, E7, E13b, E14-E18, E19a-c). Against J2's own `origin/main` the same checks give **0** failing code anchors and **1** failing page anchor (E14). Section 4.
7. **Biggest risks:** the page re-port (new Simple view, icon rail with flyouts, Artifacts tabs, native Run settings, `/library` path logic); the late judge (cost, strict records); `POST /api/ask` cannot run in the API process (it needs the engine's model seam) and must not bypass the per-agent model and effort; two diverging copies of J2 (J2's own repo and `prototypes/j2`). Section 7.
8. **Recommended shape (architect decides):** vendor from one pinned source, and land the engine-side work before the page work (the old ported page keeps working against the new engine: verified with the legacy flow test). Section 7.4.

## 1. Provenance and method

### 1.1 Provenance

| Item | Value | Evidence |
|---|---|---|
| Worktree | branch `feat/sutra-pro-j2-sync-4`, HEAD = `origin/main` = `b5dd56f87b45e6994f906ec2fb051e75efcdadc4` (2026-11-10), working tree clean before this report was added | `git rev-parse HEAD`, `git status` |
| `prototypes/j2` last touch | `00efb179e21cb79fae157a0679e819921ac37726` (2026-11-09) "Document rows: a Map link to the PRD keeps landing on the Documents view" | `git log -1 -- prototypes/j2` |
| `prototypes/j2` first commit | `a57d5556` (2026-11-06) "Add J2 prototype under prototypes/j2": 216 files, +52,657 | `git show --stat a57d5556` |
| `prototypes/j2` history | 37 commits (list in 1.5) | `git log -- prototypes/j2` |
| Tree id of `prototypes/j2` at `origin/main` | `99b6f3a05de78a609b593d81d7fb06b55c32b961` | `git rev-parse origin/main:prototypes/j2` |
| Vendored baseline | J2_Prototype `9200cf626e5c05032caefda4f96b694284efdc5e` (2026-11-06, PR #31 `template-library-fixes`) | `sutra_app/engine/VENDORED.md`, `scripts/vendor_j2.py` `BASELINE`, `tests/engine/legacy/EXPECTED.json` |
| J2_Prototype local `main` | `9200cf6` | `git branch` in the clone |
| J2_Prototype remote-tracking `origin/main` | `dfa44b3` (2026-11-09, merge of PR #33 `adaptation-map`), 12 commits after 9200cf6. Not re-fetched (no network): **not verified against the live remote; check with `git fetch --dry-run` in the clone** | `git log main..origin/main` |
| J2 branches still unmerged | `build-on-run` (1 commit ahead: the design doc `80f8704`), `backend-builder` (5 ahead, tip `7cce55c`) | `git rev-list --count origin/main..origin/<branch>` |
| State of the copy at import | `a57d5556` was 33aeeda-era `j2.py` (+11/-43 against 9200cf6) plus the unmerged Simple-view redesign page (`j2_ui.html` +848/-226 against 9200cf6). Four ports (2026-11-04: `1dcacdb4`, `5ab8d1ac`, `6de5bfeb`, `53f2e160`) brought the J2 code files up to 9200cf6 | `git diff --no-index --numstat` of the extractions |

### 1.2 How I compared

```
git -C <J2> archive 9200cf6      | tar -x -C <scratch>/j2-9200cf6        # vendored baseline
git -C <J2> archive origin/main  | tar -x -C <scratch>/j2-origin-main    # J2's own main, for 1.4
git archive a57d5556 prototypes/j2 | tar -x --strip-components=2 -C <scratch>/j2-a57d5556   # the import state
sha256 of every file in both trees; git diff --no-index --numstat per changed file
git log --format=@@%h --name-only --no-renames -- prototypes/j2          # commits per file
ast walk of every .py: functions and classes only in one tree
python3 -I anchor_check.py ...   # throwaway: every Edit of vendor_j2 and port_j2_ui against the new source, raw and in order
scripts/vendor_j2.py --source <folder> --commit <id> --check ; scripts/port_j2_ui.py --j2 <folder> --check   # the real scripts: same answers
trial: copy sutra-pro to <scratch>, overlay the files vendor_j2 builds from the new source, run Sutra's own tests there; the same tests on an untouched copy are the control
```

The repository, the J2_Prototype clone and `prototypes/j2` were never written (`git status` clean afterwards; the J2_Prototype clone had one modified `.gitignore` before I started).

### 1.3 Superset evidence (all verified)

| Check | Result |
|---|---|
| Functions and classes defined in any `.py` of 9200cf6 and missing from `prototypes/j2` | none (gained: 3 in `j2.py`, 7 in `j2_agent.py`, 11 in `j2_artifacts.py`, 3 in `j2_map.py`, 12 in `j2_template_lib.py`, 2 in `j2_server.py`, 16 in `j2_flow_test.py`, plus 2 new modules) |
| Byte-identical to 9200cf6 | 9 of 14 vendored modules (`j2_artifact_models`, `j2_board`, `j2_change`, `j2_check`, `j2_realization`, `j2_rules`, `j2_schema`, `j2_send`, `j2_story`), `llm.py`, `j2_graph_layout.js`, `README.md`, `SETUP.md`, all `docs/` that existed, `agents/`, `conditions/`, `artifacts/types.json`, `scenarios/`, `vendor/` |
| Lines added by 33aeeda..9200cf6 in `j2.py`, `j2_template_lib.py`, `j2_artifact_models.py`, `llm.py`, `j2_flow_test.py` that are absent from the copy | 0 of 35, 30, 18, 9 and 116 |
| parse_decision negation (`NEGATION`, `affirmed`, `OPTION_WORDS`) | present, same counts (2, 1, 3 in `j2.py`) |
| Router overrule of a weak extend (`EXTEND_MIN`) | present, 5 occurrences in `j2_template_lib.py` in both trees |
| First page builder schema fix (`inline_definitions`) and refused-schema report | `j2_artifact_models.py` and `llm.py` byte-identical |
| Review tests (`2a758d4`) | 24 of 24 added lines present in `j2_flow_test.py` |
| Behaviour: Sutra's legacy flow test (a port of the 9200cf6 flow test) against the new vendored engine | passes (`SUTRA_SLOW=1`, `tests/engine/test_engine_legacy.py::test_flow_script_fast_passes`); `change_test` and `realization_test` pass too |
| J2's own new test blocks on the new code (scratch copy of `prototypes/j2`) | `plan_map_view`, `late_judge_run`, `artifacts_groups`, `run_settings`, `chat_panel`, `function_chat`, `view_kept`, `simple_redesign` pass (parts that need Chrome or `runs/` are skipped by J2 itself); `agent_views` skipped (no saved run) |
| Lost | `runs/` and `Claude outputs/`. Side effect: J2's whole `--fast` flow test cannot finish inside `prototypes/j2`: it fails at `j2_flow_test.py:10158` (`assert len(cross_runs) == 4, "both saved runs are in runs/"`) and says "replay test skipped: runs/j2-20261015-114723 not found". Sutra's legacy port already guards the blocks that need saved runs (`SUTRA_J2_CHECKOUT`) |

### 1.4 The delta split: U (also on J2's `origin/main`) and S (sutra copy only)

Lines are added/removed. Verified by extracting `origin/main` and diffing both ways.

| File | 9200cf6 to J2 `origin/main` (U) | J2 `origin/main` to `prototypes/j2` (S) |
|---|---|---|
| `j2.py` | +119/-9 | identical |
| `j2_agent.py` | +180/-0 | identical |
| `j2_map.py` | +62/-0 | identical |
| `library/` (157 files) | 27 changed, 52 new | identical |
| `j2_template_lib.py` | +213/-3 (catalog, provenance) | +49/-16 (Document generic templates) |
| `templates/{prd,hld,lld}/generic.json` | unchanged | +256, +265, +275 (the `Document` entry) |
| `templates/{design,website}/generic.json` | unchanged | +1/-1 each (the `from` string) |
| `j2_artifacts.py` | +1/-1 | +298/-1 (groups, views, Documents group) |
| `j2_server.py` | +18/-2 (`/library`, `/api/plan-map`, `/api/activity`, `/api/catalog`, `POST /api/ask`) | +48 (`/api/artifacts/groups`, `/api/runlist`, `/api/changes`) |
| `j2_ui.html` | +347/-36 (Map tab, catalog page, template lines, function feed and question box) | +1397/-467 (Simple-view redesign, icon rail, chat panel, Artifacts groups and tabs, native Run settings, Documents group) |
| `j2_ui_render.js` | +3/-1 | +5/-4 |
| `j2_flow_test.py` | +119/-7 | +1275/-264 |
| `j2_agent_models.py`, `j2_agent_views.py` | absent | new (237 and 432 lines) |
| 4 docs | absent | new (`agent-views-j2-proposal.md`, `build-on-run-design.md`, two `docs/mocks/*.html`) |

Consequence: the engine files `j2.py`, `j2_agent.py`, `j2_map.py` and the seed library are doubly sourced and identical. The three S engine files (`j2_artifacts.py`, `j2_template_lib.py`, generic templates) matter only for the Artifacts groups and the Document-level templates.

### 1.5 The 37 commits of `prototypes/j2` by theme

Hashes are the sutra repository's (J2's `origin/main` carries the U commits under other hashes: same titles).

| Theme | Part | Commits |
|---|---|---|
| Import | base | `a57d5556` |
| Ports of J2 PR #31 work | U (to 9200cf6) | `1dcacdb4` router overrule, `5ab8d1ac` parse_decision negation, `6de5bfeb` page-builder schema and refused-schema report, `53f2e160` review tests |
| Adaptation Map data, feed, question box, late judge | U | `2b0986e0` (J2: `0a71ae1`) |
| Library catalog parts 1-5 | U | `e1e56515`, `75cb83a9` (part 1), `052454e6`, `f0271437` (part 2), `21ff3d4f` (part 3), `6c3e6423` (part 4), `457b8524` (part 5) |
| Map in the current UI, chat panel, every function | S | `27cc4ec7`, `85c55600`, `83979d52` |
| Run settings (native) | S | `e7800503` |
| Artifacts four groups, header, Summary/Agent/Human tabs | S | `c350a73f`, `8eea1b92`, `0500d42b`, `e9b00d08` (mock page only), `6419e7f2` |
| Template viewer tabs, rail Library flyout | S | `b77f8c20`, `9cb04581` |
| Agent-readable views 1-4, Documents group, audit rows | S | `c36aa772`, `765c9c9b`, `39eb5045`, `e5c4be77`, `1a74691b`, `6aaa178a`, `8146aae6`, `0de27da0`, `00efb179` |
| Test follow-ups | S | `f8d5223d`, `c6d68959` |
| Build-on-run design doc and the merge that brought it | S (J2 branch `build-on-run`, unmerged) | `21686376`, `6231fa25` |

## 2. Inventory of every file under `prototypes/j2` (274 files)

Status against 9200cf6: identical 175, changed 41, new 58. Not in the copy: 1,490 files (`runs/` 1,489, `Claude outputs/` 1). 9200cf6 had 1,706 files.

### 2.1 Top-level files (39: 28 identical, 9 changed, 2 new)

"J2 main" = same / differs / absent against J2 `origin/main` `dfa44b3`. "Vendored" = the list in `scripts/vendor_j2.py` or `scripts/port_j2_ui.py`.

| File | Status, lines | J2 main | Vendored today | Sutra-owned counterpart |
|---|---|---|---|---|
| `j2.py` | changed +119/-9 | same | CODE | `sutra_app/engine/j2.py` (P1-P5, P7-P9, P11, P13, P14) |
| `j2_agent.py` | changed +180/-0 | same | CODE (no patch) | `engine/j2_agent.py`; `views.agent` |
| `j2_agent_models.py` | new +237 | absent | no | none |
| `j2_agent_views.py` | new +432 | absent | no | none |
| `j2_artifact_models.py` | identical | same | CODE (P1) | `engine/j2_artifact_models.py` |
| `j2_artifacts.py` | changed +297/-0 | differs | CODE (P1) | `engine/j2_artifacts.py`; `views.artifacts`, `artifacts_tree`, `code`, `artifact` |
| `j2_board.py` | identical | same | CODE | `engine/j2_board.py` |
| `j2_change.py` | identical | same | CODE (P1) | `engine/j2_change.py` |
| `j2_check.py` | identical | same | CODE (P12) | `engine/j2_check.py` |
| `j2_map.py` | changed +62/-0 | same | CODE (P1) | `engine/j2_map.py`; `views.map`, `plan` |
| `j2_realization.py` | identical | same | CODE (P1, P2, P7) | `engine/j2_realization.py` |
| `j2_rules.py` | identical | same | CODE | `engine/j2_rules.py` |
| `j2_schema.py` | identical | same | CODE | `engine/j2_schema.py` |
| `j2_send.py` | identical | same | CODE | `engine/j2_send.py` |
| `j2_story.py` | identical | same | CODE (P1) | `engine/j2_story.py` |
| `j2_template_lib.py` | changed +262/-19 | differs | CODE (P1, P10, P12) | `engine/j2_template_lib.py`; `views.library`, `library_item`, `run_templates` |
| `j2_server.py` | changed +66/-2 | differs | no | `engine/views.py`, `engine/api/*`, `engine/j2_server.py` (stdlib adapter) |
| `j2_ui.html` | changed +1601/-360 | differs | `port_j2_ui.py` J2_PAGE | `sutra_app/ui/pages/j2_ui.html`, `static/css/j2.css` (E1-E19) |
| `j2_ui_render.js` | changed +6/-3 | differs | `port_j2_ui.py` J2_RENDER | `ui/pages/j2_ui_render.js` (H1-H3) |
| `j2_graph_layout.js` | identical | same | `port_j2_ui.py` J2_LAYOUT | `ui/pages/j2_graph_layout.js` (H1) |
| `j2_flow_test.py` | changed +1389/-266 | differs | legacy port | `tests/engine/legacy/j2_flow_test.py` |
| `change_test.py`, `realization_test.py`, `j2_replay_size.py` | identical | same | legacy port | `tests/engine/legacy/*` |
| `llm.py` | identical | same | no | `engine/llm.py` (Sutra's seam over `ModelPort`) |
| `README.md`, `SETUP.md` | identical | same | REF_TOP | `docs/reference/j2/` |
| `requirements.txt`, `run_checks.sh`, `.env.example`, `.gitignore`, `screenshot.png` | identical | same | no | `pyproject.toml`, `scripts/engine_gate.sh`, `docs/ENVIRONMENT.md` |
| `server.py`, `studio.py`, `ui.html`, `mock_site.py` | identical | same | no (older studio) | none |
| `negotiate.py`, `negotiate_server.py`, `negotiate_ui.html` | identical | same | no (budget-conflict demo) | none |

Commits per changed file (since the import `a57d5556`):

| File | Commits |
|---|---|
| `j2.py` | `2b0986e0`, `1dcacdb4`, `5ab8d1ac` |
| `j2_agent.py`, `j2_map.py` | `2b0986e0` |
| `j2_artifacts.py` | `c350a73f`, `8eea1b92`, `6419e7f2`, `765c9c9b`, `39eb5045`, `0de27da0`, `00efb179` |
| `j2_template_lib.py` | `1dcacdb4`, `e1e56515`, `75cb83a9`, `e5c4be77` |
| `j2_server.py` | `e7800503`, `c350a73f`, `2b0986e0`, `052454e6`, `457b8524` |
| `j2_ui.html` | `e7800503`, `c350a73f`, `8eea1b92`, `0500d42b`, `6419e7f2`, `2b0986e0`, `27cc4ec7`, `85c55600`, `052454e6`, `f0271437`, `21ff3d4f`, `6c3e6423`, `457b8524`, `83979d52`, `b77f8c20`, `9cb04581`, `c6d68959`, `8146aae6` |
| `j2_ui_render.js` | `2b0986e0`, `83979d52` |
| `j2_flow_test.py` | `e7800503`, `c350a73f`, `8eea1b92`, `0500d42b`, `6419e7f2`, `2b0986e0`, `27cc4ec7`, `85c55600`, `6de5bfeb`, `1dcacdb4`, `5ab8d1ac`, `53f2e160`, `83979d52`, `b77f8c20`, `f8d5223d`, `c6d68959`, `765c9c9b`, `39eb5045`, `1a74691b`, `6aaa178a`, `0de27da0`, `00efb179` |
| `j2_agent_models.py` | `c36aa772` |
| `j2_agent_views.py` | `c36aa772`, `765c9c9b`, `39eb5045` |
| `library/index.json`, 26 `meta.json` | `e1e56515`, `75cb83a9` |
| `templates/*/generic.json` | `e5c4be77` |

### 2.2 Folders

| Folder | Files | Identical / changed / new | Vendored today | Note |
|---|---|---|---|---|
| `agents/` | 20 | 20 / 0 / 0 | 10 role files (`agents/j2/{team,identity,adaptation,priority,coordination,audit,builder,confidence-judge}.md`, `rates.json`, `stages.json`) to `engine/agents/j2/` | not vendored: `agents/j2/_placeholders/` (6) and the older studio agents (4) |
| `artifacts/` | 1 (`types.json`) | 1 / 0 / 0 | yes, `engine/artifacts/types.json` | no type for the project report (see 6.7) |
| `conditions/` | 4 | 4 / 0 / 0 | yes, `engine/conditions/` | |
| `docs/` | 43 | 39 / 0 / 4 | 8 reference docs and `docs/superpowers/` (2) to `docs/reference/j2/` (all identical) | new, not vendored: `agent-views-j2-proposal.md` (40 lines), `build-on-run-design.md` (552 lines, design only: no code mentions it), `mocks/j2-artifacts-mock.html` (153 lines, 289 KB), `mocks/j2-run-settings-mock.html` (121 lines) |
| `library/` | 157 | 78 / 27 / 52 | whole tree to `engine/seed/library/` | detail in 2.3 |
| `scenarios/` | 2 | 2 / 0 / 0 | no | |
| `templates/` | 5 (`{design,hld,lld,prd,website}/generic.json`) | 0 / 5 / 0 | yes, `engine/templates/` | `Document` entry in prd, hld, lld (3.D) |
| `vendor/` | 3 (`d3.min.js`, `d3-LICENSE`, `README.md`) | 3 / 0 / 0 | no in the engine; `port_j2_ui.py` J2_VENDOR to `ui/static/vendor/` | |
| `runs/` (J2 repo only) | 1,489 in 114 folders | removed | no | |
| `Claude outputs/` (J2 repo only) | 1 | removed | no | |

### 2.3 Library detail (seed for Sutra)

| Item | Count | Detail |
|---|---|---|
| Changed | 27 | `library/index.json` (54,079 to 168,048 bytes, +4161/-520: new `runs` section of 8 rows and provenance on each version) and 26 `v1/meta.json` (+13 to +37, -1 each: `made_by.date`, `business`, `mock`, `collected_from`) |
| New | 52 | 13 version folders of 4 files (`meta.json`, `model.py`, `schema.json`, `spec.json`): 8 folders of 6 new templates (`prd/goals/still-point-yoga-prd-goals` v1 v2; `prd/out-of-scope/still-point-yoga-prd-out-of-scope` v1 v2; `prd/problem/still-point-yoga-problem-users-and-goals` v1; `prd/success-metrics/still-point-yoga-prd-success-metrics` v1; `.../still-point-yoga-prd-success-metrics-and-out-of-scope` v1; `prd/users/still-point-yoga-prd-users` v1) and 5 folders of 4 existing templates (`hld/components` v2, `lld/pages-and-sections` v2, `prd/problem` v2, `prd/requirements` v2 v3) |
| Result | 32 templates, 39 versions (baseline 26 and 26) | all 26 baseline versions are now flagged `mock: true`, the 13 new ones `mock: false`; businesses: Still Point Yoga 35 versions, Thread (the boutique brief) 4; `runs` rows: 8 (6 mock, 2 live, model "sonnet") |

## 3. Behaviour changes by theme

### 3.A Late judge and stage/zone placement (`j2.py`, `2b0986e0`; **U**)

| Aspect | Change |
|---|---|
| New | `J2Run.PLAN_NAME` (regex), `_plan_name`, `_place_wf(wf, row, src)`, `_late_judge(batch)` |
| `_register` | `batch = self._late_judge(norm(agreed))`; a new validator refusal when `w["judge"]["ready"] is False` ("the judge scored it X, below the 0.80 gate (weakest: ...)"), placed after the unknown rate-card parts check and before "its cost is 0"; the old stage-only block (`if self.real_summary:`) is replaced by `self._place_wf(wf, w, src)` when `self.real is not None` |
| Workflow rows | gain `stage_from`, `certainty`, `certainty_from` (verified: all 8 workflows of the Brew Lab realization run; `stage` values unchanged) and, for a late row, `judge` = `{score, weakest, missing[<=3], rounds, ready, zone, stage, note}` |
| `realization.json` | gains `late`: `[{workflow, revises, t, cycle, calls, seconds, score, weakest, missing, rounds, ready, zone, stage, note}]` |
| Chat and events | system lines "Judge: NAME scored 0.95 [after one improvement][, below the 0.80 gate (weakest: ...) or , at or above the 0.80 gate]; zone Z, stage S." with meta key `judge=NAME`, or "Judge: NAME was not scored (...); registered as proposed."; event `adaptation/late_judge` |
| Model calls | only when realization is on, the plan is a dict and no change plan is running; rows the plan already judged (name in the plan, no `revises`) are skipped; a resent row is judged once (`_late_seen`). Per late workflow: `j2_change.judged` (1 judge call, `Session.ask` max_tokens 16000, effort high, JSON; a retry when the reply lacks the workflow); under `j2_realization.THRESHOLD` (0.80) also `j2_change.improve` (1) and a second `judged` (1). `self.calls += s.calls`. Tagged by P7 as role judge/planner, purpose judge/plan, function = the turn's function (`_register` runs in `_turn_priority`, j2.py:6600, and in the change relay: `_relay_doc_revise`, j2.py:5894, and `_relay_revise`, j2.py:5964; the relay needs `J2_CHANGE`, which is off by default in Sutra) |
| When it fires | verified: a forced audit failure alone (`J2_FORCE_AUDIT_FAIL=1`, `J2_CHANGE` off, `J2_FIXES` 0 or 1) gives 1 late entry; plain mock runs give 0. In live runs: every fix after an audit finding, replacement, change revision or relay round |
| Mock-only | `"estimated_resources": {"money": 10}` added to three mock proposal rows (the "Visiting hours" revise, "Cover item N", "Fix item N"); `workflows[W-5].estimate` 0 to 10 in `brewlab_fixes0` |
| Prompts | none changed; embedded data grows: golden `realization` call 5 (Coordination) 26,459 to 27,611 characters; golden `brewlab_fixes0` call 22 (Priority) 19,523 to 19,562 (mock only) |
| Settings, env | none (no new `J2_*`); `EngineSettings.realization` defaults to `True`, so the late judge is on by default in Sutra |

### 3.B Adaptation Map data, function feed and question (`j2_map.py`, `j2_agent.py`; **U**)

| Item | What |
|---|---|
| `j2_map.plan_map(d)` | `plan-map/1` from `realization.json`, `workflows.json`, `change.json`, `goal.json`: `{found: false}` or `{found, goal, statement, zone, confidence, threshold, stages[{id, thinking, goal, zone, confidence, workflows[]}], workflows[{id, name, stage, zone, zone_from, score, weakest, rounds, cycle, status, cost, revises, purpose, change_start, revisions, read}], unplaced[], changes[{id, request, phase, closed}]}` |
| `j2_agent.activity(d, who)` | `activity/1`: `{schema, who, persona, found, names, events[{kind: msg/call/plan/wf/judge/revise/change, t, ...}]}` from `chat.jsonl`, `calls.jsonl`, `realization.json` (including `late`), `change.json`. Pure file reads |
| `j2_agent.answer(d, who, question, ask=None)` | a question to one function, answered from its records only: without `ask` (J2 passes `None` in mock mode) the lines of the records that share the question's words; with `ask` one model call `ask(system, user, records_only, max_tokens=700, effort="low")`. **New prompt** (system): "You are NAME (WHO), one function of the J2 team that built this run. The Requester asks you a question about what you did. Answer only from the records below ... Plain words, short sentences, no headings ..."; user: `YOUR RECORDS`, the lines (last 60,000 characters), `QUESTION`, the text. Result `{who, answer, from: "records" or "model"}`. Questions and answers are not saved (the page keeps them in memory) |
| Verified | all three run inside the vendored package on a real mock run folder (trial); `activity` lists the late judge as events; `answer` works with `ask=None` and with a stub `ask` |

### 3.C Artifacts groups, views, Documents group, agent-readable modules (`j2_artifacts.py`, new modules; **S**)

| Item | What |
|---|---|
| `j2_artifacts.groups(d, m)` | `artifacts-groups/1`, five groups: plan (Charter, Realization plan, Workflows), guides, site (sections and style guide), **documents** (PRD, HLD, LLD), records (receipts, audits, one row per audit `A-n`, conditions, shots); each row has `id, kind, name, file, maker, nodes, views` plus kind-specific keys; `views = {summary: true, agent: {format, file, schema, model, valid} or null, human: {format, file} or null}`. 89 key paths on a mock website run. Calls `j2_map.build`, and has a **third lazy `import j2_map`** (the P1 anchor failure) |
| `agent_view`, `human_view`, `views` | the three Artifacts tabs. Agent-readable looks for a Pydantic JSON beside the file (`prd.md` to `prd.json`), `agent/<record>.json`, `agent/audits/A-n.json`, `site/sections/<id>.json`, `design.json`, else the row's own JSON, else raw text |
| `j2_agent_models.py` | `agent-views/1`: closed Pydantic models (`Guide` and kinds, `Charter`, `WorkflowPlan`, `Receipts`, `Conditions`, `AuditResult`), `envelope`, `validate` |
| `j2_agent_views.py` | CLI only: `python3 j2_agent_views.py build <run_dir> or --all [--runs DIR]`. **Nothing in J2 calls it during a run**: `docs/agent-views-j2-proposal.md` is a proposal (`J2_AGENT_VIEWS=1`, four hook points in `j2.py`), not code. It imports `j2_agent_models`, `j2_artifact_models`, `j2_template_lib` by flat name and inserts its own folder in `sys.path` |
| Verified | the CLI on a scratch copy of a Sutra-engine mock run wrote 15 JSON files (14 valid; the style guide "not recorded"); the vendored `groups()` reads them (formats `json`, schemas `agent-views/1` and `artifact-schema/1`, `valid: true`) and `served()` serves `agent/*.json`. Without the CLI the Agent-readable tab shows only the run's own JSON (`goal.json`, `realization.json`, `workflows.json`, `audits.json`, `style.json`) with `schema` and `valid` null |
| Gap seen | a Project work run (`project.md`) appears in no group, and in no group of the old tree either (`artifacts/types.json` has no type for it; `TYPES_PATH` is a constant). Verified with a mock project run |

### 3.D Template library (`j2_template_lib.py`, `templates/`, `library/`; catalog **U**, Document templates **S**)

| Item | What |
|---|---|
| Document generic templates | `DOCUMENT = "Document"`, `document_model`, `document_render`, `generic_sections`; `generic`, `generic_file`, `library_view`, `_library_view_of`, `codegen_generic` changed. `templates/{prd,hld,lld}/generic.json` gain a last entry (`PRD/1 · Document` etc., `section: "Document"`, with a `render` block of 6 sections for prd); `design` and `website` change only the `from` string. `/api/library` groups for prd, hld, lld gain the `Document` section; `/api/library/<a>/Document/generic/v1` gains `files["render.md"]` and `readable.render` (additive) |
| Catalog | `collect(runs_dir, runs=None)` (CLI `python3 j2_template_lib.py --collect [--runs DIR]`) gives every run's templates to `library/` (same spec sha is one version; a taken number with another sha is renumbered, with `renumbered_from`); helpers `run_facts`, `run_date`, `_decision_files`, `_use`, `_add_use`, `_provenance`, `_place`; `catalog_view()` returns `{schema, dir, groups, runs}` (verified: 101 key paths on the new seed). **`collect` and `_place` write `index.json` and version folders with no lock**: P10 wraps only `store` and `mark_used` |
| Runtime store | unchanged: `store`, `mark_used`, `_route_template` are not in the diff, so P10 and P12 anchors still match |
| Seed | 2.3. `host/loop.py _seed_library` copies the seed once (when `<data>/library` does not exist); `ops/doctor.py sync_seed_library` adds templates by `artifact/section/slug` only (so the 4 existing templates' new versions never reach an existing install) |

### 3.E HTTP routes (J2 `j2_server.py` versus Sutra `engine/api/*`)

| Route | Part | J2 handler | JSON shape | Sutra today | Needed |
|---|---|---|---|---|---|
| `GET /api/plan-map?run=` | U | `j2_map.plan_map(d)` | 3.B | none | view + route + stdlib row + `J2_PATHS` |
| `GET /api/activity?who=&run=` | U | `j2_agent.activity(d, who)` | 3.B | none | same |
| `POST /api/ask` `{who, q, run}` | U | `j2_agent.answer(..., ask=None if llm.MOCK else llm.ask)`; 400 `{"error": "not a function"}` unless `who` is one of the six `FUNCS` | `{who, answer, from}` | none | **a port, not a view**: 6.1 |
| `GET /api/catalog` | U | `j2_template_lib.catalog_view()` | 3.D | none | view + route + stdlib row + `J2_PATHS` |
| `GET /library` | U | serves `j2_ui.html` | HTML | none: pages are `/`, `/console`, `/d/{dept}/` (`ui/routes.py`) | page route + port edits: 6.2 |
| `GET /api/artifacts/groups?run=` | S | `j2_artifacts.groups(d, j2_map.build(d, live))` | 3.C | none | view like `artifacts_tree` (needs `LIVE_VIEWS`) |
| `GET /api/runlist`, `GET /api/changes` | S | `j2_server.run_list`, inline | same as P13 (`tests/engine/golden/api_shapes.json` key `patched`) | `views.runlist`, `changes` through P13 | none (same logic; 6.3) |
| `GET /api/library` | U and S | `library_view()` | version rows gain `business{name,type}`, `made_by.date`, `mock`, `collected_from{run,where}`, `renumbered_from`; Document sections | `views.library` | golden: 4.5 |
| `GET /api/library/<a>/<s>/<slug>/v<N>` | S | | Document generic: `render.md`, `readable.render` | `views.library_item` | additive |
| `GET /api/artifacts`, `POST /api/output` | unchanged routes | | | `views.artifacts`, `views.output` | the page no longer calls either |

### 3.F Page (`j2_ui.html` 403,068 to 585,080 bytes; `j2_ui_render.js`)

The page is regenerated by `scripts/port_j2_ui.py`; the question is which new feature needs what.

| Feature | Part | Routes | Client state | Note for the port |
|---|---|---|---|---|
| Simple view redesign: bot landing `sland`, greeting `sgreet`, chips, team card, build journey `sJourney*`, finish card, device switch, "Show how it was built" | S | `/api/state`, `/api/say`, `/api/changes`, `/site/<v>` | `SJ`; `j2view`, `j2theme` | removes `outsel`, `sotype`, `stitle`, `to-simple`, `to-detail`, `runsel`, `sask-change`; `sframe` has no `src` in the markup (script sets it, j2_ui.html:1761) |
| Icon rail with flyouts (`#rail`, `RAILITEMS`, `railOpen`, `railStatus`, `rfly`, `.rpool`) | S | none | `RAIL`; `j2railopen` | replaces the rail Sutra's E7 patches |
| Chat panel `#chatp` and button `#chatfab`; function mode with feed and question box | S (panel), U (Adaptation feed and question) | `/api/state`, `/api/say`, `/api/activity`, `POST /api/ask` | `CHAT`, `FEED`, `QA`, `CHATFN`, `ASKMODE`; `j2chat` | J2 also has `chatFollow` and `askFn` in its own main; the every-function scope and the panel layout are S: not verified in detail (diff the two `chatFollow` bodies) |
| Adaptation > Map (`planmap` tab) | U | `/api/plan-map` | `PLANMAP`, `PMSEL` | |
| Artifacts: five groups, list and details, tabs Summary / Agent-readable / Human-readable | S | `/api/artifacts/groups`, `/api/artifact`, `/api/code` | `ARTS`, `ARTOPEN` | `/api/artifacts` is no longer called |
| Template viewer tabs, template line on workflow rows and atom cards, provenance | U (line, provenance), S (three tabs) | `/api/library`, `/api/library/...`, `/api/run-templates` | `TPLTABS`, `LIB` | |
| Shared library page `/library` (by run, by artifact, search, hide mock) | U | `/api/catalog`, `/api/library/...` | `CAT`; URL `view`, `business`, `q`, `mock`, `open` | tests `location.pathname === "/library"`; hard-codes `/library` in 3 static links, 2 script assignments and `data-catgo` |
| Run settings: Appearance cards, searchable run list, 20 at a time | S | `/api/runlist` | `RUNS`; URL `run` | native now: Sutra's E14-E18 are redundant |
| Harness | S | | | `j2_ui_render.js` also prints `finish`, `journey`, `journeyhtml`, `sframe`, `needids`; H1-H3 still match |

Browser state added: `j2chat` (and a per-run key `CHAT.key`); `j2bar` dropped; URL parameters `business`, `mock`, `open`, `q`, `view` added. Still none of `EventSource`, `XMLHttpRequest`, `eval`, `new Function`, `document.cookie`, `setInterval`; the one external reference is the fonts link that E1 removes. **Motion:** the page now has 40 `@keyframes`, 71 `animation:` and 43 `infinite` (baseline 3, 8, 4); all keyframes animate only transform, opacity or dash offset, and 8 `prefers-reduced-motion` blocks exist. D122's probe has not been run on it (not verified: `tests/ui/perf/fluid_probe.js`).

### 3.G Prompts, conditions, types, templates, flags, files (summary)

| Material | Changed? |
|---|---|
| Role files `agents/j2/*.md` (8) and `rates.json`, `stages.json` | no (byte-identical) |
| Conditions `conditions/*.json`, `artifacts/types.json` | no |
| Prompt constants in `j2.py`, `j2_realization.py`, `j2_change.py` | no (the last two are identical files) |
| Prompts as data | yes: workflow rows embedded in Coordination and Priority prompts; mock replies |
| New prompt | `j2_agent.answer` only |
| Generic templates | yes: Document entries (3.D) |
| Seed library | yes: 79 files |
| Env flags and `EngineSettings` | none new (45 `os.getenv` names in both trees; `J2_RUNS_DIR` is also read by the non-vendored `j2_agent_views.py`); `.env.example` identical; `docs/ENVIRONMENT.md` and `sutra_app/engine/spec.py` need nothing |
| New run-folder files written by a live run | none; changes to existing files: `realization.json` `late`, `workflows.json` rows, `chat.jsonl` meta `judge` |
| New run-folder files written by tools | `j2_agent_views.py build`: `agent/{goal,workflows,receipts,conditions}.json`, `agent/audits/A-n.json`, `artifacts/<name>.json`, `site/sections/<id>.json`, stamped `prd.json` `hld.json` `lld.json` `design.json`; `collect`: `library/` and its index |

### 3.H J2's tests and docs

`j2_flow_test.py` gains 10 blocks (`late_judge_run`, `plan_map_view`, `artifacts_groups`, `agent_views`, `chat_panel`, `function_chat`, `view_kept`, `run_settings`, `simple_redesign`, and the `agent_views_page` helper) and keeps every 9200cf6 function. The flow test calls `/api/ask`, `/api/artifacts/groups`, `/api/runlist` and `/api/changes` over HTTP (so Sutra's stdlib adapter is tested by them); the other new functions are called directly. Docs: `build-on-run-design.md` is design only (no code mentions it); `backend-builder` is still absent (no `j2_backend.py`, `agents/j2/backend.md`, `templates/backend/`, no "backend" in `j2.py` or `rates.json`).

## 4. Anchor check

The throwaway script loaded `scripts/vendor_j2.py` and `scripts/port_j2_ui.py` by path, read the new source as a plain folder, and tested every Edit raw (count in the file) and in order (count after earlier edits, as `apply_edits` does). Sanity: against the 9200cf6 extraction it reports 53 code and 29 page edits all matching and a 152-file build. The two real scripts print the same failures, so the developer can re-run them:

```
scripts/py scripts/vendor_j2.py --source <folder of prototypes/j2> --commit <sha> --check
scripts/py scripts/port_j2_ui.py --j2 <folder of prototypes/j2> --check
```

### 4.1 Code anchors (`J2_EDITS` 34 in `j2.py` + `OTHER_EDITS` 19 = 53)

| Result | Edit | Detail |
|---|---|---|
| **Fails** | P1 `j2_artifacts.py` `"    import j2_map\n"` | expected 2, found 3 (j2_artifacts.py:214, 237, 463; the third is in `groups()`). Real message: `j2_artifacts.py: P1 expects its anchor 2 time(s), found 3`. With `count=3` the build succeeds (204 files, 152 + 52 new seed) |
| Moved, still match | P7 `j2.py` template generator `llm.ask` | j2.py 8411 to 8521 (+110) |
| | P7 `j2.py` reviewer `llm.ask` | 9553 to 9663 (+110) |
| | P1 `j2_template_lib.py` imports | 38 to 39 (`import sys`) |
| | P10 `store`, `mark_used` | 859 to 887, 906 to 934 (+28) |
| | P12 `j2_template_lib.py` x3 | 716 to 744, 779 to 807, 785 to 813 (+28) |
| Unchanged | the other 44 anchors (45 unmoved, one of them the failing P1), including P14, P13, P4, P5, P8, P9, P11 | |

VENDORED.md ranges that change on a re-vendor: P1 (adds `j2_artifacts.py:463`; `j2_template_lib.py:41-42`), P7 (`j2.py:8755-8756`, `9898-9899`), P10 (`j2_template_lib.py:889-925`, `970-977`), P12 (`746-747`, `809`, `815`); P2, P3, P4, P5, P8, P9, P11, P13, P14 keep theirs. The design docs cite `j2.py` lines below 6650 (for example 2360-3892, 5704): those lines did not move.

Modules `vendor_j2.py` does not list that the new code imports: **none**. `j2.py` imports the 11 listed siblings plus `llm` (Sutra's own seam); no vendored module imports `j2_agent_views` or `j2_agent_models`. Residual flat imports after the edits: only the three `j2_map` ones in `j2_artifacts.py` until the count is fixed.

### 4.2 Page anchors (`port_j2_ui.py`: 25 edits on `j2_ui.html`, 3 on the render harness, 1 on the layout harness)

| Edit | Found / expected | What happened in the new page | Handling |
|---|---|---|---|
| E2 | 1 / 2 | `frame` keeps `src="/site/latest"` (line 771); the Simple iframe is `<iframe id="sframe" title="Your result"></iframe>` (line 710) and its `src` is set by script (line 1761, `runQ()` already carries `dept` through E4) | count 1 for `frame`; a new edit gives `sframe` the sandbox |
| E5 | 0 / 1 | `$("stitle")` is gone | retire, or show the team name on the greeting |
| E6a | 0 / 1 | `showTab` rewritten (breadcrumb `crumb`, `chatFollow(name)`, unconditional `railReveal`; lines 2106-2117) | new anchor so `graph` and `orgchart` also hide the title bar |
| E7 | 0 / 1 | the rail is an icon rail (`.ri[data-ri]`, `#rfly`, `.rpool` of tab buttons at line 741; sections from `RAILITEMS`) | place the `railhome` row and the two tab buttons, and give them a flyout section, or `railModel` files them under Settings as "Other" |
| E13b | 3 / 2 | a third "no ranking records" in `railStatus` (line 4518) | count 3; `E13_WORDS` is shared with `tests/ui` parity (`--e13-json`) |
| E14 to E18 | 0 / 1 each | Run settings is native (Appearance cards, searchable runs, `.rsec`); J2's `TABHINT.runsettings` already says "How the app looks, and which run you are looking at." (`TABSUB.runsettings` still says "what to build") | retire the five edits and `RUN_SETTINGS_CSS` (21 of its 27 rule lines are verbatim in J2's `<style>`) |
| E19a to E19c | 0 / 1 each | `OUTS`, `outOptions`, `/api/output` are gone from the page with the Simple start select | owner decision (Q3): re-home the per-request output choice or drop it |
| Pass, moved | E3 427 to 840, E4 467 to 877, E6b 1313 to 2116, E8 381 to 786, E9 423 to 836, E10 2064 to 3135, E11 2357 to 3428, E12 3346 to 4587, E13a 1298 to 2097, E13c, E13d | anchors match; each needs a semantic re-check (not verified in a browser) | |
| Pass | E1 (style block, 96,851 characters), H1 to H3 (render harness), H1 (layout harness) | | |

### 4.3 Against J2's own `origin/main` (`dfa44b3`)

Code anchors 53 of 53 match with the scripts as they are; `vendor_j2.py` builds 204 files unchanged; of the page edits only E14 fails (J2 added an `id="to-library2"` link to the old Run settings block). `vendor_j2.py --check` against the committed tree names 6 non-seed files (`VENDORED.md`, `j2.py`, `j2_agent.py`, `j2_artifacts.py`, `j2_map.py`, `j2_template_lib.py`) and 79 seed files. The generic templates do not change.

### 4.4 Trial: the new vendored files overlaid on a scratch copy of `sutra-pro` (the one P1 count corrected in the script)

Build: 204 files; 38 differ (`VENDORED.md`, `j2.py`, `j2_agent.py`, `j2_artifacts.py`, `j2_map.py`, `j2_template_lib.py`, 5 generic templates, 27 seed) and 52 are new (seed); nothing stale.

| Where it is checked | Same file set, untouched copy (control) | With the overlay |
|---|---|---|
| `tests/engine` (non-legacy), `tests/library`, `tests/ops`, `tests/contracts`, packaging, layout, docs, traceability, ownership | the failures listed under "Pre-existing" | the 14 below, and nothing else |
| `tests/orchestrator`, `tests/integration`, `tests/e2e`, `tests/ui` (port edits, dept page, serve, fake backend) | pre-existing failures only | no new failure |
| Legacy flow test (`SUTRA_SLOW=1`), 9200cf6-era port | passes | passes |

### 4.5 The 14 tests that fail only with the overlay

| Test | Cause |
|---|---|
| `test_engine_vendor.py::test_the_data_files_are_all_there` | pins the seed at 105 files and 26 `meta.json`; now 157 and 39 |
| `test_engine_vendor.py::test_vendored_md_names_the_baseline_commit` | pins `9200cf6`, `33aeeda`, `ce2631f` in the header (my trial header carried a dummy id; the real change is the new source line) |
| `test_engine_prompts.py::test_engine_asks_the_model_what_j2_asked[brewlab_fixes0]` and `[realization]`, and `test_a_changed_role_file_is_seen` (reuses `brewlab_fixes0`) | the two goldens: 3.A. The other four scenarios are equal (`brewlab_fixes1`, `prd`, `design_docs`, `template_library`); the trial engine equals the new J2 run for run in all six |
| `test_engine_fn_golden.py` (3 tests) | `fn_atoms_brewlab.json` prompt digest and `run_events.jsonl` (`tokens_out` 515 to 525) |
| `test_engine_views.py` (live, saved, idle shapes) | `/api/library` gains 24 key paths (46 to 70): 8 provenance (`business`, `business.name`, `business.type`, `collected_from`, `collected_from.run`, `collected_from.where`, `made_by.date`, `mock`) and 16 data-dependent `enums.<Name>` map keys of the new templates (`enums.Goal.id`, `enums.address`, ...) |
| `test_lib_records.py::test_every_meta_key_j2_attaches_to_a_message_is_in_message_meta` | `{'judge'}` is the one meta key `MessageMeta` does not know (`sutra_app/library/chat.py`; the test scans `j2.py` itself) |
| `test_doctor.py::test_the_seed_library_is_checked_and_synced_without_overwriting`, `test_cli.py::test_config_sync_library_adds_what_is_missing_and_is_idempotent` | the seed has 32 template keys, not 26 |

The same 14 fail when only J2's `origin/main` is vendored (verified), so none of them comes from the S files.

Pre-existing in this environment (fail identically on the untouched copy): `tests/ops/test_cli.py` (3: stop, slow server, real server), `tests/ops/test_lock.py` (1), `tests/orchestrator/test_startup.py` (2), `tests/ui/test_fake_backend.py::test_screenshots_are_never_committed` (the scratch copy is not a git repository); and one order-dependent registry test when `test_lib_records.py` runs alone. Not run: node tests (`tests/ui/js`), browser tests, `tests/connectors`, `tests/release`, live runs.

Strict records (verified with a forced audit failure, realization on): `gate_record` in `strict` mode rejects `realization.json` with "late: Extra inputs are not permitted" (`RealizationDoc` in `sutra_app/library/wire.py` is closed). In the default `log` mode it is one `record.warning` trace line per save. The chat line with meta `judge` has the same fate through `MessageMeta`. Workflow rows with the new keys pass: `registered_from_j2` copies named keys only (a pre-existing `version` complaint on mock rows is the same with and without the sync).

## 5. Sutra-side impact

### 5.1 What must change, by J2 change

| J2 change | Sutra files | What |
|---|---|---|
| Source and baseline | `scripts/vendor_j2.py` | `BASELINE`; the static header text in `render_vendored_md` ("main on 2026-11-06, PR #31 ..."); P1 `j2_artifacts.py` `count=3`; P13 wording if it stays; docstring "14 code modules". No other patch changes. Run it on a `git archive` extraction with `--source <folder> --commit <sha>` |
| Regenerated | `sutra_app/engine/VENDORED.md`, the 5 changed modules, 5 generic templates, 79 seed files | by the script (`--check` must pass) |
| Late judge | `sutra_app/library/chat.py` (`MessageMeta`: `judge`), `sutra_app/library/wire.py` (`RealizationDoc`: `late` and a row class), `docs/schemas/realization.v1.json` (export; `tests/library/test_lib_schema_drift.py` should catch it: not verified) | additive fields; no vendored patch |
| New read routes | `engine/views.py` (4 views, `HANDLER_COUNT` 30 to 35, `LIVE_VIEWS` + `artifacts_groups`), `engine/api/run_views.py`, `engine/api/library.py`, `engine/j2_server.py` (`route()` table), `ui/static/js/sutra_ctx.js` (`J2_EXACT` 23 to 28: `/api/plan-map`, `/api/activity`, `/api/catalog`, `/api/artifacts/groups`, `/api/ask`) | each view is 2 to 4 lines on the pattern of `artifacts_tree`, `plan`, `agent`, `library` |
| `POST /api/ask` | `engine/api/ports.py` (a new `EngineServices` method), `engine/api/commands.py` or a new route module, `sutra_app/orchestrator/services.py`, `connectors/router.py` (`PICK_PURPOSES`) | 6.1 |
| `/library` page | `sutra_app/ui/routes.py` (a page route), `scripts/port_j2_ui.py` (path edits), `sutra_ctx.js` | 6.2 |
| Run settings native | `scripts/port_j2_ui.py` (drop E14-E18, `RUN_SETTINGS_CSS`, the `run-settings.css` link in `E1_NEW`), delete `sutra_app/ui/static/css/run-settings.css` | 6.3 |
| Page | `scripts/port_j2_ui.py`, `sutra_app/ui/pages/*`, `static/css/j2.css`, `dept_ext.js`, `node_panel.js` (rail and panel coexistence) | 4.2 |
| Seed growth | `tests/engine/test_engine_vendor.py` (157, 39), `tests/ops/test_doctor.py` and `test_cli.py` (32), `sutra_app/ops/doctor.py` `sync_seed_library` (add missing versions, optional), `sutra_app/engine/host/loop.py` (unchanged) | |
| Legacy suites | `tests/engine/legacy/j2_flow_test.py`, `EXPECTED.json` (`j2_commit`, minimums) | Sutra's 90 hunks of edits against the 9200cf6 copy: 83 re-apply to the new file, 7 are rejected, all in blocks that read the page or `j2_server` (`get("/")` to `served_page(get)` twice, one of them around the old `outsel` assertion that J2 has dropped; `cwd=HERE`; `page_file("vendor")` twice; the `import j2_server` header; `page_file("j2_ui.html")`): merge by hand. `change_test.py`, `realization_test.py`, `j2_replay_size.py` need no change |
| Docs | `docs/design/j2-sync-4.md` (new), `docs/DECISIONS.md` (next id D135), `docs/design/j2-sync.md` (a line in "Later syncs"), `docs/design/engine.md` (7.1 table, patch table), `docs/design/ui.md` (edit table), `docs/design/library.md`, `docs/diagram` key | `docs/ENVIRONMENT.md` unchanged |

### 5.2 Goldens that change, and why

| Golden | Changes | Cause | Re-record with |
|---|---|---|---|
| `tests/engine/golden/prompts_brewlab_fixes0.json` | yes | mock `estimated_resources`: Priority prompt call 22 and the workflows digest | `scripts/record_engine_golden.py --source <folder> --commit <sha>` (a plain folder works) |
| `prompts_realization.json` | yes | `_place_wf` keys: Coordination prompt call 5 (+1,152 characters) and the workflows digest | same |
| `prompts_brewlab_fixes1`, `prd`, `design_docs`, `template_library` | no (verified equal) | | |
| `fn_atoms_brewlab.json`, `run_events.jsonl` | yes | the same two causes in the function-node run | `scripts/record_fn_golden.py` |
| `api_shapes.json` | `get.{live,saved,idle}.library.keys` +24; rows for the new routes; the `patched` section (runlist, changes) becomes ordinary J2 routes | provenance and data-dependent `enums.*` keys | `scripts/record_api_shapes.py --source <folder>`; make `key_paths` collapse `enums.<Name>` to `enums.*` so a new seed template cannot move it again |
| `tests/ui/fixtures/j2/*` and `golden-<key>.json` | yes, on the page re-port | the page and harness output changed | `scripts/capture_j2_fixtures.py` (add the new routes to its list) |
| `tests/engine/legacy/EXPECTED.json` | yes | new commit and larger minimums | after the port |

### 5.3 New tests worth writing

Existing tests that count J2's routes and must move with them: `tests/engine/test_engine_views.py` (`HANDLER_COUNT == 30`), `tests/ui/js/ctx.test.js` (23 exact names), `tests/contracts/test_contract_route_table.py`, `tests/ui/fake_backend.py` and `tests/ui/test_fake_backend.py` ("J2's 28 routes"), `tests/engine/test_engine_api_scope.py`, `tests/test_traceability.py`. New tests worth writing: `views` shape tests for the four routes; an engine test that the late judge's calls carry purpose `judge` or `plan`, the turn's function and honour `PICK_PURPOSES`; a strict-mode run with a forced late judgement; the `/api/ask` port (records-only without a model, the agent's pick with one, an unknown function refused, nothing written to the engine's run files); a prompt golden for `j2_agent.answer`'s system text; `doctor` sync of new versions; the `/library` path edits in `test_port_edits.py`; `page_render.test.js` keys for the new harness output.

### 5.4 Needs no Sutra work (and why)

| J2 change | Why |
|---|---|
| The 9 identical modules, all role files, conditions, `artifacts/types.json`, `README.md`, `SETUP.md`, `llm.py`, `j2_graph_layout.js` | byte-identical to what is vendored |
| `j2_agent_models.py`, `j2_agent_views.py` | no runtime path imports them; vendoring needs P1 x3 and removing the `sys.path` hack: only if the owner wants live agent JSON (6.6) |
| `j2_server.py` itself | Sutra does not vendor it; only the route semantics matter (3.E) |
| `build-on-run-design.md`, the two mocks, `agent-views-j2-proposal.md` | documents; no code behind them |
| New env flags | there are none |
| `/api/runlist`, `/api/changes` | P13 has identical logic (`run_row`, `run_list`, `run_changes`) |
| `library/` provenance in `meta.json` | copied byte for byte with the seed; the library package accepts it (`tests/library` green in the trial) |
| Runtime template store (`store`, `mark_used`, `_route_template`) | not in the diff: P10 and P12 hold |

## 6. Overlaps and conflicts with the newer Sutra work

Owner rules held throughout: one engine that gains capabilities, nothing routed in front of it (D126); every agent has its own chat session with its own model and effort (R2, D130-D134).

### 6.1 "Chat with every function" and the Map chat versus agent chat sessions (D130-D134)

| | J2 | Sutra |
|---|---|---|
| What it is | a stateless question to a function about its run, answered from records, not saved (`QA` lives in the page) | durable per-agent, per-run session, own provider, model and effort (D131), steering (D132), live partials (D133), one transcript (D108) |
| Where | right-hand `#chatp` panel, `POST /api/ask` | node panel Chat tab, `GET /api/teams/{dept}/agents` |

Conflicts, verified: (a) `llm.ask` needs `llm.configure(port)` from the host in the engine process; in the FastAPI process `_PORT` is `None` and a live `llm.ask` raises `NoModelAvailable` ("no port was configured (llm.configure)", `engine/llm.py:155`), so J2's `ask=llm.ask` cannot work there (D9, D14: one process per run, files only); (b) a model answer through J2's path would bypass the agent's pick, the usage ledger, the egress scan and limits; (c) two chat surfaces for the same function.

Recommendation (enhances, does not reroute; the owner picks the function, so it is an explicit action, not word routing): phase 1, serve `GET /api/activity` and answer `POST /api/ask` records-only (`ask=None`): no model, no session, no conflict. Phase 2, add an `EngineServices` method implemented by the orchestrator: open the function's agent session for that run (`AgentSessions.open`), call the connector with `CallTag(function=who, purpose="agent_chat")` (add `agent_chat` to `PICK_PURPOSES`; `PURPOSE_PATTERN` allows it) so the agent's own model and effort apply and usage is booked to that session, store question and answer as lines of that session, and pass that callable as `ask` to the unchanged `j2_agent.answer`. Keep J2's panel and Sutra's node panel for now (feed versus session); unify later.

### 6.2 Library catalog (`/library`, `/api/catalog`, `--collect`) versus Sutra's seeding, P10 and the name `sutra_app/library`

Names: no clash in the API (`sutra_app/library/api.py` already keeps its routes under `/api/schemas`; `/api/library` and `/api/catalog` are J2's) or the package. Pages: Sutra has `/`, `/console`, `/d/{dept}/`; the J2 page tests `location.pathname === "/library"`.

Recommendation: serve `/d/{dept}/library` (the page needs the team shell: rail, token, CSP) with port edits for the pathname test and the `/library` links; `/api/catalog` as a team route reading the one global library (read only: no lock needed, P12 makes the index replace atomic). Never run J2's `--collect` on a live data folder (unlocked read-modify-write). If the owner wants "By run" to list Sutra's runs, add a Sutra-owned step after a run ends (host or an ops command) that calls `collect(<team runs dir>, [run_id])` inside `j2_template_lib._library_lock()`: no J2 patch. Otherwise the page lists only the 8 J2 development runs of the seed (6 mock). Extend `sync_seed_library` to add missing versions so existing installs get the 5 new versions of existing templates.

### 6.3 J2 Run settings versus patch P13

J2's native pane and run list are the design Sutra's E14-E18 copied from the old copy (E17's run-list block is 89% identical to J2's; the differences are comments and `viewHref` versus `runHref`). Recommendation: retire E14-E18 and `run-settings.css`; keep the data behind it. P13 stays correct (same logic as `j2_server.run_row`, `run_list`), but its reason ("J2's own repository does not have them") is gone for the copy: either rewrite the P13 note, or retire the patch by moving the ~50 lines into Sutra-owned `views.py` (P13 changes no J2 behaviour; this makes the vendored diff one patch smaller). `PATCH_VIEWS` and the `patched` golden section then become ordinary routes recorded from J2.

### 6.4 Simple-view redesign and Artifacts tabs versus E1-E19

Facts in 3.F and 4.2: 13 of 29 edits fail, the rail changed shape, the start select that E19 patched no longer exists. Recommendation: re-derive, never hand edit; keep E1, E3, E4, E6b, E8-E13 (with the semantic re-check), rewrite E2, E5 (or retire), E6a, E7, E13b; retire E14-E19 unless the owner wants the per-request output choice back (Q3). D129 still holds through Settings (`engine.json` `output`), `TaskSettings.J2_OUTPUT` and `auto` as default.

### 6.5 Late judge versus capabilities, picks and records

The judge and improve calls are tagged judge/plan, so `PICK_PURPOSES` (`connectors/router.py:71`) applies the function's own pick and `LIVE_PURPOSES` (`engine/capabilities/agents.py`) shows them as the agent's live work: nothing to build. Open: which atom the usage rows are charged to (not verified: read the `usage` events of a forced-audit-failure run through the host). Cost: realization is on by default; each late workflow costs 1 to 3 high-effort calls (plus a retry when a reply lacks the workflow) (live cost not verified: `scripts/live_smoke.py` counting usage rows by purpose). Do not add a J2 patch to switch it off unless the owner asks; if so it would be a new numbered patch (P15) with an `EngineSettings` flag.

### 6.6 Agent-readable views versus Sutra's runs

J2 writes the JSON only from a CLI. For the tab to be useful in Sutra runs, a Sutra-owned run-end step (host, after `run.ended`) could run `j2_agent_views.build(d, quiet=True)`: requires vendoring the two modules with P1 x3 and removing the `sys.path` insert (a patch), or a subprocess of J2's own CLI. Recommendation: defer; take the read side now (the tab shows the run's own JSON and text).

### 6.7 Smaller overlaps

| Topic | Fact | Resolution |
|---|---|---|
| Project work (D128) in Artifacts | `project.md` is in no group and in no group of the old tree; `TYPES_PATH` is a constant in `j2_artifacts.py` | pre-existing gap, more visible with the new pane; fix needs a recorded patch or a capability hook: ask the owner |
| Motion (D122) | 43 infinite animations, all transform/opacity/dash offset | run `fluid_probe.js` after the port; add overrides in `sutra-panel.css` as D122 did for the idle drift |
| Build on a run (J2 design) versus follow-ups (D21, `rehydrate.py`, P11) | design only, no code | revisit when J2 ships code: a new `J2Run` entry point and `based_on` |
| Provider sessions and the page's chat panel | both are right-hand panels | check z-order and focus with `NodePanel` (not verified in a browser) |

## 7. Open questions, risks, effort

### 7.1 Open questions with a recommended answer

| # | Question | Recommended answer |
|---|---|---|
| Q1 | Where does sync 4 vendor from: `prototypes/j2` at a pinned sutra commit, or J2's own `origin/main`? | D114 allows the copy when J2's repo lacks a change. Take `prototypes/j2` at a pinned commit (extract with `git archive`, record the commit, the tree id of `prototypes/j2` and the extraction in `VENDORED.md`) because it is the only superset; note in the sync note that `j2.py`, `j2_agent.py`, `j2_map.py` and the seed equal J2's `dfa44b3`. If the owner wants to follow J2 first, do J2's `origin/main` as a first step: it needs no vendor-script change and one page-edit repair (E14) |
| Q2 | Take J2's new page including the Simple-view redesign? | Yes: it is what the J2 side now calls J2; keep the "page is generated" rule |
| Q3 | Bring back the per-request output choice (D129, E19)? | Yes if the owner still wants it on the start page: one new edit on the landing or in Run settings; else rely on Settings and `auto` |
| Q4 | `POST /api/ask`: records-only first? | Yes (6.1), model answers through the orchestrator port in a second step |
| Q5 | `/library` under the team (`/d/{dept}/library`) or a global page? | under the team (page shell); the data is global |
| Q6 | Collect Sutra's runs into the catalog? | yes, as a Sutra-owned locked step, or accept that "By run" shows only J2's 8 development runs |
| Q7 | Ship the seed templates that are marked `mock: true` (26 of 39)? | keep: they are valid templates; the catalog's Hide mock toggle exists |
| Q8 | Keep P13 as a patch or move it to `views.py`? | move (one patch fewer, no behaviour change), optional |
| Q9 | Vendor `j2_agent_*`? | not now (6.6) |
| Q10 | Make the late judge optional? | no patch now; measure cost first |
| Q11 | Project report in Artifacts? | ask the owner; needs a recorded patch or a capability hook |

### 7.2 Risks (ranked)

| # | Risk | Where |
|---|---|---|
| 1 | The page re-port is the critical path: 13 failing anchors, a new rail that Sutra's two tabs and the team chip must fit into, 11 passing anchors that need a behaviour check | 4.2 |
| 2 | Late judge: extra high-effort calls by default (realization on); strict records reject `late` and `judge`; goldens | 3.A, 4.5 |
| 3 | `/api/ask` in the API process has no model seam and would bypass picks, usage and egress | 6.1 |
| 4 | Two diverging copies of J2 (J2's own repo and `prototypes/j2`): later J2 merges of agent views, Artifacts or the Simple view may differ from the copy | 1.4 |
| 5 | `/library` is a root path in J2's page; every link and the pathname test must follow `/d/{dept}/` | 3.F, 6.2 |
| 6 | Seed: 26 of 39 versions are mock, `runs` holds J2's development runs, existing installs do not receive new versions | 2.3, 3.D |
| 7 | Hidden coupling: a third lazy import in `j2_artifacts.py`; `sframe` src set by script; `served()` accepts `agent/*.json` only because J2's listing does (verified for the CLI output); `j2_agent_views.py` flat imports; a test that pins seed counts and a shape golden that holds data-dependent keys | 3.C, 4.1 |
| 8 | Line numbers: only VENDORED.md ranges and the P7, P10, P12 rows move; the design docs' `j2.py` references below line 6650 stay valid | 4.1 |
| 9 | Windows: no new risk found in the vendored code (paths use `os.path` and `/` in records; P12 holds); not run on Windows | not verified: run `windows` CI |
| 10 | Size: `j2_ui.html` +45% (585,080 bytes; the CSP script hashes recompute per page file), `j2.py` +9 KB, seed index 168 KB, legacy flow test +124 KB | |
| 11 | Motion: 43 infinite animations | 3.F |
| 12 | J2's own flow test cannot finish in `prototypes/j2` (needs `runs/`); the legacy port guards it | 1.3 |

### 7.3 Effort (S under half a day, M one to three days, L more than three; one developer)

| Theme | Size | Notes |
|---|---|---|
| Re-vendor, `VENDORED.md`, seed counts, doctor tests | S | one count and the header text in the script |
| Goldens (2 prompt, 2 function-node, shapes) and records models (`judge`, `late`, schema export) | M | mostly recording and review |
| Four read routes and the stdlib adapter, `J2_PATHS`, route-count tests | M | patterned on existing views |
| `POST /api/ask` records-only | S | |
| `POST /api/ask` with the agent's model, session lines, usage | L | orchestrator, router, tests |
| Catalog page under the team, path edits, seed policy | M | |
| Catalog collector for Sutra's runs (optional) | M | locked, per team |
| Page re-port: rewrite E2, E5, E6a, E7, E13b, new edits, rail placement | L | the critical path |
| UI tests, fixtures, harness keys, port-edit table | M | |
| Legacy flow port (7 hunks by hand), `EXPECTED.json` | S | |
| Agent-readable views live (optional) | M | deferred |
| Docs, decisions, sync note | S | |

### 7.4 Suggested work split (the architect decides)

1. **Engine sync** (re-vendor, goldens, records models, seed tests, legacy port): independent of the page; the old ported page keeps working against the new engine (verified: the 9200cf6-era legacy flow test passes, the UI python tests are unchanged).
2. **Read routes and the ask port, phase 1** (views, adapters, `J2_PATHS`, shapes).
3. **Page re-port and UI tests** (the large package; depends on 2 for the new routes).
4. **Ask with the agent's model, catalog collector, agent views live** (each optional, each its own decision).

## Appendix A. Not verified, and how to check

| Item | How to check |
|---|---|
| J2's live `origin/main` (I used the clone's remote-tracking ref) | `git -C <J2> fetch --dry-run` |
| The new page under Sutra's shell (CSP, sandbox, node panel next to `#chatp`, rail) | after the re-port: `SUTRA_BROWSER=1`, `tests/ui/test_browser_smoke.py`, `node --test tests/ui/js/*.test.js` (node tests not run here) |
| Whether J2's chat panel scope (every function) is S or U | diff `chatFollow` and the `chatp` markup in the two pages |
| Late judge cost and usage attribution in live runs | `scripts/live_smoke.py`, count `usage` events by purpose; read the atom of the late judge rows |
| Whether `sutra_app/library` validates the Document generic entries | `tests/library` was green in the trial; add a test that loads `engine/templates/prd/generic.json` through the library models |
| Schema-drift test after adding `late` and `judge` | `tests/library/test_lib_schema_drift.py` |
| Windows | CI `windows` job; `tests/ops` and `tests/engine` there |
| Motion (D122) | `tests/ui/perf/fluid_probe.js` on the ported page |
