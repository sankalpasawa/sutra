/**
 * pattern-detector — finds repeated founder utterances that no registered
 * TriggerSpec matches, so the engine can propose a new Workflow + TriggerSpec.
 *
 * SPEC v1.2 §4.3. v1 rule (D45): NO LLM. Frequency + sequence detection over
 * the H-Sutra log JSONL only. Routing is simulated against the boot-time
 * trigger set — no dependency on Router state (which is in-memory only).
 *
 * Determinism: same input log + same trigger set + same proposer_version
 * yields the same DetectedPattern[].
 */
import type { TriggerSpec } from '../types/trigger-spec.js';
import type { UserKitOptions } from '../persistence/user-kit.js';
export interface PatternDetectorOptions {
    /** Absolute path to the H-Sutra log JSONL file. */
    readonly hsutra_log_path: string;
    /** Minimum repeats to surface a pattern. Default 4 per codex prior verdict. */
    readonly k_threshold?: number;
    /** Window in ms before now() to consider events. Default 7d. */
    readonly window_ms?: number;
    /** Cap on samples kept per pattern. Default 4. */
    readonly max_samples?: number;
    /** UserKit opts forwarded to loadProposal for dedup. */
    readonly user_kit_opts?: UserKitOptions;
    /** Override now() for deterministic tests. */
    readonly now_ms?: number;
}
export interface DetectedPattern {
    /** P-<sha8> stable across runs (derived from normalized_phrase only). */
    readonly pattern_id: string;
    readonly normalized_phrase: string;
    readonly evidence_count: number;
    readonly utterance_samples: ReadonlyArray<string>;
    readonly first_seen_ms: number;
    readonly last_seen_ms: number;
}
/**
 * Normalize an utterance for grouping. Lowercase, strip punctuation, drop
 * stopwords, sort tokens for set-equality (so "track design partners" and
 * "design partners track" group together). Returns empty string if nothing
 * informative remains.
 */
export declare function normalizeUtterance(text: string): string;
export declare function patternIdFor(normalized_phrase: string): string;
/**
 * Detect frequency patterns in the H-Sutra log that no registered trigger
 * matches AND no prior proposal already covers.
 */
export declare function detectPatterns(triggers: ReadonlyArray<TriggerSpec>, opts: PatternDetectorOptions): DetectedPattern[];
//# sourceMappingURL=pattern-detector.d.ts.map