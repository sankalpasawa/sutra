# S1 · Contracts: process and wire contracts among the engine, the orchestrator and the connectors
_Settled 2026-11-04 by the solution architect (workflow batch S1, name `contracts`). Machine record with the exact patch text: `S1-contracts.json` (same ids). The owner can veto any entry._

**Sources read.** `engine.md`, `orchestrator.md`, `connectors.md` (all contract parts), `sections.json` open risks of the three, `ui.md` only where it names routes (UI-D2), `library.md` where it touches atoms and ids, `DECISIONS.md` D1-D12, `gen.py`, the function-node draft and the three critic reports (the final spec did not exist), and the J2 code. Section numbers below are the numbers in the section files as they stand today.

**How to patch.** `where` names the heading to edit. In `work_packages`, action `change` means APPEND the listed `owns`, `depends_on` and `acceptance` entries to the existing package (its title starts with `APPEND:`); action `add` creates the package. The cross-section tests live in one new package, `CT-1` (`tests/contracts/test_contract_*.py`); its modules import the sections they compare unconditionally, so CT-1 merges after them. **Overlap with batch S2 (models).** S2-models-05 to 10 settle the function-node layer's layout, lifecycle, atom fields and ids; S2-models-02, 03, 08, 12, 14 settle node vocabulary, statuses, the `node` task/context forms, shared JSON helpers and the Department record. S1 defers to them wherever both speak, and says so in the block (S1-05, S1-09, S1-10, S1-18).

## Index
| Id | Topic | Decision in one line |
|---|---|---|
| 01 | J2 routes and the J2 page | root paths, one mount, team in `?dept=`; the UI serves the page |
| 02 | `make_port`, `PortSpec`, `Allowance` | one signature in `connectors/engine_port.py`; the two types live in `engine/port.py` |
| 03 | `RunSpec.settings` and engine flags | three layers; 7 task keys; engine host resolves; owner edits via `/api/engine/settings` |
| 04 | `stop_live` | True when nothing of the team is starting or running; stops a waiting task; never a running one |
| 05 | Usage rows | the Router builds every row; two sinks; the server alone writes the ledger |
| 06 | Allowance | the caller keeps the envelope; v1 sends none; router ceiling 6 |
| 07 | CallTag mapping | `purpose` open string; ORCH `step` goes to `stage` |
| 08 | A2-A4 | accepted with five corrections; session API kept, no v1 caller |
| 09 | Final run-event list | eight events, `at` on every line, `session` removed |
| 10 | Function nodes on the wire | no new event type; the atom id rides on every call's tag; the rest is S2-models-05 to 10 |
| 11 | Run folder, D9, spawn, env | orchestrator creates the folder; one shared env allowlist |
| 12 | Follow-ups | new task each time; rehydrate or fresh; the realization pause explained |
| 13 | Non-blocking `user_says` | P4 accepted; host inbox FIFO; stop first |
| 14 | `SUTRA_MAX_RUNS`, 81 MB | working teams counted; waiting teams capped separately |
| 15 | Shutdown and stop ladder | one ladder: stop line, 8 s, SIGTERM, 4 s, SIGKILL |
| 16 | Crash detection, recovery | process gone, or silent 30 s at start; `at`-based age |
| 17 | Diagram text, billing guard | exact new strings; API-key login refused |
| 18 | JSON extractors | settled by S2-models-12 (one copy in the library); S1 adds a same-object check |
| 19 | Owner override key | the server holds the key; the engine sees only the command |

---

### S1-contracts-01 · J2 routes at the root with `?dept=`; the UI serves the page
- **Decision.** The 28 J2 data routes (23 GET, 5 POST) keep J2's paths at the root and are mounted once. The team is `?dept=<id>` only, the run `?run=<id>` (J2: always a read-only disk view). No `/d/{dept}/api/...` copy, no `X-Sutra-Dept` header, no cookie. Missing or malformed dept gives 400 `dept_required`; unknown dept 404. The UI alone serves `/`, `/d/{dept}/` and the 308 from `/?dept=`; the engine has no HTML route and no pages module. One constant `DEPT_ID_RE = ^[a-z][a-z0-9-]{1,39}$` (ORCH's rule) serves the route dependency, `TaskSpec.dept_id` and the UI. `EngineServices` is defined only in `engine/api/ports.py`.
- **Why.** UI-D2 counted 28 fetch sites and 15 URL-in-HTML sites: one fetch wrapper and one `runQ` edit beat 43 edits or a base tag. `/d/{dept}/` is already the page. J2 rewrites `location.search` (j2_ui.html:3212, 3222), so the team sits in the page path and the API query. One mount is one route table (56 routes become 28). ORCH 5.6 and ORCH-D7 already say `?dept=`; D6 keeps J2 paths.
- **Rejected.** Both mounts (engine 7.2); path prefix only (ORCH E-1 reading); header or cookie; the engine serving the page.
- **Changes.** engine §1, §2, §3.1, §4.0, §4.9, §6 F1-F3 F9, §7 heading, §7.2, §9, §10 E4, §11 ENG-D4, §12 · orchestrator §1.3, §3.5 (delete the `EngineServices` copy), §5.6, §10 · ui §0, §4.1, §4.2, §13 req 8 · new `test_contract_route_table.py`.
- **Label.** J2 paths at root · ?dept= picks the team

### S1-contracts-02 · `make_port`, `PortSpec`, `Allowance`: one signature, one owner
- **Decision.** `PortSpec` (`mock`, `connector`, `run_id`, `dept_id`, `task_id`, `data_dir`) and `Allowance` (`max_calls`, `max_usd`, `deadline`, `envelope_id`) are defined in `engine/port.py`. `make_port(spec: PortSpec, *, usage_sink=None) -> ModelPort` exists only in `connectors/engine_port.py`. `RunSpec` never appears in the connector layer. Mock (`--mock`, `SUTRA_MOCK`, `SUTRA_OFFLINE`, `STUDIO_MOCK`, `connector == 'stub'`) means the host builds `ScriptedPort`; otherwise `make_port` then `preflight()`. `make_port(mock=True)` still returns a stub-only Router, proven equal to `ScriptedPort` by one shared test. `CompletionRequest.allowance` is typed `Allowance | None`.
- **Why.** `RunSpec` has no `model` field; `PortSpec` in `spec.py` would make connectors import the settings module; `port.py` is already the shared seam.
- **Rejected.** `make_port(RunSpec)`; `PortSpec` in `spec.py`; a dict-typed allowance; the host always calling `make_port`.
- **Changes.** connectors §3.10, §2, §3.1, §9 A1 · engine §4.1, §4.4, §4.7 step 5 · tests in E0 and CN-7, plus `test_contract_make_port.py`.
- **Label.** one seam: make_port(PortSpec) -> ModelPort

### S1-contracts-03 · `RunSpec.settings` and engine flags
- **Decision.** Three layers: `data/engine.json` (global), `data/departments/<dept>/engine.json`, and the task's `RunSpec.settings`, a closed set of seven keys (`J2_OUTPUT`, `J2_BUDGET`, `J2_BUDGET_CAP`, `J2_FIXES`, `J2_MEMORY`, `J2_SLIM`, `J2_RATES`) validated by `TaskService.create` (422 otherwise). The engine host resolves `EngineSettings.layered(...)` and writes `<run>/settings.json`; the orchestrator never reads `engine.json`. All other flags are file-only. The owner edits them in Settings through `GET` and `PUT /api/engine/settings[?dept=]` (engine adapter, token, atomic 0600 write, `set`/`unset`, 422 on unknown or locked fields); `LOCKED_FIELDS` (live email, recipients, Chrome path, force_* and test switches) stay hand-edit only. Changes apply to the next run.
- **Why.** J2's defaults stay in one place; dangerous switches cannot be set by a model reply or a web request; the owner gets a real control; only the engine knows what it uses.
- **Rejected.** All fields in `RunSpec.settings`; an orchestrator copy of defaults; env only; a SQLite table; PUT of locked fields.
- **Changes.** engine §4.4, §4.7, §5, §7.1 (rows 31-32), §9, §10 E4 · orchestrator §3.3, §3.4, §6.2, §4.2 · ui §6.6 Settings and §8 · `test_contract_settings.py`.
- **Label.** settings: 2 files + 7 task keys · edit in Settings

### S1-contracts-04 · `stop_live`
- **Decision.** `stop_live(dept) -> bool`, sync, only for `POST /api/reset?dept=`. Stops a `waiting_user` task through the stop ladder (outcome `reset by you`), cancels the team's queued and blocked tasks, returns True when nothing of the team is starting or running afterwards (also when there was nothing), and False, touching nothing, when a task is starting or running. The reset handler turns False into 409 `{"ok":false}` and True into `page.json.since_run = latest run id` plus 200. History is never deleted. The engine process just receives the ordinary stop line.
- **Why.** The sections agreed on name and bool; they had not said the no-task case (J2's "Try again" calls reset after a crash), queued tasks, or sync versus async.
- **Rejected.** Killing a running task; deleting history; async `stop_live`.
- **Changes.** orchestrator §3.4, §5.5, §7 · engine §4.9, §6 F9, §7.1 row 30, §9.
- **Label.** reset stops a waiting team, never a running one

### S1-contracts-05 · Usage rows
- **Decision.** One builder, two sinks, one ledger writer. The Router builds exactly one `UsageIn` per request (failures included) and gives it to a `UsageSink`: `UsageStore` in the server (chat agent, `records_usage = True`), `EventUsageSink` in an engine process (appends a `usage` event; the server's Projector writes the row). `UsageIn` and `UsageSink` are defined once in `connectors/usage.py` (fields add `step` and `atom_id`). `usage_ledger` gains `step` and `atom_id` (no foreign key) and keeps nullable `detail_json` (A2 accepted). `call_ref = '{run_id}:{call_no}'` when `call_no > 0`, else `'r:{request_id}'`; unique `(task_id, call_ref)` with `ON CONFLICT DO NOTHING`. `atom_id` is stored as given for a function atom and as `<run_id>:<atom>` for a J2 workflow atom (S2-models-10). Tokens always; `usd` where the provider reports it (Claude list-price delta), NULL for Codex without rates; stub rows excluded from totals; credits never converted. `ChatStore.note_provider` keeps the session chip current.
- **Why.** `call_finished` fires only from `J2Run.call`; the summary, template, reviewer, planner and judge calls (j2.py:3113, 8372, 9514; j2_realization.py:685) would be missing, and failures too. Connectors risk 11 misread the sections: they agree.
- **Rejected.** Usage built in the shim from `call_finished`; the engine writing SQLite; a second `UsageIn` in ORCH.
- **Changes.** connectors §2, §3.8, §3.10, §9, §10 · engine §4.1, §4.3, §4.5, §4.9, §6 F1, §11 ENG-D3 · orchestrator §3.3, §3.5, §4.1 DDL, §5.6 · `test_contract_usage.py`.
- **Label.** router builds one row per call · server writes it

### S1-contracts-06 · Allowance
- **Decision.** The caller that owns the envelope enforces it. `J2Run` keeps its own accounting (credits, `model_call_limit`, `retry_limit`) and sends `allowance=None`; the chat agent sends none; the router applies its ceiling of 6 invocations and the timeout. Credits are never converted to usd. Over-allowance raises `EnvelopeExceededError` before any spawn; the capability stays for the function-node layer (`Allowance(max_calls=3, envelope_id=<atom>)`).
- **Why.** J2 never counted the llm layer's retry and does not enforce `time_limit_minutes` or `stop_loss`; two counters are two truths (CD10).
- **Rejected.** `max_calls` = remaining J2 calls; credit-to-usd conversion; a router-side counter.
- **Changes.** connectors §3.6, §9 CD10 · engine §4.1, §9 · test asserts `allowance is None` for every engine tag.
- **Label.** envelope kept by caller · router ceiling 6

### S1-contracts-07 · CallTag mapping
- **Decision.** `CallTag.purpose` is an open string (`^[a-z_]{1,24}$`; documented set includes `chat_plan`, `chat`); `CallTag.step` stays the J2 step number; `AsyncConnector` maps ORCH's string `step` to `CallTag.stage`, `function` to `CallTag.function`, `context.purpose` to `CallTag.purpose`.
- **Why.** ORCH passes `step='decide'` and `purpose='chat_plan'`; the tag had an int and a closed Literal.
- **Rejected.** Extending the Literal; a string `step`.
- **Changes.** engine §4.1 · connectors §3.10, §3.1 · `test_orchestrator_port.py`.
- **Label.** (none)

### S1-contracts-08 · A2-A4
- **Decision.** A2 accepted with five corrections: positional `session_hook(session_id, provider, model, provider_session_id)` = `ChatStore.set_provider`, plus `note_provider` (connector and model only); `transcripts=ChatTranscripts(chats)`, a new adapter, not the `ChatStore`; `events=` through `EventBus.publish_one`, and the SSE table gains `connector.health|switch|mode`; `build_api_router(router=..., write_guard=require_token)` mounted by ORCH-8, with the wrong "ENG §4.8" guard reference and the dangling `/api/engine/preflight` fixed; `build_router` reads only `data_dir`, `connector`, `offline` from `Settings`. A3 accepted. A4 narrowed to Test per provider and Codex Sign in (no pin control). The session API stays (the diagram names it) with no v1 caller: the chat agent keeps one-shot `call_json`; engine calls are one-shot and stateless.
- **Why.** Checked against what ORCH 3.5 calls: `transcripts=chats` has the wrong signature; connector events had no SSE rows.
- **Rejected.** `ChatStore` as `TranscriptSource`; deleting the session machinery now; `set_provider` from one-shot calls.
- **Changes.** orchestrator §3.4, §3.5, §4.2, §6.3, ORCH-2/3/8 · connectors §6, §9, §3.6, §10 · ui §6.6 and §8 (Settings, Connectors rows).
- **Label.** sessions: set_provider + transcript hook wired

### S1-contracts-09 · The final run-event list
- **Decision.** Eight events, closed union on `t`, `at` (ISO UTC) on every line: `run.started`, `say`, `node`, `step`, `atom`, `usage`, `heartbeat`, `run.ended`. Fields in Appendix A. The `session` event is removed (J2 calls are one-shot and stateless; the chip comes from `usage`). `node` takes S2-models-08's forms (`task{id 't-<n>', kind, summary, state, set_by}`, context strings, no `goal`) and gains `wait_on`, `tokens`; `atom` gains `refused` and, for `work-atom/0.3`, S2-models-07's `outcome`, `card`, `ledger` (timestamps are epoch seconds); `usage` gains `ok`, `how`, `atom`, `detail`; `run.started` gains `schema`, `mock`, `seed`; `run.ended` gains `code`. Publisher: every 250 ms and at turn boundaries, order node, step, atom. `run.started` is emitted after the seed decision; early failures emit only `run.ended`. The Projector tolerates unknown fields (noted once) and skips unknown types; tests parse strict. `validator` lines go to the session of `next`; `speaks_to` edges are projected from `say`.
- **Why.** No timestamp meant replay stamped every message with the replay time and reconcile could not judge age; `session` fires on every one-shot call with nothing resumable; `usage` lacked `ok/how/detail/atom`; `refused` was missing; no machine-readable end code.
- **Rejected.** A `turn` event (duplicates `node.task.state` and the atom lines); keeping `session`; a `seq` field; closed parsing in production.
- **Changes.** orchestrator §3.3, §5.6, ORCH-1/6 · engine §3.3, §4.3, §4.5, §4.6, §4.7, §11 · S2's unconditional `test_engine_events_contract.py`, mirrored in `test_contract_run_events.py` (CT-1).
- **Label.** events: run.started · say · node · step · atom · usage

### S1-contracts-10 · Function nodes on the wire
- **Decision.** No new event type (S2-models-07 agrees). A function turn starts and ends as `node.task.state` running to done (task id `t-<turn_no>`, S2-models-08); each turn is one `work-atom/0.3` record (S2-models-06). The layer (`engine/fnodes/layer.py`, `SUTRA_HOOKS`, S2-models-05) writes every transition as one `atom` line, synchronously, with the library's outcome, card and ledger row (S2-models-07); the 250 ms publisher writes only `atom/1` lines. Every model request of the turn, helper calls included, carries `tag.atom`: the layer binds it with `llm.bind_atom(atom_id)` after `open_atom` and clears it at `turn_finished` and on every run-end path. The Router puts it in `UsageIn.atom_id`, so cost sums per atom; usage is not built from `call_finished`. Atom ids and storage keys are S2-models-10's (library helpers mint function ids; `W-n.aK` is stored as `<run_id>:<id>`). The Projector fills `session_id`/`department_id`, gates the body, takes forward moves only, stores the shipped card as a `card` chat message in the node's own session (`src_ref '<run_id>#atom:<atom_id>:<outcome>:<attempt>'`), appends the ledger row, and abandons a finished task's open function atoms (`run.ended` or `reconcile`). The layer abandons its own open atom through the existing `run_status` and `run_error` hooks; there is no `run_ended` hook. A refused open warns and the turn proceeds in v1.
- **Why.** S2 settles the layer, the lifecycle, the ids and the atom fields; S1 must not contradict it and fixes only the process-contract points. The tag-bound atom id is needed because the Router builds usage rows.
- **Rejected.** A second event for function atoms; server-minted ids or server-rendered cards; a `run_ended` hook; usage built from `CallInfo`.
- **Changes.** engine §4.2 (`llm.bind_atom`), §4.3, §4.5 usage row · orchestrator §5.6 usage and `run.ended` rows · tests in E0 and CT-1.
- **Label.** every call tagged with its atom · cost per atom

### S1-contracts-11 · Run folder, D9, spawn, environment
- **Decision.** D9 is confirmed: one process per task, `python -m sutra_app.engine --run-dir`, files only, exits after `run.ended`, a waiting run stays alive. The orchestrator creates the folder (`0700`, `exist_ok=False`, new id on collision), writes `task.json` atomically (`0600`), creates empty `inbox.jsonl` and `events.jsonl`, then spawns; the engine never creates it and exits 2 when the layout or `task.json` is wrong. The child environment is one allowlist shared with the connectors, `connectors.env.PASS_NAMES`, plus `SHELL`, `TERM`, `PYTHONPATH`, `SUTRA_*` except `SUTRA_TOKEN`, and the seven task keys; the CLI children then drop every `SUTRA_*`. `RunSpec` (writer) and `TaskSpec` (reader) stay two classes with a contract test.
- **Why.** ORCH's launcher list lacked `CLAUDE_CONFIG_DIR`, `CODEX_HOME`, `XDG_*`, proxy and certificate variables, so an engine host would pass its CLIs a different login directory; `PYTHONPATH` is needed for worktree runs.
- **Rejected.** The engine making its folder; threads or pipes; two allowlists; the full environment.
- **Changes.** orchestrator §5.6, §3.5, §7 · engine §4.7, §3.4 P3, §11 ENG-D2 · connectors §2, §4 · `test_contract_env_and_spec.py`.
- **Label.** process per run · files only · server makes the folder

### S1-contracts-12 · Follow-ups: rehydrate or fresh
- **Decision.** A follow-up is always a new task, run id, folder and process; the old folder is read-only history. `seed_from` is set in two places only: `deliver`/`deliver_to_department` without a live task, and `create(follows=<task of the same department>)` (chat agent assignments, `POST /api/tasks` with `follows`); never by retry. The engine tries `rehydrate`, else starts fresh with the old files in `upstream/<old>/` and one plain system line. Rehydrate is allowed for `done` or `done_with_open_items` website runs without a document chain; realization on or off is no longer a condition, and `real`, `real_base`, `real_summary`, `real_asked` are restored when `realization.json` exists. **The pause is explained** (Appendix B): with realization on J2 loads no rate card (j2.py:2893), the mock change proposal has no `estimated_resources`, so cost is 0 (j2.py:6652), twice, then the limit question (j2.py:3465). It happens without rehydrate too. Orphaned-question rule: answering a question of an ended task makes a follow-up whose `framing` carries that question. `upstream[].files` are relative to the upstream run's folder, checked for `..` and escaping links.
- **Why.** J2's "Tell us if you want changes" needs the old state; the probe removed the only obstacle; the fresh path keeps everything else working.
- **Rejected.** Standby processes; pickling `J2Run`; refusing follow-ups; a J2 patch P12 for the mock; always rehydrating.
- **Changes.** engine §2, §4.8, §6 F4, §10 E1-b, §12, `test_engine_rehydrate.py` (control, scripted realization, refusals) · orchestrator §5.5, §6.2, §3.4 · live test in `test_engine_live.py`.
- **Label.** follow-up: rehydrate, else fresh with old files

### S1-contracts-13 · Non-blocking `user_says`
- **Decision.** P4 accepted (lock order defeated J2's own `status == 'running'` check). Nobody calls `user_says` from HTTP: the orchestrator answers 409 from the task row. The host's 150 ms tick is the only caller, and a False result is the normal path for an answer sent right after a question (the run thread is still finishing its summary): lines are read in `n` order into a FIFO, the head is retried, one trace line `inbox.deferred` is written, `stop` is handled when read and discards what is queued behind it.
- **Why.** Keeps J2's intent; makes the answer race deterministic instead of lossy.
- **Rejected.** Blocking in the host; dropping a busy line; sending lines to a running task.
- **Changes.** engine §3.4 P4, §4.5, §4.7, §9 · orchestrator §5.5.
- **Label.** answers queue while a run finishes its turn

### S1-contracts-14 · `SUTRA_MAX_RUNS` and 81 MB
- **Decision.** `SUTRA_MAX_RUNS` (3) counts `starting|running`; new `SUTRA_MAX_LIVE` (12, about 1 GB idle) counts every live process. A run that pauses frees its slot and triggers `start_ready()`; the owner's answer is never queued. Held-back tasks show "waiting for a free slot". No idle reaper in v1.
- **Why.** Counting waiting runs would let three questioning teams starve the other two assignments of one request.
- **Rejected.** Counting waiting runs; no cap; a timed reaper; hibernation.
- **Changes.** orchestrator §3.4, §5.6, §6.2, §6.4, §7, §10, ORCH-1/6 · engine §2, §12.
- **Label.** max runs counts working teams; waiting ones idle

### S1-contracts-15 · Shutdown and the stop ladder
- **Decision.** One ladder for "stop this task" and shutdown: stop line, `STOP_GRACE_S = 8`, SIGTERM to the group, `TERM_GRACE_S = 4`, SIGKILL (worst case 12 s). Shutdown runs the ladders of all live tasks in parallel, drains, takes the status from `run.ended` else `stopped` ("the app was closed"), cancels watchers, checkpoints WAL. The engine finishes a stop inside 6 s (`stopping` flag skips reviewer and report). A run stopped while waiting continues as a fresh follow-up (S1-12).
- **Why.** The sections gave 5/5 and 10/5; the engine's real work is small (Claude exits in 1.3 s on SIGINT).
- **Rejected.** Leaving waiting runs alive on exit; two ladders; SIGKILL first.
- **Changes.** orchestrator §5.1, §5.6, §7 · engine §6 F5 F6, §4.7.
- **Label.** shutdown: stop · 8 s · SIGTERM · 4 s · SIGKILL

### S1-contracts-16 · Crash detection and stale-run recovery
- **Decision.** Heartbeat from a daemon thread every 5 s; `last_event_at` is the `at` of the newest applied line. While the server runs: crashed = no terminal event and `alive(pid)` False after a final drain; a silent but alive process is flagged "no signal for N s", never killed. At start `reconcile()`: drain from `events_offset`; terminal event settles; alive and fresh (<= 30 s) re-attaches; alive but silent only runs the ladder if `ps` shows `sutra_app.engine --run-dir <dir>`, else nothing is signalled; pid gone, or `starting` with no pid, is crashed; `starting` with a live pid and no event within 30 s of the spawn (`last_event_at` is seeded with the spawn time) follows the silent rule; crashed tasks abandon their open atoms; ends with `server.resync`.
- **Why.** Age from receipt time is wrong after downtime; the identity check avoids killing a reused pid.
- **Rejected.** Killing silent processes while running; staleness by read time; trusting the pid.
- **Changes.** orchestrator §5.1 step 6, §5.6, §7 · engine §4.5, §4.7, §6 F7 d.
- **Label.** crash = process gone, or silent 30 s at app start

### S1-contracts-17 · Diagram text and the billing guard
- **Decision.** Codex connector line 2: `ChatGPT login or API key in the keychain` becomes **`your ChatGPT login, never an API key`** (36 characters). Codex CLI box: `installed and signed in through Sutra` becomes **`on this Mac · signed in via Sutra`** (33). The Claude boxes stay. The guard is stricter: an API-key login is refused with no override (`allow_api_key_billing` removed); only a positive api_key status is refused, unknown methods are allowed.
- **Why.** D7 and the Claude box say never an API key; Sutra does not install CLIs; the proposed strings (56 and 47 characters) do not fit boxes of about 41 characters.
- **Rejected.** The CD13 and CD17 proposals; the original wording.
- **Changes.** diagram (two strings) · connectors §3.5, §3.6, §9 CD13 CD17, `policy.default.json`, tests.
- **Label.** your ChatGPT login, never an API key

### S1-contracts-18 · One JSON extractor (settled by S2-models-12)
- **Decision.** Adopt S2-models-12: `library/replies.py` holds the single copy of `extract_json` and `close_json`; `engine/llm.py` re-exports it, `connectors/jsonio.py` imports it, E0 and CN-1 depend on L1. S1 adds only a check that the three names are the same object (`test_contract_json_extract_parity.py`, CT-1).
- **Why.** S2-models-12 owns shared helpers and the import-direction rule; the first S1 draft (verbatim engine copy plus parity test) is withdrawn to avoid contradicting it.
- **Rejected.** A separate S1 rule; a connectors-owned copy.
- **Changes.** none beyond the CT-1 test.
- **Label.** (none)

### S1-contracts-19 · Owner override key
- **Decision.** The server holds `J2_OVERRIDE_KEY` (`Settings.override_key`, from env or `SUTRA_ENV_FILE`). A text starting with the key is an override: accepted only for a `waiting_user` task, sent as `{kind:'override', cmd}`, stored as "Owner override sent"; otherwise 409 and a note, never a task. The engine never sees the key. `redact` collects env values named KEY/TOKEN/SECRET/PASSWORD/AUTH plus every `.env` value (>= 8 characters).
- **Why.** Engine and ORCH both said the server checks the key, but ORCH's `Settings` had no field and nothing loaded `.env`.
- **Rejected.** The engine checking; storing the key; matching it anywhere in the text; a follow-up from an override.
- **Changes.** orchestrator §3.1, §5.5, §6.4, redact · engine §4.4 · tests.
- **Label.** override key stays on the server

---

## Appendix A · The final run-event list (normative)
Every line: `{"t": <type>, "at": "<ISO-8601 UTC Z>", ...}`, one `os.write`, readers take only complete lines. Eight types.

| `t` | Fields | Producer | Projection |
|---|---|---|---|
| `run.started` | `pid:int`, `schema:'events/1'`, `mock:bool`, `seed:'none'\|'rehydrated'\|'fresh'` | host, after the seed decision | task `running`, pid stored |
| `say` | `id:int`, `who` (identity, adaptation, priority, coordination, audit, validator, system, `W-n`, `team:<role>`; never `user`), `text`, `to_user:bool`, `act`, `pause`, `questions`, `next` | `message_posted` | `src_ref '<run>#chat:<id>'`; identity+to_user to the department session (question: task `waiting_user`, needs-you card); function to its session; `validator` to the session of `next`; `system` to Identity; `speaks_to` edge from `who` to `next` |
| `node` | one of `fn` or `step` (`W-n` or `team:<role>`); `status` (the nine map words; functions use the first five); `detail`, `calls`, `seconds`; optional `task{id:'t-<n>', kind, summary, state:'running'\|'done', set_by}`, `context[str]` (`'<kind>: <summary>'`, up to 40 of 200 characters), `wait_on`, `tokens{input,output}`; no `goal` (S2-models-08) | StatePublisher (250 ms, turn boundaries) | `GraphStore.put_node`; running needs `task`, waiting needs `wait_on`; `last_seen` from `detail`, `stats` from calls, seconds, tokens |
| `step` | `step:'W-n'\|'team:<role>'`, `name`, `parent`, `status`, `handoff[]`, `reads[]`, `rework` | StatePublisher | step node, `handoff` and `depends_on` edges |
| `atom` | `node`, `atom{id, schema:'atom/1'\|'work-atom/0.3', goal, work_kind:'llm\|skill\|bash\|manual', verify_template, status, attempt:0..3, closed_by, reason, body, ts_open:int, ts_closed:int\|null}` (epoch seconds); status `open\|closed\|verify_failed\|abandoned` for atom/1, `open\|closed\|refused\|abandoned` for work-atom/0.3; work-atom/0.3 only: `outcome`, `card`, `ledger` (S2-models-07) | publisher (atom/1), function-node layer (work-atom/0.3, synchronous) | forward-only upsert (atom/1 key `<run_id>:<id>`); card message and ledger row for work-atom/0.3 |
| `usage` | `fn`, `step`, `atom`, `provider`, `model`, `purpose`, `usd`, `tokens_in`, `tokens_out`, `seconds`, `ok`, `how`, `call_ref`, `detail` | Router or ScriptedPort through `EventUsageSink` | ledger row, `ON CONFLICT DO NOTHING`, chip |
| `heartbeat` | none | daemon thread, 5 s | `last_event_at` |
| `run.ended` | `status:'done'\|'done_with_open_items'\|'stopped'\|'crashed'`, `outcome`, `code` | host, last line | task terminal; atoms abandoned; dependants; `start_ready()` |

Removed: `session`. Unknown fields: `parse_event(strict=False)` drops the keys a variant does not declare (noted once per run) before validating, so the variants stay closed Values (S2-models-01); tests use `strict=True`. Unknown types: skipped with a note.

## Appendix B · Evidence for the realization pause (S1-12)
Probe in a scratch copy of J2 `ce2631f` (Brew Lab, mock mode; scripts `rehydrate_probe.py` variants under the session scratchpad `s1/j2/`; `j2.py` byte-identical to the repo):
1. Realization on, rehydrated run, change request: "Validator rejected 'Requester change': its cost is 0", twice, then Identity's limit question (the pause the engine section saw).
2. Realization on, the same `J2Run` continuing after Done (no rehydrate): the identical pause.
3. Realization on, rehydrated, rate card put back with `load_rates('website', card=True)`: Done, workflows 8 to 9, sites 7 to 8, with or without restoring `real*`.
Cause: `j2.py:2893` loads no rate card when realization is on; the mock reply of the change branch (`_turn_adaptation`, feedback) has `parts` but no `estimated_resources`; `_register` refuses cost 0 (`j2.py:6652`); two empty cycles trigger the limit question (`j2.py:3465`). A real model fills `estimated_resources.money` (format at `j2.py:5125`); that is expected, not verified live.

## Appendix C · Work packages touched
`add` CT-1 (cross-section contract tests). `change` (append): E0, E1, E3, E4; CN-1, CN-4, CN-6, CN-7; ORCH-1, ORCH-2, ORCH-3, ORCH-6, ORCH-8; UI-7. No package is removed. New dependencies: ORCH-3 on CN-6; ORCH-6 on CN-1; CT-1 on E0, E4, CN-7, CN-9, ORCH-1, ORCH-6.

## Appendix D · Unresolved (with the fallback and the test)
1. **Function-node spec not final.** Fallback: atom per function turn, warn on refuse, the engine ships outcome, card and ledger; the wire does not change; `test_engine_events_contract.py` and `test_projector_fnodes.py` (S2-models-07) fail first.
2. **Realization follow-up with a real model.** Fallback: rehydrate allowed; the live follow-up test decides; one `realization == 0` condition can be put back.
3. **`ps` identity check across platforms.** Fallback: silent-but-alive with unreadable command is treated dead without a signal; `test_reconcile_pid_reuse_not_signalled`.
4. **Quota knowledge is per process.** Fallback: each process re-learns with one failed call and falls back to Codex with a note.
