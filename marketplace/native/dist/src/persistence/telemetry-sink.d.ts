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
import type { EngineEvent } from '../types/engine-event.js';
export interface TelemetrySinkOptions {
    /** $SUTRA_NATIVE_HOME-equivalent root. Sink path = <home>/runtime/telemetry/events.jsonl. */
    readonly home: string;
}
export interface TelemetryRecord {
    readonly seq: number;
    readonly ts_ms: number;
    readonly event: EngineEvent;
}
export interface ReplayOptions extends TelemetrySinkOptions {
    /** Skip records with seq < fromSeq. Default: 0 (replay all). */
    readonly fromSeq?: number;
}
/**
 * Resolve the JSONL sink path for a given HOME root.
 */
export declare function telemetrySinkPath(opts: TelemetrySinkOptions): string;
/**
 * Read the highest seq currently on disk. Returns 0 when the file is
 * absent or has no parseable records. Used at sink-open to initialize the
 * in-memory counter so per-process appends continue from the right number.
 *
 * Robust to truncated/corrupt trailing lines (treats them as absent).
 */
export declare function readLastSeq(opts: TelemetrySinkOptions): number;
/**
 * Test-only helper. Resets the in-memory counter for a given HOME so a
 * subsequent appendTelemetry re-reads from disk. Safe to call from tests
 * that recreate $SUTRA_NATIVE_HOME between scenarios.
 */
export declare function resetTelemetryCounter(opts: TelemetrySinkOptions): void;
/**
 * Append a TelemetryRecord wrapping the EngineEvent to the sink.
 * Per-event open/write/fsync/close — durable under arbitrary process
 * death. Returns the assigned record (caller can correlate via seq).
 *
 * On any I/O failure throws — caller (NativeEngine wire) is expected to
 * route through the existing onError sink, never silently drop.
 */
export declare function appendTelemetry(event: EngineEvent, opts: TelemetrySinkOptions): TelemetryRecord;
/**
 * Replay all (or a suffix of) telemetry records from disk in seq order.
 * Returns the underlying EngineEvents — wrap in TelemetryRecord-aware
 * code only when the seq is needed.
 *
 * Robust to corrupt lines (skips them, continues).
 */
export declare function replayTelemetry(opts: ReplayOptions): EngineEvent[];
/**
 * Read raw TelemetryRecords (with seq + ts_ms metadata). For tests that
 * need to assert seq monotonicity / record shape, not just events.
 */
export declare function readTelemetryRecords(opts: ReplayOptions): TelemetryRecord[];
//# sourceMappingURL=telemetry-sink.d.ts.map