/**
 * L1 DATA — contract tests (deterministic edges)
 */
import { describe, it, expect } from 'vitest'
import { l1Data } from '../../../src/laws/l1-data.js'

describe('L1 DATA — contract', () => {
  it('plain DataRef without stable_identity → false', () => {
    expect(
      l1Data.shouldPromoteToAsset({
        kind: 'k',
        schema_ref: 's',
        locator: 'l',
        version: '',
        mutability: 'immutable',
        retention: '',
      }),
    ).toBe(false)
  })

  it('stable_identity present + lifecycle_states.length === 1 → false', () => {
    expect(
      l1Data.shouldPromoteToAsset({
        kind: 'k',
        schema_ref: 's',
        locator: 'l',
        version: '',
        mutability: 'immutable',
        retention: '',
        stable_identity: 'id-1',
        lifecycle_states: ['draft'],
      }),
    ).toBe(false)
  })

  it('empty stable_identity string → false', () => {
    expect(
      l1Data.shouldPromoteToAsset({
        kind: 'k',
        schema_ref: 's',
        locator: 'l',
        version: '',
        mutability: 'immutable',
        retention: '',
        stable_identity: '',
        lifecycle_states: ['a', 'b'],
      }),
    ).toBe(false)
  })

  it('full Asset (stable_identity + 2 lifecycle_states) → true', () => {
    expect(
      l1Data.shouldPromoteToAsset({
        kind: 'k',
        schema_ref: 's',
        locator: 'l',
        version: '',
        mutability: 'immutable',
        retention: '',
        stable_identity: 'id-1',
        lifecycle_states: ['draft', 'published'],
      }),
    ).toBe(true)
  })

  it('null / non-object input → false', () => {
    expect(l1Data.shouldPromoteToAsset(null)).toBe(false)
    expect(l1Data.shouldPromoteToAsset(undefined)).toBe(false)
    expect(l1Data.shouldPromoteToAsset(42)).toBe(false)
  })
})
