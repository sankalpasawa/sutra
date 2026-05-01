/**
 * Regression gate for the M11 dogfood ENOENT surfaced 2026-05-01 on first
 * `curl …/native/install | bash` adopt: readMarketplaceString resolved
 * `<native>/plugin.json` instead of `.claude-plugin/plugin.json`, and the
 * manifest shipped without a `marketplace` field, so G-1a crashed before
 * the hermetic CI variant could even reach `stubInstall: true`.
 *
 * Two assertions:
 *   1. Manifest exists at the path the dogfood script reads from.
 *   2. The `marketplace` field is present and matches the canonical
 *      install string `native@sutra` (which the install.sh banner +
 *      registered marketplace name + plugin name all converge on).
 *
 * Spec source:
 *   - holding/plans/native-v1.x/ (M11 dogfood + install path)
 *   - codex consult 2026-05-01 §4 (dedicated unit gate, not E2E)
 */
import { describe, it, expect } from 'vitest'
import { readFileSync, existsSync } from 'node:fs'
import { resolve, dirname } from 'node:path'
import { fileURLToPath } from 'node:url'

const here = dirname(fileURLToPath(import.meta.url))
const manifestPath = resolve(here, '..', '..', '.claude-plugin', 'plugin.json')

describe('Native plugin manifest — readMarketplaceString contract', () => {
  it('plugin.json exists at the path readMarketplaceString resolves', () => {
    expect(existsSync(manifestPath)).toBe(true)
  })

  it('plugin.json carries a non-empty `marketplace` field', () => {
    const parsed = JSON.parse(readFileSync(manifestPath, 'utf-8')) as {
      marketplace?: string
    }
    expect(typeof parsed.marketplace).toBe('string')
    expect((parsed.marketplace ?? '').length).toBeGreaterThan(0)
  })

  it('canonical marketplace string is `native@sutra`', () => {
    const parsed = JSON.parse(readFileSync(manifestPath, 'utf-8')) as {
      marketplace?: string
    }
    expect(parsed.marketplace).toBe('native@sutra')
  })
})
