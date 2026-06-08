---
issue: 19
title: "[feedback v2.7.3] from plugin"
author: vinitharmalkar
state: OPEN
created: 2026-04-28T07:44:18Z
updated: 2026-04-28T08:17:31Z
labels: —
url: https://github.com/sankalpasawa/sutra/issues/19
comments: [{'id': 'IC_kwDOR5MNCs8AAAABAkvCoQ', 'author': {'login': 'vinitharmalkar'}, 'authorAssociation': 'NONE', 'body': '**Triage note — feature request, not noise**\n\n**Real title:** Feature: Cross-LLM Provider Switcher — `sutra provider select` to switch between Claude, DeepSeek, OpenAI within Claude Code\n\n**Summary:** Let users switch LLM providers (Claude, DeepSeek V4, OpenAI, etc.) from within Claude Code the same way they pick a model today — one command, no manual env var juggling. Sutra owns the full UX and routing layer.\n\n**Why now:** DeepSeek V4-Pro (released April 24, 2026) is 3–10x cheaper than Claude on output tokens. For high-volume agentic workloads this is a $4,000–7,000/month difference per user. No clean switching mechanism exists today.\n\n**Technical path (no Claude Code changes needed):**\nClaude Code already supports `ANTHROPIC_BASE_URL` (custom gateway), `ANTHROPIC_CUSTOM_MODEL_OPTION*` (register custom models in /model picker), and `apiKeyHelper` (dynamic auth). A LiteLLM proxy (MIT, pip install) translates Anthropic Messages API → DeepSeek/OpenAI. Sutra manages config, switching UX, and cost tracking on top.\n\n**Proposed pieces:**\n- `sutra provider select <name>` — switch active provider, writes to settings.local.json\n- `provider-switcher.sh` (SessionStart) — banner showing active provider + cost tier\n- `provider-env-injector.sh` (PreToolUse) — injects ANTHROPIC_BASE_URL + registers /model picker entries\n- `sutra provider gateway start` — boots LiteLLM proxy from providers.json\n- Cost tracker extension — reads provider pricing instead of hardcoded Claude rates\n\n**Full spec including providers.json schema, edge cases, acceptance criteria, and file list is in the issue body.**\n\n**Version target:** 2.8.x · macOS Darwin 25.3.0', 'createdAt': '2026-04-28T08:17:31Z', 'includesCreatedEdit': False, 'isMinimized': False, 'minimizedReason': '', 'reactionGroups': [], 'url': 'https://github.com/sankalpasawa/sutra/issues/19#issuecomment-4333486753', 'viewerDidAuthor': False}]
---

# #19 [feedback v2.7.3] from plugin

**Author:** vinitharmalkar  |  **State:** OPEN  |  **Labels:** —
**Created:** 2026-04-28T07:44:18Z  |  **Updated:** 2026-04-28T08:17:31Z
**URL:** https://github.com/sankalpasawa/sutra/issues/19

---

Feature Request: Cross-LLM Provider Switcher — sutra provider select

SUMMARY:
Let users switch between Claude, DeepSeek V4, OpenAI, and other LLMs from within Claude Code the same way they pick a model today — with a single command or session-start prompt. Sutra owns the full UX + routing layer; Claude Code's existing ANTHROPIC_BASE_URL + ANTHROPIC_CUSTOM_MODEL_OPTION* mechanism is the hook.

WHY NOW:
DeepSeek V4-Pro dropped April 24, 2026. At standard pricing it is 3x cheaper than Claude Sonnet 4.6 on output tokens and 10x cheaper than Opus 4.7. V4-Flash is /bin/zsh.14//bin/zsh.28 per 1M tokens. For high-volume agentic workloads (sessions running 10M+ output tokens/day), this is a ,000–7,000/month cost difference per user. But there is no clean way to switch without manually managing env vars across terminals.

HOW CLAUDE CODE MAKES THIS POSSIBLE (no Claude Code changes needed):
1. ANTHROPIC_BASE_URL — points Claude Code at any gateway endpoint instead of api.anthropic.com
2. ANTHROPIC_CUSTOM_MODEL_OPTION / ANTHROPIC_CUSTOM_MODEL_OPTION_NAME / <HIGH-ENTROPY> — registers custom model names in the /model picker
3. apiKeyHelper (settings.json) — dynamic auth token injection per provider
4. ANTHROPIC_MODEL env var — overrides active model without touching settings.json

The proxy layer (LiteLLM) accepts Anthropic Messages API format and translates to DeepSeek/OpenAI endpoints. Claude Code never needs to know it is talking to a different provider.

PROPOSED ARCHITECTURE — Four Pieces:

PIECE 1 — sutra provider CLI subcommand (new command):
  sutra provider list              → show available providers + current active
  sutra provider select <name>     → switch active provider (writes config + restarts env)
  sutra provider add <name> <url>  → register a custom gateway
  sutra provider remove <name>     → deregister
  sutra provider status            → show active provider, latency ping, estimated cost tier

Registry stored at ~/.sutra/providers.json:
{
  'anthropic-direct': { base_url: null, model_map: { opus: 'claude-opus-4-7', sonnet: 'claude-sonnet-4-6' }, api_key_env: 'ANTHROPIC_API_KEY', cost_per_M_input: 5.00, cost_per_M_output: 25.00 },
  'deepseek-v4-pro':  { base_url: 'https://api.deepseek.com/v1', model_map: { opus: 'deepseek-v4-pro', sonnet: 'deepseek-v4-flash' }, api_key_env: 'DEEPSEEK_API_KEY', cost_per_M_input: 1.74, cost_per_M_output: 3.48 },
  'deepseek-v4-flash': { base_url: 'https://api.deepseek.com/v1', model_map: { opus: 'deepseek-v4-flash', sonnet: 'deepseek-v4-flash' }, api_key_env: 'DEEPSEEK_API_KEY', cost_per_M_input: 0.14, cost_per_M_output: 0.28 }
}

PIECE 2 — provider-switcher.sh (SessionStart hook):
On session start, if active provider != anthropic-direct, emit banner:
  ┌─ SUTRA PROVIDER: DeepSeek V4-Pro ──────────────────────────────┐
  │  Routing via LiteLLM gateway at localhost:4000                  │
  │  Cost tier: .74/.48 per 1M tokens (vs / Anthropic)    │
  │  sutra provider select claude  to switch back                   │
  └─────────────────────────────────────────────────────────────────┘
Exits silently if using anthropic-direct.

PIECE 3 — provider-env-injector.sh (PreToolUse + settings bridge):
When provider is switched, writes to ~/.claude/settings.local.json:
  { 'env': { 'ANTHROPIC_BASE_URL': 'http://localhost:4000', 'ANTHROPIC_API_KEY': '' }, 'model': 'deepseek-v4-pro' }
Also registers ANTHROPIC_CUSTOM_MODEL_OPTION vars so the /model picker shows provider-prefixed names:
  <HIGH-ENTROPY>
  <HIGH-ENTROPY> V4-Pro (via Sutra)
  <HIGH-ENTROPY> V4 Pro — .74/.48 per 1M tokens

PIECE 4 — LiteLLM bootstrap helper (optional, bundled):
  sutra provider gateway start     → starts litellm proxy on localhost:4000 with current providers.json
  sutra provider gateway stop      → kills the proxy
  sutra provider gateway status    → shows running providers + health
Generates a litellm_config.yaml from providers.json on the fly. User only needs litellm installed (pip install litellm).

PIECE 5 — Cost tracker extension:
Existing estimation-collector hook hardcodes Anthropic pricing. Extend it to read cost_per_M_input/output from the active provider in providers.json instead. Same TASK/DEPTH/COST block format, but now shows: 'Cost: ~/bin/zsh.12 (~DeepSeek V4-Flash pricing)' instead of always assuming Claude rates.

USER EXPERIENCE (complete flow):
  1. sutra provider add deepseek-v4-pro https://api.deepseek.com/v1    ← one-time setup
  2. sutra provider select deepseek-v4-pro                              ← switch
  3. claude                                                             ← start session, banner shows active provider
  4. /model                                                             ← picker shows 'DeepSeek V4-Pro (via Sutra)' alongside Claude models
  5. sutra provider select claude                                       ← switch back
  Kill-switch: SUTRA_PROVIDER_ROUTING=0 or ~/.sutra-provider-routing-disabled

FILES TO CREATE/MODIFY:
  bin/sutra                   — add 'provider' subcommand dispatcher
  scripts/provider.sh         — main CLI implementation
  scripts/provider-gateway.sh — LiteLLM bootstrap helper
  hooks/provider-switcher.sh  — SessionStart banner
  hooks/provider-env-injector.sh — settings bridge
  hooks/hooks.json            — register 2 new hooks
  lib/providers.sh            — shared provider registry read/write functions
  lib/cost-rates.sh           — refactor hardcoded Anthropic rates to be provider-aware
  ~/.sutra/providers.json     — runtime provider registry (auto-created on first 'sutra provider add')
  PERMISSIONS.md              — document new files + env vars written
  tests/unit/test-provider.sh — unit tests for registry CRUD + env injection

BENCHMARK CONTEXT (why this matters):
Claude Opus 4.7 leads on: SWE-bench Pro (64.3% vs 55.4%), GPQA Diamond (94.2% vs 90.1%), tool use (MCPAtlas 77.3% vs 73.6%), vision (DeepSeek V4 is text-only).
DeepSeek V4-Pro leads on: competitive coding (Codeforces 3206 — highest ever), math (HMMT 95.2%), BrowseComp (83.4%), price (3-10x cheaper on output).
Use case routing: Claude for SWE/agentic tasks, DeepSeek for math/competitive coding, DeepSeek Flash for high-volume cheap tasks. Sutra is the routing layer that makes this frictionless.

PRIORITY: High. This is the single largest cost lever available to Sutra users. No Claude Code changes needed — the ANTHROPIC_BASE_URL + LiteLLM pattern already works today. Sutra adds the discovery, switching UX, cost tracking, and session banner. Version target: 2.8.x
