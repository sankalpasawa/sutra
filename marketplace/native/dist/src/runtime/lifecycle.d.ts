/**
 * lifecycle — D4 SKELETON activation contract (PID file + lock + status).
 *
 * Native runs as a subprocess of either:
 *   - Claude Code session (via `/start-native` slash command → exec sutra-native start)
 *   - Plain shell (sutra-native start)
 *
 * v1.0 lifecycle is foreground: `start` acquires a PID lock, prints the
 * activation banner, then exits (the actual H-Sutra subscriber + router
 * land in D2 and run inside the same process or a forked daemon — TBD
 * during D2). PID lock prevents two concurrent activations from the same
 * tenant.
 *
 * v1.1 will move the long-running watcher into a forked daemon and the
 * lifecycle module gains daemonize() + reapStaleLock() helpers.
 *
 * PID file location:
 *   $SUTRA_NATIVE_HOME/native.pid          (default: ~/.sutra-native/)
 *
 * Lock semantics:
 *   - Atomic create via { flag: 'wx' } (fails if file exists)
 *   - Stale lock detection via kill(pid, 0) — if process gone, reap + retake
 *   - File contents: JSON { pid, started_at_ms, host_kind }
 *
 * Codex master review (D4) gates promotion to v1.1 daemon mode.
 */
export interface PidLockState {
    readonly pid: number;
    readonly started_at_ms: number;
    readonly host_kind: string;
}
export interface AcquireResult {
    readonly acquired: boolean;
    readonly reason?: 'lock_held_alive' | 'io_error';
    readonly existing?: PidLockState;
}
export declare function defaultPidPath(): string;
/**
 * Atomically write the PID file. Fails (acquired=false) if a live process
 * already holds the lock. If the existing PID is stale (process gone), the
 * stale file is reaped and the lock is retaken.
 */
export declare function acquirePidLock(pidPath?: string, hostKind?: string): AcquireResult;
/**
 * Release the lock at the given path.
 *
 * Default behavior: only release if this process owns the lock (pid match).
 * This protects against accidental cross-process release in a future v1.1
 * daemon mode where multiple processes might coexist.
 *
 * `force: true` releases REGARDLESS of pid ownership. Required for v1.0
 * foreground mode where `start` exits immediately (lock pid is dead by the
 * time `stop` runs). Codex master review 2026-05-03 caught the missing force
 * path — `cmdStop` now uses `force: true`.
 */
export declare function releasePidLock(pidPath?: string, opts?: {
    force?: boolean;
}): void;
export declare function readPidLock(pidPath?: string): PidLockState | null;
export interface StatusReport {
    readonly running: boolean;
    readonly pid: number | null;
    readonly started_at_ms: number | null;
    readonly host_kind: string | null;
    readonly uptime_ms: number | null;
    readonly stale_lock: boolean;
}
export declare function getStatus(pidPath?: string): StatusReport;
//# sourceMappingURL=lifecycle.d.ts.map