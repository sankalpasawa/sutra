/**
 * Contract test — version-sync guard (v1.1.3+).
 *
 * Native ships its version in FIVE places. Pre-v1.1.3 they drifted:
 *   package.json = 1.1.1, plugin.json = 1.1.2, marketplace catalog = 1.1.1,
 *   src/cli/sutra-native.ts:VERSION = 1.1.2, src/index.ts:NATIVE_VERSION = 1.1.0.
 * The binary's --version reported plugin.json's value while marketplace
 * install pulled package.json's value, leading to silent ship-vs-installed
 * mismatch. Codex consult 2026-05-03 P1: enforce single-source-of-truth
 * via this guard.
 *
 * Source of truth: package.json (the npm contract). All four other
 * surfaces must equal package.json.version.
 *
 * Failure mode: fails loudly with the actual values so the release
 * engineer can sync them.
 */

import { describe, it, expect } from 'vitest'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'

interface VersionSource {
  label: string
  path: string
  version: string
}

function readJson(path: string): unknown {
  return JSON.parse(readFileSync(path, 'utf8')) as unknown
}

/**
 * Extract a version literal from a TS source file by regex. Captures the
 * first match of `<varName> = '<version>'` or `<varName> = "<version>"`.
 * Returns 'MISSING' if no match — the test will fail loudly.
 */
function extractTsVersion(filePath: string, varName: string): string {
  const src = readFileSync(filePath, 'utf8')
  const re = new RegExp(`${varName}\\s*=\\s*['"]([^'"]+)['"]`)
  const m = re.exec(src)
  return m ? m[1] : 'MISSING'
}

describe('version-sync contract — native plugin (5 sources must match)', () => {
  it('package.json + plugin.json + marketplace.json + 2 TS constants all advertise the same native version', () => {
    const root = resolve(__dirname, '../..')
    const repoRoot = resolve(root, '../..') // sutra repo root from native package

    const pkg = readJson(resolve(root, 'package.json')) as { version: string }
    const plugin = readJson(resolve(root, '.claude-plugin/plugin.json')) as { version: string }
    const catalog = readJson(resolve(repoRoot, '.claude-plugin/marketplace.json')) as {
      plugins: Array<{ name: string; version: string }>
    }

    const nativeEntry = catalog.plugins.find((p) => p.name === 'native')

    const cliVersion = extractTsVersion(resolve(root, 'src/cli/sutra-native.ts'), 'VERSION')
    const libVersion = extractTsVersion(resolve(root, 'src/index.ts'), 'NATIVE_VERSION')

    const sources: VersionSource[] = [
      { label: 'package.json',                       path: 'native/package.json',                       version: pkg.version },
      { label: 'plugin.json',                        path: 'native/.claude-plugin/plugin.json',         version: plugin.version },
      { label: 'marketplace.json (native entry)',    path: 'sutra/.claude-plugin/marketplace.json',     version: nativeEntry?.version ?? 'MISSING' },
      { label: 'cli/sutra-native.ts:VERSION',        path: 'native/src/cli/sutra-native.ts',            version: cliVersion },
      { label: 'index.ts:NATIVE_VERSION',            path: 'native/src/index.ts',                       version: libVersion },
    ]

    const distinct = new Set(sources.map((s) => s.version))

    if (distinct.size !== 1) {
      const summary = sources
        .map((s) => `  ${s.label.padEnd(40)} ${s.version}  (${s.path})`)
        .join('\n')
      expect.fail(
        `version drift detected across ${sources.length} sources:\n${summary}\n\nFix: pick package.json's value as the source of truth + sync the other four.`,
      )
    }

    // Sanity: catalog must have a native entry at all.
    expect(nativeEntry, 'no plugins[name="native"] entry in sutra/.claude-plugin/marketplace.json').toBeDefined()
  })
})
