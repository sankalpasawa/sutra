/**
 * Tenant primitive contract tests — M4.1 (D4 §1.1; D1 P-A1).
 */

import { describe, expect, it } from 'vitest'
import {
  TenantSchema,
  createTenant,
  isValidTenant,
  type Tenant,
} from '../../../src/schemas/tenant.js'
import * as TenantFx from '../../fixtures/tenant.fixture.js'

describe('Tenant primitive (M4.1; D4 §1.1)', () => {
  it('creates a default single-tenant', () => {
    const t = createTenant({ id: 'T-default', name: 'Asawa Holding' })
    expect(isValidTenant(t)).toBe(true)
    expect(t.id).toBe('T-default')
    expect(t.isolation_contract).toBe('single-tenant')
    expect(t.parent_tenant_id).toBeNull()
    expect(t.managed_agents_session).toBeNull()
    expect(t.audit_log_path).toBeNull()
  })

  it('rejects malformed id (no T- prefix)', () => {
    expect(() => createTenant({ id: 'bad-prefix', name: 'X' })).toThrow()
  })

  it('rejects uppercase characters in id (pattern is lowercase only)', () => {
    expect(() => createTenant({ id: 'T-Asawa', name: 'X' })).toThrow()
  })

  it('rejects empty id', () => {
    expect(() => createTenant({ id: '', name: 'X' })).toThrow()
  })

  it('rejects empty name', () => {
    expect(() => createTenant({ id: 'T-x', name: '' })).toThrow()
  })

  it('accepts multi-tenant-shared isolation_contract override', () => {
    const t = createTenant({
      id: 'T-shared-pool',
      name: 'Shared Pool',
      isolation_contract: 'multi-tenant-shared',
    })
    expect(t.isolation_contract).toBe('multi-tenant-shared')
  })

  it('accepts multi-tenant-isolated isolation_contract override', () => {
    const t = createTenant({
      id: 'T-isolated',
      name: 'Isolated',
      isolation_contract: 'multi-tenant-isolated',
    })
    expect(t.isolation_contract).toBe('multi-tenant-isolated')
  })

  it('rejects unknown isolation_contract value', () => {
    expect(() =>
      // @ts-expect-error — intentionally invalid enum
      createTenant({ id: 'T-x', name: 'X', isolation_contract: 'multi-tenant-bogus' }),
    ).toThrow()
  })

  it('accepts a valid parent_tenant_id', () => {
    const t = createTenant({
      id: 'T-child',
      name: 'Child',
      parent_tenant_id: 'T-parent',
    })
    expect(t.parent_tenant_id).toBe('T-parent')
  })

  it('rejects a malformed parent_tenant_id', () => {
    expect(() =>
      createTenant({ id: 'T-child', name: 'Child', parent_tenant_id: 'bogus' }),
    ).toThrow()
  })

  it('accepts a non-null managed_agents_session', () => {
    const t = createTenant({
      id: 'T-bound',
      name: 'Bound',
      managed_agents_session: 'sess-abc',
    })
    expect(t.managed_agents_session).toBe('sess-abc')
  })

  it('accepts a non-null audit_log_path', () => {
    const t = createTenant({
      id: 'T-audited',
      name: 'Audited',
      audit_log_path: '/var/log/sutra/audit.jsonl',
    })
    expect(t.audit_log_path).toBe('/var/log/sutra/audit.jsonl')
  })

  it('isValidTenant rejects non-objects', () => {
    expect(isValidTenant(null)).toBe(false)
    expect(isValidTenant(undefined)).toBe(false)
    expect(isValidTenant('T-x')).toBe(false)
    expect(isValidTenant(42)).toBe(false)
  })

  it('isValidTenant rejects records missing required fields', () => {
    expect(isValidTenant({ id: 'T-x' })).toBe(false)
    expect(isValidTenant({ name: 'no id' })).toBe(false)
  })

  it('round-trip: serialize → parse preserves all fields', () => {
    const t = createTenant({
      id: 'T-roundtrip',
      name: 'Roundtrip',
      isolation_contract: 'multi-tenant-isolated',
      parent_tenant_id: 'T-root',
      managed_agents_session: 'sess-123',
      audit_log_path: '/audit.jsonl',
    })
    const json = JSON.stringify(t)
    const parsed = TenantSchema.parse(JSON.parse(json)) as Tenant
    expect(parsed).toEqual(t)
  })

  it('fixtures: validMinimal + validFull both round-trip', () => {
    const a = createTenant(TenantFx.validMinimal())
    expect(isValidTenant(a)).toBe(true)
    const b = createTenant(TenantFx.validFull())
    expect(isValidTenant(b)).toBe(true)
  })

  it('fixtures: invalidMissingRequired throws or fails predicate', () => {
    const bad = TenantFx.invalidMissingRequired()
    let threwOrFailed = false
    try {
      // @ts-expect-error — fixture intentionally missing required field
      const t = createTenant(bad)
      if (!isValidTenant(t)) threwOrFailed = true
    } catch {
      threwOrFailed = true
    }
    expect(threwOrFailed).toBe(true)
  })
})
