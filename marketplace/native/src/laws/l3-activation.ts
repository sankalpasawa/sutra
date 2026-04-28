/**
 * L3 ACTIVATION law — V2 spec §3 row L3
 *
 * Rule: "TriggerEvent creates Execution iff
 *        `schema_match(payload) AND route_predicate(payload)`."
 *
 * Mechanization: Predicate compiled to executable check.
 *
 * For Native v1.0 (M3) we accept pre-compiled predicate functions on the spec.
 * Runtime compilation of serialized predicate strings is deferred to M5
 * Workflow Engine integration per `holding/plans/native-v1.0/M3-laws.md` M3.3.3.
 *
 * Source-of-truth: holding/research/2026-04-28-v2-architecture-spec.md §3 L3
 */

/**
 * TriggerSpec used by L3 ACTIVATION.
 * - `payload_validator`: pure function — JSON-schema match check (compiled fn).
 * - `route_predicate`:   pure function — routing condition.
 */
export interface ActivationSpec {
  id: string
  payload_validator: (payload: unknown) => boolean
  route_predicate: (payload: unknown) => boolean
}

export interface ActivationEvent {
  spec_id: string
  payload: unknown
}

export const l3Activation = {
  /**
   * Should this TriggerEvent activate (create an Execution) under the given spec?
   *
   * True iff BOTH `payload_validator(payload)` AND `route_predicate(payload)`
   * return true. Spec/event mismatch (`event.spec_id !== spec.id`) → false.
   *
   * Predicate functions are evaluated defensively: any thrown error counts
   * as `false` (predicates must be total for activation; partial = no-go).
   */
  shouldActivate(event: ActivationEvent | unknown, spec: ActivationSpec | unknown): boolean {
    if (typeof event !== 'object' || event === null) return false
    if (typeof spec !== 'object' || spec === null) return false
    const e = event as Record<string, unknown>
    const s = spec as Record<string, unknown>

    if (typeof e.spec_id !== 'string' || typeof s.id !== 'string') return false
    if (e.spec_id !== s.id) return false

    if (typeof s.payload_validator !== 'function') return false
    if (typeof s.route_predicate !== 'function') return false

    let schemaOk: boolean
    try {
      schemaOk = (s.payload_validator as (p: unknown) => boolean)(e.payload) === true
    } catch {
      return false
    }
    if (!schemaOk) return false

    let routeOk: boolean
    try {
      routeOk = (s.route_predicate as (p: unknown) => boolean)(e.payload) === true
    } catch {
      return false
    }

    return routeOk
  },
}
