/**
 * DOMAIN — V2 spec §1 Primitive 1
 *
 * Bounded authority + accountability container.
 * The only primitive that contains another primitive (Domain.contains(Charter), per L5 META).
 *
 * Source-of-truth: holding/research/2026-04-28-v2-architecture-spec.md §1 P1
 */

import type { Constraint } from '../types/index.js'

/**
 * D-numbered hierarchy id pattern.
 * - Root domain is 'D0'
 * - Sub-domains are 'D1', 'D2', ...
 * - Nested sub-domains are 'D1.D2', 'D1.D2.D3', ...
 *
 * Note: the V2 spec text used \.D (literal D) — the M2.1 plan example regex
 * had a stray \D escape that would never match. This regex matches the spec.
 */
const D_ID_PATTERN = /^D\d+(\.D\d+)*$/

/**
 * Domain primitive shape — V2 spec §1.
 *
 * `reparent_op` from the spec is a runtime operation, not a stored field, so it
 * is not modeled here; the data shape is the 7 fields below.
 */
export interface Domain {
  id: string
  name: string
  /** null at D0 (org root); otherwise the parent Domain.id */
  parent_id: string | null
  /** Constraint[] with durability='durable' per V2 §1 P1 */
  principles: Constraint[]
  /** accumulated context, decisions, history */
  intelligence: string
  /** human role(s) responsible */
  accountable: string[]
  /** what this domain is empowered to decide */
  authority: string
}

/**
 * Construct a Domain after validating the D-numbered id shape.
 * Returns a frozen object so primitive instances are immutable by default.
 */
export function createDomain(spec: Domain): Domain {
  if (!D_ID_PATTERN.test(spec.id)) {
    throw new Error(
      `Domain.id must match D-numbered hierarchy pattern (D0, D1, D1.D2, ...); got "${spec.id}"`,
    )
  }
  if (!Array.isArray(spec.principles)) {
    throw new Error('Domain.principles must be an array')
  }
  if (!Array.isArray(spec.accountable)) {
    throw new Error('Domain.accountable must be an array')
  }
  return Object.freeze({ ...spec, principles: [...spec.principles], accountable: [...spec.accountable] })
}

/**
 * Predicate: is this Domain shape valid against V2 §1 P1?
 *
 * Used by:
 * - registry validation
 * - L5 META containment-edge checks
 */
export function isValidDomain(d: Domain): boolean {
  if (typeof d !== 'object' || d === null) return false
  if (typeof d.id !== 'string' || !D_ID_PATTERN.test(d.id)) return false
  if (typeof d.name !== 'string') return false
  if (d.parent_id !== null && typeof d.parent_id !== 'string') return false
  if (!Array.isArray(d.principles)) return false
  if (typeof d.intelligence !== 'string') return false
  if (!Array.isArray(d.accountable)) return false
  if (typeof d.authority !== 'string') return false
  return true
}
