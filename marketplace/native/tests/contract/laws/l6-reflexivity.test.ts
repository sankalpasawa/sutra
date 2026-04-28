/**
 * L6 REFLEXIVITY — contract tests
 */
import { describe, it, expect } from 'vitest'
import { l6Reflexivity } from '../../../src/laws/l6-reflexivity.js'
import { createWorkflow } from '../../../src/primitives/workflow.js'
import type { Constraint } from '../../../src/types/index.js'

const baseW = (modifies: boolean) =>
  createWorkflow({
    id: 'W-x',
    preconditions: '',
    step_graph: [{ step_id: 0, action: 'wait', inputs: [], outputs: [], on_failure: 'abort' }],
    inputs: [],
    outputs: [],
    state: [],
    postconditions: '',
    failure_policy: '',
    stringency: 'task',
    interfaces_with: [],
    modifies_sutra: modifies,
  })

describe('L6 REFLEXIVITY — contract', () => {
  it('non-Sutra-modifying Workflow → requiresApproval=false (no constraints needed)', () => {
    const w = baseW(false)
    expect(l6Reflexivity.requiresApproval(w, [])).toBe(false)
  })

  it('Sutra-modifying Workflow + no reflexive_check Constraint → requiresApproval=true', () => {
    const w = baseW(true)
    expect(l6Reflexivity.requiresApproval(w, [])).toBe(true)
  })

  it('Sutra-modifying + reflexive_check Constraint w/ founder_authorization=true → requiresApproval=false', () => {
    const w = baseW(true)
    const c: Constraint = {
      name: 'sutra-mod-1',
      predicate: 'p',
      durability: 'durable',
      owner_scope: 'workflow',
      type: 'reflexive_check',
    }
    const result = l6Reflexivity.requiresApproval(w, [c], {
      'sutra-mod-1': {
        constraint_name: 'sutra-mod-1',
        founder_authorization: true,
        meta_charter_approval: false,
      },
    })
    expect(result).toBe(false)
  })

  it('Sutra-modifying + reflexive_check Constraint w/ both auth=false → requiresApproval=true', () => {
    const w = baseW(true)
    const c: Constraint = {
      name: 'sutra-mod-1',
      predicate: 'p',
      durability: 'durable',
      owner_scope: 'workflow',
      type: 'reflexive_check',
    }
    const result = l6Reflexivity.requiresApproval(w, [c], {
      'sutra-mod-1': {
        constraint_name: 'sutra-mod-1',
        founder_authorization: false,
        meta_charter_approval: false,
      },
    })
    expect(result).toBe(true)
  })

  it('reflexiveChecks() returns only reflexive_check Constraints', () => {
    const cs: Constraint[] = [
      { name: 'a', predicate: 'p', durability: 'durable', owner_scope: 'workflow', type: 'reflexive_check' },
      { name: 'b', predicate: 'p', durability: 'durable', owner_scope: 'workflow', type: 'predicate' },
      { name: 'c', predicate: 'p', durability: 'durable', owner_scope: 'workflow', type: 'invariant' },
    ]
    const out = l6Reflexivity.reflexiveChecks(cs)
    expect(out).toHaveLength(1)
    expect(out[0]?.name).toBe('a')
  })
})
