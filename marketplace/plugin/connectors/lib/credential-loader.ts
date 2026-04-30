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
 *   - SlackBotBundle        type='slack-bot'    token (xoxb-/xoxp-)
 *   - GmailOAuthBundle      type='gmail-oauth'  full OAuth state + refresh
 *   - ComposioToolkitBundle type='composio'     toolkit identifier
 *
 * Migration policy:
 *   - load() reads .age FIRST. Falls back to .json when .age missing.
 *   - .json fallback emits MIGRATION_PENDING beacon to auditLogPath.
 *   - save() writes .age via SecretStoreAge.encrypt(). Does NOT auto-delete .json
 *     — explicit migration script handles cleanup after grace period.
 */

import {
  appendFileSync,
  closeSync,
  existsSync,
  fsyncSync,
  lstatSync,
  mkdirSync,
  openSync,
  readFileSync,
  renameSync,
  writeSync,
} from 'node:fs';
import { constants as fsConstants } from 'node:fs';
import { dirname, join } from 'node:path';
import * as os from 'node:os';

const { O_WRONLY, O_CREAT, O_EXCL, O_NOFOLLOW } = fsConstants;

import type { SecretStoreAge } from './secret-store-age.js';
import { CredentialNotFoundError } from './errors.js';

// ---------------------------------------------------------------------------
// Discriminated union — credential bundles per connector type.
//
// IMPORTANT: discriminator field is `type` (NOT `kind`) and values match the
// shipped backend contracts in lib/backends/*.ts so that credentials saved
// through CredentialLoader stay compatible with existing call.mjs +
// verify-connection.mjs consumers that hard-check `cred.type`.
//
// Shipped contracts (verbatim):
//   - slack-direct.ts: { type: 'slack-bot', token: string }
//   - gmail-direct.ts: { type: 'gmail-oauth', clientId, clientSecret, accessToken, refreshToken, expiresAt }
//
// `obtained_at` is added by the loader for audit/forensics; callers can
// ignore it unless they need it.
// ---------------------------------------------------------------------------

export interface SlackBotBundle {
  readonly type: 'slack-bot';
  readonly token: string;
  readonly obtained_at: number;
}

export interface GmailOAuthBundle {
  readonly type: 'gmail-oauth';
  readonly clientId: string;
  readonly clientSecret: string;
  readonly accessToken: string;
  readonly refreshToken: string;
  readonly expiresAt: number;
  readonly obtained_at: number;
}

export interface ComposioToolkitBundle {
  readonly type: 'composio';
  readonly toolkit: string;
  readonly obtained_at: number;
}

export type CredentialBundle =
  | SlackBotBundle
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
  //   AND dual-writes <keyDir>/<connector>.json plaintext during the migration
  //   window so existing consumers (scripts/call.mjs + verify-connection.mjs)
  //   that read .json directly stay functional until Wave 5 (M1.10) migrates
  //   them onto CredentialLoader.load().
  //
  // Migration policy (per spec §M1.8 + §5):
  //   - Wave 3 (this file)  : save() dual-writes .age + .json
  //   - Wave 5 (M1.10)      : connect.sh + verify-connection.mjs use loader
  //   - Wave 6 (M1.11)      : call.mjs reroutes through Router
  //   - M2 polish           : drop .json writer once all consumers on .age
  //
  // The .json path uses the same atomic-write + symlink-refusal discipline
  // as secret-store-age (mirrors `sutra_safe_write` from privacy-sanitize.sh)
  // so it does not regress safety while the migration window is open.
  // -------------------------------------------------------------------------
  async save(connector_name: string, bundle: CredentialBundle): Promise<void> {
    if (typeof connector_name !== 'string' || connector_name.length === 0) {
      throw new Error('CredentialLoader.save: connector_name required');
    }
    if (!bundle || typeof bundle !== 'object' || typeof bundle.type !== 'string') {
      throw new Error('CredentialLoader.save: bundle must be a CredentialBundle');
    }
    const agePath = join(this.#keyDir, `${connector_name}.age`);
    const jsonPath = join(this.#keyDir, `${connector_name}.json`);
    const plaintext = Buffer.from(JSON.stringify(bundle), 'utf8');
    const encryptOpts =
      this.#signal !== undefined ? { signal: this.#signal } : {};

    // 1. Encrypted .age write (canonical going forward)
    await this.#secretStore.encrypt(agePath, plaintext, encryptOpts);

    // 2. Migration-window .json write (atomic + symlink-safe; same discipline
    //    as sutra_safe_write).
    this.#writeJsonShadow(jsonPath, plaintext);
  }

  // -------------------------------------------------------------------------
  // private — atomic + symlink-safe .json write for migration shadow path
  //   Mirrors sutra_safe_write semantics from plugin/lib/privacy-sanitize.sh:
  //     - lstat target; refuse symlink
  //     - lstat parent; refuse symlinked parent
  //     - mkdir parent recursive 0o700
  //     - openSync EXCL + NOFOLLOW + 0o600
  //     - fsync, atomic rename
  // -------------------------------------------------------------------------
  #writeJsonShadow(target: string, plaintext: Buffer): void {
    if (existsSync(target)) {
      const st = lstatSync(target);
      if (st.isSymbolicLink()) {
        throw new Error(`CredentialLoader.save: refusing symlink target: ${target}`);
      }
    }
    const parent = dirname(target);
    if (existsSync(parent)) {
      const ps = lstatSync(parent);
      if (ps.isSymbolicLink()) {
        throw new Error(`CredentialLoader.save: refusing symlinked parent: ${parent}`);
      }
    }
    mkdirSync(parent, { recursive: true, mode: 0o700 });
    const tmp = `${target}.tmp.${process.pid}`;
    const flags =
      // eslint-disable-next-line no-bitwise
      O_WRONLY | O_CREAT | O_EXCL | (O_NOFOLLOW ?? 0);
    const fd = openSync(tmp, flags, 0o600);
    try {
      writeSync(fd, plaintext);
      fsyncSync(fd);
    } finally {
      closeSync(fd);
    }
    renameSync(tmp, target);
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
