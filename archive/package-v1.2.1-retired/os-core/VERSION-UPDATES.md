# Sutra — Version Update Protocol

## How New Learnings Reach Existing Companies

When the founder gives feedback or when a new company's onboarding reveals gaps, Sutra evolves. But existing companies (like DayFlow) are pinned to a version. This protocol manages the flow.

## The Flow

```
FEEDBACK arrives (from founder, from client, from onboarding)
  ↓
SUTRA SESSION evaluates: is this a real gap or a preference?
  ↓
If gap → add to Sutra's source files (layer2/layer3/layer4)
  ↓
Accumulate until 5+ changes → publish new version (v1.1, v1.2, etc.)
  ↓
For each existing client:
  ↓
Write update notice to {company}/feedback-from-sutra/version-{N}.md
  ↓
Next time that company's session starts → OS loads the notice
  ↓
Company decides: upgrade, skip, or partial adopt
```

## When Does Sutra Run?

Sutra runs as its own session. Separate from any company.

| Trigger | What Sutra Does |
|---------|----------------|
| Founder gives feedback ("add landing pages by default") | Adds to onboarding checklist, updates CLIENT-ONBOARDING.md |
| New company onboarded, reveals a gap | Fills the gap in Sutra's modules, bumps version |
| Weekly (or when founder requests) | Reviews all feedback-to-sutra/ across clients, batches into version |
| Founder says "validate new protocols against DayFlow" | Sutra writes update notice to DayFlow's folder |

## What Gets Versioned

| Change Type | Version Bump | Example |
|-------------|-------------|---------|
| New checklist item | Patch (v1.0 → v1.0.1) | "Add landing page by default" |
| New product type template | Minor (v1.0 → v1.1) | "Content platform architecture patterns" |
| Process restructure | Major (v1.0 → v2.0) | "Rewrote onboarding from 5 to 8 phases" |

## Validation Against Existing Companies

When Sutra adds a new protocol, it should be validated against existing clients:

1. Sutra writes `{company}/feedback-from-sutra/pending-{date}-{topic}.md`
2. Content: what changed, why, what the company should consider
3. Next time the company session runs, it reads the pending file
4. Company agent evaluates: relevant? helpful? adopt or skip?
5. Company writes response to `feedback-to-sutra/response-{date}-{topic}.md`
6. Sutra reads the response in next Sutra session

This is the two-way feedback loop. Sutra pushes updates. Companies push back if the update doesn't fit.

## Feedback Routing — Role-Based Permissions

Feedback routing depends on WHO is giving feedback, determined by their role in the hierarchy.

### The Hierarchy

```
CEO of Asawa Inc. (holding)
├── Has: full authority over all companies and Sutra itself
├── Can: change any Sutra doc, any company doc, any protocol
│
├── CEO of Sutra (operating system company)
│   ├── Has: authority over Sutra's processes, modules, onboarding
│   ├── Can: update Sutra docs, approve/reject client feedback
│   ├── Cannot: make product decisions for client companies
│   │
│   └── CEO of {Client Company} (e.g., CEO of DayFlow, CEO of Hehe)
│       ├── Has: authority over their company only
│       ├── Can: give feedback TO Sutra (captured as PENDING)
│       ├── Cannot: change Sutra docs directly
│       └── Cannot: change other companies' docs
```

### Role Detection by Session Context

| Session context | Role | Permissions |
|----------------|------|-------------|
| `asawa-inc/holding/` | CEO of Asawa | Full authority. Changes anything immediately. |
| `asawa-inc/sutra/` | CEO of Sutra | Changes Sutra docs. Processes client feedback with explicit approval. |
| `asawa-inc/{company}/` or `/sutra-onboard` | CEO of {Company} | Changes own company only. Feedback to Sutra = PENDING. |

### When CEO of {Company} gives feedback about Sutra

1. Write to `{company}/feedback-to-sutra/{date}-{topic}.md`
2. Mark as **PENDING**
3. Do NOT update any Sutra doc
4. Do NOT change CLIENT-ONBOARDING.md, ENFORCEMENT.md, or any protocol
5. Feedback sits until a Sutra session processes it

### When CEO of Sutra processes feedback

In a Sutra session:

1. List all pending: `find asawa-inc/*/feedback-to-sutra/ -name "*.md" | xargs grep "PENDING"`
2. For each PENDING item, present to CEO of Sutra:
   - What the client CEO said
   - What it would change in Sutra
   - Recommendation: apply, reject, or defer
3. CEO of Sutra explicitly approves or rejects each item
4. Approved → update Sutra docs, mark INCORPORATED
5. Rejected → mark REJECTED with reason
6. Deferred → stays PENDING

### When CEO of Asawa gives feedback

Direct apply. No approval gate. CEO of Asawa owns everything.

**ENFORCEMENT: HARD** — A client company session CANNOT modify Sutra source files. Only capture feedback. Sutra session processes it with explicit approval from CEO of Sutra.
