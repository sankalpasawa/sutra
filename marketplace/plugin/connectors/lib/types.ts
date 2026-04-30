/**
 * Sutra Connectors — Shared types
 * Frozen by LLD §2.1 (holding/research/2026-04-30-connectors-LLD.md)
 * Diverging from these requires charter amendment + codex re-review.
 */

export type Tier = 'T1' | 'T2' | 'T3' | 'T4';

export type Depth = 1 | 2 | 3 | 4 | 5;

/** Format: '<connector>:<action>:<resource>?'  e.g. 'slack:read-channel:#dayflow-eng' */
export type Capability = string;

export interface ConnectorCallContext {
  readonly clientId: string;
  readonly tier: Tier;
  readonly depth: Depth;
  readonly capability: Capability;
  readonly args: Readonly<Record<string, unknown>>;
  readonly ts: number;
  readonly sessionId: string;
  readonly approvalToken?: string;
  /**
   * Native-compat (Mode B) fields — optional in legacy mode, REQUIRED when
   * the Router is constructed with mode='native-compat' (M1.3).
   *  - idempotency_key: caller-supplied unique id; backends/rev-hooks dedupe.
   *  - signal:          AbortSignal threaded through Router → adapter →
   *                     backend.fetch() so cancellation propagates to network.
   *  - event_id:        opaque trace id for cross-system correlation.
   * Adding these as optional keeps Mode A (legacy) call sites untouched.
   */
  readonly idempotency_key?: string;
  readonly signal?: AbortSignal;
  readonly event_id?: string;
}

export interface ConnectorCallResult {
  readonly outcome: 'allowed' | 'blocked' | 'approved-after-gate' | 'error';
  readonly reason?: string;
  readonly value?: unknown;
  readonly approvalRequired?: boolean;
  readonly approvalToken?: string;
  readonly errorClass?: string;
}

export interface FounderApprovalRequest {
  readonly callContext: ConnectorCallContext;
  readonly summary: string;
  readonly riskLevel: 'low' | 'medium' | 'high';
}

export interface CapabilityDecl {
  readonly id: Capability;
  readonly action: 'read' | 'write' | 'admin';
  readonly resourcePattern: string;
  readonly minDepth: Depth;
  readonly approvalRequired: boolean;
  readonly costEstimate: 'free' | 'cents' | 'dollars';
}

export interface ConnectorManifest {
  readonly schemaVersion: '1';
  readonly name: string;
  readonly description: string;
  readonly composioToolkit: string;
  readonly capabilities: ReadonlyArray<CapabilityDecl>;
  readonly tierAccess: Readonly<Record<Tier, ReadonlyArray<Capability>>>;
  readonly auditFields: ReadonlyArray<string>;
  readonly redactPaths: ReadonlyArray<string>;
  /**
   * Optional integration descriptor (M1.13). When present, declares which
   * adapter the Router should dispatch to. Absence = legacy/Composio default.
   *  - kind: 'composio' (catalog) or 'direct' (first-party backend)
   *  - target: opaque identifier (e.g. 'slack-direct', 'gmail-direct')
   */
  readonly integration?: {
    readonly kind: 'composio' | 'direct';
    readonly target: string;
  };
}

export interface CapabilityCheckResult {
  readonly granted: boolean;
  readonly reason:
    | 'tier-allowed'
    | 'tier-denied'
    | 'pattern-mismatch'
    | 'depth-floor'
    | 'unknown-capability';
}

export interface PolicyDecision {
  readonly verdict: 'allow' | 'block' | 'require-approval';
  readonly reason: string;
  readonly capabilityCheck: CapabilityCheckResult;
  readonly depthCheck: { readonly allowed: boolean; readonly minRequired: Depth };
  readonly fleetPolicyCheck: { readonly allowed: boolean; readonly activeFreeze?: string };
}

export interface AuditEvent {
  readonly ts: number;
  readonly clientId: string;
  readonly tier: Tier;
  readonly depth: Depth;
  readonly capability: Capability;
  readonly outcome: 'allowed' | 'blocked' | 'approved-after-gate' | 'error';
  readonly reason?: string;
  readonly approvalToken?: string;
  readonly sessionId: string;
  readonly redactedArgsHash: string;
  readonly errorClass?: string;
}

export interface AuditSinkConfig {
  readonly path: string;
  readonly redactPaths: ReadonlyArray<string>;
}

export interface FleetPolicy {
  readonly version: string;
  readonly lastUpdated: number;
  readonly freezes: ReadonlyArray<FreezeRule>;
  /**
   * @deprecated v0 — documented in CHARTER §7 but NOT implemented.
   *
   * Per codex iter-11 review (P2 #5), tierOverrides is deferred to v1.x via
   * TODO-CONNECTORS-004. The field is kept optional only to preserve existing
   * test fixtures; runtime policy evaluation does not consult it. Setting a
   * value here has no effect.
   *
   * Remove or implement in v1.x; until then, all tier access flows through
   * `ConnectorManifest.tierAccess`.
   */
  readonly tierOverrides?: Readonly<Partial<Record<Tier, ReadonlyArray<Capability>>>>;
}

export interface FreezeRule {
  readonly id: string;
  readonly capabilityPattern: string;
  readonly tierScope: ReadonlyArray<Tier>;
  readonly until?: number;
  readonly reason: string;
}

export interface FleetPolicySource {
  load(): Promise<FleetPolicy>;
  watch(onChange: (p: FleetPolicy) => void): () => void;
}

/**
 * Narrow Composio surface — no plan/discover/workbench/session-memory.
 *
 * `executeTool` accepts an OPTIONAL fourth `opts` arg with `{ signal? }`
 * (M1.4). Existing call sites that pass three args remain valid: the parameter
 * is optional and undefined-safe (fetch / SDK calls ignore an undefined
 * signal). Mode-B Router threads `ctx.signal` here so cancellation propagates
 * end-to-end (Router → adapter → backend.fetch).
 */
export interface ComposioClient {
  authenticate(toolkit: string, oauthToken: string): Promise<void>;
  executeTool(
    toolkit: string,
    tool: string,
    args: Record<string, unknown>,
    opts?: { signal?: AbortSignal },
  ): Promise<unknown>;
  isAuthenticated(toolkit: string): Promise<boolean>;
}
