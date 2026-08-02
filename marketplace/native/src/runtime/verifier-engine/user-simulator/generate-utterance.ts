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

import type { UserProfile, Scenario } from '../../../types/user-profile.js'

const PLACEHOLDER = /\{\{(\w+)\}\}/g

export function generateUtterance(profile: UserProfile, scenario: Scenario): string {
  if (profile.id !== scenario.profile_id) {
    throw new Error(
      `profile_id mismatch: profile=${profile.id} scenario=${scenario.profile_id}`,
    )
  }
  const missing = missingSubstitutions(profile, scenario)
  if (missing.length > 0) {
    throw new Error(`missing substitution(s): ${missing.join(', ')}`)
  }
  return profile.utterance_template.replace(PLACEHOLDER, (_, key: string) =>
    scenario.goal_seed[key] ?? '',
  )
}

export function missingSubstitutions(profile: UserProfile, scenario: Scenario): string[] {
  const required = new Set<string>()
  for (const m of profile.utterance_template.matchAll(PLACEHOLDER)) {
    required.add(m[1])
  }
  return [...required].filter(k => !(k in scenario.goal_seed))
}
