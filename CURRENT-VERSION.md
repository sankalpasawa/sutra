# Sutra — Current Version

## v2.4.0 (2026-04-25) — Tier 1.5 compositional reads

Permission-gate auto-approves safe read-only shell pipelines (ls, cat, grep, head, tail, wc, echo, printf, pwd, date, whoami, which, basename, dirname, realpath, cut, uniq, tr, column) composed via `; && || |` and stderr redirects `2>&1` / `2>/dev/null`. Python shlex-based tokenizer with 5-gate architecture (hard rejects, env shadowing, tokenize+fold, pipeline ops, per-primitive argv validation). `sh_lex_check.py` at `marketplace/plugin/lib/`. Charter §4 Tier 1.5 amended. 58+ unit tests + 11 integration + 1 rollback test, all green. Codex 10 rounds GO, Claude plan-eng-review GO.

Rollback: `bash marketplace/plugin/scripts/rollback-compositional.sh` strips `Bash(compositional-read:*)` from settings.local.json (idempotent, backs up once).

## v2.3.0 (2026-04-25) — additive: `sutra` CLI assistant subcommands

- **8 new `sutra` subcommands** for the Assistant Interaction Layer (v2.2.0 shipped the engine; v2.3.0 ships the terminal UX):
  - `sutra enable` — turn assistant on (removes kill-switch files)
  - `sutra disable` — persistent off via ~/.sutra-assistant-disabled (zero tokens)
  - `sutra explain [--last N|--turn N]` — narrative renderer
  - `sutra ask <surface> "question" "opt1,opt2,opt3"` — queue feedback prompt
  - `sutra answer <prompt_id> <option>` — answer a queued prompt
  - `sutra pending` — list unresolved feedback
  - `sutra profile` — show client profile
  - `sutra decommission [--dry-run|--confirm]` — product kill-switch
- All subcommands work in any client repo where `sutra` is on PATH (Claude Code auto-adds plugin bin/ to PATH).
- Founder directive 2026-04-25: "It should be able to update if the user says enable Billu — from the terminal itself." One command flips the switch in any company session.

# Sutra — Current Version

## v2.2.0 (2026-04-25) — additive: Assistant Interaction Layer

- **New OS class: Interaction Layer** at `os/interaction/`. First artifact: `ASSISTANT.md` charter. Sits above the 5 foundational blocks; human-facing surface for legibility, feedback capture, per-user customization (S2+), energy tracking (S5+), and passenger-mode problem-solving (S3+). Spec: `holding/research/2026-04-24-assistant-layer-design.md`.
- **5 new scripts in plugin hooks/**: `assistant-kill-switch.sh` (3-syscall zero-cost shim), `assistant-observer.sh` (turn.observed events, cursor-from-events-tip atomic), `assistant-explain.sh` (narrative renderer), `assistant-feedback.sh` (ask/list/answer/profile), `assistant-decommission.sh` (product kill-switch with atomic settings rewrite).
- **Stop hook registered**: `hooks.json` fires `assistant-kill-switch.sh` on every Stop; shim exits zero-cost if any of 3 disable flags active; otherwise exec's observer.
- **Default OFF at L1 per D32**. Clients flip `enabled_hooks.assistant_observer: true` in `os/SUTRA-CONFIG.md` to activate. 4-layer kill-switch (L1 Sutra authority / L2 user runtime / L3 per-instance / L4 product decommission).
- **Event contract v1.0**: `turn.observed`, `log.rewound`, `feedback.prompted`, `feedback.captured`. Envelope stable; payloads starting shape (will evolve at S2+).
- **39 tests green** at Asawa reference instance (9 kill-switch + 24 observer + 6 explain). Codex rounds: 4 absorbed (1 REJECT → MODIFY → PASS on approach/spec/P2/P3).

## v1.9.1 (2026-04-20) — additive

- **Charters as first-class OS concept**: new directory `os/charters/` parallel to `os/engines/` and `os/protocols/`. Holds cross-cutting Initiative Charters (vs. unit-level Definition Charters like `departments/*/CHARTER.md`). Placement doc + protocol for adding new charters in `os/charters/README.md`. Unit-architecture model documented: every unit (org, department, sub-unit) = definition charter + skills + initiative charter participations; cascades recursively.
- **Initiative Charter: Tokens** (`os/charters/TOKENS.md`) — first cross-cutting charter. DRI Sutra-OS; Contributors Analytics, Engineering, Operations. Applies to Sutra (first instance). Downstream propagation queued (requires `upgrade-clients.sh` extension — tracked in charter roadmap step 12). Q2 OKRs: baseline 6 companies × 10 sessions by Apr 26, boot P50 −30% and gov overhead <15% by Jun 30, propagate to ≥3 companies.
- **Follow-on formalization queued in TODO**: PROTO-019 candidate for unit-architecture + `ADDING-DEPARTMENTS.md` + schema extension for charters in `state/system.yaml`.
- Triggered by: Founder direction 2026-04-20 — "A lot of tokens have been used; we need to find some optimization ways" + "departments are skills; charters are cross-sectional; both cascade at every level."

## v1.9 (2026-04-15)

- **PROTO-017 Policy-to-Implementation Coverage Gate**: every edit to a Sutra policy file surfaces a PROTO-000 reminder (5-part rule); `verify-policy-coverage.sh` generates `POLICY-COVERAGE.md` ledger mapping every written commitment to its enforcer and deployed clients. Rows without both are DRIFT.
- **PROTO-018 Auto-Propagation on Version Bump**: `upgrade-clients.sh` walks the client registry on version change and reorganizes each client to the new manifest (sync engines, pin version, install declared hooks, register in settings.json). Closes the drift loop where version bumps in Sutra didn't propagate.
- **MANIFEST-v1.9**: tier-aware (1 governance, 2 product, 3 platform). Covers ALL shipping hooks, not just `enforce-boundaries.sh`. Asserts declared ⊆ installed invariant per client.
- **verify-os-deploy.sh extended** to accept `asawa` (holding) and `sutra` (self) as targets. Holding and platform are now in the verification universe.
- Triggered by: Billu onboarding audit (2026-04-15) — declared-but-not-installed hooks (RC4) + manifest silent on 95% of shipping hooks + recurring version drift. The drift pattern stops here.

## v1.8 (2026-04-11)

- **COVERAGE-ENGINE.md v1.0**: Runtime process coverage for client companies. Tracks whether every expected Sutra step fired during a session, per task, per depth. 26 trackable methods across 6 categories (gates, engines, lifecycle phases, verification, research, calibration). Expected checklist auto-generated from assigned depth (D1=4 steps, D2=7, D3=14, D4=19, D5=24).
- **method-registry.jsonl**: Machine-readable registry of all Sutra methods with depth requirements. Deployed to each company's `os/` directory.
- **Coverage hooks**: `log-coverage.sh` (logs method fires with evidence) + `coverage-report.sh` (reads log, compares to expected, shows gaps). Deployed to `.claude/hooks/`.
- **Coverage toggle**: `coverage: on|off` in SUTRA-CONFIG.md. Silent no-op when off. Zero overhead in production.
- **Evidence requirement**: Each logged method must include task-specific evidence, not generic claims. "goal: audit 47 pages" is valid; "defined objective" is not.
- **Aggregation**: Task-level, session-level, and 30-day rolling company-level coverage reports.
- Triggered by: Founder direction 2026-04-09 — "when a client company is running on Sutra, I want to monitor whether all methods are being used." Tested on Dharmik (2 tasks, 100% coverage). Deployed to DayFlow.

## v1.7 (2026-04-06)

- **ADAPTIVE-PROTOCOL.md v3**: "Gear" renamed to "Depth" (customer focus). 5 depth levels (1-5) controlling task decomposition granularity. Speed vs precision as governing trade-off. Company size no longer determines depth. Progressive OS merged as Company State.
- **P9 principle**: Structure adapts, content is configurable. Don't hardcode values that vary by company.
- **Task-to-protocol conversion**: LEARN phase now converts solved tasks into reusable protocols. First time = problem-solving. Second time = follow the protocol.
- **PROTO-013/014**: Enterprise-grade version deploy + client-side auto-check. 5-phase deploy (classify > deploy > verify > graduate > deprecate). 4-level verification (install > behavioral > adoption scorecard > mechanical). Phase 0 baseline check catches gaps from previous versions.
- **Founding Principle 0**: Customer Focus First — supersedes all five founding principles. If the customer doesn't get it, the rest doesn't matter.
- **verify-os-deploy.sh**: Runnable verification script for all 4 levels. CEO of Asawa can audit any company's OS compliance.

## v1.6 (2026-04-06)

- **CHARTERS.md**: Cross-functional goal framework — horizontal outcome goals that span vertical practices; KRAs, KPIs, OKRs per charter; DRI + contributors model
- **ROADMAP-MEETING.md**: Replaces HOD Meeting with OKR-driven process — impact/effort matrix, forward-looking goal-setting instead of backward-looking status updates
- **INPUT-ROUTING.md**: Human input classification protocol — every founder input classified (direction/task/feedback/new concept/question) before action; 3 enforcement levels (hook gate, protocol, skill); whitelisted system-maintenance actions
- **ADAPTIVE-PROTOCOL.md v2**: 10 parameters, pre-scoring gates, two-axis routing, undertriage tracking
- **TASK-LIFECYCLE.md updated**: L1 fast-path added; artifact requirements matrix (HLD, ADR, research gate, regression test at L3+)
- **ESTIMATION-ENGINE.md updated**: Auto-calibration feedback loop, CALIBRATION-STATE.json, log format v1.1
- **HUMAN-AGENT-INTERFACE**: Consolidated from L2 contraction
- **4 artifact templates**: HLD, ADR, Research Gate, Bug Fix
- **OKRs.md**: 8 charters for Sutra (expanded from 4)
- **Versioning protocol**: CURRENT-VERSION.md split from RELEASES.md
- **Tiered research cadence**: AI research weekly, frameworks bi-weekly
- **Client registry**: 6 companies (DayFlow, PPR, Maze, Jarvis, Paisa, Asawa)
- Triggered by: Founder session 2026-04-06 — infrastructure hardening, adaptive protocol v2, artifact gates, estimation auto-calibration

## Client Registry

Reconciled 2026-04-17 (post-propagation run: `bash holding/hooks/upgrade-clients.sh` + CLAUDE.md version bumps in maze/ppr/paisa/asawa).

Status vocabulary: `IN-SYNC` (all artifacts at pinned) · `PARTIAL` (SUTRA-VERSION bumped but v1.9 artifacts missing) · `STALE` (pinned behind current) · `GHOST` (registry row exists but no on-disk directory).

| # | Company | Pinned to | Tier | Status |
|---|---------|-----------|------|--------|
| 1 | DayFlow | v1.9 | 2 | IN-SYNC — verify-os-deploy.sh 100%. |
| 2 | PPR | v1.9 | 2 | IN-SYNC — 2026-04-17 propagation run. verify-os-deploy.sh 100%. |
| 3 | Maze | v1.9 | 2 | IN-SYNC — 2026-04-17 propagation run. verify-os-deploy.sh 100%. |
| 4 | Paisa | v1.9 | 2 | IN-SYNC — 2026-04-17 propagation run (up from v1.4 STALE). verify-os-deploy.sh 100%. |
| 5 | Asawa | v1.9 | 1 | IN-SYNC — holding CLAUDE.md bumped 2026-04-17. |
| 6 | Dharmik | v1.8 | 2 | GHOST — external client, no on-disk dir at asawa-holding/dharmik. Row reflects last known. |
| 7 | Billu | v1.9 | 1 | IN-SYNC at tier-1 scope. CLAUDE.md/SUTRA-VERSION=v1.9. MANIFEST + POLICY-COVERAGE not required at tier 1. |
| 8 | Sutra | v1.9 | 3 | SELF-HOSTED. Governance + platform. POLICY-COVERAGE.md = sutra/layer2-operating-system/POLICY-COVERAGE.md (canonical). |

*Jarvis row removed 2026-04-17: archived per SYSTEM-MAP 2026-04-15, replaced by Billu. No on-disk directory; no ongoing work. Per "either onboard or remove row" directive.*

## Release Model

```
SUTRA (develops continuously)
  │
  │ Publishes: v1.0, v1.1, v1.2, v2.0...
  │
  ▼
RELEASE (versioned, stable snapshot)
  │
  │ Client fetches a specific version
  │
  ▼
DAYFLOW (pins to v1.0, runs it, gives feedback)
  │
  │ Feedback goes to Sutra (not to the release)
  │
  ▼
SUTRA (incorporates feedback into next version)
  │
  │ Publishes v1.1 (includes DayFlow's learnings)
  │
  ▼
DAYFLOW (decides when to upgrade: stay on v1.0 or fetch v1.1)
```
