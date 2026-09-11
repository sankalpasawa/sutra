# Creation check — brief for the Stop-time subagent

Purpose: what a subagent verifies whenever a turn created something new, so that no creation lands without its dimensions (D74 complete creation, closed vocabulary). The deterministic floor is `creation-guard.sh` (PreToolUse) and `creation-stop-check.sh` (Stop); this brief is the judgement layer on top of them.

**Title**: Creation check brief
**Status**: ACTIVE with the guard in WARN mode; HARD when `.claude/creation-guard-mode` says hard
**Scope**: every new file or directory inside the repo this turn, however it was created (Write, Edit, Bash, subagent, script)
**Owner**: Core Plugin, Governance Hooks
**Updated**: 2026-09-11
**Source inputs**:

- founder direction D74 (2026-09-11)
- `holding/NEW-THING-PROTOCOL.md` section 2a (fit check)
- `holding/directory/GUARD-DESIGN.md`

## What to verify, per creation <a id="checks"></a>

| Dimension | Question | Evidence that satisfies it |
|---|---|---|
| domain | which department owns this? | a `CHARTER.md` or department `README.md` above the path; the turn's placement marker `DOMAIN_REF`; a rule in `.claude/creation-guard-rules.json` |
| charter | which promise does it answer to? | the placement marker `CHARTER_ID`; a `CHARTER.md` up the tree; the new file is itself a charter |
| placement | was this turn placed? | `.claude/sessions/<sid>/placement-registered` with a resolved `DOMAIN_REF` |
| artifact kind | does it fit the closed vocabulary? | one of: app, page, cli, code, sql, engine, hook, skill, policy, ledger, test, doc, plan, adr, charter, protocol, direction; docs also carry a layer L5-L14 |

## What to do with the result <a id="result"></a>

| Result | Action |
|---|---|
| all four present | say so in one line; nothing else |
| a dimension missing | create it before the turn ends: write the placement, name the charter, or add the department rule; never delete the creation to make the check pass |
| the kind is new | STOP. Print a highlighted `NEW KIND` event with the path and why it fits nothing; route to NEW-THING-PROTOCOL section 2a; wait for the founder |
| the guard was skipped by the kill-switch | report the skip; the audit row is in the hook log |

## Output form <a id="output"></a>

```text
CREATION CHECK: <n> created, <m> complete, <k> missing, <j> new kind
  <path> :: domain=<yes|no> charter=<yes|no> placement=<yes|no> kind=<kind|NEW>
```

## Provenance <a id="provenance"></a>

```yaml
provenance: {author: claude-fable-5-1 (session 6b3f51dd), date: 2026-09-11, inputs: [D74, NEW-THING-PROTOCOL 2a, GUARD-DESIGN.md], review: codex R3+R4 folded, supersedes: none, confidence: moderate, gaps: [subagent invocation is by convention until a SubagentStop wiring lands]}
```
