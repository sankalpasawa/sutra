"""Schema. Design 02 §2.3, verbatim in intent.

Written for SQLite; every construct survives a copy-paste port to PostgreSQL.
The PG deltas are recorded in the design doc, not guessed at here.
"""

MIGRATIONS = [
("001_operators", """
CREATE TABLE IF NOT EXISTS operators (
  id          TEXT PRIMARY KEY,
  handle      TEXT NOT NULL UNIQUE,
  created_at  TEXT NOT NULL,
  updated_at  TEXT NOT NULL
);
"""),

("002_connectors", """
CREATE TABLE IF NOT EXISTS connectors (
  id                     TEXT PRIMARY KEY,
  operator_id            TEXT NOT NULL REFERENCES operators(id) ON DELETE CASCADE,
  provider               TEXT NOT NULL,
  provider_account_id    TEXT NOT NULL,
  provider_account_node  TEXT,
  provider_username      TEXT NOT NULL,
  display_name           TEXT,
  avatar_url             TEXT,
  account_type           TEXT NOT NULL DEFAULT 'user',
  label                  TEXT,
  status                 TEXT NOT NULL
                           CHECK (status IN ('PENDING','ACTIVE','ERROR',
                                             'REAUTH_REQUIRED','DISCONNECTED')),
  status_reason          TEXT,
  api_base               TEXT NOT NULL DEFAULT 'https://api.github.com',
  created_at             TEXT NOT NULL,
  updated_at             TEXT NOT NULL,
  last_used_at           TEXT,
  last_validated_at      TEXT,
  disconnected_at        TEXT,
  UNIQUE (operator_id, provider, provider_account_id)
);
CREATE INDEX IF NOT EXISTS idx_conn_operator_active
  ON connectors(operator_id, provider) WHERE disconnected_at IS NULL;
CREATE INDEX IF NOT EXISTS idx_conn_status
  ON connectors(status) WHERE status <> 'DISCONNECTED';
"""),

("003_connector_credentials", """
-- Local mode stores NO secret material here. The Keychain does.
-- Hosted mode populates the ciphertext columns and leaves keychain_ref NULL.
CREATE TABLE IF NOT EXISTS connector_credentials (
  connector_id        TEXT PRIMARY KEY REFERENCES connectors(id) ON DELETE CASCADE,
  credential_type     TEXT NOT NULL
                        CHECK (credential_type IN ('user_to_server','installation','pat')),
  keychain_ref        TEXT,
  access_token_enc    BLOB,
  refresh_token_enc   BLOB,
  dek_wrapped         BLOB,
  kms_key_id          TEXT,
  encryption_version  INTEGER NOT NULL DEFAULT 1,
  access_expires_at   TEXT,
  refresh_expires_at  TEXT,
  rotated_at          TEXT,
  created_at          TEXT NOT NULL,
  updated_at          TEXT NOT NULL,
  CHECK (keychain_ref IS NOT NULL OR access_token_enc IS NOT NULL)
);
"""),

("004_connector_scopes", """
CREATE TABLE IF NOT EXISTS connector_scopes (
  id            INTEGER PRIMARY KEY,
  connector_id  TEXT NOT NULL REFERENCES connectors(id) ON DELETE CASCADE,
  scope         TEXT NOT NULL,
  source        TEXT NOT NULL CHECK (source IN ('installation','oauth_scope')),
  granted_at    TEXT NOT NULL,
  UNIQUE (connector_id, scope)
);
"""),

("005_connector_installations", """
CREATE TABLE IF NOT EXISTS connector_installations (
  id                    INTEGER PRIMARY KEY,
  connector_id          TEXT NOT NULL REFERENCES connectors(id) ON DELETE CASCADE,
  installation_id       INTEGER NOT NULL,
  account_login         TEXT NOT NULL,
  account_id            INTEGER NOT NULL,
  account_type          TEXT NOT NULL,
  repository_selection  TEXT NOT NULL CHECK (repository_selection IN ('all','selected')),
  permissions_json      TEXT NOT NULL,
  suspended_at          TEXT,
  sso_required          INTEGER NOT NULL DEFAULT 0,
  synced_at             TEXT NOT NULL,
  UNIQUE (connector_id, installation_id)
);
"""),

("006_connector_metadata", """
CREATE TABLE IF NOT EXISTS connector_metadata (
  id            INTEGER PRIMARY KEY,
  connector_id  TEXT NOT NULL REFERENCES connectors(id) ON DELETE CASCADE,
  kind          TEXT NOT NULL,
  external_id   TEXT NOT NULL,
  payload_json  TEXT NOT NULL,
  etag          TEXT,
  fetched_at    TEXT NOT NULL,
  expires_at    TEXT NOT NULL,
  UNIQUE (connector_id, kind, external_id)
);
CREATE INDEX IF NOT EXISTS idx_meta_kind
  ON connector_metadata(connector_id, kind, expires_at);
"""),

("007_oauth_transactions", """
CREATE TABLE IF NOT EXISTS oauth_transactions (
  id                 TEXT PRIMARY KEY,
  operator_id        TEXT NOT NULL REFERENCES operators(id) ON DELETE CASCADE,
  provider           TEXT NOT NULL,
  strategy           TEXT NOT NULL CHECK (strategy IN ('device','web_pkce')),
  state_hash         TEXT,
  code_verifier_enc  BLOB,
  device_code_enc    BLOB,
  redirect_uri       TEXT,
  requested_scopes   TEXT,
  reconnect_of       TEXT REFERENCES connectors(id),
  status             TEXT NOT NULL
                       CHECK (status IN ('CREATED','AUTHORIZATION_STARTED','CALLBACK_RECEIVED',
                                         'CODE_EXCHANGED','CONNECTOR_CREATED','COMPLETED',
                                         'EXPIRED','CANCELLED','FAILED','REJECTED')),
  failure_code       TEXT,
  connector_id       TEXT REFERENCES connectors(id),
  poll_interval      INTEGER NOT NULL DEFAULT 5,
  created_at         TEXT NOT NULL,
  expires_at         TEXT NOT NULL,
  completed_at       TEXT
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_tx_state
  ON oauth_transactions(state_hash) WHERE state_hash IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_tx_sweep ON oauth_transactions(status, expires_at);
"""),

("008_approval_grants", """
CREATE TABLE IF NOT EXISTS approval_grants (
  id              TEXT PRIMARY KEY,
  operator_id     TEXT NOT NULL REFERENCES operators(id) ON DELETE CASCADE,
  connector_id    TEXT NOT NULL REFERENCES connectors(id) ON DELETE CASCADE,
  agent_id        TEXT NOT NULL,
  session_id      TEXT NOT NULL,
  capability      TEXT NOT NULL,
  resource        TEXT NOT NULL,
  operation_hash  TEXT NOT NULL,
  decision        TEXT NOT NULL CHECK (decision IN ('GRANTED','DENIED')),
  decided_at      TEXT NOT NULL,
  expires_at      TEXT NOT NULL,
  consumed_at     TEXT,
  UNIQUE (operation_hash, session_id)
);
CREATE INDEX IF NOT EXISTS idx_grant_lookup
  ON approval_grants(connector_id, capability, expires_at);
"""),

("009_connector_events", """
CREATE TABLE IF NOT EXISTS connector_events (
  id            INTEGER PRIMARY KEY,
  operator_id   TEXT NOT NULL,
  connector_id  TEXT,
  agent_id      TEXT,
  session_id    TEXT,
  event_type    TEXT NOT NULL,
  resource      TEXT,
  operation     TEXT,
  result        TEXT NOT NULL
                  CHECK (result IN ('SUCCESS','DENIED','FAILED','PENDING_APPROVAL')),
  reason_code   TEXT,
  request_id    TEXT,
  detail_json   TEXT,
  occurred_at   TEXT NOT NULL,
  prev_hash     TEXT,
  row_hash      TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_events_conn
  ON connector_events(connector_id, occurred_at DESC);
CREATE INDEX IF NOT EXISTS idx_events_op
  ON connector_events(operator_id, occurred_at DESC);

-- Append-only, enforced by the database rather than by discipline.
CREATE TRIGGER IF NOT EXISTS connector_events_no_update
  BEFORE UPDATE ON connector_events
  BEGIN SELECT RAISE(ABORT, 'connector_events is append-only'); END;
CREATE TRIGGER IF NOT EXISTS connector_events_no_delete
  BEFORE DELETE ON connector_events
  BEGIN SELECT RAISE(ABORT, 'connector_events is append-only'); END;
"""),

("010_transaction_label", """
-- The connector label is chosen at begin_connect and consumed at poll_connect,
-- which may be a DIFFERENT PROCESS (the begin/poll CLI split). Holding it in
-- memory silently dropped it. Transaction state belongs in the transaction row.
ALTER TABLE oauth_transactions ADD COLUMN label TEXT;
"""),

("011_strategy_loopback", """
-- The strategy CHECK listed only the two flows GitHub needed. Slack has no
-- device flow and no PKCE, so its redirect flow is plain loopback -- a third
-- name, and one the constraint rejected outright. SQLite cannot alter a CHECK
-- in place, so the column is rebuilt.
ALTER TABLE oauth_transactions RENAME TO oauth_transactions_old;

CREATE TABLE oauth_transactions (
  id                 TEXT PRIMARY KEY,
  operator_id        TEXT NOT NULL REFERENCES operators(id) ON DELETE CASCADE,
  provider           TEXT NOT NULL,
  strategy           TEXT NOT NULL
                       CHECK (strategy IN ('device','web_pkce','loopback')),
  state_hash         TEXT,
  code_verifier_enc  BLOB,
  device_code_enc    BLOB,
  redirect_uri       TEXT,
  requested_scopes   TEXT,
  reconnect_of       TEXT REFERENCES connectors(id),
  status             TEXT NOT NULL
                       CHECK (status IN ('CREATED','AUTHORIZATION_STARTED','CALLBACK_RECEIVED',
                                         'CODE_EXCHANGED','CONNECTOR_CREATED','COMPLETED',
                                         'EXPIRED','CANCELLED','FAILED','REJECTED')),
  failure_code       TEXT,
  connector_id       TEXT REFERENCES connectors(id),
  poll_interval      INTEGER NOT NULL DEFAULT 5,
  label              TEXT,
  created_at         TEXT NOT NULL,
  expires_at         TEXT NOT NULL,
  completed_at       TEXT
);

INSERT INTO oauth_transactions
  SELECT id, operator_id, provider, strategy, state_hash, code_verifier_enc,
         device_code_enc, redirect_uri, requested_scopes, reconnect_of, status,
         failure_code, connector_id, poll_interval, label, created_at,
         expires_at, completed_at
  FROM oauth_transactions_old;

DROP TABLE oauth_transactions_old;

CREATE UNIQUE INDEX IF NOT EXISTS idx_tx_state
  ON oauth_transactions(state_hash) WHERE state_hash IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_tx_sweep ON oauth_transactions(status, expires_at);
"""),
]
