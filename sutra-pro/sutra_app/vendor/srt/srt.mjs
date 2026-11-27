// Sutra's launcher for the bundled srt (D462). The desktop app runs it on Electron's own node with ELECTRON_RUN_AS_NODE=1;
// that variable is removed here so it never reaches the sandboxed command. cli.js runs srt's main() on import.
delete process.env.ELECTRON_RUN_AS_NODE;
await import('./node_modules/@anthropic-ai/sandbox-runtime/dist/cli.js');
