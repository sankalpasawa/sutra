/**
 * L1 DATA — property tests (V2 §3)
 */
import { describe, it } from 'vitest'
import * as fc from 'fast-check'
import { l1Data } from '../../src/laws/l1-data.js'
import { assetArb, dataRefNoAssetFieldsArb } from './arbitraries.js'

describe('L1 DATA — property tests', () => {
  it('forall DataRef without stable_identity / lifecycle_states: NOT promotable', () => {
    fc.assert(
      fc.property(dataRefNoAssetFieldsArb, (ref) => l1Data.shouldPromoteToAsset(ref) === false),
      { numRuns: 1000 },
    )
  })

  it('forall full Asset (stable_identity + lifecycle_states.length>1): promotable', () => {
    fc.assert(
      fc.property(assetArb, (asset) => l1Data.shouldPromoteToAsset(asset) === true),
      { numRuns: 1000 },
    )
  })

  it('forall asset-shaped record with empty stable_identity: NOT promotable', () => {
    fc.assert(
      fc.property(assetArb, (asset) => {
        const broken = { ...asset, stable_identity: '' }
        return l1Data.shouldPromoteToAsset(broken) === false
      }),
      { numRuns: 1000 },
    )
  })

  it('forall asset-shaped record with lifecycle_states.length<=1: NOT promotable', () => {
    fc.assert(
      fc.property(assetArb, fc.array(fc.string({ minLength: 1, maxLength: 8 }), { maxLength: 1 }), (asset, shortLs) => {
        const broken = { ...asset, lifecycle_states: shortLs }
        return l1Data.shouldPromoteToAsset(broken) === false
      }),
      { numRuns: 1000 },
    )
  })
})
