# Sutra Connectors — Quickstart

**Version:** v2.11.1

---

## What this is

Sutra Connectors is a governed bridge from your Sutra session to provider APIs (Slack, Gmail, and more coming). The plugin owns audit, depth-gating, and tier-scoped policy. Direct backends call provider APIs without a third-party broker — your tokens never leave your machine.

---

## Prereqs

- Node.js ≥18 (Sutra plugin requires it; check with `node --version`)
- `age` binary (encryption-at-rest for credentials) — **on macOS with brew, Sutra auto-installs this on first connectors command**; other OSes see install table below

Install `age` for your OS:

| OS | Command | Auto-install? |
|---|---|---|
| macOS | `brew install age` | ✅ — Sutra runs this if brew is present |
| Debian / Ubuntu | `sudo apt install age` | ❌ (sudo) — install manually |
| Arch | `sudo pacman -S age` | ❌ (sudo) — install manually |
| Windows (scoop) | `scoop install age` | ❌ — install manually |
| Manual | https://github.com/FiloSottile/age/releases | — |

Verify: `age --version` should print `1.x.x`.

---

## Install the plugin

```
/plugin marketplace add sankalpasawa/sutra
/plugin install core@sutra
```

(`/plugin install sutra@marketplace` also works; `core@sutra` is the canonical form.)

> **Runtime npm deps are pre-bundled.** As of v2.11.1, the plugin ships `connectors/node_modules/` (yaml, cockatiel, nanoid; ~2.2 MB) inside the plugin tree, so `/plugin install` and `/plugin update` both deliver a fully-working connectors stack with **zero first-call npm install delay**. No `npm install` step required.

---

## First-time setup

### 1. Generate an age keypair (one-time, ~10s)

```bash
mkdir -p ~/.sutra-connectors/keys && chmod 700 ~/.sutra-connectors/keys
age-keygen -o ~/.sutra-connectors/keys/sutra-identity.key
grep '^# public key:' ~/.sutra-connectors/keys/sutra-identity.key | sed 's/^# public key: //' > ~/.sutra-connectors/keys/sutra-recipient.txt
chmod 600 ~/.sutra-connectors/keys/sutra-identity.key
chmod 644 ~/.sutra-connectors/keys/sutra-recipient.txt
```

The identity key decrypts; the recipient file encrypts. Both stay on your machine.

### 2. Connect Slack (~2 minutes)

```bash
sutra connect slack
```

The CLI walks you through:

1. Open https://api.slack.com/apps → **Create New App** → **From scratch**
2. Pick your workspace, then add these Bot Token scopes: `channels:history`, `channels:read`, `chat:write`, `users:read`
3. **Install to Workspace**, copy the Bot User OAuth Token (`xoxb-...`)
4. Paste it at the prompt

The token is encrypted with your age key and saved to `~/.sutra-connectors/oauth/slack.age`.

### 3. Verify it works

```bash
sutra connect-test slack
```

Expected output:

```
✔ Slack OK
  team:    YourWorkspace
  user:    your-bot-name
  bot_id:  B0123ABCDEF
  url:     https://yourworkspace.slack.com/
```

---

## Daily use

Once connected, call any capability via `sutra call <connector> <tool> --key=value`:

```bash
# List channels the bot can see
sutra call slack list-channels

# Read recent messages from a channel
sutra call slack read-channel --channel=C0123ABCDEF --limit=10

# Post a message
sutra call slack post-message --channel=C0123ABCDEF --text="hello from Sutra"
```

All `--key=value` args are forwarded to the provider API. See the per-connector manifest in `manifests/<connector>.yaml` for the full tool list.

---

## Troubleshooting

| Error | Fix |
|---|---|
| `age: command not found` | Install `age` (see Prereqs). |
| `No credential found for connector: slack` | Re-run `sutra connect slack`. |
| `Slack API error: invalid_auth` | Token revoked or expired — re-run `sutra connect slack`. |
| `node_modules missing` | Should not happen on v2.11.0+ (deps pre-bundled). Recovery: `cd ~/.claude/plugins/cache/sutra/core/<version>/connectors && npm install --omit=dev` |
| First call feels slow | Should be instant on v2.11.1+ (deps pre-bundled). On older versions preflight ran `npm install --omit=dev` on first call — bump to v2.11.1 to remove the delay. |

---

## Mode A vs Mode B — when to pick

| Mode | Use when | What's different |
|---|---|---|
| **A — legacy** (default) | You're calling Slack/Gmail directly from your shell or a CI job | Single-process, no idempotency key required, no AbortSignal — the current Sutra default |
| **B — native-compat** (opt-in) | You're wrapping calls in a Native Temporal Activity (Sutra v1.0+) | Requires `idempotency_key` + `signal` in ctx; cockatiel retry policy applies; 1 MB payload bound enforced |

Most users want **Mode A**. Mode B is for the Native runtime per spec §M1.2.

---

## Where credentials live

```
~/.sutra-connectors/
├── keys/
│   ├── sutra-identity.key      # decryption key (chmod 600)
│   └── sutra-recipient.txt     # public recipient (chmod 644)
└── oauth/
    ├── slack.age               # encrypted at rest
    └── slack.json              # plaintext shadow during migration window
```

The `.json` shadow exists for backward compatibility during the migration window. See `CHARTER.md` for retention policy.

---

## Audit trail

Every call writes a JSONL line to `.enforcement/connector-audit.jsonl` in your project root:

```json
{"ts":1777501234,"clientId":"your-project","tier":"T1","depth":3,
 "capability":"slack:post-message:#general","outcome":"allowed",
 "sessionId":"<id>","redactedArgsHash":"<sha256>"}
```

Filter recent calls:

```bash
jq -r '"\(.ts) \(.capability) \(.outcome)"' .enforcement/connector-audit.jsonl | tail -20
```

Fields: `ts`, `depth`, `tier`, `capability`, `outcome`, `redactedArgsHash` (sha256 of the redacted args — actual values never written to disk).

---

**Sutra Connectors v2.11.1** · See [CHARTER.md](./CHARTER.md) for governance contract · See [ARCHITECTURE.yaml](./ARCHITECTURE.yaml) for module structure.
