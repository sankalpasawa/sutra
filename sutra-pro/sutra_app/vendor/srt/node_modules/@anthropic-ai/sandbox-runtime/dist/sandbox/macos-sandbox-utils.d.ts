import type { FsReadRestrictionConfig, FsWriteRestrictionConfig } from './sandbox-schemas.js';
import type { IgnoreViolationsConfig } from './sandbox-config.js';
export interface MacOSSandboxParams {
    command: string;
    /**
     * Attribution key for this invocation: the string encoded into the
     * seatbelt log tag and the proxy username, and reported as the
     * violation's `command`. Defaults to `command`. Set it when the string
     * you execute differs from the one you will later look violations up by
     * (e.g. you wrap an assembled `source snapshot && eval '<cmd>'` but query
     * `getViolationsForCommand('<cmd>')`).
     */
    commandId?: string;
    needsNetworkRestriction: boolean;
    httpProxyPort?: number;
    socksProxyPort?: number;
    /** Per-session proxy auth token; embedded in proxy env URLs. */
    proxyAuthToken?: string;
    /** Path to the TLS-termination CA cert; injected as trust env vars. */
    caCertPath?: string;
    /** Path to the JVM proxy agent jar; injected via JAVA_TOOL_OPTIONS. */
    javaAgentJarPath?: string;
    allowUnixSockets?: string[];
    allowAllUnixSockets?: boolean;
    allowLocalBinding?: boolean;
    allowMachLookup?: string[];
    readConfig: FsReadRestrictionConfig | undefined;
    writeConfig: FsWriteRestrictionConfig | undefined;
    /** Environment variable names to unset for the sandboxed child (env -u) */
    unsetEnvVars?: string[];
    /** Environment variables to set for the sandboxed child (env NAME=VALUE) */
    setEnvVars?: Record<string, string>;
    /**
     * Whole-file credential masks. SBPL cannot redirect reads, so on macOS
     * these degrade to read-deny on realPath until the DYLD interposer
     * lands. fakePath is unused here.
     */
    maskedFileBinds?: Array<{
        realPath: string;
        fakePath: string;
    }>;
    /**
     * Masked files that degraded to a read-deny because their extract
     * pattern matched nothing under `onExtractNoMatch: 'deny'`. Denied as
     * literals, like {@link maskedFileBinds}: each is a file the library
     * opened, not a spelling to match.
     */
    degradeToDenyPaths?: readonly string[];
    ignoreViolations?: IgnoreViolationsConfig | undefined;
    allowPty?: boolean;
    allowGitConfig?: boolean;
    /**
     * Directories to emit as `safe.directory` via `GIT_CONFIG_*` env
     * vars — see {@link buildPosixGitSafeDirEnv}.
     */
    gitSafeDirectories?: readonly string[];
    enableWeakerNetworkIsolation?: boolean;
    allowAppleEvents?: boolean;
    binShell?: string;
}
/**
 * The mandatory write denies (no filesystem scanning). Each name appears
 * twice: once as the path in the cwd, and once as a pattern for the same
 * name anywhere beneath it, which macOS matches via a regex.
 *
 * Both are anchored at the cwd, and the cwd is a name on disk that may
 * contain `[`, `*` or `?`. So the first is a literal entry, and the second
 * carries the cwd as its anchor — only the `**\/<name>` tail is pattern.
 * Compiled as one glob, a cwd like `a[b/c]d` would turn into a character
 * class and every one of these denies would match nothing.
 */
export declare function macGetMandatoryDenyEntries(allowGitConfig?: boolean): PathEntry[];
export interface SandboxViolationEvent {
    line: string;
    command?: string;
    encodedCommand?: string;
    timestamp: Date;
}
export type SandboxViolationCallback = (violation: SandboxViolationEvent) => void;
/**
 * One denyOnly / allowWithinDeny / allowWrite entry after normalization.
 * Whether `path` is a pattern or a name on disk is decided once, by
 * whoever produced the spelling — a caller's pattern or a path the library
 * resolved — and is never re-derived from the characters in `path`: a
 * resolved name may itself contain `[`, `*` or `?`.
 */
export type PathEntry = {
    glob: false;
    path: string;
} | {
    glob: true;
    path: string;
    /**
     * Set when this glob is anchored at a directory that is a name on
     * disk (the cwd, for the mandatory `**\/<name>` patterns, or an
     * existing one that holds glob characters): the prefix of
     * `path` that is a literal path rather than part of the pattern.
     */
    anchor?: string;
};
/**
 * Wrap command with macOS sandbox
 */
export declare function wrapCommandWithSandboxMacOS(params: MacOSSandboxParams): string;
/**
 * Start monitoring macOS system logs for sandbox violations
 * Look for sandbox-related kernel deny events ending in {logTag}
 */
export declare function startMacOSSandboxLogMonitor(callback: SandboxViolationCallback, ignoreViolations: IgnoreViolationsConfig | undefined, 
/** Map a decoded attribution key to the command text it represents, before
 *  ignoreViolations matching and before the event's `command` is set. Only
 *  the manager holds the registry that can do that, so it is required
 *  rather than defaulted: a caller with no registry passes
 *  `sanitizeUnregisteredCommandKey`, which treats the key as the untrusted
 *  bytes it arrived as. */
resolveCommandText: (decodedKey: string) => string): () => void;
//# sourceMappingURL=macos-sandbox-utils.d.ts.map