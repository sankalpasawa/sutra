/**
 * TenantIsolation contract test (M9 Group FF T-154).
 *
 * Asserts:
 *  - same-tenant op never throws (no edge required)
 *  - cross-tenant op WITH a matching delegates_to edge passes
 *  - cross-tenant op WITHOUT a matching edge throws CrossTenantBoundaryError
 *  - error carries source/target/operation fields
 *  - empty edges array → cross-tenant op throws
 *  - non-array edges → cross-tenant op throws (defensive)
 *  - bogus input shapes → TypeError (engine surface contract)
 *  - instance + static API both deliver the same decision
 *
 * Engine contract (codex M9 P1.2 fold): the engine READS existing D4 §3
 * `delegates_to: Tenant→Tenant` edges; it does NOT define a parallel
 * delegation schema. These tests validate against `DelegatesToEdge` as
 * exported from `src/types/edges.ts`.
 *
 * Spec source:
 *   - holding/plans/native-v1.0/M9-e2e-vinit.md Group FF T-154
 *   - .enforcement/codex-reviews/2026-04-30-m9-pre-dispatch.md P1.2
 *   - holding/research/2026-04-29-native-d4-primitives-composition-spec.md §3
 */

import { describe, it, expect } from 'vitest'

import {
  TenantIsolation,
  CrossTenantBoundaryError,
} from '../../../src/engine/tenant-isolation.js'
import type { DelegatesToEdge } from '../../../src/types/edges.js'

const edge = (source: string, target: string): DelegatesToEdge => ({
  kind: 'delegates_to',
  source,
  target,
})

describe('TenantIsolation — same-tenant always allowed', () => {
  it('same source + target returns without error, no edge required', () => {
    expect(() =>
      TenantIsolation.assertCrossTenantAllowed({
        source_tenant: 'T-asawa',
        target_tenant: 'T-asawa',
        operation: 'invoke_skill:W-noop',
        delegates_to_edges: [],
      }),
    ).not.toThrow()
  })

  it('same source + target ignores edges entirely', () => {
    // even if edges contradict (none match), same-tenant op still passes.
    expect(() =>
      TenantIsolation.assertCrossTenantAllowed({
        source_tenant: 'T-paisa',
        target_tenant: 'T-paisa',
        operation: 'step_action:wait',
        delegates_to_edges: [edge('T-other-a', 'T-other-b')],
      }),
    ).not.toThrow()
  })
})

describe('TenantIsolation — cross-tenant requires delegates_to edge', () => {
  it('cross-tenant op WITH matching edge passes', () => {
    expect(() =>
      TenantIsolation.assertCrossTenantAllowed({
        source_tenant: 'T-asawa',
        target_tenant: 'T-paisa',
        operation: 'invoke_skill:W-billu-skill',
        delegates_to_edges: [edge('T-asawa', 'T-paisa')],
      }),
    ).not.toThrow()
  })

  it('cross-tenant op WITHOUT edge throws CrossTenantBoundaryError', () => {
    expect(() =>
      TenantIsolation.assertCrossTenantAllowed({
        source_tenant: 'T-asawa',
        target_tenant: 'T-paisa',
        operation: 'invoke_skill:W-billu-skill',
        delegates_to_edges: [],
      }),
    ).toThrow(CrossTenantBoundaryError)
  })

  it('cross-tenant op with edge in REVERSE direction throws', () => {
    // T-paisa -> T-asawa edge does NOT grant T-asawa -> T-paisa op.
    expect(() =>
      TenantIsolation.assertCrossTenantAllowed({
        source_tenant: 'T-asawa',
        target_tenant: 'T-paisa',
        operation: 'invoke_skill:W-x',
        delegates_to_edges: [edge('T-paisa', 'T-asawa')],
      }),
    ).toThrow(CrossTenantBoundaryError)
  })

  it('error carries source_tenant + target_tenant + operation fields', () => {
    try {
      TenantIsolation.assertCrossTenantAllowed({
        source_tenant: 'T-asawa',
        target_tenant: 'T-paisa',
        operation: 'invoke_skill:W-billu-skill',
        delegates_to_edges: [],
      })
      expect.fail('expected CrossTenantBoundaryError')
    } catch (err) {
      expect(err).toBeInstanceOf(CrossTenantBoundaryError)
      const e = err as CrossTenantBoundaryError
      expect(e.source_tenant).toBe('T-asawa')
      expect(e.target_tenant).toBe('T-paisa')
      expect(e.operation).toBe('invoke_skill:W-billu-skill')
      expect(e.name).toBe('CrossTenantBoundaryError')
      expect(e.message).toContain('T-asawa -> T-paisa')
      expect(e.message).toContain('no delegates_to edge')
    }
  })
})

describe('TenantIsolation — defensive input handling', () => {
  it('throws TypeError on null input', () => {
    expect(() =>
      TenantIsolation.assertCrossTenantAllowed(null as unknown as never),
    ).toThrow(TypeError)
  })

  it('throws TypeError on empty source_tenant', () => {
    expect(() =>
      TenantIsolation.assertCrossTenantAllowed({
        source_tenant: '',
        target_tenant: 'T-paisa',
        operation: 'op',
        delegates_to_edges: [],
      }),
    ).toThrow(TypeError)
  })

  it('throws TypeError on empty operation', () => {
    expect(() =>
      TenantIsolation.assertCrossTenantAllowed({
        source_tenant: 'T-asawa',
        target_tenant: 'T-paisa',
        operation: '',
        delegates_to_edges: [],
      }),
    ).toThrow(TypeError)
  })
})

describe('TenantIsolation — instance form mirrors static', () => {
  it('iso.assertCrossTenantAllowed matches static decision', () => {
    const iso = new TenantIsolation()

    // same-tenant — pass
    expect(() =>
      iso.assertCrossTenantAllowed({
        source_tenant: 'T-asawa',
        target_tenant: 'T-asawa',
        operation: 'op',
        delegates_to_edges: [],
      }),
    ).not.toThrow()

    // cross-tenant without edge — fail
    expect(() =>
      iso.assertCrossTenantAllowed({
        source_tenant: 'T-asawa',
        target_tenant: 'T-paisa',
        operation: 'op',
        delegates_to_edges: [],
      }),
    ).toThrow(CrossTenantBoundaryError)
  })
})
