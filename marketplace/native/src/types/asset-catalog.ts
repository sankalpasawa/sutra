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

import type { Asset } from './index.js'

/** sha256 hex (lowercase, 64 chars). Canonical content-address id. */
export const SHA256_HEX_PATTERN = /^[0-9a-f]{64}$/

/**
 * Domain id — `D\d+` with optional dotted-decimal sub-domains. Mirrors the
 * canonical pattern in src/primitives/domain.ts (avoids a circular import).
 */
export const DOMAIN_ID_PATTERN = /^D\d+(\.D\d+)*$/

/** Execution id pattern — `E-...`. Mirrors src/primitives/execution.ts. */
export const EXECUTION_ID_PATTERN = /^E-.+$/

/**
 * A cataloged asset record. Once registered, ALL fields are deep-frozen so
 * downstream consumers (renderers, lineage walkers) cannot mutate the audit
 * trail. Emitted as one JSONL row per registration.
 */
export interface CatalogedAsset {
  /** sha256 of the raw content bytes (lowercase hex, 64 chars). Canonical id. */
  readonly content_sha256: string
  /** Owning Domain. Replay uses this to anchor the asset's path on disk. */
  readonly domain_id: string
  /** When the catalog received this asset (ms since epoch). */
  readonly cataloged_at_ms: number
  /** The full Asset record (deep-frozen on register). */
  readonly asset: Readonly<Asset>
  /** Optional Execution id that produced this content (replay attribution). */
  readonly producer_execution_id?: string
  /** Upstream content shas this asset consumed. Empty array when standalone. */
  readonly consumes_sha256: ReadonlyArray<string>
}

const MUTABILITY_VALUES: ReadonlySet<string> = new Set(['mutable', 'immutable'])
const AUTHORITATIVE_STATUS_VALUES: ReadonlySet<string> = new Set(['authoritative', 'advisory'])

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
export function isAssetShape(value: unknown): boolean {
  if (typeof value !== 'object' || value === null) return false
  const a = value as Record<string, unknown>

  // DataRef base fields — all non-empty strings
  if (typeof a.kind !== 'string' || a.kind.length === 0) return false
  if (typeof a.schema_ref !== 'string' || a.schema_ref.length === 0) return false
  if (typeof a.locator !== 'string' || a.locator.length === 0) return false
  if (typeof a.version !== 'string') return false
  if (typeof a.retention !== 'string') return false

  // mutability enum
  if (typeof a.mutability !== 'string' || !MUTABILITY_VALUES.has(a.mutability)) return false

  // authoritative_status: optional, but if present must be in enum
  if (a.authoritative_status !== undefined) {
    if (typeof a.authoritative_status !== 'string' || !AUTHORITATIVE_STATUS_VALUES.has(a.authoritative_status)) {
      return false
    }
  }

  // Asset-only L1 promotion fields
  if (typeof a.stable_identity !== 'string' || a.stable_identity.length === 0) return false
  if (!Array.isArray(a.lifecycle_states)) return false
  for (const s of a.lifecycle_states) {
    if (typeof s !== 'string' || s.length === 0) return false
  }

  return true
}

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
export function isCatalogedAsset(value: unknown): value is CatalogedAsset {
  if (typeof value !== 'object' || value === null) return false
  const v = value as Partial<CatalogedAsset> & Record<string, unknown>

  if (typeof v.content_sha256 !== 'string' || !SHA256_HEX_PATTERN.test(v.content_sha256)) return false
  if (typeof v.domain_id !== 'string' || !DOMAIN_ID_PATTERN.test(v.domain_id)) return false
  if (typeof v.cataloged_at_ms !== 'number' || !Number.isFinite(v.cataloged_at_ms) || v.cataloged_at_ms < 0) {
    return false
  }
  if (!isAssetShape(v.asset)) return false

  if (v.producer_execution_id !== undefined) {
    if (typeof v.producer_execution_id !== 'string' || !EXECUTION_ID_PATTERN.test(v.producer_execution_id)) {
      return false
    }
  }

  if (!Array.isArray(v.consumes_sha256)) return false
  for (const s of v.consumes_sha256) {
    if (typeof s !== 'string' || !SHA256_HEX_PATTERN.test(s)) return false
  }

  return true
}
