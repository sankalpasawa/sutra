/**
 * Regression gate for the M12 §5.2 deferred bug — surfaced 2026-05-01 on
 * standalone curl|bash install: the dogfood script's default artifactDir
 * used `resolve(packageRoot, '..', '..', '..', '.enforcement', ...)` which
 * only resolved correctly when Native was at sutra/marketplace/native/ inside
 * asawa-holding. In a standalone install (`/tmp/<dir>/native`) the ancestor
 * traversal walked off the filesystem root and G-5 crashed with mkdir EACCES.
 *
 * This test asserts the default artifactDir lands INSIDE the package root,
 * so the dogfood works identically in both deployment shapes.
 *
 * Spec source:
 *   - holding/research/2026-04-30-native-asawa-dogfood-findings.md §5.2
 *   - .enforcement/codex-reviews/2026-04-30-m12-pre-dispatch.md (deferred gap)
 */
import { describe, it, expect } from 'vitest'
import { rmSync } from 'node:fs'
import { resolve, dirname } from 'node:path'
import { fileURLToPath } from 'node:url'

import { runDogfood } from '../../scripts/dogfood-time-to-value.js'

const here = dirname(fileURLToPath(import.meta.url))
const packageRoot = resolve(here, '..', '..')

describe('Native dogfood — default artifactDir lands inside package root', () => {
  it('artifact directory is a descendant of the package root, not an ancestor', async () => {
    // Run with no artifactDir override — exercises the default path.
    const result = await runDogfood({ stubInstall: true, silent: true })

    const expectedPrefix = resolve(packageRoot, '.enforcement') + '/'

    try {
      expect(result.artifact_path).toBeDefined()
      expect(result.artifact_path.startsWith(expectedPrefix)).toBe(true)
      expect(result.verdict).toBe('PASS')
    } finally {
      try {
        rmSync(dirname(result.artifact_path), { recursive: true, force: true })
      } catch {
        // ignore cleanup error
      }
    }
  }, 30_000)

  it('default artifactDir does not start at filesystem root', async () => {
    const result = await runDogfood({ stubInstall: true, silent: true })

    try {
      expect(result.artifact_path.startsWith('/.')).toBe(false)
    } finally {
      try {
        rmSync(dirname(result.artifact_path), { recursive: true, force: true })
      } catch {
        // ignore
      }
    }
  }, 30_000)
})
