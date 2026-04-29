/**
 * DataRef.authoritative_status property tests — M4.6 (D2 §5).
 *
 * 1000+ cases per property: round-trip preservation + reject invalid value +
 * default fill.
 */

import { describe, expect, it } from 'vitest'
import * as fc from 'fast-check'
import {
  AUTHORITATIVE_STATUS_VALUES,
  AuthoritativeStatusSchema,
} from '../../src/types/authoritative-status.js'
import { DataRefSchema } from '../../src/types/index.js'

const PROP_RUNS = 1000

const validStatusArb = fc.constantFrom(...AUTHORITATIVE_STATUS_VALUES)

const dataRefSeedArb = fc.record({
  kind: fc.string({ minLength: 1, maxLength: 12 }),
  schema_ref: fc.string({ minLength: 1, maxLength: 24 }),
  locator: fc.string({ minLength: 1, maxLength: 24 }),
  version: fc.string({ maxLength: 6 }),
  mutability: fc.constantFrom('mutable', 'immutable') as fc.Arbitrary<
    'mutable' | 'immutable'
  >,
  retention: fc.string({ maxLength: 12 }),
})

describe('DataRef.authoritative_status property tests (M4.6)', () => {
  it('round-trip: explicit status survives parse + JSON cycle', () => {
    fc.assert(
      fc.property(dataRefSeedArb, validStatusArb, (seed, status) => {
        const r = DataRefSchema.parse({ ...seed, authoritative_status: status })
        expect(r.authoritative_status).toBe(status)
        const j = JSON.parse(JSON.stringify(r))
        expect(DataRefSchema.parse(j).authoritative_status).toBe(status)
      }),
      { numRuns: PROP_RUNS },
    )
  })

  it('default applied when authoritative_status omitted', () => {
    fc.assert(
      fc.property(dataRefSeedArb, (seed) => {
        const r = DataRefSchema.parse(seed)
        expect(r.authoritative_status).toBe('authoritative')
      }),
      { numRuns: PROP_RUNS },
    )
  })

  it('reject: any string outside the enum is rejected by schema', () => {
    const badStringArb = fc
      .string({ maxLength: 16 })
      .filter(
        (s) => !(AUTHORITATIVE_STATUS_VALUES as readonly string[]).includes(s),
      )
    fc.assert(
      fc.property(dataRefSeedArb, badStringArb, (seed, bad) => {
        expect(
          DataRefSchema.safeParse({
            ...seed,
            authoritative_status: bad,
          }).success,
        ).toBe(false)
      }),
      { numRuns: PROP_RUNS },
    )
  })

  it('AuthoritativeStatusSchema parses every enum value', () => {
    fc.assert(
      fc.property(validStatusArb, (status) => {
        expect(AuthoritativeStatusSchema.safeParse(status).success).toBe(true)
      }),
      { numRuns: PROP_RUNS },
    )
  })
})
