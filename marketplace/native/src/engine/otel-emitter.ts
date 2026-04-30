/**
 * OTelEmitter — M8 Group Z (T-105).
 *
 * Universal evidence-emit gateway. Every consequential decision in the
 * Native runtime — policy allow/deny, skill resolve/miss/cap, step
 * start/complete/fail, failure-policy outcome — flows through this emitter
 * via an `OTelEventRecord`. Emitted records collect into the configured
 * `OTelExporter`; tests use `InMemoryOTelExporter`; production uses an
 * OTLP HTTP exporter (M11 dogfood will wire the real implementation; the
 * shell stub here lets the runtime "emit nowhere" without a hard dep on
 * a live collector).
 *
 * Why a SEPARATE record shape (NOT raw DecisionProvenance):
 * - DecisionProvenance (src/schemas/decision-provenance.ts) pins the strict
 *   D2 §2.1 schema with a closed `decision_kind` enum (DECIDE / EXECUTE /
 *   OVERRIDE / APPROVE / REJECT / DELEGATE / TERMINATE / AUDIT). Group Z
 *   needs a broader event-kind set (POLICY_ALLOW, STEP_START, …) that the
 *   OTel layer carries WITHOUT polluting the constitutional decision shape.
 * - The OTel record is the OBSERVABILITY event; DecisionProvenance is the
 *   CONSTITUTIONAL artifact. Each can reference the other; they are not
 *   the same type.
 * - Group BB (host-LLM provenance) emits decision_kind='HOST_LLM_INVOCATION'
 *   on this same OTelEventRecord shape — the open-ended enum lives here.
 *
 * Replay-determinism (V2 §A11; codex master 2026-04-30 P1.1 fold):
 * - The emitter does NOT generate timestamps inside the constructor — the
 *   caller supplies a stable timestamp (or omits to let the Activity
 *   boundary stamp). The in-memory exporter does no I/O at emit-time.
 * - `trace_id` is supplied by the caller (executor builds it deterministic
 *   per D-NS-26: sha256(workflow.id + run_seq); see step-graph-executor).
 *
 * Spec source:
 *  - holding/plans/native-v1.0/M8-hooks-otel-mcp.md Group Z T-105
 *  - holding/research/2026-04-29-native-d2-decision-provenance-spec.md §2.1
 *  - .enforcement/codex-reviews/2026-04-30-architecture-pivot-rereview.md
 */

import type { AgentIdentity } from '../types/agent-identity.js'

/**
 * Decision kinds emitted on the OTel record.
 *
 * SUPERSET of `DecisionKindSchema` (src/schemas/decision-provenance.ts) —
 * carries both the strict D2 §2.1 set AND Group Z/BB observability kinds.
 * Downstream OTel consumers (collector, dashboards) match against this
 * open-ended discriminator string; the strict D2 kinds remain valid for
 * provenance-cross-referencing the OTel event back to a DP record.
 *
 * Group Z kinds (this milestone):
 *   - POLICY_ALLOW / POLICY_DENY  — policy-dispatcher.ts (T-106)
 *   - SKILL_RESOLVED / SKILL_UNRESOLVED / SKILL_RECURSION_CAP  — skill-invocation.ts (T-107)
 *   - STEP_START / STEP_COMPLETE / STEP_FAIL  — step-graph-executor.ts (T-108)
 *   - FAILURE_POLICY_ROLLBACK / FAILURE_POLICY_ESCALATE / FAILURE_POLICY_PAUSE
 *     / FAILURE_POLICY_ABORT / FAILURE_POLICY_CONTINUE  — failure-policy.ts (T-109)
 *
 * Group BB kinds (next milestone, NOT shipped here):
 *   - HOST_LLM_INVOCATION
 *
 * D2 §2.1 strict kinds (cross-reference; OTel consumers may receive these
 * when a DP record is mirrored to OTel):
 *   - DECIDE / EXECUTE / OVERRIDE / APPROVE / REJECT / DELEGATE / TERMINATE / AUDIT
 */
export type OTelEventKind =
  // Group Z kinds — policy
  | 'POLICY_ALLOW'
  | 'POLICY_DENY'
  // Group Z kinds — skill
  | 'SKILL_RESOLVED'
  | 'SKILL_UNRESOLVED'
  | 'SKILL_RECURSION_CAP'
  // Group Z kinds — step lifecycle
  | 'STEP_START'
  | 'STEP_COMPLETE'
  | 'STEP_FAIL'
  // Group Z kinds — failure-policy outcomes
  | 'FAILURE_POLICY_ROLLBACK'
  | 'FAILURE_POLICY_ESCALATE'
  | 'FAILURE_POLICY_PAUSE'
  | 'FAILURE_POLICY_ABORT'
  | 'FAILURE_POLICY_CONTINUE'
  // Group BB kinds (forward-declared; emission lands at M8 Group BB)
  | 'HOST_LLM_INVOCATION'
  // D2 §2.1 strict-set (cross-reference)
  | 'DECIDE'
  | 'EXECUTE'
  | 'OVERRIDE'
  | 'APPROVE'
  | 'REJECT'
  | 'DELEGATE'
  | 'TERMINATE'
  | 'AUDIT'

/**
 * OTel event record — the canonical wire shape for every M8 evidence-emit.
 *
 * Fields:
 * - decision_kind  — discriminator (OTelEventKind)
 * - trace_id       — deterministic correlation id for one Workflow run
 *                    (D-NS-26: sha256(workflow.id + run_seq), no clock)
 * - span_id        — optional sub-trace id when the executor wants finer
 *                    granularity (e.g. per-step span); omitted for v1.0
 * - workflow_id    — Workflow.id the event belongs to
 * - step_id        — present for STEP_* + skill kinds; integer step id
 * - agent_identity — optional; carried when the caller (executor) supplies it
 * - actor          — optional; authority-holder id (D1 §1) — carried when known
 * - attributes     — open-ended bag for kind-specific fields (policy_id,
 *                    rule_name, sanitized reason, recursion_depth, outputs_hash,
 *                    failure_reason, etc.). Discoverability: each emission
 *                    site documents what it puts in `attributes`.
 *
 * Pure data — no methods. Passed by value through the exporter. Mutability
 * is the consumer's responsibility (ReadonlyArray on the InMemoryOTelExporter
 * intentionally prevents callers from mutating captured records).
 */
export interface OTelEventRecord {
  readonly decision_kind: OTelEventKind
  readonly trace_id: string
  readonly span_id?: string
  readonly workflow_id?: string
  readonly step_id?: number
  readonly agent_identity?: AgentIdentity
  readonly actor?: string
  readonly attributes: Readonly<Record<string, unknown>>
}

/**
 * Exporter contract. The emitter does NOT do I/O directly — exporters do.
 *
 * Two implementations ship at v1.0:
 *  - InMemoryOTelExporter: synchronous in-memory collector for tests.
 *  - NoopOTelExporter: silent default for production callers that do not
 *    yet have a collector wired (M11 dogfood will install a real OTLP HTTP
 *    exporter; this stub keeps the runtime emit-safe in the meantime).
 *
 * Custom exporters (e.g. file-backed for offline replay) implement this
 * interface and pass to `new OTelEmitter(exporter)`.
 */
export interface OTelExporter {
  /**
   * Export a batch of records. Implementations MUST NOT throw on a
   * well-formed record — exporter failures are observability concerns,
   * not Workflow-execution concerns. Async return so future HTTP exporters
   * can flush asynchronously without changing the call site.
   */
  export(records: ReadonlyArray<OTelEventRecord>): Promise<void>
  /**
   * Flush any buffered records. In-memory exporters no-op; HTTP exporters
   * use this to drain before shutdown.
   */
  flush(): Promise<void>
}

/**
 * In-memory exporter for tests. Collects records into a public array; resets
 * on demand. Synchronous semantics under the async API — Promise.resolve()-only.
 *
 * Use:
 *   const exporter = new InMemoryOTelExporter()
 *   const emitter = new OTelEmitter(exporter)
 *   await emitter.emit({ decision_kind: 'POLICY_ALLOW', trace_id: 'abc', attributes: {} })
 *   expect(exporter.records).toHaveLength(1)
 */
export class InMemoryOTelExporter implements OTelExporter {
  /**
   * Collected records, in insertion order. Mutable internally so the
   * emitter can append; consumers should treat as read-only — the field
   * is `readonly` from the outside (TS prevents reassignment but not
   * mutation). Tests assert against this directly.
   */
  public readonly records: OTelEventRecord[] = []

  /**
   * Append the provided records. Pure synchronous append wrapped in a
   * resolved Promise — the async signature is for API parity with
   * production exporters that flush over the network.
   */
  async export(records: ReadonlyArray<OTelEventRecord>): Promise<void> {
    for (const r of records) this.records.push(r)
  }

  /** No-op — in-memory exporter has no buffer. */
  async flush(): Promise<void> {
    // intentional no-op
  }

  /**
   * Test convenience: clear collected records between cases. Mutates the
   * `records` array in-place (callers holding a reference will see the
   * mutation; this is intentional for the test seam).
   */
  reset(): void {
    this.records.length = 0
  }
}

/**
 * No-op exporter for production callers without a wired collector. Drops
 * every record on the floor. Discovers itself via the OTelEmitter default
 * factory — `OTelEmitter.disabled()` returns an emitter wired to this
 * exporter so callers can stay branch-free at the emit site.
 */
export class NoopOTelExporter implements OTelExporter {
  async export(_records: ReadonlyArray<OTelEventRecord>): Promise<void> {
    // intentional no-op
  }
  async flush(): Promise<void> {
    // intentional no-op
  }
}

/**
 * OTLP HTTP exporter — minimal stub.
 *
 * v1.0 ships the SHELL only: the constructor accepts an endpoint URL but
 * the implementation does NOT yet POST. M11 dogfood will wire a real
 * OTLP HTTP exporter via `@opentelemetry/sdk-node` (already in deps).
 *
 * Why ship a stub now: the production code-path can already call
 * `new OTLPHttpExporter(url)` so wiring is a one-line config change at
 * M11 — no executor refactor at activation time. Until then, the stub
 * silently no-ops (records are discarded) so misconfiguration cannot
 * accidentally break execution.
 *
 * Codex master review note: the stub is INTENTIONALLY non-functional. A
 * lying "I sent it" exporter would silently swallow audit data. The
 * documented contract here is "drops records; M11 will replace" — the
 * runtime never claims to have exported.
 */
export class OTLPHttpExporter implements OTelExporter {
  constructor(public readonly endpoint: string) {
    if (typeof endpoint !== 'string' || endpoint.length === 0) {
      throw new TypeError('OTLPHttpExporter: endpoint must be a non-empty string')
    }
  }

  async export(_records: ReadonlyArray<OTelEventRecord>): Promise<void> {
    // M11 dogfood will replace with a real OTLP HTTP POST. Until then,
    // drop the records — observability is a non-blocking concern.
  }

  async flush(): Promise<void> {
    // M11 dogfood will replace with a buffer drain. Until then, no-op.
  }
}

/**
 * The OTel emission gateway. Single method `emit(record)` enqueues to the
 * configured exporter; `flush()` delegates to the exporter for shutdown
 * draining.
 *
 * Construction:
 *   new OTelEmitter(new InMemoryOTelExporter())   // tests
 *   new OTelEmitter(new NoopOTelExporter())       // production stub
 *   OTelEmitter.disabled()                         // sugar for NoopOTelExporter
 */
export class OTelEmitter {
  constructor(private readonly exporter: OTelExporter) {
    if (typeof exporter !== 'object' || exporter === null) {
      throw new TypeError('OTelEmitter: exporter must be an OTelExporter instance')
    }
    if (typeof exporter.export !== 'function' || typeof exporter.flush !== 'function') {
      throw new TypeError(
        'OTelEmitter: exporter must implement export(records) and flush()',
      )
    }
  }

  /**
   * Emit one OTel event. Records are forwarded to the exporter as a
   * single-element batch — this keeps the wire shape consistent with
   * future batched-emit codepaths without changing the emit() call site.
   *
   * Idempotent for in-memory exporters; HTTP exporters MAY dedupe at the
   * collector but that is an exporter concern, not the emitter's.
   */
  async emit(record: OTelEventRecord): Promise<void> {
    await this.exporter.export([record])
  }

  /** Drain any buffered records — called at shutdown / between tests. */
  async flush(): Promise<void> {
    await this.exporter.flush()
  }

  /**
   * Sugar: build an emitter wired to a NoopOTelExporter. Use as the default
   * when no observability collector is configured — keeps emit-call-sites
   * branch-free instead of forcing every call site to write
   * `if (emitter) emitter.emit(...)`.
   */
  static disabled(): OTelEmitter {
    return new OTelEmitter(new NoopOTelExporter())
  }
}
