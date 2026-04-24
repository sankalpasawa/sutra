# Charters — the 5 cross-cutting governance docs

Charters are cross-cutting rules that apply across every company Sutra governs. They sit above protocols (which are specific mechanisms) and above hooks (which are specific enforcements).

## The 5 charters

| Charter     | Owns                                                          | File                              |
|-------------|---------------------------------------------------------------|-----------------------------------|
| TOKENS      | Token budget, context weighting, Analytics-dept scorecards   | os/charters/TOKENS.md             |
| SPEED       | Time-per-task, phase taxonomy, operationalization            | os/charters/SPEED.md              |
| PRIVACY     | Data collection, retention, consent, sanitization            | os/charters/PRIVACY.md            |
| SECURITY    | Access, integrity, authentication (the NEW v1.0 charter)     | os/charters/SECURITY.md           |
| PEDAGOGY    | LEARN → BUILD → GROW human journey through the OS            | os/charters/PEDAGOGY.md           |

## What a charter contains

- Purpose
- Principles (ordered by enforcement priority)
- Tiered contract (T0-T4 defaults)
- Failure modes + primitives map
- Key Results (measurable)
- Relationship to other charters

## What a charter is NOT

- It is NOT a protocol. Protocols are specific mechanisms (PROTO-004 = secret gate).
- It is NOT a hook. Hooks execute at tool-call time.
- It is NOT a process. Processes describe HOW to do things.

Charter = THE RULES. Protocol = THE MECHANISM. Hook = THE ENFORCEMENT.

## How charters update

Monthly: KR dashboard check. Quarterly: re-read and reconcile. On any primitive change: re-review charter.
