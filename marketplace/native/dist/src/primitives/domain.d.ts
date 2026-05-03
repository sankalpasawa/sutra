/**
 * DOMAIN — V2 spec §1 Primitive 1
 *
 * Bounded authority + accountability container.
 * The only primitive that contains another primitive (Domain.contains(Charter), per L5 META).
 *
 * Source-of-truth: holding/research/2026-04-28-v2-architecture-spec.md §1 P1
 */
import type { Constraint } from '../types/index.js';
/** Default tenant when none specified — single-tenant v1.0 baseline. */
export declare const DEFAULT_TENANT_ID = "T-default";
/**
 * Domain primitive shape — V2 spec §1.
 *
 * `reparent_op` from the spec is a runtime operation, not a stored field, so it
 * is not modeled here; the data shape is the 7 fields below.
 */
export interface Domain {
    id: string;
    name: string;
    /** null at D0 (org root); otherwise the parent Domain.id */
    parent_id: string | null;
    /** Constraint[] with durability='durable' per V2 §1 P1 */
    principles: Constraint[];
    /** accumulated context, decisions, history */
    intelligence: string;
    /** human role(s) responsible */
    accountable: string[];
    /** what this domain is empowered to decide */
    authority: string;
    /**
     * Owning Tenant id (M4.1; D4 §1.1 closes Tenant→Domain ownership).
     * Defaults to `T-default` (single-tenant v1.0 baseline).
     */
    tenant_id: string;
}
/** A Domain may omit `tenant_id`; createDomain fills the default. */
export type DomainSpec = Omit<Domain, 'tenant_id'> & {
    tenant_id?: string;
};
/**
 * Construct a Domain after validating the D-numbered id shape.
 * Returns a frozen object so primitive instances are immutable by default.
 */
export declare function createDomain(spec: DomainSpec): Domain;
/**
 * Predicate: is this Domain shape valid against V2 §1 P1?
 *
 * Used by:
 * - registry validation
 * - L5 META containment-edge checks
 *
 * Validates V2 §1 P1 invariants:
 * - id matches D-numbered pattern
 * - id='D0' ⇒ parent_id=null
 * - non-root: parent_id matches D-numbered pattern
 * - principles[*].durability === 'durable'
 */
export declare function isValidDomain(d: Domain): boolean;
//# sourceMappingURL=domain.d.ts.map