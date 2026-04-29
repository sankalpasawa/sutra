/**
 * Sutra Connectors — Fleet policy consumer
 * Frozen by LLD §2.6 (holding/research/2026-04-30-connectors-LLD.md).
 *
 * FleetPolicyCache:
 *  - Eagerly loads from FleetPolicySource on construction (test invariant:
 *    `loadSpy called once` after `new FleetPolicyCache(...)` + microtask flush).
 *  - Subscribes to source.watch(); onChange updates cached policy + lastLoadedAt.
 *  - current() throws StalePolicyError when (now - lastLoadedAt) > staleAfterMs.
 *  - refresh() re-loads from source and resets lastLoadedAt.
 *  - dispose() invokes the unsubscribe captured from source.watch().
 *
 * Filtering note: tests assert that the cache exposes the RAW policy
 * (all freezes preserved, including expired ones). The active-set filter
 * (`f.until === undefined || f.until > now`) is the consumer's responsibility
 * (policy.ts), not the cache's. See test "freeze rule with `until` past current
 * time is filtered (inactive) before evaluation" — `policy.freezes` has length 3
 * and the test does the filter inline.
 *
 * No external deps. Date.now() (compatible with vi.useFakeTimers + setSystemTime).
 */

import { StalePolicyError } from './errors.js';
import type { FleetPolicy, FleetPolicySource } from './types.js';

export class FleetPolicyCache {
  readonly #source: FleetPolicySource;
  readonly #staleAfterMs: number;
  #cached: FleetPolicy | undefined;
  #lastLoadedAt: number;
  #unsubscribe: (() => void) | undefined;
  #loadPromise: Promise<void> | undefined;

  constructor(source: FleetPolicySource, staleAfterMs: number) {
    this.#source = source;
    this.#staleAfterMs = staleAfterMs;
    this.#cached = undefined;
    this.#lastLoadedAt = Date.now();

    // Eager load — tests verify loadSpy called once after construction.
    this.#loadPromise = this.#load();

    // Subscribe to updates. onChange replaces cached policy and resets clock.
    this.#unsubscribe = this.#source.watch((p: FleetPolicy) => {
      this.#cached = p;
      this.#lastLoadedAt = Date.now();
    });
  }

  async #load(): Promise<void> {
    const p = await this.#source.load();
    this.#cached = p;
    this.#lastLoadedAt = Date.now();
  }

  /**
   * Returns the cached FleetPolicy. Throws StalePolicyError if the cache is
   * past the freshness window. Throws a plain Error if called before the
   * initial eager load has settled (caller must await microtask).
   */
  current(): FleetPolicy {
    if (this.#cached === undefined) {
      throw new Error(
        'FleetPolicyCache.current() called before initial load settled',
      );
    }
    if (this.isStale()) {
      throw new StalePolicyError(
        `Fleet policy is stale (last loaded ${
          Date.now() - this.#lastLoadedAt
        }ms ago, threshold ${this.#staleAfterMs}ms). Call refresh() before evaluating.`,
      );
    }
    return this.#cached;
  }

  /**
   * Returns true when (Date.now() - lastLoadedAt) > staleAfterMs.
   * Strict greater-than mirrors test: at exactly threshold, still fresh.
   */
  isStale(): boolean {
    return Date.now() - this.#lastLoadedAt > this.#staleAfterMs;
  }

  /**
   * Re-loads from source. After resolution, isStale() returns false.
   */
  async refresh(): Promise<void> {
    await this.#load();
  }

  /**
   * Detach from source.watch(). Idempotent. After dispose, further source
   * emit() calls do not mutate the cache.
   */
  dispose(): void {
    if (this.#unsubscribe !== undefined) {
      this.#unsubscribe();
      this.#unsubscribe = undefined;
    }
  }
}
