/**
 * Reporter — formats transcript + multi-axis assertion table for stdout.
 *
 * Both-sides chronological transcript per founder direction. ASCII only —
 * no unicode box-drawing per D-UX-1.
 *
 * SPEC: docs/superpowers/specs/2026-05-07-verifier-engine-v1-design.md §7 + §8
 */

import type { AssertionReport, NativeRun } from '../../../types/assertion-report.js'

export function formatTranscript(utterance: string, run: NativeRun): string {
  const start = run.events[0]?.ts ?? 0
  const fmt = (ts: number) => {
    const sec = Math.floor((ts - start) / 1000)
    return `${String(Math.floor(sec / 60)).padStart(2, '0')}:${String(sec % 60).padStart(2, '0')}`
  }
  const lines: string[] = []
  lines.push(`${fmt(start)} USER     "${utterance}"`)
  for (const ev of run.events) {
    if (ev.type === 'utterance') continue
    const payload = ev.payload ? JSON.stringify(ev.payload) : ''
    lines.push(`${fmt(ev.ts)} NATIVE   ${ev.type}${payload ? ' ' + payload : ''}`)
  }
  return lines.join('\n')
}

export function formatReport(report: AssertionReport): string {
  const lines: string[] = []
  // Column widths: # 2, tier 9, id 30, axis 20, status 6.
  // id widened to 30 so full assertion ids (e.g. "tier-2/non-goal/e-commerce" = 26)
  // appear verbatim — needed by tests that grep for full ids and by humans
  // reading reports.
  lines.push('+----+-----------+--------------------------------+----------------------+--------+')
  lines.push('| #  | tier      | id                             | axis                 | status |')
  lines.push('+----+-----------+--------------------------------+----------------------+--------+')
  report.results.forEach((r, i) => {
    lines.push(
      `| ${String(i + 1).padEnd(2)} | ${r.tier.padEnd(9)} | ${trunc(r.id, 30).padEnd(30)} | ${r.axis.padEnd(20)} | ${r.status.padEnd(6)} |`
    )
  })
  lines.push('+----+-----------+--------------------------------+----------------------+--------+')
  lines.push('')
  lines.push(`VERDICT: ${report.verdict}  ${report.summary.pass}/${report.summary.total} pass  ${report.summary.fail} fail  ${report.summary.skipped} skipped  ${(report.duration_ms / 1000).toFixed(1)}s`)
  return lines.join('\n')
}

function trunc(s: string, n: number): string {
  return s.length <= n ? s : s.slice(0, n - 1) + '...'
}
