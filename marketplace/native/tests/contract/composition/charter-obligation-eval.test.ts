/**
 * M12 Group XX (T-243). Default Composition v1.0 — Workflow 2 contract test.
 *
 * Verifies charter-obligation-eval seed Workflow constructs + has policy_check
 * wired on the gated step (so the M7 policy_dispatcher fires when caller
 * supplies it at executeStepGraph time).
 */

import { describe, it, expect } from 'vitest'

import { buildCharterObligationEvalWorkflow } from '../../../composition/charter-obligation-eval.js'
import { isValidWorkflow } from '../../../src/primitives/workflow.js'
import {
  executeStepGraph,
  __resetWorkflowRunSeqForTest,
  type ActivityDispatcher,
} from '../../../src/engine/step-graph-executor.js'

describe('Default Composition v1.0 — charter-obligation-eval', () => {
  it('builds + validates with policy_check wired on gated step', () => {
    const { domain, charter, workflow } = buildCharterObligationEvalWorkflow({
      tenant_id: 'T-test',
      domain_id: 'D1.D8',
      obligation_predicate: 'approval_present == true',
    })
    expect(domain.id).toBe('D1.D8')
    expect(charter.id).toBe('C-obligation-gate')
    expect(charter.obligations).toHaveLength(1)
    expect(charter.obligations[0]?.predicate).toBe('approval_present == true')
    expect(workflow.id).toBe('W-charter-obligation-eval')
    expect(isValidWorkflow(workflow)).toBe(true)
    expect(workflow.step_graph).toHaveLength(1)
    expect(workflow.step_graph[0]?.policy_check).toBe(true)
  })

  it('runs through executeStepGraph; succeeds without policy_dispatcher (gate dormant)', async () => {
    __resetWorkflowRunSeqForTest()
    const { workflow } = buildCharterObligationEvalWorkflow({
      tenant_id: 'T-test',
      domain_id: 'D1.D8',
      obligation_predicate: 'always_true',
    })
    // No policy_dispatcher supplied → policy_check is dormant per M7 D-NS-19/22
    // (defensive default: gate fires only when BOTH dispatcher AND compiled
    // policy supplied). Step proceeds normally.
    const dispatch: ActivityDispatcher = () => ({ kind: 'ok', outputs: [{}] })
    const result = await executeStepGraph(workflow, dispatch)
    expect(result.state).toBe('success')
    expect(result.completed_step_ids).toEqual([1])
  })
})
