/**
 * Unit tests for connectors/lib/capability.ts
 *
 * Frozen contract: LLD §2.3
 *   tierGrants(tier, capability, manifest) -> CapabilityCheckResult
 *   matchesResourcePattern(capability, declaredPattern) -> boolean
 *   isOverbroadCapability(capability) -> boolean
 *
 * Test plan: §3.2 of holding/research/2026-04-30-connectors-test-plan.md
 *
 * iter 3 — TDD RED: every test fails until iter 5b implements capability.ts
 * (current stub throws 'not implemented (TDD red phase)').
 */

import { describe, it, expect } from 'vitest';

import {
  isOverbroadCapability,
  matchesResourcePattern,
  tierGrants,
} from '../../lib/capability.js';
import type { ConnectorManifest } from '../../lib/types.js';

// ---------------------------------------------------------------------------
// Fixture: minimal in-test ConnectorManifest. Mirrors the shape of the real
// slack manifest enough to exercise tierGrants across all four tiers.
// ---------------------------------------------------------------------------

const fixture: ConnectorManifest = {
  schemaVersion: '1',
  name: 'slack',
  description: 'Test slack manifest fixture (capability.test.ts)',
  composioToolkit: 'slack',
  capabilities: [
    {
      id: 'slack:read-channel:#dayflow-eng',
      action: 'read',
      resourcePattern: '#*',
      minDepth: 1,
      approvalRequired: false,
      costEstimate: 'free',
    },
    {
      id: 'slack:read-channel:#ops',
      action: 'read',
      resourcePattern: '#*',
      minDepth: 1,
      approvalRequired: false,
      costEstimate: 'free',
    },
    {
      id: 'slack:write-channel:#public-launch',
      action: 'write',
      resourcePattern: '#*',
      minDepth: 3,
      approvalRequired: true,
      costEstimate: 'cents',
    },
    {
      id: 'slack:list-users:users/*',
      action: 'read',
      resourcePattern: 'users/*',
      minDepth: 2,
      approvalRequired: false,
      costEstimate: 'free',
    },
  ],
  tierAccess: {
    T1: [
      'slack:read-channel:#dayflow-eng',
      'slack:read-channel:#ops',
      'slack:write-channel:#public-launch',
      'slack:list-users:users/*',
    ],
    T2: [
      'slack:read-channel:#dayflow-eng',
      'slack:write-channel:#public-launch',
    ],
    T3: ['slack:read-channel:#dayflow-eng'],
    T4: [],
  },
  auditFields: ['clientId', 'tier', 'capability'],
  redactPaths: ['$.token', '$.user.email'],
};

// ---------------------------------------------------------------------------
// tierGrants — LLD §2.3
// ---------------------------------------------------------------------------

describe('capability.tierGrants', () => {
  it('returns granted=true with reason=tier-allowed when T1 reads a channel listed in tierAccess.T1', () => {
    const result = tierGrants('T1', 'slack:read-channel:#dayflow-eng', fixture);
    expect(result.granted).toBe(true);
    expect(result.reason).toBe('tier-allowed');
  });

  it('returns granted=false with reason=tier-denied when T3 attempts to read a T1-only channel not present in tierAccess.T3', () => {
    const result = tierGrants('T3', 'slack:read-channel:#ops', fixture);
    expect(result.granted).toBe(false);
    expect(result.reason).toBe('tier-denied');
  });

  it('returns granted=false with reason=tier-denied for T4 when its tierAccess list is empty', () => {
    const result = tierGrants('T4', 'slack:read-channel:#dayflow-eng', fixture);
    expect(result.granted).toBe(false);
    expect(result.reason).toBe('tier-denied');
  });

  it('returns granted=false with reason=unknown-capability when the capability id is not declared in manifest.capabilities', () => {
    const result = tierGrants('T1', 'slack:delete-channel:#nope', fixture);
    expect(result.granted).toBe(false);
    expect(result.reason).toBe('unknown-capability');
  });

  it('returns granted=false with reason=pattern-mismatch when the capability resource segment does not match the declared resourcePattern glob', () => {
    // tierAccess.T1 includes 'slack:list-users:users/*' but invocation passes
    // a non-matching resource (no users/ prefix).
    const result = tierGrants('T1', 'slack:list-users:admins/42', fixture);
    expect(result.granted).toBe(false);
    expect(result.reason).toBe('pattern-mismatch');
  });
});

// ---------------------------------------------------------------------------
// matchesResourcePattern — LLD §2.3
// ---------------------------------------------------------------------------

describe('capability.matchesResourcePattern', () => {
  it('returns true for a channel-style capability whose resource segment satisfies the "#*" glob', () => {
    expect(
      matchesResourcePattern('slack:read-channel:#dayflow-eng', '#*'),
    ).toBe(true);
  });

  it('returns false for a capability whose resource segment lacks the "#" prefix required by the "#*" glob', () => {
    expect(matchesResourcePattern('slack:read-channel:dm-user-12', '#*')).toBe(
      false,
    );
  });

  it('returns true for hyphen-rich channel ids matching "#*" (e.g. "#a-b-c-d")', () => {
    expect(matchesResourcePattern('slack:read-channel:#a-b-c-d', '#*')).toBe(
      true,
    );
  });

  it('returns true for resource segments matching a "users/*" prefix glob', () => {
    expect(
      matchesResourcePattern('slack:list-users:users/U12345', 'users/*'),
    ).toBe(true);
  });

  it('returns true against the universal "*" glob for any non-empty capability id', () => {
    expect(matchesResourcePattern('slack:read-channel:#whatever', '*')).toBe(
      true,
    );
  });

  it('returns true for capability ids with no resource segment when matched against the universal "*" pattern', () => {
    // Globless capability — no third colon-separated segment.
    expect(matchesResourcePattern('slack:list-users', '*')).toBe(true);
  });
});

// ---------------------------------------------------------------------------
// isOverbroadCapability — LLD §2.3
// ---------------------------------------------------------------------------

describe('capability.isOverbroadCapability', () => {
  it('returns true for a connector-wildcard capability of the form "slack:*"', () => {
    expect(isOverbroadCapability('slack:*')).toBe(true);
  });

  it('returns true for a toolkit-wildcard capability of the form "*:read-channel:#x"', () => {
    expect(isOverbroadCapability('*:read-channel:#x')).toBe(true);
  });

  it('returns true for a mid-string action wildcard of the form "slack:*:#x"', () => {
    expect(isOverbroadCapability('slack:*:#x')).toBe(true);
  });

  it('returns false for a fully scoped capability like "slack:read-channel:#dayflow-eng"', () => {
    expect(isOverbroadCapability('slack:read-channel:#dayflow-eng')).toBe(
      false,
    );
  });

  it('returns false for an empty capability string (edge case — empty is not "overbroad", it is malformed)', () => {
    expect(isOverbroadCapability('')).toBe(false);
  });

  it('returns true for a "gmail:*" connector-wildcard to confirm the rule generalizes beyond slack', () => {
    expect(isOverbroadCapability('gmail:*')).toBe(true);
  });
});
