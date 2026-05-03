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
export declare const TENANT_ID_PATTERN: RegExp;
/**
 * Isolation contract levels — informs runtime enforcement at custody boundary.
 *
 * - `single-tenant`           → v1.0 default; one tenant per process
 * - `multi-tenant-shared`     → multiple tenants; shared underlying state
 * - `multi-tenant-isolated`   → multiple tenants; per-tenant state segregation
 */
export declare const TenantIsolationContract: z.ZodEnum<{
    "single-tenant": "single-tenant";
    "multi-tenant-shared": "multi-tenant-shared";
    "multi-tenant-isolated": "multi-tenant-isolated";
}>;
export type TenantIsolationContract = z.infer<typeof TenantIsolationContract>;
/**
 * Tenant primitive shape — D4 §1.1.
 */
export declare const TenantSchema: z.ZodObject<{
    id: z.ZodString;
    name: z.ZodString;
    isolation_contract: z.ZodDefault<z.ZodEnum<{
        "single-tenant": "single-tenant";
        "multi-tenant-shared": "multi-tenant-shared";
        "multi-tenant-isolated": "multi-tenant-isolated";
    }>>;
    parent_tenant_id: z.ZodDefault<z.ZodNullable<z.ZodString>>;
    managed_agents_session: z.ZodDefault<z.ZodNullable<z.ZodString>>;
    audit_log_path: z.ZodDefault<z.ZodNullable<z.ZodString>>;
}, z.core.$strip>;
export type Tenant = z.infer<typeof TenantSchema>;
/**
 * Construct a Tenant after schema validation. Throws on invalid input.
 *
 * Spec source: D4 §1.1; D1 P-A1 (sovereignty primitive).
 */
export declare function createTenant(input: Partial<Tenant> & {
    id: string;
    name: string;
}): Tenant;
/**
 * Predicate: is this Tenant shape valid against D4 §1.1?
 */
export declare function isValidTenant(t: unknown): t is Tenant;
//# sourceMappingURL=tenant.d.ts.map