# 2 · Data Model, Lifecycle, Credentials

Covers deliverables **6 (connector lifecycle), 7 (database schema), 8 (credential architecture)**.

---

## 2.1 Connector lifecycle

```
                    ┌──────────┐
   authorize ──────►│ PENDING  │  transaction open, no credential yet
                    └────┬─────┘
        transaction COMPLETED │        ┌──────────────┐
                    ┌────▼─────┐       │    ERROR     │ provider fault / our fault
                    │  ACTIVE  │◄─────►│ (transient)  │ retryable, credential intact
                    └──┬────┬──┘       └──────────────┘
        401 / revoked  │    │  refresh token expired (6 mo idle)
        SSO required   │    │
                    ┌──▼────▼──────────┐
                    │ REAUTH_REQUIRED  │  credential kept, unusable
                    └────────┬─────────┘
       user reconnects       │  ──► back to ACTIVE (same connector row, same id)
                    ┌────────▼─────────┐
                    │  DISCONNECTED    │  terminal; credential destroyed, row retained
                    └──────────────────┘
```

`EXPIRED` from the founder's list is **not** a distinct state. An 8-hour access token expiring is normal operation handled by refresh, invisible to the UI. Only *refresh* failure is a state change, and its state is `REAUTH_REQUIRED`. Modelling routine expiry as a connector state would show the user a scary status eight times a day for nothing.

| State | UI representation | Agent tools | User action offered |
|---|---|---|---|
| `PENDING` | `◐ Connecting…` + the device `user_code`, copyable, with the countdown | blocked | Cancel |
| `ACTIVE` | `● Connected as octocat` + repo/org counts | allowed per policy | Manage · Disconnect |
| `ERROR` | `▲ GitHub unreachable — retrying` + last success time | blocked, retried | Retry now |
| `REAUTH_REQUIRED` | `▲ Reconnect needed — <specific reason>` | blocked | **Reconnect** (primary) · Disconnect |
| `DISCONNECTED` | `○ Not connected` | none | Connect |

The `REAUTH_REQUIRED` reason must be specific, because the four causes need four different user actions: *"your authorisation was revoked on GitHub"* / *"this org requires SAML sign-in"* / *"Sutra needs an extra permission"* / *"you were removed from this organisation."* A generic "reconnect" makes three of those a dead end.

---

## 2.2 OAuth transaction

An explicit, server-side, short-lived, single-use record — never global login state.

```
CREATED ─► AUTHORIZATION_STARTED ─► CALLBACK_RECEIVED ─► CODE_EXCHANGED ─► CONNECTOR_CREATED ─► COMPLETED
   └──────────────┴─────────────────────────┴──────────────┴─► EXPIRED | CANCELLED | FAILED | REJECTED
```

(`CALLBACK_RECEIVED` is skipped in device flow — polling replaces it. The state is retained so both strategies share one FSM.)

| Property | How it is achieved |
|---|---|
| Unpredictable | `secrets.token_urlsafe(32)` — 256 bits from the OS CSPRNG |
| Single-use | Redemption is `UPDATE … WHERE status='AUTHORIZATION_STARTED'` and requires `rowcount == 1`. A replay updates 0 rows and is rejected. |
| Short-lived | `expires_at = now + 10 min`; a sweeper marks `EXPIRED`; validation checks the clock as well as the status |
| Server-side | Row in `oauth_transactions`. `state` is stored as **SHA-256 only** — a database read cannot reconstruct a live state value |
| Destroyed on success | `COMPLETED` nulls `state_hash`, `code_verifier_enc`, `device_code_enc`. The row survives for audit; its secrets do not |
| Bound to an operator | `operator_id` is taken from the authenticated session at creation and re-checked at redemption. A transaction cannot be completed by a different operator. |

---

## 2.3 Schema

Written for SQLite (local, v1). Every construct is chosen to survive a copy-paste port to PostgreSQL; the PG deltas are noted after each table.

```sql
-- ─── 001_operators.sql ───────────────────────────────────────────
-- Sutra's own identity. Deliberately thin: connectors must not
-- depend on how Sutra authenticates people (see 01-architecture §1.3).
CREATE TABLE operators (
  id            TEXT PRIMARY KEY,             -- PG: UUID DEFAULT gen_random_uuid()
  handle        TEXT NOT NULL UNIQUE,
  created_at    TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  updated_at    TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);

-- ─── 002_connectors.sql ──────────────────────────────────────────
CREATE TABLE connectors (
  id                     TEXT PRIMARY KEY,
  operator_id            TEXT NOT NULL REFERENCES operators(id) ON DELETE CASCADE,
  provider               TEXT NOT NULL,           -- 'github'
  provider_account_id    TEXT NOT NULL,           -- GitHub numeric user id — STABLE
  provider_account_node  TEXT,                    -- GraphQL node_id
  provider_username      TEXT NOT NULL,           -- MUTABLE: display only, never a key
  display_name           TEXT,
  avatar_url             TEXT,
  account_type           TEXT NOT NULL DEFAULT 'user'  -- user | enterprise_user
                           CHECK (account_type IN ('user','enterprise_user')),
  label                  TEXT,                    -- user-assigned: "work", "personal"
  status                 TEXT NOT NULL
                           CHECK (status IN ('PENDING','ACTIVE','ERROR',
                                             'REAUTH_REQUIRED','DISCONNECTED')),
  status_reason          TEXT,                    -- REVOKED | SSO_REQUIRED | SCOPE_INSUFFICIENT
                                                  -- | REFRESH_EXPIRED | ORG_ACCESS_REMOVED
  api_base               TEXT NOT NULL DEFAULT 'https://api.github.com',  -- GHES support
  created_at             TEXT NOT NULL,
  updated_at             TEXT NOT NULL,
  last_used_at           TEXT,
  last_validated_at      TEXT,
  disconnected_at        TEXT,                    -- soft delete
  UNIQUE (operator_id, provider, provider_account_id)
);
CREATE INDEX idx_conn_operator_active ON connectors(operator_id, provider)
  WHERE disconnected_at IS NULL;   -- PG: identical partial index
CREATE INDEX idx_conn_status ON connectors(status) WHERE status <> 'DISCONNECTED';
```

**On `UNIQUE(operator_id, provider, provider_account_id)`** — yes, and it is the specific defence against the §25 hazard. Reconnecting account A must find the existing row and rotate its credential; connecting account B must insert a second row. Keying on `provider_username` instead would silently merge two people the moment someone renames on GitHub, and would fail to reunite a user with their own connector after a rename. GitHub's numeric `id` is immutable and is the only correct key (see `03-github-integration.md §3.3`).

Note the unique constraint deliberately does **not** exclude soft-deleted rows: reconnecting after a disconnect reuses the same connector id, so history, audit rows and grants remain attached to one continuous relationship.

```sql
-- ─── 003_connector_credentials.sql ───────────────────────────────
-- Local mode: this table holds NO secret material. The Keychain does.
-- Hosted mode: ciphertext columns are populated and the ref is NULL.
CREATE TABLE connector_credentials (
  connector_id           TEXT PRIMARY KEY REFERENCES connectors(id) ON DELETE CASCADE,
  credential_type        TEXT NOT NULL
                           CHECK (credential_type IN ('user_to_server','installation','pat')),
  keychain_ref           TEXT,                    -- local: "sutra.connector.<id>"
  access_token_enc       BLOB,                    -- hosted: KMS-envelope ciphertext
  refresh_token_enc      BLOB,
  dek_wrapped            BLOB,                    -- hosted: DEK wrapped by the KMS CMK
  kms_key_id             TEXT,                    -- which CMK — needed for rotation
  encryption_version     INTEGER NOT NULL DEFAULT 1,
  access_expires_at      TEXT,                    -- ~ now + 8h  (F5)
  refresh_expires_at     TEXT,                    -- ~ now + 6mo (F5)
  rotated_at             TEXT,
  created_at             TEXT NOT NULL,
  updated_at             TEXT NOT NULL,
  CHECK (keychain_ref IS NOT NULL OR access_token_enc IS NOT NULL)
);

-- ─── 004_connector_scopes.sql ────────────────────────────────────
-- What GITHUB granted. Provider truth, refreshed on validate.
CREATE TABLE connector_scopes (
  id            INTEGER PRIMARY KEY,          -- PG: BIGSERIAL
  connector_id  TEXT NOT NULL REFERENCES connectors(id) ON DELETE CASCADE,
  scope         TEXT NOT NULL,                -- 'contents:write', 'pull_requests:write'
  source        TEXT NOT NULL
                  CHECK (source IN ('installation','oauth_scope')),
  granted_at    TEXT NOT NULL,
  UNIQUE (connector_id, scope)
);

-- ─── 005_connector_capabilities.sql ──────────────────────────────
-- What WE authorise (≠ scopes). See 04-capabilities-agent.md.
CREATE TABLE connector_capabilities (
  id            INTEGER PRIMARY KEY,
  connector_id  TEXT NOT NULL REFERENCES connectors(id) ON DELETE CASCADE,
  capability    TEXT NOT NULL,                -- 'github.repository.contents.read'
  mode          TEXT NOT NULL
                  CHECK (mode IN ('AUTO','ASK_USER','DENY')),
  resource      TEXT NOT NULL DEFAULT '*',    -- '*' | 'my-org/*' | 'my-org/my-repo'
  granted_by    TEXT NOT NULL
                  CHECK (granted_by IN ('user','default_policy','admin')),
  created_at    TEXT NOT NULL,
  UNIQUE (connector_id, capability, resource)
);
CREATE INDEX idx_cap_lookup ON connector_capabilities(connector_id, capability);

-- ─── 006_connector_installations.sql ─────────────────────────────
-- GitHub App only: one row per org/user installation reachable by this connector.
CREATE TABLE connector_installations (
  id                    INTEGER PRIMARY KEY,
  connector_id          TEXT NOT NULL REFERENCES connectors(id) ON DELETE CASCADE,
  installation_id       INTEGER NOT NULL,      -- GitHub's id
  account_login         TEXT NOT NULL,
  account_id            INTEGER NOT NULL,
  account_type          TEXT NOT NULL,         -- 'Organization' | 'User'
  repository_selection  TEXT NOT NULL
                          CHECK (repository_selection IN ('all','selected')),
  permissions_json      TEXT NOT NULL,         -- PG: JSONB
  suspended_at          TEXT,
  sso_required          INTEGER NOT NULL DEFAULT 0,
  synced_at             TEXT NOT NULL,
  UNIQUE (connector_id, installation_id)
);

-- ─── 007_connector_metadata.sql ──────────────────────────────────
-- Cached provider objects. Disposable by construction: dropping this
-- table must cost a refetch and nothing else.
CREATE TABLE connector_metadata (
  id            INTEGER PRIMARY KEY,
  connector_id  TEXT NOT NULL REFERENCES connectors(id) ON DELETE CASCADE,
  kind          TEXT NOT NULL,                -- 'repository' | 'organization' | 'branch'
  external_id   TEXT NOT NULL,                -- GitHub numeric id as text
  payload_json  TEXT NOT NULL,                -- PG: JSONB
  etag          TEXT,                         -- conditional requests (07-operations §7.2)
  fetched_at    TEXT NOT NULL,
  expires_at    TEXT NOT NULL,
  UNIQUE (connector_id, kind, external_id)
);
CREATE INDEX idx_meta_kind ON connector_metadata(connector_id, kind, expires_at);

-- ─── 008_oauth_transactions.sql ──────────────────────────────────
CREATE TABLE oauth_transactions (
  id                  TEXT PRIMARY KEY,
  operator_id         TEXT NOT NULL REFERENCES operators(id) ON DELETE CASCADE,
  provider            TEXT NOT NULL,
  strategy            TEXT NOT NULL CHECK (strategy IN ('device','web_pkce')),
  state_hash          TEXT,                   -- SHA-256(state). NULL after completion.
  code_verifier_enc   BLOB,                   -- web_pkce only. NULL after completion.
  device_code_enc     BLOB,                   -- device only.    NULL after completion.
  redirect_uri        TEXT,                   -- web_pkce only, exact-match validated
  requested_scopes    TEXT,
  reconnect_of        TEXT REFERENCES connectors(id),  -- set when re-authorising
  status              TEXT NOT NULL
                        CHECK (status IN ('CREATED','AUTHORIZATION_STARTED','CALLBACK_RECEIVED',
                                          'CODE_EXCHANGED','CONNECTOR_CREATED','COMPLETED',
                                          'EXPIRED','CANCELLED','FAILED','REJECTED')),
  failure_code        TEXT,
  connector_id        TEXT REFERENCES connectors(id),
  created_at          TEXT NOT NULL,
  expires_at          TEXT NOT NULL,
  completed_at        TEXT
);
CREATE UNIQUE INDEX idx_tx_state ON oauth_transactions(state_hash)
  WHERE state_hash IS NOT NULL;
CREATE INDEX idx_tx_sweep ON oauth_transactions(status, expires_at);

-- ─── 009_approval_grants.sql ─────────────────────────────────────
-- One grant authorises exactly ONE operation. See 04 §4.6.
CREATE TABLE approval_grants (
  id               TEXT PRIMARY KEY,
  operator_id      TEXT NOT NULL REFERENCES operators(id) ON DELETE CASCADE,
  connector_id     TEXT NOT NULL REFERENCES connectors(id) ON DELETE CASCADE,
  agent_id         TEXT NOT NULL,
  session_id       TEXT NOT NULL,
  capability       TEXT NOT NULL,
  resource         TEXT NOT NULL,             -- 'my-org/my-repo'
  operation_hash   TEXT NOT NULL,             -- SHA-256 of canonicalised tool args
  decision         TEXT NOT NULL CHECK (decision IN ('GRANTED','DENIED')),
  decided_at       TEXT NOT NULL,
  expires_at       TEXT NOT NULL,             -- ≤ 5 min
  consumed_at      TEXT,                      -- single-use
  UNIQUE (operation_hash, session_id)
);
CREATE INDEX idx_grant_lookup ON approval_grants(connector_id, capability, expires_at);

-- ─── 010_connector_events.sql ────────────────────────────────────
-- Append-only. No UPDATE, no DELETE — enforced by trigger AND by grant.
CREATE TABLE connector_events (
  id             INTEGER PRIMARY KEY,          -- PG: BIGSERIAL
  operator_id    TEXT NOT NULL,
  connector_id   TEXT,
  agent_id       TEXT,
  session_id     TEXT,
  event_type     TEXT NOT NULL,                -- CONNECTOR_CREATED, PULL_REQUEST_CREATED, …
  resource       TEXT,
  operation      TEXT,
  result         TEXT NOT NULL CHECK (result IN ('SUCCESS','DENIED','FAILED','PENDING_APPROVAL')),
  reason_code    TEXT,
  request_id     TEXT,
  detail_json    TEXT,                         -- NEVER credential material
  occurred_at    TEXT NOT NULL,
  prev_hash      TEXT,                         -- hash chain: tamper-evidence
  row_hash       TEXT NOT NULL
);
CREATE INDEX idx_events_conn ON connector_events(connector_id, occurred_at DESC);
CREATE INDEX idx_events_op   ON connector_events(operator_id, occurred_at DESC);

CREATE TRIGGER connector_events_no_update
  BEFORE UPDATE ON connector_events
  BEGIN SELECT RAISE(ABORT, 'connector_events is append-only'); END;
CREATE TRIGGER connector_events_no_delete
  BEFORE DELETE ON connector_events
  BEGIN SELECT RAISE(ABORT, 'connector_events is append-only'); END;
```

**PostgreSQL deltas**: `TEXT`→`UUID` for ids, `TEXT` timestamps→`TIMESTAMPTZ`, `INTEGER PRIMARY KEY`→`BIGSERIAL`, `*_json`→`JSONB`, `BLOB`→`BYTEA`, triggers→`REVOKE UPDATE, DELETE ON connector_events FROM app_role` plus row-level security keyed on `operator_id`. The RLS policy is the hosted deployment's structural defence against T-11 (cross-user access) and should be added the day Postgres appears, not later.

### Soft deletion

`connectors` soft-delete (`disconnected_at`) so the id stays resolvable for audit rows that reference it. `connector_credentials` **hard**-delete — a disconnected connector must leave no credential material anywhere. `connector_events` never delete. `connector_metadata` and `approval_grants` hard-delete on disconnect.

---

## 2.4 Credential architecture

### Where credentials live — the recommendation

| Option | Verdict |
|---|---|
| Plaintext in PostgreSQL | Never. One backup, one log dump, one `SELECT *` in a support session and every user's GitHub is compromised. |
| App-level encrypted DB fields, key in env | Weak: the key travels with the app, appears in process listings and crash dumps, and rotating it means decrypting everything at once. Acceptable only as a stepping stone. |
| **OS keychain (local — chosen for v1)** | Encrypted at rest by the OS, ACL'd to our binary, excluded from ordinary file backups, and invisible to a `find` across the disk. Correct for a desktop-resident service. |
| **KMS envelope encryption over Postgres (hosted — chosen for v2)** | Per-connector DEK, wrapped by a KMS CMK the service can call but never read. A stolen database yields nothing without live KMS access, which is logged and revocable. |
| Dedicated vault (Vault / secrets manager) | Justified when connectors span services and need dynamic leasing. Over-built for one service; revisit at that point. |

Both chosen options sit behind one `CredentialStore` port, so no caller knows which is in use.

### Local: Keychain

```
Keychain item
  service : "com.sutra.connector"
  account : "<connector_id>"                     ← the only linkage
  value   : {"access_token": …, "refresh_token": …,
             "access_expires_at": …, "refresh_expires_at": …, "v": 1}
  access  : kSecAttrAccessibleWhenUnlockedThisDeviceOnly
```

`ThisDeviceOnly` is deliberate: it blocks iCloud Keychain sync, so a GitHub credential cannot silently propagate to another machine — that would be device sprawl with no connector row and no audit trail to match.

Windows and Linux adapters (DPAPI, libsecret) implement the same port. Where an OS keystore is genuinely unavailable, the fallback is an age-encrypted 0600 file with a key derived from a user passphrase — **not** an unencrypted file, and the UI must say which mode is active.

### Hosted: envelope encryption

```
      ┌──────────────────────────────────┐
      │ KMS CMK  (never leaves the HSM)  │
      └───────────────┬──────────────────┘
       Encrypt/Decrypt│  (IAM-scoped to the connector-service role only)
      ┌───────────────▼──────────────────┐
      │ DEK — one per connector, AES-256 │  wrapped form stored in dek_wrapped
      └───────────────┬──────────────────┘
      ┌───────────────▼──────────────────┐
      │ AES-256-GCM(token)               │  AAD = connector_id ‖ encryption_version
      │ → access_token_enc               │  binds ciphertext to its row: a swapped
      └──────────────────────────────────┘    row fails authentication, not decrypts
```

| Concern | Design |
|---|---|
| Key rotation (CMK) | KMS-scheduled. Rewrap DEKs in the background; `kms_key_id` per row makes it resumable and lets old and new coexist. |
| Credential rotation | Every refresh writes a new credential and destroys the old (F5: refresh tokens rotate on use). `rotated_at` records it. |
| Access policy | Only the connector-service role may call `kms:Decrypt`, and only on that CMK. Human operators are denied `Decrypt` outright, not merely discouraged. |
| Backups | Backups contain ciphertext + wrapped DEKs. Restoring a backup into an environment without the CMK yields nothing — this is the property that makes DB backups safe to hold. |
| Disaster recovery | CMK is multi-region with a documented restore drill. **A lost CMK is not recoverable and must be treated as total connector loss → all users re-auth.** That is the accepted cost of not holding key material ourselves. |
| Logging | The `Credential` type has `__repr__` / `__str__` / `__format__` overridden to `<Credential redacted>` and is excluded from serialisation. A test asserts a token value never appears in any log sink. |

### In-memory handling

Decrypted tokens exist only inside a request scope, are never attached to a response model, never enter a cache keyed by anything a caller supplies, and never cross into the renderer's process. `Credential` is not JSON-serialisable by construction — attempting it raises.

---

## 2.5 Reauthorization

Do **not** delete a connector on API failure. Classify first:

| Signal from GitHub | Cause | Connector state | User-facing action |
|---|---|---|---|
| `401` + refresh succeeds | routine 8h expiry | `ACTIVE` (no change) | none — invisible |
| `401` + refresh returns `bad_refresh_token` | 6-month idle expiry (F5) | `REAUTH_REQUIRED` / `REFRESH_EXPIRED` | Reconnect |
| `401` + `bad_credentials` on a fresh token | user revoked the app on GitHub | `REAUTH_REQUIRED` / `REVOKED` | Reconnect |
| `403` + `X-GitHub-SSO` header present | org requires SAML sign-in | `ACTIVE`; that org marked `sso_required` | "Authorise for <org>" deep link |
| `403` + rate-limit headers / `retry-after` | rate limited | `ACTIVE` | none — back off (`07 §7.1`) |
| `403`, no rate headers, no SSO | insufficient permission on this repo | `ACTIVE` | "Sutra doesn't have access to <repo>" + install link |
| `404` on a repo the user names | private repo not in the installation, or gone | `ACTIVE` | "Not accessible — add it to the Sutra installation" |
| `5xx` / timeout / DNS | GitHub outage or local network | `ERROR` (transient) | "Retrying" + status-page link |

Two mistakes this table exists to prevent: **treating every 403 as fatal** (three of the four 403 rows are non-fatal, and one is routine), and **treating a 404 as "repo does not exist"** — GitHub returns 404 rather than 403 for private resources you cannot see, so 404 frequently means *permission*, not *absence*.

Reconnect reuses the same connector row: same `id`, same capability grants, same history. Only the credential is replaced. A reconnect that returns a **different** `provider_account_id` is not a reconnect — it is a new connector, and the UI must say so rather than silently rebinding an existing row to a different human.

---

## 2.6 Disconnect

```
DELETE /connectors/github/{id}
   │
   ├─ 1. status → DISCONNECTED, disconnected_at = now   (stops new work immediately)
   ├─ 2. cancel in-flight operations for this connector
   ├─ 3. CredentialStore.delete() — Keychain item destroyed / ciphertext + DEK dropped
   ├─ 4. DELETE connector_metadata, approval_grants for this connector
   ├─ 5. best-effort provider revocation (see below)
   ├─ 6. audit CONNECTOR_DISCONNECTED (result reflects whether step 5 succeeded)
   └─ 7. connector row RETAINED (soft) so audit history stays resolvable
```

Order matters: local credential destruction (3) precedes remote revocation (5), so a network failure at the last step still leaves us holding nothing.

**Should we revoke on GitHub too?** Yes, attempted, and reported honestly.

| | Revoke remotely | Local-only delete |
|---|---|---|
| Access after disconnect | genuinely none | none from Sutra; the grant still exists on GitHub |
| Requires | `client_secret` — **hosted only (F2/F3)** | nothing |
| Local mode reality | cannot call the revocation endpoint | this is what we do |

So: hosted mode revokes remotely and reports it. **Local mode cannot**, and the disconnect confirmation must say so plainly — *"Sutra has deleted its copy of your GitHub credentials. To also remove Sutra's authorisation on GitHub, revoke it in your GitHub settings → [link]."* Claiming a revocation we did not perform would be the more comfortable copy and a lie.

---

## 2.7 Multiple GitHub accounts

| Concern | Design |
|---|---|
| Identification | `provider_account_id` = GitHub's immutable numeric user id. Never `login`. |
| Uniqueness | `UNIQUE(operator_id, provider, provider_account_id)`. Connecting B while A exists inserts; reconnecting A rotates in place. **The §25 overwrite hazard is structurally impossible.** |
| Disambiguation in UI | `label` (user-set: "work" / "personal") + `@login` + avatar. Never the connector UUID. |
| Repository selection | Repos are namespaced by connector. `my-org/my-repo` reachable through both connectors is two distinct rows; the UI shows which connector each result came from. |
| Agent context | Exactly one `connector_id` is bound per agent session. An agent that needs both accounts runs two sessions. No implicit fallback, no "try the other one" — that is a cross-account data path. |
| Credential isolation | One Keychain item / one DEK per connector. Compromise of one is not compromise of the other. |
| Ambiguous request | If the operator says "open a PR on acme/api" and two connectors can reach it, the **user** picks. The agent must not, and the system must not guess. |
