/**
 * pattern-detector — finds repeated founder utterances that no registered
 * TriggerSpec matches, so the engine can propose a new Workflow + TriggerSpec.
 *
 * SPEC v1.2 §4.3. v1 rule (D45): NO LLM. Frequency + sequence detection over
 * the H-Sutra log JSONL only. Routing is simulated against the boot-time
 * trigger set — no dependency on Router state (which is in-memory only).
 *
 * Determinism: same input log + same trigger set + same proposer_version
 * yields the same DetectedPattern[].
 */

import { createHash } from 'node:crypto'
import { existsSync, readFileSync } from 'node:fs'

import { evaluate, type PredicateContext } from './predicate.js'
import { isHSutraEvent, type HSutraEvent } from '../types/h-sutra-event.js'
import type { TriggerSpec } from '../types/trigger-spec.js'
import { loadProposal } from '../persistence/proposal-ledger.js'
import type { UserKitOptions } from '../persistence/user-kit.js'

export interface PatternDetectorOptions {
  /** Absolute path to the H-Sutra log JSONL file. */
  readonly hsutra_log_path: string
  /** Minimum repeats to surface a pattern. Default 4 per codex prior verdict. */
  readonly k_threshold?: number
  /** Window in ms before now() to consider events. Default 7d. */
  readonly window_ms?: number
  /** Cap on samples kept per pattern. Default 4. */
  readonly max_samples?: number
  /** UserKit opts forwarded to loadProposal for dedup. */
  readonly user_kit_opts?: UserKitOptions
  /** Override now() for deterministic tests. */
  readonly now_ms?: number
}

export interface DetectedPattern {
  /** P-<sha8> stable across runs (derived from normalized_phrase only). */
  readonly pattern_id: string
  readonly normalized_phrase: string
  readonly evidence_count: number
  readonly utterance_samples: ReadonlyArray<string>
  readonly first_seen_ms: number
  readonly last_seen_ms: number
}

const STOPWORDS: ReadonlySet<string> = new Set([
  'a', 'an', 'the', 'i', 'we', 'you', 'they', 'he', 'she', 'it',
  'is', 'are', 'was', 'were', 'be', 'been', 'being', 'am',
  'to', 'of', 'in', 'on', 'at', 'by', 'for', 'with', 'from', 'as',
  'and', 'or', 'but', 'so', 'if', 'than', 'that', 'this', 'these', 'those',
  'do', 'does', 'did', 'have', 'has', 'had',
  'will', 'would', 'shall', 'should', 'may', 'might', 'must', 'can', 'could',
  'me', 'my', 'mine', 'us', 'our', 'ours', 'your', 'yours',
])

/**
 * Normalize an utterance for grouping. Lowercase, strip punctuation, drop
 * stopwords, sort tokens for set-equality (so "track design partners" and
 * "design partners track" group together). Returns empty string if nothing
 * informative remains.
 */
export function normalizeUtterance(text: string): string {
  const lowered = text.toLowerCase()
  const cleaned = lowered.replace(/[^a-z0-9\s]+/g, ' ')
  const tokens = cleaned
    .split(/\s+/)
    .filter((t) => t.length > 0 && !STOPWORDS.has(t))
  if (tokens.length === 0) return ''
  return [...tokens].sort().join(' ')
}

export function patternIdFor(normalized_phrase: string): string {
  const hash = createHash('sha256').update(normalized_phrase).digest('hex').slice(0, 8)
  return `P-${hash}`
}

/** Convert ISO-8601 string OR unix-ms number to unix ms. Returns 0 on parse failure. */
function tsToMs(ts: unknown): number {
  if (typeof ts === 'number' && Number.isFinite(ts)) return ts
  if (typeof ts === 'string') {
    const parsed = Date.parse(ts)
    return Number.isFinite(parsed) ? parsed : 0
  }
  return 0
}

/** Read JSONL file → array of HSutraEvent. Tolerates malformed rows (drops them). */
function readHSutraLog(path: string): HSutraEvent[] {
  if (!existsSync(path)) return []
  const text = readFileSync(path, 'utf8')
  const out: HSutraEvent[] = []
  for (const line of text.split('\n')) {
    const trimmed = line.trim()
    if (!trimmed) continue
    try {
      const parsed = JSON.parse(trimmed)
      if (isHSutraEvent(parsed)) out.push(parsed)
    } catch {
      // skip malformed
    }
  }
  return out
}

/** True if any registered TriggerSpec for `founder_input` matches the event. */
function anyTriggerMatches(
  triggers: ReadonlyArray<TriggerSpec>,
  evt: HSutraEvent,
): boolean {
  const ctx: PredicateContext = {
    input_text: evt.input_text,
    event_type: 'founder_input',
    hsutra: evt,
  }
  for (const t of triggers) {
    if (t.event_type !== 'founder_input') continue
    if (evaluate(t.route_predicate, ctx).matched) return true
  }
  return false
}

interface PatternAccumulator {
  normalized_phrase: string
  evidence_count: number
  utterance_samples: string[]
  first_seen_ms: number
  last_seen_ms: number
}

/**
 * Detect frequency patterns in the H-Sutra log that no registered trigger
 * matches AND no prior proposal already covers.
 */
export function detectPatterns(
  triggers: ReadonlyArray<TriggerSpec>,
  opts: PatternDetectorOptions,
): DetectedPattern[] {
  const k_threshold = opts.k_threshold ?? 4
  const window_ms = opts.window_ms ?? 7 * 24 * 60 * 60 * 1000
  const max_samples = opts.max_samples ?? 4
  const now_ms = opts.now_ms ?? Date.now()
  const cutoff_ms = now_ms - window_ms

  const events = readHSutraLog(opts.hsutra_log_path)
  const acc = new Map<string, PatternAccumulator>()

  for (const evt of events) {
    const text = evt.input_text
    if (typeof text !== 'string' || text.length === 0) continue

    const ts_ms = tsToMs(evt.ts) || now_ms
    if (ts_ms < cutoff_ms) continue

    if (anyTriggerMatches(triggers, evt)) continue

    const normalized = normalizeUtterance(text)
    if (normalized.length === 0) continue

    const existing = acc.get(normalized)
    if (existing) {
      existing.evidence_count++
      if (existing.utterance_samples.length < max_samples) {
        existing.utterance_samples.push(text)
      }
      if (ts_ms > existing.last_seen_ms) existing.last_seen_ms = ts_ms
      if (ts_ms < existing.first_seen_ms) existing.first_seen_ms = ts_ms
    } else {
      acc.set(normalized, {
        normalized_phrase: normalized,
        evidence_count: 1,
        utterance_samples: [text],
        first_seen_ms: ts_ms,
        last_seen_ms: ts_ms,
      })
    }
  }

  const detected: DetectedPattern[] = []
  for (const a of acc.values()) {
    if (a.evidence_count < k_threshold) continue
    const pattern_id = patternIdFor(a.normalized_phrase)

    // Dedup against ProposalLedger — already proposed once means skip even
    // if pending/approved/rejected. Audit trail preserved either way.
    if (loadProposal(pattern_id, opts.user_kit_opts) !== null) continue

    detected.push({
      pattern_id,
      normalized_phrase: a.normalized_phrase,
      evidence_count: a.evidence_count,
      utterance_samples: [...a.utterance_samples],
      first_seen_ms: a.first_seen_ms,
      last_seen_ms: a.last_seen_ms,
    })
  }
  return detected
}
