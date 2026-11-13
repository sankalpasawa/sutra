# remove-restrictions: plan and status

Branch `remove-restrictions`. Written 2026-11-13 so a new session can pick up. The original plan was in a session
that ended on a login error; steps 0–4 are recovered from commits, steps 5–9 and the standing rules are the founder's.

## Test cadence (founder, 2026-11-13)

| When | Run |
|---|---|
| After each step | `python3 j2_flow_test.py --fast --skip map_focus,graph_map,left_bar_toggle,artifacts_groups,warm_ui,map_motion` |
| After step 5 (UI) and before the final commit | `--fast --browser` with the same skips, **not piped through `tail`** (20+ min; progress must show) |
| After step 5 | Live release check: `python3 tools/release_check.py` (cap $60 across all checks; ledger `runs/release/ledger.json`) |

The six skips read local saved runs and fail on the base commit already.

Release check pass rule (`43bc2095`): a brief passes only on an outcome starting `Done:` (workable).
"Done with open items" fails.

## Done

| Step | Commit | What | Release check |
|---|---|---|---|
| 0 | `374bf9ef` | `tools/release_check.py`: the three release briefs live, each in its own process, ledger against the cap | Baseline only |
| 1 | `2092553c` | Builders get Claude's built-in tools and the network; reads fenced to their folder; limits default in code (`j2.AGENT_DEFAULTS`, listed commented in `.env.example`) | Mock 3/3; live smoke $0.09 |
| 2 | `b9d336a2` | One general path: every builder writes files with its tools; folder stage deleted; check bundles warn | Live: policy Done, script Done, coffee shop Done with open items (no facts in the old brief). $10.83 of $60 |
| 3 | `d2bb7f6d` | A guess warns, never blocks; "Assumptions to confirm" only when the template asks | Mock 3/3 |
| 4 | `4ca95c96` | A missing capability becomes a planned script with its own test (`templates/atom_rules.md`); realization planner may search the web with tools on | `--fast` only |
| — | `43bc2095` | Release check: coffee shop brief gives its facts (Bean There, 12 Park Road, hours, menu with prices); only `Done:` passes | Mock 3/3 |
| 5 | `fb430a31` | UI: one artifact view (no Documents tab), every output-folder file with its maker, Template line, conditions with the sandboxed test, warnings apart from failures, runs by type label | Live 3/3 Done, $2.12 (total $12.95 of $60); `--fast` and `--fast --browser` pass |
| audit | `feb5361a` | Hard-coding audit fixes; C2 title | `--fast` |
| — | `9dc8ad0a` | The planner names a new type's form; note for Kaivan | `--fast` |
| 6a | `50ffeb87` | No built-in folder type: a folder output gets a type the planner names for what it makes; old runs of a deleted type still open | `--fast`, mock 3/3 |
| 7 | (this commit) | Run for real: planned by Adaptation, checked by code, run only on the exact reply RUN <code>, sandboxed, writing one folder, receipt in receipts.jsonl | Live 4/4 Done, $6.04 (total $18.98 of $60); the demo folder sorted for real |
| 5 follow-up | `16ae61f7` | Group by what the run made, Preview its main output, final-attempt failures, C2 evidence says code reran the test, code names not flagged as facts, Template line first | `--fast`, `--fast --browser` |

## Step 5: UI

| # | Change | Impact | Effort |
|---|---|---|---|
| 5a | One artifact view everywhere: Summary, Agent-readable, Human-readable, and a "Template" line naming the template that made it. Remove the separate document viewer and its extra buttons. | High | L |
| 5b | The artifact shows every file a tools builder wrote in the run's output folder (`out/`), not only the page or main document. Clicking a file in the list shows it: code as text, images as images. | High | M |
| 5c | The test result (the sandboxed rerun) shows in the artifact's Summary. | Med | S |
| 5d | Advisory-check warnings and `guess_warning` rows show as warnings, apart from failed checks. | Med | S |
| 5e | Scripts built for a missing capability (step 4), with their tests, show as reusable artifacts of the run. | Med | S |
| 5f | The run list labels a run by its type's label (e.g. "Script"), not "website" or "document". | Med | S |
| 5g | Start page: remove any forced choice of type or form; the prompt alone decides. | Med | S |

Out of scope: the Library tab and RTSCOPES (Kaivan owns them). Do not change them.

After step 5: `--fast --browser` (no `tail`) and the live release check.

## Step 6a: a folder output gets a type that names what was made (done)

Done as planned except 6a.4: the offline mock planner already picks the page type for every brief that names no
type, so the mock release check is unchanged (3/3) and needed no folder-type mock. 6a.5 went further than planned:
`j2_types.recorded` now covers a deleted type of any form from `artifacts.json`, and `saved_def` gives a folder no
sections.

**Why it goes before step 6.** Step 6 saves and reuses runs by their type. Done first, a saved script run is
reused as a "Copy script", not as any folder output under the generic "Agent".

**Finding.** Adaptation can already make a new type in any form: `types_text` (`j2_realization.py`) says "when no
type fits, make a new one", `j2_types.create()` accepts a form without sections, and `J2Run` creates it
(`j2.py`, the `new_types` loop after `plan_goal`). The file-copy run (j2-20261113-164130) picked the built-in type
`agent` instead, because that type is in the list and fits any folder. The rubric, conditions, test runner,
builder text, charter format and mock all sit on the agent *form* (`artifacts/types.json` `forms.agent`), not on
the type, so a new type in that form gets all of them.

| # | Change | File (owner) | Impact | Effort |
|---|---|---|---|---|
| 6a.1 | Delete the built-in `agent` type entry; keep `forms.agent`. With no folder type in the list, the planner makes one in the agent form (e.g. `copy_script`, label "Script") through the existing `create()` path | `artifacts/types.json` (Disha) | High | S |
| 6a.2 | A new folder type is stored in `artifacts/types.local.json` (gitignored; no template, so nothing goes to `library/`), reused by later runs, promoted with `python3 j2_types.py --promote <name>`. No code change | `j2_types.py` (Disha), read only | n/a | 0 |
| 6a.3 | The planner's type text: say that a folder form is a form, not a type, so a folder output always names its own type. Wording only, no type names | `j2_realization.py` `types_text` (Disha) | Med | S |
| 6a.4 | Mock path: the offline deliverables mock picks a named type or the page type. For a folder brief it must propose a new type in the agent form, driven by the form's `mock` data, with no keyword matching. Release check brief 3 (mock) must still end `Done:` | `j2.py` `J2Run._deliverables` offline mock, `j2_realization.deliverable_mocks` (Disha) | Med | M |
| 6a.5 | Saved runs whose type was `agent`: `j2_types.recorded()` keeps a deleted type's label only for planner-made types. Old agent runs would show the raw name. Fall back to the run's `summary.json` or `artifacts.json` label, else the form's label | `j2_types.py` `recorded` (Disha), `j2_server.run_row` (Disha) | Low | S |
| 6a.6 | Tests that call `set_output("agent")` (3 in `j2_flow_test.py`), plus `guesses_warn`, `general_path`, `missing_capabilities` and `one_artifact_view`, make a folder type with `j2_types.create(..., form="agent")` in a temp types file | `j2_flow_test.py` (Disha) | Med | M |

Not touched: `templates/agent/` (under `templates/`, which step 6's rule reserves), `conditions/agent.json` beyond C2's
title, the Library tab, `j2_template_lib.py`. Risk: a live planner may still choose a page or document type for a
script brief; the release check's script brief shows it (its outcome names the type). After: `--fast`, mock release
check; a live check only with step 7.

## Step 6: library

Folder and workspace runs save and reuse through Kaivan's `run_template_from_run` and `save_run_template`; no second
store. Do not edit Kaivan's files: `j2_template_lib.py`, `library/`, `templates/`, `j2_agent_views.py`,
`j2_artifact_models.py`, the Library tab. If `decision_group` or anything there must change, write exactly what is
needed as a note for the founder to send him. After: `--fast`, mock release check.

**Status:** done without a change from Kaivan. Folder workflows record their outputs from the run folder
(`<folder>/<file>`, `J2Run._register`), which his `_stage_of` already matches (`"<folder>/"`, `j2_template_lib.py:2368`);
checked on copies of the three real folder runs (j2-20261113-195301, -195303, -164130): each saves as a run template.
A run that follows a run template with a folder for its type starts from that template's files (copied from the saved
run), code checks them before any builder call, and the decision is "reused" (`J2Run._reuse_folder`, test
`folder_run_reused`). The fallback request is dropped from the note.

### Note for Kaivan (sent; status after his merge `afa6881b`)

| Item | Status |
|---|---|
| 1. `_stage_of` for folder runs | Not needed: we now record outputs as `<folder>/<file>`, which his `_stage_of` matches |
| 2. `decision_group` counts a folder type as pages | Fixed in main: the type's `group`, else its form |
| 3. `assumptions_section` (`j2_template_lib.py:470`) | Kept in main |
| 4. Builder guidance line in `templates/builder.md` ("never run on the Requester's folders; code does that after approval") | Written by us (founder's call); tell him, as `templates/` is his |
| Tests | `library_cleanup` narrowed to `types.json`'s own types in our merge; `sutra_library` fails on a machine whose saved run recorded "phone" as a charter value |

## Step 7: run for real

When a brief asks to act on real files, the workflow states the command and the folder. The Requester approves in
chat. Code, not an agent, checks that exact approval. Then the command runs with write access to that one folder
only, with a receipt in `receipts.jsonl`. After: `--fast`, live release check.

### Design (approved 2026-11-13; built, with a read-only "reads" list and a fourth live brief)

| # | What | Who decides | File (owner) |
|---|---|---|---|
| 7.1 | The planner may add a real run to a folder deliverable: `"real_run": {"command": [argv], "folder": "<absolute path>", "why": str}` on the workflow that runs the built script. Whether a brief asks to act on real files is the planner's call (no keywords) | Adaptation | prompt text in a new data file `artifacts/real_run.md`, named by `types.json` `builder_tools.real_run` (Disha) |
| 7.2 | Validator (code): the folder is an absolute path the brief or the Requester's answers name word for word, it exists and is a folder, and it is not the home folder, `/`, the repo or the run folder; argv[0] is the form's runner program (`test_runner[0]`); every other argument is inside the built output folder or the stated folder. Anything else is refused back to Adaptation | code (guardrail) | `j2.py` |
| 7.3 | After the deliverable is workable (tests passed in the sandbox), code posts the exact command and folder in chat with a one-time code, and asks: "Reply exactly: RUN <code>". Decide for me never answers it; nothing runs until the Requester does | code | `j2.py` |
| 7.4 | Code compares the Requester's next message with `RUN <code>` exactly (trimmed). Anything else: not run, and said so. A second request needs a new code | code (guardrail) | `j2.py` |
| 7.5 | On approval: run `J2_SANDBOX_CMD` with settings like `sandbox_settings`: no network; reads the built output folder and the stated folder; writes only the stated folder; the builder's time limit | code (guardrail) | `j2.py` |
| 7.6 | Receipt in `receipts.jsonl`: `{"kind": "real_run", "command", "folder", "code", "approved_msg", "sha256" of each built file run, "exit", "output" (its end), "seconds", "t", "by": "code"}`; a chat line with the result. A refusal or an expired code gets a receipt too | code | `j2.py` |
| 7.7 | UI: the receipt shows in the deliverable's Summary (like the conditions); the approval request is a Needs-you card | UI | `j2_ui.html`, `j2_artifacts.py` |
| 7.8 | Tests: a mock run with a real-run workflow; wrong reply, Decide for me, a folder the brief doesn't name, `..` in an argument, a write outside the folder (with the fake sandbox: the settings are checked, not enforced) are each refused; the exact reply runs it once with a receipt | n/a | `j2_flow_test.py` |

**Known limit:** one folder, read and write. A command that reads one folder and writes another (copy A to B) needs
two folders: allow a `"reads"` list (read only) next to `"folder"` (the only write)? Founder's call.

**Release check:** the three briefs ask for no real run, so the live check after step 7 only shows nothing else
broke. A brief that does (e.g. "sort the files in /tmp/j2-sort-demo") would test it live; add it?

### Paused (founder, 2026-11-13, at 85% of weekly usage)

- Dry run before the RUN code: run the command on a copy of the stated folders in the sandbox and show what would be
  created, changed or deleted, with counts; then ask for the code. With a test.

## Step 8: delete dead code (paused, founder, 2026-11-13)

Delete page/document code the general path no longer uses, plus tests that only checked it, each listed in the
commit message. After: `--fast`, mock release check.

## Step 9: SETUP.md for teammates

claude-cli and Node versions, installs, every `.env` line (including `J2_SANDBOX_CMD` and the limit defaults),
tested from a fresh clone. After: `--fast`, `--fast --browser`, live release check.

## Standing rules

| Rule | Detail |
|---|---|
| No new names in code | No new type, form, tool or keyword names in code |
| `--fast` | After every step |
| `--fast --browser` | Only after steps 5 and 9 (no `tail`) |
| Live release check | Only after steps 5, 7 and 9 |
| Mock release check | After steps 6 and 8 |
| Spend | Hard $60 cap across all live checks (`runs/release/ledger.json`) |
