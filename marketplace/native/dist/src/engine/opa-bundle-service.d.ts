/**
 * OPA bundle service — M7 Group V (T-089).
 *
 * In-memory store for `CompiledPolicy` records produced by Group U's
 * `compileCharter`. Policies are keyed by (`policy_id`, `policy_version`); the
 * latest registered version wins for unversioned `get()` lookups, and every
 * version remains addressable so Group V's evaluator can pin to a specific
 * compiler revision when needed (audit trail per M8 OTel emission).
 *
 * Determinism contract (sovereignty foundation):
 * - Idempotent on `policy_version` collision: registering the same compiled
 *   policy twice is a no-op (same rego_source + same compiler version → same
 *   hash, so the second register just overwrites with identical content).
 * - The bundle service does NOT compile, parse, or rewrite Rego — it is a
 *   pure storage layer. All Rego shape decisions live in
 *   `charter-rego-compiler.ts`.
 * - No I/O: reads and writes are in-memory only. Persistence (e.g. SQLite
 *   bundle cache, signed-bundle distribution) is a future concern; the v1.0
 *   contract treats the service as session-scoped state owned by the runtime.
 *
 * Source-of-truth:
 *  - holding/plans/native-v1.0/M7-opa-compiler.md Group V T-089
 *  - holding/research/2026-04-29-native-v1.0-final-architecture.md §6
 */
import type { CompiledPolicy } from './charter-rego-compiler.js';
/**
 * Versioned in-memory bundle store.
 *
 * Internal shape:
 *   bundles: Map<policy_id, Map<policy_version, CompiledPolicy>>
 *   latest:  Map<policy_id, policy_version>
 *
 * The "latest" map records the most recently registered version for each
 * `policy_id`. Unversioned `get(policy_id)` returns that version; this lets
 * the dispatcher dispatch the active policy without threading a version
 * through every call site, while still permitting version-pinned audit
 * lookups via `get(policy_id, policy_version)`.
 */
export declare class OPABundleService {
    private readonly bundles;
    private readonly latest;
    /**
     * Register a compiled policy. The (policy_id, policy_version) tuple is the
     * cache key; subsequent registrations of the same tuple overwrite the prior
     * entry (idempotent — same Charter + same compiler → same hash → same
     * content). The most recently registered version is recorded as the
     * `latest` for unversioned lookups.
     */
    register(policy: CompiledPolicy): void;
    /**
     * Remove all versions of a policy. Used when the parent Charter is
     * decommissioned (V2 §1 Charter.termination criteria met) or replaced
     * by a successor with a different `policy_id`.
     */
    unregister(policy_id: string): void;
    /**
     * Look up a compiled policy. When `policy_version` is omitted, returns the
     * most recently registered version. Returns `null` when no matching record
     * exists — callers MUST handle the missing case (typically by treating it
     * as a deny per sovereignty discipline; the evaluator never fabricates a
     * policy).
     */
    get(policy_id: string, policy_version?: string): CompiledPolicy | null;
    /**
     * List every registered version for a `policy_id` in the order they were
     * inserted (Map iteration order is insertion order in JS). Returns an
     * empty array when the policy is unknown — never throws.
     */
    list_versions(policy_id: string): string[];
}
//# sourceMappingURL=opa-bundle-service.d.ts.map