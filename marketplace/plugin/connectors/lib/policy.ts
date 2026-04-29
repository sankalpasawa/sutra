/**
 * Sutra Connectors — Policy + approval gate (BEHAVIOR CORE)
 * Frozen by LLD §2.4. Implementation lands iter 4 (sequential green, first).
 *
 * Implementation notes:
 *   - evaluatePolicy composes three sub-checks (capability, depth, fleet) into
 *     a single PolicyDecision struct. Order of precedence on block:
 *       1. capability (unknown / tier-denied / pattern-mismatch)
 *       2. depth-floor
 *       3. fleet freeze (active-freeze:<id>)
 *   - require-approval verdict only fires when ALL three sub-checks pass AND
 *     the matched CapabilityDecl.approvalRequired is true AND ctx carries no
 *     consumable approvalToken.
 *   - consumeApproval is single-use: returns true on first call (and removes
 *     from the issued set), false thereafter / for unknown tokens.
 *   - issueApproval mints a UUID-like token and adds it to the issued set;
 *     it's exported for the router/test harness per LLD §3 data flow.
 */

import type {
  ConnectorCallContext,
  ConnectorManifest,
  FleetPolicy,
  PolicyDecision,
  CapabilityDecl,
  CapabilityCheckResult,
  Capability,
  Depth,
  Tier,
  FreezeRule,
} from './types.js';

// ---------------------------------------------------------------------------
// Approval token registry (module-level, single-use, ctx-bound)
// ---------------------------------------------------------------------------

/**
 * Approval bindings — fix for codex iter-11 P1 #3 (token replay).
 *
 * Tokens are bound to (clientId, sessionId, capability, ts) at issue time.
 * Consume requires matching ctx for binding to apply. Bindings expire after
 * APPROVAL_TTL_MS to bound the replay window even within the same session.
 */
interface ApprovalBinding {
  readonly clientId: string;
  readonly sessionId: string;
  readonly capability: string;
  readonly issuedAt: number;
}

const ISSUED_TOKENS: Map<string, ApprovalBinding> = new Map<string, ApprovalBinding>();

/** Approval freshness window — token valid for matching ctx within 5 minutes of issue. */
const APPROVAL_TTL_MS = 5 * 60 * 1000;

/**
 * Mint a new approval token bound to the issuing ctx. Per LLD §3 + codex iter-11
 * security fix: founder ack flow → router calls this → caller re-invokes call(ctx)
 * with ctx.approvalToken=<minted>; consumeApproval(token, ctx) verifies binding
 * before single-use consumption.
 *
 * The binding is captured from ctx.clientId, ctx.sessionId, ctx.capability, ctx.ts
 * at issue time. Caller MUST pass the same ctx (or one matching on those four
 * fields, within APPROVAL_TTL_MS) when re-invoking.
 */
export function issueApproval(ctx?: ConnectorCallContext): string {
  const token = `appr-${generateUuidLike()}`;
  if (ctx !== undefined) {
    ISSUED_TOKENS.set(token, {
      clientId: ctx.clientId,
      sessionId: ctx.sessionId,
      capability: ctx.capability,
      issuedAt: ctx.ts,
    });
  } else {
    // Defensive — pre-iter-12 callers may still mint without ctx. Record an
    // empty binding so the token exists but can never be consumed via
    // ctx-bound consumeApproval. (Effectively unusable; safer than throwing.)
    ISSUED_TOKENS.set(token, {
      clientId: '',
      sessionId: '',
      capability: '',
      issuedAt: 0,
    });
  }
  return token;
}

/**
 * Verify whether a token EXISTS and binds to the given ctx. Does NOT consume.
 * Used by evaluatePolicy to decide require-approval vs allow without burning
 * the token (consumption happens at the router post-decision step).
 */
export function isApprovalValidFor(
  token: string | undefined,
  ctx: ConnectorCallContext,
): boolean {
  if (typeof token !== 'string' || token.length === 0) return false;
  const binding = ISSUED_TOKENS.get(token);
  if (binding === undefined) return false;
  return bindingMatches(binding, ctx);
}

/**
 * Consume an approval token. Returns true ONLY if the token was issued AND
 * its binding matches the supplied ctx (clientId, sessionId, capability) AND
 * is within the freshness window. Removes from registry on success.
 *
 * Backward-compat: ctx is optional ONLY for callers that genuinely have no
 * ctx (e.g. legacy tests). When ctx is omitted the consume is rejected for
 * any binding that has a non-empty clientId — i.e. real bound tokens require
 * ctx. The legacy-empty-binding path (issued without ctx) consumes for any
 * caller, preserving the pre-iter-12 contract for the explicit unbound case.
 */
export function consumeApproval(
  token: string,
  ctx?: ConnectorCallContext,
): boolean {
  if (typeof token !== 'string' || token.length === 0) return false;
  const binding = ISSUED_TOKENS.get(token);
  if (binding === undefined) return false;

  // Legacy unbound issue (ctx-less issueApproval) — accept any consume.
  if (
    binding.clientId === '' &&
    binding.sessionId === '' &&
    binding.capability === ''
  ) {
    ISSUED_TOKENS.delete(token);
    return true;
  }

  // Bound token — require matching ctx.
  if (ctx === undefined) return false;
  if (!bindingMatches(binding, ctx)) return false;

  ISSUED_TOKENS.delete(token);
  return true;
}

function bindingMatches(
  binding: ApprovalBinding,
  ctx: ConnectorCallContext,
): boolean {
  if (binding.clientId !== ctx.clientId) return false;
  if (binding.sessionId !== ctx.sessionId) return false;
  if (binding.capability !== ctx.capability) return false;
  // Freshness — bound to the issue ts.
  const age = ctx.ts - binding.issuedAt;
  if (age < 0 || age > APPROVAL_TTL_MS) return false;
  return true;
}

// ---------------------------------------------------------------------------
// Public API: evaluatePolicy
// ---------------------------------------------------------------------------

export function evaluatePolicy(
  ctx: ConnectorCallContext,
  manifest: ConnectorManifest,
  fleetPolicy: FleetPolicy,
): PolicyDecision {
  // 1. Find matching capability declaration.
  const decl = findCapabilityDecl(ctx.capability, manifest.capabilities);

  // 2a. Unknown capability → block.
  if (decl === undefined) {
    const capabilityCheck: CapabilityCheckResult = {
      granted: false,
      reason: 'unknown-capability',
    };
    const depthCheck = { allowed: false, minRequired: 5 as Depth };
    const fleetPolicyCheck = { allowed: true };
    return {
      verdict: 'block',
      reason: 'unknown-capability',
      capabilityCheck,
      depthCheck,
      fleetPolicyCheck,
    };
  }

  // 2b. Tier-access check: ctx.capability must appear (exact or prefix-glob)
  //     in manifest.tierAccess[ctx.tier].
  const tierEntries: ReadonlyArray<Capability> =
    manifest.tierAccess[ctx.tier] ?? [];
  const tierGranted = tierEntries.some((entry) =>
    matchesTierEntry(ctx.capability, entry),
  );

  // 2c. Resource pattern check: ctx.capability resource portion must satisfy
  //     decl.resourcePattern.
  const patternOk = matchesResource(ctx.capability, decl.resourcePattern);

  // Compose capabilityCheck — earliest failure wins for the reason field.
  let capabilityCheck: CapabilityCheckResult;
  if (!tierGranted) {
    capabilityCheck = { granted: false, reason: 'tier-denied' };
  } else if (!patternOk) {
    capabilityCheck = { granted: false, reason: 'pattern-mismatch' };
  } else {
    capabilityCheck = { granted: true, reason: 'tier-allowed' };
  }

  // 3. Depth floor check.
  const depthCheck = {
    allowed: ctx.depth >= decl.minDepth,
    minRequired: decl.minDepth,
  };

  // 4. Fleet policy / freeze check.
  const fleetPolicyCheck = evaluateFleetFreezes(ctx, fleetPolicy.freezes);

  // 5. Compose final verdict (precedence: capability → depth → freeze → approval).
  if (!capabilityCheck.granted) {
    return {
      verdict: 'block',
      reason: capabilityCheck.reason,
      capabilityCheck,
      depthCheck,
      fleetPolicyCheck,
    };
  }
  if (!depthCheck.allowed) {
    return {
      verdict: 'block',
      reason: 'depth-floor',
      capabilityCheck,
      depthCheck,
      fleetPolicyCheck,
    };
  }
  if (!fleetPolicyCheck.allowed) {
    const freezeId = fleetPolicyCheck.activeFreeze ?? 'unknown';
    return {
      verdict: 'block',
      reason: `active-freeze:${freezeId}`,
      capabilityCheck,
      depthCheck,
      fleetPolicyCheck,
    };
  }

  // 6. Approval gate — checks pass; if approval required and no consumable
  //    token bound to THIS ctx, return require-approval; otherwise allow.
  if (decl.approvalRequired) {
    const tokenOk = isApprovalValidFor(ctx.approvalToken, ctx);
    if (!tokenOk) {
      return {
        verdict: 'require-approval',
        reason: 'approval-required',
        capabilityCheck,
        depthCheck,
        fleetPolicyCheck,
      };
    }
  }

  return {
    verdict: 'allow',
    reason: 'tier-allowed',
    capabilityCheck,
    depthCheck,
    fleetPolicyCheck,
  };
}

// ---------------------------------------------------------------------------
// Internal helpers
// ---------------------------------------------------------------------------

/**
 * Find the manifest CapabilityDecl whose id matches ctx.capability.
 *
 * Match strategy (iter 12 — codex final-fix):
 *   1. EXACT id match → return decl.
 *   2. ELSE: scan decls whose id contains '*' — treat the decl id as a
 *      glob pattern (same matchesGlob helper used elsewhere) and match
 *      against ctx.capability. First glob-id hit wins.
 *   3. ELSE: undefined → unknown-capability.
 *
 * Why glob-id fallback (iter 12): T4 tier access uses prefix patterns like
 * 'slack:read-channel:#public-*'. The manifest now ships a corresponding
 * glob-id decl ('slack:read-channel:#public-*') so any concrete capability
 * matching that prefix (e.g. '#public-announce') resolves to a real decl
 * rather than being dropped as unknown-capability.
 *
 * Iter 11 unknown-capability invariant preserved: a ctx.capability that
 * matches NEITHER an exact decl NOR any glob-id decl still returns
 * undefined. The unit-test fixture (policy.test.ts buildManifest) only
 * uses exact-id decls, so its CAP_UNKNOWN ('slack:read-channel:#never-declared')
 * still hits no decl → still returns unknown-capability.
 *
 * Per LLD §2.4, resourcePattern is still the post-decl gate (matchesResource
 * → pattern-mismatch); the glob-id fallback only widens DECL DISCOVERY for
 * legitimately glob-shaped declarations, it does not absorb arbitrary ids.
 */
function findCapabilityDecl(
  capability: Capability,
  decls: ReadonlyArray<CapabilityDecl>,
): CapabilityDecl | undefined {
  // 1. Exact id match first — fast path + preserves iter-11 unknown-capability test.
  for (const d of decls) {
    if (d.id === capability) return d;
  }
  // 2. Glob-id fallback — only decls whose id literally contains '*'.
  for (const d of decls) {
    if (d.id.includes('*') && matchesGlob(capability, d.id)) {
      return d;
    }
  }
  // 3. No match — caller surfaces unknown-capability.
  return undefined;
}

/**
 * Resource-portion pattern check for the matched decl.
 * Extracts the resource (everything after 'connector:action:') and globs it.
 */
function matchesResource(
  capability: Capability,
  resourcePattern: string,
): boolean {
  const parts = capability.split(':');
  const resource = parts.slice(2).join(':');
  return matchesGlob(resource, resourcePattern);
}

/**
 * Glob matcher for resourcePattern + tier-access entries.
 *   - empty pattern: never matches (defensive)
 *   - '*': matches anything (including empty)
 *   - 'foo*' / '#*' / 'prefix/*': matches any string starting with the literal
 *     prefix (the part before '*')
 *   - otherwise: exact match
 */
function matchesGlob(value: string, pattern: string): boolean {
  if (pattern === undefined || pattern === null || pattern === '') return false;
  if (pattern === '*') return true;
  const starIdx = pattern.indexOf('*');
  if (starIdx === -1) {
    return value === pattern;
  }
  // Prefix glob: literal portion before '*' must prefix value.
  // (We intentionally treat '*' anywhere as "prefix glob" since LLD only
  //  enumerates leading-prefix patterns like '#*', 'users/*', 'slack:write-*'.)
  const prefix = pattern.slice(0, starIdx);
  return value.startsWith(prefix);
}

/**
 * Tier-access entry matcher. Each entry in tierAccess[tier] is either:
 *   - an exact capability id ('slack:read-channel:#dayflow-eng')
 *   - or a glob pattern ('slack:write-*')
 * The capability is granted if it matches any entry exactly OR via glob.
 */
function matchesTierEntry(capability: Capability, entry: Capability): boolean {
  if (entry === capability) return true;
  if (entry.includes('*')) {
    return matchesGlob(capability, entry);
  }
  return false;
}

/**
 * Walk the freeze list; return blocked + activeFreeze on the first matching
 * rule, else allowed. A freeze matches when ALL of:
 *   - capabilityPattern matches ctx.capability (glob),
 *   - tierScope includes ctx.tier,
 *   - until is undefined (indefinite) OR until > ctx.ts (still active).
 */
function evaluateFleetFreezes(
  ctx: ConnectorCallContext,
  freezes: ReadonlyArray<FreezeRule>,
): { allowed: boolean; activeFreeze?: string } {
  for (const fz of freezes) {
    if (!matchesGlob(ctx.capability, fz.capabilityPattern)) continue;
    if (!fz.tierScope.includes(ctx.tier as Tier)) continue;
    if (fz.until !== undefined && fz.until <= ctx.ts) continue;
    return { allowed: false, activeFreeze: fz.id };
  }
  return { allowed: true };
}

/**
 * UUID-like generator (no external deps). Format: 8-4-4-4-12 hex.
 * Uses Math.random — sufficient for in-process single-use token uniqueness;
 * a future iter may swap to crypto.randomUUID() once the runtime target is
 * confirmed Node 16+.
 */
function generateUuidLike(): string {
  const hex = (n: number): string =>
    Math.floor(Math.random() * Math.pow(16, n))
      .toString(16)
      .padStart(n, '0');
  return `${hex(8)}-${hex(4)}-${hex(4)}-${hex(4)}-${hex(12)}`;
}
