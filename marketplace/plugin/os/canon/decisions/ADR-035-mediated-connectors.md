<!-- MIRROR (read-only distribution copy). Canonical: sutra/os/decisions/ADR-035-mediated-connectors.md. -->
# ADR-035: Mediated connectors — connections Sutra observes but does not own

**Status**: Accepted (implemented 2026-08-22)
**Date**: 2026-08-22
**Amends**: [ADR-034](ADR-034-connector-token-ownership.md) — narrows its scope statement without changing any of its decisions
**Driver**: founder direction 2026-08-22 — "create the connector for google, however, try to read that connector as from claude credentials … if its not authenticated from claude then it should show not authenticated else … show from which account it is connected to"

## Context

ADR-034 decided that the Connector Service is the **only** confidential client and
owns every credential Sutra touches. That is still true for every connector Sutra
authorises. It is silent on a case that now exists: a connection the operator
authorised **inside another application**, which Sutra can see but can never hold.

Google is that case. Gmail and Google Drive are connected through Claude's own
connector directory. Sutra was asked to surface them.

### What was measured, not assumed (macOS, `claude` 2.1.212, 2026-08-22)

| # | Finding | Consequence |
|---|---|---|
| M1 | claude.ai connectors use a `claudeai-proxy` transport and store **no token locally**. The one local `mcpOAuth` entry (`gdrive`) has an **empty** `accessToken`. | There is no credential for Sutra to own, adopt, or refresh. |
| M2 | The connector list is fetched per invocation from `GET /v1/mcp_servers`. | Membership is a **server** fact; Sutra cannot be offline-correct about it. |
| M3 | Each row's status is a live MCP connect + `listTools` with a 5s timeout. | The status string is a **probe outcome**, not a state. |
| M4 | The same unchanged Drive connector reported four different statuses within one hour: `Connected · tools fetch failed`, `✔ Connected`, `! Needs authentication`, `Connected · tools fetch failed`. | Rendering the probe as state would make the tile contradict itself while nothing changed. |
| M5 | Offline, `claude mcp list` prints `No MCP servers configured.` and **exits 0** — identical to being signed out and to genuinely having none. | Absence of rows is never evidence of absence of connection. |
| M6 | The `/v1/mcp_servers` payload carries `id, url, display_name, icon_url, tools[], stateless, eligible…` and **no account, email or subject**. No local store records the binding. Neither Google MCP server exposes a whoami tool, and their scopes contain no `openid`/`email`/`profile`. | **The connected Google account is not knowable**, even to a fully credentialed caller. |
| M7 | `claude mcp list` **rewrites** `~/.claude/mcp-needs-auth-cache.json` on every run. | Observing this costs a live probe against every one of the operator's connectors and mutates another program's state. It is not inert. |

## Decision

Introduce a second, deliberately weaker class of connection: a **mediated
connector** — one Sutra reports on and cannot act on. Implemented in
`marketplace/plugin/sutra-ui/mediated_connectors.py`, beside `providers.py`, the
module that already exists to observe other CLIs honestly.

1. **Google is NOT registered as a `ProviderSpec`.** The connector data model
   would force a lie: `Credential` rejects an empty `access_token`,
   `oauth_transactions.strategy` is CHECK-constrained to the three strategies
   Sutra implements, and `connectors.provider_account_id` is NOT NULL. Every one
   of those fields would have to be invented.

2. **The module imports nothing from `connectors.*`.** It therefore cannot reach
   the CredentialStore, the connector DB, or the OAuth machinery. ADR-034's
   invariant is preserved by construction, not by discipline.

3. **Sutra does not read Claude's credential store.** It was verified that Sutra's
   runtime *can* read the `Claude Code-credentials` Keychain item without a
   prompt — the item has a permissive ACL. Sutra does not, because it has no need
   to and reading another application's secrets to display a status would be a
   trust boundary Sutra should not cross. The only interface used is the CLI's
   public output.

4. **Membership is rendered as state; the probe is rendered as an observation.**
   "Added in Claude" is a claim. "Claude's last check reported it not
   authenticated" is attributed to the check that produced it, with the raw
   string quoted. Per M4 the second can change four times an hour, and a UI that
   asserts it as fact is a UI that lies three times out of four.

5. **Absence is only assertable with proof of presence.** `Not added in Claude`
   is emitted **only** when at least one `claude.ai ` row was parsed, proving the
   server list arrived. Every other path — no CLI, timeout, error, empty output —
   renders **Status unknown**. Per M5 the convenient answer and the honest answer
   differ here, and the convenient one is wrong.

6. **No account is displayed, and the absence is stated.** Per M6 the account is
   not knowable. The tile says so: *"Google account: not visible to Sutra."* The
   payload carries `account_known: false` so the promise is testable. The nearest
   value to hand is `~/.claude.json oauthAccount.emailAddress` — the **Claude**
   account, frequently an `@gmail.com` address, injected into every Claude session
   as plain text. Rendering it under a Google label would look correct on most
   developers' machines and be wrong for every operator whose Claude login differs
   from their Google connection. A test asserts it never appears.

7. **Checking is manual, rate limited and single-flight.** Per M7 a check is a
   live probe that mutates Claude's state. Opening the screen reads cache only.
   `refresh=true` is capped at one real invocation per 60s and serialised by a
   lock, so a page cannot spawn `claude` processes in a loop.

8. **The child process is contained.** Fixed argv, `stdin=DEVNULL`, an explicit
   `cwd` (never inherited — the CLI enumerates `.mcp.json` from the working
   directory, so inheriting it inside a cloned repo would let that repo's stdio
   command run), and an environment **allowlist**. A denylist was rejected: the
   backend's environment carries `SUTRA_DESKTOP_TOKEN`, which authorises replacing
   `/Applications/Sutra.app`, plus any provider client secrets the operator
   exported — all of which `claude` and every process it spawns would inherit.

9. **Served on its own route with its own truth class.** `GET
   /api/connectors/mediated`, `truth_class: "observed"`. Never merged into
   `/api/connectors/providers` (`"authoritative"`), so Claude's connections cannot
   inflate Sutra's own connected count in the rail badge.

## Consequences

- ADR-034 is unchanged for every connector Sutra authorises. Its scope statement
  now reads: the Connector Service is the only confidential client **for
  connections Sutra owns**. Mediated connections have no confidential client in
  Sutra at all.
- Sutra gains a surface that is honest about not knowing things. The dashed tile
  border and the `via Claude` chip exist so the difference is visible at a glance.
- **Observing costs a probe.** Sutra cannot report on these connections without
  running the Claude CLI, which contacts every one of the operator's connectors
  and rewrites Claude's cache. This is disclosed on the tile rather than hidden.
- The parser is coupled to human CLI output (there is no `--json`). It fails to
  `unknown`, never to a confident answer, and proof-of-fetch is deliberately
  decoupled from the strict row regex so a cosmetic format change degrades one
  row instead of making the tile announce a falsehood.
- **Not delivered**: the connected Google account. Not deferred — not knowable.
  If Anthropic later exposes the binding, point 6 is the only thing that changes.
