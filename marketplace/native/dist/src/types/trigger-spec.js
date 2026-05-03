/**
 * TriggerSpec — D2 step 2 schema (deferred-to-Phase-3 primitive,
 * v1.0 inline form per V2 §8 lines 240-243).
 *
 * Per founder direction 2026-05-02: TriggerSpec is the routing primitive
 * that binds an EVENT shape (cron tick, founder input matching keywords,
 * file drop, webhook) to a TARGET WORKFLOW id. The Router consults the
 * registered TriggerSpecs and dispatches the first whose predicate matches.
 *
 * Predicate flavor (v1.0): STRUCTURED only — no string parsing. A string
 * predicate parser ("contains('X') AND contains('Y')") is deferred to v1.1
 * to keep the deterministic-routing surface minimal + auditable.
 *
 * I-NPD-1 (softened): predicates are evaluated deterministically. LLM
 * fallback is OPTIONAL, opt-in per Router config, and every fallback call
 * records prompt_hash for replay.
 */
/** Runtime allow-list — kept in sync with TriggerEventType. */
export const TRIGGER_EVENT_TYPES = new Set([
    'founder_input',
    'cron',
    'file_drop',
    'webhook',
]);
/** Runtime allow-list of Predicate.type literals — kept in sync with Predicate union. */
export const PREDICATE_TYPES = new Set([
    'contains',
    'matches',
    'event_type_eq',
    'cell_eq',
    'verb_eq',
    'direction_eq',
    'risk_eq',
    'always_true',
    'and',
    'or',
    'not',
]);
/**
 * Structural type guard for a Predicate — verifies the discriminator only.
 * Deep-validity (e.g. that an `and` clause's children are themselves valid)
 * is intentionally NOT checked here — `evaluate()` is total over the union
 * and any leaves with unknown discriminator return false at evaluation time.
 * The point of this guard is to catch obvious misuse at the registration
 * boundary, not to fully type-check user input.
 */
export function isPredicate(value) {
    if (typeof value !== 'object' || value === null)
        return false;
    const t = value.type;
    return typeof t === 'string' && PREDICATE_TYPES.has(t);
}
/**
 * Type guard — used by the Router on registration to reject malformed specs.
 * Tightened per codex master review (2026-05-03): event_type is checked
 * against the runtime allow-list, and route_predicate must have a known
 * Predicate.type discriminator.
 */
export function isTriggerSpec(value) {
    if (typeof value !== 'object' || value === null)
        return false;
    const v = value;
    return (typeof v.id === 'string' &&
        v.id.length > 0 &&
        typeof v.event_type === 'string' &&
        TRIGGER_EVENT_TYPES.has(v.event_type) &&
        typeof v.target_workflow === 'string' &&
        v.target_workflow.length > 0 &&
        isPredicate(v.route_predicate));
}
//# sourceMappingURL=trigger-spec.js.map