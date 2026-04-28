/**
 * L2 BOUNDARY — property tests (V2 §3)
 */
import { describe, it } from 'vitest'
import * as fc from 'fast-check'
import { l2Boundary } from '../../src/laws/l2-boundary.js'
import { interfaceArb } from './arbitraries.js'

describe('L2 BOUNDARY — property tests', () => {
  it('forall Interface with empty contract_schema: invalid', () => {
    fc.assert(
      fc.property(interfaceArb({ contract_schema: fc.constant('') }), (iface) =>
        l2Boundary.isValid(iface) === false,
      ),
      { numRuns: 1000 },
    )
  })

  it('forall Interface with valid JSON-object contract_schema: valid', () => {
    // Generate a JSON-object string (always parses + is an object).
    const jsonObjectArb = fc
      .dictionary(fc.string({ minLength: 1, maxLength: 6 }), fc.constantFrom(1, 'x', true))
      .map((o) => JSON.stringify(o))
    fc.assert(
      fc.property(interfaceArb({ contract_schema: jsonObjectArb }), (iface) =>
        l2Boundary.isValid(iface) === true,
      ),
      { numRuns: 1000 },
    )
  })

  it('forall Interface with non-JSON contract_schema string: invalid', () => {
    // Non-JSON: any string that does not start with [, {, ", t, f, n, or a digit/minus.
    const nonJsonArb = fc
      .string({ minLength: 1, maxLength: 16 })
      .filter((s) => {
        const trimmed = s.trimStart()
        if (trimmed.length === 0) return true
        const c = trimmed[0]!
        return !'[{"tfn-0123456789'.includes(c)
      })
    fc.assert(
      fc.property(interfaceArb({ contract_schema: nonJsonArb }), (iface) =>
        l2Boundary.isValid(iface) === false,
      ),
      { numRuns: 1000 },
    )
  })

  it('forall Interface with JSON-string-root contract_schema: invalid (per L2 v1.0)', () => {
    fc.assert(
      fc.property(
        interfaceArb({ contract_schema: fc.string({ maxLength: 8 }).map((s) => JSON.stringify(s)) }),
        (iface) => l2Boundary.isValid(iface) === false,
      ),
      { numRuns: 1000 },
    )
  })

  // ---------------------------------------------------------------------------
  // Codex M3 P1 #1 (2026-04-28) — array roots are not valid schema documents.
  // ---------------------------------------------------------------------------

  it('P1.1: forall Interface with JSON-array-root contract_schema: invalid', () => {
    const arrayRootArb = fc
      .array(fc.oneof(fc.integer(), fc.string({ maxLength: 6 }), fc.boolean()), { maxLength: 5 })
      .map((arr) => JSON.stringify(arr))
    fc.assert(
      fc.property(interfaceArb({ contract_schema: arrayRootArb }), (iface) =>
        l2Boundary.isValid(iface) === false,
      ),
      { numRuns: 1000 },
    )
  })

  it('P1.1: forall Interface with JSON-boolean-root contract_schema: invalid (M3 conservative)', () => {
    const boolRootArb = fc.boolean().map((b) => JSON.stringify(b))
    fc.assert(
      fc.property(interfaceArb({ contract_schema: boolRootArb }), (iface) =>
        l2Boundary.isValid(iface) === false,
      ),
      { numRuns: 1000 },
    )
  })

  it('P1.1: forall Interface with JSON-null-root contract_schema: invalid', () => {
    fc.assert(
      fc.property(interfaceArb({ contract_schema: fc.constant('null') }), (iface) =>
        l2Boundary.isValid(iface) === false,
      ),
      { numRuns: 200 },
    )
  })
})
