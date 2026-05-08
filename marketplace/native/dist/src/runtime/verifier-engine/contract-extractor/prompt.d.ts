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
export declare const CONTRACT_EXTRACTION_PROMPT: string;
export declare function buildExtractionPrompt(utterance: string): string;
//# sourceMappingURL=prompt.d.ts.map