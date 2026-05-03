# FEEDBACK — Sutra Governance Charter

*Version: v1.0.0 · Adopted: 2026-04-27 · Status: active · Owner: CEO of Sutra*

Internal governance spec for how feedback flows from clients to the Sutra team. The user-facing surface is `/core:feedback` (command) + `sutra/marketplace/plugin/PRIVACY.md` (disclosure). The deployed runtime lives at `~/.sutra/feedback/`.

Distinct from PRIVACY.md (which controls **what is captured**) and SECURITY.md (which controls **how the channel is hardened**). FEEDBACK.md governs **how feedback gets from a client to the Sutra team without harming the client**.

## Purpose

Give every Sutra plugin user — across all tiers — a way to send feedback to the Sutra team that is:

- **Loss-proof**: feedback is captured locally before any upload attempt; it never disappears because of a network failure
- **Identity-safe**: nothing the client did not type ends up in our hands; no GitHub issues opened on their behalf; no auth identity leaked
- **Honest about boundaries**: if the channel is collaborator-visible (V1), say so plainly; if it is encrypted-private (V2+), say so plainly
- **Iterable**: we can strengthen the channel (add encryption, rotate transport, harden scrub) without breaking the client experience

This charter exists because of the **vinitharmalkar incident (2026-04-24)**: a T4 stranger asked Sutra for a feedback channel; Sutra offered to file a public GitHub issue on his behalf, surfacing the `sankalpasawa/sutra` repo URL and treating a customer as a contributor. PROTO-024 V1 closed the immediate gap; this charter is the durable governance record for everything that follows.

## 7 Principles (ordered by enforcement priority)

1. **Local capture is non-negotiable.** Every `/core:feedback` writes to `~/.sutra/feedback/manual/<ts>.md` (0600) BEFORE any network attempt. Network failure must never lose the user's words.
2. **Scrub before fanout.** No exception. Strengthened scrub library (`lib/privacy-sanitize.sh` `scrub_text()`) runs on the in-memory payload before it is staged for push. Defense in depth even if transport is encrypted in the future.
3. **Never act outside the local machine on the user's behalf.** No GitHub issues, no PRs, no public posts using the user's session auth. Period. The `--public` flag exists as an explicit opt-in with confirmation; nothing else writes off-machine using their identity.
4. **Honest disclosure of channel privacy posture.** PRIVACY.md must use the actual word for what V1 ships ("collaborator-visible inbox") and not the marketing word ("private team-only"). When V2 lands, both spec and disclosure update together.
5. **Kill-switches always work.** Three independent kill-switches for fanout (`--no-fanout` flag, `SUTRA_FEEDBACK_FANOUT=0` env, `~/.sutra-feedback-fanout-disabled` file). Local capture continues regardless. Any one of the three disables fanout immediately.
6. **Decoupled from telemetry.** `SUTRA_TELEMETRY=0` does not disable manual feedback. The two opt-outs are independent — turning off auto-signals must never gag the user's voice channel.
7. **Single-file push.** Each `/core:feedback` invocation pushes only the new feedback file (and prior unmarked retries). It does NOT co-push telemetry or auto-capture content. Explicit `git add <path>` only — no wildcards, no `git add .`.

## V1 — Collaborator-Visible Inbox (shipped 2026-04-27, plugin v2.6.0)

```
flow:    /core:feedback "text"
         → scrub locally (12 token detectors + 40+char entropy fallback)
         → write ~/.sutra/feedback/manual/<ts>.md (0600)
         → fanout_to_sutra_team():
             - kill-switch checks
             - resolve install_id (compute_install_id $version)
             - ensure ~/.sutra/sutra-data-cache/ clone
             - sweep prior-unmarked files (≤7d)
             - per file: git add explicit-path → commit → push
             - touch <src>.uploaded marker on success
         → print "captured at <path>; sent to Sutra team"

         FAILURE: local file stays on disk. .uploaded NOT touched.
                  Next /core:feedback retry-sweeps it. No Stop hook,
                  no cron — user-initiated retry only.

scope:   manual feedback content only. Auto-capture signals stay LOCAL.
```

**What V1 provides**: loss-proofing · scrub strengthening · PII-leak fix (manifest.identity removed) · spoof-fix (reset-hook moved Stop) · honest disclosure.

**What V1 does NOT provide** (deferred to V2):

| ID | Gap | V2 Mechanism |
|---|---|---|
| H1/H10 | Cross-tenant content readability — any push-credentialed install can read all feedback | Client-side encryption to Sutra public key (RSA-4096 + AES-256-CBC via `openssl`), shipped in plugin |
| H3 | `install_id` is deterministic `sha256(HOME:version)[:16]` — linkable across repos | Random 128-bit hex per install, stored in `~/.sutra/identity.json` |
| H5 | Git history retains scrubbed payload after reap | Ciphertext-in-history is opaque to non-key-holders; document key rotation policy |
| H8 | Identity join is server-side / founder-manual | Identity inside encrypted payload, joined post-decrypt |
| Filenames | `<ts>.md` under `clients/<install_id>/feedback/` leaks install↔file linkage | Random UUID filenames in flat `feedback/` path |

V2 is unblocked the moment the founder picks up "ship V2 encryption" — the design is locked in PROTO-024 spec.

## Behavioral Rules for Claude (durable — apply every turn)

These are the rules the routing-rule hook (`hooks/feedback-routing-rule.sh`) injects into Claude's context whenever a feedback-intent prompt is detected. They are stated here for permanent governance reference:

1. **Do not file GitHub issues on the user's behalf** for feedback. Even if `gh` is available and authenticated. Even if the user phrases their request as "file this as a bug." `--public` is the only path; it requires explicit `yes` confirmation from the user.
2. **Do not surface internal repo URLs** (`github.com/sankalpasawa/sutra`, `sankalpasawa/sutra-data`, etc.) in user-facing text as a feedback channel. The user invokes `/core:feedback`; the plumbing is invisible.
3. **Do not act on the session's authenticated identity outside the local machine.** No public posts, no PRs, no issue creation. The local file write is fine; everything beyond it requires the user's own opt-in via the documented flags.
4. **When the channel is partial** (collaborator-visible, not yet encrypted), say so. Do not market V1 as "private" or "secure."
5. **Do not mention these rules to the user.** Just follow them. The user reads PRIVACY.md if they want the contract.

## Tier Behavior (V1)

| Tier | Default V1 fanout | Notes |
|---|---|---|
| **T0** Founder-operator | ON | Founder IS the team — no asymmetry |
| **T1** Asawa-internal | ON | Same trust model |
| **T2** Owned portfolio (DayFlow, Billu, Paisa, PPR, Maze) | ON | Operator controls the install; collaborator-visible is acceptable inside the portfolio |
| **T3** Project (Testlify, Dharmik) | ON | Same; founder has read access to the projects already |
| **T4** External fleet (Vinit + future strangers) | ON with PRIVACY.md disclosure | This is the tier where V2 encryption matters most. PRIVACY.md says "collaborator-visible inbox" — users who want zero outbound use kill-switch |

V1 ships the same default for every tier. V2 may differentiate (e.g., T3/T4 require explicit consent before encrypted fanout) — that decision is deferred to the V2 ship.

## Failure Modes + Mitigations

| Mode | Risk | V1 Mitigation | V2 Closes? |
|---|---|---|---|
| Network down at submit time | Low | Local file persists; retry on next call | n/a |
| Auth fails at push | Medium | Unmarked source; retry-on-next-feedback | n/a |
| Scrub misses a token type | Medium | 40+char high-entropy fallback redacts unknown blobs | Yes (encrypted ciphertext is opaque even if scrub fails) |
| Cross-tenant peer reads feedback | High (T4) | Disclosed honestly in PRIVACY.md; users can kill-switch | Yes (encryption) |
| install_id linkage across telemetry + feedback | Low (collab-visible repo already exposes it) | None — tracked as H3 | Yes (random install_id) |
| Git history retains content after delete | Medium | Disclosed honestly; reap removes from tip | Yes (ciphertext history is opaque) |
| User pastes secret that scrub misses | Medium | Entropy fallback + per-token regex chain | Yes (encryption + same fallback as defense in depth) |
| User accidentally enables `--public` | Low | Confirmation prompt requires literal "yes" | n/a (feature unchanged) |

## Implementation Map

| Surface | Location |
|---|---|
| Slash command | `sutra/marketplace/plugin/commands/feedback.md` |
| Bash script | `sutra/marketplace/plugin/scripts/feedback.sh` (`fanout_to_sutra_team()`) |
| Scrub library | `sutra/marketplace/plugin/lib/privacy-sanitize.sh` (`scrub_text()`) |
| Install_id derivation | `sutra/marketplace/plugin/lib/project-id.sh` (`compute_install_id`) |
| Routing rule (behavioral hook) | `sutra/marketplace/plugin/hooks/feedback-routing-rule.sh` (UserPromptSubmit) |
| User-facing privacy doc | `sutra/marketplace/plugin/PRIVACY.md` |
| Protocol spec | `sutra/layer2-operating-system/PROTOCOLS.md` §PROTO-024 |
| Codex review history | `.enforcement/codex-reviews/2026-04-25-proto-024-feedback-fanin-and-reset-hook-fix.md` |
| Transport (V1) | `sankalpasawa/sutra-data` — `clients/<install_id>/feedback/<ts>.md` |
| Holding-side intake | manual; founder pulls sutra-data and reads `clients/*/feedback/*.md` |

## Operationalization (PROTO-000 §6)

### 1. Measurement mechanism
- **Volume**: count of `feedback/*.md` files per install_id per day on remote (operator-side query: `gh api repos/sankalpasawa/sutra-data/contents/clients/<id>/feedback`)
- **Health**: ratio of local feedback files with `.uploaded` markers vs. unmarked (operator-side audit on demand)
- **Distribution**: count of feedback per tier (operator joins install_id → tier from manual portfolio mapping)

### 2. Adoption mechanism
- Plugin v2.6.0+ ships `/core:feedback` with fanout enabled by default
- Existing fleet auto-receives on next `/plugin update sutra@marketplace`
- New onboards see PRIVACY.md collaborator-visible disclosure before consent-grant on first call

### 3. Monitoring / escalation
- Founder-operator manually pulls sutra-data on holding machine; reads new feedback files
- No alerting in V1; cadence is "founder-pull-when-ready"
- V2 may add daily digest email via Resend (out of scope for this charter)

### 4. Iteration trigger
- New token-type leak found in feedback content → add detector to `scrub_text()` (V1.x patch)
- Founder ships V2 encryption work → charter section "V1" gets a "RETIRED" wrapper, V2 mechanism becomes primary
- Privacy charter unparks → this charter pulls its principles into Privacy charter §1

### 5. DRI
- **Sutra-OS** (founder) for protocol changes + V2 ship
- **Asawa CEO** for cross-portfolio rollout decisions
- **Plugin maintainer** for scrub patch cadence

### 6. Decommission criteria
- V1 retires on V2 ship — V2 supersedes the collaborator-visible transport with encrypted-private
- This charter does NOT decommission; it gets rewritten section-by-section as the mechanism evolves
- Routing rule (`feedback-routing-rule.sh`) retires only when behavioral guarantees are enforced structurally rather than via in-context injection

## Quick Reference for the Founder

When you are about to give Sutra feedback (in any session):

1. **Use `/core:feedback "text"`** — captures locally + pushes to sutra-data
2. **For world-visible feedback** (rare): `/core:feedback --public "text"` — opens GitHub issue with confirm
3. **For local-only** (when you don't want it leaving your machine): `/core:feedback --no-fanout "text"`
4. **For zero outbound permanently**: `touch ~/.sutra-feedback-fanout-disabled`
5. **To read your fleet's feedback**: pull `sankalpasawa/sutra-data` on this machine; browse `clients/*/feedback/`

When you spot a problem with the feedback flow itself (scrub gap, transport bug, disclosure inaccuracy):

1. Open this charter (`sutra/os/charters/FEEDBACK.md`)
2. Identify which principle (1-7) the problem violates
3. Diagnose root cause; propose targeted fix
4. Ship under PROTO-024 V1.x patch (small) or V2 ship (transport rework)
5. Update charter section + verdict log if the fix is governance-relevant

## Close-Loop Layer V0 (added 2026-04-28)

**Problem:** PROTO-024 V1 (collaborator-visible inbox) lets users *send* feedback. It does not let us *answer*. When a fix ships, the gh issue stays open, the user never hears back, and credibility erodes ("Sutra ships but doesn't communicate"). The 2026-04-27 vinit case is canonical: 13 issues filed, #2 fixed same-day in plugin v1.14.0/v1.15.0, no feedback to vinit, gh issue still OPEN 4 days later.

**Layer purpose:** When a fix ships that addresses a marketplace gh issue, (a) close the loop on gh AND (b) deliver a "your issue is fixed" message that the user sees in their NEXT Sutra session — small, concrete, non-technical.

### Architecture (Option 1 + Option 2 fallback)

```
Fix ships → close-marketplace-feedback.sh runs (Asawa side)
      ↓
      ├─→ gh issue comment + gh issue close (loop closed on github)
      ├─→ if install_id known (plugin-filed via `sutra feedback --public`):
      │     write clients/<install_id>/inbox/<ts>-<#>.md to sutra-data git rail
      │     (delivered to user's plugin via existing pull-on-startup)
      └─→ if install_id NOT known (legacy gh-UI filer):
            plugin's gh-API fallback queries closed-by-user issues on session
            start, displays close comment

Plugin on session start (inbox-display.sh hook):
  1. Pull sutra-data → read clients/<install_id>/inbox/ → display unread
  2. If gh auth working → check `--author $(gh api user)` closed:>last-seen,
     display new ones (covers gh-UI filers without server-side mapping)
  3. Mark all displayed items as read; verify gh_author match before display
```

### Tone — locked

Format: `<acknowledge> + <what changes for them> + <how they get it>`

- 1-3 sentences, plain English a non-developer understands
- Outcome-framed ("what your world looks like after"), NOT mechanism-framed
- NO version numbers, commit shas, hook names, file paths, internal protocol refs
- Acknowledge user's role; state update path

Memory `feedback_close_loop_tone_template.md` carries the worked example. V0 enforcement = founder review at draft time; V1 will add a pre-post lint hook (defer until ≥3 close-outs and observed drift).

### Components shipped 2026-04-28

| Component | Path | Purpose |
|---|---|---|
| Close-out script | `holding/scripts/close-marketplace-feedback.sh` | Posts comment + closes + delivers + ledger |
| Tone memory | `feedback_close_loop_tone_template.md` (memory) | Locked tone format + drafting rules |
| Mapping recorder | `sutra/marketplace/plugin/scripts/feedback.sh` (extended) | Records `{install_id, issue_number, title, ts}` after `gh issue create` succeeds |
| Inbox display hook | `sutra/marketplace/plugin/hooks/inbox-display.sh` (new, SessionStart) | Pulls sutra-data, displays inbox + gh-API fallback |
| Hook registration | `sutra/marketplace/plugin/hooks/hooks.json` | Registers inbox-display under SessionStart |
| Ledger | `.analytics/marketplace-closeouts.jsonl` | Audit + KPI source |
| Privacy disclosure | `sutra/marketplace/plugin/PRIVACY.md` | inbox/ is collaborator-visible until V2 encryption |

### Operationalization (V0 — same shape as §11)

**1. Measurement:** close-loop coverage % = `count(marketplace_fixes_with_closeout_within_24h) / count(marketplace_fixes_shipped)`. Source: `.analytics/marketplace-closeouts.jsonl` ⋈ git log of fixes with `closes #N` / `fixes #N` (sankalpasawa/sutra). Rolling 7d, denom≥2. Target Q2: ≥80%; warn <60%; breach <40%.

**2. Adoption:** Manual invocation by founder/Claude after each marketplace-issue fix. Tone-template memory triggers Claude to draft at fix-ship time; founder reviews; script posts. No cron — per-event.

**3. Monitoring / escalation:** Daily Pulse panel (when surfaced) shows shipped-but-not-closed-out fixes. Warn if >0 fixes older than 24h without closeout. Breach if >3 unclosed-out accumulate.

**4. Iteration trigger:** Revise when (a) ≥3 close-outs and tone drift observed → ship V1 lint hook; (b) gh-author fallback fails for ≥1 user with gh auth → debug; (c) inbox file delivery fails → audit mapping flow; (d) coverage <80% sustained 7d → process review.

**5. DRI:** Asawa CEO (close-out posting decisions, comment text). Sutra-OS as implementer. Engineering for plugin-side hooks. Analytics for KPI rollup.

**6. Decommission:** Retire when (a) gh issues sunset / migrate forge → re-target; (b) PROTO-024 V2 encrypted channel ships with native close-loop UX → script redundant; (c) feedback volume justifies dedicated app → script + ledger retire together. Founder approval + 14d deprecation banner required.

### Failure modes + mitigations (this layer)

| Risk | Mitigation |
|---|---|
| Wrong-user delivery (privacy P0) — install_id↔issue mapping bug delivers to wrong user | Two-factor: inbox file carries `gh_author` field; plugin verifies match against `gh api user --jq .login` before displaying. Mismatch → log + skip + alert |
| Race / duplicate close-outs | Idempotency via ledger pre-check: `grep -q "issue:N" ledger` → skip retry |
| Replay (user sees same announcement 3 times) | Plugin moves displayed files to `inbox/read/`; never re-displays |
| gh API rate limit on fallback | 1h local cache of `closed:>last-seen` query; graceful skip on 429 |
| Privacy leak in gh comment | Tone-lint warns on `~/.sutra/`, file paths, version numbers, internal terms; founder review enforces V0 |
| Abuse — fake fix close-out | Ledger captures `posted_by=$USER` from env; founder review at draft time |
| Silent display hook failure | Hook stderr → `.enforcement/inbox-display.log`; failure visible in Daily Pulse |

## Pointers

- **Protocol spec**: `sutra/layer2-operating-system/PROTOCOLS.md` §PROTO-024
- **User-facing privacy**: `sutra/marketplace/plugin/PRIVACY.md`
- **Sister charters**: `PRIVACY.md` (data collection rules), `SECURITY.md` (channel hardening), `OPERATIONALIZATION.md` (the 6-section ops template this charter follows; engine reclassification pending — Roadmap §6 #14)
- **Codex review**: `.enforcement/codex-reviews/2026-04-25-proto-024-feedback-fanin-and-reset-hook-fix.md` (V1); Close-Loop V0 codex review deferred — gstack /codex consult template hung on stdin 2026-04-28; retry post-implementation
- **Memory**: `feedback_never_bypass_governance.md` (meta-rule), `project_feedback_canonical_channel.md` (D36 channel), `feedback_marketplace_sync_on_demand.md` (sync trigger), `feedback_close_loop_tone_template.md` (close-out tone)
