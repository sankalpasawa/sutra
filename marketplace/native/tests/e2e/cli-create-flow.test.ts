/**
 * E2E — CLI create-on-the-fly flow.
 *
 * Drives the sutra-native CLI's main() entrypoint in-process with a mocked
 * stdout/stderr/env so the test runs fast and deterministically. This is
 * the same pattern used by the existing contract tests; the lifecycle
 * subprocess test (l3-daemon-simulation) covers the bin shim path.
 *
 * Proves a founder can, with five subcommands, go from empty user-kit to
 * an executed workflow:
 *   1. create-domain    → file appears in $SUTRA_NATIVE_HOME/user-kit/domains/
 *   2. create-charter   → file appears in user-kit/charters/, references the domain
 *   3. create-workflow  → file appears in user-kit/workflows/
 *   4. list             → reports what was persisted
 *   5. run <W-id>       → prints workflow_started ... workflow_completed events
 *
 * Each describe block uses an isolated SUTRA_NATIVE_HOME tmp dir so the
 * test never touches the developer's real ~/.sutra-native/.
 */

import { existsSync, mkdtempSync, readFileSync, rmSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { afterAll, beforeAll, describe, expect, it } from 'vitest'

import { main } from '../../src/cli/sutra-native.js'

interface CliResult {
  code: number
  stdout: string
  stderr: string
}

function runCli(argv: string[], home: string): CliResult {
  let stdout = ''
  let stderr = ''
  const code = main({
    argv,
    env: { ...process.env, SUTRA_NATIVE_HOME: home, HOME: home },
    stdout: (s) => {
      stdout += s
    },
    stderr: (s) => {
      stderr += s
    },
  })
  return { code, stdout, stderr }
}

describe('E2E CLI: create-domain → create-charter → create-workflow → list → run', () => {
  let HOME_DIR: string

  beforeAll(() => {
    HOME_DIR = mkdtempSync(join(tmpdir(), 'sutra-native-e2e-'))
  })

  afterAll(() => {
    if (HOME_DIR && existsSync(HOME_DIR)) {
      rmSync(HOME_DIR, { recursive: true, force: true })
    }
  })

  it('create-domain persists D6 Health to user-kit/domains/', () => {
    const r = runCli(['create-domain', '--id', 'D6', '--name', 'Health'], HOME_DIR)
    expect(r.code).toBe(0)
    expect(r.stdout).toContain('Domain D6')
    expect(r.stdout).toContain('Health')
    const path = join(HOME_DIR, 'user-kit', 'domains', 'D6.json')
    expect(existsSync(path)).toBe(true)
    const persisted = JSON.parse(readFileSync(path, 'utf8'))
    expect(persisted.id).toBe('D6')
    expect(persisted.name).toBe('Health')
    expect(persisted.tenant_id).toBe('T-default')
  })

  it('create-charter persists C-sleep under D6', () => {
    const r = runCli(
      [
        'create-charter',
        '--id',
        'C-sleep',
        '--purpose',
        'Hold a 6h floor on nightly sleep',
        '--domain',
        'D6',
      ],
      HOME_DIR,
    )
    expect(r.code).toBe(0)
    expect(r.stdout).toContain('Charter C-sleep')
    expect(r.stdout).toContain('under D6')
    const path = join(HOME_DIR, 'user-kit', 'charters', 'C-sleep.json')
    expect(existsSync(path)).toBe(true)
    const persisted = JSON.parse(readFileSync(path, 'utf8'))
    expect(persisted.id).toBe('C-sleep')
    expect(persisted.acl[0].domain_or_charter_id).toBe('D6')
  })

  it('create-workflow persists W-checkin with wait → terminate', () => {
    const r = runCli(
      ['create-workflow', '--id', 'W-checkin', '--steps', 'wait,terminate'],
      HOME_DIR,
    )
    expect(r.code).toBe(0)
    expect(r.stdout).toContain('Workflow W-checkin')
    expect(r.stdout).toContain('wait → terminate')
    const path = join(HOME_DIR, 'user-kit', 'workflows', 'W-checkin.json')
    expect(existsSync(path)).toBe(true)
    const persisted = JSON.parse(readFileSync(path, 'utf8'))
    expect(persisted.id).toBe('W-checkin')
    expect(persisted.step_graph).toHaveLength(2)
    expect(persisted.step_graph[0].action).toBe('wait')
    expect(persisted.step_graph[1].action).toBe('terminate')
  })

  it('list reports all three created entities', () => {
    const r = runCli(['list'], HOME_DIR)
    expect(r.code).toBe(0)
    expect(r.stdout).toContain('DOMAINS (1)')
    expect(r.stdout).toContain('D6')
    expect(r.stdout).toContain('Health')
    expect(r.stdout).toContain('CHARTERS (1)')
    expect(r.stdout).toContain('C-sleep')
    expect(r.stdout).toContain('WORKFLOWS (1)')
    expect(r.stdout).toContain('W-checkin')
  })

  it('list domains shows only domains', () => {
    const r = runCli(['list', 'domains'], HOME_DIR)
    expect(r.code).toBe(0)
    expect(r.stdout).toContain('DOMAINS')
    expect(r.stdout).not.toContain('CHARTERS')
    expect(r.stdout).not.toContain('WORKFLOWS')
  })

  it('run W-checkin executes via LiteExecutor and prints events', () => {
    const r = runCli(['run', 'W-checkin', '--execution-id', 'E-cli-001'], HOME_DIR)
    expect(r.code).toBe(0)
    expect(r.stdout).toContain('[workflow_started]')
    expect(r.stdout).toContain('W-checkin')
    expect(r.stdout).toContain('exec=E-cli-001')
    expect(r.stdout).toContain('[step_started]')
    expect(r.stdout).toContain('[step_completed]')
    expect(r.stdout).toContain('[workflow_completed]')
    expect(r.stdout).toMatch(/OK: \d+ step\(s\) completed/)
  })

  it('run on missing workflow id exits 3 with helpful error', () => {
    const r = runCli(['run', 'W-does-not-exist'], HOME_DIR)
    expect(r.code).toBe(3)
    expect(r.stderr).toContain('not found in user-kit')
    expect(r.stderr).toContain('list workflows')
  })

  it('run with no positional arg exits 2', () => {
    const r = runCli(['run'], HOME_DIR)
    expect(r.code).toBe(2)
    expect(r.stderr).toContain('workflow id required')
  })

  it('create-domain rejects missing --name', () => {
    const r = runCli(['create-domain', '--id', 'D-bad'], HOME_DIR)
    expect(r.code).toBe(2)
    expect(r.stderr).toContain('--name is required')
  })

  it('create-domain rejects bad id pattern (D-ID validator)', () => {
    const r = runCli(['create-domain', '--id', 'NotADomain', '--name', 'X'], HOME_DIR)
    expect(r.code).toBe(2)
    expect(r.stderr).toContain('Domain.id')
  })

  it('create-workflow rejects unknown step action', () => {
    const r = runCli(
      ['create-workflow', '--id', 'W-bad', '--steps', 'wait,nonsense_action'],
      HOME_DIR,
    )
    expect(r.code).toBe(2)
    expect(r.stderr).toContain('not one of')
  })

  it('create-charter rejects missing --purpose', () => {
    const r = runCli(['create-charter', '--id', 'C-noop'], HOME_DIR)
    expect(r.code).toBe(2)
    expect(r.stderr).toContain('--purpose is required')
  })

  it('help lists the new founder-facing subcommands', () => {
    const r = runCli(['help'], HOME_DIR)
    expect(r.code).toBe(0)
    expect(r.stdout).toContain('create-domain')
    expect(r.stdout).toContain('create-charter')
    expect(r.stdout).toContain('create-workflow')
    expect(r.stdout).toContain('list')
    expect(r.stdout).toContain('run')
  })
})

describe('E2E CLI: empty user-kit edge cases', () => {
  let HOME_DIR: string

  beforeAll(() => {
    HOME_DIR = mkdtempSync(join(tmpdir(), 'sutra-native-e2e-empty-'))
  })

  afterAll(() => {
    if (HOME_DIR && existsSync(HOME_DIR)) {
      rmSync(HOME_DIR, { recursive: true, force: true })
    }
  })

  it('list on empty user-kit reports zero entities + hint', () => {
    const r = runCli(['list'], HOME_DIR)
    expect(r.code).toBe(0)
    expect(r.stdout).toContain('DOMAINS (0)')
    expect(r.stdout).toContain('CHARTERS (0)')
    expect(r.stdout).toContain('WORKFLOWS (0)')
    expect(r.stdout).toContain('try: sutra-native create-domain')
  })
})
