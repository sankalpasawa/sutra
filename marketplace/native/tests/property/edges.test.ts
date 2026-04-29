/**
 * Edge types property tests — M4.8 (Group C; T-019).
 *
 * Each property runs ≥1000 fast-check cases per M4 plan A-2 / queue T-019.
 *
 * Coverage:
 *   - random valid OwnsEdge        validates
 *   - random valid DelegatesToEdge validates
 *   - random valid EmitsEdge       validates
 *   - random invalid `kind` values rejected by the discriminated union
 */

import { describe, expect, it } from 'vitest'
import * as fc from 'fast-check'
import {
  DelegatesToEdgeSchema,
  EdgeSchema,
  EmitsEdgeSchema,
  OwnsEdgeSchema,
  isValidEdge,
} from '../../src/types/edges.js'

const PROP_RUNS = 1000

// ---- arbitraries -----------------------------------------------------------

const tenantIdArb = fc
  .string({ minLength: 1, maxLength: 24 })
  .filter((s) => /^[a-z0-9-]+$/.test(s))
  .map((s) => `T-${s}`)

const domainIdArb = fc
  .array(fc.integer({ min: 0, max: 999 }), { minLength: 1, maxLength: 4 })
  .map((nums) => nums.map((n) => `D${n}`).join('.'))

// Workflow.id W-<.+> — generate non-empty body of mostly-safe chars
const workflowIdArb = fc
  .string({ minLength: 1, maxLength: 16 })
  .filter((s) => s.length >= 1)
  .map((s) => `W-${s}`)

const executionIdArb = fc
  .string({ minLength: 1, maxLength: 16 })
  .filter((s) => s.length >= 1)
  .map((s) => `E-${s}`)

// Hook ids are free-form (no canonical pattern in v1.0); just non-empty.
const hookIdArb = fc.string({ minLength: 1, maxLength: 24 })

// EmitsEdge source can be any of W- / E- / hook
const emitsSourceArb = fc.oneof(workflowIdArb, executionIdArb, hookIdArb)

// DecisionProvenance.id `dp-<lowercase-hex>`
const dpIdArb = fc
  .string({ minLength: 1, maxLength: 32 })
  .filter((s) => /^[a-f0-9]+$/.test(s))
  .map((s) => `dp-${s}`)

const ownsEdgeArb = fc.record({
  kind: fc.constant('owns' as const),
  source: tenantIdArb,
  target: domainIdArb,
})

const delegatesToEdgeArb = fc.record({
  kind: fc.constant('delegates_to' as const),
  source: tenantIdArb,
  target: tenantIdArb,
})

const emitsEdgeArb = fc.record({
  kind: fc.constant('emits' as const),
  source: emitsSourceArb,
  target: dpIdArb,
})

// ---- properties ------------------------------------------------------------

describe('OwnsEdge property tests (M4.8 T-019)', () => {
  it('every random valid OwnsEdge round-trips through OwnsEdgeSchema', () => {
    fc.assert(
      fc.property(ownsEdgeArb, (e) => {
        const parsed = OwnsEdgeSchema.parse(e)
        expect(parsed).toEqual(e)
        expect(isValidEdge(parsed)).toBe(true)
      }),
      { numRuns: PROP_RUNS },
    )
  })

  it('every random valid OwnsEdge round-trips through EdgeSchema (union)', () => {
    fc.assert(
      fc.property(ownsEdgeArb, (e) => {
        expect(EdgeSchema.parse(e)).toEqual(e)
      }),
      { numRuns: PROP_RUNS },
    )
  })
})

describe('DelegatesToEdge property tests (M4.8 T-019)', () => {
  it('every random valid DelegatesToEdge round-trips', () => {
    fc.assert(
      fc.property(delegatesToEdgeArb, (e) => {
        const parsed = DelegatesToEdgeSchema.parse(e)
        expect(parsed).toEqual(e)
        expect(EdgeSchema.parse(e)).toEqual(e)
      }),
      { numRuns: PROP_RUNS },
    )
  })
})

describe('EmitsEdge property tests (M4.8 T-019)', () => {
  it('every random valid EmitsEdge round-trips', () => {
    fc.assert(
      fc.property(emitsEdgeArb, (e) => {
        const parsed = EmitsEdgeSchema.parse(e)
        expect(parsed).toEqual(e)
        expect(EdgeSchema.parse(e)).toEqual(e)
      }),
      { numRuns: PROP_RUNS },
    )
  })
})

describe('Invalid `kind` values rejected — discriminated union (M4.8 T-019)', () => {
  it('every random non-{owns,delegates_to,emits} kind is rejected', () => {
    const KNOWN = new Set(['owns', 'delegates_to', 'emits'])
    const badKindArb = fc.string({ minLength: 1, maxLength: 16 }).filter((s) => !KNOWN.has(s))
    const badEdgeArb = fc.record({
      kind: badKindArb,
      source: fc.string({ minLength: 1, maxLength: 16 }),
      target: fc.string({ minLength: 1, maxLength: 16 }),
    })
    fc.assert(
      fc.property(badEdgeArb, (e) => {
        expect(EdgeSchema.safeParse(e).success).toBe(false)
        expect(isValidEdge(e)).toBe(false)
      }),
      { numRuns: PROP_RUNS },
    )
  })
})
