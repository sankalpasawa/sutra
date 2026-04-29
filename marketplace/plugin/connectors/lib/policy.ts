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
// Approval token registry (module-level, single-use semantics)
// ---------------------------------------------------------------------------

const ISSUED_TOKENS: Set<string> = new Set<string>();

/**
 * Mint a new approval token, register it as single-use, return the string.
 * Per LLD §3: founder ack flow → router calls this → caller re-invokes call(ctx)
 * with ctx.approvalToken=<minted>; consumeApproval(token) gates the actual run.
 *
 * The optional ctx parameter is accepted for forward-compatibility (richer
 * tokens may bind to clientId/sessionId in a later iter); it is not used
 * to derive the token today.
 */
export function issueApproval(_ctx?: ConnectorCallContext): string {
  const token = `appr-${generateUuidLike()}`;
  ISSUED_TOKENS.add(token);
  return token;
}

/**
 * Consume an approval token. Returns true if the token was issued and
 * has not been consumed; removes it from the registry. Returns false
 * for unknown / already-consumed tokens.
 */
export function consumeApproval(token: string): boolean {
  if (typeof token !== 'string' || token.length === 0) return false;
  if (!ISSUED_TOKENS.has(token)) return false;
  ISSUED_TOKENS.delete(token);
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
  //    token, return require-approval; otherwise allow.
  if (decl.approvalRequired) {
    const tokenOk =
      typeof ctx.approvalToken === 'string' &&
      ctx.approvalToken.length > 0 &&
      ISSUED_TOKENS.has(ctx.approvalToken);
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
 * Match strategy: EXACT id match only.
 *
 * Rationale (iter 11 fix): a prior prefix-fallback that matched on the first
 * two ':'-segments (connector:action) plus a resourcePattern glob caused a
 * mis-classification. A capability like 'slack:read-channel:#never-declared'
 * — never declared in the manifest — would silently match the
 * 'slack:read-channel:#dayflow-eng' decl (whose resourcePattern '#*' accepts
 * any '#' resource), then fall through to a tier-denied verdict because the
 * tierAccess list enumerates exact ids. The test "ctx.capability is not
 * declared in manifest" expects unknown-capability, not tier-denied.
 *
 * Per LLD §2.4, the manifest is the closed set of declared capabilities;
 * resourcePattern is checked AFTER an exact decl is found (matchesResource
 * → 'pattern-mismatch'), it is not a way to "find" a decl for a different id.
 */
function findCapabilityDecl(
  capability: Capability,
  decls: ReadonlyArray<CapabilityDecl>,
): CapabilityDecl | undefined {
  for (const d of decls) {
    if (d.id === capability) return d;
  }
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
