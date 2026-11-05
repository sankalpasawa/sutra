# Sutra Pro: design overview

One page. The authority for any detail is the section it links to; for any choice it is `docs/DECISIONS.md`. This page
describes the app AS BUILT on `main` (the as-built notes are `docs/notes/<package>.md`). The machine-checked map from every owner
rule, decision, endpoint and package to modules and tests is `docs/TRACEABILITY.md` (data: `docs/design/traceability.json`,
generator: `scripts/build_traceability.py`).

## 1. Purpose

Sutra Pro is a local web app for one owner. The owner talks to one chat. The chat agent reads ONE global org chart of departments
(teams), reuses a team that fits or adds, rearranges or merges teams, and hands the work to a department. Each department does its
work with the J2 prototype's loop (Identity, Adaptation, Priority, Coordination, Audit), where each of the five functions is an agentic
graph node with a goal, constraints, context and a work atom whose `verify` check is the teeth. Every model call goes through a connector
layer with a Claude connector and a Codex connector (CLI first, on the owner's own logins). The app serves the J2 page for each team
and adds a home page, a workflow graph and an org chart in the same design language. It runs on `127.0.0.1` and pushes nothing anywhere.

## 2. The five tiers as built

Source of the tiers: the owner's draw.io page 3, redrawn in `docs/diagram/gen.py` (figure notes in `docs/diagram/README.md`).

| Tier | What it does | Modules as built (packages) |
|---|---|---|
| Experience | Home (start page, org chat, rail), the J2 page per team at `/d/{dept}/`, graph, org chart, node drawer, Settings | `sutra_app/ui/` : `boot.py`, `routes.py`, `pages/` (home, J2 page port, graph layout), `static/js/` (`sutra_ctx`, `sutra_events`, `graph_*`, `orgchart_view`, `fnode_view`, `node_panel`, `chat_view`, `settings_view`, `home`, `dept_ext`) (UI-0 to UI-9) |
| Orchestration | Chat agent (decide, change, assign), org chart store and rules, tasks and run launcher, watcher and projector, event bus and SSE, stores, the HTTP API, the app shell | `sutra_app/orchestrator/` : `agent/` (chat agent, `demo.py`), `chart.py`, `chart_rules.py`, `departments.py`, `nodes.py`, `graph.py`, `chats.py`, `atoms.py`, `usage.py`, `tasks.py`, `runs.py`, `projector.py`, `events.py`, `redact.py`, `api/`; `sutra_app/main.py`, `__main__.py`; `sutra_app/ops/` (doctor, lock, logging, config, browser) (ORCH-1 to ORCH-8, GAP-OPS-1, GAP-DEMO) |
| Department runtime | One process per run: J2's loop run by the five functions, its workflow builders and validators, the 30 views, the function-node layer, the run-event stream | `sutra_app/engine/` : `j2*.py` (vendored, P1-P11), `views.py`, `api/` (FastAPI adapter), `host/` (loop, heartbeat, inbox, publisher), `fnodes/` (layer, declare, registry of 14 checks, checks, evidence), `rehydrate.py`, `features.py`, `spec.py`, `events.py`, `port.py` (E0 to E8, GAP-W1, GAP-TUNE, GAP-E1B) |
| Connector layer | `ModelConnector` base, `ClaudeConnector`, `CodexConnector`, `StubConnector`, router with policy, health, transcript carry-over and usage rows, ports for the engine and the orchestrator, tools (MCP) | `sutra_app/connectors/` : `base.py`, `claude.py`, `codex.py`, `stub.py`, `router.py`, `policy.py` (`policy.default.json`), `health.py`, `transcript.py`, `usage.py`, `engine_port.py`, `orchestrator_port.py`, `factory.py`, `api.py`, `tools/` (CN-1 to CN-9) |
| Server contents | SQLite (the server is the only writer), run folders and blobs, the interface library of closed pydantic models, the template library | `sutra_app/orchestrator/db.py`, `schema.py`, `records.py`; `sutra_app/library/` (closed models, registry, write gate, wire documents, `specs/function_specs.json`, `artifacts/`, `templates.py`) (L1 to L10); data folder `~/.sutra-pro` or `SUTRA_DATA_DIR` |

Flow of one request: chat message -> chat agent (three staged structured calls through the connector router) -> one org chart change
(reuse, add or rearrange; `ChartChange` record) -> assignment -> task -> `python -m sutra_app.engine --run-dir` (one process per run)
-> run files and `events.jsonl` -> watcher -> projector -> stores, atoms, usage rows -> event bus -> SSE -> page. Every layer speaks to the
next only through files, the closed library models, or the one model seam `make_port(PortSpec) -> ModelPort`.

## 3. Owner rules, the decisions and the modules that carry them

| Owner rule | Decisions | Implemented by | Proved by |
|---|---|---|---|
| New app, no relation to the old sutra-ui; its design is the J2 prototype's | D1, D4, D6, D13, D89, D90 | `sutra_app/engine/` (vendored J2), `sutra_app/ui/pages/j2_ui.html` (the port) | `tests/engine/test_engine_vendor.py`, `tests/ui/test_port_edits.py` |
| ONE global org chart; tasks reuse, add to or rearrange it, never one per workflow | D26, D42, D43, D44, D67, D68, D70 | `library/org_chart.py`, `orchestrator/chart.py`, `chart_rules.py`, `agent/planner.py` | `tests/library/test_lib_org_chart.py`, `tests/orchestrator/test_chart_store.py` |
| Five function nodes: goal, constraints, context, work atom, `verify` is the teeth | D49 to D66 | `engine/fnodes/`, `library/node.py`, `atom.py`, `functions.py`, `orchestrator/atoms.py` | `tests/engine/test_engine_fn_*.py`, `tests/library/test_lib_atom*.py` |
| Connector layer with a Claude and a Codex connector, CLI first | D7, D17, D27 to D38 | `sutra_app/connectors/` | `tests/connectors/` (fake CLIs, stub) |
| Everything in the J2 prototype is present | D4, D13, D25, D46, D47, D84, D90, D91 | `engine/features.py`, `views.py`, `api/`, `library/artifacts` | `tests/engine/test_engine_features.py`, `_views.py`, `_prompts.py`, `_legacy.py`, `tests/contracts/` |
| Local only: bind 127.0.0.1, never push, never open PRs | D1, D11, D81, D89 | `main.py` (loopback Host guard), `scripts/wt.sh` | `tests/orchestrator/test_api_security.py`, `tests/test_build_plan.py` |
| Every decision documented, in the design and as a badge on the diagram | D1 to D97 | `docs/DECISIONS.md`, `docs/diagram/decisions.json`, `gen.py` | `tests/contracts/test_contract_diagram_strings.py`, `tests/test_traceability.py` |

How the five function nodes work (the authority is `docs/design/function-nodes.md`): one turn is one atom, declared before the work
(AI, code or a question to the owner) with a named `verify` check from a registry of fourteen pure functions (D53, D54). The layer
runs inside the engine process; the server stores forward moves only (D51, D58). Version 1 observes: a failed check fails the atom, not
the turn (D52). Every model call is charged to one atom id (D59); the append-only Atom log is the `atom_ledger` table (D60).

## 4. As-built deviations that matter

From the "deviations" sections of the notes; each names its package. The specification text of a package is the section file, the as built
text is its note.

- CN-1: `connectors/__init__` loads `Router`, `build_router`, `make_port` lazily (a module `__getattr__`), because their modules merged later.
- CN-4: Codex images go BEFORE `-m` (`-i` is variadic), and the reply is the last non-blank `agent_message`.
- CN-6: `UsageIn.how` allows `text`; `Rate` has an optional fourth price (cache write); a counter that goes backwards is taken whole (CD5).
- CN-7: `max_attempts` counts tries per provider; the router reads no environment (`mode_from_env()` does, for the factory).
- CN-8: the Sutra MCP server accepts `--db` and `--gh-exe`; a tool failure is an `isError` result, not a JSON-RPC error.
- CN-9: a missing required CLI flag is recorded as the existing `flag` cooldown (no new "degraded" state); stub and offline never probe a CLI.
- E0: a real empty reply raises `EmptyReply`; in mock mode `PROVIDER` and `MODEL` stay None as in J2's files; `atom` events carry `card` and `ledger`.
- E1: `rehydrate` restores `calls` from `summary.json`, so a continued run starts one call short and ids stay unique.
- E2: `RunCtx` gained `dept_id`, `commands`, `here` and `vendor`; a bad number in `since` or `id` reads as 0 (J2 crashed its thread).
- E3: `run.started` is emitted after the seed decision and before the host's own system lines.
- E4: the five POSTs and the PUT read the body by hand, so a non-object body is J2's 400 `bad json`, not FastAPI's 422.
- E6: `factory(..., spec=)` is the host's name for the task spec; the reply phase runs only checks whose registry phases include `reply`.
- GAP-W1: a default run now builds the function layer (G01); stop and SIGTERM abandon open atoms; `.env` defaults beside the data outside a checkout (D95).
- L3, L4, L5: bounds are wider than the spec where J2 data showed longer values; department steps are typed `AIStep | CodeStep` only.
- L8: `gate_record` in `log` mode returns warning strings, which `engine/hooks.py` already turns into `record.warning` trace lines.
- ORCH-2: control events (`server.hello`, `server.resync`) carry no sequence number and never enter the replay ring.
- ORCH-6: a follow-up's `seed_from` lives in `tasks.settings_json` under the reserved key `_seed_from`.
- ORCH-8: the Host guard is its own ASGI middleware (the envelope `bad_host`); `create_app` starts nothing, the lifespan does.
- GAP-OPS-1: lock and logging are taken in `run`, not `create_app`; the lock is taken before the socket is bound; `config init` writes the effective env file.
- GAP-TUNE: nine refused replies were three validator defects, loosened in the classes only; `reply-valid` and every J2 prompt are unchanged.
- GAP-E1B: a follow-up after a finished document chain is rehydrated and the change goes to Adaptation for the last stage, as J2 does.
- UI-3, UI-5, UI-8: after an error the first `server.hello` acts as `server.resync`; pan and zoom are the pane's own (no d3.zoom); the stream opens with the first view.
- GAP-DEMO: `--offline` answers the chat agent from the message with a small reply book (D97); `stub.py` is untouched.

## 5. Known limits

From `docs/design/gaps.md` (low findings, no package unless noted) and `docs/notes/GAP-DEMO.md`.

- G18 `enforce` mode is reserved: "verify is the teeth" is observed, not enforced (D52); `SUTRA_NODES=enforce` raises. Decide after the live false-failure rate is known.
- G19 Quota and cooldown knowledge is per process; a new run re-learns it with one failed call.
- G20 The architecture diagram is not refreshed past D87 and `gen.py` is unowned; D88 onwards have no pills yet.
- G21 Excluded J2 material (older studio, negotiation demo, explainer pages) is recorded by D91, not ported.
- G22 One accepted contrast exception (dark, filed node second line, 4.22:1) in `tests/ui/js/contrast.test.js`.
- G23 No spend circuit breaker across the whole app; the subscription quota is the real limit (D38).
- G24 Seed library templates are copied once; `doctor` reports missing ones, `config sync-library` copies them (GAP-OPS-1).
- G25 One runtime copy of the artifact models (`E1-c`) is open; `tests/library/test_lib_engine_parity.py` is the guard.
- G26 Nothing tells the owner that a team asked a question when no tab is open.
- G27 No dependency audit or secret scan in CI; dependencies use `>=` ranges.
- Offline demo (GAP-DEMO, D97): no Claude or Codex; every message becomes a new task for one team, named from its first words; rearranging,
  status and small talk are not understood; the Test, sign-in and check-connectors buttons answer 409 `offline`; all usage rows are `stub`, usd 0.
- Not yet merged when this page was written: GAP-E2E and GAP-E2E-UI (the real-process scenarios and the browser walk), GAP-LIVE (live smoke
  with the real CLIs, run only on the owner's word), GAP-CONSOLE, GAP-DATA, GAP-DOCS, GAP-INSTALL. Eight design fallbacks wait on live
  evidence (G07), among them `anyOf` chart ops, Codex native schema and image input.

## 6. How to run

Needs Python 3.11 and `uv`. The Claude CLI and the Codex CLI are used only when you sign in to them yourself; `--offline` needs neither.

```
uv venv .venv --python 3.11 && uv pip install --python .venv/bin/python -e ".[dev]"
scripts/run.sh                     # doctor (offline), then the server; opens Chrome when it is installed
scripts/run.sh --offline --no-browser --port 9000
scripts/py -m sutra_app doctor | status | stop | config show | open
scripts/gate.sh                    # the whole suite (Python and JavaScript), as the merge gate runs it
scripts/py scripts/build_traceability.py          # refresh docs/TRACEABILITY.md; add --check to verify
```

The server binds `127.0.0.1` only, on port 8780 or the next free one up to 8799. The data folder is `SUTRA_DATA_DIR` or `~/.sutra-pro`
when installed (D88). One instance per data folder (D94). Writes need the per-launch token (D81). Longer instructions (README.md, the
getting-started, operations, environment and troubleshooting documents of GAP-DOCS) may not exist yet; `sutra-pro --help` lists the flags and variables.

## 7. The packages by section

62 work packages, listed with their paths, notes and merge commits in `docs/TRACEABILITY.md` section F and ordered in `docs/BUILD-PLAN.md`.

| Section | Packages |
|---|---|
| library (`docs/design/library.md`) | L1 to L10 |
| engine (`docs/design/engine.md`) | E0 to E8 |
| connectors (`docs/design/connectors.md`) | CN-1 to CN-9 |
| orchestrator (`docs/design/orchestrator.md`) | ORCH-1 to ORCH-8, CT-1 (cross-section contract tests) |
| ui (`docs/design/ui.md`) | UI-0 to UI-9 |
| release | REL-1 (CI, wheel), REL-2 (macOS app bundle) |
| gaps (`docs/design/gaps.md`) | GAP-W1, GAP-OPS-1, GAP-TUNE, GAP-E1B, GAP-DEMO, GAP-TRACE merged or in flight; GAP-E2E, GAP-E2E-UI, GAP-LIVE, GAP-CONSOLE, GAP-DATA, GAP-DOCS, GAP-INSTALL planned |

## 8. Where to read more

- `docs/design/engine.md`, `connectors.md`, `library.md`, `orchestrator.md`, `ui.md`: the five section designs.
- `docs/design/settlements/` (S1 contracts, S2 models, S3 web, S4 function nodes): the rulings that were applied to the sections; a paragraph carries a tag like `[S1-contracts-03]`.
- `docs/design/function-nodes.md`: the authoritative design of the five function nodes (concepts in `function-nodes-spec.json`).
- `docs/DECISIONS.md`: every owner rule and decision D1 to D97, with what was rejected and where the diagram shows it.
- `docs/BUILD-PLAN.md` (from `docs/build-plan.json`): the packages, their paths and waves.
- `docs/design/gaps.md`: the coverage critic's findings G01 to G27 and the follow-up packages.
- `docs/design/j2-sync.md`: how the J2 baseline moved to `33aeeda`.
- `docs/TRACEABILITY.md`: owner rule, step, chip, endpoint, decision and package rows.
- `docs/RELEASE.md`, `docs/RELEASE-macos.md`: wheel and macOS releases (local only until the owner says otherwise).
