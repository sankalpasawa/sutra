# ADR-043 — Two AIs per task: a Shadow chat and a worker chat (Proposed, 2026-09-16)

**Status**: Proposed · **updated**: 2026-09-16 · author: CEO of Asawa

## Status

Proposed — 2026-09-16 (founder rulings, session 0e13cd35: "only those two AIs, no more AIs"; "each shadow to be an individual shadow sutra chat"; "the Now chat should determine how I split them"). Accepted when the v4 build lands (`holding/plans/shadow/BUILD-PLAN-V4.md` step 20).

## Context

Shadow (`marketplace/plugin/sutra-ui/`) drives one worker chat per task. Three model processes take part today: the founder's persistent Shadow session (`shadow_session.py:80`), the worker chat spawned with a brief (`shadow_runner.py:1754`), and a cold one-shot decider per turn (`shadow_runner.py:1379`). The brief is a string template with the founder's words pasted in (`app.py:1707`); real missions on 2026-09-15 and 2026-09-16 carried that template. A task start costs three cold `claude` boots, each turn one more, and the third process has no chat the founder can open.

The decider was separated so that reasoning would not serialise against the founder's typing in one global chat nor grow one context without bound (`shadow_runner.py:1382`). That reason does not hold once each task has its own chat.

### Alternatives considered

- **One global Shadow chat steering every task**: re-creates the context growth the decider avoided; rejected by the founder.
- **Keep the decider, compose the brief with it**: still a third process per turn; rejected under "no more AIs".
- **Worker chat steers itself**: no floor, no approval object; rejected.

## Decision (proposed 2026-09-16)

Every task MUST run on exactly two model processes, both ordinary Sutra chats:

1. The task's Shadow chat: born at Start or at the first message typed in the task chat, resumable with `--resume`, listed in Chats as "Shadow: task". It writes the brief at Start and at every turn boundary reads the worker's reply and returns the next instruction through the say path. It carries no Shadow tools, so it can only return text the engine validates.
2. The task's worker chat: spawned once with the brief, driven only through the say path, subject to the floors.

Rules that follow:

- The persistent Shadow session becomes the Now chat: it splits one founder message into one or several drafts (one `mission` fence per task) and does no work itself.
- The one-shot decider stays as the fallback when a task's Shadow chat is dead (`BUILD-PLAN-V4.md` G-1).
- The founder's "How Shadow behaves" text is appended at boot of every Shadow chat, below the floors and the founder's words in the task chat, above global rules.

## Consequences

| Kind | Effect |
|---|---|
| positive | one process per turn less; a chat to open for every task; a composed brief |
| positive | floor and approval stay on the say path (`app.py:3148`) |
| negative | up to cap plus one live `claude` processes (cap 5, `mission_engine.py:192`); the sheet exposes the cap |
| neutral | `test_shadow_reasoning_runtime.py` asserts the fallback path instead of "no chat record" |
| open | whether a task's Shadow chat outlives its task for Retry (plan: no, V3-9) |

## Provenance

```yaml
provenance: {author: claude-fable-5-1 (session 0e13cd35, atom a-0e13cd35-04), date: 2026-09-16, inputs: [founder rulings 2026-09-16, BUILD-PLAN-V4.md v1.1, REVIEWS-PLAN.md fold, shadow_runner.py, shadow_session.py, app.py], review: codex design-review of the plan folded (TaskChat env, settings scope, app seed), supersedes: none, confidence: high on the decision; moderate on the cap consequence until measured, gaps: [Retry lifetime of the task's Shadow chat]}
```
