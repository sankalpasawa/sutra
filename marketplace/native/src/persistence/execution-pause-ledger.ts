/**
 * execution-pause-ledger — durable record of step.on_failure='pause' lifecycle.
 *
 * v1.3.0 Wave 4 (codex W4 advisory #3 fold + advisory #2 best-effort semantics).
 *
 * Purpose: when a Workflow step has `on_failure='pause'` and FAILS at runtime,
 * lite-executor persists a durable ExecutionPauseRecord{status:'pending'} and
 * returns ExecutionResult{status:'paused'}. The founder's `resume E-<id>`
 * (or programmatic NativeEngine.resumeFromPause) flips the record's status;
 * resume re-enters the workflow at step_index+1.
 *
 * Distinction from execution-approval-ledger:
 *   - approval-ledger: pause BEFORE running a step (requires_approval=true gate)
 *   - pause-ledger:    pause AFTER a step FAILED (on_failure='pause' handler)
 *
 * Codex W4 advisory #3 fold (mutual exclusion): pause/escalate states are
 * mutually exclusive with rollback. resumeFromPause() rejects runs already
 * escalated or in rollback — guard implemented at NativeEngine layer (this
 * file is the storage primitive only).
 *
 * Mirrors execution-approval-ledger.ts at the API + state-machine + atomic-
 * write level. Replay-safe: boot-time reload via NativeEngine constructor
 * surfaces pending pauses as informational (DO NOT auto-resume — founder
 * must explicitly approve via the NativeEngine surface).
 *
 * State machine (single transition + atomic):
 *   pending → resumed              (terminal sink — resume succeeded)
 *   pending → terminal             (terminal sink — failed run that exhausted retries
 *                                   or founder explicitly terminated; future hook)
 *   any other transition → throws (caller bug; ledger == truth).
 *
 * Storage:
 *   $SUTRA_NATIVE_HOME/runtime/pending-pauses/E-<id>.json
 *
 * Written via atomicWriteSync (fsync + atomic rename). Crash-safe: a crash
 * mid-write never leaves a torn record.
 */

import { existsSync, mkdirSync, readFileSync, readdirSync } from 'node:fs'
import { join } from 'node:path'

import { atomicWriteSync } from './atomic-write.js'
import { userKitRoot, type UserKitOptions } from './user-kit.js'

// ---------------------------------------------------------------------------
// Schema
// ---------------------------------------------------------------------------

export type ExecutionPauseStatus = 'pending' | 'resumed' | 'terminal'

export interface ExecutionPauseRecord {
  /** E-<turn_id>-<seq>; matches NativeEngine.executionId construction. */
  readonly execution_id: string
  /** W-<id> of the paused workflow. */
  readonly workflow_id: string
  /** 1-based step_index of the step that FAILED + triggered the pause. */
  readonly step_index: number
  /** State machine; see file header. */
  readonly status: ExecutionPauseStatus
  /** Original step failure reason that triggered the pause (audit trail). */
  readonly reason: string
  /** When the record was first written (executor pause point). */
  readonly created_at_ms: number
  /** When status flipped pending → resumed (workflow continued). */
  readonly resumed_at_ms?: number
  /** When status flipped pending → terminal (founder terminated / abandoned). */
  readonly terminal_at_ms?: number
  /** Free-form reason on terminal flip (operator-supplied). */
  readonly terminal_reason?: string
}

const E_ID_PATTERN = /^E-.+$/

export function isExecutionPauseRecord(
  value: unknown,
): value is ExecutionPauseRecord {
  if (typeof value !== 'object' || value === null) return false
  const v = value as Partial<ExecutionPauseRecord>
  if (typeof v.execution_id !== 'string' || !E_ID_PATTERN.test(v.execution_id)) return false
  if (typeof v.workflow_id !== 'string' || v.workflow_id.length === 0) return false
  if (typeof v.step_index !== 'number' || !Number.isInteger(v.step_index) || v.step_index < 0) {
    return false
  }
  if (
    v.status !== 'pending' &&
    v.status !== 'resumed' &&
    v.status !== 'terminal'
  ) return false
  if (typeof v.reason !== 'string') return false
  if (typeof v.created_at_ms !== 'number' || !Number.isFinite(v.created_at_ms)) return false
  if (v.resumed_at_ms !== undefined && typeof v.resumed_at_ms !== 'number') return false
  if (v.terminal_at_ms !== undefined && typeof v.terminal_at_ms !== 'number') return false
  if (v.terminal_reason !== undefined && typeof v.terminal_reason !== 'string') return false
  return true
}

// ---------------------------------------------------------------------------
// File layout helpers (runtime/, NOT user-kit/)
// ---------------------------------------------------------------------------

function pauseDir(opts: UserKitOptions = {}): string {
  return join(userKitRoot(opts), 'runtime', 'pending-pauses')
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
 * Persist an ExecutionPauseRecord to its E-<id>.json file via atomic write.
 *
 * Used at three points:
 *   1. lite-executor pause (status='pending') — on_failure='pause' handler
 *   2. NativeEngine.resumeFromPause (status='resumed' after run completes)
 *   3. Operator/founder termination (status='terminal')
 *
 * Throws TypeError on malformed input.
 */
export function persistPause(
  rec: ExecutionPauseRecord,
  opts: UserKitOptions = {},
): string {
  if (!isExecutionPauseRecord(rec)) {
    throw new TypeError(
      `persistPause: malformed record (execution_id=${(rec as { execution_id?: unknown }).execution_id})`,
    )
  }
  const dir = pauseDir(opts)
  ensureDir(dir)
  const path = join(dir, `${rec.execution_id}.json`)
  writeJson(path, rec)
  return path
}

/**
 * Load a single ExecutionPauseRecord by execution_id; returns null when the
 * file does not exist or fails the validator.
 */
export function loadPause(
  execution_id: string,
  opts: UserKitOptions = {},
): ExecutionPauseRecord | null {
  const path = join(pauseDir(opts), `${execution_id}.json`)
  if (!existsSync(path)) return null
  const raw = readJson(path)
  return isExecutionPauseRecord(raw) ? raw : null
}

/**
 * List all pause records, optionally filtered by status. Used by NativeEngine
 * boot-time reload to surface pending pauses as informational logs.
 */
export function listPauses(
  opts: UserKitOptions = {},
  status_filter?: ExecutionPauseStatus,
): ExecutionPauseRecord[] {
  const dir = pauseDir(opts)
  if (!existsSync(dir)) return []
  const all = readdirSync(dir)
    .filter((f) => f.endsWith('.json'))
    .map((f) => readJson(join(dir, f)))
    .filter(isExecutionPauseRecord)
  return status_filter ? all.filter((r) => r.status === status_filter) : all
}

/**
 * Atomic state-machine transition: pending → resumed.
 *
 * Called by NativeEngine.resumeFromPause after the post-pause workflow run
 * completes. Marks the ledger entry as terminal-on-the-resume-side.
 */
export function markResumed(
  execution_id: string,
  opts: UserKitOptions = {},
  now_ms: number = Date.now(),
): ExecutionPauseRecord {
  const existing = loadPause(execution_id, opts)
  if (!existing) {
    throw new Error(
      `markResumed (pause-ledger): no pause record found with id "${execution_id}"`,
    )
  }
  if (existing.status !== 'pending') {
    throw new Error(
      `markResumed (pause-ledger): cannot transition "${existing.status}" → "resumed" — only pending records may be resumed`,
    )
  }
  const updated: ExecutionPauseRecord = {
    ...existing,
    status: 'resumed',
    resumed_at_ms: now_ms,
  }
  persistPause(updated, opts)
  return updated
}

/**
 * Atomic state-machine transition: pending → terminal.
 *
 * Reserved for explicit operator termination of a paused execution that will
 * not be resumed. Future hook for `terminate E-<id> <reason>` utterance.
 */
export function markTerminal(
  execution_id: string,
  reason: string,
  opts: UserKitOptions = {},
  now_ms: number = Date.now(),
): ExecutionPauseRecord {
  const existing = loadPause(execution_id, opts)
  if (!existing) {
    throw new Error(
      `markTerminal (pause-ledger): no pause record found with id "${execution_id}"`,
    )
  }
  if (existing.status !== 'pending') {
    throw new Error(
      `markTerminal (pause-ledger): cannot transition "${existing.status}" → "terminal" — only pending records may be terminalized`,
    )
  }
  const updated: ExecutionPauseRecord = {
    ...existing,
    status: 'terminal',
    terminal_at_ms: now_ms,
    terminal_reason: reason,
  }
  persistPause(updated, opts)
  return updated
}
