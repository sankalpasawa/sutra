# Devin parity: what we take from Devin, and what we leave

Status: accepted by the owner's standing rule (decide, document). Author: solution-architect, 2026-11-20. Design only.
Paths are relative to `sutra-pro/`. "Today" = read in the code. The nodes work (MAN-1..15) is built behind `SUTRA_NODES_V1` and is not yet seen live.
Source: https://devin.ai/ and docs.devin.ai (llms.txt and the pages listed at the end).

The owner asked: take inspiration from Devin and make sure Sutra Pro has the functions Devin has.
Answer: we build the functions that fit a local-first desktop app, as small packages DV-1..DV-13, each behind its own flag (default 0). We skip what needs a cloud, a public address, a stored token, or pushing code.

Verdicts: ADOPT (as Devin does), ADAPT (local-first shape), ALREADY HAVE, SKIP.

## 1. Devin vs Sutra Pro

| Capability | Devin | Sutra Pro today | Verdict | Package |
|---|---|---|---|---|
| Each session in its own cloud VM | yes | each team run is its own local process and run folder | SKIP VM; process isolation ALREADY HAVE | none |
| Works with the laptop closed | cloud | no: a closed laptop is a refusal (D296) | SKIP; only stay-awake against idle sleep | DV-12 |
| Parallel child sessions with a coordinator | yes | projects with nodes (flag off, not seen live) | ALREADY HAVE | finish the beta |
| Per-child skill, tags, spend limit | yes | prompt and credit slice per node; no skill, no tags | ADAPT | DV-2, DV-3 |
| Message, pause, stop children | yes | pause, stop, kill, steer exist | ALREADY HAVE | none |
| Mix frontier models per task | yes | two providers, per-session pick, reviewer uses the other provider | ALREADY HAVE; per-step pick in the plan | DV-4 |
| Session list, tags, search, timeline | yes | chat search, team find, task list, project page; no project list, no tags | ADAPT | DV-2 |
| Session Insights | yes | usage console, atom log, run views; nothing per project | ADAPT | DV-2 |
| Budgets and spend limits | yes | monthly dollar limit, plan guard, per-node and per-project caps | ALREADY HAVE | none |
| Ask Devin (cited answers) | yes | direct chat reads the folder; no citation check, no "turn into work" | ADAPT | DV-1 |
| Interactive Planning | plan reviewed before code; timer | plan gate asks only for cost or risky grant | ADAPT, no timer | DV-4 |
| Playbooks / Skills | yes, from sessions | J2 playbooks are website-shaped; run templates off; team rules | ADOPT as "Recipes" | DV-3 |
| Knowledge / Memory | suggestions, dedupe, dreaming | owner notes, team rules, J2 lessons | ADAPT suggestions; SKIP dreaming | DV-11 |
| Wiki, DeepWiki, diagrams | yes | none for code | ADAPT | DV-7 |
| Machine snapshots | yes | none | SKIP; folder profile goes in the wiki | DV-7 |
| Scheduled sessions | cron, one-time | recurring per team (`recurring.py`) | ADAPT, no cron text | DV-6 |
| Triggers Slack/Teams/Linear/Jira/alerts/webhooks | yes | none | SKIP (P15, loopback, no tokens) | none |
| Triggers GitHub PR/issue/CI | yes | read tools exist, nothing polls | ADAPT read-only polling | DV-9 |
| Notifications | Slack, email | browser notices; none with no tab open | ADAPT native notices; SKIP Slack, email | DV-6 |
| Devin Review | bugs, flags, security, fix | reviewer node (verdict only) | ADAPT | DV-5 |
| Code scans, Security Swarm | yes | none packaged | ADAPT as read-only recipes | DV-10 |
| Browser testing with video | yes | J2 Audit screenshots for builds | ADAPT screenshots, no video | DV-8 |
| Opens PRs, comments, statuses | yes | Sutra never pushes (D1, D11, P15) | SKIP | none |
| Parallel git worktrees | yes | write scopes and leases; worktrees deferred (D261) | ADAPT later | DV-13 |
| MCP marketplace, public API, secrets vault, Computer Use, voice, IDE | yes | own read-only MCP server; local API with token | SKIP | none |
| Audit logs | yes | node audit, egress audit, atom ledger, tool audit | ALREADY HAVE | none |
| RBAC, SSO, SCIM | yes | one owner; owner's access caps every grant (P14) | SKIP | none |

Notes: the Devin docs give severity and finding types for Review, not a confidence score; "confirmed by code" in DV-5 is our own design. Devin is itself merging ideas (Playbooks into Skills, Knowledge into Skills, Scheduled Sessions into Automations); we build one Recipe, one notes, one schedule idea.
Name clash: J2 already has "playbooks" (a lesson file per business type, `engine/j2.py`). The owner-facing word is **Recipe**.

## 2. Rules that decide verdicts

P8 local data, D1 and D11 (no cloud service, loopback only, never pushes); P12 one database writer; P14 owner caps every grant, a feature may only narrow; P15 external send off (no Slack, Teams, Jira, Linear, no GitHub comments, statuses or labels); D296 closed laptop is a refusal (silence is a refusal, so no auto-proceed timer); a model never approves a model (labels meaning true or allowed come from code or the owner); flag off is byte-identical (no table read, route 404 before the token, no prompt or golden change); releases never Latest, beta first; simple language.

## 3. Hard-row verdicts

- Laptop closed: SKIP. No clean local trick. DV-12 stops idle sleep only.
- Slack, Teams, Jira, Linear, webhooks: SKIP (posting is P15; receiving needs a public address or stored token).
- GitHub: ADAPT read-only. Through the owner's own `gh` login and the tier 4 read tools; polls only while the app is open; never writes; issue and PR text is untrusted data and never starts work by itself, the owner presses Start.
- Pull requests: SKIP. Local version: a team changes your folder, a reviewer checks it, you commit.
- Video: SKIP. Captioned screenshots answer the same question.
- Plan timer: SKIP (D296).
- Dreaming: SKIP (model approving a model).

## 4. Roadmap

Each package: own flag default 0, additive migration only, beta app first, gate in the foreground, never Latest.

### DV-1. Ask: cited answers, read only (ADAPT of Ask Devin) — size M, flag `SUTRA_ASK_V1`
Value: ask about your folder and get an answer where every claim points to a file and lines, and Sutra says which citations it could check.
Reuses: direct chat route (`orchestrator/api/chat_v2.py`), `chat_ground.py`, read-only folder grant (`connectors/workdir.py`), limits of `agent_ask.py` (2 calls, $0.25, 120 s), secret scrub, egress audit, `tool_kinds.py`.
New: pure module `orchestrator/citations.py` reads `[path:line-line]` marks and checks each by code (file exists, inside the folder, range exists, optional quote on those lines): label "checked" or "could not find". The model never labels itself. A composer switch Ask | Do (`mode=ask` forces read access). An answer card (additive `ChatCard` kind) with sources. A "Turn this into work" button that drafts a request the owner edits and sends. No new table.
Stays the same: direct chat without `mode`, its grounding text byte for byte, the owner's access cap, all write paths.

### DV-2. Work list, tags, "How did it go?" (ADAPT of session management and Insights) — M, `SUTRA_WORK_V1`
Value: one page lists everything Sutra did, lets you label and search it, and tells you in plain words what a finished project cost and where it got stuck.
Reuses: `GET /api/projects`, `tasks`, `ChatSearch`, `TeamFind`, `UsageStore`, `node_audit`, atom ledger, heads-up, the console JS.
New: table `work_tags(item_kind, item_id, tag)`; page `/work` (nav item only with the flag); `GET /api/work?tag=&q=&status=`, `PUT /api/work/{kind}/{id}/tags`, `GET /api/projects/{id}/summary` (calls, minutes, dollars by step, retries, questions, scope notices, why it stopped; computed by code; an optional model sentence is propose-only, off by default, capped).
Stays the same: task and project tables, existing pages, usage console. Projects half needs MAN-13.

### DV-3. Recipes (ADOPT of Playbooks and Skills) — M, `SUTRA_RECIPES_V1`
Value: save a finished project as a recipe (steps, rules, blanks) and start it again with one click.
Shape: sections Overview, Procedure, Specifications, Advice, Forbidden, Needs from you; revertible versions; `$1`-style blanks.
Reuses: the planner (re-plans on each start, no frozen graph in v1), `POST /api/projects` or `POST /api/tasks`, `standing_rules.py` (Forbidden maps to never), the note gate in `notes.py` (secrets refused, limits), `team_find.py`, the seed-sync pattern of the template library (D144).
New: tables `recipes`, `recipe_versions` (append-only); `GET/POST /api/recipes`, `POST /api/recipes/{id}/start {blanks}`, `POST /api/projects/{id}/save-as-recipe` (a model drafts, the owner edits and saves); page `/recipes`; read-only starter recipes ("Review my last commits", "Weekly folder health", "Write release notes", "Explain this folder"); Markdown export and import by owner action only.
Risk: a recipe becomes request text, so an imported one is a prompt-injection door: only the owner writes or imports one, a model draft is never saved by itself, the plan gate runs on every start.
Stays the same: planner schemas and prompts, run templates, J2's playbooks.

### DV-4. Plan first (ADAPT of Interactive Planning) — M, `SUTRA_PLANFIRST_V1` (needs nodes)
Value: see the whole plan (who does what, what each step may touch, what it may cost), change it, then press Start. No timer: silence means nothing starts.
Reuses: the plan gate and `approvals` (`gatekeeper.evaluate`), `caps_json["plan"]`, node plan, `ProjectService.answer`, project page cards, DV-1's checker.
New: approval kind `plan_review` (allow once or deny); owner edits while `awaiting_approval` (drop a step, lower a slice, narrow a scope, pick a lighter or deeper effort per step); `PATCH /api/projects/{id}/plan` re-runs `evaluate` on every edit and refuses any edit that widens a grant (D306, P14); a setting "Always show me the plan" (default off) and a per-request switch.
Stays the same: with the setting off the gate asks exactly as today; Decide for me is still the only auto-answer; what a no does (D315).
Waits for the nodes beta to run real projects.

### DV-5. Review findings with code-checked labels (ADAPT of Devin Review) — M, `SUTRA_FINDINGS_V1` (needs nodes and reviewer)
Value: a review lists each problem with file, line, kind, how serious, and whether Sutra's own code could confirm it; a "Fix this" button hands one to the right team.
Reuses: reviewer node and verdict file, change list from git (`folder_watch.py`), the `inspect` grant, `GithubTools` (to read a PR diff the owner names), the review-loop question.
New: library family `findings/1` (file, line range, kind `bug|risk|security|note`, severity, why max 300 chars, quoted line max 200); code checker `orchestrator/finding_check.py` (file in change list, lines in a changed hunk, quote present): labels "confirmed by code", "could not confirm", "not in this change"; table `findings` (status open, fix_started, fixed, dismissed; only the owner, or the server when a fix task ends done, moves it); Findings panel on the project page; `GET /api/projects/{id}/findings`, `POST /api/findings/{id}/dismiss`, `POST /api/findings/{id}/fix` (drafts a follow-up task; the owner presses it).
Stays the same: the reviewer stays read only; its verdict only informs (D330, D338); works with no findings.
Needs G25 first.

### DV-6. Schedules v2 and real desktop notices (ADAPT) — M, `SUTRA_SCHEDULES_V2`, `SUTRA_NOTIFY_V1`
Value: run a recipe or project on a schedule or once at a set time, and get a native desktop notice when something needs you, even with no browser tab open.
Reuses: `recurring.py` (catch-up, busy skip, pause after 3 crashes), `TaskService.create_scheduled`, `attention_prefs.py` (quiet hours, hourly cap), `needs_you`, the desktop shell.
New: `recurring` gains `kind` (`task|recipe`) and `every` gains `once` (with a date) and `month` (one additive migration with defaults); a scheduled recipe that reaches a plan gate with nobody home does not start (D296) and the row says so; native notice on macOS and Windows obeying quiet hours.
Stays the same: existing schedules, catch-up rule, the web-only app.

### DV-7. Folder wiki (ADAPT of Wiki and Codemaps) — L, `SUTRA_WIKI_V1`
Value: a plain guide to your folder (what each part does, how parts connect, with a diagram), kept up to date, so a question or plan starts from a map.
Owner-started with a cost estimate first; lives in the data folder, never in your folder.
Reuses: engine capability registry (D126) to add a read-only output type `wiki` without touching vendored J2; the read-only grant; the existing d3 graph drawing; the git wrapper in `folder_watch` to mark a page stale when the commit moved.
New: files under `<data>/wikis/<folder id>/`; index in `meta` (no migration); page `/wiki`; `GET /api/wiki`, `GET /api/wiki/pages/{slug}`, `POST /api/wiki/refresh` (estimate card first; only changed parts); a folder profile page (how to install, test, run) editable by the owner. The new output type is registered only while the flag is on so capability and prompt goldens do not move.
Risk: cost (estimate, cap, changed parts only) and accuracy (every page lists source files; DV-1's checker can verify).

### DV-8. Test it: browser check with screenshots (ADAPT of QA Engineer) — L, `SUTRA_TESTIT_V1` (needs nodes and findings)
Value: after a web change, Sutra opens your page in a real browser, walks the steps you list, and shows captioned screenshots with pass or fail per step. Screenshots, no video, your own machine only.
Reuses: headless Chrome helper behind J2 Audit (`engine/j2_check.py`, `ops/browser.find_chrome`), 360 and 1280 px widths, the light node host, DV-5 findings.
New: a `tester` role (changes the CHECK on `agent_nodes.role`: own migration); only `127.0.0.1` or `file://` addresses the owner or project names; v1 is a static site or a page already running ("start my dev server" is out of v1); `POST /api/projects/{id}/test {url, steps}`; a filmstrip panel; failures become findings.
Risk: medium-high (flaky browser automation, Chrome required, Windows unmeasured, hostile page text treated as data).

### DV-9. Watch GitHub, read only (ADAPT of GitHub triggers) — M, `SUTRA_WATCH_V1`
Value: tell Sutra to watch a repo you own; it shows "CI failed on #42" or "new bug report" in Needs you with a button to start a review or fix. It never writes to GitHub.
Reuses: `GithubTools` (own `gh` login, untrusted wrapper, 20 KB cap), tier 4 approval (MAN-8), the `recurring.py` tick pattern, `needs_you`.
New: tables `watches` (repo, what, every N minutes, floor 15, cursor) and `watch_events` (append-only, unique by source id); one fixed read template `github_checks_get` (tier 4, allow-listed); the poll is code only, no model sees an event until the owner presses Start; a section in `/work`.
Stays the same: P15 (no comment, status or label), `gh` keeps the login. After DV-5; off by default.

### DV-10. Scans (ADAPT of Code Scans and Security Swarm) — S, needs DV-3 and DV-5
Value: one click checks your folder for security slips, slow code, missing tests or dead code, shows a findings list, never changes a file.
Reuses: Recipes (starter recipes), findings, read-only workers (no write scope, so no lease conflicts), git for "since the last scan".
New: starter recipe data and `source: scan` on findings. No new table. Shows a cost estimate; Decide for me never raises one over `project_credits`.

### DV-11. Suggested notes (ADAPT of Knowledge suggestions) — M, `SUTRA_NOTES_V2`
Value: after work, Sutra suggests a few things worth remembering; you approve or dismiss each; it points out notes that look like duplicates.
Reuses: `notes.py` and its gate, `library/practice.py`, `docs/design/memory-evaluation.md` (take its storage decision first or together).
New: table `note_suggestions` (text, source, status `pending|approved|dismissed`, unique by source); a quiet list in the Notes page, not on the badge; `GET /api/notes/suggestions`, `POST .../{id}/approve|dismiss`; duplicate hints by word overlap in code. A suggestion is scrubbed, labelled as from a model, never active until approved.

### DV-12. Stay awake while work runs (ADAPT of "keeps working") — S, `SUTRA_KEEPAWAKE_V1`
Value: while a project runs, optionally stop the computer sleeping by itself, so long work finishes when you step away with the lid open.
Reuses: Conductor knows when nodes are live; `oslayer.py`; the desktop shell's power-save blocker.
New: setting `keep_awake` (default off); holds the block while at least one node or task is live; releases at zero, on stop and kill; a line on the project page.
Stays the same: D296. A closed lid is still a refusal. Do not promise lid-closed behaviour.

### DV-13. Worktree writers — L, not now (`SUTRA_WORKTREES_V1`)
Two steps change the same folder at once, each in its own git worktree under `<data>/worktrees/<node>`, you merge the result. Not now: it writes the repo's git data, which scoped writers are denied today; nodes beta has no real-world evidence; D261 deferred it on purpose.

## 5. Stays the same for every package

Flag-off path byte-identical; one database writer; external send off; owner's access caps every grant and every edit to a plan or recipe can only narrow; models propose, code checks, the owner decides; branch from the newest main, `scripts/gate.sh` foreground, beta first, never Latest.

## 6. Order and the owner's three questions (decided)

Build first, in order: DV-1, DV-2, DV-3, DV-4, DV-5. DV-1, DV-2 (tasks half) and DV-3 can start now. DV-4 and DV-5 edit the plan gate and the reviewer, so they follow the nodes beta and G23..G26. Then DV-6, DV-12, DV-7, DV-11, DV-10, DV-9, DV-8.
Do not build: cloud VMs and snapshots, laptop-closed work, Slack/Teams/Jira/Linear/PagerDuty/webhooks, PRs and commit statuses, secrets vault and browser sign-in for agents, Computer Use and voice and IDE, RBAC/SSO/SCIM, nightly dreaming, auto-proceed timers, video, Python workflow scripts, MCP marketplace, Android and Chief of Staff bots, worktree writers now.
Owner questions, decided: GitHub read-only watching = yes, after DV-5, off by default, no faster than every 15 minutes. Stay-awake switch = yes, default off. Worktrees and local branches = not yet; revisit after the nodes beta has run on real projects.

## 7. Sources

Devin, read 2026-11-20: devin.ai; docs.devin.ai llms.txt; product-guides (creating-playbooks, skills, memory, automations, scheduled-sessions, session-insights, auto-triage); work-with-devin (advanced-capabilities, ask-devin, interactive-planning, devin-review, deepwiki, code-scans, testing-and-recordings, dynamic-workflows, devin-session-tools, local-hands, devin-mcp, bots); desktop/devin-local (modes, worktrees); onboard-devin (environment, knowledge-onboarding); integrations (gh, linear); enterprise (custom-roles, usage-policies); get-started/first-run; release-notes/2026 (partly read).
Not found: an Advanced mode page, a Review confidence score. Interactive Planning's 30-second wait was taken from a search summary, not the page.
