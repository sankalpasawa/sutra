/**
 * Contract tests — ArtifactCatalog (D2 step 3 of vertical slice).
 *
 * Coverage:
 *   sha256 / CAS    — deterministic hash, idempotent content write
 *   path resolution — domain-attached layout (<root>/<id>/index.jsonl + content/)
 *                     invalid domain_id throws
 *                     invalid sha throws on resolveContentPath
 *   register()      — writes content + appends index row + returns frozen entry
 *                     producer_execution_id validation
 *                     consumes_sha256 validation (per-entry)
 *                     same content registered twice = idempotent content write
 *                     same content registered in TWO domains = two entries
 *   lookup          — getEntriesBySha returns [] for unknown,
 *                     [entry...] for known (insertion order)
 *                     getByDomain
 *                     getConsumersOf walks lineage edges
 *                     getByProducerExecution
 *   load            — loadDomain reads JSONL into memory (idempotent)
 *                     malformed rows dropped + counter incremented
 *                     getByDomain on unloaded domain triggers loadDomain
 *   immutability    — entries are deep-frozen (caller cannot mutate audit)
 */

import { describe, it, expect, beforeEach, afterEach } from 'vitest'
import {
  appendFileSync,
  existsSync,
  mkdirSync,
  mkdtempSync,
  readFileSync,
  rmSync,
  writeFileSync,
} from 'node:fs'
import { join } from 'node:path'
import { tmpdir } from 'node:os'
import {
  ArtifactCatalog,
  computeContentSha256,
  resolveDefaultRoot,
} from '../../../src/runtime/artifact-catalog.js'
import type { CatalogedAsset } from '../../../src/types/asset-catalog.js'
import type { Asset } from '../../../src/types/index.js'

function asset(over: Partial<Asset> = {}): Asset {
  return {
    kind: 'json',
    schema_ref: 'sutra://schema/test/v1',
    locator: 'cas://content',
    version: '1.0.0',
    mutability: 'immutable',
    retention: 'permanent',
    stable_identity: 'test-asset',
    lifecycle_states: ['draft', 'published'],
    ...over,
  }
}

describe('ArtifactCatalog — D2 step 3 contract', () => {
  let workdir: string
  let catalog: ArtifactCatalog

  beforeEach(() => {
    workdir = mkdtempSync(join(tmpdir(), 'artifact-catalog-test-'))
    catalog = new ArtifactCatalog({ root_dir: workdir })
  })

  afterEach(() => {
    if (existsSync(workdir)) rmSync(workdir, { recursive: true, force: true })
  })

  describe('computeContentSha256 (D2.3b — CAS)', () => {
    it('is deterministic across calls', () => {
      expect(computeContentSha256('hello world')).toBe(computeContentSha256('hello world'))
    })

    it('emits 64 hex chars', () => {
      expect(computeContentSha256('any')).toMatch(/^[0-9a-f]{64}$/)
    })

    it('differs for different inputs', () => {
      expect(computeContentSha256('a')).not.toBe(computeContentSha256('b'))
    })

    it('handles Buffer + string identically when bytes match', () => {
      expect(computeContentSha256(Buffer.from('xyz'))).toBe(computeContentSha256('xyz'))
    })
  })

  describe('path resolution (D2.3e — domain-attached resolver)', () => {
    it('resolveDomainDir = <root>/<domain_id>', () => {
      expect(catalog.resolveDomainDir('D38')).toBe(join(workdir, 'D38'))
    })

    it('resolveIndexPath = <root>/<domain_id>/index.jsonl', () => {
      expect(catalog.resolveIndexPath('D1')).toBe(join(workdir, 'D1', 'index.jsonl'))
    })

    it('resolveContentPath = <root>/<domain_id>/content/<sha>', () => {
      const sha = 'a'.repeat(64)
      expect(catalog.resolveContentPath('D1', sha)).toBe(join(workdir, 'D1', 'content', sha))
    })

    it('throws TypeError on invalid domain_id', () => {
      expect(() => catalog.resolveDomainDir('not-a-domain')).toThrow(TypeError)
      expect(() => catalog.resolveDomainDir('d1')).toThrow(TypeError) // lowercase d
    })

    it('throws TypeError on invalid sha for resolveContentPath', () => {
      expect(() => catalog.resolveContentPath('D1', 'short')).toThrow(TypeError)
      expect(() => catalog.resolveContentPath('D1', 'g'.repeat(64))).toThrow(TypeError) // non-hex
    })

    it('resolveDefaultRoot is <cwd>/holding/native/artifacts', () => {
      expect(resolveDefaultRoot('/tmp/x')).toBe('/tmp/x/holding/native/artifacts')
    })

    it('accepts dotted-decimal sub-domain ids (D1.D2.D3)', () => {
      expect(catalog.resolveDomainDir('D1.D2.D3')).toBe(join(workdir, 'D1.D2.D3'))
    })
  })

  describe('register (D2.3a + 3c + 3d)', () => {
    it('writes content file at content/<sha> and appends index.jsonl row', () => {
      const entry = catalog.register({
        domain_id: 'D1',
        content: 'hello world',
        asset: asset(),
      })
      const expectedSha = computeContentSha256('hello world')
      expect(entry.content_sha256).toBe(expectedSha)
      expect(existsSync(join(workdir, 'D1', 'content', expectedSha))).toBe(true)
      expect(existsSync(join(workdir, 'D1', 'index.jsonl'))).toBe(true)
      const row = readFileSync(join(workdir, 'D1', 'index.jsonl'), 'utf8').trim()
      expect(JSON.parse(row).content_sha256).toBe(expectedSha)
    })

    it('records cataloged_at_ms as a finite timestamp', () => {
      const before = Date.now()
      const entry = catalog.register({ domain_id: 'D1', content: 'x', asset: asset() })
      const after = Date.now()
      expect(entry.cataloged_at_ms).toBeGreaterThanOrEqual(before)
      expect(entry.cataloged_at_ms).toBeLessThanOrEqual(after)
    })

    it('idempotent — same content registered twice writes content file once', () => {
      const sha = computeContentSha256('same-bytes')
      catalog.register({ domain_id: 'D1', content: 'same-bytes', asset: asset() })
      const contentPath = join(workdir, 'D1', 'content', sha)
      const stat1 = readFileSync(contentPath, 'utf8')
      catalog.register({ domain_id: 'D1', content: 'same-bytes', asset: asset() })
      const stat2 = readFileSync(contentPath, 'utf8')
      expect(stat1).toBe(stat2)
      // BUT two index rows: catalog records each registration
      const rows = readFileSync(join(workdir, 'D1', 'index.jsonl'), 'utf8').trim().split('\n')
      expect(rows).toHaveLength(2)
    })

    it('same content registered in TWO domains creates two entries', () => {
      catalog.register({ domain_id: 'D1', content: 'shared', asset: asset() })
      catalog.register({ domain_id: 'D2', content: 'shared', asset: asset() })
      const sha = computeContentSha256('shared')
      const entries = catalog.getEntriesBySha(sha)
      expect(entries).toHaveLength(2)
      expect(entries.map((e) => e.domain_id).sort()).toEqual(['D1', 'D2'])
    })

    it('records producer_execution_id when provided', () => {
      const entry = catalog.register({
        domain_id: 'D1',
        content: 'p',
        asset: asset(),
        producer_execution_id: 'E-build-001',
      })
      expect(entry.producer_execution_id).toBe('E-build-001')
    })

    it('throws on invalid producer_execution_id', () => {
      expect(() =>
        catalog.register({
          domain_id: 'D1',
          content: 'p',
          asset: asset(),
          producer_execution_id: 'not-an-execution-id',
        }),
      ).toThrow(TypeError)
    })

    it('records consumes_sha256 lineage edges', () => {
      const upstreamSha = 'a'.repeat(64)
      const entry = catalog.register({
        domain_id: 'D1',
        content: 'down',
        asset: asset(),
        consumes_sha256: [upstreamSha],
      })
      expect(entry.consumes_sha256).toEqual([upstreamSha])
    })

    it('throws on invalid sha in consumes_sha256', () => {
      expect(() =>
        catalog.register({
          domain_id: 'D1',
          content: 'x',
          asset: asset(),
          consumes_sha256: ['not-a-sha'],
        }),
      ).toThrow(TypeError)
    })

    it('throws on invalid domain_id at register', () => {
      expect(() => catalog.register({ domain_id: 'd1', content: 'x', asset: asset() })).toThrow(TypeError)
    })
  })

  describe('lookup (D2.3a + 3d)', () => {
    it('getEntriesBySha returns [] for unknown sha', () => {
      expect(catalog.getEntriesBySha('a'.repeat(64))).toEqual([])
    })

    it('getEntriesBySha returns [] for syntactically invalid sha', () => {
      expect(catalog.getEntriesBySha('short')).toEqual([])
    })

    it('getByDomain returns insertion order', () => {
      catalog.register({ domain_id: 'D1', content: 'first', asset: asset() })
      catalog.register({ domain_id: 'D1', content: 'second', asset: asset() })
      catalog.register({ domain_id: 'D1', content: 'third', asset: asset() })
      const list = catalog.getByDomain('D1')
      expect(list.map((e) => e.content_sha256)).toEqual([
        computeContentSha256('first'),
        computeContentSha256('second'),
        computeContentSha256('third'),
      ])
    })

    it('getConsumersOf walks lineage', () => {
      const upstream = catalog.register({ domain_id: 'D1', content: 'up', asset: asset() })
      const down = catalog.register({
        domain_id: 'D1',
        content: 'down',
        asset: asset(),
        consumes_sha256: [upstream.content_sha256],
      })
      const consumers = catalog.getConsumersOf(upstream.content_sha256)
      expect(consumers.map((e) => e.content_sha256)).toEqual([down.content_sha256])
    })

    it('getConsumersOf returns [] for invalid sha', () => {
      expect(catalog.getConsumersOf('bad-sha')).toEqual([])
    })

    it('getByProducerExecution finds all entries by execution id', () => {
      catalog.register({
        domain_id: 'D1',
        content: 'a',
        asset: asset(),
        producer_execution_id: 'E-run-1',
      })
      catalog.register({
        domain_id: 'D2',
        content: 'b',
        asset: asset(),
        producer_execution_id: 'E-run-1',
      })
      catalog.register({
        domain_id: 'D1',
        content: 'c',
        asset: asset(),
        producer_execution_id: 'E-run-2',
      })
      expect(catalog.getByProducerExecution('E-run-1')).toHaveLength(2)
      expect(catalog.getByProducerExecution('E-run-2')).toHaveLength(1)
    })

    it('getByProducerExecution returns [] for invalid execution id', () => {
      expect(catalog.getByProducerExecution('not-an-id')).toEqual([])
    })
  })

  describe('loadDomain (cross-process replay)', () => {
    it('reads index.jsonl into memory + makes entries queryable', () => {
      // Write rows directly to disk (simulating prior process)
      const indexPath = join(workdir, 'D1', 'index.jsonl')
      mkdirSync(join(workdir, 'D1'), { recursive: true })
      const sha = computeContentSha256('preexisting')
      const entry = {
        content_sha256: sha,
        domain_id: 'D1',
        cataloged_at_ms: 1700000000000,
        asset: asset(),
        consumes_sha256: [],
      }
      writeFileSync(indexPath, JSON.stringify(entry) + '\n')

      // Fresh catalog (same root) — entry not visible yet
      const fresh = new ArtifactCatalog({ root_dir: workdir })
      // First call to getByDomain triggers loadDomain
      const list = fresh.getByDomain('D1')
      expect(list).toHaveLength(1)
      expect(list[0]?.content_sha256).toBe(sha)
    })

    it('loadDomain is idempotent (no double-counting)', () => {
      const indexPath = join(workdir, 'D1', 'index.jsonl')
      mkdirSync(join(workdir, 'D1'), { recursive: true })
      const sha = computeContentSha256('once')
      writeFileSync(
        indexPath,
        JSON.stringify({
          content_sha256: sha,
          domain_id: 'D1',
          cataloged_at_ms: 1700000000000,
          asset: asset(),
          consumes_sha256: [],
        }) + '\n',
      )
      const fresh = new ArtifactCatalog({ root_dir: workdir })
      fresh.loadDomain('D1')
      fresh.loadDomain('D1') // 2nd call should no-op
      expect(fresh.getByDomain('D1')).toHaveLength(1)
    })

    it('drops malformed JSONL rows + increments counter', () => {
      const indexPath = join(workdir, 'D1', 'index.jsonl')
      mkdirSync(join(workdir, 'D1'), { recursive: true })
      const goodSha = computeContentSha256('good')
      writeFileSync(
        indexPath,
        [
          'this is not json',
          JSON.stringify({ content_sha256: 'too-short', domain_id: 'D1' }), // valid JSON, bad shape
          JSON.stringify({
            content_sha256: goodSha,
            domain_id: 'D1',
            cataloged_at_ms: 1700000000000,
            asset: asset(),
            consumes_sha256: [],
          }),
        ].join('\n') + '\n',
      )
      const fresh = new ArtifactCatalog({ root_dir: workdir })
      fresh.loadDomain('D1')
      expect(fresh.getByDomain('D1')).toHaveLength(1)
      expect(fresh.getMalformedRowCount()).toBe(2)
    })

    it('loadDomain on missing index.jsonl is a no-op', () => {
      const fresh = new ArtifactCatalog({ root_dir: workdir })
      expect(() => fresh.loadDomain('D99')).not.toThrow()
      expect(fresh.getByDomain('D99')).toEqual([])
    })

    it('loadDomain on invalid domain_id is a no-op', () => {
      const fresh = new ArtifactCatalog({ root_dir: workdir })
      expect(() => fresh.loadDomain('not-a-domain')).not.toThrow()
    })
  })

  describe('immutability', () => {
    it('CatalogedAsset entries are deep-frozen on register', () => {
      const entry = catalog.register({ domain_id: 'D1', content: 'x', asset: asset() })
      expect(Object.isFrozen(entry)).toBe(true)
      expect(Object.isFrozen(entry.asset)).toBe(true)
      expect(Object.isFrozen(entry.consumes_sha256)).toBe(true)
      expect(() => {
        ;(entry as { content_sha256: string }).content_sha256 = 'hacked'
      }).toThrow()
    })

    it('Loaded entries are deep-frozen too', () => {
      const indexPath = join(workdir, 'D1', 'index.jsonl')
      mkdirSync(join(workdir, 'D1'), { recursive: true })
      writeFileSync(
        indexPath,
        JSON.stringify({
          content_sha256: computeContentSha256('y'),
          domain_id: 'D1',
          cataloged_at_ms: 1700000000000,
          asset: asset(),
          consumes_sha256: [],
        }) + '\n',
      )
      const fresh = new ArtifactCatalog({ root_dir: workdir })
      fresh.loadDomain('D1')
      const e = fresh.getByDomain('D1')[0]!
      expect(Object.isFrozen(e)).toBe(true)
    })
  })

  describe('concurrent-domain isolation', () => {
    it('appending to D1 does not pollute D2 index', () => {
      catalog.register({ domain_id: 'D1', content: 'a', asset: asset() })
      catalog.register({ domain_id: 'D2', content: 'b', asset: asset() })
      const d1Rows = readFileSync(join(workdir, 'D1', 'index.jsonl'), 'utf8')
        .trim()
        .split('\n')
      const d2Rows = readFileSync(join(workdir, 'D2', 'index.jsonl'), 'utf8')
        .trim()
        .split('\n')
      expect(d1Rows).toHaveLength(1)
      expect(d2Rows).toHaveLength(1)
      expect(JSON.parse(d1Rows[0]!).content_sha256).toBe(computeContentSha256('a'))
      expect(JSON.parse(d2Rows[0]!).content_sha256).toBe(computeContentSha256('b'))
    })
  })

  describe('Asset-shape strict validation (codex P1 fold 2026-05-03)', () => {
    it('register throws when asset missing stable_identity', () => {
      const bad = { ...asset() } as Partial<Asset>
      delete (bad as Record<string, unknown>).stable_identity
      expect(() =>
        catalog.register({ domain_id: 'D1', content: 'x', asset: bad as Asset }),
      ).toThrow(TypeError)
    })

    it('register throws on empty stable_identity', () => {
      expect(() =>
        catalog.register({
          domain_id: 'D1',
          content: 'x',
          asset: asset({ stable_identity: '' }),
        }),
      ).toThrow(TypeError)
    })

    it('register throws when lifecycle_states is not an array', () => {
      const bad = asset() as unknown as Record<string, unknown>
      bad.lifecycle_states = 'not-an-array'
      expect(() =>
        catalog.register({ domain_id: 'D1', content: 'x', asset: bad as unknown as Asset }),
      ).toThrow(TypeError)
    })

    it('register throws when lifecycle_states contains non-string', () => {
      const bad = asset() as unknown as Record<string, unknown>
      bad.lifecycle_states = ['draft', 42]
      expect(() =>
        catalog.register({ domain_id: 'D1', content: 'x', asset: bad as unknown as Asset }),
      ).toThrow(TypeError)
    })

    it('register throws on invalid mutability enum', () => {
      expect(() =>
        catalog.register({
          domain_id: 'D1',
          content: 'x',
          asset: asset({ mutability: 'maybe' as unknown as 'mutable' }),
        }),
      ).toThrow(TypeError)
    })

    it('register throws on invalid authoritative_status enum (when present)', () => {
      const bad = asset() as unknown as Record<string, unknown>
      bad.authoritative_status = 'maybe'
      expect(() =>
        catalog.register({ domain_id: 'D1', content: 'x', asset: bad as unknown as Asset }),
      ).toThrow(TypeError)
    })

    it('register accepts asset without authoritative_status (optional field)', () => {
      const ok = { ...asset() } as Partial<Asset>
      delete (ok as Record<string, unknown>).authoritative_status
      expect(() =>
        catalog.register({ domain_id: 'D1', content: 'x', asset: ok as Asset }),
      ).not.toThrow()
    })

    it('register throws on empty kind/schema_ref/locator', () => {
      expect(() =>
        catalog.register({ domain_id: 'D1', content: 'x', asset: asset({ kind: '' }) }),
      ).toThrow(TypeError)
      expect(() =>
        catalog.register({ domain_id: 'D1', content: 'x', asset: asset({ schema_ref: '' }) }),
      ).toThrow(TypeError)
      expect(() =>
        catalog.register({ domain_id: 'D1', content: 'x', asset: asset({ locator: '' }) }),
      ).toThrow(TypeError)
    })
  })

  describe('DOMAIN_ID dotted-form discipline (codex P2 fold 2026-05-03)', () => {
    it('rejects "D1.2" (sub-domain must be "D<digits>")', () => {
      expect(() => catalog.register({ domain_id: 'D1.2', content: 'x', asset: asset() })).toThrow(
        TypeError,
      )
    })

    it('rejects empty sub-segment "D1." ', () => {
      expect(() => catalog.register({ domain_id: 'D1.', content: 'x', asset: asset() })).toThrow(
        TypeError,
      )
    })

    it('accepts deeply nested D1.D2.D3.D4', () => {
      expect(() =>
        catalog.register({ domain_id: 'D1.D2.D3.D4', content: 'x', asset: asset() }),
      ).not.toThrow()
    })
  })

  describe('defensive-copy semantics (codex P2 fold 2026-05-03)', () => {
    it('getEntriesBySha — mutating returned array does not pollute internal Map', () => {
      const entry = catalog.register({ domain_id: 'D1', content: 'x', asset: asset() })
      const list = catalog.getEntriesBySha(entry.content_sha256) as CatalogedAsset[]
      list.pop()
      expect(catalog.getEntriesBySha(entry.content_sha256)).toHaveLength(1)
    })

    it('getByDomain — mutating returned array does not pollute internal Map', () => {
      catalog.register({ domain_id: 'D1', content: 'x', asset: asset() })
      const list = catalog.getByDomain('D1') as CatalogedAsset[]
      list.pop()
      expect(catalog.getByDomain('D1')).toHaveLength(1)
    })

    it('getConsumersOf returns a new array each call', () => {
      const up = catalog.register({ domain_id: 'D1', content: 'up', asset: asset() })
      catalog.register({
        domain_id: 'D1',
        content: 'down',
        asset: asset(),
        consumes_sha256: [up.content_sha256],
      })
      const a = catalog.getConsumersOf(up.content_sha256) as CatalogedAsset[]
      a.pop()
      expect(catalog.getConsumersOf(up.content_sha256)).toHaveLength(1)
    })
  })

  describe('loadDomain late-arrival recovery (codex P2 fold 2026-05-03)', () => {
    it('absent index.jsonl does NOT mark domain loaded — later writer becomes visible', () => {
      const fresh = new ArtifactCatalog({ root_dir: workdir })
      // First call: file does not exist → returns [], does NOT mark loaded
      expect(fresh.getByDomain('D1')).toEqual([])

      // External writer (simulate another process) creates the index.jsonl
      mkdirSync(join(workdir, 'D1'), { recursive: true })
      const sha = computeContentSha256('late')
      writeFileSync(
        join(workdir, 'D1', 'index.jsonl'),
        JSON.stringify({
          content_sha256: sha,
          domain_id: 'D1',
          cataloged_at_ms: 1700000000000,
          asset: asset(),
          consumes_sha256: [],
        }) + '\n',
      )

      // Subsequent call must pick up the new row
      const list = fresh.getByDomain('D1')
      expect(list).toHaveLength(1)
      expect(list[0]?.content_sha256).toBe(sha)
    })
  })

  // Imports retained for reference even though some are only used in a subset
  // of test setups above.
  void appendFileSync
})
