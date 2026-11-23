# Named Projects Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or
> superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** the owner works in named projects the way Codex does: a project has a name the owner typed, a folder on disk,
receives the prompts sent to it, can be renamed or deleted, and (Phase 2) the next prompt edits the files in its folder.

**Architecture:** a project stays a Sutra team (a department of the org chart); no new layer. Code-only routes under
`/api/teams` create, rename and hide teams through `ChartStore.apply` (no model call). The working folder, today one file
per app (`connectors/workdir.py`), gains one file per team with the app-wide folder as the fallback. A folder no longer
selects project work. A finished run copies its deliverables into the team's folder, guarded by a manifest.

**Tech stack:** Python 3 (FastAPI, SQLite, pydantic), the vendored J2 engine (`sutra_app/engine`), plain browser JS
(`sutra_app/ui/static/js`, node tests in `tests/ui/js/`), Electron preload `window.sutraDesktop.chooseFolder()`.

**Spec:** `D:\Downloads\Sutra Pro Named Projects PRD.pdf` (Named Projects PRD, 23 Nov 2026; requirement ids R1.x, R2.x and
journeys CUJ 1 to 7 below refer to it). The owner's decisions Q1 to Q13 are below; where the PRD and this plan differ,
the PRD wins unless the line says "owner".

**Branch:** `named-projects`, worktree `C:\Users\sandi\Documents\sutra-named-projects`, at `origin/main` 06ea534c.
All paths below are relative to `sutra-pro/`; every command runs from `sutra-pro/` in the worktree.

## Decisions (owner, 2026-11-23)

| # | Decision |
|---|---|
| Q1 | One project = one team. Its own agents, runs and page. |
| Q2 | "+ New project" opens **Create project**: Project name (required, 1 to 80 characters, a name in use is refused) and an optional source folder. |
| Q3 | The start heading reads "What should we make in <Project>?"; the name is a dropdown that switches project. On Attention it also offers "Let Sutra choose" (plain "What should we make?") and "+ New project…". |
| Q4 | Attention starts on the last project used; "Let Sutra choose" only when none was picked yet. |
| Q5 | The existing "Pulse" section and Friday's run are left as they are. |
| Q6 | Targeted tests for the new parts only; no full gate, no CI wait, no release. |
| Q7 | A project's folder says where the team works. It no longer turns a run into project work. |
| Q8 | Delete hides the project and keeps its runs and files. Confirm first; refused while it works. The hidden team is renamed "<name> (deleted <d Mon>)" so the name is free. |
| Q9 | The project folder holds the current work. A finished run writes its results there; Phase 2 edits them in place. Files Sutra did not write are never touched. |
| Q10 | After a folder is picked: "Allow Sutra Pro's team to read and edit files in <path>?" **Read and edit** (default), **Read only**, **Cancel**. |
| Q11 | Every project has a folder: the chosen one, else `Documents\Sutra Pro\<project name>\`, made at creation. |
| Q11b | Create project stays disabled until a name is typed. No "Untitled". |
| Q12 | Two phases. Phase 1 (tasks 0 to 11) goes to the beta first; Phase 2 (tasks 12 to 15) follows. |
| Q13 | "Let Sutra choose" never makes a project by itself: when the org chat would add a team, the owner names it in the Create project box first. Reusing a project asks nothing. |
| S1 | (owner, this session) This session builds Phase 1, checks CUJs 1 to 5 on a local server (the beta builds only on a Mac), pushes the branch `named-projects`, and stops. Merge to `main` and Phase 2 wait for the owner's beta try on the Mac. |

## Global Constraints

- `git fetch origin && git merge origin/main` before each task and before the push. Your branch
  `sutra-pro-no-project-words` (D253, not on main) rewrites `select.py`. If it lands first, merge it and keep both changes:
  only the rules `owner`, `followup` and `planner` remain.
- New routes are `/api/teams`, `/api/teams/{dept_id}` and `/api/teams/last`. Never `/api/projects/...`: that prefix
  belongs to the multi-agent projects behind `SUTRA_NODES_V1`. `GET /api/teams/{dept}/agents` already exists
  (`api/agent_chats.py`) and stays.
- Every write route has `dependencies=[Depends(require_token)]` (`sutra_app/orchestrator/api/deps.py`).
- The UI shows plain words only: "project", never department, chart or node.
- The owner sees these strings exactly:
  - "Give the project a name"
  - "A project called <name> already exists"
  - "Saved in Documents\Sutra Pro\<name>" (with `/` on a Mac)
  - "<name> is working. Wait for it or stop it."
  - "<name> is working. Stop it first."
  - "Working. Stop it first."
  - "Saved to <folder>: <n> files (<a> new, <b> updated)."
  - "Not updated: <file> was changed outside Sutra"
- Decisions take the next free numbers after fetching (main is at D424, so D425 onward). Each one is a
  `## D<n> — title` block in `docs/DECISIONS.md` (Sources / Decided / Why / Rejected / Diagram bullets) plus an entry in
  `docs/diagram/decisions.json`. `tests/test_diagram_decisions.py` enforces both.
- Never write the owner's name, a login or an absolute home path into a file under `sutra-pro/` (`tests/test_ownership.py`).
- Python tests: `scripts/py -m pytest <files> -q` (Git Bash). Node tests: `node --test tests/ui/js/<file>.test.js`.
  A new node test file goes in `tests/ui/js/` (`tests/ui/test_node_suite.py` globs only there).
- Commits are authored by the git identity already set in the worktree and end with
  `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.

## Review Focus

1. **A name that is not a valid folder name**, such as `Pulse: v2`, `a/b`, `CON` or `Notes.`. The project keeps the typed
   name, and the default folder gets a safe name. Test: task 3, `test_default_folder_name_is_safe_on_every_os`.
2. **The default folder already exists**, for example after "Pulse" was deleted and a new "Pulse" is made. The new
   project gets `Pulse 2` and never writes into the old project's files. Test: task 3, `test_default_folder_never_reuses_an_old_one`.
3. **The project folder was moved or deleted on disk before a run ends.** The run still ends well. The chat says
   "Not saved: <path> is not there any more", and Sutra does not recreate the folder. Test: task 9, `test_a_vanished_folder_is_reported_not_made`.
4. **A target file is locked or unwritable**, for example open in Word on Windows. That file is skipped and named in the
   chat; the other files are saved and the run's end is unaffected. Test: task 9, `test_a_locked_file_is_skipped_and_named`.
5. **A deleted project's page is still open**, or Attention's last pick is a deleted project. Sending to it is refused
   with "This project was deleted." Attention falls back to "Let Sutra choose". Test: task 3, `test_a_hidden_team_is_read_only`;
   task 8, `"a deleted last pick reads as Let Sutra choose"`.

---

## Phase 1: projects, folders and results in the folder

| # | Task | Impact | Effort |
|---|---|---|---|
| 0 | Baseline of the touched tests | lets the rest start | 0.5 h |
| 1 | A working folder per team | Pulse can have its own folder | 3 h |
| 2 | A folder no longer selects project work | no more one-team runs from a folder | 1 h |
| 3 | `/api/teams`: create, rename, hide | the server side of the feature | 5 h |
| 4 | Hidden teams are invisible to the org chat | a deleted project gets no new work | 2 h |
| 5 | The org chat asks for a name before it adds a project | no project without the owner's name | 4 h |
| 6 | Create project box | the owner starts projects | 3 h |
| 7 | Rename and Delete in the ⋯ menu | the owner manages projects | 2 h |
| 8 | "What should we make in <Project>?" and the dropdown | the owner chooses where each prompt goes | 4 h |
| 9 | A finished run writes its results into the project folder | the work is where the owner expects it | 3 h |
| 10 | Decisions and docs | required on main | 1.5 h |
| 11 | Local check of CUJs 1 to 5, push the branch | the owner can try it | 1 h |

### Task 0: Baseline

- [ ] **Step 1:** In the worktree run `git fetch origin && git merge origin/main`.
- [ ] **Step 2:** Run the baseline and write down any test that already fails. Those failures are noted, not fixed.
  - Run: `scripts/py -m pytest tests/connectors/test_workdir.py tests/connectors/test_workdir_chat.py tests/engine/test_select_output.py tests/engine/test_engine_project.py tests/orchestrator/test_chart_store.py tests/orchestrator/test_api_chart.py tests/orchestrator/test_departments.py tests/orchestrator/test_schema.py -q`
  - Run: `node --test tests/ui/js/project_rail.test.js tests/ui/js/front_door.test.js tests/ui/js/dept_ext.test.js tests/ui/js/sections_store.test.js tests/ui/js/output_pick.test.js`

### Task 1: A working folder per team

**Files:**
- Modify: `sutra_app/connectors/workdir.py` (`WorkFolder`, :244-331)
- Modify: `sutra_app/connectors/router.py` (`chat_folder` :385, `folder_for` :396, `_chat_turn` :1090)
- Modify: `sutra_app/orchestrator/api/chat_v2.py` (the `ChatTurnIn(...)` at :271, :481, :536)
- Modify: `sutra_app/engine/host/loop.py` (`_has_folder` :327, `_owner_grant` :710)
- Test: `tests/connectors/test_workdir_per_team.py` (new)

**Interfaces:**
- Produces:
  - `WorkFolder(data_dir, work_root=None, *, dept_id: str = "")`. With `dept_id=""` the file is
    `<data>/connectors/workdir.json`, exactly as today. With a team id it is `<data>/departments/<dept_id>/workdir.json`,
    with the same body, mode 0600 and atomic write. A `dept_id` that fails `DEPT_ID_RE` raises `ValueError`.
  - `WorkFolder.for_team(self, dept_id: str) -> WorkFolder`, same `data_dir` and `work_root`.
  - `WorkFolder.team_grant(self, dept_id: str) -> Optional[Folder]`: the team's own grant when its `get()` is not None,
    else this instance's own grant (the app-wide fallback). `dept_id=""` gives the app-wide grant.
  - The existing `stored/problem/stored_access/get/grant/preview/set/set_access/clear` act on the instance's own file
    only, unchanged.

- [ ] **Step 1: Write the failing tests** in `tests/connectors/test_workdir_per_team.py`:
  - `test_a_team_folder_is_its_own_file`: `WorkFolder(data, dept_id="pulse").set(str(a), access="edit")` writes
    `data/departments/pulse/workdir.json` with `{"version": 1, "path": <real a>, "access": "edit"}`, and the app-wide file
    is not created.
  - `test_team_grant_prefers_the_team_folder`: with app-wide `b` and team `a`, `team_grant("pulse") == real(a)` and
    `.edit is True`.
  - `test_a_team_without_a_folder_gets_the_app_wide_one`: `team_grant("web") == real(b)`.
  - `test_a_vanished_team_folder_falls_back`: set team `a`, `rmdir(a)`; `team_grant("pulse") == real(b)` and never `a`.
  - `test_blank_dept_is_the_app_wide_folder`: `team_grant("") == WorkFolder(data).grant()`.
  - `test_a_team_folder_is_refused_like_the_app_wide_one`: `set(str(data))` raises `InvalidRequestError` with
    "That folder belongs to Sutra itself".
  - `test_a_bad_team_id_is_refused`: `WorkFolder(data, dept_id="../x")` raises `ValueError`.
- [ ] **Step 2: Run the tests and see them fail**
  - Run: `scripts/py -m pytest tests/connectors/test_workdir_per_team.py -q`
  - Expected: FAIL (`unexpected keyword argument 'dept_id'`).
- [ ] **Step 3: Implement** the Interfaces above in `workdir.py`.
- [ ] **Step 4: Thread the team through the callers.**
  - `router.py`: `chat_folder(self, dept_id: str = "") -> str` returns `self.folders.team_grant(dept_id) or ""`. Keep the
    offline and exception paths.
  - `router.py`: `folder_for(tag)` calls `self.chat_folder(tag.dept_id)`; `_chat_turn` calls
    `self.chat_folder(state.ctx.tag.dept_id)`.
  - `chat_v2.py`: when `session.kind == "department"`, build the turn's tag with `dept_id=session.node_id`, keeping the
    existing `workspace` (`CallTag(dept_id=..., workspace=...)`). The org chat (`cs_org`) keeps `dept_id=""`.
  - `loop.py`: `_has_folder` and `_owner_grant` use `WorkFolder(self.paths.data_dir).team_grant(self.task.dept_id)`.
- [ ] **Step 5: Add a router test** in the same file: `test_router_chat_folder_uses_the_team`. A `Router` whose `folders`
  is `WorkFolder(data)` returns team `a` for `chat_folder("pulse")` and app-wide `b` for `chat_folder("")`. Build the
  `Router` the same way `tests/connectors/test_workdir_chat.py` does.
- [ ] **Step 6: Run the new tests and the baseline workdir tests; all pass.**
  - Run: `scripts/py -m pytest tests/connectors/test_workdir_per_team.py tests/connectors/test_workdir.py tests/connectors/test_workdir_chat.py -q`
- [ ] **Step 7: Commit** with the message `Sutra Pro: a working folder per team, the app-wide folder as fallback (named projects 1)`.

### Task 2: A folder no longer selects project work (Q7, R1.7)

**Files:**
- Modify: `sutra_app/engine/capabilities/select.py` (`RULES` :32, rule at :92-93, `chat_line` :97-108)
- Modify: `tests/engine/test_select_output.py` (TABLE rows :17, :19, :28, :34, :35; the assertion at :87)
- Modify: `tests/engine/test_engine_project.py:276-290`

- [ ] **Step 1: Change the tests first.**
  - In `test_select_output.py`, every TABLE row that expected rule `"folder"` now expects `(None, "planner")`.
  - Replace the `:87` assertion with `test_a_folder_alone_leaves_the_choice_to_the_planner`:
    `choose_output("look around", True) == Selection(None, "planner", "the team's planner chooses")`.
  - Rename `test_a_folder_that_is_set_turns_an_unclear_request_into_project_work` to
    `test_a_folder_that_is_set_leaves_an_unclear_request_to_the_planner`. Assert `record["rule"] == "planner"`,
    `record["output"] is None` and `record["folder"] is True`, and that no chat line contains "project work".
  - Keep: the owner's explicit choice `"project"` with `has_folder=True` still gives rule `"owner"` (:161).
- [ ] **Step 2: Run the tests and see them fail.**
  - Run: `scripts/py -m pytest tests/engine/test_select_output.py tests/engine/test_engine_project.py -q`
- [ ] **Step 3: Implement.** Remove the folder rule and `"folder"` from `RULES`. `chat_line` has no folder-rule wording
  left to drop; leave its no-folder hint for owner and project choices as it is.
- [ ] **Step 4: Run the tests; all pass.** Same command.
- [ ] **Step 5: Commit** with the message `Sutra Pro: a working folder no longer turns a run into project work (named projects 2)`.

### Task 3: `/api/teams`: create, rename, hide (R1.1 to R1.5, R1.13)

**Files:**
- Create: `sutra_app/orchestrator/team_admin.py`
- Create: `sutra_app/orchestrator/api/teams.py`
- Modify: `sutra_app/orchestrator/schema.py` (add `DDL_V9_HIDDEN_TEAMS`, append it to `MIGRATIONS` :336, update `__all__`)
- Modify: `sutra_app/orchestrator/departments.py` (`row` :52, `listing` :60, `get` :68, the docstring :11-13)
- Modify: `sutra_app/orchestrator/errors.py` (`STATUS_BY_CODE`: add `name_taken` → 409)
- Modify: `sutra_app/orchestrator/chart.py` and `chart_rules.py` (owner changes skip the similar-name reuse check)
- Modify: `sutra_app/orchestrator/wiring.py` (`services.team_admin`), `sutra_app/main.py` (`ROUTERS` :70, the import :47)
- Modify: `sutra_app/oslayer.py` (`documents_dir() -> Path`)
- Test: `tests/orchestrator/test_team_admin.py` (new)

**Interfaces:**
- Produces:
  - `DDL_V9_HIDDEN_TEAMS = ("ALTER TABLE departments ADD COLUMN hidden_at INTEGER",)`.
  - `DepartmentStore.hidden_ids(self, conn=None) -> set[str]`.
  - `DepartmentStore.listing()`, `get()` and `problems()` skip rows with `hidden_at IS NOT NULL`; `get()` of a hidden team
    raises `NotFound("that team")`.
  - `DepartmentStore.row()` still returns a hidden team, with `archived=True`. Its runs stay readable and writes get 403
    `read_only` through `engine/api/ctx.py`. That 403's sentence is "This project was deleted." (add it where `read_only`
    is raised for an archived row).
  - `oslayer.documents_dir() -> Path`: on Windows the Documents known folder via `SHGetKnownFolderPath(FOLDERID_Documents)`
    (ctypes), falling back to `Path.home() / "Documents"` on any error; elsewhere `Path.home() / "Documents"`.
  - In `team_admin.py`:
    - `clean_name(raw: str) -> str` collapses whitespace and strips. An empty result raises
      `AppError("validation", "Give the project a name", {"field": "name"})`. More than 80 characters raises
      `AppError("validation", "Keep the project name to 80 characters", {"field": "name"})`.
    - `folder_name(name: str, taken: Callable[[str], bool]) -> str`:
      - Replace each of `<>:"/\|?*` and each control character with `-`, then strip trailing dots and spaces.
      - An empty result or a Windows device name gives `"Project"`.
      - While `taken(candidate)` is true, append ` 2`, ` 3`, and so on.
    - `deleted_name(name: str, today: date) -> str` gives `f"{base} (deleted {today.day} {today:%b})"` with `base` cut so
      the total is at most 80 characters.
    - `class TeamAdmin(db, chart: ChartStore, departments: DepartmentStore, data_dir: Path, clock, *, documents: Path | None = None, work_root: Path | None = None)`.
      `documents` defaults to `oslayer.documents_dir()`.
    - `TeamAdmin.name_problem(self, name: str, *, except_id: str | None = None) -> str | None` compares by the library's
      name key (NFKC, whitespace removed, casefold) against visible teams and returns the "already exists" sentence.
    - `TeamAdmin.create(self, name: str, folder: str | None = None, access: Literal["edit","read"] = "edit") -> TeamCreated`,
      where `TeamCreated` is a frozen dataclass `(team: DepartmentOut, folder: str, access: str)`.
    - `TeamAdmin.ensure_folder(self, dept_id: str, name: str, folder: str | None, access: str) -> str` checks or makes the
      folder and stores it with `WorkFolder(data, work_root, dept_id=dept_id).set(...)`. Task 5 reuses it.
    - `TeamAdmin.rename(self, dept_id: str, name: str) -> DepartmentOut`.
    - `TeamAdmin.hide(self, dept_id: str) -> None`.
  - Routes in `api/teams.py` (`build_router()` and `router = build_router()`, the same shape as `api/sections.py`):
    ```
    POST   /api/teams           {name: str, folder?: str|null, access?: "edit"|"read"}  -> 201 {team: DepartmentOut, folder, access}
    PATCH  /api/teams/{dept_id} {name: str}                                            -> 200 DepartmentOut
    DELETE /api/teams/{dept_id}                                                        -> 200 {"hidden": true}
    ```
    Bodies use `ConfigDict(extra="forbid")`. `dept_id` is `Path(pattern=DEPT_ID_RE)`. All three take the token.

- [ ] **Step 1: Write the failing tests** in `tests/orchestrator/test_team_admin.py`.
  - Setup: reuse `Env` from `orchestrator.test_chart_store`. Build a client the way
    `tests/orchestrator/test_api_chart.py:17-55` `make_client` does, plus `services.team_admin` and the teams router.
    Pass `documents=tmp_path / "Documents"`.
  - `test_create_makes_a_team_with_five_agents_and_a_folder`: POST `{"name": "Pulse"}` → 201.
    - `team.name == "Pulse"` and `len(team.functions) == 5`.
    - `data/departments/<id>/` exists.
    - `folder == str(tmp/Documents/Sutra Pro/Pulse)`, the folder exists, and `access == "edit"`.
    - `WorkFolder(data, dept_id=id).get() == folder`.
    - `chart_changes` has one more row, with `actor == "user"`.
  - `test_create_needs_the_token` → 401 `bad_token`.
  - `test_a_blank_name_is_refused`: `"   "` → 422 with message "Give the project a name"; 81 characters → 422; no team is made.
  - `test_a_name_in_use_is_refused_ignoring_case_and_spaces`: after "Pulse", `" pulse "` → 409 `name_taken`
    "A project called Pulse already exists".
  - `test_owner_names_skip_the_similar_name_check`: after "Pulse", "Pulse app" → 201.
  - `test_a_chosen_folder_is_checked_and_stored`:
    - folder `tmp/src` with `access: "read"` → `WorkFolder(..., dept_id).stored_access() == "read"`;
    - a folder that does not exist → 422 "There is no folder at …", and no team is made.
  - `test_default_folder_name_is_safe_on_every_os`:
    - "Pulse: v2" makes the folder `Pulse- v2`;
    - "CON" makes `Project`;
    - "Notes." makes `Notes`;
    - the team names stay as typed.
  - `test_default_folder_never_reuses_an_old_one`: `Documents/Sutra Pro/Pulse` already exists with a file → the folder
    becomes `Pulse 2`.
  - `test_rename_keeps_the_id`: PATCH `{"name": "Pulse pilot"}` → 200, same id, new name. A name in use → 409.
  - `test_delete_hides_and_frees_the_name`:
    - DELETE → `{"hidden": true}`;
    - `listing()` has no row for it;
    - its `org_nodes.name == "Pulse (deleted 23 Nov)"` (the clock on 2026-11-23);
    - `departments/<id>/` and the folder still exist;
    - POST "Pulse" again → 201 with a different id.
  - `test_delete_is_refused_while_the_team_works`: add a task with status `running` (`add_task` in `test_departments.py`)
    → 409 `busy` "Pulse is working. Stop it first."
  - `test_a_hidden_team_is_read_only`: `departments.row(id).archived is True`.
  - `test_deleted_name_fits_80`: an 80-character name becomes at most 80 characters and ends `(deleted 23 Nov)`.
  - `test_migration_adds_hidden_at`: `PRAGMA table_info(departments)` has `hidden_at`, and `SCHEMA_VERSION == 9`.
- [ ] **Step 2: Run the tests and see them fail.**
  - Run: `scripts/py -m pytest tests/orchestrator/test_team_admin.py -q`
- [ ] **Step 3: Implement the schema, `departments.py`, `errors.py` and `oslayer.documents_dir`.**
- [ ] **Step 4: Implement `TeamAdmin.create`.**
  - `clean_name`, then `name_problem` (409 `name_taken`).
  - Folder: a given folder goes through `check_folder(folder, data_dir=..., work_root=...)`. With none, run
    `mkdir(parents=True, exist_ok=False)` on `documents / "Sutra Pro" / folder_name(...)`; `taken` is "exists and is not
    empty".
  - Build `GATE.check("chart_change", ChartChange.from_request(ChartChangeRequest(reason=f"The owner made the project {name}", ops=[AddOp(node=NewNode(ref="$p", kind="department", name=name, parent="root"))]), id=chart.next_change_id(), task_id="owner-teams", base_revision=chart.head().model.revision))`.
  - `chart.apply(..., actor="user", ctx=ChangeContext(session_id="cs_org", request_id="owner-teams", request_title=f"New project {name}"[:80]))`.
    On `stale`, rebuild once with the new head and apply again.
  - The new id is the result's ref map entry for `"$p"`. Then `ensure_folder`.
  - When the chart apply fails, remove a default folder that was just made and is still empty.
- [ ] **Step 5: Owner changes skip the similar-name check.** Pass `actor` from `ChartStore.apply` down to
  `ChartRules.extras(conn, chart, change, *, actor)`. Call `reuse_violations` only when `actor == "chat_agent"`. The
  library's exact-sibling `duplicate_name` check stays for everyone.
- [ ] **Step 6: Implement `rename`.** One `RenameOp(node=dept_id, name=clean)`, after `name_problem(except_id=dept_id)`.
- [ ] **Step 7: Implement `hide`.**
  - Refuse when `tasks` has a row for the team with a status in `chart_rules.OPEN_STATUSES`.
  - Otherwise `RenameOp` to `deleted_name(...)`. If that name is taken too, append ` 2`, ` 3`, and so on.
  - Then `UPDATE departments SET hidden_at = ? WHERE id = ?` in a `db` transaction.
- [ ] **Step 8: Mount and amend.** Wire `services.team_admin` in `wiring.py` and mount the router in `main.py` `ROUTERS`
  (anywhere after `agent`). Amend the DL5 sentence in `departments.py:11-13`, `api/departments.py:7`,
  `models.py:622` and `library/department.py:13` to: "never moved or merged; the owner may hide it (D426), which renames
  it and keeps its id, runs and files".
- [ ] **Step 9: Run the new tests and the chart, department and schema tests; all pass.**
  - Run: `scripts/py -m pytest tests/orchestrator/test_team_admin.py tests/orchestrator/test_chart_store.py tests/orchestrator/test_api_chart.py tests/orchestrator/test_departments.py tests/orchestrator/test_schema.py -q`
- [ ] **Step 10: Commit** with the message `Sutra Pro: the owner makes, renames and hides projects without a model call (named projects 3)`.

### Task 4: Hidden teams are invisible to the org chat

**Files:**
- Modify: `sutra_app/orchestrator/chart_rules.py` (`digest` :153, `reuse_violations` :51, `assignments` :128)
- Modify: `sutra_app/orchestrator/chart.py` (`view` :124)
- Modify: `sutra_app/orchestrator/agent/agent.py` (callers of `candidates` :214 and `fallback_plan` :403; the `choice_plan`
  node check :197; the `reuse_nodes` check :246-249)
- Modify: `sutra_app/orchestrator/chat_ground.py:150,184`
- Test: `tests/orchestrator/test_hidden_teams.py` (new)

**Interfaces:**
- Consumes: `DepartmentStore.hidden_ids()` (task 3).
- Produces: `chart_rules.without_hidden(chart: OrgChart, hidden: set[str]) -> OrgChart`. It is a `model_copy` with each
  hidden department and every node under it removed. Edges to removed nodes are dropped.

- [ ] **Step 1: Write the failing tests.** Build Sales and Web with `Env.build()`, then hide Web through `TeamAdmin.hide`.
  - `test_digest_leaves_out_a_hidden_team`: "Web" is not in `chart.digest("make a site")`.
  - `test_candidates_leave_out_a_hidden_team`: `candidates(without_hidden(head, hidden), "web site")` has no `web`.
  - `test_a_change_that_reuses_a_hidden_team_is_refused`: a chat-agent change with `reuses=["web"]`, or a draft assigned
    to `web`, gives a violation whose message is "That project was deleted".
  - `test_an_add_like_a_hidden_team_is_not_a_reuse`: a chat-agent add named "Web Shop", next to a hidden
    "Web Shop (deleted 23 Nov)", has no `reuse_candidate`.
  - `test_agent_org_view_leaves_out_a_hidden_team`: `chart.view()` has no node `web` and none of its function nodes.
  - `test_chat_grounding_leaves_out_a_hidden_team`: assert on the grounding text built at `chat_ground.py:150`.
- [ ] **Step 2: Run and see them fail.**
  - Run: `scripts/py -m pytest tests/orchestrator/test_hidden_teams.py -q`
- [ ] **Step 3: Implement.**
  - `digest`, `reuse_violations` and `view` filter through `hidden_ids`.
  - `assignments` and the agent's reuse and choice checks refuse hidden ids with "That project was deleted".
  - `agent.py` passes `without_hidden(head, hidden)` to `candidates` and `fallback_plan`.
  - The SQL in `chat_ground.py` adds `AND id NOT IN (SELECT id FROM departments WHERE hidden_at IS NOT NULL)`.
- [ ] **Step 4: Run the new tests and the agent tests; all pass.**
  - Run: `scripts/py -m pytest tests/orchestrator/test_hidden_teams.py tests/orchestrator/agent -q`
- [ ] **Step 5: Commit** with the message `Sutra Pro: a deleted project is invisible to the org chat (named projects 4)`.

### Task 5: The org chat asks for a name before it adds a project (Q13, R1.11)

**Files:**
- Modify: `sutra_app/orchestrator/chart_rules.py` (`classify` :41)
- Modify: `sutra_app/orchestrator/chart.py` (`classify` :141, `apply` :334, `decide` :263)
- Modify: `sutra_app/orchestrator/agent/planner.py` (`LINES` :35-63)
- Modify: `sutra_app/orchestrator/agent/runner.py` (`decide` :167, `_ask_approval` :542, `_approval_question` :866,
  `_decide_flow` :563)
- Modify: `sutra_app/orchestrator/models.py` (`ApprovalCard` :287, `NeedsYouOut` :680)
- Modify: `sutra_app/orchestrator/chats.py:410-415` (the approval needs-you row)
- Modify: `sutra_app/orchestrator/api/chart.py` (`DecisionIn` :31) and `api/agent.py:79-86`
- Modify: `sutra_app/ui/static/js/chat_view.js` (`choiceCard` :206) and `front_door.js` (`needCard` :146)
- Modify: `sutra_app/ui/static/js/home.js` (`onFrontClick`, and the chat click handler for `data-act`)
- Test: `tests/orchestrator/agent/test_add_needs_name.py` (new)
- Test: additions to `tests/ui/js/front_door.test.js` and `tests/ui/js/chat_view.test.js`

**Interfaces:**
- Consumes: `TeamAdmin.ensure_folder`, `TeamAdmin.name_problem` and `clean_name` (task 3).
- Produces:
  - `classify(change, *, actor: str = "chat_agent")`. It returns `"approve"` also when `actor == "chat_agent"` and any op
    is an `AddOp` with `node.kind == "department"`.
  - `ProposedAdd(Value)`: `ref: Ref`, `name: Name`.
  - `ApprovalCard.adds: list[ProposedAdd] = []` and `NeedsYouOut.change_id: ChangeId | None = None`. Both
    `NeedsYouOut.adds: list[ProposedAdd] = []` and the card's `adds` are left out of the JSON when empty, the way the
    `project_id` serializer at `models.py:280-284` does it, so existing cards keep their wire shape.
  - `LINES["approve_add"] = "I'd start a new project for this: {name}. Name it to create it, or say no."`.
  - `ChartStore.decide(self, change_id, approve, *, names: dict[str, str] | None = None)` rewrites each named ref's
    `NewNode.name` (through `clean_name`) in the stored change before the re-check. With `names`, the re-check runs as
    `actor="user"`.
  - `Runner.decide(self, change_id, approve, *, names=None, folder=None, access="edit")`.
  - `DecisionIn` adds `names: dict[str, str] | None = None`, `folder: str | None = None` and
    `access: Literal["edit","read"] = "edit"`.
  - After an approved add, whatever the path (card button, typed "yes" or the decision route), `_decide_flow` calls
    `team_admin.ensure_folder(new_id, name, folder, access)` for each department ref.
  - Cards with `adds` show the buttons "Name it…" (`data-act="name-add"`, `data-change`, `data-ref`, `data-name`) and
    "Not now" (the existing decline). Task 6 opens the box from them.

- [ ] **Step 1: Write the failing tests** in `tests/orchestrator/agent/test_add_needs_name.py`, in the style of the runner
  tests in `tests/orchestrator/agent/`.
  - `test_a_chat_agent_add_waits_for_the_owner`: a chat-agent change adding department "Cafe site" →
    `pending_approval`, and the chart revision is unchanged. The card has
    `adds == [{"ref": "$a", "name": "Cafe site"}]` and its question comes from `LINES["approve_add"]`.
  - `test_naming_it_applies_the_add_under_that_name`: `runner.decide(id, True, names={"$a": "Cafe"})` → applied. The new
    team is named "Cafe", its folder is `Documents/Sutra Pro/Cafe`, and the stored plan resumes.
  - `test_a_plain_yes_uses_the_suggested_name`: answering the card with option `yes` applies "Cafe site" and makes its folder.
  - `test_declining_leaves_the_chart`: `decide(id, False)` → rejected, and no team or folder is made.
  - `test_a_name_in_use_is_refused_at_decide`: `names={"$a": "Pulse"}` with Pulse existing → 409 `name_taken`, and the
    change stays pending.
  - `test_a_reuse_and_an_owner_change_stay_auto`: `classify(reuse_change) == "auto"` and
    `classify(add_change, actor="user") == "auto"`.
  - `test_needs_you_carries_the_change_and_adds`: the approval row of `/api/needs-you` has `change_id` and `adds`.
- [ ] **Step 2: Run and see them fail.**
  - Run: `scripts/py -m pytest tests/orchestrator/agent/test_add_needs_name.py -q`
- [ ] **Step 3: Implement the server side** as in Interfaces. `_approval_question` gains an AddOp branch using
  `line("approve_add", name=names_phrase([...]))`. `_ask_approval` puts `adds` on the card.
- [ ] **Step 4: Write the failing UI tests.**
  - `front_door.test.js`: `"an approval that adds a project offers Name it and Not now"`. `needCard` of an approval item
    with `adds` has a button `data-act="name-add"` with `data-change`, `data-ref` and `data-name`, and the values are escaped.
  - `chat_view.test.js`: the same for `choiceCard` of type approval with `adds`.
- [ ] **Step 5: Implement the cards.**
  - The button handlers call `CreateProject.open({changeId, ref, name})` (task 6). The box posts to
    `/api/chart/changes/<id>/decision` with `{approve: true, names: {[ref]: name}, folder?, access}`, then goes to
    `/d/<result.refs[ref]>/`.
  - CUJ 3: on Attention, after a "Let Sutra choose" send, the first needs-you approval with `adds` opens the box by itself,
    once per `change_id`. `home.js` keeps the opened ids in its state, and the `chart.approval` event triggers the
    refetch. Add `"an add approval opens the box once"` to the Home tests that cover `decideFront`.
- [ ] **Step 6: Run the server and node tests; all pass.**
  - Run: `scripts/py -m pytest tests/orchestrator/agent -q`
  - Run: `node --test tests/ui/js/front_door.test.js tests/ui/js/chat_view.test.js`
- [ ] **Step 7: Commit** with the message `Sutra Pro: the org chat asks the owner to name a project before adding it (named projects 5)`.

### Task 6: Create project box (R1.1 to R1.4, R1.16)

**Files:**
- Create: `sutra_app/ui/static/js/create_project.js`, `sutra_app/ui/static/css/create_project.css`
- Modify: `sutra_app/ui/static/js/sutra_ctx.js` (`api` at :336-341: add `patch: (path, body) => send("PATCH", path, body)`)
- Modify: `sutra_app/ui/static/js/project_rail.js` (`onNew` :232-241 opens the box; the `#pr-new` href stays `/` for no-JS)
- Modify: `sutra_app/ui/pages/home.html` (script before `project_rail.js` at :145; CSS link near :9)
- Modify: `sutra_app/ui/static/js/dept_ext.js` (`rail()` :373-387 loads `create_project.js` and its CSS before the rail)
- Modify: `tests/ui/test_shared_css.py` (add the sheet to `SHELL_FAMILY` if that test requires every Home sheet)
- Test: `tests/ui/js/create_project.test.js` (new)

**Interfaces:**
- Consumes: `POST /api/teams` (task 3); the decision route with `names` (task 5);
  `window.sutraDesktop.chooseFolder(): Promise<string|null>`.
- Produces a UMD module `CreateProject` (the same IIFE and `module.exports` shape as `project_rail.js:26,400-404`):
  - `html(state) -> string`, where `state = {name, folder, access, typing, error, errorField, busy, win, desktop, suggest}`.
  - `canCreate(state) -> boolean`: true when the trimmed name is 1 to 80 characters, not busy, and not waiting on the trust question.
  - `savedIn(name, win) -> string`.
  - `open(opts?: {name?, changeId?, ref?}) -> {close}`: mounts on `document.body` and uses `SutraCtx.api`.

- [ ] **Step 1: Write the failing tests** in `tests/ui/js/create_project.test.js`.
  - `"the box has a title, a Project name field and a source folder"`: `html({})` contains "Create project",
    `<label for="cpname">Project name</label>`, `maxlength="80"` and "Source folder".
  - `"Create stays disabled until a name is typed"`: `canCreate({name: "  "}) === false`, `canCreate({name: "Pulse"}) === true`,
    and the button carries `disabled` when the name is empty.
  - `"no folder says where it is saved"`: `savedIn("Pulse", true) === "Saved in Documents\\Sutra Pro\\Pulse"` and
    `savedIn("Pulse", false) === "Saved in Documents/Sutra Pro/Pulse"`.
  - `"a picked folder asks the trust question"`: `html({folder: "C:\\x", typing: false, access: null, desktop: true})`
    contains "Allow Sutra Pro's team to read and edit files in C:\\x?", "Read and edit", "Read only" and "Cancel".
  - `"Add shows only in the desktop app; a browser gets a path field"`: with `desktop: false` there is no "Add" and there
    is an `<input id="cpfolder">`.
  - `"an error shows under its field"`: `errorField: "name"` puts the message under the name field with `role="alert"`.
  - `"a suggested name fills the field"`: `html({name: "Cafe site", suggest: true})` has `value="Cafe site"`.
  - `"wire strings are escaped"`: a name `<b>"x"</b>` appears escaped.
- [ ] **Step 2: Run and see them fail.**
  - Run: `node --test tests/ui/js/create_project.test.js`
- [ ] **Step 3: Implement.**
  - Markup: `role="dialog" aria-modal="true" aria-labelledby="cptitle"`. Focus goes to the name field. Esc and Cancel
    close the box and return focus. Tab is trapped as in `welcome.js:127-171`.
  - Add calls `chooseFolder()`; `null` changes nothing. A picked path shows the trust question.
    - Read and edit → `access: "edit"`.
    - Read only → `access: "read"`.
    - Cancel → the folder is cleared.
  - Create runs `api.post("/api/teams", {name, folder?, access})`. A rejection shows `ApiError.message` under the field
    named by `details.field` (`name` by default). Success sets `location.href = "/d/" + id + "/"`.
  - In decision mode (`changeId` set) Create posts to the decision route instead (task 5).
  - CSS uses the `--pr-*` tokens from `project_rail.css` with dark values. Below 600px the box is full width. No external URLs.
- [ ] **Step 4: Wire it in.** `project_rail.js` `onNew` calls `preventDefault` and `CreateProject.open()` when
  `root.CreateProject` exists, else the old behaviour. Update the `onNew` test in `project_rail.test.js` if one asserts
  the `/` link.
- [ ] **Step 5: Run the tests; all pass.**
  - Run: `node --test tests/ui/js/create_project.test.js tests/ui/js/project_rail.test.js`
  - Run: `scripts/py -m pytest tests/ui/test_shared_css.py tests/ui/test_port_edits.py -q`
- [ ] **Step 6: Commit** with the message `Sutra Pro: the Create project box with a name and a folder (named projects 6)`.

### Task 7: Rename and Delete in the ⋯ menu (R1.13, R1.15)

**Files:**
- Modify: `sutra_app/ui/static/js/project_rail.js` (`projectMenu` :275-285, `onClick` :287-311, `nameBox` :89-92,
  `finishName` :313-329, the ⋯ button's `aria-label` :101-103)
- Test: `tests/ui/js/project_rail.test.js`

**Interfaces:**
- Consumes: `PATCH /api/teams/{id}` and `DELETE /api/teams/{id}` (task 3); `SutraCtx.api.patch` (task 6);
  `SectionsStore.assign(doc, team, null)`.
- Produces: `ProjectRail.projectMenuHtml(project, sections) -> string`, exported for the test.

- [ ] **Step 1: Write the failing tests.**
  - `"a project's menu has Rename, Delete, then Move to section"`: the order of `data-pr` values is `teamrename`,
    `teamdelete`, then the move items.
  - `"Delete of a working project is disabled"`: a project in state `making` gives the Delete button `disabled` and the
    note "Working. Stop it first."
  - `"the menu button names the project"`: `aria-label="More for Pulse"`.
  - `"rename allows 80 characters"`: the team rename box has `maxlength="80"`, and sections keep 40.
- [ ] **Step 2: Run and see them fail.**
  - Run: `node --test tests/ui/js/project_rail.test.js`
- [ ] **Step 3: Implement.** `nameBox` takes a `max` argument.
  - Rename puts the name box in place of the row's name. Enter runs `api.patch("/api/teams/" + id, {name})` then
    `load()`. Esc cancels. A refusal shows in `.pr-err`.
  - Delete asks `root.confirm("Delete " + name + "? It leaves the sidebar. Its runs and files stay on disk.")`.
    Then it runs `api.del("/api/teams/" + id)`, removes the team from its section with `commit(ss.assign(doc, id, null))`,
    and calls `load()`. If the page is that team's (`ctx.dept === id`), it goes to `/`.
- [ ] **Step 4: Run the tests; all pass.** Same command.
- [ ] **Step 5: Commit** with the message `Sutra Pro: Rename and Delete in a project's menu (named projects 7)`.

### Task 8: "What should we make in <Project>?" (R1.8 to R1.10)

**Files:**
- Create: `sutra_app/ui/static/js/project_pick.js`
- Modify: `sutra_app/ui/static/js/dept_ext.js` (`init` :439-470 fills `#sgreet`; `j2_ui.html` is not edited)
- Modify: `sutra_app/ui/static/js/home.js` (fills `#fd-new-h`; `send` :600-633 and `sendFront` :923-939 route a project
  pick; the pick is loaded at boot)
- Modify: `sutra_app/ui/pages/home.html` (script tag before `home.js`)
- Modify: `sutra_app/orchestrator/api/teams.py` (`GET /api/teams/last` and `PUT /api/teams/last`)
- Test: `tests/ui/js/project_pick.test.js` (new); `tests/orchestrator/test_team_admin.py` (last-pick tests)

**Interfaces:**
- Consumes: `/api/departments` (visible teams only after task 3); `CreateProject.open` (task 6).
- Produces:
  - `GET /api/teams/last` → `{"dept": "<id>"|""}`.
  - `PUT /api/teams/last` `{dept}` → 200, with the token. The pick is stored in `last_project.json`, in the same folder and
    with the same atomic write as the sections file (`api/sections.py`). Browser storage is not used, because it is per
    port. A stored id that is hidden or unknown reads as `""`.
  - A UMD module `ProjectPick`:
    - `heading(projects, pick, {attention}) -> string`;
    - `menuHtml(projects, pick, {attention}) -> string`;
    - `mount(el, {projects, pick, attention, onPick}) -> {set, close}`. `onPick` receives an id, `""` for "Let Sutra
      choose", or `"+new"`.

- [ ] **Step 1: Write the failing server tests**:
  - `test_last_pick_round_trips`;
  - `test_a_hidden_last_pick_reads_as_none`;
  - `test_last_pick_needs_the_token`.
- [ ] **Step 2: Write the failing node tests** in `tests/ui/js/project_pick.test.js`:
  - `"a project heading names it as a button"`: the result is
    `What should we make in <button class="pp-name" aria-haspopup="menu">Pulse</button>?`.
  - `"Let Sutra choose reads What should we make?"`: `heading(P, "", {attention: true})` is the text
    "What should we make?", followed by a button "Let Sutra choose ▾".
  - `"the menu lists every project, then Let Sutra choose and New project on Attention only"`.
  - `"a team page menu has no Let Sutra choose"`.
  - `"a deleted last pick reads as Let Sutra choose"`: a pick that is not in `projects` gives the `""` heading.
  - `"names are escaped"`.
- [ ] **Step 3: Run both and see them fail.**
  - Run: `scripts/py -m pytest tests/orchestrator/test_team_admin.py -q`
  - Run: `node --test tests/ui/js/project_pick.test.js`
- [ ] **Step 4: Implement.**
  - **Team page.** `dept_ext.js` replaces `#sgreet`'s text with `heading(...)` for `boot.dept`. Picking another project
    goes to `/d/<id>/`; "+ New project…" opens the box.
  - **Attention.** `home.js` loads `/api/teams/last` and fills `#fd-new-h`. Each pick does a `PUT`. A send with a project
    pick calls `api.post("/api/say?dept=" + encodeURIComponent(id), {text, usd_budget?})`.
    - A 409 shows "<name> is working. Wait for it or stop it."
    - A 403 shows "This project was deleted." and resets the pick to `""`.
    - Success opens `/d/<id>/`.
  - **Let Sutra choose.** A `""` pick sends to `cs_org` as today.
  - `output_pick.js` keeps its "What should we make?" label under the box. Its tests pin it, and it labels the
    output-type choice, not the project.
- [ ] **Step 5: Run the tests, plus the pinned page and Home tests; all pass.**
  - Run: `node --test tests/ui/js/project_pick.test.js tests/ui/js/dept_ext.test.js tests/ui/js/front_door.test.js`
  - Run: `scripts/py -m pytest tests/orchestrator/test_team_admin.py tests/ui/test_port_edits.py -q`
- [ ] **Step 6: Commit** with the message `Sutra Pro: the start heading names the project and switches it (named projects 8)`.

### Task 9: A finished run writes its results into the project folder (R1.12, R1.14)

**Files:**
- Create: `sutra_app/engine/host/export.py`
- Modify: `sutra_app/engine/host/finish.py` (`STEPS`: append `("export", export.step)`)
- Test: `tests/engine/test_export_to_folder.py` (new; unit tests on a built run directory and one mock end-to-end run)

**Interfaces:**
- Consumes: `WorkFolder(data, dept_id=...).grant()`, the team's own folder with no app-wide fallback (task 1);
  `j2_artifacts.listing(run_dir)` and `groups(run_dir)`.
- Produces:
  - `deliverable_files(run_dir: Path) -> list[str]`: relative paths with `/`.
    - Included: each deliverable row's `file`, the sibling `<name>.docx` when it exists, and every file of a folder row
      (`kind == "folder"`).
    - Excluded: anything matching `*.json`, `*.jsonl`, `site/**`, `out/**`, dotfiles and symlinks.
  - `Manifest`, stored at `<folder>/.sutra/manifest.json` as `{"version": 1, "run_id": str, "files": {path: sha256}}`.
    It has `load(folder) -> Manifest`, where a missing or bad file gives an empty manifest, and an atomic `save(folder)`.
  - `export_run(run_dir: Path, folder: Path, run_id: str) -> ExportResult`, a frozen dataclass with
    `new, updated, unchanged, outside, failed` (lists of paths).
    - A target that is absent is written (`new`).
    - A target whose sha equals the manifest's is written only if the content differs (`updated`, else `unchanged`).
    - A target that exists and either is not in the manifest or has a sha that differs from it is not touched (`outside`).
    - An `OSError` on one file adds it to `failed` and moves on.
    - Each write goes to a temp file, then `oslayer.replace`.
    - A path that resolves outside `folder` is skipped.
  - `step(host) -> dict | None`, a `finish` step.
    - The team has no own folder, or its grant has `edit` False: raise `Skip("no project folder")` or
      `Skip("the project may only read its folder")`.
    - The folder is missing: post "Not saved: <folder> is not there any more" and skip.
    - Otherwise write `<run>/export.json` as `{"folder", "new", "updated", "unchanged", "outside", "failed"}`.
    - Post "Saved to <folder>: <n> files (<a> new, <b> updated)." when `a + b > 0`.
    - Post one line per `outside` file, at most 10, then "and <k> more".
    - Name `failed` files as "Not saved: <file> could not be written".
    - Return the counts for the trace.

- [ ] **Step 1: Write the failing tests.**
  - `test_deliverables_go_to_the_folder_under_the_same_paths`: a run dir with `prd.md`, `prd.docx`, `pulse_app/main.py`
    (a folder row), `goal.json` and `site/index.html` exports `prd.md`, `prd.docx` and `pulse_app/main.py` only. The
    manifest has those three.
  - `test_a_file_sutra_never_wrote_is_untouched`: `notes.md` already in the folder, and a deliverable also named
    `notes.md` → the folder's `notes.md` keeps its bytes and is in `outside`.
  - `test_a_file_changed_since_sutra_wrote_it_is_not_overwritten`: export, edit `prd.md` in the folder, export a new
    `prd.md` → the folder keeps the owner's edit, and the result lists `prd.md` in `outside`.
  - `test_an_unchanged_file_is_not_rewritten`: export twice → the second run has `unchanged == [...]` and the mtime is
    unchanged.
  - `test_a_locked_file_is_skipped_and_named`: patch `oslayer.replace` to raise `PermissionError` for one path → that
    path is in `failed` and the others are written.
  - `test_a_vanished_folder_is_reported_not_made`: `step` with a granted folder that was removed → the chat line
    "Not saved: … is not there any more", and the folder still does not exist.
  - `test_a_read_only_project_folder_gets_nothing`: `step` raises `Skip`.
  - `test_a_finished_mock_run_writes_into_the_team_folder` (with the `j2` and `make_run_dir` fixtures, as in
    `test_engine_project.py:143`):
    - team `web` has an edit folder;
    - after the run, the deliverables are there;
    - `export.json` exists;
    - the chat has a "Saved to" line.
  - `test_a_stopped_run_writes_nothing`: the same run stopped through the inbox stop line → the folder stays empty and
    there is no `export.json`.
- [ ] **Step 2: Run and see them fail.**
  - Run: `scripts/py -m pytest tests/engine/test_export_to_folder.py -q`
- [ ] **Step 3: Implement** `export.py` and the `finish.py` step.
- [ ] **Step 4: Run the new tests and the finish and project tests; all pass.**
  - Run: `scripts/py -m pytest tests/engine/test_export_to_folder.py tests/engine/test_engine_project.py tests/engine/test_engine_deliverable.py -q`
- [ ] **Step 5: Commit** with the message `Sutra Pro: a finished run saves its results into the project folder (named projects 9)`.

### Task 10: Decisions and docs

**Files:** `docs/DECISIONS.md`, `docs/diagram/decisions.json`, `docs/design/ui.md`, `docs/design/library.md:219,639` (DL5)

- [ ] **Step 1:** Fetch, then add the decisions with the next free numbers (expected D425 to D428):
  - D425 "A working folder no longer selects project work" (amends D129, D165, D253; source: the 19 Nov run).
    Label "folder = where the team works, not project work". Anchor `"Department records"`.
  - D426 "The owner makes, renames and hides projects without a model call" (amends DL5: hidden, never removed).
    Anchor `"One global org chart"`.
  - D427 "The org chat asks the owner to name a project before adding it" (amends D68). Anchor `"Chat agent (orchestrator)"`.
  - D428 "A finished run saves its results into the project folder, guarded by a manifest". Anchor `"band:DEPARTMENT RUNTIME"`.
- [ ] **Step 2:** In `docs/design/ui.md`, add the Create project box, the ⋯ menu, and the heading with its dropdown.
  Amend DL5 in `library.md` with a pointer to D426. Write no release notes, because no release is asked for (Q6).
- [ ] **Step 3:** Run the doc checks and every test file named in tasks 1 to 9; all pass.
  - Run: `scripts/py -m pytest tests/test_diagram_decisions.py tests/test_ownership.py -q`
- [ ] **Step 4: Commit** with the message `Sutra Pro: decisions D425 to D428 for named projects`.

### Task 11: Local check of CUJs 1 to 5, push the branch (S1)

- [ ] **Step 1:** Start the server from the worktree with a throwaway data folder in the scratchpad, never `~/.sutra-pro`.
  Use the command in `docs/GETTING-STARTED.md`, with its data-dir setting. Mock mode (`STUDIO_MOCK=1`) keeps runs from
  spending credits.
- [ ] **Step 2:** Walk CUJs 1 to 5 in a browser and note each pass or fail:
  1. Create "Pulse" with a folder (Read and edit); the page asks "What should we make in Pulse?".
  2. Pick Pulse on Attention and send; the run starts in Pulse.
  3. "Let Sutra choose" with a prompt that fits no project opens the box with a suggested name. This needs a model, so
     check it with the scripted connector the agent tests use, or note it as not verified.
  4. After a mock run, the folder has the deliverables and `.sutra/manifest.json`.
  5. Rename to "Pulse pilot"; delete a second test project, confirm, and its folder stays.
- [ ] **Step 3:** `git fetch origin && git merge origin/main`, rerun every test file named in tasks 1 to 10, then
  `git push origin named-projects` (with `env -u GITHUB_TOKEN -u GH_TOKEN` if the push is refused).
- [ ] **Step 4:** Rollback note: migration v9 makes a plain revert unusable on a migrated database (an older app refuses a newer schema);
  roll back by a revert that keeps `DDL_V9_HIDDEN_TEAMS` (D426).
- [ ] **Step 5:** Stop. Report to the owner: the commit, the CUJ results, what was not verified, and that the beta try on
  the Mac (`scripts/py scripts/install_app.py beta`) gates the merge to `main` and Phase 2.

## Phase 2: the next prompt continues from the project folder

Starts only after the owner passes CUJs 1 to 5 in the beta (S1).

| # | Task | Impact | Effort |
|---|---|---|---|
| 12 | A follow-up of any finished run continues it | the charter and decisions carry over | 4 h |
| 13 | The follow-up starts from the folder's files and writes back only changes | "keep building on top of it" | 4 h |
| 14 | Two-run proof | CUJs 6 and 7 | 2 h |
| 15 | Beta try, push to main | the owner uses it | 1 h |

### Task 12: Continue any finished run (R2.1, R2.7)

**Files:** `sutra_app/engine/rehydrate.py` (`check_source` :253-286), `sutra_app/engine/host/loop.py` (`_seed` :537)
**Test:** `tests/engine/test_rehydrate_any_output.py` (new)

- [ ] **Step 1: Write the failing tests.**
  - `test_a_finished_folder_output_run_is_rehydrated`: a done run with `goal.json`, `workflows.json`, a chat header and a
    `pulse_app/` folder row, but no page or chain → `check_source` returns, and `pulse_app/` is restored with the rest.
  - `test_a_finished_project_run_is_rehydrated`: the same for a `project.md` run.
  - `test_an_unfinished_run_is_still_refused`: "the earlier run was stopped before it finished".
  - `test_a_run_without_a_charter_is_still_refused`.
- [ ] **Step 2:** Run the tests and see them fail.
- [ ] **Step 3: Implement.** Replace the "no page and no document chain" refusal: a run is continuable when it finished
  with `goal.json` and `workflows.json`. Keep the chain and page checks for runs that have them. Restore every folder row's
  folder.
- [ ] **Step 4:** Run the tests and the existing rehydrate tests; all pass.
- [ ] **Step 5: Commit.**

### Task 13: Start from the folder, write back only changes (R2.2 to R2.6)

**Files:** `sutra_app/engine/host/loop.py` (`_seed`), `sutra_app/engine/host/export.py`
**Test:** `tests/engine/test_export_to_folder.py`

**Interfaces:** `import_from_folder(folder: Path, run_dir: Path) -> list[str]` in `export.py`.
- It copies each manifest path from the folder into the run dir, overwriting the restored copy, and returns the paths
  whose bytes differed (the owner's edits).
- Only manifest paths are read, never other files (R2.4).
- The manifest is then re-based on the copied files, so an owner edit counts as Sutra's baseline for the write-back.

- [ ] **Step 1: Write the failing tests.**
  - `test_a_follow_up_starts_from_the_owners_edit`: export, then edit `pulse_app/digest.py` in the folder. Use a `.py`
    file because `*.json` deliverables are not exported. Then `import_from_folder` → the run dir has the edit, and the
    return value lists it.
  - `test_files_sutra_never_wrote_are_never_read`: `secret.txt` in the folder is not copied.
  - `test_only_changed_files_are_written_back`: after the import, change one file in the run and export → `updated` has
    one path, every other file is byte-identical, and nothing is deleted.
  - `test_the_chat_names_the_changed_files`: "Changed in Pulse: pulse_app/digest.py".
- [ ] **Step 2:** Run the tests and see them fail.
- [ ] **Step 3: Implement.** `_seed` calls `import_from_folder` after a successful rehydrate when the team has its own
  folder. Export reports changes with "Changed in <name>: …" (at most 10 paths).
- [ ] **Step 4:** Run the tests; all pass.
- [ ] **Step 5: Commit.**

### Task 14: Two-run proof (CUJs 6 and 7)

- [ ] **Step 1:** Write `tests/engine/test_named_project_two_runs.py`, a mock run end to end:
  - Run 1 builds and exports `pulse_app/`.
  - The test edits one folder file by hand.
  - Run 2 ("change the digest time to 08:30", `seed_from` run 1) rehydrates, starts from the hand edit, and changes one file.
  - Assert: the trace has `seed.*` lines; only the changed file's sha differs from the manifest before; all other files
    are byte-identical; run 1's files are still in its run history.
- [ ] **Step 2:** Run the test; it passes.
- [ ] **Step 3:** Add decision D429, "A follow-up continues any finished run and edits the project folder in place".
- [ ] **Step 4: Commit.**

### Task 15: Beta try, push

- [ ] **Step 1:** On the Mac: `scripts/py scripts/install_app.py beta`. Walk CUJs 6 and 7 with a real Pulse project.
- [ ] **Step 2:** `git fetch origin && git merge origin/main`, rerun the Phase 1 and Phase 2 test files, then
  `git push origin named-projects:main`.

## Calls made in this plan (owner to check)

| # | Call | Why |
|---|---|---|
| C1 | A team folder that vanished falls back to the app-wide folder for chats and runs, but results are saved only to the team's own folder | results must never land in another project's folder |
| C2 | A Read only project folder gets no results written | Read only caps what Sutra may do there (Q10) |
| C3 | A plain "yes" to the org chat's add card creates the project under the suggested name | the owner saw the name and said yes; the box is there to change it |
| C4 | The last Attention pick is stored on the server, not in the browser | browser storage is per port and would not survive a restart (R1.9) |
| C5 | Owner-typed names skip the similar-name reuse check; exact duplicates are still refused | the check exists to stop the model from making near-copies |
| C6 | `site/` and `out/` are not exported, as the PRD says, so a website run's `site/index.html` does not reach the folder | follow the PRD; revisit if the owner wants websites exported |
| C7 | No release notes in Phase 1 | no release is asked for (Q6) |
