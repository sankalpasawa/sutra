import { type SandboxViolationEvent } from './macos-sandbox-utils.js';
import { type IgnoreViolationsConfig } from './sandbox-config.js';
/**
 * In-memory tail for sandbox violations
 */
export declare class SandboxViolationStore {
    private violations;
    private totalCount;
    private readonly maxSize;
    private listeners;
    addViolation(violation: SandboxViolationEvent): void;
    getViolations(limit?: number): SandboxViolationEvent[];
    getCount(): number;
    getTotalCount(): number;
    getViolationsForCommand(command: string): SandboxViolationEvent[];
    clear(): void;
    subscribe(listener: (violations: SandboxViolationEvent[]) => void): () => void;
    private notifyListeners;
}
/**
 * Whether a violation should be suppressed by the user's `ignoreViolations`
 * config: `'*'` patterns apply to every command, other keys are matched as
 * substrings of the (decoded) command. `line` is the violation text the
 * patterns are substring-matched against. Shared by every violation
 * producer (macOS log monitor, Linux seccomp observer, proxy denies) so a
 * pattern suppresses the same event regardless of which one saw it.
 */
export declare function shouldIgnoreViolation(line: string, command: string | undefined, ignoreViolations: IgnoreViolationsConfig | undefined): boolean;
/**
 * What a violation reports for an attribution key no invocation registered.
 * Such a key arrived over a carrier the sandboxed process can write, so it
 * is bytes rather than text: sanitize it and cut it to the length a key this
 * process minted can have — the carriers are bounded far more loosely than
 * that (an HTTP proxy header budget is kilobytes).
 */
export declare function sanitizeUnregisteredCommandKey(decodedKey: string): string;
/**
 * How much of a denial reason supplied by the ask callback a violation line
 * carries, in UTF-16 code units: a few sentences fit, a document does not.
 */
export declare const MAX_DENIAL_REASON_LENGTH = 500;
/**
 * A denial reason the ask callback supplied, as a violation line may carry
 * it: sanitized first, so the cut counts what is displayed, then cut so that
 * one answer cannot flood the text a model reads. The end is trimmed after
 * the cut: the reason sits inside parentheses, where the store's own trim of
 * the line's ends does not reach.
 */
export declare function sanitizeDenialReason(reason: string): string;
//# sourceMappingURL=sandbox-violation-store.d.ts.map