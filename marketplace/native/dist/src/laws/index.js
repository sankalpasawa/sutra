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
export { l4Commitment, } from './l4-commitment.js';
export { l4TerminalCheck, t1Postconditions, t2OutputSchemas, t3StepTraces, t4InterfaceContracts, t5NoAbandonedChildren, t6ReflexiveAuth, } from './l4-terminal-check.js';
export { l5Meta, } from './l5-meta.js';
export { l6Reflexivity, } from './l6-reflexivity.js';
//# sourceMappingURL=index.js.map