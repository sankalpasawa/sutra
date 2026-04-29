/**
 * Domain fixture factories — M4.10 baseline.
 *
 * Spec source: V2 §1 Primitive 1 + `src/primitives/domain.ts`.
 */

import type { Domain } from '../../src/primitives/domain.js'
import type { Constraint } from '../../src/types/index.js'

/**
 * Minimal valid Domain — D0 root with no principles, just the required fields.
 * `tenant_id` defaults to `T-default` via createDomain (M4.1).
 */
export function validMinimal(): Domain {
  return {
    id: 'D0',
    name: 'Asawa Inc.',
    parent_id: null,
    principles: [],
    intelligence: '',
    accountable: ['founder'],
    authority: 'org-root',
    tenant_id: 'T-default',
  }
}

/**
 * Fully populated valid Domain — sub-domain with one durable principle and
 * an explicit non-default tenant_id (M4.1 multi-tenant readiness).
 */
export function validFull(): Domain {
  const principle: Constraint = {
    name: 'plugin-first',
    predicate: 'every implementation defaults to L0 plugin path',
    durability: 'durable',
    owner_scope: 'domain',
    type: 'predicate',
  }
  return {
    id: 'D1.D2',
    name: 'Sutra-OS / Engine',
    parent_id: 'D1',
    principles: [principle],
    intelligence: 'engine charter + V2 spec + M3 laws shipped',
    accountable: ['sutra-os-team', 'asawa-ceo'],
    authority: 'plugin-runtime',
    tenant_id: 'T-asawa-holding',
  }
}

/**
 * Invalid: missing the required `id` field. Constructor must throw.
 */
export function invalidMissingRequired(): Partial<Domain> {
  return {
    name: 'orphan',
    parent_id: null,
    principles: [],
    intelligence: '',
    accountable: [],
    authority: '',
  }
}
