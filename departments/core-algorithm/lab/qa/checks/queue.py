"""Independent checks for 0.17.0-queue: rank a queue by impact (matrix row R31b), the decision-provenance row (R91) and
problem styles (R101). Reads the record and the pack files only; never imports the lab's code.
Each group of claims is one function over the record, so the same function is run again on forged copies of the record
(S82, S85, S88): a claim that still holds on a forged record was not checked. S89 carries its own seven forgeries.
What the claims below name of the three recorded sequences is rebuilt here from the pack files or compared with a run
that is. They do not name everything a sequence holds (the confirming review; settled in words, the fix is the next
version's): inside a run its needs, its proof, its candidates and the truth of its goal before and after are compared
with nothing rebuilt; of the lines of a trace a claim reads only what it names (in the listed look of the queue the
methods, the verdict and the blockers of a gate line and not its cost, while the ranked look is held to the hash
chains of case 57, whose gate lines S89 explains; in the looks of the style sequence no gate line at all); the branch
of a run of case 58 is not read (the first run's is held only to the second copy the case keeps of that run, by the
base's own checks); and a key that is added to a sequence, a look or a run is not seen. On the add-on base under this
version a change in one place of a sequence is told by the seal that base keeps over it (its check S201); a record
made again with its seals passes these checks and is told only by a unit test that makes the sequences and the cases
again and compares (tests/test_queue.py, the tests named test_confirm_). Values are compared as JSON (1 is not true)."""
import json

QUEUE, RANKED, LOAN_DESK = '130_collections_queue', '131_queue_ranked', '132_loan_desk'
STYLE_DESK = ['133_complaint_desk', '134_style_run_the_book', '135_style_incident']
STOPPED = ['30_build_goal', '31_build_theory', '82_components_without_constructor']   # the packs of case 30_stop: a step the gate admits and its handler then refuses
OWN_CASES = ['57_queue_ranked', '58_gate_decisions', '59_style_unmatched']             # the cases this version brings
SCHEMA_ROW = ['schema_version', 'turn_id', 'decision_seq', 'ts', 'operator_id', 'charter_ref', 'domain_ref', 'task_tier', 'phase', 'intent_type',
          'factors', 'authority_verdict', 'reversibility', 'approval_ref', 'work_ref', 'output_ref', 'channels']   # a hand copy of the names of decision-provenance-row.schema.json, in its order (that file lives outside the lab)
NULLS = ['ts', 'operator_id', 'charter_ref', 'domain_ref', 'task_tier', 'intent_type', 'reversibility']           # what the lab cannot compute
VERSION = 'lab-decision-provenance/1'
UNEXPLAINED = 'These books do not explain this trace'
START = {'compute': 10, 'money': 10, 'attention': 3}   # the budget a State holds before any pack sets one (the base verifier's ask books assume the same)
RANK = ['SEMANTICS_MISSING', 'SEMANTICS_UNAPPROVED', 'EVIDENCE_CONFLICT', 'REFUSED', 'QUERY_EVIDENCE', 'AUTHORITY_REQUIRED', 'PROVIDER_REQUIRED', 'RESOURCE_REQUIRED', 'METHOD_ABSENT', 'CYCLE_LIMIT']


def _file(ROOT, name):
    return json.loads((ROOT / 'scenarios' / (name + '.json')).read_text())


def _case(data, cid):
    return [c for c in data['cases'] if c['id'] == cid][0]


def _roots(res):
    return [r['trace_root_sha256'] for r in res['runs']]


def _lines(run, operation):
    return [e for e in run['trace'] if e['operation'] == operation]


def _named(run, operation):
    return [e['data'].get('predicate') for e in _lines(run, operation)]


def _built(ROOT, names, sha):
    """What a State holds after these pack files, applied in order: the queue, the budget, the provider slots, the grants, the list of packs,
    the methods and the approved rules."""
    out = {'goals': [], 'budget': dict(START), 'providers': {}, 'grants': set(), 'loaded': [], 'table': {}, 'rules': {}}
    for n in names:
        f = _file(ROOT, n)
        if 'goals' in f:
            out['goals'] = list(f['goals'])
        for r in f.get('rules', []):
            if r.get('approved') is True:
                out['rules'][r['head']] = r
        for m in f.get('methods', []):
            out['table'][m['id']] = m
        out['providers'].update(f.get('providers', {}))
        out['grants'] |= set(f.get('grants', []))
        out['grants'] -= set(f.get('revoke_grants', []))
        out['budget'].update(f.get('budget', {}))
        out['loaded'].append({'pack': n, 'sha256': sha(f)})
    return out


def _paid(built, runs):
    """The budget and the provider slots of `built`, less what these runs' receipts cost: each receipt pays its method's cost and one slot of its provider."""
    budget, slots = dict(built['budget']), dict(built['providers'])
    for r in runs:
        for x in r['model_receipts']:
            m = built['table'][x['method']]
            for dim, v in m.get('cost', {}).items():
                budget[dim] -= v
            slots[m['provider']] -= 1
    return {'budget': budget, 'providers': slots}


def _snap(built, runs=()):   # what tools/scenes/queue_rank.py snapshots of a State: the queue, the books and the list of packs
    return dict(_paid(built, runs), goals=built['goals'], grants=sorted(built['grants']), loaded=built['loaded'])


# ---------------------------------------------------------------------------------------------- R31b: rank a queue by impact
def _replay(q, order):
    """The collections queue replayed from the pack file alone, goal by goal in `order`. Every route of a goal is one branch of its rule: one condition,
    made by one method whose grant is held and whose provider has a slot for every goal (rank_claims checks the pack is that simple), so the budget
    is the only line that can turn a route away. At a goal's turn the gate admits a route when its cost fits what is left; among the admitted routes
    the kernel keeps those no other beats on every line and takes the first by the preference order. Returns, per goal, the gate's answer to each
    route, the lines it was short on, the method taken and how many routes it was taken from; then what is left of the budget and of the slots."""
    left, slots = dict(q['budget']), dict(q['providers'])
    rules = {r['head']: r for r in q['rules']}
    maker = {m['effect']: m for m in q['methods']}
    out = []
    for g in order:
        gate = []
        for branch in rules[g]['branches']:
            m = maker[branch[0]]
            short = sorted(d for d, v in m['cost'].items() if v > left[d])
            gate.append((m, ['RESOURCE_REQUIRED'] if short else [], short))
        admitted = [m for m, why, _ in gate if not why]
        beats = lambda a, b: all(a['cost'][d] <= b['cost'][d] for d in left) and any(a['cost'][d] < b['cost'][d] for d in left)
        best = [m for m in admitted if not any(beats(o, m) for o in admitted)]
        take = min(best, key=lambda m: [m['cost'][d] for d in q['preference']] + [m['id']]) if best else None
        if take is not None:
            for d, v in take['cost'].items():
                left[d] -= v
            slots[take['provider']] -= 1
        out.append({'goal': g, 'gate': [[[m['id']], not why, why] for m, why, _ in gate], 'short': [short for _, _, short in gate], 'takes': take,
                    'options': len(best), 'branch': None if take is None else '%s/OR%d' % (rules[g]['id'], [b[0] for b in rules[g]['branches']].index(take['effect']) + 1)})
    return out, left, slots


def _as_replayed(res, replay, sha):
    """One recorded look against the replay, run by run: the gate's answer to each route, the route taken, how many it was taken from, its branch, its cost and its receipt."""
    ok = len(res['runs']) == len(replay)
    for r, rep in zip(res['runs'], replay):
        gate = [[e['data']['methods'], e['data']['accepted'], e['data']['blockers']] for e in _lines(r, 'ADMISSION')]
        take = rep['takes']
        if take is None:
            want_status = [x for x in RANK if any(x in why for _, _, why in rep['gate'])][0]
            ok = ok and sha([r['goal'], gate, r['status'], r['work_state'], r['actions'], r['model_receipts'], r['cost'], r['selected_branch'], r['pareto_options']]) \
                == sha([rep['goal'], rep['gate'], want_status, 'blocked', [], [], None, None, 0])
        else:
            ok = ok and sha([r['goal'], gate, r['status'], r['work_state'], r['actions'], [x['method'] for x in r['model_receipts']], r['cost'], r['selected_branch'], r['pareto_options']]) \
                == sha([rep['goal'], rep['gate'] + [[[take['id']], True, []]], 'LOCAL_MODEL_EFFECTS_RECORDED', 'completed', [take['id']], [take['id']], take['cost'], rep['branch'], rep['options']])
    return ok


def rank_claims(data, ROOT, sha):
    q, kept = _file(ROOT, QUEUE), _file(ROOT, RANKED)
    listed = q['goals']
    rules = {r['head']: r for r in q['rules']}
    impact = {g: rules[g]['impact'] for g in listed}                     # declared on each goal's approved rule, in the pack file
    want = [g for n in sorted(set(impact.values()), reverse=True) for g in listed if impact[g] == n]   # highest first; equal impacts in the order the queue listed them
    sc, case = data['scenes']['queue_rank'], _case(data, '57_queue_ranked')
    a, b, c = sc['as_listed'], sc['as_ranked'], case['run']
    plain, ranked = _built(ROOT, [QUEUE], sha), _built(ROOT, [QUEUE, RANKED], sha)
    true = {x['predicate'] for x in q['evidence'] if x['truth'] == 'TRUE' and x['verified'] is True}
    simple = (all(len(br) == 1 for r in q['rules'] for br in r['branches']) and len({m['effect'] for m in q['methods']}) == len(q['methods'])
              and all(m['action'] == 'simulate_fact' and set(m['requires']) <= true for m in q['methods'])
              and {br[0] for r in q['rules'] for br in r['branches']} == {m['effect'] for m in q['methods']}
              and all(m['grant'] in q['grants'] and q['providers'][m['provider']] >= len(listed) for m in q['methods']))   # what _replay assumes of this pack
    rep_a, left_a, slots_a = _replay(q, listed)
    rep_b, left_b, slots_b = _replay(q, want)
    spends = lambda rep: [x['goal'] for x in rep if x['takes'] is not None and x['takes']['cost']['attention'] > 0]   # who got one of the desk's calls
    held = lambda rep: [x['goal'] for x in rep if x['takes'] is None]
    on_attention = lambda rep: all(x['short'] == [['attention']] * len(x['short']) for x in rep if x['takes'] is None)
    two = [g for g in listed if len(rules[g]['branches']) > 1]           # the goal with two routes
    route = lambda rep, g: [x for x in rep if x['goal'] == g][0]

    def undeclared(names):                                               # the first goal of this queue that declares no impact, and why: read from the pack files
        built = _built(ROOT, names, sha)
        for g in built['goals']:
            rule = built['rules'].get(g)
            why = 'no rule' if rule is None else 'no impact' if 'impact' not in rule else None if (type(rule['impact']) is int and rule['impact'] >= 0) else 'not a whole number'
            if why:
                return built, g, why
        return built, None, None

    no = sc['not_ranked']
    found = [undeclared(x['packs']) for x in no]
    calls = q['budget']['attention']
    return {
        'S80_the_queue_is_ranked_by_declared_impact_the_ranking_is_kept_as_a_pack_and_nothing_else_changes': (
            all(type(n) is int and n >= 0 for n in impact.values()) and all(rules[g]['approved'] is True for g in listed)
            and want != listed and len(set(impact.values())) < len(listed)   # the recorded queue is out of order and holds a tie: the order and the tie rule are both exercised
            # the ranking pack is the order and its reasons, and nothing else: nothing the gate or the planner reads
            and sha(kept) == sha({'schema': 'sutra-extension/2', 'id': RANKED, 'goals': want, 'ranked_by': [{'goal': g, 'impact': impact[g], 'rule': rules[g]['id']} for g in want]})
            and sha(sc['ranking']) == sha(kept)                              # the live ranking in the recorded sequence is the scenario file
            # around the ranking: the queue's order and the list of packs are all that changed, and ranking a second time changed nothing
            and sha(sc['before_ranking']) == sha(_snap(plain)) and sha(sc['after_ranking']) == sha(_snap(ranked)) and sha(sc['after_ranking_again']) == sha(_snap(ranked))
            and plain['goals'] == listed and ranked['goals'] == want
            and all(sha(_snap(ranked)[k]) == sha(_snap(plain)[k]) for k in ('budget', 'providers', 'grants')) and ranked['loaded'][:1] == plain['loaded']
            and sha(sc['after_listed']) == sha(_snap(plain, a['runs'])) and sha(sc['after_ranked']) == sha(_snap(ranked, b['runs']))
            and sha([a['status'], a['goals'], [r['goal'] for r in a['runs']]]) == sha(['EVALUATED', listed, listed])
            and sha([b['status'], b['goals'], [r['goal'] for r in b['runs']]]) == sha(['EVALUATED', want, want])
            and sha([c['status'], c['goals'], [r['goal'] for r in c['runs']]]) == sha(['EVALUATED', want, want])
            and _roots(c) == _roots(b) and case['packs'] == [QUEUE, RANKED]
            and all(r['provenance'] == plain['loaded'] for r in a['runs']) and all(r['provenance'] == ranked['loaded'] for r in b['runs'] + c['runs'])
            # three queues that are not ranked, each for another reason, each left as it was
            and [x['packs'] for x in no] == [['00_goal'], ['133_complaint_desk'], [LOAN_DESK]]
            and [why for _, _, why in found] == ['no rule', 'no impact', 'not a whole number']
            and all(x['refused'] == 'No declared impact for standing goal: ' + g for x, (_, g, _) in zip(no, found))
            and all(sha(x['before']) == sha(_snap(built)) and sha(x['after']) == sha(_snap(built)) for x, (built, _, _) in zip(no, found))),
        'S81_the_order_decides_who_gets_the_budget_and_can_change_the_route_a_goal_takes': (
            simple and 0 < calls < len(listed)
            # each look is the pack replayed in its order: the same gate answers, the same routes, the same costs
            and _as_replayed(a, rep_a, sha) and _as_replayed(b, rep_b, sha) and _as_replayed(c, rep_b, sha)
            and sha([sc['after_listed']['budget'], sc['after_listed']['providers']]) == sha([left_a, slots_a])
            and sha([sc['after_ranked']['budget'], sc['after_ranked']['providers']]) == sha([left_b, slots_b])
            and sha(case['derived_state']['budget_after']) == sha(left_b) and left_a['attention'] == 0 and left_b['attention'] == 0
            # who gets the desk's calls: the first goals as listed, the goals worth most when ranked
            and spends(rep_a) == listed[:calls] and spends(rep_b) == want[:calls] and set(spends(rep_a)) != set(spends(rep_b))
            and sum(impact[g] for g in spends(rep_b)) > sum(impact[g] for g in spends(rep_a))
            and min(impact[g] for g in spends(rep_b)) >= max(impact[g] for g in listed if g not in spends(rep_b))
            # every held goal was turned away on the attention line and on no other
            and held(rep_a) == [g for g in listed[calls:] if g not in two] and held(rep_b) == [g for g in want[calls:] if g not in two]
            and bool(held(rep_a)) and bool(held(rep_b)) and on_attention(rep_a) and on_attention(rep_b)
            # the order changes the books a goal finds: the goal with two routes takes its first route as listed, from both, and its other route when
            # ranked, after the gate turned the first one away
            and len(two) == 1 and two[0] == listed[0] and two[0] == want[-1]
            and route(rep_a, two[0])['options'] == 2 and [ok for _, ok, _ in route(rep_a, two[0])['gate']] == [True, True]
            and route(rep_b, two[0])['options'] == 1 and route(rep_b, two[0])['gate'] == [[[route(rep_a, two[0])['takes']['id']], False, ['RESOURCE_REQUIRED']], [[route(rep_b, two[0])['takes']['id']], True, []]]
            and route(rep_a, two[0])['branch'] != route(rep_b, two[0])['branch'] and route(rep_b, two[0])['takes']['cost']['attention'] == 0),
    }


# ---------------------------------------------------------------------------------------------- R91: the decision-provenance row
def _books(built):
    return {'grants': set(built['grants']), 'slots': dict(built['providers']), 'budget': dict(built['budget']), 'table': built['table']}


def _rebuild(runs, books, sha):
    """The decision rows of these runs, rebuilt from their traces and the books. The books are paid here as the receipts go by, and the questions
    the chains close are remembered from run to run. None when the books do not explain a line the gate wrote, or when a step at the gate is
    followed by neither its effect nor its stop."""
    rows, closed = [], {}
    for run in runs:
        mine, stepping, t, read = [], False, run['trace'], {}
        row = lambda verdict, phase, factors, approval=None, output=None, channels=(): dict(zip(SCHEMA_ROW, [
            VERSION, run['trace_root_sha256'], len(mine), None, None, None, None, None, phase, None, factors, verdict, None, approval, run['goal'], output, list(channels)]))
        for e in t:
            if e['operation'] == 'ASK_CLOSED':
                closed[e['data']['ask']] = e['data']
            elif e['operation'] == 'RETAIN' and e['data']['predicate'] not in read:
                read[e['data']['predicate']] = e

        def answered(fact, truth, source):
            end = closed.get(run['scope'] + '|' + fact)
            return end['receipt'] if end is not None and end['truth'] == truth and end.get('source') == source else None

        for i, e in enumerate(t):
            d, ref = e['data'], 'trace:%d' % e['seq']
            if e['operation'] == 'SELECT':
                stepping = True
            elif e['operation'] == 'ADMISSION':
                lines, wrong, need = [{'type': 'method', 'value': m, 'source_ref': ref} for m in d['methods']], set(), {}
                for m in d['methods']:
                    grant, provider = books['table'][m]['grant'], books['table'][m]['provider']
                    lines.append({'type': 'grant_held' if grant in books['grants'] else 'grant_missing', 'value': grant, 'source_ref': ref})
                    wrong |= set() if grant in books['grants'] else {'AUTHORITY_REQUIRED'}
                    need[provider] = need.get(provider, 0) + 1
                for provider, n in need.items():
                    free = books['slots'].get(provider, 0)
                    lines.append({'type': 'provider_free' if free >= n else 'provider_short', 'value': '%s: needs %d, has %d' % (provider, n, free), 'source_ref': ref})
                    wrong |= set() if free >= n else {'PROVIDER_REQUIRED'}
                for dim, n in d['cost'].items():
                    there = books['budget'][dim]
                    lines.append({'type': 'budget_fits' if n <= there else 'budget_short', 'value': '%s: needs %d, has %d' % (dim, n, there), 'source_ref': ref})
                    wrong |= set() if n <= there else {'RESOURCE_REQUIRED'}
                summed = {dim: sum(books['table'][m].get('cost', {}).get(dim, 0) for m in d['methods']) for dim in books['budget']}
                if sha(summed) != sha(d['cost']) or sorted(wrong) != d['blockers'] or d['accepted'] is not (not wrong):
                    return None
                receipt = stop = nxt = None
                if stepping:
                    nxt = t[i + 1]
                    one = len(d['methods']) == 1 and not wrong
                    if one and nxt['operation'] == 'LOCAL_EFFECT' and nxt['data']['receipt']['method'] == d['methods'][0]:
                        receipt = nxt['data']['receipt']
                    elif one and nxt['operation'] == 'STEP_STOPPED' and nxt['data']['method'] == d['methods'][0]:
                        stop = nxt
                    else:
                        return None
                phase = 'step' if stepping else 'plan'
                ask = receipt.get('ask') if receipt and receipt.get('parked') is True else None
                if wrong:
                    mine.append(row('denied', phase, lines))
                elif isinstance(ask, dict):
                    lines.append({'type': 'asked', 'value': '%s: %s' % (ask['to'], ask['predicate']), 'source_ref': 'trace:%d' % nxt['seq']})
                    mine.append(row('escalated', phase, lines, approval=receipt['sha256'], channels=[ask['to']]))
                else:
                    facts, cited, who = [], [], []
                    for m in d['methods']:
                        for f in books['table'][m].get('requires', []):
                            if f not in facts:
                                facts.append(f)   # each fact once, in the order the methods require them
                    for f in facts:
                        seen = read.get(f)
                        source = seen['data'].get('source') if seen is not None else None
                        question = answered(f, 'TRUE', source) if seen is not None else None
                        if question is not None:
                            lines.append({'type': 'decision', 'value': '%s: TRUE, decided by %s' % (f, source), 'source_ref': 'trace:%d' % seen['seq']})
                            cited.append(question)
                            who += [source] if isinstance(source, str) and source not in who else []
                    if stop is not None:
                        lines.append({'type': 'stopped', 'value': stop['data']['reason'], 'source_ref': 'trace:%d' % stop['seq']})
                    mine.append(row('granted', phase, lines, approval=cited[0] if cited else None, output=receipt['sha256'] if receipt else None, channels=who))
            elif e['operation'] == 'REFUSED':
                said = d.get('source')
                mine.append(row('denied', 'decision', [{'type': 'decision', 'value': '%s: FALSE, decided by %s' % (d['predicate'], said), 'source_ref': ref}],
                                approval=answered(d['predicate'], 'FALSE', said), channels=[said] if isinstance(said, str) else []))
            elif e['operation'] == 'LOCAL_EFFECT':
                m = books['table'][d['receipt']['method']]
                for dim, v in m.get('cost', {}).items():
                    books['budget'][dim] -= v
                books['slots'][m['provider']] -= 1
        if not mine:
            block = _lines(run, 'BLOCK')
            mine.append(row('not_evaluated', None, [{'type': 'blocked', 'value': block[0]['data']['reason'], 'source_ref': 'trace:%d' % block[0]['seq']}] if block else []))
        rows += mine
    return rows


def _stamp(issued, truth):   # the whole row a stamp on this receipt is: who was asked answers, on the fact asked about, and cites the receipt
    return {'predicate': issued['ask']['predicate'], 'truth': truth, 'verified': True, 'final': True, 'source': 'STAMP:' + issued['ask']['to'],
            'version': 'ask-' + issued['sha256'][:12], 'answers': issued['sha256'], 'scope': issued['scope']}


def _whole_chains(runs, check_chain):
    return all(check_chain(r['trace']) and r['trace'][-1]['sha256'] == r['trace_root_sha256'] for r in runs)


def provenance_claims(data, ROOT, sha, check_chain):
    desk = _file(ROOT, LOAN_DESK)
    table = {m['id']: m for m in desk['methods']}
    sc, case, halted = data['scenes']['queue_provenance'], _case(data, '58_gate_decisions'), _case(data, '30_stop')
    runs, no, yes = case['run']['runs'], sc['answered_no'], sc['answered_yes']   # the rows are rebuilt from the case's own runs: the sequence records no second copy of the look
    rec, rec_no, rec_yes, rec_stop = sc['decisions'], sc['decisions_after_no'], sc['decisions_after_yes'], sc['decisions_of_a_stopped_step']
    built, built_stop = _built(ROOT, [LOAN_DESK], sha), _built(ROOT, STOPPED, sha)
    false = {'S83_every_gate_decision_reads_as_one_row_rebuilt_from_the_record': False, 'S84_each_row_cites_the_line_the_receipt_the_stop_or_the_answer_behind_it': False}
    if (not _whole_chains(runs + no['runs'] + yes['runs'] + halted['run']['runs'], check_chain) or any(r['provenance'] != built['loaded'] for r in runs + no['runs'] + yes['runs'])
            or any(r['provenance'] != built_stop['loaded'] for r in halted['run']['runs']) or halted['packs'] != STOPPED or case['packs'] != [LOAN_DESK]):
        return false
    flat = lambda b: {'grants': sorted(b['grants']), 'providers': b['slots'], 'budget': b['budget']}
    again = lambda b: {'grants': set(b['grants']), 'slots': dict(b['slots']), 'budget': dict(b['budget']), 'table': b['table']}
    start = _books(built)
    before = json.loads(json.dumps(flat(start)))
    rows = _rebuild(runs, start, sha)                # `start` is paid as the receipts go by: after this call it holds the books as the look left them
    after = json.loads(json.dumps(flat(start)))
    rows_no, rows_yes = _rebuild(no['runs'], again(start), sha), _rebuild(yes['runs'], again(start), sha)
    rows_stop = _rebuild(halted['run']['runs'], _books(built_stop), sha)
    gate_lines = sum(len(_lines(r, 'ADMISSION')) for r in runs)
    numbered = all([x['decision_seq'] for x in rec if x['turn_id'] == r['trace_root_sha256']] == list(range(sum(1 for x in rec if x['turn_id'] == r['trace_root_sha256']))) for r in runs)
    verdicts = {}
    for x in rec:
        verdicts.setdefault(x['work_ref'], []).append(x['authority_verdict'])
    line = lambda goal, kind: [f['value'] for x in rec if x['work_ref'] == goal for f in x['factors'] if f['type'] == kind]
    parked = [x for r in runs for x in r['model_receipts'] if x.get('parked') is True]
    esc = [x for x in rec if x['authority_verdict'] == 'escalated']
    paid = sum(table[x['method']]['cost'].get('money', 0) for r in runs[:4] for x in r['model_receipts'])   # what the goals before the audit paid in money
    audit, last = table['sample-audit-7005@1']['cost']['money'], runs[5]
    if len(parked) != 1 or len(no['runs']) != 1 or len(yes['runs']) != 1 or len(halted['run']['runs']) != 1:
        return false
    asked, no_run, yes_run, stop_run = parked[0], no['runs'][0], yes['runs'][0], halted['run']['runs'][0]
    ask_method = table[asked['method']]
    fact, key = ask_method['effect'], '%s|%s' % (desk['scope'], ask_method['effect'])
    refused, read, closed_no, closed_yes = _lines(no_run, 'REFUSED'), _lines(yes_run, 'RETAIN'), _lines(no_run, 'ASK_CLOSED'), _lines(yes_run, 'ASK_CLOSED')
    stops = _lines(stop_run, 'STEP_STOPPED')
    every = rec + rec_no + rec_yes + rec_stop
    steps = [x for x in every if x['phase'] == 'step' and x['authority_verdict'] == 'granted']
    return {
        'S83_every_gate_decision_reads_as_one_row_rebuilt_from_the_record': (
            rows is not None and rows_no is not None and rows_yes is not None and rows_stop is not None
            and sha(rec) == sha(rows) and sha(rec_no) == sha(rows_no) and sha(rec_yes) == sha(rows_yes) and sha(rec_stop) == sha(rows_stop)
            and sha(sc['books_before']) == sha(before) and sha(sc['books_after']) == sha(after)
            and sha(case['derived_state']['budget_after']) == sha(after['budget'])
            and all(list(x) == SCHEMA_ROW and x['schema_version'] == VERSION and all(x[k] is None for k in NULLS) for x in every)
            and sum(1 for x in rec if x['phase'] in ('plan', 'step')) == gate_lines and numbered
            and sha([case['run']['status'], case['run']['goals'], [r['goal'] for r in runs]]) == sha(['EVALUATED', desk['goals'], desk['goals']])
            and verdicts == {'loan_7001_disbursed': ['granted', 'granted', 'granted'], 'fee_7002_waived': ['denied'], 'limit_7003_raised': ['granted', 'escalated'],
                             'statement_7004_posted': ['denied'], 'audit_7005_sampled': ['denied'], 'writeoff_7006_booked': ['not_evaluated']}
            # books that do not explain the trace are refused: the books as the look LEFT them, handed in as if it had started from them
            and sc['wrong_books_refused'] == UNEXPLAINED and _rebuild(runs, again(start), sha) is None),
        'S84_each_row_cites_the_line_the_receipt_the_stop_or_the_answer_behind_it': (
            table['waive-fee-7002@1']['grant'] not in desk['grants'] and line('fee_7002_waived', 'grant_missing') == [table['waive-fee-7002@1']['grant']]
            and desk['providers']['print-room'] == 0 and line('statement_7004_posted', 'provider_short') == ['print-room: needs 1, has 0']
            and audit <= desk['budget']['money'] and paid > 0                # the audit would have fitted the day's budget: what the first goal paid is what turned it away
            and line('audit_7005_sampled', 'budget_short') == ['money: needs %d, has %d' % (audit, desk['budget']['money'] - paid)]
            # a cost equal to what is left fits: the desk has attention for exactly the one question it asks
            and ask_method['cost']['attention'] == desk['budget']['attention'] > 0
            and [v for v in line('limit_7003_raised', 'budget_fits') if v.startswith('attention')] == ['attention: needs %d, has %d' % (desk['budget']['attention'], desk['budget']['attention'])] * 2
            # escalated: the receipt of the question and who was asked
            and len(esc) == 1 and esc[0]['phase'] == 'step' and esc[0]['approval_ref'] == asked['sha256'] and esc[0]['output_ref'] is None
            and esc[0]['channels'] == [asked['ask']['to']] == [ask_method['ask_to']] and asked['ask']['predicate'] == fact
            and esc[0]['factors'][-1]['value'] == '%s: %s' % (asked['ask']['to'], fact)
            # a granted step has the receipt its effect left, or the stop that followed, never both and never neither; nothing else has an output
            and all((x['output_ref'] is None) == (len([f for f in x['factors'] if f['type'] == 'stopped']) == 1) for x in steps)
            and [x['output_ref'] for x in rec if x['phase'] == 'step' and x['authority_verdict'] == 'granted'] == [x['sha256'] for r in runs for x in r['model_receipts'] if x.get('parked') is not True]
            and all(x['output_ref'] is None for x in every if not (x['phase'] == 'step' and x['authority_verdict'] == 'granted'))
            and all(not [f for f in x['factors'] if f['type'] == 'stopped'] for x in every if x not in steps)
            # the stopped step (case 30_stop): three receipts, then a step the gate admitted and the handler refused
            and stop_run['status'] == 'STEP_STOPPED' and len(stops) == 1 and len(stop_run['model_receipts']) == 3
            and [(x['phase'], x['authority_verdict']) for x in rec_stop] == [('plan', 'granted')] + [('step', 'granted')] * 4
            and [x['output_ref'] for x in rec_stop] == [None] + [x['sha256'] for x in stop_run['model_receipts']] + [None]
            and rec_stop[-1]['factors'][-1] == {'type': 'stopped', 'value': stop_run['stopped']['reason'], 'source_ref': 'trace:%d' % stops[0]['seq']}
            and stops[0]['data']['reason'] == stop_run['stopped']['reason'] and stops[0]['data']['method'] == stop_run['stopped']['method'] == rec_stop[-1]['factors'][0]['value']
            # the two stamps, each compared whole with the row a stamp on the parked receipt is: who answered, on which fact, citing which receipt
            and sha(no['event']) == sha(_stamp(asked, 'FALSE')) and sha(yes['event']) == sha(_stamp(asked, 'TRUE'))
            and sha([no['status'], no['affected'], yes['status'], yes['affected']]) == sha(['RECONCILED', ['limit_7003_raised'], 'RECONCILED', ['limit_7003_raised']])
            # the no: denied, by the party the chain names, on the question the chain closes
            and sha([no_run['status'], no_run['actions'], no_run['selected_branch']]) == sha(['REFUSED', [], None]) and len(refused) == 1 and len(closed_no) == 1
            and sha(refused[0]['data']) == sha({'predicate': fact, 'source': no['event']['source']})
            and sha(closed_no[0]['data']) == sha({'ask': key, 'receipt': asked['sha256'], 'truth': 'FALSE', 'source': no['event']['source']})
            and sha(rec_no) == sha([dict(zip(SCHEMA_ROW, [VERSION, no_run['trace_root_sha256'], 0, None, None, None, None, None, 'decision', None,
                                    [{'type': 'decision', 'value': '%s: FALSE, decided by %s' % (fact, no['event']['source']), 'source_ref': 'trace:%d' % refused[0]['seq']}],
                                    'denied', None, asked['sha256'], no_run['goal'], None, [no['event']['source']]]))])
            # the yes: the plan and the step that rest on it are granted, cite the line where the run read the decided fact, the receipt of the question and who decided
            and sha([yes_run['status'], yes_run['actions'], yes_run['selected_branch']]) == sha(['LOCAL_MODEL_EFFECTS_RECORDED', ['update-limit-7003@1'], [r['id'] for r in desk['rules'] if r['head'] == yes_run['goal']][0] + '/OR1'])
            and fact in table['update-limit-7003@1']['requires']
            and len(closed_yes) == 1 and sha(closed_yes[0]['data']) == sha({'ask': key, 'receipt': asked['sha256'], 'truth': 'TRUE', 'source': yes['event']['source']})
            and len(read) >= 1 and all(sha(x['data']) == sha({'predicate': fact, 'source': yes['event']['source'], 'version': yes['event']['version']}) for x in read if x['data']['predicate'] == fact)
            and [(x['authority_verdict'], x['phase'], x['approval_ref'], x['channels']) for x in rec_yes] == [('granted', 'plan', asked['sha256'], [yes['event']['source']]), ('granted', 'step', asked['sha256'], [yes['event']['source']])]
            and all(x['factors'][-1] == {'type': 'decision', 'value': '%s: TRUE, decided by %s' % (fact, yes['event']['source']),
                                         'source_ref': 'trace:%d' % [e['seq'] for e in read if e['data']['predicate'] == fact][0]} for x in rec_yes)
            and rec_yes[1]['output_ref'] == yes_run['model_receipts'][0]['sha256']
            # nothing else in the day's rows cites an answer: approvals are the one question asked and its two answers
            and all(x['approval_ref'] is None and x['channels'] == [] for x in rec + rec_stop if x['authority_verdict'] != 'escalated')
            # the run that never reached the gate
            and not _lines(last, 'ADMISSION') and not _lines(last, 'REFUSED')
            and [(x['phase'], x['factors']) for x in rec if x['work_ref'] == last['goal']] == [(None, [{'type': 'blocked', 'value': last['status'], 'source_ref': 'trace:3'}])]),
    }


def _explained(case, ROOT, sha, check_chain):
    """The decision rows of a case's runs, rebuilt from its traces and the pack files; None when a chain does not hold, a pack is not its file,
    or the books do not explain a gate line."""
    runs = case['run']['runs']
    if not runs:
        return []
    built = _built(ROOT, [p['pack'] for p in runs[0]['provenance']], sha)
    if not _whole_chains(runs, check_chain) or any(r['provenance'] != built['loaded'] for r in runs):
        return None
    try:
        rows = _rebuild(runs, _books(built), sha)
    except (KeyError, TypeError, IndexError):
        return None
    gate_lines = sum(len(_lines(r, 'ADMISSION')) for r in runs)
    return rows if rows is not None and sum(1 for x in rows if x['phase'] in ('plan', 'step')) == gate_lines else None


def _repaired(run, sha):   # a forger who also repairs the hash chain: every line numbered and hashed again, and the root with them
    prev = 'GENESIS'
    for i, e in enumerate(run['trace']):
        e['seq'], e['prev_sha256'] = i + 1, prev
        e['sha256'] = sha({k: v for k, v in e.items() if k != 'sha256'})
        prev = e['sha256']
    run['trace_root_sha256'] = prev


def _covered(cid):
    """Whether a case is one the every-case claim is about: this version's own three, and the cases of the lab it was added to (numbered up to 50).
    What another added version brings is its own to check. A case id is any plain name (another version's 67a_x begins with no whole number): such a case is not counted."""
    head = cid.split('_')[0]
    return cid in OWN_CASES or (head.isascii() and head.isdigit() and int(head) <= 50)


def every_case_claims(data, ROOT, sha, check_chain):
    scope = [c for c in data['cases'] if _covered(c['id'])]
    rows = [_explained(c, ROOT, sha, check_chain) for c in scope]
    flat = [x for r in rows if r for x in r]
    words = {x['authority_verdict'] for x in flat}
    steps = [x for x in flat if x['phase'] == 'step' and x['authority_verdict'] == 'granted']
    halted = [x for x in steps if [f for f in x['factors'] if f['type'] == 'stopped']]

    def refused(cid, change, repair, chains):
        """Whether a forged copy of one case is not explained, with its hash chains in the state the forgery means them to be in (`chains`):
        so each forgery below is refused for the one reason it names, not for a chain it broke on the way."""
        c = json.loads(json.dumps(_case(data, cid)))
        change(c['run']['runs'])
        for r in c['run']['runs'] if repair else []:
            _repaired(r, sha)
        return _whole_chains(c['run']['runs'], check_chain) is chains and _explained(c, ROOT, sha, check_chain) is None

    def no_effect(runs):                                                 # the first step's receipt line is gone
        t = runs[0]['trace']
        del t[[e['operation'] for e in t].index('LOCAL_EFFECT')]

    def turned_away(runs):                                               # the fee, which the gate turned away as a plan, dressed as a step the gate turned away
        t = runs[1]['trace']
        at = [e['operation'] for e in t].index('ADMISSION')
        t.insert(at, {'operation': 'SELECT', 'data': {'actions': t[at]['data']['methods']}})
        t.insert(at + 2, {'operation': 'STEP_STOPPED', 'data': {'method': t[at + 1]['data']['methods'][0], 'reason': 'Gate changed before effect: AUTHORITY_REQUIRED'}})

    forgeries = [
        ('24_budget', lambda runs: runs[0]['trace'][0]['data'].update(goal='another_goal'), False, False),                   # a line edited and the chain left as it was: the chain does not hold
        ('24_budget', lambda runs: runs[0]['provenance'][-1].update(sha256='0' * 64), False, True),                          # a pack that is not its file
        ('24_budget', lambda runs: _lines(runs[0], 'ADMISSION')[0]['data'].update(accepted=True, blockers=[]), True, True),  # the gate said yes where the pack files' books say no
        ('58_gate_decisions', no_effect, True, True),                                                                        # a step at the gate with no effect and no stop after it
        ('58_gate_decisions', lambda runs: _lines(runs[0], 'LOCAL_EFFECT')[0]['data']['receipt'].update(method=runs[0]['actions'][1]), True, True),   # a step followed by another step's receipt
        ('30_stop', lambda runs: _lines(runs[0], 'STEP_STOPPED')[0]['data'].update(method=runs[0]['actions'][0]), True, True),                        # a stop that names another step
        ('58_gate_decisions', turned_away, True, True)]                                                                      # a step the gate turned away after admitting its plan
    alive = [i for i, forgery in enumerate(forgeries) if not refused(*forgery)]
    return {'S89_the_pack_files_books_explain_every_gate_line_of_every_case_of_this_version': (
        # the count in the next line is written here, not derived: the cases numbered up to 50 of the lab this version was reviewed on (the built-in cases of its base
        # and must-cohere's case 50) and its own three. On a lab that holds another number of such cases this claim fails with nothing wrong in the version, until the
        # count is edited with the lab; deriving it is owed to the next version (the confirming review)
        len(scope) == 35 and all(r is not None for r in rows) and words == {'granted', 'denied', 'escalated', 'not_evaluated'}
        # on every case: a granted step has its receipt or the stop that followed it, never both and never neither; the one stopped step is case 30's
        and all((x['output_ref'] is None) == bool([f for f in x['factors'] if f['type'] == 'stopped']) for x in steps) and len(halted) == 1
        and not alive)}


# ---------------------------------------------------------------------------------------------- R101: problem styles
def style_claims(data, ROOT, sha):
    desk, book, incident, campaign = (_file(ROOT, n) for n in STYLE_DESK + ['139_style_campaign'])
    routed = {n: _file(ROOT, n) for n in ('136_routed_by_the_book', '137_routed_incident', '138_routed_unmatched')}
    goal = desk['goals'][0]
    decl = [r for r in desk['rules'] if r['head'] == goal][0]            # the declaration: one branch per declared style, [the router's row, the card's head], then the fallback
    decl2 = [r for r in campaign['rules'] if r['head'] == goal][0]
    guards, heads = [br[0] for br in decl['branches']], [br[1] for br in decl['branches']]
    fallback = [m for m in desk['methods'] if m['action'] == 'ask']      # the one question the declaration's last branch rests on
    card = lambda p: [r for r in p['rules'] if 'card' in r][0]
    own = lambda p: [m['id'] for m in p['methods']]
    makes = lambda p: sorted(m['effect'] for m in p['methods'])
    asks = lambda p: [m for m in p['methods'] if m['action'] == 'ask']
    word = lambda p: [[x['predicate'], x['truth'], x['verified'], x['source']] for x in p['evidence']]
    sc, case = data['scenes']['queue_styles'], _case(data, '59_style_unmatched')
    standing = ('unrouted', 'by_the_book', 'incident', 'old_style_under_new', 'other_old_style_under_new', 'unlisted', 'unmatched')
    events = ('answered_no', 'new_style', 'answered_yes')
    if len(fallback) != 1 or any(len(sc[k]['runs']) != 1 for k in standing + events):
        return {'S86_two_styles_give_one_goal_two_plans_each_from_its_own_card': False, 'S87_an_unmatched_problem_asks_the_charter_owner_and_a_new_card_closes_it': False}
    fb = fallback[0]
    run = lambda k: sc[k]['runs'][0]
    a, b, none, unlisted, lost, old, old2 = (run(k) for k in standing[1:3] + ('unrouted', 'unlisted', 'unmatched', 'old_style_under_new', 'other_old_style_under_new'))
    no, new, yes = run('answered_no'), run('new_style'), run('answered_yes')
    selected = lambda r: [e['data']['actions'] for e in _lines(r, 'SELECT')]
    refined = lambda r: [e['data']['rule'] for e in _lines(r, 'REFINE')]
    loaded = lambda r: [p['pack'] for p in r['provenance']]
    said = lambda r: [[e['data']['predicate'], e['data']['source']] for e in _lines(r, 'RETAIN') if e['data']['predicate'].startswith('styled_')]   # the router's rows this run read
    built = lambda *more: _built(ROOT, STYLE_DESK + list(more), sha)
    after = lambda k, b, *runs: sha(sc['after_' + k]) == sha(_paid(b, runs))
    router = routed['138_routed_unmatched']['evidence'][0]['source']
    names = lambda guard: {'predicate': guard, 'truth': 'TRUE', 'verified': True, 'source': router, 'version': 'r2'}   # the router's row as tools/scenes/queue_styles.py sends it
    asked = lost['model_receipts'][-1] if lost['model_receipts'] else {}
    key = '%s|%s' % (desk['scope'], fb['effect'])
    new_guard = decl2['branches'][-1][0]
    FIELDS = {'style', 'what_is_missing', 'cause_effect', 'reach', 'cadence', 'vehicle', 'verify', 'gate', 'unmatched'}
    zero = {d: 0 for d in desk['budget']}
    return {
        'S86_two_styles_give_one_goal_two_plans_each_from_its_own_card': (
            all(sha([sc[k]['status'], sc[k]['goals'], run(k)['goal']]) == sha(['EVALUATED', [goal], goal]) for k in standing)
            and loaded(a) == STYLE_DESK + ['136_routed_by_the_book'] and loaded(b) == STYLE_DESK + ['137_routed_incident']
            and a['provenance'] == built('136_routed_by_the_book')['loaded'] and b['provenance'] == built('137_routed_incident')['loaded']
            # the router's word is one row: the style it matched, and nothing about the others
            and word(routed['136_routed_by_the_book']) == [[guards[0], 'TRUE', True, router]] and word(routed['137_routed_incident']) == [[guards[1], 'TRUE', True, router]]
            and said(a) == [[guards[0], router]] and said(b) == [[guards[1], router]]
            # the declaration: one branch per style (the router's row, then the card's head), and a last one for the unmatched
            and len(decl['branches']) == 3 and all(len(br) == 2 for br in decl['branches']) and len(set(guards)) == 3
            and [card(book)['head'], card(incident)['head']] == heads[:2] and len(set(heads)) == 3
            and all(set(card(p)['card']) == FIELDS for p in (book, incident, campaign))                # a card: four descriptors and four handling defaults, as pack content
            and selected(a) == [own(book)] and selected(b) == [own(incident)] and not set(own(book)) & set(own(incident))
            and makes(book) == sorted(card(book)['branches'][0]) and makes(incident) == sorted(card(incident)['branches'][0])   # each plan makes exactly its own card's done-when
            and refined(a) == [decl['id'], card(book)['id']] and refined(b) == [decl['id'], card(incident)['id']]
            and a['selected_branch'] == decl['id'] + '/OR1' and b['selected_branch'] == decl['id'] + '/OR2'
            and (a['status'], a['work_state'], a['actions']) == ('LOCAL_MODEL_EFFECTS_RECORDED', 'completed', own(book))
            and (b['status'], b['work_state'], b['actions'] + b['pending']) == ('WAITING', 'waiting', own(incident))
            # the gate posture rides on the card: the auto card has no ask among its methods and runs through; the ask card parks on the party it names
            and card(book)['card']['gate'] == 'auto' and not asks(book) and card(incident)['card']['gate'] == 'ask' and len(asks(incident)) == 1
            and b['waits'] == [asks(incident)[0]['id']] and b['model_receipts'][-1].get('parked') is True
            and b['model_receipts'][-1]['ask']['to'] == asks(incident)[0]['ask_to'] and not [x for x in a['model_receipts'] if x.get('parked')]
            and after('by_the_book', built(), a) and after('incident', built(), b)),
        'S87_an_unmatched_problem_asks_the_charter_owner_and_a_new_card_closes_it': (
            # the fallback is declared: the last branch is the router's own word that nothing matched, then the charter owner's answer to one question
            decl['branches'][2] == [guards[2], fb['effect']] and fb['ask_to'] == 'charter-owner' and fb['provider'] == 'charter-owner' and fb['cost']['attention'] == 1
            and word(routed['138_routed_unmatched']) == [[guards[2], 'TRUE', True, router]]
            # unmatched (case 59): no card runs; the goal asks that one question, pays for it once and waits; the run cites the router's row
            and loaded(lost) == STYLE_DESK + ['138_routed_unmatched'] and lost['provenance'] == built('138_routed_unmatched')['loaded']
            and case['packs'] == loaded(lost) and case['outcome']['trace_root_sha256'] == lost['trace_root_sha256'] and _roots(case['run']) == [lost['trace_root_sha256']]
            and sha([case['run']['status'], case['run']['goals'], [r['goal'] for r in case['run']['runs']]]) == sha(['EVALUATED', [goal], [goal]])
            and sha([lost['status'], lost['work_state'], lost['actions'], lost['pending'], lost['waits'], lost['selected_branch'], lost['cost']])
            == sha(['WAITING', 'waiting', [fb['id']], [], [fb['id']], decl['id'] + '/OR3', fb['cost']])
            and selected(lost) == [[fb['id']]] and refined(lost) == [decl['id']] and said(lost) == [[guards[2], router]]
            and len(lost['model_receipts']) == 1 and asked.get('parked') is True
            and sha(asked['ask']) == sha({'predicate': fb['effect'], 'question': fb['question'], 'to': fb['ask_to'], 'asked_in': asked['ask']['asked_in']})
            and after('unmatched', built(), lost) and sha(case['derived_state']['budget_after']) == sha(_paid(built(), [lost])['budget'])
            and case['outcome']['learning'] == []                              # a question that is out is not a gap: nothing is proposed
            # before the router has spoken the goal blocks and names the rows it reads: each declared style and the unmatched word
            and loaded(none) == STYLE_DESK and sha([none['status'], none['stop_reasons'], none['actions'], none['model_receipts'], none['selected_branch']]) == sha(['QUERY_EVIDENCE', ['QUERY_EVIDENCE'], [], [], None])
            and _named(none, 'QUERY_EVIDENCE') == guards and after('unrouted', built())
            # a style the declaration does not list: the row arrives, no goal reads it, and the look that follows is line for line the look before the router spoke
            and new_guard not in guards and sha(sc['unlisted_named']) == sha({'status': 'RECONCILED', 'event': names(new_guard), 'affected': [], 'runs': []})
            and unlisted['trace_root_sha256'] == none['trace_root_sha256'] and sha(unlisted) == sha(none) and loaded(unlisted) == STYLE_DESK and after('unlisted', built())
            # the owner says no: a decision. The goal stops as REFUSED and nobody is asked again; nothing more is paid
            and sha(sc['answered_no']['event']) == sha(_stamp(asked, 'FALSE')) and sha([sc['answered_no']['status'], sc['answered_no']['affected']]) == sha(['RECONCILED', [goal]])
            and sha([no['status'], no['work_state'], no['stop_reasons'], no['actions'], no['model_receipts'], no['selected_branch']]) == sha(['REFUSED', 'blocked', ['QUERY_EVIDENCE', 'REFUSED'], [], [], None])
            and [sha(e['data']) for e in _lines(no, 'REFUSED')] == [sha({'predicate': fb['effect'], 'source': 'STAMP:' + fb['ask_to']})]
            and [sha(e['data']) for e in _lines(no, 'ASK_CLOSED')] == [sha({'ask': key, 'receipt': asked['sha256'], 'truth': 'FALSE', 'source': 'STAMP:' + fb['ask_to']})]
            and no['provenance'] == lost['provenance'] and after('no', built(), lost)
            # a new style: one more card and a declaration that cites the one it replaces and keeps its branches; the router names it and the goal plans from the new card
            and decl2['replaces'] == decl['id'] and decl2['branches'] == decl['branches'] + [[new_guard, card(campaign)['head']]]
            and sha(sc['new_style']['event']) == sha(names(new_guard)) and sha([sc['new_style']['status'], sc['new_style']['affected']]) == sha(['RECONCILED', [goal]])
            and new['provenance'] == built('138_routed_unmatched', '139_style_campaign')['loaded']
            and sha([new['status'], new['work_state'], new['actions'], new['selected_branch']]) == sha(['LOCAL_MODEL_EFFECTS_RECORDED', 'completed', own(campaign), decl2['id'] + '/OR4'])
            and selected(new) == [own(campaign)] and refined(new) == [decl2['id'], card(campaign)['id']] and makes(campaign) == sorted(card(campaign)['branches'][0])
            and not set(own(campaign)) & set(own(book) + own(incident) + [fb['id']])
            and said(new) == [[guards[2], router], [new_guard, router]] and _named(new, 'REFUSED') == [fb['effect']]   # the owner's no still stands on the fallback; the new card is another route
            and after('new_style', built('139_style_campaign'), lost, new)
            # the owner says yes, on a second State: a new home. The goal is closed for this desk by that decision, with no step of any card
            and sha(sc['answered_yes']['event']) == sha(_stamp(asked, 'TRUE')) and sha([sc['answered_yes']['status'], sc['answered_yes']['affected']]) == sha(['RECONCILED', [goal]])
            and sha([yes['status'], yes['work_state'], yes['actions'], yes['model_receipts'], yes['cost'], yes['selected_branch']])
            == sha(['SUPPORTED_BY_EVIDENCE', 'completed', [], [], zero, decl['id'] + '/OR3'])
            and selected(yes) == [[]] and yes['provenance'] == lost['provenance'] and after('yes', built(), lost)
            and [sha(e['data']) for e in _lines(yes, 'ASK_CLOSED')] == [sha({'ask': key, 'receipt': asked['sha256'], 'truth': 'TRUE', 'source': 'STAMP:' + fb['ask_to']})]
            # the two older cards are the same files and plan as before under the new declaration
            and old['provenance'] == built('136_routed_by_the_book', '139_style_campaign')['loaded'] and old['provenance'][:4] == a['provenance']
            and sha([old['status'], old['actions'], old['selected_branch'], old['cost']]) == sha([a['status'], a['actions'], decl2['id'] + '/OR1', a['cost']])
            and after('old_style_under_new', built('139_style_campaign'), old) and sha(sc['after_old_style_under_new']) == sha(sc['after_by_the_book'])
            and old2['provenance'] == built('137_routed_incident', '139_style_campaign')['loaded'] and old2['provenance'][:4] == b['provenance']
            and sha([old2['status'], old2['actions'], old2['pending'], old2['waits'], old2['selected_branch'], old2['cost']])
            == sha([b['status'], b['actions'], b['pending'], b['waits'], decl2['id'] + '/OR2', b['cost']])
            and after('other_old_style_under_new', built('139_style_campaign'), old2) and sha(sc['after_other_old_style_under_new']) == sha(sc['after_incident'])),
    }


# ---------------------------------------------------------------------------------------------- the checks, and the same claims on forged records
def checks(data, ROOT, sha, check_chain):
    groups = {'rank': lambda d: rank_claims(d, ROOT, sha), 'provenance': lambda d: provenance_claims(d, ROOT, sha, check_chain), 'styles': lambda d: style_claims(d, ROOT, sha)}
    reads = {'rank': (('57_queue_ranked',), 'queue_rank'), 'provenance': (('58_gate_decisions', '30_stop'), 'queue_provenance'), 'styles': (('59_style_unmatched',), 'queue_styles')}
    mine = lambda d, group: {'cases': [c for c in d['cases'] if c['id'] in reads[group][0]],
                             'scenes': {reads[group][1]: d['scenes'][reads[group][1]]}}   # what a group's claims read, and nothing else: a forged copy is a copy of this
    honest, was = {}, {}   # per group: what its claims read, as text, and the sha256 of that; filled below, where a record that cannot be read is one failed row and not an error

    def survives(group, change):
        d = json.loads(honest[group])   # a fresh copy of what the claims read, for each forgery
        try:
            change(d)
            return sha(d) == was[group] or all(groups[group](d).values())   # a forgery that changes nothing is not a forgery: it counts as one that survived
        except Exception:
            return False   # a record so wrong that the claims cannot be read (or the forgery cannot even be made) has failed them

    case = lambda d, cid: [c for c in d['cases'] if c['id'] == cid][0]
    q = lambda d: d['scenes']['queue_rank']
    p = lambda d: d['scenes']['queue_provenance']
    s = lambda d: d['scenes']['queue_styles']
    gate = lambda r: [e['data'] for e in r['trace'] if e['operation'] == 'ADMISSION'][0]
    verdict = lambda d, word: [x for x in p(d)['decisions'] if x['authority_verdict'] == word][0]
    names = lambda r, operation: [e['data'] for e in r['trace'] if e['operation'] == operation]
    one = lambda d, k: s(d)[k]['runs'][0]
    kind = lambda rows, t: [f for x in rows for f in x['factors'] if f['type'] == t]
    forged = {
        'rank': [lambda d: q(d)['as_ranked']['runs'].reverse(),
                 lambda d: q(d)['as_ranked'].update(goals=list(q(d)['as_listed']['goals'])),
                 lambda d: q(d)['as_listed'].update(status='NO_STANDING_GOAL'),
                 lambda d: q(d)['ranking']['goals'].reverse(),
                 lambda d: q(d)['ranking']['ranked_by'][0].update(impact=1),
                 lambda d: q(d)['ranking']['ranked_by'][0].update(impact=9.0),
                 lambda d: q(d)['ranking'].update(grants=['action:write-1041@1']),
                 lambda d: q(d)['as_ranked']['runs'][0]['provenance'].pop(),
                 lambda d: q(d)['as_ranked']['runs'][1]['provenance'][-1].update(sha256='0' * 64),
                 lambda d: q(d)['before_ranking']['budget'].update(attention=99),
                 lambda d: q(d)['before_ranking']['providers'].update({'collections-desk': 4}),
                 lambda d: q(d)['before_ranking']['goals'].reverse(),
                 lambda d: q(d)['after_ranking']['budget'].update(money=9),
                 lambda d: q(d)['after_ranking']['grants'].pop(),
                 lambda d: q(d)['after_ranking']['loaded'].pop(),
                 lambda d: q(d)['after_ranking']['goals'].reverse(),
                 lambda d: q(d)['after_ranking_again']['loaded'].append(dict(q(d)['after_ranking_again']['loaded'][-1])),
                 lambda d: q(d)['after_listed']['goals'].reverse(),
                 lambda d: q(d)['after_listed']['budget'].update(compute=10),
                 lambda d: q(d)['after_listed']['providers'].update({'collections-desk': 5}),
                 lambda d: q(d)['after_ranked']['budget'].update(attention=1),
                 lambda d: q(d)['after_ranked']['budget'].update(attention=0.0),
                 lambda d: q(d)['after_ranked']['budget'].update(money=10),
                 lambda d: q(d)['after_ranked']['providers'].update({'collections-desk': 5}),
                 lambda d: q(d)['after_ranked']['loaded'][0].update(sha256='0' * 64),
                 lambda d: q(d)['as_listed']['runs'][2].update(work_state='completed'),
                 lambda d: q(d)['as_listed']['runs'][0]['model_receipts'].clear(),
                 lambda d: q(d)['as_listed']['runs'][0].update(actions=['write-1041@1']),
                 lambda d: q(d)['as_listed']['runs'][0].update(pareto_options=1),
                 lambda d: q(d)['as_ranked']['runs'][3].update(actions=['call-1041@1']),
                 lambda d: q(d)['as_ranked']['runs'][3].update(pareto_options=2),
                 lambda d: q(d)['as_ranked']['runs'][3].update(cost={'compute': 1, 'money': 0, 'attention': 1}),
                 lambda d: [r.update(selected_branch='R-PROMISE-1042@1/OR2') for res in (q(d)['as_listed'], q(d)['as_ranked']) for r in res['runs'] if r['goal'] == 'loan_1042_promise'],
                 lambda d: gate(q(d)['as_ranked']['runs'][2]).update(blockers=['AUTHORITY_REQUIRED']),
                 lambda d: gate(q(d)['as_ranked']['runs'][3]).update(accepted=True, blockers=[]),
                 lambda d: gate(q(d)['as_listed']['runs'][3]).update(accepted=True),
                 lambda d: q(d)['as_ranked']['runs'][2].update(status='PROVIDER_REQUIRED'),
                 lambda d: case(d, '57_queue_ranked')['run']['goals'].reverse(),
                 lambda d: case(d, '57_queue_ranked')['run'].update(status='NO_STANDING_GOAL'),
                 lambda d: case(d, '57_queue_ranked')['run']['runs'].pop(),
                 lambda d: case(d, '57_queue_ranked')['run']['runs'][0].update(trace_root_sha256='0' * 64),
                 lambda d: case(d, '57_queue_ranked')['run']['runs'][3].update(actions=['call-1041@1']),
                 lambda d: case(d, '57_queue_ranked')['derived_state']['budget_after'].update(attention=2),
                 lambda d: case(d, '57_queue_ranked').update(packs=[QUEUE]),
                 lambda d: q(d)['not_ranked'][0].update(refused=None),
                 lambda d: q(d)['not_ranked'][1].update(refused='No declared impact for standing goal: loan_7001_disbursed'),
                 lambda d: q(d)['not_ranked'][2]['after']['goals'].reverse(),
                 lambda d: [x['goals'].reverse() for x in (q(d)['not_ranked'][2]['before'], q(d)['not_ranked'][2]['after'])],
                 lambda d: [x['budget'].update(money=1) for x in (q(d)['not_ranked'][1]['before'], q(d)['not_ranked'][1]['after'])],
                 lambda d: q(d)['not_ranked'][0]['after']['loaded'].append({'pack': 'never-applied', 'sha256': '0' * 64}),
                 lambda d: q(d)['not_ranked'].pop(),
                 lambda d: q(d)['not_ranked'][0].update(packs=['01_domain'])],
        'provenance': [lambda d: verdict(d, 'denied').update(authority_verdict='granted'),
                       lambda d: verdict(d, 'escalated').update(authority_verdict='granted'),
                       lambda d: verdict(d, 'not_evaluated').update(authority_verdict='denied'),
                       lambda d: verdict(d, 'granted').update(authority_verdict='denied'),
                       lambda d: kind(p(d)['decisions'], 'budget_short')[0].update(value='money: needs 9, has 10'),
                       lambda d: kind(p(d)['decisions'], 'grant_missing')[0].update(type='grant_held'),
                       lambda d: kind(p(d)['decisions'], 'provider_short')[0].update(value='print-room: needs 1, has 1'),
                       lambda d: [f for f in kind(p(d)['decisions'], 'budget_fits') if f['value'] == 'attention: needs 1, has 1'][0].update(type='budget_short'),
                       lambda d: p(d)['decisions'].pop(0),
                       lambda d: p(d)['decisions'].reverse(),
                       lambda d: p(d)['decisions'].append(dict(p(d)['decisions'][-1])),
                       lambda d: p(d)['decisions'][1].update(output_ref='0' * 64),
                       lambda d: p(d)['decisions'][1].update(output_ref=None),
                       lambda d: p(d)['decisions'][0].update(output_ref=p(d)['decisions'][1]['output_ref']),
                       lambda d: p(d)['decisions'][1].update(decision_seq=1.0),
                       lambda d: p(d)['decisions'][0].update(turn_id='0' * 64),
                       lambda d: p(d)['decisions'][0].update(charter_ref='C-loan-desk'),
                       lambda d: p(d)['decisions'][0].update(ts='2026-11-13T00:00:00Z'),
                       lambda d: p(d)['decisions'][0].update(work_ref='another_goal'),
                       lambda d: p(d)['decisions'][0]['factors'][0].update(source_ref='trace:1'),
                       lambda d: p(d)['decisions'][0].pop('channels'),
                       lambda d: p(d)['decisions'][0].update(channels=['STAMP:credit-head']),
                       lambda d: p(d)['decisions'][0].update(approval_ref=verdict(d, 'escalated')['approval_ref']),
                       lambda d: verdict(d, 'escalated').update(approval_ref=None),
                       lambda d: verdict(d, 'escalated').update(channels=['mallory']),
                       lambda d: verdict(d, 'escalated').update(output_ref=verdict(d, 'escalated')['approval_ref']),
                       lambda d: p(d)['decisions_after_no'][0].update(authority_verdict='granted'),
                       lambda d: p(d)['decisions_after_no'][0].update(channels=[]),
                       lambda d: p(d)['decisions_after_no'][0].update(approval_ref=None),
                       lambda d: p(d)['decisions_after_yes'][1].update(output_ref=None),
                       lambda d: p(d)['decisions_after_yes'].pop(),
                       lambda d: p(d)['decisions_after_yes'][0].update(approval_ref=None),
                       lambda d: p(d)['decisions_after_yes'][1].update(approval_ref='0' * 64),
                       lambda d: p(d)['decisions_after_yes'][1].update(channels=[]),
                       lambda d: p(d)['decisions_after_yes'][1].update(channels=['STAMP:mallory']),
                       lambda d: p(d)['decisions_after_yes'][1]['factors'].pop(),
                       lambda d: p(d)['decisions_after_yes'][0]['factors'][-1].update(value='head_7003_approved: TRUE, decided by STAMP:mallory'),
                       lambda d: p(d)['decisions_after_yes'][0]['factors'][-1].update(source_ref='trace:10'),
                       lambda d: p(d)['decisions_of_a_stopped_step'][-1]['factors'].pop(),
                       lambda d: p(d)['decisions_of_a_stopped_step'][-1]['factors'][-1].update(value='Handler refused: something else'),
                       lambda d: p(d)['decisions_of_a_stopped_step'][-1]['factors'][-1].update(source_ref='trace:17'),
                       lambda d: p(d)['decisions_of_a_stopped_step'][-1].update(output_ref=p(d)['decisions_of_a_stopped_step'][-2]['output_ref']),
                       lambda d: p(d)['decisions_of_a_stopped_step'][-1].update(authority_verdict='denied'),
                       lambda d: p(d)['decisions_of_a_stopped_step'][1]['factors'].append(dict(p(d)['decisions_of_a_stopped_step'][-1]['factors'][-1])),
                       lambda d: p(d)['decisions_of_a_stopped_step'].pop(),
                       lambda d: p(d)['books_before']['budget'].update(money=11),
                       lambda d: p(d)['books_before']['budget'].update(attention=True),
                       lambda d: p(d)['books_after']['providers'].update({'credit-head': 1}),
                       lambda d: p(d)['books_after']['budget'].update(compute=9),
                       lambda d: p(d)['books_before']['grants'].append('action:waive-fee-7002@1'),
                       lambda d: p(d).update(wrong_books_refused=None),
                       lambda d: p(d)['answered_no']['event'].update(truth='TRUE'),
                       lambda d: p(d)['answered_no']['event'].update(answers='0' * 64),
                       lambda d: p(d)['answered_no']['event'].update(final=1),
                       lambda d: p(d)['answered_no']['event'].update(verified=1),
                       lambda d: p(d)['answered_no']['event'].update(source='STAMP:mallory'),
                       lambda d: p(d)['answered_no']['event'].update(version='ask-000000000000'),
                       lambda d: p(d)['answered_no']['event'].update(scope='lendco/elsewhere'),
                       lambda d: p(d)['answered_no'].update(affected=[]),
                       lambda d: p(d)['answered_no'].update(status='DECISION_STANDS'),
                       lambda d: p(d)['answered_yes']['event'].update(source='STAMP:mallory'),
                       lambda d: p(d)['answered_yes']['event'].update(answers='0' * 64),
                       lambda d: p(d)['answered_yes']['event'].update(final=False),
                       lambda d: p(d)['answered_yes']['event'].update(final=1),
                       lambda d: p(d)['answered_yes']['event'].update(verified=False),
                       lambda d: p(d)['answered_yes']['event'].update(verified=1),
                       lambda d: p(d)['answered_yes']['event'].update(predicate='another_fact'),
                       lambda d: p(d)['answered_yes']['event'].update(scope='lendco/elsewhere'),
                       lambda d: p(d)['answered_yes']['event'].update(version='ask-000000000000'),
                       lambda d: p(d)['answered_yes']['event'].update(truth='FALSE'),
                       lambda d: p(d)['answered_yes'].update(affected=[]),
                       lambda d: p(d)['answered_yes'].update(status='UNVERIFIED_EVENT_IGNORED'),
                       lambda d: p(d)['answered_yes']['runs'][0].update(actions=[]),
                       lambda d: p(d)['answered_yes']['runs'][0].update(selected_branch='R-LIMIT-7003@1/OR2'),
                       lambda d: p(d)['answered_no']['runs'][0].update(selected_branch='R-LIMIT-7003@1/OR1'),
                       lambda d: p(d)['answered_yes']['runs'][0]['provenance'][0].update(sha256='0' * 64),
                       lambda d: p(d)['answered_no']['runs'].append(dict(p(d)['answered_no']['runs'][0])),
                       lambda d: gate(case(d, '58_gate_decisions')['run']['runs'][1]).update(accepted=True, blockers=[]),
                       lambda d: case(d, '58_gate_decisions')['run']['runs'][0]['provenance'][0].update(sha256='0' * 64),
                       lambda d: [r['provenance'].clear() for r in case(d, '58_gate_decisions')['run']['runs'] if r['work_state'] == 'blocked'],
                       lambda d: case(d, '58_gate_decisions')['run']['goals'].reverse(),
                       lambda d: case(d, '58_gate_decisions')['run'].update(status='NO_STANDING_GOAL'),
                       lambda d: case(d, '58_gate_decisions')['derived_state']['budget_after'].update(money=9),
                       lambda d: case(d, '58_gate_decisions')['derived_state'].pop('budget_after'),
                       lambda d: case(d, '58_gate_decisions').update(packs=[]),
                       lambda d: case(d, '30_stop')['run']['runs'][0]['stopped'].update(reason='Handler refused: something else'),
                       lambda d: case(d, '30_stop')['run']['runs'][0]['model_receipts'].pop(),
                       lambda d: case(d, '30_stop')['run']['runs'][0].update(status='LOCAL_MODEL_EFFECTS_RECORDED')],
        'styles': [lambda d: one(d, 'by_the_book').update(actions=list(one(d, 'incident')['actions'])),
                   lambda d: one(d, 'by_the_book').update(goal='another_goal'),
                   lambda d: one(d, 'by_the_book').update(selected_branch='R-STYLES@1/OR2'),
                   lambda d: one(d, 'by_the_book').update(status='WAITING'),
                   lambda d: names(one(d, 'by_the_book'), 'REFINE')[1].update(rule='R-STYLE-INCIDENT@1'),
                   lambda d: names(one(d, 'by_the_book'), 'SELECT')[0]['actions'].append('write-cause-8801@1'),
                   lambda d: names(one(d, 'by_the_book'), 'RETAIN')[0].update(source='walk-in/anyone'),
                   lambda d: one(d, 'by_the_book')['provenance'].pop(),
                   lambda d: s(d)['by_the_book'].update(status='NO_STANDING_GOAL'),
                   lambda d: one(d, 'by_the_book')['model_receipts'][0].update(parked=True),
                   lambda d: s(d)['after_by_the_book']['budget'].update(money=10),
                   lambda d: [s(d)[k]['budget'].update(money=10) for k in ('after_by_the_book', 'after_old_style_under_new')],
                   lambda d: s(d)['after_by_the_book']['providers'].update({'ops-desk': 4}),
                   lambda d: one(d, 'incident').update(status='LOCAL_MODEL_EFFECTS_RECORDED'),
                   lambda d: one(d, 'incident').update(waits=[]),
                   lambda d: one(d, 'incident').update(pending=[]),
                   lambda d: one(d, 'incident')['model_receipts'][-1]['ask'].update(to='mallory'),
                   lambda d: one(d, 'incident')['model_receipts'][-1].update(parked=1),
                   lambda d: s(d)['after_incident']['budget'].update(attention=2),
                   lambda d: s(d)['incident'].update(goals=['complaint_8801_closed', 'another_goal']),
                   lambda d: one(d, 'unmatched').update(status='PLAN_READY'),
                   lambda d: one(d, 'unmatched').update(actions=['match-ledger-8801@1']),
                   lambda d: one(d, 'unmatched').update(waits=[]),
                   lambda d: one(d, 'unmatched').update(selected_branch='R-STYLES@1/OR1'),
                   lambda d: one(d, 'unmatched').update(cost={'compute': 0, 'money': 0, 'attention': 0}),
                   lambda d: one(d, 'unmatched')['model_receipts'][-1]['ask'].update(to='ops-head'),
                   lambda d: one(d, 'unmatched')['model_receipts'][-1]['ask'].update(question='Another question?'),
                   lambda d: one(d, 'unmatched')['model_receipts'][-1].update(parked=1),
                   lambda d: names(one(d, 'unmatched'), 'RETAIN')[0].update(source='walk-in/anyone'),
                   lambda d: names(one(d, 'unmatched'), 'SELECT')[0]['actions'].append('match-ledger-8801@1'),
                   lambda d: one(d, 'unmatched').update(trace_root_sha256='0' * 64),
                   lambda d: one(d, 'unmatched')['provenance'][1].update(sha256='0' * 64),
                   lambda d: s(d)['after_unmatched']['budget'].update(attention=2),
                   lambda d: s(d)['after_unmatched']['providers'].update({'charter-owner': 1}),
                   lambda d: one(d, 'unrouted').update(status='METHOD_ABSENT'),
                   lambda d: one(d, 'unrouted').update(selected_branch='R-STYLES@1/OR1'),
                   lambda d: one(d, 'unlisted').update(selected_branch='R-STYLES@1/OR1'),
                   lambda d: one(d, 'unlisted').update(needs=['styled_campaign']),
                   lambda d: one(d, 'answered_no').update(selected_branch='R-STYLES@1/OR3'),
                   lambda d: names(one(d, 'unrouted'), 'QUERY_EVIDENCE')[2].update(predicate='styled_campaign'),
                   lambda d: one(d, 'unrouted')['trace'].pop(4),
                   lambda d: s(d)['after_unrouted']['budget'].update(attention=1),
                   lambda d: s(d)['unlisted_named'].update(affected=['complaint_8801_closed']),
                   lambda d: s(d)['unlisted_named']['event'].update(predicate='styled_incident'),
                   lambda d: s(d)['unlisted_named']['event'].update(source='walk-in/anyone'),
                   lambda d: s(d)['unlisted_named']['event'].update(verified=1),
                   lambda d: s(d)['unlisted_named'].update(status='UNVERIFIED_EVENT_IGNORED'),
                   lambda d: one(d, 'unlisted').update(trace_root_sha256='0' * 64),
                   lambda d: s(d)['after_unlisted']['providers'].update({'ops-desk': 3}),
                   lambda d: s(d)['answered_no']['event'].update(source='STAMP:ops-head'),
                   lambda d: s(d)['answered_no']['event'].update(final=1),
                   lambda d: s(d)['answered_no']['event'].update(answers='0' * 64),
                   lambda d: s(d)['answered_no'].update(affected=[]),
                   lambda d: one(d, 'answered_no').update(status='QUERY_EVIDENCE'),
                   lambda d: one(d, 'answered_no').update(stop_reasons=['REFUSED']),
                   lambda d: names(one(d, 'answered_no'), 'REFUSED')[0].update(source='STAMP:ops-head'),
                   lambda d: s(d)['after_no']['budget'].update(attention=0),
                   lambda d: one(d, 'new_style').update(actions=[]),
                   lambda d: one(d, 'new_style').update(selected_branch='R-STYLES@1/OR1'),
                   lambda d: one(d, 'new_style')['provenance'].pop(),
                   lambda d: one(d, 'new_style')['provenance'][1].update(sha256='0' * 64),
                   lambda d: s(d)['new_style']['event'].update(predicate='styled_by_the_book'),
                   lambda d: s(d)['new_style']['event'].update(source='walk-in/anyone'),
                   lambda d: s(d)['new_style'].update(affected=[]),
                   lambda d: s(d)['after_new_style']['budget'].update(money=10),
                   lambda d: s(d)['after_new_style']['providers'].update({'ops-desk': 4}),
                   lambda d: s(d)['answered_yes']['event'].update(source='STAMP:mallory'),
                   lambda d: s(d)['answered_yes']['event'].update(final=1),
                   lambda d: s(d)['answered_yes']['event'].update(truth='FALSE'),
                   lambda d: s(d)['answered_yes']['event'].update(answers='0' * 64),
                   lambda d: s(d)['answered_yes'].update(affected=[]),
                   lambda d: one(d, 'answered_yes').update(status='LOCAL_MODEL_EFFECTS_RECORDED'),
                   lambda d: one(d, 'answered_yes').update(actions=['match-ledger-8801@1']),
                   lambda d: one(d, 'answered_yes').update(selected_branch='R-STYLES@1/OR1'),
                   lambda d: one(d, 'answered_yes')['provenance'].pop(),
                   lambda d: s(d)['after_yes']['budget'].update(compute=9),
                   lambda d: case(d, '59_style_unmatched')['outcome'].update(learning=[{'kind': 'INVESTIGATE_GAP'}]),
                   lambda d: case(d, '59_style_unmatched')['derived_state']['budget_after'].update(money=9),
                   lambda d: case(d, '59_style_unmatched').update(packs=STYLE_DESK),
                   lambda d: case(d, '59_style_unmatched')['run']['runs'].append(dict(case(d, '59_style_unmatched')['run']['runs'][0])),
                   lambda d: case(d, '59_style_unmatched')['run'].update(goals=[]),
                   lambda d: case(d, '59_style_unmatched')['outcome'].update(trace_root_sha256='0' * 64),
                   lambda d: one(d, 'old_style_under_new').update(actions=['match-ledger-8801@1']),
                   lambda d: one(d, 'old_style_under_new').update(selected_branch='R-STYLES@1/OR1'),
                   lambda d: s(d)['after_old_style_under_new']['budget'].update(money=10),
                   lambda d: one(d, 'other_old_style_under_new').update(waits=[]),
                   lambda d: one(d, 'other_old_style_under_new')['provenance'][2].update(sha256='0' * 64),
                   lambda d: s(d)['after_other_old_style_under_new']['providers'].update({'ops-head': 1})],
    }
    labels = {'rank': 'S82_the_queue_claims_fail_on_forged_records', 'provenance': 'S85_the_decision_row_claims_fail_on_forged_records',
              'styles': 'S88_the_style_claims_fail_on_forged_records'}
    out = []
    for group in ('rank', 'provenance', 'styles'):
        try:
            honest[group] = json.dumps(mine(data, group))
            was[group] = sha(json.loads(honest[group]))
            claims = groups[group](mine(data, group))
        except Exception as e:   # a record so wrong that this group's claims cannot be read: one failed row under the group's own check id, never an error and never an id outside this module's numbers
            out.append((labels[group], False, 'the ' + group + ' claims cannot be read: ' + type(e).__name__))
            continue
        out += [(name, ok is True, '') for name, ok in claims.items()]
        alive = [i for i, change in enumerate(forged[group]) if survives(group, change)]
        out.append((labels[group], all(ok is True for ok in claims.values()) and not alive, str(alive)))
    try:
        out += [(name, ok is True, '') for name, ok in every_case_claims(data, ROOT, sha, check_chain).items()]
    except Exception as e:
        out.append(('S89_the_pack_files_books_explain_every_gate_line_of_every_case_of_this_version', False, type(e).__name__))
    return out
