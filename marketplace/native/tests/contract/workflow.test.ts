import { describe, it, expect } from 'vitest'
import { createWorkflow, isValidWorkflow } from '../../src/primitives/workflow.js'
import type { DataRef, WorkflowStep } from '../../src/types/index.js'

const dr = (kind: string): DataRef => ({
  kind,
  schema_ref: 'schema://x',
  locator: 'mem://x',
  version: 'v1',
  mutability: 'immutable',
  retention: '7d',
})

describe('Workflow primitive (V2 §1 P3 + V2.1 §A4 + V2.2 §A10 + V2.3 §A11 + V2.4 §A12)', () => {
  it('creates a minimal workflow with default flag values', () => {
    const w = createWorkflow({
      id: 'W-min',
      preconditions: 'true',
      step_graph: [
        {
          step_id: 1,
          skill_ref: 'noop',
          inputs: [],
          outputs: [],
          on_failure: 'abort',
        },
      ],
      inputs: [],
      outputs: [],
      state: [],
      postconditions: 'true',
      failure_policy: 'abort',
      stringency: 'task',
      interfaces_with: [],
    })
    expect(isValidWorkflow(w)).toBe(true)
    // V2.3 §A11 default
    expect(w.reuse_tag).toBe(false)
    // V2.4 §A12 default
    expect(w.modifies_sutra).toBe(false)
    // V2.2 §A10 default
    expect(w.on_override_action).toBe('escalate')
    // V2.1 §A4 default
    expect(w.expects_response_from).toBeNull()
    // V2.3 §A11 — return_contract optional (defaults to null)
    expect(w.return_contract).toBeNull()
  })

  it('creates a Skill (Workflow with reuse_tag=true) per V2.3 §A11', () => {
    const skill = createWorkflow({
      id: 'W-skill',
      preconditions: 'always',
      step_graph: [
        { step_id: 1, action: 'terminate', inputs: [], outputs: [], on_failure: 'escalate' },
      ],
      inputs: [],
      outputs: [],
      state: [],
      postconditions: 'true',
      failure_policy: 'escalate',
      stringency: 'task',
      interfaces_with: [],
      reuse_tag: true,
      return_contract: 'schema://skill-result',
    })
    expect(skill.reuse_tag).toBe(true)
    expect(skill.return_contract).toBe('schema://skill-result')
  })

  it('rejects step with BOTH skill_ref and action (XOR violation)', () => {
    expect(() =>
      createWorkflow({
        id: 'W-bad',
        preconditions: 'true',
        step_graph: [
          {
            step_id: 1,
            skill_ref: 'foo',
            action: 'wait',
            inputs: [],
            outputs: [],
            on_failure: 'abort',
          } as WorkflowStep,
        ],
        inputs: [],
        outputs: [],
        state: [],
        postconditions: 'true',
        failure_policy: 'abort',
        stringency: 'task',
        interfaces_with: [],
      }),
    ).toThrow(/skill_ref XOR action|mutually exclusive/i)
  })

  it('rejects step with NEITHER skill_ref nor action (L2 BOUNDARY violation)', () => {
    expect(() =>
      createWorkflow({
        id: 'W-empty-step',
        preconditions: 'true',
        step_graph: [
          {
            step_id: 1,
            inputs: [],
            outputs: [],
            on_failure: 'abort',
          } as WorkflowStep,
        ],
        inputs: [],
        outputs: [],
        state: [],
        postconditions: 'true',
        failure_policy: 'abort',
        stringency: 'task',
        interfaces_with: [],
      }),
    ).toThrow(/skill_ref XOR action|must specify/i)
  })

  it('rejects empty step_graph (workflow must do something)', () => {
    expect(() =>
      createWorkflow({
        id: 'W-empty',
        preconditions: 'true',
        step_graph: [],
        inputs: [],
        outputs: [],
        state: [],
        postconditions: 'true',
        failure_policy: 'abort',
        stringency: 'task',
        interfaces_with: [],
      }),
    ).toThrow(/step_graph/)
  })

  it('rejects non-W-prefixed id', () => {
    expect(() =>
      createWorkflow({
        id: 'X-nope',
        preconditions: 'true',
        step_graph: [{ step_id: 1, action: 'terminate', inputs: [], outputs: [], on_failure: 'abort' }],
        inputs: [],
        outputs: [],
        state: [],
        postconditions: 'true',
        failure_policy: 'abort',
        stringency: 'task',
        interfaces_with: [],
      }),
    ).toThrow(/Workflow\.id/)
  })

  it('accepts all stringency values', () => {
    for (const s of ['task', 'process', 'protocol'] as const) {
      const w = createWorkflow({
        id: `W-${s}`,
        preconditions: 'true',
        step_graph: [{ step_id: 1, action: 'terminate', inputs: [], outputs: [], on_failure: 'abort' }],
        inputs: [],
        outputs: [],
        state: [],
        postconditions: 'true',
        failure_policy: 'abort',
        stringency: s,
        interfaces_with: [],
      })
      expect(w.stringency).toBe(s)
    }
  })

  it('accepts all on_override_action values per V2.2 §A10', () => {
    for (const action of ['pause', 'splice', 'restart', 'escalate'] as const) {
      const w = createWorkflow({
        id: `W-${action}`,
        preconditions: 'true',
        step_graph: [{ step_id: 1, action: 'terminate', inputs: [], outputs: [], on_failure: 'abort' }],
        inputs: [],
        outputs: [],
        state: [],
        postconditions: 'true',
        failure_policy: 'abort',
        stringency: 'task',
        interfaces_with: [],
        on_override_action: action,
      })
      expect(w.on_override_action).toBe(action)
    }
  })

  it('rejects invalid stringency value', () => {
    expect(() =>
      createWorkflow({
        id: 'W-bad-string',
        preconditions: 'true',
        step_graph: [{ step_id: 1, action: 'terminate', inputs: [], outputs: [], on_failure: 'abort' }],
        inputs: [],
        outputs: [],
        state: [],
        postconditions: 'true',
        failure_policy: 'abort',
        // @ts-expect-error — runtime guard
        stringency: 'optional',
        interfaces_with: [],
      }),
    ).toThrow(/stringency/)
  })

  it('preserves DataRef arrays in inputs/outputs/state', () => {
    const w = createWorkflow({
      id: 'W-data',
      preconditions: 'true',
      step_graph: [
        { step_id: 1, skill_ref: 'consume', inputs: [dr('in')], outputs: [dr('out')], on_failure: 'abort' },
      ],
      inputs: [dr('w-in')],
      outputs: [dr('w-out')],
      state: [dr('w-state')],
      postconditions: 'true',
      failure_policy: 'abort',
      stringency: 'task',
      interfaces_with: [],
    })
    expect(w.inputs).toHaveLength(1)
    expect(w.outputs).toHaveLength(1)
    expect(w.state).toHaveLength(1)
    expect(w.inputs[0]?.kind).toBe('w-in')
  })

  it('returned Workflow is frozen', () => {
    const w = createWorkflow({
      id: 'W-froz',
      preconditions: 'true',
      step_graph: [{ step_id: 1, action: 'terminate', inputs: [], outputs: [], on_failure: 'abort' }],
      inputs: [],
      outputs: [],
      state: [],
      postconditions: 'true',
      failure_policy: 'abort',
      stringency: 'task',
      interfaces_with: [],
    })
    expect(Object.isFrozen(w)).toBe(true)
  })
})
