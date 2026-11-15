"""Independent checks for the journal version (matrix gap 1, rows R07 and R11): the recorded sequences journal_restart,
journal_refusals and journal_chain, and case 60. Reads the record and the pack files only; never imports the lab's code.

Everything here is computed again, with json and the verifier's own hash alone, out of the journal texts the record
keeps: the chain and the head of every text and that nothing stands after it, the closed keys of every entry, the
budget and the provider slots after every entry (from the journal's own packs and receipts), what the doors let in
(an event row against the checkers its header names, an answer against the question that was out and the party that
was asked, a step that ran against the `execute` of its entry), the ledger rows and the counts, that a pack id enters
once, that a journal which another one continues ends on the entry that names it, and for every refusal on record
that the thing refused is wrong in the way its words say.

Held to the kernel's recorded run, not computed: the brief of every look, event and answer entry. Every such entry
of every kept journal has its recorded run, and the brief is that run.

S90 to S98 hold the claims C1 to C9 of the version's passage, each as separate tests (parts() below); a failed check
names the tests that failed. S99 shows that every test refuses a forgery of its own: each forged record listed in
FORGERIES is refused by the test it is listed for, and no test is without one.

One thing cannot be computed without the kernel: the State digest of an entry after a look. That half belongs to
replay, and the unit tests hold it. S96 computes the digest of every header and of the pack entries before the first
look, which shows what the digest is made of. Not held here: a record forged as a whole, journals and runs together;
what a kernel run carries beyond what its entry keeps of it (the verifier's own check of every run, S42, holds a run
to its trace)."""
import json

START = {'compute': 10, 'money': 10, 'attention': 3}      # what a new State has: this budget, this preference, this scope, no provider slots
PREFERENCE = ['compute', 'money', 'attention']
SCOPE = 'orgA/fulfillment'
QUESTION = 'orgA/fulfillment|customer_approved'
SHIP = 'ship-replacement@1'
MARKS = chr(0x2028) + chr(0x2029) + chr(0x85)             # the three line marks in the question of pack 141 (U+2028, U+2029, U+0085), written so that this file holds no character that cannot be seen
COVERED = ('seq', 'prev_sha256', 'kind', 'body', 'result')                    # what an entry's hash covers
BODY = {'pack': ['pack'], 'event': ['execute', 'row'], 'look': ['execute'], 'answer': ['execute', 'receipt', 'source', 'truth'], 'close': ['next']}
PLAN_END = ('BLOCK', 'SELECT', 'ADMISSION', 'LOCAL_EFFECT', 'STEP_ALREADY_TRUE', 'STEP_STOPPED')
EVENT_DOOR = 'The event door lets in only verified rows that are not decisions, from a checker the header names'
ONCE = 'A hand-over passes the door once: a pack with the id {} was already let in'
MOVED = 'The journal moved on since this run was replayed (its head names {} entries now): replay it and try again'
OUTSIDE = 'The State was changed outside the journal after entry {}'
NO_ASK = 'No open ask matches this receipt'
NOT_THE_PARTY = 'The answer does not come from the party that was asked'
EXECUTE = 'execute is true or false'
EXACTLY = 'The {} door takes exactly: {}'
NAMES = 'A closing entry names the journal that continues this one: its kinds and checkers (lists of names) and, if it has one, its name'
SAME_KINDS = 'A journal that continues another names the same action kinds'
CLOSED = 'This run takes no more entries (its journal is closed and goes on in the journal its last entry names)'
NAMES_ANOTHER = 'The journal is closed and names another journal as the one that continues it'
NOT_CLOSED = 'A journal continues one that is closed: the journal handed in before it does not end on a closing entry'
WITHOUT = 'This journal continues another one: hand that journal in first, replayed to the head this header cites'
DEEP = '[' * 1000 + ']' * 1000                            # a line that nests a thousand deep: no entry does, and no reader takes it apart
WHATS = ['cut short', 'an entry changed', 'an entry dropped', 'an entry dropped and the head moved back to match', 'an entry doubled', 'two entries swapped',
         'a head that names another hash', 'no head', 're-chained by a forger', 'an entry that nests a thousand deep']   # the ways the kept text is tampered with in journal_refusals, in order
DOORS = [('look', EXECUTE), ('look', EXECUTE), ('look', EXACTLY.format('look', 'execute')), ('look', EXACTLY.format('look', 'execute')), ('pack', ONCE.format('"80_ask_method"')),
         ('event', EVENT_DOOR), ('event', EVENT_DOOR), ('event', EVENT_DOOR), ('event', EXACTLY.format('event', 'execute, row')), ('answer', NO_ASK), ('answer', NOT_THE_PARTY),
         ('answer', EXECUTE), ('answer', EXACTLY.format('answer', 'execute, receipt, source, truth')), ('resume', 'Unknown journal entry kind: resume'),
         ('header', 'A journal has one header, entry 0'), ('close', EXACTLY.format('close', 'next')), ('close', SAME_KINDS)]   # the bodies tried at the doors in journal_refusals, in order: the kind and the words
IDS = ('S90_a_journal_is_whole_in_order_and_ends_on_its_head_or_it_is_refused',            # claim C1 of the README passage, and so on to C9
       'S91_the_same_journal_gives_the_same_answer_and_the_packs_alone_do_not',
       'S92_a_no_and_a_finished_step_survive_a_restart',
       'S93_the_books_are_computed_again_and_every_brief_is_the_kernels_recorded_run',
       'S94_of_two_writers_from_one_head_the_second_save_is_refused',
       'S95_the_doors_take_a_pack_id_once_and_refuse_what_is_not_theirs',
       'S96_a_head_covers_no_file_hash_and_the_digest_is_of_named_views',
       'S97_continuing_a_journal_is_a_write_to_it_and_the_new_header_cites_that_head',
       'S98_ledger_rows_and_counts_are_read_from_the_text_alone')
FORGED = 'S99_every_test_of_the_journal_claims_fails_on_forged_records_of_its_own'


def dumps(v):
    return json.dumps(v, sort_keys=True, ensure_ascii=False, separators=(',', ':'))


def text_of(lines):
    return ''.join(line + '\n' for line in lines)


def read(text, head, sha):
    """('ok', entries), or why a text cannot be read up to a head: ('no head', None), ('short', lines), ('broken', n),
    ('other hash', None). The lines are cut at line feeds only; a line is an entry when it is the canonical text of
    what it holds, is numbered in order, is hashed over the one before and does not follow a closing entry."""
    if type(head) is not dict or sorted(head) != ['length', 'sha256'] or type(head['length']) is not int or head['length'] < 1:
        return 'no head', None
    lines = text.split('\n')[:-1]
    if len(lines) < head['length']:
        return 'short', len(lines)
    out, prev, closed = [], 'GENESIS', False
    for n, line in enumerate(lines[:head['length']]):
        try:
            e = json.loads(line)
            ok = (not closed and dumps(e) == line and sorted(k for k in e if k != 'stated') == sorted(COVERED + ('sha256',)) and type(e['seq']) is int and e['seq'] == n
                  and e['prev_sha256'] == prev and (e['kind'] == 'header') == (n == 0) and (e['kind'] == 'header' or e['kind'] in BODY)
                  and e['sha256'] == sha({k: e[k] for k in COVERED}))
        except Exception:   # also a line this reader cannot take apart at all
            ok = False
        if not ok:
            return 'broken', n
        out.append(e)
        prev, closed = e['sha256'], e['kind'] == 'close'
    return ('ok', out) if prev == head['sha256'] else ('other hash', None)


def whole(text, head, past=0):
    """The text holds exactly the lines its head names (and `past` more), each ended by its line feed, and nothing after the last."""
    return type(text) is str and type(head) is dict and type(head.get('length')) is int and len(text.split('\n')) == head['length'] + past + 1 and text.endswith('\n')


def named(body, may):
    """What names a journal: its kinds and checkers, lists of names with none twice, and where it has one its name."""
    strings = lambda v: type(v) is list and all(type(x) is str and x for x in v) and len(set(v)) == len(v)
    return (type(body) is dict and {'kinds', 'checkers'} <= set(body) <= may and strings(body['kinds']) and len(body['kinds']) > 0 and strings(body['checkers'])
            and ('name' not in body or (type(body['name']) is str and body['name'] != '')))


def shapes(entries):
    """Every entry holds exactly the keys of its kind, and exact types where the doors ask for them."""
    for e in entries:
        kind, body, result = e['kind'], e['body'], e['result']
        if kind == 'header':
            if not named(body, {'kinds', 'checkers', 'name', 'continues'}) or ('continues' in body and (type(body['continues']) is not dict or sorted(body['continues']) != ['length', 'sha256'])):
                return False
        elif sorted(body) != BODY[kind] or ('execute' in body and type(body['execute']) is not bool) or (kind == 'close' and not named(body['next'], {'kinds', 'checkers', 'name'})):
            return False
        want = ['budget', 'providers', 'state'] + ([] if kind in ('header', 'pack', 'close') else ['briefs', 'status', 'goals' if kind == 'look' else 'affected'])
        if sorted(result) != sorted(want) or type(result['state']) is not str or len(result['state']) != 64 or set(result['state']) - set('0123456789abcdef'):
            return False
        if any(type(v) is not int for v in list(result['budget'].values()) + list(result['providers'].values())):
            return False
        if 'stated' in e and (sorted(e['stated']) != ['code'] or any(type(v) is not str for v in e['stated']['code'].values())):
            return False
    return True


def books(chain, sha):
    """The first entry whose budget or provider slots, stated in plain, do not follow from the packs and the receipts
    before it, as (journal, entry); None when every entry's books add up. `chain` is one journal or several in order."""
    budget, slots, methods = dict(START), {}, {}
    for j, entries in enumerate(chain):
        for e in entries:
            if e['kind'] == 'pack':
                p = e['body']['pack']
                budget.update(p.get('budget', {}))
                slots.update(p.get('providers', {}))
                methods.update({m['id']: m for m in p.get('methods', [])})
            for b in e['result'].get('briefs', []):
                for x in b['receipts']:
                    slots[methods[x['method']]['provider']] -= 1
                    for dim, v in methods[x['method']].get('cost', {}).items():
                        budget[dim] -= v
            if sha(e['result']['budget']) != sha(budget) or sha(e['result']['providers']) != sha(slots):
                return j, e['seq']
    return None


def walked(chain, sha):
    """What the doors let in, read back from the entries of one journal or of a chain in order. Returns, by rule, the
    entries a door would not have let in, each as (journal, entry):
      event    the row is verified, is not a decision, and comes from a checker the header of its journal names;
      answer   it presents, whole, the receipt of a question that is out at that point (sent by a step of an earlier
               entry and not answered since), and it comes from the party that receipt says was asked;
      execute  an entry one of whose runs ran, skipped or stopped a step was taken with execute true."""
    bad, out = {'event': [], 'answer': [], 'execute': []}, {}
    for j, entries in enumerate(chain):
        checkers = entries[0]['body']['checkers']
        for e in entries:
            body, at = e['body'], (j, e['seq'])
            if e['kind'] == 'event' and (body['row'].get('verified') is not True or body['row'].get('final') or body['row'].get('source') not in checkers):
                bad['event'].append(at)
            if e['kind'] == 'answer':
                r = body['receipt']
                asked = out.pop(r.get('sha256'), None) if type(r) is dict and type(r.get('sha256')) is str else None
                if asked is None or sha(asked) != sha(r) or body['source'] != asked['ask']['to']:
                    bad['answer'].append(at)
            for b in e['result'].get('briefs', []):
                if (b['receipts'] or b.get('skipped') or b.get('stopped')) and body.get('execute') is not True:
                    bad['execute'].append(at)
                for x in b['receipts']:
                    if type(x.get('ask')) is dict:
                        out[x['sha256']] = x
    return bad


def brief(r):
    """What an entry keeps of a run, made here from the run as the record holds it."""
    b = {k: r[k] for k in ('goal', 'scope', 'status', 'work_state', 'actions', 'cost', 'trace_root_sha256')}
    b['receipts'] = r['model_receipts']
    b.update({k: r[k] for k in ('stop_reasons', 'pending', 'waits', 'skipped', 'stopped') if r.get(k)})
    t = r['trace']
    end = max(i for i, x in enumerate(t) if x['operation'] in PLAN_END)
    settled = [{'operation': x['operation'], 'data': x['data']} for x in t[end + 1:-1]]
    if settled:
        b['settled'] = settled
    return b


def stamp(body):
    """The row the stamp writes for an answer, made here from what the answer presents (for a fact that other evidence had not already made true)."""
    r = body['receipt']
    return {'predicate': r['ask']['predicate'], 'truth': body['truth'], 'verified': True, 'final': True, 'source': 'STAMP:' + r['ask']['to'],
            'version': 'ask-' + r['sha256'][:12], 'answers': r['sha256'], 'scope': r['scope']}


def answered(kind, body, got, sha):
    """What the kernel returned beside its runs, against what was handed in: a look names the goals it ran, an event
    returns the row it stored and the goals it reached, an answer returns the stamp's row."""
    names = [r['goal'] for r in got['runs']]
    if kind == 'look':
        return sorted(got) == ['goals', 'runs', 'status'] and got['goals'] == names and got['status'] == ('EVALUATED' if names else 'NO_STANDING_GOAL')
    row = body['row'] if kind == 'event' else stamp(body)
    return sorted(got) == ['affected', 'event', 'runs', 'status'] and got['status'] == 'RECONCILED' and got['affected'] == names and sha(got['event']) == sha(row)


def told(entries, step, sha):
    """A recorded step against the entry it names: the entry's briefs are the briefs of the runs the kernel returned,
    and what the kernel returned beside them is what the entry's body handed in."""
    e, got = entries[step['entry']], step['result']
    return (e['kind'] in ('look', 'event', 'answer') and sha(e['result']['briefs']) == sha([brief(r) for r in got['runs']]) and e['result']['status'] == got['status']
            and (sha(e['result']['goals']) == sha(got['goals']) if e['kind'] == 'look' else sha(e['result']['affected']) == sha(got['affected']))
            and answered(e['kind'], e['body'], got, sha))


def pack_ids(chain):
    return [e['body']['pack'].get('id') for entries in chain for e in entries if e['kind'] == 'pack']


def digest_after(kinds, packs, sha):
    """The State digest after these packs and nothing else, made here: the hash of the named views of what a look
    reads, every empty view left out. Good for packs that hold a scope, goals, rows, rules, methods, provider slots,
    grants, a budget and a preference: what the recorded sequences hand over before their first look."""
    scope, goals, budget, preference = SCOPE, [], dict(START), list(PREFERENCE)
    evidence, rules, proposed, methods, providers, grants, loaded = {}, {}, {}, [], {}, set(), []
    for p in packs:
        scope, goals, preference = p.get('scope', scope), p.get('goals', goals), p.get('preference', preference)
        for row in p.get('evidence', []):
            if row.get('verified'):
                evidence[row.get('scope', scope) + '|' + row['predicate']] = dict(row, scope=row.get('scope', scope))
        for r in p.get('rules', []):
            if r.get('approved', False):
                rules[r['head']] = r
            else:
                proposed[r['head']] = dict(r, status='PROPOSED_ONLY')
        methods += [[m['id'], m] for m in p.get('methods', [])]
        providers.update(p.get('providers', {}))
        grants = (grants | set(p.get('grants', []))) - set(p.get('revoke_grants', []))
        budget.update(p.get('budget', {}))
        loaded.append({'pack': p['id'], 'sha256': sha(p)})
    views = {'scope': scope, 'goals': goals, 'evidence': evidence, 'rules': rules, 'proposed': proposed, 'methods': methods, 'providers': providers,
             'grants': sorted(grants), 'budget': budget, 'preference': preference, 'loaded': loaded, 'kinds': list(kinds)}
    return sha({k: v for k, v in views.items() if v not in ('', [], {})})


def record(chain):
    return [(entries[0]['sha256'][:12], entries) for entries in chain]


def ledger(chain, sha):
    """The ledger rows, made here from the entries alone: handed in, asked, decided, ran."""
    rows, asked = [], {}
    for journal, entries in record(chain):
        for e in entries:
            at, body, result = {'journal': journal, 'entry': e['seq'], 'sha256': e['sha256']}, e['body'], e['result']
            if e['kind'] == 'pack':
                rows.append(dict(at, what='handed_in', pack=body['pack'].get('id'), pack_sha256=sha(body['pack'])))
            elif e['kind'] == 'event':
                rows.append(dict(at, what='handed_in', row={k: body['row'].get(k) for k in ('predicate', 'truth', 'source', 'version')}, status=result['status'], affected=result['affected']))
            elif e['kind'] == 'answer':
                r = body['receipt']
                rows.append(dict(at, what='decided', predicate=r['ask']['predicate'], truth=body['truth'], by=body['source'], answers=r['sha256'], asked_at=asked.get(r['sha256']), status=result['status']))
            for i, b in enumerate(result.get('briefs', [])):
                run = journal + ':' + str(e['seq']) + '.' + str(i)
                row = dict(at, what='ran', run=run, executed=body['execute'], receipts=[x['sha256'] for x in b['receipts']])
                row.update({k: b[k] for k in ('goal', 'scope', 'status', 'work_state', 'actions', 'cost', 'trace_root_sha256')})
                row.update({k: b[k] for k in ('stop_reasons', 'pending', 'waits', 'skipped', 'stopped', 'settled') if k in b})
                rows.append(row)
                for x in b['receipts']:
                    if type(x.get('ask')) is dict:
                        asked.setdefault(x['sha256'], dict(at, run=run))
                        rows.append(dict(at, what='asked', run=run, receipt=x['sha256'], method=x['method'], to=x['ask']['to'], question=x['ask']['question'], predicate=x['ask']['predicate']))
    return rows


def counts(chain):
    """How often each goal was looked at and each step ran, stopped or was skipped, made here, every occurrence cited."""
    goals, steps = {}, {}
    for journal, entries in record(chain):
        for e in entries:
            for i, b in enumerate(e['result'].get('briefs', [])):
                at = {'journal': journal, 'entry': e['seq'], 'sha256': e['sha256'], 'run': i}
                g = goals.setdefault(b['scope'] + '|' + b['goal'], {'looked': 0, 'executed': 0, 'statuses': {}, 'trace_roots': [], 'at': []})
                g['looked'] += 1
                g['executed'] += 1 if e['body']['execute'] is True else 0
                g['statuses'][b['status']] = g['statuses'].get(b['status'], 0) + 1
                if b['trace_root_sha256'] not in g['trace_roots']:
                    g['trace_roots'].append(b['trace_root_sha256'])
                g['at'].append(dict(at, status=b['status']))
                seen = [(x['method'], 'ran') for x in b['receipts']] + ([(b['stopped']['method'], 'stopped')] if 'stopped' in b else []) + [(m, 'skipped') for m in b.get('skipped', [])]
                for method, what in seen:
                    s = steps.setdefault(b['scope'] + '|' + method, {'ran': 0, 'stopped': 0, 'skipped': 0, 'at': []})
                    s[what] += 1
                    s['at'].append(dict(at, what=what))
    return {'goals': goals, 'steps': steps}


def door(kind, body, header, let_in, out, sha):
    """What the journal's doors say to a body, decided here; None for a body that would pass."""
    if type(kind) is not str or kind not in ('header', 'pack', 'event', 'look', 'answer', 'close'):
        return 'Unknown journal entry kind: ' + str(kind)[:40]
    if kind == 'header':
        return 'A journal has one header, entry 0'
    if sorted(body) != BODY[kind]:
        return EXACTLY.format(kind, ', '.join(BODY[kind]))
    if 'execute' in body and type(body['execute']) is not bool:
        return EXECUTE
    if kind == 'pack' and type(body['pack']) is not dict:
        return 'A pack entry holds a pack'
    if kind == 'event' and type(body['row']) is not dict:
        return 'An event entry holds one row'
    if kind == 'close':
        return NAMES if not named(body['next'], {'kinds', 'checkers', 'name'}) else SAME_KINDS if body['next']['kinds'] != header['kinds'] else None
    if kind == 'pack' and body['pack'].get('id') in let_in:
        return ONCE.format(json.dumps(body['pack'].get('id'), ensure_ascii=False))
    if kind == 'event' and (body['row'].get('verified') is not True or body['row'].get('final') or body['row'].get('source') not in header['checkers']):
        return EVENT_DOOR
    if kind == 'answer':
        r = body['receipt']
        if (type(body['truth']) is not str or body['truth'] not in ('TRUE', 'FALSE') or type(body['source']) is not str or type(r) is not dict or type(r.get('ask')) is not dict
                or type(r['ask'].get('predicate')) is not str):
            return 'An answer is TRUE or FALSE, from a named party, to an ask receipt'
        if out is None or sha(r) != sha(out):
            return NO_ASK
        if body['source'] != out['ask']['to']:
            return NOT_THE_PARTY
    return None


def parts(d, ROOT, sha, only=None):
    """The tests behind C1 to C9, each on its own: {check number: {test: holds}}. A test that cannot read what it
    needs does not hold. `only` names one check (its first three characters) when the others are not wanted."""
    scenes = d['scenes']
    restart, refusals, chain = scenes['journal_restart'], scenes['journal_refusals'], scenes['journal_chain']
    past, writers, once, outside, more = refusals['past_the_head'], refusals['second_writer'], refusals['pack_twice'], refusals['outside'], restart['one_dry_look_more']
    n, m, alone, calone, said, late = restart['no'], restart['line_marks'], restart['from_packs_alone'], chain['from_packs_alone'], chain['refused'], chain['late_writer']
    first_w, second_w, again_w, kernel_alone, twice = writers['first'], writers['second'], writers['again'], once['kernel_alone'], once['holds_it_twice']
    case = [c for c in d['cases'] if c['id'] == '60_pack_twice'][0]
    handlers = d['action_handlers']

    def get(make):   # what a test needs, or None when the record does not hold it: the tests that need it then do not hold
        try:
            return make()
        except Exception:
            return None

    def journal(holder, text='text', head='head', past_head=0):   # a kept text read to its head: whole, in order, and with nothing after it
        verdict, got = read(holder[text], holder[head], sha)
        return got if verdict == 'ok' and whole(holder[text], holder[head], past_head) else None
    main, no, dry, marks = get(lambda: journal(restart)), get(lambda: journal(n)), get(lambda: journal(more)), get(lambda: journal(m))
    base, past_after, wrote, onced = get(lambda: journal(refusals)), get(lambda: journal(past, 'text_after_save', 'head_after_save')), get(lambda: journal(writers)), get(lambda: journal(once))
    j1, j2 = get(lambda: journal(chain['first'])), get(lambda: journal(chain['second']))
    twin, wrote_first, held_twice = get(lambda: journal(restart, 'twin_text', 'twin_head')), get(lambda: journal(second_w, 'kept_text', 'kept_head')), get(lambda: journal(twice))
    kept = {'main': main, 'no': no, 'dry': dry, 'marks': marks, 'base': base, 'past_after': past_after, 'wrote': wrote, 'onced': onced, 'j1': j1, 'j2': j2}
    singles = [main, no, dry, marks, base, past_after, wrote, onced, j1]   # the nine journals that start from nothing; j2 continues j1
    every = singles + [j2]
    same = lambda a, b: sha(a) == sha(b)                                    # compared as JSON: 1 is not true and not 1.0
    run = lambda step: step['result']['runs'][0]
    head_of = lambda entries, at=None: {'length': at or len(entries), 'sha256': entries[(at or len(entries)) - 1]['sha256']}
    lines = lambda text: text.split('\n')[:-1]
    hexes = lambda v: type(v) is str and len(v) == 64 and not set(v) - set('0123456789abcdef')
    receipt = get(lambda: main[6]['result']['briefs'][0]['receipts'][0])   # the question process 1 sent
    other = get(lambda: dry[7]['result']['briefs'][0]['receipts'][0])      # the question sent on the journal with one dry look more
    out = get(lambda: {QUESTION: {'method': receipt['method'], 'receipt': receipt['sha256'], 'issued': receipt}})
    pack_file = lambda name: json.loads((ROOT / 'scenarios' / (name + '.json')).read_text(encoding='utf-8'))
    first, again, yes, later = restart['first'], restart['again'], restart['answered_yes'], restart['later']
    receipt_of_base = lambda: base[6]['result']['briefs'][0]['receipts'][0]
    out_of_base = lambda: {QUESTION: {'method': receipt_of_base()['method'], 'receipt': receipt_of_base()['sha256'], 'issued': receipt_of_base()}}

    def snap(s, entry, asks):   # a snapshot against the entry it was taken after: the books the entry states, and the questions out
        return same(s, {'budget': entry['result']['budget'], 'providers': entry['result']['providers'], 'open_asks': asks})

    def tampered(what):   # one tampered text: how this reader finds it, whether the recorded refusal says just that, where, and the record's row
        t = [x for x in refusals['tampered'] if x['what'] == what][0]
        verdict, got = read(t['text'], t['head'], sha)
        words = {'short': 'The journal ends before its head: {} entries, the head names {}'.format(got, (t['head'] or {}).get('length')),
                 'broken': 'The journal is broken at entry {}'.format(got), 'other hash': 'The journal does not end on the hash its head names',
                 'no head': 'No head, no restart: the head is kept outside the journal, and none is kept here'}.get(verdict)
        return verdict, words is not None and t['refused'] == words, got, t

    def derived():   # each tampered text is the kept text changed in the way it says, and in no other: compared as whole texts, so nothing stands after any of them
        k, t, head = lines(refusals['text']), {x['what']: x for x in refusals['tampered']}, refusals['head']
        entries = [json.loads(x) for x in k]
        edited = json.loads(dumps(entries[5]))
        edited['body']['pack']['methods'][0]['ask_to'] = 'someone-else'             # who is asked, changed in the pack as it was handed in, the entry's hash left as it was
        forged = {x: entries[6][x] for x in COVERED}
        forged['result'] = dict(forged['result'], budget=dict(forged['result']['budget'], attention=3))   # the charge for the question taken back, and the entry hashed again
        forged['sha256'] = sha(forged)
        return (whole(refusals['text'], head) and same(head, head_of(entries))
                and t[WHATS[0]]['text'] == text_of(k[:-1]) and same(t[WHATS[0]]['head'], head)
                and t[WHATS[1]]['text'] == text_of(k[:5] + [dumps(edited)] + k[6:]) and same(t[WHATS[1]]['head'], head) and edited['body']['pack']['methods'][0]['ask_to'] != entries[5]['body']['pack']['methods'][0]['ask_to']
                and t[WHATS[2]]['text'] == text_of(k[:3] + k[4:]) and same(t[WHATS[2]]['head'], head)
                and t[WHATS[3]]['text'] == text_of(k[:3] + k[4:]) and same(t[WHATS[3]]['head'], {'length': 6, 'sha256': head['sha256']})
                and t[WHATS[4]]['text'] == text_of(k[:4] + k[3:]) and same(t[WHATS[4]]['head'], head)
                and t[WHATS[5]]['text'] == text_of(k[:2] + [k[3], k[2]] + k[4:]) and same(t[WHATS[5]]['head'], head)
                and t[WHATS[6]]['text'] == refusals['text'] and same(t[WHATS[6]]['head'], {'length': 7, 'sha256': entries[5]['sha256']})
                and t[WHATS[7]]['text'] == refusals['text'] and t[WHATS[7]]['head'] is None
                and t[WHATS[8]]['text'] == text_of(k[:6] + [dumps(forged)]) and same(t[WHATS[8]]['head'], {'length': 7, 'sha256': forged['sha256']}) and 'stated' not in entries[6]
                and t[WHATS[9]]['text'] == text_of(k[:3] + [DEEP] + k[4:]) and same(t[WHATS[9]]['head'], head))

    def refused_run(step):
        return (run(step)['status'], run(step)['work_state'], run(step)['actions'], run(step)['model_receipts']) == ('REFUSED', 'blocked', [], [])

    def steps():   # every recorded step with the journal that holds its entry, and the `execute` the sequence took it with
        taken = ([('main', restart[k]) for k in ('first', 'again', 'answered_yes', 'later')] + [('no', first), ('no', n['answered_no']), ('no', n['look']), ('marks', m['look'])]
                 + [('dry', more[k]) for k in ('dry', 'look', 'answered_yes')] + [('base', refusals['look']), ('past_after', refusals['look']), ('past_after', past['look'])]
                 + [('wrote', refusals['look']), ('wrote', first_w['step']), ('wrote', again_w['step']), ('onced', once['shipped']), ('onced', once['came_back'])]
                 + [('j1', chain['first']['look']), ('j2', chain['second']['look']), ('j2', chain['second']['came_back']), ('j2', chain['second']['look_again']), ('j2', chain['restarted']['look'])])
        return [(name, step, step is not more['dry']) for name, step in taken]   # every look, event and answer of the sequences executes, but the one dry look

    def every_entry_is_a_step():   # no look, event or answer entry of a kept journal is without its recorded run, and each was taken with the `execute` its sequence gave
        named_steps = {}
        for name, step, executed in steps():
            named_steps.setdefault(name, {})[step['entry']] = executed
        return all(sorted(named_steps.get(name, {})) == [e['seq'] for e in x if e['kind'] in ('look', 'event', 'answer')]
                   and all(x[at]['body']['execute'] is executed for at, executed in named_steps.get(name, {}).items()) for name, x in kept.items())

    def code_of(kinds):   # what the record itself says of the code these action kinds run on: the kernel, and each kind's handler file
        said_of = {'kernel.core': d['kernel_sha256']}
        for k in kinds:
            said_of[handlers[k].get('module') or handlers[k]['file'][:-3].replace('/', '.')] = handlers[k]['sha256']
        return said_of

    def journal_file(stated):   # where the record lists the files a version added by sha256, the journal's own file is held to that list too
        listed = [v for k, v in ((d.get('added') or {}).get('files') or {}).items() if k.endswith('extensions/journal.py')]
        return hexes(stated) and all(v == stated for v in listed)

    def digests(entries):   # the State digest of the header and of the five packs before the first look, made here
        kinds, packs, ok = entries[0]['body']['kinds'], [], entries[0]['result']['state'] == digest_after(entries[0]['body']['kinds'], [], sha)
        for e in entries[1:]:
            if e['kind'] != 'pack':
                break
            packs.append(e['body']['pack'])
            ok = ok and e['result']['state'] == digest_after(kinds, packs, sha)
        return ok and len(packs) == 5

    def cited(c, of):   # every count is the number of its citations, and every citation names an entry of the record by number and hash
        by_name = dict(record(of))
        return (all(same(v[k], len([a for a in v['at'] if a['what'] == k])) for v in c['steps'].values() for k in ('ran', 'stopped', 'skipped'))
                and all(same(v['looked'], len(v['at'])) and same(v['looked'], sum(v['statuses'].values())) for v in c['goals'].values())
                and all(by_name[a['journal']][a['entry']]['sha256'] == a['sha256'] for group in (c['goals'], c['steps']) for v in group.values() for a in v['at']))

    def snaps():   # every snapshot taken after an entry, with that entry and the questions out after it
        other_out = {QUESTION: {'method': other['method'], 'receipt': other['sha256'], 'issued': other}}
        return [(restart['after_first'], main[6], out), (restart['restarted']['after'], main[6], out), (restart['after_again'], main[7], out), (restart['after_yes'], main[8], {}), (restart['after_later'], main[9], {}),
                (n['after_no'], no[7], {}), (n['after_look'], no[8], {}), (more['after_dry'], dry[6], {}), (more['after_look'], dry[7], other_out), (more['after_yes'], dry[8], {}),
                (past['after_restart'], base[6], out_of_base()), (once['after_shipped'], onced[6], {}), (once['after_levels'], onced[7], {}), (once['after_came_back'], onced[8], {}), (once['after_refusal'], onced[8], {}),
                (outside['after_restart'], base[6], out_of_base()), (refusals['after_doors']['after'], base[6], out_of_base()),
                (chain['first']['after'], j1[6], {}), (late['after_restart'], j1[7], {}), (late['after_step'], j2[2], {}),
                (chain['second']['after_look'], j2[1], {}), (chain['second']['after_came_back'], j2[2], {}), (chain['restarted']['after'], j2[3], {}), (chain['restarted']['after_look'], j2[4], {})]

    def outside_a_journal():   # what the kernel returned where no kept journal stood between: (the door, what was handed in, what came back)
        yes_to = lambda r: {'receipt': r, 'truth': 'TRUE'}
        return [('look', None, alone['look']), ('answer', yes_to(receipt), alone['answered_yes']), ('look', None, n['from_packs_alone']['look']), ('answer', yes_to(receipt), n['from_packs_alone']['answered_yes']),
                ('look', None, calone['look']), ('look', None, kernel_alone['shipped']), ('event', onced[8]['body'], kernel_alone['came_back']), ('answer', yes_to(receipt_of_base()), outside['bypass']),
                ('event', wrote[8]['body'], second_w['step']['result']), ('event', j2[2]['body'], late['step']['result'])]

    def stray():   # the entry that stands past the head: the text read one entry further, with the head it would have had
        got = lines(past['text'])
        last = json.loads(got[7])
        verdict, entries = read(past['text'], {'length': 8, 'sha256': last['sha256']}, sha)
        return entries if verdict == 'ok' and whole(past['text'], past['head'], 1) else None

    def twice_is_once_and_one_more():   # the journal that holds the level pack twice: the journal that holds it once, and the entry that let it in a second time, chained on
        again_in = {x: onced[7][x] for x in COVERED}
        again_in.update(seq=9, prev_sha256=onced[8]['sha256'], result=dict(onced[7]['result'], state=onced[8]['result']['state']))
        again_in['sha256'] = sha(again_in)
        return twice['text'] == once['text'] + dumps(again_in) + '\n' and same(twice['head'], {'length': 10, 'sha256': again_in['sha256']}) and 'stated' not in onced[7]

    def tried():   # the bodies the sequence tried at the doors, in order, made here from what the record holds elsewhere: the receipt, the second writer's row, the kept head, the pack file
        r, row = receipt_of_base(), wrote[8]['body']['row']
        other = dict(r, ask=dict(r['ask'], to='someone-else'))
        yes_to = lambda presented, source, execute: {'receipt': presented, 'truth': 'TRUE', 'source': source, 'execute': execute}
        return [{'execute': 'false'}, {'execute': 1}, {'execute': True, 'note': 'x'}, {}, {'pack': pack_file('80_ask_method')},
                {'row': dict(row, source='the-hand'), 'execute': True}, {'row': dict(row, predicate='customer_approved', final=True), 'execute': True}, {'row': dict(row, verified=False), 'execute': True}, {'row': row},
                yes_to(other, 'someone-else', True), yes_to(r, 'someone-else', True), yes_to(r, r['ask']['to'], 'yes'), {'fact': 'customer_approved', 'truth': 'TRUE', 'source': r['ask']['to'], 'execute': True},
                {'head': refusals['head']}, {'kinds': refusals['kinds'], 'checkers': []}, {}, {'next': {'kinds': ['ask'], 'checkers': []}}]

    question = lambda: pack_file('141_ask_with_line_marks')['methods'][0]['question']
    goal, step = SCOPE + '|order_complete', SCOPE + '|' + SHIP
    closing = lambda: {'next': {k: v for k, v in j2[0]['body'].items() if k != 'continues'}}   # what the closing entry of journal 1 must say: the journal that continues it, named as its own header names it
    tests = {
        'S90': {   # C1: whole, in order and on its head, or refused
            'every_kept_text_reads_to_its_head_and_nothing_stands_after_it': lambda: all(x is not None for x in every + [twin, wrote_first, held_twice]),
            'every_entry_holds_the_keys_of_its_kind': lambda: all(shapes(x) for x in every + [stray()]),
            'ten_tampered_texts_are_on_record': lambda: ([t['what'] for t in refusals['tampered']] == WHATS
                                                         and all(t['text'] != refusals['text'] or not same(t['head'], refusals['head']) for t in refusals['tampered'])),
            'each_is_the_kept_text_changed_in_the_way_it_says': derived,
            'a_text_cut_short_is_refused': lambda: [tampered(w)[:3] for w in (WHATS[0], WHATS[2])] == [('short', True, 6), ('short', True, 6)],
            'a_changed_dropped_doubled_or_swapped_entry_is_refused_by_number': lambda: [tampered(w)[:3] for w in (WHATS[1], WHATS[3], WHATS[4], WHATS[5])] == [('broken', True, 5), ('broken', True, 3), ('broken', True, 4), ('broken', True, 2)],
            'a_line_no_reader_can_take_apart_is_a_broken_entry_by_number': lambda: tampered(WHATS[9])[:3] == ('broken', True, 3) and lines(tampered(WHATS[9])[3]['text'])[3] == DEEP,
            'a_head_for_another_hash_is_refused': lambda: tampered(WHATS[6])[:2] == ('other hash', True),
            'no_head_no_restart': lambda: tampered(WHATS[7])[:2] == ('no head', True) and tampered(WHATS[7])[3]['head'] is None,
            'an_entry_past_the_head_is_reported': lambda: (same(past['head'], refusals['head']) and same(past['head'], head_of(base)) and past['text'][:len(refusals['text'])] == refusals['text'] and same(past['cut'], 1)
                                                           and stray()[:7] == base and stray()[7]['kind'] == 'answer' and same(past['writer']['entry'], 7) and told(stray(), past['writer'], sha)
                                                           and same(stray()[7]['body'], {'receipt': receipt_of_base(), 'truth': 'TRUE', 'source': receipt_of_base()['ask']['to'], 'execute': True})
                                                           and books([stray()], sha) is None and walked([stray()], sha) == {'event': [], 'answer': [], 'execute': []}),
            'and_is_never_run': lambda: (snap(past['after_restart'], base[6], out_of_base()) and same(past['look']['entry'], 7) and told(past_after, past['look'], sha)
                                         and (run(past['look'])['status'], run(past['look'])['model_receipts']) == ('WAITING', [])),
            'and_is_cut_by_the_next_save': lambda: past_after[:7] == base and past_after[7]['kind'] == 'look' and len(past_after) == 8 and same(past['head_after_save'], head_of(past_after)),
            'a_line_mark_cuts_no_entry': lambda: (all(mark in question() for mark in MARKS) and same([run(m['look'])['model_receipts'][0]['ask']['question'], m['question_after_restart'],
                                                  marks[6]['result']['briefs'][0]['receipts'][0]['ask']['question']], [question()] * 3) and len(marks) == 7 and same(m['head']['length'], 7)
                                                  and len(m['text'].splitlines()) > 7 and m['state_after_restart'] == marks[6]['result']['state'] and pack_ids([marks]) == m['packs']),
        },
        'S91': {   # C2: the same journal up to its head, the same answer; the packs alone do not give it
            'the_walk_is_the_journal': lambda: ([e['kind'] for e in main] == ['header'] + ['pack'] * 5 + ['look', 'look', 'answer', 'look'] and pack_ids([main]) == restart['packs']
                                                and same([x['entry'] for x in (first, again, yes, later)], [6, 7, 8, 9]) and same(restart['head_after_first'], head_of(main, 7))),
            'process_one_asks_and_stops': lambda: ((run(first)['status'], run(first)['actions'], run(first)['pending']) == ('WAITING', [receipt['method']], [SHIP]) and receipt['ask']['to'] == 'customer'
                                                   and receipt.get('parked') is True and same(main[6]['result']['budget'], dict(START, attention=2)) and snap(restart['after_first'], main[6], out)),
            'after_the_restart_the_question_is_still_out': lambda: (same(restart['restarted']['head'], restart['head_after_first']) and same(restart['restarted']['cut'], 0)
                                                                    and restart['restarted']['state'] == main[6]['result']['state'] and snap(restart['restarted']['after'], main[6], out)),
            'the_look_waits_runs_nothing_and_charges_nothing': lambda: ((run(again)['status'], run(again)['actions'], run(again)['model_receipts'], run(again)['pending'], run(again)['waits']) == ('WAITING', [], [], [SHIP], [receipt['method']])
                                                                        and same(main[7]['result']['budget'], main[6]['result']['budget']) and same(main[7]['result']['providers'], main[6]['result']['providers'])
                                                                        and snap(restart['after_again'], main[7], out)),
            'the_answer_presents_that_receipt_and_the_plan_goes_on': lambda: (same(main[8]['body'], {'receipt': receipt, 'truth': 'TRUE', 'source': receipt['ask']['to'], 'execute': True})
                                                                              and (run(yes)['status'], run(yes)['actions']) == ('LOCAL_MODEL_EFFECTS_RECORDED', [SHIP])
                                                                              and same(main[8]['result']['budget'], {'compute': 8, 'money': 8, 'attention': 2}) and snap(restart['after_yes'], main[8], {})),
            'asked_once_and_charged_once_in_the_whole_journal': lambda: ([x['sha256'] for e in main for b in e['result'].get('briefs', []) for x in b['receipts'] if 'ask' in x] == [receipt['sha256']]
                                                                         and same(START['attention'] - main[9]['result']['budget']['attention'], 1)),
            'it_ends_on_the_text_and_the_head_of_a_twin_that_never_stopped': lambda: (twin is not None and restart['twin_text'] == restart['text'] and same(restart['twin_head'], restart['head'])
                                                                                      and same(restart['head'], head_of(main)) and len(main) == 10),
            'from_the_packs_alone_the_receipt_is_refused': lambda: alone['answer_refused'] == NO_ASK and same(alone['after_refusal'], {'budget': START, 'providers': main[5]['result']['providers'], 'open_asks': {}}),
            'and_the_customer_is_asked_and_charged_again': lambda: (alone['look']['runs'][0]['status'] == 'WAITING' and same(alone['look']['runs'][0]['model_receipts'], [receipt]) and same(alone['after_look'], restart['after_first'])
                                                                    and same((START['attention'] - restart['after_first']['budget']['attention']) + (START['attention'] - alone['after_look']['budget']['attention']), 2)
                                                                    and (alone['answered_yes']['runs'][0]['status'], alone['answered_yes']['runs'][0]['actions']) == ('LOCAL_MODEL_EFFECTS_RECORDED', [SHIP])
                                                                    and same(alone['after_yes'], restart['after_yes'])),
            'one_dry_look_more_is_another_receipt_under_the_same_packs': lambda: (dry[:6] == main[:6] and [e['kind'] for e in dry[6:]] == ['look', 'look', 'answer'] and same([dry[6]['body'], dry[7]['body']], [{'execute': False}, {'execute': True}])
                                                                                  and same([more[k]['entry'] for k in ('dry', 'look', 'answered_yes')], [6, 7, 8])
                                                                                  and (run(more['dry'])['status'], run(more['dry'])['model_receipts']) == ('PLAN_READY', []) and same(dry[6]['result']['budget'], START) and snap(more['after_dry'], dry[6], {})
                                                                                  and run(more['look'])['status'] == 'WAITING' and other['sha256'] != receipt['sha256'] and other['ask']['asked_in'] != receipt['ask']['asked_in']
                                                                                  and same(dict(other, sha256='', ask=dict(other['ask'], asked_in='')), dict(receipt, sha256='', ask=dict(receipt['ask'], asked_in='')))
                                                                                  and same(run(more['look'])['provenance'], run(first)['provenance']) and run(more['look'])['trace_root_sha256'] != run(first)['trace_root_sha256']
                                                                                  and snap(more['after_look'], dry[7], {QUESTION: {'method': other['method'], 'receipt': other['sha256'], 'issued': other}})),
            'which_the_first_receipt_does_not_answer': lambda: (more['first_receipt_refused'] == NO_ASK and same(dry[8]['body'], {'receipt': other, 'truth': 'TRUE', 'source': 'customer', 'execute': True})
                                                                and (run(more['answered_yes'])['status'], run(more['answered_yes'])['actions']) == ('LOCAL_MODEL_EFFECTS_RECORDED', [SHIP])
                                                                and snap(more['after_yes'], dry[8], {}) and same(more['head'], head_of(dry)) and len(dry) == 9),
        },
        'S92': {   # C3: a no and a finished step survive a restart
            'the_no_is_an_entry': lambda: (no[:7] == main[:7] and [e['kind'] for e in no[7:]] == ['answer', 'look'] and same([n['answered_no']['entry'], n['look']['entry']], [7, 8])
                                           and same(no[7]['body'], {'receipt': receipt, 'truth': 'FALSE', 'source': 'customer', 'execute': True})),
            'after_a_restart_it_reads_refused_and_nothing_is_paid': lambda: (refused_run(n['answered_no']) and refused_run(n['look']) and snap(n['after_no'], no[7], {}) and snap(n['after_look'], no[8], {})
                                                                             and same(no[8]['result']['budget'], no[6]['result']['budget']) and same(no[6]['result']['budget'], {'compute': 10, 'money': 10, 'attention': 2})),
            'a_later_yes_is_refused_and_leaves_no_entry': lambda: n['later_yes_refused'] == NO_ASK and same(n['head'], head_of(no)) and len(no) == 9,
            'from_the_packs_alone_the_no_is_forgotten_and_a_yes_ships': lambda: (n['from_packs_alone']['look']['runs'][0]['status'] == 'WAITING'
                                                                                 and (n['from_packs_alone']['answered_yes']['runs'][0]['status'], n['from_packs_alone']['answered_yes']['runs'][0]['actions']) == ('LOCAL_MODEL_EFFECTS_RECORDED', [SHIP])
                                                                                 and same(n['from_packs_alone']['after_yes'], restart['after_yes'])),
            'what_ran_is_not_run_or_paid_again': lambda: ((run(later)['status'], run(later)['model_receipts']) == ('SUPPORTED_BY_EVIDENCE', []) and same(main[9]['result']['budget'], main[8]['result']['budget'])
                                                          and snap(restart['after_later'], main[9], {})
                                                          and all((run(s)['status'], run(s)['model_receipts']) == ('SUPPORTED_BY_EVIDENCE', []) for s in (chain['second']['look'], chain['restarted']['look']))
                                                          and same(j2[1]['result']['budget'], j1[6]['result']['budget']) and same(j1[6]['result']['budget'], {'compute': 8, 'money': 8, 'attention': 3})),
            'from_the_packs_alone_it_runs_and_is_paid_again': lambda: ((calone['look']['runs'][0]['status'], [x['method'] for x in calone['look']['runs'][0]['model_receipts']]) == ('LOCAL_MODEL_EFFECTS_RECORDED', [SHIP])
                                                                       and same(calone['after']['budget'], {'compute': 8, 'money': 8, 'attention': 3}) and same(calone['after'], chain['first']['after'])),
        },
        'S93': {   # C4: the books computed again; every brief held to the kernel's recorded run
            'the_books_follow_from_the_packs_and_the_receipts': lambda: all(books([x], sha) is None for x in singles) and books([j1, j2], sha) is None,
            'every_pack_entry_is_its_scenario_file': lambda: all(same(e['body']['pack'], pack_file(e['body']['pack']['id'])) for x in every for e in x if e['kind'] == 'pack'),
            'every_brief_is_the_run_the_kernel_returned': lambda: all(told(kept[name], s, sha) for name, s, _ in steps()),
            'every_look_event_and_answer_entry_has_its_recorded_run_and_was_taken_as_the_sequence_took_it': every_entry_is_a_step,
            'every_snapshot_is_the_books_its_entry_states': lambda: all(snap(s, e, asks) for s, e, asks in snaps()),
            'what_the_kernel_returned_outside_a_journal_is_what_was_handed_in': lambda: all(answered(kind, body, got, sha) for kind, body, got in outside_a_journal()),
            'every_journal_is_of_the_name_kinds_checkers_and_packs_its_sequence_gives': lambda: (
                all(same(x[0]['body'], {'kinds': restart['kinds'], 'checkers': [], 'name': 'restart'}) for x in (main, no, dry)) and same(marks[0]['body'], {'kinds': restart['kinds'], 'checkers': [], 'name': 'line-marks'})
                and all(same(x[0]['body'], {'kinds': refusals['kinds'], 'checkers': ['fixture/stock-recount'], 'name': 'refusals'}) for x in (base, past_after, wrote)) and pack_ids([base]) == refusals['packs']
                and same(onced[0]['body'], {'kinds': ['simulate_fact'], 'checkers': ['fixture/courier'], 'name': 'once'})
                and same(j1[0]['body'], {'kinds': chain['kinds'], 'checkers': chain['checkers'], 'name': 'orders-1'})
                and same(j2[0]['body'], {'kinds': chain['kinds'], 'checkers': chain['checkers'], 'name': 'orders-2', 'continues': chain['first']['head']})),
            'a_journal_re_chained_by_a_forger_is_refused_where_its_books_break': lambda: (tampered(WHATS[8])[0] == 'ok' and tampered(WHATS[8])[3]['text'] != refusals['text'] and books([tampered(WHATS[8])[2]], sha) == (0, 6)
                                                                                          and tampered(WHATS[8])[3]['refused'] == 'The journal does not replay at entry 6: the result differs (budget)'),
        },
        'S94': {   # C5: one writer at a time
            'two_runs_start_from_one_head': lambda: same(writers['base'], refusals['head']) and same(writers['base'], head_of(base)) and wrote[:7] == base,
            'the_first_save_is_taken': lambda: ([e['kind'] for e in wrote[7:]] == ['answer', 'event'] and wrote[7]['body']['truth'] == 'FALSE' and same(first_w['step']['entry'], 7)
                                                and run(first_w['step'])['status'] == 'REFUSED' and same(first_w['head'], head_of(wrote, 8))),
            'the_second_save_is_refused': lambda: same(second_w['step']['entry'], 7) and run(second_w['step'])['status'] == 'WAITING' and second_w['refused'] == MOVED.format(8),
            'and_changes_nothing_that_is_kept': lambda: (same(second_w['kept_head'], first_w['head']) and wrote_first == wrote[:8] and second_w['kept_text'] == text_of(lines(writers['text'])[:8])
                                                         and run(second_w['step'])['trace_root_sha256'] not in [b['trace_root_sha256'] for e in wrote for b in e['result'].get('briefs', [])]),
            'the_loser_replays_and_acts_on_what_the_first_wrote': lambda: (same(again_w['restarted_at'], first_w['head']) and same(again_w['step']['entry'], 8) and run(again_w['step'])['status'] == 'REFUSED'
                                                                           and same(wrote[8]['body'], {'row': second_w['step']['result']['event'], 'execute': True}) and again_w['later_yes_refused'] == NO_ASK
                                                                           and same(writers['head'], head_of(wrote)) and len(wrote) == 9),
        },
        'S95': {   # C6: the doors
            'a_pack_id_enters_a_journal_once': lambda: all(len(set(pack_ids([x]))) == len(pack_ids([x])) for x in singles) and len(set(pack_ids([j1, j2]))) == len(pack_ids([j1, j2])),
            'the_level_pack_is_let_in_once_and_refused_the_second_time': lambda: (pack_ids([onced]) == once['packs'] + ['140_levels_restated'] and same(once['levels_entry'], 7) and onced[7]['body']['pack']['id'] == '140_levels_restated'
                                                                                  and once['refused'] == ONCE.format('"140_levels_restated"') and same(once['after_refusal'], once['after_came_back'])
                                                                                  and snap(once['after_came_back'], onced[8], {}) and same(onced[8]['result']['budget'], {'compute': 8, 'money': 8, 'attention': 3})
                                                                                  and same(onced[7]['result']['budget'], START) and same(once['head'], head_of(onced)) and len(onced) == 9),
            'the_kernel_alone_takes_it_twice': lambda: (kernel_alone['loaded'] == once['packs'] + ['140_levels_restated'] * 2
                                                        and [kernel_alone[k]['runs'][0]['status'] for k in ('shipped', 'came_back')] == ['LOCAL_MODEL_EFFECTS_RECORDED'] * 2
                                                        and same(kernel_alone['budgets'], [dict(zip(PREFERENCE, x)) for x in ([8, 8, 3], [10, 10, 3], [8, 8, 3], [10, 10, 3])])
                                                        and [p['pack'] for p in case['outcome']['provenance']].count('140_levels_restated') == 2 and case['packs'].count('140_levels_restated') == 2
                                                        and case['outcome']['status'] == 'QUERY_EVIDENCE' and len({p['sha256'] for p in case['outcome']['provenance'] if p['pack'] == '140_levels_restated'}) == 1),
            'a_journal_that_holds_it_twice_does_not_replay': lambda: (held_twice is not None and twice_is_once_and_one_more() and pack_ids([held_twice]).count('140_levels_restated') == 2
                                                                      and twice['refused'] == 'The journal does not replay at entry {}: '.format(
                                                                          [e['seq'] for e in held_twice if e['kind'] == 'pack' and e['body']['pack'].get('id') == '140_levels_restated'][1]) + ONCE.format('"140_levels_restated"')),
            'every_event_row_is_verified_and_comes_from_a_checker_its_header_names': lambda: (all(walked([x], sha)['event'] == [] for x in singles) and walked([j1, j2], sha)['event'] == []
                                                                                              and [[e['seq'] for e in x if e['kind'] == 'event'] for x in (wrote, onced, j2)] == [[8], [8], [2]]),
            'every_answer_presents_the_receipt_of_a_question_that_is_out_and_comes_from_the_party_asked': lambda: (all(walked([x], sha)['answer'] == [] for x in singles) and walked([j1, j2], sha)['answer'] == []
                                                                                                                   and [[e['seq'] for e in x if e['kind'] == 'answer'] for x in (main, no, dry, wrote)] == [[8], [7], [8], [7]]),
            'an_entry_that_ran_skipped_or_stopped_a_step_was_taken_with_execute_true': lambda: all(walked([x], sha)['execute'] == [] for x in singles) and walked([j1, j2], sha)['execute'] == [],
            'every_door_refuses_in_the_words_of_its_rule': lambda: ([(x['kind'], x['refused']) for x in refusals['doors']] == DOORS and same([x['body'] for x in refusals['doors']], tried())
                                                                    and all(sorted(x) == ['body', 'kind', 'refused'] for x in refusals['doors'])
                                                                    and all(x['refused'] == door(x['kind'], x['body'], base[0]['body'], pack_ids([base]), receipt_of_base(), sha) for x in refusals['doors'])),
            'and_the_refusals_change_nothing': lambda: same(refusals['after_doors'], {'head': refusals['head'], 'state': base[6]['result']['state'],
                                                                                       'after': {'budget': base[6]['result']['budget'], 'providers': base[6]['result']['providers'], 'open_asks': out_of_base()}}),
            'a_state_changed_outside_the_journal_is_refused_at_the_next_entry': lambda: (run({'result': outside['bypass']})['status'] == 'LOCAL_MODEL_EFFECTS_RECORDED'
                                                                                         and same(outside['after_bypass'], {'budget': {'compute': 8, 'money': 8, 'attention': 2}, 'open_asks': {},
                                                                                                                            'providers': dict(base[6]['result']['providers'], **{'local-provider': base[6]['result']['providers']['local-provider'] - 1})})
                                                                                         and outside['refused'] == OUTSIDE.format(6) and outside['no_head'] == OUTSIDE.format(6) and same(outside['entries'], 7) and len(base) == 7
                                                                                         and snap(outside['after_restart'], base[6], out_of_base())),
        },
        'S96': {   # C7: what a head covers
            'the_code_is_stated_once_beside_the_entry_and_outside_its_hash': lambda: all([e['seq'] for e in x if 'stated' in e] == [0] and x[0]['sha256'] != sha({k: x[0][k] for k in COVERED + ('stated',)}) for x in every),
            'and_it_is_the_code_the_record_names': lambda: (all(same({k: v for k, v in x[0]['stated']['code'].items() if k != 'extensions.journal'}, code_of(x[0]['body']['kinds'])) for x in every)
                                                            and all(journal_file(x[0]['stated']['code']['extensions.journal']) for x in every) and len({x[0]['stated']['code']['extensions.journal'] for x in every}) == 1),
            'a_restart_under_the_same_code_gives_no_notice': lambda: restart['restarted']['notice'] == [],
            'no_file_hash_stands_under_a_head': lambda: all(h not in dumps([{k: e[k] for k in COVERED} for e in x]) for x in every for h in list(x[0]['stated']['code'].values()) + [d['kernel_sha256']]),
            'no_name_of_a_format_stands_under_a_head': lambda: all(set(x[0]['body']) <= {'kinds', 'checkers', 'name', 'continues'} for x in every),
            'the_digest_is_of_named_views_with_every_empty_view_left_out': lambda: all(digests(x) for x in singles),
        },
        'S97': {   # C8: continuing a journal is a write to it; a chain of journals
            'the_journal_that_is_continued_ends_on_a_closing_entry_that_names_the_next': lambda: ([e['kind'] for e in j1] == ['header'] + ['pack'] * 5 + ['look', 'close'] and same(j1[7]['body'], closing())
                                                                                                  and j1[7]['body']['next'].get('name') == 'orders-2' and same(j1[7]['result'], {k: j1[6]['result'][k] for k in ('budget', 'providers', 'state')})
                                                                                                  and same(chain['first']['head_before_closing'], head_of(j1, 7)) and same(chain['first']['head'], head_of(j1))),
            'a_writer_from_the_head_before_the_closing_is_refused_and_changes_nothing_kept': lambda: (same(late['step']['entry'], 7) and (run(late['step'])['status'], run(late['step'])['actions']) == ('LOCAL_MODEL_EFFECTS_RECORDED', [SHIP])
                                                                                                      and same(late['after_step']['budget'], {'compute': 6, 'money': 6, 'attention': 3}) and late['refused'] == MOVED.format(8)
                                                                                                      and same(late['kept_head'], chain['first']['head']) and late['kept_text'] == chain['first']['text']),
            'a_closed_journal_takes_no_entry_and_no_other_journal_continues_it': lambda: (same(late['restarted_at'], chain['first']['head']) and late['entry_refused'] == CLOSED and late['another_journal_refused'] == NAMES_ANOTHER
                                                                                          and snap(late['after_restart'], j1[7], {}) and same(late['after_restart']['budget'], {'compute': 8, 'money': 8, 'attention': 3})
                                                                                          and same(late['kept_head_after'], chain['first']['head']) and late['kept_text_after'] == chain['first']['text']),
            'the_header_cites_the_head_it_continues': lambda: (same(j2[0]['body'].get('continues'), chain['first']['head']) and same(chain['first']['head'], head_of(j1)) and 'continues' not in j1[0]['body']
                                                               and j2[0]['prev_sha256'] == 'GENESIS'),
            'and_starts_from_that_state_not_from_the_packs': lambda: (j2[0]['result']['state'] == j1[-1]['result']['state'] and same(j2[0]['result']['budget'], j1[-1]['result']['budget'])
                                                                      and same(j2[0]['result']['providers'], j1[-1]['result']['providers']) and j2[0]['body']['kinds'] == j1[0]['body']['kinds']
                                                                      and j1[0]['body']['kinds'] == chain['kinds'] and pack_ids([j2]) == [] and pack_ids([j1]) == chain['packs']),
            'the_second_journal_goes_on_where_the_first_stopped': lambda: ([e['kind'] for e in j2] == ['header', 'look', 'event', 'look', 'look']
                                                                           and same([chain['second'][k]['entry'] for k in ('look', 'came_back', 'look_again')] + [chain['restarted']['look']['entry']], [1, 2, 3, 4])
                                                                           and (run(chain['second']['came_back'])['status'], run(chain['second']['came_back'])['actions']) == ('LOCAL_MODEL_EFFECTS_RECORDED', [SHIP])
                                                                           and same(j2[2]['result']['budget'], {'compute': 6, 'money': 6, 'attention': 3}) and snap(chain['second']['after_came_back'], j2[2], {})),
            'the_chain_replays_as_one_record': lambda: (chain['restarted']['state'] == j2[3]['result']['state'] and chain['second']['state_before_the_restart'] == j2[3]['result']['state'] and snap(chain['restarted']['after'], j2[3], {})
                                                        and same(chain['second']['head'], head_of(j2)) and len(j2) == 5),
            'a_journal_without_the_one_it_continues_is_refused': lambda: said['without_the_first'] == WITHOUT and said['after_a_first_that_is_not_closed'] == NOT_CLOSED,
            'a_pack_id_passes_once_across_the_chain': lambda: said['pack_again'] == ONCE.format('"03_approval"') and '03_approval' in pack_ids([j1]),
        },
        'S98': {   # C9: the record read back without the kernel
            'the_ledger_rows_are_made_again_from_the_text': lambda: same(restart['ledger'], ledger([main], sha)) and same(chain['ledger'], ledger([j1, j2], sha)),
            'the_counts_are_made_again_from_the_text': lambda: (same(restart['counts'], counts([main])) and same(chain['counts'], counts([j1, j2])) and same(chain['counts_after_first'], counts([j1]))),
            'every_count_cites_its_entries_by_number_and_hash': lambda: cited(restart['counts'], [main]) and cited(chain['counts'], [j1, j2]),
            'handed_in_asked_decided_and_ran_are_all_there': lambda: (same([[r['what'] for r in restart['ledger']].count(w) for w in ('handed_in', 'asked', 'decided', 'ran')], [5, 1, 1, 4])
                                                                      and all(r['sha256'] == main[r['entry']]['sha256'] for r in restart['ledger'])
                                                                      and same([r['asked_at'] for r in restart['ledger'] if r['what'] == 'decided'], [{'journal': main[0]['sha256'][:12], 'entry': 6, 'sha256': main[6]['sha256'], 'run': main[0]['sha256'][:12] + ':6.0'}])),
            'counted_by_entry_and_never_by_trace_root': lambda: (same(chain['counts']['steps'][step]['ran'], 2) and [(a['journal'], a['entry']) for a in chain['counts']['steps'][step]['at']] == [(j1[0]['sha256'][:12], 6), (j2[0]['sha256'][:12], 2)]
                                                                 and same([chain['counts']['goals'][goal]['looked'], len(chain['counts']['goals'][goal]['trace_roots'])], [5, 2])
                                                                 and len({b['trace_root_sha256'] for x in (j1, j2) for e in x for b in e['result'].get('briefs', [])}) == 2),
            'the_counts_as_of_an_earlier_head': lambda: (same(restart['counts_at_first'], counts([main[:7]])) and list(restart['counts_at_first']['steps']) == [SCOPE + '|' + receipt['method']]
                                                         and same(restart['counts_at_first']['goals'][goal]['looked'], 1) and same(chain['counts_after_first']['steps'][step]['ran'], 1)),
        },
    }
    got = {}
    for number, each in tests.items():
        if only in (None, number):
            got[number] = {}
            for name, test in each.items():
                try:
                    got[number][name] = test() is True
                except Exception:
                    got[number][name] = False
    return got


def rewrite(holder, change, sha, text='text', head='head', chain=True):
    """What a forger can do without any secret: change entries of a kept text, hash the chain again, and move the head."""
    entries = [json.loads(line) for line in holder[text].split('\n')[:-1]]
    change(entries)
    prev = 'GENESIS'
    for n, e in enumerate(entries):
        if chain:
            e.update(seq=n, prev_sha256=prev)
            e['sha256'] = sha({k: e[k] for k in COVERED})
        prev = e['sha256']
    holder[text] = ''.join(dumps(e) + '\n' for e in entries)
    if chain and head:
        holder[head] = {'length': len(entries), 'sha256': prev}


def forgeries(sha, kernel_file):
    """(the check, the test that must refuse it, the forgery). A forgery gets a copy of what these checks read of the record."""
    scene = lambda d, name: d['scenes']['journal_' + name]
    restart, refusals, chain = (lambda d: scene(d, 'restart')), (lambda d: scene(d, 'refusals')), (lambda d: scene(d, 'chain'))
    tampered = lambda d, what: [t for t in refusals(d)['tampered'] if t['what'] == what][0]
    past, writers, once, outside = (lambda d: refusals(d)['past_the_head']), (lambda d: refusals(d)['second_writer']), (lambda d: refusals(d)['pack_twice']), (lambda d: refusals(d)['outside'])
    more, no, alone, marks = (lambda d: restart(d)['one_dry_look_more']), (lambda d: restart(d)['no']), (lambda d: restart(d)['from_packs_alone']), (lambda d: restart(d)['line_marks'])
    late, first, second = (lambda d: chain(d)['late_writer']), (lambda d: chain(d)['first']), (lambda d: chain(d)['second'])
    r0 = lambda step: step['result']['runs'][0]
    line = lambda holder, at, text='text': json.loads(holder[text].split('\n')[at])
    flip = lambda text, at: text[:at] + ('0' if text[at] != '0' else '1') + text[at + 1:]   # one character of a text changed
    tail = lambda holder, more_text, text='text': holder.update({text: holder[text] + more_text})   # something standing after the last entry of a kept text
    goal, step = SCOPE + '|order_complete', SCOPE + '|' + SHIP

    def remake(d, change):   # the restart journal re-made by a forger, with every head and every copy the record keeps of it
        r = restart(d)
        rewrite(r, change, sha)
        r['twin_head'], r['twin_text'] = dict(r['head']), r['text']
        r['head_after_first'] = r['restarted']['head'] = {'length': 7, 'sha256': line(r, 6)['sha256']}

    def rewrote(d, change):   # the two writers' journal re-made by a forger, with every head and every copy the record keeps of it
        w = writers(d)
        rewrite(w, change, sha)
        w['first']['head'] = w['second']['kept_head'] = w['again']['restarted_at'] = {'length': 8, 'sha256': line(w, 7)['sha256']}
        w['second']['kept_text'] = ''.join(x + '\n' for x in w['text'].split('\n')[:8])

    def second_ask(es):   # the question sent a second time by the look after the restart
        es[7]['result']['briefs'][0]['receipts'] = [dict(es[6]['result']['briefs'][0]['receipts'][0])]

    def restray(d, old, new):   # the entry that stands past the head, one field of it changed and nothing hashed again
        p = past(d)
        got = p['text'].split('\n')
        got[7] = got[7].replace(old, new, 1)
        p['text'] = '\n'.join(got)

    def another_question(es, at):   # the receipt an answer presents, with another question in it
        es[at]['body']['receipt']['ask'].update(question='Another question?')

    def later_entry(es):   # one more look, chained on after the closing entry
        es.append(json.loads(json.dumps(es[6])))

    return [
        # S90: whole, in order, on its head
        ('S90', 'every_kept_text_reads_to_its_head_and_nothing_stands_after_it', lambda d: rewrite(restart(d), lambda es: es[7]['body'].update(execute=False), sha, chain=False)),      # an entry changed, the chain left as it was
        ('S90', 'every_kept_text_reads_to_its_head_and_nothing_stands_after_it', lambda d: rewrite(restart(d), lambda es: es.pop(3), sha, chain=False)),
        ('S90', 'every_kept_text_reads_to_its_head_and_nothing_stands_after_it', lambda d: restart(d).update(text=restart(d)['text'].replace('"kind":"look"', '"kind": "look"', 1))),   # not the text the journal writes
        ('S90', 'every_kept_text_reads_to_its_head_and_nothing_stands_after_it', lambda d: second(d)['head'].update(length=4)),                                              # a head that names fewer entries and the last one's hash
        ('S90', 'every_kept_text_reads_to_its_head_and_nothing_stands_after_it', lambda d: tail(restart(d), 'x')),                                                           # one character after the last entry
        ('S90', 'every_kept_text_reads_to_its_head_and_nothing_stands_after_it', lambda d: tail(restart(d), restart(d)['text'].split('\n')[8] + '\n')),                      # one more whole entry after the head
        ('S90', 'every_kept_text_reads_to_its_head_and_nothing_stands_after_it', lambda d: tail(writers(d), '{"torn')),
        ('S90', 'every_kept_text_reads_to_its_head_and_nothing_stands_after_it', lambda d: tail(restart(d), 'x', 'twin_text')),
        ('S90', 'every_kept_text_reads_to_its_head_and_nothing_stands_after_it', lambda d: tail(writers(d)['second'], 'x', 'kept_text')),
        ('S90', 'every_kept_text_reads_to_its_head_and_nothing_stands_after_it', lambda d: tail(once(d)['holds_it_twice'], 'x')),
        ('S90', 'every_kept_text_reads_to_its_head_and_nothing_stands_after_it', lambda d: [tail(h, 'x') for h in (no(d), more(d), marks(d), refusals(d), once(d), first(d), second(d))]),
        ('S90', 'every_kept_text_reads_to_its_head_and_nothing_stands_after_it', lambda d: tail(past(d), 'x', 'text_after_save')),
        ('S90', 'every_kept_text_reads_to_its_head_and_nothing_stands_after_it', lambda d: rewrite(first(d), later_entry, sha)),                                             # an entry after the closing entry, the chain made again
        ('S90', 'every_entry_holds_the_keys_of_its_kind', lambda d: remake(d, lambda es: es[7]['body'].update(note='x'))),                                   # a key the look door does not take
        ('S90', 'every_entry_holds_the_keys_of_its_kind', lambda d: remake(d, lambda es: es[7]['body'].update(execute=1))),
        ('S90', 'every_entry_holds_the_keys_of_its_kind', lambda d: remake(d, lambda es: es[4]['result']['providers'].update({'local-provider': 5.0}))),
        ('S90', 'every_entry_holds_the_keys_of_its_kind', lambda d: remake(d, lambda es: es[0]['body'].update(schema='journal/2'))),
        ('S90', 'every_entry_holds_the_keys_of_its_kind', lambda d: remake(d, lambda es: es[9]['result'].update(kernel=kernel_file))),
        ('S90', 'every_entry_holds_the_keys_of_its_kind', lambda d: rewrite(first(d), lambda es: es[7]['body'].update(note='x'), sha)),                      # a key the close door does not take
        ('S90', 'every_entry_holds_the_keys_of_its_kind', lambda d: rewrite(first(d), lambda es: es[7]['body']['next'].pop('checkers'), sha)),
        ('S90', 'every_entry_holds_the_keys_of_its_kind', lambda d: rewrite(first(d), lambda es: es[7]['result'].update(status='CLOSED'), sha)),
        ('S90', 'ten_tampered_texts_are_on_record', lambda d: refusals(d)['tampered'].pop(1)),
        ('S90', 'ten_tampered_texts_are_on_record', lambda d: tampered(d, 'an entry changed').update(text=refusals(d)['text'])),                            # the kept text itself, said to be refused
        ('S90', 'each_is_the_kept_text_changed_in_the_way_it_says', lambda d: tampered(d, 'an entry changed').update(text=flip(tampered(d, 'an entry changed')['text'], -4))),   # one more character changed, past the entry that breaks
        ('S90', 'each_is_the_kept_text_changed_in_the_way_it_says', lambda d: tampered(d, 'an entry changed').update(text=tampered(d, 'an entry changed')['text'].replace('someone-else', 'someone else'))),   # changed in another way than it says
        ('S90', 'each_is_the_kept_text_changed_in_the_way_it_says', lambda d: tampered(d, 'two entries swapped').update(text=refusals(d)['text'].replace('"seq":2,', '"seq":3,', 1))),   # an entry renumbered, said to be a swap
        ('S90', 'each_is_the_kept_text_changed_in_the_way_it_says', lambda d: tampered(d, 'a head that names another hash')['head'].update(sha256='0' * 64)),
        ('S90', 'each_is_the_kept_text_changed_in_the_way_it_says', lambda d: tail(tampered(d, 'cut short'), 'x')),                                         # something after a tampered text
        ('S90', 'each_is_the_kept_text_changed_in_the_way_it_says', lambda d: tail(tampered(d, 'no head'), '{"torn')),
        ('S90', 'each_is_the_kept_text_changed_in_the_way_it_says', lambda d: tail(tampered(d, 're-chained by a forger'), 'x')),
        ('S90', 'each_is_the_kept_text_changed_in_the_way_it_says', lambda d: tampered(d, 're-chained by a forger').update(text=flip(tampered(d, 're-chained by a forger')['text'], -80))),
        ('S90', 'each_is_the_kept_text_changed_in_the_way_it_says', lambda d: tampered(d, 'an entry that nests a thousand deep').update(text=tampered(d, 'an entry that nests a thousand deep')['text'].replace('[]', '[0]'))),
        ('S90', 'a_text_cut_short_is_refused', lambda d: tampered(d, 'cut short').update(refused='The journal ends before its head: 5 entries, the head names 7')),
        ('S90', 'a_text_cut_short_is_refused', lambda d: tampered(d, 'an entry dropped').update(refused=None)),
        ('S90', 'a_changed_dropped_doubled_or_swapped_entry_is_refused_by_number', lambda d: tampered(d, 'an entry changed').update(refused='The journal is broken at entry 4')),
        ('S90', 'a_changed_dropped_doubled_or_swapped_entry_is_refused_by_number', lambda d: tampered(d, 'two entries swapped').update(refused=None)),
        ('S90', 'a_changed_dropped_doubled_or_swapped_entry_is_refused_by_number', lambda d: tampered(d, 'an entry doubled').update(refused='The journal does not end on the hash its head names')),
        ('S90', 'a_line_no_reader_can_take_apart_is_a_broken_entry_by_number', lambda d: tampered(d, 'an entry that nests a thousand deep').update(refused=None)),              # taken for a failure of the process: no refusal on record
        ('S90', 'a_line_no_reader_can_take_apart_is_a_broken_entry_by_number', lambda d: tampered(d, 'an entry that nests a thousand deep').update(refused='The journal is broken at entry 4')),
        ('S90', 'a_line_no_reader_can_take_apart_is_a_broken_entry_by_number', lambda d: tampered(d, 'an entry that nests a thousand deep').update(text=refusals(d)['text'].replace('"seq":3,', '"seq":3 ,', 1))),   # another broken line, said to be the deep one
        ('S90', 'a_head_for_another_hash_is_refused', lambda d: tampered(d, 'a head that names another hash').update(refused='The journal is broken at entry 6')),
        ('S90', 'no_head_no_restart', lambda d: tampered(d, 'no head').update(refused=None)),
        ('S90', 'no_head_no_restart', lambda d: tampered(d, 'no head').update(head={'length': 7, 'sha256': '0' * 64})),
        ('S90', 'an_entry_past_the_head_is_reported', lambda d: past(d).update(cut=0)),
        ('S90', 'an_entry_past_the_head_is_reported', lambda d: past(d).update(head={'length': 8, 'sha256': line(past(d), 7)['sha256']})),                    # the stray entry said to be under the head
        ('S90', 'an_entry_past_the_head_is_reported', lambda d: tail(past(d), 'x')),                                                                         # and something more after it
        ('S90', 'an_entry_past_the_head_is_reported', lambda d: restray(d, '"truth":"TRUE"', '"truth":"FALSE"')),                                             # one field of the stray entry changed, its hash left as it was
        ('S90', 'an_entry_past_the_head_is_reported', lambda d: restray(d, '"money":8', '"money":9')),
        ('S90', 'an_entry_past_the_head_is_reported', lambda d: rewrite(past(d), lambda es: es[7]['body'].update(source='someone-else'), sha, head=None)),    # the stray yes from another party, hashed again
        ('S90', 'an_entry_past_the_head_is_reported', lambda d: rewrite(past(d), lambda es: es[7]['result']['budget'].update(money=10), sha, head=None)),     # the stray yes that paid nothing, hashed again
        ('S90', 'an_entry_past_the_head_is_reported', lambda d: r0(past(d)['writer']).update(status='REFUSED')),
        ('S90', 'and_is_never_run', lambda d: r0(past(d)['look']).update(status='LOCAL_MODEL_EFFECTS_RECORDED')),
        ('S90', 'and_is_never_run', lambda d: past(d)['after_restart']['open_asks'].clear()),                                                              # the stray yes took effect after all
        ('S90', 'and_is_cut_by_the_next_save', lambda d: rewrite(past(d), lambda es: es.__setitem__(7, line(past(d), 7)), sha, 'text_after_save', 'head_after_save')),   # the stray yes kept after all
        ('S90', 'a_line_mark_cuts_no_entry', lambda d: marks(d).update(question_after_restart='May we send a replacement?')),
        ('S90', 'a_line_mark_cuts_no_entry', lambda d: marks(d).update(state_after_restart='0' * 64)),
        # S91: the same journal, the same answer
        ('S91', 'the_walk_is_the_journal', lambda d: restart(d)['again'].update(entry=8)),
        ('S91', 'the_walk_is_the_journal', lambda d: restart(d)['packs'].pop()),
        ('S91', 'process_one_asks_and_stops', lambda d: restart(d)['after_first']['budget'].update(attention=3)),
        ('S91', 'process_one_asks_and_stops', lambda d: r0(restart(d)['first']).update(pending=[])),
        ('S91', 'after_the_restart_the_question_is_still_out', lambda d: restart(d)['restarted']['after']['open_asks'].clear()),                             # the question forgotten
        ('S91', 'after_the_restart_the_question_is_still_out', lambda d: restart(d)['restarted'].update(cut=1)),
        ('S91', 'after_the_restart_the_question_is_still_out', lambda d: restart(d)['restarted'].update(state='0' * 64)),
        ('S91', 'the_look_waits_runs_nothing_and_charges_nothing', lambda d: restart(d)['after_again']['budget'].update(attention=1)),                       # charged again
        ('S91', 'the_look_waits_runs_nothing_and_charges_nothing', lambda d: r0(restart(d)['again']).update(waits=[])),
        ('S91', 'the_answer_presents_that_receipt_and_the_plan_goes_on', lambda d: remake(d, lambda es: es[8]['body'].update(source='someone-else'))),       # an answer from another party
        ('S91', 'the_answer_presents_that_receipt_and_the_plan_goes_on', lambda d: remake(d, lambda es: es[8]['body']['receipt'].update(sha256='0' * 64))),  # an answer to another receipt
        ('S91', 'asked_once_and_charged_once_in_the_whole_journal', lambda d: remake(d, second_ask)),
        ('S91', 'it_ends_on_the_text_and_the_head_of_a_twin_that_never_stopped', lambda d: restart(d)['twin_head'].update(sha256='0' * 64)),
        ('S91', 'it_ends_on_the_text_and_the_head_of_a_twin_that_never_stopped', lambda d: restart(d).update(twin_text=text_of(restart(d)['twin_text'].split('\n')[:9]))),   # the twin's text one entry short
        ('S91', 'it_ends_on_the_text_and_the_head_of_a_twin_that_never_stopped', lambda d: tail(restart(d), restart(d)['text'].split('\n')[8] + '\n')),                       # a text that is not the twin's: one more entry stands in it
        ('S91', 'it_ends_on_the_text_and_the_head_of_a_twin_that_never_stopped', lambda d: rewrite(restart(d), lambda es: es[9]['body'].update(execute=False), sha)),        # the last look said to have been dry: another journal than the twin's
        ('S91', 'from_the_packs_alone_the_receipt_is_refused', lambda d: alone(d).update(answer_refused=None)),
        ('S91', 'from_the_packs_alone_the_receipt_is_refused', lambda d: alone(d)['after_refusal']['budget'].update(compute=8, money=8)),
        ('S91', 'and_the_customer_is_asked_and_charged_again', lambda d: alone(d)['after_look']['budget'].update(attention=3)),
        ('S91', 'and_the_customer_is_asked_and_charged_again', lambda d: alone(d)['look']['runs'][0]['model_receipts'][0]['ask'].update(question='Another question?')),
        ('S91', 'one_dry_look_more_is_another_receipt_under_the_same_packs', lambda d: r0(more(d)['look'])['provenance'].pop()),
        ('S91', 'one_dry_look_more_is_another_receipt_under_the_same_packs', lambda d: more(d)['after_dry']['budget'].update(attention=2)),                  # the dry look charged
        ('S91', 'one_dry_look_more_is_another_receipt_under_the_same_packs', lambda d: more(d).update(text=restart(d)['text'], head=dict(restart(d)['head']))),   # the journal without the dry look, said to be the one with it
        ('S91', 'which_the_first_receipt_does_not_answer', lambda d: more(d).update(first_receipt_refused=None)),
        ('S91', 'which_the_first_receipt_does_not_answer', lambda d: rewrite(more(d), lambda es: es[8]['body'].update(receipt=line(restart(d), 6)['result']['briefs'][0]['receipts'][0]), sha)),   # answered with the first receipt after all
        # S92: decided and ran
        ('S92', 'the_no_is_an_entry', lambda d: rewrite(no(d), lambda es: es[7]['body'].update(truth='TRUE'), sha)),
        ('S92', 'the_no_is_an_entry', lambda d: no(d)['look'].update(entry=7)),
        ('S92', 'after_a_restart_it_reads_refused_and_nothing_is_paid', lambda d: r0(no(d)['look']).update(status='WAITING')),
        ('S92', 'after_a_restart_it_reads_refused_and_nothing_is_paid', lambda d: no(d)['after_look']['budget'].update(compute=8, money=8)),
        ('S92', 'a_later_yes_is_refused_and_leaves_no_entry', lambda d: no(d).update(later_yes_refused=None)),
        ('S92', 'a_later_yes_is_refused_and_leaves_no_entry', lambda d: no(d)['head'].update(length=10)),
        ('S92', 'from_the_packs_alone_the_no_is_forgotten_and_a_yes_ships', lambda d: no(d)['from_packs_alone']['answered_yes']['runs'][0].update(status='REFUSED')),
        ('S92', 'what_ran_is_not_run_or_paid_again', lambda d: r0(restart(d)['later']).update(status='LOCAL_MODEL_EFFECTS_RECORDED')),
        ('S92', 'what_ran_is_not_run_or_paid_again', lambda d: restart(d)['after_later']['budget'].update(money=6)),
        ('S92', 'what_ran_is_not_run_or_paid_again', lambda d: r0(chain(d)['restarted']['look']).update(model_receipts=[dict(r0(first(d)['look'])['model_receipts'][0])])),
        ('S92', 'from_the_packs_alone_it_runs_and_is_paid_again', lambda d: chain(d)['from_packs_alone']['look']['runs'][0].update(status='SUPPORTED_BY_EVIDENCE')),
        ('S92', 'from_the_packs_alone_it_runs_and_is_paid_again', lambda d: chain(d)['from_packs_alone']['after']['budget'].update(money=10)),
        # S93: the books computed again, the briefs held to the recorded runs
        ('S93', 'the_books_follow_from_the_packs_and_the_receipts', lambda d: remake(d, lambda es: es[8]['result']['budget'].update(money=10))),             # the shipment not paid
        ('S93', 'the_books_follow_from_the_packs_and_the_receipts', lambda d: remake(d, lambda es: es[6]['result']['budget'].update(attention=3))),          # the question not charged
        ('S93', 'the_books_follow_from_the_packs_and_the_receipts', lambda d: remake(d, lambda es: es[8]['result']['providers'].update({'local-provider': 5}))),
        ('S93', 'the_books_follow_from_the_packs_and_the_receipts', lambda d: rewrite(second(d), lambda es: es[2]['result']['budget'].update(money=8), sha)),
        ('S93', 'the_books_follow_from_the_packs_and_the_receipts', lambda d: rewrite(first(d), lambda es: es[7]['result']['budget'].update(money=10), sha)),   # the closing entry said to have put the levels back
        ('S93', 'every_pack_entry_is_its_scenario_file', lambda d: remake(d, lambda es: es[3]['body']['pack']['methods'][1]['cost'].update(money=0))),      # a pack that is not its file
        ('S93', 'every_pack_entry_is_its_scenario_file', lambda d: remake(d, lambda es: es[5]['body']['pack']['methods'][0].update(ask_to='someone-else'))),
        ('S93', 'every_brief_is_the_run_the_kernel_returned', lambda d: remake(d, lambda es: es[8]['result']['briefs'][0].update(trace_root_sha256='0' * 64))),
        ('S93', 'every_brief_is_the_run_the_kernel_returned', lambda d: remake(d, lambda es: es[9]['result']['briefs'][0].update(status='LOCAL_MODEL_EFFECTS_RECORDED'))),
        ('S93', 'every_brief_is_the_run_the_kernel_returned', lambda d: r0(restart(d)['answered_yes']).update(cost={'compute': 0, 'money': 0, 'attention': 0})),
        ('S93', 'every_brief_is_the_run_the_kernel_returned', lambda d: restart(d)['answered_yes']['result']['event'].update(source='STAMP:someone-else')),   # the stamp said to be another party's
        ('S93', 'every_brief_is_the_run_the_kernel_returned', lambda d: second(d)['came_back']['result']['event'].update(version='returned-2')),
        ('S93', 'every_brief_is_the_run_the_kernel_returned', lambda d: rewrote(d, lambda es: es[6]['result']['briefs'][0].update(status='PLAN_READY'))),     # the look that asked, in the two writers' journal: another status
        ('S93', 'every_brief_is_the_run_the_kernel_returned', lambda d: rewrote(d, lambda es: es[6]['result']['briefs'][0].update(trace_root_sha256='0' * 64))),
        ('S93', 'every_brief_is_the_run_the_kernel_returned', lambda d: rewrote(d, lambda es: es[6]['result']['briefs'][0].pop('pending'))),
        ('S93', 'every_brief_is_the_run_the_kernel_returned', lambda d: rewrote(d, lambda es: es[6]['result'].update(goals=[]))),
        ('S93', 'every_brief_is_the_run_the_kernel_returned', lambda d: rewrite(past(d), lambda es: es[6]['result']['briefs'][0].update(work_state='ready'), sha, 'text_after_save', 'head_after_save')),
        ('S93', 'every_brief_is_the_run_the_kernel_returned', lambda d: r0(refusals(d)['look']).update(actions=[])),
        ('S93', 'every_look_event_and_answer_entry_has_its_recorded_run_and_was_taken_as_the_sequence_took_it', lambda d: refusals(d).pop('look')),           # the look that asked, with no run on record
        ('S93', 'every_look_event_and_answer_entry_has_its_recorded_run_and_was_taken_as_the_sequence_took_it', lambda d: remake(d, lambda es: es[7]['body'].update(execute=False))),   # the look that waited, said to have been dry
        ('S93', 'every_look_event_and_answer_entry_has_its_recorded_run_and_was_taken_as_the_sequence_took_it', lambda d: rewrite(second(d), lambda es: es[4]['body'].update(execute=False), sha)),
        ('S93', 'every_look_event_and_answer_entry_has_its_recorded_run_and_was_taken_as_the_sequence_took_it', lambda d: rewrite(no(d), lambda es: es[8]['body'].update(execute=False), sha)),
        ('S93', 'every_look_event_and_answer_entry_has_its_recorded_run_and_was_taken_as_the_sequence_took_it', lambda d: rewrite(more(d), lambda es: es[6]['body'].update(execute=True), sha)),   # the dry look said to have executed
        ('S93', 'every_look_event_and_answer_entry_has_its_recorded_run_and_was_taken_as_the_sequence_took_it', lambda d: rewrite(second(d), lambda es: es.append(dict(json.loads(json.dumps(es[4])))), sha)),   # one more look in the journal than the sequence took
        ('S93', 'every_snapshot_is_the_books_its_entry_states', lambda d: second(d)['after_look']['budget'].update(compute=10, money=10)),                    # the second journal said to start from the packs' levels
        ('S93', 'every_snapshot_is_the_books_its_entry_states', lambda d: once(d)['after_levels']['budget'].update(compute=8, money=8)),
        ('S93', 'every_snapshot_is_the_books_its_entry_states', lambda d: chain(d)['restarted']['after_look']['providers'].update({'local-provider': 5})),
        ('S93', 'every_snapshot_is_the_books_its_entry_states', lambda d: late(d)['after_step']['providers'].update({'local-provider': 4})),
        ('S93', 'what_the_kernel_returned_outside_a_journal_is_what_was_handed_in', lambda d: alone(d)['answered_yes']['event'].update(answers='0' * 64)),
        ('S93', 'what_the_kernel_returned_outside_a_journal_is_what_was_handed_in', lambda d: writers(d)['second']['step']['result'].update(affected=[])),
        ('S93', 'what_the_kernel_returned_outside_a_journal_is_what_was_handed_in', lambda d: once(d)['kernel_alone']['came_back'].update(status='DECISION_STANDS')),
        ('S93', 'what_the_kernel_returned_outside_a_journal_is_what_was_handed_in', lambda d: late(d)['step']['result']['event'].update(truth='TRUE')),
        ('S93', 'every_journal_is_of_the_name_kinds_checkers_and_packs_its_sequence_gives', lambda d: refusals(d)['packs'].pop()),
        ('S93', 'every_journal_is_of_the_name_kinds_checkers_and_packs_its_sequence_gives', lambda d: restart(d)['kinds'].reverse()),
        ('S93', 'every_journal_is_of_the_name_kinds_checkers_and_packs_its_sequence_gives', lambda d: chain(d)['checkers'].append('the-hand')),
        ('S93', 'every_journal_is_of_the_name_kinds_checkers_and_packs_its_sequence_gives', lambda d: remake(d, lambda es: es[0]['body'].update(name='another'))),            # a header under another name
        ('S93', 'every_journal_is_of_the_name_kinds_checkers_and_packs_its_sequence_gives', lambda d: rewrite(marks(d), lambda es: es[0]['body'].update(name='restart'), sha)),
        ('S93', 'every_journal_is_of_the_name_kinds_checkers_and_packs_its_sequence_gives', lambda d: rewrite(once(d), lambda es: es[0]['body'].pop('name'), sha)),
        ('S93', 'every_journal_is_of_the_name_kinds_checkers_and_packs_its_sequence_gives', lambda d: rewrote(d, lambda es: es[0]['body'].update(checkers=[]))),              # the checker of the second writer's row taken out of the header
        ('S93', 'every_journal_is_of_the_name_kinds_checkers_and_packs_its_sequence_gives', lambda d: rewrite(first(d), lambda es: es[0]['body'].update(name='orders-0'), sha)),
        ('S93', 'a_journal_re_chained_by_a_forger_is_refused_where_its_books_break', lambda d: tampered(d, 're-chained by a forger').update(refused='The journal does not replay at entry 5: the result differs (budget)')),
        ('S93', 'a_journal_re_chained_by_a_forger_is_refused_where_its_books_break', lambda d: tampered(d, 're-chained by a forger').update(text=refusals(d)['text'], head=dict(refusals(d)['head']))),
        # S94: one writer
        ('S94', 'two_runs_start_from_one_head', lambda d: writers(d)['base'].update(length=6)),
        ('S94', 'the_first_save_is_taken', lambda d: writers(d)['first']['head'].update(length=9)),
        ('S94', 'the_first_save_is_taken', lambda d: r0(writers(d)['first']['step']).update(status='WAITING')),
        ('S94', 'the_second_save_is_refused', lambda d: writers(d)['second'].update(refused=None)),
        ('S94', 'the_second_save_is_refused', lambda d: writers(d)['second'].update(refused=MOVED.format(7))),
        ('S94', 'and_changes_nothing_that_is_kept', lambda d: writers(d)['second'].update(kept_head=dict(refusals(d)['head']))),
        ('S94', 'and_changes_nothing_that_is_kept', lambda d: writers(d)['second'].update(kept_text=refusals(d)['text'])),                                    # what was kept before the first writer, said to be kept after the refusal
        ('S94', 'and_changes_nothing_that_is_kept', lambda d: writers(d)['second'].update(kept_text=writers(d)['text'], kept_head=dict(writers(d)['head']))),   # the refused writer's row kept after all
        ('S94', 'and_changes_nothing_that_is_kept', lambda d: tail(writers(d)['second'], writers(d)['text'].split('\n')[8] + '\n', 'kept_text')),
        ('S94', 'and_changes_nothing_that_is_kept', lambda d: r0(writers(d)['second']['step']).update(trace_root_sha256=r0(writers(d)['again']['step'])['trace_root_sha256'])),   # the refused writer's run kept after all
        ('S94', 'the_loser_replays_and_acts_on_what_the_first_wrote', lambda d: writers(d)['again'].update(restarted_at=dict(refusals(d)['head']))),
        ('S94', 'the_loser_replays_and_acts_on_what_the_first_wrote', lambda d: writers(d)['again'].update(later_yes_refused=None)),
        ('S94', 'the_loser_replays_and_acts_on_what_the_first_wrote', lambda d: r0(writers(d)['again']['step']).update(status='WAITING')),
        # S95: the doors
        ('S95', 'a_pack_id_enters_a_journal_once', lambda d: rewrite(once(d), lambda es: es.append(json.loads(json.dumps(es[7]))), sha)),                    # the kept journal holds the level pack twice
        ('S95', 'the_level_pack_is_let_in_once_and_refused_the_second_time', lambda d: once(d).update(refused=None)),
        ('S95', 'the_level_pack_is_let_in_once_and_refused_the_second_time', lambda d: once(d)['after_refusal']['budget'].update(compute=10, money=10)),     # the levels were restated a second time
        ('S95', 'the_kernel_alone_takes_it_twice', lambda d: once(d)['kernel_alone']['loaded'].pop()),
        ('S95', 'the_kernel_alone_takes_it_twice', lambda d: once(d)['kernel_alone']['loaded'].__setitem__(0, '00_goals')),
        ('S95', 'the_kernel_alone_takes_it_twice', lambda d: once(d)['kernel_alone']['budgets'][3].update(money=8)),
        ('S95', 'the_kernel_alone_takes_it_twice', lambda d: [c for c in d['cases'] if c['id'] == '60_pack_twice'][0]['outcome']['provenance'].pop()),
        ('S95', 'a_journal_that_holds_it_twice_does_not_replay', lambda d: once(d)['holds_it_twice'].update(refused='The journal does not replay at entry 7: ' + ONCE.format('"140_levels_restated"'))),
        ('S95', 'a_journal_that_holds_it_twice_does_not_replay', lambda d: once(d)['holds_it_twice'].update(text=once(d)['text'], head=dict(once(d)['head']))),   # the journal that holds it once, said to be refused
        ('S95', 'a_journal_that_holds_it_twice_does_not_replay', lambda d: rewrite(once(d)['holds_it_twice'], lambda es: es[9]['result']['budget'].update(money=8), sha)),   # the second hand-over said to have left the levels as they were
        ('S95', 'a_journal_that_holds_it_twice_does_not_replay', lambda d: rewrite(once(d)['holds_it_twice'], lambda es: es[0]['body'].update(checkers=[]), sha)),
        ('S95', 'every_event_row_is_verified_and_comes_from_a_checker_its_header_names', lambda d: rewrote(d, lambda es: es[0]['body'].update(checkers=[]))),            # the header names no checker, and a row came in
        ('S95', 'every_event_row_is_verified_and_comes_from_a_checker_its_header_names', lambda d: rewrite(once(d), lambda es: es[0]['body'].update(checkers=[]), sha)),
        ('S95', 'every_event_row_is_verified_and_comes_from_a_checker_its_header_names', lambda d: rewrite(second(d), lambda es: es[0]['body'].update(checkers=['fixture/stock-recount']), sha)),   # the second journal names another checker than the one its row came from
        ('S95', 'every_event_row_is_verified_and_comes_from_a_checker_its_header_names', lambda d: rewrote(d, lambda es: es[8]['body']['row'].update(source='the-hand'))),
        ('S95', 'every_event_row_is_verified_and_comes_from_a_checker_its_header_names', lambda d: rewrite(once(d), lambda es: es[8]['body']['row'].update(verified=False), sha)),
        ('S95', 'every_event_row_is_verified_and_comes_from_a_checker_its_header_names', lambda d: rewrite(second(d), lambda es: es[2]['body']['row'].update(final=True), sha)),   # a decision let in at the event door
        ('S95', 'every_answer_presents_the_receipt_of_a_question_that_is_out_and_comes_from_the_party_asked', lambda d: remake(d, lambda es: es[8]['body'].update(source='someone-else'))),
        ('S95', 'every_answer_presents_the_receipt_of_a_question_that_is_out_and_comes_from_the_party_asked', lambda d: remake(d, lambda es: another_question(es, 8))),
        ('S95', 'every_answer_presents_the_receipt_of_a_question_that_is_out_and_comes_from_the_party_asked', lambda d: rewrite(no(d), lambda es: es[7]['body'].update(source='someone-else'), sha)),
        ('S95', 'every_answer_presents_the_receipt_of_a_question_that_is_out_and_comes_from_the_party_asked', lambda d: rewrite(no(d), lambda es: es[7]['body']['receipt'].update(scope='orgB/fulfillment'), sha)),
        ('S95', 'every_answer_presents_the_receipt_of_a_question_that_is_out_and_comes_from_the_party_asked', lambda d: rewrite(more(d), lambda es: es[8]['body'].update(source='owner'), sha)),
        ('S95', 'every_answer_presents_the_receipt_of_a_question_that_is_out_and_comes_from_the_party_asked', lambda d: rewrite(more(d), lambda es: es[8]['body']['receipt']['ask'].update(asked_in='0' * 64), sha)),
        ('S95', 'every_answer_presents_the_receipt_of_a_question_that_is_out_and_comes_from_the_party_asked', lambda d: rewrote(d, lambda es: es[7]['body'].update(source='someone-else'))),
        ('S95', 'every_answer_presents_the_receipt_of_a_question_that_is_out_and_comes_from_the_party_asked', lambda d: rewrote(d, lambda es: another_question(es, 7))),
        ('S95', 'every_answer_presents_the_receipt_of_a_question_that_is_out_and_comes_from_the_party_asked', lambda d: rewrote(d, lambda es: es[7]['body']['receipt'].update(parked=False))),
        ('S95', 'every_answer_presents_the_receipt_of_a_question_that_is_out_and_comes_from_the_party_asked', lambda d: remake(d, lambda es: es.insert(9, json.loads(json.dumps(es[8]))))),   # the same receipt answered a second time
        ('S95', 'an_entry_that_ran_skipped_or_stopped_a_step_was_taken_with_execute_true', lambda d: remake(d, lambda es: es[6]['body'].update(execute=False))),          # the look that asked, said to have been dry
        ('S95', 'an_entry_that_ran_skipped_or_stopped_a_step_was_taken_with_execute_true', lambda d: remake(d, lambda es: es[8]['body'].update(execute=False))),          # the yes that shipped, said not to have executed
        ('S95', 'an_entry_that_ran_skipped_or_stopped_a_step_was_taken_with_execute_true', lambda d: rewrite(no(d), lambda es: es[6]['body'].update(execute=False), sha)),
        ('S95', 'an_entry_that_ran_skipped_or_stopped_a_step_was_taken_with_execute_true', lambda d: rewrite(more(d), lambda es: es[7]['body'].update(execute=False), sha)),
        ('S95', 'an_entry_that_ran_skipped_or_stopped_a_step_was_taken_with_execute_true', lambda d: rewrite(marks(d), lambda es: es[6]['body'].update(execute=False), sha)),
        ('S95', 'an_entry_that_ran_skipped_or_stopped_a_step_was_taken_with_execute_true', lambda d: rewrite(refusals(d), lambda es: es[6]['body'].update(execute=False), sha)),
        ('S95', 'an_entry_that_ran_skipped_or_stopped_a_step_was_taken_with_execute_true', lambda d: rewrite(past(d), lambda es: es[6]['body'].update(execute=False), sha, 'text_after_save', 'head_after_save')),
        ('S95', 'an_entry_that_ran_skipped_or_stopped_a_step_was_taken_with_execute_true', lambda d: rewrote(d, lambda es: es[6]['body'].update(execute=False))),
        ('S95', 'an_entry_that_ran_skipped_or_stopped_a_step_was_taken_with_execute_true', lambda d: rewrite(once(d), lambda es: es[6]['body'].update(execute=False), sha)),
        ('S95', 'an_entry_that_ran_skipped_or_stopped_a_step_was_taken_with_execute_true', lambda d: rewrite(once(d), lambda es: es[8]['body'].update(execute=False), sha)),
        ('S95', 'an_entry_that_ran_skipped_or_stopped_a_step_was_taken_with_execute_true', lambda d: rewrite(first(d), lambda es: es[6]['body'].update(execute=False), sha)),
        ('S95', 'an_entry_that_ran_skipped_or_stopped_a_step_was_taken_with_execute_true', lambda d: rewrite(second(d), lambda es: es[2]['body'].update(execute=False), sha)),
        ('S95', 'every_door_refuses_in_the_words_of_its_rule', lambda d: refusals(d)['doors'][0].update(refused=None)),
        ('S95', 'every_door_refuses_in_the_words_of_its_rule', lambda d: refusals(d)['doors'][0].update(refused='The look door takes exactly: execute')),
        ('S95', 'every_door_refuses_in_the_words_of_its_rule', lambda d: refusals(d)['doors'][5].update(refused=NO_ASK)),
        ('S95', 'every_door_refuses_in_the_words_of_its_rule', lambda d: refusals(d)['doors'][9].update(refused='The answer does not come from the party that was asked')),
        ('S95', 'every_door_refuses_in_the_words_of_its_rule', lambda d: refusals(d).update(doors=refusals(d)['doors'][:5])),
        ('S95', 'every_door_refuses_in_the_words_of_its_rule', lambda d: refusals(d)['doors'].pop(13)),                                                      # the one body of an unknown kind, gone from the record
        ('S95', 'every_door_refuses_in_the_words_of_its_rule', lambda d: refusals(d)['doors'].pop(14)),                                                      # the header, gone from the record
        ('S95', 'every_door_refuses_in_the_words_of_its_rule', lambda d: refusals(d)['doors'].pop(12)),
        ('S95', 'every_door_refuses_in_the_words_of_its_rule', lambda d: refusals(d)['doors'].pop()),                                                        # the closing entry that names other kinds, gone from the record
        ('S95', 'every_door_refuses_in_the_words_of_its_rule', lambda d: refusals(d)['doors'].reverse()),
        ('S95', 'every_door_refuses_in_the_words_of_its_rule', lambda d: refusals(d)['doors'][10]['body'].update(truth='MAYBE')),                             # an answer that is no answer, said to be refused for its party
        ('S95', 'every_door_refuses_in_the_words_of_its_rule', lambda d: refusals(d)['doors'][0]['body'].update(execute='no')),                               # another body than the one that was tried, refused by the same rule in the same words
        ('S95', 'every_door_refuses_in_the_words_of_its_rule', lambda d: refusals(d)['doors'][7]['body']['row'].update(version='3')),
        ('S95', 'every_door_refuses_in_the_words_of_its_rule', lambda d: refusals(d)['doors'][9]['body']['receipt']['ask'].update(to='nobody')),
        ('S95', 'every_door_refuses_in_the_words_of_its_rule', lambda d: refusals(d)['doors'][16]['body']['next'].update(kinds=['simulate_fact', 'ask'])),      # a closing entry that names the same kinds, said to be refused
        ('S95', 'and_the_refusals_change_nothing', lambda d: refusals(d)['after_doors']['head'].update(length=8)),
        ('S95', 'and_the_refusals_change_nothing', lambda d: refusals(d)['after_doors']['after']['open_asks'].clear()),
        ('S95', 'a_state_changed_outside_the_journal_is_refused_at_the_next_entry', lambda d: outside(d).update(refused=None)),
        ('S95', 'a_state_changed_outside_the_journal_is_refused_at_the_next_entry', lambda d: outside(d).update(entries=8)),
        ('S95', 'a_state_changed_outside_the_journal_is_refused_at_the_next_entry', lambda d: outside(d)['after_bypass']['providers'].update({'local-provider': 5})),
        ('S95', 'a_state_changed_outside_the_journal_is_refused_at_the_next_entry', lambda d: outside(d)['after_restart']['budget'].update(compute=8, money=8)),   # the bypass took effect after all
        # S96: what a head covers
        ('S96', 'the_code_is_stated_once_beside_the_entry_and_outside_its_hash', lambda d: rewrite(restart(d), lambda es: es[5].update(stated={'code': {}}), sha, chain=False)),
        ('S96', 'the_code_is_stated_once_beside_the_entry_and_outside_its_hash', lambda d: rewrite(restart(d), lambda es: es[0].pop('stated'), sha, chain=False)),
        ('S96', 'and_it_is_the_code_the_record_names', lambda d: rewrite(restart(d), lambda es: es[0]['stated']['code'].update({'kernel.core': '0' * 64}), sha, chain=False)),   # the statement is not true of the kernel the record names
        ('S96', 'and_it_is_the_code_the_record_names', lambda d: d['action_handlers']['ask'].update(sha256='0' * 64)),
        ('S96', 'and_it_is_the_code_the_record_names', lambda d: d.update(added={'files': {'extensions/journal.py': '0' * 64}})),                            # a record that lists another journal file than the one the entries state
        ('S96', 'and_it_is_the_code_the_record_names', lambda d: rewrite(first(d), lambda es: es[0]['stated']['code'].update({'extensions.journal': '1' * 64}), sha, chain=False)),   # two journals of one record under two journal files
        ('S96', 'a_restart_under_the_same_code_gives_no_notice', lambda d: restart(d)['restarted'].update(notice=[{'entry': 0, 'differs': ['kernel.core']}])),
        ('S96', 'no_file_hash_stands_under_a_head', lambda d: remake(d, lambda es: es[0]['body'].update(name=kernel_file))),                               # a file hash under the head
        ('S96', 'no_name_of_a_format_stands_under_a_head', lambda d: remake(d, lambda es: es[0]['body'].update(schema='journal/2'))),
        ('S96', 'the_digest_is_of_named_views_with_every_empty_view_left_out', lambda d: remake(d, lambda es: es[0]['result'].update(state='0' * 64))),
        ('S96', 'the_digest_is_of_named_views_with_every_empty_view_left_out', lambda d: remake(d, lambda es: es[2]['result'].update(state=es[1]['result']['state']))),
        # S97: continuing a journal is a write to it; a chain of journals
        ('S97', 'the_journal_that_is_continued_ends_on_a_closing_entry_that_names_the_next', lambda d: rewrite(first(d), lambda es: es.pop(), sha)),            # journal 1 with no closing entry: nothing kept says it was continued
        ('S97', 'the_journal_that_is_continued_ends_on_a_closing_entry_that_names_the_next', lambda d: rewrite(first(d), lambda es: es[7]['body']['next'].update(name='orders-2b'), sha)),   # closed in the name of another journal
        ('S97', 'the_journal_that_is_continued_ends_on_a_closing_entry_that_names_the_next', lambda d: rewrite(first(d), lambda es: es[7]['body']['next'].update(checkers=[]), sha)),
        ('S97', 'the_journal_that_is_continued_ends_on_a_closing_entry_that_names_the_next', lambda d: first(d)['head_before_closing'].update(length=8)),
        ('S97', 'the_journal_that_is_continued_ends_on_a_closing_entry_that_names_the_next', lambda d: rewrite(first(d), lambda es: es[7]['result'].update(state='0' * 64), sha)),   # the closing entry said to have changed the State
        ('S97', 'a_writer_from_the_head_before_the_closing_is_refused_and_changes_nothing_kept', lambda d: late(d).update(refused=None)),                       # the second writer's save taken after all
        ('S97', 'a_writer_from_the_head_before_the_closing_is_refused_and_changes_nothing_kept', lambda d: late(d).update(refused=MOVED.format(7))),
        ('S97', 'a_writer_from_the_head_before_the_closing_is_refused_and_changes_nothing_kept', lambda d: late(d).update(kept_text=text_of(first(d)['text'].split('\n')[:7] + [first(d)['text'].split('\n')[6]]))),   # another entry kept in the place of the closing entry
        ('S97', 'a_writer_from_the_head_before_the_closing_is_refused_and_changes_nothing_kept', lambda d: tail(late(d), 'x', 'kept_text')),
        ('S97', 'a_writer_from_the_head_before_the_closing_is_refused_and_changes_nothing_kept', lambda d: late(d)['kept_head'].update(length=9)),
        ('S97', 'a_writer_from_the_head_before_the_closing_is_refused_and_changes_nothing_kept', lambda d: r0(late(d)['step']).update(status='SUPPORTED_BY_EVIDENCE', actions=[])),
        ('S97', 'a_closed_journal_takes_no_entry_and_no_other_journal_continues_it', lambda d: late(d).update(entry_refused=None)),                           # the closed journal took one more entry
        ('S97', 'a_closed_journal_takes_no_entry_and_no_other_journal_continues_it', lambda d: late(d).update(another_journal_refused=None)),                 # a second journal continues the same head
        ('S97', 'a_closed_journal_takes_no_entry_and_no_other_journal_continues_it', lambda d: late(d)['after_restart']['budget'].update(compute=6, money=6)),   # the refused writer's shipment kept after all
        ('S97', 'a_closed_journal_takes_no_entry_and_no_other_journal_continues_it', lambda d: late(d)['restarted_at'].update(length=7)),
        ('S97', 'a_closed_journal_takes_no_entry_and_no_other_journal_continues_it', lambda d: tail(late(d), 'x', 'kept_text_after')),
        ('S97', 'the_header_cites_the_head_it_continues', lambda d: rewrite(second(d), lambda es: es[0]['body']['continues'].update(length=7), sha)),         # the head before the closing entry: what was continued before continuing was a write
        ('S97', 'the_header_cites_the_head_it_continues', lambda d: rewrite(second(d), lambda es: es[0]['body'].pop('continues'), sha)),
        ('S97', 'and_starts_from_that_state_not_from_the_packs', lambda d: rewrite(second(d), lambda es: es[0]['result'].update(state='0' * 64), sha)),
        ('S97', 'and_starts_from_that_state_not_from_the_packs', lambda d: rewrite(second(d), lambda es: es[0]['result'].update(budget=dict(START)), sha)),   # the second journal said to start from the packs' levels
        ('S97', 'the_second_journal_goes_on_where_the_first_stopped', lambda d: second(d)['after_came_back']['budget'].update(compute=8, money=8)),
        ('S97', 'the_second_journal_goes_on_where_the_first_stopped', lambda d: chain(d)['restarted']['look'].update(entry=1)),
        ('S97', 'the_chain_replays_as_one_record', lambda d: second(d).update(state_before_the_restart='0' * 64)),
        ('S97', 'the_chain_replays_as_one_record', lambda d: chain(d)['restarted'].update(state='0' * 64)),
        ('S97', 'a_journal_without_the_one_it_continues_is_refused', lambda d: chain(d)['refused'].update(without_the_first=None)),
        ('S97', 'a_journal_without_the_one_it_continues_is_refused', lambda d: chain(d)['refused'].update(after_a_first_that_is_not_closed=None)),
        ('S97', 'a_pack_id_passes_once_across_the_chain', lambda d: chain(d)['refused'].update(pack_again=None)),
        # S98: the record read back
        ('S98', 'the_ledger_rows_are_made_again_from_the_text', lambda d: [r for r in restart(d)['ledger'] if r['what'] == 'ran'][1].update(status='LOCAL_MODEL_EFFECTS_RECORDED')),
        ('S98', 'the_ledger_rows_are_made_again_from_the_text', lambda d: [r for r in restart(d)['ledger'] if r['what'] == 'asked'][0].update(to='someone-else')),
        ('S98', 'the_ledger_rows_are_made_again_from_the_text', lambda d: restart(d)['ledger'].pop(3)),
        ('S98', 'the_ledger_rows_are_made_again_from_the_text', lambda d: [r for r in chain(d)['ledger'] if r['what'] == 'handed_in' and 'row' in r][0]['row'].update(truth='TRUE')),
        ('S98', 'the_ledger_rows_are_made_again_from_the_text', lambda d: [r for r in restart(d)['ledger'] if r['what'] == 'ran'][0].pop('pending')),
        ('S98', 'the_counts_are_made_again_from_the_text', lambda d: chain(d)['counts']['steps'][step].update(ran=1)),                                       # counted by trace root, not by entry
        ('S98', 'the_counts_are_made_again_from_the_text', lambda d: chain(d)['counts']['goals'][goal]['trace_roots'].append('0' * 64)),
        ('S98', 'the_counts_are_made_again_from_the_text', lambda d: chain(d)['counts']['goals'][goal]['trace_roots'].clear()),
        ('S98', 'the_counts_are_made_again_from_the_text', lambda d: chain(d)['counts_after_first']['steps'][step].update(ran=2)),
        ('S98', 'every_count_cites_its_entries_by_number_and_hash', lambda d: chain(d)['counts']['steps'][step]['at'].pop()),
        ('S98', 'every_count_cites_its_entries_by_number_and_hash', lambda d: chain(d)['counts']['steps'][step]['at'][1].update(sha256='0' * 64)),
        ('S98', 'every_count_cites_its_entries_by_number_and_hash', lambda d: restart(d)['counts']['goals'][goal].update(looked=5)),
        ('S98', 'handed_in_asked_decided_and_ran_are_all_there', lambda d: restart(d)['ledger'][0].update(sha256='0' * 64)),
        ('S98', 'handed_in_asked_decided_and_ran_are_all_there', lambda d: [r for r in restart(d)['ledger'] if r['what'] == 'decided'][0]['asked_at'].update(entry=7)),
        ('S98', 'counted_by_entry_and_never_by_trace_root', lambda d: chain(d)['counts']['steps'][step]['at'].reverse()),
        ('S98', 'counted_by_entry_and_never_by_trace_root', lambda d: chain(d)['counts']['goals'][goal].update(looked=2)),
        ('S98', 'the_counts_as_of_an_earlier_head', lambda d: restart(d)['counts_at_first']['goals'][goal].update(looked=2)),
        ('S98', 'the_counts_as_of_an_earlier_head', lambda d: restart(d).update(counts_at_first=json.loads(json.dumps(restart(d)['counts'])))),              # the counts at the last head, said to be those at the first
    ]


def checks(data, ROOT, sha, check_chain):
    try:
        mine = {'kernel_sha256': data['kernel_sha256'], 'action_handlers': data['action_handlers'], 'cases': [c for c in data['cases'] if c['id'] == '60_pack_twice'],
                'scenes': {k: data['scenes'][k] for k in ('journal_restart', 'journal_refusals', 'journal_chain')}}   # all that these checks read of the record
        if type(data.get('added')) is dict and type(data['added'].get('files')) is dict:
            mine['added'] = {'files': data['added']['files']}        # and, where a later applier lists them, the files a version added
        got = parts(mine, ROOT, sha)
        listed = forgeries(sha, data['kernel_sha256'])
    except Exception as why:   # a record these checks cannot read has failed every one of them
        return [(cid, False, 'the record could not be read: ' + type(why).__name__) for cid in IDS + (FORGED,)]
    rows = [(cid, all(got[cid[:3]].values()), ' '.join(sorted(name for name, ok in got[cid[:3]].items() if not ok))) for cid in IDS]

    def refused(number, name, change):   # the forged record fails the test the forgery is listed for; a forgery that cannot be made shows nothing
        d = json.loads(json.dumps(mine))
        try:
            change(d)
        except Exception:
            return False
        try:
            return parts(d, ROOT, sha, only=number)[number][name] is False
        except Exception:   # a record so wrong that no test can read it has failed this one too
            return True
    try:
        left = [i for i, (number, name, change) in enumerate(listed) if number not in got or name not in got[number] or not refused(number, name, change)]
        bare = sorted(number + '.' + name for number, each in got.items() for name in each if (number, name) not in {(a, b) for a, b, _ in listed})
        held = all(ok for _, ok, _ in rows)
        detail = (str({'forgeries not refused by their test': left, 'tests without a forgery': bare}) if left or bare
                  else 'a claim does not hold on the record itself, so what its forgeries are refused for shows nothing' if not held
                  else str(len(listed)) + ' forged records, each refused by the test it is listed for; ' + str(sum(len(each) for each in got.values())) + ' tests, none without a forgery')
        rows.append((FORGED, held and not left and not bare, detail))
    except Exception as why:
        rows.append((FORGED, False, 'the forgeries could not be run: ' + type(why).__name__))
    return rows
