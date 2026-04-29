/**
 * CutoverContract property tests — M4.7 (D1 §11.1).
 *
 * 500+ fast-check cases per property per TASK-QUEUE.md §1 T-010:
 * - random cutover contracts round-trip via createCutoverContract → JSON → parse
 * - rollback_gate is non-empty when contract is set
 * - behavior_invariants is non-empty array of non-empty strings when set
 * - null is always accepted (no cutover required)
 */

import { describe, expect, it } from 'vitest'
import * as fc from 'fast-check'
import {
  CutoverContractSchema,
  createCutoverContract,
  isValidCutoverContract,
  type CutoverContract,
} from '../../src/schemas/cutover-contract.js'

const PROP_RUNS = 500

const nonEmptyStringArb = fc.string({ minLength: 1, maxLength: 32 })

const fullCutoverArb: fc.Arbitrary<NonNullable<CutoverContract>> = fc.record({
  source_engine: nonEmptyStringArb,
  target_engine: nonEmptyStringArb,
  behavior_invariants: fc.array(nonEmptyStringArb, {
    minLength: 1,
    maxLength: 5,
  }),
  rollback_gate: nonEmptyStringArb,
  canary_window: nonEmptyStringArb,
})

const cutoverOrNullArb: fc.Arbitrary<CutoverContract> = fc.oneof(
  fullCutoverArb,
  fc.constant(null),
)

describe('CutoverContract property tests (M4.7)', () => {
  it('round-trip: createCutoverContract → JSON → parse equals original (≥500 cases)', () => {
    fc.assert(
      fc.property(cutoverOrNullArb, (cc) => {
        const v = createCutoverContract(cc)
        const parsed = CutoverContractSchema.parse(
          JSON.parse(JSON.stringify(v)),
        )
        expect(parsed).toEqual(v)
      }),
      { numRuns: PROP_RUNS },
    )
  })

  it('isValidCutoverContract true for every accepted record (≥500 cases)', () => {
    fc.assert(
      fc.property(cutoverOrNullArb, (cc) => {
        const v = createCutoverContract(cc)
        expect(isValidCutoverContract(v)).toBe(true)
      }),
      { numRuns: PROP_RUNS },
    )
  })

  it('rollback_gate non-empty whenever contract is set (≥500 cases)', () => {
    fc.assert(
      fc.property(fullCutoverArb, (cc) => {
        const v = createCutoverContract(cc)
        expect(v).not.toBeNull()
        expect(v?.rollback_gate.length).toBeGreaterThan(0)
      }),
      { numRuns: PROP_RUNS },
    )
  })

  it('behavior_invariants ≥1 element, all non-empty when contract is set (≥500 cases)', () => {
    fc.assert(
      fc.property(fullCutoverArb, (cc) => {
        const v = createCutoverContract(cc)
        expect(v).not.toBeNull()
        expect(v?.behavior_invariants.length).toBeGreaterThan(0)
        for (const inv of v?.behavior_invariants ?? []) {
          expect(inv.length).toBeGreaterThan(0)
        }
      }),
      { numRuns: PROP_RUNS },
    )
  })

  it('empty behavior_invariants always rejected when contract set (≥500 cases)', () => {
    fc.assert(
      fc.property(fullCutoverArb, (cc) => {
        expect(() =>
          createCutoverContract({ ...cc, behavior_invariants: [] }),
        ).toThrow()
      }),
      { numRuns: PROP_RUNS },
    )
  })

  it('any required string emptied → reject (≥500 cases per field)', () => {
    const fieldArb = fc.constantFrom(
      'source_engine',
      'target_engine',
      'rollback_gate',
      'canary_window',
    ) as fc.Arbitrary<
      'source_engine' | 'target_engine' | 'rollback_gate' | 'canary_window'
    >
    fc.assert(
      fc.property(fullCutoverArb, fieldArb, (cc, field) => {
        const broken = { ...cc, [field]: '' }
        expect(() => createCutoverContract(broken)).toThrow()
      }),
      { numRuns: PROP_RUNS },
    )
  })

  it('null always accepted as the no-cutover state (≥500 cases)', () => {
    fc.assert(
      fc.property(fc.constant(null), (n) => {
        const v = createCutoverContract(n)
        expect(v).toBeNull()
        expect(isValidCutoverContract(v)).toBe(true)
      }),
      { numRuns: PROP_RUNS },
    )
  })
})
