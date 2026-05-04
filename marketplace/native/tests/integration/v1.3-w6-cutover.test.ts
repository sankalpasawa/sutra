/**
 * v1.3.0 W6 — cutover engine tests (validator + dry-run + CLI subcommands).
 *
 * Coverage matrix (plan §Step 6 — cutover):
 *   1. Valid contract → validateCutoverContract returns valid=true.
 *   2. Invalid contract (no-op cutover) → valid=false + specific error.
 *   3. Invalid contract (duplicate invariants) → valid=false + error.
 *   4. Invalid contract (unparseable canary_window) → valid=false + error.
 *   5. null contract (no cutover) → valid=true (degenerate plan).
 *   6. dryRunApplyCutover on valid → 5 reversible mutations.
 *   7. CLI `cutover validate <valid.json>` → exit 0.
 *   8. CLI `cutover validate <invalid.json>` → exit 2 + errors on stderr.
 *   9. CLI `cutover validate <missing.json>` → exit 3 (io error).
 *  10. CLI `cutover dry-run <valid.json>` → exit 0 + plan rendered to stdout.
 *  11. CLI `cutover dry-run <invalid.json>` → exit 2.
 */

import { mkdtempSync, rmSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { afterEach, beforeEach, describe, expect, it } from 'vitest'

import {
  validateCutoverContract,
  isParseableDuration,
} from '../../src/engine/cutover-validator.js'
import { dryRunApplyCutover } from '../../src/engine/cutover-applier.js'
import { main } from '../../src/cli/sutra-native.js'

interface CliResult {
  code: number
  stdout: string
  stderr: string
}

async function runCli(argv: string[]): Promise<CliResult> {
  let stdout = ''
  let stderr = ''
  const code = await main({
    argv,
    env: { ...process.env },
    stdout: (s) => {
      stdout += s
    },
    stderr: (s) => {
      stderr += s
    },
  })
  return { code, stdout, stderr }
}

let workDir: string

beforeEach(() => {
  workDir = mkdtempSync(join(tmpdir(), 'native-w6-cutover-'))
})

afterEach(() => {
  rmSync(workDir, { recursive: true, force: true })
})

describe('v1.3.0 W6 #1 — validateCutoverContract', () => {
  it('valid contract → valid=true, errors=[]', () => {
    const c = {
      source_engine: 'core',
      target_engine: 'native',
      behavior_invariants: ['no_dropped_events', 'ordering_preserved'],
      rollback_gate: 'error_rate > 0.01',
      canary_window: 'PT72H',
    }
    const r = validateCutoverContract(c)
    expect(r.valid).toBe(true)
    expect(r.errors).toEqual([])
  })

  it('null contract (no cutover) → valid=true', () => {
    const r = validateCutoverContract(null)
    expect(r.valid).toBe(true)
    expect(r.errors).toEqual([])
  })

  it('source_engine === target_engine → valid=false with specific error', () => {
    const c = {
      source_engine: 'native',
      target_engine: 'native',
      behavior_invariants: ['x'],
      rollback_gate: 'gate',
      canary_window: '60s',
    }
    const r = validateCutoverContract(c)
    expect(r.valid).toBe(false)
    expect(r.errors.some((e) => e.includes('no-op'))).toBe(true)
  })

  it('duplicate behavior_invariants → valid=false', () => {
    const c = {
      source_engine: 'core',
      target_engine: 'native',
      behavior_invariants: ['dup', 'dup', 'unique'],
      rollback_gate: 'gate',
      canary_window: 'PT72H',
    }
    const r = validateCutoverContract(c)
    expect(r.valid).toBe(false)
    expect(r.errors.some((e) => e.includes('duplicate'))).toBe(true)
  })

  it('whitespace-only invariant → valid=false', () => {
    const c = {
      source_engine: 'core',
      target_engine: 'native',
      behavior_invariants: ['real', '   '],
      rollback_gate: 'gate',
      canary_window: '60s',
    }
    const r = validateCutoverContract(c)
    // Schema-level min(1) likely catches "   " but the post-trim check
    // catches it again as a different error path. Either way, valid=false.
    expect(r.valid).toBe(false)
  })

  it('unparseable canary_window → valid=false', () => {
    const c = {
      source_engine: 'core',
      target_engine: 'native',
      behavior_invariants: ['x'],
      rollback_gate: 'gate',
      canary_window: 'forever',
    }
    const r = validateCutoverContract(c)
    expect(r.valid).toBe(false)
    expect(r.errors.some((e) => e.includes('canary_window'))).toBe(true)
  })

  it('missing fields → schema errors surface with `schema:` prefix', () => {
    const c = { source_engine: 'core' } as unknown
    const r = validateCutoverContract(c)
    expect(r.valid).toBe(false)
    expect(r.errors.some((e) => e.startsWith('schema:'))).toBe(true)
  })
})

describe('v1.3.0 W6 #2 — isParseableDuration', () => {
  it.each([
    ['60', true],
    ['3600', true],
    ['7d', true],
    ['72h', true],
    ['60s', true],
    ['10m', true],
    ['PT72H', true],
    ['P7D', true],
    ['PT60S', true],
    ['', false],
    ['forever', false],
    ['7days', false],
    ['-1', false],
    ['0', false], // Non-positive rejected
  ])('parses %s → %s', (input, expected) => {
    expect(isParseableDuration(input)).toBe(expected)
  })
})

describe('v1.3.0 W6 #3 — dryRunApplyCutover', () => {
  it('valid contract → 5 reversible planned mutations', () => {
    const c = {
      source_engine: 'core',
      target_engine: 'native',
      behavior_invariants: ['inv1'],
      rollback_gate: 'gate',
      canary_window: 'PT72H',
    }
    const plan = dryRunApplyCutover(c)
    expect(plan.valid).toBe(true)
    expect(plan.mode).toBe('dry-run')
    expect(plan.planned_mutations.length).toBe(5)
    expect(plan.planned_mutations.every((m) => m.reversible)).toBe(true)
    expect(plan.canary_window_seconds).toBe(72 * 60 * 60)
  })

  it('invalid contract → empty mutations + errors populated', () => {
    const c = {
      source_engine: 'x',
      target_engine: 'x',
      behavior_invariants: ['a'],
      rollback_gate: 'g',
      canary_window: 'forever',
    }
    const plan = dryRunApplyCutover(c)
    expect(plan.valid).toBe(false)
    expect(plan.planned_mutations.length).toBe(0)
    expect(plan.errors.length).toBeGreaterThan(0)
  })

  it('null contract → degenerate plan, valid=true, no mutations', () => {
    const plan = dryRunApplyCutover(null)
    expect(plan.valid).toBe(true)
    expect(plan.planned_mutations.length).toBe(0)
  })

  it('canary_window_seconds derived from short-form, ISO-8601, and bare seconds', () => {
    const base = {
      source_engine: 'core',
      target_engine: 'native',
      behavior_invariants: ['x'],
      rollback_gate: 'gate',
    }
    expect(dryRunApplyCutover({ ...base, canary_window: '60s' }).canary_window_seconds).toBe(60)
    expect(dryRunApplyCutover({ ...base, canary_window: 'PT2H' }).canary_window_seconds).toBe(2 * 60 * 60)
    expect(dryRunApplyCutover({ ...base, canary_window: '120' }).canary_window_seconds).toBe(120)
  })
})

describe('v1.3.0 W6 #4 — CLI cutover validate', () => {
  it('valid contract file → exit 0', async () => {
    const path = join(workDir, 'cutover-valid.json')
    writeFileSync(
      path,
      JSON.stringify({
        source_engine: 'core',
        target_engine: 'native',
        behavior_invariants: ['no_drops'],
        rollback_gate: 'fail_rate > 0.01',
        canary_window: 'PT72H',
      }),
    )
    const r = await runCli(['cutover', 'validate', path])
    expect(r.code).toBe(0)
    expect(r.stdout).toContain('VALID')
  })

  it('invalid contract file → exit 2 with errors on stderr', async () => {
    const path = join(workDir, 'cutover-invalid.json')
    writeFileSync(
      path,
      JSON.stringify({
        source_engine: 'core',
        target_engine: 'core',
        behavior_invariants: ['dup', 'dup'],
        rollback_gate: 'gate',
        canary_window: 'forever',
      }),
    )
    const r = await runCli(['cutover', 'validate', path])
    expect(r.code).toBe(2)
    expect(r.stderr).toContain('INVALID')
    expect(r.stderr).toContain('no-op')
    expect(r.stderr).toContain('duplicate')
  })

  it('missing file → exit 3 (io error)', async () => {
    const r = await runCli(['cutover', 'validate', join(workDir, 'no-such-file.json')])
    expect(r.code).toBe(3)
    expect(r.stderr).toContain('not found')
  })

  it('non-JSON file → exit 3 with parse-failed message', async () => {
    const path = join(workDir, 'not-json.json')
    writeFileSync(path, 'not json at all')
    const r = await runCli(['cutover', 'validate', path])
    expect(r.code).toBe(3)
    expect(r.stderr).toContain('parse failed')
  })

  it('unknown subcommand → exit 2', async () => {
    const r = await runCli(['cutover', 'apply'])
    expect(r.code).toBe(2)
    expect(r.stderr).toContain('unknown subcommand')
  })

  it('missing path argument → exit 2', async () => {
    const r = await runCli(['cutover', 'validate'])
    expect(r.code).toBe(2)
    expect(r.stderr).toContain('contract path required')
  })
})

describe('v1.3.0 W6 #5 — CLI cutover dry-run', () => {
  it('valid contract → exit 0, plan rendered', async () => {
    const path = join(workDir, 'cutover-valid.json')
    writeFileSync(
      path,
      JSON.stringify({
        source_engine: 'core',
        target_engine: 'native',
        behavior_invariants: ['no_drops', 'ordering'],
        rollback_gate: 'fail_rate > 0.01',
        canary_window: 'PT72H',
      }),
    )
    const r = await runCli(['cutover', 'dry-run', path])
    expect(r.code).toBe(0)
    expect(r.stdout).toContain('CUTOVER PLAN')
    expect(r.stdout).toContain('arm_parallel_canary')
    expect(r.stdout).toContain('register_invariant_observers')
    expect(r.stdout).toContain('register_rollback_gate')
    expect(r.stdout).toContain('Apply-with-rollback is deferred to v1.x.1')
  })

  it('invalid contract → exit 2', async () => {
    const path = join(workDir, 'cutover-invalid.json')
    writeFileSync(
      path,
      JSON.stringify({
        source_engine: 'core',
        target_engine: 'core',
        behavior_invariants: ['x'],
        rollback_gate: 'g',
        canary_window: 'PT72H',
      }),
    )
    const r = await runCli(['cutover', 'dry-run', path])
    expect(r.code).toBe(2)
    expect(r.stderr).toContain('INVALID')
  })

  it('null contract dry-run → exit 0, degenerate plan', async () => {
    const path = join(workDir, 'cutover-null.json')
    writeFileSync(path, 'null')
    const r = await runCli(['cutover', 'dry-run', path])
    expect(r.code).toBe(0)
    expect(r.stdout).toContain('no cutover required')
  })
})
