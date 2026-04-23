# Sutra Plugin — Interface Contracts

**Version**: v1 (Phase 2 deliverable, 2026-04-23)
**Status**: normative for plugin v1.12.3+
**Scope**: Core ↔ Extensions ↔ Practice Packs ↔ Client Config
**Related**: `holding/designs/sutra-core-architecture.svg` (Phase 2 block); `holding/research/2026-04-23-core-sutra-pipeline-ontology-correction.md`

---

## 1. `os/SUTRA-CONFIG.md` keys (per-client source of truth)

Every client repo carries `os/SUTRA-CONFIG.md` declaring:

| Key | Type | Default | Meaning |
|---|---|---|---|
| `tier` | 1 · 2 · 3 | 2 | governance-only / product / self-host |
| `sutra_version` | semver | pinned by install | Version of Sutra OS this client is pinned to |
| `depth_default` | 1-5 | 3 | Default task depth when none declared |
| `depth_range` | `[min,max]` | `[1,5]` | Tier-1 typically `[1,2]`; Tier-3 `[1,5]` |
| `enforcement_level` | soft · hard | soft | SOFT = warn, HARD = block |
| `enabled_hooks` | map `hook_name: bool` | all false | D32 hot-reload registry × enabled switch |
| `enabled_methods` | map `method_name: bool` | all false | D31 Coverage Engine method activation |
| `enabled_extensions` | map `ext_name: bool` | all false | Practice Packs + Departments opt-in |

**Rule**: client writes only booleans. Sutra writes the registry (keys, defaults, schema). Client cannot invent keys.

---

## 2. Pack Loader interface

**Runtime**: on `SessionStart`, plugin reads `os/SUTRA-CONFIG.md` → for each `enabled_extensions.<name>: true`, mounts `plugin/extensions/<name>/` into the active registry.

**Contract an Extension must satisfy**:

| Required file | Purpose |
|---|---|
| `CHARTER.md` | what this extension does, 6-section Operationalization |
| `manifest.json` | `name`, `version`, `declares: {hooks, skills, metrics, roles}`, `requires: {core_version, other_extensions}` |
| `hooks/*.sh` (optional) | hook files registered if present; matcher from manifest |
| `skills/<name>/SKILL.md` (optional) | skills exposed to LLM |

**Isolation**: extensions cannot mutate Core's runtime state; they read contracts + write to their own namespace under `.enforcement/<extension>/`.

---

## 3. Boundary role-resolution precedence

Fixed order (from `enforce-boundaries.sh`):

1. Env `ACTIVE_ROLE` (slash-command or shell export)
2. File `.claude/active-role` (first non-blank line)
3. CWD basename inference (`asawa-holding`, `sutra`, `dayflow`, `billu`, `maze`, `ppr`, `paisa`)
4. **Fail-closed**: unknown repo → exit 2 (block)

**Override**: Holding-only `god-mode` (Asawa CEO, 2h auto-expire, password-gated). Checks `.enforcement/god-mode.active` marker only when `ACTIVE_ROLE=asawa`.

---

## 4. Core Extension ABI (lifecycle events exposed to extensions)

| Claude Code event | Plugin-exposed hook point | Extension may |
|---|---|---|
| `SessionStart` | on-session-start | register startup tasks (cron-like); mount data |
| `UserPromptSubmit` | on-user-prompt | reset per-turn markers; route classifications |
| `PreToolUse` | pre-tool `matcher` | gate (exit 0 allow, 2 block); emit audit |
| `PostToolUse` | post-tool `matcher` | log, compress, measure; emit telemetry |
| `Stop` | on-stop | flush, triage, aggregate |

**Forbidden**: mutate Core state files · rewrite Boundary result · block without producing an override path.

---

## 5. Compatibility / Versioned ABI

- Plugin version uses semver: `core_version` (Core ABI) + `plugin_version` (package).
- Extensions declare `requires.core_version: ">=1.12.3"` in manifest.
- Install-time check: refuse install if client's pinned `sutra_version` < extension's required `core_version`.
- Schema migration: Work Unit object (Kernel layer) uses `schema_version`; migration scripts live in `plugin/migrations/<from>-<to>.sh` (Kernel iteration).

---

## 6. What this file does NOT cover (Kernel reserved)

The following are Phase-7 / Kernel concerns, not Phase-2 contracts:
- Persistence contract (State Store + Event Journal)
- Execution Control Plane (Budget/Lease Manager)
- Concurrency primitives
- Capability/Principal model beyond roles
- Event Bus + causal trace
- Full agent-graph abstraction

See `holding/research/2026-04-23-core-sutra-pipeline-ontology-correction.md` §6-10 + TODO kernel-dept-boundaries.

---

## Operationalization

### 1. Measurement mechanism
Adoption metric: `clients_with_valid_SUTRA_CONFIG` / `total_registered_clients` from `sutra/CURRENT-VERSION.md` Client Registry. Schema-valid = keys ⊆ declared set + types match.

### 2. Adoption mechanism
Ships as part of plugin v1.12.3+. Every install reads this contract via `START-HERE.md` reference. Existing clients see it on next upgrade.

### 3. Monitoring / escalation
`verify-os-deploy.sh` (vendor-side) scans client configs for contract compliance. Warn: invalid key detected. Breach: extension mounts fail on missing manifest.

### 4. Iteration trigger
New Core capability (new lifecycle event); new extension pattern discovered across ≥2 clients; Kernel layer lands.

### 5. DRI
Sutra-OS.

### 6. Decommission criteria
Never retires; evolves. Major version bumps produce migration docs at `plugin/migrations/`.

---

## Stems

interface-contracts, sutra-config-schema, pack-loader, boundary-role-resolution, extension-abi, versioned-abi, phase-2-deliverable, kernel-reserved
