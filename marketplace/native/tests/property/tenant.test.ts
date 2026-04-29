/**
 * Tenant primitive property tests — M4.1.
 *
 * Each property runs ≥1000 fast-check cases per M4 plan A-2.
 */

import { describe, expect, it } from 'vitest'
import * as fc from 'fast-check'
import {
  TenantSchema,
  createTenant,
  isValidTenant,
  type Tenant,
} from '../../src/schemas/tenant.js'

const PROP_RUNS = 1000

const tenantIdArb = fc
  .string({ minLength: 1, maxLength: 24 })
  .filter((s) => /^[a-z0-9-]+$/.test(s))
  .map((s) => `T-${s}`)

const isolationContractArb = fc.constantFrom(
  'single-tenant',
  'multi-tenant-shared',
  'multi-tenant-isolated',
) as fc.Arbitrary<Tenant['isolation_contract']>

const validTenantInputArb: fc.Arbitrary<{
  id: string
  name: string
  isolation_contract?: Tenant['isolation_contract']
  parent_tenant_id?: string | null
  managed_agents_session?: string | null
  audit_log_path?: string | null
}> = fc.record({
  id: tenantIdArb,
  name: fc.string({ minLength: 1, maxLength: 30 }),
  isolation_contract: isolationContractArb,
  parent_tenant_id: fc.option(tenantIdArb, { nil: null }),
  managed_agents_session: fc.option(fc.string({ minLength: 1, maxLength: 20 }), { nil: null }),
  audit_log_path: fc.option(fc.string({ minLength: 1, maxLength: 60 }), { nil: null }),
})

describe('Tenant property tests (M4.1)', () => {
  it('round-trips: createTenant → JSON → parse equals original', () => {
    fc.assert(
      fc.property(validTenantInputArb, (input) => {
        const t = createTenant(input)
        const json = JSON.stringify(t)
        const parsed = TenantSchema.parse(JSON.parse(json)) as Tenant
        expect(parsed).toEqual(t)
      }),
      { numRuns: PROP_RUNS },
    )
  })

  it('isValidTenant true on every createTenant output', () => {
    fc.assert(
      fc.property(validTenantInputArb, (input) => {
        const t = createTenant(input)
        expect(isValidTenant(t)).toBe(true)
      }),
      { numRuns: PROP_RUNS },
    )
  })

  it('rejects ids that fail T-<lowercase> pattern', () => {
    const PATTERN = /^T-[a-z0-9-]+$/
    const badIdArb = fc
      .oneof(
        fc.string({ maxLength: 8 }),
        fc.string({ minLength: 1, maxLength: 5 }).map((s) => `T-${s}!`),
        fc.string({ minLength: 1, maxLength: 5 }).map((s) => `${s}T-x`),
        fc.constant(''),
        fc.constant('T-'),
        fc.constant('T-?bad'),
        fc.constant('t-lower'),
        fc.constant('T-UPPER'),
      )
      .filter((s) => !PATTERN.test(s))
    fc.assert(
      fc.property(badIdArb, (badId) => {
        let threwOrFailed = false
        try {
          const t = createTenant({ id: badId, name: 'x' })
          if (!isValidTenant(t)) threwOrFailed = true
        } catch {
          threwOrFailed = true
        }
        expect(threwOrFailed).toBe(true)
      }),
      { numRuns: PROP_RUNS },
    )
  })

  it('rejects empty name', () => {
    fc.assert(
      fc.property(tenantIdArb, (id) => {
        expect(() => createTenant({ id, name: '' })).toThrow()
      }),
      { numRuns: PROP_RUNS },
    )
  })

  it('default isolation_contract is single-tenant when omitted', () => {
    fc.assert(
      fc.property(tenantIdArb, fc.string({ minLength: 1, maxLength: 30 }), (id, name) => {
        const t = createTenant({ id, name })
        expect(t.isolation_contract).toBe('single-tenant')
      }),
      { numRuns: PROP_RUNS },
    )
  })
})
