/**
 * L3 ACTIVATION — contract tests
 */
import { describe, it, expect } from 'vitest'
import { l3Activation, type ActivationSpec, type ActivationEvent } from '../../../src/laws/l3-activation.js'

const baseSpec = (
  overrides: Partial<ActivationSpec> = {},
): ActivationSpec => ({
  id: 's-1',
  payload_validator: () => true,
  route_predicate: () => true,
  ...overrides,
})

describe('L3 ACTIVATION — contract', () => {
  it('matched spec_id + both predicates true → activates', () => {
    const event: ActivationEvent = { spec_id: 's-1', payload: { x: 1 } }
    expect(l3Activation.shouldActivate(event, baseSpec())).toBe(true)
  })

  it('schema match false → does NOT activate', () => {
    const spec = baseSpec({ payload_validator: () => false })
    expect(l3Activation.shouldActivate({ spec_id: 's-1', payload: {} }, spec)).toBe(false)
  })

  it('route predicate false → does NOT activate', () => {
    const spec = baseSpec({ route_predicate: () => false })
    expect(l3Activation.shouldActivate({ spec_id: 's-1', payload: {} }, spec)).toBe(false)
  })

  it('mismatched spec_id → does NOT activate', () => {
    expect(l3Activation.shouldActivate({ spec_id: 'other', payload: {} }, baseSpec())).toBe(false)
  })

  it('throwing predicate → does NOT activate', () => {
    const throws = baseSpec({
      payload_validator: () => {
        throw new Error('boom')
      },
    })
    expect(l3Activation.shouldActivate({ spec_id: 's-1', payload: {} }, throws)).toBe(false)
  })
})
