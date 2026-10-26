"""layers/audit/v1.py -- Audit, version 1: the implementation behind the interface's audit entries (PRD A1.18).

Its recipe is v1.json beside it: the Audit engine object. It starts on a checked version of the department's
deliverable ('$deliverable', whatever the kind), picks what to check, checks the record mechanically, reads each
done-when item (audit.items, in the S-30 shape), judges the pages against the brief, and files a reading.

Every code, prompt, draft and check name the recipe uses is provided here by reference (ref_to): the bodies stay in
engine_runtime's Audit region until they move, and a name the layer changes is copied into this module and changed here
(PRD A1.19). It holds its words (WORDS and LAYOUT, which layers/prompts.py compiles), so no part of it is read from
the .md bundle. view() is today's pane, by reference, with the readings of readings.jsonl added.
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
# Audit's words, by the split rule of A1.16 from function-prompts/audit/*.md (python -m layers.prompts --extract audit);
# judge.items is the part this layer added (A1-ITEMS), written in the bundle as the others are. The bundle is the
# fallback every department's own whole-file copy (M2.2) reads, and W3-PROOF deletes it.
WORDS = {
    'goal': {
        'does': {
            'text': 'drops in on what went live and checks claims against the record',
        },
        'skills': {
            'items': [
                'pick what to check',
                'check the record mechanically',
                'judge a page against the brief',
            ],
        },
    },
    'judge': {
        'judge': {
            'task': (
                'Check what the department made against what it was asked. Read the brief and what the '
                "department's own engines filed, then the pages. Find any statement of fact on a page that neither "
                'the brief nor a filed artifact gives: a phone number, an address, a date, a count, a name, a '
                'claim of history. A fact a filed artifact gives, with its source, is backed: do not report it.'
            ),
            'guidance': 'high: a reader could be harmed or misled by it. At most eight findings.',
        },
        'items': {
            'task': (
                'Read the work against what was asked, one done-when item at a time. For each item below give a '
                'verdict: met only when the work itself shows it; not met when the work leaves it out or shows it '
                'does not hold; to confirm when it rests on a fact only the owner can give, or the work cannot '
                'show it either way. Say in one line what is or is not true (the claim) and in one line what in '
                'the work shows it (the evidence). What code measured is given below: weigh it, and never call an '
                'item met that a measure shows failing.'
            ),
            'guidance': (
                'One row for every item, each under its own id, and no other row. A finding is something to put '
                'right that you saw while reading: say where it is and what is wrong, and name the item it belongs '
                'to, or null. high: a reader could be harmed or misled by it. Never guess a fact that neither the '
                'brief nor a filed artifact gives: a phone number, an address, a date, a count, a name. A fact a '
                'filed artifact gives, with its source, is backed: do not report it. At most eight findings.'
            ),
        },
    },
}
LAYOUT = {
    'goal': {
        'does': '{text}',
        'skills': '{items}',
    },
    'judge': {
        'judge': (
            '{task} {returns} {guidance}\n'
            '\n'
            'THE BRIEF:\n'
            '{{brief}}{{filed}}\n'
            '\n'
            'THE PAGES:\n'
            '{{pages}}'
        ),
        'items': (
            '{task}\n'
            '{returns}\n'
            '{guidance}\n'
            '\n'
            'THE BRIEF:\n'
            '{{brief}}{{filed}}\n'
            '\n'
            'THE DELIVERABLE:\n'
            '{{deliverable}}\n'
            '\n'
            'THE DONE-WHEN ITEMS:\n'
            '{{items}}\n'
            '\n'
            'WHAT CODE MEASURED:\n'
            '{{measured}}'
        ),
    },
}


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
