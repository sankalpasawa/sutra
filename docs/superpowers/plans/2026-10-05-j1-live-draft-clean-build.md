# J1 live-draft clean build

Implement the frozen contract in `contracts/2026-10-05-j1-contract.md` by
extending Root's existing Setup engine. Persist the conversation in Request
versions, add a converse step before shape, preserve rule-driven approval,
create through `founding.spawn`, and expose the durable result in Root's chat.

Execution order:

1. Encode contract tests.
2. Persist the Request conversation and outstanding question.
3. Add Setup converse and shape behavior.
4. Replace the unconditional birth stamp with a matching-rule gate.
5. Make creation and handoff idempotent with checkpoints.
6. Render the Root question, final tell, and child once.
7. Run focused Python, Node, connection, and release checks.

Rollback is controlled by `J1_FLOW_V1`; readers continue to accept legacy
records. In-flight founding checkpoints are reconciled or quarantined, never
deleted.
