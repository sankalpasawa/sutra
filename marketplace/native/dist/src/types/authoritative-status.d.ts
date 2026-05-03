/**
 * AuthoritativeStatus — DataRef.authoritative_status enum (M4.6; D2 §5).
 *
 * Resolves the "markdown vs code source-of-truth" arbitration per D2 §5.2 by
 * making each artifact's standing explicit:
 * - `authoritative` → this DataRef IS the source of truth; others MUST conform
 * - `advisory`      → describes/hints; downstream may diverge
 *
 * Default value: `authoritative` (safest); explicit `advisory` must be declared.
 *
 * Drift detection (D2 §5.4) lands at M8 hooks; M4.6 ships only the field.
 *
 * Spec source:
 * - holding/research/2026-04-29-native-d2-decision-provenance-spec.md §5
 * - holding/plans/native-v1.0/M4-schemas-edges.md §M4.6
 */
import { z } from 'zod';
/**
 * Allowed authoritative-status values.
 */
export declare const AUTHORITATIVE_STATUS_VALUES: readonly ["authoritative", "advisory"];
/**
 * AuthoritativeStatusSchema — z.enum on the two values above.
 */
export declare const AuthoritativeStatusSchema: z.ZodEnum<{
    authoritative: "authoritative";
    advisory: "advisory";
}>;
export type AuthoritativeStatus = z.infer<typeof AuthoritativeStatusSchema>;
/**
 * Predicate: is this value a valid AuthoritativeStatus?
 */
export declare function isValidAuthoritativeStatus(v: unknown): v is AuthoritativeStatus;
//# sourceMappingURL=authoritative-status.d.ts.map