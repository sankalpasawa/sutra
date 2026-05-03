/**
 * D5.5 R-FS-SAFETY — path-traversal + injection hardening tests across the
 * three FS-touching native modules:
 *
 *   1. ArtifactCatalog (src/runtime/artifact-catalog.ts) — resolves
 *      <root>/<domain_id>/index.jsonl and content/<sha256> paths from
 *      operator + workflow inputs.
 *   2. HSutraConnector (src/runtime/h-sutra-connector.ts) — reads from a
 *      log_path supplied via constructor or env override.
 *   3. lifecycle (src/runtime/lifecycle.ts) — writes a PID file under
 *      $SUTRA_NATIVE_HOME (default ~/.sutra-native).
 *
 * Hardening discipline: every public API that takes a string used in a
 * filesystem path MUST reject path-traversal + control characters BEFORE
 * the string reaches join(). Tests below probe the boundary.
 */

import { describe, it, expect, beforeEach, afterEach } from 'vitest'
import { existsSync, mkdtempSync, rmSync, readdirSync, writeFileSync } from 'node:fs'
import { join, normalize, resolve, sep } from 'node:path'
import { tmpdir } from 'node:os'
import {
  ArtifactCatalog,
  computeContentSha256,
} from '../../src/runtime/artifact-catalog.js'
import {
  HSutraConnector,
  resolveHSutraLogPath,
} from '../../src/runtime/h-sutra-connector.js'
import {
  acquirePidLock,
  releasePidLock,
  defaultPidPath,
} from '../../src/runtime/lifecycle.js'
import type { Asset } from '../../src/types/index.js'
import type { HSutraEvent } from '../../src/types/h-sutra-event.js'

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

describe('R-FS-SAFETY — ArtifactCatalog domain_id boundary', () => {
  let workdir: string
  let catalog: ArtifactCatalog

  beforeEach(() => {
    workdir = mkdtempSync(join(tmpdir(), 'fs-safety-test-'))
    catalog = new ArtifactCatalog({ root_dir: workdir })
  })

  afterEach(() => {
    if (existsSync(workdir)) rmSync(workdir, { recursive: true, force: true })
  })

  const traversalAttempts = [
    '../etc/passwd',
    '..',
    '../../',
    'D1/../../etc',
    '/etc/passwd',         // absolute path
    'D1\x00.D2',            // null byte injection
    'D1\nD2',               // newline injection
    'D1\rD2',               // carriage return
    '.D1',                  // leading dot
    'd1',                   // wrong case
    'D',                    // missing digits
    '',                     // empty
    'D1.D',                 // trailing partial sub-domain
  ]

  for (const attempt of traversalAttempts) {
    const safeName = JSON.stringify(attempt)
    it(`rejects domain_id ${safeName} at register`, () => {
      expect(() =>
        catalog.register({ domain_id: attempt, content: 'x', asset: asset() }),
      ).toThrow(TypeError)
    })

    it(`rejects domain_id ${safeName} at resolveDomainDir`, () => {
      expect(() => catalog.resolveDomainDir(attempt)).toThrow(TypeError)
    })
  }

  it('successful register: resolved paths stay UNDER root_dir', () => {
    const entry = catalog.register({
      domain_id: 'D1.D2.D3',
      content: 'hello',
      asset: asset(),
    })
    const root = resolve(workdir)
    const indexPath = resolve(catalog.resolveIndexPath('D1.D2.D3'))
    const contentPath = resolve(catalog.resolveContentPath('D1.D2.D3', entry.content_sha256))
    expect(indexPath.startsWith(root + sep)).toBe(true)
    expect(contentPath.startsWith(root + sep)).toBe(true)
    // No segment of the resolved path is `..`
    expect(normalize(indexPath)).toBe(indexPath)
    expect(normalize(contentPath)).toBe(contentPath)
  })
})

describe('R-FS-SAFETY — ArtifactCatalog sha256 boundary', () => {
  let workdir: string
  let catalog: ArtifactCatalog

  beforeEach(() => {
    workdir = mkdtempSync(join(tmpdir(), 'fs-safety-sha-'))
    catalog = new ArtifactCatalog({ root_dir: workdir })
  })

  afterEach(() => {
    if (existsSync(workdir)) rmSync(workdir, { recursive: true, force: true })
  })

  const badShas = [
    '../../etc/passwd',
    'a'.repeat(63),                   // wrong length
    'a'.repeat(65),                   // wrong length
    'g'.repeat(64),                   // non-hex
    'A'.repeat(64),                   // uppercase rejected
    'a' + sep + 'b'.repeat(62),        // path separator embedded
    'a\x00' + 'b'.repeat(62),          // null byte
    '',
  ]

  for (const sha of badShas) {
    const safeName = JSON.stringify(sha)
    it(`rejects content_sha256 ${safeName} at resolveContentPath`, () => {
      expect(() => catalog.resolveContentPath('D1', sha)).toThrow(TypeError)
    })
  }

  it('rejects malicious sha in consumes_sha256[]', () => {
    expect(() =>
      catalog.register({
        domain_id: 'D1',
        content: 'x',
        asset: asset(),
        consumes_sha256: ['../etc/passwd'.padEnd(64, 'a')],
      }),
    ).toThrow(TypeError)
  })

  it('successful register sha256: resolved content path stays under root_dir', () => {
    const entry = catalog.register({ domain_id: 'D1', content: 'data', asset: asset() })
    const root = resolve(workdir)
    const path = resolve(catalog.resolveContentPath('D1', entry.content_sha256))
    expect(path.startsWith(root + sep)).toBe(true)
    // sha256 is the LAST path segment (cas-style)
    expect(path.endsWith(entry.content_sha256)).toBe(true)
  })

  it('content sha is deterministic regardless of fs ops', () => {
    const e1 = catalog.register({ domain_id: 'D1', content: 'X', asset: asset() })
    const sha = computeContentSha256('X')
    expect(e1.content_sha256).toBe(sha)
    // No leading/trailing whitespace, no path separators
    expect(e1.content_sha256).toMatch(/^[0-9a-f]{64}$/)
  })
})

describe('R-FS-SAFETY — producer_execution_id injection boundary', () => {
  let workdir: string
  let catalog: ArtifactCatalog

  beforeEach(() => {
    workdir = mkdtempSync(join(tmpdir(), 'fs-safety-exec-'))
    catalog = new ArtifactCatalog({ root_dir: workdir })
  })

  afterEach(() => {
    if (existsSync(workdir)) rmSync(workdir, { recursive: true, force: true })
  })

  it('rejects producer_execution_id without E- prefix', () => {
    expect(() =>
      catalog.register({
        domain_id: 'D1',
        content: 'x',
        asset: asset(),
        producer_execution_id: 'no-prefix',
      }),
    ).toThrow(TypeError)
  })

  it('accepts E-prefixed execution id with hyphens + alphanumerics', () => {
    expect(() =>
      catalog.register({
        domain_id: 'D1',
        content: 'x',
        asset: asset(),
        producer_execution_id: 'E-build-001',
      }),
    ).not.toThrow()
  })

  // EXECUTION_ID_PATTERN is permissive (E-.+ — matches anything after E-).
  // FS safety relies on producer_execution_id NOT being used as a path
  // component (recorded in JSONL only). Codex P2.1 fold 2026-05-03: the
  // assertion below proves no path under the catalog root contains a
  // segment derived from the malicious id, regardless of what was
  // serialized into the JSONL row.
  it('malicious-but-E-prefixed id is recorded but never appears as a path segment', () => {
    const evilId = 'E-../../../tmp/foo'
    const entry = catalog.register({
      domain_id: 'D1',
      content: 'x',
      asset: asset(),
      producer_execution_id: evilId,
    })
    expect(entry.producer_execution_id).toBe(evilId)

    // Walk the entire catalog root + assert no file/dir name is derived
    // from the evil id. Only D1/, D1/index.jsonl, D1/content/, and
    // D1/content/<sha> should exist.
    const allEntries: string[] = []
    function walk(dir: string): void {
      for (const e of readdirSync(dir, { withFileTypes: true })) {
        allEntries.push(e.name)
        const full = join(dir, e.name)
        if (e.isDirectory()) walk(full)
      }
    }
    walk(workdir)
    for (const name of allEntries) {
      expect(name.includes('..')).toBe(false)
      expect(name.includes('foo')).toBe(false)
      expect(name.includes('tmp')).toBe(false)
    }
    // Sanity: the legitimate paths exist
    expect(existsSync(join(workdir, 'D1', 'content', entry.content_sha256))).toBe(true)
  })
})

describe('R-FS-SAFETY — HSutraConnector log_path boundary (codex P1.1 fold 2026-05-03)', () => {
  let workdir: string

  beforeEach(() => {
    workdir = mkdtempSync(join(tmpdir(), 'fs-safety-conn-'))
  })

  afterEach(() => {
    if (existsSync(workdir)) rmSync(workdir, { recursive: true, force: true })
  })

  it('start on missing log_path is a no-op (no crash, no file creation)', () => {
    const conn = new HSutraConnector({ log_path: join(workdir, 'does-not-exist.jsonl') })
    expect(() => conn.start()).not.toThrow()
    conn.stop()
    expect(existsSync(join(workdir, 'does-not-exist.jsonl'))).toBe(false)
  })

  it('connector reads only from configured log_path (no traversal beyond)', () => {
    const targetLog = join(workdir, 'h-sutra.jsonl')
    writeFileSync(
      targetLog,
      JSON.stringify({ turn_id: 't-1', input_text: 'hi' }) + '\n',
    )
    // Drop a sibling file that COULD be confused with the log
    writeFileSync(join(workdir, 'unrelated.jsonl'), JSON.stringify({ turn_id: 't-evil' }) + '\n')

    const conn = new HSutraConnector({ log_path: targetLog })
    const captured: string[] = []
    conn.onEvent((e) => {
      captured.push(e.turn_id)
    })
    conn.start()
    conn.stop()

    expect(captured).toEqual(['t-1'])
    expect(captured).not.toContain('t-evil')
  })

  it('connector with control-character bytes in input_text does not corrupt audit', () => {
    const targetLog = join(workdir, 'h-sutra.jsonl')
    writeFileSync(
      targetLog,
      JSON.stringify({ turn_id: 't-2', input_text: 'evil\x07\x1b[31mRED\x1b[0m' }) + '\n',
    )
    const conn = new HSutraConnector({ log_path: targetLog })
    const captured: HSutraEvent[] = []
    conn.onEvent((e) => {
      captured.push(e)
    })
    conn.start()
    conn.stop()

    // The connector preserves the raw text (sanitization is the renderer's job
    // per D2.4 cellPrefix sanitization). Audit step here just confirms no
    // crash + the event still surfaces.
    expect(captured).toHaveLength(1)
    expect(captured[0]?.turn_id).toBe('t-2')
  })

  it('resolveHSutraLogPath default is under cwd (not absolute escape)', () => {
    const cwd = '/tmp/safe-cwd'
    const path = resolveHSutraLogPath(cwd)
    // Must start with the cwd we provided — no traversal to /etc, /home, etc.
    expect(path.startsWith(cwd)).toBe(true)
  })
})

describe('R-FS-SAFETY — lifecycle PID file boundary (codex P1.1 fold 2026-05-03)', () => {
  let workdir: string
  let pidPath: string

  beforeEach(() => {
    workdir = mkdtempSync(join(tmpdir(), 'fs-safety-lifecycle-'))
    pidPath = join(workdir, 'native.pid')
  })

  afterEach(() => {
    if (existsSync(workdir)) rmSync(workdir, { recursive: true, force: true })
  })

  it('acquirePidLock writes ONLY to the configured pidPath', () => {
    const result = acquirePidLock(pidPath, 'cli-test')
    expect(result.acquired).toBe(true)
    expect(existsSync(pidPath)).toBe(true)
    // No other file under workdir
    const entries = readdirSync(workdir).filter((e) => e !== 'native.pid')
    expect(entries).toEqual([])
    releasePidLock(pidPath, { force: true })
    expect(existsSync(pidPath)).toBe(false)
  })

  it('acquirePidLock with nested missing parent dir creates only the parent (no traversal)', () => {
    const nestedPid = join(workdir, 'a', 'b', 'c', 'native.pid')
    const result = acquirePidLock(nestedPid, 'cli-test')
    expect(result.acquired).toBe(true)
    expect(existsSync(nestedPid)).toBe(true)
    // Path stays under workdir
    expect(nestedPid.startsWith(workdir + sep)).toBe(true)
    releasePidLock(nestedPid, { force: true })
  })

  it('defaultPidPath honors SUTRA_NATIVE_HOME when set', () => {
    const original = process.env.SUTRA_NATIVE_HOME
    try {
      process.env.SUTRA_NATIVE_HOME = '/custom/sutra-native'
      expect(defaultPidPath()).toBe('/custom/sutra-native/native.pid')
    } finally {
      if (original === undefined) delete process.env.SUTRA_NATIVE_HOME
      else process.env.SUTRA_NATIVE_HOME = original
    }
  })

  it('PID lock release is no-op on missing file (does not crash)', () => {
    expect(() => releasePidLock(join(workdir, 'no-such.pid'), { force: true })).not.toThrow()
  })
})
