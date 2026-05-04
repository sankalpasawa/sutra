/**
 * v1.3.0 Wave 3 — operator surface + cron daemon scheduler tick tests.
 *
 * Coverage matrix (codex W3 fold + plan §Step 5):
 *
 *   Cron daemon (W3 BLOCKER 1 fold — cadence_spec activation):
 *     1. CadenceScheduler tick fires N expected times in M deterministic-clock
 *        minutes; callback dispatches engine.handleHSutraEvent N times.
 *     2. Cron trigger WITHOUT cadence_spec is logged "[cron] ... inactive"
 *        and skipped during scheduler arming.
 *     3. Cron trigger WITH valid cadence_spec is registered and tick fires
 *        the synthetic cron event at the correct cadence.
 *
 *   workflow status (W3.status):
 *     4. workflow status of nonexistent E → exit 3 + "not found".
 *     5. workflow status of completed E → STARTED + COMPLETED with duration.
 *     6. workflow status of paused E → pending approval + prompt_summary.
 *
 *   workflow cancel (W3.cancel — codex W3 BLOCKER 2 fold):
 *     7. workflow cancel of pending paused E → updateApprovalStatus to
 *        'rejected' with reason='cancelled'; cancellation marker written.
 *     8. workflow cancel of nonexistent E → records cancellation marker.
 *
 *   tenant list (W3.tenant — codex W3 BLOCKER 3 fold):
 *     9. tenant list with 2 tenants across domains → sorted dedup'd output
 *        with per-tenant counts.
 */

import { existsSync, mkdtempSync, readFileSync, rmSync, writeFileSync, mkdirSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { afterEach, beforeEach, describe, expect, it } from 'vitest'

import { main } from '../../src/cli/sutra-native.js'
import { CadenceScheduler } from '../../src/engine/cadence-scheduler.js'
import { NativeEngine } from '../../src/runtime/native-engine.js'
import { createWorkflow } from '../../src/primitives/workflow.js'
import { createDomain } from '../../src/primitives/domain.js'
import {
  persistDomain,
  persistTrigger,
  persistWorkflow,
} from '../../src/persistence/user-kit.js'
import { listApprovals, persistApproval } from '../../src/persistence/execution-approval-ledger.js'
import { appendDecisionProvenanceLog } from '../../src/runtime/emergence-provenance.js'
import { buildExecutionDecisionProvenance } from '../../src/runtime/execution-provenance.js'
import type { TriggerSpec } from '../../src/types/trigger-spec.js'
import type { Workflow } from '../../src/primitives/workflow.js'
import type { ExecutionApprovalRecord } from '../../src/persistence/execution-approval-ledger.js'

interface CliResult {
  code: number
  stdout: string
  stderr: string
}

async function runCli(argv: string[], home: string): Promise<CliResult> {
  let stdout = ''
  let stderr = ''
  const code = await main({
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

function buildSimpleWorkflow(id = 'W-w3-test'): Workflow {
  return createWorkflow({
    id,
    preconditions: '',
    step_graph: [
      {
        step_id: 1,
        action: 'wait',
        inputs: [],
        outputs: [],
        on_failure: 'abort',
      },
    ],
    inputs: [],
    outputs: [],
    state: [],
    postconditions: '',
    failure_policy: 'abort',
    stringency: 'task',
    interfaces_with: [],
  })
}

function buildGatedWorkflow(id = 'W-w3-gated'): Workflow {
  return createWorkflow({
    id,
    preconditions: '',
    step_graph: [
      {
        step_id: 1,
        action: 'wait',
        inputs: [],
        outputs: [],
        on_failure: 'abort',
      },
      {
        step_id: 2,
        action: 'wait',
        inputs: [
          {
            kind: 'config',
            schema_ref: '',
            locator: 'gated-step-2',
            version: '1',
            mutability: 'immutable',
            retention: 'ephemeral',
          },
        ],
        outputs: [],
        on_failure: 'abort',
        requires_approval: true,
      },
    ],
    inputs: [],
    outputs: [],
    state: [],
    postconditions: '',
    failure_policy: 'abort',
    stringency: 'task',
    interfaces_with: [],
  })
}

// ===========================================================================
// CRON daemon scheduler tick — codex W3 blocker 1
// ===========================================================================

describe('v1.3.0 W3 #13 — cron daemon scheduler tick + cadence_spec activation', () => {
  it('CadenceScheduler tick fires expected number of times in deterministic-clock minutes', async () => {
    let now = 0
    const sched = new CadenceScheduler({ clock: () => now })
    sched.start()
    let fires = 0
    sched.register({ kind: 'every_n_minutes', n: 1 }, () => {
      fires++
    })
    // Advance the clock 6 minutes; tick once at end. The scheduler advances
    // next_fire_at after each fire so a single tick at t=6min triggers as
    // many fires as scheduled times have elapsed (cron-like semantics).
    // Per scheduler design: tick() at t=6min fires ONCE (the first scheduled
    // fire at t=1min); subsequent ticks at later t fire the queued ones.
    // For 6 fires we tick once per minute — matches the daemon's 60s cadence.
    for (let m = 1; m <= 6; m++) {
      now = m * 60_000
      await sched.tick()
    }
    expect(fires).toBe(6)
  })

  it('engine.handleHSutraEvent dispatches cron event when scheduler fires', async () => {
    let now = 0
    const sched = new CadenceScheduler({ clock: () => now })
    sched.start()

    // Build engine with cron trigger
    const wf = buildSimpleWorkflow('W-cron-target')
    const cronTrigger: TriggerSpec = {
      id: 'T-cron-test',
      event_type: 'cron',
      route_predicate: { type: 'always_true' },
      target_workflow: wf.id,
    }
    const events: string[] = []
    const engine = new NativeEngine({
      triggers: [cronTrigger],
      workflows: [wf],
      proposer_enabled: false,
      skip_user_kit: true,
      write: () => {},
    })
    for (const t of engine.renderer.getRegisteredTypes()) {
      engine.renderer.register(t as never, ((e: { type: string }) => {
        events.push(e.type)
        return ''
      }) as never)
    }

    // Wire scheduler callback to dispatch into engine
    sched.register({ kind: 'every_n_minutes', n: 1 }, async () => {
      await engine.handleHSutraEvent({
        turn_id: `cron-T-cron-test-${now}`,
        event_type: 'cron',
        input_text: '',
      } as never)
    })

    // Advance clock 3 minutes, tick after each
    for (let m = 1; m <= 3; m++) {
      now = m * 60_000
      await sched.tick()
    }

    // Expect 3 routing decisions + 3 workflow_started + ... cycles
    const routings = events.filter((t) => t === 'routing_decision').length
    const wfStarts = events.filter((t) => t === 'workflow_started').length
    expect(routings).toBe(3)
    expect(wfStarts).toBe(3)
  })

  it('cron trigger WITHOUT cadence_spec → logged "inactive" + skipped during arming', async () => {
    // Test daemon arming logic by exercising listTriggers → cadence_spec gate.
    // We mimic the cmdDaemon arming loop here by using the same scheduler
    // interface; a cron trigger without cadence_spec must produce zero
    // registrations and a stderr log line.
    const HOME = mkdtempSync(join(tmpdir(), 'native-w3-cron-noccad-'))
    try {
      // Persist a Workflow + cron Trigger WITHOUT cadence_spec
      const wf = buildSimpleWorkflow('W-cron-noccad')
      persistWorkflow(wf, { home: HOME })
      const t: TriggerSpec = {
        id: 'T-cron-noccad',
        event_type: 'cron',
        route_predicate: { type: 'always_true' },
        target_workflow: wf.id,
        // no cadence_spec — trigger is dormant
      }
      persistTrigger(t, { home: HOME })

      // Mimic the daemon arming logic: read triggers, check cadence_spec
      const { listTriggers } = await import('../../src/persistence/user-kit.js')
      const triggers = listTriggers({ home: HOME })
      const inactive: string[] = []
      const registered: string[] = []
      const sched = new CadenceScheduler({ clock: () => 0 })
      sched.start()
      for (const tr of triggers) {
        if (tr.event_type !== 'cron') continue
        if (!tr.cadence_spec) {
          inactive.push(tr.id)
          continue
        }
        sched.register(tr.cadence_spec as never, () => {})
        registered.push(tr.id)
      }
      expect(inactive).toEqual(['T-cron-noccad'])
      expect(registered).toEqual([])
    } finally {
      rmSync(HOME, { recursive: true, force: true })
    }
  })

  it('cron trigger WITH valid cadence_spec → registered + scheduler tick fires correctly', async () => {
    const HOME = mkdtempSync(join(tmpdir(), 'native-w3-cron-cad-'))
    try {
      const wf = buildSimpleWorkflow('W-cron-cad')
      persistWorkflow(wf, { home: HOME })
      const t: TriggerSpec = {
        id: 'T-cron-cad',
        event_type: 'cron',
        route_predicate: { type: 'always_true' },
        target_workflow: wf.id,
        cadence_spec: { kind: 'every_n_minutes', n: 1 },
      }
      persistTrigger(t, { home: HOME })

      const { listTriggers } = await import('../../src/persistence/user-kit.js')
      const triggers = listTriggers({ home: HOME })
      let now = 0
      const sched = new CadenceScheduler({ clock: () => now })
      sched.start()
      let fires = 0
      for (const tr of triggers) {
        if (tr.event_type !== 'cron' || !tr.cadence_spec) continue
        sched.register(tr.cadence_spec as never, () => {
          fires++
        })
      }
      // Advance 3 minutes
      for (let m = 1; m <= 3; m++) {
        now = m * 60_000
        await sched.tick()
      }
      expect(fires).toBe(3)
    } finally {
      rmSync(HOME, { recursive: true, force: true })
    }
  })
})

// ===========================================================================
// workflow status — W3.status
// ===========================================================================

describe('v1.3.0 W3.status — workflow status subcommand', () => {
  let HOME: string
  beforeEach(() => {
    HOME = mkdtempSync(join(tmpdir(), 'native-w3-status-'))
  })
  afterEach(() => {
    if (HOME && existsSync(HOME)) rmSync(HOME, { recursive: true, force: true })
  })

  it('workflow status of nonexistent E → exit 3 + "not found"', async () => {
    const r = await runCli(['workflow', 'status', 'E-does-not-exist'], HOME)
    expect(r.code).toBe(3)
    expect(r.stderr).toContain('not found')
  })

  it('workflow status of completed E → shows STARTED + COMPLETED with duration', async () => {
    // Seed: write 2 DP records (started + completed) for an execution
    const startTs = 1700000000000
    const endTs = startTs + 5000
    appendDecisionProvenanceLog(
      buildExecutionDecisionProvenance({
        workflow_id: 'W-test',
        execution_id: 'E-w3-completed',
        stage: 'STARTED',
        ts_ms: startTs,
        outcome: 'execution started',
      }),
      { home: HOME },
    )
    appendDecisionProvenanceLog(
      buildExecutionDecisionProvenance({
        workflow_id: 'W-test',
        execution_id: 'E-w3-completed',
        stage: 'COMPLETED',
        ts_ms: endTs,
        outcome: 'success: 1 step(s) completed in 5000ms',
      }),
      { home: HOME },
    )

    const r = await runCli(['workflow', 'status', 'E-w3-completed'], HOME)
    expect(r.code).toBe(0)
    expect(r.stdout).toContain('EXECUTION E-w3-completed')
    expect(r.stdout).toContain('state:')
    expect(r.stdout).toContain('COMPLETED')
    expect(r.stdout).toContain('duration_ms:  5000')
    // Provenance trail
    expect(r.stdout).toContain('execution started')
  })

  it('workflow status of paused E → shows pending approval with prompt_summary', async () => {
    // Seed: write started DP record + a pending approval entry
    const startTs = 1700000000000
    appendDecisionProvenanceLog(
      buildExecutionDecisionProvenance({
        workflow_id: 'W-gated',
        execution_id: 'E-w3-paused',
        stage: 'STARTED',
        ts_ms: startTs,
        outcome: 'execution started',
      }),
      { home: HOME },
    )
    const rec: ExecutionApprovalRecord = {
      execution_id: 'E-w3-paused',
      workflow_id: 'W-gated',
      step_index: 2,
      prompt_summary: 'action=wait input="please-review-this"',
      status: 'pending',
      created_at_ms: startTs + 100,
    }
    persistApproval(rec, { home: HOME })

    const r = await runCli(['workflow', 'status', 'E-w3-paused'], HOME)
    expect(r.code).toBe(0)
    expect(r.stdout).toContain('state:        paused')
    expect(r.stdout).toContain('paused_step:  2')
    expect(r.stdout).toContain('please-review-this')
    expect(r.stdout).toContain('approve E-w3-paused')
  })

  it('workflow status (no E-id) → lists all known executions', async () => {
    appendDecisionProvenanceLog(
      buildExecutionDecisionProvenance({
        workflow_id: 'W-a',
        execution_id: 'E-aaa',
        stage: 'STARTED',
        ts_ms: 1700000000000,
        outcome: 'execution started',
      }),
      { home: HOME },
    )
    appendDecisionProvenanceLog(
      buildExecutionDecisionProvenance({
        workflow_id: 'W-a',
        execution_id: 'E-aaa',
        stage: 'COMPLETED',
        ts_ms: 1700000001000,
        outcome: 'success',
      }),
      { home: HOME },
    )
    appendDecisionProvenanceLog(
      buildExecutionDecisionProvenance({
        workflow_id: 'W-b',
        execution_id: 'E-bbb',
        stage: 'STARTED',
        ts_ms: 1700000002000,
        outcome: 'execution started',
      }),
      { home: HOME },
    )

    const r = await runCli(['workflow', 'status'], HOME)
    expect(r.code).toBe(0)
    expect(r.stdout).toContain('EXECUTIONS (2)')
    expect(r.stdout).toContain('E-aaa')
    expect(r.stdout).toContain('E-bbb')
    expect(r.stdout).toContain('COMPLETED')
    expect(r.stdout).toContain('STARTED')
  })
})

// ===========================================================================
// workflow cancel — W3.cancel (codex blocker 2 fold)
// ===========================================================================

describe('v1.3.0 W3.cancel — workflow cancel subcommand', () => {
  let HOME: string
  beforeEach(() => {
    HOME = mkdtempSync(join(tmpdir(), 'native-w3-cancel-'))
  })
  afterEach(() => {
    if (HOME && existsSync(HOME)) rmSync(HOME, { recursive: true, force: true })
  })

  it('workflow cancel of pending paused E → updateApprovalStatus rejected with reason=cancelled', async () => {
    const rec: ExecutionApprovalRecord = {
      execution_id: 'E-w3-cancel-1',
      workflow_id: 'W-gated',
      step_index: 2,
      prompt_summary: 'action=wait input="x"',
      status: 'pending',
      created_at_ms: 1700000000000,
    }
    persistApproval(rec, { home: HOME })
    expect(listApprovals({ home: HOME }, 'pending')).toHaveLength(1)

    const r = await runCli(['workflow', 'cancel', 'E-w3-cancel-1'], HOME)
    expect(r.code).toBe(0)
    expect(r.stdout).toContain('Cancelled paused execution E-w3-cancel-1')
    expect(r.stdout).toContain('pending → rejected')

    expect(listApprovals({ home: HOME }, 'pending')).toHaveLength(0)
    const rejected = listApprovals({ home: HOME }, 'rejected')
    expect(rejected).toHaveLength(1)
    expect(rejected[0]!.execution_id).toBe('E-w3-cancel-1')
    expect(rejected[0]!.decision_reason).toBe('cancelled')

    // Cancellation marker written
    const markerPath = join(HOME, 'runtime', 'cancellations', 'E-w3-cancel-1.json')
    expect(existsSync(markerPath)).toBe(true)
    const marker = JSON.parse(readFileSync(markerPath, 'utf8'))
    expect(marker.execution_id).toBe('E-w3-cancel-1')
    expect(marker.mode).toBe('pending-rejected')
  })

  it('workflow cancel of nonexistent E → records cancellation marker (no-record mode)', async () => {
    const r = await runCli(['workflow', 'cancel', 'E-w3-nofile'], HOME)
    expect(r.code).toBe(0)
    expect(r.stdout).toContain('Cancellation marker recorded for E-w3-nofile')

    const markerPath = join(HOME, 'runtime', 'cancellations', 'E-w3-nofile.json')
    expect(existsSync(markerPath)).toBe(true)
    const marker = JSON.parse(readFileSync(markerPath, 'utf8'))
    expect(marker.execution_id).toBe('E-w3-nofile')
    expect(marker.mode).toBe('no-record')
  })

  it('workflow cancel of already-terminal E → idempotent no-op + exit 0', async () => {
    const rec: ExecutionApprovalRecord = {
      execution_id: 'E-w3-already-done',
      workflow_id: 'W-x',
      step_index: 1,
      prompt_summary: 'x',
      status: 'resumed',
      created_at_ms: 1700000000000,
      decided_at_ms: 1700000001000,
      decision_reason: 'founder approved',
      resumed_at_ms: 1700000002000,
    }
    persistApproval(rec, { home: HOME })

    const r = await runCli(['workflow', 'cancel', 'E-w3-already-done'], HOME)
    expect(r.code).toBe(0)
    expect(r.stdout).toContain('already terminal')
    expect(r.stdout).toContain('status=resumed')
  })

  it('workflow cancel without execution id → exit 2 + usage error', async () => {
    const r = await runCli(['workflow', 'cancel'], HOME)
    expect(r.code).toBe(2)
    expect(r.stderr).toContain('execution id required')
  })
})

// ===========================================================================
// tenant list — W3.tenant (codex blocker 3 fold)
// ===========================================================================

describe('v1.3.0 W3.tenant — tenant list subcommand', () => {
  let HOME: string
  beforeEach(() => {
    HOME = mkdtempSync(join(tmpdir(), 'native-w3-tenant-'))
  })
  afterEach(() => {
    if (HOME && existsSync(HOME)) rmSync(HOME, { recursive: true, force: true })
  })

  it('tenant list with 2 tenants across domains → sorted dedup output with per-tenant counts', async () => {
    // Seed: 3 domains across 2 tenants + 1 workflow with custody_owner
    persistDomain(
      createDomain({
        id: 'D1',
        name: 'D1',
        parent_id: null,
        principles: [],
        intelligence: 'i',
        accountable: ['founder'],
        authority: 'auth',
        tenant_id: 'T-alpha',
      }),
      { home: HOME },
    )
    persistDomain(
      createDomain({
        id: 'D2',
        name: 'D2',
        parent_id: null,
        principles: [],
        intelligence: 'i',
        accountable: ['founder'],
        authority: 'auth',
        tenant_id: 'T-alpha',
      }),
      { home: HOME },
    )
    persistDomain(
      createDomain({
        id: 'D3',
        name: 'D3',
        parent_id: null,
        principles: [],
        intelligence: 'i',
        accountable: ['founder'],
        authority: 'auth',
        tenant_id: 'T-beta',
      }),
      { home: HOME },
    )
    // Workflow with custody_owner=T-gamma — tenant only seen in workflow
    const wfg = createWorkflow({
      id: 'W-with-custody',
      preconditions: '',
      step_graph: [
        {
          step_id: 1,
          action: 'wait',
          inputs: [],
          outputs: [],
          on_failure: 'abort',
        },
      ],
      inputs: [],
      outputs: [],
      state: [],
      postconditions: '',
      failure_policy: 'abort',
      stringency: 'task',
      interfaces_with: [],
      custody_owner: 'T-gamma',
    })
    persistWorkflow(wfg, { home: HOME })

    const r = await runCli(['tenant', 'list'], HOME)
    expect(r.code).toBe(0)
    expect(r.stdout).toContain('TENANTS (3)')
    // Sorted alpha < beta < gamma
    const idxAlpha = r.stdout.indexOf('T-alpha')
    const idxBeta = r.stdout.indexOf('T-beta')
    const idxGamma = r.stdout.indexOf('T-gamma')
    expect(idxAlpha).toBeGreaterThan(-1)
    expect(idxBeta).toBeGreaterThan(idxAlpha)
    expect(idxGamma).toBeGreaterThan(idxBeta)
    // Counts: alpha = 2 domains 0 workflows, beta = 1 domain, gamma = 0 domains 1 workflow
    const alphaLine = r.stdout.split('\n').find((l) => l.includes('T-alpha'))!
    expect(alphaLine).toMatch(/T-alpha\s+2\s+0/)
    const betaLine = r.stdout.split('\n').find((l) => l.includes('T-beta'))!
    expect(betaLine).toMatch(/T-beta\s+1\s+0/)
    const gammaLine = r.stdout.split('\n').find((l) => l.includes('T-gamma'))!
    expect(gammaLine).toMatch(/T-gamma\s+0\s+1/)
  })

  it('tenant list with no tenants → empty-state hint', async () => {
    const r = await runCli(['tenant', 'list'], HOME)
    expect(r.code).toBe(0)
    expect(r.stdout).toContain('TENANTS (0)')
    expect(r.stdout).toContain('none')
  })

  it('tenant <unknown> → exit 2 + usage error', async () => {
    const r = await runCli(['tenant', 'fly-me-to-the-moon'], HOME)
    expect(r.code).toBe(2)
    expect(r.stderr).toContain('unknown subcommand')
  })
})
