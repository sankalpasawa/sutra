/**
 * F-10 routing/gating positions inventory (M4.9 Group F).
 *
 * Per M4-schemas-edges.md M4.9 + V2 §3 HARD requirement (machine-checkable).
 * Each field DECIDES which branch executes — must have typed (non-string-prose-only)
 * representation OR a typed parser.
 *
 * A field qualifies as "routing/gating" iff its value DECIDES which branch
 * executes. F-10 property test asserts each of these 10 positions has a typed
 * representation; M5 + M7 will enforce at runtime; M4 ships the schema-level
 * check.
 *
 * Source-of-truth:
 *  - holding/research/2026-04-29-native-d4-primitives-composition-spec.md §3
 *  - holding/plans/native-v1.0/M4-schemas-edges.md M4.9 (F-10 inventory)
 */
/**
 * 10-position inventory of routing/gating fields per M4.9 §F-10.
 *
 * Order is normative — F-10 property tests iterate this list verbatim.
 */
export const ROUTING_GATING_POSITIONS = [
    'Workflow.preconditions',
    'Workflow.failure_policy',
    'Workflow.step_graph[i].action',
    'Workflow.step_graph[i].skill_ref',
    'Workflow.expects_response_from',
    'Workflow.on_override_action',
    'Charter.acl[]',
    'Charter.obligations[i].mechanization',
    'TriggerSpec.pattern',
    'BoundaryEndpoint.class',
];
/**
 * Static descriptor: each routing/gating position's representation kind in v1.0.
 *
 * IMPORTANT — every entry below is decidable, NOT free-form English prose:
 * either it's a TS-level discriminated union/enum, a typed record, a regex-guarded
 * id reference, or a string with a registered parser at M5+. The F-10 property
 * test asserts each entry is present in this map; the descriptor is the
 * machine-checkable contract.
 */
export const ROUTING_GATING_REPRESENTATIONS = {
    // M5 Group K (T-052) — flipped to `parser-bound` per codex P2.6 (D-NS-13 (b)).
    // Parsers shipped at `src/laws/f10-parsers.ts`:
    //   - parseWorkflowPreconditions  → boolean expression AST
    //   - parseWorkflowFailurePolicy  → 5-enum / structured JSON
    'Workflow.preconditions': 'parser-bound',
    'Workflow.failure_policy': 'parser-bound',
    // M7 codex P1.3: TriggerSpec.pattern parser-bound at M7. Charter.obligations[i].mechanization
    // stays typed_parser (deferred to v1.x — Constraint schema lacks the field).
    // Parser shipped at `src/laws/f10-parsers.ts` as `parseTriggerSpecPattern`
    // — V2 §A11 5-enum (preprocessor / observer / gate / fan_out / negotiation).
    'TriggerSpec.pattern': 'parser-bound',
    'Charter.obligations[i].mechanization': 'typed_parser',
    // Closed enums — decidable at the type level.
    'Workflow.on_override_action': 'typed_enum',
    'BoundaryEndpoint.class': 'typed_enum',
    'Workflow.step_graph[i].action': 'typed_enum',
    // Typed references — regex/format guard at the schema boundary.
    'Workflow.step_graph[i].skill_ref': 'typed_ref',
    'Workflow.expects_response_from': 'typed_ref',
    // Typed record — structured AclEntry list.
    'Charter.acl[]': 'typed_record',
};
/**
 * Predicate: is this routing/gating field machine-checkable in v1.0?
 *
 * Returns `true` iff the position has a registered representation kind in
 * `ROUTING_GATING_REPRESENTATIONS` (i.e., it has a typed representation OR a
 * typed parser hook). Returns `false` for any position not registered — that's
 * the F-10 violation: a routing/gating field exists in the schema with
 * English-prose-only semantics.
 *
 * F-10 property test asserts every entry of `ROUTING_GATING_POSITIONS` is
 * machine-checkable.
 */
export function isMachineCheckable(field) {
    return field in ROUTING_GATING_REPRESENTATIONS;
}
/**
 * Predicate: are ALL 10 routing/gating positions machine-checkable?
 *
 * Used by F-10 aggregator predicate; if any registered position lacks a
 * representation kind, F-10 fails.
 */
export function allRoutingGatingMachineCheckable() {
    for (const pos of ROUTING_GATING_POSITIONS) {
        if (!isMachineCheckable(pos))
            return false;
    }
    return true;
}
//# sourceMappingURL=routing-gating-positions.js.map