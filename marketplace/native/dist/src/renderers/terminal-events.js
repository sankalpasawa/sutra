/**
 * terminal-events — minimal renderer mapping EngineEvent → ASCII line.
 *
 * Used by the CLI's `run` subcommand so founders can see workflow execution
 * happen in real time. Each event becomes one line of stdout. No colors, no
 * unicode box-drawing — keeps it readable in any terminal + log file.
 */
export function formatEvent(e) {
    switch (e.type) {
        case 'workflow_started':
            return `[workflow_started]   ${e.workflow_id}  exec=${e.execution_id}`;
        case 'workflow_completed':
            return `[workflow_completed] ${e.workflow_id}  exec=${e.execution_id}  duration=${e.duration_ms}ms`;
        case 'workflow_failed':
            return `[workflow_failed]    ${e.workflow_id}  exec=${e.execution_id}  reason=${e.reason}`;
        case 'step_started':
            return `[step_started]       ${e.workflow_id}  step ${e.step_index}/${e.step_count}  id=${e.step_id}`;
        case 'step_completed':
            return `[step_completed]     ${e.workflow_id}  step ${e.step_index}/${e.step_count}  id=${e.step_id}  duration=${e.duration_ms}ms`;
        case 'routing_decision':
            return `[routing_decision]   mode=${e.mode}  workflow=${e.workflow_id ?? 'none'}  trigger=${e.trigger_id ?? 'none'}`;
        case 'policy_decision':
            return `[policy_decision]    rule=${e.rule_id}  verdict=${e.verdict}${e.reason ? '  reason=' + e.reason : ''}`;
        case 'artifact_registered':
            return `[artifact_registered] domain=${e.domain_id}  kind=${e.asset_kind}  sha=${e.content_sha256.slice(0, 12)}`;
        default: {
            const exhaustive = e;
            return `[unknown_event] ${JSON.stringify(exhaustive)}`;
        }
    }
}
//# sourceMappingURL=terminal-events.js.map