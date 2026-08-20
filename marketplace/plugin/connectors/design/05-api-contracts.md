# 5 · API Contracts

Covers deliverables **16 (backend API), 17 (desktop API)**.

---

## 5.1 Conventions

| Aspect | Rule |
|---|---|
| Base | local `http://127.0.0.1:7000/api/v1` · hosted `https://api.sutra.…/v1` |
| Caller auth | local: `Authorization: Bearer <per-launch token>` from the app bundle's 0700 dir, rotated every launch. hosted: operator session JWT |
| Origin defence | `Origin`/`Host` allow-list; CORS never `*`; `TrustedHostMiddleware` retained |
| Authorization | every route resolves `operator_id` from the session and filters by it in the query — never trusts a path id alone |
| Not-yours | **404**, never 403 (avoids an existence oracle) |
| Idempotency | mutating routes accept `Idempotency-Key`; replay returns the first result |
| Errors | one envelope, always |
| Rate limiting | per-operator and per-connector token buckets; 429 + `Retry-After` |
| Secrets | no route, in any deployment, at any status code, returns credential material |

```json
{"error": {"code": "CAPABILITY_DENIED",
           "message": "This connector may not write pull requests on acme-corp/api.",
           "connector_id": "conn_01J…",
           "request_id": "req_01J…",
           "retryable": false,
           "user_action": "GRANT_CAPABILITY"}}
```

`user_action` ∈ `NONE · RECONNECT · GRANT_CAPABILITY · AUTHORISE_SSO · INSTALL_APP · ADD_REPOSITORY · WAIT · CONTACT_ORG_OWNER`. The renderer switches on this, not on the message — so error UX is a contract, not string-matching.

---

## 5.2 Connector lifecycle routes

### `GET /connectors`
List all connectors for the operator, all providers.
**Auth** operator session · **AuthZ** filtered by `operator_id` · **200**

```json
{"connectors": [{
  "id": "conn_01J…", "provider": "github", "status": "ACTIVE",
  "account": {"id": "583231", "username": "octocat", "avatar_url": "https://…"},
  "label": "personal",
  "counts": {"organizations": 3, "repositories": 12},
  "created_at": "…", "last_used_at": "…"}]}
```
Never returns scopes, tokens, or installation ids. **Errors** 401.

### `POST /connectors/github/authorize`
Begin a connect (or reconnect) transaction.
**Body** `{"label": "work", "reconnect_of": "conn_01J…"}` — both optional. **No provider data is accepted from the caller**: not a redirect URI, not scopes, not a client id.
**Idempotency** an operator with an open non-expired transaction gets that one back rather than a second.
**202**

```json
{"transaction_id": "tx_01J…", "strategy": "device",
 "user_code": "WDJB-MJHT",
 "verification_uri": "https://github.com/login/device",
 "expires_at": "2026-08-20T12:15:00Z", "poll_interval_seconds": 5}
```
**Errors** 401 · 409 `CONNECTOR_LIMIT` · 503 `PROVIDER_UNAVAILABLE`.

### `GET /connectors/github/authorize/{transaction_id}`
Poll transaction status. **AuthZ** transaction's `operator_id` must equal the session's.
**200** `{"status": "AUTHORIZATION_STARTED"}` → … → `{"status":"COMPLETED","connector_id":"conn_01J…"}`
**Errors** 404 (not yours / unknown) · 410 `TRANSACTION_EXPIRED`.
Polling is server-throttled to the interval GitHub gave us, so a chatty renderer cannot trigger `slow_down` on the upstream.

### `DELETE /connectors/github/authorize/{transaction_id}`
Cancel. **204.** Transaction → `CANCELLED`, secrets nulled.

### `GET /oauth/github/callback` — hosted deployment only
Not present in local mode; there is no callback in device flow.
**Query** `code`, `state` · **Auth** none (public by necessity) · **AuthZ** by `state` alone.
Order: look up `state_hash` → single-use claim (`rowcount==1`) → expiry → exchange with `client_secret` + `code_verifier` → identity → connector → redirect to a static "you may close this window" page.
**Never** reflects `state` or `code` into the response body, and never redirects to a URI supplied in the request.

### `GET /connectors/github/{id}`
**200** connector detail + capability summary. **404** if not the operator's.

### `POST /connectors/github/{id}/reauthorize`
Opens a transaction with `reconnect_of` preset. Same response as `authorize`. On completion, a **different** `provider_account_id` is rejected with 409 `ACCOUNT_MISMATCH` — it does not silently rebind the row (`02 §2.5`).

### `DELETE /connectors/github/{id}`
Runs the `02 §2.6` sequence. **200**, honest about remote revocation:
```json
{"status": "DISCONNECTED",
 "credentials_deleted": true,
 "provider_authorization_revoked": false,
 "revoke_instructions_url": "https://github.com/settings/connections/applications/…"}
```
**Idempotent**: deleting an already-disconnected connector returns 200, not 404.

---

## 5.3 Discovery routes

### `GET /connectors/github/{id}/organizations`
**200** per `03 §3.5`, including `access: "sso_required"` entries. Cache 15 min, `stale_at` returned.

### `GET /connectors/github/{id}/repositories`
**Query** `installation_id`, `visibility`, `query`, `cursor`, `limit≤100`.
**200** per `03 §3.4`. `cursor` is opaque and signed; a tampered cursor is 400 `INVALID_CURSOR`, never dereferenced.
**Errors** 409 `CONNECTOR_NOT_ACTIVE` · 429 · 502 `PROVIDER_ERROR`.

### `POST /connectors/github/{id}/validate`
Live check: `GET /user` + refresh if needed. Updates `status`, `status_reason`, `last_validated_at`, `provider_username`. Rate-limited to 1/min/connector — this route is a self-inflicted-DoS vector if the UI polls it.

### `GET /connectors/github/{id}/capabilities` · `PUT …/capabilities`
Read and set the connector's capability grants (`04 §4.1`). PUT is full-replacement with an `If-Match` ETag so two settings tabs cannot silently clobber each other. Every change is audited with before/after.

---

## 5.4 Agent tool routes

### `POST /agent/tools/github/{tool_name}`
**Auth** agent session token (issued per session, bound to `operator_id` + `connector_id` + `agent_id`).
**Body** the tool arguments only — **no `connector_id`** (`04 §4.2`).

| Status | Meaning |
|---|---|
| 200 | executed; result body |
| 202 | `APPROVAL_REQUIRED` + `approval_id` — the agent must stop and wait |
| 400 | `INVALID_ARGUMENTS` (schema) |
| 403 | `CAPABILITY_DENIED` — terminal for this call |
| 404 | connector not found *or* not this operator's |
| 409 | `CONNECTOR_NOT_ACTIVE` |
| 429 | rate limited, `Retry-After` |
| 502 | provider error, mapped |

Write tools require `Idempotency-Key`; a replayed key returns the original result rather than opening a second pull request.

Every response that carries provider text is wrapped:
```json
{"result": {"content_type": "untrusted_external_content",
            "source": "github:acme-corp/api@main:/README.md",
            "content": "…"}}
```

### `GET /agent/approvals/{approval_id}` · `POST /agent/approvals/{approval_id}/decide`
The first is polled by the agent runtime; the second is called **only by the desktop UI on a human action**, never by an agent session token. Enforced by token type, not by convention.

---

## 5.5 Desktop-facing contracts

The renderer additionally consumes:

| Route | Purpose |
|---|---|
| `GET /connectors/stream` (SSE) | connector state changes, transaction progress, pending approvals — so the UI never polls |
| `GET /connectors/github/{id}/events?limit=50` | the audit trail for this connector, rendered in Manage |
| `GET /connectors/github/{id}/health` | rate-limit budget remaining, last validation, current reason code |

The SSE stream carries state and identifiers only. A pending-approval event carries the `approval_id`; the card's contents are fetched over the authenticated route. Approval payloads do not ride the stream, so a stream leak is not an approval-content leak.
