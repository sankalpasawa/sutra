/**
 * h-sutra-connector — D2 step 1 of vertical slice.
 *
 * Native subscribes to the H-Sutra log file (Sutra Core v2.14+ writes one
 * JSONL row per founder turn). Per C3 + C10:
 *   - Asawa override path: holding/state/interaction/log.jsonl
 *   - Default path:        .sutra/h-sutra.jsonl
 *   - READ-ONLY at v1.0 (never appends; never mutates)
 *
 * The connector:
 *   1. Reads the existing file from byte offset 0 (catch-up on restart)
 *   2. Watches for appends via fs.watch (with stat-based offset tracking)
 *   3. Parses each newline-terminated row as JSON → HSutraEvent
 *   4. Caches by turn_id (Map; 24h TTL by default)
 *   5. Emits to registered listeners
 *
 * Codex amendment 5 (R-WATCHER + R-IDEMPOTENCY) — explicit handling:
 *   - Log ROTATION: stat()'d ino changes → reset offset to 0
 *   - Log TRUNCATION: stat().size < currentOffset → reset to 0
 *   - DUPLICATE lines: same turn_id seen twice → cache update, NO double-emit
 *   - PARTIAL writes: incomplete trailing line buffered until newline arrives
 *   - RESTART CATCH-UP: cold start reads from byte 0 (no resume offset
 *     persisted at v1.0; v1.1+ may persist for large logs)
 *
 * The connector is DEFENSIVE — malformed rows are dropped silently with a
 * counter increment (getStats().malformed). Never throws to the listener.
 */
import { type HSutraEvent } from '../types/h-sutra-event.js';
export type HSutraEventListener = (event: HSutraEvent) => void;
export interface HSutraConnectorStats {
    readonly events_seen: number;
    readonly events_emitted: number;
    readonly duplicates_skipped: number;
    readonly malformed_rows: number;
    readonly cache_size: number;
    readonly current_offset: number;
    readonly current_inode: number | null;
    readonly listener_count: number;
}
export interface HSutraConnectorOptions {
    /** Time-to-live for cached events (ms). Default: 24h. */
    readonly cache_ttl_ms?: number;
    /** Custom path; otherwise resolves Asawa override → default. */
    readonly log_path?: string;
}
/**
 * Resolve the H-Sutra log path. Asawa override (holding/state/interaction/
 * log.jsonl) takes priority if it exists; otherwise default (.sutra/
 * h-sutra.jsonl). Both relative to process.cwd().
 */
export declare function resolveHSutraLogPath(cwd?: string): string;
export declare class HSutraConnector {
    private listeners;
    private cache;
    private watcher;
    private logPath;
    private cacheTtl;
    private partialLine;
    private currentOffset;
    private currentInode;
    private eventsSeenCount;
    private eventsEmittedCount;
    private duplicatesSkippedCount;
    private malformedRowsCount;
    constructor(options?: HSutraConnectorOptions);
    /**
     * Begin watching. Reads the file from byte 0 (restart catch-up), emits
     * each row, then registers fs.watch for subsequent appends.
     *
     * Idempotent — repeated calls are a no-op if already watching.
     */
    start(): void;
    stop(): void;
    onEvent(listener: HSutraEventListener): () => void;
    getCachedEvent(turn_id: string): HSutraEvent | null;
    getStats(): HSutraConnectorStats;
    /**
     * Manually trigger a re-scan. Used by tests + by callers that want to
     * pull events synchronously rather than waiting for the fs.watch event.
     */
    pollNow(): void;
    private handleFsEvent;
    private readNewBytes;
    private processLine;
    private evictExpired;
}
//# sourceMappingURL=h-sutra-connector.d.ts.map