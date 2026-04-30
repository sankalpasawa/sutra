/**
 * Sutra Connectors — secret-store-age (M1.7, load-bearing safety primitive).
 *
 * TS port of `sutra_safe_write` from sutra/marketplace/plugin/lib/privacy-sanitize.sh:100-112
 * + `age` subprocess wrapping with deterministic kill discipline.
 *
 * Spec authority: holding/research/2026-04-30-core-connectors-hardening-spec.md §M1.7
 * Codex direction (8 rounds converged): DIRECTIVE-ID 1777545909 (ADVISORY)
 *
 * Load-bearing invariants (codex-converged):
 *   1. Single `settled` flag — every reject/resolve goes through `settle(fn)`
 *      atomic check-and-set; eliminates double-settle race regardless of event
 *      ordering.
 *   2. `killWithEscalation()` symmetric for BOTH timeout AND abort paths:
 *      SIGTERM → 2s wait → check `proc.exitCode === null && proc.signalCode === null`
 *      → SIGKILL.
 *   3. `signal` is NOT passed to spawn() — abort owned exclusively by the
 *      explicit `signal.addEventListener('abort', onAbort, { once: true })`.
 *      No dual-ownership race.
 *   4. stdio: ['ignore', 'pipe', 'pipe'] — stdin closed (noninteractive);
 *      identity-file mode only (no -p passphrase prompt).
 *   5. Listener cleanup in error/close handlers via removeEventListener to
 *      prevent leak on long-lived signal sources.
 *   6. Already-aborted fast path — if signal already aborted at entry, fire
 *      onAbort immediately and return.
 *
 * Write path (sutra_safe_write semantics):
 *   - lstat target — refuse symlink
 *   - lstat parent — refuse symlinked parent
 *   - mkdir parent recursive with mode 0o700
 *   - openSync <target>.tmp.<pid> with O_WRONLY|O_CREAT|O_EXCL|O_NOFOLLOW, mode 0o600
 *   - feed plaintext via spawn `age -e -r <recipient>` stdin; encrypted bytes
 *     written to the held fd
 *   - fsyncSync, closeSync
 *   - renameSync(tmp, target) — atomic POSIX rename
 *
 * Read path:
 *   - lstat target — refuse symlink
 *   - spawn `age -d -i <identity-path> <target>`
 *   - collect stdout chunks; on close, Buffer.concat(chunks)
 */

import {
  closeSync,
  existsSync,
  fsyncSync,
  lstatSync,
  mkdirSync,
  openSync,
  renameSync,
  unlinkSync,
  writeSync,
} from 'node:fs';
import { spawn } from 'node:child_process';
import { dirname } from 'node:path';
import { constants as fsConstants } from 'node:fs';

import {
  SecretStoreSafetyError,
  SecretStoreTimeoutError,
  SecretStoreDecryptError,
  AbortError,
} from './errors.js';

const { O_WRONLY, O_CREAT, O_EXCL } = fsConstants;
// O_NOFOLLOW is POSIX; on platforms that lack it (very rare in Node 18+ on
// Linux/macOS), fall back to 0 — symlink-on-target is still caught by the
// explicit lstat check above. This matches the spec.
const O_NOFOLLOW = (fsConstants as unknown as { O_NOFOLLOW?: number }).O_NOFOLLOW ?? 0;

export interface SecretStoreAgeConfig {
  readonly identityPath: string;
  readonly recipientPath: string;
}

export interface DecryptOptions {
  readonly signal?: AbortSignal;
  readonly timeoutMs?: number;
}

export interface EncryptOptions {
  readonly signal?: AbortSignal;
  readonly timeoutMs?: number;
}

const DEFAULT_TIMEOUT_MS = 5_000;
const TERM_TO_KILL_GRACE_MS = 2_000;

export class SecretStoreAge {
  readonly #identityPath: string;
  readonly #recipientPath: string;

  constructor(cfg: SecretStoreAgeConfig) {
    if (!cfg || typeof cfg !== 'object') {
      throw new Error('SecretStoreAge: cfg required');
    }
    if (typeof cfg.identityPath !== 'string' || cfg.identityPath.length === 0) {
      throw new Error('SecretStoreAge: cfg.identityPath required');
    }
    if (typeof cfg.recipientPath !== 'string' || cfg.recipientPath.length === 0) {
      throw new Error('SecretStoreAge: cfg.recipientPath required');
    }
    this.#identityPath = cfg.identityPath;
    this.#recipientPath = cfg.recipientPath;
  }

  // --------------------------------------------------------------------------
  // encrypt — atomic, symlink-safe write of `age`-encrypted bytes
  // --------------------------------------------------------------------------
  async encrypt(
    target: string,
    plaintext: Buffer,
    opts: EncryptOptions = {},
  ): Promise<void> {
    // 1. lstat target — refuse symlink
    if (existsSync(target)) {
      const st = lstatSync(target);
      if (st.isSymbolicLink()) {
        throw new SecretStoreSafetyError(`refusing symlink target: ${target}`);
      }
    }

    // 2. lstat parent — refuse symlinked parent (lstat the parent path itself,
    //    not its contents — sutra_safe_write semantics)
    const parent = dirname(target);
    if (existsSync(parent)) {
      const ps = lstatSync(parent);
      if (ps.isSymbolicLink()) {
        throw new SecretStoreSafetyError(`refusing symlinked parent: ${parent}`);
      }
    }

    // 3. mkdir parent recursive with 0o700
    mkdirSync(parent, { recursive: true, mode: 0o700 });

    // 4. open <target>.tmp.<pid> with O_WRONLY|O_CREAT|O_EXCL|O_NOFOLLOW, 0o600
    const tmp = `${target}.tmp.${process.pid}`;
    const fd = openSync(tmp, O_WRONLY | O_CREAT | O_EXCL | O_NOFOLLOW, 0o600);

    let renamed = false;
    try {
      await this.#runAgeEncrypt(fd, plaintext, opts);
      fsyncSync(fd);
      closeSync(fd);
      renameSync(tmp, target);
      renamed = true;
    } finally {
      if (!renamed) {
        // Best-effort cleanup. The fd may already be closed by the success path
        // exception window; closeSync on a closed fd throws — swallow.
        try {
          closeSync(fd);
        } catch {
          /* fd already closed */
        }
        try {
          unlinkSync(tmp);
        } catch {
          /* tmp may not exist if openSync failed earlier */
        }
      }
    }
  }

  // --------------------------------------------------------------------------
  // decrypt — symlink-safe + deterministic-kill subprocess wrapper
  // --------------------------------------------------------------------------
  async decrypt(target: string, opts: DecryptOptions = {}): Promise<Buffer> {
    const st = lstatSync(target);
    if (st.isSymbolicLink()) {
      throw new SecretStoreSafetyError(`refusing symlink: ${target}`);
    }

    const signal = opts.signal;
    const timeoutMs = opts.timeoutMs ?? DEFAULT_TIMEOUT_MS;
    const identityPath = this.#identityPath;

    return new Promise<Buffer>((resolve, reject) => {
      // INVARIANT 6 (must run BEFORE spawn): already-aborted fast path.
      // If signal is already aborted, do not launch the age subprocess at
      // all — synchronously reject. Defending against the regression where
      // we used to spawn first then check, which violated the discipline.
      if (signal && signal.aborted) {
        reject(new AbortError('age -d aborted via signal (pre-spawn fast path)'));
        return;
      }

      // INVARIANT 3: signal NOT passed to spawn — explicit listener owns abort.
      // INVARIANT 4: stdio ignore stdin (noninteractive); pipe stdout/stderr.
      const proc = spawn('age', ['-d', '-i', identityPath, target], {
        stdio: ['ignore', 'pipe', 'pipe'],
      });

      const chunks: Buffer[] = [];
      let stderrBuf = '';
      // INVARIANT 1: single `settled` flag (no closed/killed split).
      let settled = false;

      const settle = (fn: () => void): void => {
        if (settled) return;
        settled = true;
        fn();
      };

      // INVARIANT 2: symmetric kill escalation for BOTH timeout AND abort.
      const killWithEscalation = (): void => {
        try {
          proc.kill('SIGTERM');
        } catch {
          /* ignore */
        }
        const escalation = setTimeout(() => {
          if (proc.exitCode === null && proc.signalCode === null) {
            try {
              proc.kill('SIGKILL');
            } catch {
              /* ignore */
            }
          }
        }, TERM_TO_KILL_GRACE_MS);
        escalation.unref();
      };

      proc.stdout?.on('data', (b: Buffer) => {
        chunks.push(b);
      });
      proc.stderr?.on('data', (b: Buffer) => {
        stderrBuf += b.toString();
      });

      const timer = setTimeout(() => {
        settle(() => {
          killWithEscalation();
          // INVARIANT 5: cleanup listener on settle path
          if (signal) signal.removeEventListener('abort', onAbort);
          reject(
            new SecretStoreTimeoutError(
              `age -d exceeded ${timeoutMs}ms for ${target}`,
            ),
          );
        });
      }, timeoutMs);
      timer.unref();

      const onAbort = (): void => {
        settle(() => {
          clearTimeout(timer);
          killWithEscalation();
          if (signal) signal.removeEventListener('abort', onAbort);
          reject(new AbortError('age -d aborted via signal'));
        });
      };

      if (signal) {
        // INVARIANT 6: already-aborted fast path
        if (signal.aborted) {
          onAbort();
          return;
        }
        signal.addEventListener('abort', onAbort, { once: true });
      }

      proc.on('error', (err) => {
        settle(() => {
          clearTimeout(timer);
          if (signal) signal.removeEventListener('abort', onAbort);
          reject(err);
        });
      });

      proc.on('close', (code) => {
        settle(() => {
          clearTimeout(timer);
          if (signal) signal.removeEventListener('abort', onAbort);
          if (code !== 0) {
            reject(
              new SecretStoreDecryptError(
                `age -d exited ${code}: ${stderrBuf.trim()}`,
              ),
            );
            return;
          }
          resolve(Buffer.concat(chunks));
        });
      });
    });
  }

  // --------------------------------------------------------------------------
  // private — runAgeEncrypt: feeds plaintext to `age -e -r <recipient>` stdin,
  // pipes ciphertext to the open fd. Same state-machine discipline as decrypt.
  // --------------------------------------------------------------------------
  async #runAgeEncrypt(
    fd: number,
    plaintext: Buffer,
    opts: EncryptOptions,
  ): Promise<void> {
    const signal = opts.signal;
    const timeoutMs = opts.timeoutMs ?? DEFAULT_TIMEOUT_MS;
    const recipientPath = this.#recipientPath;

    return new Promise<void>((resolve, reject) => {
      // INVARIANT 6 (must run BEFORE spawn): already-aborted fast path.
      // If signal is already aborted, do not launch the age subprocess at
      // all — synchronously reject. Mirrors decrypt() symmetric discipline.
      if (signal && signal.aborted) {
        reject(new AbortError('age -e aborted via signal (pre-spawn fast path)'));
        return;
      }

      const proc = spawn('age', ['-e', '-R', recipientPath], {
        stdio: ['pipe', 'pipe', 'pipe'],
      });

      let stderrBuf = '';
      let settled = false;

      const settle = (fn: () => void): void => {
        if (settled) return;
        settled = true;
        fn();
      };

      const killWithEscalation = (): void => {
        try {
          proc.kill('SIGTERM');
        } catch {
          /* ignore */
        }
        const escalation = setTimeout(() => {
          if (proc.exitCode === null && proc.signalCode === null) {
            try {
              proc.kill('SIGKILL');
            } catch {
              /* ignore */
            }
          }
        }, TERM_TO_KILL_GRACE_MS);
        escalation.unref();
      };

      proc.stdout?.on('data', (b: Buffer) => {
        // Write ciphertext to the held fd (already 0o600, EXCL+NOFOLLOW)
        try {
          writeSync(fd, b);
        } catch (err) {
          settle(() => {
            clearTimeout(timer);
            if (signal) signal.removeEventListener('abort', onAbort);
            killWithEscalation();
            reject(err);
          });
        }
      });
      proc.stderr?.on('data', (b: Buffer) => {
        stderrBuf += b.toString();
      });

      const timer = setTimeout(() => {
        settle(() => {
          killWithEscalation();
          if (signal) signal.removeEventListener('abort', onAbort);
          reject(
            new SecretStoreTimeoutError(`age -e exceeded ${timeoutMs}ms`),
          );
        });
      }, timeoutMs);
      timer.unref();

      const onAbort = (): void => {
        settle(() => {
          clearTimeout(timer);
          killWithEscalation();
          if (signal) signal.removeEventListener('abort', onAbort);
          reject(new AbortError('age -e aborted via signal'));
        });
      };

      if (signal) {
        if (signal.aborted) {
          onAbort();
          return;
        }
        signal.addEventListener('abort', onAbort, { once: true });
      }

      proc.on('error', (err) => {
        settle(() => {
          clearTimeout(timer);
          if (signal) signal.removeEventListener('abort', onAbort);
          reject(err);
        });
      });

      proc.on('close', (code) => {
        settle(() => {
          clearTimeout(timer);
          if (signal) signal.removeEventListener('abort', onAbort);
          if (code !== 0) {
            reject(
              new SecretStoreDecryptError(
                `age -e exited ${code}: ${stderrBuf.trim()}`,
              ),
            );
            return;
          }
          resolve();
        });
      });

      // Feed plaintext to age stdin and close — single-shot.
      proc.stdin?.on('error', (err) => {
        settle(() => {
          clearTimeout(timer);
          if (signal) signal.removeEventListener('abort', onAbort);
          killWithEscalation();
          reject(err);
        });
      });
      try {
        proc.stdin?.end(plaintext);
      } catch (err) {
        settle(() => {
          clearTimeout(timer);
          if (signal) signal.removeEventListener('abort', onAbort);
          killWithEscalation();
          reject(err);
        });
      }
    });
  }
}
