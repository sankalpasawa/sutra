/**
 * L1 DATA law — V2 spec §3 row L1
 *
 * Rule: "If lifecycle is exhausted by producer/consumer execution → DataRef.
 *        Else → Asset."
 *
 * Mechanization: Promotion check `stable_identity AND len(lifecycle_states) > 1`.
 *
 * Pure predicate. No side effects. Deterministic.
 *
 * Source-of-truth: holding/research/2026-04-28-v2-architecture-spec.md §3 L1
 */
import type { Asset, DataRef } from '../types/index.js';
export declare const l1Data: {
    /**
     * Should this data ref be promoted from DataRef → Asset?
     *
     * True iff:
     *   - `stable_identity` is present and a non-empty string, AND
     *   - `lifecycle_states` is an array of length > 1.
     *
     * Accepts either a plain DataRef (which lacks the Asset-only fields, so
     * always returns false) or a fully-populated Asset record (which can
     * return true). Defensive against deserialized records: every shape check
     * is explicit.
     */
    shouldPromoteToAsset(ref: DataRef | Asset | unknown): boolean;
};
//# sourceMappingURL=l1-data.d.ts.map