/**
 * M11 Group TT — I-11 time-to-value ≤30min invariant (realized from M9 stub).
 *
 * Per D-NS-47 (codex P2.1 fold) the test ships TWO variants:
 *
 *   CI variant (always runs):
 *     Executes the REAL G-2..G-5 path of the dogfood script (engine barrel
 *     import + Vinit fixture construction + executeStepGraph + observable
 *     artifact emission) with HERMETIC FAKE-INSTALL stub for G-1a/G-1b.
 *     Asserts a per-gate engine-path budget (G-2..G-5 sum < 5000ms) plus the
 *     I-11 verdict shape (`PASS`/`CLOSED`). This is the real I-11 invariant
 *     proxy in CI — not a parser test.
 *
 *   Real-clock variant (`runIf(process.env.RUN_REAL_DOGFOOD === '1')`):
 *     Spawns the actual dogfood script via `npx tsx` with REAL install paths;
 *     parses gate JSONL; asserts G-6 ≤ 1800000ms. Carries the empirical
 *     evidence captured in the M11 findings doc.
 *
 * Spec source:
 *   - holding/plans/native-v1.0/M11-dogfood.md (§A-3, T-225, D-NS-47)
 *   - holding/research/2026-04-29-native-d5-invariant-register.md (I-11)
 *   - .enforcement/codex-reviews/2026-04-30-m11-pre-dispatch.md (P2.1)
 *
 * Realizes the D-NS-37 stub at `tests/integration/m9-invariants-consolidated.test.ts`.
 */

import { describe, it, expect } from 'vitest'
import { spawnSync } from 'node:child_process'
import { resolve, dirname } from 'node:path'
import { fileURLToPath } from 'node:url'
import { rmSync } from 'node:fs'

import {
  runDogfood,
  I_11_THRESHOLD_MS,
  type DogfoodResult,
  type GateRecord,
} from '../../scripts/dogfood-time-to-value.js'

// =============================================================================
// CI variant (always runs) — real engine path with hermetic fake-install.
// =============================================================================

describe('M11 — I-11 time-to-value (CI variant: real G-2..G-5 with hermetic fake-install)', () => {
  it('runs the REAL engine path through executeStepGraph and emits PASS', async () => {
    // Per D-NS-47 fold: stubInstall=true substitutes G-1a/G-1b synthetic ms;
    // G-2..G-5 run for real against the package working tree. Use a temp
    // artifact dir to keep test runs hermetic.
    const here = dirname(fileURLToPath(import.meta.url))
    const artifactDir = resolve(here, '..', '..', '.tmp-m11-test-artifact')
    let result: DogfoodResult
    try {
      result = await runDogfood({ stubInstall: true, silent: true, artifactDir })
    } finally {
      try {
        rmSync(artifactDir, { recursive: true, force: true })
      } catch {
        // ignore cleanup error
      }
    }

    // I-11 verdict shape — closed when total_ms ≤ threshold
    expect(result.verdict).toBe('PASS')
    expect(result.ps_13_status).toBe('CLOSED')
    expect(result.threshold_ms).toBe(I_11_THRESHOLD_MS)

    // Real engine path completed (not a parser test)
    expect(result.fixture_summary.terminal_state).toBe('success')
    expect(result.fixture_summary.completed_step_ids).toEqual([1, 2, 3, 4, 5, 6])
    expect(result.fixture_summary.workflow_id).toBe('W-build-completion-verification-hook')
    expect(result.fixture_summary.charter_id).toBe('C-vinit-feedback-resolution')
    expect(result.fixture_summary.domain_id).toBe('D1.D2')

    // All 8 gates emitted (G-0, G-1a, G-1b, G-2, G-3, G-4, G-5, G-6)
    const gateIds = result.gates.map((g) => g.gate)
    expect(gateIds).toEqual(['G-0', 'G-1a', 'G-1b', 'G-2', 'G-3', 'G-4', 'G-5', 'G-6'])

    // Per-gate engine-path budget: G-2..G-5 sum should be well under 5000ms
    // when stubInstall=true (excludes any real install timing). This proves
    // the engine integration is fast enough that I-11 latency is dominated
    // by install path, not engine path.
    const engineGates = result.gates.filter((g) => ['G-2', 'G-3', 'G-4', 'G-5'].includes(g.gate))
    expect(engineGates).toHaveLength(4)
    const enginePathMs =
      Math.max(...engineGates.map((g) => g.ms_since_start)) -
      Math.min(...engineGates.map((g) => g.ms_since_start))
    expect(enginePathMs).toBeLessThan(5000)

    // Stubbed install gates emit synthetic notes
    const g1a = result.gates.find((g) => g.gate === 'G-1a')!
    expect(g1a.notes ?? '').toMatch(/stubbed/)

    // Marketplace string captured (per A-7 reproducibility context)
    expect(result.marketplace_install_string.length).toBeGreaterThan(0)
  }, 30_000)

  it('I-11 threshold matches D5 invariant register (1800000ms = 30min)', () => {
    expect(I_11_THRESHOLD_MS).toBe(30 * 60 * 1000)
  })

  it('GateRecord shape exposes ms_since_start so downstream tools can compute variance', async () => {
    const here = dirname(fileURLToPath(import.meta.url))
    const artifactDir = resolve(here, '..', '..', '.tmp-m11-shape-artifact')
    let result: DogfoodResult
    try {
      result = await runDogfood({ stubInstall: true, silent: true, artifactDir })
    } finally {
      try {
        rmSync(artifactDir, { recursive: true, force: true })
      } catch {
        // ignore
      }
    }
    for (const g of result.gates as GateRecord[]) {
      expect(typeof g.gate).toBe('string')
      expect(typeof g.label).toBe('string')
      expect(typeof g.ts).toBe('number')
      expect(typeof g.ms_since_start).toBe('number')
      expect(g.ms_since_start).toBeGreaterThanOrEqual(0)
    }
  }, 30_000)
})

// =============================================================================
// Real-clock variant (gated behind RUN_REAL_DOGFOOD=1).
// =============================================================================

const REAL_DOGFOOD_ENABLED = process.env.RUN_REAL_DOGFOOD === '1'

describe.runIf(REAL_DOGFOOD_ENABLED)(
  'M11 — I-11 time-to-value (real-clock variant; RUN_REAL_DOGFOOD=1)',
  () => {
    it('spawns dogfood script with real install path; asserts G-6 ≤ 1800000ms', () => {
      const here = dirname(fileURLToPath(import.meta.url))
      const scriptPath = resolve(here, '..', '..', 'scripts', 'dogfood-time-to-value.ts')

      const proc = spawnSync('npx', ['tsx', scriptPath], {
        cwd: resolve(here, '..', '..'),
        encoding: 'utf-8',
        timeout: I_11_THRESHOLD_MS + 60_000,
      })

      expect(proc.status === 0 || proc.status === 1).toBe(true)
      // Parse gate JSONL — every line that's not a `#`-prefixed summary line
      const lines = (proc.stdout ?? '')
        .split('\n')
        .filter((l) => l.length > 0 && !l.startsWith('#'))
      const gates = lines.map((l) => JSON.parse(l) as GateRecord)
      const g6 = gates.find((g) => g.gate === 'G-6')
      expect(g6).toBeDefined()
      expect(g6!.ms_since_start).toBeLessThanOrEqual(I_11_THRESHOLD_MS)
    }, I_11_THRESHOLD_MS + 120_000)
  },
)
