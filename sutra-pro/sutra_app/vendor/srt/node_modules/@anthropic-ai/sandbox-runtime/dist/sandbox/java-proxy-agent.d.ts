export declare const JAVA_PROXY_AGENT_JAR_NAME = "srt-proxy-agent.jar";
/**
 * Locate srt-proxy-agent.jar. Order:
 * 0. explicit path (config `javaAgentJarPath`) — used if it exists,
 * 1. vendor/java-proxy-agent/ next to this module (bundled),
 * 2. ../../vendor/java-proxy-agent/ (package root — normal npm install),
 * 3. ../vendor/java-proxy-agent/ (dist/vendor — some bundlers),
 * 4. a global npm install of the package (native builds without vendor/).
 * Returns null when nothing is found; callers then leave JAVA_TOOL_OPTIONS
 * alone (JVMs are simply not proxy-aware, as before) rather than failing.
 *
 * The global-npm fallback resolves `npm root -g` without blocking the event
 * loop.
 */
export declare function getJavaProxyAgentJarPathAsync(explicitPath?: string): Promise<string | null>;
/**
 * Compose the JAVA_TOOL_OPTIONS value for a sandboxed child.
 *
 * `-javaagent:<jar>` is prepended when a jar path is given; `flags` are
 * appended (e.g. macOS's -Djava.net.preferIPv4Stack=true). The parent's
 * own JAVA_TOOL_OPTIONS is preserved unless that var is on the
 * credential-deny list, in which case it is dropped so the deny holds.
 * Flags already present in the inherited value are not duplicated.
 * Returns undefined when there is nothing to set.
 */
export declare function buildJavaToolOptions(opts: {
    agentJarPath?: string;
    flags?: string[];
    unsetEnvVars?: string[];
    inherited?: string;
}): string | undefined;
//# sourceMappingURL=java-proxy-agent.d.ts.map