# 7 · Operations

Covers deliverables **20 (rate limits), 21 (caching), 22 (audit architecture), 23 (observability)**.

---

## 7.1 Rate limiting

### GitHub's actual limits (verified 2026-08-20)

| Limit | Value |
|---|---|
| User access token (user-to-server) | 5,000 req/hr (15,000 for Enterprise Cloud orgs) |
| Installation token | 5,000/hr minimum, +50/hr per repo above 20 repos, +50/hr per user above 20 users, **capped at 12,500/hr** |
| Headers | `x-ratelimit-limit`, `x-ratelimit-remaining`, `x-ratelimit-used`, `x-ratelimit-reset` |
| Secondary: concurrency | no more than **100 concurrent requests** |
| Secondary: content-creating | **80/min** and **500/hr** |
| Secondary: points | GET/HEAD/OPTIONS = 1 point; POST/PATCH/PUT/DELETE = 5 points |
| Status on breach | **403 or 429** for both primary and secondary |
| `retry-after` | seconds to wait, on secondary limits |

### Classifying a 403 — never retry blindly

```
403 or 429 received
  ├── retry-after present            → SECONDARY limit. Sleep exactly that long. Never sooner.
  ├── x-ratelimit-remaining == 0     → PRIMARY limit. Sleep until x-ratelimit-reset.
  ├── X-GitHub-SSO present           → NOT a rate limit. SSO required. Do not retry; surface an action.
  └── none of the above              → PERMISSION denied. Do not retry, ever. Surface the reason.
```

Blind retry on 403 is the single most common way an integration gets an App flagged for abuse: two of the four branches are permanent failures, and retrying them looks exactly like an attack.

### Our budgets — deliberately below GitHub's

| Scope | Budget | Rationale |
|---|---|---|
| Per connector | 3,000/hr | leaves ≥40% headroom for the user's other GitHub tooling on the same token |
| Per operator | 4,000/hr across connectors | one runaway agent must not starve the person |
| Per agent session | 500/hr, 30/min | bounds a looping agent to a recoverable amount of damage |
| Content-creating | 20/min, 100/hr per connector | far under 80/500; approval-gated anyway |
| Global concurrency | 20 per connector, 50 process-wide | under the 100 ceiling with room for other clients |

Token buckets in Redis (hosted) or SQLite with an advisory lock (local). Exhaustion returns 429 + `Retry-After` and is a metric, not a silent stall.

### Retry policy

| Condition | Retry? | How |
|---|---|---|
| 5xx, timeout, connection reset | yes | exp. backoff 1→2→4→8s, ±25% jitter, max 4 |
| Secondary rate limit | yes | exactly `retry-after`, then one retry |
| Primary rate limit | yes | wait to `x-ratelimit-reset`; if >5 min, fail with `WAIT` and tell the user when |
| 401 | once | after refresh; a second 401 → `REAUTH_REQUIRED` |
| 403 permission, 404, 422 | **never** | terminal |
| Non-idempotent write | **never** without `Idempotency-Key` | a retried PR creation is a duplicate PR |

Circuit breaker per connector: 5 consecutive `PROVIDER_UNAVAILABLE` → open 60s → half-open single probe. State surfaces as connector `ERROR` so the user sees "retrying" instead of a hang.

---

## 7.2 Caching

| Data | TTL | Invalidated by | Cacheable? |
|---|---|---|---|
| Organizations | 15 min | reconnect, install change, manual refresh | ✅ |
| Repository list | 10 min | reconnect, install change, manual refresh | ✅ |
| Repository metadata | 10 min | write to that repo | ✅ |
| Branch list | 2 min | our own branch create/delete | ✅ |
| Pull request list | 1 min | our own PR create/update | ✅ |
| PR detail | 30 s | our own comment/update | ✅ |
| **File contents** | keyed by **immutable commit SHA only**, 24 h | never (SHA is immutable) | ✅ *only at a SHA* |
| File contents at a branch ref | **not cached** | — | ❌ — a moving ref cached is a stale-code bug |
| Search results | 60 s | — | ✅ |
| Rate-limit state | live | — | ✅ (must be) |
| **Credentials** | **never** | — | ❌ **never in any application cache** |
| Capability decisions | **never** | — | ❌ re-resolve per call; a cached ALLOW outlives a revocation |

Two rules with teeth: **cache file contents only at a commit SHA**, never at `main`; and **never cache an authorization decision**, because the window between a user revoking a capability and a cached ALLOW expiring is precisely the window an incident happens in.

ETags from `connector_metadata.etag` drive conditional requests. A 304 costs no primary rate-limit quota, which is the cheapest capacity win available.

Cache keys always include `connector_id`. A key without it is a cross-account data leak waiting for a collision; CI rejects any cache key construction that omits it.

---

## 7.3 Audit architecture

Every meaningful action writes one row, before the result reaches the caller.

| Event | Emitted when |
|---|---|
| `CONNECTOR_CREATED` · `CONNECTOR_REAUTHORIZED` · `CONNECTOR_DISCONNECTED` | lifecycle |
| `CONNECTOR_VALIDATION_FAILED` · `CONNECTOR_STATE_CHANGED` | health |
| `CAPABILITY_GRANTED` · `CAPABILITY_REVOKED` | policy change, with before/after |
| `REPOSITORY_ACCESSED` · `FILE_READ` · `CODE_SEARCHED` | reads |
| `BRANCH_CREATED` · `COMMIT_CREATED` · `PULL_REQUEST_CREATED` · `PULL_REQUEST_MERGED` · `ISSUE_COMMENTED` | writes |
| `TOOL_DENIED` · `APPROVAL_REQUESTED` · `APPROVAL_GRANTED` · `APPROVAL_REJECTED` | authorization |
| `RATE_LIMIT_HIT` · `PROVIDER_ERROR` | operations |

Each row: `operator_id · connector_id · agent_id · session_id · event_type · resource · operation · result · reason_code · request_id · detail_json · occurred_at · prev_hash · row_hash`.

**Never**: tokens, refresh tokens, `client_secret`, device codes, `state`, file contents, diff bodies. `detail_json` holds identifiers and counts — `{"files": 2, "additions": 14, "deletions": 3}`, not the diff.

Tamper-evidence: `row_hash = SHA-256(prev_hash ‖ canonical_json(row))`. A verifier walks the chain on a schedule; a break is a P1 alert. Append-only is enforced by trigger locally and by revoked grants in Postgres (`02 §2.3`). Local mode's honest limitation is in T-18: a user with root on their own machine can delete the file — which is the clearest argument for shipping the hosted sink.

Retention: connector events 400 days; approval decisions 400 days; OAuth transactions 90 days (secrets nulled at completion, not at expiry).

Every audit row for a write action also emits a **DecisionProvenance** row (ADR-007) and registers an **Artifact** (B9), satisfying B17 AC#2.

---

## 7.4 Observability

### Metrics

```
connector_connect_started{provider,strategy}
connector_connect_success{provider}
connector_connect_failed{provider,failure_code}
connector_reauth_required{provider,reason}         ← reason cardinality is bounded (6 values)
connector_disconnected{provider,initiator}
connector_active_total{provider,status}            gauge

github_api_request{endpoint_class,method,status}
github_api_duration_seconds                        histogram
github_api_failure{error_code}
github_rate_limited{limit_type}                    primary | secondary
github_rate_budget_remaining{connector_id_hash}    gauge

github_tool_invocation{tool,decision}
github_tool_denied{tool,reason}
github_tool_approval_requested{tool}
github_tool_approval_granted{tool}
github_tool_approval_rejected{tool}
github_tool_duration_seconds                       histogram

prompt_injection_suspected{source_type}            telemetry ONLY — never an authz input
untrusted_content_read{instruction_like}
audit_chain_verification_failed                    → P1
```

Label hygiene: never a raw `connector_id` (it is a user identifier), never a repo name (often confidential), never a token. Where per-connector granularity is needed, use a salted hash.

### Alerts

| Condition | Severity | Why |
|---|---|---|
| `audit_chain_verification_failed > 0` | **P1** | evidence integrity gone |
| Token-shaped string in any log sink | **P1** | credential leak |
| `connector_connect_failed` ratio > 30% / 15 min | P2 | flow broken, likely upstream |
| `github_rate_limited{secondary}` > 0 | P2 | abuse-detection risk to the App |
| `github_tool_denied` > 50 / session | P2 | escalation attempt or broken policy |
| `github_tool_approval_rejected` spike | P2 | strong injection signal |
| Circuit breaker open > 5 min | P3 | GitHub degraded |

### Tracing

One `request_id` per inbound call, propagated into every GitHub request's `User-Agent` correlation suffix and into every audit row, so "what did the agent actually do at 14:32" is one query, not a reconstruction.

---

## 7.5 Webhooks — future

```
GitHub ──► POST /webhooks/github ──► verify HMAC ──► map installation_id → connector
                                                  ──► ConnectorEvent (untrusted)
                                                  ──► Artifact (B9) ──► agent, if subscribed
```

| Concern | Design |
|---|---|
| Identity association | `payload.installation.id` → `connector_installations.installation_id` → connector. **Never** trust a repo or user field in the payload for identity. One installation may map to several connectors (two operators, same org) — fan out, do not pick one. |
| Authenticity | `X-Hub-Signature-256` HMAC verified with `compare_digest` **before parsing**. |
| Replay | `X-GitHub-Delivery` recorded; duplicates dropped. |
| Content | Every field untrusted (`06 §6.2`). A webhook body is a remote attacker's most direct channel into an agent. |
| Local mode | No public endpoint exists. Webhooks are a hosted-only capability — stated, not faked with polling that pretends to be push. |
| Events | `push`, `pull_request`, `issues`, `issue_comment`, `repository`, `installation`, `installation_repositories` |
| `installation.deleted` | The App was uninstalled → affected connectors → `REAUTH_REQUIRED` / `ORG_ACCESS_REMOVED`. This is the one webhook worth shipping first: without it, uninstall is discovered only on the next failed call. |
