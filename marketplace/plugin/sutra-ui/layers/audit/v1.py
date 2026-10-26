"""layers/audit/v1.py -- Audit, version 1: the implementation behind the interface's audit entries (PRD A1.18).

Its recipe is v1.json beside it: the Audit engine object. It starts on a checked version of the department's
deliverable ('$deliverable', whatever the kind), picks what to check, checks the record mechanically, reads each
done-when item (audit.items, in the S-30 shape), judges the pages against the brief, and files a reading.

Every code, prompt, draft and check name the recipe uses is provided here by reference (ref_to): the bodies stay in
engine_runtime's Audit region until they move, and a name the layer changes is copied into this module and changed here
(PRD A1.19). WORDS and LAYOUT are empty, so its prompts are still read from the .md bundle. view() is today's pane, by
reference, with the readings of readings.jsonl added.
"""
from layers import R, W, J, S, FV, ref_to  # noqa: F401 -- lazy proxies: tests reload engine_runtime, so never a module object

LAYER = 'audit'
VERSION = 1
IMPLEMENTS = 1
RECIPE = 'v1.json'
CODE = {
    'audit_pick': ref_to('audit_pick'),
    'audit_mechanical': ref_to('audit_mechanical'),
    'audit_file': ref_to('audit_file'),
}
PROMPT = {
    'audit_judge': ref_to('p_audit_judge'),
    'audit_items': ref_to('p_audit_items'),
}
DRAFT = {
    'audit_judge_draft': ref_to('d_audit_judge'),
    'audit_items_draft': ref_to('d_audit_items'),
}
CHECK = {
    'picked_a_sample': ref_to('c_picked_a_sample'),
    'has_a_verdict': ref_to('c_has_a_verdict'),
    'findings_name_where_and_what': ref_to('c_findings_name_where_and_what'),
    'said_what_it_did': ref_to('c_said_what_it_did'),
    'reading_is_s30': ref_to('c_reading_is_s30'),
}
WORDS, LAYOUT = {}, {}


def _summary(r, verdicts):
    """What a reading says, in the owner's words: names (D2), never counts."""
    where = '%s v%s' % (r.get('artifact'), r.get('v'))
    if not r.get('read'):
        return 'did not read %s: %s' % (where, r.get('why_not_read') or 'it was not read')
    left = ['%s %s' % (i, 'not met' if v == 'not_met' else 'to confirm') for i, v in verdicts.items() if v != 'met']
    return 'read %s: %s' % (where, ', '.join(left) if left else 'every done-when item holds')


def _entry(r):
    """One reading of the journal as the pane lists it: when, what it says, and the verdict of each done-when item."""
    verdicts = R.audit_verdicts(r.get('items'))
    return {'summary': _summary(r, verdicts), 'at': r.get('at'), 'artifact': r.get('artifact'), 'v': r.get('v'),
            'read': bool(r.get('read')), 'why_not_read': r.get('why_not_read'), 'verdicts': verdicts}


def _latest(rows):
    """The newest reading that read its version: one entry for each done-when item, the row whose verdict stands (when code
    and the reader disagreed, both rows are in the journal and the worse stands); None when no version has been read."""
    r = next((x for x in reversed(rows) if x.get('read')), None)
    if r is None:
        return None
    verdicts, seen, items = R.audit_verdicts(r.get('items')), set(), []
    for row in r.get('items') or []:
        if row['id'] in seen or row['verdict'] != verdicts.get(row['id']):
            continue
        seen.add(row['id'])
        items.append({k: row[k] for k in ('id', 'verdict', 'method', 'evidence', 'claim')})
    return {'artifact': r['artifact'], 'v': r['v'], 'at': r.get('at'), 'items': items}


def view(ref, d, events, asks):
    """Audit's pane (S.VIEWS['audit']): today's part, by reference, with the readings of readings.jsonl in place of the
    ledger's lines once any exists, each with its artifact, version, whether it was read and the verdict of each item, and
    `latest`: the newest version read, item by item (M8.3)."""
    part = dict(FV._j2_part(ref, d, 'Audit', events, asks))
    rows = W.rows(ref, 'readings.jsonl')
    if rows:
        part['readings'] = [_entry(r) for r in rows[-6:]]
    part['latest'] = _latest(rows)
    return FV._clean(part)
