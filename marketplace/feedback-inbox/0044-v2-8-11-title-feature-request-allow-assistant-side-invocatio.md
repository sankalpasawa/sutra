---
issue: 44
title: "[v2.8.11] title: \"Feature request: allow assistant-side invocation of /core:feedback --pub"
author: vinitharmalkar
state: OPEN
created: 2026-04-30T11:14:46Z
updated: 2026-04-30T11:14:46Z
labels: —
url: https://github.com/sankalpasawa/sutra/issues/44
comments: []
---

# #44 [v2.8.11] title: "Feature request: allow assistant-side invocation of /core:feedback --pub

**Author:** vinitharmalkar  |  **State:** OPEN  |  **Labels:** —
**Created:** 2026-04-30T11:14:46Z  |  **Updated:** 2026-04-30T11:14:46Z
**URL:** https://github.com/sankalpasawa/sutra/issues/44

---

---
title: "Feature request: allow assistant-side invocation of /core:feedback --public under explicit user instruction"
plugin_version: "core@2.8.11"
captured_at: "2026-04-30T09:58:00Z"
captured_by: "Vinit Harmalkar (Founder's Office, Testlify)"
install_id: "379c80b799d9270b"
project_id: "9005f911b7c8"
type: "feature-request"
priority: "medium"
related_components:
  - "hooks/routing-rule.sh"
  - "hooks/feedback-channel-guard.sh"
  - "scripts/feedback.sh"
  - "PROTO-024 V1 (collaborator-visible inbox)"
---

# Feature request: optional assistant-side invocation of `/core:feedback --public`

## What I'm asking for

When a user explicitly instructs the assistant to file feedback (e.g. "send this to Sutra dev"), give Sutra a sanctioned, auditable path for the assistant to invoke `/core:feedback --public "<message>"` on the user's behalf — instead of always requiring the user to type the slash command themselves.

The current routing rule (`hooks/routing-rule.sh`) makes this an absolute prohibition with a "no exception" clause. I'm not asking Sutra to remove the safe-default — I'm asking for a **scoped, opt-in escape hatch** for users who want it.

## Why this matters (my use case)

I run a daily Sutra-mediated workflow as a founder's-office operator at Testlify. The friction pattern I keep hitting:

1. Something breaks (e.g. the inbox-display.sh hook bug I'm filing today).
2. The assistant analyzes thoroughly and stages a detailed report at `~/.sutra/feedback/pending/`.
3. To publish, I have to switch focus, copy the message, type the slash command, paste, hit enter.
4. In practice this means I publish far less often than I should — feedback that should reach the Sutra dev team gets stuck in pending forever.

The current design optimizes for "explicit user action = unambiguous accountability". My need is the opposite: I want Sutra to be a smooth-running OS where I can dictate "send this" once and trust the system to execute. The friction is the bug for users like me.

## Concrete proposal — three layers, opt-in

I think the design space has at least three reasonable options. Listing in increasing strictness:

### Option A — environment-gated permission

```bash
# In ~/.zshrc or .env
export <HIGH-ENTROPY>
```

When set, `routing-rule.sh` allows the assistant to invoke `/core:feedback --public` if and only if:

- The current user message contains an explicit publish instruction (regex match on "publish", "file", "send to sutra", "/core:feedback")
- The proposed message body has been shown to the user in the same turn
- The user's most recent message is less than N seconds old (no stale auth)

### Option B — `--auto` flag on the slash command itself

```
/core:feedback --public --auto "<message>"
```

The `--auto` flag signals "this invocation came from the assistant, not the user". The binary applies tighter scrubbing, includes a `via_assistant: true` marker in the issue body, and tags the issue with `[assistant-filed]` for triage. Users opt in by configuring `SUTRA_ASSISTANT_FEEDBACK=1`; assistant only invokes when configured.

### Option C — confirmation handshake

The assistant invokes `/core:feedback --preview "<message>"` (new flag) which:

1. Scrubs the message
2. Shows the user the exact issue title + body that *would* be published
3. Returns a 30-second token to the assistant
4. Assistant calls `/core:feedback --confirm <token>` once the user says "yes, send"

This preserves the "explicit user action" property while removing the typing friction. Closest to the current design philosophy.

## What I'd accept

Any of A, B, or C — or a fourth design Sutra prefers — would unblock my workflow. **C** is closest to the current "explicit accountability" design point and would probably get past code review fastest. **A** is the lowest-effort to implement. **B** lives in the middle.

## What I'd push back on

- "Just type the command yourself" — the friction is exactly the problem.
- "Use `--public` interactively today" — I do, but the cost of context-switching means I file maybe 1 in 5 things I should.
- "Wait for V2 with encryption" — encryption is orthogonal to invocation flow.

## How I see this fitting Sutra's existing primitives

- The depth-marker enforcement already shows Sutra is comfortable with conditional gates (`company` profile hard-blocks, `project` warn-only, `individual` warn-only)
- The trust mode design already encodes "auto-approve recoverable, prompt on catastrophic" — same shape applies here
- PROTO-024 V1's collaborator-visible inbox model is unchanged either way
- `feedback-channel-guard.sh` could remain as-is — Option B/C wouldn't trigger the guard since the binary's own rail is used, not direct `gh issue create`

## Cost-benefit

| Dimension | Current state | With this feature |
|---|---|---|
| Friction for high-volume users | High — typed-out command per issue | Low — "send this" works |
| Accountability trail | Strong (user typed) | Strong (Option C) / Strong-with-marker (Option B) / Strong-with-trigger-detection (Option A) |
| Hallucination risk | None (assistant cannot invoke) | Low (gated by user-message regex / confirmation handshake) |
| Cross-tenant hijack risk | None | None — gates fire locally on user machine, no remote bypass |
| Implementation complexity | n/a | Option A: ~30 LoC. Option B: ~80 LoC + scrub flag. Option C: ~150 LoC + state-store. |

## Filed alongside

Filed in the same batch as `<HIGH-ENTROPY>.md`. Ironic dependency: I'm using the system I want to improve to ask for the improvement.

---

**Reporter note**: Filed via Sutra's sanctioned `/core:feedback --public` channel. Routing-rule.sh respected; no `gh issue create` shortcuts attempted, even though my preference would be for the assistant to have invoked it directly.
