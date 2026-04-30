/**
 * Sutra Connectors — credential-loader (M1.8).
 *
 * Reads/writes typed credential bundles for connectors. Prefers age-encrypted
 * `.age` files via SecretStoreAge; falls back to `.json` plaintext during the
 * migration window, emitting a MIGRATION_PENDING audit beacon.
 *
 * Spec authority: holding/research/2026-04-30-core-connectors-hardening-spec.md §M1.8
 * Wave 3 of Core/Connectors Hardening.
 *
 * Discriminated union (codex-load-bearing — Gmail-shape fit):
 *   - SlackPatBundle        kind='slack-pat'    token (xoxb-/xoxp-)
 *   - GmailOAuthBundle      kind='gmail-oauth'  full OAuth state + refresh
 *   - ComposioToolkitBundle kind='composio'     toolkit identifier
 *
 * Migration policy:
 *   - load() reads .age FIRST. Falls back to .json when .age missing.
 *   - .json fallback emits MIGRATION_PENDING beacon to auditLogPath.
 *   - save() writes .age via SecretStoreAge.encrypt(). Does NOT auto-delete .json
 *     — explicit migration script handles cleanup after grace period.
 */

import {
  appendFileSync,
  existsSync,
  mkdirSync,
  readFileSync,
} from 'node:fs';
import { dirname, join } from 'node:path';
import * as os from 'node:os';

import type { SecretStoreAge } from './secret-store-age.js';
import { CredentialNotFoundError } from './errors.js';

// ---------------------------------------------------------------------------
// Discriminated union — credential bundles per connector kind
// ---------------------------------------------------------------------------

export interface SlackPatBundle {
  readonly kind: 'slack-pat';
  readonly token: string;
  readonly obtained_at: number;
}

export interface GmailOAuthBundle {
  readonly kind: 'gmail-oauth';
  readonly clientId: string;
  readonly clientSecret: string;
  readonly accessToken: string;
  readonly refreshToken: string;
  readonly expiresAt: number;
  readonly obtained_at: number;
}

export interface ComposioToolkitBundle {
  readonly kind: 'composio';
  readonly toolkit: string;
  readonly obtained_at: number;
}

export type CredentialBundle =
  | SlackPatBundle
  | GmailOAuthBundle
  | ComposioToolkitBundle;

// ---------------------------------------------------------------------------
// Loader options + class
// ---------------------------------------------------------------------------

export interface CredentialLoaderOpts {
  readonly secretStore: SecretStoreAge;
  readonly keyDir?: string;
  readonly auditLogPath?: string;
  readonly signal?: AbortSignal;
}

const DEFAULT_KEY_DIR = join(os.homedir(), '.sutra-connectors', 'oauth');
const DEFAULT_AUDIT_LOG_PATH = '.enforcement/connector-audit.jsonl';

export class CredentialLoader {
  readonly #secretStore: SecretStoreAge;
  readonly #keyDir: string;
  readonly #auditLogPath: string;
  readonly #signal: AbortSignal | undefined;

  constructor(opts: CredentialLoaderOpts) {
    if (!opts || typeof opts !== 'object') {
      throw new Error('CredentialLoader: opts required');
    }
    if (!opts.secretStore || typeof opts.secretStore.decrypt !== 'function') {
      throw new Error('CredentialLoader: opts.secretStore (SecretStoreAge) required');
    }
    this.#secretStore = opts.secretStore;
    this.#keyDir = opts.keyDir ?? DEFAULT_KEY_DIR;
    this.#auditLogPath = opts.auditLogPath ?? DEFAULT_AUDIT_LOG_PATH;
    this.#signal = opts.signal;
  }

  // -------------------------------------------------------------------------
  // load — returns parsed bundle from .age (preferred) or .json (fallback)
  // -------------------------------------------------------------------------
  async load(connector_name: string): Promise<CredentialBundle> {
    if (typeof connector_name !== 'string' || connector_name.length === 0) {
      throw new Error('CredentialLoader.load: connector_name required');
    }
    const agePath = join(this.#keyDir, `${connector_name}.age`);
    const jsonPath = join(this.#keyDir, `${connector_name}.json`);

    // 1. Try .age FIRST
    if (existsSync(agePath)) {
      const decryptOpts =
        this.#signal !== undefined ? { signal: this.#signal } : {};
      const cleartext = await this.#secretStore.decrypt(agePath, decryptOpts);
      return JSON.parse(cleartext.toString('utf8')) as CredentialBundle;
    }

    // 2. Fall back to .json plaintext (migration window)
    if (existsSync(jsonPath)) {
      this.#emitMigrationBeacon(connector_name, jsonPath);
      const cleartext = readFileSync(jsonPath, 'utf8');
      return JSON.parse(cleartext) as CredentialBundle;
    }

    // 3. Neither present — throw
    throw new CredentialNotFoundError(connector_name);
  }

  // -------------------------------------------------------------------------
  // save — encrypts bundle JSON via secret-store-age to <keyDir>/<connector>.age
  //   - does NOT auto-delete .json on save (explicit migration script does)
  // -------------------------------------------------------------------------
  async save(connector_name: string, bundle: CredentialBundle): Promise<void> {
    if (typeof connector_name !== 'string' || connector_name.length === 0) {
      throw new Error('CredentialLoader.save: connector_name required');
    }
    if (!bundle || typeof bundle !== 'object' || typeof bundle.kind !== 'string') {
      throw new Error('CredentialLoader.save: bundle must be a CredentialBundle');
    }
    const agePath = join(this.#keyDir, `${connector_name}.age`);
    const plaintext = Buffer.from(JSON.stringify(bundle), 'utf8');
    const encryptOpts =
      this.#signal !== undefined ? { signal: this.#signal } : {};
    await this.#secretStore.encrypt(agePath, plaintext, encryptOpts);
    // NB: do NOT auto-delete the legacy .json — migration script owns cleanup
    // after the grace period (per spec §M1.8 + §5).
  }

  // -------------------------------------------------------------------------
  // private — append MIGRATION_PENDING audit beacon
  //   Best-effort: ensure parent dir exists (matches secret-store-age sutra_safe_write
  //   ergonomics); swallow append errors so a missing audit log never crashes
  //   credential reads.
  // -------------------------------------------------------------------------
  #emitMigrationBeacon(connector: string, jsonPath: string): void {
    const event = {
      ts: Date.now(),
      event: 'MIGRATION_PENDING',
      connector,
      path: jsonPath,
      msg: `plaintext .json read; migrate to .age via 'sutra connect ${connector}'`,
    };
    try {
      const parent = dirname(this.#auditLogPath);
      if (parent.length > 0 && !existsSync(parent)) {
        mkdirSync(parent, { recursive: true });
      }
      appendFileSync(this.#auditLogPath, JSON.stringify(event) + '\n');
    } catch {
      // Beacon best-effort — never crash a credential load on audit write failure.
    }
  }
}
