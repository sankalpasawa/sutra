/**
 * TelemetrySink — v1.3.0 W6 (final wave production hardening).
 *
 * Append-only JSONL sink for EngineEvents with per-event fsync. Closes the
 * page-cache loss window for telemetry: every emitted event survives a
 * crash, in monotonic per-sink seq order, recoverable via replayTelemetry.
 *
 * Design points:
 *   - One JSONL file per HOME root: <home>/runtime/telemetry/events.jsonl
 *   - Each line: {"seq": N, "ts_ms": M, "event": <EngineEvent>}
 *   - Per-event open/write/fsync/close — safe under arbitrary process death
 *   - seq counter recovers on first append by reading the existing file's
 *     last line; subsequent appends use the in-memory counter (single
 *     writer per process)
 *   - Zero new dependencies — pure node:fs
 *
 * Wired into NativeEngine via opt-in constructor option `telemetry_sink_path`
 * (W6.engine-wire commit). When set, every emitted event also goes through
 * appendTelemetry. When unset, behavior is identical to v1.3.0-w5.
 *
 * Replay determinism: replayTelemetry returns events in seq order so a
 * cold-start can reconstruct the live event stream byte-for-byte.
 */

import {
  closeSync,
  existsSync,
  fsyncSync,
  mkdirSync,
  openSync,
  readFileSync,
  writeSync,
} from 'node:fs'
import { dirname, join } from 'node:path'

import type { EngineEvent } from '../types/engine-event.js'

export interface TelemetrySinkOptions {
  /** $SUTRA_NATIVE_HOME-equivalent root. Sink path = <home>/runtime/telemetry/events.jsonl. */
  readonly home: string
}

export interface TelemetryRecord {
  readonly seq: number
  readonly ts_ms: number
  readonly event: EngineEvent
}

export interface ReplayOptions extends TelemetrySinkOptions {
  /** Skip records with seq < fromSeq. Default: 0 (replay all). */
  readonly fromSeq?: number
}

/**
 * Resolve the JSONL sink path for a given HOME root.
 */
export function telemetrySinkPath(opts: TelemetrySinkOptions): string {
  return join(opts.home, 'runtime', 'telemetry', 'events.jsonl')
}

/**
 * Read the highest seq currently on disk. Returns 0 when the file is
 * absent or has no parseable records. Used at sink-open to initialize the
 * in-memory counter so per-process appends continue from the right number.
 *
 * Robust to truncated/corrupt trailing lines (treats them as absent).
 */
export function readLastSeq(opts: TelemetrySinkOptions): number {
  const path = telemetrySinkPath(opts)
  if (!existsSync(path)) return 0
  let raw: string
  try {
    raw = readFileSync(path, 'utf8')
  } catch {
    return 0
  }
  // Walk lines bottom-up so we don't have to JSON.parse the whole file
  // on every cold start.
  const lines = raw.split('\n')
  for (let i = lines.length - 1; i >= 0; i--) {
    const line = lines[i]?.trim()
    if (!line) continue
    try {
      const rec = JSON.parse(line) as TelemetryRecord
      if (typeof rec.seq === 'number' && Number.isFinite(rec.seq)) {
        return rec.seq
      }
    } catch {
      // Corrupt trailing line — keep walking.
      continue
    }
  }
  return 0
}

/**
 * In-process per-HOME seq counter. Keyed by absolute sink path so two
 * NativeEngine instances under different HOMEs don't collide. Lazy-init
 * from disk on first use.
 */
const seqCounters = new Map<string, number>()

function nextSeq(path: string, opts: TelemetrySinkOptions): number {
  const cached = seqCounters.get(path)
  if (cached !== undefined) {
    const next = cached + 1
    seqCounters.set(path, next)
    return next
  }
  const fromDisk = readLastSeq(opts)
  const next = fromDisk + 1
  seqCounters.set(path, next)
  return next
}

/**
 * Test-only helper. Resets the in-memory counter for a given HOME so a
 * subsequent appendTelemetry re-reads from disk. Safe to call from tests
 * that recreate $SUTRA_NATIVE_HOME between scenarios.
 */
export function resetTelemetryCounter(opts: TelemetrySinkOptions): void {
  seqCounters.delete(telemetrySinkPath(opts))
}

/**
 * Append a TelemetryRecord wrapping the EngineEvent to the sink.
 * Per-event open/write/fsync/close — durable under arbitrary process
 * death. Returns the assigned record (caller can correlate via seq).
 *
 * On any I/O failure throws — caller (NativeEngine wire) is expected to
 * route through the existing onError sink, never silently drop.
 */
export function appendTelemetry(
  event: EngineEvent,
  opts: TelemetrySinkOptions,
): TelemetryRecord {
  const path = telemetrySinkPath(opts)
  mkdirSync(dirname(path), { recursive: true })
  const seq = nextSeq(path, opts)
  const record: TelemetryRecord = {
    seq,
    ts_ms: typeof event.ts_ms === 'number' ? event.ts_ms : Date.now(),
    event,
  }
  const line = JSON.stringify(record) + '\n'
  const fd = openSync(path, 'a')
  try {
    writeSync(fd, line)
    fsyncSync(fd)
  } finally {
    closeSync(fd)
  }
  return record
}

/**
 * Replay all (or a suffix of) telemetry records from disk in seq order.
 * Returns the underlying EngineEvents — wrap in TelemetryRecord-aware
 * code only when the seq is needed.
 *
 * Robust to corrupt lines (skips them, continues).
 */
export function replayTelemetry(opts: ReplayOptions): EngineEvent[] {
  const path = telemetrySinkPath(opts)
  if (!existsSync(path)) return []
  let raw: string
  try {
    raw = readFileSync(path, 'utf8')
  } catch {
    return []
  }
  const fromSeq = opts.fromSeq ?? 0
  const records: TelemetryRecord[] = []
  for (const line of raw.split('\n')) {
    if (!line.trim()) continue
    try {
      const rec = JSON.parse(line) as TelemetryRecord
      if (typeof rec.seq !== 'number' || !rec.event) continue
      if (rec.seq < fromSeq) continue
      records.push(rec)
    } catch {
      continue
    }
  }
  records.sort((a, b) => a.seq - b.seq)
  return records.map((r) => r.event)
}

/**
 * Read raw TelemetryRecords (with seq + ts_ms metadata). For tests that
 * need to assert seq monotonicity / record shape, not just events.
 */
export function readTelemetryRecords(opts: ReplayOptions): TelemetryRecord[] {
  const path = telemetrySinkPath(opts)
  if (!existsSync(path)) return []
  let raw: string
  try {
    raw = readFileSync(path, 'utf8')
  } catch {
    return []
  }
  const fromSeq = opts.fromSeq ?? 0
  const records: TelemetryRecord[] = []
  for (const line of raw.split('\n')) {
    if (!line.trim()) continue
    try {
      const rec = JSON.parse(line) as TelemetryRecord
      if (typeof rec.seq !== 'number' || !rec.event) continue
      if (rec.seq < fromSeq) continue
      records.push(rec)
    } catch {
      continue
    }
  }
  records.sort((a, b) => a.seq - b.seq)
  return records
}
