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
import { existsSync, readFileSync, statSync, watch } from 'node:fs';
import { isHSutraEvent } from '../types/h-sutra-event.js';
const DEFAULT_CACHE_TTL_MS = 24 * 60 * 60 * 1000;
/**
 * Resolve the H-Sutra log path. Asawa override (holding/state/interaction/
 * log.jsonl) takes priority if it exists; otherwise default (.sutra/
 * h-sutra.jsonl). Both relative to process.cwd().
 */
export function resolveHSutraLogPath(cwd = process.cwd()) {
    const asawaPath = `${cwd}/holding/state/interaction/log.jsonl`;
    if (existsSync(asawaPath))
        return asawaPath;
    return `${cwd}/.sutra/h-sutra.jsonl`;
}
export class HSutraConnector {
    listeners = [];
    cache = new Map();
    watcher = null;
    logPath;
    cacheTtl;
    partialLine = '';
    currentOffset = 0;
    currentInode = null;
    // Stats
    eventsSeenCount = 0;
    eventsEmittedCount = 0;
    duplicatesSkippedCount = 0;
    malformedRowsCount = 0;
    constructor(options = {}) {
        this.logPath = options.log_path ?? resolveHSutraLogPath();
        this.cacheTtl = options.cache_ttl_ms ?? DEFAULT_CACHE_TTL_MS;
    }
    /**
     * Begin watching. Reads the file from byte 0 (restart catch-up), emits
     * each row, then registers fs.watch for subsequent appends.
     *
     * Idempotent — repeated calls are a no-op if already watching.
     */
    start() {
        if (this.watcher)
            return;
        // Capture initial inode + size if file exists
        if (existsSync(this.logPath)) {
            const stat = statSync(this.logPath);
            this.currentInode = stat.ino;
            // Read existing rows from byte 0 for restart catch-up
            this.readNewBytes(0, stat.size);
        }
        else {
            this.currentInode = null;
            this.currentOffset = 0;
        }
        // Watch for appends. fs.watch fires on rename + change events.
        this.watcher = watch(getDir(this.logPath), { persistent: false }, (eventType, filename) => {
            if (filename && !this.logPath.endsWith(filename))
                return;
            this.handleFsEvent();
        });
    }
    stop() {
        if (this.watcher) {
            this.watcher.close();
            this.watcher = null;
        }
    }
    onEvent(listener) {
        this.listeners.push(listener);
        return () => {
            this.listeners = this.listeners.filter((l) => l !== listener);
        };
    }
    getCachedEvent(turn_id) {
        this.evictExpired();
        const entry = this.cache.get(turn_id);
        return entry ? entry.event : null;
    }
    getStats() {
        this.evictExpired();
        return {
            events_seen: this.eventsSeenCount,
            events_emitted: this.eventsEmittedCount,
            duplicates_skipped: this.duplicatesSkippedCount,
            malformed_rows: this.malformedRowsCount,
            cache_size: this.cache.size,
            current_offset: this.currentOffset,
            current_inode: this.currentInode,
            listener_count: this.listeners.length,
        };
    }
    /**
     * Manually trigger a re-scan. Used by tests + by callers that want to
     * pull events synchronously rather than waiting for the fs.watch event.
     */
    pollNow() {
        this.handleFsEvent();
    }
    // ---------------------------------------------------------------------
    // Internal
    // ---------------------------------------------------------------------
    handleFsEvent() {
        if (!existsSync(this.logPath)) {
            // File deleted/missing — reset state
            this.currentOffset = 0;
            this.currentInode = null;
            this.partialLine = '';
            return;
        }
        const stat = statSync(this.logPath);
        // Detect rotation (inode change) — reset to 0
        if (this.currentInode !== null && stat.ino !== this.currentInode) {
            this.currentOffset = 0;
            this.partialLine = '';
            this.currentInode = stat.ino;
        }
        // Detect truncation (size < offset) — reset to 0
        if (stat.size < this.currentOffset) {
            this.currentOffset = 0;
            this.partialLine = '';
        }
        if (this.currentInode === null) {
            this.currentInode = stat.ino;
        }
        // Read new bytes
        if (stat.size > this.currentOffset) {
            this.readNewBytes(this.currentOffset, stat.size);
        }
    }
    readNewBytes(start, end) {
        let chunk;
        try {
            const fd = readFileSync(this.logPath, { encoding: 'utf8' });
            chunk = fd.slice(start, end);
        }
        catch {
            return;
        }
        this.currentOffset = end;
        // Combine with any buffered partial line from prior call
        const combined = this.partialLine + chunk;
        const lines = combined.split('\n');
        // Last element might be partial (no trailing \n) — buffer it
        this.partialLine = lines.pop() ?? '';
        for (const line of lines) {
            if (line.trim().length === 0)
                continue;
            this.processLine(line);
        }
    }
    processLine(line) {
        let parsed;
        try {
            parsed = JSON.parse(line);
        }
        catch {
            this.malformedRowsCount++;
            return;
        }
        if (!isHSutraEvent(parsed)) {
            this.malformedRowsCount++;
            return;
        }
        this.eventsSeenCount++;
        // Idempotency: same turn_id twice → cache update, no re-emit
        const existing = this.cache.get(parsed.turn_id);
        if (existing) {
            this.duplicatesSkippedCount++;
            // Refresh cache TTL but don't re-emit
            this.cache.set(parsed.turn_id, { event: parsed, cached_at_ms: Date.now() });
            return;
        }
        this.cache.set(parsed.turn_id, { event: parsed, cached_at_ms: Date.now() });
        this.eventsEmittedCount++;
        // Fire listeners (defensive — never let listener throw escape)
        for (const listener of this.listeners) {
            try {
                listener(parsed);
            }
            catch {
                // Listener errors are isolated; counter not incremented.
            }
        }
    }
    evictExpired() {
        const cutoff = Date.now() - this.cacheTtl;
        for (const [k, v] of this.cache.entries()) {
            if (v.cached_at_ms < cutoff) {
                this.cache.delete(k);
            }
        }
    }
}
function getDir(path) {
    const idx = path.lastIndexOf('/');
    return idx >= 0 ? path.slice(0, idx) : '.';
}
//# sourceMappingURL=h-sutra-connector.js.map