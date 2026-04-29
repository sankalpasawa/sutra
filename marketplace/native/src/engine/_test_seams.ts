/**
 * Engine test seams — INTERNAL.
 *
 * Re-exports the `__set/resetWorkflowContextProbeForTest` hooks for tests
 * ONLY. Kept out of `src/engine/index.ts` so that public consumers of the
 * engine barrel cannot reach in and override the F-12 probe at runtime.
 *
 * Test imports use this path directly:
 *   import { __setWorkflowContextProbeForTest } from '../../src/engine/_test_seams.js'
 *
 * Spec source:
 *  - holding/plans/native-v1.0/M5-workflow-engine.md Group I (quality fix-up)
 */

export {
  __setWorkflowContextProbeForTest,
  __resetWorkflowContextProbeForTest,
} from './activity-wrapper.js'
