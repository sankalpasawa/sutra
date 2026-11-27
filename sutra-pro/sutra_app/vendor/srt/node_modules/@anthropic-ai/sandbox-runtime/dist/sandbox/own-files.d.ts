/**
 * A warning when a sandboxed command could rewrite this copy of the library:
 * the host side runs unsandboxed, so whoever may write
 * `<project>/node_modules/` decides what the next run there executes.
 *
 * That is when the package directory holding `moduleFile` lies at or under one
 * of `allowedWritePaths`, as spelled or where it really is. Undefined
 * otherwise, and for a copy not under a `node_modules` (a checkout, which is
 * the project being worked on) or with no manifest on disk (compiled into an
 * application). An allowed write path that is a pattern is not judged.
 */
export declare function ownInstallWarning(allowedWritePaths: readonly string[], moduleFile?: string): string | undefined;
//# sourceMappingURL=own-files.d.ts.map