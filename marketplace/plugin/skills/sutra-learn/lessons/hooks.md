# Hooks — how the plugin protects you

Sutra ships ~20 plugin hooks that fire at specific Claude Code events:

| Event            | Purpose                                                    |
|------------------|------------------------------------------------------------|
| SessionStart     | Initialize, banner, privacy refresh                        |
| UserPromptSubmit | Detect directives, count corrections, reset turn markers   |
| PreToolUse       | Gate actions (depth missing, secret in content, role block)|
| PostToolUse      | Cascade checks, estimation logging, compliance tracking    |
| Stop             | Session-end metrics, retention cleanup, abandonment signal |
| PermissionRequest| Meta-permission for repeated approvals                     |

## The three that matter most

1. **depth-marker-pretool.sh** — blocks Edit/Write if depth block not written. Teaches depth discipline.
2. **keys-in-env-vars.sh (PROTO-004)** — blocks Edit/Write if content looks like an API key. Prevents accidental secret commits.
3. **enforce-boundaries.sh** — blocks cross-tier edits (e.g., Asawa session editing a client's IP).

## Override pattern

Every hard-enforced hook has an override:

```
CODEX_DIRECTIVE_ACK=1 CODEX_DIRECTIVE_REASON="..." <tool-call>
PROTO004_ACK=1 PROTO004_ACK_REASON="test fixture" <tool-call>
BUILD_LAYER_ACK=1 BUILD_LAYER_ACK_REASON="..." <tool-call>
```

Every override is logged. Patterns in override usage are fed back into the feedback-auto-override signal (see privacy charter).

## When to override vs. comply

- Comply: the hook is usually right. It exists because someone got burned.
- Override: you understand *why* the hook fired AND why your case is different. Write the reason in `ACK_REASON` — future-you will read it during incident review.

## Kill-switch

If a hook is actively wrong for your workflow, disable it:

```
touch ~/.sutra-<hook-name>-disabled
# or
SUTRA_<HOOK>_DISABLED=1 claude
```

Then file a `/sutra feedback` describing what was wrong.
