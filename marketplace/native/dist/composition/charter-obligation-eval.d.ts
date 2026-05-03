/**
 * Default Composition v1.0 — Workflow 2: charter-obligation-eval
 *
 * Seed Workflow that exercises the OPA policy path (M7) against a Charter
 * obligation. Evaluator returns allow/deny based on the Charter's compiled
 * Rego policy; result is observed in the step graph executor's policy gate.
 *
 * Use case: a Tenant operator wants to gate an action behind their Charter's
 * obligations without building the policy plumbing themselves. They import
 * this seed, customize the obligation predicate, and the policy gate fires.
 *
 * Spec source:
 *   - holding/plans/native-v1.0/M12-release-canary.md (D-NS-52, A-1, T-241)
 *
 * NOT shipped at v1.0:
 *   - Compiled Rego output (caller compiles via M7 charter→rego compiler)
 *   - Real policy_dispatcher (caller wires per their OPA setup)
 */
export interface CharterObligationEvalOptions {
    tenant_id: string;
    domain_id: string;
    /** Operator's obligation predicate (e.g. "approval_present == true"). */
    obligation_predicate: string;
}
export declare function buildCharterObligationEvalWorkflow(opts: CharterObligationEvalOptions): {
    domain: import("../src/primitives/domain.js").Domain;
    charter: import("../src/primitives/charter.js").Charter;
    workflow: import("../src/primitives/workflow.js").Workflow;
};
//# sourceMappingURL=charter-obligation-eval.d.ts.map