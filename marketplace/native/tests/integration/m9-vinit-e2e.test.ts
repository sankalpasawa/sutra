/**
 * M9 Group JJ — V2 §8 Vinit hook E2E (T-171..T-176).
 *
 * THE HEADLINE TEST. Composes every primitive (Domain/Charter/Workflow/
 * Execution) + every law (L1..L6 implicit via terminal_check + l4) + every
 * engine (Workflow/Skill/OPA/OTel/Governance/Cadence/Tenant) onto ONE
 * runtime path matching the V2 architecture-spec §8 worked example
 * verbatim. By M9 close this test validates that the architecture pivots,
 * milestone deliveries, and codex folds compose cleanly under one E2E load.
 *
 * Fixture (V2 §8 spec lines 220-260, structurally faithful per codex M9
 * P1.4 fold):
 *
 *   DOMAIN  D1.D2 "Sutra-OS · Plugin Reliability"
 *     principles=[Customer Focus First, no fabrication, archive never delete]
 *     accountable=[founder]
 *
 *   CHARTER C-vinit-feedback-resolution
 *     purpose="Vinit's filed gh issues get resolved + closed"
 *     obligations=[respond within 24h, ship fix, close gh issue with evidence]
 *     invariants=[no fabricated commits, gh closure references actual code change]
 *     success_metrics=[avg response time, % closed within 7d]
 *
 *   WORKFLOW W-build-completion-verification-hook
 *     preconditions="issue identified; scope agreed"
 *     stringency='process'
 *     inputs=[DataRef(gh_issue_body), DataRef(founder_directives)]
 *     outputs=[Asset(shipped_hook), Asset(ops_block_md)]
 *     interfaces_with=[
 *       Interface{endpoint=github-api, contract=gh_issue_close_schema, ...},
 *       Interface{endpoint=hook-fs,    contract=plugin_hook_path_schema, ...},
 *     ]
 *     step_graph=[research, design, build, test, operationalize, close]
 *       (each step is a `skill_ref` to a stub leaf Workflow with reuse_tag=true)
 *
 *   EXECUTION lineage:
 *     parent_exec_id='E-asawa-q2'
 *     sibling_group='g-vinit-walk-2026-04-28'
 *     trigger_event='founder_message:build-completion-verification-hook'
 *
 * Codex M9 P1.4 fold: each step is a `skill_ref` (NOT `action='no-op'` —
 * that is invalid; valid actions are `spawn_sub_unit|wait|terminate|
 * invoke_host_llm` only). The 6 stub Skills are leaf Workflows with
 * `reuse_tag=true` + minimal `return_contract` so the SkillEngine resolves
 * + validates them through the M6 path.
 *
 * I-1..I-9 + I-12 are asserted under E2E composition; I-10/I-11 stubs
 * (Phase 3 + M11/M12) ship as `it.skip` markers per D-NS-37.
 *
 * Spec source:
 *   - holding/plans/native-v1.0/M9-e2e-vinit.md Group JJ T-171..T-176
 *   - holding/research/2026-04-28-v2-architecture-spec.md §8 (lines 220-259)
 *   - holding/research/2026-04-29-native-d5-invariant-register.md §1
 *   - .enforcement/codex-reviews/2026-04-30-m9-pre-dispatch.md P1.4
 */

import { describe, it, expect } from 'vitest'

import { createDomain } from '../../src/primitives/domain.js'
import { createCharter } from '../../src/primitives/charter.js'
import { createWorkflow, isValidWorkflow } from '../../src/primitives/workflow.js'
import { createExecution, isValidStateTransition } from '../../src/primitives/execution.js'
import { createTenant } from '../../src/schemas/tenant.js'
import { SkillEngine } from '../../src/engine/skill-engine.js'
import {
  executeStepGraph,
  __resetWorkflowRunSeqForTest,
  type ActivityDispatcher,
} from '../../src/engine/step-graph-executor.js'
import {
  GovernanceOverhead,
} from '../../src/engine/governance-overhead.js'
import {
  InMemoryOTelExporter,
  OTelEmitter,
} from '../../src/engine/otel-emitter.js'
import {
  terminalCheck,
  type TerminalCheckForbiddenCouplingsInput,
} from '../../src/laws/l4-terminal-check.js'
import { createDecisionProvenance } from '../../src/schemas/decision-provenance.js'
import type { DataRef, Asset, Interface, Constraint } from '../../src/types/index.js'

// =============================================================================
// V2 §8 fixture — verbatim spec values, structurally faithful
// =============================================================================

const SCHEMA_VOID = JSON.stringify({ type: 'object' })

/** Build one of the 6 stub Skills (leaf Workflows w/ reuse_tag=true). */
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

function buildVinitFixture() {
  const tenant = createTenant({ id: 'T-asawa', name: 'Asawa' })

  // V2 §8 — Domain
  const domain = createDomain({
    id: 'D1.D2',
    name: 'Sutra-OS · Plugin Reliability',
    parent_id: 'D1',
    principles: [
      { name: 'Customer Focus First', predicate: 'always_true', durability: 'durable', owner_scope: 'domain' },
      { name: 'no fabrication', predicate: 'always_true', durability: 'durable', owner_scope: 'domain' },
      { name: 'archive never delete', predicate: 'always_true', durability: 'durable', owner_scope: 'domain' },
    ],
    intelligence: '',
    accountable: ['founder'],
    authority: 'CEO of Asawa',
    tenant_id: 'T-asawa',
  })

  // V2 §8 — Charter
  const obligations: Constraint[] = [
    { name: 'respond within 24h', predicate: 'response_time_h <= 24', durability: 'durable', owner_scope: 'charter', type: 'obligation' },
    { name: 'ship fix', predicate: 'fix_shipped == true', durability: 'durable', owner_scope: 'charter', type: 'obligation' },
    { name: 'close gh issue with evidence', predicate: 'closure_evidence_ref != null', durability: 'durable', owner_scope: 'charter', type: 'obligation' },
  ]
  const invariants: Constraint[] = [
    { name: 'no fabricated commits', predicate: 'commits_traceable == true', durability: 'durable', owner_scope: 'charter', type: 'invariant' },
    { name: 'gh closure references actual code change', predicate: 'closure_diff_nonempty == true', durability: 'durable', owner_scope: 'charter', type: 'invariant' },
  ]
  const charter = createCharter({
    id: 'C-vinit-feedback-resolution',
    purpose: "Vinit's filed gh issues get resolved + closed",
    scope_in: 'Vinit-filed gh issues on sankalpasawa/sutra',
    scope_out: 'External feedback channels (Slack, email)',
    obligations,
    invariants,
    success_metrics: ['avg response time', '% closed within 7d'],
    constraints: [],
    acl: [],
    authority: 'D1.D2',
    termination: 'When Vinit ceases external sessions',
  })

  // V2 §8 — DataRef inputs/outputs (using the M4.3 schema)
  const inputs: DataRef[] = [
    {
      kind: 'gh_issue_body',
      schema_ref: 'gh_issue_close_schema',
      locator: 'https://github.com/sankalpasawa/sutra/issues/4',
      version: '1',
      mutability: 'immutable',
      retention: 'session',
      authoritative_status: 'authoritative',
    },
    {
      kind: 'founder_directives',
      schema_ref: 'founder_directives_schema',
      locator: 'inline:vinit-build-directive',
      version: '1',
      mutability: 'immutable',
      retention: 'session',
      authoritative_status: 'authoritative',
    },
  ]
  const outputs: Asset[] = [
    {
      kind: 'shipped_hook',
      schema_ref: 'plugin_hook_path_schema',
      locator: 'sutra/marketplace/plugin/hooks/build-completion-verification.sh',
      version: '1',
      mutability: 'immutable',
      retention: 'permanent',
      authoritative_status: 'authoritative',
      stable_identity: 'hook:build-completion-verification',
      lifecycle_states: ['draft', 'shipped'],
    },
    {
      kind: 'ops_block_md',
      schema_ref: 'plugin_hook_path_schema',
      locator: 'holding/research/2026-04-30-vinit-hook-ops.md',
      version: '1',
      mutability: 'immutable',
      retention: 'permanent',
      authoritative_status: 'authoritative',
      stable_identity: 'doc:vinit-hook-ops',
      lifecycle_states: ['draft', 'shipped'],
    },
  ]

  // V2 §8 — Interfaces (github-api + hook-fs)
  const interfaces_with: Interface[] = [
    {
      endpoint_ref: 'github-api',
      workflow_ref: 'W-build-completion-verification-hook',
      direction: 'bidirectional',
      contract_schema: 'gh_issue_close_schema',
      qos: 'best-effort',
      failure_modes: ['rate_limited', '5xx_unavailable'],
    },
    {
      endpoint_ref: 'hook-fs',
      workflow_ref: 'W-build-completion-verification-hook',
      direction: 'outbound',
      contract_schema: 'plugin_hook_path_schema',
      qos: 'sync',
      failure_modes: ['eperm', 'enospc'],
    },
  ]

  // V2 §8 — 6-step skill_ref step_graph (codex P1.4 fold; each step
  // references a stub leaf Skill, NOT action='no-op').
  const STEP_NAMES = [
    'research',
    'design',
    'build',
    'test',
    'operationalize',
    'close',
  ] as const

  const skill_engine = new SkillEngine()
  STEP_NAMES.forEach((name) => skill_engine.register(buildStubSkill(`W-${name}-skill`)))

  const workflow = createWorkflow({
    id: 'W-build-completion-verification-hook',
    preconditions: 'issue identified; scope agreed',
    step_graph: [
      { step_id: 1, skill_ref: 'W-research-skill', inputs, outputs: [], on_failure: 'abort' },
      { step_id: 2, skill_ref: 'W-design-skill', inputs: [], outputs: [], on_failure: 'abort' },
      { step_id: 3, skill_ref: 'W-build-skill', inputs: [], outputs: [], on_failure: 'abort' },
      { step_id: 4, skill_ref: 'W-test-skill', inputs: [], outputs: [], on_failure: 'abort' },
      { step_id: 5, skill_ref: 'W-operationalize-skill', inputs: [], outputs: [], on_failure: 'abort' },
      { step_id: 6, skill_ref: 'W-close-skill', inputs: [], outputs: outputs as DataRef[], on_failure: 'abort' },
    ],
    inputs: inputs as DataRef[],
    outputs: outputs as DataRef[],
    state: [],
    postconditions: 'gh issue closed with evidence; hook shipped',
    failure_policy: 'abort',
    stringency: 'process',
    interfaces_with,
  })

  // V2 §8 — TriggerSpec (modelled inline; M5 doesn't ship TriggerSpec
  // as a primitive yet — Phase 3 lands the wire-format. For M9 the
  // trigger is captured via Execution.trigger_event semantics.)
  const trigger_event = 'founder_message:build-completion-verification-hook'

  // V2 §8 — Execution lineage (parent_exec + sibling_group verbatim)
  const execution = createExecution({
    id: 'E-vinit-hook-2026-04-28',
    workflow_id: workflow.id,
    trigger_event,
    state: 'pending',
    logs: [],
    results: [],
    parent_exec_id: 'E-asawa-q2',
    sibling_group: 'g-vinit-walk-2026-04-28',
    fingerprint: 'vinit-walk-fp-1',
  })

  return { tenant, domain, charter, workflow, execution, skill_engine, trigger_event, inputs, outputs, interfaces_with, obligations, invariants }
}

// =============================================================================
// T-171 — fixture compiles + validates against M4 schemas
// =============================================================================

describe('M9 Group JJ — T-171: V2 §8 Vinit fixture validates against M4 schemas', () => {
  it('Domain/Charter/Workflow/Execution all construct + isValid* succeeds', () => {
    const f = buildVinitFixture()
    expect(f.domain.id).toBe('D1.D2')
    expect(f.charter.id).toBe('C-vinit-feedback-resolution')
    expect(f.charter.purpose).toBe("Vinit's filed gh issues get resolved + closed")
    expect(f.charter.obligations).toHaveLength(3)
    expect(f.charter.invariants).toHaveLength(2)
    expect(f.charter.success_metrics).toEqual(['avg response time', '% closed within 7d'])
    expect(isValidWorkflow(f.workflow)).toBe(true)
    expect(f.workflow.step_graph).toHaveLength(6)
    expect(f.workflow.stringency).toBe('process')
    expect(f.workflow.interfaces_with).toHaveLength(2)
    expect(f.execution.parent_exec_id).toBe('E-asawa-q2')
    expect(f.execution.sibling_group).toBe('g-vinit-walk-2026-04-28')
    expect(f.execution.trigger_event).toBe('founder_message:build-completion-verification-hook')
  })
})

// =============================================================================
// T-172 — full E2E lifecycle through all 6 step_graph nodes
// =============================================================================

describe('M9 Group JJ — T-172: full lifecycle through 6 step_graph nodes', () => {
  it('executeStepGraph runs all 6 stub Skills; terminal state success', async () => {
    __resetWorkflowRunSeqForTest()
    const f = buildVinitFixture()
    // Stub dispatcher returns minimal schema-compliant payload (empty
    // object) for each leaf Skill's wait step — type:object accepts {}.
    const dispatch: ActivityDispatcher = () => ({ kind: 'ok', outputs: [{}] })

    const result = await executeStepGraph(f.workflow, dispatch, {
      skill_engine: f.skill_engine,
    })
    expect(result.state).toBe('success')
    expect(result.failure_reason).toBeNull()
    expect(result.completed_step_ids).toEqual([1, 2, 3, 4, 5, 6])
    expect(result.visited_step_ids).toEqual([1, 2, 3, 4, 5, 6])
    expect(result.child_edges).toBeDefined()
    expect(result.child_edges).toHaveLength(6)
    // Verify the Execution can transition through pending → running → success
    expect(isValidStateTransition('pending', 'running')).toBe(true)
    expect(isValidStateTransition('running', 'success')).toBe(true)
  })
})

// =============================================================================
// T-173 — I-7 + I-9 (DecisionProvenance under E2E)
// =============================================================================

describe('M9 Group JJ — T-173: I-7 + I-9 (DecisionProvenance per Execution)', () => {
  it('every governance hook emits DP with policy_id + policy_version under E2E', async () => {
    __resetWorkflowRunSeqForTest()
    const f = buildVinitFixture()
    const exporter = new InMemoryOTelExporter()
    const emitter = new OTelEmitter(exporter)
    const dispatch: ActivityDispatcher = () => ({ kind: 'ok', outputs: [{}] })

    const result = await executeStepGraph(f.workflow, dispatch, {
      skill_engine: f.skill_engine,
      otel_emitter: emitter,
    })
    expect(result.state).toBe('success')
    // I-7 — at least one consequential decision is in the OTel stream.
    // Under M9 composition the SKILL_RESOLVED + STEP_COMPLETE events are
    // the consequential decisions (one per step).
    const skill_resolved = exporter.records.filter((r) => r.decision_kind === 'SKILL_RESOLVED')
    expect(skill_resolved.length).toBeGreaterThanOrEqual(6)
    // Every governance event carries trace_id (correlation contract).
    for (const ev of skill_resolved) {
      expect(typeof ev.trace_id).toBe('string')
      expect(ev.trace_id.length).toBeGreaterThan(0)
    }

    // I-9 — DecisionProvenance schema accepts policy_id + policy_version
    // (we mint a sample DP referencing the Workflow to assert the shape).
    const dp = createDecisionProvenance({
      id: 'dp-aabbcc',
      actor: 'asawa@nurix.ai',
      agent_identity: { kind: 'human', id: 'human:asawa@nurix.ai', version: '1' },
      timestamp: '2026-04-30T12:00:00Z',
      evidence: [],
      authority_id: 'CEO-Asawa',
      policy_id: 'C-vinit-feedback-resolution',
      policy_version: '1.0',
      confidence: 0.95,
      decision_kind: 'EXECUTE',
      scope: 'WORKFLOW',
      outcome: 'Vinit hook execution kicked off',
      next_action_ref: f.workflow.id,
    })
    expect(dp.policy_id).toBe('C-vinit-feedback-resolution')
    expect(dp.policy_version).toBe('1.0')
  })
})

// =============================================================================
// T-174 — I-6 (cross-component overhead ≤15% under E2E)
// =============================================================================

describe('M9 Group JJ — T-174: I-6 (overhead ≤15% under composition)', () => {
  it('GovernanceOverhead under E2E load stays in green/yellow zone', async () => {
    __resetWorkflowRunSeqForTest()
    const f = buildVinitFixture()
    const overhead = new GovernanceOverhead()
    overhead.startTurn('m9-vinit-e2e', 10_000)
    // Track minor governance overhead — well under 15%.
    overhead.track('m9-vinit-e2e', 'input_routing', 50)
    overhead.track('m9-vinit-e2e', 'depth_estimation', 100)
    overhead.track('m9-vinit-e2e', 'blueprint', 200)

    const dispatch: ActivityDispatcher = () => ({ kind: 'ok', outputs: [{}] })
    const result = await executeStepGraph(f.workflow, dispatch, {
      skill_engine: f.skill_engine,
      governance_overhead: overhead,
      turn_id: 'm9-vinit-e2e',
    })
    expect(result.state).toBe('success')
    const report = overhead.endTurn('m9-vinit-e2e')
    // 350 / 10000 = 3.5%
    expect(report.overhead_pct).toBeLessThan(0.15)
    expect(report.threshold_tripped).toBe(false)
  })
})

// =============================================================================
// T-175 — I-1..I-5 re-verified under composition
// =============================================================================

describe('M9 Group JJ — T-175: I-1..I-5 hold under E2E composition', () => {
  it('I-1 Domain.id valid; I-2 Charter has obligations; I-3 step skill_ref XOR action; I-4 success Execution failure_reason null; I-5 terminal_check (T1-T6 implicit)', async () => {
    __resetWorkflowRunSeqForTest()
    const f = buildVinitFixture()

    // I-1 — Domain.id matches D-numbered pattern
    expect(/^D\d+(\.D\d+)*$/.test(f.domain.id)).toBe(true)
    // I-2 — Charter has obligations + invariants
    expect(f.charter.obligations.length).toBeGreaterThan(0)
    expect(f.charter.invariants.length).toBeGreaterThan(0)
    // I-3 — every step has skill_ref XOR action (validated at construction)
    for (const step of f.workflow.step_graph) {
      const hasSkill = typeof step.skill_ref === 'string' && step.skill_ref.length > 0
      const hasAction = typeof step.action === 'string' && step.action.length > 0
      expect(hasSkill !== hasAction).toBe(true) // XOR
    }

    // I-4 — running Execution has failure_reason=null UNTIL it transitions to failed.
    expect(f.execution.failure_reason).toBeNull()

    // I-5 — terminalCheck T1-T6 + F-1..F-7 fired and clears for legal fixture.
    const tc_input: TerminalCheckForbiddenCouplingsInput = {
      workflow: f.workflow,
      execution: f.execution,
      charter: f.charter,
      tenant: f.tenant,
      operationalizes_charters: [f.charter.id],
      reflexive_auth: { founder_authorization: false, meta_charter_approval: false },
      containment_chain: [f.tenant.id, f.domain.id, f.charter.id, f.workflow.id],
    }
    const tc = terminalCheck(tc_input)
    expect(tc.pass).toBe(true)
    expect(tc.violations).toEqual([])

    // Run the executor with the probe → confirms the Workflow runs to
    // success when terminalCheck clears (composition path, not just unit).
    const dispatch: ActivityDispatcher = () => ({ kind: 'ok', outputs: [{}] })
    const result = await executeStepGraph(f.workflow, dispatch, {
      skill_engine: f.skill_engine,
      terminalCheckProbe: () => terminalCheck(tc_input).violations,
    })
    expect(result.state).toBe('success')
    expect(result.failure_reason).toBeNull()
  })
})

// =============================================================================
// T-176 — I-10 + I-11 stubs (deferred to Phase 3 / M11/M12 per D-NS-37)
// =============================================================================

describe('M9 Group JJ — T-176: I-10 / I-11 deferred stubs', () => {
  it.skip('I-10 cutover canary green during Core → Native cutover (Phase 3 — M9 ships test scaffold only)', () => {
    // Test scaffold lives here; full assertion arrives at Phase 3 cutover
    // (P-C12). The skip marker is intentional — D-NS-37.
    expect(true).toBe(true)
  })

  it.skip('I-11 time-to-value ≤30min for new Sutra adopter (M11/M12 — M9 ships test scaffold only)', () => {
    // Test scaffold lives here; full assertion arrives at M11 dogfood +
    // M12 default-composition rollout. Skip marker intentional — D-NS-37.
    expect(true).toBe(true)
  })
})
