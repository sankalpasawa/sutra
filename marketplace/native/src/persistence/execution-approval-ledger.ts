/**
 * execution-approval-ledger — durable record of step-level approval lifecycle.
 *
 * v1.3.0 Wave 2 (codex W2 BLOCKER 3 fold + advisories A,E 2026-05-04).
 *
 * Purpose: when a Workflow step has `requires_approval=true`, lite-executor
 * pauses BEFORE running the step and writes a durable
 * ExecutionApprovalRecord{status:'pending'}. The founder's `approve E-<id>`
 * or `reject E-<id> <reason>` utterance flips the record's status; resume
 * loads the record on boot and continues the run from the paused step.
 *
 * Codex W2 advisory A fold: this ledger does NOT live under user-kit/ (which
 * is reserved for founder-created primitives — Domains, Charters, Workflows,
 * Triggers, Proposals). It lives at a separate runtime/execution ledger root
 * to keep the namespace clean:
 *
 *   $SUTRA_NATIVE_HOME/runtime/pending-approvals/E-<id>.json
 *
 * Mirrors proposal-ledger.ts at the API + state-machine + atomic-write level
 * (codex W2 advisory E "reuse proposal-flow ordering" fold). Replay-safe:
 *   - boot-time reload via NativeEngine constructor (operator-visible log of
 *     pending approvals; founder must explicitly approve to resume).
 *   - stale-approve idempotency: approve E-<id> for an already-decided
 *     execution returns explicit 'no-op already-handled' — never throws.
 *
 * State machine (single transition + atomic):
 *   pending → approved → resumed              (terminal sink)
 *   pending → rejected                          (terminal sink)
 *   any other transition → throws (caller bug; ledger == truth).
 *
 * Codex W2 BLOCKER 3 fold: written via atomicWriteSync (fsync + atomic rename
 * via persistence/atomic-write.ts) so a crash mid-write never leaves a torn
 * record. Stale-approve emits approval_already_handled event distinct from
 * "never existed" (which still throws / returns null per advisory D).
 */

import { existsSync, mkdirSync, readFileSync, readdirSync } from 'node:fs'
import { join } from 'node:path'

import { atomicWriteSync } from './atomic-write.js'
import { userKitRoot, type UserKitOptions } from './user-kit.js'

// ---------------------------------------------------------------------------
// Schema
// ---------------------------------------------------------------------------

export type ExecutionApprovalStatus =
  | 'pending'
  | 'approved'
  | 'rejected'
  | 'resumed'
  | 'terminal'

export interface ExecutionApprovalRecord {
  /** E-<turn_id>-<seq>; matches NativeEngine.executionId construction. */
  readonly execution_id: string
  /** W-<id> of the paused workflow. */
  readonly workflow_id: string
  /** 1-based step_index of the paused step (matches StepStartedEvent.step_index semantics). */
  readonly step_index: number
  /** Truncated step description for founder UI (action, host if any, locator first ~200 chars). */
  readonly prompt_summary: string
  /** State machine; see file header. */
  readonly status: ExecutionApprovalStatus
  /** When the record was first written (executor pause point). */
  readonly created_at_ms: number
  /** When status flipped to approved/rejected; null while pending. */
  readonly decided_at_ms?: number
  /** Free-form reason on decision; only set on reject (approve uses the bare verb). */
  readonly decision_reason?: string
  /** When status flipped from approved → resumed (workflow continued past the gate). */
  readonly resumed_at_ms?: number
}

const E_ID_PATTERN = /^E-.+$/

export function isExecutionApprovalRecord(
  value: unknown,
): value is ExecutionApprovalRecord {
  if (typeof value !== 'object' || value === null) return false
  const v = value as Partial<ExecutionApprovalRecord>
  if (typeof v.execution_id !== 'string' || !E_ID_PATTERN.test(v.execution_id)) return false
  if (typeof v.workflow_id !== 'string' || v.workflow_id.length === 0) return false
  if (typeof v.step_index !== 'number' || !Number.isInteger(v.step_index) || v.step_index < 0) {
    return false
  }
  if (typeof v.prompt_summary !== 'string') return false
  if (
    v.status !== 'pending' &&
    v.status !== 'approved' &&
    v.status !== 'rejected' &&
    v.status !== 'resumed' &&
    v.status !== 'terminal'
  ) return false
  if (typeof v.created_at_ms !== 'number' || !Number.isFinite(v.created_at_ms)) return false
  if (v.decided_at_ms !== undefined && typeof v.decided_at_ms !== 'number') return false
  if (v.decision_reason !== undefined && typeof v.decision_reason !== 'string') return false
  if (v.resumed_at_ms !== undefined && typeof v.resumed_at_ms !== 'number') return false
  return true
}

// ---------------------------------------------------------------------------
// File layout helpers (codex advisory A fold — runtime/, NOT user-kit/)
// ---------------------------------------------------------------------------

function approvalDir(opts: UserKitOptions = {}): string {
  return join(userKitRoot(opts), 'runtime', 'pending-approvals')
}

function ensureDir(dir: string): void {
  mkdirSync(dir, { recursive: true })
}

function writeJson(path: string, value: unknown): void {
  atomicWriteSync(path, JSON.stringify(value, null, 2) + '\n')
}

function readJson(path: string): unknown {
  return JSON.parse(readFileSync(path, 'utf8'))
}

// ---------------------------------------------------------------------------
// CRUD
// ---------------------------------------------------------------------------

/**
 * Persist an ExecutionApprovalRecord to its E-<id>.json file via atomic write.
 *
 * Used at three points:
 *   1. lite-executor pause (status='pending')
 *   2. NativeEngine.applyExecutionApproval (status='approved' / 'rejected')
 *   3. NativeEngine.resumeApproved (status='resumed' after run completes)
 *
 * Throws TypeError on malformed input; the constructor at the lite-executor
 * pause point won't reach here unless validateStep already passed, but we
 * defend at the persistence boundary anyway (codex W2 fold: type guards
 * guard, never assume callers).
 */
export function persistApproval(
  rec: ExecutionApprovalRecord,
  opts: UserKitOptions = {},
): string {
  if (!isExecutionApprovalRecord(rec)) {
    throw new TypeError(
      `persistApproval: malformed record (execution_id=${(rec as { execution_id?: unknown }).execution_id})`,
    )
  }
  const dir = approvalDir(opts)
  ensureDir(dir)
  const path = join(dir, `${rec.execution_id}.json`)
  writeJson(path, rec)
  return path
}

/**
 * Load a single ExecutionApprovalRecord by execution_id; returns null when
 * the file does not exist. Distinguishable from "exists but malformed"
 * (returns null after JSON parse + validator miss; codex W2 advisory D —
 * stale-approve uses this null to surface a proper error).
 */
export function loadApproval(
  execution_id: string,
  opts: UserKitOptions = {},
): ExecutionApprovalRecord | null {
  const path = join(approvalDir(opts), `${execution_id}.json`)
  if (!existsSync(path)) return null
  const raw = readJson(path)
  return isExecutionApprovalRecord(raw) ? raw : null
}

/**
 * List all approvals, optionally filtered by status. Used by:
 *   - NativeEngine constructor boot-time reload (codex W2 BLOCKER 3 fold —
 *     surface pending approvals to operator on restart)
 *   - operator inspection commands (future)
 */
export function listApprovals(
  opts: UserKitOptions = {},
  status_filter?: ExecutionApprovalStatus,
): ExecutionApprovalRecord[] {
  const dir = approvalDir(opts)
  if (!existsSync(dir)) return []
  const all = readdirSync(dir)
    .filter((f) => f.endsWith('.json'))
    .map((f) => readJson(join(dir, f)))
    .filter(isExecutionApprovalRecord)
  return status_filter ? all.filter((r) => r.status === status_filter) : all
}

/**
 * Atomic state-machine transition: pending → approved | rejected.
 *
 * Throws on any other transition (codex W2 fold: ledger == truth, callers
 * must not silently overwrite). Stale-approve handling (approving an
 * already-approved/resumed/terminal record) is the CALLER's responsibility
 * (NativeEngine emits approval_already_handled and skips this update) —
 * this function strictly enforces the pending→{approved,rejected} edge.
 */
export function updateApprovalStatus(
  execution_id: string,
  next: 'approved' | 'rejected',
  reason: string,
  opts: UserKitOptions = {},
  now_ms: number = Date.now(),
): ExecutionApprovalRecord {
  const existing = loadApproval(execution_id, opts)
  if (!existing) {
    throw new Error(
      `updateApprovalStatus: no approval record found with id "${execution_id}"`,
    )
  }
  if (existing.status !== 'pending') {
    throw new Error(
      `updateApprovalStatus: cannot transition "${existing.status}" → "${next}" — approvals decided once (state machine)`,
    )
  }
  const updated: ExecutionApprovalRecord = {
    ...existing,
    status: next,
    decided_at_ms: now_ms,
    decision_reason: reason,
  }
  persistApproval(updated, opts)
  return updated
}

/**
 * Atomic state-machine transition: approved → resumed.
 *
 * Called by NativeEngine.resumeApproved after the post-pause workflow run
 * completes (success or failure — either way the approval gate has done its
 * job). Marks the ledger entry as terminal-on-the-resume-side so subsequent
 * approve/reject for this execution returns approval_already_handled.
 */
export function markResumed(
  execution_id: string,
  opts: UserKitOptions = {},
  now_ms: number = Date.now(),
): ExecutionApprovalRecord {
  const existing = loadApproval(execution_id, opts)
  if (!existing) {
    throw new Error(
      `markResumed: no approval record found with id "${execution_id}"`,
    )
  }
  if (existing.status !== 'approved') {
    throw new Error(
      `markResumed: cannot transition "${existing.status}" → "resumed" — only approved records may be resumed`,
    )
  }
  const updated: ExecutionApprovalRecord = {
    ...existing,
    status: 'resumed',
    resumed_at_ms: now_ms,
  }
  persistApproval(updated, opts)
  return updated
}
