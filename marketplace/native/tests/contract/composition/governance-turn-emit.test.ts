/**
 * M12 Group XX (T-243). Default Composition v1.0 — Workflow 1 contract test.
 *
 * Verifies governance-turn-emit seed Workflow constructs + validates against
 * M2 primitives + M3 laws, and runs through executeStepGraph to terminal_state.
 */

import { describe, it, expect } from 'vitest'

import { buildGovernanceTurnEmitWorkflow } from '../../../composition/governance-turn-emit.js'
import { isValidWorkflow } from '../../../src/primitives/workflow.js'
import {
  executeStepGraph,
  __resetWorkflowRunSeqForTest,
  type ActivityDispatcher,
} from '../../../src/engine/step-graph-executor.js'

describe('Default Composition v1.0 — governance-turn-emit', () => {
  it('builds + validates against M2 primitives', () => {
    const { domain, charter, workflow } = buildGovernanceTurnEmitWorkflow({
      tenant_id: 'T-test',
      domain_id: 'D1.D9',
    })
    expect(domain.id).toBe('D1.D9')
    expect(domain.tenant_id).toBe('T-test')
    expect(charter.id).toBe('C-governance-turn')
    expect(charter.obligations).toHaveLength(1)
    expect(workflow.id).toBe('W-governance-turn-emit')
    expect(isValidWorkflow(workflow)).toBe(true)
    expect(workflow.step_graph).toHaveLength(2)
  })

  it('runs through executeStepGraph to terminal_state=success', async () => {
    __resetWorkflowRunSeqForTest()
    const { workflow } = buildGovernanceTurnEmitWorkflow({
      tenant_id: 'T-test',
      domain_id: 'D1.D9',
    })
    const dispatch: ActivityDispatcher = () => ({ kind: 'ok', outputs: [{}] })
    const result = await executeStepGraph(workflow, dispatch)
    expect(result.state).toBe('success')
    expect(result.completed_step_ids).toEqual([1, 2])
  })

  it('accepts custom charter_id', () => {
    const { charter } = buildGovernanceTurnEmitWorkflow({
      tenant_id: 'T-x',
      domain_id: 'D2',
      charter_id: 'C-custom',
    })
    expect(charter.id).toBe('C-custom')
  })
})
