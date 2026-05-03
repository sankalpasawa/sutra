#!/usr/bin/env node
/**
 * sutra-native CLI — v1.1.1 entrypoint (daemon mode).
 *
 * Subcommands at v1.1.1:
 *   start      — fork a detached daemon child that runs NativeEngine until
 *                SIGTERM; parent acquires PID lock for the DAEMON pid +
 *                returns. Idempotent (lock contention → exit 1).
 *   stop       — read PID file, send SIGTERM to daemon, release lock.
 *   daemon     — INTERNAL: run NativeEngine in foreground until signal.
 *                Spawned by cmdStart; not for direct human use (but valid).
 *   status     — read PID file; report running | stopped | stale-lock
 *   version    — print version
 *   help       — print usage
 *
 * Exit codes:
 *   0 = success
 *   1 = lock contention (already running)
 *   2 = unknown subcommand / usage error
 *   3 = io error
 *
 * v1.1.1 fix: v1.1.0 cmdStart only acquired the PID lock + printed banner;
 * the engine never subscribed to H-Sutra log so "hello" went nowhere.
 * cmdStart now spawns a detached daemon child via child_process.spawn that
 * runs NativeEngine.start() until SIGTERM. PID lock records the DAEMON pid.
 */
import { spawn } from 'node:child_process';
import { existsSync, mkdirSync, openSync, unlinkSync, writeFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { acquirePidLock, defaultPidPath, getStatus, readPidLock, releasePidLock, } from '../runtime/lifecycle.js';
import { NativeEngine } from '../runtime/native-engine.js';
const VERSION = '1.1.1';
export function main(ctx) {
    const sub = ctx.argv[0] ?? 'help';
    switch (sub) {
        case 'start':
            return cmdStart(ctx);
        case 'stop':
            return cmdStop(ctx);
        case 'daemon':
            return cmdDaemon(ctx);
        case 'status':
            return cmdStatus(ctx);
        case 'version':
        case '--version':
        case '-v':
            ctx.stdout(`${VERSION}\n`);
            return 0;
        case 'help':
        case '--help':
        case '-h':
            ctx.stdout(usage());
            return 0;
        default:
            ctx.stderr(`sutra-native: unknown subcommand "${sub}"\n\n${usage()}`);
            return 2;
    }
}
/**
 * cmdDaemon — INTERNAL: run NativeEngine in foreground until SIGTERM.
 *
 * Spawned detached by cmdStart. Logs to ~/.sutra-native/native.log via
 * the inherited stdio pipe. SIGTERM/SIGINT trigger a clean shutdown.
 *
 * v1.1.1 fix per founder report 2026-05-03 (sutra-native start did not
 * actually run the engine; this is the missing wire).
 */
function cmdDaemon(ctx) {
    const nativeHome = ctx.env.SUTRA_NATIVE_HOME ?? `${ctx.env.HOME}/.sutra-native`;
    const readyPath = ctx.env.SUTRA_NATIVE_READY ?? `${nativeHome}/native.ready`;
    const intakeLog = ctx.env.SUTRA_HSUTRA_LOG_PATH;
    const engine = new NativeEngine({
        connector_options: intakeLog ? { log_path: intakeLog } : {},
        write: (line) => ctx.stdout(line + '\n'),
        on_error: (err) => ctx.stderr(`[native-engine] ${err.message}\n`),
    });
    ctx.stdout(`sutra-native daemon: starting (pid=${process.pid}, v=${VERSION})\n`);
    try {
        engine.start();
    }
    catch (err) {
        ctx.stderr(`sutra-native daemon: engine.start failed: ${err instanceof Error ? err.message : String(err)}\n`);
        return 3;
    }
    ctx.stdout(`sutra-native daemon: subscribed (intake_log=${intakeLog ?? 'default cwd resolution'})\n`);
    // Codex P1 fold 2026-05-03 (DIRECTIVE-ID: 1777802035): write a readiness
    // marker so the parent cmdStart can detect successful initialization
    // (vs spawning a doomed child). Parent polls existsSync(readyPath); we
    // own writing it. Removed in shutdown() so a fresh start can re-detect.
    try {
        mkdirSync(dirname(readyPath), { recursive: true });
        writeFileSync(readyPath, JSON.stringify({ pid: process.pid, ts_ms: Date.now() }));
    }
    catch (err) {
        ctx.stderr(`sutra-native daemon: failed to write ready marker at ${readyPath}: ${err instanceof Error ? err.message : String(err)}\n`);
        return 3;
    }
    const shutdown = (signal) => {
        ctx.stdout(`sutra-native daemon: received ${signal}; tearing down\n`);
        try {
            engine.stop();
        }
        catch { /* best-effort */ }
        try {
            if (existsSync(readyPath))
                unlinkSync(readyPath);
        }
        catch { /* best-effort */ }
        process.exit(0);
    };
    process.on('SIGTERM', () => shutdown('SIGTERM'));
    process.on('SIGINT', () => shutdown('SIGINT'));
    // Codex P1 fold 2026-05-03: REFERENCED setInterval (NOT .unref()) so the
    // event loop does NOT exit. Without this, fs.watch persistent:false in
    // the connector lets the loop empty + Node implicitly exits the daemon
    // microseconds after engine.start returns. This timer holds the loop
    // open until SIGTERM/SIGINT calls process.exit.
    setInterval(() => { }, 60_000);
    // Unreachable under normal operation (signal handlers exit). Return 0
    // for type completeness.
    return 0;
}
/**
 * cmdStop — v1.1.1 daemon mode: send SIGTERM to recorded daemon pid,
 * then release the lock. Falls back to force-release if the daemon is
 * already gone (crash recovery).
 */
function cmdStop(ctx) {
    const pidPath = ctx.env.SUTRA_NATIVE_PID ?? defaultPidPath();
    const state = readPidLock(pidPath);
    if (!state) {
        ctx.stdout('sutra-native: not running (no PID file)\n');
        return 0;
    }
    // Try to terminate the daemon process.
    let signaled = false;
    try {
        process.kill(state.pid, 'SIGTERM');
        signaled = true;
    }
    catch {
        // Process already gone — fine, just clean up the lock.
    }
    releasePidLock(pidPath, { force: true });
    const after = readPidLock(pidPath);
    if (after) {
        ctx.stderr(`sutra-native: failed to release lock at ${pidPath} (io error)\n`);
        return 1;
    }
    ctx.stdout(`sutra-native: stopped (${signaled ? 'SIGTERM sent + ' : ''}released lock pid=${state.pid})\n`);
    return 0;
}
/**
 * cmdStart — v1.1.1 daemon mode: spawn detached child running the engine.
 *
 * The child runs `sutra-native daemon` which calls NativeEngine.start()
 * + blocks until signaled. Parent records the CHILD pid in the lock file
 * so cmdStop can later kill the right process.
 *
 * Stdout/stderr of the child are appended to ~/.sutra-native/native.log
 * so the founder can tail it for telemetry without polluting the Claude
 * Code session output.
 */
function cmdStart(ctx) {
    const hostKind = ctx.env.CLAUDE_SESSION_ID ? 'claude-code' : 'cli';
    const pidPath = ctx.env.SUTRA_NATIVE_PID ?? defaultPidPath();
    const nativeHome = ctx.env.SUTRA_NATIVE_HOME ?? `${ctx.env.HOME}/.sutra-native`;
    const logPath = `${nativeHome}/native.log`;
    const readyPath = ctx.env.SUTRA_NATIVE_READY ?? `${nativeHome}/native.ready`;
    // Pre-flight: refuse early if a live lock already holds (avoids spawning
    // a doomed child that fights for the lock). Stale locks (process gone)
    // are reaped + the start proceeds.
    const existingLock = readPidLock(pidPath);
    if (existingLock) {
        try {
            process.kill(existingLock.pid, 0);
            const ageMin = Math.round((Date.now() - existingLock.started_at_ms) / 60000);
            ctx.stderr(`sutra-native: already running (pid=${existingLock.pid}, host=${existingLock.host_kind}, started ${ageMin}m ago)\n` +
                `  PID file: ${pidPath}\n` +
                `  To stop: sutra-native stop\n`);
            return 1;
        }
        catch {
            // Stale — release before re-acquiring
            releasePidLock(pidPath, { force: true });
        }
    }
    // Clear any stale ready marker so the poll below only succeeds on a
    // genuinely fresh daemon start.
    try {
        if (existsSync(readyPath))
            unlinkSync(readyPath);
    }
    catch {
        // best-effort
    }
    const nodeBin = process.execPath;
    const selfPath = resolve(process.argv[1] ?? __filename);
    try {
        mkdirSync(nativeHome, { recursive: true });
    }
    catch {
        // best-effort
    }
    // Codex P1 fold 2026-05-03 (DIRECTIVE-ID: 1777802035): use Node's openSync
    // in append mode + spawn directly (no bash -c). Cleaner than shell
    // redirection + portable.
    let logFd;
    try {
        logFd = openSync(logPath, 'a');
    }
    catch (err) {
        ctx.stderr(`sutra-native: failed to open log ${logPath}: ${err instanceof Error ? err.message : String(err)}\n`);
        return 3;
    }
    const child = spawn(nodeBin, [selfPath, 'daemon'], {
        detached: true,
        stdio: ['ignore', logFd, logFd],
        env: {
            ...process.env,
            SUTRA_NATIVE_PID: pidPath,
            SUTRA_NATIVE_HOME: nativeHome,
            SUTRA_NATIVE_READY: readyPath,
        },
    });
    if (typeof child.pid !== 'number') {
        ctx.stderr('sutra-native: failed to spawn daemon child\n');
        return 3;
    }
    child.unref();
    // Parent owns the PID file (the LOCK).
    const state = {
        pid: child.pid,
        started_at_ms: Date.now(),
        host_kind: hostKind,
    };
    try {
        mkdirSync(dirname(pidPath), { recursive: true });
        writeFileSync(pidPath, JSON.stringify(state, null, 2), { flag: 'w' });
    }
    catch (err) {
        ctx.stderr(`sutra-native: spawned daemon (pid=${child.pid}) but failed to write PID file: ${err instanceof Error ? err.message : String(err)}\n`);
        return 3;
    }
    // Codex P1 fold 2026-05-03: poll for readiness marker (the daemon writes
    // it once engine.start succeeds). 50ms cadence × 100 = 5s timeout.
    const startupTimeoutMs = parseInt(ctx.env.SUTRA_NATIVE_STARTUP_TIMEOUT_MS ?? '5000', 10);
    const pollIntervalMs = 50;
    const maxPolls = Math.ceil(startupTimeoutMs / pollIntervalMs);
    let ready = false;
    for (let i = 0; i < maxPolls; i++) {
        if (existsSync(readyPath)) {
            ready = true;
            break;
        }
        // Also check the child hasn't already died
        try {
            process.kill(child.pid, 0);
        }
        catch {
            ctx.stderr(`sutra-native: daemon child died during startup (pid=${child.pid}). See ${logPath}\n`);
            releasePidLock(pidPath, { force: true });
            return 3;
        }
        // Sync sleep via Atomics.wait on a tiny SharedArrayBuffer would be cleanest
        // but adds complexity; busy-poll a date check is sufficient at 50ms.
        const target = Date.now() + pollIntervalMs;
        while (Date.now() < target) { /* busy wait */ }
    }
    if (!ready) {
        ctx.stderr(`sutra-native: daemon did not signal ready within ${startupTimeoutMs}ms. Killing pid=${child.pid}. See ${logPath}\n`);
        try {
            process.kill(child.pid, 'SIGTERM');
        }
        catch { /* */ }
        releasePidLock(pidPath, { force: true });
        return 3;
    }
    // Suppress unused-import warning — acquirePidLock kept for callers that
    // may want the older single-step behavior.
    void acquirePidLock;
    ctx.stdout(formatBanner(hostKind, pidPath, child.pid, logPath));
    return 0;
}
function cmdStatus(ctx) {
    const pidPath = ctx.env.SUTRA_NATIVE_PID ?? defaultPidPath();
    const report = getStatus(pidPath);
    ctx.stdout(formatStatus(report, pidPath));
    return 0;
}
function formatBanner(hostKind, pidPath, daemonPid, logPath) {
    const pidLine = daemonPid !== undefined
        ? `│ ✓ Activated  v=${VERSION}  host=${hostKind.padEnd(11)}  daemon_pid=${daemonPid}    │`
        : `│ ✓ Activated  v=${VERSION}  host=${hostKind.padEnd(11)}  pid=${process.pid}        │`;
    return [
        '┌─ SUTRA-NATIVE ──────────────────────────────────────────────┐',
        pidLine,
        `│ PID file:  ${pidPath.slice(0, 50).padEnd(50)} │`,
        logPath
            ? `│ Log:       ${logPath.slice(0, 50).padEnd(50)} │`
            : '│ Daemon:    runtime-active engine subscribed                  │',
        '│ Surfaces:  /start-native (slash) · sutra-native (CLI)        │',
        '└──────────────────────────────────────────────────────────────┘',
        '',
        'Next: founder input flows through Sutra Core H-Sutra layer →',
        '      Native engine routes via TriggerSpec → executes Workflow.',
        '',
    ].join('\n');
}
function formatStatus(r, pidPath) {
    if (!r.running && !r.stale_lock) {
        return [
            'sutra-native: stopped',
            `  PID file: ${pidPath} (absent)`,
            `  Version: ${VERSION}`,
            '',
        ].join('\n');
    }
    if (r.stale_lock) {
        return [
            'sutra-native: STALE LOCK',
            `  PID file: ${pidPath}`,
            `  Recorded pid: ${r.pid} (process gone — lock will be reaped on next start)`,
            `  Version: ${VERSION}`,
            '',
        ].join('\n');
    }
    const uptimeMin = Math.round((r.uptime_ms ?? 0) / 60000);
    return [
        'sutra-native: running',
        `  pid:        ${r.pid}`,
        `  host:       ${r.host_kind}`,
        `  started:    ${r.started_at_ms ? new Date(r.started_at_ms).toISOString() : '?'}`,
        `  uptime:     ${uptimeMin}m`,
        `  PID file:   ${pidPath}`,
        `  Version:    ${VERSION}`,
        '',
    ].join('\n');
}
function usage() {
    return [
        'sutra-native — Native productization CLI (v' + VERSION + ')',
        '',
        'Usage:',
        '  sutra-native <subcommand> [options]',
        '',
        'Subcommands:',
        '  start      Activate Native (acquire PID lock, print banner)',
        '  stop       Deactivate Native (release PID lock)',
        '  status     Report current activation state',
        '  version    Print version',
        '  help       Print this usage',
        '',
        'Environment:',
        '  SUTRA_NATIVE_HOME  Base dir for PID file (default: ~/.sutra-native)',
        '  SUTRA_NATIVE_PID   Override PID file path entirely',
        '  CLAUDE_SESSION_ID  Auto-set when invoked from /start-native slash',
        '',
        'See: holding/plans/native-productization-v1.0/SPEC.md',
        '',
    ].join('\n');
}
export { cmdStart, cmdStatus, formatBanner, formatStatus, usage };
// Auto-execute when called as bin (not when imported as a module).
// Detection: process.argv[1] resolves to this file or the .js dist twin.
const isMain = process.argv[1] !== undefined &&
    (process.argv[1].endsWith('sutra-native.js') ||
        process.argv[1].endsWith('sutra-native.ts') ||
        process.argv[1].endsWith('/sutra-native'));
if (isMain) {
    const sub = process.argv[2];
    const exitCode = main({
        argv: process.argv.slice(2),
        env: process.env,
        stdout: (s) => process.stdout.write(s),
        stderr: (s) => process.stderr.write(s),
    });
    // Codex P1 fold 2026-05-03 (DIRECTIVE-ID: 1777802035): for the `daemon`
    // subcommand, cmdDaemon installs SIGTERM/SIGINT handlers + a referenced
    // setInterval that keeps the event loop alive. Calling process.exit here
    // would kill the daemon microseconds after engine.start. Skip exit for
    // daemon mode; let the signal handlers control teardown.
    if (sub !== 'daemon') {
        process.exit(exitCode);
    }
    // For daemon mode: function returns; event loop stays alive via the ref'd
    // timer in cmdDaemon. process.exit fires from SIGTERM handler.
}
//# sourceMappingURL=sutra-native.js.map