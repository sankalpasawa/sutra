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
export const l1Data = {
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
    shouldPromoteToAsset(ref) {
        if (typeof ref !== 'object' || ref === null)
            return false;
        const r = ref;
        // V2 §3 L1 mechanization step 1: stable_identity must be present + non-empty string.
        if (!('stable_identity' in r))
            return false;
        if (typeof r.stable_identity !== 'string')
            return false;
        if (r.stable_identity.length === 0)
            return false;
        // V2 §3 L1 mechanization step 2: lifecycle_states.length > 1.
        if (!('lifecycle_states' in r))
            return false;
        if (!Array.isArray(r.lifecycle_states))
            return false;
        if (r.lifecycle_states.length <= 1)
            return false;
        return true;
    },
};
//# sourceMappingURL=l1-data.js.map