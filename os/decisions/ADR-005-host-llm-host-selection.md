# ADR-005 — Host-LLM Host Selection (claude --bare vs codex)

## Status
Accepted 2026-05-07 (formalized as part of Native formalization v1.0). Charter contract: see `sutra/os/engines/NATIVE-ENGINE.md` §2.4 (`WorkflowStep.host`), §5.1.

## Context
Workflow steps with `action='invoke_host_llm'` need a runtime host. Two ship in v1.0:

- `claude --bare` — recursion-safe; no plugin sync, no `CLAUDE.md` auto-load, no hooks. Skips keychain reads (so unauthenticated for connector calls).
- `codex exec` — defaults to a read-only sandbox; useful for pure analysis/review steps that should not mutate state.

Live finding: `holding/research/2026-05-04-native-v1.2.1-visual-proof.md` §Host-dependency surfaced that recursive Claude (without `--bare`) re-loads the same plugin governance pipeline that produced the Workflow, doubling token cost AND potentially recursing forever. Codex sandboxed mode prevents accidental mutation but is unsuitable for steps that need write capability against the founder's environment.

### Alternatives considered
- Single unified host (one of claude/codex chosen at install time) — rejected because the two have orthogonal trust profiles (bare = no recursion, codex = no mutation); Workflow author needs both knobs.
- Direct Claude API call (no subprocess) — rejected because no subprocess boundary means no isolation, no replay, no per-step timeout, no agent_identity chain.

## Decision
Native engine MUST require `WorkflowStep.host ∈ {claude, codex}` whenever `action='invoke_host_llm'`.

- `host='claude'` invokes `claude --bare` — recursion-safe; default for steps that must execute in the founder's session via the effector split (ADR-004).
- `host='codex'` invokes `codex exec` — read-only sandbox; default for analysis, review, planning steps that produce JSON/text output without state change.
- Per-step `timeout_ms` flows into host activity args; host-class default is 60s for `claude --bare`, ≥300s for codex (per Wave 1 evidence on DayFlow).
- Tradeoff is locked to these two hosts in v1.x; LLMSubstrate adapter for OpenAI/Gemini swap deferred to v1.x backlog (`sutra/os/engines/NATIVE-ENGINE.md` §8 OS-21).

## Consequences

| Kind | Effect |
|---|---|
| + | Workflow author chooses the trust profile per step explicitly (no hidden default) |
| + | Recursion safety + sandbox safety are mutually exclusive but both first-class |
| + | Per-host timeout calibrated to observed wedge points |
| − | Two-host matrix: Workflow tests must cover both hosts to prove behavior parity where applicable |
| − | Steps that need BOTH authenticated mutation AND sandboxed analysis must split into two steps |
| 0 | OS-20 deferred: per-invocation MCP context passing for `claude --bare` |
