/**
 * Public library entry point — @sutra/native v1.1.0.
 *
 * Wave 3 GA library exports per codex consult 2026-05-03. Consumers
 * import { NativeEngine } from '@sutra/native' and embed the engine in
 * their own daemon / hook / test surface.
 *
 * Stability: types here are the v1.1.0 PUBLIC contract. Breaking changes
 * require a major version bump. Internal modules (src/engine/**, source-
 * preview surface) are NOT re-exported here and may change at any time.
 */
// Runtime engine
export { NativeEngine, createDefaultEngine } from './runtime/native-engine.js';
export { executeWorkflow } from './runtime/lite-executor.js';
// Composable runtime modules
export { HSutraConnector, resolveHSutraLogPath } from './runtime/h-sutra-connector.js';
export { Router, computePromptHash, buildFallbackPrompt } from './runtime/router.js';
export { ArtifactCatalog, computeContentSha256, resolveDefaultRoot } from './runtime/artifact-catalog.js';
export { RendererRegistry, DEFAULT_RENDERERS } from './runtime/renderer-registry.js';
export { TRIGGER_EVENT_TYPES, PREDICATE_TYPES, isPredicate, isTriggerSpec } from './types/trigger-spec.js';
export { isCatalogedAsset, isAssetShape, SHA256_HEX_PATTERN, DOMAIN_ID_PATTERN, EXECUTION_ID_PATTERN } from './types/asset-catalog.js';
export { ENGINE_EVENT_TYPES, isEngineEvent } from './types/engine-event.js';
// Starter kit
export { loadStarterKit, STARTER_DOMAINS, STARTER_CHARTERS, STARTER_WORKFLOWS, STARTER_TRIGGERS, STARTER_WORKFLOW_CHARTER_MAP, ONBOARDING_WORKFLOW } from './starter-kit/index.js';
/** Library version (sync with package.json + plugin.json + marketplace.json + cli/sutra-native.ts:VERSION). Enforced by tests/contract/version-sync.test.ts. */
export const NATIVE_VERSION = '1.1.3';
//# sourceMappingURL=index.js.map