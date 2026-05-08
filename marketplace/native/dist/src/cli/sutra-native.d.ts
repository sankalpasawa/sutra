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
/**
 * v1.3.0 W1.8 (codex W1.8 + W3 fold) — `sutra-native create-trigger`.
 *
 * Mints a TriggerSpec + persists to user-kit/triggers/<T-id>.json.
 *
 * Flags:
 *   --id <T-id>                                      required
 *   --workflow-id <W-id>                             required; verified
 *                                                     against the user-kit
 *                                                     via loadWorkflow
 *   --event-type <founder_input|cron|file_drop|webhook>
 *                                                     required; validated
 *                                                     against TRIGGER_EVENT_TYPES
 *   --match-all "<csv>" XOR --match-any "<csv>"       required when
 *                                                     event-type='founder_input';
 *                                                     mutually exclusive
 *   --cadence-spec <json-string>                      accepted for cron
 *                                                     (W3 fold; W1 just
 *                                                     persists, W3 wires)
 *   --charter-id <C-id>                              optional
 *   --domain-id <D-id>                               optional
 *   --description <text>                             optional
 *
 * Predicate construction (codex W1.8 fold):
 *   - founder_input + --match-all "kw1,kw2"  → AND of contains predicates
 *   - founder_input + --match-any "kw1,kw2"  → OR of contains predicates
 *   - cron                                    → always_true
 *
 * Errors exit 2 (usage error) or 3 (io error). codex W1.8 mandates
 * EXPLICIT errors for the validation paths (workflow not found, both
 * match flags set, neither match flag set).
 */
declare function cmdCreateTrigger(ctx: CommandContext): number;
declare function cmdList(ctx: CommandContext): number;
declare function cmdRun(ctx: CommandContext): Promise<number>;
/**
 * v1.3.0 W3 (operator surface dispatcher).
 *
 * `sutra-native workflow status [E-id]`     — list executions or show one
 * `sutra-native workflow cancel <E-id>`     — cancel a paused/unknown execution
 *                                              (added in W3.cancel commit)
 *
 * Status reads decision-provenance.jsonl (workflow STARTED / COMPLETED /
 * FAILED records) and unions in pending approval ledger entries to surface
 * paused executions.
 */
declare function cmdWorkflow(ctx: CommandContext): number;
declare function cmdWorkflowStatus(ctx: CommandContext): number;
/**
 * v1.3.0 W3 (codex W3 BLOCKER 2 fold) — workflow cancel.
 *
 * Cancel was BLOCKED at W3 plan time until paused-execution machinery from
 * W2 shipped. W2 ships the execution-approval-ledger so cancel-while-paused
 * is now wireable: ledger pending → rejected with reason='cancelled'.
 *
 * Three paths:
 *   - approval record exists, status='pending'    → updateApprovalStatus
 *     to 'rejected' reason='cancelled'; engine emits workflow_failed
 *     reason=cancelled on next dispatch (the rejection branch).
 *   - approval record exists, status terminal     → idempotent no-op,
 *     emits "already terminal" + exit 0.
 *   - no approval record (running or unknown)     → write a marker at
 *     runtime/cancellations/E-<id>.json so the engine can consume on
 *     next ingest. Best-effort + auditable since lite-executor lacks
 *     a cancel token (codex W3 advisory).
 */
declare function cmdWorkflowCancel(ctx: CommandContext): number;
/**
 * v1.3.0 W3 (codex W3 BLOCKER 3 fold) — tenant list.
 *
 * `sutra-native tenant list` scans Domains (each carries `tenant_id`) and
 * unions with Workflows where `custody_owner` is non-null. NO separate
 * tenant registry file (codex W3: "scan Domains, not a registry file").
 * Output sorted, deduplicated, with per-tenant counts.
 *
 * Codex W3 BLOCKER 3 closes the "where do tenants come from" question.
 * Domains carry tenant_id (D4 §1.1) so the existence of a Domain implies
 * the tenant. Workflows can carry a custody_owner=T-<id> (M4.4 / D-NS-11)
 * which may add tenants not yet represented as Domains.
 */
declare function cmdTenant(ctx: CommandContext): number;
declare function cmdTenantList(ctx: CommandContext): number;
/**
 * v1.3.0 W6 (cutover engine) — `sutra-native cutover validate <contract.json>`
 * + `sutra-native cutover dry-run <contract.json>`.
 *
 * The cutover-validator + cutover-applier (dry-run) are pure functions over
 * the CutoverContract zod-validated shape. The CLI is the founder-facing
 * surface: read the JSON, run the validator/dry-run, print result, exit
 *   0 — success
 *   2 — validation error (contract structurally invalid)
 *   3 — io error (file missing / unreadable / not JSON)
 *
 * Apply-with-rollback is DEFERRED to v1.x.1 per plan §6 + codex implicit
 * advisory. v1.3.0 ships observe + plan; never mutate.
 */
declare function cmdCutover(ctx: CommandContext): number;
declare function cmdCutoverValidate(ctx: CommandContext): number;
declare function cmdCutoverDryRun(ctx: CommandContext): number;
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
export { cmdStart, cmdStatus, cmdCreateDomain, cmdCreateCharter, cmdCreateWorkflow, cmdCreateTrigger, cmdList, cmdRun, cmdWorkflow, cmdWorkflowStatus, cmdWorkflowCancel, cmdTenant, cmdTenantList, cmdCutover, cmdCutoverValidate, cmdCutoverDryRun, formatBanner, formatStatus, usage, };
//# sourceMappingURL=sutra-native.d.ts.map