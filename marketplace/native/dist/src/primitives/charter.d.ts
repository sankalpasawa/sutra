/**
 * CHARTER — V2 spec §1 Primitive 2 + V2.2 §A8 (acl[])
 *
 * Durable commitment envelope. Owns Workflows that operationalize this commitment.
 *
 * Source-of-truth: holding/research/2026-04-28-v2-architecture-spec.md §1 P2 + §17 A8
 */
import type { AclEntry, Constraint } from '../types/index.js';
import { type CutoverContract } from '../schemas/cutover-contract.js';
/**
 * Charter primitive shape — V2 §1 + V2.2 §A8.
 */
export interface Charter {
    id: string;
    /** 1-line outcome statement; required non-empty (HARD per V2 §3) */
    purpose: string;
    /** what is included (machine-checkable predicate) */
    scope_in: string;
    /** what is explicitly excluded */
    scope_out: string;
    /** what MUST be delivered; each Constraint typed obligation or untyped */
    obligations: Constraint[];
    /** what MUST always hold; each Constraint typed invariant or untyped */
    invariants: Constraint[];
    /** how to measure delivery */
    success_metrics: string[];
    /** inherited from parent Domain; may be narrower */
    authority: string;
    /** decommission criteria */
    termination: string;
    /** episodic Constraints (durability='episodic') */
    constraints: Constraint[];
    /** V2.2 §A8 — per-Domain/Charter access control list */
    acl: AclEntry[];
    /**
     * M4.7 — D1 §11.1 (P-A11). Optional cutover contract used when migrating
     * the Charter from one engine to another (e.g. Core → Native). `null`
     * when no cutover required (the default for greenfield Charters).
     * Cutover engine (P-B1) + migration tooling (P-C12) at M10 consume this.
     *
     * Optional on the TS shape because `createCharter` defaults absent values
     * to `null` via CutoverContractSchema.parse — existing callers continue
     * to compile without supplying the field.
     */
    cutover_contract?: CutoverContract;
}
/**
 * Construct a Charter after validating shape + V2.2 §A8 acl invariants.
 * Returns a frozen object.
 */
export declare function createCharter(spec: Charter): Charter;
/**
 * Predicate: is this Charter shape valid against V2 §1 P2 + V2.2 §A8?
 *
 * Deep-validates ACL entries — defensive runtime checks for deserialized records:
 * - domain_or_charter_id non-empty string
 * - access in {read, write, append, none}
 * - reason non-empty string
 */
export declare function isValidCharter(c: Charter): boolean;
//# sourceMappingURL=charter.d.ts.map