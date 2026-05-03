/**
 * TENANT — V2 sovereignty primitive (D1 §1 Authority Map P-A1, D4 §1.1).
 *
 * Tenant is the isolation primitive that owns Domains. v1.0 ships single-tenant
 * by default; the schema lands now so v1.1 multi-tenant doesn't require breaking
 * changes.
 *
 * Spec source:
 * - holding/research/2026-04-29-native-d1-authority-map.md §1-§3
 * - holding/research/2026-04-29-native-d4-primitives-composition-spec.md §1.1
 * - holding/plans/native-v1.0/M4-schemas-edges.md §M4.1
 */
import { z } from 'zod';
/**
 * Tenant id pattern: `T-<lowercase-alphanumeric-with-hyphens>`.
 * Example: `T-default`, `T-asawa-holding`, `T-billu-prod`.
 */
export const TENANT_ID_PATTERN = /^T-[a-z0-9-]+$/;
/**
 * Isolation contract levels — informs runtime enforcement at custody boundary.
 *
 * - `single-tenant`           → v1.0 default; one tenant per process
 * - `multi-tenant-shared`     → multiple tenants; shared underlying state
 * - `multi-tenant-isolated`   → multiple tenants; per-tenant state segregation
 */
export const TenantIsolationContract = z.enum([
    'single-tenant',
    'multi-tenant-shared',
    'multi-tenant-isolated',
]);
/**
 * Tenant primitive shape — D4 §1.1.
 */
export const TenantSchema = z.object({
    /** `T-<id>` pattern; required, immutable identity. */
    id: z.string().regex(TENANT_ID_PATTERN),
    /** Human-readable; non-empty. */
    name: z.string().min(1),
    /** Defaults to `single-tenant` for v1.0. */
    isolation_contract: TenantIsolationContract.default('single-tenant'),
    /** `null` for root tenants; otherwise the parent Tenant.id. */
    parent_tenant_id: z.string().regex(TENANT_ID_PATTERN).nullable().default(null),
    /** Reserved for Managed Agents bridging; null when not bound. */
    managed_agents_session: z.string().nullable().default(null),
    /** Optional path/locator to an audit log file or sink. */
    audit_log_path: z.string().nullable().default(null),
});
/**
 * Construct a Tenant after schema validation. Throws on invalid input.
 *
 * Spec source: D4 §1.1; D1 P-A1 (sovereignty primitive).
 */
export function createTenant(input) {
    return TenantSchema.parse({ ...input });
}
/**
 * Predicate: is this Tenant shape valid against D4 §1.1?
 */
export function isValidTenant(t) {
    return TenantSchema.safeParse(t).success;
}
//# sourceMappingURL=tenant.js.map