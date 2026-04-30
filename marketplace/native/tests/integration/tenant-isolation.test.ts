/**
 * M9 Group FF — TenantIsolation integration test (T-155).
 *
 * Drives the full step-graph executor with cross-tenant scenarios and asserts
 * I-8 + F-6:
 *
 *   I-8 (D5 invariant): Tenant boundary not crossed without a `delegates_to`
 *        edge granting the operation.
 *   F-6 (D4 forbidden coupling): Cross-tenant operation without a matching
 *        `delegates_to` edge MUST be rejected at runtime.
 *
 * Codex M9 re-review P1 fold: enforcement is RUNTIME-DERIVED, not annotation-
 * driven. The executor compares `tenant_context_id` against each step's
 * effective tenant (from skill_ref's owning Workflow.custody_owner OR the
 * parent Workflow's custody_owner) and calls
 * `TenantIsolation.assertCrossTenantAllowed` unconditionally on mismatch —
 * NO `WorkflowStep.crosses_tenant?` opt-out hint exists.
 *
 * Each scenario has TWO halves:
 *   - positive: cross-tenant op WITHOUT edge → CrossTenantBoundaryError
 *               surfaces as failed Execution with errMsg
 *               'cross_tenant_boundary:<source>:<target>:<operation>'
 *   - negative: cross-tenant op WITH matching edge → step succeeds end-to-end
 *
 * Spec source:
 *   - holding/plans/native-v1.0/M9-e2e-vinit.md Group FF T-155 (A-3 row F-6)
 *   - .enforcement/codex-reviews/2026-04-30-m9-pre-dispatch.md P1.2 + re-review P1
 *   - holding/research/2026-04-29-native-d5-invariant-register.md §1 I-8
 */

import { describe, it, expect } from 'vitest'

import { createWorkflow } from '../../src/primitives/workflow.js'
import { SkillEngine } from '../../src/engine/skill-engine.js'
import {
  executeStepGraph,
  __resetWorkflowRunSeqForTest,
  type ActivityDispatcher,
} from '../../src/engine/step-graph-executor.js'
import type { DelegatesToEdge } from '../../src/types/edges.js'

const SCHEMA_INT = JSON.stringify({ type: 'integer' })

// =============================================================================
// Fixtures — single fixture file matching M9 plan Group FF acceptance.
// =============================================================================

const ALWAYS_OK_DISPATCH: ActivityDispatcher = (descriptor) => ({
  kind: 'ok',
  outputs: [`out-${descriptor.step_id}`],
})

describe('M9 Group FF — F-6 cross-tenant rejection (action step path)', () => {
  it('action step WITH workflow.custody_owner ≠ tenant_context_id AND no edge → cross_tenant_boundary failure', async () => {
    __resetWorkflowRunSeqForTest()
    // Workflow's custody_owner is T-paisa; we operate as T-asawa with NO
    // delegates_to edge. The first action step should fail with the
    // canonical cross_tenant_boundary errMsg routed via M5 failure-policy
    // (on_failure='abort' → state='failed', failure_reason populated).
    const wf = createWorkflow({
      id: 'W-cross-tenant-deny',
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
    expect(result.failure_reason).toContain('cross_tenant_boundary:T-asawa:T-paisa:')
    expect(result.failure_reason).toContain('step_action:wait')
    // visited contains the failed step; completed does NOT (codex P1.1 contract).
    expect(result.visited_step_ids).toContain(1)
    expect(result.completed_step_ids).not.toContain(1)
  })

  it('action step WITH matching delegates_to edge → step succeeds end-to-end', async () => {
    __resetWorkflowRunSeqForTest()
    const wf = createWorkflow({
      id: 'W-cross-tenant-allow',
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
    expect(result.failure_reason).toBeNull()
    expect(result.completed_step_ids).toEqual([1])
    expect(result.visited_step_ids).toEqual([1, 2])
  })
})

describe('M9 Group FF — F-6 cross-tenant rejection (skill_ref step path)', () => {
  it('skill_ref step where resolved Skill.custody_owner ≠ tenant_context_id AND no edge → cross_tenant_boundary failure', async () => {
    __resetWorkflowRunSeqForTest()
    // The Skill (a leaf Workflow) has custody_owner=T-paisa.
    const skill = createWorkflow({
      id: 'W-cross-tenant-skill',
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
      custody_owner: 'T-paisa',
    })
    const engine = new SkillEngine()
    engine.register(skill)

    // Parent Workflow has no custody_owner declared (single-tenant base);
    // operates as T-asawa. The skill_ref step's resolved Skill.custody_owner
    // (T-paisa) is the cross-tenant target. NO delegates_to edge.
    const parent = createWorkflow({
      id: 'W-cross-tenant-parent-deny',
      preconditions: '',
      step_graph: [
        {
          step_id: 1,
          skill_ref: 'W-cross-tenant-skill',
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
    })

    const result = await executeStepGraph(parent, ALWAYS_OK_DISPATCH, {
      tenant_context_id: 'T-asawa',
      delegates_to_edges: [],
      skill_engine: engine,
    })

    expect(result.state).toBe('failed')
    expect(result.failure_reason).toContain('cross_tenant_boundary:T-asawa:T-paisa:')
    expect(result.failure_reason).toContain('invoke_skill:W-cross-tenant-skill')
  })

  it('skill_ref step WITH matching delegates_to edge → step succeeds + child_edge recorded', async () => {
    __resetWorkflowRunSeqForTest()
    const skill = createWorkflow({
      id: 'W-cross-tenant-skill-ok',
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
      custody_owner: 'T-paisa',
    })
    const engine = new SkillEngine()
    engine.register(skill)

    const parent = createWorkflow({
      id: 'W-cross-tenant-parent-allow',
      preconditions: '',
      step_graph: [
        {
          step_id: 1,
          skill_ref: 'W-cross-tenant-skill-ok',
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
    })

    const edges: ReadonlyArray<DelegatesToEdge> = [
      { kind: 'delegates_to', source: 'T-asawa', target: 'T-paisa' },
    ]
    // Skill leaf returns 7 (passes SCHEMA_INT).
    const dispatch: ActivityDispatcher = () => ({ kind: 'ok', outputs: [7] })

    const result = await executeStepGraph(parent, dispatch, {
      tenant_context_id: 'T-asawa',
      delegates_to_edges: edges,
      skill_engine: engine,
    })

    expect(result.state).toBe('success')
    expect(result.failure_reason).toBeNull()
    expect(result.completed_step_ids).toEqual([1])
    expect(result.child_edges).toBeDefined()
    expect(result.child_edges).toHaveLength(1)
    expect(result.child_edges![0]!.skill_ref).toBe('W-cross-tenant-skill-ok')
  })
})

describe('M9 Group FF — I-8 boundary invariant', () => {
  it('Workflow with no custody_owner → no cross-tenant op possible (gate is no-op)', async () => {
    // Single-tenant default at v1.0: workflow.custody_owner=null → no
    // effective tenant resolves → assertion never fires regardless of
    // tenant_context_id.
    __resetWorkflowRunSeqForTest()
    const wf = createWorkflow({
      id: 'W-no-custody',
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
    })
    const result = await executeStepGraph(wf, ALWAYS_OK_DISPATCH, {
      tenant_context_id: 'T-asawa',
      delegates_to_edges: [],
    })
    expect(result.state).toBe('success')
  })

  it('matching tenant on workflow → no cross-tenant op (gate no-ops)', async () => {
    __resetWorkflowRunSeqForTest()
    const wf = createWorkflow({
      id: 'W-same-tenant',
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
      custody_owner: 'T-asawa',
    })
    const result = await executeStepGraph(wf, ALWAYS_OK_DISPATCH, {
      tenant_context_id: 'T-asawa',
      delegates_to_edges: [],
    })
    expect(result.state).toBe('success')
  })

  it('runtime-derived gate cannot be bypassed by producer omission (no advisory hint)', async () => {
    // The contract is: there is NO `WorkflowStep.crosses_tenant?` field.
    // Producers cannot mark a step as "not cross-tenant" to skip
    // enforcement. The executor derives cross-tenant fact at runtime
    // by comparing tenant_context_id vs effective_tenant. This test
    // proves the gate fires when the operator misses the edge,
    // even on a "normal-looking" step without any annotation.
    __resetWorkflowRunSeqForTest()
    const wf = createWorkflow({
      id: 'W-no-bypass',
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
      delegates_to_edges: [], // operator forgot the edge
    })
    expect(result.state).toBe('failed')
    expect(result.failure_reason).toContain('cross_tenant_boundary')
  })
})
