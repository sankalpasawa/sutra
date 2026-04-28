/**
 * L3 ACTIVATION — property tests (V2 §3)
 */
import { describe, it } from 'vitest'
import * as fc from 'fast-check'
import { l3Activation } from '../../src/laws/l3-activation.js'
import { triggerPairArb } from './arbitraries.js'

describe('L3 ACTIVATION — property tests', () => {
  it('forall (spec, event) with schemaMatch=true AND routeMatch=true: activates', () => {
    fc.assert(
      fc.property(
        triggerPairArb.filter(({ schemaMatch, routeMatch }) => schemaMatch && routeMatch),
        ({ spec, event }) => l3Activation.shouldActivate(event, spec) === true,
      ),
      { numRuns: 1000 },
    )
  })

  it('forall (spec, event) with schemaMatch=false: does NOT activate', () => {
    fc.assert(
      fc.property(
        triggerPairArb.filter(({ schemaMatch }) => !schemaMatch),
        ({ spec, event }) => l3Activation.shouldActivate(event, spec) === false,
      ),
      { numRuns: 1000 },
    )
  })

  it('forall (spec, event) with routeMatch=false: does NOT activate', () => {
    fc.assert(
      fc.property(
        triggerPairArb.filter(({ routeMatch }) => !routeMatch),
        ({ spec, event }) => l3Activation.shouldActivate(event, spec) === false,
      ),
      { numRuns: 1000 },
    )
  })

  it('forall (spec, event) with mismatched spec_id: does NOT activate', () => {
    fc.assert(
      fc.property(triggerPairArb, fc.string({ minLength: 1, maxLength: 8 }), ({ spec, event }, otherId) => {
        if (otherId === spec.id) return true // skip — not a mismatch
        const wrongEvent = { ...event, spec_id: otherId }
        return l3Activation.shouldActivate(wrongEvent, spec) === false
      }),
      { numRuns: 1000 },
    )
  })
})
