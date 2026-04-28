import { describe, it, expect } from 'vitest'
import {
  createExecution,
  isValidExecution,
  isValidStateTransition,
} from '../../src/primitives/execution.js'

describe('Execution primitive (V2 §1 P4 + V2.4 §A12 failure_reason)', () => {
  it('creates a root execution (parent_exec_id=null) in pending state', () => {
    const e = createExecution({
      id: 'E-001',
      workflow_id: 'W-root',
      trigger_event: 'evt-1',
      state: 'pending',
      logs: [],
      results: [],
      parent_exec_id: null,
      sibling_group: null,
      fingerprint: 'fp-abc',
    })
    expect(isValidExecution(e)).toBe(true)
    expect(e.parent_exec_id).toBeNull()
    expect(e.state).toBe('pending')
    expect(e.failure_reason).toBeNull()
  })

  it('creates a child execution with parent_exec_id set', () => {
    const e = createExecution({
      id: 'E-child',
      workflow_id: 'W-leaf',
      trigger_event: 'evt-spawn',
      state: 'running',
      logs: [{ ts: 1, msg: 'started' }],
      results: [],
      parent_exec_id: 'E-001',
      sibling_group: 'group-A',
      fingerprint: 'fp-child',
    })
    expect(e.parent_exec_id).toBe('E-001')
    expect(e.sibling_group).toBe('group-A')
  })

  it('rejects non-E-prefixed id', () => {
    expect(() =>
      createExecution({
        id: 'X-bad',
        workflow_id: 'W-x',
        trigger_event: 'evt',
        state: 'pending',
        logs: [],
        results: [],
        parent_exec_id: null,
        sibling_group: null,
        fingerprint: 'fp',
      }),
    ).toThrow(/Execution\.id/)
  })

  it('rejects non-W-prefixed workflow_id', () => {
    expect(() =>
      createExecution({
        id: 'E-x',
        workflow_id: 'not-a-workflow',
        trigger_event: 'evt',
        state: 'pending',
        logs: [],
        results: [],
        parent_exec_id: null,
        sibling_group: null,
        fingerprint: 'fp',
      }),
    ).toThrow(/workflow_id/)
  })

  it('rejects state=failed without failure_reason (V2.4 §A12 invariant)', () => {
    expect(() =>
      createExecution({
        id: 'E-fail',
        workflow_id: 'W-x',
        trigger_event: 'evt',
        state: 'failed',
        logs: [],
        results: [],
        parent_exec_id: null,
        sibling_group: null,
        fingerprint: 'fp',
        failure_reason: null,
      }),
    ).toThrow(/failure_reason/)
  })

  it('rejects state!=failed with failure_reason set (V2.4 §A12 invariant)', () => {
    expect(() =>
      createExecution({
        id: 'E-mismatch',
        workflow_id: 'W-x',
        trigger_event: 'evt',
        state: 'success',
        logs: [],
        results: [],
        parent_exec_id: null,
        sibling_group: null,
        fingerprint: 'fp',
        failure_reason: 'should not be here',
      }),
    ).toThrow(/failure_reason/)
  })

  it('accepts state=failed with terminal_check_failed:T<i> reason', () => {
    const e = createExecution({
      id: 'E-t1-fail',
      workflow_id: 'W-x',
      trigger_event: 'evt',
      state: 'failed',
      logs: [],
      results: [],
      parent_exec_id: null,
      sibling_group: null,
      fingerprint: 'fp',
      failure_reason: 'terminal_check_failed:T1',
    })
    expect(e.failure_reason).toBe('terminal_check_failed:T1')
  })

  it('rejects invalid state value', () => {
    expect(() =>
      createExecution({
        id: 'E-x',
        workflow_id: 'W-x',
        trigger_event: 'evt',
        // @ts-expect-error — runtime guard
        state: 'frozen',
        logs: [],
        results: [],
        parent_exec_id: null,
        sibling_group: null,
        fingerprint: 'fp',
      }),
    ).toThrow(/state/)
  })

  describe('state machine transitions', () => {
    it('allows pending → running', () => {
      expect(isValidStateTransition('pending', 'running')).toBe(true)
    })
    it('allows running → success', () => {
      expect(isValidStateTransition('running', 'success')).toBe(true)
    })
    it('allows running → failed', () => {
      expect(isValidStateTransition('running', 'failed')).toBe(true)
    })
    it('allows running → declared_gap', () => {
      expect(isValidStateTransition('running', 'declared_gap')).toBe(true)
    })
    it('allows running → escalated', () => {
      expect(isValidStateTransition('running', 'escalated')).toBe(true)
    })
    it('rejects pending → success (must go through running)', () => {
      expect(isValidStateTransition('pending', 'success')).toBe(false)
    })
    it('rejects success → running (terminal state immutable)', () => {
      expect(isValidStateTransition('success', 'running')).toBe(false)
    })
    it('rejects failed → success (terminal state immutable)', () => {
      expect(isValidStateTransition('failed', 'success')).toBe(false)
    })
  })

  it('returned Execution is frozen', () => {
    const e = createExecution({
      id: 'E-froz',
      workflow_id: 'W-x',
      trigger_event: 'evt',
      state: 'pending',
      logs: [],
      results: [],
      parent_exec_id: null,
      sibling_group: null,
      fingerprint: 'fp',
    })
    expect(Object.isFrozen(e)).toBe(true)
  })
})
