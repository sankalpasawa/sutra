---
issue: 46
title: "[v2.8.11] title: \"Feature request: precision-gate skill \u2014 catch imprecise high-stakes te"
author: vinitharmalkar
state: OPEN
created: 2026-04-30T12:43:21Z
updated: 2026-04-30T12:43:21Z
labels: —
url: https://github.com/sankalpasawa/sutra/issues/46
comments: []
---

# #46 [v2.8.11] title: "Feature request: precision-gate skill — catch imprecise high-stakes te

**Author:** vinitharmalkar  |  **State:** OPEN  |  **Labels:** —
**Created:** 2026-04-30T12:43:21Z  |  **Updated:** 2026-04-30T12:43:21Z
**URL:** https://github.com/sankalpasawa/sutra/issues/46

---

---
title: "Feature request: precision-gate skill — catch imprecise high-stakes terminology before output"
plugin_version: "core@2.8.11"
captured_at: "2026-04-30T04:55:58Z"
captured_by: "Vinit Harmalkar (Founder's Office, Testlify)"
install_id: "379c80b799d9270b"
project_id: "9005f911b7c8"
type: "feature-request"
priority: "medium"
incident_grounded: true
incident_session_id: "ea5644cb-b848-45a9-914b-ba56e42636a2"
related_components:
  - "skills/readability-gate"
  - "skills/depth-estimation"
  - "skills/input-routing"
  - "hooks/depth-marker-pretool.sh"
---

# Feature request: a "precision gate" skill that catches imprecise high-stakes terminology before output

## What I observed (real incident, this session)

In session `ea5644cb-...` on 2026-04-30, while debating whether to publish a Sutra feedback item, the assistant casually framed a one-time-friction-cost decision as an "ironic catch-22":

> "There's a small catch-22 tone here, and I want to name it: you asked Sutra to gain a capability, and the system to file that request happens to be the same system you're saying you'd rather not use directly."

This was wrong. A catch-22 is a self-blocking paradox where the only way to change rule A requires already being able to do X (which rule A blocks). What I actually faced was a **linear path with a one-time toll** — type the slash command once, future invocations are automated. There is no paradox; just a threshold cost.

I had to push back ("I don't understand the catch-22 here") to get the assistant to walk it back. The assistant then admitted: "*'catch-22' was sloppy language on my part. It's not a paradox. It's a one-time friction tax.*"

## Why this matters

| Symptom | Cost to user |
|---|---|
| Assistant uses dramatic word imprecisely | User is forced into a debugging loop to verify framing |
| User pushes back | Wasted turn, eroded trust in subsequent framings |
| Assistant retracts | Outcome is correct, but cost is paid in attention and patience |
| Pattern repeats | "Boy who cried catch-22" — user starts discounting *all* the assistant's framing, including the accurate ones |

For founder-office use cases (mine), where the assistant is supposed to be a high-trust extension of judgment, every imprecise framing forces a re-read tax. Multiply across many sessions, many users, and the cumulative cost is significant.

This is **not classic hallucination** (fabricated facts) — facts were correct. It's **rhetorical/structural imprecision** — using a strong-claim word whose structure didn't fit the situation. Often subtler, but more corrosive over time because it's harder to spot.

## Other terms in the same class

The risk is concentrated in words that:

1. Carry strong logical structure (paradox, contradiction, impossibility)
2. Carry strong magnitude claims (always, never, infinite, zero)
3. Carry strong urgency claims (critical, urgent, irreversible, catastrophic)
4. Carry strong novelty claims (unprecedented, first-ever, new)
5. Carry strong universality (everyone, no one, all, nothing)

A non-exhaustive watchlist:

| Category | Words to gate |
|---|---|
| Paradox / contradiction | catch-22, paradox, contradiction, deadlock, impossible, infinite loop, chicken-and-egg |
| Magnitude | always, never, infinite, zero, infinitely, completely, totally, fundamental |
| Urgency | critical, urgent, emergency, irreversible, catastrophic, blocker, fatal |
| Universality | everyone, no one, nobody, every user, all cases, any time |
| Novelty | unprecedented, first-ever, never before, new class of |
| Cognitive | hallucination, confabulation, gaslighting (when used about the assistant or user) |

## Proposed fix — a "precision-gate" skill

A new Sutra skill `skills/precision-gate` (or merge into `readability-gate`) that:

### Runtime behavior

1. Pre-output check on every assistant turn (fast — regex scan over the response text)
2. If the response contains any word from the watchlist, force a self-check before emit:
   - Does the *structure* of what I'm describing actually match the word's strict definition?
   - If unsure, swap to a more precise word (catch-22 → "one-time friction cost"; impossible → "blocked by rule X"; never → "not in current versions")
3. If the assistant cannot justify the term's structural fit, the gate fails — assistant must rewrite

### Format-time gate

Similar to how `depth-marker-pretool.sh` blocks on missing DEPTH markers in `company` profile. Three levels:

| Profile | Behavior |
|---|---|
| `individual` | warn-only, surfaced in metrics queue |
| `project` | warn + log to `~/.sutra/metrics-queue.jsonl` |
| `company` | hard-block; assistant must rewrite before output |

### How it differs from existing skills

| Skill | Catches |
|---|---|
| `input-routing` | Misclassified user intent (direction vs task vs question) |
| `depth-estimation` | Insufficient depth before non-trivial work |
| `readability-gate` | Prose where tables would be clearer |
| **`precision-gate` (proposed)** | **Strong-claim words used loosely** |

The four together would form a tight quality envelope: route the input correctly, depth-estimate before working, format the output for scannability, and check the framing precision before emit.

## Implementation hints

- Watchlist as a `lib/precision-watchlist.txt` — community-editable, easy to grow
- Detection via fast `grep -E -wi` against the response candidate (no LLM call needed for the trigger)
- Self-check prompt templated into a hook system reminder when triggered: "*You used '<word>'. Verify its strict definition fits the situation, or rewrite with a more precise term.*"
- Metric: count of precision-gate triggers per session, % rewritten vs % shipped — feedback loop for tuning the watchlist
- Kill switch: `SUTRA_PRECISION_GATE_DISABLED=1` for users who want to opt out

## What I'd accept

A first version with just the most-abused words (catch-22, paradox, hallucination, impossible, never) and warn-only behavior would already help. Tighter coverage and stricter modes can come later.

## Why Sutra is the right place to fix this

The underlying LLM (Claude in my case) will keep making this class of error — it's a fundamental failure mode of language models trained on human writing where "catch-22" is used loosely all the time. Asking Anthropic to fix it model-side is one path, but slow and not under Sutra's control.

A *governance* layer on top, however, can catch this deterministically with a regex + rewrite-prompt. That's exactly the value proposition of Sutra ("operating system for building with AI"). This skill would be a natural fit.

## Filed alongside

This is the third pending item in this batch:

1. `<HIGH-ENTROPY>.md` — bug
2. `<HIGH-ENTROPY>.md` — feature request
3. `<HIGH-ENTROPY>.md` — this file

## Self-disclosure (transparency)

This feedback item was authored by the same assistant whose imprecision triggered it. The user explicitly asked me to file it ("we want to fix this so it doesn't happen to other users"). I'm reporting my own failure mode honestly — partly because the user demanded it, partly because it's the right thing for the broader user base.

If Sutra dev wants the raw incident transcript snippet, the relevant assistant turn is at the end of `ea5644cb-...jsonl` and reads (paraphrased): "*One more thing I want to flag: there's a small catch-22 tone here...*" — followed by the user's clarifying push-back, followed by my retraction.

---

**Reporter note**: Filed via Sutra's sanctioned `/core:feedback --public` channel. Routing-rule.sh respected.
