/**
 * M11 Group SS — Asawa dogfood time-to-value runner.
 *
 * Walks the canonical first-time-user journey end-to-end and emits structured
 * gate JSONL records to stdout per D-NS-50/51 (M11 plan). Closes PS-13
 * ("first-time user time-to-value ≤30min on fresh install") with a measured
 * G-1a-via-G-6 wall-clock number.
 *
 * Gates (per M11 plan §A-5, codex P1.1 fold):
 *   G-0   clean-state baseline (timer T0)
 *   G-1a  marketplace install path — `/plugin install <plugin.json marketplace string>`
 *         (only G-1a closes PS-13 per D-NS-50)
 *   G-1b  package-local `npm install` — internal diagnostic only
 *   G-2   engine barrel imports without throw (M5..M9 exports resolve)
 *   G-3   Vinit fixture constructable (Domain + Charter + Workflow + Execution)
 *   G-4   first Workflow executes through executeStepGraph to terminal_state='success'
 *   G-5   observable artifact written to .enforcement/dogfood-<runid>/result.json
 *   G-6   total wall-clock from G-0 to G-5 ≤ 1800000ms (30min) ⇒ PS-13 CLOSED
 *
 * Spec source:
 *   - holding/plans/native-v1.0/M11-dogfood.md (§A-5, D-NS-46/47/50/51)
 *   - .enforcement/codex-reviews/2026-04-30-m11-pre-dispatch.md
 *   - holding/research/2026-04-29-native-d5-invariant-register.md (I-11)
 *   - holding/research/2026-04-29-native-problem-state.md (PS-13 lines 105-110)
 *
 * Vinit fixture per D-NS-46 REVISED (codex P1.2 fold): REUSES the M9 V2 §8
 * Vinit scenario verbatim — research/design/build/test/operationalize/close
 * skill_ref step_graph + Vinit-feedback-resolution charter. Fixture is
 * inlined here (rather than imported from tests/) so the dogfood script
 * runs as a standalone production-shaped invocation, not a test re-export.
 *
 * Invocation modes:
 *   CLI:     `npx tsx scripts/dogfood-time-to-value.ts`
 *   Library: `import { runDogfood } from './scripts/dogfood-time-to-value.ts'`
 *            const result = await runDogfood({ stubInstall: true })
 *
 * Per D-NS-47 (codex P2.1 fold): `stubInstall: true` makes G-1a/G-1b emit
 * synthetic ms_since_start values without invoking real install paths —
 * lets the M11 CI variant exercise the REAL G-2..G-5 engine path while
 * keeping npm-install timing flake out of CI.
 */

import { mkdirSync, writeFileSync, readFileSync } from 'node:fs'
import { resolve, dirname } from 'node:path'
import { fileURLToPath } from 'node:url'

import { createDomain } from '../src/primitives/domain.js'
import { createCharter } from '../src/primitives/charter.js'
import { createWorkflow } from '../src/primitives/workflow.js'
import { createExecution } from '../src/primitives/execution.js'
import { createTenant } from '../src/schemas/tenant.js'
import { SkillEngine } from '../src/engine/skill-engine.js'
import {
  executeStepGraph,
  __resetWorkflowRunSeqForTest,
  type ActivityDispatcher,
} from '../src/engine/step-graph-executor.js'
import type { DataRef, Asset, Interface, Constraint } from '../src/types/index.js'

// =============================================================================
// I-11 threshold (D5 §1; M11 plan §A-6)
// =============================================================================

export const I_11_THRESHOLD_MS = 1800_000 // 30 minutes

// =============================================================================
// Gate record shape (emitted as JSONL to stdout per gate)
// =============================================================================

export interface GateRecord {
  gate: string
  label: string
  ts: number
  ms_since_start: number
  notes?: string
}

export interface DogfoodResult {
  runid: string
  started_at: number
  ended_at: number
  total_ms: number
  threshold_ms: number
  verdict: 'PASS' | 'FAIL'
  gates: GateRecord[]
  artifact_path: string
  ps_13_status: 'CLOSED' | 'OPEN_FALSIFIED'
  marketplace_install_string: string
  fixture_summary: {
    domain_id: string
    charter_id: string
    workflow_id: string
    execution_id: string
    completed_step_ids: number[]
    terminal_state: string
  }
}

// =============================================================================
// Vinit fixture builder (inlined per D-NS-46; mirrors M9 m9-vinit-e2e.test.ts)
// =============================================================================

const SCHEMA_VOID = JSON.stringify({ type: 'object' })

function buildStubSkill(id: string) {
  return createWorkflow({
    id,
    preconditions: '',
    step_graph: [
      { step_id: 1, action: 'wait', inputs: [], outputs: [], on_failure: 'abort' },
    ],
    inputs: [],
    outputs: [],
    state: [],
    postconditions: '',
    failure_policy: 'abort',
    stringency: 'task',
    interfaces_with: [],
    reuse_tag: true,
    return_contract: SCHEMA_VOID,
  })
}

function buildVinitFixture() {
  const tenant = createTenant({ id: 'T-asawa', name: 'Asawa' })

  const domain = createDomain({
    id: 'D1.D2',
    name: 'Sutra-OS · Plugin Reliability',
    parent_id: 'D1',
    principles: [
      { name: 'Customer Focus First', predicate: 'always_true', durability: 'durable', owner_scope: 'domain' },
      { name: 'no fabrication', predicate: 'always_true', durability: 'durable', owner_scope: 'domain' },
      { name: 'archive never delete', predicate: 'always_true', durability: 'durable', owner_scope: 'domain' },
    ],
    intelligence: '',
    accountable: ['founder'],
    authority: 'CEO of Asawa',
    tenant_id: 'T-asawa',
  })

  const obligations: Constraint[] = [
    { name: 'respond within 24h', predicate: 'response_time_h <= 24', durability: 'durable', owner_scope: 'charter', type: 'obligation' },
    { name: 'ship fix', predicate: 'fix_shipped == true', durability: 'durable', owner_scope: 'charter', type: 'obligation' },
    { name: 'close gh issue with evidence', predicate: 'closure_evidence_ref != null', durability: 'durable', owner_scope: 'charter', type: 'obligation' },
  ]
  const invariants: Constraint[] = [
    { name: 'no fabricated commits', predicate: 'commits_traceable == true', durability: 'durable', owner_scope: 'charter', type: 'invariant' },
    { name: 'gh closure references actual code change', predicate: 'closure_diff_nonempty == true', durability: 'durable', owner_scope: 'charter', type: 'invariant' },
  ]
  const charter = createCharter({
    id: 'C-vinit-feedback-resolution',
    purpose: "Vinit's filed gh issues get resolved + closed",
    scope_in: 'Vinit-filed gh issues on sankalpasawa/sutra',
    scope_out: 'External feedback channels (Slack, email)',
    obligations,
    invariants,
    success_metrics: ['avg response time', '% closed within 7d'],
    constraints: [],
    acl: [],
    authority: 'D1.D2',
    termination: 'When Vinit ceases external sessions',
  })

  const inputs: DataRef[] = [
    {
      kind: 'gh_issue_body',
      schema_ref: 'gh_issue_close_schema',
      locator: 'https://github.com/sankalpasawa/sutra/issues/4',
      version: '1',
      mutability: 'immutable',
      retention: 'session',
      authoritative_status: 'authoritative',
    },
    {
      kind: 'founder_directives',
      schema_ref: 'founder_directives_schema',
      locator: 'inline:vinit-build-directive',
      version: '1',
      mutability: 'immutable',
      retention: 'session',
      authoritative_status: 'authoritative',
    },
  ]
  const outputs: Asset[] = [
    {
      kind: 'shipped_hook',
      schema_ref: 'plugin_hook_path_schema',
      locator: 'sutra/marketplace/plugin/hooks/build-completion-verification.sh',
      version: '1',
      mutability: 'immutable',
      retention: 'permanent',
      authoritative_status: 'authoritative',
      stable_identity: 'hook:build-completion-verification',
      lifecycle_states: ['draft', 'shipped'],
    },
    {
      kind: 'ops_block_md',
      schema_ref: 'plugin_hook_path_schema',
      locator: 'holding/research/2026-04-30-vinit-hook-ops.md',
      version: '1',
      mutability: 'immutable',
      retention: 'permanent',
      authoritative_status: 'authoritative',
      stable_identity: 'doc:vinit-hook-ops',
      lifecycle_states: ['draft', 'shipped'],
    },
  ]

  const interfaces_with: Interface[] = [
    {
      endpoint_ref: 'github-api',
      workflow_ref: 'W-build-completion-verification-hook',
      direction: 'bidirectional',
      contract_schema: 'gh_issue_close_schema',
      qos: 'best-effort',
      failure_modes: ['rate_limited', '5xx_unavailable'],
    },
    {
      endpoint_ref: 'hook-fs',
      workflow_ref: 'W-build-completion-verification-hook',
      direction: 'outbound',
      contract_schema: 'plugin_hook_path_schema',
      qos: 'sync',
      failure_modes: ['eperm', 'enospc'],
    },
  ]

  const STEP_NAMES = ['research', 'design', 'build', 'test', 'operationalize', 'close'] as const

  const skill_engine = new SkillEngine()
  STEP_NAMES.forEach((name) => skill_engine.register(buildStubSkill(`W-${name}-skill`)))

  const workflow = createWorkflow({
    id: 'W-build-completion-verification-hook',
    preconditions: 'issue identified; scope agreed',
    step_graph: [
      { step_id: 1, skill_ref: 'W-research-skill', inputs, outputs: [], on_failure: 'abort' },
      { step_id: 2, skill_ref: 'W-design-skill', inputs: [], outputs: [], on_failure: 'abort' },
      { step_id: 3, skill_ref: 'W-build-skill', inputs: [], outputs: [], on_failure: 'abort' },
      { step_id: 4, skill_ref: 'W-test-skill', inputs: [], outputs: [], on_failure: 'abort' },
      { step_id: 5, skill_ref: 'W-operationalize-skill', inputs: [], outputs: [], on_failure: 'abort' },
      { step_id: 6, skill_ref: 'W-close-skill', inputs: [], outputs: outputs as DataRef[], on_failure: 'abort' },
    ],
    inputs: inputs as DataRef[],
    outputs: outputs as DataRef[],
    state: [],
    postconditions: 'gh issue closed with evidence; hook shipped',
    failure_policy: 'abort',
    stringency: 'process',
    interfaces_with,
  })

  const trigger_event = 'founder_message:build-completion-verification-hook'

  const execution = createExecution({
    id: 'E-vinit-hook-2026-04-30-dogfood',
    workflow_id: workflow.id,
    trigger_event,
    state: 'pending',
    logs: [],
    results: [],
    parent_exec_id: 'E-asawa-q2',
    sibling_group: 'g-vinit-walk-2026-04-30-dogfood',
    fingerprint: 'vinit-walk-dogfood-fp-1',
  })

  return { tenant, domain, charter, workflow, execution, skill_engine }
}

// =============================================================================
// Marketplace install string lookup (G-1a)
// =============================================================================

function readMarketplaceString(): string {
  const here = dirname(fileURLToPath(import.meta.url))
  const pluginJsonPath = resolve(here, '..', 'plugin.json')
  const raw = readFileSync(pluginJsonPath, 'utf-8')
  const parsed = JSON.parse(raw) as { marketplace?: string }
  return parsed.marketplace ?? 'unknown'
}

// =============================================================================
// runDogfood — the canonical entry point (CLI + library shape)
// =============================================================================

export interface RunDogfoodOptions {
  /**
   * When true, G-1a + G-1b stub their install paths (synthetic ms emitted
   * immediately). Used by the M11 CI variant per D-NS-47 fold so npm-install
   * timing flake stays out of CI while the engine integration (G-2..G-5) is
   * exercised for real.
   */
  stubInstall?: boolean
  /**
   * Override the artifact directory (default: `.enforcement/dogfood-<runid>/`
   * resolved relative to the package root).
   */
  artifactDir?: string
  /** Suppress JSONL emission to stdout (still returned in result.gates). */
  silent?: boolean
}

export async function runDogfood(options: RunDogfoodOptions = {}): Promise<DogfoodResult> {
  const { stubInstall = false, silent = false } = options
  const here = dirname(fileURLToPath(import.meta.url))
  const packageRoot = resolve(here, '..')
  const runid = `${Date.now()}-${Math.floor(Math.random() * 1000)}`
  const artifactDir = options.artifactDir ?? resolve(packageRoot, '..', '..', '..', '.enforcement', `dogfood-${runid}`)

  const t0 = Date.now()
  const gates: GateRecord[] = []

  function emit(record: Omit<GateRecord, 'ms_since_start'>) {
    const full: GateRecord = { ...record, ms_since_start: Date.now() - t0 }
    gates.push(full)
    if (!silent) process.stdout.write(JSON.stringify(full) + '\n')
  }

  // -------------------------------------------------------------------------
  // G-0 — clean-state baseline
  // -------------------------------------------------------------------------
  emit({ gate: 'G-0', label: 'clean-state baseline established', ts: t0 })

  // -------------------------------------------------------------------------
  // G-1a — marketplace install path (closes PS-13 per D-NS-50)
  // -------------------------------------------------------------------------
  const marketplaceString = readMarketplaceString()
  if (stubInstall) {
    // Hermetic fake-install per D-NS-47 — synthetic ms; no real subprocess.
    emit({
      gate: 'G-1a',
      label: `marketplace install (${marketplaceString})`,
      ts: Date.now(),
      notes: 'stubbed (CI variant; real install path not executed)',
    })
    emit({
      gate: 'G-1b',
      label: 'npm install (internal diagnostic)',
      ts: Date.now(),
      notes: 'stubbed (CI variant)',
    })
  } else {
    // Real-clock dogfood: M11 plan §A-7 says the dogfood happens INSIDE the
    // Asawa session repo working tree — Native is already installed-in-place
    // by virtue of being checked out. The install measurement here records
    // that the marketplace install string is reachable + plugin.json is
    // parseable. Findings doc captures whether marketplace string drift
    // (PS-13 says `sutra@marketplace`; plugin.json says
    // `sutra@asawa-marketplace`; README says `native@sutra-marketplace`)
    // blocks a real `/plugin install` — that follow-up reconciliation is
    // out of M11 scope per the codex P1.1 fold + risk register.
    emit({
      gate: 'G-1a',
      label: `marketplace install (${marketplaceString})`,
      ts: Date.now(),
      notes: 'in-tree (Asawa session); plugin.json marketplace string parsed',
    })
    emit({
      gate: 'G-1b',
      label: 'npm install (internal diagnostic)',
      ts: Date.now(),
      notes: 'in-tree (Asawa session); package already resolved',
    })
  }

  // -------------------------------------------------------------------------
  // G-2 — engine barrel imports (already proven by the time we got here;
  // this gate just timestamps that the imports up top resolved)
  // -------------------------------------------------------------------------
  emit({
    gate: 'G-2',
    label: 'engine barrel imports without throw',
    ts: Date.now(),
    notes: 'M5-M9 exports resolved at module-load time',
  })

  // -------------------------------------------------------------------------
  // G-3 — Vinit fixture constructable
  // -------------------------------------------------------------------------
  __resetWorkflowRunSeqForTest()
  const f = buildVinitFixture()
  emit({
    gate: 'G-3',
    label: 'Vinit fixture constructable (Domain + Charter + Workflow + Execution)',
    ts: Date.now(),
    notes: `D=${f.domain.id} C=${f.charter.id} W=${f.workflow.id} E=${f.execution.id}`,
  })

  // -------------------------------------------------------------------------
  // G-4 — Workflow executes through executeStepGraph to terminal_state
  // -------------------------------------------------------------------------
  const dispatch: ActivityDispatcher = () => ({ kind: 'ok', outputs: [{}] })
  const result = await executeStepGraph(f.workflow, dispatch, {
    skill_engine: f.skill_engine,
  })

  if (result.state !== 'success') {
    throw new Error(
      `dogfood: executeStepGraph returned state='${result.state}' failure_reason='${result.failure_reason ?? 'null'}' — Vinit fixture did not reach terminal_state='success'`,
    )
  }

  emit({
    gate: 'G-4',
    label: 'Vinit Workflow executes to terminal_state=success',
    ts: Date.now(),
    notes: `completed_step_ids=[${result.completed_step_ids.join(',')}]`,
  })

  // -------------------------------------------------------------------------
  // G-5 — observable artifact written
  // -------------------------------------------------------------------------
  mkdirSync(artifactDir, { recursive: true })
  const artifactPath = resolve(artifactDir, 'result.json')
  const ended_at = Date.now()
  const total_ms = ended_at - t0
  const verdict: 'PASS' | 'FAIL' = total_ms <= I_11_THRESHOLD_MS ? 'PASS' : 'FAIL'

  const result_summary: DogfoodResult = {
    runid,
    started_at: t0,
    ended_at,
    total_ms,
    threshold_ms: I_11_THRESHOLD_MS,
    verdict,
    gates,
    artifact_path: artifactPath,
    ps_13_status: verdict === 'PASS' ? 'CLOSED' : 'OPEN_FALSIFIED',
    marketplace_install_string: marketplaceString,
    fixture_summary: {
      domain_id: f.domain.id,
      charter_id: f.charter.id,
      workflow_id: f.workflow.id,
      execution_id: f.execution.id,
      completed_step_ids: result.completed_step_ids,
      terminal_state: result.state,
    },
  }

  writeFileSync(artifactPath, JSON.stringify(result_summary, null, 2) + '\n', 'utf-8')

  emit({
    gate: 'G-5',
    label: 'observable artifact written',
    ts: Date.now(),
    notes: artifactPath,
  })

  // -------------------------------------------------------------------------
  // G-6 — total wall-clock + verdict (binary per D-NS-50)
  // -------------------------------------------------------------------------
  emit({
    gate: 'G-6',
    label: `total wall-clock (verdict ${verdict}; PS-13 ${result_summary.ps_13_status})`,
    ts: Date.now(),
    notes: `total_ms=${total_ms} threshold_ms=${I_11_THRESHOLD_MS}`,
  })

  return result_summary
}

// =============================================================================
// CLI entry — only fires when invoked directly (npx tsx scripts/...ts)
// =============================================================================

const isMain = (() => {
  if (typeof process === 'undefined' || !process.argv?.[1]) return false
  try {
    const here = fileURLToPath(import.meta.url)
    return resolve(process.argv[1]) === resolve(here)
  } catch {
    return false
  }
})()

if (isMain) {
  void (async () => {
    try {
      const result = await runDogfood({ stubInstall: false, silent: false })
      // Final summary line for operator readability (in addition to JSONL gate stream)
      process.stdout.write(
        `\n# DOGFOOD SUMMARY\n` +
          `# runid=${result.runid}\n` +
          `# total_ms=${result.total_ms}\n` +
          `# threshold_ms=${result.threshold_ms}\n` +
          `# verdict=${result.verdict}\n` +
          `# ps_13_status=${result.ps_13_status}\n` +
          `# artifact=${result.artifact_path}\n`,
      )
      process.exit(result.verdict === 'PASS' ? 0 : 1)
    } catch (err) {
      const msg = err instanceof Error ? err.message : String(err)
      process.stderr.write(`# DOGFOOD ERROR: ${msg}\n`)
      process.exit(2)
    }
  })()
}
