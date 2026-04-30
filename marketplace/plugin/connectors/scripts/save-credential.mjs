#!/usr/bin/env node
/**
 * Sutra Connectors — save-credential CLI (M1.10).
 *
 * Bridges connect.sh (Bash) → CredentialLoader.save() (TS).
 * Reads a bundle JSON file produced by connect.sh and writes it via the
 * loader, which dual-writes .age (encrypted) + .json (plaintext shadow)
 * using sutra_safe_write semantics.
 *
 * Usage: save-credential.mjs <connector> <bundle-json-path>
 *
 * Exit codes:
 *   0 — saved
 *   2 — bad args
 *   3 — bundle file unreadable
 *   4 — secret-store error
 */
import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { homedir } from 'node:os';

import { CredentialLoader, SecretStoreAge } from '../lib/index.js';
import { assertAgeAvailable } from './preflight-age.mjs';

// M2 step 2 — defense in depth: connect.sh's age-keypair check is upstream,
// but if save-credential.mjs is invoked directly we still want a clear error
// before SecretStoreAge tries to spawn age and fails opaquely.
assertAgeAvailable();

const [, , connector, bundlePath] = process.argv;

if (!connector || !bundlePath) {
  console.error('usage: save-credential.mjs <connector> <bundle-json-path>');
  process.exit(2);
}

let bundle;
try {
  const text = readFileSync(bundlePath, 'utf8');
  bundle = JSON.parse(text);
} catch (err) {
  console.error(`save-credential: cannot read ${bundlePath}: ${err?.message ?? err}`);
  process.exit(3);
}

if (!bundle || typeof bundle !== 'object' || typeof bundle.type !== 'string') {
  console.error('save-credential: bundle must have a string `type` discriminator');
  process.exit(2);
}

const keyDir = join(homedir(), '.sutra-connectors', 'keys');
const oauthDir = join(homedir(), '.sutra-connectors', 'oauth');
const store = new SecretStoreAge({
  identityPath: join(keyDir, 'sutra-identity.key'),
  recipientPath: join(keyDir, 'sutra-recipient.txt'),
});
const loader = new CredentialLoader({ secretStore: store, keyDir: oauthDir });

try {
  await loader.save(connector, bundle);
  console.log(`save-credential: saved ${connector} → ${oauthDir}/${connector}.{age,json}`);
} catch (err) {
  console.error(`save-credential: ${err?.message ?? err}`);
  process.exit(4);
}
