# ADR-015 — Native Ships Its Own H-Sutra Producer (Vendored)

## Status
Accepted 2026-05-07 (formalized as part of Native formalization v1.0). Charter contract: see `sutra/os/engines/NATIVE-ENGINE.md` §5.3 (H-Sutra event bus); D-direction: D49 in `holding/FOUNDER-DIRECTIONS.md`.

## Context
Native consumes H-Sutra events (9-cell × 3-tag classification per founder turn — schema in `sutra/os/charters/HUMAN-SUTRA-LAYER.md`). Two install topologies were live:

- **Depend on `core@sutra` at runtime** — Native imports H-Sutra producer from the core plugin.
- **Vendor (ship Native's own copy)** — Native bundles `per-turn-h-sutra.sh` + `classify.sh` inside the native plugin.

The first option works for Asawa (where both plugins are installed) but blocks standalone fleet adoption: a T4 user who wants Native without the full core plugin gets a runtime missing-dependency error. Native is meant to be installable on its own.

Founder direction D49 (`holding/FOUNDER-DIRECTIONS.md`) made this explicit: Native must ship a vendored H-Sutra producer; no runtime `core@sutra` dependency.

Sources: `FOUNDER-DIRECTIONS.md` §D49; `holding/research/2026-05-06-native-understanding-guide.md` §TL;DR; `holding/RESUME-NATIVE-CHARTER.md`.

### Alternatives considered
- Require `core@sutra` as install dependency — rejected: blocks standalone fleet adoption (D49).
- Symlink to core's copy — rejected: non-portable; breaks on fresh client install where core isn't present.
- Post-write dedupe guard (both plugins write; Native dedupes) — rejected by codex P1 in pre-dispatch fold; complexity without proportional benefit.

## Decision
Native engine MUST vendor its own H-Sutra producer (`per-turn-h-sutra.sh` + `classify.sh`) inside the `native@sutra` plugin; MUST NOT depend on `core@sutra` at runtime.

- Native's vendored producer writes to its own log path; consumers (`HSutraConnector`) tail that file.
- When `core@sutra` is also installed (e.g. on Asawa), each plugin writes to its own log path — Asawa's CLAUDE.md routes which is canonical for that session.
- Schema (9-cell + 3-tag) is shared via `sutra/os/charters/HUMAN-SUTRA-LAYER.md`; both plugins MUST emit identical row shape.
- Append fail-CLOSED at row level; missing rows never block downstream Edit/Write/Bash.

## Consequences

| Kind | Effect |
|---|---|
| + | Native installs standalone — no runtime `core@sutra` dependency required |
| + | T4 fleet adoption unblocked: single-plugin install path works |
| + | Schema parity enforced via shared charter — drift is detectable |
| − | Two physical copies of producer code (Native + core) — drift risk if charter updates |
| − | Asawa runs both producers — needs explicit log-path routing per session |
| 0 | OS-7 deferred: Native owns its own UserPromptSubmit intake (currently still arrives via core hook on Asawa) |
