<!-- MIRROR (read-only distribution copy). Canonical: sutra/os/decisions/ADR-010-organic-emergence-propose-approve.md. -->
# ADR-010 — Organic Emergence: Propose-Approve at k≥4

## Status
Accepted 2026-05-07 (formalized as part of Native formalization v1.0). Charter contract: see `sutra/os/engines/NATIVE-ENGINE.md` §3.2 (events 12-14), §3.4 (approval utterances); related: ADR-009.

## Context
Native v1.2 added a pattern detector that watches the H-Sutra event log for repeated founder utterances matching no registered Workflow. When a pattern repeats, the system has three plausible responses:

1. **Auto-register** — detect the pattern, mint a Workflow, register it. Fastest, but unsafe: no founder oversight, no naming, no PNC review.
2. **Skip** — log the repetition, do nothing. Safest, but loses the entire emergent-workflow value prop.
3. **Propose-approve** — at threshold k, emit a `pattern_proposed` event with a draft Workflow JSON; founder approves or rejects via utterance.

Founder direction D45 (`holding/FOUNDER-DIRECTIONS.md`) established that organic emergence is a v1.2 goal but must remain founder-gated. `holding/plans/native-v1.2/organic-emergence-v1-SPEC.md` §1 Goals + gap-audit `OE-1` set the threshold (k≥4) based on signal-to-noise observation: k=2 is too noisy (one-offs), k=3 still ambiguous, k=4 is the smallest k where a pattern is consistently a real workflow.

### Alternatives considered
- Auto-register on detection — rejected because no oversight; can mint workflows from typos / experimental phrasings.
- Higher threshold k>4 — rejected because k=5+ delays the first proposal too long; founder loses the "Native noticed!" moment.
- LLM-drafted full Workflow on first match — rejected for v1.2 (codex P1.3 deferred to v1.x as a separate "smarter proposer" question).

## Decision
Native engine MUST require explicit founder approval via `approve P-<id>` utterance to register any pattern-detected Workflow; the detector MUST propose only at k≥4 utterance matches.

- Pattern detector reads H-Sutra JSONL (ADR-013) and tracks per-pattern hit count + sample utterances.
- At k≥4 with no registered workflow matching the pattern → emit `pattern_proposed` (event 12) with draft JSON + sample utterances.
- Founder utterance `approve P-<id>` → `proposal_approved` (event 13) → register Workflow.
- Founder utterance `reject P-<id> <reason>` (or `--feature-flag SUTRA_NATIVE_PROPOSER` off) → `proposal_rejected` (event 14).

## Consequences

| Kind | Effect |
|---|---|
| + | Founder retains control of registry; no surprise workflows |
| + | k=4 threshold tuned to live signal — fewer false-positive proposals |
| + | Sample utterances ship with the proposal — founder can audit the matched evidence |
| − | First useful proposal delayed until k=4 is reached (cold start cost) |
| − | Manual approval loop adds friction for high-frequency patterns |
| 0 | Smarter LLM-drafted Workflows on first match deferred to v1.x backlog |
