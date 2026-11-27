/**
 * `p` with every symbolic link on the way to it resolved. The real path is
 * the kernel's on every runtime, whatever characters its names hold.
 *
 * Off Windows a backslash is a character of a name like any other, and
 * runtimes differ in what `realpathSync` does with one. So the real path of a
 * name is asked of the file system component by component, split at `/`
 * alone, where the name holds a backslash. Every other name is asked of
 * `realpathSync.native`, since runtimes differ in how they read a link's
 * target too. On Windows `realpathSync` is asked, of `p` as it is.
 *
 * A `.`, `..` or `//` in `p` itself, and a `/` at its end, is folded in text
 * before anything is looked at: `link/..` is the directory that holds the
 * link. In a link's target they are read as the kernel reads them, `..` being
 * the parent of the real directory reached.
 *
 * An error carries the `code` the kernel gave the call that failed, ELOOP
 * past the number of links the kernel follows, and EILSEQ where the way leads
 * through a name that is no text.
 */
export declare function realPathOf(p: string): string;
/**
 * The kernel's way to `folded`, an absolute path with no `.`, `..` or `//` of
 * its own: name by name, split at `/` alone, every link followed. `real` is
 * as far as it leads, '' being the root. `rest` is what it has not come to:
 * nothing, or first the name that is not there, or that `real` lets nobody
 * look for (EACCES), with what the kernel said of it. Whatever else stops the
 * way is thrown. POSIX only.
 */
export declare function wayTo(folded: string): {
    real: string;
    rest: string[];
    notThere?: unknown;
};
//# sourceMappingURL=real-path.d.ts.map