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
export type TriggerEventType = 'founder_input' | 'cron' | 'file_drop' | 'webhook';
/** Runtime allow-list — kept in sync with TriggerEventType. */
export declare const TRIGGER_EVENT_TYPES: ReadonlySet<TriggerEventType>;
/**
 * Structured predicate. Either a leaf condition (contains, matches, eq)
 * or a logical combinator (and, or, not).
 *
 * Leaf predicates examine a context object (input text + H-Sutra fields).
 * Combinators recurse over child predicates.
 */
export type Predicate = {
    readonly type: 'contains';
    readonly value: string;
    readonly case_sensitive?: boolean;
} | {
    readonly type: 'matches';
    readonly pattern: string;
    readonly flags?: string;
} | {
    readonly type: 'event_type_eq';
    readonly value: TriggerEventType;
} | {
    readonly type: 'cell_eq';
    readonly value: string;
} | {
    readonly type: 'verb_eq';
    readonly value: 'DIRECT' | 'QUERY' | 'ASSERT';
} | {
    readonly type: 'direction_eq';
    readonly value: 'INBOUND' | 'INTERNAL' | 'OUTBOUND';
} | {
    readonly type: 'risk_eq';
    readonly value: 'LOW' | 'MEDIUM' | 'HIGH';
} | {
    readonly type: 'always_true';
} | {
    readonly type: 'and';
    readonly clauses: ReadonlyArray<Predicate>;
} | {
    readonly type: 'or';
    readonly clauses: ReadonlyArray<Predicate>;
} | {
    readonly type: 'not';
    readonly clause: Predicate;
};
export interface TriggerSpec {
    /** Stable id, e.g. 'T-build-product'. */
    readonly id: string;
    /** Event class this trigger listens for. */
    readonly event_type: TriggerEventType;
    /** Predicate evaluated against the event + input text. */
    readonly route_predicate: Predicate;
    /** Workflow id to dispatch on match. */
    readonly target_workflow: string;
    /** Owning Domain id (for audit + Charter lookup). */
    readonly domain_id?: string;
    /** Owning Charter id (for ACL). */
    readonly charter_id?: string;
    /** Free-form description for operators. */
    readonly description?: string;
}
/** Runtime allow-list of Predicate.type literals — kept in sync with Predicate union. */
export declare const PREDICATE_TYPES: ReadonlySet<string>;
/**
 * Structural type guard for a Predicate — verifies the discriminator only.
 * Deep-validity (e.g. that an `and` clause's children are themselves valid)
 * is intentionally NOT checked here — `evaluate()` is total over the union
 * and any leaves with unknown discriminator return false at evaluation time.
 * The point of this guard is to catch obvious misuse at the registration
 * boundary, not to fully type-check user input.
 */
export declare function isPredicate(value: unknown): value is Predicate;
/**
 * Type guard — used by the Router on registration to reject malformed specs.
 * Tightened per codex master review (2026-05-03): event_type is checked
 * against the runtime allow-list, and route_predicate must have a known
 * Predicate.type discriminator.
 */
export declare function isTriggerSpec(value: unknown): value is TriggerSpec;
//# sourceMappingURL=trigger-spec.d.ts.map