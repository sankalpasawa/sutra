/**
 * atomic-write — fsync + atomic rename helper for governance state.
 *
 * Per holding/research/2026-05-04-d7-fsync-hardening-scope.md (D7 SCOPE-DOWN
 * codex 2026-05-04). Closes the page-cache loss window for proposal-ledger +
 * user-kit (founder approvals must survive crash).
 *
 * Pattern: write to .tmp file with fsync, then atomic rename. POSIX guarantees
 * rename atomicity within same filesystem. Caller responsible for both paths
 * being on same fs (typically true for governance state under HOME).
 */

import { openSync, writeSync, fsyncSync, closeSync, renameSync, mkdirSync } from 'node:fs'
import { dirname } from 'node:path'

/**
 * Atomically write data to path, with fsync flush to disk before rename.
 *
 * Crash-safety: any crash before rename leaves only the .tmp file
 * (recoverable / discardable); any crash after rename has the new content
 * fully on disk (fsync'd before rename).
 */
export function atomicWriteSync(path: string, data: string): void {
  mkdirSync(dirname(path), { recursive: true })
  const tmp = `${path}.tmp.${process.pid}.${Date.now()}`
  const fd = openSync(tmp, 'w')
  try {
    writeSync(fd, data)
    fsyncSync(fd)
  } finally {
    closeSync(fd)
  }
  renameSync(tmp, path)
}
