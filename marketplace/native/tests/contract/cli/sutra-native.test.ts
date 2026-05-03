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
import { main, formatBanner, formatStatus, usage, detectHostKind } from '../../../src/cli/sutra-native.js'

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

  // v1.1.x: start subcommand changed from foreground (lock-as-marker) to
  // daemon-spawn (lock-as-pid). The in-process main({argv:['start']}) test
  // approach below cannot work because cmdStart spawns a child process via
  // child_process.spawn — incompatible with vitest in-process invocation.
  // L3 daemon-simulation tests (tests/integration/l3-daemon-simulation.test.ts,
  // gated by RUN_DAEMON_TESTS=1) cover the v1.1.x daemon contract end-to-end.
  // Skipped here to keep the L1 contract suite green.
  describe.skip('start subcommand (v1.0.x foreground contract — superseded by L3)', () => {
    it('exits 0 + writes PID file + prints banner on first activation; lock PERSISTS after main() returns', async () => {
      const { captured, ctx } = makeCtx(['start'], pidPath)
      const code = await main(ctx)
      expect(code).toBe(0)
      // Per codex master 2026-05-03: lock must persist after start returns
      // so /start-native is idempotent and status keeps reporting running.
      // The auto-release exit hook was removed.
      expect(existsSync(pidPath)).toBe(true)
      expect(captured.stdout).toContain('SUTRA-NATIVE')
      expect(captured.stdout).toContain('Activated')
      expect(captured.stderr).toBe('')
    })

    it('detects host_kind=cli when CLAUDE_SESSION_ID is unset', async () => {
      const { captured, ctx } = makeCtx(['start'], pidPath)
      await main(ctx)
      expect(captured.stdout).toContain('host=cli')
    })

    it('detects host_kind=claude-code when CLAUDE_SESSION_ID is set', async () => {
      const { captured, ctx } = makeCtx(['start'], pidPath, 'session-123')
      await main(ctx)
      expect(captured.stdout).toContain('host=claude-code')
    })

    it('exits 1 with informative stderr when lock already held', async () => {
      // First activation
      const first = makeCtx(['start'], pidPath)
      expect(await main(first.ctx)).toBe(0)

      // Second activation should hit lock_held_alive
      const second = makeCtx(['start'], pidPath)
      const code = await main(second.ctx)
      expect(code).toBe(1)
      expect(second.captured.stderr).toContain('already running')
      expect(second.captured.stderr).toContain('pid=')
    })
  })

  describe('status subcommand', () => {
    it('exits 0 + reports stopped when no lock', async () => {
      const { captured, ctx } = makeCtx(['status'], pidPath)
      const code = await main(ctx)
      expect(code).toBe(0)
      expect(captured.stdout).toContain('stopped')
    })

    // Depends on v1.0.x start behavior (in-process main + lock persists).
    // v1.1.x daemon mode tested in L3 harness instead.
    it.skip('exits 0 + reports running after start (v1.0.x — superseded by L3)', async () => {
      // Start
      const startCtx = makeCtx(['start'], pidPath)
      await main(startCtx.ctx)

      // Status
      const { captured, ctx } = makeCtx(['status'], pidPath)
      const code = await main(ctx)
      expect(code).toBe(0)
      expect(captured.stdout).toContain('running')
      expect(captured.stdout).toContain(`pid:        ${process.pid}`)
    })

    it('reports STALE LOCK when PID file holds dead process', async () => {
      writeFileSync(
        pidPath,
        JSON.stringify({
          pid: 999999999,
          started_at_ms: Date.now() - 60000,
          host_kind: 'cli',
        }),
      )
      const { captured, ctx } = makeCtx(['status'], pidPath)
      expect(await main(ctx)).toBe(0)
      expect(captured.stdout).toContain('STALE LOCK')
    })
  })

  describe('version / help / help', () => {
    it('version subcommand prints version + exits 0', async () => {
      const { captured, ctx } = makeCtx(['version'], pidPath)
      const code = await main(ctx)
      expect(code).toBe(0)
      expect(captured.stdout.trim()).toMatch(/^\d+\.\d+\.\d+$/)
    })

    it('--version flag works equivalently', async () => {
      const { captured, ctx } = makeCtx(['--version'], pidPath)
      expect(await main(ctx)).toBe(0)
      expect(captured.stdout.trim()).toMatch(/^\d+\.\d+\.\d+$/)
    })

    it('help subcommand prints usage + exits 0', async () => {
      const { captured, ctx } = makeCtx(['help'], pidPath)
      const code = await main(ctx)
      expect(code).toBe(0)
      expect(captured.stdout).toContain('Usage:')
      expect(captured.stdout).toContain('start')
      expect(captured.stdout).toContain('status')
    })

    it('no subcommand defaults to help', async () => {
      const { captured, ctx } = makeCtx([], pidPath)
      expect(await main(ctx)).toBe(0)
      expect(captured.stdout).toContain('Usage:')
    })
  })

  describe('unknown subcommand', () => {
    it('exits 2 + prints error + usage to stderr', async () => {
      const { captured, ctx } = makeCtx(['nonsense'], pidPath)
      const code = await main(ctx)
      expect(code).toBe(2)
      expect(captured.stderr).toContain('unknown subcommand')
      expect(captured.stderr).toContain('nonsense')
    })
  })

  describe('helper functions', () => {
    it('formatBanner contains version + host + pid', async () => {
      const banner = formatBanner('cli', '/tmp/test.pid')
      expect(banner).toContain('SUTRA-NATIVE')
      expect(banner).toContain('host=cli')
      expect(banner).toContain('PID file:')
    })

    it('formatStatus(stopped) reports stopped', async () => {
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

    it('usage lists all subcommands', async () => {
      const u = usage()
      expect(u).toContain('start')
      expect(u).toContain('status')
      expect(u).toContain('version')
      expect(u).toContain('help')
    })

    it('usage documents CLAUDECODE env var (v1.1.3+)', async () => {
      const u = usage()
      expect(u).toContain('CLAUDECODE')
      // Legacy CLAUDE_SESSION_ID still listed as fallback
      expect(u).toContain('CLAUDE_SESSION_ID')
    })
  })

  /**
   * detectHostKind — host detection helper extracted in v1.1.3 for unit
   * testability. cmdStart now delegates to detectHostKind(env). The previous
   * inline check (CLAUDE_SESSION_ID only) mis-attributed every Claude Code
   * session as host=cli because Claude Code v2.x does NOT export
   * CLAUDE_SESSION_ID to Bash tool calls. Codex consult 2026-05-03 verdict
   * CHANGES-REQUIRED → folded.
   */
  describe('detectHostKind (v1.1.3 host detection contract)', () => {
    it('returns claude-code when CLAUDECODE === "1" (primary signal)', () => {
      expect(detectHostKind({ CLAUDECODE: '1' } as NodeJS.ProcessEnv)).toBe('claude-code')
    })

    it('returns cli when CLAUDECODE !== "1" and CLAUDE_SESSION_ID unset', () => {
      expect(detectHostKind({} as NodeJS.ProcessEnv)).toBe('cli')
      expect(detectHostKind({ CLAUDECODE: '0' } as NodeJS.ProcessEnv)).toBe('cli')
      expect(detectHostKind({ CLAUDECODE: '' } as NodeJS.ProcessEnv)).toBe('cli')
    })

    it('returns claude-code when only legacy CLAUDE_SESSION_ID is set', async () => {
      // Legacy fallback path — CC may not actually export this in Bash tool
      // calls today, but slash commands / hooks / future versions might.
      expect(detectHostKind({ CLAUDE_SESSION_ID: 'sess-abc' } as NodeJS.ProcessEnv)).toBe('claude-code')
    })

    it('CLAUDECODE takes precedence when both signals present', async () => {
      // If a future hook sets both, CLAUDECODE='1' is canonical.
      expect(
        detectHostKind({ CLAUDECODE: '1', CLAUDE_SESSION_ID: 'sess-abc' } as NodeJS.ProcessEnv),
      ).toBe('claude-code')
    })

    it('returns cli when CLAUDECODE present but not "1" and no CLAUDE_SESSION_ID', () => {
      // Strict equality — only CLAUDECODE='1' counts; truthy strings like
      // 'true' or '0' do NOT (Anthropic documents the value as "1").
      expect(detectHostKind({ CLAUDECODE: 'true' } as NodeJS.ProcessEnv)).toBe('cli')
    })

    it('does NOT inspect AI_AGENT or CLAUDE_CODE_* env vars', async () => {
      // Codex P2 advisory 2026-05-03: these are weak/non-canonical signals;
      // detector intentionally narrow to keep cardinality stable.
      expect(
        detectHostKind({
          AI_AGENT: 'claude-code/2.1.126/agent',
          CLAUDE_CODE_ENTRYPOINT: 'cli',
        } as NodeJS.ProcessEnv),
      ).toBe('cli')
    })
  })
})
