/**
 * proposal-ledger — durable record of pattern → proposal → decision lifecycle.
 *
 * Required by SPEC v1.2 §4.2 and codex P1 finding "thing missed":
 * the H-Sutra connector replays the JSONL log from byte 0 on daemon start, so
 * without a durable ledger the same pattern would be re-proposed forever after
 * any restart.
 *
 * Storage layout (per-user, NOT shipped with plugin):
 *   $SUTRA_NATIVE_HOME/user-kit/proposals/<pattern_id>.json
 *
 * One JSON file per ProposalEntry; pattern_id is the filename.
 *
 * Status state machine: pending → approved | rejected. Once decided, the
 * entry is preserved (audit trail) but won't be re-proposed.
 */

import { existsSync, mkdirSync, readFileSync, readdirSync, writeFileSync } from 'node:fs'
import { join } from 'node:path'

import { userKitRoot, type UserKitOptions } from './user-kit.js'

// ---------------------------------------------------------------------------
// Schema
// ---------------------------------------------------------------------------

export type ProposalStatus = 'pending' | 'approved' | 'rejected'

export interface ProposalEntry {
  /** P-<sha8>; stable across restarts because derived from normalized_phrase. */
  readonly pattern_id: string
  /** The normalized phrase the detector grouped on. */
  readonly normalized_phrase: string
  /** How many input_text events matched the normalized phrase when proposed. */
  readonly evidence_count: number
  /** First H-Sutra event ts that contributed to the pattern, in unix ms. */
  readonly first_seen_ms: number
  /** Last H-Sutra event ts that contributed to the pattern, in unix ms. */
  readonly last_seen_ms: number
  /** First few raw input_text samples for founder context (capped). */
  readonly utterance_samples: ReadonlyArray<string>
  /** Proposed Workflow id (pre-creation; matches builder output). */
  readonly proposed_workflow_id: string
  /** Proposed TriggerSpec id (pre-creation). */
  readonly proposed_trigger_id: string
  /** Charter the proposal will attach to (default 'C-daily-pulse'). */
  readonly proposed_charter_id: string
  /** Domain the proposal will attach to (default 'D1'). */
  readonly proposed_domain_id: string
  /** Lifecycle. */
  readonly status: ProposalStatus
  /** When the proposal was first written. */
  readonly proposed_at_ms: number
  /** When approved/rejected; null while pending. */
  readonly decided_at_ms: number | null
  /** Free-form reason on decision; null while pending. */
  readonly decision_reason: string | null
}

const PATTERN_ID_PATTERN = /^P-[0-9a-f]{8}$/

export function isProposalEntry(value: unknown): value is ProposalEntry {
  if (typeof value !== 'object' || value === null) return false
  const v = value as Partial<ProposalEntry>
  return (
    typeof v.pattern_id === 'string' &&
    PATTERN_ID_PATTERN.test(v.pattern_id) &&
    typeof v.normalized_phrase === 'string' &&
    v.normalized_phrase.length > 0 &&
    typeof v.evidence_count === 'number' &&
    v.evidence_count >= 0 &&
    typeof v.first_seen_ms === 'number' &&
    typeof v.last_seen_ms === 'number' &&
    Array.isArray(v.utterance_samples) &&
    v.utterance_samples.every((s) => typeof s === 'string') &&
    typeof v.proposed_workflow_id === 'string' &&
    typeof v.proposed_trigger_id === 'string' &&
    typeof v.proposed_charter_id === 'string' &&
    typeof v.proposed_domain_id === 'string' &&
    (v.status === 'pending' || v.status === 'approved' || v.status === 'rejected') &&
    typeof v.proposed_at_ms === 'number' &&
    (v.decided_at_ms === null || typeof v.decided_at_ms === 'number') &&
    (v.decision_reason === null || typeof v.decision_reason === 'string')
  )
}

// ---------------------------------------------------------------------------
// File layout helpers
// ---------------------------------------------------------------------------

function proposalDir(opts: UserKitOptions = {}): string {
  return join(userKitRoot(opts), 'user-kit', 'proposals')
}

function ensureDir(dir: string): void {
  mkdirSync(dir, { recursive: true })
}

function writeJson(path: string, value: unknown): void {
  writeFileSync(path, JSON.stringify(value, null, 2) + '\n', { encoding: 'utf8' })
}

function readJson(path: string): unknown {
  return JSON.parse(readFileSync(path, 'utf8'))
}

// ---------------------------------------------------------------------------
// CRUD
// ---------------------------------------------------------------------------

export function persistProposal(entry: ProposalEntry, opts: UserKitOptions = {}): string {
  if (!isProposalEntry(entry)) {
    throw new TypeError(
      `persistProposal: malformed entry (pattern_id=${(entry as { pattern_id?: unknown }).pattern_id})`,
    )
  }
  const dir = proposalDir(opts)
  ensureDir(dir)
  const path = join(dir, `${entry.pattern_id}.json`)
  writeJson(path, entry)
  return path
}

export function loadProposal(
  pattern_id: string,
  opts: UserKitOptions = {},
): ProposalEntry | null {
  const path = join(proposalDir(opts), `${pattern_id}.json`)
  if (!existsSync(path)) return null
  const raw = readJson(path)
  return isProposalEntry(raw) ? raw : null
}

export function listProposals(
  opts: UserKitOptions = {},
  status_filter?: ProposalStatus,
): ProposalEntry[] {
  const dir = proposalDir(opts)
  if (!existsSync(dir)) return []
  const all = readdirSync(dir)
    .filter((f) => f.endsWith('.json'))
    .map((f) => readJson(join(dir, f)))
    .filter(isProposalEntry)
  return status_filter ? all.filter((p) => p.status === status_filter) : all
}

export function updateProposalStatus(
  pattern_id: string,
  next_status: 'approved' | 'rejected',
  decision_reason: string,
  opts: UserKitOptions = {},
  now_ms: number = Date.now(),
): ProposalEntry {
  const existing = loadProposal(pattern_id, opts)
  if (!existing) {
    throw new Error(`updateProposalStatus: no proposal found with id "${pattern_id}"`)
  }
  if (existing.status !== 'pending') {
    throw new Error(
      `updateProposalStatus: cannot transition from "${existing.status}" — proposals are decided once`,
    )
  }
  const updated: ProposalEntry = {
    ...existing,
    status: next_status,
    decided_at_ms: now_ms,
    decision_reason,
  }
  persistProposal(updated, opts)
  return updated
}
