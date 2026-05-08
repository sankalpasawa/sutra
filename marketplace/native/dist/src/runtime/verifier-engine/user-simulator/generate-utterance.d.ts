/**
 * generateUtterance — render a deterministic utterance from a profile +
 * scenario.goal_seed. Pure function, no I/O. Test fixtures load profile +
 * scenario from JSON; this function renders.
 *
 * Per founder direction 2026-05-08: simple {{var}} substitution; no random
 * variation in v1. Same profile + scenario always produces same utterance.
 *
 * SPEC: docs/superpowers/specs/2026-05-07-verifier-engine-v1-design.md §7
 */
import type { UserProfile, Scenario } from '../../../types/user-profile.js';
export declare function generateUtterance(profile: UserProfile, scenario: Scenario): string;
export declare function missingSubstitutions(profile: UserProfile, scenario: Scenario): string[];
//# sourceMappingURL=generate-utterance.d.ts.map