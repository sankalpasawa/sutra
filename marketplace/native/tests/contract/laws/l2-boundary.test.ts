/**
 * L2 BOUNDARY — contract tests
 */
import { describe, it, expect } from 'vitest'
import { l2Boundary } from '../../../src/laws/l2-boundary.js'

const baseInterface = {
  endpoint_ref: 'ep-1',
  workflow_ref: 'W-1',
  direction: 'outbound' as const,
  qos: 'best-effort',
  failure_modes: [],
}

describe('L2 BOUNDARY — contract', () => {
  it('Interface with empty contract_schema → invalid', () => {
    expect(l2Boundary.isValid({ ...baseInterface, contract_schema: '' })).toBe(false)
  })

  it('Interface with malformed JSON contract_schema → invalid', () => {
    expect(l2Boundary.isValid({ ...baseInterface, contract_schema: '{not-json' })).toBe(false)
  })

  it('Interface with valid JSON-object contract_schema → valid', () => {
    expect(
      l2Boundary.isValid({
        ...baseInterface,
        contract_schema: '{"type":"object","properties":{"x":{"type":"number"}}}',
      }),
    ).toBe(true)
  })

  it('null input → invalid', () => {
    expect(l2Boundary.isValid(null)).toBe(false)
  })
})
