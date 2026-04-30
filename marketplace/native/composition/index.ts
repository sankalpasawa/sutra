/**
 * Default Composition v1.0 — barrel.
 *
 * 3 seed Workflows that ship out-of-box with Native v1.0. Each exercises a
 * different engine subset so a fresh operator can pick a starting point that
 * matches their use case:
 *
 *   1. governance-turn-emit — minimal turn emit (M5 step-graph + M8 OTel surface)
 *   2. charter-obligation-eval — policy-gated action (M7 OPA + policy_dispatcher)
 *   3. skill-chain-stub — Skill chaining (M6 SkillEngine resolve path)
 *
 * See `composition/README.md` for operator usage guide.
 *
 * Spec source:
 *   - holding/plans/native-v1.0/M12-release-canary.md (D-NS-52)
 *   - holding/research/2026-04-29-native-v1.0-final-architecture.md line 229
 */

export {
  buildGovernanceTurnEmitWorkflow,
  type GovernanceTurnEmitOptions,
} from './governance-turn-emit.js'

export {
  buildCharterObligationEvalWorkflow,
  type CharterObligationEvalOptions,
} from './charter-obligation-eval.js'

export {
  buildSkillChainStubWorkflow,
  type SkillChainStubOptions,
} from './skill-chain-stub.js'
