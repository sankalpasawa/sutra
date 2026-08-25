<!-- MIRROR (read-only distribution copy). Canonical: sutra/os/decisions/ADR-004-registry-and-effector-split.md. -->
# ADR-004 — Registry-and-Effector Split (Native vs Claude)

## Status
Accepted 2026-05-07 (formalized as part of Native formalization v1.0). Charter contract: see `sutra/os/engines/NATIVE-ENGINE.md` §1, §5.1, §5.2.

## Context
Native must turn Workflow JSON into executed work, but the daemon process that owns the Workflow registry is detached from the founder's interactive session. Two architectures were live during v1.0/v1.1:

1. Native daemon dispatches all file/git/network mutations itself (requires per-Workflow sandbox declaration; no live capability to authenticate keychain reads from a detached subprocess in v1.0).
2. Native owns registry + audit; the founder's interactive Claude session is the effector that performs the mutations the Workflow declares.

Live evidence: `holding/research/2026-05-04-native-v1.2.1-visual-proof.md` §Host-dependency finding showed `host: claude --bare` skips keychain reads (recursion-safe but unauthenticated) and `host: codex` defaults to a read-only sandbox. Per-Workflow sandbox config is v1.3 scope (see `holding/plans/native-v1.x/RESUME-V1.X.md` §0).

### Alternatives considered
- Make Native dispatch mutations via daemon — rejected because v1.0 has no per-Workflow sandbox primitive and the daemon cannot read founder credentials safely.
- Direct Claude API call (no subprocess host) — rejected because subprocess isolation is the only way to keep host-LLM execution recursion-safe + replayable.

## Decision
Native engine MUST be the registry + audit layer; the founder's interactive host-LLM session MUST be the effector that performs declared mutations.

- Native owns: Workflow JSON, Trigger predicates, Execution rows, EngineEvent audit, DecisionProvenance, Tenant isolation.
- Claude (founder session) owns: filesystem writes, git operations, network calls — driven by Workflow steps but executed in the authenticated session.
- The split is recorded on every Execution via `agent_identity` chain (see `sutra/os/engines/NATIVE-ENGINE.md` §2.6, ADR-015).
- v1.3 may add per-Workflow sandbox config to permit daemon-side mutations (`sutra/os/engines/NATIVE-ENGINE.md` §8 OS-1, OS-2); the split itself remains the default.

## Consequences

| Kind | Effect |
|---|---|
| + | Daemon stays unauthenticated and recursion-safe; no credential exfil surface |
| + | Founder retains ASK-gate visibility on every mutation that goes through the session |
| + | Audit trail (Execution + EngineEvent) records intent BEFORE Claude effector runs — replayable |
| − | Two-process coordination: Native fires the workflow row, Claude session must still execute the steps |
| − | Autonomous "fire-and-forget" workflows blocked at v1.0 (deferred to v1.3 per OS-1/OS-2) |
| 0 | NL routing table in `CLAUDE.md` documents the split per Workflow type |
