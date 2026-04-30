/**
 * M12 Group YY (T-246). Hook tampering — runtime-enforced attack test.
 *
 * Vector: a Workflow with modifies_sutra=true attempts to modify Sutra
 * structural paths (hooks, plugin runtime) without a cleared reflexive_check
 * Constraint. L6 REFLEXIVITY law catches this pre-execution via
 * `l6Reflexivity.requiresApproval(...)` returning true (= gate fires; founder
 * or meta-charter approval required before dispatch).
 *
 * Mitigation under test:
 *  - L6 REFLEXIVITY law: modifies_sutra=true requires reflexive_check Constraint
 *    cleared before terminal_check passes
 *  - The attack is the absence of a reflexive_check Constraint OR an unsatisfied
 *    one (no founder_authorization, no meta_charter_approval)
 *  - The legitimate path needs reflexive_check Constraint + satisfaction set
 *
 * Spec source:
 *   - holding/plans/native-v1.0/M12-release-canary.md (T-246, A-3 attack class 2)
 *   - holding/research/2026-04-30-native-threat-model.md §2
 *   - sutra/marketplace/native/src/laws/l6-reflexivity.ts (the canonical anchor)
 */

import { describe, it, expect } from 'vitest'

import { createWorkflow } from '../../src/primitives/workflow.js'
import {
  l6Reflexivity,
  type ReflexiveSatisfactionMap,
} from '../../src/laws/l6-reflexivity.js'
import type { Constraint } from '../../src/types/index.js'

describe('M12 — Hook tampering (runtime-enforced)', () => {
  it('L6 REFLEXIVITY rejects modifies_sutra=true with NO reflexive_check Constraint', () => {
    const attacker_workflow = createWorkflow({
      id: 'W-attacker-hook-tamper',
      preconditions: '',
      step_graph: [
        { step_id: 1, action: 'wait', inputs: [], outputs: [], on_failure: 'abort' },
      ],
      inputs: [],
      outputs: [],
      state: [],
      postconditions: '',
      failure_policy: 'abort',
      stringency: 'process',
      interfaces_with: [],
      modifies_sutra: true, // ← ATTACK VECTOR
    })

    // Empty constraints array — attacker omits reflexive_check Constraint
    const constraints: Constraint[] = []

    // L6 fires: requiresApproval=true (gate is active; dispatch blocked)
    expect(l6Reflexivity.requiresApproval(attacker_workflow, constraints)).toBe(true)
  })

  it('L6 REFLEXIVITY rejects modifies_sutra=true with reflexive_check Constraint but NO satisfaction', () => {
    const attacker_workflow = createWorkflow({
      id: 'W-attacker-empty-satisfaction',
      preconditions: '',
      step_graph: [
        { step_id: 1, action: 'wait', inputs: [], outputs: [], on_failure: 'abort' },
      ],
      inputs: [],
      outputs: [],
      state: [],
      postconditions: '',
      failure_policy: 'abort',
      stringency: 'process',
      interfaces_with: [],
      modifies_sutra: true,
    })

    const constraints: Constraint[] = [
      {
        name: 'reflexive_check_for_hook_path',
        predicate: 'always_true',
        durability: 'durable',
        owner_scope: 'charter',
        type: 'reflexive_check',
      },
    ]
    // Satisfaction map empty → attacker tried to declare the constraint but
    // didn't get founder/meta-charter approval.
    const satisfaction: ReflexiveSatisfactionMap = {}

    expect(l6Reflexivity.requiresApproval(attacker_workflow, constraints, satisfaction)).toBe(true)
  })

  it('L6 REFLEXIVITY accepts modifies_sutra=true WITH reflexive_check + founder_authorization', () => {
    const legit_workflow = createWorkflow({
      id: 'W-legit-sutra-mod',
      preconditions: '',
      step_graph: [
        { step_id: 1, action: 'wait', inputs: [], outputs: [], on_failure: 'abort' },
      ],
      inputs: [],
      outputs: [],
      state: [],
      postconditions: '',
      failure_policy: 'abort',
      stringency: 'process',
      interfaces_with: [],
      modifies_sutra: true,
    })

    const constraints: Constraint[] = [
      {
        name: 'reflexive_check_for_hook_path',
        predicate: 'always_true',
        durability: 'durable',
        owner_scope: 'charter',
        type: 'reflexive_check',
      },
    ]
    // Founder approved this Workflow's reflexive_check Constraint.
    const satisfaction: ReflexiveSatisfactionMap = {
      reflexive_check_for_hook_path: {
        constraint_name: 'reflexive_check_for_hook_path',
        founder_authorization: true,
        meta_charter_approval: false,
      },
    }

    expect(l6Reflexivity.requiresApproval(legit_workflow, constraints, satisfaction)).toBe(false)
  })

  it('L6 REFLEXIVITY no-ops when modifies_sutra=false (defensive: never gates innocent workflows)', () => {
    const innocent_workflow = createWorkflow({
      id: 'W-innocent',
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
      modifies_sutra: false, // ← does NOT touch Sutra
    })

    expect(l6Reflexivity.requiresApproval(innocent_workflow, [])).toBe(false)
  })
})
