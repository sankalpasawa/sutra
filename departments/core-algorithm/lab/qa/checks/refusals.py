"""Independent checks for 0.15.0-refusals (matrix rows R49, R103, R37): cases 51 to 53 and the recorded sequence `refusals`.
Reads the record and the pack files only; never imports the lab's code. Each claim is derived here a second time by this file's
own reading of the pack files: what stands after a list of packs (`fold`), the class of a request by a marker word, the look
that follows from reading a step's prerequisites in order, the books after each receipt (budget, provider slots, rows written),
what a child pack relaxes, the name of a review. Every look is tied to the packs it says it loaded, and the stored state of
each case (facts, rules, budget, journal, the viewer's world and knowledge) is rebuilt from the pack files and compared whole.
What a look says beside its trace (proof, needs, branch) is tied to the rows of its trace, and for the looks of the desk it is
rebuilt whole. NOT read here: the order and number of the proof lines of the servicing team's looks, and a key added to a run
(the base verifier does not read these either). S69 shows that the same claims fail on forged records and packs."""
import json

NAMES = ['110_ops_desk', '111_requested_actions', '112_servicing_team', '113_servicing_standing_rules', '114_practice_money_movement',
         '115_servicing_loosens', '116_pack_review', '117_review_of_loosening', '118_review_of_practice', '119_platform_allows_itself']
TABLE = ('history_rewrite', 'recursive_delete', 'disk_or_system', 'remote_mutation', 'privilege_escalation', 'unreadable_command',
         'destructive_tool', 'bulk_tool', 'credential_path', 'private_host')   # the classifier's closed table, in its order
ALWAYS = ('remote_mutation', 'bulk_tool')   # the two classes the desk permits; the other eight it refuses
MARKS = (('command', 'remote_mutation', 'rsync'), ('command', 'privilege_escalation', 'sudo'), ('command', 'unreadable_command', '|'),
         ('tool', 'destructive_tool', 'purge'), ('path', 'credential_path', '.aws'), ('host', 'private_host', '169.254.'))
DEFAULT = {'compute': 10, 'money': 10, 'attention': 3}   # the budget of a State whose packs set none
OWNER_LINES = [('always', "Always check the payee's account against the loan book before a refund is paid."),
               ('ask', 'Ask me first before a refund is paid.'),
               ('never', "Never pay a refund to an account that is not the borrower's own.")]
QUESTION = 'A refund of an overpaid instalment is due to the borrower. May it be paid?'
PRACTICE_LINES = [('identity', 'always', 'Every money effect names its source record (the bank file, a ledger row or a payment reference) before it is judged.'),
                  ('coordination', 'never', 'A payment and its reconciliation are never held by the same person or model: one makes, another checks.')]
ASKED = 'lendco/servicing|owner_approved_refund'


def same(a, b):   # compared as JSON: 1 is not true and not 1.0
    return json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True)


def ops(r):
    return [(e['operation'], e['data'].get('predicate') or e['data'].get('method')) for e in r['trace']]


def sources(r, op):
    return {e['data'].get('predicate'): e['data'].get('source') for e in r['trace'] if e['operation'] == op}


def blocked(r, reason):
    return same((r['status'], r['work_state'], r['actions'], r['model_receipts'], r['cost'], r['stop_reasons']), (reason, 'blocked', [], [], None, [reason]))


def loaded(r, names):   # the look says it loaded exactly these packs, in this order (the base ties each entry's sha to its file)
    return [p['pack'] for p in r['provenance']] == names


def argued(r, after=None):   # what a look says beside its trace: every proof line, need and branch is carried by a row of its trace; the goal was unknown before, and reads `after` at the end
    t = r['trace']
    lines = ({'%s \u21d0 %s: alternative %d' % (e['data']['predicate'], e['data']['rule'], i + 1) for e in t if e['operation'] == 'REFINE' for i in range(e['data']['alternatives'])}
             | {'%s would establish %s' % (e['data']['method'], e['data']['predicate']) for e in t if e['operation'] == 'METHOD_MATCH'}
             | {'%s observed TRUE (%s)' % (e['data']['predicate'], e['data'].get('source')) for e in t if e['operation'] == 'RETAIN'})
    branches = {'%s/OR%d' % (e['data']['rule'], i + 1) for e in t if e['operation'] == 'REFINE' for i in range(e['data']['alternatives'])} | {''}
    stopped = r['work_state'] == 'blocked'
    return (all(line in lines for line in r['proof']) and set(r['needs']) <= {e['data']['predicate'] for e in t if e['operation'] == 'METHOD_MATCH'} and same(r['candidates'], [])
            and (same((r['proof'], r['needs'], r['selected_branch']), ([], [], None)) if stopped else r['selected_branch'] in branches and len(r['proof']) > 0)
            and r['goal_truth_before'] == 'UNKNOWN' and (r.get('goal_truth_after') == after if after else 'goal_truth_after' not in r))


def keyed(d, *names):   # a block of the record holds exactly these keys
    return set(d) == set(names)


def read(request):   # this file's own reading of a recorded request: the classes, in the table's order, whose marker word it carries
    return [c for kind, c, mark in MARKS if kind == request['kind'] and mark in request['text']]


def fold(packs):   # this file's own reading of what stands after these packs, in load order
    w = {'scope': 'orgA/fulfillment', 'goals': [], 'budget': dict(DEFAULT), 'providers': {}, 'grants': set(), 'rows': {}, 'rules': {}, 'methods': {}}
    for p in packs:
        w['scope'] = p.get('scope', w['scope'])
        w['goals'] = list(p['goals']) if 'goals' in p else w['goals']
        for e in p.get('evidence', []):
            key = e.get('scope', w['scope']) + '|' + e['predicate']
            if e.get('verified') is True and not (w['rows'].get(key, {}).get('final') is True and e.get('final') is not True):   # a decision stands until another decision
                w['rows'][key] = dict(e, scope=e.get('scope', w['scope']))
        for r in p.get('rules', []):
            w['rules'][r['head']] = r
        for m in p.get('methods', []):
            w['methods'][m['id']] = m
        w['providers'].update(p.get('providers', {}))
        w['grants'] = (w['grants'] | set(p.get('grants', []))) - set(p.get('revoke_grants', []))
        w['budget'].update(p.get('budget', {}))
    return w


def settle(w, r):   # the books after the receipts of one look: each step is paid once, takes one slot of its provider, and a step that is no question writes its row
    for x in r['model_receipts']:
        m = w['methods'][x['method']]
        for dim, v in m.get('cost', {}).items():
            w['budget'][dim] -= v
        w['providers'][m['provider']] -= 1
        if m['action'] != 'ask':
            w['rows'][w['scope'] + '|' + m['effect']] = {'predicate': m['effect'], 'truth': 'TRUE', 'verified': True, 'source': 'LOCAL_MODEL:' + m['id'], 'version': 'local-sim-1',
                                                         'evidence_kind': 'SIMULATED_LOCAL', 'scope': w['scope'],
                                                         'depends_on': [{'predicate': p, 'version': w['rows'][w['scope'] + '|' + p].get('version')} for p in m['requires']]}


def books(w, asks, turned):   # a snapshot of the sequence, as this file expects it
    return {'budget': w['budget'], 'providers': w['providers'], 'open_asks': asks, 'turned_away': turned}


def stored(c, w, sha):   # the case's stored state, its looks and the viewer's copies, against what the pack files and the receipts give
    ds, runs = c['derived_state'], c['run']['runs']
    return (keyed(c, 'id', 'title', 'description', 'area', 'packs', 'pack_digest', 'scope', 'run', 'outcome', 'derived_state', 'four_views') and keyed(c['run'], 'status', 'goals', 'runs')
            and keyed(ds, 'facts', 'rule_ids', 'candidate_count', 'budget_after', 'historical_events') and keyed(c['four_views'], 'world', 'knowledge', 'design', 'run')
            and all(same(r['learning'], []) and same(r['learning_record'], {'source_trace': r['trace_root_sha256'], 'learning_sha256': sha(r['learning'])}) for r in runs)
            and same(ds['facts'], w['rows']) and list(ds['facts']) == list(w['rows']) and same(ds['budget_after'], w['budget']) and same(ds['rule_ids'], [r['id'] for r in w['rules'].values()])
            and same(ds['candidate_count'], 0) and same(c['scope'], w['scope'])
            and same(ds['historical_events'], [{'goal': r['goal'], 'scope': r['scope'], 'status': r['status'], 'trace_root_sha256': r['trace_root_sha256']} for r in runs])
            and same(c['four_views']['world'], [{'predicate': k, 'truth': v['truth'], 'source': v.get('source')} for k, v in w['rows'].items()])
            and same(c['four_views']['knowledge'], list(w['rules'].values()))
            and same((c['run']['status'], c['run']['goals']), ('EVALUATED', w['goals'])) and [r['goal'] for r in runs] == w['goals'] and same(c['outcome'], runs[0])
            and all(loaded(r, c['packs']) and r['scope'] == w['scope'] for r in runs))


def desk_look(m, r, w):   # the look of one step of the queue: what reading its prerequisites in order over the stored rows must give, against what the record says
    want, end = [('GOAL_ACCEPTED', None), ('METHOD_MATCH', m['effect'])], 'RUNS'
    for p in m['requires']:
        row = w['rows'].get(w['scope'] + '|' + p)
        if row is not None and row['truth'] == 'TRUE':
            want.append(('RETAIN', p))
        elif row is not None and row['truth'] == 'FALSE' and row.get('final') is True:
            want.append(('REFUSED', p))
            end = 'REFUSED'
            break
        else:   # nobody ruled, or nothing was screened: the kernel stops reading here and asks for evidence
            want.append(('QUERY_EVIDENCE', p))
            end = 'QUERY_EVIDENCE'
            break
    held = m['grant'] in w['grants'] and w['providers'].get(m['provider'], 0) >= 1 and all(w['budget'][dim] >= v for dim, v in m['cost'].items())   # nothing else stood in the way
    read_rows = all(e['data'].get('source') == w['rows'][w['scope'] + '|' + e['data']['predicate']].get('source') for e in r['trace'] if e['operation'] in ('RETAIN', 'REFUSED'))
    if end != 'RUNS':   # refused or unknown: nothing admitted, run, paid or written
        return held and read_rows and blocked(r, end) and argued(r) and r['goal'] == m['effect'] and ops(r) == want + [('BLOCK', None), ('TERMINAL', None)]
    receipt = {'method': m['id'], 'scope': w['scope'], 'action': m['action'], 'status': 'LOCAL_ONLY', 'model_effect': m['effect']}
    proof = ['%s would establish %s' % (m['id'], m['effect'])] + ['%s observed TRUE (%s)' % (p, w['rows'][w['scope'] + '|' + p].get('source')) for p in m['requires']]
    return (held and read_rows and same((r['status'], r['work_state'], r['actions'], r['goal'], r['stop_reasons']), ('LOCAL_MODEL_EFFECTS_RECORDED', 'completed', [m['id']], m['effect'], []))
            and argued(r, 'MODEL_DERIVABLE_NOT_EXTERNAL_PROOF') and same((r['proof'], r['needs'], r['selected_branch']), (proof, [m['effect']], ''))
            and same([{k: v for k, v in x.items() if k != 'sha256'} for x in r['model_receipts']], [receipt]) and same(r['cost'], m['cost'])
            and ops(r) == want + [('ADMISSION', None), ('SELECT', None), ('ADMISSION', None), ('LOCAL_EFFECT', None), ('TERMINAL', None)])


def relaxed_by(parents, child):   # this file's own reading of what a child pack relaxes, for the three ways the recorded counterexample does
    found, standing, decided = [], {}, {}
    for p in parents:
        for r in p.get('rules', []):
            standing[r['head']] = r                      # the rule that stands on each head after the parents
        for e in p.get('evidence', []):
            if e.get('final') is True:
                decided[e['predicate']] = e['truth']     # the decision that stands on each fact after the parents
    asked = {m['effect'] for p in parents for m in p.get('methods', []) if m.get('action') == 'ask'}
    scope = [p['scope'] for p in parents if 'scope' in p][-1]   # where the parents' decisions stand
    for r in child.get('rules', []):
        old = standing.get(r['head'])
        if old is not None and r.get('replaces') == old['id']:
            for i, b in enumerate(r['branches'], 1):
                if not any(set(a) <= set(b) for a in old['branches']):
                    near = min(old['branches'], key=lambda a: (-len(set(a) & set(b)), len(set(a) - set(b))))   # the alternative of the parent it shares most with
                    found.append(('CONDITION_DROPPED', 'rule', r['id'], old['id'], r['head'], i, sorted(set(near) - set(b))))
    for e in child.get('evidence', []):
        if e.get('final') is True and e['truth'] == 'TRUE' and decided.get(e['predicate']) == 'FALSE':
            found.append(('REFUSAL_DROPPED', 'decision', e['predicate'], scope, e['source']))
    for e in child.get('evidence', []):
        if e['truth'] == 'TRUE' and e['verified'] is True and e['predicate'] in asked and decided.get(e['predicate']) is None:
            found.append(('ASK_DROPPED', 'answer', e['predicate'], e['source'], 'UNKNOWN' if e.get('depends_on') else 'TRUE'))
    return found


SAID = {'rule': ('rule', 'replaces', 'head', 'alternative', 'dropped'), 'decision': ('fact', 'scope', 'source'), 'answer': ('fact', 'source', 'reads'),
        'looser': ('method', 'fact'), 'budget': ('dimension', 'was', 'now')}   # what a finding of each way carries, beside its kind, its way and its sentence
SENTENCE = {'rule': lambda f: '%s replaces %s: its alternative %d keeps no alternative of the parent whole; the nearest loses %s' % (f['rule'], f['replaces'], f['alternative'], ', '.join(f['dropped'])),
            'decision': lambda f: 'the parent refuses %s (a FALSE decision in %s); the pack replaces it with a TRUE decision' % (f['fact'], f['scope']),
            'answer': lambda f: 'the pack carries a TRUE row on %s, which the parent asks about: it answers for the party that was to be asked' % f['fact'],
            'looser': lambda f: '%s is a method for %s, which the parent refuses: it says the refusal more loosely (the kernel will not use it while the decision stands)' % (f['method'], f['fact']),
            'budget': lambda f: 'the pack raises the budget for %s from %d to %d' % (f['dimension'], f['was'], f['now'])}


def told(f):   # what a recorded finding says, in the shape of relaxed_by; one with a key this file does not know, or a sentence that says something else, tells nothing
    if set(f) != {'kind', 'how', 'line', *SAID[f['how']]} or f['line'] != SENTENCE[f['how']](f):
        return None
    return (f['kind'], f['how'], *(f[k] for k in SAID[f['how']]))


IDS = ('S60_requests_are_screened_by_name_and_the_desk_rules_on_every_class', 'S61_a_refused_class_is_refused_whatever_else_holds',
       'S62_deny_wins_over_a_permitted_class_a_later_allow_and_a_later_pack', 'S63_always_ask_never_in_one_look',
       'S64_the_owners_answer_decides_and_the_refused_route_stays_shut', 'S65_a_practice_pick_only_adds',
       'S66_the_check_names_what_a_child_relaxes', 'S67_the_kernel_applies_a_pack_that_relaxes', 'S68_the_review_of_exactly_this_pack_blocks_its_install')


def claims(d, P, sha):
    try:
        return _claims(d, P, sha)
    except Exception:   # a record or a pack so wrong that nothing can be read has failed every claim
        return {cid: False for cid in IDS}


def _claims(d, P, sha):
    case = {c['id']: c for c in d['cases']}
    seq = d['scenes']['refusals']
    desk, queue, team, lines, practice, loosens, review, v_loose, v_pick, later = (P[n] for n in NAMES)
    line = {l['tag']: l for l in lines['standing_rules']}
    c51, c52, c53 = case['51_refused_class'], case['52_standing_rules'], case['53_child_relaxes']
    runs51, steps = c51['run']['runs'], queue['methods']
    name = lambda step, request: 'screened:' + step + '@req-' + sha(request)[:12]   # a screening row is named by its step and the digest of its request
    screening = lambda step, request: {'predicate': name(step, request), 'truth': 'TRUE', 'verified': True, 'source': 'adapter:refusals/classes@1',
                                       'version': 'req-' + sha(request)[:12], 'request': request, 'classes': read(request)}
    view = lambda runs: [(r['goal'], r['status'], r['actions'], r['trace_root_sha256']) for r in runs]
    turned = lambda scope, fact: [{'status': 'DECISION_STANDS', 'scope': scope, 'predicate': fact}]
    pair = lambda parents, child: child['id'] + '@pair-' + sha([parents, child])[:12]   # a review is named by its child and the digest of the packs compared

    def s60():   # R49: every step of the queue carries its request and the screening row of exactly that request; the desk rules on every class of the table
        rows, rulings = {e['predicate']: e for e in queue['evidence']}, {e['predicate']: e for e in desk['evidence']}
        ruled = lambda c, e: (e['verified'] is True and e['source'] == 'owner:lendco/operations' and e['version'] == 'denylist-1' and isinstance(e['line'], str) and len(e['line']) > 10
                              and same((e['truth'], e.get('final', False), e['tag']), ('TRUE', False, 'always') if c in ALWAYS else ('FALSE', True, 'never')))
        late, after, export = seq['desk']['rescreened'], seq['desk']['after_rescreened'], steps[5]
        again = late['event']['request']   # the request that was screened later for the step that already ran
        return (len(steps) == len(queue['evidence']) == len(rows) == 8 and queue['goals'] == [m['effect'] for m in steps] and {m['request']['kind'] for m in steps} == {'command', 'tool', 'path', 'host'}
                and all(same(rows.get(name(m['id'], m['request'])), screening(m['id'], m['request'])) and m['requires'] == [name(m['id'], m['request'])] + ['may:' + c for c in read(m['request'])]
                        and m['grant'] in queue['grants'] and m['action'] == 'simulate_fact' for m in steps)
                and [e['predicate'] for e in desk['evidence']] == ['may:' + c for c in TABLE] and len(rulings) == 10 and all(ruled(c, rulings['may:' + c]) for c in TABLE)
                and all(c in TABLE for m in steps for c in read(m['request'])) and same((desk['scope'], queue['scope'], later['scope']), ('lendco/operations',) * 3)
                # the reading of another request for the step that ran is another fact: no step requires it, nothing runs, nothing is paid
                and read(export['request']) == [] and same(again, {'kind': 'command', 'text': 'sudo ' + export['request']['text']}) and read(again) == ['privilege_escalation']   # the step's own command, as another user
                and name(export['id'], again) not in [p for m in steps for p in m['requires']]
                and same(late, {'status': 'RECONCILED', 'event': screening(export['id'], again), 'affected': [], 'runs': []}) and same(after, seq['desk']['after'])
                and keyed(seq, 'desk', 'yes', 'no', 'narrowing') and keyed(seq['desk'], 'packs', 'allow_later', 'look', 'after', 'rescreened', 'after_rescreened', 'later_pack'))

    def s61():   # R49: a step in a refused class is refused though grant, slot and budget are there; every prerequisite is read in order; the others run; the stored state is what the packs give
        w, ok = fold([desk, queue]), len(runs51) == len(steps) == 8 and same(c51['packs'], NAMES[:2])
        for m, r in zip(steps, runs51):
            ok = ok and desk_look(m, r, w)
            settle(w, r)
        refused = [m for m, r in zip(steps, runs51) if r['status'] == 'REFUSED']
        return (ok and len(refused) == 6 and {m['request']['kind'] for m in refused} == {'command', 'tool', 'path', 'host'}
                and [r['status'] for r in runs51].count('LOCAL_MODEL_EFFECTS_RECORDED') == 2 and stored(c51, w, sha)
                and same(w['budget'], {'compute': 8, 'money': 8, 'attention': 3}) and same(w['providers'], {'local-provider': 6}))

    def s62():   # R49: deny wins over a class that is permitted, over an allow that arrives later, and over a later pack with its own method, grant and budget
        dk, lp, two = seq['desk'], seq['desk']['later_pack'], steps[6]
        w, w2 = fold([desk, queue]), fold([desk, queue, later])
        own = [m for m in later['methods'] if w['rows'].get(w['scope'] + '|' + m['effect'], {}).get('truth') == 'FALSE']   # the later pack's own way to a refused permission
        ok = (two['requires'][1:] == ['may:remote_mutation', 'may:privilege_escalation'] and runs51[6]['status'] == 'REFUSED'
              and same(dk['packs'], NAMES[:2]) and same(dk['allow_later'], {'status': 'DECISION_STANDS', 'affected': [], 'runs': []})
              and same(lp['packs'], NAMES[:2] + NAMES[9:]) and len(own) == 1 and own[0]['grant'] in later['grants'] and all(later['budget'][dim] > desk['budget'][dim] for dim in later['budget'])
              and len(dk['look']['runs']) == len(lp['look']['runs']) == 8 and keyed(lp, 'packs', 'relaxed', 'look', 'after') and keyed(dk['look'], 'status', 'goals', 'runs') and keyed(lp['look'], 'status', 'goals', 'runs'))
        for look, world in ((dk['look'], w), (lp['look'], w2)):
            ok = ok and same((look['status'], look['goals']), ('EVALUATED', queue['goals'])) and same(view(look['runs']), view(runs51))
            for m, r in zip(steps, look['runs']):
                ok = ok and desk_look(m, r, world) and loaded(r, dk['packs'] if world is w else lp['packs'])
                settle(world, r)
        return (ok and own[0]['id'] not in [a for r in lp['look']['runs'] for a in r['actions']]
                and same(dk['after'], books(w, {}, turned('lendco/operations', 'may:privilege_escalation'))) and same(lp['after'], books(w2, {}, []))
                and same(w2['budget'], {'compute': 48, 'money': 48, 'attention': 3}))

    def s63():   # R103: the three lines of the owner, each by the pack construct it names, in one look
        r, rec, w = c52['outcome'], c52['outcome']['model_receipts'], fold([team, lines])
        always = [m['id'] for m in team['methods'] if m['grant'] == line['always']['grant']]                             # the step the always line lets run
        asks = [m for m in lines['methods'] if m['id'] == line['ask']['method'] and m['action'] == 'ask']               # the question of the ask line
        never = [e for e in lines['evidence'] if e['predicate'] == line['never']['decision'] and e.get('final') is True and e['truth'] == 'FALSE' and e['verified'] is True]
        shut = [m for m in team['methods'] if line['never']['decision'] in m['requires']]                               # the route the never line closes
        work = [m for m in team['methods'] if asks and asks[0]['effect'] in m['requires']]                              # the work that waits for the answer
        ok = (same([(l['tag'], l['line']) for l in lines['standing_rules']], OWNER_LINES) and len(always) == len(asks) == len(never) == len(shut) == len(work) == 1
              and line['always']['grant'] in lines['grants'] and line['always']['grant'] not in team['grants'] and same((team['scope'], lines['scope']), ('lendco/servicing',) * 2)
              and same((r['status'], r['work_state'], r['actions'], r['waits'], r['stop_reasons']), ('WAITING', 'waiting', [always[0], asks[0]['id']], [asks[0]['id']], []))
              and len(rec) == 2 and rec[0]['method'] == always[0] and 'parked' not in rec[0]
              and same((rec[1]['method'], rec[1]['parked'], rec[1]['ask']['to'], rec[1]['ask']['predicate'], asks[0]['ask_to']), (asks[0]['id'], True, 'owner', asks[0]['effect'], 'owner'))
              and same((rec[1]['ask']['question'], asks[0]['question']), (QUESTION, QUESTION))
              and r['pending'] == ['pay-to-borrower@1', 'reconcile-by-maker@1'] and r['pending'][0] == work[0]['id']
              and {(e['data'].get('predicate'), e['data'].get('source')) for e in r['trace'] if e['operation'] == 'REFUSED'} == {(never[0]['predicate'], 'owner:lendco/servicing')}
              and shut[0]['id'] not in r['actions'] + r['pending'] and shut[0]['grant'] in team['grants']
              and all(shut[0]['cost'][dim] <= work[0]['cost'][dim] for dim in work[0]['cost']) and shut[0]['cost']['money'] < work[0]['cost']['money']
              and same(r['cost'], {'compute': 1, 'money': 0, 'attention': 1}) and len(c52['run']['runs']) == 1 and same(c52['packs'], NAMES[2:4])
              and argued(r, 'UNKNOWN') and same((r['needs'], r['selected_branch']), (['refund_paid', 'payee_account_checked', 'owner_approved_refund', 'payment_reconciled'], 'R-REFUND@1/OR1')))
        settle(w, r)
        return ok and stored(c52, w, sha) and same(w['budget'], {'compute': 9, 'money': 10, 'attention': 2})

    def s64():   # R103: the owner's yes lets the work run; the owner's no refuses it; the route the never line closed stays shut either way
        y, n, names = seq['yes'], seq['no'], NAMES[2:5]
        first, said_yes, ran = y['look']['runs'][0], y['answered_yes'], y['answered_yes']['runs'][0]
        first_no, said_no, no, again = n['look']['runs'][0], n['answered_no'], n['answered_no']['runs'][0], n['look_again']['runs'][0]
        issued, issued_no = first['model_receipts'][-1], first_no['model_receipts'][-1]
        stamp = lambda ev, receipt, truth: same(ev, {'predicate': 'owner_approved_refund', 'truth': truth, 'verified': True, 'final': True, 'source': 'STAMP:owner',
                                                      'version': 'ask-' + receipt['sha256'][:12], 'answers': receipt['sha256'], 'scope': 'lendco/servicing'})
        entry = lambda receipt: {ASKED: {'method': receipt['method'], 'receipt': receipt['sha256'], 'issued': receipt}}   # the question on the books, whole
        closed = lambda r: [e['data'] for e in r['trace'] if e['operation'] == 'ASK_CLOSED']   # the question taken off the books, inside the run that the answer started
        closing = lambda receipt, truth: [{'ask': ASKED, 'receipt': receipt['sha256'], 'truth': truth, 'source': 'STAMP:owner'}]
        wy, wn = fold([team, lines, practice]), fold([team, lines, practice])
        ok = (same((y['packs'], n['packs']), (names, names)) and all(len(x['runs']) == 1 for x in (y['look'], n['look'], n['look_again'], said_yes, said_no))
              and keyed(y, 'packs', 'look', 'after_look', 'answered_yes', 'after_yes') and keyed(n, 'packs', 'look', 'answered_no', 'allow_later', 'look_again', 'after')
              and all(same(x, {'status': 'EVALUATED', 'goals': ['refund_settled'], 'runs': x['runs']}) for x in (y['look'], n['look'], n['look_again']))
              and all(keyed(x, 'status', 'event', 'affected', 'runs') for x in (said_yes, said_no))
              and argued(first, 'UNKNOWN') and argued(first_no, 'UNKNOWN') and argued(ran, 'MODEL_DERIVABLE_NOT_EXTERNAL_PROOF') and argued(no) and argued(again)
              and all(x['selected_branch'] == 'R-REFUND@2/OR1' for x in (first, first_no, ran))
              and all(loaded(x, names) for x in (first, ran, first_no, no, again))
              and first['status'] == first_no['status'] == 'WAITING' and same(first['pending'], ['pay-to-borrower@1', 'reconcile-by-checker@1']) and same(view([first]), view([first_no]))
              and same((issued['method'], issued['parked'], issued['ask']['to'], issued['ask']['question']), ('ask-owner-refund@1', True, 'owner', QUESTION)) and same(issued, issued_no))
        settle(wy, first)
        ok = ok and same(y['after_look'], books(wy, entry(issued), []))
        ok = (ok and same((said_yes['status'], said_yes['affected']), ('RECONCILED', ['refund_settled'])) and stamp(said_yes['event'], issued, 'TRUE')
              and same((ran['status'], ran['work_state'], ran['actions'], ran['stop_reasons']), ('LOCAL_MODEL_EFFECTS_RECORDED', 'completed', first['pending'], []))
              and ('REFUSED', 'third_party_payout_allowed') in ops(ran) and same(closed(ran), closing(issued, 'TRUE')) and closed(first) == [])
        wy['rows'][ASKED] = said_yes['event']
        settle(wy, ran)
        ok = ok and same(y['after_yes'], books(wy, {}, [])) and same(wy['budget'], {'compute': 5, 'money': 8, 'attention': 2})
        settle(wn, first_no)
        return (ok and same((said_no['status'], said_no['affected']), ('RECONCILED', ['refund_settled'])) and stamp(said_no['event'], issued_no, 'FALSE')
                and blocked(no, 'REFUSED') and blocked(again, 'REFUSED') and same(closed(no), closing(issued_no, 'FALSE')) and closed(again) == [] and closed(first_no) == []
                and all([p for o, p in ops(x) if o == 'REFUSED'] == ['owner_approved_refund', 'third_party_payout_allowed'] for x in (no, again))
                and all(same(sources(x, 'REFUSED'), {'owner_approved_refund': 'STAMP:owner', 'third_party_payout_allowed': 'owner:lendco/servicing'}) for x in (no, again))
                and same(n['allow_later'], {'status': 'DECISION_STANDS', 'affected': [], 'runs': []})
                and same(n['after'], books(wn, {}, turned('lendco/servicing', 'third_party_payout_allowed'))) and same(wn['budget'], {'compute': 8, 'money': 10, 'attention': 2}))

    def s65():   # R103 and R37: the practice pick only adds (a condition with its step, a refusal), the look changes accordingly, and its own review supports its install
        old, new, r52, look, nw = team['rules'][0], practice['rules'][0], c52['outcome'], seq['yes']['look']['runs'][0], seq['narrowing']['practice']
        duty, shut = ([l for l in practice['standing_rules'] if l['tag'] == t][0] for t in ('always', 'never'))
        review_run, p_pick = c53['run']['runs'][1], pair([team, lines], practice)
        return (same([(l['function'], l['tag'], l['line']) for l in practice['standing_rules']], PRACTICE_LINES) and same(practice['practice']['id'], 'money-movement') and same(practice['scope'], 'lendco/servicing')
                and new['replaces'] == old['id'] and new['head'] == old['head'] and all(any(set(a) <= set(b) for a in old['branches']) for b in new['branches'])   # this file's own subset test
                and [c for b in new['branches'] for c in b if all(c not in a for a in old['branches'])] == ['source_record_named'] and duty['rule'] == new['id'] and duty['grant'] in practice['grants']
                and [m['id'] for m in practice['methods'] if m['grant'] == duty['grant'] and m['effect'] == 'source_record_named'] == ['name-source-record@1']
                and any(e['predicate'] == shut['decision'] and e.get('final') is True and e['truth'] == 'FALSE' for e in practice['evidence'])
                and any(e['predicate'] == shut['decision'] and e['truth'] == 'TRUE' and not e.get('final') for e in team['evidence'])
                and look['actions'] == ['name-source-record@1'] + r52['actions']
                and same((r52['pending'], look['pending']), (['pay-to-borrower@1', 'reconcile-by-maker@1'], ['pay-to-borrower@1', 'reconcile-by-checker@1']))
                and ('REFUSED', shut['decision']) in ops(look) and ('REFUSED', shut['decision']) not in ops(r52)
                and relaxed_by([team, lines], practice) == [] and same(nw, {'parents': NAMES[2:4], 'child': NAMES[4], 'relaxed': []})
                and same((review_run['goal'], review_run['status'], review_run['work_state'], review_run['actions'], review_run['model_receipts'], review_run['stop_reasons']),
                         ('installable:' + p_pick, 'SUPPORTED_BY_EVIDENCE', 'completed', [], [], []))
                and ops(review_run) == [('GOAL_ACCEPTED', None), ('REFINE', 'installable:' + p_pick), ('RETAIN', 'narrows:' + p_pick), ('ADMISSION', None), ('SELECT', None), ('TERMINAL', None)]
                and same(sources(review_run, 'RETAIN'), {'narrows:' + p_pick: 'adapter:refusals/narrowing@1'}) and argued(review_run, 'UNKNOWN') and keyed(seq['narrowing'], 'practice', 'loosened')
                and same((review_run['proof'], review_run['needs'], review_run['selected_branch'], review_run['cost']),
                         (['installable:%s \u21d0 R-INSTALL:%s: alternative 1' % (p_pick, p_pick), 'narrows:%s observed TRUE (adapter:refusals/narrowing@1)' % p_pick], [], 'R-INSTALL:%s/OR1' % p_pick, {'compute': 0, 'money': 0, 'attention': 0})))

    def s66():   # R37: what the check recorded for the child packs is what this file reads in the pack files
        nw, want, lp = seq['narrowing']['loosened'], relaxed_by([team, lines, practice], loosens), seq['desk']['later_pack']['relaxed']
        refused = [e['predicate'] for e in desk['evidence'] if e.get('final') is True and e['truth'] == 'FALSE']
        return (same((nw['parents'], nw['child']), (NAMES[2:5], NAMES[5])) and len(want) == 3 and same([told(f) for f in nw['relaxed']], want)
                and [f['kind'] for f in nw['relaxed']] == ['CONDITION_DROPPED', 'REFUSAL_DROPPED', 'ASK_DROPPED']
                and same([told(f) for f in lp],   # the later pack on the desk: a looser line, two raised ceilings
                         [('REFUSAL_DROPPED', 'looser', m['id'], m['effect']) for m in later['methods'] if m['effect'] in refused]
                         + [('CEILING_RAISED', 'budget', dim, desk['budget'][dim], later['budget'][dim]) for dim in sorted(later['budget']) if later['budget'][dim] > desk['budget'][dim]])
                and len(lp) == 3)

    def s67():   # R37: the kernel itself applies the pack that relaxes; the look then pays by the refused route, unasked, without the dropped condition
        loose, w = seq['narrowing']['loosened'], fold([team, lines, practice, loosens])
        r, kept = loose['look']['runs'][0], sources(loose['look']['runs'][0], 'RETAIN')
        ok = (same(loose['packs'], NAMES[2:6]) and len(loose['look']['runs']) == 1 and loaded(r, NAMES[2:6]) and same((loose['look']['status'], loose['look']['goals']), ('EVALUATED', ['refund_settled']))
              and same((r['status'], r['work_state'], r['actions'], r['stop_reasons']), ('LOCAL_MODEL_EFFECTS_RECORDED', 'completed', ['pay-to-third-party@1', 'reconcile-by-checker@1'], []))
              and len(r['model_receipts']) == 2 and all(w['methods'][x['method']]['action'] != 'ask' for x in r['model_receipts'])
              and kept.get('third_party_payout_allowed') == kept.get('owner_approved_refund') == 'team:lendco/servicing'
              and not any(p == 'source_record_named' for _, p in ops(r)) and ('REFUSED', 'maker_may_reconcile') in ops(r) and same(loosens['scope'], 'lendco/servicing')
              and keyed(loose, 'parents', 'child', 'relaxed', 'packs', 'look', 'after') and argued(r, 'MODEL_DERIVABLE_NOT_EXTERNAL_PROOF') and r['selected_branch'] == 'R-REFUND@3/OR1')
        settle(w, r)
        return ok and same(loose['after'], books(w, {}, [])) and same(w['budget'], {'compute': 7, 'money': 9, 'attention': 3})

    def s68():   # R37: the review is one decision, named by the child and the digest of the packs compared; the install of that child rests on exactly it, and another review does not stand in
        runs, found, w = c53['run']['runs'], seq['narrowing']['loosened']['relaxed'], fold([review, v_loose, v_pick])
        p_loose, p_pick = pair([team, lines, practice], loosens), pair([team, lines], practice)
        rule = lambda p: {'id': 'R-INSTALL:' + p, 'head': 'installable:' + p, 'branches': [['narrows:' + p]], 'approved': True, 'source': 'reviewed/child-narrows-never-relaxes'}
        row = lambda p, child, parents, relaxed: {'predicate': 'narrows:' + p, 'truth': 'FALSE' if relaxed else 'TRUE', 'verified': True, 'final': True, 'source': 'adapter:refusals/narrowing@1',
                                                  'version': p.rsplit('@', 1)[1], 'child': child, 'parents': parents, 'relaxed': relaxed}
        return (same(c53['packs'], NAMES[6:9]) and p_loose != p_pick and same(review['rules'], [rule(p_loose), rule(p_pick)]) and same(review['goals'], ['installable:' + p_loose, 'installable:' + p_pick])
                and same((review['scope'], v_loose['scope'], v_pick['scope']), ('lendco/pack-review',) * 3)
                and len(found) == 3 and same(v_loose['evidence'], [row(p_loose, NAMES[5], NAMES[2:5], found)]) and same(v_pick['evidence'], [row(p_pick, NAMES[4], NAMES[2:4], [])])
                and len(runs) == 2 and blocked(runs[0], 'REFUSED') and argued(runs[0])
                and ops(runs[0]) == [('GOAL_ACCEPTED', None), ('REFINE', 'installable:' + p_loose), ('REFUSED', 'narrows:' + p_loose), ('BLOCK', None), ('TERMINAL', None)]
                and same(sources(runs[0], 'REFUSED'), {'narrows:' + p_loose: 'adapter:refusals/narrowing@1'})
                and runs[1]['status'] == 'SUPPORTED_BY_EVIDENCE' and stored(c53, w, sha) and same(w['budget'], DEFAULT))

    out = {}
    for cid, fn in zip(IDS, (s60, s61, s62, s63, s64, s65, s66, s67, s68)):
        try:
            out[cid] = bool(fn())
        except Exception:   # a record so wrong that a claim cannot be read has failed that claim
            out[cid] = False
    return out


def checks(data, ROOT, sha, check_chain):
    P = {n: json.loads((ROOT / 'scenarios' / (n + '.json')).read_text()) for n in NAMES}
    got = claims(data, P, sha)

    def forged(change):   # a copy of the record and of the pack files with one thing changed: some claim must fail
        d, p = json.loads(json.dumps(data)), json.loads(json.dumps(P))
        try:
            change(d, p)
        except Exception:
            return False   # a forgery that cannot be made is reported, not counted
        return not all(claims(d, p, sha).values())

    case = lambda d, cid: [c for c in d['cases'] if c['id'] == cid][0]
    desk_runs = lambda d: case(d, '51_refused_class')['run']['runs']
    desk_facts = lambda d: case(d, '51_refused_class')['derived_state']['facts']
    team_run = lambda d: case(d, '52_standing_rules')['outcome']
    team_facts = lambda d: case(d, '52_standing_rules')['derived_state']['facts']
    review = lambda d: case(d, '53_child_relaxes')
    review_facts = lambda d: list(review(d)['derived_state']['facts'].values())
    seq = lambda d: d['scenes']['refusals']
    loose = lambda d: seq(d)['narrowing']['loosened']
    refusal = lambda r: [e for e in r['trace'] if e['operation'] == 'REFUSED'][0]['data']
    asked = lambda d: seq(d)['yes']['after_look']['open_asks'][ASKED]

    def short(x):   # a look that says it loaded fewer packs
        x['provenance'] = x['provenance'][:1]

    forgeries = [
        # the record: case 51, its looks and its stored state
        lambda d, p: desk_runs(d)[0].update(status='LOCAL_MODEL_EFFECTS_RECORDED'),
        lambda d, p: desk_runs(d)[0].update(status='QUERY_EVIDENCE', stop_reasons=['QUERY_EVIDENCE']),
        lambda d, p: desk_runs(d)[0].update(actions=['restart-ledger-sync@1']),
        lambda d, p: desk_runs(d)[1].update(stop_reasons=['REFUSED', 'METHOD_ABSENT']),
        lambda d, p: desk_runs(d)[5].update(status='REFUSED'),
        lambda d, p: desk_runs(d)[5]['model_receipts'].pop(),
        lambda d, p: desk_runs(d)[5]['model_receipts'][0].update(model_effect='rate_table_pushed'),
        lambda d, p: refusal(desk_runs(d)[2]).update(predicate='may:bulk_tool'),
        lambda d, p: refusal(desk_runs(d)[3]).update(source='team:lendco/platform'),
        lambda d, p: desk_runs(d)[6]['trace'].pop(3),
        lambda d, p: refusal(desk_runs(d)[6]).update(predicate='may:remote_mutation'),
        lambda d, p: desk_runs(d)[1]['provenance'].pop(),
        lambda d, p: desk_runs(d)[1]['provenance'].reverse(),
        lambda d, p: desk_runs(d)[7].update(goal='due_list_exported'),
        lambda d, p: desk_runs(d).pop(),
        lambda d, p: desk_runs(d)[5].update(goal_truth_after='UNKNOWN'),
        lambda d, p: desk_runs(d)[1].update(goal_truth_before='TRUE'),
        lambda d, p: desk_runs(d)[5]['proof'].pop(),
        lambda d, p: desk_runs(d)[7]['proof'].reverse(),
        lambda d, p: desk_runs(d)[1].update(selected_branch=''),
        lambda d, p: desk_runs(d)[7].update(needs=[]),
        lambda d, p: desk_runs(d)[3]['candidates'].append({'status': 'PROPOSED_ONLY'}),
        lambda d, p: desk_runs(d)[2]['learning_record'].update(learning_sha256='0' * 64),
        lambda d, p: desk_runs(d)[4]['learning_record'].update(source_trace=desk_runs(d)[3]['trace_root_sha256']),
        lambda d, p: case(d, '51_refused_class')['derived_state']['budget_after'].update(compute=10),
        lambda d, p: case(d, '51_refused_class')['derived_state']['budget_after'].update(compute=8.0),
        lambda d, p: desk_facts(d).update({'lendco/operations|ledger_sync_restarted': {'truth': 'TRUE'}}),
        lambda d, p: desk_facts(d)['lendco/operations|may:privilege_escalation'].update(truth='TRUE'),
        lambda d, p: desk_facts(d)['lendco/operations|may:privilege_escalation'].update(final=False),
        lambda d, p: [desk_facts(d).pop(k) for k in list(desk_facts(d)) if '|may:' in k and desk_facts(d)[k]['truth'] == 'FALSE'],
        lambda d, p: desk_facts(d).update({'lendco/platform|due_list_exported': desk_facts(d).pop('lendco/operations|due_list_exported')}),
        lambda d, p: desk_facts(d)['lendco/operations|due_list_exported']['depends_on'][0].update(version='req-000000000000'),
        lambda d, p: desk_facts(d)['lendco/operations|may:credential_path'].update(line='Credential stores may be read.'),
        lambda d, p: case(d, '51_refused_class')['derived_state']['historical_events'][0].update(status='LOCAL_MODEL_EFFECTS_RECORDED'),
        lambda d, p: case(d, '51_refused_class')['derived_state']['historical_events'].append({'status': 'DECISION_STANDS', 'scope': 'lendco/operations', 'predicate': 'may:private_host'}),
        lambda d, p: case(d, '51_refused_class')['four_views']['world'][4].update(truth='TRUE'),
        lambda d, p: case(d, '51_refused_class').update(scope='lendco/platform'),
        # the record: the desk's sequence
        lambda d, p: seq(d).update(more={}),
        lambda d, p: seq(d)['desk'].update(packs=['110_ops_desk']),
        lambda d, p: seq(d)['desk']['rescreened']['event']['request'].update(text='sudo ls'),
        lambda d, p: seq(d)['desk']['allow_later'].update(status='RECONCILED'),
        lambda d, p: seq(d)['desk']['allow_later'].update(affected=['ledger_sync_restarted']),
        lambda d, p: seq(d)['desk']['after'].update(turned_away=[]),
        lambda d, p: seq(d)['desk']['after']['turned_away'][0].update(predicate='may:private_host'),
        lambda d, p: seq(d)['desk']['look']['runs'][0].update(status='LOCAL_MODEL_EFFECTS_RECORDED'),
        lambda d, p: seq(d)['desk']['look']['runs'][6].update(actions=['sync-loan-book-as-root@1']),
        lambda d, p: short(seq(d)['desk']['look']['runs'][2]),
        lambda d, p: seq(d)['desk']['look'].update(goals=[]),
        lambda d, p: seq(d)['desk']['after']['budget'].update(money=7),
        lambda d, p: seq(d)['desk']['after']['providers'].update({'local-provider': 0}),
        lambda d, p: seq(d)['desk']['after']['providers'].update({'local-provider': 6.0}),
        lambda d, p: seq(d)['desk']['after']['open_asks'].update(left={}),
        lambda d, p: seq(d)['desk']['rescreened'].update(status='DECISION_STANDS'),
        lambda d, p: seq(d)['desk']['rescreened'].update(affected=['due_list_exported']),
        lambda d, p: seq(d)['desk']['rescreened']['event'].update(predicate='screened:export-due-list@1'),
        lambda d, p: seq(d)['desk']['rescreened']['event'].update(classes=[]),
        lambda d, p: seq(d)['desk']['rescreened']['event']['request'].update(text='python3 reports/due_list.py --month 2026-11'),
        lambda d, p: seq(d)['desk']['rescreened']['event'].update(source='anyone'),
        lambda d, p: seq(d)['desk']['after_rescreened']['budget'].update(compute=7, money=7),
        lambda d, p: seq(d)['desk']['after_rescreened']['providers'].update({'local-provider': 5}),
        lambda d, p: seq(d)['desk']['later_pack'].update(packs=['110_ops_desk', '111_requested_actions']),
        lambda d, p: seq(d)['desk']['later_pack']['look']['runs'][0].update(status='LOCAL_MODEL_EFFECTS_RECORDED'),
        lambda d, p: seq(d)['desk']['later_pack']['look']['runs'][0].update(actions=['permit-root@1', 'restart-ledger-sync@1']),
        lambda d, p: seq(d)['desk']['later_pack']['look']['runs'][3]['provenance'].pop(),
        lambda d, p: seq(d)['desk']['later_pack']['after']['budget'].update(compute=50),
        lambda d, p: seq(d)['desk']['later_pack']['after']['providers'].update({'local-provider': 8}),
        lambda d, p: seq(d)['desk']['later_pack']['after']['turned_away'].append({'status': 'DECISION_STANDS', 'scope': 'lendco/operations', 'predicate': 'may:private_host'}),
        lambda d, p: seq(d)['desk']['later_pack']['relaxed'].pop(0),
        lambda d, p: seq(d)['desk']['later_pack']['relaxed'][1].update(now=10),
        lambda d, p: seq(d)['desk']['later_pack']['relaxed'][0].update(kind='CONDITION_DROPPED'),
        lambda d, p: seq(d)['desk']['later_pack']['relaxed'][0].update(line='nothing was relaxed'),
        lambda d, p: seq(d)['desk']['later_pack']['relaxed'][1].update(line='the pack lowers the budget for compute from 50 to 10'),
        # the record: case 52 and the owner's answers
        lambda d, p: team_run(d).update(status='PLAN_READY'),
        lambda d, p: team_run(d).update(pending=['reconcile-by-maker@1']),
        lambda d, p: team_run(d).update(actions=['ask-owner-refund@1', 'check-payee-account@1']),
        lambda d, p: team_run(d)['model_receipts'].reverse(),
        lambda d, p: team_run(d)['model_receipts'][1]['ask'].update(to='team-lead'),
        lambda d, p: team_run(d)['model_receipts'][1]['ask'].update(question='May the team decide?'),
        lambda d, p: team_run(d)['model_receipts'][1].update(parked=1),
        lambda d, p: team_run(d)['model_receipts'][0].update(parked=True),
        lambda d, p: refusal(team_run(d)).update(source='fixture/test'),
        lambda d, p: refusal(team_run(d)).update(predicate='maker_may_reconcile'),
        lambda d, p: [short(x) for x in (team_run(d), case(d, '52_standing_rules')['run']['runs'][0])],
        lambda d, p: case(d, '52_standing_rules')['derived_state']['budget_after'].update(attention=3),
        lambda d, p: case(d, '52_standing_rules')['derived_state']['budget_after'].update(money=10.0),
        lambda d, p: team_facts(d)['lendco/servicing|third_party_payout_allowed'].update(truth='TRUE'),
        lambda d, p: team_facts(d)['lendco/servicing|third_party_payout_allowed'].update(final=False),
        lambda d, p: team_facts(d).pop('lendco/servicing|payee_account_checked'),
        lambda d, p: team_facts(d)['lendco/servicing|payee_account_checked'].update(source='fixture/loan-book'),
        lambda d, p: case(d, '52_standing_rules')['derived_state'].update(rule_ids=[]),
        lambda d, p: team_run(d)['proof'].append('refund_paid observed TRUE (anyone)'),
        lambda d, p: team_run(d).update(selected_branch='R-REFUND@2/OR1'),
        lambda d, p: seq(d)['yes'].update(packs=['112_servicing_team', '113_servicing_standing_rules']),
        lambda d, p: seq(d)['yes']['look'].update(status='NO_STANDING_GOAL'),
        lambda d, p: seq(d)['no']['look_again'].update(goals=[]),
        lambda d, p: seq(d)['yes']['answered_yes']['runs'][0].update(goal_truth_after='UNKNOWN'),
        lambda d, p: [e for e in seq(d)['yes']['answered_yes']['runs'][0]['trace'] if e['operation'] == 'ASK_CLOSED'][0]['data'].update(source='STAMP:team-lead'),
        lambda d, p: [e for e in seq(d)['no']['answered_no']['runs'][0]['trace'] if e['operation'] == 'ASK_CLOSED'][0]['data'].update(truth='TRUE'),
        lambda d, p: seq(d)['no']['answered_no']['runs'][0]['proof'].append('refund_paid observed TRUE (anyone)'),
        lambda d, p: seq(d)['yes']['look']['runs'][0]['provenance'].pop(),
        lambda d, p: seq(d)['yes']['answered_yes']['runs'][0].update(actions=['pay-to-third-party@1', 'reconcile-by-checker@1']),
        lambda d, p: seq(d)['yes']['answered_yes']['runs'][0].update(status='WAITING'),
        lambda d, p: short(seq(d)['yes']['answered_yes']['runs'][0]),
        lambda d, p: seq(d)['yes']['answered_yes']['event'].update(source='STAMP:team-lead'),
        lambda d, p: seq(d)['yes']['answered_yes']['event'].update(answers='0' * 64),
        lambda d, p: seq(d)['yes']['answered_yes']['event'].update(final=1),
        lambda d, p: seq(d)['yes']['after_look']['budget'].update(attention=2.0),
        lambda d, p: seq(d)['yes']['after_look']['providers'].update({'owner-channel': 1}),
        lambda d, p: asked(d)['issued']['ask'].update(to='team-lead'),
        lambda d, p: asked(d).update(receipt='0' * 64),
        lambda d, p: asked(d).update(method='pay-to-third-party@1'),
        lambda d, p: seq(d)['yes']['after_look']['turned_away'].append({'status': 'DECISION_STANDS', 'scope': 'lendco/servicing', 'predicate': 'owner_approved_refund'}),
        lambda d, p: seq(d)['yes']['after_yes']['budget'].update(money=10),
        lambda d, p: seq(d)['yes']['after_yes']['providers'].update({'local-provider': 4}),
        lambda d, p: seq(d)['yes']['after_yes']['open_asks'].update(left={}),
        lambda d, p: seq(d)['yes']['after_yes']['turned_away'].append({'status': 'DECISION_STANDS', 'scope': 'lendco/servicing', 'predicate': 'owner_approved_refund'}),
        lambda d, p: seq(d)['no'].update(packs=['112_servicing_team']),
        lambda d, p: seq(d)['no'].pop('packs'),
        lambda d, p: seq(d)['no']['answered_no']['runs'][0].update(status='WAITING'),
        lambda d, p: seq(d)['no']['answered_no']['runs'][0].update(actions=['pay-to-third-party@1']),
        lambda d, p: short(seq(d)['no']['answered_no']['runs'][0]),
        lambda d, p: seq(d)['no']['answered_no']['event'].update(truth='TRUE'),
        lambda d, p: seq(d)['no']['look_again']['runs'][0].update(status='LOCAL_MODEL_EFFECTS_RECORDED'),
        lambda d, p: seq(d)['no']['look_again']['runs'][0]['provenance'].reverse(),
        lambda d, p: seq(d)['no']['allow_later'].update(status='RECONCILED', affected=['refund_settled']),
        lambda d, p: seq(d)['no']['after'].update(turned_away=[]),
        lambda d, p: seq(d)['no']['after']['budget'].update(money=8),
        lambda d, p: seq(d)['no']['after']['providers'].update({'owner-channel': 1}),
        # the record: the practice pick, the check's findings, the pack that relaxes, case 53
        lambda d, p: seq(d)['yes']['look']['runs'][0].update(pending=['pay-to-borrower@1', 'reconcile-by-maker@1']),
        lambda d, p: seq(d)['yes']['look']['runs'][0].update(actions=['check-payee-account@1', 'ask-owner-refund@1']),
        lambda d, p: seq(d)['narrowing']['practice']['relaxed'].append({'kind': 'CEILING_RAISED', 'how': 'budget'}),
        lambda d, p: seq(d)['narrowing']['practice'].update(child='115_servicing_loosens'),
        lambda d, p: seq(d)['narrowing']['practice'].update(parents=['112_servicing_team']),
        lambda d, p: loose(d)['relaxed'].pop(),
        lambda d, p: loose(d)['relaxed'].reverse(),
        lambda d, p: loose(d)['relaxed'][0].update(dropped=[]),
        lambda d, p: loose(d)['relaxed'][0].update(replaces='R-REFUND@1'),
        lambda d, p: loose(d)['relaxed'][1].update(fact='maker_may_reconcile'),
        lambda d, p: loose(d)['relaxed'][1].update(scope='lendco/collections'),
        lambda d, p: loose(d)['relaxed'][2].update(kind='CEILING_RAISED'),
        lambda d, p: loose(d)['relaxed'][2].update(reads='UNKNOWN'),
        lambda d, p: loose(d)['relaxed'][2].update(line=''),
        lambda d, p: loose(d)['relaxed'][0].update(line='R-REFUND@3 replaces a rule and keeps every condition'),
        lambda d, p: loose(d).update(packs=['112_servicing_team', '113_servicing_standing_rules', '114_practice_money_movement']),
        lambda d, p: loose(d)['look']['runs'][0].update(status='WAITING'),
        lambda d, p: loose(d)['look']['runs'][0].update(actions=['pay-to-borrower@1', 'reconcile-by-checker@1']),
        lambda d, p: loose(d)['look']['runs'][0]['provenance'].pop(),
        lambda d, p: loose(d)['after']['budget'].update(compute=10),
        lambda d, p: loose(d)['after']['providers'].update({'owner-channel': 0}),
        lambda d, p: loose(d)['after']['turned_away'].append({'status': 'DECISION_STANDS', 'scope': 'lendco/servicing', 'predicate': 'third_party_payout_allowed'}),
        lambda d, p: review(d)['outcome'].update(status='SUPPORTED_BY_EVIDENCE'),
        lambda d, p: [x.update(status='SUPPORTED_BY_EVIDENCE') for x in (review(d)['outcome'], review(d)['run']['runs'][0])],
        lambda d, p: review(d)['outcome'].update(status='METHOD_ABSENT', stop_reasons=['METHOD_ABSENT']),
        lambda d, p: review(d)['outcome'].update(stop_reasons=[]),
        lambda d, p: review(d)['run']['runs'][1].update(status='REFUSED'),
        lambda d, p: review(d)['run']['runs'][1].update(goal=review(d)['run']['runs'][0]['goal']),
        lambda d, p: review(d)['run']['runs'][1]['provenance'].pop(),
        lambda d, p: review(d)['run']['runs'].pop(),
        lambda d, p: review(d)['run']['runs'][1].update(selected_branch=None),
        lambda d, p: review(d)['run']['runs'][1]['proof'].pop(),
        lambda d, p: review(d)['run']['runs'][1].update(goal_truth_after='TRUE'),
        lambda d, p: review(d).update(packs=['116_pack_review', '117_review_of_loosening']),
        lambda d, p: review_facts(d)[0].update(final=False),
        lambda d, p: review_facts(d)[0].update(truth='TRUE'),
        lambda d, p: review_facts(d)[0].update(relaxed=[]),
        lambda d, p: review_facts(d)[0].update(version='pair-000000000000'),
        lambda d, p: review_facts(d)[0].update(source='fixture/reviewed'),
        lambda d, p: review_facts(d)[1].update(truth='FALSE'),
        lambda d, p: review_facts(d)[1].update(child='115_servicing_loosens'),
        lambda d, p: review(d)['derived_state']['budget_after'].update(money=0),
        lambda d, p: review(d)['derived_state']['rule_ids'].pop(),
        # the pack files: what the record rests on said something else
        lambda d, p: p['111_requested_actions']['methods'][0]['requires'].pop(),
        lambda d, p: p['111_requested_actions']['methods'][5]['requires'].append('may:privilege_escalation'),
        lambda d, p: p['111_requested_actions']['methods'][0]['requires'].__setitem__(0, 'screened:restart-ledger-sync@1'),
        lambda d, p: p['111_requested_actions']['evidence'][0].update(classes=[]),
        lambda d, p: p['111_requested_actions']['evidence'][0].update(predicate='screened:restart-ledger-sync@1'),
        lambda d, p: p['111_requested_actions']['evidence'][2].update(source='fixture/reviewed'),
        lambda d, p: p['111_requested_actions']['methods'][1]['request'].update(text='python3 reports/due_list.py --month 2026-11'),
        lambda d, p: p['111_requested_actions']['grants'].remove('action:restart-ledger-sync@1'),
        lambda d, p: p['110_ops_desk']['evidence'][0].update(final=False),
        lambda d, p: p['110_ops_desk']['evidence'][4].update(truth='TRUE'),
        lambda d, p: p['110_ops_desk']['evidence'][3].update(truth='FALSE'),
        lambda d, p: p['110_ops_desk']['evidence'][3].update(final=True),
        lambda d, p: p['110_ops_desk']['evidence'].pop(1),
        lambda d, p: p['110_ops_desk']['evidence'][1].update(predicate='may:recursive_copy'),
        lambda d, p: p['110_ops_desk']['evidence'][9].pop('line'),
        lambda d, p: p['110_ops_desk']['providers'].update({'local-provider': 0}),
        lambda d, p: p['110_ops_desk']['providers'].update({'local-provider': 1}),
        lambda d, p: p['110_ops_desk']['budget'].update(money=0),
        lambda d, p: p['110_ops_desk'].update(scope='lendco/platform'),
        lambda d, p: p['113_servicing_standing_rules']['grants'].remove('action:check-payee-account@1'),
        lambda d, p: p['112_servicing_team']['grants'].append('action:check-payee-account@1'),
        lambda d, p: p['113_servicing_standing_rules']['evidence'][0].update(truth='TRUE'),
        lambda d, p: p['113_servicing_standing_rules']['evidence'][0].update(final=False),
        lambda d, p: p['113_servicing_standing_rules']['methods'][0].update(ask_to='team-lead'),
        lambda d, p: p['113_servicing_standing_rules']['methods'][0].update(action='simulate_fact'),
        lambda d, p: p['113_servicing_standing_rules']['methods'][0].update(question='May the team decide?'),
        lambda d, p: p['113_servicing_standing_rules']['standing_rules'].reverse(),
        lambda d, p: p['113_servicing_standing_rules']['standing_rules'][2].update(line='Pay a refund to any account.'),
        lambda d, p: p['113_servicing_standing_rules']['standing_rules'][1].pop('line'),
        lambda d, p: p['113_servicing_standing_rules']['providers'].update({'owner-channel': 0}),
        lambda d, p: p['112_servicing_team']['methods'][2]['cost'].update(money=3),
        lambda d, p: p['112_servicing_team']['providers'].update({'local-provider': 5}),
        lambda d, p: p['114_practice_money_movement']['rules'][0]['branches'][0].remove('payment_reconciled'),
        lambda d, p: p['114_practice_money_movement']['rules'][0].update(replaces='R-REFUND@0'),
        lambda d, p: p['114_practice_money_movement']['evidence'][0].update(final=False),
        lambda d, p: p['114_practice_money_movement']['grants'].clear(),
        lambda d, p: p['114_practice_money_movement']['standing_rules'][0].update(line='Money effects are judged on trust.'),
        lambda d, p: p['114_practice_money_movement'].pop('practice'),
        lambda d, p: p['115_servicing_loosens']['rules'][0]['branches'][0].append('source_record_named'),
        lambda d, p: p['115_servicing_loosens']['evidence'][0].update(truth='FALSE'),
        lambda d, p: p['115_servicing_loosens']['evidence'].pop(),
        lambda d, p: p['115_servicing_loosens']['evidence'][1].update(version='draft-2'),
        lambda d, p: p['116_pack_review']['rules'][0]['branches'][0].pop(),
        lambda d, p: p['116_pack_review']['rules'][0]['branches'][0].__setitem__(0, p['116_pack_review']['rules'][1]['branches'][0][0]),
        lambda d, p: p['116_pack_review']['goals'].reverse(),
        lambda d, p: p['117_review_of_loosening']['evidence'][0].update(truth='TRUE'),
        lambda d, p: p['117_review_of_loosening']['evidence'][0].update(predicate=p['118_review_of_practice']['evidence'][0]['predicate']),
        lambda d, p: p['118_review_of_practice']['evidence'][0].update(truth='FALSE'),
        lambda d, p: p['118_review_of_practice']['evidence'][0].update(relaxed=[{'kind': 'CEILING_RAISED'}]),
        lambda d, p: p['118_review_of_practice']['evidence'][0].update(predicate=p['117_review_of_loosening']['evidence'][0]['predicate']),
        lambda d, p: p['119_platform_allows_itself']['methods'][0].update(effect='may:remote_mutation'),
        lambda d, p: p['119_platform_allows_itself']['budget'].update(money=10),
        lambda d, p: p['119_platform_allows_itself']['grants'].clear(),
    ]
    left = [i for i, f in enumerate(forgeries) if not forged(f)]
    return [(cid, ok, '') for cid, ok in got.items()] + [('S69_refusals_fail_on_forged_records_and_packs', not left, str(left))]
