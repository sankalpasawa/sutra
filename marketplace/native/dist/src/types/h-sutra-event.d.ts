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
export type HSutraVerb = 'DIRECT' | 'QUERY' | 'ASSERT';
export type HSutraDirection = 'INBOUND' | 'INTERNAL' | 'OUTBOUND';
export type HSutraTense = 'past' | 'present' | 'future';
export type HSutraTiming = 'NOW' | 'NEXT' | 'LATER';
export type HSutraReversibility = 'reversible' | 'partial' | 'irreversible';
export type HSutraRisk = 'LOW' | 'MEDIUM' | 'HIGH';
export interface HSutraEvent {
    /** REQUIRED — unique per founder turn; Native uses this as routing key. */
    readonly turn_id: string;
    /** ISO 8601 timestamp written by Sutra Core. */
    readonly ts?: string;
    /** 9-cell verb dimension. */
    readonly verb?: HSutraVerb;
    /** 9-cell direction dimension. */
    readonly direction?: HSutraDirection;
    /** Pre-joined cell coordinate (e.g., "DIRECT·INBOUND"). */
    readonly cell?: string;
    /** Tense tag. */
    readonly tense?: HSutraTense;
    /** Timing tag. */
    readonly timing?: HSutraTiming;
    /** Channel tag (e.g., "CHAT"). */
    readonly channel?: string;
    /** Reversibility classification. */
    readonly reversibility?: HSutraReversibility;
    /** Risk level. */
    readonly risk?: HSutraRisk;
    /** Raw founder input text (when present in the log row). */
    readonly input_text?: string;
    /** Pass-through for any field Native doesn't yet know about. */
    readonly [extra: string]: unknown;
}
/**
 * Type guard — accepts any object with a string turn_id field.
 * Used by the connector to filter malformed JSONL rows without crashing.
 */
export declare function isHSutraEvent(value: unknown): value is HSutraEvent;
//# sourceMappingURL=h-sutra-event.d.ts.map