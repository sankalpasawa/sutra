"""The chat agent (orchestrator 5.2, 5.3): staged structured calls, code template lines, the turn runner.

    ports      ConnectorPort, ConnectorFailure, the constants of a request
    replies    ChatDecision, AssignmentDraft, AssignmentPlan (family `chat_turn`)
    prompts    the four templates in `templates/` and their loader
    planner    keyword fallback, status report, the code template lines
    agent      ChatAgent: stages A (decide), B (change), C (assign), with retries
    runner     TurnRunner: the queue, the turn T0 to T9, approvals

The model's output is structure only: no sentence of it is ever shown in the org chat.
"""
