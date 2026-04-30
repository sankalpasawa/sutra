/**
 * TenantIsolation — M9 Group FF (T-151).
 *
 * Runtime engine that enforces cross-tenant operation safety per D1 P-B8 +
 * D4 §3 (the F-6 forbidden coupling). The engine is a READ-ONLY accessor of
 * the existing `delegates_to: Tenant→Tenant` typed edges already shipped in
 * `src/types/edges.ts` (and already consumed by `l4-terminal-check.ts`
 * `f6Predicate` at lines 481/494/637 — see codex M9 pre-dispatch P1.2 fold).
 *
 * Why an engine and not just a predicate:
 * - L4 terminal-check `f6Predicate` runs at TERMINAL-CHECK time (after a
 *   Workflow has already executed end-to-end) — too late to abort an
 *   in-flight cross-tenant step. The runtime needs an enforcement point at
 *   STEP-DISPATCH time so a violating step never runs.
 * - The step-graph-executor (M5) calls `assertCrossTenantAllowed` from
 *   inside the per-step loop (M9 T-153 wiring). When the source tenant
 *   differs from the target tenant AND no `delegates_to` edge grants the
 *   operation, the call THROWS `CrossTenantBoundaryError`. The executor
 *   catches the throw and synthesizes a step failure with errMsg
 *   `cross_tenant_boundary:<source>->>:<target>:<operation>` so M5
 *   failure-policy routes the violation through the same 5-set
 *   (rollback / escalate / pause / abort / continue) as any other step
 *   failure.
 *
 * Why runtime-DERIVED, not annotation-driven (codex M9 re-review P1 fold):
 * - The previous proposal had a `WorkflowStep.crosses_tenant?: boolean`
 *   advisory hint; producers could omit it and skip enforcement. That was
 *   a bypass loophole. The fix: cross-tenant detection is RUNTIME-DERIVED
 *   in step-graph-executor by comparing `Execution.tenant_context.tenant_id`
 *   against each step's resolved tenant. There is NO opt-out flag.
 *
 * Why no new schema (codex M9 pre-dispatch P1.2 fold):
 * - D4 already defines `delegates_to: Tenant→Tenant` as a typed edge
 *   (src/types/edges.ts:71-83). The engine reads those edges; it does NOT
 *   define a parallel `TenantDelegation` shape. Forking the composition
 *   model right before GA was the explicit codex rejection.
 *
 * Spec source:
 *   - holding/plans/native-v1.0/M9-e2e-vinit.md Group FF T-150..T-155
 *   - .enforcement/codex-reviews/2026-04-30-m9-pre-dispatch.md P1.2 + re-review P1
 *   - holding/research/2026-04-29-native-d4-primitives-composition-spec.md §3
 *   - holding/research/2026-04-29-native-d1-authority-map.md (P-B8 + P-B9)
 */

import type { DelegatesToEdge } from '../types/edges.js'

/**
 * Thrown by `assertCrossTenantAllowed` when the runtime detects a
 * cross-tenant operation that is NOT covered by a `delegates_to` edge.
 *
 * Plain Error subclass with `name='CrossTenantBoundaryError'` so
 * `instanceof` works across the test suite. Mirrors the
 * `BuiltinNotAllowedError`, `TurnNotStartedError`, `OPAUnavailableError`,
 * `HostUnavailableError` patterns used elsewhere in the engine — no
 * central errors module in this codebase.
 *
 * Carries the load-bearing fields (source/target/operation) so the
 * step-graph-executor can synthesize a step-failure message with the
 * canonical envelope `cross_tenant_boundary:<source>:<target>:<operation>`
 * that downstream tooling can lift from `failure_reason` without parsing
 * free-form text.
 */
export class CrossTenantBoundaryError extends Error {
  readonly source_tenant: string
  readonly target_tenant: string
  readonly operation: string

  constructor(input: {
    source_tenant: string
    target_tenant: string
    operation: string
  }) {
    super(
      `CrossTenantBoundaryError: ${input.source_tenant} -> ${input.target_tenant} (${input.operation}) — no delegates_to edge granting the operation`,
    )
    this.name = 'CrossTenantBoundaryError'
    this.source_tenant = input.source_tenant
    this.target_tenant = input.target_tenant
    this.operation = input.operation
  }
}

/**
 * Input shape for `assertCrossTenantAllowed`. Carries the source +
 * target tenants, a non-empty operation tag (used in the error message
 * + observability), and the registered `delegates_to_edges` set the
 * runtime is operating against (typically threaded in from the
 * `terminalCheckProbe` context per the M5 boundary).
 *
 * Why an `approvals?` slot (optional, currently unused at v1.0):
 * - D1 P-B9 references multi-party approval semantics (D5 OQ-D5-4) that
 *   may extend cross-tenant grants beyond the simple "edge exists" check.
 *   The slot is reserved on the API so v1.x can layer approval semantics
 *   in without changing the call signature; v1.0 ignores it (per the
 *   M9 plan "Per-multi-party Approval quorum — v1.x" deferral).
 */
export interface AssertCrossTenantAllowedInput {
  /** Source tenant id (the operating context). Non-empty `T-...` pattern. */
  source_tenant: string
  /** Target tenant id (the resource being touched). Non-empty `T-...` pattern. */
  target_tenant: string
  /** Operation tag for error message + observability (non-empty). */
  operation: string
  /** Registered D4 §3 typed edges; engine reads as-is. */
  delegates_to_edges: ReadonlyArray<DelegatesToEdge>
  /**
   * v1.0 reserved — will carry multi-party approval tokens in v1.x
   * (D5 OQ-D5-4). At v1.0 this is ignored; supplying it does not change
   * the decision.
   */
  approvals?: ReadonlyArray<unknown>
}

/**
 * The TenantIsolation engine. Stateless; instantiate one per runtime if
 * you want to inject a custom edge source, but the v1.0 API surface is a
 * single static method that takes the edge set as input.
 *
 * Construction-free use:
 *   TenantIsolation.assertCrossTenantAllowed({
 *     source_tenant: 'T-asawa', target_tenant: 'T-paisa',
 *     operation: 'invoke_skill', delegates_to_edges: edges,
 *   })
 *
 * (Method is static + the class also exists in instance form so dependency
 * injection at integration-test time stays uniform with the rest of the
 * engine surface.)
 */
export class TenantIsolation {
  /**
   * Assert that a cross-tenant operation from `source_tenant` to
   * `target_tenant` is permitted by the supplied `delegates_to_edges`.
   *
   * Decision logic (read-only against existing D4 edge surface):
   *   1. If source === target: not a cross-tenant op; return immediately
   *      (no error, no edge required).
   *   2. Else: scan `delegates_to_edges` for an edge with
   *      `kind='delegates_to'`, `source=source_tenant`, `target=target_tenant`.
   *      If found: return; else THROW `CrossTenantBoundaryError`.
   *
   * Edge-set non-array: treated as "no edges" (defensive — a producer
   * supplying garbage gets the same deny as supplying an empty set).
   *
   * Mirrors `f6Predicate` (l4-terminal-check.ts:494) decision but is
   * RUNTIME (throws) where f6 is TERMINAL (returns boolean violation).
   */
  static assertCrossTenantAllowed(input: AssertCrossTenantAllowedInput): void {
    if (typeof input !== 'object' || input === null) {
      throw new TypeError(
        'TenantIsolation.assertCrossTenantAllowed: input must be a non-null object',
      )
    }
    const { source_tenant, target_tenant, operation, delegates_to_edges } = input
    if (typeof source_tenant !== 'string' || source_tenant.length === 0) {
      throw new TypeError(
        'TenantIsolation.assertCrossTenantAllowed: source_tenant must be a non-empty string',
      )
    }
    if (typeof target_tenant !== 'string' || target_tenant.length === 0) {
      throw new TypeError(
        'TenantIsolation.assertCrossTenantAllowed: target_tenant must be a non-empty string',
      )
    }
    if (typeof operation !== 'string' || operation.length === 0) {
      throw new TypeError(
        'TenantIsolation.assertCrossTenantAllowed: operation must be a non-empty string',
      )
    }

    // (1) same-tenant op → trivially allowed; no edge required.
    if (source_tenant === target_tenant) return

    // (2) cross-tenant op → require a delegates_to edge.
    if (Array.isArray(delegates_to_edges)) {
      for (const e of delegates_to_edges) {
        if (
          typeof e === 'object' &&
          e !== null &&
          e.kind === 'delegates_to' &&
          e.source === source_tenant &&
          e.target === target_tenant
        ) {
          return
        }
      }
    }

    throw new CrossTenantBoundaryError({
      source_tenant,
      target_tenant,
      operation,
    })
  }

  /**
   * Instance-form mirror — same decision, dispatched as `iso.assert(...)`.
   * Useful when an integration test injects a TenantIsolation instance
   * into a higher-level container that resolves engines by reference.
   */
  assertCrossTenantAllowed(input: AssertCrossTenantAllowedInput): void {
    TenantIsolation.assertCrossTenantAllowed(input)
  }
}
