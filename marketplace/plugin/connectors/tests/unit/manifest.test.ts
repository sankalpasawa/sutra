/**
 * Sutra Connectors — manifest.ts unit tests (TDD red phase).
 *
 * References:
 *  - LLD §2.2 — holding/research/2026-04-30-connectors-LLD.md (frozen interfaces)
 *  - Test plan §3.1 — holding/research/2026-04-30-connectors-test-plan.md
 *
 * All assertions here MUST currently fail because lib/manifest.ts is a stub
 * that throws ManifestError('not implemented (TDD red phase)') from both
 * parseManifest() and validateManifest().
 *
 * Mock-free: manifest.ts is pure (yaml text in, ConnectorManifest out / throw).
 */

import { describe, it, expect } from 'vitest';
import {
  parseManifest,
  validateManifest,
  ManifestError,
} from '../../lib/manifest.js';
import type {
  ConnectorManifest,
  CapabilityDecl,
  Tier,
  Capability,
} from '../../lib/types.js';

// -----------------------------------------------------------------------------
// Inline fixtures — kept small; integration tests load real manifests/slack.yaml
// -----------------------------------------------------------------------------

const VALID_SLACK_YAML = `
schemaVersion: '1'
name: slack
description: Slack reference connector for Sutra v0
composioToolkit: slack
capabilities:
  - id: slack:read-channel:#dayflow-eng
    action: read
    resourcePattern: '#*'
    minDepth: 1
    approvalRequired: false
    costEstimate: free
  - id: slack:write-channel:#public-launch
    action: write
    resourcePattern: '#*'
    minDepth: 5
    approvalRequired: true
    costEstimate: cents
  - id: slack:admin-channel:#ops
    action: admin
    resourcePattern: '#*'
    minDepth: 5
    approvalRequired: true
    costEstimate: dollars
tierAccess:
  T1:
    - slack:read-channel:#dayflow-eng
    - slack:write-channel:#public-launch
    - slack:admin-channel:#ops
  T2:
    - slack:read-channel:#dayflow-eng
    - slack:write-channel:#public-launch
  T3: []
  T4: []
auditFields:
  - workspace_id
  - channel_id
redactPaths:
  - $.token
  - $.user.email
`;

const MALFORMED_YAML = `
schemaVersion: '1
name: slack
  capabilities:
   - id: bad
     action read
   resourcePattern '#*
`;

// Build a programmatic, fully-valid manifest for validateManifest tests.
const buildValidManifest = (): ConnectorManifest => ({
  schemaVersion: '1',
  name: 'slack',
  description: 'Slack reference connector',
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
      id: 'slack:write-channel:#public-launch',
      action: 'write',
      resourcePattern: '#*',
      minDepth: 5,
      approvalRequired: true,
      costEstimate: 'cents',
    },
    {
      id: 'slack:admin-channel:#ops',
      action: 'admin',
      resourcePattern: '#*',
      minDepth: 5,
      approvalRequired: true,
      costEstimate: 'dollars',
    },
  ],
  tierAccess: {
    T1: ['slack:read-channel:#dayflow-eng'],
    T2: ['slack:read-channel:#dayflow-eng', 'slack:write-channel:#public-launch'],
    T3: [],
    T4: [],
  } satisfies Record<Tier, ReadonlyArray<Capability>>,
  auditFields: ['workspace_id', 'channel_id'],
  redactPaths: ['$.token', '$.user.email'],
});

// -----------------------------------------------------------------------------
// parseManifest — happy path + structural failures
// -----------------------------------------------------------------------------

describe('manifest.parseManifest', () => {
  it('manifest.parseManifest accepts valid-slack.yaml and returns ConnectorManifest with schemaVersion=1', () => {
    const m = parseManifest(VALID_SLACK_YAML);
    expect(m.schemaVersion).toBe('1');
    expect(m.name).toBe('slack');
    expect(m.composioToolkit).toBe('slack');
    expect(Array.isArray(m.capabilities)).toBe(true);
    expect(m.capabilities.length).toBeGreaterThanOrEqual(3);
  });

  it('manifest.parseManifest rejects malformed YAML with code=malformed', () => {
    try {
      parseManifest(MALFORMED_YAML);
      // If no throw, force-fail with explicit signal (current stub DOES throw,
      // but with code='malformed' from the not-implemented body — same code,
      // different message; this test will go GREEN once the real parser
      // reports YAML parse failure with code='malformed').
      expect.fail('parseManifest must throw on malformed YAML');
    } catch (err) {
      expect(err).toBeInstanceOf(ManifestError);
      expect((err as ManifestError).code).toBe('malformed');
    }
  });

  it('manifest.parseManifest throws ManifestError when schemaVersion is missing with code=schema-version', () => {
    const yaml = VALID_SLACK_YAML.replace(/schemaVersion: '1'\n/, '');
    try {
      parseManifest(yaml);
      expect.fail('parseManifest must throw when schemaVersion missing');
    } catch (err) {
      expect(err).toBeInstanceOf(ManifestError);
      expect((err as ManifestError).code).toBe('schema-version');
    }
  });

  it('manifest.parseManifest throws ManifestError when schemaVersion is "2" with code=schema-version', () => {
    const yaml = VALID_SLACK_YAML.replace("schemaVersion: '1'", "schemaVersion: '2'");
    try {
      parseManifest(yaml);
      expect.fail('parseManifest must throw when schemaVersion mismatches');
    } catch (err) {
      expect(err).toBeInstanceOf(ManifestError);
      expect((err as ManifestError).code).toBe('schema-version');
    }
  });

  it('manifest.parseManifest throws ManifestError when name field is missing with code=missing-field', () => {
    const yaml = VALID_SLACK_YAML.replace('name: slack\n', '');
    try {
      parseManifest(yaml);
      expect.fail('parseManifest must throw when name field missing');
    } catch (err) {
      expect(err).toBeInstanceOf(ManifestError);
      expect((err as ManifestError).code).toBe('missing-field');
    }
  });

  it('manifest.parseManifest throws ManifestError when capabilities array is empty with code=missing-field', () => {
    const yaml = `
schemaVersion: '1'
name: slack
description: empty caps
composioToolkit: slack
capabilities: []
tierAccess:
  T1: []
  T2: []
  T3: []
  T4: []
auditFields: []
redactPaths: []
`;
    try {
      parseManifest(yaml);
      expect.fail('parseManifest must throw when capabilities is empty');
    } catch (err) {
      expect(err).toBeInstanceOf(ManifestError);
      expect((err as ManifestError).code).toBe('missing-field');
    }
  });

  it('manifest.parseManifest preserves costEstimate=cents for slack:write-channel capability', () => {
    const m = parseManifest(VALID_SLACK_YAML);
    const writeCap = m.capabilities.find(
      (c: CapabilityDecl) => c.id === 'slack:write-channel:#public-launch',
    );
    expect(writeCap).toBeDefined();
    expect(writeCap!.costEstimate).toBe('cents');
  });

  it('manifest.parseManifest is pure: same yamlText input returns deep-equal manifest across N=100 calls', () => {
    const first = parseManifest(VALID_SLACK_YAML);
    for (let i = 0; i < 100; i++) {
      const next = parseManifest(VALID_SLACK_YAML);
      expect(next).toEqual(first);
    }
  });
});

// -----------------------------------------------------------------------------
// validateManifest — semantic failures + acceptance
// -----------------------------------------------------------------------------

describe('manifest.validateManifest', () => {
  it('manifest.validateManifest accepts slack manifest with read+write+admin capabilities all properly bounded', () => {
    const m = buildValidManifest();
    expect(() => validateManifest(m)).not.toThrow();
  });

  it('manifest.validateManifest rejects overbroad capability "slack:*" with code=overbroad-capability', () => {
    const base = buildValidManifest();
    const m: ConnectorManifest = {
      ...base,
      capabilities: [
        ...base.capabilities,
        {
          id: 'slack:*',
          action: 'read',
          resourcePattern: '*',
          minDepth: 1,
          approvalRequired: false,
          costEstimate: 'free',
        },
      ],
      tierAccess: {
        ...base.tierAccess,
        T1: [...base.tierAccess.T1, 'slack:*'],
      },
    };
    try {
      validateManifest(m);
      expect.fail('validateManifest must reject overbroad capability');
    } catch (err) {
      expect(err).toBeInstanceOf(ManifestError);
      expect((err as ManifestError).code).toBe('overbroad-capability');
    }
  });

  it('manifest.validateManifest rejects capability id not matching declared resourcePattern with code=invalid-capability', () => {
    const base = buildValidManifest();
    // Resource segment 'dm-user-12' does NOT match resourcePattern '#*'
    const broken: CapabilityDecl = {
      id: 'slack:read-channel:dm-user-12',
      action: 'read',
      resourcePattern: '#*',
      minDepth: 1,
      approvalRequired: false,
      costEstimate: 'free',
    };
    const m: ConnectorManifest = {
      ...base,
      capabilities: [...base.capabilities, broken],
    };
    try {
      validateManifest(m);
      expect.fail('validateManifest must reject pattern-mismatched capability id');
    } catch (err) {
      expect(err).toBeInstanceOf(ManifestError);
      expect((err as ManifestError).code).toBe('invalid-capability');
    }
  });

  it('manifest.validateManifest rejects capability with action outside read|write|admin with code=invalid-capability', () => {
    const base = buildValidManifest();
    const broken = {
      id: 'slack:execute-channel:#x',
      action: 'execute' as unknown as 'read', // forced cast: testing runtime guard
      resourcePattern: '#*',
      minDepth: 1,
      approvalRequired: false,
      costEstimate: 'free',
    } as CapabilityDecl;
    const m: ConnectorManifest = {
      ...base,
      capabilities: [...base.capabilities, broken],
    };
    try {
      validateManifest(m);
      expect.fail('validateManifest must reject invalid action');
    } catch (err) {
      expect(err).toBeInstanceOf(ManifestError);
      expect((err as ManifestError).code).toBe('invalid-capability');
    }
  });

  it('manifest.validateManifest rejects minDepth outside 1..5 range with code=invalid-capability', () => {
    const base = buildValidManifest();
    const broken = {
      id: 'slack:read-channel:#deep',
      action: 'read',
      resourcePattern: '#*',
      minDepth: 7 as unknown as 5, // forced: out-of-range
      approvalRequired: false,
      costEstimate: 'free',
    } as CapabilityDecl;
    const m: ConnectorManifest = {
      ...base,
      capabilities: [...base.capabilities, broken],
    };
    try {
      validateManifest(m);
      expect.fail('validateManifest must reject out-of-range minDepth');
    } catch (err) {
      expect(err).toBeInstanceOf(ManifestError);
      expect((err as ManifestError).code).toBe('invalid-capability');
    }
  });

  it('manifest.validateManifest rejects tierAccess referencing capability id not in capabilities[] with code=invalid-capability', () => {
    const base = buildValidManifest();
    const m: ConnectorManifest = {
      ...base,
      tierAccess: {
        ...base.tierAccess,
        T1: [...base.tierAccess.T1, 'slack:read-channel:#nonexistent'],
      },
    };
    try {
      validateManifest(m);
      expect.fail('validateManifest must reject tierAccess referencing unknown capability');
    } catch (err) {
      expect(err).toBeInstanceOf(ManifestError);
      expect((err as ManifestError).code).toBe('invalid-capability');
    }
  });

  it('manifest.validateManifest preserves redactPaths array verbatim for downstream AuditSink config', () => {
    const m = buildValidManifest();
    // No throw expected; structural assertion that validateManifest does not
    // mutate (manifest is readonly, but the contract says paths flow downstream).
    expect(() => validateManifest(m)).not.toThrow();
    expect(m.redactPaths).toEqual(['$.token', '$.user.email']);
  });
});

// -----------------------------------------------------------------------------
// ManifestError shape (LLD §2.2 + errors.ts)
// -----------------------------------------------------------------------------

describe('ManifestError', () => {
  it('ManifestError is instanceof Error and exposes a typed code field', () => {
    const e = new ManifestError('boom', 'malformed');
    expect(e).toBeInstanceOf(Error);
    expect(e).toBeInstanceOf(ManifestError);
    expect(e.code).toBe('malformed');
    expect(e.name).toBe('ManifestError');
    expect(e.message).toBe('boom');
  });
});
