/**
 * ArtifactCatalog — D2 step 3 of vertical slice.
 *
 * Domain-attached, content-addressable artifact catalog. Workflows produce
 * Assets; the catalog assigns each one a sha256 of its raw content + writes
 * an append-only JSONL row that downstream Workflows + Renderers consume by
 * deterministic id.
 *
 * Filesystem layout (per-Domain, sovereignty-anchored per L5 META law):
 *
 *   <root_dir>/
 *     <domain_id>/
 *       index.jsonl              ← append-only catalog (one CatalogedAsset per row)
 *       content/<sha256>         ← raw bytes (content-addressable storage)
 *
 * Default root_dir: <cwd>/holding/native/artifacts (Asawa override pattern,
 * mirrors resolveHSutraLogPath in h-sutra-connector). T4 fleet supplies its
 * own root via constructor.
 *
 * Per softened I-NPD-1: every register() call records a CatalogedAsset with
 * content_sha256 + cataloged_at_ms + producer_execution_id + consumes_sha256;
 * replay reads index.jsonl in order and reconstructs the same lineage DAG.
 *
 * Per C10: Native does NOT mutate or delete cataloged content. Append-only.
 * Operators retire content via filesystem operations outside the catalog.
 */
import type { Asset } from '../types/index.js';
import { type CatalogedAsset } from '../types/asset-catalog.js';
export interface ArtifactCatalogOptions {
    /** Override root dir. Default: <cwd>/holding/native/artifacts. */
    readonly root_dir?: string;
}
export interface RegisterRequest {
    readonly domain_id: string;
    readonly content: string | Buffer;
    readonly asset: Asset;
    /** Optional Execution id that produced this content. Must match EXECUTION_ID_PATTERN. */
    readonly producer_execution_id?: string;
    /** Upstream content shas this asset depends on. Must each be valid sha256 hex. */
    readonly consumes_sha256?: ReadonlyArray<string>;
}
/** Default root: Asawa override pattern, per Asawa convention. */
export declare function resolveDefaultRoot(cwd?: string): string;
/**
 * Compute sha256 hex (lowercase, 64 chars) of arbitrary content. Public so
 * callers can pre-compute hashes for consumes_sha256 arrays without holding
 * a Catalog instance.
 */
export declare function computeContentSha256(content: string | Buffer): string;
export declare class ArtifactCatalog {
    private readonly rootDir;
    /** In-memory index: content_sha256 → CatalogedAsset[]. Loaded lazily per domain. */
    private readonly bySha;
    /** In-memory index: domain_id → CatalogedAsset[] (insertion-ordered). */
    private readonly byDomainMap;
    /** Domains whose index.jsonl has been read into memory. */
    private readonly loadedDomains;
    constructor(options?: ArtifactCatalogOptions);
    /** Per-domain directory: <root>/<domain_id>/. */
    resolveDomainDir(domain_id: string): string;
    /** Per-domain index.jsonl path: <root>/<domain_id>/index.jsonl. */
    resolveIndexPath(domain_id: string): string;
    /** Per-domain content path: <root>/<domain_id>/content/<sha256>. */
    resolveContentPath(domain_id: string, content_sha256: string): string;
    /**
     * Register an Asset with raw content. Computes sha256, writes content to
     * disk (idempotent — same sha is safe to re-register), appends one row
     * to index.jsonl, returns the deep-frozen CatalogedAsset.
     *
     * Throws TypeError on:
     *   - invalid domain_id
     *   - invalid producer_execution_id (when present)
     *   - invalid sha in consumes_sha256
     */
    register(req: RegisterRequest): CatalogedAsset;
    /**
     * Look up all cataloged entries with a given content_sha256. Multiple
     * Domains can catalog the same content; this returns one entry per Domain
     * that registered it. Returns [] when sha is unknown.
     */
    getEntriesBySha(content_sha256: string): ReadonlyArray<CatalogedAsset>;
    /** All cataloged entries owned by this Domain (insertion order). */
    getByDomain(domain_id: string): ReadonlyArray<CatalogedAsset>;
    /** Entries whose `consumes_sha256` includes the given sha. */
    getConsumersOf(content_sha256: string): ReadonlyArray<CatalogedAsset>;
    /** Entries whose producer_execution_id equals the given Execution id. */
    getByProducerExecution(execution_id: string): ReadonlyArray<CatalogedAsset>;
    /**
     * Force-load a Domain's index.jsonl into memory. Useful for cross-process
     * replay where a fresh Catalog instance needs to see prior registrations.
     *
     * Codex P2 fold 2026-05-03: the "loaded" mark is set AFTER a successful
     * read so:
     *   - missing index.jsonl is NOT marked loaded (later append + retry works)
     *   - transient read failure is NOT marked loaded (caller can retry)
     *   - already-loaded domain still no-ops (idempotent on success)
     *
     * Re-loading the same index.jsonl is also idempotent: every entry already
     * present in the in-memory map is skipped via dedup keyed on the JSON
     * encoding of (content_sha256, domain_id, cataloged_at_ms).
     *
     * Malformed rows are dropped silently with a counter; the counter is
     * exposed via `getMalformedRowCount()`.
     */
    loadDomain(domain_id: string): void;
    /** Compute the in-memory dedup signature set for a Domain. */
    private seenSignatures;
    private malformedRowCount;
    /** Diagnostics: how many JSONL rows failed validation during load. */
    getMalformedRowCount(): number;
    private indexInMemory;
}
//# sourceMappingURL=artifact-catalog.d.ts.map