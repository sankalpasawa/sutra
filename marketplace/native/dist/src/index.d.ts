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
export { NativeEngine, createDefaultEngine, type NativeEngineOptions } from './runtime/native-engine.js';
export { executeWorkflow, type ExecuteOptions, type ExecutionResult } from './runtime/lite-executor.js';
export { HSutraConnector, resolveHSutraLogPath, type HSutraConnectorOptions, type HSutraConnectorStats } from './runtime/h-sutra-connector.js';
export { Router, computePromptHash, buildFallbackPrompt, type RouterOptions, type RouteRequest, type LLMFallback } from './runtime/router.js';
export { ArtifactCatalog, computeContentSha256, resolveDefaultRoot, type ArtifactCatalogOptions, type RegisterRequest } from './runtime/artifact-catalog.js';
export { RendererRegistry, DEFAULT_RENDERERS, type Renderer, type RendererRegistryOptions, type EventByType, type RendererForType } from './runtime/renderer-registry.js';
export type { HSutraEvent, HSutraVerb, HSutraDirection, HSutraTense, HSutraTiming, HSutraReversibility, HSutraRisk } from './types/h-sutra-event.js';
export type { TriggerSpec, Predicate, TriggerEventType } from './types/trigger-spec.js';
export { TRIGGER_EVENT_TYPES, PREDICATE_TYPES, isPredicate, isTriggerSpec } from './types/trigger-spec.js';
export type { RoutingDecision, RoutingMode, PredicateAttempt } from './types/routing-decision.js';
export type { CatalogedAsset } from './types/asset-catalog.js';
export { isCatalogedAsset, isAssetShape, SHA256_HEX_PATTERN, DOMAIN_ID_PATTERN, EXECUTION_ID_PATTERN } from './types/asset-catalog.js';
export type { EngineEvent, EngineEventType, RenderContext, RoutingDecisionEvent, WorkflowStartedEvent, WorkflowCompletedEvent, WorkflowFailedEvent, ArtifactRegisteredEvent, PolicyDecisionEvent, StepStartedEvent, StepCompletedEvent } from './types/engine-event.js';
export { ENGINE_EVENT_TYPES, isEngineEvent } from './types/engine-event.js';
export { loadStarterKit, type StarterKit, STARTER_DOMAINS, STARTER_CHARTERS, STARTER_WORKFLOWS, STARTER_TRIGGERS, STARTER_WORKFLOW_CHARTER_MAP, ONBOARDING_WORKFLOW } from './starter-kit/index.js';
/** Library version (sync with package.json + plugin.json + marketplace.json + cli/sutra-native.ts:VERSION). Enforced by tests/contract/version-sync.test.ts. */
export declare const NATIVE_VERSION = "1.1.3";
//# sourceMappingURL=index.d.ts.map