/**
 * Contract tests — sutra-native CLI (D4 SKELETON).
 *
 * Test the main() entry function with stubbed CommandContext.
 *
 * R-NPD-START.1 + R-START.4 + R-NPD-START.2 + R-NPD-START.3 covered here
 * (banner emission, exit codes, subcommand dispatch). Slash command end-
 * to-end test in tests/integration/start-slash.test.ts (D5).
 */

import { describe, it, expect, beforeEach, afterEach } from 'vitest'
import { mkdtempSync, rmSync, existsSync, writeFileSync } from 'node:fs'
import { join } from 'node:path'
import { tmpdir } from 'node:os'
import { main, formatBanner, formatStatus, usage } from '../../../src/cli/sutra-native.js'

interface Captured {
  stdout: string
  stderr: string
}

function makeCtx(argv: string[], pidPath: string, sessionId?: string): {
  captured: Captured
  ctx: Parameters<typeof main>[0]
} {
  const captured: Captured = { stdout: '', stderr: '' }
  const env: NodeJS.ProcessEnv = {
    SUTRA_NATIVE_PID: pidPath,
  }
  if (sessionId !== undefined) env.CLAUDE_SESSION_ID = sessionId
  return {
    captured,
    ctx: {
      argv,
      env,
      stdout: (s) => {
        captured.stdout += s
      },
      stderr: (s) => {
        captured.stderr += s
      },
    },
  }
}

describe('sutra-native CLI — D4 SKELETON contract', () => {
  let workdir: string
  let pidPath: string

  beforeEach(() => {
    workdir = mkdtempSync(join(tmpdir(), 'sutra-native-cli-test-'))
    pidPath = join(workdir, 'native.pid')
  })

  afterEach(() => {
    if (existsSync(workdir)) {
      rmSync(workdir, { recursive: true, force: true })
    }
  })

  describe('start subcommand', () => {
    it('exits 0 + writes PID file + prints banner on first activation; lock PERSISTS after main() returns', () => {
      const { captured, ctx } = makeCtx(['start'], pidPath)
      const code = main(ctx)
      expect(code).toBe(0)
      // Per codex master 2026-05-03: lock must persist after start returns
      // so /start-native is idempotent and status keeps reporting running.
      // The auto-release exit hook was removed.
      expect(existsSync(pidPath)).toBe(true)
      expect(captured.stdout).toContain('SUTRA-NATIVE')
      expect(captured.stdout).toContain('Activated')
      expect(captured.stderr).toBe('')
    })

    it('detects host_kind=cli when CLAUDE_SESSION_ID is unset', () => {
      const { captured, ctx } = makeCtx(['start'], pidPath)
      main(ctx)
      expect(captured.stdout).toContain('host=cli')
    })

    it('detects host_kind=claude-code when CLAUDE_SESSION_ID is set', () => {
      const { captured, ctx } = makeCtx(['start'], pidPath, 'session-123')
      main(ctx)
      expect(captured.stdout).toContain('host=claude-code')
    })

    it('exits 1 with informative stderr when lock already held', () => {
      // First activation
      const first = makeCtx(['start'], pidPath)
      expect(main(first.ctx)).toBe(0)

      // Second activation should hit lock_held_alive
      const second = makeCtx(['start'], pidPath)
      const code = main(second.ctx)
      expect(code).toBe(1)
      expect(second.captured.stderr).toContain('already running')
      expect(second.captured.stderr).toContain('pid=')
    })
  })

  describe('status subcommand', () => {
    it('exits 0 + reports stopped when no lock', () => {
      const { captured, ctx } = makeCtx(['status'], pidPath)
      const code = main(ctx)
      expect(code).toBe(0)
      expect(captured.stdout).toContain('stopped')
    })

    it('exits 0 + reports running after start', () => {
      // Start
      const startCtx = makeCtx(['start'], pidPath)
      main(startCtx.ctx)

      // Status
      const { captured, ctx } = makeCtx(['status'], pidPath)
      const code = main(ctx)
      expect(code).toBe(0)
      expect(captured.stdout).toContain('running')
      expect(captured.stdout).toContain(`pid:        ${process.pid}`)
    })

    it('reports STALE LOCK when PID file holds dead process', () => {
      writeFileSync(
        pidPath,
        JSON.stringify({
          pid: 999999999,
          started_at_ms: Date.now() - 60000,
          host_kind: 'cli',
        }),
      )
      const { captured, ctx } = makeCtx(['status'], pidPath)
      expect(main(ctx)).toBe(0)
      expect(captured.stdout).toContain('STALE LOCK')
    })
  })

  describe('version / help / help', () => {
    it('version subcommand prints version + exits 0', () => {
      const { captured, ctx } = makeCtx(['version'], pidPath)
      const code = main(ctx)
      expect(code).toBe(0)
      expect(captured.stdout.trim()).toMatch(/^\d+\.\d+\.\d+$/)
    })

    it('--version flag works equivalently', () => {
      const { captured, ctx } = makeCtx(['--version'], pidPath)
      expect(main(ctx)).toBe(0)
      expect(captured.stdout.trim()).toMatch(/^\d+\.\d+\.\d+$/)
    })

    it('help subcommand prints usage + exits 0', () => {
      const { captured, ctx } = makeCtx(['help'], pidPath)
      const code = main(ctx)
      expect(code).toBe(0)
      expect(captured.stdout).toContain('Usage:')
      expect(captured.stdout).toContain('start')
      expect(captured.stdout).toContain('status')
    })

    it('no subcommand defaults to help', () => {
      const { captured, ctx } = makeCtx([], pidPath)
      expect(main(ctx)).toBe(0)
      expect(captured.stdout).toContain('Usage:')
    })
  })

  describe('unknown subcommand', () => {
    it('exits 2 + prints error + usage to stderr', () => {
      const { captured, ctx } = makeCtx(['nonsense'], pidPath)
      const code = main(ctx)
      expect(code).toBe(2)
      expect(captured.stderr).toContain('unknown subcommand')
      expect(captured.stderr).toContain('nonsense')
    })
  })

  describe('helper functions', () => {
    it('formatBanner contains version + host + pid', () => {
      const banner = formatBanner('cli', '/tmp/test.pid')
      expect(banner).toContain('SUTRA-NATIVE')
      expect(banner).toContain('host=cli')
      expect(banner).toContain('PID file:')
    })

    it('formatStatus(stopped) reports stopped', () => {
      const out = formatStatus(
        {
          running: false,
          pid: null,
          started_at_ms: null,
          host_kind: null,
          uptime_ms: null,
          stale_lock: false,
        },
        '/tmp/test.pid',
      )
      expect(out).toContain('stopped')
    })

    it('usage lists all subcommands', () => {
      const u = usage()
      expect(u).toContain('start')
      expect(u).toContain('status')
      expect(u).toContain('version')
      expect(u).toContain('help')
    })
  })
})
