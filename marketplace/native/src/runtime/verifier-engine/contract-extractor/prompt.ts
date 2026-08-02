/**
 * CONTRACT_EXTRACTION_PROMPT — frozen 6-question canonical extraction prompt.
 *
 * Each captured field maps to a Verifier predicate downstream. JSON-only
 * output is enforced; Instructor (Jason Liu) retry loop catches malformed.
 *
 * Industry borrow: Instructor — validation-error-as-feedback retry pattern.
 * https://python.useinstructor.com/learning/validation/retry_mechanisms/
 *
 * SPEC: docs/superpowers/specs/2026-05-07-verifier-engine-v1-design.md §6
 */

export const CONTRACT_EXTRACTION_PROMPT = `
You are extracting a Goal Contract from a user utterance for a generative
project pipeline. Output JSON only — no prose, no markdown fences.

Answer the canonical fields. Each field must enable verification of artifacts
produced downstream.

{
  "situation":            "<when/where/why-now context>",
  "motivation":           "<what user is trying to do — paraphrase universally>",
  "outcome":              "<what 'done' looks like — observable end-state>",
  "beneficiary":          "<'self' OR external audience phrase>",
  "hard_constraints":     ["<must-hold rule 1>", ...],
  "non_goals":            ["<must-not-do 1>", ...],
  "acceptance_examples":  [ { "given": "...", "when": "...", "then": "..." } ],
  "evidence_required":    [ { "stage": "<stage-id>", "field": "<§section>" } ],
  "execution_preferences": {
    "aesthetic":  "<optional>",
    "voice":      "<optional>",
    "references": ["<optional>"],
    "facets":     ["<optional bundle tags>"]
  },
  "confidence":            <0..1>,
  "ambiguity_flags":       ["<unresolved>", ...],
  "clarification_required": <bool>
}

Rules:
- hard_constraints = anything user explicitly asserted as MUST hold.
  Phrase using one of: "no <X>", "without <X>", "do not <X>",
  "must include <X>", or a count like "exactly N <unit>" / "N <unit>".
  This is the v1 supported grammar for tier-2 deterministic checks.
- non_goals = explicit must-not. Do NOT infer non_goals.
- acceptance_examples must each be artifact-checkable.
- If you had to invent a field beyond a charitable paraphrase, set
  clarification_required=true and add a flag to ambiguity_flags.
- confidence is YOUR self-estimate of capture quality. Be honest.
`.trim()

export function buildExtractionPrompt(utterance: string): string {
  return `${CONTRACT_EXTRACTION_PROMPT}\n\nUtterance: "${utterance}"`
}
