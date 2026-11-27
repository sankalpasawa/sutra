/**
 * The glob syntax of a filesystem entry. {@link parseGlob} alone reads it;
 * what else needs it goes by the tokens.
 */
export declare enum GlobTokenKind {
    /** Characters that stand for themselves, none of them a separator. */
    Text = "text",
    /** `/` */
    Separator = "separator",
    /** `?`: one character of a name. */
    AnyChar = "anyChar",
    /** `*`: any number of characters of a name. */
    Star = "star",
    /** `**`: any number of characters, separators among them. */
    Globstar = "globstar",
    /** `**` with the `/` after it: any number of directories. */
    GlobstarSlash = "globstarSlash",
    /** `[abc]`, `[a-z]`: one character of a set. */
    Set = "set"
}
export type GlobToken = {
    kind: GlobTokenKind.Text;
    text: string;
} | {
    kind: GlobTokenKind.Set;
    /** What is written between the brackets. */
    members: string;
    /** `[+-9]` does: a `/` lies between the two. */
    matchesSeparator: boolean;
} | {
    kind: GlobTokenKind.Separator | GlobTokenKind.AnyChar | WildcardKind;
};
/** The kinds that match any number of characters. */
type WildcardKind = GlobTokenKind.Star | GlobTokenKind.Globstar | GlobTokenKind.GlobstarSlash;
/**
 * `pattern` as its tokens, in time that grows with its length. Every string
 * is a pattern, and no character escapes another:
 *
 * - A set runs from a `[` to the first `]` after it, be that the next
 *   character. All between the two are members, a `*`, a `?`, a `/` or another
 *   `[` too, and `^` and `!` do not negate.
 * - Brackets that spell no set (see {@link setRanges}) are text, as POSIX
 *   reads a `[` that opens none, and what is between them keeps its meaning.
 *   So are a `[` that nothing closes and a `]` that nothing opens.
 * - Of a run of `*`, the last two go with a `/` that follows. Two or more of
 *   the rest are a `**`.
 */
export declare function parseGlob(pattern: string): GlobToken[];
/** A regular expression that matches `text` and nothing else. */
export declare function escapeRegexLiteral(text: string): string;
/** The regular expression for what `token` matches. */
export declare function globTokenToRegex(token: GlobToken): string;
/**
 * Convert a glob pattern to a regular expression
 *
 * This implements gitignore-style pattern matching to match the behavior of the
 * `ignore` library used by the permission system.
 *
 * Supported patterns:
 * - * matches any characters except / (e.g., *.ts matches foo.ts but not foo/bar.ts)
 * - ** matches any characters including / (e.g., src/**\/*.ts matches all .ts files in src/)
 * - ? matches any single character except / (e.g., file?.txt matches file1.txt)
 * - [abc] matches any character in the set (e.g., file[0-9].txt matches file3.txt)
 *
 * Whatever a pattern spells, what is returned compiles, so that no entry keeps
 * a sandbox from starting (see {@link parseGlob}). Only its size can be more
 * than an engine takes.
 *
 * Shared between macOS sandbox profiles and Linux glob expansion.
 */
export declare function globToRegex(globPattern: string): string;
/**
 * Regex for a glob used in a DENY rule: {@link globToRegex} plus an optional
 * `/…` tail, so the deny covers everything beneath each match the way
 * `subpath` does for literals. Callers strip a trailing `/**` before the
 * pattern gets here (removeTrailingGlobSuffix), so `**\/secrets/**` arrives
 * as `**\/secrets` and, matched exactly, would deny only the directory
 * vnode while `secrets/key` stayed readable. This is what the Linux backend
 * already does (a deny masks the whole subtree). Only ever widens a deny.
 *
 * Takes a whole pattern, so every character in it is glob syntax: right for
 * the pattern reading of a spelling the caller wrote, which is what
 * `readRuleCovers` passes. A pattern anchored at a directory that is a
 * name on disk goes through the macOS `denyGlobEntryRegex`, which splices
 * that directory back in escaped and calls this for the tail.
 */
export declare function denyGlobRegex(normalizedGlob: string): string;
export {};
//# sourceMappingURL=glob-pattern.d.ts.map