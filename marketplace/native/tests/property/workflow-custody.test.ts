/**
 * Workflow.custody_owner property tests — M4.4 (D-NS-11 default c).
 *
 * 1000+ cases per property: round-trip preservation + reject malformed.
 */

import { describe, expect, it } from 'vitest'
import * as fc from 'fast-check'
import { createWorkflow, isValidWorkflow } from '../../src/primitives/workflow.js'
import { workflowArb } from './arbitraries.js'

const PROP_RUNS = 1000

const tenantIdArb = fc
  .string({ minLength: 1, maxLength: 24 })
  .filter((s) => /^[a-z0-9-]+$/.test(s))
  .map((s) => `T-${s}`)

const custodyOwnerArb: fc.Arbitrary<string | null> = fc.option(tenantIdArb, {
  nil: null,
})

describe('Workflow.custody_owner property tests (M4.4)', () => {
  it('round-trip: any valid custody_owner survives createWorkflow + isValidWorkflow', () => {
    fc.assert(
      fc.property(workflowArb(), custodyOwnerArb, (wf, owner) => {
        const w = createWorkflow({ ...wf, custody_owner: owner })
        expect(w.custody_owner).toEqual(owner)
        expect(isValidWorkflow(w)).toBe(true)
      }),
      { numRuns: PROP_RUNS },
    )
  })

  it('reject: any non-null string that fails T- pattern is rejected', () => {
    const badArb = fc
      .oneof(
        fc.string({ maxLength: 8 }),
        fc.constant('T-'),
        fc.constant(''),
        fc.constant('T-UPPER'),
        fc.constant('asawa-holding'),
      )
      .filter((s) => !/^T-[a-z0-9-]+$/.test(s))
    fc.assert(
      fc.property(workflowArb(), badArb, (wf, bad) => {
        expect(() =>
          createWorkflow({ ...wf, custody_owner: bad as string }),
        ).toThrow()
      }),
      { numRuns: PROP_RUNS },
    )
  })
})
