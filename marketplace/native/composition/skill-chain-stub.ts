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

import { createDomain } from '../src/primitives/domain.js'
import { createCharter } from '../src/primitives/charter.js'
import { createWorkflow } from '../src/primitives/workflow.js'
import { SkillEngine } from '../src/engine/skill-engine.js'

const SCHEMA_VOID = JSON.stringify({ type: 'object' })

export interface SkillChainStubOptions {
  tenant_id: string
  domain_id: string
}

function buildStubSkill(id: string) {
  return createWorkflow({
    id,
    preconditions: '',
    step_graph: [
      { step_id: 1, action: 'wait', inputs: [], outputs: [], on_failure: 'abort' },
    ],
    inputs: [],
    outputs: [],
    state: [],
    postconditions: '',
    failure_policy: 'abort',
    stringency: 'task',
    interfaces_with: [],
    reuse_tag: true,
    return_contract: SCHEMA_VOID,
  })
}

export function buildSkillChainStubWorkflow(opts: SkillChainStubOptions) {
  const domain = createDomain({
    id: opts.domain_id,
    name: 'Skill Chain',
    parent_id: 'D0',
    principles: [
      { name: 'Skills compose into chains', predicate: 'always_true', durability: 'durable', owner_scope: 'domain' },
    ],
    intelligence: '',
    accountable: ['founder'],
    authority: 'tenant',
    tenant_id: opts.tenant_id,
  })

  const charter = createCharter({
    id: 'C-skill-chain',
    purpose: 'Demonstrate Skill chaining via SkillEngine resolve path',
    scope_in: 'Skill-reuse Workflows',
    scope_out: 'One-off action steps',
    obligations: [],
    invariants: [],
    success_metrics: ['skills-chained-per-run >= 2'],
    constraints: [],
    acl: [],
    authority: opts.domain_id,
    termination: 'When chain cap reached',
  })

  const skill_engine = new SkillEngine()
  skill_engine.register(buildStubSkill('W-stub-skill-a'))
  skill_engine.register(buildStubSkill('W-stub-skill-b'))

  const workflow = createWorkflow({
    id: 'W-skill-chain-stub',
    preconditions: 'skill chain registered',
    step_graph: [
      { step_id: 1, skill_ref: 'W-stub-skill-a', inputs: [], outputs: [], on_failure: 'abort' },
      { step_id: 2, skill_ref: 'W-stub-skill-b', inputs: [], outputs: [], on_failure: 'abort' },
    ],
    inputs: [],
    outputs: [],
    state: [],
    postconditions: 'skill chain completed',
    failure_policy: 'abort',
    stringency: 'task',
    interfaces_with: [],
  })

  return { domain, charter, workflow, skill_engine }
}
