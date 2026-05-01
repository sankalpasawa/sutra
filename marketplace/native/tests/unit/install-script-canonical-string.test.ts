/**
 * Drift gate between installer (sutra/website/native/install.sh) and
 * the plugin manifest. Catches the failure mode where install.sh advertises
 * one marketplace string but plugin.json carries a different one — the
 * exact drift the script's own comment block at lines 343-365 flagged
 * ("PS-13 says `sutra@marketplace`; plugin.json says `sutra@asawa-marketplace`;
 * README says `native@sutra-marketplace`").
 *
 * Per codex consult 2026-05-01 §5 — cheap end-of-flow check that catches
 * documentation/code drift the unit tests on plugin.json alone cannot.
 */
import { describe, it, expect } from 'vitest'
import { readFileSync, existsSync } from 'node:fs'
import { resolve, dirname } from 'node:path'
import { fileURLToPath } from 'node:url'

const here = dirname(fileURLToPath(import.meta.url))
const manifestPath = resolve(here, '..', '..', '.claude-plugin', 'plugin.json')
const installScriptPath = resolve(here, '..', '..', '..', '..', 'website', 'native', 'install.sh')

describe('Installer ↔ manifest marketplace-string convergence', () => {
  const manifest = JSON.parse(readFileSync(manifestPath, 'utf-8')) as { marketplace: string }
  const canonical = manifest.marketplace

  it('install.sh source exists', () => {
    expect(existsSync(installScriptPath)).toBe(true)
  })

  it('install.sh references the canonical marketplace string from plugin.json', () => {
    const installSource = readFileSync(installScriptPath, 'utf-8')
    expect(installSource.includes(canonical)).toBe(true)
  })

  it('install.sh does not reference deprecated drift variants', () => {
    const installSource = readFileSync(installScriptPath, 'utf-8')
    const drifted = ['sutra@marketplace', 'sutra@asawa-marketplace', 'native@sutra-marketplace']
    for (const variant of drifted) {
      if (variant === canonical) continue
      expect(installSource.includes(variant)).toBe(false)
    }
  })
})
