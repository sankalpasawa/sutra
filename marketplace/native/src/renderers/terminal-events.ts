/**
 * terminal-events — minimal renderer mapping EngineEvent → ASCII line.
 *
 * Used by the CLI's `run` subcommand so founders can see workflow execution
 * happen in real time. Each event becomes one line of stdout. No colors, no
 * unicode box-drawing — keeps it readable in any terminal + log file.
 */

import type { EngineEvent } from '../types/engine-event.js'

export function formatEvent(e: EngineEvent): string {
  switch (e.type) {
    case 'workflow_started':
      return `[workflow_started]   ${e.workflow_id}  exec=${e.execution_id}`
    case 'workflow_completed':
      return `[workflow_completed] ${e.workflow_id}  exec=${e.execution_id}  duration=${e.duration_ms}ms`
    case 'workflow_failed':
      return `[workflow_failed]    ${e.workflow_id}  exec=${e.execution_id}  reason=${e.reason}`
    case 'step_started':
      return `[step_started]       ${e.workflow_id}  step ${e.step_index}/${e.step_count}  id=${e.step_id}`
    case 'step_completed':
      return `[step_completed]     ${e.workflow_id}  step ${e.step_index}/${e.step_count}  id=${e.step_id}  duration=${e.duration_ms}ms`
    case 'routing_decision':
      return `[routing_decision]   mode=${e.mode}  workflow=${e.workflow_id ?? 'none'}  trigger=${e.trigger_id ?? 'none'}`
    case 'policy_decision':
      return `[policy_decision]    rule=${e.rule_id}  verdict=${e.verdict}${e.reason ? '  reason=' + e.reason : ''}`
    case 'artifact_registered':
      return `[artifact_registered] domain=${e.domain_id}  kind=${e.asset_kind}  sha=${e.content_sha256.slice(0, 12)}`
    case 'pattern_proposed':
      return `[pattern_proposed]   ${e.pattern_id}  evidence=${e.evidence_count}  phrase="${e.normalized_phrase}"  workflow=${e.proposed_workflow_id}`
    case 'proposal_approved':
      return `[proposal_approved]  ${e.pattern_id}  workflow=${e.registered_workflow_id}  trigger=${e.registered_trigger_id}`
    case 'proposal_rejected':
      return `[proposal_rejected]  ${e.pattern_id}  reason=${e.reason}`
    case 'approval_requested':
      return `[approval_requested] ${e.workflow_id}  exec=${e.execution_id}  step=${e.step_index}  prompt="${e.prompt_summary}"  Type "approve ${e.execution_id}" to resume or "reject ${e.execution_id} <reason>" to terminate.`
    case 'approval_granted':
      return `[approval_granted]   ${e.workflow_id}  exec=${e.execution_id}  step=${e.step_index}  resuming...`
    case 'approval_denied':
      return `[approval_denied]    ${e.workflow_id}  exec=${e.execution_id}  step=${e.step_index}  reason=${e.reason}`
    case 'approval_already_handled':
      return `[approval_already_handled] ${e.workflow_id}  exec=${e.execution_id}  step=${e.step_index}  originally_decided_at=${e.originally_decided_at_ms}`
    case 'workflow_rollback_started':
      return `[workflow_rollback_started] ${e.workflow_id}  exec=${e.execution_id}  reason=${e.reason}`
    case 'step_compensated':
      return `[step_compensated]   ${e.workflow_id}  exec=${e.execution_id}  step=${e.step_index}  duration=${e.duration_ms}ms`
    case 'step_compensation_failed':
      return `[step_compensation_failed] ${e.workflow_id}  exec=${e.execution_id}  step=${e.step_index}  reason=${e.reason}`
    case 'workflow_rollback_complete':
      return `[workflow_rollback_complete] ${e.workflow_id}  exec=${e.execution_id}  steps_compensated=${e.steps_compensated}`
    case 'workflow_rollback_partial':
      return `[workflow_rollback_partial] ${e.workflow_id}  exec=${e.execution_id}  steps_compensated=${e.steps_compensated}  steps_failed=${e.steps_failed}`
    case 'workflow_escalated':
      return `[workflow_escalated] ${e.workflow_id}  exec=${e.execution_id}  reason=${e.reason}`
    case 'step_paused':
      return `[step_paused]        ${e.workflow_id}  exec=${e.execution_id}  step=${e.step_index}  reason=${e.reason}  Call resumeFromPause("${e.execution_id}") to continue.`
    default: {
      const exhaustive: never = e
      return `[unknown_event] ${JSON.stringify(exhaustive)}`
    }
  }
}
