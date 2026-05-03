/**
 * CatalogedAsset — D2 step 3 of vertical slice.
 *
 * Adds content-addressable + lineage metadata to the existing Asset
 * primitive (V2 §2 + L1 promotion law). Native v1.0 ships an artifact
 * catalog so:
 *   - Workflows can produce typed outputs that downstream Workflows can
 *     reference by deterministic content hash (sha256 of bytes).
 *   - The audit trail records which Execution produced which content + what
 *     prior assets it consumed (replay can rebuild the lineage DAG).
 *   - A Domain owns its own artifact tree on disk (sovereignty per L5 META
 *     law: Tenant OWNS Domain; Domain CONTAINS Charter; Asset is anchored
 *     to a single owning Domain).
 *
 * Per founder direction 2026-05-02 + C8: storage is local filesystem at
 * v1.0 (no cloud blob store). The catalog appends to `index.jsonl` per
 * domain; content bytes live next to the index in `content/<sha256>`.
 *
 * I-NPD-1 audit semantics: every register() call produces a CatalogedAsset
 * with content_sha256 (canonical id), domain_id (owner), cataloged_at_ms,
 * optional producer_execution_id, and optional consumes_sha256[] (lineage
 * edges). Replay from the JSONL stream reconstructs the same DAG.
 */
import type { Asset } from './index.js';
/** sha256 hex (lowercase, 64 chars). Canonical content-address id. */
export declare const SHA256_HEX_PATTERN: RegExp;
/**
 * Domain id — `D\d+` with optional dotted-decimal sub-domains. Mirrors the
 * canonical pattern in src/primitives/domain.ts (avoids a circular import).
 */
export declare const DOMAIN_ID_PATTERN: RegExp;
/** Execution id pattern — `E-...`. Mirrors src/primitives/execution.ts. */
export declare const EXECUTION_ID_PATTERN: RegExp;
/**
 * A cataloged asset record. Once registered, ALL fields are deep-frozen so
 * downstream consumers (renderers, lineage walkers) cannot mutate the audit
 * trail. Emitted as one JSONL row per registration.
 */
export interface CatalogedAsset {
    /** sha256 of the raw content bytes (lowercase hex, 64 chars). Canonical id. */
    readonly content_sha256: string;
    /** Owning Domain. Replay uses this to anchor the asset's path on disk. */
    readonly domain_id: string;
    /** When the catalog received this asset (ms since epoch). */
    readonly cataloged_at_ms: number;
    /** The full Asset record (deep-frozen on register). */
    readonly asset: Readonly<Asset>;
    /** Optional Execution id that produced this content (replay attribution). */
    readonly producer_execution_id?: string;
    /** Upstream content shas this asset consumed. Empty array when standalone. */
    readonly consumes_sha256: ReadonlyArray<string>;
}
/**
 * Strict structural validity for the embedded Asset shape. Used by both
 * `isCatalogedAsset()` (load path) and `ArtifactCatalog.register()` (write
 * path) per codex P1 fold 2026-05-03 — write-path validation closes the
 * "register persists, loadDomain rejects" inconsistency.
 *
 * Asset = DataRef + L1-promotion fields (`stable_identity`,
 * `lifecycle_states`). All required fields must be present, with the right
 * types, and `mutability` / `authoritative_status` are validated against
 * their enums.
 *
 * Returns true iff the value is an Asset-shaped object. Never throws.
 */
export declare function isAssetShape(value: unknown): boolean;
/**
 * Structural type guard for a CatalogedAsset row read off disk. Defensive
 * against malformed JSONL rows; never throws. Callers (e.g. ArtifactCatalog
 * load path) drop rows that fail this guard.
 *
 * Validates:
 *   - content_sha256 matches SHA256_HEX_PATTERN
 *   - domain_id matches DOMAIN_ID_PATTERN
 *   - cataloged_at_ms is a finite non-negative number
 *   - asset passes isAssetShape() — full Asset validation incl. L1 promotion
 *     fields + mutability enum (codex P1 fold 2026-05-03)
 *   - producer_execution_id (when present) matches EXECUTION_ID_PATTERN
 *   - consumes_sha256 is an array of valid sha256 hex strings (may be empty)
 */
export declare function isCatalogedAsset(value: unknown): value is CatalogedAsset;
//# sourceMappingURL=asset-catalog.d.ts.map