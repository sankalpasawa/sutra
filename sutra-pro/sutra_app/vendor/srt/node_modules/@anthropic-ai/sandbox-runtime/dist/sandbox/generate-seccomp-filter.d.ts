/**
 * Get paths to check for globally installed @anthropic-ai/sandbox-runtime package.
 * This is used as a fallback when the binaries aren't bundled (e.g., native builds).
 *
 * Blocks the event loop on `npm root -g` (~100 ms) the first time it is
 * called in a process unless {@link getGlobalNpmPathsAsync} has already
 * filled the cache; initialize() goes through the async variant.
 */
export declare function getGlobalNpmPaths(): string[];
/**
 * Async variant of {@link getGlobalNpmPaths}: runs `npm root -g` without
 * blocking the event loop and shares the same per-process cache, so a
 * later sync call returns immediately. Never rejects — a failed or
 * timed-out npm yields just the static fallback locations, as the sync
 * variant does.
 */
export declare function getGlobalNpmPathsAsync(): Promise<string[]>;
/**
 * Get the path to the apply-seccomp binary from the vendor directory
 * Returns the path if it exists, null otherwise
 *
 * Pre-built apply-seccomp binaries are organized by architecture:
 * - vendor/seccomp/{x64,arm64}/apply-seccomp
 *
 * Tries multiple paths for resilience:
 * 0. Explicit path provided via parameter (checked first if provided)
 * 1. vendor/seccomp/{arch}/apply-seccomp (bundled - when bundled into consuming packages)
 * 2. ../../vendor/seccomp/{arch}/apply-seccomp (package root - standard npm installs)
 * 3. ../vendor/seccomp/{arch}/apply-seccomp (dist/vendor - for bundlers)
 * 4. Global npm install (if seccompBinaryPath not provided) - for native builds
 *
 * @param seccompBinaryPath - Optional explicit path to the apply-seccomp binary. If provided
 *   and exists, it will be used. If not provided, falls back to searching local paths and
 *   then global npm install (for native builds where vendor directory isn't bundled).
 */
export declare function getApplySeccompBinaryPath(seccompBinaryPath?: string): string | null;
/**
 * Async variant of {@link getApplySeccompBinaryPath}: same lookup order and
 * shared cache, but the global-npm fallback resolves `npm root -g` without
 * blocking the event loop. Resolving once through here (as
 * checkDependenciesAsync does) makes later sync calls cache hits.
 */
export declare function getApplySeccompBinaryPathAsync(seccompBinaryPath?: string): Promise<string | null>;
//# sourceMappingURL=generate-seccomp-filter.d.ts.map