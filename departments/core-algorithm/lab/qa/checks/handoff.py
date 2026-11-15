"""Independent checks of 0.18.0-handoff: S140 and S141. They read the record and the pack files, and import nothing of the lab.

What is read: cases 84 to 87 and the two recorded sequences, handoff_letter (work handed over and checked, with tries) and
handoff_existing (the same need stated with the parts the lab had before). The base's own checks hold every run of both to its
trace and its packs. What they do not know is a hand-off: that a receipt says what its method says, that a next try follows a failed
check and is told of it, that a closing line says `confirmed` only of the checker's own row on the try that was out, and that the
step that needs the work ran only on that row. S140 holds these, as sixteen separate tests (tests() below).

This module keeps its own copy of the rule for a check, written from the version's passage and not taken from the kind's file:
a row is the check of the try that is out when it is on that try's fact, comes from the checker the METHOD names in its pack file,
names that try's receipt under `checks`, reads TRUE or FALSE and is no decision. A walk of the letter sequence is followed look
by look with that rule (follow() below): which try is out, what its checker has said of it, how many slots each provider has left.

S141 shows that every test is needed: each forgery listed is refused by the test it is listed for, and every test has a forgery
that it alone refuses. A forgery here changes the record as it is handed in; some change one field, some re-tell a look whole."""
import json

LETTER, OLD = 'handoff_letter', 'handoff_existing'
CASES = ('84_handed_over', '85_no_step', '86_no_slot_left', '87_next_hand')
IDS = ('S140_the_record_of_a_hand_off_holds_what_the_version_claims', 'S141_each_test_of_the_hand_off_refuses_a_forgery_of_its_own')
KIND, FACT, QUEUE, SCOPE = 'handoff', 'letter_drafted', 'queue-collections-letter@1', 'lendco/collections-letters'
HAND, CHECKER, OFFICER = 'model:letter-drafter', 'checker:loan-book', 'person:collections-officer'
TO_MODEL, TO_OFFICER = 'hand-letter-to-model@1', 'hand-letter-to-officer@1'
TOLD = ('truth', 'source', 'version', 'why')
PLAN_ROWS = ('SELECT', 'BLOCK', 'ADMISSION', 'LOCAL_EFFECT', 'STEP_ALREADY_TRUE', 'STEP_STOPPED')
GATE = ('AUTHORITY_REQUIRED', 'PROVIDER_REQUIRED', 'RESOURCE_REQUIRED')
DONE = 'LOCAL_MODEL_EFFECTS_RECORDED'
DOOR = 'The event door lets in only verified rows that are not decisions, from a checker the header names'
STAMP = 'An answer is TRUE or FALSE, from a named party, to an ask receipt'
LAST = {'tries': 'after_book_changed', 'spent': 'after'}   # the snapshot that stands at the end of each walk
NAMES = ('receipts', 'tries', 'closes', 'needs', 'waits', 'bound', 'door', 'cases', 'chains', 'old_doer', 'old_checker_no', 'old_stamped_yes', 'old_rows', 'old_no_step', 'old_three_asks', 'old_parts')


def looks_of(v, found=None):
    """Every look under a part of the record, in the order it stands: a dict that holds a list under `runs`."""
    found = [] if found is None else found
    if type(v) is dict:
        if type(v.get('runs')) is list:
            found.append(v)
        else:
            for x in v.values():
                looks_of(x, found)
    elif type(v) is list:
        for x in v:
            looks_of(x, found)
    return found


def steps_of(v, found=None):
    """Every step under a walk, in order: a dict of exactly {entry, result}."""
    found = [] if found is None else found
    if type(v) is dict:
        if set(v) == {'entry', 'result'}:
            found.append(v)
        else:
            for x in v.values():
                steps_of(x, found)
    elif type(v) is list:
        for x in v:
            steps_of(x, found)
    return found


def told(row):
    return {k: row[k] for k in TOLD if k in row and (k != 'why' or type(row[k]) is str)}


def is_check(row, tried, methods):
    """This module's copy of the rule: is `row` the check of the try `tried` (a hand-over receipt)?"""
    return (type(row) is dict and row.get('predicate') == tried[KIND]['predicate'] and row.get('source') == methods[tried['method']]['verified_by']
            and row.get('checks') == tried['sha256'] and row.get('final') is not True and row.get('truth') in ('TRUE', 'FALSE'))


def follow(part, methods):
    """One walk, look by look: for every run {'run', 'out', 'said', 'stored', 'handed', 'lines'}. `out` is the hand-over that is out
    when the run is planned, `said` what its checker has said of it by then (this module's rule: the last row let in on the fact,
    when it is the check of that try and the row it rests on has not moved since), `stored` the last row let in on the fact,
    `handed` the hand-overs the run issued, `lines` its closing lines."""
    out, said, stored, rows = None, None, None, []
    for look in looks_of(part):
        row = look.get('event')
        if type(row) is dict:
            if row.get('predicate') == FACT:
                stored, said = row, (row if out is not None and is_check(row, out, methods) else None)
            elif said is not None and any(d.get('predicate') == row.get('predicate') and d.get('version') != row.get('version') for d in said.get('depends_on', [])):
                said = None   # the row the check rested on has moved: the check does not read any more
        for r in look['runs']:
            handed = [x for x in r['model_receipts'] if x.get('action') == KIND]
            lines = [e['data'] for e in r['trace'] if e['operation'] == 'HANDOFF_CLOSED']
            rows.append({'run': r, 'out': out, 'said': said, 'stored': stored, 'handed': handed, 'lines': lines})
            if handed:
                out, said = handed[-1], None
            if lines:
                out, said = None, None
    return rows


def tests(mine, packs, sha, check_chain):
    """The sixteen tests, each on its own: {name: holds}. A test that cannot read what it needs does not hold; when the walks
    themselves cannot be followed, none holds."""
    same = lambda a, b: sha(a) == sha(b)   # compared as JSON: 1 is not true and not 1.0
    try:
        methods = {m['id']: m for p in packs.values() for m in p.get('methods', [])}
        case = {c['id']: c for c in mine['cases']}
        letter, old = mine['scenes'][LETTER], mine['scenes'][OLD]
        walks = {name: follow(part, methods) for name, part in letter.items()}
        every = [x for rows in walks.values() for x in rows]
    except Exception:
        return {name: False for name in NAMES}
    loaded = lambda part: [packs[n] for n in part['packs']] + ([packs[part['next_hand']]] if 'next_hand' in part else [])   # every pack a walk was handed, in order
    status = lambda look: [(r['status'], r['work_state'], r['actions'], len(r['model_receipts'])) for r in look['runs']]
    reads = lambda snap, fact, *want: same([snap[fact].get(k) for k in ('truth', 'source', 'final')], list(want))
    zero = lambda r: type(r['cost']) is dict and all(same(v, 0) for v in r['cost'].values())

    def receipts():   # every hand-over receipt says what its method says in the pack file, and has the shape of one
        found = [x for c in CASES for r in case[c]['run']['runs'] for x in r['model_receipts'] if x.get('action') == KIND] + [x for row in every for x in row['handed']]
        ok = len(found) >= 2
        for x in found:
            m, h = methods[x['method']], x[KIND]
            ok = ok and (m['action'] == KIND and set(x) == {'method', 'scope', 'action', 'status', 'parked', KIND, 'sha256'} and x['parked'] is True and x['status'] == 'LOCAL_ONLY'
                         and set(h) == {'predicate', 'to', 'instruction', 'verified_by', 'try', 'before', 'handed_in'}
                         and same([h['predicate'], h['to'], h['instruction'], h['verified_by']], [m['effect'], m['handoff_to'], m['instruction'], m['verified_by']])
                         and h['to'] != h['verified_by'] and type(h['handed_in']) is str and len(h['handed_in']) == 64)
        return ok

    def tries():   # a first hand-over is try 1 and knows of nothing; a next one follows a failed check of the try before and is told of it
        ok = True
        for rows in walks.values():
            seen = []
            for row in rows:
                for x in row['handed']:
                    h, before = x[KIND], row['out']
                    numbered = type(h['try']) is int and [b.get('try') for b in h['before']] == list(range(1, h['try'])) and all(set(b) == {'try', 'to', 'receipt', 'checked'} for b in h['before'])
                    if before is None:
                        ok = ok and numbered and h['try'] == 1 and h['before'] == []
                    else:
                        failed = row['said'] is not None and row['said']['truth'] == 'FALSE'
                        ok = ok and numbered and failed and h['try'] == before[KIND]['try'] + 1 and same(h['before'], before[KIND]['before'] + [
                            {'try': before[KIND]['try'], 'to': before[KIND]['to'], 'receipt': before['sha256'], 'checked': told(row['said'])}])
                    seen.append(h['handed_in'])
            ok = ok and len(set(seen)) == len(seen) and len(seen) >= 3
        return ok

    def closes():   # a closing line names the try that was out and the row the fact reads from, and says confirmed only of the checker's own TRUE on that try
        found = [(row, line) for row in every for line in row['lines']]
        ok = len(found) == 2
        for row, line in found:
            was, at, ops = row['out'], row['stored'], [e['operation'] for e in row['run']['trace']]
            ok = ok and (was is not None and at is not None and set(line) == {'handoff', 'receipt', 'tries', 'truth', 'source', 'version', 'checks', 'confirmed'}
                         and same([line['handoff'], line['receipt'], line['tries']], [row['run']['scope'] + '|' + was[KIND]['predicate'], was['sha256'], was[KIND]['try']])
                         and same([line['truth'], line['source'], line['version'], line['checks']], [at.get('truth'), at.get('source'), at.get('version'), at.get('checks')])
                         and line['confirmed'] is (row['said'] is not None and row['said']['truth'] == 'TRUE')
                         and ops.index('HANDOFF_CLOSED') > max(i for i, op in enumerate(ops) if op in PLAN_ROWS) and ops[-1] == 'TERMINAL')
        return ok

    def needs():   # the step that needs the work ran only in a look that took the checker's TRUE on the try that was out, and that look closed the hand-off
        facts = {m['effect'] for m in methods.values() if m['action'] == KIND}
        ran = [row for row in every if any(set(methods[x['method']].get('requires', [])) & facts for x in row['run']['model_receipts'])]
        return len(ran) == 2 and all(row['out'] is not None and row['said'] is not None and row['said']['truth'] == 'TRUE' and len(row['lines']) == 1
                                     and row['run']['status'] == DONE for row in ran)

    def waits():   # while a try is out and its check has not failed the look waits and hands nothing over; after a failed check it hands the work over again or the gate turns it down
        ok, n = True, 0
        for row in every:
            r, was = row['run'], row['out']
            if was is None or row['lines']:
                continue
            n += 1
            if row['said'] is None:
                ok = ok and same([r['status'], r['work_state'], r['actions'], r['model_receipts'], r.get('waits')], ['WAITING', 'waiting', [], [], [was['method']]]) and zero(r)
            elif row['handed']:
                ok = ok and len(r['model_receipts']) == 1 and same([r['status'], r['work_state'], r['actions'], r['waits']], ['WAITING', 'waiting', [row['handed'][0]['method']], [row['handed'][0]['method']]])
            else:
                ok = ok and r['work_state'] == 'blocked' and r['status'] in GATE and r['model_receipts'] == [] and r['actions'] == []
        return ok and n == 10

    def bound():   # no hand is handed more tries than the capacity its provider is given in the packs; the books at the end of a walk are the packs' less what the receipts took (no pack of these walks states a level twice)
        ok = True
        for name, part in letter.items():
            rows, capacity, budget = walks[name], {}, {'compute': 10, 'money': 10, 'attention': 3}
            for p in loaded(part):
                capacity.update(p.get('providers', {}))
                budget.update(p.get('budget', {}))
            used = {}
            for row in rows:
                for x in row['run']['model_receipts']:
                    m = methods[x['method']]
                    used[m['provider']] = used.get(m['provider'], 0) + 1
                    for dim, v in m.get('cost', {}).items():
                        budget[dim] -= v
                blocked = row['run']['status'] == 'PROVIDER_REQUIRED'
                spent = row['out'] is not None and used.get(methods[row['out']['method']]['provider'], 0) == capacity[methods[row['out']['method']]['provider']]
                ok = ok and (not blocked or (spent and row['said'] is not None and row['said']['truth'] == 'FALSE'))
            ok = ok and all(n <= capacity[p] for p, n in used.items()) and same(part[LAST[name]]['providers'], {p: capacity[p] - used.get(p, 0) for p in capacity}) and same(part[LAST[name]]['budget'], budget)
        return ok and any(row['run']['status'] == 'PROVIDER_REQUIRED' for row in every)

    def door():   # what the journal's door refused, what a restart found, one row let in is one entry and one look, and the header names the checker of the methods
        t = letter['tries']
        ok = same(t['at_the_door'], {'a_stamp_from_the_hand': STAMP, 'a_stamp_from_the_checker': STAMP, 'the_hands_own_row': DOOR, 'a_decision_under_the_checkers_name': DOOR})
        ok = ok and same(t['restarted'], {'head': t['head_kept'], 'cut': 0, 'notice': [], 'after': t['after_failed_check']}) and same(t['after_second_look'], t['after_handed_over'])
        for part in letter.values():
            entries = [s['entry'] for s in steps_of(part)]
            ok = ok and all(type(n) is int for n in entries) and entries == sorted(set(entries)) and all(len(s['result']['runs']) == 1 for s in steps_of(part)) and len(looks_of(part)) == len(entries)
        named = sorted({m['verified_by'] for n in t['packs'] for m in packs[n].get('methods', []) if m['action'] == KIND})
        return ok and same([t['kinds'], t['checkers']], [['simulate_fact', KIND], named]) and t['head']['length'] == max(s['entry'] for s in steps_of(t)) + 1

    def cases():   # the four cases: handed over and waiting; no step; no slot; the next hand
        r = {c: case[c]['run']['runs'][0] for c in CASES}
        book = lambda c: case[c]['derived_state']['budget_after']
        to = lambda c: [(x['method'], x[KIND]['to'], x[KIND]['try'], x[KIND]['before']) for x in r[c]['model_receipts']]
        return (same([r[c]['status'] for c in CASES], ['WAITING', 'QUERY_EVIDENCE', 'PROVIDER_REQUIRED', 'WAITING'])
                and same([to('84_handed_over'), to('87_next_hand')], [[(TO_MODEL, HAND, 1, [])], [(TO_OFFICER, OFFICER, 1, [])]]) and r['85_no_step']['model_receipts'] == [] and r['86_no_slot_left']['model_receipts'] == []
                and same([r['84_handed_over']['pending'], r['87_next_hand']['pending']], [[QUEUE], [QUEUE]])
                and same([book(c) for c in CASES], [{'compute': 8, 'money': 5, 'attention': 3}, {'compute': 10, 'money': 5, 'attention': 3}, {'compute': 10, 'money': 5, 'attention': 3}, {'compute': 10, 'money': 5, 'attention': 2}])
                and all(SCOPE + '|' + FACT not in case[c]['derived_state']['facts'] for c in CASES))

    asked = lambda part: part['look']['runs'][0]['model_receipts'][-1]
    turned_away = lambda look: same([look['status'], look['runs']], ['DECISION_STANDS', []])

    def old_doer():   # an ask put to the doer: its own answer is a decision, the letter is queued on it, and the checker's FALSE is turned away
        d = old['doer_asked']
        return (asked(d)['ask']['to'] == HAND and status(d['look']) == [('WAITING', 'waiting', [asked(d)['method']], 1)]
                and same([d['doer_says_done']['event'].get(k) for k in ('truth', 'final', 'source')], ['TRUE', True, 'STAMP:' + HAND]) and status(d['doer_says_done']) == [(DONE, 'completed', [QUEUE], 1)]
                and turned_away(d['checker_says_no']) and reads(d['after'], FACT, 'TRUE', 'STAMP:' + HAND, True) and reads(d['after'], 'letter_queued', 'TRUE', 'LOCAL_MODEL:' + QUEUE, None) and same(d['after'], d['after_done']))

    def old_checker_no():   # an ask put to the checker: one no ends it, and a second draft is confirmed by no stamp and by no row
        c = old['checker_asked']
        return (asked(c)['ask']['to'] == CHECKER and same(c['doer_says_done'], {'party': HAND, 'truth': 'TRUE', 'refused': 'The answer does not come from the party that was asked'})
                and status(c['checker_says_no']) == [('REFUSED', 'blocked', [], 0)] and same(c['second_draft_stamp'], {'party': CHECKER, 'truth': 'TRUE', 'refused': 'No open ask matches this receipt'})
                and turned_away(c['second_draft_row']) and status(c['look_again']) == [('REFUSED', 'blocked', [], 0)] and reads(c['after'], FACT, 'FALSE', 'STAMP:' + CHECKER, True)
                and same([c['after']['budget'], c['after']['providers']], [{'compute': 10, 'money': 5, 'attention': 2}, {'local-provider': 4, 'checker-channel': 2}]))

    def old_stamped_yes():   # a stamped yes rests on nothing: the book changes, the letter still counts as drafted and stays queued, and the checker's FALSE is turned away
        y = old['checker_stamps_yes']
        return ('depends_on' not in y['checker_says_yes']['event'] and y['checker_says_yes']['event'].get('final') is True and status(y['checker_says_yes']) == [(DONE, 'completed', [QUEUE], 1)]
                and y['book_changes']['event']['predicate'] == 'loan_on_book' and status(y['book_changes']) == [('SUPPORTED_BY_EVIDENCE', 'completed', [], 0)] and turned_away(y['checker_says_no'])
                and reads(y['after'], FACT, 'TRUE', 'STAMP:' + CHECKER, True) and reads(y['after'], 'letter_queued', 'TRUE', 'LOCAL_MODEL:' + QUEUE, None) and same(y['after'], y['after_yes']) and same(y['after_book'], y['after_yes']))

    def old_rows():   # rows under an ask: every failed check leaves the same question out, hands nothing over, pays nothing; a passing row lets the plan go on and the question stays out
        w = old['checker_rows']
        failed = w['failed_checks']
        return (len(failed) == 3 and all(status(f['check']) == [('WAITING', 'waiting', [], 0)] and f['check']['event']['truth'] == 'FALSE' and f['check']['event'].get('final') is not True
                                         and same(f['check']['runs'][0]['waits'], [asked(w)['method']]) and zero(f['check']['runs'][0])
                                         and same([f['after']['budget'], f['after']['providers'], f['after']['open_asks']], [w['after_look']['budget'], w['after_look']['providers'], w['after_look']['open_asks']]) for f in failed)
                and status(w['passing_check']) == [(DONE, 'completed', [QUEUE], 1)] and reads(w['after'], FACT, 'TRUE', CHECKER, None) and same(w['after']['open_asks'], w['after_look']['open_asks']) and len(w['after']['open_asks']) == 1)

    def old_no_step():   # no step: blocked for want of evidence, then of a method; nobody is handed anything; a passing row alone queues the letter
        n = old['no_step']
        return (not any(m['effect'] == FACT for name in n['packs'] for m in packs[name].get('methods', [])) and status(n['look']) == [('QUERY_EVIDENCE', 'blocked', [], 0)]
                and status(n['failed_check']) == [('METHOD_ABSENT', 'blocked', [], 0)] and status(n['passing_check']) == [(DONE, 'completed', [QUEUE], 1)]
                and same([n['after']['budget'], n['after']['providers'], n['after']['open_asks']], [{'compute': 9, 'money': 5, 'attention': 3}, {'local-provider': 3}, {}]))

    def old_three_asks():   # three asks under one rule: a later receipt holds its pack's words only; three noes refuse the goal; a yes cannot complete
        t = old['three_asks']
        later = [t['no_to_try_1']['runs'][0]['model_receipts'][-1], t['no_to_try_2']['runs'][0]['model_receipts'][-1]]
        stop = t['yes']['yes_to_try_2']['runs'][0]
        return (all(sorted(x['ask']) == ['asked_in', 'predicate', 'question', 'to'] and x['ask']['question'] == methods[x['method']]['question'] and x['ask']['to'] == CHECKER for x in later)
                and [status(t[k])[0][0] for k in ('look', 'no_to_try_1', 'no_to_try_2', 'no_to_try_3')] == ['WAITING', 'WAITING', 'WAITING', 'REFUSED']
                and len({asked(t)['method'], later[0]['method'], later[1]['method']}) == 3
                and same([stop['status'], stop['stopped']], ['STEP_STOPPED', {'method': QUEUE, 'reason': 'Prerequisite not true before effect: ' + FACT}])
                and same([t['yes']['draft_2_passes'].get(k) for k in ('truth', 'final')], ['TRUE', True]) and t['yes']['after']['letter_queued']['truth'] == 'UNKNOWN')

    def old_parts():   # the attempt uses no part of this version: no method of its packs and no receipt of its runs is of the new kind, and no line of the kind stands in it
        names = sorted({n for part in old.values() for n in part['packs']})
        runs = [r for look in looks_of(old) for r in look['runs']]
        return (len(runs) == 23 and all(m['action'] in ('ask', 'simulate_fact') for n in names for m in packs[n].get('methods', []))
                and all(x['action'] in ('ask', 'simulate_fact') for r in runs for x in r['model_receipts']) and not any(e['operation'].startswith('HANDOFF') for r in runs for e in r['trace'])
                and all([p['pack'] for p in r['provenance']] == part['packs'] for part in old.values() for look in looks_of(part) for r in look['runs']))

    def chains():   # every run of both sequences is a whole chain that ends on its root
        runs = [r for seq in (letter, old) for look in looks_of(seq) for r in look['runs']]
        return len(runs) == 39 and all(check_chain(r['trace']) is True and r['trace_root_sha256'] == r['trace'][-1]['sha256'] for r in runs)

    each = (receipts, tries, closes, needs, waits, bound, door, cases, chains, old_doer, old_checker_no, old_stamped_yes, old_rows, old_no_step, old_three_asks, old_parts)   # in the order of NAMES
    got = {}
    for name, test in zip(NAMES, each):
        try:
            got[name] = test() is True
        except Exception:
            got[name] = False
    return got


def run_of(step):
    return step['result']['runs'][0]


def retold(r, sha, change):
    """What a forger can do without any secret: change a run, hash its receipts and its chain again, and name the new root."""
    change(r)
    prev = 'GENESIS'
    for x in r['model_receipts']:
        x['sha256'] = sha({k: v for k, v in x.items() if k != 'sha256'})
    for n, e in enumerate(r['trace']):
        if e['operation'] == 'LOCAL_EFFECT':
            e['data']['receipt'] = json.loads(json.dumps([x for x in r['model_receipts'] if x['method'] == e['data']['receipt']['method']][0]))
        e.update(seq=n + 1, prev_sha256=prev)
        e['sha256'] = prev = sha({k: v for k, v in e.items() if k != 'sha256'})
    r['trace_root_sha256'] = prev


def line_of(r):
    return [e['data'] for e in r['trace'] if e['operation'] == 'HANDOFF_CLOSED'][0]


T = lambda m: m['scenes'][LETTER]['tries']
P = lambda m: m['scenes'][LETTER]['spent']
O = lambda m, part: m['scenes'][OLD][part]
C = lambda m, cid: [c for c in m['cases'] if c['id'] == cid][0]


def unconfirmed(m, p, sha):   # the passing check re-told as a row that names no receipt, with the line made to match: the letter was queued all the same
    look = T(m)['passing_check'][0]['result']
    look['event']['checks'] = None
    retold(look['runs'][0], sha, lambda r: line_of(r).update(checks=None, confirmed=False))


def by_the_hand(m, p, sha):   # the passing check re-told as the hand's own row, with the line made to match (source the hand, not confirmed)
    look = P(m)['passing_check'][0]['result']
    look['event']['source'] = HAND
    retold(look['runs'][0], sha, lambda r: line_of(r).update(source=HAND, confirmed=False))


def queued_while_waiting(m, p, sha):   # the look after the restart re-told as the look that queued the letter
    r = run_of(T(m)['look_after_restart'])
    done = json.loads(json.dumps(run_of(T(m)['passing_check'][0])))
    r.update({k: done[k] for k in ('status', 'work_state', 'actions', 'model_receipts', 'cost', 'trace', 'trace_root_sha256')})
    r.pop('waits', None)
    r.pop('pending', None)
    retold(r, sha, lambda x: x['trace'].pop([e['operation'] for e in x['trace']].index('HANDOFF_CLOSED')))


# (the test that must refuse it, the forgery). A forgery gets a copy of what the tests read of the record, a copy of the packs, and sha.
FORGERIES = [
    ('receipts', lambda m, p, sha: run_of(P(m)['officer'])['model_receipts'][0][KIND].update(verified_by=OFFICER)),          # the last hand-over said to be checked by the hand itself
    ('receipts', lambda m, p, sha: run_of(P(m)['officer'])['model_receipts'][0][KIND].update(instruction='Sign the letter.')),
    ('receipts', lambda m, p, sha: run_of(P(m)['officer'])['model_receipts'][0].update(parked=False)),
    ('receipts', lambda m, p, sha: p['214_hand_to_officer']['methods'][0].update(verified_by=OFFICER)),                       # the pack says the officer checks the officer; the receipt still names the checker
    ('tries', lambda m, p, sha: run_of(T(m)['book_changed'][0])['model_receipts'][0][KIND].update({'try': 2})),               # a new hand-over said to be a second try
    ('tries', lambda m, p, sha: run_of(P(m)['officer'])['model_receipts'][0][KIND]['before'][2]['checked'].update(why='the letter was fine')),   # what the officer is told of the third check
    ('tries', lambda m, p, sha: run_of(P(m)['officer'])['model_receipts'][0][KIND]['before'].pop(0)),                         # a try left out of what the next hand is told
    ('tries', lambda m, p, sha: T(m)['failed_check'][0]['result']['event'].update(truth='UNKNOWN')),                          # a second try handed over although the check of the first did not fail
    ('tries', lambda m, p, sha: P(m)['wrong_letters'][0]['check'][0]['result']['event'].update(source=HAND)),                 # a second try handed over on the hand's own FALSE
    ('closes', lambda m, p, sha: retold(run_of(T(m)['passing_check'][0]), sha, lambda r: line_of(r).update(confirmed=False))),
    ('closes', lambda m, p, sha: retold(run_of(P(m)['passing_check'][0]), sha, lambda r: line_of(r).update(tries=1))),
    ('closes', lambda m, p, sha: retold(run_of(T(m)['passing_check'][0]), sha, lambda r: line_of(r).update(receipt=run_of(T(m)['handed_over'][0])['model_receipts'][0]['sha256']))),   # closed under the receipt of the first try
    ('closes', lambda m, p, sha: retold(run_of(P(m)['passing_check'][0]), sha, lambda r: line_of(r).update(source=HAND))),    # the line says the hand's row closed it; the row let in is the checker's
    ('closes', lambda m, p, sha: retold(run_of(T(m)['passing_check'][0]), sha, lambda r: line_of(r).update(note='checked twice'))),
    ('needs', unconfirmed),
    ('needs', by_the_hand),
    ('needs', queued_while_waiting),
    ('waits', lambda m, p, sha: run_of(T(m)['second_look']).update(status='PLAN_READY', work_state='ready')),
    ('waits', lambda m, p, sha: run_of(T(m)['late_copy'][0]).update(waits=[TO_OFFICER])),
    ('waits', lambda m, p, sha: run_of(P(m)['dry_look']).update(status='WAITING', work_state='waiting')),                     # no slot is left and the look is said to wait
    ('waits', lambda m, p, sha: run_of(T(m)['look_after_restart']).update(cost={'compute': 2, 'money': 0, 'attention': 0})),  # a look that waits said to have cost a try
    ('bound', lambda m, p, sha: T(m)['after_book_changed']['providers'].update({'letter-model': 1})),
    ('bound', lambda m, p, sha: P(m)['after']['budget'].update(compute=5)),
    ('bound', lambda m, p, sha: p['211_hand_to_model']['providers'].update({'letter-model': 2})),                             # the pack states two tries; the record holds three hand-overs to the model
    ('door', lambda m, p, sha: T(m)['at_the_door'].update(the_hands_own_row=None)),                                           # the hand's own row said to be let in
    ('door', lambda m, p, sha: T(m)['at_the_door'].update(a_stamp_from_the_hand=None)),
    ('door', lambda m, p, sha: T(m)['restarted'].update(cut=1)),
    ('door', lambda m, p, sha: T(m).update(checkers=[CHECKER, HAND])),                                                        # a header that names the hand among its checkers
    ('door', lambda m, p, sha: P(m)['officer'].update(entry=3)),
    ('cases', lambda m, p, sha: C(m, '86_no_slot_left')['derived_state']['budget_after'].update(compute=8)),
    ('cases', lambda m, p, sha: C(m, '84_handed_over')['derived_state']['facts'].update({SCOPE + '|' + FACT: {'predicate': FACT, 'truth': 'TRUE', 'verified': True, 'source': HAND, 'scope': SCOPE}})),   # the hand-over said to have written the letter's row
    ('cases', lambda m, p, sha: C(m, '87_next_hand')['run']['runs'][0]['model_receipts'][0][KIND].update({'try': 4})),
    ('chains', lambda m, p, sha: run_of(T(m)['second_look'])['trace'][0]['data'].update(scope='lendco/other')),              # a row changed and not hashed again
    ('chains', lambda m, p, sha: O(m, 'no_step')['look']['runs'][0].update(trace_root_sha256='0' * 64)),
    ('old_doer', lambda m, p, sha: O(m, 'doer_asked')['checker_says_no'].update(status='RECONCILED')),
    ('old_doer', lambda m, p, sha: [O(m, 'doer_asked')[k]['letter_drafted'].update(source=CHECKER, final=None) for k in ('after', 'after_done')]),   # the letter said to stand on the checker's row
    ('old_checker_no', lambda m, p, sha: O(m, 'checker_asked')['second_draft_stamp'].update(refused=None)),
    ('old_checker_no', lambda m, p, sha: O(m, 'checker_asked')['look_again']['runs'][0].update(status='WAITING', work_state='waiting')),
    ('old_stamped_yes', lambda m, p, sha: O(m, 'checker_stamps_yes')['checker_says_no'].update(status='RECONCILED')),
    ('old_stamped_yes', lambda m, p, sha: O(m, 'checker_stamps_yes')['after']['letter_queued'].update(truth='UNKNOWN')),
    ('old_rows', lambda m, p, sha: O(m, 'checker_rows')['failed_checks'][1]['after']['budget'].update(attention=1)),          # a failed check said to have been paid
    ('old_rows', lambda m, p, sha: O(m, 'checker_rows')['after']['open_asks'].clear()),                                       # the question said to be closed by the passing row
    ('old_no_step', lambda m, p, sha: O(m, 'no_step')['look']['runs'][0].update(status='WAITING', work_state='waiting')),
    ('old_no_step', lambda m, p, sha: O(m, 'no_step')['after']['providers'].update({'letter-model': 2})),
    ('old_three_asks', lambda m, p, sha: O(m, 'three_asks')['no_to_try_1']['runs'][0]['model_receipts'][-1]['ask'].update(before=[{'try': 1, 'why': 'wrong amount'}])),   # the second ask said to know of the first
    ('old_three_asks', lambda m, p, sha: O(m, 'three_asks')['yes']['yes_to_try_2']['runs'][0].update(status=DONE)),
    ('old_parts', lambda m, p, sha: O(m, 'checker_rows')['look']['runs'][0]['model_receipts'][0].update(action=KIND)),
    ('old_parts', lambda m, p, sha: p['216_ask_the_checker']['methods'][0].update(action=KIND)),
]


def checks(data, ROOT, sha, check_chain):
    try:
        mine = {'cases': [c for c in data['cases'] if c['id'] in CASES], 'scenes': {n: data['scenes'][n] for n in (LETTER, OLD)}}
        packs = {f.stem: json.loads(f.read_text()) for f in sorted((ROOT / 'scenarios').glob('21*.json'))}
        got = tests(mine, packs, sha, check_chain)
    except Exception as e:
        return [(cid, False, 'the cases, the two sequences or the pack files of the hand-off cannot be read: ' + type(e).__name__) for cid in IDS]

    def refused_by(change):   # the tests that refuse one forgery; None when the forgery cannot be made
        m, p = json.loads(json.dumps(mine)), json.loads(json.dumps(packs))
        try:
            change(m, p, sha)
        except Exception:
            return None
        return sorted(name for name, ok in tests(m, p, sha, check_chain).items() if not ok)
    seen = [refused_by(change) for _, change in FORGERIES]
    wrong = {i: by for i, ((target, _), by) in enumerate(zip(FORGERIES, seen)) if by is None or target not in by}   # accepted, or not made, or refused by other tests only
    alone = {target for (target, _), by in zip(FORGERIES, seen) if by == [target]}
    bare = sorted(set(got) - alone)                                                                                   # a test without a forgery that it alone refuses
    return [(IDS[0], all(got.values()), ' '.join(sorted(name for name, ok in got.items() if not ok))),
            (IDS[1], all(got.values()) and not wrong and not bare, str({'not refused by its own test': wrong, 'tests without a forgery of their own': bare}) if wrong or bare else '')]
