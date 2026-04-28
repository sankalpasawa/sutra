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

  // ---------------------------------------------------------------------------
  // Codex M3 P1 #1 (2026-04-28) — array roots are NOT valid JSON Schema
  // documents. The M3 boundary must reject `'[]'`, `'[1,2,3]'`, and trivial
  // raw-boolean roots (V2 §3 HARD spirit, conservative — full Draft-7/2020-12
  // trivial schema compile lives in M5).
  // ---------------------------------------------------------------------------

  it('P1.1: contract_schema = "[]" (empty array root) → invalid', () => {
    expect(l2Boundary.isValid({ ...baseInterface, contract_schema: '[]' })).toBe(false)
  })

  it('P1.1: contract_schema = "[1,2,3]" (numeric array root) → invalid', () => {
    expect(l2Boundary.isValid({ ...baseInterface, contract_schema: '[1,2,3]' })).toBe(false)
  })

  it('P1.1: contract_schema = "true" (raw boolean trivial schema) → invalid (M3 conservative)', () => {
    expect(l2Boundary.isValid({ ...baseInterface, contract_schema: 'true' })).toBe(false)
  })

  it('P1.1: contract_schema = "false" (raw boolean trivial schema) → invalid (M3 conservative)', () => {
    expect(l2Boundary.isValid({ ...baseInterface, contract_schema: 'false' })).toBe(false)
  })

  it('P1.1: contract_schema = "null" (JSON null root) → invalid', () => {
    expect(l2Boundary.isValid({ ...baseInterface, contract_schema: 'null' })).toBe(false)
  })
})
