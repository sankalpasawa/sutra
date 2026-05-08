/**
 * UserProfile + Scenario — drives test simulation from a deterministic persona
 * rather than a hardcoded utterance string.
 *
 * Per founder direction 2026-05-08: "user utterance is profile driven, fix it
 * on creating a website for pets". The profile defines the user's persona +
 * an utterance template; the scenario binds a profile to a goal_seed
 * (substitution map). generateUtterance(profile, scenario) renders the final
 * utterance — a thin, deterministic layer over the profile.
 *
 * v1 keeps it minimal: one template per profile, simple {{var}} substitution.
 * v1.1+ may add multi-template variants, response/follow-up scripts.
 *
 * SPEC: docs/superpowers/specs/2026-05-07-verifier-engine-v1-design.md §7
 */

export interface UserProfile {
  readonly id: string
  readonly voice: string
  readonly communication_style: string
  readonly utterance_template: string  // contains {{var}} placeholders
}

export interface Scenario {
  readonly id: string
  readonly profile_id: string
  readonly goal_seed: Readonly<Record<string, string>>  // substitution map
  readonly expected_failure_axes?: readonly string[]    // hint for failure-surface tests
}
