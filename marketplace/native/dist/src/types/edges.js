/**
 * Native v1.0 edge types — M4.8 (Group C in TASK-QUEUE.md §1).
 *
 * Three new edge types per D4 §2.2:
 *   - `owns`          : Tenant → Domain        (P-A1, sovereignty)
 *   - `delegates_to`  : Tenant → Tenant        (P-B8, cross-tenant delegation)
 *   - `emits`         : Workflow/Execution/Hook → DecisionProvenance  (P-A3, attribution)
 *
 * IMPORTANT — L5 META law preserves only `Domain.contains.Charter` as
 * containment. The `owns` edge here is sovereignty-not-containment:
 * Tenant OWNS Domain (sovereignty boundary) but does NOT contain it.
 * Containment edges remain limited to Domain → Charter only.
 *
 * Per D4 §2.2 + D1 P-A1 + D2 P-A3.
 *
 * Note on cross-kind validation: id-pattern guards at the schema level catch the
 * common "wrong primitive in source/target" mistakes (e.g. `owns` with a
 * Workflow id as target). Stricter constraints — like "delegates_to source !==
 * target" or "emits source must already exist in registry" — are runtime
 * concerns, not schema concerns, and live at terminal_check (M4.9) and the
 * Workflow Engine (M5+).
 */
import { z } from 'zod';
// -----------------------------------------------------------------------------
// id-pattern regexes — kept local to avoid coupling to consumer schemas.
// Mirrors the canonical patterns in:
//   - src/schemas/tenant.ts                  (TENANT_ID_PATTERN)
//   - src/primitives/domain.ts               (D_ID_PATTERN)
//   - src/primitives/workflow.ts             (W_ID_PATTERN)
//   - src/primitives/execution.ts            (E_ID_PATTERN)
//   - src/schemas/decision-provenance.ts     (DP_ID_PATTERN)
// -----------------------------------------------------------------------------
const TENANT_ID_PATTERN = /^T-[a-z0-9-]+$/;
const DOMAIN_ID_PATTERN = /^D\d+(\.D\d+)*$/;
const DP_ID_PATTERN = /^dp-[a-f0-9]+$/;
/**
 * EmitsEdge source pattern — Workflow / Execution / Hook ids only (D4 §2.2).
 *
 * Tightened in Group G' fix-up (2026-04-29) per codex master P3.5: the schema
 * previously accepted any non-empty string, allowing Tenant/Domain/garbage ids
 * to validate as provenance emitters. Now restricted to one of:
 *   - Workflow:  `W-<id>`  (canonical W_ID_PATTERN: `^W-.+$`)
 *   - Execution: `E-<id>`  (canonical E_ID_PATTERN: `^E-.+$`)
 *   - Hook:      `H-<id>`  (Group G' canonicalization; free-form body)
 *
 * Pattern mirrors the canonical primitive id patterns (no character-class
 * restriction on the body) so any valid Workflow/Execution id is accepted.
 */
const EMITS_SOURCE_PATTERN = /^(W-.+|E-.+|H-.+)$/;
// -----------------------------------------------------------------------------
// `owns` — Tenant → Domain (D4 §2.2; D1 P-A1)
//
// Sovereignty edge. Tenant OWNS Domain but does NOT contain it (L5 META law).
// -----------------------------------------------------------------------------
export const OwnsEdgeSchema = z.object({
    kind: z.literal('owns'),
    source: z.string().regex(TENANT_ID_PATTERN),
    target: z.string().regex(DOMAIN_ID_PATTERN),
});
// -----------------------------------------------------------------------------
// `delegates_to` — Tenant → Tenant (D4 §2.2; D1 P-B8)
//
// Cross-tenant delegation (e.g. Asawa → Paisa managed-agent session). Schema
// allows source === target; F-6 terminal_check (M4.9) enforces "different
// tenants" at the runtime composition layer.
// -----------------------------------------------------------------------------
export const DelegatesToEdgeSchema = z.object({
    kind: z.literal('delegates_to'),
    source: z.string().regex(TENANT_ID_PATTERN),
    target: z.string().regex(TENANT_ID_PATTERN),
});
// -----------------------------------------------------------------------------
// `emits` — Workflow / Execution / Hook → DecisionProvenance (D4 §2.2; D2 P-A3)
//
// Provenance attribution edge. Source MUST match one of three id namespaces:
//   - Workflow.id   `W-<id>`
//   - Execution.id  `E-<id>`
//   - Hook.id       `H-<id>`
// Target is always a DecisionProvenance.id (`dp-<hex>`).
//
// Source pattern tightened in Group G' fix-up (2026-04-29) per codex master
// P3.5: prior `z.string().min(1)` allowed Tenant/Domain/garbage ids through.
// -----------------------------------------------------------------------------
export const EmitsEdgeSchema = z.object({
    kind: z.literal('emits'),
    source: z.string().regex(EMITS_SOURCE_PATTERN),
    target: z.string().regex(DP_ID_PATTERN),
});
// -----------------------------------------------------------------------------
// Discriminated union — single entry point for edge validation.
// -----------------------------------------------------------------------------
export const EdgeSchema = z.discriminatedUnion('kind', [
    OwnsEdgeSchema,
    DelegatesToEdgeSchema,
    EmitsEdgeSchema,
]);
/**
 * Predicate: is this Edge shape valid against D4 §2.2?
 */
export function isValidEdge(e) {
    return EdgeSchema.safeParse(e).success;
}
//# sourceMappingURL=edges.js.map