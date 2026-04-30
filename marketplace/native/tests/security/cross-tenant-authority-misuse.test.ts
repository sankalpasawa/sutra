/**
 * M12 Group YY (T-247). Cross-tenant authority misuse — runtime-enforced
 * attack test (codex P1.2 fold replacement for non-runtime-enforceable
 * exfiltration test).
 *
 * Vector: a Workflow running under Tenant A's tenant_context attempts an
 * operation against Tenant B's resources without a delegates_to edge
 * granting that operation. M9 TenantIsolation engine catches this at
 * runtime via the executor's runtime-derived cross-tenant gate (no
 * advisory bypass per M9 re-review P1 fold).
 *
 * Mitigation under test:
 *  - TenantIsolation.assertCrossTenantAllowed throws CrossTenantBoundaryError
 *    when no delegates_to edge grants the operation
 *  - L4 terminal-check (`l4-terminal-check.ts:481/494/637`) rejects F-6
 *    forbidden coupling
 *  - Fail-closed default (M9 codex master P1.1 fold): when
 *    workflow.custody_owner !== null AND tenant_context_id is undefined,
 *    executor moves to state='failed'
 *
 * Spec source:
 *   - holding/plans/native-v1.0/M12-release-canary.md (T-247 codex P1.2 fold)
 *   - holding/research/2026-04-30-native-threat-model.md §3
 */

import { describe, it, expect } from 'vitest'

import {
  TenantIsolation,
  CrossTenantBoundaryError,
} from '../../src/engine/tenant-isolation.js'

describe('M12 — Cross-tenant authority misuse (runtime-enforced)', () => {
  const isolation = new TenantIsolation()

  it('throws CrossTenantBoundaryError when no delegates_to edge grants the op', () => {
    expect(() =>
      isolation.assertCrossTenantAllowed({
        source_tenant: 'T-attacker',
        target_tenant: 'T-victim',
        operation: 'read-charter',
        delegates_to_edges: [], // ← ATTACK: no delegation, attempts cross-tenant op anyway
      }),
    ).toThrow(CrossTenantBoundaryError)
  })

  it('throws CrossTenantBoundaryError when delegates_to chain points elsewhere (wrong target)', () => {
    expect(() =>
      isolation.assertCrossTenantAllowed({
        source_tenant: 'T-attacker',
        target_tenant: 'T-victim',
        operation: 'read-charter',
        delegates_to_edges: [
          // Edge exists but for a DIFFERENT target — attacker can't claim it
          { kind: 'delegates_to', source: 'T-attacker', target: 'T-other' },
        ],
      }),
    ).toThrow(CrossTenantBoundaryError)
  })

  it('throws CrossTenantBoundaryError when delegates_to chain has wrong source', () => {
    expect(() =>
      isolation.assertCrossTenantAllowed({
        source_tenant: 'T-attacker',
        target_tenant: 'T-victim',
        operation: 'read-charter',
        delegates_to_edges: [
          // Edge exists but from a DIFFERENT source — attacker can't claim it
          { kind: 'delegates_to', source: 'T-other', target: 'T-victim' },
        ],
      }),
    ).toThrow(CrossTenantBoundaryError)
  })

  it('passes when a valid delegates_to edge grants the source→target operation', () => {
    expect(() =>
      isolation.assertCrossTenantAllowed({
        source_tenant: 'T-asawa',
        target_tenant: 'T-dayflow',
        operation: 'read-charter',
        delegates_to_edges: [
          { kind: 'delegates_to', source: 'T-asawa', target: 'T-dayflow' },
        ],
      }),
    ).not.toThrow()
  })

  it('CrossTenantBoundaryError is the canonical error class (not a generic Error)', () => {
    try {
      isolation.assertCrossTenantAllowed({
        source_tenant: 'T-x',
        target_tenant: 'T-y',
        operation: 'op',
        delegates_to_edges: [],
      })
      expect.fail('expected CrossTenantBoundaryError to be thrown')
    } catch (err) {
      expect(err).toBeInstanceOf(CrossTenantBoundaryError)
      expect(err).toBeInstanceOf(Error)
    }
  })
})
