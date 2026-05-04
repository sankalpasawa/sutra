/**
 * NativeEngine — v1.1.0 wires the D2 vertical slice into a single
 * subscribable runtime so SessionStart hook → engine.start() → founder
 * input → SUCCESS Execution flows end-to-end.
 *
 * Composition:
 *   HSutraConnector   → reads founder events from Sutra Core JSONL log
 *   Router            → maps events to TriggerSpec → target Workflow
 *   LiteExecutor      → walks the matched Workflow's step_graph
 *   ArtifactCatalog   → records cataloged outputs (optional)
 *   RendererRegistry  → prints terminal lines per EngineEvent
 *
 * Per softened I-NPD-1: every routing decision + workflow event flows
 * through a single emit() pipeline so audit/replay sees the same stream
 * a fresh subscriber would.
 *
 * Failure isolation: any per-event handler throw is caught + logged via
 * the on_error callback (defaults to console.error). The connector's own
 * listener-throw isolation (D2.1) keeps a buggy renderer from killing
 * the whole subscription.
 */

import type { Workflow } from '../primitives/workflow.js'
import type { TriggerSpec } from '../types/trigger-spec.js'
import type { HSutraEvent } from '../types/h-sutra-event.js'
import type {
  EngineEvent,
  RoutingDecisionEvent,
  PatternProposedEvent,
  ProposalApprovedEvent,
  ProposalRejectedEvent,
  ApprovalGrantedEvent,
  ApprovalDeniedEvent,
  ApprovalAlreadyHandledEvent,
} from '../types/engine-event.js'
import { HSutraConnector, type HSutraConnectorOptions } from './h-sutra-connector.js'
import { Router } from './router.js'
import { ArtifactCatalog, type ArtifactCatalogOptions } from './artifact-catalog.js'
import { RendererRegistry } from './renderer-registry.js'
import { executeWorkflow, executeWorkflowResume } from './lite-executor.js'
import { loadStarterKit, STARTER_WORKFLOW_CHARTER_MAP } from '../starter-kit/index.js'
import {
  listTriggers as listUserKitTriggers,
  listWorkflows as listUserKitWorkflows,
  persistTrigger,
  persistWorkflow,
  type UserKitOptions,
} from '../persistence/user-kit.js'
import {
  loadProposal,
  persistProposal,
  updateProposalStatus,
} from '../persistence/proposal-ledger.js'
import {
  listApprovals,
  loadApproval,
  markResumed,
  persistApproval,
  updateApprovalStatus,
  type ExecutionApprovalRecord,
} from '../persistence/execution-approval-ledger.js'
import { detectPatterns, type PatternDetectorOptions } from './pattern-detector.js'
import { buildProposal } from './proposal-builder.js'
import {
  appendDecisionProvenanceLog,
  buildEmergenceDecisionProvenance,
} from './emergence-provenance.js'

export interface NativeEngineOptions {
  readonly connector_options?: HSutraConnectorOptions
  readonly catalog_options?: ArtifactCatalogOptions
  /** Replace the starter triggers + workflows. Default: load the v1.1.0 starter kit. */
  readonly triggers?: ReadonlyArray<TriggerSpec>
  readonly workflows?: ReadonlyArray<Workflow>
  /** Sink for rendered lines. Default: console.log. */
  readonly write?: (line: string) => void
  /** Sink for non-fatal errors. Default: console.error. */
  readonly on_error?: (err: Error) => void

  // -------------------------------------------------------------------------
  // SPEC v1.2 §4.5 — organic emergence v1
  // -------------------------------------------------------------------------
  /** Enable the no-match → propose loop. Default reads SUTRA_NATIVE_PROPOSER. */
  readonly proposer_enabled?: boolean
  /** UserKit storage opts (HOME override etc); shared by user-kit + ledger. */
  readonly user_kit_options?: UserKitOptions
  /** Pattern-detector knobs (k_threshold, window_ms, etc). */
  readonly pattern_detector_options?: Partial<PatternDetectorOptions>
  /** Skip loading user-kit primitives at boot. Default false. */
  readonly skip_user_kit?: boolean
  /** Override clock for deterministic tests. */
  readonly now_ms?: () => number
}

// v1.3.0 W2 (codex W2 advisory C fold) — centralized namespace dispatcher.
// PROPOSAL approvals (P-<sha8>) and EXECUTION approvals (E-<id>) flow through
// the SAME parser so future namespaces (R-<id> for runs, etc.) plug in cleanly.
//
// Pattern: `(approve|reject) (P-XXXXXXXX|E-...) [reason]`
//   - P namespace: P-<sha8> (8 lowercase hex). Reason optional on reject.
//   - E namespace: E-<turn_id>-<seq> (alphanumeric + hyphens; matches NativeEngine's
//     executionId construction). Reason optional on reject.
//
// Returned `id` is namespace-prefixed (e.g., 'P-deadbeef' or 'E-t1-1') so
// downstream loaders (loadProposal / loadApproval) work directly with it.
const APPROVAL_RE = /^\s*(approve|reject)\s+([PE]-[A-Za-z0-9_-]+)(?:\s+(.+))?\s*$/i

export interface ApprovalUtterance {
  readonly namespace: 'P' | 'E'
  readonly id: string
  readonly action: 'approve' | 'reject'
  readonly reason?: string
}

/**
 * Parse a founder utterance for approve/reject commands across ALL namespaces.
 *
 * Returns null when text doesn't match the approval grammar. Returns parsed
 * components when it does. Caller dispatches based on `namespace`:
 *   - 'P' → applyApproval / applyRejection (proposal-ledger)
 *   - 'E' → applyExecutionApproval / applyExecutionRejection (execution-approval-ledger)
 *
 * Codex W2 advisory C fold (2026-05-04): a single parser keeps the H-Sutra
 * surface coherent and lets unit tests verify "approve P-deadbeef" vs
 * "approve E-t1-1" with one set of regex assertions.
 */
export function parseApprovalUtterance(text: string): ApprovalUtterance | null {
  if (typeof text !== 'string') return null
  const m = APPROVAL_RE.exec(text.trim())
  if (!m) return null
  const action = m[1].toLowerCase() as 'approve' | 'reject'
  const id = m[2]
  const namespace = id.startsWith('P-') ? 'P' : 'E'
  const reason = m[3]?.trim()
  const out: ApprovalUtterance = reason
    ? { namespace, id, action, reason }
    : { namespace, id, action }
  return out
}

export class NativeEngine {
  readonly connector: HSutraConnector
  readonly router: Router
  readonly catalog: ArtifactCatalog
  readonly renderer: RendererRegistry
  private readonly workflowsById: Map<string, Workflow>
  private readonly write: (line: string) => void
  private readonly onError: (err: Error) => void
  private executionCounter = 0
  private started = false
  /**
   * v1.2.1: serialization queue. The connector delivers events synchronously
   * but handleHSutraEvent is now async (host-LLM dispatch may take seconds).
   * Without this chain, two founder turns could overlap and collide on
   * executionCounter / ledger state. Each event is appended to the chain so
   * they run sequentially even when the connector fires faster than dispatch
   * resolves. Codex master review (DIRECTIVE 1777839055) P1 fold.
   */
  private turnQueue: Promise<void> = Promise.resolve()

  // SPEC v1.2 §4.5 — proposer state
  private readonly proposerEnabled: boolean
  private readonly userKitOptions: UserKitOptions
  private readonly patternDetectorOptions: Partial<PatternDetectorOptions>
  private readonly nowMs: () => number

  constructor(options: NativeEngineOptions = {}) {
    const kit = loadStarterKit()
    this.connector = new HSutraConnector(options.connector_options ?? {})
    this.router = new Router()
    this.catalog = new ArtifactCatalog(options.catalog_options ?? {})
    this.renderer = new RendererRegistry()
    this.write = options.write ?? ((line) => console.log(line))
    this.onError = options.on_error ?? ((err) => console.error(`[native-engine] ${err.message}`))
    this.nowMs = options.now_ms ?? (() => Date.now())

    // Proposer wiring — default OFF unless env says on; explicit option wins.
    this.userKitOptions = options.user_kit_options ?? {}
    this.patternDetectorOptions = options.pattern_detector_options ?? {}
    if (typeof options.proposer_enabled === 'boolean') {
      this.proposerEnabled = options.proposer_enabled
    } else {
      const flag = (this.userKitOptions.env ?? process.env).SUTRA_NATIVE_PROPOSER
      this.proposerEnabled = flag === 'on' || flag === '1' || flag === 'true'
    }

    const starterTriggers = options.triggers ?? kit.triggers
    const starterWorkflows = options.workflows ?? kit.workflows
    this.workflowsById = new Map(starterWorkflows.map((w) => [w.id, w]))

    for (const t of starterTriggers) {
      try {
        this.router.registerTrigger(t)
      } catch (err) {
        this.onError(err instanceof Error ? err : new Error(String(err)))
      }
    }

    // SPEC v1.2 §4.5(a) — load user-kit Workflows + TriggerSpecs from disk so
    // emergent primitives registered in prior sessions survive daemon restart.
    if (!options.skip_user_kit) {
      try {
        const userWorkflows = listUserKitWorkflows(this.userKitOptions)
        for (const w of userWorkflows) this.workflowsById.set(w.id, w)
        const userTriggers = listUserKitTriggers(this.userKitOptions)
        for (const t of userTriggers) {
          try {
            this.router.registerTrigger(t)
          } catch (err) {
            this.onError(err instanceof Error ? err : new Error(String(err)))
          }
        }
      } catch (err) {
        // user-kit dir might not exist yet — non-fatal.
        this.onError(err instanceof Error ? err : new Error(String(err)))
      }
    }

    // v1.3.0 W2 (codex W2 BLOCKER 3 fold) — boot-time reload of pending
    // execution approvals. Per codex advisory: "the pending approval state
    // must survive restart, but DO NOT auto-resume — founder must explicitly
    // approve". So we only LIST + log; resumption is gated on the founder's
    // next `approve E-<id>` utterance.
    //
    // The list is logged via onError as informational (no dedicated info
    // sink at v1.3.0; codex P1 wave-2 will add structured operator logging).
    try {
      const pendingApprovals = listApprovals(this.userKitOptions, 'pending')
      if (pendingApprovals.length > 0) {
        this.onError(
          new Error(
            `[native-engine boot] ${pendingApprovals.length} pending step approval(s) on disk: ${pendingApprovals
              .map((r) => `${r.execution_id}@step${r.step_index}`)
              .join(', ')}. Founder must explicitly "approve E-<id>" or "reject E-<id> <reason>" to resume.`,
          ),
        )
      }
    } catch (err) {
      // pending-approvals dir might not exist on first boot — non-fatal.
      this.onError(err instanceof Error ? err : new Error(String(err)))
    }
  }

  /** Begin watching the H-Sutra log + processing events. Idempotent. */
  start(): void {
    if (this.started) return
    this.started = true

    this.connector.onEvent((evt) => {
      // v1.2.1 codex P1 fold: chain through turnQueue so events from the
      // synchronous connector are serialized despite handleHSutraEvent now
      // being async (host-LLM dispatch can take seconds).
      this.turnQueue = this.turnQueue.then(() =>
        this.handleHSutraEvent(evt)
          .then(() => undefined)
          .catch((err) => {
            this.onError(err instanceof Error ? err : new Error(String(err)))
          }),
      )
    })

    this.connector.start()
  }

  /** Stop watching + release resources. Idempotent. */
  stop(): void {
    if (!this.started) return
    this.started = false
    this.connector.stop()
  }

  /**
   * v1.2.1: await the queue of in-flight turns from the live connector path.
   * Useful for tests that need to assert state after an async dispatch
   * completes (since `handleHSutraEvent` returns immediately to the listener
   * but the work continues on the queue chain).
   */
  async drain(): Promise<void> {
    await this.turnQueue
  }

  /**
   * Process one founder event end-to-end:
   *   1. Router.route → RoutingDecision
   *   2. Emit routing_decision event → render line
   *   3. If matched: Workflow Engine executes step_graph
   *   4. Emit each workflow/step event → render line
   *
   * Returns the count of EngineEvents emitted (useful for tests + telemetry).
   *
   * v1.2.1: async to support invoke_host_llm dispatch through executeWorkflow.
   */
  async handleHSutraEvent(evt: HSutraEvent): Promise<number> {
    let emitted = 0

    // SPEC v1.2 §4.5(b) + v1.3.0 W2 — approve/reject command parsing PRECEDES
    // routing. Single parser handles BOTH namespaces (codex W2 advisory C):
    //   - P-<sha8> → proposal lifecycle (emergence v1)
    //   - E-<id>   → execution-approval lifecycle (step-level approval gate)
    const text = evt.input_text ?? ''
    const utt = parseApprovalUtterance(text)
    if (utt) {
      if (utt.namespace === 'P') {
        return utt.action === 'approve'
          ? this.applyApproval(utt.id, evt)
          : this.applyRejection(utt.id, utt.reason ?? 'no reason provided', evt)
      }
      // namespace === 'E' — v1.3.0 W2 step-level approval gate
      return utt.action === 'approve'
        ? await this.applyExecutionApproval(utt.id, evt)
        : this.applyExecutionRejection(utt.id, utt.reason ?? 'no reason provided', evt)
    }

    // v1.2.2 N7 (narrowed) — read evt.event_type with founder_input as default;
    // cron path now reachable when scheduler injects { event_type: 'cron', ... }
    const eventType = (evt as { event_type?: 'founder_input' | 'cron' }).event_type ?? 'founder_input'
    const decision = this.router.route({
      event_type: eventType,
      input_text: evt.input_text,
      hsutra: evt,
    })

    const routingEvt: RoutingDecisionEvent = {
      type: 'routing_decision',
      ts_ms: decision.ts_ms,
      turn_id: decision.turn_id,
      mode: decision.mode,
      workflow_id: decision.workflow_id,
      trigger_id: decision.trigger_id,
      attempts_count: decision.attempts.length,
    }
    this.emitEvent(routingEvt, evt)
    emitted++

    if (decision.mode === 'exact' && decision.workflow_id) {
      const wf = this.workflowsById.get(decision.workflow_id)
      if (!wf) {
        this.onError(new Error(`Router matched workflow "${decision.workflow_id}" but it is not loaded`))
        return emitted
      }

      const executionId = `E-${evt.turn_id}-${++this.executionCounter}`
      // v1.2.2 N2 — pass user-kit options so lite-executor writes DP-records
      // for routed executions; cmdRun direct path leaves these unset (codex
      // narrowing — keep direct executions ungated + non-DP).
      // v1.2.2 N4 — also resolve the operating Charter id (via STARTER_WORKFLOW_CHARTER_MAP
      // at v1.2.2; user-kit charter resolution is v1.x scope).
      // v1.3.0 W2 — wire approval_persist callback so a paused step writes
      // a durable ExecutionApprovalRecord to runtime/pending-approvals/.
      const charterId = STARTER_WORKFLOW_CHARTER_MAP.get(wf.id)
      await executeWorkflow({
        workflow: wf,
        execution_id: executionId,
        workflow_run_seq: this.executionCounter,
        user_kit_options_for_dp: this.userKitOptions,
        charter_id: charterId,
        approval_persist: (rec) => {
          try {
            persistApproval(rec, this.userKitOptions)
          } catch (err) {
            // Re-throw — lite-executor turns persist failures into
            // workflow_failed reason=approval_persist_failed:<msg>, which
            // is the right founder-facing surface (no silent drop).
            throw err
          }
        },
        emit: (engineEvt) => {
          this.emitEvent(engineEvt, evt)
          emitted++
        },
      })
      return emitted
    }

    // SPEC v1.2 §4.5(c) — no-match → run pattern detector → persist + emit
    // pattern_proposed events. Founder approves/rejects via subsequent
    // utterance ("approve P-xxx" / "reject P-xxx").
    if (decision.mode === 'no-match' && this.proposerEnabled) {
      try {
        emitted += this.runProposerPass(evt)
      } catch (err) {
        this.onError(err instanceof Error ? err : new Error(String(err)))
      }
    }

    return emitted
  }

  /** SPEC v1.2 §4.5(c) — proposer pass. Returns count of events emitted. */
  private runProposerPass(evt: HSutraEvent): number {
    const detectorOpts: PatternDetectorOptions = {
      hsutra_log_path: this.connector.getLogPath(),
      ...this.patternDetectorOptions,
      user_kit_opts: this.userKitOptions,
    }
    const triggers = this.router.getRegisteredTriggers()
    const patterns = detectPatterns(triggers, detectorOpts)
    let emitted = 0
    for (const p of patterns) {
      const built = buildProposal(p, { now_ms: this.nowMs() })
      try {
        persistProposal(built.entry, this.userKitOptions)
      } catch (err) {
        this.onError(err instanceof Error ? err : new Error(String(err)))
        continue
      }
      const proposedEvt: PatternProposedEvent = {
        type: 'pattern_proposed',
        ts_ms: this.nowMs(),
        pattern_id: p.pattern_id,
        normalized_phrase: p.normalized_phrase,
        evidence_count: p.evidence_count,
        proposed_workflow_id: built.workflow.id,
        proposed_trigger_id: built.trigger.id,
      }
      this.emitEvent(proposedEvt, evt)
      emitted++
    }
    return emitted
  }

  /**
   * SPEC v1.2 §4.5(b) — approve a pending proposal by pattern_id.
   *
   * Codex master P2.4 fold: ordering is now atomic-friendly:
   *   (1) Persist Workflow + TriggerSpec to user-kit (durable; survives restart)
   *   (2) Flip ledger status to 'approved' (audit truth)
   *   (3) Register trigger live + add workflow to in-memory map
   *   (4) Emit DecisionProvenance audit (P1.1 fold) + proposal_approved event
   *
   * On failure at any step the engine logs an error and returns early WITHOUT
   * emitting proposal_approved, so the founder never sees a confirmation that
   * is not backed by ledger state.
   */
  private applyApproval(pattern_id: string, evt: HSutraEvent): number {
    const entry = loadProposal(pattern_id, this.userKitOptions)
    if (!entry || entry.status !== 'pending') {
      this.onError(
        new Error(
          `applyApproval: no pending proposal for "${pattern_id}" (status=${entry?.status ?? 'absent'})`,
        ),
      )
      return 0
    }
    const built = buildProposal(
      {
        pattern_id: entry.pattern_id,
        normalized_phrase: entry.normalized_phrase,
        evidence_count: entry.evidence_count,
        utterance_samples: entry.utterance_samples,
        first_seen_ms: entry.first_seen_ms,
        last_seen_ms: entry.last_seen_ms,
      },
      {
        default_charter_id: entry.proposed_charter_id,
        default_domain_id: entry.proposed_domain_id,
        now_ms: entry.proposed_at_ms,
      },
    )

    // (1) Persist primitives first — these are durable and idempotent.
    try {
      persistWorkflow(built.workflow, this.userKitOptions)
      persistTrigger(built.trigger, this.userKitOptions)
    } catch (err) {
      this.onError(err instanceof Error ? err : new Error(String(err)))
      return 0
    }

    // (2) Flip ledger status — must succeed before live registration so a
    // crash between (1) and (3) leaves the ledger == truth on next boot.
    try {
      updateProposalStatus(
        pattern_id,
        'approved',
        `founder approved via "approve ${pattern_id}"`,
        this.userKitOptions,
        this.nowMs(),
      )
    } catch (err) {
      this.onError(err instanceof Error ? err : new Error(String(err)))
      return 0
    }

    // (3) Register live (in-memory). On failure emit nothing; next boot will
    // pick up the persisted Workflow + TriggerSpec via the user-kit loader.
    try {
      this.router.registerTrigger(built.trigger)
    } catch (err) {
      this.onError(err instanceof Error ? err : new Error(String(err)))
      return 0
    }
    this.workflowsById.set(built.workflow.id, built.workflow)

    // (4) Audit + UI event.
    const decided_at_ms = this.nowMs()
    try {
      appendDecisionProvenanceLog(
        buildEmergenceDecisionProvenance({
          decision_kind: 'APPROVE',
          pattern_id,
          target_workflow_id: built.workflow.id,
          decided_at_ms,
          outcome: `Approved emergent pattern ${pattern_id}; registered ${built.workflow.id} + ${built.trigger.id}`,
        }),
        this.userKitOptions,
      )
    } catch (err) {
      this.onError(err instanceof Error ? err : new Error(String(err)))
    }

    const approvedEvt: ProposalApprovedEvent = {
      type: 'proposal_approved',
      ts_ms: decided_at_ms,
      pattern_id,
      registered_workflow_id: built.workflow.id,
      registered_trigger_id: built.trigger.id,
    }
    this.emitEvent(approvedEvt, evt)
    return 1
  }

  /** SPEC v1.2 §4.5(b) — reject a pending proposal by pattern_id. */
  private applyRejection(pattern_id: string, reason: string, evt: HSutraEvent): number {
    const entry = loadProposal(pattern_id, this.userKitOptions)
    if (!entry || entry.status !== 'pending') {
      this.onError(
        new Error(
          `applyRejection: no pending proposal for "${pattern_id}" (status=${entry?.status ?? 'absent'})`,
        ),
      )
      return 0
    }
    try {
      updateProposalStatus(pattern_id, 'rejected', reason, this.userKitOptions, this.nowMs())
    } catch (err) {
      this.onError(err instanceof Error ? err : new Error(String(err)))
      return 0
    }
    const decided_at_ms = this.nowMs()
    try {
      appendDecisionProvenanceLog(
        buildEmergenceDecisionProvenance({
          decision_kind: 'REJECT',
          pattern_id,
          target_workflow_id: entry.proposed_workflow_id,
          decided_at_ms,
          outcome: `Rejected emergent pattern ${pattern_id}: ${reason}`,
        }),
        this.userKitOptions,
      )
    } catch (err) {
      this.onError(err instanceof Error ? err : new Error(String(err)))
    }
    const rejectedEvt: ProposalRejectedEvent = {
      type: 'proposal_rejected',
      ts_ms: decided_at_ms,
      pattern_id,
      reason,
    }
    this.emitEvent(rejectedEvt, evt)
    return 1
  }

  /**
   * v1.3.0 W2 (codex W2 BLOCKER 3 + advisory C/D fold) — `approve E-<id>`
   * branch.
   *
   * Loads the ExecutionApprovalRecord; on status='pending' flips to
   * 'approved', emits approval_granted, then resumes the workflow run via
   * resumeApproved. On any other status (already-approved, resumed,
   * rejected, terminal) emits approval_already_handled with the original
   * decided_at_ms — never throws (advisory D: stale approve is no-op,
   * distinguishable from "never existed").
   */
  private async applyExecutionApproval(execId: string, evt: HSutraEvent): Promise<number> {
    const rec = loadApproval(execId, this.userKitOptions)
    if (!rec) {
      this.onError(
        new Error(`applyExecutionApproval: no approval record for "${execId}"`),
      )
      return 0
    }
    if (rec.status !== 'pending') {
      const handledEvt: ApprovalAlreadyHandledEvent = {
        type: 'approval_already_handled',
        ts_ms: this.nowMs(),
        execution_id: rec.execution_id,
        workflow_id: rec.workflow_id,
        step_index: rec.step_index,
        originally_decided_at_ms: rec.decided_at_ms ?? rec.created_at_ms,
      }
      this.emitEvent(handledEvt, evt)
      return 1
    }

    // Atomic transition pending → approved (advisory E ordering: ledger
    // first, then runtime resume, then markResumed on completion).
    let updated: ExecutionApprovalRecord
    try {
      updated = updateApprovalStatus(
        execId,
        'approved',
        `founder approved via "approve ${execId}"`,
        this.userKitOptions,
        this.nowMs(),
      )
    } catch (err) {
      this.onError(err instanceof Error ? err : new Error(String(err)))
      return 0
    }

    const grantedEvt: ApprovalGrantedEvent = {
      type: 'approval_granted',
      ts_ms: this.nowMs(),
      execution_id: updated.execution_id,
      workflow_id: updated.workflow_id,
      step_index: updated.step_index,
    }
    this.emitEvent(grantedEvt, evt)
    let emitted = 1

    // Resume the workflow run from the paused step. The lite-executor
    // bypass at isResumeFirstStep skips the requires_approval gate exactly
    // once (for the step that was paused), so the workflow continues.
    try {
      emitted += await this.resumeApproved(updated, evt)
    } catch (err) {
      this.onError(err instanceof Error ? err : new Error(String(err)))
    }
    return emitted
  }

  /**
   * v1.3.0 W2 — `reject E-<id> <reason>` branch.
   *
   * Loads the record; on pending flips to 'rejected', emits approval_denied
   * AND a workflow_failed (reason='approval_denied:<reason>') so the audit
   * trail shows the workflow terminated. On any other status emits
   * approval_already_handled (advisory D).
   */
  private applyExecutionRejection(execId: string, reason: string, evt: HSutraEvent): number {
    const rec = loadApproval(execId, this.userKitOptions)
    if (!rec) {
      this.onError(
        new Error(`applyExecutionRejection: no approval record for "${execId}"`),
      )
      return 0
    }
    if (rec.status !== 'pending') {
      const handledEvt: ApprovalAlreadyHandledEvent = {
        type: 'approval_already_handled',
        ts_ms: this.nowMs(),
        execution_id: rec.execution_id,
        workflow_id: rec.workflow_id,
        step_index: rec.step_index,
        originally_decided_at_ms: rec.decided_at_ms ?? rec.created_at_ms,
      }
      this.emitEvent(handledEvt, evt)
      return 1
    }

    let updated: ExecutionApprovalRecord
    try {
      updated = updateApprovalStatus(
        execId,
        'rejected',
        reason,
        this.userKitOptions,
        this.nowMs(),
      )
    } catch (err) {
      this.onError(err instanceof Error ? err : new Error(String(err)))
      return 0
    }

    const deniedEvt: ApprovalDeniedEvent = {
      type: 'approval_denied',
      ts_ms: this.nowMs(),
      execution_id: updated.execution_id,
      workflow_id: updated.workflow_id,
      step_index: updated.step_index,
      reason,
    }
    this.emitEvent(deniedEvt, evt)
    // Also emit workflow_failed so the audit trail closes the loop.
    const failedEvt: EngineEvent = {
      type: 'workflow_failed',
      ts_ms: this.nowMs(),
      workflow_id: updated.workflow_id,
      execution_id: updated.execution_id,
      reason: `approval_denied:${reason}`,
    }
    this.emitEvent(failedEvt, evt)
    return 2
  }

  /**
   * v1.3.0 W2 — resume an approved-and-paused execution.
   *
   * Looks up the original Workflow by workflow_id, then calls
   * executeWorkflowResume with resume_from_step_index = (paused_step_index - 1)
   * so the gated step IS the first step to run. The lite-executor bypass
   * skips its requires_approval gate exactly once.
   *
   * On completion (success or failure), markResumed flips the ledger entry
   * to 'resumed' so subsequent approve/reject for this execution returns
   * approval_already_handled.
   */
  private async resumeApproved(rec: ExecutionApprovalRecord, evt: HSutraEvent): Promise<number> {
    const wf = this.workflowsById.get(rec.workflow_id)
    if (!wf) {
      this.onError(
        new Error(`resumeApproved: workflow "${rec.workflow_id}" no longer loaded; cannot resume "${rec.execution_id}"`),
      )
      return 0
    }
    let emitted = 0
    const charterId = STARTER_WORKFLOW_CHARTER_MAP.get(wf.id)
    try {
      await executeWorkflowResume({
        workflow: wf,
        execution_id: rec.execution_id,
        workflow_run_seq: this.executionCounter,
        user_kit_options_for_dp: this.userKitOptions,
        charter_id: charterId,
        // Resume MUST skip steps 1..paused_step_index-1 so the gated step
        // (paused_step_index) is the first to execute. The bypass on
        // isResumeFirstStep skips its requires_approval gate.
        resume_from_step_index: rec.step_index - 1,
        // Wire approval_persist again so a SECOND requires_approval=true
        // step downstream can pause the resumed run.
        approval_persist: (r) => {
          persistApproval(r, this.userKitOptions)
        },
        emit: (engineEvt) => {
          this.emitEvent(engineEvt, evt)
          emitted++
        },
      })
    } catch (err) {
      this.onError(err instanceof Error ? err : new Error(String(err)))
    }
    // Ledger transition approved → resumed (terminal sink for the resume side).
    try {
      markResumed(rec.execution_id, this.userKitOptions, this.nowMs())
    } catch (err) {
      this.onError(err instanceof Error ? err : new Error(String(err)))
    }
    return emitted
  }

  /**
   * Public helper: run a single founder turn (no log file round-trip).
   * Used by tests + the v1.1.0 demo path.
   *
   * v1.2.1: async to forward host-LLM dispatch errors / completion ordering
   * from handleHSutraEvent's executeWorkflow await.
   */
  async ingest(evt: HSutraEvent): Promise<number> {
    return this.handleHSutraEvent(evt)
  }

  /** Lookup the Charter that operationalizes a Workflow (v1.1.0 starter map). */
  ownerCharterOf(workflowId: string): string | undefined {
    return STARTER_WORKFLOW_CHARTER_MAP.get(workflowId)
  }

  private emitEvent(event: EngineEvent, hsutra: HSutraEvent | null): void {
    try {
      const line = this.renderer.render(event, { hsutra: hsutra ?? null })
      if (line) this.write(line)
    } catch (err) {
      this.onError(err instanceof Error ? err : new Error(String(err)))
    }
  }
}

/** Convenience builder for the v1.1.0 default engine wiring. */
export function createDefaultEngine(options: NativeEngineOptions = {}): NativeEngine {
  return new NativeEngine(options)
}
