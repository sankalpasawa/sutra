/**
 * Tenant fixture factories — M4.1 (D4 §1.1; D1 P-A1).
 */

import type { Tenant } from '../../src/schemas/tenant.js'

/**
 * Minimal valid Tenant — id + name only; defaults applied.
 */
export function validMinimal(): Partial<Tenant> & { id: string; name: string } {
  return {
    id: 'T-default',
    name: 'Asawa Holding',
  }
}

/**
 * Fully populated valid Tenant — every optional field supplied.
 */
export function validFull(): Tenant {
  return {
    id: 'T-asawa-holding',
    name: 'Asawa Holding',
    isolation_contract: 'multi-tenant-isolated',
    parent_tenant_id: 'T-root',
    managed_agents_session: 'sess-asawa-2026-04',
    audit_log_path: '/var/log/sutra/asawa-audit.jsonl',
  }
}

/**
 * Invalid: missing required `id` field. Constructor must throw.
 */
export function invalidMissingRequired(): Partial<Tenant> {
  return {
    name: 'Orphan Tenant',
    isolation_contract: 'single-tenant',
    parent_tenant_id: null,
    managed_agents_session: null,
    audit_log_path: null,
  }
}
