---
name: deepseek
preamble-tier: 3
version: 1.0.0
description: |
  Sutra-owned peer-reviewer wrapper for DeepSeek's Anthropic-compatible API.
  Four modes — Review (diff pass/fail gate), Challenge (adversarial),
  Consult (free-form Q&A; v1 fresh-per-call, no session replay), Design-review
  (single doc). Mirrors codex-sutra structurally; uses DeepSeek as the second
  AI lane for second-opinion + convergence under PROTO-019 v2 (deferred).
  v1-min ships factually correct transport + downgrade defense + auditable
  SKIPPED logging. Governance machinery (scrubber, session-machine, preflight
  budgeting, schema unification) is deferred to v2 with documented TODO markers
  (see "Known v1 limitations" below).
allowed-tools:
  - Bash
  - BashOutput
  - Read
  - Write
  - AskUserQuestion
upstream-source:
  parent-pattern: codex-sutra v1.0.0 (sibling skill)
  api: DeepSeek anthropic-compat endpoint (api.deepseek.com/anthropic)
  api-docs: https://api-docs.deepseek.com/guides/anthropic_api
---

## Why this skill exists

Sutra has codex-sutra (OpenAI codex CLI). Adding DeepSeek as a second AI
lane means second-opinion review by a different vendor + reasoning model.
Disagreement between codex and deepseek carries signal that single-vendor
review does not.

v2 (deferred) wires both into a PROTO-019 union gate (both must converge).
v1 ships founder-invoked only.

---

## Codex review history (rounds 1-4)

This skill was designed under PROTO-019 directive 1778399454 with 4 codex
rounds. Final verdict ADVISORY. Trail at:
`.enforcement/codex-reviews/2026-05-10-deepseek-sutra-design.md`.

---

## Known v1 limitations (v2 PR queued)

| Marker | Limitation | v2 plan |
|---|---|---|
| TODO[v2-scrubber] | No outbound data scrubbing (binary excl / secret regex / path allowlist). v1 sends payload as-is. | Add `bin/deepseek-payload-scrub.sh` per design §B (file -b --mime-type, AWS/JWT/PEM/.env regex, ≤500 KB cap with AskUserQuestion). |
| TODO[v2-session] | Consult session continuity disabled. Every `/deepseek consult` starts fresh. | Add UUID-scoped per-repo per-branch session dirs `.context/deepseek-sessions/<uuid>/`, replay redaction, --new-session flag. |
| TODO[v2-preflight] | No pre-flight token/cost budgeting. v1 has no wall-clock cap (D2026-05-13) — relies on API-side timeouts only. | Estimate input tokens + estimated_cost preflight gate before HTTP send. |
| TODO[v2-schema] | Separate gate-logs per skill (codex-reviews/ vs deepseek-reviews/). | Unify under canonical `sutra/os/engines/PEER-REVIEW-EVENT-SCHEMA.md`. |
| TODO[v2-shim-scrub] | Shim path (`deepseek-claude`) has no outbound scrubbing. | Pre-launch warning; eventually wrap claude-code stdin/stdout. |
| TODO[v2-shim-keychain] | Key stored at `~/.config/deepseek/auth.token` (chmod 600). | Optional macOS Keychain item. |
| TODO[v2-shim-conflict] | Shim does not detect concurrent claude-on-Anthropic session. | Lockfile + warning. |

Surfacing the gaps explicitly is the contract — silent omission would not be.

---

## Pre-flight (Step 0)

### Key resolution order (canonical-first, backwards-compatible)

| Priority | Path | Format | Notes |
|---|---|---|---|
| 1 | `$DEEPSEEK_TOKEN_FILE` (env override) | JSON or plain text (auto-detect by `.json` suffix) | Explicit operator override |
| 2 | `~/.sutra-connectors/oauth/deepseek.json` | JSON `{savedAt, token, type}` | **Canonical** — matches slack.json precedent (2026-05-01) |
| 3 | `~/.config/deepseek/auth.token` | Plain text | Legacy, kept for backwards compatibility |

First readable path wins. Fleet members can use either path; canonical is
recommended for parity with other Sutra connectors.

### Pre-flight bash

```bash
# Reap orphan temp files >24h
find /tmp/deepseek-* -mmin +1440 -delete 2>/dev/null || true

# Key resolution (canonical-first)
KEY_FILE=""
KEY_SRC=""
if [ -n "${DEEPSEEK_TOKEN_FILE:-}" ] && [ -r "$DEEPSEEK_TOKEN_FILE" ]; then
  KEY_FILE="$DEEPSEEK_TOKEN_FILE"; KEY_SRC=env
elif [ -r "$HOME/.sutra-connectors/oauth/deepseek.json" ]; then
  KEY_FILE="$HOME/.sutra-connectors/oauth/deepseek.json"; KEY_SRC=canonical
elif [ -r "$HOME/.config/deepseek/auth.token" ]; then
  KEY_FILE="$HOME/.config/deepseek/auth.token"; KEY_SRC=legacy
fi

if [ -z "$KEY_FILE" ]; then
  cat <<'SETUP'
deepseek: no key found. Setup (canonical, recommended):

  mkdir -p ~/.sutra-connectors/oauth && chmod 700 ~/.sutra-connectors/oauth
  SAVED_AT=$(date -u +%Y-%m-%dT%H:%M:%SZ)
  jq -nc --arg t "sk-YOUR-KEY-HERE" --arg s "$SAVED_AT" \
    '{savedAt:$s, token:$t, type:"api_key"}' \
    > ~/.sutra-connectors/oauth/deepseek.json
  chmod 600 ~/.sutra-connectors/oauth/deepseek.json

Get a key at https://platform.deepseek.com → API Keys.
SETUP
  COMMIT=$(git rev-parse --short HEAD 2>/dev/null || echo unknown)
  printf '{"skill":"deepseek","mode":"preflight","ts":"%s","verdict":"SKIPPED","reason":"not_configured","commit":"%s"}\n' \
    "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$COMMIT" >> .enforcement/deepseek-reviews/gate-log.jsonl
  exit 0
fi

# Kill-switch check
if [ -e "$HOME/.deepseek-disabled" ]; then
  printf '{"skill":"deepseek","mode":"preflight","ts":"%s","verdict":"SKIPPED","reason":"kill_switch","commit":"%s","key_src":"%s"}\n' \
    "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$(git rev-parse --short HEAD 2>/dev/null || echo unknown)" "$KEY_SRC" \
    >> .enforcement/deepseek-reviews/gate-log.jsonl
  exit 0
fi

# Permission enforcement (both file shapes)
PERM=$(stat -f '%Lp' "$KEY_FILE" 2>/dev/null || stat -c '%a' "$KEY_FILE")
if [ "$PERM" != "600" ]; then
  echo "deepseek: $KEY_FILE has perms $PERM — chmod 600 required" >&2
  exit 1
fi

# Extract token: JSON canonical uses jq .token; plain text uses file contents
if [[ "$KEY_FILE" == *.json ]]; then
  if ! command -v jq >/dev/null 2>&1; then
    echo "deepseek: jq required to read canonical JSON keystore; install jq or use legacy path" >&2
    exit 1
  fi
  DEEPSEEK_TOKEN=$(jq -r '.token' "$KEY_FILE")
else
  DEEPSEEK_TOKEN=$(cat "$KEY_FILE")
fi

if [ -z "$DEEPSEEK_TOKEN" ] || [ "$DEEPSEEK_TOKEN" = "null" ]; then
  echo "deepseek: token empty/null in $KEY_FILE (KEY_SRC=$KEY_SRC)" >&2
  exit 1
fi
```

All downstream curl invocations use `$DEEPSEEK_TOKEN` (the resolved string),
not `$(cat "$KEY_FILE")` — covers both file shapes uniformly.

---

## Mode detection

| Input | Mode | Step |
|---|---|---|
| `/deepseek review [focus]` | Review | 2A |
| `/deepseek challenge [focus]` | Challenge | 2B |
| `/deepseek consult <prompt>` | Consult | 2C |
| `/deepseek design-review <path>` | Design Review | 2D |
| `/deepseek` no args, diff exists | AskUserQuestion: review / challenge / other | — |
| `/deepseek` no args, no diff | Ask: "What should deepseek look at?" | — |

`--flash` flag anywhere: strip it, set model to `deepseek-v4-flash` (cheaper, faster, no reasoning).

---

## Model + transport

**Endpoint**: `https://api.deepseek.com/anthropic/v1/messages`
**Auth header**: `x-api-key: $(cat ~/.config/deepseek/auth.token)` (per DeepSeek anthropic-compat docs; NOT `Authorization: Bearer`)
**Default model**: `deepseek-v4-pro` (no `[1m]` suffix — that's a Claude-Code-side context tag; the API takes the base name per docs)
**Override**: env `DEEPSEEK_MODEL`
**Effort knob**: request body includes `thinking: {type: "enabled", budget_tokens: 32000}` + `output_config: {effort: "high"}` per DeepSeek docs.

### Model-downgrade defense (folds R2-P1.1 + R4-P2.1)

After every `/v1/messages` response, compare `request.model` vs `response.model`:

| Condition | Verdict | reason |
|---|---|---|
| `response.model` field present + exact match | (continue with intended verdict) | (none) |
| `response.model` absent | ADVISORY | `response_model_missing` |
| `response.model` is a versioned alias of requested (e.g. `deepseek-v4-pro-202405` for `deepseek-v4-pro`) — string starts-with match | (continue with intended verdict) + log advisory | `model_aliased` |
| `response.model` is a known downgrade (requested=`deepseek-v4-pro`, returned=`deepseek-v4-flash`) | **FAIL** | `model_downgrade` |
| `response.model` is any other mismatch | ADVISORY | `model_unexpected` |

`DEEPSEEK_ACCEPT_DOWNGRADE=1` env converts FAIL → ADVISORY for next call only (audit-logged).

---

## Per-mode reasoning effort defaults

| Mode | thinking.budget_tokens | output_config.effort | Reason |
|---|---|---|---|
| Review (2A) | 32000 | high | Bounded by diff; needs thoroughness |
| Challenge (2B) | 32000 | high | Adversarial; bounded by diff |
| Consult (2C) | 32000 | high | Large context; needs depth |
| Design-review (2D) | 16000 | medium | Document-bounded; speed > max reasoning |

Override via env `DEEPSEEK_THINKING_BUDGET` (integer) or `DEEPSEEK_EFFORT` (low/medium/high).

---

## The launcher pattern (used by all 4 modes)

Same launcher discipline as codex-sutra: process-group isolation, single-writer
TMPDONE rule, stdin `</dev/null`. macOS uses python `os.setsid()` fallback
when `setsid` binary absent.

```bash
# Orphan reap
find /tmp/deepseek-* -mmin +1440 -delete 2>/dev/null || true

TS=$(date +%s)
TMPRESP=/tmp/deepseek-resp.$$.${TS}.txt
TMPERR=/tmp/deepseek-err.$$.${TS}.txt
TMPDONE=/tmp/deepseek-done.$$.${TS}        # WRAPPER WRITES ONLY
TMPNAT=/tmp/deepseek-natural.$$.${TS}      # SUBSHELL WRITES ONLY

REQUEST_JSON=$(jq -nc \
  --arg model "${DEEPSEEK_MODEL:-deepseek-v4-pro}" \
  --argjson budget "${DEEPSEEK_THINKING_BUDGET:-32000}" \
  --arg effort "${DEEPSEEK_EFFORT:-high}" \
  --rawfile prompt "$PROMPT_FILE" \
  '{
    model: $model,
    max_tokens: 8192,
    thinking: { type: "enabled", budget_tokens: $budget },
    output_config: { effort: $effort },
    messages: [{ role: "user", content: $prompt }],
    stream: true
  }')

# Launch curl in its own process group — uses $DEEPSEEK_TOKEN
# (resolved by pre-flight, works for both JSON canonical + plain text legacy)
if command -v setsid >/dev/null 2>&1; then
  setsid bash -c "curl -sS \
    -H \"x-api-key: $DEEPSEEK_TOKEN\" \
    -H \"Content-Type: application/json\" \
    -H \"anthropic-version: 2023-06-01\" \
    -d @<(echo \"\$REQUEST_JSON\") \
    https://api.deepseek.com/anthropic/v1/messages \
    > \"$TMPRESP\" 2> \"$TMPERR\"; echo \$? > \"$TMPNAT\"" &
else
  # macOS fallback
  nohup python3 -c "
import os, subprocess, json
os.setsid()
req = '$DEEPSEEK_TOKEN'
body = '''$REQUEST_JSON'''
r = subprocess.run(['curl','-sS',
  '-H', f'x-api-key: {req}',
  '-H', 'Content-Type: application/json',
  '-H', 'anthropic-version: 2023-06-01',
  '-d', body,
  'https://api.deepseek.com/anthropic/v1/messages'],
  stdin=subprocess.DEVNULL,
  stdout=open('$TMPRESP','w'),
  stderr=open('$TMPERR','w'))
open('$TMPNAT','w').write(str(r.returncode))
" > /dev/null 2>&1 &
fi
DEEPSEEK_PID=$!
PGID=$DEEPSEEK_PID

# Poll loop — no wall-clock hard cap (D2026-05-13).
# Stall warn at 5 min no-progress; heartbeat every 10 min.
# Founder Ctrl-C → SIGINT trap forwards to process group.
START=$(date +%s)
LAST_BYTES=0
STALL_POLLS=0
INTERRUPTED=""
LAST_HEARTBEAT_BUCKET=0

trap 'INTERRUPTED=1; kill -TERM "-$PGID" 2>/dev/null; sleep 2; kill -KILL "-$PGID" 2>/dev/null' INT

while [ ! -s "$TMPNAT" ] && [ -z "$INTERRUPTED" ]; do
  sleep 30
  NOW=$(date +%s); ELAPSED=$((NOW-START))
  BYTES=$(wc -c < "$TMPRESP" 2>/dev/null || echo 0)
  if [ "$BYTES" = "$LAST_BYTES" ]; then STALL_POLLS=$((STALL_POLLS+1));
  else STALL_POLLS=0; LAST_BYTES=$BYTES; fi
  [ $STALL_POLLS -eq 10 ] && echo "deepseek: no output for 5 min — may be stuck. Founder can interrupt with Ctrl-C."
  HEARTBEAT_BUCKET=$((ELAPSED/600))
  if [ "$HEARTBEAT_BUCKET" -ne "$LAST_HEARTBEAT_BUCKET" ] && [ "$HEARTBEAT_BUCKET" -gt 0 ]; then
    LAST_HEARTBEAT_BUCKET=$HEARTBEAT_BUCKET
    echo "deepseek still running at $((HEARTBEAT_BUCKET*10)) min. No hard cap; Ctrl-C to interrupt."
  fi
done

# Wrapper writes final TMPDONE
if [ -n "$INTERRUPTED" ]; then
  echo "EXIT:130 REASON:interrupted" > "$TMPDONE"
elif [ -s "$TMPNAT" ]; then
  NAT_EXIT=$(cat "$TMPNAT")
  if [ "$NAT_EXIT" = "0" ]; then
    echo "EXIT:0 REASON:natural" > "$TMPDONE"
  else
    echo "EXIT:$NAT_EXIT REASON:curl_exit_$NAT_EXIT" > "$TMPDONE"
  fi
else
  echo "EXIT:255 REASON:unknown" > "$TMPDONE"
fi
```

---

## SSE response parsing (anthropic-format)

DeepSeek's anthropic-compat endpoint emits standard Anthropic SSE events:
`event: message_start` / `event: content_block_start` / `event: content_block_delta`
(with `data: {"type":"content_block_delta","delta":{"type":"text_delta","text":"..."}}`)
/ `event: content_block_stop` / `event: message_delta` (carries `usage` + `stop_reason`)
/ `event: message_stop`.

Parser uses `python3` (no deps) to read named events and accumulate `delta.text`,
capture `usage` on `message_delta`, observe `stop_reason`. Skill embeds this
parser inline rather than shipping a separate `bin/` script (matches codex-sutra
single-file pattern). See parse block below.

```python
# Inline parser invoked after launcher returns
python3 - <<'PARSE_EOF' < "$TMPRESP"
import sys, json, re
buf = []
usage = None
stop_reason = None
model = None
last_event = None
for line in sys.stdin:
    line = line.strip()
    if line.startswith("event:"):
        last_event = line.split(":",1)[1].strip()
        continue
    if not line.startswith("data:"):
        continue
    payload = line[5:].strip()
    if payload == "[DONE]" or payload == "":
        continue
    try:
        obj = json.loads(payload)
    except Exception:
        continue
    t = obj.get("type")
    if t == "message_start":
        msg = obj.get("message", {})
        model = msg.get("model")
        usage = msg.get("usage")
    elif t == "content_block_delta":
        d = obj.get("delta", {})
        if d.get("type") == "text_delta":
            buf.append(d.get("text",""))
    elif t == "message_delta":
        delta = obj.get("delta", {})
        if "stop_reason" in delta:
            stop_reason = delta["stop_reason"]
        if "usage" in obj:
            # accumulate output_tokens from message_delta usage block
            mu = obj.get("usage", {})
            if usage is None: usage = {}
            usage["output_tokens"] = mu.get("output_tokens", usage.get("output_tokens",0))
    elif t == "error":
        err = obj.get("error", {})
        print(json.dumps({"ok": False, "error": err.get("type","unknown"), "message": err.get("message","")}))
        sys.exit(0)
out = {
    "ok": True,
    "content": "".join(buf),
    "usage": usage,
    "stop_reason": stop_reason,
    "model": model,
}
if not buf:
    out["ok"] = False
    out["error"] = "empty_stream"
if stop_reason == "max_tokens":
    out["ok"] = False
    out["error"] = "output_truncated"
print(json.dumps(out))
PARSE_EOF
```

---

## Verdict format

```
DEEPSEEK-VERDICT: PASS | ADVISORY | CHANGES-REQUIRED
```

`[P1]` (blocker) and `[P2]` (advisory) markers identical to codex-sutra so
callers can union codex + deepseek output without parser branching.

---

## Gate-log schema

`.enforcement/deepseek-reviews/gate-log.jsonl` — one JSON per line. v1 schema:

```json
{
  "skill": "deepseek",
  "mode": "review|challenge|consult|design-review|preflight",
  "ts": "2026-05-10T08:00:00Z",
  "verdict": "PASS|ADVISORY|CHANGES-REQUIRED|FAIL|SKIPPED",
  "model": "deepseek-v4-pro|deepseek-v4-flash|...",
  "directive_id": null,
  "findings": 0,
  "advisories": 0,
  "input_tokens": null,
  "output_tokens": null,
  "estimated_cost_usd": null,
  "reason": null,
  "commit": "<sha>",
  "wall_seconds": 0,
  "killed": null
}
```

**`estimated_cost_usd` semantics** (folds R4-P2.2): this is a **post-call audit
estimate** derived from the returned `usage` block (input_tokens × input_price +
output_tokens × output_price). It is NOT a pre-call budgeting control — that
gate ships in v2 under TODO[v2-preflight]. Operators read this column for cost
visibility; it does not block calls.

v2 unifies the schema across codex-sutra + deepseek under
`sutra/os/engines/PEER-REVIEW-EVENT-SCHEMA.md` (TODO[v2-schema]).

---

## Fail-closed table (v1)

| Failure | Detection | Verdict | reason |
|---|---|---|---|
| Key missing | env empty | SKIPPED | not_configured |
| Kill-switch | `~/.deepseek-disabled` | SKIPPED | kill_switch |
| Key perms wrong | not chmod 600 | (skill exits 1, no verdict) | n/a |
| 401 | HTTP status | FAIL | auth_error |
| 429 | HTTP status | FAIL | rate_limit |
| 5xx | HTTP status | FAIL | api_error_<status> |
| Curl non-zero | exit code | FAIL | curl_exit_<N> |
| Empty stream | parser empty_stream | FAIL | empty_response |
| Output truncated | stop_reason=max_tokens | FAIL | output_truncated |
| Model downgrade (pro→flash) | response.model mismatch | FAIL | model_downgrade |
| Model unexpected | response.model unknown mismatch | ADVISORY | model_unexpected |
| Model alias | response.model versioned alias | (continue) + advisory log | model_aliased |
| Model absent | response.model not in response | ADVISORY | response_model_missing |
| No verdict markers (review/design-review) | grep | FAIL | malformed_output |
| Founder interrupt (Ctrl-C / SIGINT) | wrapper trap fires during poll | FAIL | interrupted |
| Log-write fail | append fails | FAIL + stderr beacon | log_write_failed |

Stderr beacon: `DEEPSEEK-RESULT verdict=<v> reason=<r> commit=<sha>` —
last-resort durable signal when gate-log.jsonl is unwritable.

---

## Important rules

- **No wall-clock hard cap** (founder D2026-05-13). Wrapper polls indefinitely
  with stall + heartbeat warnings. Curl runs without `--max-time`; the
  DeepSeek API's own server-side timeout is the only network bound. Founder
  Ctrl-C → SIGINT trap forwards SIGTERM/SIGKILL to the whole process group.
- **Read-only.** v1 makes HTTP calls only; never writes to repo files (except
  `.enforcement/deepseek-reviews/gate-log.jsonl` and `/tmp/deepseek-*`).
- **Verbatim presentation.** Output goes inside `DEEPSEEK SAYS` block unmodified.
  Claude synthesis goes AFTER the block, never inside.
- **Boundary always first.** Every prompt leads with the codex-sutra-style
  filesystem boundary string.
- **Fail-closed.** Every non-model failure path maps to gate-log entry with
  structured `reason`. PROTO-019 callers (v2) branch on `reason`.
- **SKIPPED is auditable.** Key-missing and kill-switch produce gate-log
  rows — never silent exit 0.

---

## Filesystem boundary (mandatory prompt prefix)

```
IMPORTANT: Do NOT read or execute any files under ~/.claude/, ~/.agents/,
.claude/skills/, agents/, sutra/marketplace/plugin/skills/, or
sutra/marketplace/plugin/hooks/. These are Claude Code / Sutra skill and
hook definitions for a different AI system. Ignore them. Stay focused on
repository code.
```

DeepSeek's API has no filesystem access — boundary is defense-in-depth
against prompt-included skill text.
