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
import { createDomain } from '../src/primitives/domain.js';
import { createCharter } from '../src/primitives/charter.js';
import { createWorkflow } from '../src/primitives/workflow.js';
export function buildCharterObligationEvalWorkflow(opts) {
    const domain = createDomain({
        id: opts.domain_id,
        name: 'Obligation Gate',
        parent_id: 'D0',
        principles: [
            { name: 'obligations gate actions', predicate: 'always_true', durability: 'durable', owner_scope: 'domain' },
        ],
        intelligence: '',
        accountable: ['founder'],
        authority: 'tenant',
        tenant_id: opts.tenant_id,
    });
    const obligations = [
        {
            name: 'obligation gate fires before action',
            predicate: opts.obligation_predicate,
            durability: 'durable',
            owner_scope: 'charter',
            type: 'obligation',
        },
    ];
    const charter = createCharter({
        id: 'C-obligation-gate',
        purpose: 'Obligations evaluated against state before action proceeds',
        scope_in: 'Operator-initiated actions',
        scope_out: 'Background tasks with separate authority',
        obligations,
        invariants: [],
        success_metrics: ['policy-gate-fired-per-action = 1'],
        constraints: [],
        acl: [],
        authority: opts.domain_id,
        termination: 'When obligations cleared',
    });
    // Single step with policy_check=true so the M7 policy_dispatcher gate fires
    // before this step's Activity dispatch (when caller supplies the dispatcher
    // + compiled_policy options at executeStepGraph time).
    const workflow = createWorkflow({
        id: 'W-charter-obligation-eval',
        preconditions: 'action requested; charter live',
        step_graph: [
            { step_id: 1, action: 'wait', inputs: [], outputs: [], on_failure: 'abort', policy_check: true },
        ],
        inputs: [],
        outputs: [],
        state: [],
        postconditions: 'action allowed (policy passed) or aborted (policy denied)',
        failure_policy: 'abort',
        stringency: 'process',
        interfaces_with: [],
    });
    return { domain, charter, workflow };
}
//# sourceMappingURL=charter-obligation-eval.js.map