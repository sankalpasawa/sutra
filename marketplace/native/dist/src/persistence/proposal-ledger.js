/**
 * proposal-ledger — durable record of pattern → proposal → decision lifecycle.
 *
 * Required by SPEC v1.2 §4.2 and codex P1 finding "thing missed":
 * the H-Sutra connector replays the JSONL log from byte 0 on daemon start, so
 * without a durable ledger the same pattern would be re-proposed forever after
 * any restart.
 *
 * Storage layout (per-user, NOT shipped with plugin):
 *   $SUTRA_NATIVE_HOME/user-kit/proposals/<pattern_id>.json
 *
 * One JSON file per ProposalEntry; pattern_id is the filename.
 *
 * Status state machine: pending → approved | rejected. Once decided, the
 * entry is preserved (audit trail) but won't be re-proposed.
 */
import { existsSync, mkdirSync, readFileSync, readdirSync, writeFileSync } from 'node:fs';
import { join } from 'node:path';
import { userKitRoot } from './user-kit.js';
const PATTERN_ID_PATTERN = /^P-[0-9a-f]{8}$/;
export function isProposalEntry(value) {
    if (typeof value !== 'object' || value === null)
        return false;
    const v = value;
    return (typeof v.pattern_id === 'string' &&
        PATTERN_ID_PATTERN.test(v.pattern_id) &&
        typeof v.normalized_phrase === 'string' &&
        v.normalized_phrase.length > 0 &&
        typeof v.evidence_count === 'number' &&
        v.evidence_count >= 0 &&
        typeof v.first_seen_ms === 'number' &&
        typeof v.last_seen_ms === 'number' &&
        Array.isArray(v.utterance_samples) &&
        v.utterance_samples.every((s) => typeof s === 'string') &&
        typeof v.proposed_workflow_id === 'string' &&
        typeof v.proposed_trigger_id === 'string' &&
        typeof v.proposed_charter_id === 'string' &&
        typeof v.proposed_domain_id === 'string' &&
        (v.status === 'pending' || v.status === 'approved' || v.status === 'rejected') &&
        typeof v.proposed_at_ms === 'number' &&
        (v.decided_at_ms === null || typeof v.decided_at_ms === 'number') &&
        (v.decision_reason === null || typeof v.decision_reason === 'string'));
}
// ---------------------------------------------------------------------------
// File layout helpers
// ---------------------------------------------------------------------------
function proposalDir(opts = {}) {
    return join(userKitRoot(opts), 'user-kit', 'proposals');
}
function ensureDir(dir) {
    mkdirSync(dir, { recursive: true });
}
function writeJson(path, value) {
    writeFileSync(path, JSON.stringify(value, null, 2) + '\n', { encoding: 'utf8' });
}
function readJson(path) {
    return JSON.parse(readFileSync(path, 'utf8'));
}
// ---------------------------------------------------------------------------
// CRUD
// ---------------------------------------------------------------------------
export function persistProposal(entry, opts = {}) {
    if (!isProposalEntry(entry)) {
        throw new TypeError(`persistProposal: malformed entry (pattern_id=${entry.pattern_id})`);
    }
    const dir = proposalDir(opts);
    ensureDir(dir);
    const path = join(dir, `${entry.pattern_id}.json`);
    writeJson(path, entry);
    return path;
}
export function loadProposal(pattern_id, opts = {}) {
    const path = join(proposalDir(opts), `${pattern_id}.json`);
    if (!existsSync(path))
        return null;
    const raw = readJson(path);
    return isProposalEntry(raw) ? raw : null;
}
export function listProposals(opts = {}, status_filter) {
    const dir = proposalDir(opts);
    if (!existsSync(dir))
        return [];
    const all = readdirSync(dir)
        .filter((f) => f.endsWith('.json'))
        .map((f) => readJson(join(dir, f)))
        .filter(isProposalEntry);
    return status_filter ? all.filter((p) => p.status === status_filter) : all;
}
export function updateProposalStatus(pattern_id, next_status, decision_reason, opts = {}, now_ms = Date.now()) {
    const existing = loadProposal(pattern_id, opts);
    if (!existing) {
        throw new Error(`updateProposalStatus: no proposal found with id "${pattern_id}"`);
    }
    if (existing.status !== 'pending') {
        throw new Error(`updateProposalStatus: cannot transition from "${existing.status}" — proposals are decided once`);
    }
    const updated = {
        ...existing,
        status: next_status,
        decided_at_ms: now_ms,
        decision_reason,
    };
    persistProposal(updated, opts);
    return updated;
}
//# sourceMappingURL=proposal-ledger.js.map