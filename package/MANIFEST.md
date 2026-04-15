# Sutra Package Manifest — Full OS Bundle
_v1.9 — 2026-04-15_

What ships when a company runs `npx sutra-os@latest`.

## Layout installed into target `.claude/`
```
.claude/
├── settings.json           — full hook wiring (PreToolUse/PostToolUse/Stop/UserPromptSubmit)
├── hooks/sutra/            — Sutra-owned hooks (portable, do not edit)
│   └── (see "Hook Bundle" below)
├── os/                     — governance core (inherited, read-only)
│   └── (see "OS Core" below)
└── sutra-version           — version manifest: "1.9\n<timestamp>\n"
```

And into target project root:
```
CLAUDE.md                    — company template (merged with existing if present)
TODO.md                      — starter template (only if absent)
os/                          — company OS dir (SUTRA-CONFIG, STATUS, METRICS, OKRs)
.enforcement/                — audit logs dir (empty, created)
```

## Hook Bundle (ship list)

Port from `holding/hooks/` with portability fixes (use `$CLAUDE_PROJECT_DIR`, no hardcoded `holding/`):

### Core (required)
- `dispatcher-pretool.sh` — routing/depth/sutra-deploy gates + architecture awareness (trimmed)
- `dispatcher-stop.sh` — session-end checks orchestrator
- `reset-turn-markers.sh` — UserPromptSubmit marker clear
- `compliance-tracker.sh` — hook-level compliance metrics
- `resilience.sh` — retry/backoff for flaky hooks

### Governance (required)
- `estimation-enforcement.sh` — D9
- `lifecycle-check.sh` — D3 (Every Task Has a Sutra Path)
- `process-fix-check.sh` — D11
- `architecture-awareness.sh` — D12 (portable: reads target's SYSTEM-MAP or skips)
- `cascade-check.sh` — D13 (portable: warns on os/ edits)
- `new-path-detector.sh` — PROTO-001
- `version-governance.sh` — D22

### Observability (required)
- `session-logger.sh` — session start/stop events
- `session-checkpoint.sh` — periodic state snapshot
- `measurement-logger.sh` — output-driven metrics (D8)
- `kpi-tracker.sh` — Sutra KPI tracking
- `hook-health-sensor.sh` — meta-monitor
- `log-triage.sh` — triage classification log
- `log-skill-feedback.sh` — skill usage feedback

### Quality gates (required)
- `artifact-check.sh` — PROTO-009 narration vs artifact
- `context-budget-check.sh` — context spend cap
- `policy-coverage-gate.sh` — policy enforcement coverage
- `test-in-production-check.sh` — D10
- `agent-completion-check.sh` — subagent completion verification
- `codex-review-gate.sh` — optional review step
- `onboarding-self-check.sh` — onboarding integrity
- `time-allocation-tracker.sh` — D15 70/20/10
- `wait-gate.sh` — explicit wait points

### NOT shipped (holding-only)
- `god-mode.sh` — holding-only cross-company access
- `upgrade-clients.sh` — holding-only PROTO-018
- `verify-connections.sh` — holding-only integrity check
- `verify-os-deploy.sh`, `verify-policy-coverage.sh`, `verify-recursive-flow.sh` — holding-only verification
- `principle-regression.sh`, `principle-regression-tests.sh` — holding-only
- `isolation-tests.sh` — holding-only
- `input-classification-gate.sh` — superseded by dispatcher
- `auto-push.sh` — session-specific, not universal
- `check-graduation.sh` — holding-only

## OS Core (ship list)

Port from `sutra/layer2-operating-system/` to `.claude/os/`:
- `OPERATING-MODEL.md`
- `TASK-LIFECYCLE.md`
- `ADAPTIVE-PROTOCOL.md`
- `ESTIMATION-ENGINE.md`
- `ENFORCEMENT.md`
- `READABILITY-STANDARD.md`
- `PARALLELIZATION-ARCHITECTURE.md`
- `PERMISSIONS-TEMPLATE.md`
- `POLICY-COVERAGE.md`
- `PROTOCOLS.md`
- `DEFAULTS-ARCHITECTURE.md`
- `DEPLOYMENT-MODEL.md`
- `d-engines/` (whole subtree)
- `protocols/PROTO-*.md` (every active protocol)

## Templates (new, in `sutra/package/templates/`)
- `CLAUDE.md.template` — company session identity, Sutra version pin, inherited governance block
- `TODO.md.template` — starter
- `SUTRA-CONFIG.md.template` — depth default, enforcement level, hook registry
- `settings.json.template` — hook wiring
- `os-layout/` — empty starter os/ directory with STATUS.md, METRICS.md, OKRs.md stubs

## install.mjs rewrite

Add steps 4-6 after existing commands/skills install:

4. Copy `hooks/sutra/` bundle into target `.claude/hooks/sutra/`
5. Merge `settings.json` template into target `.claude/settings.json` (preserve existing hooks; append sutra bundle; don't clobber)
6. Render `CLAUDE.md`, `TODO.md`, `SUTRA-CONFIG.md` from templates if absent
7. Write `sutra-version` manifest
8. Run smoke test: invoke `test-d28-routing-gate.sh` against target

Uninstall parity:
- `--uninstall` removes `.claude/hooks/sutra/`, un-merges settings entries, leaves user content intact, removes `sutra-version`

## Phase plan

| Phase | Deliverable | Status |
|---|---|---|
| 0 | This manifest | DONE |
| 1 | Port core + governance hooks (portability fixes) | in progress |
| 2 | Observability + quality-gate hooks | pending |
| 3 | Templates (CLAUDE, TODO, SUTRA-CONFIG, settings.json) | pending |
| 4 | OS Core copy (`os-core/`) — bundle layer2 docs | pending |
| 5 | install.mjs rewrite + smoke test | pending |
| 6 | Uninstall parity + version manifest | pending |

Each phase commits atomically so partial work is safe.
