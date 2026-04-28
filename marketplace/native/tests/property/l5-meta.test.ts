/**
 * L5 META — property tests (V2 §3)
 */
import { describe, it } from 'vitest'
import * as fc from 'fast-check'
import { l5Meta, type PrimitiveKind, type EdgeKind, type TypedEdgeKind } from '../../src/laws/l5-meta.js'

const KIND_ARB: fc.Arbitrary<PrimitiveKind> = fc.constantFrom<PrimitiveKind>(
  'domain',
  'charter',
  'workflow',
  'execution',
)

const TYPED_ARB: fc.Arbitrary<TypedEdgeKind> = fc.constantFrom<TypedEdgeKind>(
  'operationalizes',
  'decomposes_into',
  'depends_on',
  'produces',
  'consumes',
  'activates',
  'interfaces_with',
  'propagates_to',
)

describe('L5 META — property tests', () => {
  it('forall (parent, child) pairs: containment valid iff (domain, charter)', () => {
    fc.assert(
      fc.property(KIND_ARB, KIND_ARB, (parent, child) => {
        const expected = parent === 'domain' && child === 'charter'
        return l5Meta.isValidContainment(parent, child) === expected
      }),
      { numRuns: 1000 },
    )
  })

  it('forall typed edges: isValidEdge returns true regardless of (parent, child)', () => {
    fc.assert(
      fc.property(TYPED_ARB, KIND_ARB, KIND_ARB, (kind, parent, child) =>
        l5Meta.isValidEdge(kind as EdgeKind, parent, child) === true,
      ),
      { numRuns: 1000 },
    )
  })

  it('forall non-(domain,charter) pairs with kind=contains: isValidEdge returns false', () => {
    fc.assert(
      fc.property(KIND_ARB, KIND_ARB, (parent, child) => {
        if (parent === 'domain' && child === 'charter') return true
        return l5Meta.isValidEdge('contains' as EdgeKind, parent, child) === false
      }),
      { numRuns: 1000 },
    )
  })
})
