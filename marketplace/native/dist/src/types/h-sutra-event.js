/**
 * HSutraEvent — the row shape Sutra Core's H-Sutra layer writes to its
 * JSONL log per founder turn (Sutra Core v2.14+).
 *
 * Native subscribes to the log file via the H-Sutra connector and consumes
 * these events downstream. Per founder direction 2026-05-02 + C10: Native
 * is READ-ONLY against the log at v1.0 — never appends, never mutates.
 *
 * Schema is permissive: turn_id is the only REQUIRED field. Other fields
 * pass through unchanged so v1.0 doesn't break when Sutra Core extends the
 * schema. The router examines whichever fields are present.
 *
 * Reference schema (from CLAUDE.md "H-Sutra Header" + Sutra Core v2.14
 * marketplace.json description):
 *   - 9-cell CQRS: 3 verbs (DIRECT/QUERY/ASSERT) × 3 directions
 *     (INBOUND/INTERNAL/OUTBOUND)
 *   - Plus 3 orthogonal tags: TENSE / TIMING / CHANNEL
 *   - Plus REVERSIBILITY (reversible/partial/irreversible) + RISK level
 */
/**
 * Type guard — accepts any object with a string turn_id field.
 * Used by the connector to filter malformed JSONL rows without crashing.
 */
export function isHSutraEvent(value) {
    return (typeof value === 'object' &&
        value !== null &&
        typeof value.turn_id === 'string' &&
        value.turn_id.length > 0);
}
//# sourceMappingURL=h-sutra-event.js.map