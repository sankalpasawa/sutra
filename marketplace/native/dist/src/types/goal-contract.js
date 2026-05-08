/**
 * GoalContract — central primitive for Verifier Engine v1.
 *
 * Per-utterance structured capture; no fixed taxonomy. Same shape for every
 * utterance; content varies. Captures both the universal job-to-be-done
 * (Job Story triple) and the user-declared constraints around it.
 *
 * Industry borrow: Job Story triple (situation/motivation/outcome) — Klement /
 * Intercom; replaces flat "purpose" field. The "situation" slot differentiates
 * "for my pets" from "for working professionals".
 *
 * Industry borrow: Hard-Assert vs Soft-Suggest split — DSPy (Stanford);
 * hard_constraints halt the pipeline, execution_preferences only bias.
 *
 * Industry borrow: BDD Given/When/Then — Cucumber/Concordion;
 * acceptance_examples become executable predicates over artifacts.
 *
 * SPEC: docs/superpowers/specs/2026-05-07-verifier-engine-v1-design.md §3
 */
export {};
//# sourceMappingURL=goal-contract.js.map