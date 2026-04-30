# MIGRATION — Core → Native cutover playbook

**Purpose**: take an existing Tenant from Sutra Core hooks (`sutra/marketplace/plugin/hooks/*.sh`) to Native primitives + engines without behavior drift, breakage, or silent feature loss.

**Closes**: PS-3 ("Cutover from Core plugin to Native is undefined for existing companies").

**Audience**: operators executing a Tenant cutover (Asawa engineer for own dogfood; T2/T3 client engineer for own portfolio company; Asawa engineer-on-behalf for assisted T4 cutovers).

**Canonical schema source**: [`src/schemas/cutover-contract.ts`](src/schemas/cutover-contract.ts) — the 5-field `CutoverContractSchema` is the single source of truth. (D1 §11.1 research doc shows an older 6-field shape; ignore that drift — code is canonical.)

---

## §1 Overview — when to migrate

You're ready to migrate a Tenant from Core to Native when **all** of these hold:

1. The Tenant has a Charter with `cutover_contract: CutoverContract` (non-null, schema-valid)
2. Native v1.0 (this plugin) is installed alongside Sutra Core in the Tenant's environment
3. You have an operator-runnable rollback plan AND know which authority can invoke each operation (Tenant owner vs founder)
4. The Tenant's tier-canary window can be honored end-to-end without conflict (see §7)
5. No active HARD-STOP escalation is in flight on the Tenant (per D5 §3)

If any hold doesn't, do NOT start cutover. Resolve preconditions first.

---

## §2 Pre-cutover audit

Before constructing the cutover_contract, capture current Tenant state. This baseline is what behavior_invariants check against.

### §2.1 Tenant-enabled Core hooks → Native capability mapping

Operator fills in the table below for THIS Tenant only. Don't try to map all 78 Core hooks — only the ones this Tenant actually uses (`settings.json` activation set + project-specific configuration).

| Core hook (Tenant uses) | Native capability replacement | Verified-by | Notes / RESIDUAL? |
|---|---|---|---|
| `cascade-check.sh` | L4 COMMITMENT law + V2 §A12 terminal_check (T2 obligation closure check) | M3 property tests + M9 F-2 integration | Replaced |
| `depth-marker-pretool.sh` | Charter obligation `depth_estimation_per_task` + V2 §A12 terminal_check (T1 charter obligation) | M3 + M9 V2 §8 E2E | Replaced |
| `codex-review-gate.sh` | `policy_dispatcher` + OPA bundle service (charter→rego compiled at runtime) | M7 codex L2 + M9 F-coupling integration | Replaced |
| `<your-hook-here>` | `<map to Native engine/primitive/charter obligation>` OR mark RESIDUAL | `<test reference>` | `<keep running OR accept gap>` |

**RESIDUAL** — Core hooks the Tenant uses but Native does NOT yet replace:

- List one per row: `<hook-name>` — operator instruction: keep running alongside Native until v1.x ships native equivalent OR explicit "accept the gap" decision recorded by Tenant owner authority.

### §2.2 Behavior baseline snapshot

Record (timestamped, written to `.enforcement/cutover/<tenant-id>-baseline.jsonl`):

- **DecisionProvenance fingerprint**: which `decision_kind` records the Tenant's hooks emit per turn under steady-state load (count + shape; for invariant comparison)
- **Charter obligations active**: list of `Charter.obligations[i]` currently firing in observed turns
- **Workflow registrations**: which Workflows are registered by name + their `step_graph` shape signatures
- **Governance overhead steady-state**: median + p95 overhead percentage per turn (read from M8 `GovernanceOverhead.report()`)
- **Active TriggerSpecs**: which trigger patterns are wired

This baseline is what `behavior_invariants` predicates compare against during canary.

---

## §3 cutover_contract construction

The contract is a Charter sub-schema (5 required fields when non-null):

```json
{
  "source_engine": "sutra-core-v2.9.1",
  "target_engine": "sutra-native-v1.0",
  "behavior_invariants": [
    "every_governance_hook_emits_decision_provenance_with_policy_id_and_policy_version",
    "no_charter_obligation_regression_vs_baseline",
    "step_graph_terminal_state_matches_baseline_for_representative_workflows"
  ],
  "rollback_gate": "behavior_invariants_violation_count > 0 OR overhead_termination_count_in_canary_window > 0",
  "canary_window": "60s"
}
```

Validate by importing `createCutoverContract` from `src/schemas/cutover-contract.ts` and parsing your fixture; if it doesn't throw, the contract is structurally valid. (See [`examples/cutover/`](examples/cutover/) for two reference fixtures.)

---

## §4 Parallel-canary execution sequence

The cutover engine (P-B1, deferred to M11+) drives this sequence. Until the engine ships, operators run the steps manually OR via thin scripts:

1. **Validate** the cutover_contract (`createCutoverContract` parse) → emit `decision_kind='AUDIT'` provenance record.
2. **Activate target engine in parallel** with source — Native runs alongside Core for the canary_window. Both emit DecisionProvenance to the same OTel sink. → emit `decision_kind='EXECUTE'` provenance record.
3. **Observe behavior_invariants** continuously through canary_window. For each predicate violation, emit `decision_kind='AUDIT'` provenance record with the violation details.
4. **Evaluate rollback_gate** continuously. When the predicate trips, jump to §6 (Rollback).
5. **Finalize** — at canary_window end, if `rollback_gate` did NOT trip AND `success_metrics` (from Charter, if defined) hold: emit `decision_kind='APPROVE'` provenance record. Disable source engine. Cutover succeeds.

| Gate | DecisionProvenance `decision_kind` | When |
|---|---|---|
| validate cutover_contract | `AUDIT` | Once at cutover start |
| activate target engine | `EXECUTE` | Once at cutover start |
| observe behavior_invariants | `AUDIT` | Continuously during canary_window (one record per observation tick OR one per violation) |
| finalize cutover | `APPROVE` | Once at canary_window end if green |
| rollback | `TERMINATE` with `reason='cutover_rollback:<predicate>'` | When rollback_gate trips |

(REJECT is intentionally NOT in the table — cutover gates use only AUDIT/EXECUTE/APPROVE/TERMINATE per the M9 lesson "don't widen contracts in integration milestones".)

---

## §5 behavior_invariants — what MUST hold across cutover

Each Tenant's contract supplies its own array of predicate strings. These three are required for every Tenant; add Tenant-specific ones on top.

### Required (every Tenant)

1. **`every_governance_hook_emits_decision_provenance_with_policy_id_and_policy_version`**
   - **What it means**: every governance hook firing during the canary emits a DecisionProvenance record with non-empty `policy_id` AND `policy_version` fields. (Carries forward I-9 from M9.)
   - **Why it matters**: ensures audit trail is intact end-to-end; if Native breaks DP emission, audit goes silent.
   - **How to evaluate**: read OTel sink for the canary_window; count DP records; assert `≥1 per consequential decision per Execution`; assert all carry policy_id + policy_version.

2. **`no_charter_obligation_regression_vs_baseline`**
   - **What it means**: every `Charter.obligations[i]` that fired in the §2.2 baseline continues firing under Native. Zero regressions allowed.
   - **Why it matters**: Charter obligations encode what the Tenant promised to do; silent regression = silent feature loss = PS-3 violation.
   - **How to evaluate**: diff the obligation-fire log from canary_window vs baseline; any obligation in baseline missing from canary log = violation.

3. **`step_graph_terminal_state_matches_baseline_for_representative_workflows`**
   - **What it means**: a representative set of Workflows (Tenant picks ≥3 covering happy-path + edge-case + failure-path) end in the same `terminal_state` under Native as under Core in baseline.
   - **Why it matters**: divergence in terminal_state = behavior drift = PS-3 violation.
   - **How to evaluate**: re-run each representative Workflow through Native; assert `Execution.state` matches baseline.

### Per-Tenant examples (build on top of required)

- **Asawa dogfood**: `founder_ask_gate_latency_p95_within_baseline_plus_10pct` (Asawa governance latency must not regress materially)
- **DayFlow**: `daily_pulse_continues_firing_at_scheduled_cadence` (DayFlow's signature daily ritual must survive)
- **Paisa**: `loan_decision_audit_trail_unbroken` (compliance — every loan decision still emits provenance)

---

## §6 rollback_gate — when to abort + revert to source

The `rollback_gate` is a single string predicate evaluated continuously during canary_window. When it returns true, abort cutover.

### Required predicate examples (≥2 every Tenant)

1. **`behavior_invariants_violation_count > 0`** — any §5 invariant fails → rollback. This is the strict default; tightening or loosening should be a Tenant-explicit decision.

2. **`overhead_termination_count_in_canary_window > 0`** — any HS-2 overhead-termination (M9 wired) fires during canary → rollback. Indicates governance overhead leak under the new path.

### Per-Tenant tightenings

- **T2 production**: add `any_HARD_STOP_other_than_overhead_termination_fires` to catch HS-1 / HS-3 / HS-4 / HS-6 / HS-7 / HS-8 (D5 §3) immediately.
- **Compliance-sensitive (Paisa, Testlify)**: add `external_authority_count_DENY_decisions_increase_vs_baseline > 0` to catch policy-dispatcher denials regressing.

---

## §7 canary_window timing (per-Tenant tier)

| Tier | Cohort | Default `canary_window` | Tunable? |
|---|---|---|---|
| **T0** | Asawa dogfood (M11) | `60s` | Yes — extend if first-pass observation period inconclusive |
| **T2-1** | DayFlow first | `7d` | Per CM3/D29 canary pattern + CM9 first-onboarding precedent |
| **T2-rest** | Billu / Paisa / PPR / Maze | `7d` | Match T2-1 rhythm |
| **T3** | Testlify / Dharmik | `14d` | Tighter — client IP requires longer observation; T2 metrics must be ≥3 weeks green first |
| **T4** | external fleet (marketplace) | `7d` | Match T2; activated post-marketplace announcement + per-cohort canary |

These are PROVISIONAL OPERATOR DEFAULTS, not normative engine semantics. Tune per-Tenant if signal arrives faster or slower than expected.

`canary_window` accepts ISO-8601 durations (`PT72H`), human shorthand (`7d`, `60s`), or seconds-as-string. Validation lives in the cutover engine; M10 doc accepts any non-empty string.

---

## §8 Post-cutover verification + finalize

When the canary_window ends without `rollback_gate` tripping:

1. **Verify success_metrics** (from `Charter.success_metrics[]` if defined; the cutover_contract itself doesn't carry success_metrics — see schema note).
2. **Emit finalize provenance**: `decision_kind='APPROVE'` with summary of canary observations.
3. **Disable source engine** for the Tenant — Core stops processing for this Tenant; Native is now sole engine.
4. **Update Tenant Charter** to clear `cutover_contract` (set to `null`) — cutover is no longer active.
5. **Archive baseline + canary observation logs** to `.enforcement/cutover/<tenant-id>-archive/` for post-mortem availability.

---

## §9 Per-Tenant tier rollout sequence

Cutovers run in tier order; later tiers gate on earlier tiers' green canary outcomes.

```
T0 Asawa dogfood (M11 close)  → must be green
        ↓
T2-1 DayFlow first (Phase 3)  → 7d canary green; zero HARD-STOPs
        ↓
T2-rest Billu / Paisa / PPR / Maze (Phase 3, sequential or parallel based on capacity)
        ↓
T3 Testlify / Dharmik (Phase 3)  → after T2 metrics ≥3 weeks green; client sign-off
        ↓
T4 external fleet (marketplace) → marketplace announcement + per-cohort canary
```

Operators do NOT skip tiers. T2 cannot start before T0 closes green; T3 cannot start before T2 metrics are observably stable.

---

## §10 Failure handling + escalation

### §10.A Rollback succeeds (the happy-failure branch)

When `rollback_gate` trips during canary:

1. Engine emits `DecisionProvenance(decision_kind='TERMINATE', reason='cutover_rollback:<predicate>')` with the offending predicate.
2. Engine invokes the `rollback` recovery operation (D5 §5.2): restore Tenant state to last-known-good per Snapshot (V2 Q4 stack decision: JSONL events + snapshots).
3. Engine invokes the `disable` recovery operation (D5 §5.2) on the target engine for this Tenant: Native stops processing; source engine continues.
4. Authority required: rollback = Tenant owner OR founder; disable = Tenant owner.
5. Operator updates Tenant Charter to clear `cutover_contract` OR keep it for re-attempt later (Tenant owner decision).

### §10.B Rollback fails (HS-5 branch — D5 §3)

If the rollback operation itself fails (e.g., snapshot corrupt; recovery primitive errors; partial state):

1. **Freeze writes** immediately on the Tenant — no further state mutation. (Critical: prevents the corrupt-state window from spreading.)
2. **Preserve snapshot + source_engine id** explicitly. Capture the current (corrupt) state as a forensic artifact, not as a recovery target. Source_engine id persists so a fresh manual recovery has a known-good baseline target.
3. **Disable target engine** fully on this Tenant, per D5 §5.2 `disable` operation. Authority: Tenant owner. Native stops processing for this Tenant.
4. **Attach all DecisionProvenance records** + execution logs from the canary_window to the escalation packet. Founder + Tenant owner need full context to make repair-vs-reset decision.
5. **Escalate** to founder + Tenant owner via HS-5 path. Decision criteria:
   - **Repair** (D5 §5.2 — Tenant owner with founder approval): if the behavior_invariants violations are recoverable (e.g., known-issue catalog entry exists; deterministic fix path). Apply repair; re-attempt cutover later.
   - **Reset** (D5 §5.2 — founder ONLY; DESTRUCTIVE): if state is corrupt beyond repair. Re-init Tenant from last clean snapshot. All work since snapshot is lost.

The repair-vs-reset call is the **founder's** call when assisted by Tenant owner context. Do not let an operator escalate-and-act unilaterally; escalation is the gate.

### §10.C Recovery contract surface (D5 §5.2 reference)

For convenience, the four canonical recovery operations:

| Operation | What it does | Authority required |
|---|---|---|
| `rollback` | Revert state to last-known-good per Snapshot | Tenant owner OR founder |
| `disable` | Disable hook/engine/workflow without rolling state | Tenant owner |
| `repair` | Apply diagnostic + fix per known-issue catalog | Tenant owner with founder approval |
| `reset` | Re-init Tenant from last clean snapshot (DESTRUCTIVE) | Founder ONLY |

User-facing CLI (`sutra recover --status / --rollback / --disable / --repair / --reset`) is deferred to v1.x per D5 §5.3; until then, recovery is operator-driven via direct invocation of the engine ops.

---

## §11 Cross-references

- **PS-3 problem state**: `holding/research/2026-04-29-native-problem-state.md` lines 40-44 — the problem this playbook closes
- **D1 §11 cutover contract spec**: `holding/research/2026-04-29-native-d1-authority-map.md` lines 292-329 — design rationale (note: shows older 6-field shape; code is canonical)
- **V2 §A12 Charter cutover sub-schema**: `holding/research/2026-04-28-v2-architecture-spec.md` — cutover_contract on Charter
- **D5 §3 HARD-STOPs (HS-5 rollback fails)**: `holding/research/2026-04-29-native-d5-invariant-register.md` §3
- **D5 §5 recovery contracts**: `holding/research/2026-04-29-native-d5-invariant-register.md` §5.2 — rollback/disable/repair/reset
- **cutover-contract.ts (M4 schema, CANONICAL)**: [`src/schemas/cutover-contract.ts`](src/schemas/cutover-contract.ts) — 5-field schema
- **F-7 reflexivity**: `holding/research/2026-04-29-native-d4-primitives-composition-spec.md` — `Workflow.modifies_sutra=true` requires reflexive_check Constraint cleared (relevant when Tenant cutover affects Sutra plugin paths)
- **Final architecture FC-2**: `holding/research/2026-04-29-native-v1.0-final-architecture.md` line 104 — "Existing companies must not break during cutover"
- **Worked-example fixtures**: [`examples/cutover/`](examples/cutover/) — Asawa dogfood + DayFlow first-T2

---

## §12 Operator quick-reference

```
1. Read this doc top-to-bottom (~15 min)
2. §2 — capture pre-cutover baseline (1-2 hr depending on Tenant complexity)
3. §3 — construct cutover_contract; validate via createCutoverContract
4. §7 — pick canary_window per Tenant tier
5. §4 — initiate parallel canary; engine drives gates
6. §5/§6 — invariants + rollback_gate evaluated continuously
7. §8 — finalize OR §10 — handle rollback (succeeds OR HS-5)
```

If anything in this playbook is unclear at the start of a real cutover, STOP and clarify before proceeding. Cutover errors compound — silent feature loss after a botched cutover is exactly the PS-3 condition this doc exists to prevent.
