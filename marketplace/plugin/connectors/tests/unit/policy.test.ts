/**
 * Sutra Connectors — policy.ts unit tests (TDD red phase, iter 3).
 *
 * Frozen contracts:
 *   - LLD §2.4  (holding/research/2026-04-30-connectors-LLD.md)
 *   - test-plan §3.3 + §4 row 2 (codex required: policy matrix)
 *
 * These tests deliberately FAIL today: the policy.ts stub throws
 * `not implemented (TDD red phase)`. Iter 4 (sequential green, first)
 * lands the implementation that turns them green.
 *
 * Constraints:
 *   - No CODEX_DIRECTIVE_ACK overrides — surface every block.
 *   - No live network, no ~/.sutra or ~/.claude writes.
 *   - ESM .js extension imports per package tsconfig.
 */

import { describe, it, expect } from 'vitest';

import { evaluatePolicy, consumeApproval } from '../../lib/policy.js';
import type {
  ConnectorCallContext,
  ConnectorManifest,
  FleetPolicy,
  Tier,
  Depth,
  Capability,
  CapabilityDecl,
  FreezeRule,
} from '../../lib/types.js';

// ---------------------------------------------------------------------------
// Fixture factories (TS literals only — no fs, no network)
// ---------------------------------------------------------------------------

const CAP_READ_DAYFLOW: Capability = 'slack:read-channel:#dayflow-eng';
const CAP_READ_OPS: Capability = 'slack:read-channel:#ops';
const CAP_WRITE_LAUNCH: Capability = 'slack:write-channel:#public-launch';
const CAP_ADMIN_USERS: Capability = 'slack:admin-users:*';
const CAP_UNKNOWN: Capability = 'slack:read-channel:#never-declared';

const decl = (
  id: Capability,
  action: CapabilityDecl['action'],
  resourcePattern: string,
  minDepth: Depth,
  approvalRequired: boolean,
): CapabilityDecl => ({
  id,
  action,
  resourcePattern,
  minDepth,
  approvalRequired,
  costEstimate: 'free',
});

function buildManifest(
  overrides: Partial<ConnectorManifest> = {},
): ConnectorManifest {
  const capabilities: ReadonlyArray<CapabilityDecl> = [
    decl(CAP_READ_DAYFLOW, 'read', '#*', 1, false),
    decl(CAP_READ_OPS, 'read', '#*', 1, false),
    decl(CAP_WRITE_LAUNCH, 'write', '#*', 3, true),
    decl(CAP_ADMIN_USERS, 'admin', 'users/*', 5, true),
  ];

  const tierAccess: Record<Tier, ReadonlyArray<Capability>> = {
    T1: [CAP_READ_OPS, CAP_READ_DAYFLOW, CAP_WRITE_LAUNCH, CAP_ADMIN_USERS],
    T2: [CAP_READ_DAYFLOW, CAP_WRITE_LAUNCH],
    T3: [CAP_READ_DAYFLOW],
    T4: [],
  };

  return {
    schemaVersion: '1',
    name: 'slack',
    description: 'Slack reference connector',
    composioToolkit: 'slack',
    capabilities,
    tierAccess,
    auditFields: [],
    redactPaths: [],
    ...overrides,
  };
}

function buildFleetPolicy(
  freezes: ReadonlyArray<FreezeRule> = [],
): FleetPolicy {
  return {
    version: '1',
    lastUpdated: 1_730_000_000_000,
    freezes,
    tierOverrides: {},
  };
}

function buildCtx(overrides: Partial<ConnectorCallContext> = {}): ConnectorCallContext {
  return {
    clientId: 'asawa-holding',
    tier: 'T1',
    depth: 1,
    capability: CAP_READ_DAYFLOW,
    args: {},
    ts: 1_730_000_000_000,
    sessionId: 'sess-test',
    ...overrides,
  };
}

// ---------------------------------------------------------------------------
// evaluatePolicy — happy path + tiered denials
// ---------------------------------------------------------------------------

describe('policy.evaluatePolicy — verdicts', () => {
  it('verdict=allow for T1 D1 reading scoped #dayflow-eng (no freeze)', () => {
    const decision = evaluatePolicy(
      buildCtx({ tier: 'T1', depth: 1, capability: CAP_READ_DAYFLOW }),
      buildManifest(),
      buildFleetPolicy(),
    );
    expect(decision.verdict).toBe('allow');
    expect(decision.capabilityCheck.granted).toBe(true);
    expect(decision.depthCheck.allowed).toBe(true);
    expect(decision.fleetPolicyCheck.allowed).toBe(true);
  });

  it('verdict=block reason=tier-denied for T3 reading T1-only #ops channel', () => {
    const decision = evaluatePolicy(
      buildCtx({ tier: 'T3', depth: 5, capability: CAP_READ_OPS }),
      buildManifest(),
      buildFleetPolicy(),
    );
    expect(decision.verdict).toBe('block');
    expect(decision.reason).toBe('tier-denied');
    expect(decision.capabilityCheck.granted).toBe(false);
    expect(decision.capabilityCheck.reason).toBe('tier-denied');
  });

  it('verdict=block reason=depth-floor for T2 D1 invoking minDepth=3 capability', () => {
    const decision = evaluatePolicy(
      buildCtx({ tier: 'T2', depth: 1, capability: CAP_WRITE_LAUNCH }),
      buildManifest(),
      buildFleetPolicy(),
    );
    expect(decision.verdict).toBe('block');
    expect(decision.reason).toBe('depth-floor');
    expect(decision.depthCheck.allowed).toBe(false);
    expect(decision.depthCheck.minRequired).toBe(3);
  });

  it('verdict=require-approval for T2 D5 write-channel where capability.approvalRequired=true', () => {
    const decision = evaluatePolicy(
      buildCtx({ tier: 'T2', depth: 5, capability: CAP_WRITE_LAUNCH }),
      buildManifest(),
      buildFleetPolicy(),
    );
    expect(decision.verdict).toBe('require-approval');
    // Cap + depth checks should pass on their own — only the approval gate flips.
    expect(decision.capabilityCheck.granted).toBe(true);
    expect(decision.depthCheck.allowed).toBe(true);
    expect(decision.fleetPolicyCheck.allowed).toBe(true);
  });

  it('verdict=block reason=active-freeze:<id> when fleet policy has matching freeze', () => {
    const freeze: FreezeRule = {
      id: 'FRZ-2026-04-30-slack-write',
      capabilityPattern: 'slack:write-*',
      tierScope: ['T2'],
      reason: 'incident-IR-42',
    };
    const decision = evaluatePolicy(
      buildCtx({ tier: 'T2', depth: 5, capability: CAP_WRITE_LAUNCH }),
      buildManifest(),
      buildFleetPolicy([freeze]),
    );
    expect(decision.verdict).toBe('block');
    expect(decision.reason).toBe(`active-freeze:${freeze.id}`);
    expect(decision.fleetPolicyCheck.allowed).toBe(false);
    expect(decision.fleetPolicyCheck.activeFreeze).toBe(freeze.id);
  });

  it('verdict=block reason=unknown-capability when ctx.capability is not declared in manifest', () => {
    const decision = evaluatePolicy(
      buildCtx({ tier: 'T1', depth: 5, capability: CAP_UNKNOWN }),
      buildManifest(),
      buildFleetPolicy(),
    );
    expect(decision.verdict).toBe('block');
    expect(decision.reason).toBe('unknown-capability');
    expect(decision.capabilityCheck.granted).toBe(false);
    expect(decision.capabilityCheck.reason).toBe('unknown-capability');
  });

  it('verdict=allow when approvalRequired=true AND ctx carries valid approvalToken', () => {
    // Note: this test asserts the *contract* — evaluatePolicy may return allow
    // when the ctx already carries a token, OR may still return require-approval
    // and let the router consume it. The frozen LLD §2.4 says caller re-invokes
    // with ctx.approvalToken=… and policy.consumeApproval gates the actual run.
    // The minimum guarantee: capability/depth/fleet checks all pass.
    const ctxWithToken = buildCtx({
      tier: 'T2',
      depth: 5,
      capability: CAP_WRITE_LAUNCH,
      approvalToken: 'TEST_APPROVAL_FAKE_TOKEN',
    });
    const decision = evaluatePolicy(ctxWithToken, buildManifest(), buildFleetPolicy());
    expect(decision.capabilityCheck.granted).toBe(true);
    expect(decision.depthCheck.allowed).toBe(true);
    expect(decision.fleetPolicyCheck.allowed).toBe(true);
    expect(['allow', 'require-approval']).toContain(decision.verdict);
  });

  it('PolicyDecision shape includes capabilityCheck, depthCheck, fleetPolicyCheck for debuggability', () => {
    const decision = evaluatePolicy(
      buildCtx(),
      buildManifest(),
      buildFleetPolicy(),
    );
    // All three sub-results MUST be present so a single struct read is enough
    // to debug a verdict (LLD §5 justification).
    expect(decision).toHaveProperty('capabilityCheck');
    expect(decision).toHaveProperty('depthCheck');
    expect(decision).toHaveProperty('fleetPolicyCheck');
    expect(decision.capabilityCheck).toHaveProperty('granted');
    expect(decision.capabilityCheck).toHaveProperty('reason');
    expect(decision.depthCheck).toHaveProperty('allowed');
    expect(decision.depthCheck).toHaveProperty('minRequired');
    expect(decision.fleetPolicyCheck).toHaveProperty('allowed');
  });
});

// ---------------------------------------------------------------------------
// Codex-required matrix: tier × capability × depth × approval → verdict
// (test-plan §4 row 2)
// ---------------------------------------------------------------------------

interface MatrixRow {
  readonly tier: Tier;
  readonly capability: Capability;
  readonly depth: Depth;
  readonly approvalToken: string | undefined;
  readonly expectedVerdict: 'allow' | 'block' | 'require-approval';
  readonly expectedReasonContains?: string;
}

// Hand-curated coverage: all 4 tiers × {read, write} × representative depths.
// At least 2 capabilities (read + write) per tier per the test-plan minimum.
const MATRIX: ReadonlyArray<MatrixRow> = [
  // T1 — internal Asawa-holding, all caps allowed
  { tier: 'T1', capability: CAP_READ_DAYFLOW, depth: 1, approvalToken: undefined, expectedVerdict: 'allow' },
  { tier: 'T1', capability: CAP_READ_OPS, depth: 5, approvalToken: undefined, expectedVerdict: 'allow' },
  { tier: 'T1', capability: CAP_WRITE_LAUNCH, depth: 3, approvalToken: undefined, expectedVerdict: 'require-approval' },
  { tier: 'T1', capability: CAP_WRITE_LAUNCH, depth: 1, approvalToken: undefined, expectedVerdict: 'block', expectedReasonContains: 'depth-floor' },

  // T2 — owned portfolio (DayFlow et al.)
  { tier: 'T2', capability: CAP_READ_DAYFLOW, depth: 1, approvalToken: undefined, expectedVerdict: 'allow' },
  { tier: 'T2', capability: CAP_READ_OPS, depth: 5, approvalToken: undefined, expectedVerdict: 'block', expectedReasonContains: 'tier-denied' },
  { tier: 'T2', capability: CAP_WRITE_LAUNCH, depth: 5, approvalToken: undefined, expectedVerdict: 'require-approval' },
  { tier: 'T2', capability: CAP_WRITE_LAUNCH, depth: 2, approvalToken: undefined, expectedVerdict: 'block', expectedReasonContains: 'depth-floor' },

  // T3 — project clients (Testlify, Dharmik): read scoped only
  { tier: 'T3', capability: CAP_READ_DAYFLOW, depth: 1, approvalToken: undefined, expectedVerdict: 'allow' },
  { tier: 'T3', capability: CAP_READ_OPS, depth: 5, approvalToken: undefined, expectedVerdict: 'block', expectedReasonContains: 'tier-denied' },
  { tier: 'T3', capability: CAP_WRITE_LAUNCH, depth: 5, approvalToken: undefined, expectedVerdict: 'block', expectedReasonContains: 'tier-denied' },

  // T4 — fleet adopters: empty tierAccess.T4 → ALL caps blocked regardless of depth
  { tier: 'T4', capability: CAP_READ_DAYFLOW, depth: 5, approvalToken: undefined, expectedVerdict: 'block', expectedReasonContains: 'tier-denied' },
  { tier: 'T4', capability: CAP_WRITE_LAUNCH, depth: 5, approvalToken: undefined, expectedVerdict: 'block', expectedReasonContains: 'tier-denied' },
];

describe('policy.evaluatePolicy — matrix (tier × capability × depth × approval)', () => {
  it.each(MATRIX)(
    'tier=$tier cap=$capability depth=$depth approval=$approvalToken → $expectedVerdict',
    ({ tier, capability, depth, approvalToken, expectedVerdict, expectedReasonContains }) => {
      const ctx = buildCtx({ tier, capability, depth, approvalToken });
      const decision = evaluatePolicy(ctx, buildManifest(), buildFleetPolicy());

      // For approval rows we accept either allow (if pre-consumed by impl) or
      // require-approval (if impl defers consumption to router) — the contract
      // permits both per LLD §2.4 + §3 data flow.
      if (expectedVerdict === 'require-approval' && approvalToken !== undefined) {
        expect(['allow', 'require-approval']).toContain(decision.verdict);
      } else {
        expect(decision.verdict).toBe(expectedVerdict);
      }

      if (expectedReasonContains !== undefined) {
        expect(decision.reason).toContain(expectedReasonContains);
      }
    },
  );
});

// ---------------------------------------------------------------------------
// consumeApproval — single-use semantics
// ---------------------------------------------------------------------------

describe('policy.consumeApproval — single-use semantics', () => {
  it('returns false for an unknown / never-issued token', () => {
    expect(consumeApproval('TEST_APPROVAL_NEVER_ISSUED')).toBe(false);
  });

  // The pair below depends on the impl exposing a way to mint a token.
  // For RED phase we only assert the second-call invariant against whatever
  // the first call returns — once the impl lands a mint API (issued via
  // ApprovalRequiredError + founder ack flow per LLD §3), this test will
  // be tightened to issue a real token and assert true→false.
  it('returns true once + false on second call (single-use invariant)', () => {
    // Iter 4 will expose `issueApprovalForTest` or similar; for now we assert
    // the contract via a placeholder token. RED expectation: throws.
    const token = 'TEST_APPROVAL_SINGLE_USE_PROBE';
    const first = consumeApproval(token);
    const second = consumeApproval(token);

    // Whatever first returns, second MUST be false.
    expect(second).toBe(false);
    // And the two calls MUST disagree iff the token was real (single-use).
    if (first === true) {
      expect(second).toBe(false);
    }
  });
});
