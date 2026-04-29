/**
 * AuthoritativeStatus + DataRef.authoritative_status contract tests — M4.6.
 *
 * Resolves PS-9 + Q7 by making each artifact's standing explicit at the schema
 * boundary (D2 §5).
 */

import { describe, expect, it } from 'vitest'
import {
  AUTHORITATIVE_STATUS_VALUES,
  AuthoritativeStatusSchema,
  isValidAuthoritativeStatus,
} from '../../../src/types/authoritative-status.js'
import { DataRefSchema } from '../../../src/types/index.js'

describe('AuthoritativeStatusSchema (M4.6)', () => {
  it('accepts "authoritative"', () => {
    expect(AuthoritativeStatusSchema.safeParse('authoritative').success).toBe(true)
    expect(isValidAuthoritativeStatus('authoritative')).toBe(true)
  })

  it('accepts "advisory"', () => {
    expect(AuthoritativeStatusSchema.safeParse('advisory').success).toBe(true)
    expect(isValidAuthoritativeStatus('advisory')).toBe(true)
  })

  it('rejects unknown enum values', () => {
    expect(AuthoritativeStatusSchema.safeParse('binding').success).toBe(false)
    expect(AuthoritativeStatusSchema.safeParse('hint').success).toBe(false)
  })

  it('rejects empty string', () => {
    expect(AuthoritativeStatusSchema.safeParse('').success).toBe(false)
  })

  it('rejects null and undefined directly', () => {
    expect(AuthoritativeStatusSchema.safeParse(null).success).toBe(false)
    expect(AuthoritativeStatusSchema.safeParse(undefined).success).toBe(false)
  })

  it('rejects numeric values', () => {
    expect(AuthoritativeStatusSchema.safeParse(1).success).toBe(false)
  })

  it('AUTHORITATIVE_STATUS_VALUES exposes the enum constants', () => {
    expect(AUTHORITATIVE_STATUS_VALUES).toEqual(['authoritative', 'advisory'])
  })
})

describe('DataRef.authoritative_status field (M4.6)', () => {
  const baseRef = {
    kind: 'json',
    schema_ref: 'native://schemas/x',
    locator: '/tmp/x.json',
    version: '1',
    mutability: 'immutable' as const,
    retention: '30d',
  }

  it('defaults to "authoritative" when omitted', () => {
    const r = DataRefSchema.parse(baseRef)
    expect(r.authoritative_status).toBe('authoritative')
  })

  it('explicit "authoritative" round-trips', () => {
    const r = DataRefSchema.parse({ ...baseRef, authoritative_status: 'authoritative' })
    expect(r.authoritative_status).toBe('authoritative')
  })

  it('explicit "advisory" round-trips', () => {
    const r = DataRefSchema.parse({ ...baseRef, authoritative_status: 'advisory' })
    expect(r.authoritative_status).toBe('advisory')
  })

  it('rejects invalid authoritative_status value', () => {
    expect(() =>
      DataRefSchema.parse({ ...baseRef, authoritative_status: 'binding' }),
    ).toThrow()
  })

  it('rejects null authoritative_status (would erase the default)', () => {
    expect(() =>
      DataRefSchema.parse({ ...baseRef, authoritative_status: null }),
    ).toThrow()
  })

  it('JSON round-trip preserves explicit advisory status', () => {
    const r = DataRefSchema.parse({ ...baseRef, authoritative_status: 'advisory' })
    const parsed = DataRefSchema.parse(JSON.parse(JSON.stringify(r)))
    expect(parsed.authoritative_status).toBe('advisory')
  })

  it('JSON round-trip preserves default authoritative status', () => {
    const r = DataRefSchema.parse(baseRef)
    const parsed = DataRefSchema.parse(JSON.parse(JSON.stringify(r)))
    expect(parsed.authoritative_status).toBe('authoritative')
  })
})
