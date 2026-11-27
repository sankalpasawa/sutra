/**
 * How an entry of `denyRead`, `allowRead`, `allowWrite` or `denyWrite` is
 * read: as the pattern its characters spell, as the path they name, or both.
 *
 * An entry with `*`, `?`, `[` or `]` is a pattern. A directory may hold those
 * in its own name (`[WIP] project`), so such an entry is ALSO read as what it
 * names wherever the part that holds the characters exists on disk. An entry
 * marked `{ path, literal: true }` is the name and nothing else.
 *
 * The decision is made by the functions here only, for each stage that
 * needs it (the manager and the wrapper's fold on Linux, the profile builder
 * on macOS, `expandWindowsFsPaths` on Windows). One wrap may ask about an
 * entry more than once, and the disk may change in between.
 */
import { type Steps } from './sandbox-utils.js';
import type { FilesystemPathEntry } from './sandbox-config.js';
import type { FsReadRestrictionConfig, FsWriteRestrictionConfig } from './sandbox-schemas.js';
/**
 * Which way a list cuts. A deny takes every reading that may hold, since one
 * more can only deny more; an allow takes one only for a path that is there
 * exactly as spelled.
 */
export type PathListKind = 'allow' | 'deny';
/** One reading of an entry, shaped as the macOS builder's `PathEntry`. */
export type PathReading = 
/** The entry is the name of this path. */
{
    glob: false;
    path: string;
}
/**
 * The entry is a pattern beneath `anchor`, a directory taken as the name it
 * is: `path` is `anchor` plus the tail, and only the tail is pattern.
 */
 | {
    glob: true;
    path: string;
    anchor: string;
};
/**
 * The spellings and the marked paths of a list, apart. Throws on an entry
 * that is neither; see {@link markedLiteralPath}.
 */
export declare function splitPathEntries(entries: readonly FilesystemPathEntry[] | undefined): {
    spelled: string[];
    marked: string[];
};
/** The spellings among the entries of a list: what may be a pattern. */
export declare function spelledOf(entries: readonly FilesystemPathEntry[] | undefined): string[];
/**
 * Whether two lists hold the same entries, in any order. Entries are told
 * apart by value: a marked entry is a new object after every clone of the
 * config, and `/x` is not `{ path: '/x' }`.
 */
export declare function samePathEntries(a: readonly FilesystemPathEntry[], b: readonly FilesystemPathEntry[]): boolean;
/**
 * The readings a caller's spelling has BESIDE the one its characters give
 * it. Empty for a spelling that is no pattern, and for a pattern none of
 * whose glob characters are part of a name on disk: that costs one `lstat`.
 *
 * A trailing `/**` is set aside first. Of the components that hold glob
 * characters, the leading ones that exist on disk as spelled are names:
 *
 * - When all of them exist, the entry is also the NAME it spells. What
 *   follows the last of them need not exist.
 * - When a pattern follows an existing one, the entry is also that pattern
 *   BENEATH the directory. There is one such reading per existing component,
 *   the longest first, so creating or removing a directory adds or removes a
 *   reading and never turns one into another.
 *
 * Whether a spelling is a pattern is decided on what the caller wrote
 * (`isPattern`); which components hold glob characters, by
 * {@link containsGlobChars} on every platform, since those are what the
 * pattern compiler and the walk take for syntax.
 *
 * A component exists for a deny as {@link mayBeThere} has it. For an allow
 * no component from the first with glob characters on may be a symbolic
 * link or beyond looking at: a name to its end, a pattern up to its first
 * pattern component, from where the walk of an allow goes through no link.
 */
export declare function literalReadings(spelling: string, kind: PathListKind, opts?: {
    isPattern?: (spelling: string) => boolean;
}): PathReading[];
/** Whether a spelling that reads as a pattern is also the name of a path. */
export declare function hasNameReading(spelling: string, kind: PathListKind): boolean;
/**
 * What a Linux read entry resolves to: what `expandGlob` returns for the
 * pattern, then what the entry's other readings add. `name` is the entry as
 * a name, in the caller's spelling.
 */
export declare function withOtherReadings(spelling: string, name: string, kind: PathListKind, expandGlob: (pattern: string, anchor?: string) => Steps<string[]>): Steps<string[]>;
/**
 * The read rules `getDefaultWritePaths()` is given: the entries, the
 * credential denies, and the name each spelling also is, as a marked path.
 */
export declare function readRulesOf(denyRead: readonly FilesystemPathEntry[], allowRead: readonly FilesystemPathEntry[] | undefined, credentialDenies: readonly string[]): {
    denyRead: FilesystemPathEntry[];
    allowRead: FilesystemPathEntry[] | undefined;
};
/**
 * The `literal…` lists of a read config: the marked entries of the two read
 * lists. A key is present only when its list is not empty.
 */
export declare function literalReadLists(denyRead: readonly FilesystemPathEntry[] | undefined, allowRead: readonly FilesystemPathEntry[] | undefined): Pick<FsReadRestrictionConfig, 'literalDenyOnly' | 'literalAllowWithinDeny'>;
/** The `literal…` lists of a write config; see {@link literalReadLists}. */
export declare function literalWriteLists(allowWrite: readonly FilesystemPathEntry[] | undefined, denyWrite: readonly FilesystemPathEntry[] | undefined): Pick<FsWriteRestrictionConfig, 'literalAllowOnly' | 'literalDenyWithinAllow'>;
/**
 * Every path a write config allows, whichever list it came in on. Whoever
 * asks "may the command write here" asks this, not `allowOnly` alone: a
 * path the caller marked literal is in `literalAllowOnly` and nowhere else.
 */
export declare function writeRootsOf(config: Pick<FsWriteRestrictionConfig, 'allowOnly' | 'literalAllowOnly'>): string[];
/**
 * The paths bound back over a read deny: the read allows and the write
 * allows, the marked ones among them. A deny glob's matches are collapsed
 * against these, and one left out loses the matches beneath it their mask.
 */
export declare function reExposedBy(expandedAllowRead: readonly string[], allowRead: readonly FilesystemPathEntry[] | undefined, writeConfig: FsWriteRestrictionConfig): string[];
/**
 * A read config for a backend to which every path is a name (Linux): the
 * literal lists folded into the lists they are more entries of, and gone as
 * keys, so that whatever reads `denyOnly` has read them all.
 */
export declare function readNamesOf(config: FsReadRestrictionConfig | undefined): FsReadRestrictionConfig | undefined;
/**
 * The same for a write config; see {@link readNamesOf}. A string of
 * `allowOnly` that holds glob characters is kept only when it is also the
 * name of a path (see {@link literalReadings}). Any other is a pattern and
 * no name: resolving a name folds a `..` by the text, so `/home/*\/../.ssh`
 * would make `/home/.ssh` writable where nothing is named `*`.
 */
export declare function writeNamesOf(config: FsWriteRestrictionConfig | undefined): FsWriteRestrictionConfig | undefined;
//# sourceMappingURL=path-entries.d.ts.map