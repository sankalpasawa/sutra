/**
 * CHARTER — V2 spec §1 Primitive 2 + V2.2 §A8 (acl[])
 *
 * Durable commitment envelope. Owns Workflows that operationalize this commitment.
 *
 * Source-of-truth: holding/research/2026-04-28-v2-architecture-spec.md §1 P2 + §17 A8
 */

import type { AclAccess, AclEntry, Constraint } from '../types/index.js'
import {
  CutoverContractSchema,
  type CutoverContract,
} from '../schemas/cutover-contract.js'

/** Charter id starts with 'C-' followed by an opaque hash/identifier (>=1 char). */
const C_ID_PATTERN = /^C-.+$/

const VALID_ACL_ACCESS: ReadonlySet<AclAccess> = new Set([
  'read',
  'write',
  'append',
  'none',
])

/**
 * Charter primitive shape — V2 §1 + V2.2 §A8.
 */
export interface Charter {
  id: string
  /** 1-line outcome statement; required non-empty (HARD per V2 §3) */
  purpose: string
  /** what is included (machine-checkable predicate) */
  scope_in: string
  /** what is explicitly excluded */
  scope_out: string
  /** what MUST be delivered; each Constraint typed obligation or untyped */
  obligations: Constraint[]
  /** what MUST always hold; each Constraint typed invariant or untyped */
  invariants: Constraint[]
  /** how to measure delivery */
  success_metrics: string[]
  /** inherited from parent Domain; may be narrower */
  authority: string
  /** decommission criteria */
  termination: string
  /** episodic Constraints (durability='episodic') */
  constraints: Constraint[]
  /** V2.2 §A8 — per-Domain/Charter access control list */
  acl: AclEntry[]
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
  cutover_contract?: CutoverContract
}

function validateConstraintRole(
  list: Constraint[],
  expected: 'obligation' | 'invariant',
  fieldName: string,
): void {
  for (const c of list) {
    if (c.type !== undefined && c.type !== expected) {
      throw new Error(
        `Charter.${fieldName}[] entries must have Constraint.type='${expected}' (or undefined); got "${c.type}"`,
      )
    }
  }
}

function validateAcl(acl: AclEntry[]): void {
  for (const entry of acl) {
    if (typeof entry.domain_or_charter_id !== 'string' || entry.domain_or_charter_id.length === 0) {
      throw new Error('Charter.acl[].domain_or_charter_id must be a non-empty string')
    }
    if (!VALID_ACL_ACCESS.has(entry.access)) {
      throw new Error(
        `Charter.acl[].access must be one of read|write|append|none; got "${String(entry.access)}"`,
      )
    }
    if (typeof entry.reason !== 'string' || entry.reason.length === 0) {
      throw new Error('Charter.acl[].reason must be a non-empty string')
    }
  }
}

/**
 * Construct a Charter after validating shape + V2.2 §A8 acl invariants.
 * Returns a frozen object.
 */
export function createCharter(spec: Charter): Charter {
  if (!C_ID_PATTERN.test(spec.id)) {
    throw new Error(`Charter.id must match pattern C-<hash>; got "${spec.id}"`)
  }
  if (typeof spec.purpose !== 'string' || spec.purpose.trim().length === 0) {
    throw new Error('Charter.purpose must be a non-empty 1-line outcome statement')
  }
  if (!Array.isArray(spec.obligations)) {
    throw new Error('Charter.obligations must be an array')
  }
  if (!Array.isArray(spec.invariants)) {
    throw new Error('Charter.invariants must be an array')
  }
  if (!Array.isArray(spec.success_metrics)) {
    throw new Error('Charter.success_metrics must be an array')
  }
  if (!Array.isArray(spec.constraints)) {
    throw new Error('Charter.constraints must be an array')
  }
  if (!Array.isArray(spec.acl)) {
    throw new Error('Charter.acl must be an array')
  }
  validateConstraintRole(spec.obligations, 'obligation', 'obligations')
  validateConstraintRole(spec.invariants, 'invariant', 'invariants')
  validateAcl(spec.acl)
  // M4.7: validate cutover_contract via CutoverContractSchema. Schema accepts
  // null (no cutover) AND fully-populated records; `.parse()` throws on any
  // malformed shape (empty source_engine, empty behavior_invariants array, etc.).
  // Default `null` when caller omits the field — keeps the v1.0 contract
  // backward-compatible with M2-M4.6 Charters.
  const cutover_contract = CutoverContractSchema.parse(
    spec.cutover_contract ?? null,
  )
  return Object.freeze({
    ...spec,
    obligations: [...spec.obligations],
    invariants: [...spec.invariants],
    success_metrics: [...spec.success_metrics],
    constraints: [...spec.constraints],
    acl: [...spec.acl],
    cutover_contract,
  })
}

/**
 * Predicate: is this Charter shape valid against V2 §1 P2 + V2.2 §A8?
 *
 * Deep-validates ACL entries — defensive runtime checks for deserialized records:
 * - domain_or_charter_id non-empty string
 * - access in {read, write, append, none}
 * - reason non-empty string
 */
export function isValidCharter(c: Charter): boolean {
  if (typeof c !== 'object' || c === null) return false
  if (typeof c.id !== 'string' || !C_ID_PATTERN.test(c.id)) return false
  if (typeof c.purpose !== 'string' || c.purpose.trim().length === 0) return false
  if (!Array.isArray(c.obligations)) return false
  if (!Array.isArray(c.invariants)) return false
  if (!Array.isArray(c.success_metrics)) return false
  if (!Array.isArray(c.constraints)) return false
  if (!Array.isArray(c.acl)) return false
  for (const entry of c.acl) {
    if (typeof entry !== 'object' || entry === null) return false
    if (typeof entry.domain_or_charter_id !== 'string' || entry.domain_or_charter_id.length === 0) {
      return false
    }
    if (!VALID_ACL_ACCESS.has(entry.access)) return false
    if (typeof entry.reason !== 'string' || entry.reason.length === 0) return false
  }
  // M4.7: cutover_contract optional on the TS shape; when present (including
  // explicit null), defer to the schema-level guard so the same predicates
  // apply to deserialized records as to constructor input.
  if ('cutover_contract' in c) {
    if (!CutoverContractSchema.safeParse(c.cutover_contract).success) {
      return false
    }
  }
  return true
}
