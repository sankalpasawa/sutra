# Devin parity: developer notes (DV-2 and DV-3)

Branch `feat/sutra-pro-devin-parity`, cut from the head of `feat/sutra-pro-agent-nodes` (c138f633). Author: developer, 2026-11-20. The architect's analysis is [devin-parity.md](devin-parity.md); DV-1 (Ask) is built by another
developer in its own worktree and is not here. Decisions are numbered from D360 so that they do not meet the ones the Ask branch adds (D350 to D353): no renumbering is needed when the branches meet (D364, [merge-plan-nodes-devin.md](merge-plan-nodes-devin.md)). This file is named for its two packages because the Ask branch has its own `devin-parity-dev-notes.md`; two files of one name would conflict when the branches meet.

## What was built

| Package | Flag | Migration | Routes | Page | Tests |
|---|---|---|---|---|---|
| DV-2 Work list, tags, "How did it go?" | `SUTRA_WORK_V1` | v7: `work_tags` | `GET /api/work`, `GET /api/work/tags`, `PUT /api/work/{kind}/{id}/tags`, `GET /api/projects/{id}/summary` | `/work` | `tests/orchestrator/test_work.py`, `tests/ui/js/work_view.test.js`, `work_page.test.js` |
| DV-3 Recipes | `SUTRA_RECIPES_V1` | v8: `recipes`, `recipe_versions` | `GET/POST /api/recipes`, `GET/PUT /api/recipes/{id}`, `revert`, `archive`, `copy`, `export`, `import`, `start`, `POST /api/projects/{id}/save-as-recipe` | `/recipes` | `tests/orchestrator/test_recipes.py`, `tests/ui/js/recipe_view.test.js`, `recipe_page.test.js` |

## Flag off is byte-identical

Each package mounts its routes and its page only when its own flag is on (`create_app`): with a flag off the paths do not exist, so the framework answers 404 before any token check, the route table is what it was and no contract
test moves. The migrations v7 and v8 only add tables (nothing reads them with the flag off; backup and restore carry them like any table). The flags are not in `Settings.public()`. No prompt, schema, golden or API shape changed.
`tests/orchestrator/test_work.py` and `test_recipes.py` each start with the flag-off test (no route, no page, no home-page link, the table is empty).

## Decisions (made without asking; also in `docs/DECISIONS.md`)

- **D360. The Work list (DV-2).** (a) One list of tasks and, with `SUTRA_NODES_V1` on, projects; a task that is a step of a project is listed under its project, not alone. (b) A tag is the owner's plain word: lower case, 1 to 30
  characters of letters, digits, spaces, `-` and `_`, at most 8 for an item; it passes the note gate (`owner_words.refusal`), so a key, a token or a password is refused and never echoed. The whole set is replaced in one `db.tx()`.
  (c) "How did it go?" (`GET /api/projects/{id}/summary`) is computed by code from rows that exist (the usage ledger by the chain of a step's tasks, the node tables, the approvals, the audit): credits are model calls (D324),
  dollars what the providers reported, minutes from the first start to the end, what was tried again, how many questions and how many Sutra answered, scope notices, where steps got stuck and why it stopped, as plain sentences. A model
  writes none of it: the optional "model sentence" of the design is NOT built (it would spend quota and adds nothing the code cannot say). (d) NO navigation item in the Home FILE: a fixed item would change the Home page with the flag off; since the review the server adds a row at serve time only while the page is mounted (D366). (e) The summary is not on the project page; it is on `/work` ("How did it go?" on a project). (f) Search is by words in the title and the request (every word, any case), done in code over the rows: it is a few
  thousand rows at most on one computer; no index and no full-text table were added.
- **D361. Recipes (DV-3).** (a) A recipe has a title and six parts: overview, procedure (1 to 30 lines, at least one), specifications, advice, forbidden (each at most 20 lines), and needs (at most 9 blanks). `$1` to `$9` in any
  text stand for the needs, in order; a `$n` with no need is refused. Every line passes the note gate and is at most 300 characters. (b) Versions only grow: `recipe_versions` has triggers that forbid update and delete; a change
  is a new version, a revert is a new version with an old version's words. (c) Starting writes a REQUEST in plain words (title, overview, numbered steps, the result must be like this, good to know, "Never do these") and posts it
  as the owner's line in the org chat, with a `client_id` (a repeat sends once). Nothing is frozen: the chat agent plans it again, the plan gate asks what it asks, the owner's access caps what a step may touch (P14), Decide for me is
  still the only auto-answer. Starting works with or without the nodes. (d) "Forbidden maps to never" was read as: the lines go into the request as "Never do these"; NO standing rule is created behind the owner's back (a standing rule
  is the owner's own choice in the Rules page). (e) Starters are in code, not rows: four read-only recipes (Review my last commits, Weekly folder health, Write release notes, Explain this folder); they cannot be changed or put
  away; "Make a copy to change" makes an ordinary recipe. Only one of them (release notes) writes, a NEW file, and says never to overwrite. (f) Only the owner writes, changes or imports a recipe. Reading a Markdown file
  (`POST /api/recipes/import`) returns a DRAFT that has passed the same checks and saves nothing; the owner reads it and presses Save. A draft from a finished project (`POST /api/projects/{id}/save-as-recipe`) is made by code
  from the project's title and its steps' titles; "a model drafts" is NOT built (no quota, and a model draft is a model's words in a place a model must not write). (g) Export is Markdown with a download name made of letters.
- **D362. Rules for both.** Routes and pages exist only with their flag (mounted in `create_app`, not guarded after the fact); the migrations are additive and in order (v7 work, v8 recipes; the nodes had v6); one writer through
  `db.tx()`; owner words only ("Recipe", "Work", "How did it go?"; no playbook, cron, node, lease, tier; a test scans the drawn words); the JS has the layers of the project page (a pure view, a page controller with injected
  fakes) and node tests for each.

## Deviations from devin-parity.md

1. No fixed navigation item for Work or Recipes in the Home file (D360 d); since the review round Home gets a row for each, added at serve time only while that page is mounted (D366).
2. No optional model sentence in the summary and no model draft of a recipe (D360 c, D361 f).
3. "Forbidden maps to never" is a line in the request, not a standing rule (D361 d).
4. Recipes are started through `post_user_message` with a `client_id` (the route of `POST /api/projects`), so a started recipe is an org chat request whether or not the nodes are on.
5. DV-2's summary needs the nodes (it is about projects); the list works without them.
6. Starters are code, not seed rows (D361 e): there is no sync to do.

## Not verified

No real model run: starting a recipe was tested to the point of the owner's line in the chat (the planner is the existing one, tested elsewhere with fakes). No real browser: the two pages have node tests for their view and
controller and a route test that every file they name is served; the layout at phone width, dark and light, and a long list were NOT looked at (the project page's check in the beta is the pattern to repeat). The beta app was
not rebuilt for this branch.

## Architect's rulings (D363)

The five departures stand. The conditions, as a list for the developer; each is small and none changes a flag-off byte:

1. **DV-2b and DV-3b, a way in.** No page or script links to `/work` or `/recipes`, and the desktop window has no address bar, so the pages cannot be reached in the app (the text of D360 d, "from the links on a project's note and card", is not true in the code). At serve time the server adds one line of links ("Work", "Recipes", each only when its flag is on) to the Home HTML; with both flags off the served bytes are what they were; a test compares them to the page file. The project page may show "How did it go?" and "Save as a recipe" only when the route answers (404 means the flag is off, so no link).
2. **Words.** Starters: "ships with Sutra, cannot be changed" (not "read only"). Under "Never do these": "This is told to the planner. It is not a lock: your folder access setting is the lock." The summary's minutes: "from the first start to the end".
3. **A test** that starting a recipe adds no standing rule (count the rows before and after).
4. **A test** `test_schema.py`: the "newer database" case uses `SCHEMA_VERSION + 1`, not `9`.
5. **Not verified, still:** no real browser, no real planner, the beta was not rebuilt. Look at both pages in the beta built from this branch (dark and light, a long list, phone width), and start one starter with a real planner, before anything is said to be working.


## The review round (DV-2 and DV-3: 4 majors, 11 minors; D365 to D367)

Every item has a test that fails without it (the tests are in `test_work.py`, `test_recipes.py`, `work_view/page.test.js`, `recipe_view.test.js`).

- **DV-2:** the Work list hides every attempt of a retried step (the whole `parent_task_id` chain, the CTE of `project_spend`), filters and pages in the database (`LIKE` with `%` and `_` as letters, `EXISTS` on the tag table, the page's own tags read afterwards); the summary's minutes start at the first attempt of any step, and its words say that any time asleep or closed is in them; steps are named by their task's title; "tried again" counts the audit's `node.retry` rows (a restart after Sutra was closed and a send-back by the reviewer are said apart); the server gives each node state its owner word; dollars are shown for each step; the page says "Showing the newest 200" and offers Show more (up to 800); the search box holds 200 characters and keeps its caret.
- **Tags:** the secret gate runs on what was typed, before lower-casing (the shapes of keys use capitals); no refusal repeats the tag; a tag is letters of any language, digits, spaces, `-` and `_`.
- **DV-3:** hidden text is refused in every line, title, blank and imported file (`owner_words.hidden_text_refusal`: the categories `Cf`, `Co`, `Cs`, `Cn`, except the two joiners that some languages need); `$$` is one dollar sign; a recipe that could never start (the request with every blank at 300 characters over 7,900) is refused when it is saved; `list` is one query; "Save as a file" sends an ASCII name and the real name in `filename*=UTF-8''`.
- **Architect's rulings:** Home rows (D366); the start form says a recipe is words, not a lock; a test that starting one makes no approval and no rule; the starter label says "cannot be changed"; the schema pin follows `SCHEMA_VERSION`; the flag-off route table is tested to equal the flag-on one minus the new paths.
- **Static files:** the four scripts and two style sheets are in the static folder and are served at `/ui/js/...` with the switches off. No page or route loads them and nothing is read; "nothing exists" is true of routes, pages, tables read and Home, not of those six files (D362 says so now).

## Verification (M1, the migration on a copy of real data)

On 2026-11-20 a read-only copy of the stable app's database (`~/.sutra-pro/db.sqlite3`, version 5, 9 tasks, 720 chat messages, 2.4 MB, made with SQLite's backup call through a read-only connection) was put in a temp folder and migrated by the code of this branch: version 5 to 8 in 2 ms; every table that was there keeps its row count; the 8 new tables (the nodes' five, `work_tags`, `recipes`, `recipe_versions`) are there empty; `PRAGMA integrity_check` ok, no foreign-key problem, the `lane` column and the two recipe triggers are there; a second run does nothing. On a second copy in a throw-away data folder `backup.before_upgrade` wrote `backups/pre-upgrade-v5-to-v8.sqlite3` (2.5 MB, mode 600, version 5, integrity ok) before the migration and wrote nothing the second time. The copies were deleted afterwards; the original and the stable app were not touched. NOT done: a restore of that backup, and a start of the real app on the copy.
