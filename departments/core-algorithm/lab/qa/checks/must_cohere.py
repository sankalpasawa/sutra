"""Independent checks for case 50, must-cohere (matrix row R55): S210 and S211. Reads the record and the pack files; imports nothing of the lab.

What case 50 records: a verified FALSE row on the goal (order_complete, from the order desk) while evidence closes one branch of the goal's rule
(original_delivered reads TRUE, from the courier's scan). The kernel names the conflict on the goal and offers no plan.

S210 holds the claims C1 to C3 of the version's passage as thirteen separate tests (tests() below). S211 shows that each test is the one that refuses
its own forgeries: every forgery listed is refused by exactly the test it is listed for, so with that test switched off it would pass."""
import json

CASE = '50_must_cohere'
PACKS = ['00_goal', '01_domain', '100_delivered_but_open']
GOAL, PART, OTHER, SCOPE = 'order_complete', 'original_delivered', 'replacement_delivered', 'orgA/fulfillment'
SCAN = {'predicate': PART, 'truth': 'TRUE', 'verified': True, 'source': 'fixture/courier-scan', 'version': '2'}   # what pack 100 holds, row for row
DESK = {'predicate': GOAL, 'truth': 'FALSE', 'verified': True, 'source': 'fixture/order-desk', 'version': '1'}
OPS = [('GOAL_ACCEPTED', None), ('REFINE', GOAL), ('RETAIN', PART), ('METHOD_ABSENT', OTHER), ('EVIDENCE_CONFLICT', GOAL), ('BLOCK', None), ('TERMINAL', None)]
IDS = ('S210_a_verified_false_goal_under_a_branch_that_evidence_closes_is_a_conflict', 'S211_each_test_of_the_conflict_refuses_a_forgery_of_its_own')


def left_by(packs):
    """The rows a list of packs leaves stored before any run (scope|fact -> row), in the order the kernel stores them. This module's own copy of the kernel's rule:
    a pack names the scope before its rows; a row that is not verified is ignored; a later row replaces an earlier one in its place; a decision stands against an ordinary row."""
    scope, rows = SCOPE, {}
    for p in packs:
        scope = p.get('scope', scope)
        for o in p.get('evidence', []):
            key = o.get('scope', scope) + '|' + o['predicate']
            if o.get('verified') is True and not (rows.get(key, {}).get('final') is True and o.get('final') is not True):
                rows[key] = dict(o, scope=o.get('scope', scope))
    return rows


def tests(case, packs, sha, check_chain):
    """The tests behind C1 to C3, each on its own: {name: holds}. A test that cannot read what it needs does not hold."""
    r, book = case['outcome'], case['derived_state']
    row = lambda op: [e['data'] for e in r['trace'] if e['operation'] == op]
    same = lambda a, b: sha(a) == sha(b)   # compared as JSON: 10 is not 10.0, 0 is not false
    each = {
        # C1: the run ends in a named conflict; nothing is offered, nothing runs, nothing is charged
        'status': lambda: same([r['status'], r['work_state'], r['goal'], r['goal_truth_before']], ['EVIDENCE_CONFLICT', 'blocked', GOAL, 'FALSE']),
        'nothing_ran': lambda: same([r['actions'], r['needs'], r['model_receipts'], r['cost'], r['selected_branch'], r['pareto_options']], [[], [], [], None, None, 0]),
        'reasons': lambda: same(r['stop_reasons'], ['EVIDENCE_CONFLICT', 'METHOD_ABSENT']) and same(row('BLOCK'), [{'reason': 'EVIDENCE_CONFLICT', 'all_reasons': ['EVIDENCE_CONFLICT', 'METHOD_ABSENT']}]),
        # C2: the trace says why, in this order: the goal's rule is taken, one branch closes on the scan, the other finds no method, the conflict is named on the goal
        'order': lambda: [(e['operation'], e['data'].get('predicate')) for e in r['trace']] == OPS,
        'chain': lambda: check_chain(r['trace']) is True and r['trace_root_sha256'] == r['trace'][-1]['sha256'],
        'refined': lambda: same(row('REFINE'), [{'predicate': GOAL, 'rule': 'R-ORDER@1', 'alternatives': 2}]),
        'retained': lambda: same(row('RETAIN'), [{'predicate': PART, 'source': SCAN['source'], 'version': SCAN['version']}]),
        'named': lambda: same(row('METHOD_ABSENT'), [{'predicate': OTHER}]) and same(row('EVIDENCE_CONFLICT'), [{'predicate': GOAL}]),   # the two rows whole: what they name, and nothing beside it
        # C3: the books are what the three pack files leave, row for row and whole; nothing was paid; the journal holds this one run
        'pack': lambda: same(packs[2].get('evidence'), [SCAN, DESK]) and [p['id'] for p in packs] == PACKS,
        'rows': lambda: same(book['facts'], left_by(packs)) and list(book['facts']) == list(left_by(packs)),
        'budget': lambda: same(book['budget_after'], {'compute': 10, 'money': 10, 'attention': 3}) and same(book['candidate_count'], 0),
        'journal': lambda: same(book['historical_events'], [{'goal': GOAL, 'scope': SCOPE, 'status': 'EVIDENCE_CONFLICT', 'trace_root_sha256': r['trace_root_sha256']}]),
        'place': lambda: same([case['packs'], case['scope'], r['scope'], book['rule_ids']], [PACKS, SCOPE, SCOPE, ['R-ORDER@1']]),
    }
    out = {}
    for name, test in each.items():
        try:
            out[name] = test() is True
        except Exception:
            out[name] = False
    return out


def remade(case, sha, change):
    """What a forger can do without any secret: change the run, hash its chain again and carry the new root to the journal."""
    r, prev = case['outcome'], 'GENESIS'
    change(r)
    for n, e in enumerate(r['trace']):
        e.update(seq=n + 1, prev_sha256=prev)
        e['sha256'] = prev = sha({k: v for k, v in e.items() if k != 'sha256'})
    r['trace_root_sha256'] = case['derived_state']['historical_events'][-1]['trace_root_sha256'] = prev


def line(r, op):
    return [e for e in r['trace'] if e['operation'] == op][0]


FACTS = lambda c: c['derived_state']['facts']
HEAD, SCANNED = SCOPE + '|' + GOAL, SCOPE + '|' + PART
# (the test that must refuse it, the forgery). A forgery gets a copy of the case, a copy of the three packs, and sha.
FORGERIES = [
    ('status', lambda c, p, sha: c['outcome'].update(status='PLAN_READY')),
    ('status', lambda c, p, sha: c['outcome'].update(work_state='ready')),
    ('status', lambda c, p, sha: c['outcome'].update(goal_truth_before='UNKNOWN')),
    ('nothing_ran', lambda c, p, sha: c['outcome'].update(actions=['ship-original@1'])),
    ('nothing_ran', lambda c, p, sha: c['outcome'].update(cost={'compute': 0, 'money': 0, 'attention': 0})),
    ('nothing_ran', lambda c, p, sha: c['outcome'].update(pareto_options=False)),
    ('reasons', lambda c, p, sha: c['outcome'].update(stop_reasons=['METHOD_ABSENT'])),
    ('reasons', lambda c, p, sha: remade(c, sha, lambda r: line(r, 'BLOCK')['data'].update(all_reasons=['EVIDENCE_CONFLICT']))),
    ('order', lambda c, p, sha: remade(c, sha, lambda r: r['trace'].insert(2, r['trace'].pop(3)))),      # the branch without a method told before the part that evidence closes
    ('named', lambda c, p, sha: remade(c, sha, lambda r: line(r, 'METHOD_ABSENT')['data'].update(predicate=OTHER, also=PART))),   # the row of the branch without a method, with a second fact in it
    ('order', lambda c, p, sha: remade(c, sha, lambda r: r['trace'].insert(1, r['trace'].pop(4)))),      # the conflict named before the rule is taken
    ('chain', lambda c, p, sha: c['outcome']['trace'][0]['data'].update(scope='orgB/fulfillment')),       # a row changed and not hashed again
    ('refined', lambda c, p, sha: remade(c, sha, lambda r: line(r, 'REFINE')['data'].update(rule='R-ORDER@2'))),
    ('retained', lambda c, p, sha: remade(c, sha, lambda r: line(r, 'RETAIN')['data'].update(source='fixture/order-desk'))),
    ('retained', lambda c, p, sha: remade(c, sha, lambda r: line(r, 'RETAIN')['data'].update(version='1'))),
    ('named', lambda c, p, sha: remade(c, sha, lambda r: line(r, 'EVIDENCE_CONFLICT')['data'].update(resolved_by='fixture/order-desk'))),   # a field added to the row that names the conflict
    ('named', lambda c, p, sha: remade(c, sha, lambda r: line(r, 'METHOD_ABSENT')['data'].update(method='ship-replacement@1'))),         # a method said to exist for the other branch
    ('pack', lambda c, p, sha: (p[2]['evidence'][1].update(source='fixture/elsewhere'), FACTS(c)[HEAD].update(source='fixture/elsewhere'))),   # the pack and the stored row changed together
    ('rows', lambda c, p, sha: FACTS(c)[HEAD].update(verified=False, final=True, version='7')),          # the head's row said to be unverified, a decision, another version
    ('rows', lambda c, p, sha: FACTS(c)[HEAD].update(truth='TRUE')),
    ('rows', lambda c, p, sha: FACTS(c)[SCANNED].update(version='1')),
    ('rows', lambda c, p, sha: FACTS(c)[SCANNED].update(source='fixture/order-desk')),
    ('rows', lambda c, p, sha: FACTS(c)[SCOPE + '|' + OTHER].update(truth='TRUE')),
    ('rows', lambda c, p, sha: FACTS(c).pop(SCOPE + '|customer_notified')),
    ('rows', lambda c, p, sha: FACTS(c).update({SCOPE + '|gift_wrapped': dict(DESK, predicate='gift_wrapped', scope=SCOPE)})),
    ('rows', lambda c, p, sha: FACTS(c).update({HEAD: FACTS(c).pop(HEAD), SCANNED: FACTS(c).pop(SCANNED)})),   # the same rows in another order
    ('budget', lambda c, p, sha: c['derived_state']['budget_after'].update(compute=9)),
    ('budget', lambda c, p, sha: c['derived_state']['budget_after'].update(compute=10.0)),
    ('budget', lambda c, p, sha: c['derived_state'].update(candidate_count=1)),
    ('journal', lambda c, p, sha: c['derived_state']['historical_events'][0].update(status='SUPPORTED_BY_EVIDENCE')),
    ('journal', lambda c, p, sha: c['derived_state']['historical_events'].append(dict(c['derived_state']['historical_events'][0]))),
    ('place', lambda c, p, sha: c.update(scope='orgB/fulfillment')),
    ('place', lambda c, p, sha: c.update(packs=PACKS[:2])),
    ('place', lambda c, p, sha: c['derived_state'].update(rule_ids=[])),
]


def checks(data, ROOT, sha, check_chain):
    try:
        case = [c for c in data['cases'] if c['id'] == CASE][0]
        packs = [json.loads((ROOT / 'scenarios' / (n + '.json')).read_text()) for n in PACKS]
        got = tests(case, packs, sha, check_chain)
    except Exception as e:
        return [(cid, False, 'case 50 or its pack files cannot be read: ' + type(e).__name__) for cid in IDS]

    def refused_by(change):   # the tests that refuse one forgery; None when the forgery cannot be made
        c, p = json.loads(json.dumps(case)), json.loads(json.dumps(packs))
        try:
            change(c, p, sha)
        except Exception:
            return None
        return sorted(name for name, ok in tests(c, p, sha, check_chain).items() if not ok)
    seen = [refused_by(change) for _, change in FORGERIES]
    wrong = {i: by for i, ((target, _), by) in enumerate(zip(FORGERIES, seen)) if by != [target]}   # accepted, refused by another test too, or not made
    bare = sorted(set(got) - {target for target, _ in FORGERIES})                                 # a test without a forgery of its own
    return [(IDS[0], all(got.values()), ' '.join(sorted(name for name, ok in got.items() if not ok))),
            (IDS[1], all(got.values()) and not wrong and not bare, str({'not refused by its own test alone': wrong, 'tests without a forgery': bare}) if wrong or bare else '')]
