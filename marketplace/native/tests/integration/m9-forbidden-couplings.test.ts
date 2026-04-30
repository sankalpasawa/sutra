/**
 * M9 Group II — F-1..F-7 forbidden coupling integration suite (T-164..T-170).
 *
 * Each test composes the engine path (`executeStepGraph` + a
 * `terminalCheckProbe` mapped from the `terminalCheck(...)` aggregate at
 * `l4-terminal-check.ts:661`, OR the constructor for couplings the
 * primitive enforces at mint time, OR the existing executor cross-tenant
 * gate from Group FF) and asserts:
 *
 *   - Positive case (rejection): the violation is detected end-to-end
 *     via the engine surface, NOT via constructor inspection alone.
 *   - Negative case (legal sibling): the same shape WITHOUT the violation
 *     succeeds end-to-end through `executeStepGraph`.
 *
 * Per codex M9 pre-dispatch P2.1 fold + per the M9 plan Group II:
 *   "Each F-test invokes executeStepGraph + terminalCheckProbe (or
 *    policy-dispatcher); not constructor-only."
 *
 * NOTE on F-4 / F-5: these are step-shape couplings (skill_ref XOR action)
 * that are enforced at the L2 BOUNDARY canonical anchor + at the
 * `createWorkflow.validateStep` operational mirror (workflow.ts:161-247).
 * The constructor REJECTS the malformed Workflow at primitive-mint, so the
 * "engine path" for F-4/F-5 *necessarily* runs through that mint boundary
 * — `executeStepGraph` cannot receive an F-4/F-5 violating step because
 * the Workflow primitive cannot be constructed. Both halves are exercised
 * (positive: createWorkflow throws; negative: a corrected sibling runs
 * end-to-end through executeStepGraph).
 *
 * NOTE on F-1 / F-2 / F-3 / F-7: these are CROSS-PRIMITIVE couplings that
 * only manifest when the runtime composes Domain + Charter + Workflow +
 * Execution. The terminalCheckProbe is the canonical engine entry point
 * for them at terminate-stage (step-graph-executor.ts:1140+).
 *
 * NOTE on F-6: already exercised in Group FF
 * (`tests/integration/tenant-isolation.test.ts`); this file adds a
 * positive-sibling assertion to confirm the M9 plan T-170 sibling-positive
 * contract for F-6 too.
 *
 * Spec source:
 *   - holding/plans/native-v1.0/M9-e2e-vinit.md Group II T-164..T-170
 *   - holding/research/2026-04-29-native-d4-primitives-composition-spec.md F-1..F-7
 *   - .enforcement/codex-reviews/2026-04-30-m9-pre-dispatch.md P2.1
 */

import { describe, it, expect } from 'vitest'

import { createWorkflow, type Workflow } from '../../src/primitives/workflow.js'
import { createCharter, type Charter } from '../../src/primitives/charter.js'
import { createDomain, type Domain } from '../../src/primitives/domain.js'
import { createExecution, type Execution } from '../../src/primitives/execution.js'
import { createTenant, type Tenant } from '../../src/schemas/tenant.js'
import {
  terminalCheck,
  type ForbiddenCouplingId,
  type TerminalCheckForbiddenCouplingsInput,
} from '../../src/laws/l4-terminal-check.js'
import {
  executeStepGraph,
  __resetWorkflowRunSeqForTest,
  type ActivityDispatcher,
} from '../../src/engine/step-graph-executor.js'
import type { DelegatesToEdge } from '../../src/types/edges.js'
import { SkillEngine } from '../../src/engine/skill-engine.js'

const SCHEMA_INT = JSON.stringify({ type: 'integer' })
const ALWAYS_OK_DISPATCH: ActivityDispatcher = (descriptor) => ({
  kind: 'ok',
  outputs: [`out-${descriptor.step_id}`],
})

// =============================================================================
// Fixtures — minimal valid primitives sets used across F-N tests.
// =============================================================================

function buildTenant(): Tenant {
  return createTenant({ id: 'T-asawa', name: 'Asawa' })
}

function buildDomain(): Domain {
  return createDomain({
    id: 'D1.D2',
    name: 'Sutra-OS · Plugin Reliability',
    parent_id: 'D1',
    principles: [],
    intelligence: '',
    accountable: ['founder'],
    authority: 'CEO of Asawa',
    tenant_id: 'T-asawa',
  })
}

function buildCharter(id = 'C-vinit-feedback-resolution'): Charter {
  return createCharter({
    id,
    purpose: 'Vinit gh issues get resolved + closed',
    scope_in: '',
    scope_out: '',
    obligations: [],
    invariants: [],
    success_metrics: [],
    constraints: [],
    acl: [],
    authority: 'D1.D2',
    termination: '',
  })
}

function buildExecution(workflow_id: string, trigger_event = 'founder_message:vinit'): Execution {
  return createExecution({
    id: 'E-vinit-walk-1',
    workflow_id,
    trigger_event,
    state: 'pending',
    logs: [],
    results: [],
    parent_exec_id: null,
    sibling_group: null,
    fingerprint: 'fp-1',
  })
}

function buildLegalWorkflow(id = 'W-vinit-build'): Workflow {
  return createWorkflow({
    id,
    preconditions: '',
    step_graph: [
      { step_id: 1, action: 'wait', inputs: [], outputs: [], on_failure: 'abort' },
      { step_id: 2, action: 'terminate', inputs: [], outputs: [], on_failure: 'abort' },
    ],
    inputs: [],
    outputs: [],
    state: [],
    postconditions: '',
    failure_policy: 'abort',
    stringency: 'task',
    interfaces_with: [],
  })
}

/** Build a terminalCheckProbe from a TerminalCheckForbiddenCouplingsInput. */
function probeFromInput(
  input: TerminalCheckForbiddenCouplingsInput,
): () => ForbiddenCouplingId[] {
  return () => terminalCheck(input).violations
}

// =============================================================================
// F-1 — Tenant directly contains Workflow (codex P1.3 fold; via terminalCheck)
// =============================================================================

describe('M9 Group II — F-1 (Tenant→Workflow containment skips Domain+Charter)', () => {
  it('positive: containment chain Tenant→Workflow (length-2) → executor returns failed with forbidden_coupling:F-1', async () => {
    __resetWorkflowRunSeqForTest()
    const tenant = buildTenant()
    const charter = buildCharter()
    const wf = buildLegalWorkflow()
    const exec = buildExecution(wf.id)

    // F-1 violation: containment_chain skips Domain + Charter.
    const probe = probeFromInput({
      workflow: wf,
      execution: exec,
      charter,
      tenant,
      operationalizes_charters: [charter.id],
      reflexive_auth: { founder_authorization: false, meta_charter_approval: false },
      containment_chain: [tenant.id, wf.id],
    })

    const result = await executeStepGraph(wf, ALWAYS_OK_DISPATCH, {
      terminalCheckProbe: probe,
    })
    expect(result.state).toBe('failed')
    expect(result.failure_reason).toContain('forbidden_coupling:')
    expect(result.failure_reason).toContain('F-1')
  })

  it('negative: legal containment chain Tenant→Domain→Charter→Workflow → executor succeeds', async () => {
    __resetWorkflowRunSeqForTest()
    const tenant = buildTenant()
    const domain = buildDomain()
    const charter = buildCharter()
    const wf = buildLegalWorkflow()
    const exec = buildExecution(wf.id)

    const probe = probeFromInput({
      workflow: wf,
      execution: exec,
      charter,
      tenant,
      operationalizes_charters: [charter.id],
      reflexive_auth: { founder_authorization: false, meta_charter_approval: false },
      containment_chain: [tenant.id, domain.id, charter.id, wf.id],
    })

    const result = await executeStepGraph(wf, ALWAYS_OK_DISPATCH, {
      terminalCheckProbe: probe,
    })
    expect(result.state).toBe('success')
    expect(result.failure_reason).toBeNull()
  })
})

// =============================================================================
// F-2 — Workflow without operationalizes link to Charter
// =============================================================================

describe('M9 Group II — F-2 (Workflow without operationalizes link)', () => {
  it('positive: empty operationalizes_charters → executor returns failed with forbidden_coupling:F-2', async () => {
    __resetWorkflowRunSeqForTest()
    const wf = buildLegalWorkflow()
    const exec = buildExecution(wf.id)
    const tenant = buildTenant()
    const charter = buildCharter()
    const probe = probeFromInput({
      workflow: wf,
      execution: exec,
      charter,
      tenant,
      operationalizes_charters: [], // F-2 violation
      reflexive_auth: { founder_authorization: false, meta_charter_approval: false },
    })

    const result = await executeStepGraph(wf, ALWAYS_OK_DISPATCH, {
      terminalCheckProbe: probe,
    })
    expect(result.state).toBe('failed')
    expect(result.failure_reason).toContain('F-2')
  })

  it('negative: operationalizes_charters includes the Charter id → executor succeeds', async () => {
    __resetWorkflowRunSeqForTest()
    const wf = buildLegalWorkflow()
    const exec = buildExecution(wf.id)
    const tenant = buildTenant()
    const charter = buildCharter()
    const probe = probeFromInput({
      workflow: wf,
      execution: exec,
      charter,
      tenant,
      operationalizes_charters: [charter.id],
      reflexive_auth: { founder_authorization: false, meta_charter_approval: false },
    })
    const result = await executeStepGraph(wf, ALWAYS_OK_DISPATCH, {
      terminalCheckProbe: probe,
    })
    expect(result.state).toBe('success')
  })
})

// =============================================================================
// F-3 — Execution spawned without TriggerEvent
// =============================================================================

describe('M9 Group II — F-3 (Execution without trigger_event)', () => {
  it('positive: empty trigger_event surfaces as forbidden_coupling:F-3 via probe', async () => {
    __resetWorkflowRunSeqForTest()
    const wf = buildLegalWorkflow()
    const tenant = buildTenant()
    const charter = buildCharter()

    // F-3 fixture: an execution-shaped object with empty trigger_event.
    // The Execution PRIMITIVE doesn't reject empty trigger_event at
    // construction (V2 §1 P4 only types it as a string), so the violation
    // surfaces at terminal_check via `f3Predicate`.
    const exec_bad = {
      id: 'E-no-trigger',
      workflow_id: wf.id,
      trigger_event: '',
      state: 'pending' as const,
      logs: [],
      results: [],
      parent_exec_id: null,
      sibling_group: null,
      fingerprint: 'fp-bad',
      failure_reason: null,
      agent_identity: null,
    }
    const probe = probeFromInput({
      workflow: wf,
      execution: exec_bad,
      charter,
      tenant,
      operationalizes_charters: [charter.id],
      reflexive_auth: { founder_authorization: false, meta_charter_approval: false },
    })
    const result = await executeStepGraph(wf, ALWAYS_OK_DISPATCH, {
      terminalCheckProbe: probe,
    })
    expect(result.state).toBe('failed')
    expect(result.failure_reason).toContain('F-3')
  })

  it('negative: legal trigger_event → executor succeeds', async () => {
    __resetWorkflowRunSeqForTest()
    const wf = buildLegalWorkflow()
    const exec = buildExecution(wf.id, 'founder_message:vinit-build')
    const tenant = buildTenant()
    const charter = buildCharter()
    const probe = probeFromInput({
      workflow: wf,
      execution: exec,
      charter,
      tenant,
      operationalizes_charters: [charter.id],
      reflexive_auth: { founder_authorization: false, meta_charter_approval: false },
    })
    const result = await executeStepGraph(wf, ALWAYS_OK_DISPATCH, {
      terminalCheckProbe: probe,
    })
    expect(result.state).toBe('success')
  })
})

// =============================================================================
// F-4 / F-5 — step shape (skill_ref XOR action) enforced at primitive-mint
// =============================================================================

describe('M9 Group II — F-4 (step with both skill_ref AND action)', () => {
  it('positive: createWorkflow REJECTS step with both skill_ref + action (L2 BOUNDARY mint)', () => {
    expect(() =>
      createWorkflow({
        id: 'W-f4-violation',
        preconditions: '',
        step_graph: [
          {
            step_id: 1,
            skill_ref: 'W-leaf',
            action: 'wait',
            inputs: [],
            outputs: [],
            on_failure: 'abort',
          },
        ],
        inputs: [],
        outputs: [],
        state: [],
        postconditions: '',
        failure_policy: 'abort',
        stringency: 'task',
        interfaces_with: [],
      }),
    ).toThrow(/skill_ref XOR action/)
  })

  it('negative: legal sibling (skill_ref OR action, exclusively) executes through executeStepGraph', async () => {
    __resetWorkflowRunSeqForTest()
    // Register a real Skill so skill_ref resolves.
    const engine = new SkillEngine()
    engine.register(
      createWorkflow({
        id: 'W-f4-leaf',
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
        return_contract: SCHEMA_INT,
      }),
    )
    const wf = createWorkflow({
      id: 'W-f4-legal',
      preconditions: '',
      step_graph: [
        { step_id: 1, skill_ref: 'W-f4-leaf', inputs: [], outputs: [], on_failure: 'abort' },
        { step_id: 2, action: 'terminate', inputs: [], outputs: [], on_failure: 'abort' },
      ],
      inputs: [],
      outputs: [],
      state: [],
      postconditions: '',
      failure_policy: 'abort',
      stringency: 'task',
      interfaces_with: [],
    })
    const dispatch: ActivityDispatcher = () => ({ kind: 'ok', outputs: [42] })
    const result = await executeStepGraph(wf, dispatch, { skill_engine: engine })
    expect(result.state).toBe('success')
  })
})

describe('M9 Group II — F-5 (step with neither skill_ref NOR action)', () => {
  it('positive: createWorkflow REJECTS step with neither field (L2 BOUNDARY mint)', () => {
    expect(() =>
      createWorkflow({
        id: 'W-f5-violation',
        preconditions: '',
        step_graph: [
          { step_id: 1, inputs: [], outputs: [], on_failure: 'abort' } as unknown as never,
        ],
        inputs: [],
        outputs: [],
        state: [],
        postconditions: '',
        failure_policy: 'abort',
        stringency: 'task',
        interfaces_with: [],
      }),
    ).toThrow(/skill_ref XOR action/)
  })

  it('negative: legal sibling (action specified) executes through executeStepGraph', async () => {
    __resetWorkflowRunSeqForTest()
    const wf = buildLegalWorkflow('W-f5-legal')
    const result = await executeStepGraph(wf, ALWAYS_OK_DISPATCH)
    expect(result.state).toBe('success')
  })
})

// =============================================================================
// F-6 — Cross-tenant operation without delegates_to edge (Group FF foundation)
// =============================================================================

describe('M9 Group II — F-6 (cross-tenant op without delegates_to)', () => {
  it('positive (already in Group FF): cross-tenant op with no edge → cross_tenant_boundary failure', async () => {
    __resetWorkflowRunSeqForTest()
    const wf = createWorkflow({
      id: 'W-f6-cross-tenant',
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
      custody_owner: 'T-paisa',
    })
    const result = await executeStepGraph(wf, ALWAYS_OK_DISPATCH, {
      tenant_context_id: 'T-asawa',
      delegates_to_edges: [],
    })
    expect(result.state).toBe('failed')
    expect(result.failure_reason).toContain('cross_tenant_boundary')
  })

  it('negative sibling: matching delegates_to edge → executor succeeds', async () => {
    __resetWorkflowRunSeqForTest()
    const wf = createWorkflow({
      id: 'W-f6-allow-sibling',
      preconditions: '',
      step_graph: [
        { step_id: 1, action: 'wait', inputs: [], outputs: [], on_failure: 'abort' },
        { step_id: 2, action: 'terminate', inputs: [], outputs: [], on_failure: 'abort' },
      ],
      inputs: [],
      outputs: [],
      state: [],
      postconditions: '',
      failure_policy: 'abort',
      stringency: 'task',
      interfaces_with: [],
      custody_owner: 'T-paisa',
    })
    const edges: ReadonlyArray<DelegatesToEdge> = [
      { kind: 'delegates_to', source: 'T-asawa', target: 'T-paisa' },
    ]
    const result = await executeStepGraph(wf, ALWAYS_OK_DISPATCH, {
      tenant_context_id: 'T-asawa',
      delegates_to_edges: edges,
    })
    expect(result.state).toBe('success')
  })
})

// =============================================================================
// F-7 — Workflow.modifies_sutra=true without reflexive_check Constraint cleared
// =============================================================================

describe('M9 Group II — F-7 (modifies_sutra=true without reflexive_check)', () => {
  it('positive: modifies_sutra=true + uncleared reflexive_auth → forbidden_coupling:F-7 via probe', async () => {
    __resetWorkflowRunSeqForTest()
    const wf = createWorkflow({
      id: 'W-f7-violation',
      preconditions: '',
      step_graph: [
        { step_id: 1, action: 'wait', inputs: [], outputs: [], on_failure: 'abort' },
        { step_id: 2, action: 'terminate', inputs: [], outputs: [], on_failure: 'abort' },
      ],
      inputs: [],
      outputs: [],
      state: [],
      postconditions: '',
      failure_policy: 'abort',
      stringency: 'task',
      interfaces_with: [],
      modifies_sutra: true,
    })
    const exec = buildExecution(wf.id)
    const tenant = buildTenant()
    const charter = buildCharter()
    const probe = probeFromInput({
      workflow: wf,
      execution: exec,
      charter,
      tenant,
      operationalizes_charters: [charter.id],
      reflexive_auth: { founder_authorization: false, meta_charter_approval: false }, // F-7 — uncleared
    })
    const result = await executeStepGraph(wf, ALWAYS_OK_DISPATCH, {
      terminalCheckProbe: probe,
    })
    expect(result.state).toBe('failed')
    expect(result.failure_reason).toContain('F-7')
  })

  it('negative: modifies_sutra=true + founder_authorization cleared → executor succeeds', async () => {
    __resetWorkflowRunSeqForTest()
    const wf = createWorkflow({
      id: 'W-f7-allow',
      preconditions: '',
      step_graph: [
        { step_id: 1, action: 'wait', inputs: [], outputs: [], on_failure: 'abort' },
        { step_id: 2, action: 'terminate', inputs: [], outputs: [], on_failure: 'abort' },
      ],
      inputs: [],
      outputs: [],
      state: [],
      postconditions: '',
      failure_policy: 'abort',
      stringency: 'task',
      interfaces_with: [],
      modifies_sutra: true,
    })
    const exec = buildExecution(wf.id)
    const tenant = buildTenant()
    const charter = buildCharter()
    const probe = probeFromInput({
      workflow: wf,
      execution: exec,
      charter,
      tenant,
      operationalizes_charters: [charter.id],
      reflexive_auth: { founder_authorization: true, meta_charter_approval: false }, // cleared
    })
    const result = await executeStepGraph(wf, ALWAYS_OK_DISPATCH, {
      terminalCheckProbe: probe,
    })
    expect(result.state).toBe('success')
    expect(result.failure_reason).toBeNull()
  })
})
