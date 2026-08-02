/**
 * Reporter — formats transcript + multi-axis assertion table for stdout.
 *
 * Both-sides chronological transcript per founder direction. ASCII only —
 * no unicode box-drawing per D-UX-1.
 *
 * SPEC: docs/superpowers/specs/2026-05-07-verifier-engine-v1-design.md §7 + §8
 */
import type { AssertionReport, NativeRun } from '../../../types/assertion-report.js';
export declare function formatTranscript(utterance: string, run: NativeRun): string;
export declare function formatReport(report: AssertionReport): string;
//# sourceMappingURL=reporter.d.ts.map