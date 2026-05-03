#!/usr/bin/env node
/**
 * sutra-native CLI — D4 SKELETON entrypoint.
 *
 * Subcommands at v1.0 (D4 SKELETON):
 *   start      — acquire PID lock + print activation banner (foreground exit;
 *                D2 will fold the H-Sutra subscriber + router into the same
 *                process or fork a daemon)
 *   status     — read PID file; report running | stopped | stale-lock
 *   version    — print version from package.json
 *   help       — print usage
 *
 * Exit codes:
 *   0 = success
 *   1 = lock contention (already running)
 *   2 = unknown subcommand / usage error
 *   3 = io error
 *
 * Per founder direction 2026-05-02: when "start Native" fires, both the
 * slash command (/start-native) and the CLI (sutra-native start) execute
 * the same activation path. Slash command lives at
 * .claude-plugin/commands/start-native.md.
 *
 * Per codex master review cadence (post-D4 wiring): this file's PID/lock +
 * banner contract is gated by a master review before D2 begins.
 */
import { type StatusReport } from '../runtime/lifecycle.js';
interface CommandContext {
    readonly argv: ReadonlyArray<string>;
    readonly env: NodeJS.ProcessEnv;
    readonly stdout: (s: string) => void;
    readonly stderr: (s: string) => void;
}
export declare function main(ctx: CommandContext): number;
declare function cmdStart(ctx: CommandContext): number;
declare function cmdStatus(ctx: CommandContext): number;
declare function formatBanner(hostKind: string, pidPath: string): string;
declare function formatStatus(r: StatusReport, pidPath: string): string;
declare function usage(): string;
export { cmdStart, cmdStatus, formatBanner, formatStatus, usage };
//# sourceMappingURL=sutra-native.d.ts.map