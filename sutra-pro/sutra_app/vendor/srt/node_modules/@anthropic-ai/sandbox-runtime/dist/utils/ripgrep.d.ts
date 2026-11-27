export interface RipgrepConfig {
    command: string;
    args?: string[];
    /** Override argv[0] when spawning (for multicall binaries that dispatch on argv[0]) */
    argv0?: string;
}
/**
 * Execute ripgrep with the given arguments
 * @param args Command-line arguments to pass to rg
 * @param target Target directory or file to search
 * @param abortSignal AbortSignal to cancel the operation
 * @param config Ripgrep configuration (command and optional args)
 * @returns Array of matching lines (one per line of output)
 * @throws RipgrepError if ripgrep exits with non-zero status (except exit code 1 which means no matches)
 */
export declare function ripGrep(args: string[], target: string, abortSignal: AbortSignal, config?: RipgrepConfig): Promise<string[]>;
/** ripgrep ended otherwise than by finding something or nothing. */
export declare class RipgrepError extends Error {
    /** What it had listed by then. */
    readonly listed: string[];
    /** What it said went wrong. The paths in it are the tree's own text. */
    readonly stderr: string;
    constructor(message: string, 
    /** What it had listed by then. */
    listed: string[], 
    /** What it said went wrong. The paths in it are the tree's own text. */
    stderr: string);
}
//# sourceMappingURL=ripgrep.d.ts.map