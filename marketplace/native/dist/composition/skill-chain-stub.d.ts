/**
 * Default Composition v1.0 — Workflow 3: skill-chain-stub
 *
 * Seed Workflow that exercises the SkillEngine resolve path (M6) by chaining
 * 2 stub Skills. Each Skill is a child Workflow with reuse_tag=true that
 * resolves through the M6 invocation protocol. Demonstrates the M9 invariants
 * composition under a smaller scope than the V2 §8 Vinit fixture.
 *
 * Use case: a Tenant operator wants to compose existing Skills (Workflows
 * with reuse_tag=true) into a parent Workflow without re-implementing the
 * resolve plumbing. They import this seed, register their own Skills via
 * the returned SkillEngine, and run.
 *
 * Spec source:
 *   - holding/plans/native-v1.0/M12-release-canary.md (D-NS-52, A-1, T-241)
 */
import { SkillEngine } from '../src/engine/skill-engine.js';
export interface SkillChainStubOptions {
    tenant_id: string;
    domain_id: string;
}
export declare function buildSkillChainStubWorkflow(opts: SkillChainStubOptions): {
    domain: import("../src/primitives/domain.js").Domain;
    charter: import("../src/primitives/charter.js").Charter;
    workflow: import("../src/primitives/workflow.js").Workflow;
    skill_engine: SkillEngine;
};
//# sourceMappingURL=skill-chain-stub.d.ts.map