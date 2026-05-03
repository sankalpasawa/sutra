/**
 * Property + contract tests — pattern-detector.
 *
 * Covers SPEC v1.2 §4.3:
 *   - K-1 occurrences = no detect; K = exactly 1 detect
 *   - window expiry filters out stale events
 *   - same input → same pattern_id (determinism)
 *   - already-proposed pattern is skipped (ledger dedup)
 *   - already-routable utterance (matches an existing trigger) is skipped
 *   - normalize is set-equality across token order
 */

import { existsSync, mkdtempSync, rmSync, writeFileSync, mkdirSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { afterEach, beforeEach, describe, expect, it } from 'vitest'
import fc from 'fast-check'

import {
  detectPatterns,
  normalizeUtterance,
  patternIdFor,
} from '../../src/runtime/pattern-detector.js'
import { persistProposal, type ProposalEntry } from '../../src/persistence/proposal-ledger.js'
import type { TriggerSpec } from '../../src/types/trigger-spec.js'

function writeLog(path: string, events: object[]): void {
  mkdirSync(join(path, '..'), { recursive: true })
  writeFileSync(path, events.map((e) => JSON.stringify(e)).join('\n') + '\n')
}

function event(turn_id: string, input_text: string, ts_ms: number): object {
  return {
    turn_id,
    input_text,
    ts: new Date(ts_ms).toISOString(),
    cell: 'DIRECT·INBOUND',
  }
}

function makeProposalEntry(pattern_id: string): ProposalEntry {
  return {
    pattern_id,
    normalized_phrase: 'test phrase',
    evidence_count: 4,
    first_seen_ms: 1700000000000,
    last_seen_ms: 1700000600000,
    utterance_samples: ['test'],
    proposed_workflow_id: 'W-x',
    proposed_trigger_id: 'T-x',
    proposed_charter_id: 'C-daily-pulse',
    proposed_domain_id: 'D1',
    status: 'pending',
    proposed_at_ms: 1700000700000,
    decided_at_ms: null,
    decision_reason: null,
  }
}

describe('normalizeUtterance', () => {
  it('lowercases and strips punctuation', () => {
    expect(normalizeUtterance('Hello, World!')).toBe('hello world')
  })

  it('strips stopwords', () => {
    expect(normalizeUtterance('I want to track design partners')).toBe(
      ['design', 'partners', 'track', 'want'].sort().join(' '),
    )
  })

  it('returns empty string when only stopwords', () => {
    expect(normalizeUtterance('I am the')).toBe('')
  })

  it('produces same output for token-shuffled input (set equality)', () => {
    const a = normalizeUtterance('design partners track')
    const b = normalizeUtterance('partners track design')
    expect(a).toBe(b)
  })
})

describe('patternIdFor determinism', () => {
  it('produces stable id from same phrase', () => {
    expect(patternIdFor('design partners track')).toBe(patternIdFor('design partners track'))
  })

  it('produces different ids for different phrases', () => {
    expect(patternIdFor('design partners')).not.toBe(patternIdFor('product launch'))
  })

  it('matches P-<8hex> shape', () => {
    expect(patternIdFor('hello world')).toMatch(/^P-[0-9a-f]{8}$/)
  })

  it('property: forall string s, patternIdFor(s) matches P-<8hex>', () => {
    fc.assert(
      fc.property(fc.string({ minLength: 1, maxLength: 40 }), (s) => {
        expect(patternIdFor(s)).toMatch(/^P-[0-9a-f]{8}$/)
      }),
      { numRuns: 200 },
    )
  })
})

describe('detectPatterns — frequency threshold', () => {
  let HOME: string
  let LOG: string
  const NOW = 1700001000000

  beforeEach(() => {
    HOME = mkdtempSync(join(tmpdir(), 'pattern-detect-'))
    LOG = join(HOME, 'h-sutra.jsonl')
  })

  afterEach(() => {
    if (HOME && existsSync(HOME)) rmSync(HOME, { recursive: true, force: true })
  })

  it('K-1 occurrences = no detect (K=4 default)', () => {
    writeLog(LOG, [
      event('t1', 'track design partners', NOW - 1000),
      event('t2', 'track design partners', NOW - 900),
      event('t3', 'track design partners', NOW - 800),
    ])
    const detected = detectPatterns([], { hsutra_log_path: LOG, now_ms: NOW, user_kit_opts: { home: HOME } })
    expect(detected).toHaveLength(0)
  })

  it('K=4 occurrences = exactly 1 detect', () => {
    writeLog(LOG, [
      event('t1', 'track design partners', NOW - 4000),
      event('t2', 'track design partners', NOW - 3000),
      event('t3', 'track design partners', NOW - 2000),
      event('t4', 'track design partners', NOW - 1000),
    ])
    const detected = detectPatterns([], { hsutra_log_path: LOG, now_ms: NOW, user_kit_opts: { home: HOME } })
    expect(detected).toHaveLength(1)
    expect(detected[0].evidence_count).toBe(4)
    expect(detected[0].pattern_id).toMatch(/^P-[0-9a-f]{8}$/)
  })

  it('groups token-shuffled utterances together (set equality)', () => {
    writeLog(LOG, [
      event('t1', 'design partners track', NOW - 4000),
      event('t2', 'partners track design', NOW - 3000),
      event('t3', 'track partners design', NOW - 2000),
      event('t4', 'design track partners', NOW - 1000),
    ])
    const detected = detectPatterns([], { hsutra_log_path: LOG, now_ms: NOW, user_kit_opts: { home: HOME } })
    expect(detected).toHaveLength(1)
    expect(detected[0].evidence_count).toBe(4)
  })

  it('K=5 occurrences = 1 detect with evidence_count 5', () => {
    writeLog(LOG, [
      event('t1', 'pipeline review', NOW - 5000),
      event('t2', 'pipeline review', NOW - 4000),
      event('t3', 'pipeline review', NOW - 3000),
      event('t4', 'pipeline review', NOW - 2000),
      event('t5', 'pipeline review', NOW - 1000),
    ])
    const detected = detectPatterns([], { hsutra_log_path: LOG, now_ms: NOW, user_kit_opts: { home: HOME } })
    expect(detected).toHaveLength(1)
    expect(detected[0].evidence_count).toBe(5)
  })
})

describe('detectPatterns — window expiry', () => {
  let HOME: string
  let LOG: string
  const NOW = 1700001000000

  beforeEach(() => {
    HOME = mkdtempSync(join(tmpdir(), 'pattern-detect-window-'))
    LOG = join(HOME, 'h-sutra.jsonl')
  })

  afterEach(() => {
    if (HOME && existsSync(HOME)) rmSync(HOME, { recursive: true, force: true })
  })

  it('drops events older than window_ms', () => {
    const week = 7 * 24 * 60 * 60 * 1000
    writeLog(LOG, [
      event('t1', 'design partners', NOW - week - 1000), // outside window
      event('t2', 'design partners', NOW - week - 500),  // outside window
      event('t3', 'design partners', NOW - 1000),
      event('t4', 'design partners', NOW - 500),
    ])
    const detected = detectPatterns([], { hsutra_log_path: LOG, window_ms: week, now_ms: NOW, user_kit_opts: { home: HOME } })
    expect(detected).toHaveLength(0)
  })

  it('keeps events inside the window', () => {
    const week = 7 * 24 * 60 * 60 * 1000
    writeLog(LOG, [
      event('t1', 'design partners', NOW - week / 2),
      event('t2', 'design partners', NOW - week / 3),
      event('t3', 'design partners', NOW - week / 4),
      event('t4', 'design partners', NOW - week / 8),
    ])
    const detected = detectPatterns([], { hsutra_log_path: LOG, window_ms: week, now_ms: NOW, user_kit_opts: { home: HOME } })
    expect(detected).toHaveLength(1)
    expect(detected[0].evidence_count).toBe(4)
  })
})

describe('detectPatterns — already-routable suppression', () => {
  let HOME: string
  let LOG: string
  const NOW = 1700001000000

  beforeEach(() => {
    HOME = mkdtempSync(join(tmpdir(), 'pattern-detect-route-'))
    LOG = join(HOME, 'h-sutra.jsonl')
  })

  afterEach(() => {
    if (HOME && existsSync(HOME)) rmSync(HOME, { recursive: true, force: true })
  })

  it('skips events that an existing TriggerSpec already matches', () => {
    const existingTrigger: TriggerSpec = {
      id: 'T-existing',
      event_type: 'founder_input',
      route_predicate: { type: 'contains', value: 'design', case_sensitive: false },
      target_workflow: 'W-existing',
    }
    writeLog(LOG, [
      event('t1', 'design partners', NOW - 4000),
      event('t2', 'design partners', NOW - 3000),
      event('t3', 'design partners', NOW - 2000),
      event('t4', 'design partners', NOW - 1000),
    ])
    const detected = detectPatterns([existingTrigger], { hsutra_log_path: LOG, now_ms: NOW, user_kit_opts: { home: HOME } })
    expect(detected).toHaveLength(0) // already-routable; not surfaced
  })
})

describe('detectPatterns — ledger dedup', () => {
  let HOME: string
  let LOG: string
  const NOW = 1700001000000

  beforeEach(() => {
    HOME = mkdtempSync(join(tmpdir(), 'pattern-detect-dedup-'))
    LOG = join(HOME, 'h-sutra.jsonl')
  })

  afterEach(() => {
    if (HOME && existsSync(HOME)) rmSync(HOME, { recursive: true, force: true })
  })

  it('skips patterns that already exist in the proposal ledger', () => {
    writeLog(LOG, [
      event('t1', 'pipeline review', NOW - 4000),
      event('t2', 'pipeline review', NOW - 3000),
      event('t3', 'pipeline review', NOW - 2000),
      event('t4', 'pipeline review', NOW - 1000),
    ])
    const expectedId = patternIdFor(normalizeUtterance('pipeline review'))
    persistProposal(makeProposalEntry(expectedId), { home: HOME })
    const detected = detectPatterns([], { hsutra_log_path: LOG, now_ms: NOW, user_kit_opts: { home: HOME } })
    expect(detected).toHaveLength(0)
  })
})

describe('detectPatterns — replay determinism', () => {
  let HOME: string
  let LOG: string
  const NOW = 1700001000000

  beforeEach(() => {
    HOME = mkdtempSync(join(tmpdir(), 'pattern-detect-determ-'))
    LOG = join(HOME, 'h-sutra.jsonl')
  })

  afterEach(() => {
    if (HOME && existsSync(HOME)) rmSync(HOME, { recursive: true, force: true })
  })

  it('produces identical pattern_id across runs', () => {
    writeLog(LOG, [
      event('t1', 'investor update', NOW - 4000),
      event('t2', 'investor update monthly', NOW - 3000),
      event('t3', 'investor update prep', NOW - 2000),
      event('t4', 'investor update again', NOW - 1000),
    ])
    const a = detectPatterns([], { hsutra_log_path: LOG, now_ms: NOW, user_kit_opts: { home: HOME } })
    const b = detectPatterns([], { hsutra_log_path: LOG, now_ms: NOW, user_kit_opts: { home: HOME } })
    expect(a).toEqual(b)
  })
})

describe('detectPatterns — malformed inputs', () => {
  let HOME: string
  let LOG: string
  const NOW = 1700001000000

  beforeEach(() => {
    HOME = mkdtempSync(join(tmpdir(), 'pattern-detect-mal-'))
    LOG = join(HOME, 'h-sutra.jsonl')
  })

  afterEach(() => {
    if (HOME && existsSync(HOME)) rmSync(HOME, { recursive: true, force: true })
  })

  it('returns empty when log file does not exist', () => {
    const detected = detectPatterns([], { hsutra_log_path: '/nonexistent/path', now_ms: NOW, user_kit_opts: { home: HOME } })
    expect(detected).toEqual([])
  })

  it('skips malformed JSONL rows', () => {
    mkdirSync(join(LOG, '..'), { recursive: true })
    writeFileSync(LOG, 'not json\n{"bad":"event"}\n' + JSON.stringify(event('t1', 'design partners', NOW - 1000)) + '\n')
    const detected = detectPatterns([], { hsutra_log_path: LOG, k_threshold: 1, now_ms: NOW, user_kit_opts: { home: HOME } })
    expect(detected).toHaveLength(1) // only the well-formed event groups
  })

  it('skips events with empty input_text', () => {
    writeLog(LOG, [
      { turn_id: 't1', ts: new Date(NOW - 1000).toISOString() }, // no input_text
      event('t2', '', NOW - 800),
      event('t3', 'design partners', NOW - 600),
      event('t4', 'design partners', NOW - 400),
      event('t5', 'design partners', NOW - 300),
      event('t6', 'design partners', NOW - 200),
    ])
    const detected = detectPatterns([], { hsutra_log_path: LOG, now_ms: NOW, user_kit_opts: { home: HOME } })
    expect(detected).toHaveLength(1)
    expect(detected[0].evidence_count).toBe(4)
  })
})
