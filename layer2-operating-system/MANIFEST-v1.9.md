# Sutra OS v1.9 — Deployment Manifest

**Version**: v1.9
**Ships**: 2026-04-15
**Predecessor**: v1.8 (archive: MANIFEST-v1.7.md — v1.8 reused v1.7 manifest, drift-inducing)
**Purpose**: Close the policy→implementation→deployment loop permanently. v1.9 ships PROTO-017 (coverage gate) + PROTO-018 (auto-propagation), and for the first time the manifest covers all hooks that ship, not just the boundary hook.

---

## What v1.9 changes vs prior manifests

Prior manifests asserted **one** hook (`enforce-boundaries.sh`). Every client actually ships 10–20 hooks (compliance, depth-enforcement, estimation, logging, coverage). The manifest was silent on 95% of what shipped, so drift was invisible. v1.9 makes the manifest comprehensive and tier-aware.

---

## Tiers

Each client declares a tier in `os/SUTRA-CONFIG.md` (`tier: 1|2|3`). The manifest asserts tier-appropriate contents.

| Tier | Purpose | Examples |
|---|---|---|
| 1 — governance | rule enforcement, no product work | Asawa (holding), Billu |
| 2 — product | full product lifecycle with estimation + coverage | DayFlow, Maze, PPR, Paisa |
| 3 — platform | Sutra itself + cross-company tooling | Sutra |

---

## 1. FILES — all tiers (baseline)

| Path | Type | Notes |
|---|---|---|
| `CLAUDE.md` | file | company-specific + Sutra-managed sections |
| `os/SUTRA-CONFIG.md` | file | must declare `tier`, `enforcement_level`, `depth_default`, `depth_range` |
| `os/SUTRA-VERSION.md` | file | pinned version line |
| `os/METRICS.md` | file | company data |
| `os/OKRs.md` | file | company goals |
| `os/feedback-to-sutra/` | dir | upstream feedback |
| `os/feedback-from-sutra/` | dir | downstream pushes |
| `.claude/hooks/enforce-boundaries.sh` | file | tier-aware boundary enforcement |
| `.claude/settings.json` | file | hook registration (MUST register every hook in `.claude/hooks/`) |

## 2. FILES — tier 2 & 3 additional

| Path | Source |
|---|---|
| `os/engines/ADAPTIVE-PROTOCOL.md` | copy from `sutra/layer2-operating-system/d-engines/` |
| `os/engines/ESTIMATION-ENGINE.md` | copy from sutra d-engines |
| `os/engines/COVERAGE-ENGINE.md` | copy from sutra d-engines (tier 2+ if `coverage: on`) |
| `os/engines/estimation-log.jsonl` | empty file on deploy, never overwrite |
| `os/engines/method-registry.jsonl` | copy from sutra (coverage) |
| `os/findings/` | dir — Depth 4-5 audit tracker |
| `os/protocols/` | dir — LEARN phase protocol store |

## 3. HOOKS — all tiers (baseline)

| Hook | Registration | Behavior |
|---|---|---|
| `enforce-boundaries.sh` | PreToolUse: Edit\|Write\|Bash | exit 2 on path outside repo |
| `session-logger.sh` | SessionStart / Stop | append session metadata |
| `log-triage.sh` | PostToolUse | append depth/triage to estimation log |

## 4. HOOKS — tier 2 & 3 additional

| Hook | Registration |
|---|---|
| `artifact-check.sh` | PostToolUse |
| `compliance-tracker.sh` | SessionStart |
| `depth-marker-pretool.sh` | PreToolUse | _(was `depth-enforcement.sh` — file removed; live mechanism is the plugin's depth-marker-pretool. MANIFEST updated 2026-04-27 per codex P3.)_
| `estimation-enforcement.sh` | PreToolUse |
| `measurement-logger.sh` | PostToolUse |
| `resilience.sh` (helper/library — invoked by other hooks; not directly registered) | _N/A — helper called as `bash resilience.sh <hook> <pass\|warn>`. Reclassified 2026-04-27 per codex P3._ |
| `log-skill-feedback.sh` | PostToolUse |

## 5. HOOKS — tier 3 only

| Hook | Registration |
|---|---|
| `policy-coverage-gate.sh` | PreToolUse: Edit\|Write\|Bash (policy files) |
| `cascade-warning.sh` | PreToolUse: Edit\|Write |
| `codex-review-gate.sh` | pre-commit / manual (`bash codex-review-gate.sh request\|verify`) |

## 5a. AI code review — ecosystem-wide (all tiers)

PROTO-019 requires an external-AI peer review on portfolio changes. The
review gate `codex-review-gate.sh` ships from `holding/hooks/` and is
invoked in two phases:

1. `request [scope]` — writes `.enforcement/codex-reviews/pending-{ts}.md`
   with the diff packet. Operator then invokes the `/codex` skill on it.
2. `verify` — reads the latest review artifact, parses `CODEX-VERDICT:`,
   exits 0 on PASS/ADVISORY, 1 on FAIL/PENDING.

Every tier includes this gate. It is path-independent (reads git diff),
so it works across Asawa holding, Sutra self-host, and all companies.

## 6. CONTENT rules

### CLAUDE.md
Must contain: `Sutra OS Version: v1.9`, `DEPTH:`, `COST:`, `EFFORT:`, `Input Routing`, `depth_selected`, `CURRENT-VERSION`.
Must NOT contain: `v1.4`–`v1.8` in version line; `Gear` (the retired term, not `Gear Level [1-4]`); `Depth Level [1-4]` or `Gear Level [1-4]` (retired depth/gear tier terminology).
Note: `Input Routing (Level N)` and other `Level N` usages referring to enforcement levels, routing levels, or non-depth concepts are ALLOWED. Verifiers MUST anchor the forbidden regex to depth context (e.g., `^## Depth.*Level [1-4]` or `\b(Depth|Gear) Level [1-4]\b`). Fix per dayflow feedback 2026-04-15-v1.9-upgrade-audit-gaps.md GAP A.

### os/SUTRA-CONFIG.md
Must contain: `tier:`, `v1.9`, `Depth 1`…`Depth 5`, lifecycle phases, `Finding Resolution Gate`.

### os/engines/ADAPTIVE-PROTOCOL.md (tier 2+)
Must contain: `Adaptive Protocol Engine v3`, `Five Depths`, `Depth 1: Direct`.

## 7. DECLARED ⊆ INSTALLED ⊆ REGISTERED invariant

For every client: every hook listed under `## Hooks` in `os/SUTRA-CONFIG.md` MUST:
1. exist at `.claude/hooks/{hook}`,
2. have the executable bit set,
3. be registered in `.claude/settings.json` under `hooks.PreToolUse` or `PostToolUse`.

Enforced by: `verify-policy-coverage.sh` — the `is_deployed()` function uses `jq` to structurally check that each declared hook is registered under `hooks.PreToolUse` or `hooks.PostToolUse` with a `.command` field referencing `hooks/{name}`. A raw path grep is insufficient; an inert or malformed entry will NOT count as deployed. Any gap produces a DRIFT row in the "Per-client declared ⟶ installed+executable+registered" table.

## 8. VERIFICATION

```bash
bash holding/hooks/verify-os-deploy.sh {company}
bash holding/hooks/verify-policy-coverage.sh
```

Valid targets for verify-os-deploy: `dayflow`, `maze`, `ppr`, `paisa`, `billu`, `sutra`, `asawa`.

## 9. PROPAGATION (PROTO-018)

On CURRENT-VERSION.md bump: `holding/hooks/upgrade-clients.sh` runs automatically. It:
1. Reads new version from CURRENT-VERSION.md.
2. For each client in registry, compares pinned version.
3. If behind: copies updated engines, rewrites SUTRA-VERSION.md, installs newly-required hooks per tier, registers in settings.json.
4. Re-runs verify-os-deploy. Reports per-client score.
5. Does not half-upgrade. On failure leaves old version and reports why.

## 10. COVERAGE LEDGER (PROTO-017)

`sutra/layer2-operating-system/POLICY-COVERAGE.md` is the source of truth for which policies are enforced and where deployed. Generated by `verify-policy-coverage.sh --write`. Rows without enforcer+deployed are DRIFT.

---

## Client registry (v1.9 targets)

| # | Company | Tier | Target version |
|---|---|---|---|
| 1 | DayFlow | 2 | v1.9 |
| 2 | Maze | 2 | v1.9 |
| 3 | PPR | 2 | v1.9 |
| 4 | Paisa | 2 | v1.9 |
| 5 | Billu | 1 | v1.9 |
| 6 | Sutra | 3 | v1.9 (self-hosted) |
| 7 | Asawa | 1 | v1.9 (holding) |
| 8 | Jarvis | 2 | v1.9 |
| 9 | Dharmik | 2 | v1.9 (external) |
