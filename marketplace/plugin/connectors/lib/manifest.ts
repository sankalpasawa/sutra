/**
 * Sutra Connectors — Manifest parser + validator
 * Frozen by LLD §2.2 (holding/research/2026-04-30-connectors-LLD.md).
 *
 * Pure module: yaml text → ConnectorManifest, or throws ManifestError.
 * No I/O, no network, no logging. Audit happens upstream.
 */

import { parse as yamlParse } from 'yaml';
import type {
  Capability,
  CapabilityDecl,
  ConnectorManifest,
  Depth,
  Tier,
} from './types.js';
import { ManifestError } from './errors.js';

export { ManifestError } from './errors.js';

const TIERS: ReadonlyArray<Tier> = ['T1', 'T2', 'T3', 'T4'];
const ACTIONS: ReadonlyArray<CapabilityDecl['action']> = ['read', 'write', 'admin'];
const COSTS: ReadonlyArray<CapabilityDecl['costEstimate']> = ['free', 'cents', 'dollars'];
const DEPTHS: ReadonlyArray<Depth> = [1, 2, 3, 4, 5];

// -----------------------------------------------------------------------------
// parseManifest — yamlText → validated ConnectorManifest, throws ManifestError
// -----------------------------------------------------------------------------

export function parseManifest(yamlText: string): ConnectorManifest {
  let raw: unknown;
  try {
    raw = yamlParse(yamlText);
  } catch (err) {
    const detail = err instanceof Error ? err.message : String(err);
    throw new ManifestError(`malformed YAML: ${detail}`, 'malformed');
  }

  if (raw === null || raw === undefined || typeof raw !== 'object' || Array.isArray(raw)) {
    throw new ManifestError(
      'malformed YAML: top-level value must be a mapping',
      'malformed',
    );
  }

  // schemaVersion is checked first so version-skew is the loudest failure.
  const obj = raw as Record<string, unknown>;
  if (!('schemaVersion' in obj)) {
    throw new ManifestError(
      "schemaVersion is required and must be '1'",
      'schema-version',
    );
  }
  if (obj.schemaVersion !== '1') {
    throw new ManifestError(
      `schemaVersion must be '1' (got ${JSON.stringify(obj.schemaVersion)})`,
      'schema-version',
    );
  }

  // Cast through unknown so validateManifest does the runtime checking.
  const candidate = obj as unknown as ConnectorManifest;
  validateManifest(candidate);
  return candidate;
}

// -----------------------------------------------------------------------------
// validateManifest — runtime structural + semantic checks, throws ManifestError
// -----------------------------------------------------------------------------

export function validateManifest(m: ConnectorManifest): void {
  if (m === null || m === undefined || typeof m !== 'object') {
    throw new ManifestError(
      'manifest must be an object',
      'missing-field',
    );
  }

  // schemaVersion (validated by parseManifest too; redundant for direct callers)
  if ((m as { schemaVersion?: unknown }).schemaVersion !== '1') {
    throw new ManifestError(
      "schemaVersion must be '1'",
      'schema-version',
    );
  }

  // name
  if (typeof m.name !== 'string' || m.name.length === 0) {
    throw new ManifestError('name must be a non-empty string', 'missing-field');
  }

  // description
  if (typeof m.description !== 'string') {
    throw new ManifestError('description must be a string', 'missing-field');
  }

  // composioToolkit
  if (typeof m.composioToolkit !== 'string' || m.composioToolkit.length === 0) {
    throw new ManifestError(
      'composioToolkit must be a non-empty string',
      'missing-field',
    );
  }

  // capabilities — non-empty array
  if (!Array.isArray(m.capabilities) || m.capabilities.length === 0) {
    throw new ManifestError(
      'capabilities must be a non-empty array',
      'missing-field',
    );
  }

  // Per-capability validation
  const seenIds = new Set<Capability>();
  for (const cap of m.capabilities) {
    validateCapability(cap);
    seenIds.add(cap.id);
  }

  // tierAccess — all 4 tiers, each an array of known capability ids
  if (
    m.tierAccess === null ||
    m.tierAccess === undefined ||
    typeof m.tierAccess !== 'object' ||
    Array.isArray(m.tierAccess)
  ) {
    throw new ManifestError(
      'tierAccess must be an object with T1, T2, T3, T4 keys',
      'missing-field',
    );
  }
  for (const tier of TIERS) {
    if (!(tier in (m.tierAccess as Record<string, unknown>))) {
      throw new ManifestError(
        `tierAccess.${tier} is required`,
        'missing-field',
      );
    }
    const list = (m.tierAccess as Record<string, unknown>)[tier];
    if (!Array.isArray(list)) {
      throw new ManifestError(
        `tierAccess.${tier} must be an array of capability ids`,
        'missing-field',
      );
    }
    for (const ref of list) {
      if (typeof ref !== 'string' || ref.length === 0) {
        throw new ManifestError(
          `tierAccess.${tier} entries must be non-empty capability id strings`,
          'invalid-capability',
        );
      }
      // Reject overbroad references at tier level too.
      if (isOverbroad(ref)) {
        throw new ManifestError(
          `tierAccess.${tier} references overbroad capability ${JSON.stringify(ref)}`,
          'overbroad-capability',
        );
      }
      if (!seenIds.has(ref) && !matchesKnownCapabilityPrefix(ref, seenIds)) {
        throw new ManifestError(
          `tierAccess.${tier} references unknown capability ${JSON.stringify(ref)}`,
          'invalid-capability',
        );
      }
    }
  }

  // auditFields — array of strings (may be empty)
  if (!Array.isArray(m.auditFields)) {
    throw new ManifestError('auditFields must be an array of strings', 'missing-field');
  }
  for (const f of m.auditFields) {
    if (typeof f !== 'string') {
      throw new ManifestError(
        'auditFields entries must be strings',
        'missing-field',
      );
    }
  }

  // redactPaths — array of strings (may be empty)
  if (!Array.isArray(m.redactPaths)) {
    throw new ManifestError('redactPaths must be an array of strings', 'missing-field');
  }
  for (const p of m.redactPaths) {
    if (typeof p !== 'string') {
      throw new ManifestError(
        'redactPaths entries must be strings',
        'missing-field',
      );
    }
  }
}

// -----------------------------------------------------------------------------
// Internal helpers
// -----------------------------------------------------------------------------

function validateCapability(cap: CapabilityDecl): void {
  if (cap === null || cap === undefined || typeof cap !== 'object') {
    throw new ManifestError(
      'capability entry must be an object',
      'invalid-capability',
    );
  }

  // id — non-empty string
  if (typeof cap.id !== 'string' || cap.id.length === 0) {
    throw new ManifestError(
      'capability.id must be a non-empty string',
      'invalid-capability',
    );
  }

  // overbroad check
  if (isOverbroad(cap.id)) {
    throw new ManifestError(
      `capability.id ${JSON.stringify(cap.id)} is overbroad — connector and action segments must be concrete (not '*')`,
      'overbroad-capability',
    );
  }

  // action
  if (!ACTIONS.includes(cap.action)) {
    throw new ManifestError(
      `capability.action must be one of ${ACTIONS.join('|')} (got ${JSON.stringify(cap.action)})`,
      'invalid-capability',
    );
  }

  // resourcePattern
  if (typeof cap.resourcePattern !== 'string' || cap.resourcePattern.length === 0) {
    throw new ManifestError(
      'capability.resourcePattern must be a non-empty string',
      'invalid-capability',
    );
  }

  // minDepth
  if (!DEPTHS.includes(cap.minDepth)) {
    throw new ManifestError(
      `capability.minDepth must be one of 1..5 (got ${JSON.stringify(cap.minDepth)})`,
      'invalid-capability',
    );
  }

  // approvalRequired
  if (typeof cap.approvalRequired !== 'boolean') {
    throw new ManifestError(
      'capability.approvalRequired must be boolean',
      'invalid-capability',
    );
  }

  // costEstimate
  if (!COSTS.includes(cap.costEstimate)) {
    throw new ManifestError(
      `capability.costEstimate must be one of ${COSTS.join('|')} (got ${JSON.stringify(cap.costEstimate)})`,
      'invalid-capability',
    );
  }

  // id resource segment must match resourcePattern.
  // Capability id format: '<connector>:<action>:<resource>?'  (resource optional)
  const idResource = extractResource(cap.id);
  if (idResource !== null && !globMatch(cap.resourcePattern, idResource)) {
    throw new ManifestError(
      `capability.id resource ${JSON.stringify(idResource)} does not match resourcePattern ${JSON.stringify(cap.resourcePattern)}`,
      'invalid-capability',
    );
  }
}

/**
 * Capability id segments: '<connector>:<action>[:<resource...>]'
 * Overbroad = either the connector OR the action segment is exactly '*',
 * regardless of trailing resource. The resource portion belongs in
 * resourcePattern, not in the id, and is allowed to be glob-y there.
 */
function isOverbroad(id: Capability): boolean {
  if (typeof id !== 'string' || id.length === 0) return false;
  const segs = id.split(':');
  if (segs.length < 2) return false;
  const connector = segs[0];
  const action = segs[1];
  return connector === '*' || action === '*';
}

/**
 * Returns the resource portion of the id (segments 3+), or null when the id
 * has no resource segment (only connector:action).
 */
function extractResource(id: Capability): string | null {
  const segs = id.split(':');
  if (segs.length < 3) return null;
  // Resource may itself contain ':' (e.g. 'kv:user:42') — rejoin.
  return segs.slice(2).join(':');
}

/**
 * Glob match: '*' matches any sequence of chars within a segment-agnostic
 * string. Sufficient for resource patterns like '#*', 'users/*', '*.json'.
 * '?' matches a single character. All other regex metacharacters are escaped.
 */
function globMatch(pattern: string, value: string): boolean {
  const escaped = pattern.replace(/[.+^${}()|[\]\\]/g, '\\$&');
  const regexSource = '^' + escaped.replace(/\*/g, '.*').replace(/\?/g, '.') + '$';
  return new RegExp(regexSource).test(value);
}

/**
 * Allow tierAccess to reference a capability by glob prefix that resolves to
 * a known capability id. Conservative: '*' is rejected upstream as overbroad,
 * so this only fires for legitimate prefix patterns like 'slack:read-channel:*'.
 */
function matchesKnownCapabilityPrefix(
  ref: Capability,
  knownIds: ReadonlySet<Capability>,
): boolean {
  if (!ref.includes('*') && !ref.includes('?')) return false;
  for (const id of knownIds) {
    if (globMatch(ref, id)) return true;
  }
  return false;
}
