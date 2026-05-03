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

import { createHash } from 'node:crypto'
import {
  appendFileSync,
  existsSync,
  mkdirSync,
  readFileSync,
  writeFileSync,
} from 'node:fs'
import { join } from 'node:path'
import type { Asset } from '../types/index.js'
import {
  isAssetShape,
  isCatalogedAsset,
  DOMAIN_ID_PATTERN,
  EXECUTION_ID_PATTERN,
  SHA256_HEX_PATTERN,
  type CatalogedAsset,
} from '../types/asset-catalog.js'

/**
 * Recursive freeze. Same shape as router.deepFreeze (kept local here to
 * avoid cross-runtime imports). Cheap for our records — Asset is flat,
 * consumes_sha256 is a string array.
 */
function deepFreeze<T>(value: T): T {
  if (value === null || typeof value !== 'object') return value
  if (Object.isFrozen(value)) return value
  Object.freeze(value)
  for (const key of Object.keys(value)) {
    deepFreeze((value as Record<string, unknown>)[key])
  }
  return value
}

export interface ArtifactCatalogOptions {
  /** Override root dir. Default: <cwd>/holding/native/artifacts. */
  readonly root_dir?: string
}

export interface RegisterRequest {
  readonly domain_id: string
  readonly content: string | Buffer
  readonly asset: Asset
  /** Optional Execution id that produced this content. Must match EXECUTION_ID_PATTERN. */
  readonly producer_execution_id?: string
  /** Upstream content shas this asset depends on. Must each be valid sha256 hex. */
  readonly consumes_sha256?: ReadonlyArray<string>
}

/** Default root: Asawa override pattern, per Asawa convention. */
export function resolveDefaultRoot(cwd: string = process.cwd()): string {
  return join(cwd, 'holding/native/artifacts')
}

/**
 * Compute sha256 hex (lowercase, 64 chars) of arbitrary content. Public so
 * callers can pre-compute hashes for consumes_sha256 arrays without holding
 * a Catalog instance.
 */
export function computeContentSha256(content: string | Buffer): string {
  return createHash('sha256').update(content).digest('hex')
}

export class ArtifactCatalog {
  private readonly rootDir: string
  /** In-memory index: content_sha256 → CatalogedAsset[]. Loaded lazily per domain. */
  private readonly bySha = new Map<string, CatalogedAsset[]>()
  /** In-memory index: domain_id → CatalogedAsset[] (insertion-ordered). */
  private readonly byDomainMap = new Map<string, CatalogedAsset[]>()
  /** Domains whose index.jsonl has been read into memory. */
  private readonly loadedDomains = new Set<string>()

  constructor(options: ArtifactCatalogOptions = {}) {
    this.rootDir = options.root_dir ?? resolveDefaultRoot()
  }

  /** Per-domain directory: <root>/<domain_id>/. */
  resolveDomainDir(domain_id: string): string {
    if (!DOMAIN_ID_PATTERN.test(domain_id)) {
      throw new TypeError(`ArtifactCatalog: invalid domain_id "${domain_id}"`)
    }
    return join(this.rootDir, domain_id)
  }

  /** Per-domain index.jsonl path: <root>/<domain_id>/index.jsonl. */
  resolveIndexPath(domain_id: string): string {
    return join(this.resolveDomainDir(domain_id), 'index.jsonl')
  }

  /** Per-domain content path: <root>/<domain_id>/content/<sha256>. */
  resolveContentPath(domain_id: string, content_sha256: string): string {
    if (!SHA256_HEX_PATTERN.test(content_sha256)) {
      throw new TypeError(`ArtifactCatalog: invalid content_sha256 "${content_sha256}"`)
    }
    return join(this.resolveDomainDir(domain_id), 'content', content_sha256)
  }

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
  register(req: RegisterRequest): CatalogedAsset {
    if (!DOMAIN_ID_PATTERN.test(req.domain_id)) {
      throw new TypeError(`ArtifactCatalog.register: invalid domain_id "${req.domain_id}"`)
    }
    // Codex P1 fold 2026-05-03: validate Asset shape at WRITE-time too —
    // closes the "register persists / loadDomain rejects" inconsistency.
    if (!isAssetShape(req.asset)) {
      throw new TypeError(
        `ArtifactCatalog.register: req.asset is not a valid Asset (missing or malformed required field)`,
      )
    }
    if (req.producer_execution_id !== undefined && !EXECUTION_ID_PATTERN.test(req.producer_execution_id)) {
      throw new TypeError(
        `ArtifactCatalog.register: invalid producer_execution_id "${req.producer_execution_id}"`,
      )
    }
    const consumes = req.consumes_sha256 ?? []
    for (const s of consumes) {
      if (!SHA256_HEX_PATTERN.test(s)) {
        throw new TypeError(`ArtifactCatalog.register: invalid consumes_sha256 entry "${s}"`)
      }
    }

    const content_sha256 = computeContentSha256(req.content)

    const entry: CatalogedAsset = {
      content_sha256,
      domain_id: req.domain_id,
      cataloged_at_ms: Date.now(),
      asset: req.asset,
      ...(req.producer_execution_id !== undefined ? { producer_execution_id: req.producer_execution_id } : {}),
      consumes_sha256: [...consumes],
    }
    const frozen = deepFreeze(entry)

    // Side effects: ensure directory tree, write content (idempotent), append index row.
    const domainDir = this.resolveDomainDir(req.domain_id)
    const contentDir = join(domainDir, 'content')
    mkdirSync(contentDir, { recursive: true })

    const contentPath = this.resolveContentPath(req.domain_id, content_sha256)
    if (!existsSync(contentPath)) {
      writeFileSync(contentPath, req.content)
    }

    const indexPath = this.resolveIndexPath(req.domain_id)
    appendFileSync(indexPath, JSON.stringify(frozen) + '\n')

    // Update in-memory indexes (lazy-load other domains' indexes elsewhere).
    this.indexInMemory(frozen)
    this.loadedDomains.add(req.domain_id)

    return frozen
  }

  /**
   * Look up all cataloged entries with a given content_sha256. Multiple
   * Domains can catalog the same content; this returns one entry per Domain
   * that registered it. Returns [] when sha is unknown.
   */
  getEntriesBySha(content_sha256: string): ReadonlyArray<CatalogedAsset> {
    if (!SHA256_HEX_PATTERN.test(content_sha256)) return []
    return [...(this.bySha.get(content_sha256) ?? [])]
  }

  /** All cataloged entries owned by this Domain (insertion order). */
  getByDomain(domain_id: string): ReadonlyArray<CatalogedAsset> {
    if (!DOMAIN_ID_PATTERN.test(domain_id)) return []
    this.loadDomain(domain_id)
    return [...(this.byDomainMap.get(domain_id) ?? [])]
  }

  /** Entries whose `consumes_sha256` includes the given sha. */
  getConsumersOf(content_sha256: string): ReadonlyArray<CatalogedAsset> {
    if (!SHA256_HEX_PATTERN.test(content_sha256)) return []
    const out: CatalogedAsset[] = []
    for (const list of this.byDomainMap.values()) {
      for (const entry of list) {
        if (entry.consumes_sha256.includes(content_sha256)) out.push(entry)
      }
    }
    return out
  }

  /** Entries whose producer_execution_id equals the given Execution id. */
  getByProducerExecution(execution_id: string): ReadonlyArray<CatalogedAsset> {
    if (!EXECUTION_ID_PATTERN.test(execution_id)) return []
    const out: CatalogedAsset[] = []
    for (const list of this.byDomainMap.values()) {
      for (const entry of list) {
        if (entry.producer_execution_id === execution_id) out.push(entry)
      }
    }
    return out
  }

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
  loadDomain(domain_id: string): void {
    if (!DOMAIN_ID_PATTERN.test(domain_id)) return
    if (this.loadedDomains.has(domain_id)) return

    const indexPath = this.resolveIndexPath(domain_id)
    if (!existsSync(indexPath)) {
      // Don't mark loaded — a later append + retry can pick up the new file.
      return
    }

    let text: string
    try {
      text = readFileSync(indexPath, 'utf8')
    } catch {
      // Don't mark loaded on read failure — caller can retry.
      return
    }

    if (text.length > 0) {
      const seen = this.seenSignatures(domain_id)
      const lines = text.split('\n')
      for (const line of lines) {
        if (line.length === 0) continue
        let parsed: unknown
        try {
          parsed = JSON.parse(line)
        } catch {
          this.malformedRowCount++
          continue
        }
        if (!isCatalogedAsset(parsed)) {
          this.malformedRowCount++
          continue
        }
        const sig = `${parsed.content_sha256}|${parsed.domain_id}|${parsed.cataloged_at_ms}`
        if (seen.has(sig)) continue
        seen.add(sig)
        this.indexInMemory(deepFreeze(parsed))
      }
    }

    this.loadedDomains.add(domain_id)
  }

  /** Compute the in-memory dedup signature set for a Domain. */
  private seenSignatures(domain_id: string): Set<string> {
    const set = new Set<string>()
    for (const entry of this.byDomainMap.get(domain_id) ?? []) {
      set.add(`${entry.content_sha256}|${entry.domain_id}|${entry.cataloged_at_ms}`)
    }
    return set
  }

  private malformedRowCount = 0

  /** Diagnostics: how many JSONL rows failed validation during load. */
  getMalformedRowCount(): number {
    return this.malformedRowCount
  }

  private indexInMemory(entry: CatalogedAsset): void {
    const shaList = this.bySha.get(entry.content_sha256) ?? []
    shaList.push(entry)
    this.bySha.set(entry.content_sha256, shaList)

    const domainList = this.byDomainMap.get(entry.domain_id) ?? []
    domainList.push(entry)
    this.byDomainMap.set(entry.domain_id, domainList)
  }
}
