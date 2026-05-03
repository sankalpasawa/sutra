/**
 * terminal-events — minimal renderer mapping EngineEvent → ASCII line.
 *
 * Used by the CLI's `run` subcommand so founders can see workflow execution
 * happen in real time. Each event becomes one line of stdout. No colors, no
 * unicode box-drawing — keeps it readable in any terminal + log file.
 */
import type { EngineEvent } from '../types/engine-event.js';
export declare function formatEvent(e: EngineEvent): string;
//# sourceMappingURL=terminal-events.d.ts.map