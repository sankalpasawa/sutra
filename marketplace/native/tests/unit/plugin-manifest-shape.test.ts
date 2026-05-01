/**
 * Plugin manifest required-fields gate. Catches drift between the manifest
 * shape Claude Code's marketplace expects and what the Native package ships.
 *
 * Per codex consult 2026-05-01 §5 — schema-shape regression catches the
 * class of bugs the M11 dogfood ENOENT belonged to (manifest field present
 * but at wrong path, or absent entirely).
 */
import { describe, it, expect } from 'vitest'
import { readFileSync } from 'node:fs'
import { resolve, dirname } from 'node:path'
import { fileURLToPath } from 'node:url'

const here = dirname(fileURLToPath(import.meta.url))
const manifestPath = resolve(here, '..', '..', '.claude-plugin', 'plugin.json')

const REQUIRED_FIELDS = [
  'name',
  'version',
  'marketplace',
  'description',
  'author',
  'license',
  'homepage',
  'keywords',
] as const

describe('Native plugin manifest — required-field shape', () => {
  const parsed = JSON.parse(readFileSync(manifestPath, 'utf-8')) as Record<string, unknown>

  it.each(REQUIRED_FIELDS)('has required field: %s', (field) => {
    expect(parsed).toHaveProperty(field)
    const value = parsed[field]
    expect(value === undefined || value === null).toBe(false)
    if (typeof value === 'string') {
      expect(value.length).toBeGreaterThan(0)
    }
    if (Array.isArray(value)) {
      expect(value.length).toBeGreaterThan(0)
    }
  })

  it('plugin name matches marketplace install-string left side', () => {
    const name = parsed.name as string
    const marketplace = parsed.marketplace as string
    const [pluginName] = marketplace.split('@')
    expect(pluginName).toBe(name)
  })

  it('semver-shaped version', () => {
    const version = parsed.version as string
    expect(version).toMatch(/^\d+\.\d+\.\d+(-[\w.]+)?$/)
  })
})
