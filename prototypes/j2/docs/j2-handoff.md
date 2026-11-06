# J2 prototype handoff

Start a new Claude Code session in the agent-studio folder and say:
"Read docs/j2-handoff.md and continue from there."

This file is the only handoff. It was checked against the code, docs/ and git log on 22 Oct 2026. Anything that could not be
checked is marked **unverified**.

## Purpose

J2 is a multi-agent "department" designed by the project owner (diagram: docs/j2-flow.jpg, public J2 page:
`https://<owner-github-username>.github.io/<owner-site>/native/system/department.html`). A small set of agents with fixed
roles takes a brief, agrees a plan inside a budget, builds the result, checks it, and talks to the person who asked only
when it must.

The developer (the person who built this prototype) uses it to test J2 as designed and to report what works and what does not.
The prototype builds a website from a brief. It can also write design documents first (PRD, HLD, LLD), and it can prepare
test emails and Slack messages (dry run only).

The user is a founder. In the product owner's words: "I just want to know what is required of me, and what my kingdom looks
like. Navigation of the department is via the map. The rest are internal things." The UI follows that: a map, a chat, and a
strip that says what needs the founder. Everything else sits under Internals.

## The agents

Official role files are in `agents/j2/`. **Never edit them.** `builder.md` and `rates.json` are placeholders written for this
prototype, not official files.

| Agent | Role (from its file) | Persona shown in the UI |
|---|---|---|
| Identity | charter guardian and conflict closer; the only agent that talks to the founder | Client Lead (Identity) |
| Adaptation | senses the goal gap and proposes workflows | Strategist (Adaptation) |
| Priority | resource bargain and envelope authority; prices and grants | Prioritiser (Priority) |
| Coordination | ordering, dependencies, hand-offs, the write lock | Scheduler (Coordination) |
| Audit | independent evidence-based check; files findings | Quality Reviewer (Audit) |

- **Builders:** one builder agent per workflow (named like "W-3 Builder"). Each workflow carries a work atom (see below).
  In the UI the builders appear as team personas, chosen from what the step makes: Product Analyst (drafting a PRD),
  Solution Architect (HLD), Technical Designer (LLD), Specialist (any other document), Web Developer (building the website),
  Messenger (sending). The persona names are display labels only; internal ids are unchanged. They live in one constant,
  `MAPLABEL`, in `j2_ui.html`.
- **Validator:** plain code, no AI call. It registers workflows, checks work atoms and runs the checks. Shown as "Checker
  (automatic)".
- **No CEO.** The official files still mention one; `agents/j2/team.md` says Identity asks the founder instead.

## How it works

1. **Brief.** The founder describes what they want. **J2.a:** Identity asks until it has enough, works out the business type
   and what visitors need, and records a charter. A fact only the founder knows is asked once; if they cannot give it, it
   is recorded as "to be confirmed" and that item is not met.
2. **J2.b** Adaptation proposes workflows. **J2.c** Priority prices them in a bounded bargain (four hops, fifteen minutes,
   8 AI calls). Past a bound, both positions go to Identity (**J2.d**).
3. **Budget.** Work credits (made-up units, not money or tokens). Start budget `J2_BUDGET` (default 100); the founder's
   approvals can raise it to `J2_BUDGET_CAP` (default twice the start). Prices come from the rate card
   (`agents/j2/rates.json`, placeholder). A cost follows the work: each done-when item has a minimum, and a fix is priced
   as a fix. When credits run out, the founder gets one decision question applied by code: add credits, leave items out, or
   finish as it is.
4. **J2.e Validator** registers each agreed workflow and creates its builder.
5. **Work atoms.** Each workflow has a work atom in the `atom/1` shape (`docs/atom-schema.md`, `docs/atom-schema.json`,
   `j2_schema.py`). Status: open, closed, verify_failed, abandoned. Each output item has a verb (make or do), a name, a form
   and a ref. Adaptation writes `expected_output` items before the build; code derives one check per item (behaviour items
   run as steps in Chrome). `depends_on` and `used_by` are recorded from what each builder's prompt actually held, so they
   show what was **given**, not what was **used**. Results go to `receipts.jsonl` and `atoms.json`.
6. **J2.f** Coordination schedules and holds the write lock. Builders write their own section (slim mode is the default, so a
   builder sees its section and a short manifest; `J2_SLIM=0` gives the older full prompts). Code assembles the page.
7. **J2.g** Audit checks the result and files findings (F-n for a website, D-n document rubric items for documents) to
   Identity. **J2.h** Identity decides if the result is workable; Adaptation records lessons and playbooks (memory in `memory/`,
   `J2_MEMORY=0` turns it off).
8. **Report.** `summary.json`, `report.json` and `report.md` are written at the end, plus `map.json` and `artifacts.json`.

**Code-routed group chat.** All agents talk in one shared chat. Code decides who may speak to whom (`ROUTES` in `j2.py`), each
message has one addressee, and an agent that addresses the founder is routed to Identity first. Identity's replies have two
parts, one for the founder and one for the team, and the code keeps them apart.

**Design documents are opt-in.** Code looks for explicit words in the brief or the founder's answers ("design docs", "PRD",
"HLD", "low-level design" and so on; "modern design" triggers nothing). Order: PRD, then HLD, then LLD, each reading the one
before it. A website follows only if the brief also names one; with an LLD, each builder gets its LLD slice and an HLD summary.
With no document asked for, the flow is unchanged (guarded by `plain_unchanged`).

**Checks.** Documents: P1 to P8 (PRD), H1 to H6 (HLD), L1 to L6 (LLD), plus the document rubric D-n (D-5 is "no invented
facts"). Website: necessary conditions N1 to N8 (`conditions/website.json`), a render check (`j2_check.py`), and Audit
findings. Condition files: `conditions/prd.json`, `hld.json`, `lld.json`, `website.json`.

**Send deeds, phase 1** (`j2_send.py`): a brief that asks for a test email or Slack message gets a deed stage. Sends are dry
run by default (nothing leaves, the deed stays open) or mock (an in-process recorder for tests). The recipient comes only from
`J2_TEST_EMAIL` and `J2_TEST_SLACK_TARGET`, never from the brief. Receipts hold a masked recipient and hashes. There is no
network code. Live sending is not built (phase 2).

## The UI today

Served by `j2_server.py` from `j2_ui.html`. The Simple view is the default (plain words, one chat and a preview). The Detailed
view is at `?view=detail`; a saved run opens read-only with `&run=<run id>`.

**Detailed view home:** the department name, a **Needs you** strip, the **Map**, and the **Chat** docked on the right (stacked
below 900px). Needs you lists every open question to the founder with an "Answer in Chat" button that focuses that question,
and shows one plain outcome line for a finished run with a "See report" link. The full outcome banner is at the top of the
Report tab.

**Left rail:** Map, Chat, and one collapsed **Internals** folder. Internals holds: Preview (the website), Goal, Workflows,
Conflicts, Timeline, Audit, Charter, Documents, Artifacts, Style guide, Lessons, Playbooks, Report, Run details, and **Run
settings** (what to build, the saved-run selector, New run, Back to simple view). Each internal view has a "Back to map" link.

**The Map is the navigation.** A click (or Enter) on a node opens its panel; the panel's Open button goes to:

| Node | Open goes to |
|---|---|
| A node waiting on you | that question in the Chat |
| You | the Needs you strip |
| Client Lead (Identity) | the Chat |
| Quality Reviewer (Audit) | the Audit tab |
| Strategist, Prioritiser, Scheduler | the two tables under the Map (messages between functions, who made each step), filtered to that function |
| A team persona (a step) | the Workflows tab filtered to that step's workflows |
| Website | the site preview |
| Charter | the Charter tab |
| Any other deliverable | its document in Artifacts |

**Map drawing** (`docs/map-schema.md`): You and the Management layer across the top; below them a tree down the middle with
Charter at the root, each team persona above the deliverable it made. Hand-off lines run down the spine; "given to" lines loop
beside it and end at the persona that was given the document. No two lines cross (loops that would interleave go on opposite
sides; the code checks every pair, and an unavoidable crossing is drawn round the outside and listed under "Not recorded").
Function-to-deliverable lines show only when a node is hovered or selected. At 600px and under, the map becomes a list of
cards. Status is never colour alone: solid ring = filed and checked, dashed = left open, double = running now, thick red with
"!" = fault, thick amber with "?" = waiting, hollow and faint = not made.

## Files map

- `j2.py`: the whole J2 flow (agents, routing, budget, validator, atoms, checks, documents, send deeds, report).
- `j2_server.py`: HTTP server and JSON endpoints (`/api/state`, `/api/map`, `/api/docs`, `/api/artifacts`, `/api/audits`, and others).
- `j2_ui.html`: the whole page (Simple and Detailed views). `j2_ui_render.js`: runs the page script against a stub DOM for tests.
- `j2_map.py`: builds `map.json` (schema map/1) from a run folder or live state. Code only, no model call.
- `j2_send.py`: send deeds, phase 1 (dry run and mock).
- `j2_artifacts.py`: lists a run's deliverables and records from `artifacts/types.json`. `artifacts/types.json`: the artifact kinds
  (PRD, HLD, LLD, website). The flow does not read it; the same kinds are also defined in `j2.py`, and a test keeps the two equal.
- `j2_schema.py`: the `atom/1` adapter and warnings. `j2_check.py`: render check and the Chrome driver for behaviour steps.
- `j2_flow_test.py`: the test suite. `j2_replay_size.py`: estimates prompt size from a saved run (no model calls).
- `llm.py`: model wrapper (Claude CLI, Anthropic API, Gemini, or offline mock). `mock_site.py`: scripted site for mock mode.
- `conditions/`: necessary conditions per output type. `agents/j2/`: official role files, `team.md`, placeholders, `rates.json`.
- `docs/`: this handoff; `atom-schema.md` and `.json`; `map-schema.md`; `j2-test-plan.md` (one run per branch of the flow);
  `j2-prompts.md` (briefs to type); `j2-flow.jpg` (the diagram); `ui-*.png` (screenshots).
- `README.md` (what J2 mode does and every setting) and `SETUP.md` (install and run). `studio.py`, `negotiate*.py`, `server.py`,
  `ui.html`: the earlier three-agent demo, not part of J2.
- `runs/`: saved runs. `memory/`: lessons and playbooks (git-ignored).

## How to run

Install once (see SETUP.md), then:

    source .venv/bin/activate
    STUDIO_PROVIDER=claude-cli python3 j2_server.py            # live, on your Claude subscription
    STUDIO_MOCK=1 python3 j2_server.py                         # offline, scripted agents, no key needed
    J2_FIXES=0 J2_MEMORY=0 STUDIO_PROVIDER=claude-cli J2_DELAY=0 python3 j2_server.py    # clean test run

Opens http://127.0.0.1:8773. Use `--port` for another port and `--no-browser` to stay headless. If the port is busy:
`lsof -ti :8773 | xargs kill`.

Environment variable names (set values in your shell or `.env`, never in files that are committed): `STUDIO_PROVIDER`,
`STUDIO_MOCK`, `J2_BUDGET`, `J2_BUDGET_CAP`, `J2_FIXES`, `J2_MEMORY`, `J2_SLIM`, `J2_OUTPUT`, `J2_DELAY`, `J2_RUNS_DIR`,
`J2_RATES`, `J2_MAX_CYCLES`, `J2_MAX_TURNS`, `J2_BARGAIN_MINUTES`, `J2_BARGAIN_CALLS`, `J2_SEND_MODE`, `J2_TEST_EMAIL`,
`J2_TEST_SLACK_TARGET`, `J2_FORCE_AUDIT_FAIL` and `J2_MEMORY_TEST_LESSONS` (test switches), `J2_OVERRIDE_KEY` (owner override),
`ANTHROPIC_API_KEY` and `GEMINI_API_KEY` (only if you do not use the Claude CLI). README.md "Modes and settings" lists them all.

Each run is saved in `runs/j2-<time>/`: `chat.jsonl`, `calls.jsonl`, `summary.json`, `atoms.json`, `map.json`, `artifacts.json`,
`receipts.jsonl`, site versions, screenshots, and the document files of a documents run. Use only fake phone numbers that start
with +91 00000 in briefs.

Budget guide. The least each stage can cost comes from `agents/j2/rates.json` (a placeholder rate card, not an official file),
worked out by `_stage_cost` in `j2.py`: every document section is a `doc_section` (10) and one is a `requirements_section` (48);
the website's essentials are a styling part (5), three page sections (10 each) and a form (15); a send deed is 5.

| Stage | Least it can cost |
|---|---|
| PRD (6 sections: 5 x 10 + 48) | 98 |
| HLD (6 sections: 5 x 10 + 48) | 98 |
| LLD (5 sections: 4 x 10 + 48) | 88 |
| Website essentials (5 + 10 + 10 + 10 + 15) | 50 |
| Test email or Slack message | 5 each |
| PRD, HLD, LLD and website together | 334 |

A fix costs 8 (`fix`). The default start budget is 100 (`J2_BUDGET`) and the cap is twice the start, so a full documents-plus-website
run needs a start budget of at least 334 to run without a funding question; at the default the founder is asked. 334 is the floor when every check passes first time. Real runs cost more because of
revisions and fixes: the reference run `runs/j2-20261016-160511` used all 500 credits (start 500, used 500, `summary.json`) and 114 AI
calls (`summary.json`; `calls.jsonl` holds 113 records). Charged credits by stage, summed from its `workflows.json`: PRD 172, HLD 122,
LLD 128, website 78. A figure of about 270 for the HLD stage alone could not be verified and does not match those files. Start at 500
for a full documents-plus-website run; that run still ended done with open items. The earlier
notes that gave 65, 65, 55 and 235 are out of date (they predate the 16 Oct recalibration in `rates.json`).

## How to test

    python3 j2_flow_test.py --fast             # offline flow test in mock mode, no browser steps
    python3 j2_flow_test.py --fast --browser   # adds the tests that drive the page in Chrome
    python3 j2_flow_test.py                    # everything, both J2_FIXES modes

SETUP.md gives about 35 seconds and 8 to 9 minutes for the first two; the suite has grown since, so treat those numbers as
**unverified**. Both fast modes passed on 22 Oct 2026 (commit b13db81).

- **`plain_unchanged`** runs twice in every mode. It runs the plain website path (no documents) in a temp copy of a fixed
  checkpoint commit and requires identical prompts, page and outcome: once with `J2_SLIM=0` against `f6938b2`, once with the
  default against the commit in `PLAIN_CHECKPOINT` (`j2_flow_test.py`). Move `PLAIN_CHECKPOINT` only when the plain path changes
  on purpose.
- **Reference runs** under `runs/`: `j2-20261016-160511` (documents plus website, done with open items) and
  `j2-20261022-123744` (done with open items). The Map tests read copies of both and check there are zero crossing lines and no
  label on a line. A mock documents run is built inside the suite as the third.
- Page tests: `j2_ui_render.js` renders the page without a browser; Chrome tests inject a probe script into a copy of the page.

## Rules

- Never edit `agents/j2/*.md`.
- Never read, print or commit `.env` or any secret. Hook tests go in a throwaway temp repo, not here.
- Never edit anything under `runs/`; it is evidence. Scrub a copy before sharing a run.
- Change the flow only in steps the project owner or developer has agreed. Keep decisions with the agents: add rules the validator
  enforces; do not hard-code an agent's choice in code.
- Commit before and after every change. Do not loosen a test to make it pass; if an assertion must change, say why.
- Do not push unless asked. No live sends: `J2_SEND_MODE` stays `dry-run` or `mock`.

## Open issues and next steps

1. **Given is not used.** Edges record what a builder's prompt held, not whether the builder used it. There is no proof the
   builders used the documents they were given. The Map says "given to" for that reason.
2. **False invented-fact flags.** The P4 name detector reads "This PRD" as a made-up name (from 16 Oct notes; the fix awaits the
   project owner's approval). The same kind of false flag is reported for H5 and D-5: **unverified**.
3. **Shallow atom checks.** LLD checks are structure only (ids, selectors, form fields); what a click does is not run
   (from 15 Oct notes, not rechecked).
4. **Budget runs out on full runs.** The two reference runs hit a limit 2 and 6 times (`limits_hit` in `summary.json`).
5. **Pause even when all checks pass:** reported, **unverified**.
6. **Page-wide parts** (navigation, hero) may have no owning workflow: **unverified**.
7. **Revisions and findings.** A revision is not reliably linked to the finding it fixes: **unverified**. Commit 979ad0f added a
   Fixes line to revise atoms from stored audits, so the gap, if real, is in what is recorded, not in the card.
8. **Send deeds phase 2** (live sending, a way to fetch) is not built. Phase 1 is dry run and mock only.
9. **Map gaps.** The Knows row is not drawn (schema only). The Charter has no version, shown as "version not recorded".
10. **Artifact types are duplicated.** `artifacts/types.json` and `j2.py` both define them; a test fails if they drift.
11. **Open question for the product owner:** should a click on a Map node open the view directly, or open the panel first (as now)?
12. From 15 to 16 Oct notes, **unverified now:** no live run has measured slim mode or documents token cost; Chrome-driven
    behaviour receipts have only run with the fake driver; the real cost of a finished HLD or LLD is not measured (`rates.json` says only PRDs were measured; the 98 and 88 minimums above are rate-card arithmetic); the project
    owner's artifact kinds file is still to be shared; the docs say `runs/` is git-ignored but it is tracked (since b2324e2).
13. Deployment needs a company API key and a hosting account (agreed in principle, not started).

## Recent history

Early rounds (6 to 8 Oct). Round 1 tested conflict handling and budget on a cafe site with nine live runs. It found, among
others: no pricing step between a ruling and the build, spending before the whole scope was checked against the budget, no
core versus nice-to-have marking, no fix reserve, "done" meaning only that sections exist, user decisions not amending the
charter, and placeholders defusing conflicts. Reports (Claude Docs, shared with the project owner): round 1 findings
`https://claude.ai/code/artifact/4503e532-d714-45ad-9cdc-5b3872fb533d`, proposed solutions
`https://claude.ai/code/artifact/f6201d73-93a9-4a24-b4e4-f2dd7759ad29`, round 2 findings
`https://claude.ai/code/artifact/f09ff16a-ea7f-4b9f-b6a0-f565fe27c312`. Later runs showed that cost now follows the work and
that limits reach the founder as one decision question (94a9a6c).

- 7 Oct, `1d12c6d` workflow agents, the loop, memory and the first UI.
- 7 Oct, `b408efe` Simple view added; `71975f4` cost follows the work; `ee42626` J2 works for any business (needs check, style guide, playbooks).
- 8 Oct, `94a9a6c` budget, drop and finish are asked and applied by code only; `6f978af` two audiences, plain messages, owner override, forms need a submit button.
- 9 Oct, `3a8960c` to `df091a7` Adaptation always proposes within budget; funded work is built before Identity asks about unfunded items.
- 11 Oct, `aa9da25` SETUP.md added.
- 12 Oct, `6464d86` Adaptation writes a work atom per workflow; `7b000cd` code runs each atom's checks and writes receipts.
- 13 Oct, `d3335c2` PRD output type; `bcd649a` website necessary conditions N1 to N8.
- 14 Oct, `16a6975` and `678dc36` expected_output items and behaviour steps run in Chrome.
- 15 Oct, `82c8ca7` atom outputs and slim prompts; `fc06c02` design documents (PRD, HLD, LLD); `9520e1f` LLD slices as builder specs; `e1e4607` budget rule for the chain.
- 16 Oct, `3a1e66c` finish-as-it-is on a document, code-written check results; `889229d` `plain_unchanged` wired into the suite; `da914c7` to `f6938b2` atom/1 schema, four statuses, verbs; `13ccccd` slim on by default.
- 20 Oct, `c6333f4` to `0de305b` Detailed view: Documents tab, atom cards, Charter tab, workflow output tags and filters, document lineage rows.
- 21 Oct, `56b6c4d` send deeds phase 1; `932fbb6` Artifacts tab and `types.json`; `19ae41a` to `5209177` Map tab (map.json, functions row, speaks-to lines); `b2324e2` runs/ tracked.
- 22 Oct, `c042f21` Detailed view rail layout; `98eb459` Map redesign (circle nodes, given-to ends on the step, click panel); `a3bfb64` Map and Chat home with Needs you and Internals; `b13db81` simplified home, Run settings, and the crossing-free tree map with team personas.
