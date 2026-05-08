/**
 * AssertionReport — output of Verifier.verify(contract, run).
 *
 * Multi-axis structure (no aggregate score) per SPEC §5 + Agentic Rubrics
 * for SWE Agents (arXiv 2601.04171) — single aggregate scores hide which
 * dimension failed.
 *
 * Industry borrow: G-Eval (Microsoft) two-step rubric judge defines the
 * 4 axes used in tier-4. Tier-1..3 results carry the same axis tag for
 * cross-tier reporting.
 *
 * NativeRun co-located here so tier modules can import the type without
 * circular dependency on the orchestrator.
 *
 * SPEC: docs/superpowers/specs/2026-05-07-verifier-engine-v1-design.md §5
 */
export {};
//# sourceMappingURL=assertion-report.js.map