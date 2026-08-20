# 3 · GitHub Integration

Covers deliverables **9 (GitHub API integration), 10 (repository discovery), 11 (organization discovery)**.

---

## 3.1 What changed from older GitHub OAuth implementations

Guidance written before ~2024 is wrong on several points that matter here. Verified 2026-08-20 against docs.github.com.

| Older guidance | Current reality | Consequence |
|---|---|---|
| "GitHub does not support PKCE" | **False.** `code_challenge` + `code_challenge_method` are documented; **`S256` only**, `plain` explicitly rejected | Use PKCE in the hosted web flow. Do not implement `plain`. |
| "PKCE lets a native app skip the client secret" | **False on GitHub.** `client_secret` is still `Required` on the token exchange | Desktop cannot redeem a code. Device flow or a server. |
| "OAuth tokens never expire" | Opt-in expiry; for GitHub Apps expiry is **on unless you opt out**. 8h token / 6-month refresh | Refresh is mandatory machinery. |
| "You need the client secret to refresh" | **Not for device-flow tokens** | A secret-less client keeps a full lifecycle. |
| "Use `/user/repos` to list what you can access" | Correct for an OAuth App; **wrong for a GitHub App** | Use `/user/installations` → `/user/installations/{id}/repositories`. |
| "Scopes describe what you can do" | For GitHub Apps, *permissions* + *installation repository selection* do | Both must be read; scopes alone under-describe access. |
| "403 means forbidden" | 403 is also rate limiting and also SAML-SSO enforcement | Classify before acting (`02 §2.5`). |

**GHES note**: GitHub Enterprise Server trails github.com on App features and has a different `api_base`. The `api_base` column exists for this; GHES support is not claimed until tested against a real instance.

---

## 3.2 API client design

One client per connector-request, constructed by `GitHubProvider`, used by nothing outside `connectors/github/`.

```
GitHubClient
  base_url        from connector.api_base
  auth            Bearer <user access token>, injected per request from CredentialStore
  headers         Accept: application/vnd.github+json
                  X-GitHub-Api-Version: 2022-11-28     ← pinned; unpinned = silent breakage
                  User-Agent: Sutra-Connector/<version>
  timeouts        connect 5s, read 30s
  retries         idempotent verbs only; never blind (07 §7.1)
  pagination      Link header rel="next" ONLY — never page arithmetic
  conditional     If-None-Match from connector_metadata.etag
  instrumentation every response's rate-limit headers → budget tracker
```

Two rules that are easy to get wrong:

1. **Follow `Link: rel="next"`, do not construct `?page=n`.** Constructed page numbers skip and duplicate entries when the underlying set changes mid-walk, and they break on endpoints that use cursors.
2. **Pin `X-GitHub-Api-Version`.** An unpinned client inherits behaviour changes on GitHub's schedule, in production, with no deploy of ours to correlate against.

### Error mapping

Every provider exception is normalised before it leaves the package. Callers above never see an HTTP status.

| GitHub | `ConnectorError` | Retryable | Connector state effect |
|---|---|---|---|
| 401 `bad_credentials` | `CREDENTIAL_INVALID` | after refresh, once | → `REAUTH_REQUIRED` if refresh fails |
| 403 + `x-ratelimit-remaining: 0` | `RATE_LIMITED` | yes, at `x-ratelimit-reset` | none |
| 403 + `retry-after` | `SECONDARY_RATE_LIMITED` | yes, after `retry-after` | none |
| 403 + `X-GitHub-SSO` | `SSO_REQUIRED` | no | mark installation `sso_required` |
| 403 otherwise | `PERMISSION_DENIED` | no | none |
| 404 | `NOT_FOUND_OR_FORBIDDEN` | no | none — **never rendered as "does not exist"** |
| 409 | `CONFLICT` (branch exists, stale ref) | no | none |
| 422 | `VALIDATION_FAILED` (+ GitHub's field errors) | no | none |
| 5xx / timeout | `PROVIDER_UNAVAILABLE` | yes, backoff | → `ERROR` after N consecutive |

The 404 row is the one that produces bad UX everywhere else: rendering it as "repository not found" sends a user hunting for a typo when the real problem is that the repo was never added to the Sutra installation.

---

## 3.3 Identity discovery

```
device flow completes ─► GET /user ─► the connector's identity
```

| Field | Stored as | Notes |
|---|---|---|
| `id` (integer) | `provider_account_id` | **Primary identity. Immutable.** The only value the unique key may use. |
| `node_id` | `provider_account_node` | GraphQL joins later |
| `login` | `provider_username` | **Mutable — display only.** Refresh on every validate. |
| `name` | `display_name` | Often null. |
| `avatar_url` | `avatar_url` | URL only; the image is never proxied or cached by us. |
| `type` | `account_type` | |
| email | **not fetched in v1** | Requires an email permission we do not need. Absent scope means `/user` returns null, and a null we designed around beats a permission we asked for without cause. |

Using `login` as identity fails in two directions: a rename orphans the connector, and a *released* username reassigned to a different person would rebind an existing connector to a stranger. The numeric id has neither failure.

---

## 3.4 Repository discovery

### The GitHub App path (correct for our choice)

```
GET /user/installations                                  → installations the user can access
      └─ for each installation:
GET /user/installations/{installation_id}/repositories    → repos the USER can reach
                                                            within that installation
```

Both take the **user access token**. This is the intersection that matters, and it is the reason the founder brief's §12 warning is right:

```
   repos on GitHub
      └── repos this USER can see            (their permission)
            └── repos in the Sutra INSTALLATION   (org owner's selection)
                  └── repos our PERMISSIONS cover  (contents, PRs, …)
                        └── repos our CAPABILITY policy allows   ← what the agent sees
```

A token is not access. Each of those four narrowings is enforced by a different party, and only the last is ours.

### Distinguishing the four things that get conflated

| Concept | Owned by | Example | Where it shows up |
|---|---|---|---|
| Repository **visibility** | repo settings | private / internal / public | `repository.visibility` |
| Repository **permission** | the user's role | admin / maintain / write / triage / read | `repository.permissions` |
| App **permission** | what the App requested and was granted | `contents: write`, `pull_requests: write` | installation `permissions` |
| **Repository selection** | org owner at install time | `all` vs `selected` | installation `repository_selection` |
| **Org restrictions** | org policy | third-party app restrictions, SAML | 403 + `X-GitHub-SSO`, or the repo simply absent |

The effective answer for "can this connector write to `acme/api`?" is the **intersection of all five**, and each is checked in a different place. This is why the capability model in `04` cannot be derived from scopes alone.

### Pagination and shape

```
GET /connectors/github/{id}/repositories
    ?installation_id=…&visibility=all|public|private&query=…&cursor=…&limit=50
```

- Cursor is an **opaque, signed** token wrapping our upstream position — never a raw GitHub URL, which would let a caller redirect our authenticated client at a URL of their choosing (T-17).
- `limit` ≤ 100, default 50.
- Results merge `connector_metadata` cache with live fetch; each row carries `stale_at`.
- A repo unreachable due to SSO is returned with `access: "sso_required"` rather than omitted — a silently missing repo is a support ticket; a labelled one is a fixable state.

```json
{
  "repositories": [{
    "id": "1296269",
    "full_name": "octocat/hello-world",
    "visibility": "private",
    "default_branch": "main",
    "archived": false,
    "user_permission": "write",
    "installation_id": 42,
    "app_permissions": {"contents": "write", "pull_requests": "write"},
    "capabilities": ["github.repository.contents.read", "github.pull_requests.write"],
    "access": "ok"
  }],
  "next_cursor": "eyJ…",
  "stale_at": "2026-08-20T12:05:00Z"
}
```

`capabilities` is computed per repository, not per connector. The renderer needs it to grey out actions that would fail — telling the user *before* the attempt why an action is unavailable.

### Collaborator repositories

A repo where the user is an outside collaborator appears only if the App is installed on the owning account. If it is not, the repo is invisible to us regardless of the user's own access. The UI's empty state must offer "install Sutra on another organisation" rather than implying the repo does not exist.

---

## 3.5 Organization discovery

```
GET /user/orgs            → orgs the user is a member of (membership truth)
GET /user/installations   → accounts where Sutra is installed (our access truth)
```

Both are needed, because they answer different questions, and the **difference between them is the most useful thing in the connector UI**:

```
orgs the user belongs to
├── acme-corp      ● Sutra installed, 12 repos selected   → usable
├── acme-labs      ○ Sutra not installed                  → [Install Sutra]
└── acme-secure    ▲ installed, SAML sign-in required     → [Authorise for acme-secure]
```

```json
{
  "organizations": [{
    "id": "583231", "login": "acme-corp",
    "avatar_url": "https://…",
    "installation": {
      "id": 42, "repository_selection": "selected",
      "permissions": {"contents": "write", "pull_requests": "write"},
      "suspended": false
    },
    "access": "ok",
    "restrictions": []
  }]
}
```

### Org restrictions, SSO, and enterprise-managed accounts

| Restriction | What the user sees | What we must do |
|---|---|---|
| **Third-party app restrictions** | Install requires owner approval; until then `PENDING` on GitHub's side | Show "awaiting <org> owner approval", poll, do not present it as an error |
| **SAML/SSO enforcement** | 403 with `X-GitHub-SSO: required; url=…` | Surface that exact URL as an "Authorise" action. Mark `sso_required` on the installation, **not** on the connector — one restricted org must not disable the other twelve |
| **Enterprise-managed users (EMU)** | Account exists only inside the enterprise; may not install third-party apps at all | Detect and say so. Do not retry into a wall. |
| **IP allow lists** | Requests from unlisted IPs are refused | Hosted deployment needs published egress IPs; local mode uses the user's own IP and usually passes |
| **Repository selection = `selected`** | Only chosen repos are reachable | Offer "add repositories" (deep link to installation settings); never fabricate the missing ones |
| **Installation suspended** | All calls fail | Distinct state and message — not "reconnect", which will not fix it |

The single most common production failure in GitHub integrations is treating SSO enforcement as a broken connector. It is not: the connector is fine, one organisation needs a browser round-trip. Modelling it per-installation is what keeps that true.
