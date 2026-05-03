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
import { type StatusReport } from '../runtime/lifecycle.js';
interface CommandContext {
    readonly argv: ReadonlyArray<string>;
    readonly env: NodeJS.ProcessEnv;
    readonly stdout: (s: string) => void;
    readonly stderr: (s: string) => void;
}
export declare function main(ctx: CommandContext): Promise<number>;
declare function cmdCreateDomain(ctx: CommandContext): number;
declare function cmdCreateCharter(ctx: CommandContext): number;
declare function cmdCreateWorkflow(ctx: CommandContext): number;
declare function cmdList(ctx: CommandContext): number;
declare function cmdRun(ctx: CommandContext): Promise<number>;
/**
 * detectHostKind — classify the runtime context that invoked sutra-native.
 *
 * Returns 'claude-code' when the process is running inside a Claude Code
 * session, 'cli' otherwise. Used as telemetry provenance, not a trust
 * boundary — callers MUST NOT make security decisions on the result.
 *
 * Detection signals (in priority order):
 *   1. CLAUDECODE === '1' — documented Claude Code env flag (v2.x+).
 *      Verified via `env | grep CLAUDE` inside Claude Code Bash tool calls.
 *   2. CLAUDE_SESSION_ID — legacy fallback. Was the v1.1.0-1.1.2 detector
 *      but Claude Code does NOT actually export this var to Bash tool calls
 *      (verified Claude Code v2.1.126); kept for forward compatibility in
 *      case the harness starts setting it, or for hooks/slash invocations
 *      that explicitly inject it.
 *
 * Codex consult 2026-05-03: defer codex-cli host detection to a separate
 * patch — CODEX_HOME / OPENAI_API_KEY are weak, non-canonical signals.
 */
export declare function detectHostKind(env: NodeJS.ProcessEnv): 'claude-code' | 'cli';
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
declare function cmdStart(ctx: CommandContext): number;
declare function cmdStatus(ctx: CommandContext): number;
declare function formatBanner(hostKind: string, pidPath: string, daemonPid?: number, logPath?: string): string;
declare function formatStatus(r: StatusReport, pidPath: string): string;
declare function usage(): string;
export { cmdStart, cmdStatus, cmdCreateDomain, cmdCreateCharter, cmdCreateWorkflow, cmdList, cmdRun, formatBanner, formatStatus, usage, };
//# sourceMappingURL=sutra-native.d.ts.map