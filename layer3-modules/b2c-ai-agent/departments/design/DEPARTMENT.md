# Design Department — AI Agent

## Mission
Own the conversation experience. For AI agents, design IS the conversation — how the agent responds, formats output, handles errors, and communicates uncertainty. The interface may be minimal (chat, CLI, API) but the interaction design is critical.

## Team
- **Chief Design Officer** (agent: `cdo`) — owns conversation UX, response formatting, error states
- **UX Writer** (sub-agent) — agent personality, tone, error messages, loading states

## Responsibilities
- Conversation flow design — how the agent greets, clarifies, responds, handles errors
- Response formatting — structure, whitespace, emphasis, code blocks, lists vs prose
- Error state design — what the agent says when it can't help, when it's uncertain, when it fails
- Loading/streaming UX — progressive disclosure during long responses
- Agent personality specification — formal vs casual, verbose vs terse, assertive vs deferential
- Conversation UI layout (if applicable) — chat interface, input affordances, action buttons
- Design QA on agent responses — do they look good? Are they scannable?

## Key Principle
The agent's response IS the product interface. A correct but poorly formatted response is a design bug. A well-formatted wrong response is an engineering bug. Both matter equally.

## Decision Authority
- **Autonomous**: Response formatting, tone adjustments within approved personality, error message copy
- **Needs founder approval**: Personality changes, new response modalities (voice, images), major UX restructuring
- **Needs cross-department input**: Capability boundaries (Product), technical constraints (Engineering)

## Health Metrics
| Metric | Target | Current |
|--------|--------|---------|
| Response readability score | Scannable in < 5s | TBD |
| Error message clarity | User knows what to do next | TBD |
| Personality consistency | No tone drift across capabilities | TBD |
