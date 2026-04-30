# Default Composition v1.0

3 seed Workflows that ship with Native v1.0. Each exercises a different engine subset; pick the one that matches your use case as a starting template.

| Seed | Exercises | Use case |
|---|---|---|
| [`governance-turn-emit`](governance-turn-emit.ts) | M5 step-graph executor + M8 OTel emitter (when wired) | Wire a per-turn governance record into your existing workflow |
| [`charter-obligation-eval`](charter-obligation-eval.ts) | M7 OPA policy_dispatcher + L4 terminal-check | Gate an action behind a Charter obligation predicate |
| [`skill-chain-stub`](skill-chain-stub.ts) | M6 SkillEngine resolve + M9 invariants composition | Chain 2+ Skills into a parent Workflow |

## Usage (operator workflow)

```typescript
import { buildGovernanceTurnEmitWorkflow } from './composition/index.js'
import { executeStepGraph } from './src/engine/step-graph-executor.js'

// 1. Build with your Tenant context.
const { domain, charter, workflow } = buildGovernanceTurnEmitWorkflow({
  tenant_id: 'T-yourtenant',
  domain_id: 'D1.D2-yourdomain',
})

// 2. Stub or wire your dispatcher (Activity boundary per M5/M6 contract).
const dispatch = () => ({ kind: 'ok' as const, outputs: [{}] })

// 3. Execute. Returns terminal state + DP records on the OTel sink (when wired).
const result = await executeStepGraph(workflow, dispatch)
```

For real workflows, customize:
- Domain principles (your Tenant's governing principles)
- Charter obligations / invariants / success_metrics (your Tenant's commitments)
- Workflow inputs / outputs / interfaces_with (your real data shapes)
- Dispatcher (your real Activity boundary — host-LLM, OPA, external API, etc.)

## When to NOT use these seeds

- You have a multi-tenant runtime (deferred to v1.1)
- You need cutover-engine semantics (P-B1; deferred to v1.x)
- You need full Vinit-style DOMAIN→CHARTER→WORKFLOW→TriggerSpec→EXECUTION lineage (see `tests/integration/m9-vinit-e2e.test.ts` as a richer reference)

## Cross-references

- Plan: `holding/plans/native-v1.0/M12-release-canary.md`
- Final architecture line 229: Default Composition is the "solo-founder bootstrap workflow set"
- M9 Vinit fixture (richer reference): [`../tests/integration/m9-vinit-e2e.test.ts`](../tests/integration/m9-vinit-e2e.test.ts)
- M11 dogfood (uses Vinit fixture): [`../scripts/dogfood-time-to-value.ts`](../scripts/dogfood-time-to-value.ts)
