/**
 * Laws barrel — V2 §3 (L1-L5) + V2.1 §A6 (L6) + V2.4 §A12 (T1-T6).
 *
 * Pure predicate functions only; no runtime state, no I/O, no side effects.
 *
 * Source-of-truth: holding/research/2026-04-28-v2-architecture-spec.md
 */
export { l1Data } from './l1-data.js';
export { l2Boundary } from './l2-boundary.js';
export { l3Activation } from './l3-activation.js';
export type { ActivationSpec, ActivationEvent } from './l3-activation.js';
export { l4Commitment, type StepCoverage, type CoverageDecision, type CoverageMatrix, } from './l4-commitment.js';
export { l4TerminalCheck, t1Postconditions, t2OutputSchemas, t3StepTraces, t4InterfaceContracts, t5NoAbandonedChildren, t6ReflexiveAuth, type TerminalCheckContext, type TerminalCheckResult, type TerminalCheckId, type SchemaValidator, type InterfaceViolationsView, type ReflexiveAuth, } from './l4-terminal-check.js';
export { l5Meta, type PrimitiveKind, type TypedEdgeKind, type EdgeKind, } from './l5-meta.js';
export { l6Reflexivity, type ReflexiveCheckSatisfaction, type ReflexiveSatisfactionMap, } from './l6-reflexivity.js';
//# sourceMappingURL=index.d.ts.map