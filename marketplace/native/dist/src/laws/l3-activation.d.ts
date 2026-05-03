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
    id: string;
    payload_validator: (payload: unknown) => boolean;
    route_predicate: (payload: unknown) => boolean;
}
export interface ActivationEvent {
    spec_id: string;
    payload: unknown;
}
export declare const l3Activation: {
    /**
     * Should this TriggerEvent activate (create an Execution) under the given spec?
     *
     * True iff BOTH `payload_validator(payload)` AND `route_predicate(payload)`
     * return true. Spec/event mismatch (`event.spec_id !== spec.id`) → false.
     *
     * Predicate functions are evaluated defensively: any thrown error counts
     * as `false` (predicates must be total for activation; partial = no-go).
     */
    shouldActivate(event: ActivationEvent | unknown, spec: ActivationSpec | unknown): boolean;
};
//# sourceMappingURL=l3-activation.d.ts.map