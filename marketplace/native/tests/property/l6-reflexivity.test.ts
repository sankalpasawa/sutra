/**
 * L6 REFLEXIVITY — property tests (V2.1 §A6)
 */
import { describe, it } from 'vitest'
import * as fc from 'fast-check'
import { l6Reflexivity, type ReflexiveSatisfactionMap } from '../../src/laws/l6-reflexivity.js'
import { workflowArb, constraintArb } from './arbitraries.js'
import type { Constraint } from '../../src/types/index.js'

describe('L6 REFLEXIVITY — property tests', () => {
  it('forall workflow with modifies_sutra=false: requiresApproval=false (regardless of constraints)', () => {
    fc.assert(
      fc.property(
        workflowArb({ modifies_sutra: false }),
        fc.array(constraintArb(), { maxLength: 3 }),
        (w, constraints) => l6Reflexivity.requiresApproval(w, constraints) === false,
      ),
      { numRuns: 1000 },
    )
  })

  it('forall workflow with modifies_sutra=true + no reflexive_check Constraint: requiresApproval=true', () => {
    fc.assert(
      fc.property(
        workflowArb({ modifies_sutra: true }),
        fc.array(
          constraintArb({ forceType: 'predicate' }),
          { maxLength: 3 },
        ),
        (w, constraints) => l6Reflexivity.requiresApproval(w, constraints) === true,
      ),
      { numRuns: 1000 },
    )
  })

  it('forall workflow modifies_sutra=true + reflexive_check w/ founder_authorization=true: requiresApproval=false', () => {
    fc.assert(
      fc.property(workflowArb({ modifies_sutra: true }), constraintArb({ forceType: 'reflexive_check' }), (w, c) => {
        const constraints: Constraint[] = [c]
        const sat: ReflexiveSatisfactionMap = {
          [c.name]: {
            constraint_name: c.name,
            founder_authorization: true,
            meta_charter_approval: false,
          },
        }
        return l6Reflexivity.requiresApproval(w, constraints, sat) === false
      }),
      { numRuns: 1000 },
    )
  })

  it('forall workflow modifies_sutra=true + reflexive_check w/ both auth=false: requiresApproval=true', () => {
    fc.assert(
      fc.property(workflowArb({ modifies_sutra: true }), constraintArb({ forceType: 'reflexive_check' }), (w, c) => {
        const constraints: Constraint[] = [c]
        const sat: ReflexiveSatisfactionMap = {
          [c.name]: {
            constraint_name: c.name,
            founder_authorization: false,
            meta_charter_approval: false,
          },
        }
        return l6Reflexivity.requiresApproval(w, constraints, sat) === true
      }),
      { numRuns: 1000 },
    )
  })

  it('forall workflow modifies_sutra=true + reflexive_check w/ meta_charter_approval=true: requiresApproval=false', () => {
    fc.assert(
      fc.property(workflowArb({ modifies_sutra: true }), constraintArb({ forceType: 'reflexive_check' }), (w, c) => {
        const constraints: Constraint[] = [c]
        const sat: ReflexiveSatisfactionMap = {
          [c.name]: {
            constraint_name: c.name,
            founder_authorization: false,
            meta_charter_approval: true,
          },
        }
        return l6Reflexivity.requiresApproval(w, constraints, sat) === false
      }),
      { numRuns: 1000 },
    )
  })
})
