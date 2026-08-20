# 1 · Architecture

Covers deliverables **1 (product), 2 (component), 3 (OAuth), 4 (callback), 5 (sequence)**.

---

## 1.1 Product architecture

```
┌──────────────────────────────────────────────────────────────┐
│ Sutra Desktop (Electron shell)                               │
│                                                              │
│   Renderer  ── static panel, chat, connector UI, approval UI  │
│      │  loopback HTTP + per-launch bearer                    │
│      ▼                                                       │
│   ┌──────────────────────────────────────────────────────┐   │
│   │ Connector Service   (FastAPI, 127.0.0.1)             │   │
│   │                                                      │   │
│   │  Connector API ─ AuthZ ─ Connector Manager           │   │
│   │  Tool Gateway ─ Capability Gate ─ Approval Gate      │   │
│   │  Provider Factory ─► GitHubProvider                  │   │
│   │  CredentialStore ─► Keychain adapter                 │   │
│   │  Audit Sink ─► append-only JSONL (hash-chained)      │   │
│   │  Connector DB ─► SQLite (WAL, 0600)                  │   │
│   └──────────────────────┬───────────────────────────────┘   │
└──────────────────────────┼───────────────────────────────────┘
                           │ HTTPS, only from this process
                           ▼
                    ┌──────────────┐
                    │  GitHub APIs │
                    └──────────────┘
```

The renderer's entire GitHub vocabulary is `connector_id` and connector state. It never sees a token, never calls github.com, and never learns whether the Connector Service is loopback or hosted.

**Hosted deployment, later — same picture, one boundary moved:**

```
Desktop ──HTTPS──► API Gateway ──► Connector Service (stateless, N replicas)
                                        ├── PostgreSQL
                                        ├── Redis (transactions, rate budgets, cache)
                                        ├── KMS (envelope encryption)
                                        └── GitHub APIs
```

Nothing above the `CredentialStore` / `ConnectorRepository` / `AuthStrategy` ports changes. That is the whole point of the hybrid choice.

---

## 1.2 Responsibility split

| Responsibility | Desktop renderer | Connector Service | GitHub | Store |
|---|---|---|---|---|
| Render connector list, states, errors | ✅ | | | |
| Start a connect flow | ✅ (asks) | ✅ (owns) | | |
| Generate `state` / `code_verifier` | ❌ never | ✅ | | ✅ persisted |
| Open the system browser | ✅ | | | |
| Exchange code / poll device flow | ❌ never | ✅ | ✅ issues | |
| Hold access + refresh token | ❌ never | ✅ in memory only | | ✅ Keychain |
| Refresh tokens | ❌ | ✅ single writer | ✅ | ✅ |
| Decide if an agent may act | ❌ | ✅ **outside the LLM** | | ✅ policy |
| Ask a human to approve | ✅ renders | ✅ issues + verifies | | ✅ grant row |
| Call the GitHub REST API | ❌ never | ✅ | ✅ | |
| Rate-limit accounting | ❌ | ✅ | ✅ headers | ✅ budgets |
| Write audit rows | ❌ (client logs are claims, not evidence) | ✅ | | ✅ append-only |
| Enforce repo/org permissions | ❌ | ✅ (our layer) | ✅ (authoritative) | |

**The asymmetry is deliberate.** Anything the renderer could forge is not trusted for a security decision. Anything a compromised renderer could do is bounded by what the Connector API will accept from it.

---

## 1.3 Connector identity ≠ application identity

Two independent identity systems that must never be collapsed:

```
Application auth                  Connector
─────────────────                 ─────────────────
Human ─► Sutra auth               Sutra operator ─► GitHubConnector ─► GitHub account
      ─► operator_id                            (persisted, scoped, revocable)
```

```
operator
├── GitHubConnector #1   (personal — id 583231, "octocat")
├── GitHubConnector #2   (work — id 991204, "octo-at-acme")
├── SlackConnector
└── JiraConnector
```

Why the separation is load-bearing, concretely:

| If collapsed | Failure that follows |
|---|---|
| "Sign in with GitHub" is also the connector | Revoking the GitHub grant logs the user out of Sutra. Losing GitHub access becomes losing your work. |
| One GitHub account per user | Personal + work accounts are unrepresentable; the second overwrites the first (§25 hazard). |
| Session lifetime = connector lifetime | A background agent cannot act, because the connector dies with the UI session. |
| Connector = auth provider | Adding Slack means adding a second login provider rather than a second connector. |

Sutra's operator identity is Sutra's own. GitHub is a *thing the operator connected*, in the same category as Slack.

---

## 1.4 Component architecture

```
                     ┌──────────────────────────┐
   HTTP ─────────────► api/            routes, DTOs, error envelope
                     └────────────┬─────────────┘
                                  │ (never reaches below without an authenticated operator)
                     ┌────────────▼─────────────┐
                     │ auth/    operator identity, loopback caller auth
                     └────────────┬─────────────┘
       ┌──────────────────────────┼──────────────────────────┐
       ▼                          ▼                          ▼
┌──────────────┐        ┌──────────────────┐       ┌──────────────────┐
│ oauth/       │        │ connectors/core/ │       │ tools/           │
│ transaction  │        │ ConnectorService │       │ Tool Gateway     │
│ state/PKCE   │        │ lifecycle, FSM   │       │ schema validate  │
│ AuthStrategy │        └────────┬─────────┘       │ capability gate  │
└──────┬───────┘                 │                 │ approval gate    │
       │                         │                 └────────┬─────────┘
       │              ┌──────────▼───────────┐              │
       └──────────────► connectors/provider/ ◄──────────────┘
                      │ ProviderFactory      │
                      │ ConnectorProvider(P) │
                      └──────────┬───────────┘
                                 ▼
                      ┌──────────────────────┐
                      │ connectors/github/   │  ◄── the ONLY package that
                      │ client, mappers,     │      knows GitHub exists
                      │ capabilities, errors │
                      └──────────┬───────────┘
      ┌──────────────────────────┼──────────────────────────┐
      ▼                          ▼                          ▼
┌────────────┐        ┌────────────────┐         ┌──────────────────┐
│credentials/│        │ database/      │         │ audit/           │
│CredentialSt│        │ repositories   │         │ append-only sink │
│Keychain|KMS│        │ SQLite | PG    │         │ hash-chained     │
└────────────┘        └────────────────┘         └──────────────────┘
```

### Ports (the swap points)

```python
class ConnectorProvider(Protocol):          # one per external service
    provider_id: str
    def auth_strategy(self) -> AuthStrategy: ...
    def fetch_identity(self, cred) -> ProviderIdentity: ...
    def capability_map(self) -> CapabilityMap: ...
    def execute(self, op: Operation, cred) -> OperationResult: ...
    def classify_error(self, exc) -> ConnectorError: ...

class AuthStrategy(Protocol):               # device flow | PKCE web flow
    def begin(self, tx: OAuthTransaction) -> AuthChallenge: ...
    def complete(self, tx: OAuthTransaction, evidence) -> Credential: ...
    def refresh(self, cred: Credential) -> Credential: ...
    def revoke(self, cred: Credential) -> None: ...

class CredentialStore(Protocol):            # Keychain | Postgres+KMS
    def save(self, connector_id, cred) -> None: ...
    def get(self, connector_id) -> Credential: ...
    def delete(self, connector_id) -> None: ...
    def rotate(self, connector_id, new: Credential) -> None: ...
```

`ConnectorService` — `connect · disconnect · get · list · refresh · validate · execute` — is provider-agnostic and contains **zero** GitHub identifiers. The compile-time rule enforced in CI: nothing outside `connectors/github/` may import a GitHub symbol or contain the string `github` except as a provider-id literal.

### Provider factory and per-provider config

```python
factory.get("github") -> GitHubProvider     # registry keyed by provider_id
```

Provider config is **data, not code** — one record per provider per environment, loaded at boot, never committed:

```
GITHUB__CLIENT_ID          public, ships fine
GITHUB__CLIENT_SECRET      hosted deployment ONLY; absent in local mode
GITHUB__APP_PRIVATE_KEY    hosted deployment ONLY (F6)
GITHUB__API_BASE           https://api.github.com  (overridable for GHES)
GITHUB__AUTH_STRATEGY      device | web_pkce
```

Local mode has no secret and no private key to leak because it is issued neither.

---

## 1.5 OAuth architecture

### GitHub App, not OAuth App

| | OAuth App | **GitHub App (chosen)** |
|---|---|---|
| Permission granularity | Coarse scopes; `repo` = read+write on every repo the user can reach | Per-repository selection + per-resource read/write (F7) |
| Org control | Org can block, but cannot scope | Owner approves installation and picks repositories |
| Token lifetime | Long-lived by default | 8h user token + 6-month refresh (F5) |
| Acting without a user | No | Installation token, 1h (F6) — hosted only |
| Can we honestly say "read-only on repo X"? | **No** | **Yes** |

The last row decides it. A capability model layered over a credential that can write everywhere is decoration.

### Where each secret lives and who generates it

| Artifact | Generated by | Stored | Lifetime | Single-use |
|---|---|---|---|---|
| `state` | Connector Service, `secrets.token_urlsafe(32)` | `oauth_transactions.state_hash` (SHA-256, never plaintext) | ≤ 10 min | ✅ |
| `code_verifier` (web flow) | Connector Service | `oauth_transactions`, encrypted | ≤ 10 min | ✅ |
| `code_challenge` | derived, S256 (F1) | not stored | — | — |
| `device_code` | GitHub | transaction row, encrypted | GitHub-set | ✅ |
| `user_code` | GitHub | shown to user, not stored | GitHub-set | ✅ |
| authorization `code` | GitHub | **never stored** | ~10 min | ✅ GitHub-enforced |
| access token | GitHub | CredentialStore only | 8h | — |
| refresh token | GitHub | CredentialStore only | 6 mo idle | rotates on use |
| `client_secret` | GitHub App settings | hosted server env only | until rotated | — |

**Never in the desktop binary, never in the renderer, never in a log, never in an API response, never in a git object.**

---

## 1.6 Callback architecture

The founder brief asks for four options compared. The comparison's conclusion is that for the chosen deployment there is **no callback at all**.

| | Loopback `127.0.0.1:<port>` | Custom scheme `sutra://` | Universal / app links | Backend HTTPS | **Device flow (chosen, local)** |
|---|---|---|---|---|---|
| Windows | ok | registry, hijackable by any installer | needs association file + signing | ok | ok |
| macOS | ok | `CFBundleURLTypes`; last-registered app can win | needs AASA + notarised app | ok | ok |
| Linux | ok | `.desktop` MIME, inconsistent across DEs | effectively unavailable | ok | ok |
| Old installed versions | old build can claim the port | **old build can claim the scheme** | version-aware | unaffected | unaffected |
| Two app instances | port conflict → random fallback port → redirect URI mismatch | both registered; OS picks | ok | unaffected | unaffected |
| Malicious local process | can race for the port and receive the `code` | can register the scheme and receive the `code` | harder | n/a | **no code to intercept** |
| Browser security | fine (RFC 8252) | scheme handlers are not origin-bound | fine | fine | fine |
| Needs `client_secret` on device | **yes (F2)** | **yes (F2)** | **yes (F2)** | no | **no (F3)** |
| Attack surface added | a local HTTP listener | a global URI handler | an association | one HTTPS route | **none** |

Rows "needs `client_secret`" and "malicious local process" settle it. The first three options require the desktop to redeem the code, which requires a shipped secret — disqualifying. Device flow removes the redirect entirely: there is no URI to hijack, no port to squat, no code in transit to steal.

**Recommendation**

| Deployment | Callback |
|---|---|
| Local (v1) | **Device flow — none.** |
| Hosted (v2) | **Backend HTTPS callback** `https://api.sutra.…/oauth/github/callback`, one registered redirect URI, exact-match, PKCE S256, desktop polls its own API for completion. Never loopback, never custom scheme. |

---

## 1.7 Sequence — connect (device flow, local, v1)

```
Renderer      Connector Service        Keychain        GitHub
   │                  │                   │              │
   │ POST /connectors/github/authorize    │              │
   ├─────────────────►│                   │              │
   │      (operator auth checked; NO provider data in request body)
   │                  │  create OAuthTransaction         │
   │                  │  state=rand(32) → store SHA-256  │
   │                  │  status=CREATED                  │
   │                  ├──── POST /login/device/code ────►│
   │                  │◄─── device_code, user_code, ─────┤
   │                  │     verification_uri, interval   │
   │                  │  status=AUTHORIZATION_STARTED    │
   │◄─────────────────┤ {transaction_id, user_code,      │
   │                  │  verification_uri, expires_at}   │
   │                  │                                  │
   │ open system browser → verification_uri              │
   │                  │                   │              │
   │                  │  poll @ interval (honour slow_down)
   │                  ├──── POST /login/oauth/access_token ─►│
   │                  │     grant_type=device_code           │
   │                  │     NO client_secret (F3)            │
   │                  │◄─── authorization_pending … then ────┤
   │                  │     access_token, refresh_token,     │
   │                  │     expires_in=28800 (F5)            │
   │                  │  status=CODE_EXCHANGED               │
   │                  ├──── GET /user ──────────────────────►│
   │                  │◄─── id (STABLE), login, avatar ──────┤
   │                  ├──── GET /user/installations ────────►│
   │                  │◄─── installations[] ─────────────────┤
   │                  │  UNIQUE(operator,'github',user.id)?  │
   │                  │    hit  → rotate credential in place │
   │                  │    miss → INSERT connector           │
   │                  ├─ save ──────────►│                   │
   │                  │  status=CONNECTOR_CREATED → COMPLETED│
   │                  │  DELETE transaction secrets          │
   │                  │  audit: CONNECTOR_CREATED            │
   │◄─────────────────┤ 201 {connector_id, account, ACTIVE}  │
   │                  │                                      │
   │ GET /connectors/github/{id}/repositories                 │
```

The renderer's only inputs to the security-relevant part of this flow are "start" and "which transaction am I waiting on." It cannot influence `state`, the token, or the identity binding.

## 1.8 Sequence — agent tool call (the path that matters most)

```
Agent(LLM)   Tool Gateway    Capability Gate   Approval Gate  Provider   GitHub
    │              │                │                │           │         │
    │ github.create_pull_request(repo, head, base, title, body)   │         │
    ├─────────────►│                │                │           │         │
    │              │ 1. session → operator_id, connector_id       │         │
    │              │    ** connector_id comes from the SESSION,   │         │
    │              │       never from the model's arguments **    │         │
    │              │ 2. JSON-schema validate args (reject unknown fields)
    │              │ 3. connector.operator_id == session.operator_id?
    │              │ 4. connector.status == ACTIVE?               │         │
    │              ├───────────────►│ effective = provider_grant  │         │
    │              │                │           ∩ connector_grant │         │
    │              │                │           ∩ agent_policy    │         │
    │              │                │  scoped to (repo, op)       │         │
    │              │◄───────────────┤ ALLOW | ASK_USER | DENY     │         │
    │              │ 5. taint check: untrusted content read this turn?
    │              │    → force ASK_USER regardless of policy     │         │
    │              ├────────────────────────────────►│ create ApprovalGrant │
    │              │                │                │ bound to hash of the │
    │              │                │                │ EXACT operation      │
    │              │                │                │ ── renders in UI ──► │
    │              │                │                │ ◄─ human decision ── │
    │              │◄────────────────────────────────┤ grant | denial       │
    │              │ 6. re-verify grant hash == this operation's hash
    │              │ 7. rate budget: connector / operator / agent │         │
    │              ├──────────────────────────────────────────────►│───────►│
    │              │◄──────────────────────────────────────────────┤◄───────┤
    │              │ 8. audit PULL_REQUEST_CREATED (result, ids, no secrets)
    │              │ 9. emit DecisionProvenance (ADR-007) + Artifact (B9)
    │◄─────────────┤ result, wrapped as UNTRUSTED if it echoes provider text
```

Steps 1, 3, 5 and 6 are the ones that stop the attacks in `06-security.md`. None of them consults the model.
