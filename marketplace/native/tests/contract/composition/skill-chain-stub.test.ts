/**
 * M12 Group XX (T-243). Default Composition v1.0 — Workflow 3 contract test.
 *
 * Verifies skill-chain-stub seed Workflow constructs + chains 2 stub Skills
 * via the M6 SkillEngine resolve path.
 */

import { describe, it, expect } from 'vitest'

import { buildSkillChainStubWorkflow } from '../../../composition/skill-chain-stub.js'
import { isValidWorkflow } from '../../../src/primitives/workflow.js'
import {
  executeStepGraph,
  __resetWorkflowRunSeqForTest,
  type ActivityDispatcher,
} from '../../../src/engine/step-graph-executor.js'

describe('Default Composition v1.0 — skill-chain-stub', () => {
  it('builds + registers 2 stub Skills + validates Workflow', () => {
    const { domain, charter, workflow, skill_engine } = buildSkillChainStubWorkflow({
      tenant_id: 'T-test',
      domain_id: 'D1.D7',
    })
    expect(domain.id).toBe('D1.D7')
    expect(charter.id).toBe('C-skill-chain')
    expect(workflow.id).toBe('W-skill-chain-stub')
    expect(isValidWorkflow(workflow)).toBe(true)
    expect(workflow.step_graph).toHaveLength(2)
    expect(workflow.step_graph[0]?.skill_ref).toBe('W-stub-skill-a')
    expect(workflow.step_graph[1]?.skill_ref).toBe('W-stub-skill-b')
    // Verify both stub Skills are resolvable on the engine
    expect(skill_engine.resolve('W-stub-skill-a')).not.toBeNull()
    expect(skill_engine.resolve('W-stub-skill-b')).not.toBeNull()
  })

  it('runs through executeStepGraph; chains both Skills to terminal_state=success', async () => {
    __resetWorkflowRunSeqForTest()
    const { workflow, skill_engine } = buildSkillChainStubWorkflow({
      tenant_id: 'T-test',
      domain_id: 'D1.D7',
    })
    const dispatch: ActivityDispatcher = () => ({ kind: 'ok', outputs: [{}] })
    const result = await executeStepGraph(workflow, dispatch, { skill_engine })
    expect(result.state).toBe('success')
    expect(result.completed_step_ids).toEqual([1, 2])
    expect(result.child_edges).toBeDefined()
    expect(result.child_edges).toHaveLength(2)
  })
})
