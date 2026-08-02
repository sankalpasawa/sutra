---
part-id: P2
bucket: pillars
template: L1-pov
parity-source: §10.2 row P2 + §10.3 row P2
parity-source-sha256: 08314122194777b0ede00159980c08f34ca438203a5d4a840bf78af6f515873e
status: DRAFT v1
authored: 2026-05-09
---

# P2: Pre/post LLM validation

## Pillar statement

> Every LLM call has a pre-declared expected output and a post-call check — Native treats LLM invocations the way engineering treats untrusted functions: with a contract on each side. Per §10.2 row P2: "every LLM call has pre-declared expected output + post-call check (testing-framework analog)." There are no silent LLM calls inside Native; every stochastic step is wrapped by a deterministic envelope.

## What this rules in

- BLUEPRINT-style declaration of expected output before any LLM call (analogous to test-first discipline).
- Post-call validation step that asserts the LLM's output matches the declared contract.
- Testing-framework analog explicitly cited in §10.2 — LLM calls treated like functions under test.
- Cross-ref to P11 (`./P11-constrained-problem-construction.md`) — constrained-problem construction is the prompt-side analog of P2's check-side.

## What this rules out

- Silent LLM calls with no declared expectation.
- Trust-by-default of LLM outputs without a check step.
- Implicit "the user will eyeball it" validation — must be a system-level post-call check, not operator-eyeball.

## Falsification test

**If an LLM call is silent (no pre/post check) → P2 broken; trust erodes.** (Exact text from §10.3 row P2.)

## Doctrine inheritance (from L0)

Per canon §10.4 doctrine-tension resolution table: P2 has NO direct conflict with the 5 Doctrine tests (Customer Focus First · Dynamic · Flexible · Scalable · Simple · Nuanced) recorded in §10.4. The table only enumerates tensions for P3 (vs Simple), P11 (vs Customer Focus), and P13 (vs Scalable). For P2, no tension is logged; inheritance is via L0 generally (Customer Focus First applies as parent of all pillars).

(If a tension exists in practice but is not in §10.4, this is a gap to surface via future ADR rather than invent inline.)

## References

- NATIVE-ENGINE.md §10.2 row P2 — pillar statement.
- NATIVE-ENGINE.md §10.3 row P2 — falsification test.
- NATIVE-ENGINE.md §10.4 — doctrine inheritance table (P2 not listed; no documented tension).
- `./P11-constrained-problem-construction.md` — prompt-side analog (pre-call contract).
- `./P12-deterministic-surface-stochastic-core.md` — P2 is one mechanism by which the deterministic surface envelops the stochastic core.
