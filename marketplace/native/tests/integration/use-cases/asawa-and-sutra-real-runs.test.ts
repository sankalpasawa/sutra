/**
 * REAL ASAWA + SUTRA RUNS — empirical execution of 13 user-utterance use
 * cases against Native v1.2.1 wired runtime.
 *
 * Per founder directive 2026-05-04 "complete autonomous authority. Run
 * all these cases in actuality. Create cases for Asawa AND Sutra, run
 * them on Native, see the output matches expected. Document everything."
 *
 * What's REAL: starter kit (9 workflows + 5 domains + 6 charters + 5
 *   triggers loaded automatically by NativeEngine), v1.2.1 LiteExecutor +
 *   hostLLMActivity wire, PatternDetector + ProposalLedger (K=4 path),
 *   applyApproval/Rejection (P2.4 ordering), the v1.2.1 dist that just
 *   shipped to the marketplace.
 *
 * What's CONTROLLED: founder utterances synthesized as realistic Asawa or
 *   Sutra-domain inputs; isolated HOME tmpdir for proposal-ledger writes;
 *   isolated H-Sutra log file (so we don't pollute the founder's real log).
 *   NativeEngine is NOT start()ed — ingest() is called directly.
 *
 * Per case: capture every emitted event, compute EXPECTED vs ACTUAL diff,
 * write trail to /tmp/asawa-uc-runs/<case>.txt for codex master review.
 *
 * Output: 13 trail files + summary at /tmp/asawa-uc-runs/_SUMMARY.txt
 */

import {
  appendFileSync, existsSync, mkdirSync, mkdtempSync, rmSync, writeFileSync,
} from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { afterAll, afterEach, beforeAll, beforeEach, describe, expect, it } from 'vitest'

import { NativeEngine } from '../../../src/runtime/native-engine.js'
import { listProposals } from '../../../src/persistence/proposal-ledger.js'
import {
  normalizeUtterance,
  patternIdFor,
} from '../../../src/runtime/pattern-detector.js'
import type { HSutraEvent } from '../../../src/types/h-sutra-event.js'
import type { EngineEvent } from '../../../src/types/engine-event.js'

const TRAIL_DIR = '/tmp/asawa-uc-runs'

interface CaseExpect {
  routing_mode?: 'exact' | 'no-match' | 'llm-fallback'
  routing_workflow_id?: string | null
  emit_workflow_completed?: boolean
  emit_pattern_proposed?: boolean
  emit_proposal_approved?: boolean
  emit_proposal_rejected?: boolean
  step_count?: number
  proposals_pending_after?: number
  proposals_approved_after?: number
  proposals_rejected_after?: number
}

function diffExpectActual(expected: CaseExpect, events: EngineEvent[], ledgerCounts: { pending: number; approved: number; rejected: number }): { match: string[]; mismatch: string[] } {
  const match: string[] = []
  const mismatch: string[] = []
  const routing = events.find((e) => e.type === 'routing_decision') as EngineEvent | undefined
  if (expected.routing_mode !== undefined) {
    if (routing?.type === 'routing_decision' && routing.mode === expected.routing_mode) {
      match.push(`routing_mode = ${expected.routing_mode}`)
    } else {
      mismatch.push(`routing_mode expected=${expected.routing_mode} actual=${routing?.type === 'routing_decision' ? routing.mode : 'NONE'}`)
    }
  }
  if (expected.routing_workflow_id !== undefined) {
    const actualWf = routing?.type === 'routing_decision' ? routing.workflow_id : null
    if (actualWf === expected.routing_workflow_id) match.push(`workflow_id = ${expected.routing_workflow_id}`)
    else mismatch.push(`workflow_id expected=${expected.routing_workflow_id} actual=${actualWf}`)
  }
  if (expected.emit_workflow_completed !== undefined) {
    const has = events.some((e) => e.type === 'workflow_completed')
    if (has === expected.emit_workflow_completed) match.push(`emit_workflow_completed = ${has}`)
    else mismatch.push(`emit_workflow_completed expected=${expected.emit_workflow_completed} actual=${has}`)
  }
  if (expected.emit_pattern_proposed !== undefined) {
    const has = events.some((e) => e.type === 'pattern_proposed')
    if (has === expected.emit_pattern_proposed) match.push(`emit_pattern_proposed = ${has}`)
    else mismatch.push(`emit_pattern_proposed expected=${expected.emit_pattern_proposed} actual=${has}`)
  }
  if (expected.emit_proposal_approved !== undefined) {
    const has = events.some((e) => e.type === 'proposal_approved')
    if (has === expected.emit_proposal_approved) match.push(`emit_proposal_approved = ${has}`)
    else mismatch.push(`emit_proposal_approved expected=${expected.emit_proposal_approved} actual=${has}`)
  }
  if (expected.emit_proposal_rejected !== undefined) {
    const has = events.some((e) => e.type === 'proposal_rejected')
    if (has === expected.emit_proposal_rejected) match.push(`emit_proposal_rejected = ${has}`)
    else mismatch.push(`emit_proposal_rejected expected=${expected.emit_proposal_rejected} actual=${has}`)
  }
  if (expected.step_count !== undefined) {
    const stepStarts = events.filter((e) => e.type === 'step_started').length
    if (stepStarts === expected.step_count) match.push(`step_count = ${expected.step_count}`)
    else mismatch.push(`step_count expected=${expected.step_count} actual=${stepStarts}`)
  }
  if (expected.proposals_pending_after !== undefined) {
    if (ledgerCounts.pending === expected.proposals_pending_after) match.push(`proposals_pending_after = ${ledgerCounts.pending}`)
    else mismatch.push(`proposals_pending_after expected=${expected.proposals_pending_after} actual=${ledgerCounts.pending}`)
  }
  if (expected.proposals_approved_after !== undefined) {
    if (ledgerCounts.approved === expected.proposals_approved_after) match.push(`proposals_approved_after = ${ledgerCounts.approved}`)
    else mismatch.push(`proposals_approved_after expected=${expected.proposals_approved_after} actual=${ledgerCounts.approved}`)
  }
  if (expected.proposals_rejected_after !== undefined) {
    if (ledgerCounts.rejected === expected.proposals_rejected_after) match.push(`proposals_rejected_after = ${ledgerCounts.rejected}`)
    else mismatch.push(`proposals_rejected_after expected=${expected.proposals_rejected_after} actual=${ledgerCounts.rejected}`)
  }
  return { match, mismatch }
}

function writeTrail(
  caseName: string,
  scope: 'ASAWA' | 'SUTRA',
  utterance: string,
  expected: CaseExpect,
  events: EngineEvent[],
  lines: string[],
  diff: { match: string[]; mismatch: string[] },
  notes: string[],
): void {
  if (!existsSync(TRAIL_DIR)) mkdirSync(TRAIL_DIR, { recursive: true })
  const out: string[] = []
  out.push(`=== ${caseName} (${scope}) — ${new Date().toISOString()} ===`)
  out.push(`UTTERANCE: ${JSON.stringify(utterance)}`)
  out.push('')
  out.push('--- EXPECTED ---')
  for (const [k, v] of Object.entries(expected)) out.push(`  ${k} = ${JSON.stringify(v)}`)
  out.push('')
  out.push('--- ACTUAL events ---')
  for (const e of events) out.push(`  ${JSON.stringify(e)}`)
  out.push('')
  out.push('--- ACTUAL rendered lines ---')
  for (const l of lines) out.push(`  ${l}`)
  out.push('')
  out.push(`--- DIFF (${diff.match.length} match, ${diff.mismatch.length} mismatch) ---`)
  for (const m of diff.match) out.push(`  ✓ ${m}`)
  for (const m of diff.mismatch) out.push(`  ✗ ${m}`)
  out.push('')
  out.push('--- NOTES ---')
  for (const n of notes) out.push(`  ${n}`)
  writeFileSync(join(TRAIL_DIR, `${caseName}.txt`), out.join('\n'))
}

interface CaseRunResult {
  case: string
  scope: 'ASAWA' | 'SUTRA'
  matchCount: number
  mismatchCount: number
}

const allResults: CaseRunResult[] = []

function record(c: string, scope: 'ASAWA' | 'SUTRA', diff: { match: string[]; mismatch: string[] }): void {
  allResults.push({ case: c, scope, matchCount: diff.match.length, mismatchCount: diff.mismatch.length })
}

describe('Asawa + Sutra real runs (Native v1.2.1, existing arch only)', () => {
  let HOME_ISOLATED: string
  let LOG_PATH: string

  beforeEach(() => {
    HOME_ISOLATED = mkdtempSync(join(tmpdir(), 'asawa-sutra-uc-runs-'))
    LOG_PATH = join(HOME_ISOLATED, 'h-sutra.jsonl')
    writeFileSync(LOG_PATH, '')
  })

  afterEach(() => {
    if (HOME_ISOLATED && existsSync(HOME_ISOLATED)) {
      rmSync(HOME_ISOLATED, { recursive: true, force: true })
    }
  })

  afterAll(() => {
    // Write summary
    if (!existsSync(TRAIL_DIR)) mkdirSync(TRAIL_DIR, { recursive: true })
    const out: string[] = []
    out.push(`=== ASAWA + SUTRA REAL RUNS — SUMMARY (${new Date().toISOString()}) ===`)
    out.push('')
    out.push(`Total cases: ${allResults.length}`)
    let totalMatch = 0
    let totalMismatch = 0
    for (const r of allResults) {
      out.push(`${r.scope} ${r.case}: match=${r.matchCount} mismatch=${r.mismatchCount}`)
      totalMatch += r.matchCount
      totalMismatch += r.mismatchCount
    }
    out.push('')
    out.push(`Aggregate: ${totalMatch} matches, ${totalMismatch} mismatches`)
    writeFileSync(join(TRAIL_DIR, '_SUMMARY.txt'), out.join('\n'))
  })

  function buildEngine(opts: { proposerEnabled?: boolean } = {}): {
    engine: NativeEngine
    events: EngineEvent[]
    lines: string[]
  } {
    const events: EngineEvent[] = []
    const lines: string[] = []
    const engine = new NativeEngine({
      user_kit_options: { home: HOME_ISOLATED },
      proposer_enabled: opts.proposerEnabled ?? false,
      pattern_detector_options: { hsutra_log_path: LOG_PATH },
      connector_options: { log_path: LOG_PATH },
      write: (l) => lines.push(l),
    })
    for (const t of [
      'routing_decision', 'workflow_started', 'workflow_completed', 'workflow_failed',
      'step_started', 'step_completed', 'pattern_proposed', 'proposal_approved', 'proposal_rejected',
    ] as const) {
      engine.renderer.register(t, (e) => {
        events.push(e)
        return `[${e.type}]`
      })
    }
    return { engine, events, lines }
  }

  function makeEvent(turn_id: string, input_text: string): HSutraEvent {
    return { turn_id, input_text, cell: 'DIRECT·INBOUND' }
  }

  function ledgerCounts(): { pending: number; approved: number; rejected: number } {
    return {
      pending: listProposals({ home: HOME_ISOLATED }, 'pending').length,
      approved: listProposals({ home: HOME_ISOLATED }, 'approved').length,
      rejected: listProposals({ home: HOME_ISOLATED }, 'rejected').length,
    }
  }

  // ════════════════════════════════════════════════════════════════════════
  // ASAWA scope — utterances about the holding company itself
  // ════════════════════════════════════════════════════════════════════════

  it('ASAWA-1 — "hello" routes to W-onboarding-tour exact match', async () => {
    const expected: CaseExpect = {
      routing_mode: 'exact',
      routing_workflow_id: 'W-onboarding-tour',
      emit_workflow_completed: true,
      step_count: 1,
    }
    const { engine, events, lines } = buildEngine()
    const utt = 'hello'
    await engine.ingest(makeEvent('asawa-1', utt))
    const diff = diffExpectActual(expected, events, ledgerCounts())
    writeTrail('ASAWA-1-hello', 'ASAWA', utt, expected, events, lines, diff, [
      'T-onboarding contains "hello" → W-onboarding-tour fires',
      'NUANCE N1: precondition "fresh_install_marker_present" not eval-checked',
      'NUANCE N2: DP-record per execution not written by lite path',
    ])
    record('ASAWA-1-hello', 'ASAWA', diff)
    expect(diff.mismatch).toEqual([])
  })

  it('ASAWA-2 — "let\'s build a feature for asawa" routes to W-feature-build', async () => {
    const expected: CaseExpect = {
      routing_mode: 'exact',
      routing_workflow_id: 'W-feature-build',
      emit_workflow_completed: true,
      step_count: 3,
    }
    const { engine, events, lines } = buildEngine()
    const utt = "let's build a feature for asawa"
    await engine.ingest(makeEvent('asawa-2', utt))
    const diff = diffExpectActual(expected, events, ledgerCounts())
    writeTrail('ASAWA-2-build-feature', 'ASAWA', utt, expected, events, lines, diff, [
      'T-build-feature predicate is AND(or(build|implement|ship), or(feature|product|endpoint|page))',
      '"build" + "feature" both present → exact match',
      '3-step workflow: wait → spawn_sub_unit → wait',
      'NUANCE N1: precondition "feature_request_input_received" not eval-checked',
    ])
    record('ASAWA-2-build-feature', 'ASAWA', diff)
    expect(diff.mismatch).toEqual([])
  })

  it('ASAWA-3 — "fix the bug in our analytics" routes to W-bug-fix', async () => {
    const expected: CaseExpect = {
      routing_mode: 'exact',
      routing_workflow_id: 'W-bug-fix',
      emit_workflow_completed: true,
      step_count: 3,
    }
    const { engine, events, lines } = buildEngine()
    const utt = 'fix the bug in our analytics scorecard'
    await engine.ingest(makeEvent('asawa-3', utt))
    const diff = diffExpectActual(expected, events, ledgerCounts())
    writeTrail('ASAWA-3-fix-bug', 'ASAWA', utt, expected, events, lines, diff, [
      'T-bug-fix predicate or("fix the bug" | "broken" | "regression")',
      'NUANCE N4: step 2 declares policy_check=true; lite-executor does NOT call OPA',
      'NUANCE N5: on_failure variants (pause/rollback/escalate) all map to abort at v1.0',
    ])
    record('ASAWA-3-fix-bug', 'ASAWA', diff)
    expect(diff.mismatch).toEqual([])
  })

  it('ASAWA-4 — "review portfolio status" no-match (no trigger keyword)', async () => {
    const expected: CaseExpect = {
      routing_mode: 'no-match',
      routing_workflow_id: null,
      emit_workflow_completed: false,
    }
    const { engine, events, lines } = buildEngine()
    const utt = 'review portfolio status across all portfolio companies'
    await engine.ingest(makeEvent('asawa-4', utt))
    const diff = diffExpectActual(expected, events, ledgerCounts())
    writeTrail('ASAWA-4-portfolio-review', 'ASAWA', utt, expected, events, lines, diff, [
      'No starter trigger keywords matched ("review", "portfolio")',
      'GAP: would benefit from R2 LLM-fallback (router.routeAsync exists, unwired)',
      'OR Asawa-specific user-kit Workflow + Trigger created via teach path',
    ])
    record('ASAWA-4-portfolio-review', 'ASAWA', diff)
    expect(diff.mismatch).toEqual([])
  })

  it('ASAWA-5 — K=4 emergence "audit asawa governance daily"', async () => {
    const expected: CaseExpect = {
      emit_pattern_proposed: true,
      proposals_pending_after: 1,
    }
    const { engine, events, lines } = buildEngine({ proposerEnabled: true })
    const NOW = Date.now()
    const phrase = 'audit asawa governance daily'
    const rows = [1, 2, 3, 4].map((i) => ({
      turn_id: `asawa-5-${i}`,
      input_text: phrase,
      ts_ms: NOW - (5 - i) * 1000,
    }))
    appendFileSync(LOG_PATH, rows.map((r) => JSON.stringify(r)).join('\n') + '\n')
    await engine.ingest(makeEvent('asawa-5-trigger', phrase))
    const diff = diffExpectActual(expected, events, ledgerCounts())
    writeTrail('ASAWA-5-K4-emergence', 'ASAWA', phrase, expected, events, lines, diff, [
      'K=4 detector fired on 4 prior identical normalized phrases',
      `expected pattern_id = ${patternIdFor(normalizeUtterance(phrase))}`,
      'ProposalLedger entry persisted as pending; emergence-provenance DP record written',
      'P2.4 ordering: persistProposal BEFORE emit',
    ])
    record('ASAWA-5-K4-emergence', 'ASAWA', diff)
    expect(diff.mismatch).toEqual([])
  })

  it('ASAWA-6 — approve emergent → ledger flips, W+T persist', async () => {
    const expected: CaseExpect = {
      emit_proposal_approved: true,
      proposals_pending_after: 0,
      proposals_approved_after: 1,
    }
    const { engine, events, lines } = buildEngine({ proposerEnabled: true })
    const NOW = Date.now()
    const phrase = 'capture asawa friction notes hourly'
    const rows = [1, 2, 3, 4].map((i) => ({
      turn_id: `asawa-6-${i}`,
      input_text: phrase,
      ts_ms: NOW - (5 - i) * 1000,
    }))
    appendFileSync(LOG_PATH, rows.map((r) => JSON.stringify(r)).join('\n') + '\n')
    await engine.ingest(makeEvent('asawa-6-trigger', phrase))
    const pid = patternIdFor(normalizeUtterance(phrase))
    expect(listProposals({ home: HOME_ISOLATED }, 'pending')).toHaveLength(1)
    await engine.ingest(makeEvent('asawa-6-approve', `approve ${pid}`))
    const diff = diffExpectActual(expected, events, ledgerCounts())
    writeTrail('ASAWA-6-approve', 'ASAWA', `approve ${pid}`, expected, events, lines, diff, [
      `pattern_id = ${pid}`,
      '4-step P2.4 ordering: persistWorkflow + persistTrigger → updateProposalStatus → registerTrigger → emit',
      'L4-COMMITMENT recorded via emergence-provenance DP',
    ])
    record('ASAWA-6-approve', 'ASAWA', diff)
    expect(diff.mismatch).toEqual([])
  })

  it('ASAWA-7 — reject emergent with reason → ledger rejected, no W persisted', async () => {
    const expected: CaseExpect = {
      emit_proposal_rejected: true,
      proposals_pending_after: 0,
      proposals_rejected_after: 1,
    }
    const { engine, events, lines } = buildEngine({ proposerEnabled: true })
    const NOW = Date.now()
    const phrase = 'do the noisy thing every minute'
    const rows = [1, 2, 3, 4].map((i) => ({
      turn_id: `asawa-7-${i}`,
      input_text: phrase,
      ts_ms: NOW - (5 - i) * 1000,
    }))
    appendFileSync(LOG_PATH, rows.map((r) => JSON.stringify(r)).join('\n') + '\n')
    await engine.ingest(makeEvent('asawa-7-trigger', phrase))
    const pid = patternIdFor(normalizeUtterance(phrase))
    await engine.ingest(makeEvent('asawa-7-reject', `reject ${pid} too generic`))
    const diff = diffExpectActual(expected, events, ledgerCounts())
    writeTrail('ASAWA-7-reject', 'ASAWA', `reject ${pid} too generic`, expected, events, lines, diff, [
      `pattern_id = ${pid}`,
      'reason = "too generic"',
      'no Workflow / Trigger persisted',
    ])
    record('ASAWA-7-reject', 'ASAWA', diff)
    expect(diff.mismatch).toEqual([])
  })

  // ════════════════════════════════════════════════════════════════════════
  // SUTRA scope — utterances about the OS plugin (sutra/ submodule)
  // ════════════════════════════════════════════════════════════════════════

  it('SUTRA-1 — "begin sutra plugin install" → W-onboarding-tour ("begin")', async () => {
    const expected: CaseExpect = {
      routing_mode: 'exact',
      routing_workflow_id: 'W-onboarding-tour',
      emit_workflow_completed: true,
      step_count: 1,
    }
    const { engine, events, lines } = buildEngine()
    const utt = 'begin sutra plugin install for new fleet machine'
    await engine.ingest(makeEvent('sutra-1', utt))
    const diff = diffExpectActual(expected, events, ledgerCounts())
    writeTrail('SUTRA-1-begin-install', 'SUTRA', utt, expected, events, lines, diff, [
      'T-onboarding contains("begin") matches → onboarding tour fires',
      'NUANCE: trigger is overly broad — non-onboarding utterances containing "begin" match too',
    ])
    record('SUTRA-1-begin-install', 'SUTRA', diff)
    expect(diff.mismatch).toEqual([])
  })

  it('SUTRA-2 — "ship the new sutra page" → W-feature-build ("ship" + "page")', async () => {
    const expected: CaseExpect = {
      routing_mode: 'exact',
      routing_workflow_id: 'W-feature-build',
      step_count: 3,
    }
    const { engine, events, lines } = buildEngine()
    const utt = 'ship the new sutra page to website'
    await engine.ingest(makeEvent('sutra-2', utt))
    const diff = diffExpectActual(expected, events, ledgerCounts())
    writeTrail('SUTRA-2-ship-page', 'SUTRA', utt, expected, events, lines, diff, [
      'T-build-feature: ship(verb) + page(noun) → exact match',
      'NUANCE: matches even though intent is more "release" than "build new feature"',
    ])
    record('SUTRA-2-ship-page', 'SUTRA', diff)
    expect(diff.mismatch).toEqual([])
  })

  it('SUTRA-3 — "fix the bug in core plugin hooks" → W-bug-fix', async () => {
    const expected: CaseExpect = {
      routing_mode: 'exact',
      routing_workflow_id: 'W-bug-fix',
      step_count: 3,
    }
    const { engine, events, lines } = buildEngine()
    const utt = 'fix the bug in core plugin hooks'
    await engine.ingest(makeEvent('sutra-3', utt))
    const diff = diffExpectActual(expected, events, ledgerCounts())
    writeTrail('SUTRA-3-fix-hooks', 'SUTRA', utt, expected, events, lines, diff, [
      'T-bug-fix matches "fix the bug"',
    ])
    record('SUTRA-3-fix-hooks', 'SUTRA', diff)
    expect(diff.mismatch).toEqual([])
  })

  it('SUTRA-4 — "deploy sutra to fleet" no-match (no trigger keyword)', async () => {
    const expected: CaseExpect = {
      routing_mode: 'no-match',
      routing_workflow_id: null,
    }
    const { engine, events, lines } = buildEngine()
    const utt = 'deploy sutra to fleet machines today'
    await engine.ingest(makeEvent('sutra-4', utt))
    const diff = diffExpectActual(expected, events, ledgerCounts())
    writeTrail('SUTRA-4-deploy', 'SUTRA', utt, expected, events, lines, diff, [
      'No starter trigger has "deploy" or "fleet"',
      'GAP: Sutra-specific Workflows + Triggers not in starter kit',
      'TODAY path: sutra-native create-workflow + create-domain (CLI manual)',
    ])
    record('SUTRA-4-deploy', 'SUTRA', diff)
    expect(diff.mismatch).toEqual([])
  })

  it('SUTRA-5 — K=4 emergence "deploy sutra fleet"', async () => {
    const expected: CaseExpect = {
      emit_pattern_proposed: true,
      proposals_pending_after: 1,
    }
    const { engine, events, lines } = buildEngine({ proposerEnabled: true })
    const NOW = Date.now()
    const phrase = 'deploy sutra fleet upgrade'
    const rows = [1, 2, 3, 4].map((i) => ({
      turn_id: `sutra-5-${i}`,
      input_text: phrase,
      ts_ms: NOW - (5 - i) * 1000,
    }))
    appendFileSync(LOG_PATH, rows.map((r) => JSON.stringify(r)).join('\n') + '\n')
    await engine.ingest(makeEvent('sutra-5-trigger', phrase))
    const diff = diffExpectActual(expected, events, ledgerCounts())
    writeTrail('SUTRA-5-K4-emergence', 'SUTRA', phrase, expected, events, lines, diff, [
      `expected pattern_id = ${patternIdFor(normalizeUtterance(phrase))}`,
      'demonstrates Sutra-domain habit emergence path identical to Asawa',
    ])
    record('SUTRA-5-K4-emergence', 'SUTRA', diff)
    expect(diff.mismatch).toEqual([])
  })

  it('SUTRA-6 — restart engine reload preserves persisted workflows', async () => {
    const expected: CaseExpect = { /* structural — no event expectation */ }
    const { engine, events, lines } = buildEngine({ proposerEnabled: true })
    const NOW = Date.now()
    const phrase = 'codex review the sutra core hooks'
    const rows = [1, 2, 3, 4].map((i) => ({
      turn_id: `sutra-6-${i}`,
      input_text: phrase,
      ts_ms: NOW - (5 - i) * 1000,
    }))
    appendFileSync(LOG_PATH, rows.map((r) => JSON.stringify(r)).join('\n') + '\n')
    await engine.ingest(makeEvent('sutra-6-trigger', phrase))
    const pid = patternIdFor(normalizeUtterance(phrase))
    await engine.ingest(makeEvent('sutra-6-approve', `approve ${pid}`))
    expect(listProposals({ home: HOME_ISOLATED }, 'approved')).toHaveLength(1)

    // Build a SECOND engine on same HOME — should reload the approved W+T
    const engine2 = new NativeEngine({
      user_kit_options: { home: HOME_ISOLATED },
      proposer_enabled: false,
      pattern_detector_options: { hsutra_log_path: LOG_PATH },
      connector_options: { log_path: LOG_PATH },
      write: () => {},
    })
    const reloadedEvents: EngineEvent[] = []
    engine2.renderer.register('routing_decision', (e) => {
      reloadedEvents.push(e); return ''
    })
    await engine2.ingest(makeEvent('sutra-6-reroute', phrase))
    const reroutedDecision = reloadedEvents.find((e) => e.type === 'routing_decision')
    if (reroutedDecision?.type !== 'routing_decision') throw new Error('type narrow')
    const diff: { match: string[]; mismatch: string[] } = {
      match: reroutedDecision.mode === 'exact' ? [`fresh-engine reroute mode = exact`] : [],
      mismatch: reroutedDecision.mode !== 'exact' ? [`fresh-engine reroute mode expected=exact actual=${reroutedDecision.mode}`] : [],
    }
    writeTrail('SUTRA-6-restart-reload', 'SUTRA', `[restart] then "${phrase}"`, { routing_mode: 'exact' }, events.concat(reloadedEvents), lines, diff, [
      'fresh NativeEngine on same user-kit reloads approved W+T',
      'demonstrates persistence + idempotent reload (P2.4 atomic-friendly)',
    ])
    record('SUTRA-6-restart-reload', 'SUTRA', diff)
    expect(diff.mismatch).toEqual([])
  })
})
