# Sutra — Catalog (Central Registry of Everything)

**Purpose**: one place to see every engine, protocol, charter, department, project, feature, and hook Sutra provides — with status, tier, and how to turn it off.

**Updated**: 2026-04-20
**Sutra version**: v1.9.1
**Rule**: every new engine / protocol / charter / department / feature MUST add a row here on creation. Every deprecation MUST update `Status` here before removal elsewhere. This file is the governance ledger for turning things on and off.

---

## 1. How to read

| Column | Meaning |
|---|---|
| **Name** | The thing |
| **Type** | engine \| protocol \| charter \| department \| project \| feature \| hook \| registry |
| **Status** | active \| wip \| disabled \| retired \| deferred |
| **Tier** | 1 (governance) \| 2 (product) \| 3 (platform) \| all |
| **Provides** | One-line value description |
| **Toggle** | Exact on/off mechanism |
| **Source** | File / directory (authoritative) |

Cross-references:
- Machine-readable source of truth for protocols/directions/hooks/tiers: `sutra/state/system.yaml`
- Hook manifest: `sutra/layer2-operating-system/MANIFEST-v1.9.md`
- Client registry (who runs what version): `sutra/CURRENT-VERSION.md` §Client Registry

---

## 2. Engines

| Name | Status | Tier | Provides | Toggle | Source |
|---|---|---|---|---|---|
| **Adaptive Protocol Engine** (v3) | active | 2, 3 | Depth routing — classifies each task to Depth 1-5; gates fire accordingly | `depth` field in SUTRA-CONFIG or omit; Depth 5 is founder override | `sutra/os/engines/ADAPTIVE-PROTOCOL.md` |
| **Estimation Engine** (v1.1) | active | 2, 3 | Pre-task token/time/file estimate + post-task actuals + auto-calibration | Always on in Tier 2+; Tier 1 logs to holding/ESTIMATION-LOG | `sutra/os/engines/ESTIMATION-ENGINE.md` |
| **Coverage Engine** (v1.0) | active | 2, 3 | Runtime process coverage — tracks whether expected Sutra methods fire per task per depth | `coverage: on\|off` in `os/SUTRA-CONFIG.md` (silent no-op when off) | `sutra/os/engines/COVERAGE-ENGINE.md` |
| **Measurement Protocol** | active | 2, 3 | Measurement registry across 26 methods (6 categories) | Coupled to Coverage Engine toggle | `sutra/os/engines/MEASUREMENT-PROTOCOL.md` + `sutra/os/engines/method-registry.jsonl` |
| **Token Telemetry** (v1, WIP) | wip | all | Per-session boot + task_end telemetry; 5 metrics to Analytics Dept | OFF until schema freeze (Phase 0 Step 2). Toggle via hook presence in `.claude/settings.json` | `holding/research/2026-04-20-token-telemetry-schema-reconciliation.md` |

---

## 3. Initiative Charters (cross-cutting)

Pattern: `sutra/layer2-operating-system/a-company-architecture/CHARTERS.md`. Placement: `sutra/os/charters/`. README: `sutra/os/charters/README.md`.

| Name | Status | DRI | Q | Provides | Toggle | Source |
|---|---|---|---|---|---|---|
| **Tokens** | active | Sutra-OS | Q2 2026 | Measurement + reduction + enforcement of session token cost (cost lens: "how much?") | Retire when gov overhead <15% sustained 2 quarters (lifecycle §11) | `sutra/os/charters/TOKENS.md` |
| **Speed** | active | Sutra-OS | Q2 2026 | Measurement + reduction of task/session wall-clock time (time lens: "how long and where?"); sibling to Tokens; shares Analytics pipeline | See SPEED.md lifecycle; retire when target reached | `sutra/os/charters/SPEED.md` |

---

## 4. Protocols

Source of truth: `sutra/state/system.yaml` §protocols. Cap = 8 active per Phase 0 D-3.

| ID | Name | Status | Enforcement | Provides | Toggle | Source |
|---|---|---|---|---|---|---|
| **PROTO-000** | Every Change Ships With Implementation | active | soft (→hard Phase 3) | Invariant: every policy marked HARD has a compiled blocking hook + regression test | `state/system.yaml` → status | `sutra/layer2-operating-system/PROTOCOLS.md` |
| **PROTO-004** | (see state.yaml) | active | varies | — | same | same |
| **PROTO-017** | Policy-to-Implementation Coverage Gate | active | hard | Every Sutra policy edit surfaces PROTO-000 reminder; generates POLICY-COVERAGE.md ledger | `state/system.yaml` → status | same |
| **PROTO-018** | Auto-Propagation on Version Bump | **disabled** (D-7) | — | `upgrade-clients.sh` walks client registry; currently MANUAL per founder | `.enforcement/proto-018-reminders.log` shows when skipped | same |
| **PROTO-019** (candidate) | Unit-Architecture (every unit = definition charter + skills + initiative charter participations) | deferred | planned | Formalize cascading model in state.yaml | TBD | sketched in `sutra/os/charters/README.md` §1-4 |

See `state/system.yaml` for the full protocol list. Directions D1–D30 similarly tracked there.

---

## 5. Departments

Pattern: every unit = definition charter + skills + initiative participations. Exemplar: `holding/departments/analytics/`.

| Name | Status | Tier | Provides | Toggle | Source |
|---|---|---|---|---|---|
| **Analytics** (v0) | active | 1 (Asawa-level) | 8-dimension scorecard; session-triggered collect + publish; reads existing logs | Run on-demand (`bash holding/departments/analytics/collect.sh`); plugin adds 3h + hook trigger in v1 | `holding/departments/analytics/CHARTER.md` |
| **Implementation** (proposed) | deferred | 1 | Would track protocol instances in production companies (TOKENS charter feeds this) | — | Mentioned in 2026-04-20 session; not built |

---

## 6. Projects / Products

| Name | Status | Tier | Provides | Toggle | Source |
|---|---|---|---|---|---|
| **Sutra OS** | active | 3 | The operating system itself — versioned releases | Client-side: `sutra/os/SUTRA-CONFIG.md` per-company opt-in | `sutra/CURRENT-VERSION.md` |
| **Sutra Marketplace / Plugin** | wip | — | Plugin deployment home; delivery mechanism to Claude Code | Not yet shipped | `sutra/marketplace/` |
| **DayFlow** | active | 2 | Product company — personal OS iOS app + primary Sutra validator | Per-company CLAUDE.md | `dayflow/` (submodule) |
| **Maze** | active | 2 | Humor feed product | same | `maze/` (submodule) |
| **PPR** | active | 2 | Wedding command center | same | `ppr/` (submodule) |
| **Paisa** | active | 2 | Digital personal loan (India) | same | `paisa/` (submodule) |
| **Billu** | active | 1 | Governance-only tier tool; minimal footprint | same (tier 1 config) | `billu/` (submodule) |
| **Asawa Holding** | active | 1 | Holding company + governance + Sutra consumer | `asawa-holding/CLAUDE.md` | `holding/` |

---

## 7. Features (governance / runtime behaviors)

Each toggles at the CLAUDE.md level or via a specific hook/config.

| Name | Status | Tier | Provides | Toggle | Source |
|---|---|---|---|---|---|
| **Input Routing (Level 2)** | active | all | Classifies every founder input (TYPE / ROUTE / FIT CHECK) before action | Whitelisted actions skip; disabling = edit CLAUDE.md §Input Routing | `holding/CLAUDE.md` §Input Routing + `sutra/layer2-operating-system/INPUT-ROUTING.md` (pattern) |
| **Depth Block (mandatory)** | active | all | Per-turn Depth + Estimation block before any Write/Edit | Marker-based enforcement in `holding/hooks/dispatcher-pretool.sh` Check 10 | same |
| **Sutra-Deploy Depth 5 Gate** | active | all | Sutra/company OS edits require Depth 5 marker | `holding/hooks/dispatcher-pretool.sh` Check 11 + `.claude/sutra-deploy-depth5` | D27 in `state/system.yaml` |
| **Readability Gate** | active | all | Output format discipline (status boards, tables, numbers over prose) | LLM behavior gate; standard at `sutra/layer2-operating-system/READABILITY-STANDARD.md` | memory `feedback_readability_is_output_gate` |
| **Execution Trace (3 levels)** | active | all | Shows what the OS did (L1 minimal, L2 standard, L3 verbose) | Founder says "show trace" / "show os" / "trace off" | `holding/CLAUDE.md` §Execution Trace + `holding/research/2026-04-09-execution-trace-spec.md` |
| **God Mode** | active | 1 (Asawa only) | Cross-company edits from Asawa holding; 2-hour auto-expire; password-gated | `bash holding/hooks/god-mode.sh activate\|deactivate` | `holding/CLAUDE.md` §God Mode + `holding/hooks/god-mode.sh` |
| **Sutra Freeze Marker** | active | 2 | Companies can place `.sutra-freeze` to block propagation | create/remove the file | `state/system.yaml` §conventions.sutra_freeze_marker |
| **Boundary Enforcement** | active | all | Blocks cross-company edits unless role matches | always on; `holding/hooks/enforce-boundaries.sh` | MANIFEST-v1.9 |
| **Cascade Gate (D13)** | active | 1 | Blocks commit on L0-L2 changes without downstream TODO evidence | `CASCADE_ACK=1 CASCADE_ACK_REASON='<why>'` env var override | `holding/hooks/cascade-check.sh` |
| **Codex Review Gate (I-11)** | active | 1 | Pre-commit requires fresh codex review marker (<10min) for sutra/holding/os paths | `CODEX_OVERRIDE=1 CODEX_OVERRIDE_REASON='<why>'` env override | `.git/hooks/pre-commit` |
| **Subagent OS Contract** | active | 1 (TEMP) | Every Task/Agent dispatch must carry OS boot block + footer | `SUBAGENT_CONTRACT_ACK=1` override | `holding/hooks/subagent-os-contract.sh` (DELETE when plugin ships — per holding CLAUDE.md TEMP section) |
| **Input Routing Whitelist** | active | all | Memory files, checkpoints, TODO checkboxes, git ops skip classification | hardcoded in CLAUDE.md | `holding/CLAUDE.md` §Input Routing |

---

## 8. Hooks (pointer)

Full hook inventory: `sutra/layer2-operating-system/MANIFEST-v1.9.md` (tier-aware: Tier 1 ships boundary + reset-turn-markers + dispatcher-pretool; Tier 2+ ships all).

Live hook log: `holding/hooks/hook-log.jsonl`.

Toggle: edit `.claude/settings.json` in each company; presence = enabled. Tier-gated install at onboarding.

---

## 9. Registries (machine-readable indices)

| Registry | Provides | Source |
|---|---|---|
| **state/system.yaml** | typed protocols, directions, hooks, tiers, invariants (single source of truth) | `sutra/state/system.yaml` |
| **method-registry.jsonl** | 26 Coverage Engine methods with depth requirements | `sutra/os/method-registry.jsonl` |
| **Client registry** | Which companies on which Sutra version; IN-SYNC/PARTIAL/STALE status | `sutra/CURRENT-VERSION.md` §Client Registry |
| **CATALOG.md** (this file) | Human-readable index over all above | `sutra/CATALOG.md` |

---

## 10. Status legend

- **active** — shipped and enabled; Toggle column shows disable mechanism
- **wip** — being built; not yet enabled
- **disabled** — was active, now off (reason in Toggle); may be re-enabled
- **retired** — explicitly turned off, documented final state, not coming back
- **deferred** — planned, not started

---

## 11. How to add an entry

When adding a new engine / protocol / charter / department / feature / hook:

1. Create the artifact in its home directory (engines in `os/engines/`, charters in `os/charters/`, etc.)
2. If protocol/direction/hook: register in `sutra/state/system.yaml` (source of truth)
3. **Add a row here** in the correct section — name, status, tier, provides, toggle, source
4. If it's an initiative that cascades to client companies: note `Applies to:` + propagation mechanism (see TOKENS charter for the pattern)

**If you skip step 3, the catalog drifts.** This drift is the thing we're preventing.

---

## 12. How to turn something off

| Layer | Off mechanism |
|---|---|
| Protocol | `state/system.yaml` → set `status: disabled`, recompile |
| Engine | If configurable: SUTRA-CONFIG.md flag; if not: code-level removal + CATALOG update |
| Charter | Lifecycle §Retire (see CHARTERS.md pattern): archive with final scores |
| Department | Remove scripts + update registry; rare |
| Hook | `.claude/settings.json` edit (per company) |
| Feature | Varies — listed in Toggle column |
| Whole Sutra version | Client opts into prior version via `upgrade-clients.sh --pin <version>` (when re-enabled; currently manual) |

Always log the off reason in `.enforcement/` or commit message. Nothing silently deactivates.

---

## 13. Gaps / TODO

- [ ] Full protocol list in §4 incomplete — mirror `state/system.yaml` fully (candidate automation: compile from YAML)
- [ ] Departments section has only Analytics — add Implementation dept when it materializes (proposed 2026-04-20)
- [ ] Hooks section is a pointer only — may expand inline if MANIFEST-v1.9 grows beyond a single-file scope
- [ ] Features section is hand-maintained — no machine check for drift; consider compile-from-state
- [ ] PROTO-019 (Unit-Architecture) formalization — not yet in state.yaml
- [ ] Add `Applies to:` + propagation status per row (partially covered in Tier column)

---

## 14. Related

- Founding doctrine (outside this repo): `~/Claude/root-os/FOUNDING-DOCTRINE.md`
- Pattern references: `sutra/layer2-operating-system/` (full pattern library)
- Roadmap / OKRs: `sutra/OKRs.md`
- TODO backlog: `sutra/TODO.md`
