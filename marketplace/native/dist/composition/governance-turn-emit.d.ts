/**
 * Default Composition v1.0 — Workflow 1: governance-turn-emit
 *
 * Seed Workflow that demonstrates a minimal governance turn end-to-end:
 * receive an input, emit a Decision-Provenance record, terminate. Exercises
 * M5 step-graph executor + M8 OTel emitter (when wired by the caller).
 *
 * Use case: a fresh Asawa-style operator wants to wire a per-turn governance
 * record into their existing workflow without rebuilding the primitives. They
 * import this seed, register a Domain + Charter for their tenant, and run.
 *
 * Spec source:
 *   - holding/plans/native-v1.0/M12-release-canary.md (D-NS-52, A-1, T-241)
 *   - holding/research/2026-04-29-native-v1.0-final-architecture.md line 229
 *
 * NOT shipped at v1.0:
 *   - Real OTel exporter binding (caller wires per their telemetry stack)
 *   - Tenant-specific obligation/invariant predicates (caller customizes)
 */
export interface GovernanceTurnEmitOptions {
    /** Operator's tenant id (e.g. "T-asawa", "T-dayflow"). */
    tenant_id: string;
    /** Domain id (e.g. "D1.D2"). */
    domain_id: string;
    /** Charter id (e.g. "C-governance-turn"). */
    charter_id?: string;
}
export declare function buildGovernanceTurnEmitWorkflow(opts: GovernanceTurnEmitOptions): {
    domain: import("../src/primitives/domain.js").Domain;
    charter: import("../src/primitives/charter.js").Charter;
    workflow: import("../src/primitives/workflow.js").Workflow;
};
//# sourceMappingURL=governance-turn-emit.d.ts.map