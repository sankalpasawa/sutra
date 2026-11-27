import { type SandboxRuntimeConfig } from '../sandbox/sandbox-config.js';
/**
 * Parse and validate sandbox configuration from a string
 * Used for parsing config from control fd (JSON lines protocol)
 */
export declare function loadConfigFromString(content: string): SandboxRuntimeConfig | null;
/**
 * Why a settings file did not yield a config. Only `missing` is a reason to
 * run with the built-in defaults; the rest name a file whose rules would be
 * silently dropped by doing so. `reason` is a printable sentence naming the
 * path — key paths and validator messages, never the file's values.
 */
export type LoadConfigResult = {
    kind: 'ok';
    config: SandboxRuntimeConfig;
} | {
    kind: 'missing';
} | {
    kind: 'empty';
} | {
    kind: 'unreadable';
    reason: string;
} | {
    kind: 'invalid';
    reason: string;
};
/**
 * Load and validate sandbox configuration from a file.
 */
export declare function loadConfig(filePath: string): LoadConfigResult;
//# sourceMappingURL=config-loader.d.ts.map