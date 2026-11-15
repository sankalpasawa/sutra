"""0.18.0-handoff: work handed to a hand and checked by a separate checker, with tries (rulings R16 and R18, read under R35).
The standing example is a lender's letters desk: a collections letter for loan L-17 is drafted by a model, outside the kernel, and
counts as drafted only when a checker that reads the loan book says so.

  CaseTests      cases 84 to 87 and the packs
  KindTests      the action kind `handoff` (kinds/handoff.py): one of the two parts this version adds; the other is the check module (CheckTests)
  AttemptTests   T1 to T8: the same need stated with the parts the lab had before, and what the algorithm makes of each
                 (T1 to T6 are also on record in the sequence handoff_existing; T7 and T8, the ordinary step, are unit tests only: their packs are built in the test)
  ClaimTests     C1 to C9: what the kind holds
  CheckerTests   the two stand-ins of the example (the hand and the checker), which read and write files in a folder
  WalkTests      seeded walks of checks and looks: what must hold in every one of them
  SequenceTests  the two recorded sequences, compared with the built record (so these run after tools/run_all.py)
  CheckTests     the independent checks S140 and S141 (qa/checks/handoff.py), run on the built record and on forged ones
  ClauseTests    the functions of the check module called in this process, on forged records: one forged record for a clause of the module that the tests above leave unheld
  LimitTests     L1 to L22: what this version does not hold, pinned as it is (L14 to L21 were found by the first review round, L22 while that round was settled; each is
                 pinned as the version behaves today)"""
from pathlib import Path
import unittest, sys, json, random, tempfile, hashlib, importlib.util
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from kernel.core import State, Kernel
from tools.run_all import CASES, KINDS, pack, scenes, undeclared   # importing the lab's tools loads the kind files: handoff is registered from kinds/handoff.py
from extensions.asks import answer, open_asks
from extensions import journal as J

open_handoffs = sys.modules['kinds.handoff'].open_handoffs
SCENE = ROOT / 'tools' / 'scenes' / 'handoff_letter.py'   # the stand-ins of the example live in the scene file that records them
_ns = {'__name__': 'tools.scenes.handoff_letter'}
exec(compile(SCENE.read_text(encoding='utf-8'), str(SCENE), 'exec'), _ns)
keep_book, draft, check = _ns['keep_book'], _ns['draft'], _ns['check']

HAND, CHECKER, OFFICER = 'model:letter-drafter', 'checker:loan-book', 'person:collections-officer'
MODEL_M, OFFICER_M, QUEUE = 'hand-letter-to-model@1', 'hand-letter-to-officer@1', 'queue-collections-letter@1'
ASK_DOER, ASK_CHECKER = 'ask-drafter-for-letter@1', 'ask-checker-about-letter@1'
SCOPE = 'lendco/collections-letters'
KEY = SCOPE + '|letter_drafted'
DONE = 'LOCAL_MODEL_EFFECTS_RECORDED'
DESK = ['210_letters_desk', '212_book_read']
MODEL = ['210_letters_desk', '211_hand_to_model', '212_book_read']
SPENT = MODEL + ['213_model_spent']
NEXT = SPENT + ['214_hand_to_officer']
BOTH = MODEL + ['214_hand_to_officer']
WORK = 'Draft the collections letter for loan L-17: name the borrower, the loan and the amount overdue.'
WRONG = 'the letter says an overdue amount of 2400; the loan book says 240'
ON_BOOK = [{'predicate': 'loan_on_book', 'version': 'book-fixture'}]
BOOK_2 = {'predicate': 'loan_on_book', 'truth': 'TRUE', 'verified': True, 'source': CHECKER, 'version': 'book-after-a-part-payment'}
WAITS = [('WAITING', [], [QUEUE], [MODEL_M], [])]             # a look that waits on the model's try and hands nothing over
HANDS = [('WAITING', [MODEL_M], [QUEUE], [MODEL_M], [])]      # a look that hands the letter to the model
NO_SLOT = [('PROVIDER_REQUIRED', [], None, None, ['PROVIDER_REQUIRED'])]


def world(names, *more): return State.from_packs([pack(n) for n in names] + list(more))
def extra(id, **fields): return {'schema': 'sutra-extension/2', 'id': id, **fields}
def st(look): return [(r['status'], r['actions'], r.get('pending'), r.get('waits'), r['stop_reasons']) for r in look['runs']]
def looks(s, execute=True): return st(Kernel(s).run_standing(execute=execute))
def held(s): return json.dumps({'budget': s.budget, 'providers': s.providers, 'evidence': s.evidence, 'grants': sorted(s.grants), 'active_work': s.active_work}, sort_keys=True)   # the books, without the journal of looks
def said(s, fact='letter_drafted'): x = s.fact(fact); return (x['truth'], x.get('source'), bool(x.get('final')))   # what a fact reads, from whose row, and whether that row is a decision
def says(truth, version, checks=None, source=CHECKER, **more): return {'predicate': 'letter_drafted', 'truth': truth, 'verified': True, 'source': source, 'version': version, 'checks': checks, **more}
def closed(look): return [e['data'] for r in look['runs'] for e in r['trace'] if e['operation'] == 'HANDOFF_CLOSED']
def issued(look): return look['runs'][0]['model_receipts'][-1]   # the receipt of the hand-over (or of the question) a look issued
def admissions(r): return [(e['data']['methods'], e['data']['accepted'], e['data']['blockers']) for e in r['trace'] if e['operation'] == 'ADMISSION']
def matched(r): return [(e['operation'], e['data']['method']) for e in r['trace'] if e['operation'] in ('METHOD_MATCH', 'METHOD_PENDING')]
def told(x): return {k: v for k, v in x['handoff'].items() if k != 'handed_in'}   # a hand-over's receipt without the digest that binds it to its State
def fails(k, receipt, version, why=WRONG): return k.on_event(says('FALSE', version, receipt['sha256'], why=why, depends_on=ON_BOOK), execute=True)
def passes(k, receipt, version='letter-right'): return k.on_event(says('TRUE', version, receipt['sha256'], depends_on=ON_BOOK), execute=True)
def handed(names=MODEL, *more):
    s = world(names, *more); k = Kernel(s); return s, k, issued(k.run_standing(execute=True))
def method(id, effect, requires=(), provider='local-provider', cost=None, action='simulate_fact', **more):
    return {'id': id, 'effect': effect, 'requires': list(requires), 'provider': provider, 'grant': 'action:' + id, 'cost': cost or {'compute': 1, 'money': 0, 'attention': 0}, 'action': action, 'approved': True, **more}


class CaseTests(unittest.TestCase):
    def test_the_four_cases_stand_in_the_table_with_their_packs(self):
        table = {c[0]: (c[3], c[4], c[5]) for c in CASES}
        self.assertEqual([table[i] for i in ('84_handed_over', '85_no_step', '86_no_slot_left', '87_next_hand')],
                         [(MODEL, True, 'Hand-off'), (DESK, True, 'Hand-off'), (SPENT, True, 'Hand-off'), (NEXT, True, 'Hand-off')])

    def test_the_packs_bring_one_new_kind_and_the_packs_of_the_attempt_bring_none(self):
        names = ['210_letters_desk', '211_hand_to_model', '212_book_read', '213_model_spent', '214_hand_to_officer', '215_ask_the_drafter', '216_ask_the_checker', '217_three_asks']
        self.assertEqual({n: sorted({m['action'] for m in pack(n).get('methods', [])}) for n in names},
                         {'210_letters_desk': ['simulate_fact'], '211_hand_to_model': ['handoff'], '212_book_read': [], '213_model_spent': [], '214_hand_to_officer': ['handoff'],
                          '215_ask_the_drafter': ['ask'], '216_ask_the_checker': ['ask'], '217_three_asks': ['ask']})   # packs 215 to 217 and pack 210 are parts the lab had before
        self.assertEqual(sorted({key for n in names for key in pack(n)} - {'schema', 'id', 'scope', 'goals', 'budget', 'preference', 'evidence', 'methods', 'providers', 'grants', 'rules'}), [])
        self.assertEqual([(m['id'], m['handoff_to'], m['verified_by'], m['provider'], m['instruction']) for n in names for m in pack(n).get('methods', []) if m['action'] == 'handoff'],
                         [(MODEL_M, HAND, CHECKER, 'letter-model', WORK), (OFFICER_M, OFFICER, CHECKER, 'collections-officer', WORK)])

    def test_84_the_letter_is_handed_over_and_the_run_waits(self):
        s = world(MODEL); r = Kernel(s).run_standing(execute=True)['runs'][0]; x = r['model_receipts'][0]
        self.assertEqual((r['status'], r['work_state'], r['actions'], r['pending'], r['waits'], r['goal_truth_after'], r['cost']),
                         ('WAITING', 'waiting', [MODEL_M], [QUEUE], [MODEL_M], 'UNKNOWN', {'compute': 2, 'money': 0, 'attention': 0}))
        self.assertEqual(told(x), {'predicate': 'letter_drafted', 'to': HAND, 'instruction': WORK, 'verified_by': CHECKER, 'try': 1, 'before': []})   # who, what, whose rows check it, which try
        self.assertEqual((x['method'], x['action'], x['status'], x['parked'], sorted(x)), (MODEL_M, 'handoff', 'LOCAL_ONLY', True, ['action', 'handoff', 'method', 'parked', 'scope', 'sha256', 'status']))
        self.assertEqual((s.budget, s.providers), ({'compute': 8, 'money': 5, 'attention': 3}, {'local-provider': 4, 'letter-model': 2}))   # one try is paid and one slot is taken
        self.assertEqual((said(s), said(s, 'letter_queued'), sorted(s.evidence)), (('UNKNOWN', None, False), ('UNKNOWN', None, False), [SCOPE + '|loan_on_book']))   # the hand-over wrote no row
        self.assertEqual(open_handoffs(s), {KEY: {'method': MODEL_M, 'receipt': x['sha256'], 'issued': x, 'checker': CHECKER, 'failed': None}})
        kept = json.dumps(s.active_work, sort_keys=True); x['handoff']['try'] = 99   # the books keep their own copy of the receipt: what the caller does to the one it was given changes nothing
        self.assertEqual((json.dumps(s.active_work, sort_keys=True), s.active_work['handoff'][KEY]['issued']['handoff']['try']), (kept, 1))

    def test_85_with_no_step_the_look_is_blocked_and_nobody_is_handed_anything(self):
        s = world(DESK); r = Kernel(s).run_standing(execute=True)['runs'][0]
        self.assertEqual((r['status'], r['work_state'], r['actions'], r['model_receipts'], r['stop_reasons']), ('QUERY_EVIDENCE', 'blocked', [], [], ['QUERY_EVIDENCE']))
        self.assertEqual((s.budget, s.providers, s.active_work), ({'compute': 10, 'money': 5, 'attention': 3}, {'local-provider': 4}, {}))

    def test_86_a_hand_with_no_slot_left_is_handed_nothing(self):
        s = world(SPENT); r = Kernel(s).run_standing(execute=True)['runs'][0]
        self.assertEqual((r['status'], r['work_state'], r['model_receipts'], r['stop_reasons']), ('PROVIDER_REQUIRED', 'blocked', [], ['PROVIDER_REQUIRED']))
        self.assertEqual(admissions(r), [([MODEL_M, QUEUE], False, ['PROVIDER_REQUIRED'])])   # the kernel's own gate, not the kind, turns the hand-over down
        self.assertEqual((s.budget, s.providers['letter-model'], open_handoffs(s)), ({'compute': 10, 'money': 5, 'attention': 3}, 0, {}))
        self.assertEqual(looks(world(SPENT), execute=False), NO_SLOT)   # the dry look says the same

    def test_87_the_next_hand_is_taken_by_the_kernels_ordinary_choice(self):
        s = world(NEXT); r = Kernel(s).run_standing(execute=True)['runs'][0]; x = r['model_receipts'][0]
        self.assertEqual((r['status'], r['actions'], r['pending'], r['waits']), ('WAITING', [OFFICER_M], [QUEUE], [OFFICER_M]))
        self.assertEqual(admissions(r)[:2], [([MODEL_M, QUEUE], False, ['PROVIDER_REQUIRED']), ([OFFICER_M, QUEUE], True, [])])
        self.assertEqual(told(x), {'predicate': 'letter_drafted', 'to': OFFICER, 'instruction': WORK, 'verified_by': CHECKER, 'try': 1, 'before': []})
        self.assertEqual((s.budget, s.providers), ({'compute': 10, 'money': 5, 'attention': 2}, {'local-provider': 4, 'letter-model': 0, 'collections-officer': 0}))
        r = Kernel(world(BOTH)).run_standing()['runs'][0]   # while the model has a slot both ways are open, and the desk, which saves attention first, takes the model
        self.assertEqual((r['status'], r['actions'], r['pareto_options'], admissions(r)), ('PLAN_READY', [MODEL_M, QUEUE], 2, [([MODEL_M, QUEUE], True, []), ([OFFICER_M, QUEUE], True, [])]))


class KindTests(unittest.TestCase):
    def test_the_kind_is_declared_in_its_own_file_and_every_state_knows_it(self):
        kind = State().actions['handoff']
        self.assertEqual(('handoff' in KINDS, undeclared(), sorted(kind), kind['run'].__module__, kind['run'].__name__, Path(sys.modules['kinds.handoff'].__file__)),
                         (True, [], ['check', 'plan', 'run', 'settle'], 'kinds.handoff', 'handoff', ROOT / 'kinds' / 'handoff.py'))

    def test_a_hand_off_that_does_not_say_who_what_and_whose_rows_check_it_is_refused_with_its_pack(self):
        good = dict(pack('211_hand_to_model')['methods'][0], id='hand-letter@t', grant='action:hand-letter@t')
        base = [pack('210_letters_desk'), pack('212_book_read')]
        ok = State.from_packs(base + [extra('t-good', methods=[good], providers={'letter-model': 1}, grants=['action:hand-letter@t'])])
        self.assertIn('hand-letter@t', ok.methods)
        bad = [{'handoff_to': None}, {'handoff_to': ''}, {'handoff_to': '   '}, {'handoff_to': 7}, {'instruction': None}, {'instruction': ' '}, {'verified_by': None}, {'verified_by': ''},
               {'verified_by': ['checker:loan-book']}, {'verified_by': HAND}, {'cost': {'compute': 0, 'money': 0, 'attention': 0}}, {'cost': {}}]
        for change in bad:
            m = {k: v for k, v in dict(good, **change).items() if v is not None}
            s = State.from_packs(base); before = held(s)
            with self.assertRaisesRegex(ValueError, 'A hand-off names who does the work, what to do and whose rows check it \\(not the hand\\), and costs something', msg=str(change)):
                s.apply(extra('t-bad', methods=[m], providers={'letter-model': 1}, grants=['action:hand-letter@t']))
            self.assertEqual((held(s), sorted(s.methods)), (before, [QUEUE]), str(change))   # a pack applies whole or not at all
        costly = dict(good, cost={'compute': 0, 'money': 0, 'attention': 1})   # one unit of anything is enough
        self.assertIn('hand-letter@t', State.from_packs(base + [extra('t-costly', methods=[costly], providers={'letter-model': 1}, grants=['action:hand-letter@t'])]).methods)

    def test_the_handler_writes_no_row_and_no_candidate_and_the_kernel_pays_the_try(self):
        s = world(MODEL); before = (dict(s.evidence), dict(s.candidates), sorted(s.grants), list(s.goals), dict(s.methods))
        r = Kernel(s).run_standing(execute=True)['runs'][0]
        self.assertEqual((dict(s.evidence), dict(s.candidates), sorted(s.grants), list(s.goals), dict(s.methods)), before)
        self.assertEqual((r['candidates'], [e['operation'] for e in r['trace']][-3:]), ([], ['ADMISSION', 'LOCAL_EFFECT', 'TERMINAL']))   # the receipt is the step's last line: a hand-over that is still out writes no line of its own
        self.assertEqual(list(s.active_work), ['handoff'])   # the one thing the kind keeps: its books

    def test_the_books_of_another_scope_are_not_read_and_not_touched(self):
        other = 'lendco/collections-notices'; self.assertEqual(len(other), len(SCOPE))   # as long as the first desk's name: a key cut by length alone would name the other desk's fact
        s, k, x = handed()
        s.apply(extra('t-other-desk', scope=other, goals=['letter_queued'], evidence=[{'predicate': 'loan_on_book', 'truth': 'TRUE', 'verified': True, 'source': CHECKER, 'version': 'their-book'}]))
        self.assertEqual((open_handoffs(s), looks(s, execute=False)), ({}, [('PLAN_READY', [MODEL_M, QUEUE], None, None, [])]))   # at the other desk nothing is out, and its look does not wait on the first desk's hand-over
        s.apply(extra('t-their-letter', evidence=[{'predicate': 'letter_drafted', 'truth': 'TRUE', 'verified': True, 'source': CHECKER, 'version': 'theirs'}]))
        out = k.run_standing(execute=True)   # there the letter reads TRUE: the run queues it and closes nothing of the first desk
        self.assertEqual((st(out), closed(out), list(s.active_work['handoff'])), ([(DONE, [QUEUE], None, None, [])], [], [KEY]))
        s.apply(extra('t-back', scope=SCOPE))
        self.assertEqual((looks(s), list(open_handoffs(s)), open_handoffs(s)[KEY]['receipt']), (WAITS, [KEY], x['sha256']))   # back at the first desk its hand-over is still out

    def test_open_handoffs_lists_what_is_out_and_nothing_that_reads_true_or_is_decided(self):
        s, k, x = handed(); k.on_event(says('TRUE', 'letter-right', x['sha256'], depends_on=ON_BOOK), execute=False)   # the checker's TRUE came in with a dry look: no executed run has closed the books yet
        self.assertEqual((open_handoffs(s), list(s.active_work['handoff'])), ({}, [KEY]))
        s, k, x = handed(); k.on_event(dict(says('FALSE', 'owner-says-no', source='owner'), final=True), execute=False)
        self.assertEqual((open_handoffs(s), list(s.active_work['handoff'])), ({}, [KEY]))
        s, k, x = handed(); k.on_event(says('FALSE', 'letter-a', x['sha256'], why=WRONG, depends_on=ON_BOOK), execute=False)   # a failed check that no executed look has acted on yet
        out_of = open_handoffs(s)[KEY]
        self.assertEqual((out_of['receipt'], out_of['failed']['truth'], out_of['failed']['why'], out_of['failed']['checks']), (x['sha256'], 'FALSE', WRONG, x['sha256']))
        out_of['issued']['handoff']['try'] = 99; out_of['failed']['why'] = 'changed'   # what is handed out is a copy
        self.assertEqual((open_handoffs(s)[KEY]['issued']['handoff']['try'], open_handoffs(s)[KEY]['failed']['why']), (1, WRONG))

    def test_a_try_whose_check_cannot_be_read_is_told_as_unchecked(self):
        s, k, x = handed()   # the handler called on work that is out with no check of it on the books: through the kernel's doors the plan waits instead (C1), so it is called here by hand
        again = sys.modules['kinds.handoff'].handoff(s, s.methods[MODEL_M], MODEL_M, [])
        self.assertEqual((again['handoff']['try'], again['handoff']['before'], again['parked']), (2, [{'try': 1, 'to': HAND, 'receipt': x['sha256'], 'checked': None}], True))


class AttemptTests(unittest.TestCase):
    """Ruling R35 of the program: the need is first stated with the parts the lab had. Each test is one way to state it, with what fails."""
    def asked(self, names):
        s = world(names); k = Kernel(s); return s, k, issued(k.run_standing(execute=True))

    def test_t1_an_ask_put_to_the_doer_is_closed_by_the_doers_own_word(self):
        s, k, x = self.asked(DESK + ['215_ask_the_drafter']); self.assertEqual((x['ask']['to'], x['method'], list(s.active_work)), (HAND, ASK_DOER, ['ask']))   # an ask's receipt is no hand-over: the kind keeps no books for it
        out = answer(k, x, 'TRUE', HAND, execute=True)   # the model says done; nobody checked anything
        self.assertEqual((st(out), said(s), said(s, 'letter_queued')), ([(DONE, [QUEUE], None, None, [])], ('TRUE', 'STAMP:' + HAND, True), ('TRUE', 'LOCAL_MODEL:' + QUEUE, False)))
        late = k.on_event(says('FALSE', 'check-of-draft-1', why=WRONG), execute=True)   # the checker's FALSE comes after, and is turned away
        self.assertEqual((late['status'], late['runs'], said(s), s.event_journal[-1]), ('DECISION_STANDS', [], ('TRUE', 'STAMP:' + HAND, True), {'status': 'DECISION_STANDS', 'scope': SCOPE, 'predicate': 'letter_drafted'}))

    def test_t2_an_ask_put_to_the_checker_ends_on_the_first_no(self):
        s, k, x = self.asked(DESK + ['216_ask_the_checker']); self.assertEqual((x['ask']['to'], x['method']), (CHECKER, ASK_CHECKER))
        self.assertNotIn(HAND, json.dumps(x))   # the receipt names the checker as the party asked; the hand stands nowhere in it
        with self.assertRaisesRegex(ValueError, 'The answer does not come from the party that was asked'): answer(k, x, 'TRUE', HAND, execute=True)
        out = answer(k, x, 'FALSE', CHECKER, execute=True)   # the first draft is wrong: the checker's no is a decision
        self.assertEqual((st(out), said(s), open_asks(s)), ([('REFUSED', [], None, None, ['REFUSED'])], ('FALSE', 'STAMP:' + CHECKER, True), {}))
        with self.assertRaisesRegex(ValueError, 'No open ask matches this receipt'): answer(k, x, 'TRUE', CHECKER, execute=True)   # a second draft: no stamp confirms it
        late = k.on_event(says('TRUE', 'check-of-draft-2'), execute=True)   # and no row does
        self.assertEqual((late['status'], said(s), looks(s)), ('DECISION_STANDS', ('FALSE', 'STAMP:' + CHECKER, True), [('REFUSED', [], None, None, ['REFUSED'])]))
        self.assertEqual((s.budget['attention'], s.providers['checker-channel']), (2, 2))   # one try was made, and there is no second

    def test_t3_a_stamped_yes_rests_on_nothing_and_outlives_the_book_it_was_given_on(self):
        s, k, x = self.asked(DESK + ['216_ask_the_checker']); answer(k, x, 'TRUE', CHECKER, execute=True)
        self.assertEqual(sorted(s.evidence[KEY]), ['answers', 'final', 'predicate', 'scope', 'source', 'truth', 'verified', 'version'])   # no depends_on: a decision rests on nothing else
        with self.assertRaisesRegex(ValueError, 'A decision is a TRUE or FALSE row that rests on nothing else'): s.observe(dict(says('TRUE', 'v', final=True, depends_on=ON_BOOK)))
        out = k.on_event(BOOK_2, execute=True)   # the loan book changes: the letter still counts as drafted and stays queued
        self.assertEqual((st(out), said(s), said(s, 'letter_queued')), ([('SUPPORTED_BY_EVIDENCE', [], None, None, [])], ('TRUE', 'STAMP:' + CHECKER, True), ('TRUE', 'LOCAL_MODEL:' + QUEUE, False)))
        late = k.on_event(says('FALSE', 'check-against-the-new-book', why='the letter says an overdue amount of 240; the loan book says 180'), execute=True)
        self.assertEqual((late['status'], said(s)), ('DECISION_STANDS', ('TRUE', 'STAMP:' + CHECKER, True)))

    def test_t4_rows_under_an_ask_never_hand_the_work_over_again_and_count_nothing(self):
        s, k, x = self.asked(DESK + ['216_ask_the_checker']); before = held(s)
        for n in range(1, 8):   # seven failed checks: the same question is out, nothing is issued, nothing is paid, nothing is counted
            out = k.on_event(says('FALSE', f'check-of-draft-{n}', why=WRONG), execute=True)
            self.assertEqual((st(out), out['runs'][0]['model_receipts'], [v['receipt'] for v in open_asks(s).values()]), ([('WAITING', [], [QUEUE], [ASK_CHECKER], [])], [], [x['sha256']]))
        self.assertEqual(json.loads(held(s))['budget'], json.loads(before)['budget']); self.assertEqual(json.loads(held(s))['providers'], json.loads(before)['providers'])
        out = k.on_event(says('TRUE', 'check-of-draft-8', depends_on=ON_BOOK), execute=True)   # a passing row lets the plan go on; the question is still out
        self.assertEqual((st(out), said(s), list(open_asks(s))), ([(DONE, [QUEUE], None, None, [])], ('TRUE', CHECKER, False), [KEY]))

    def test_t5_with_no_step_nobody_is_handed_anything_and_the_look_is_blocked(self):
        s = world(DESK); k = Kernel(s)
        self.assertEqual(looks(s), [('QUERY_EVIDENCE', [], None, None, ['QUERY_EVIDENCE'])])
        for n in (1, 2, 3):
            self.assertEqual(st(k.on_event(says('FALSE', f'check-of-draft-{n}', why=WRONG), execute=True)), [('METHOD_ABSENT', [], None, None, ['METHOD_ABSENT'])])
        self.assertEqual((s.budget, s.providers, s.active_work), ({'compute': 10, 'money': 5, 'attention': 3}, {'local-provider': 4}, {}))   # nothing was handed over, gated, paid or counted
        self.assertEqual(st(k.on_event(says('TRUE', 'check-of-draft-4', depends_on=ON_BOOK), execute=True)), [(DONE, [QUEUE], None, None, [])])   # the evidence alone still decides

    def test_t6_three_asks_under_a_rule_tell_the_next_try_nothing_and_a_yes_cannot_complete(self):
        names = DESK + ['217_three_asks']; s, k, x1 = self.asked(names)
        no_1 = answer(k, x1, 'FALSE', CHECKER, execute=True); x2 = issued(no_1)   # a stamped no closes try 1 for good, and try 2 is asked
        self.assertEqual((st(no_1), x2['method'], x2['ask']['question']), ([('WAITING', ['ask-checker-about-draft-2@1'], [QUEUE], ['ask-checker-about-draft-2@1'], [])], 'ask-checker-about-draft-2@1',
                                                                             'Try 2 of 3: does the letter drafted for loan L-17 match the loan book?'))
        self.assertEqual(sorted(x2['ask']), ['asked_in', 'predicate', 'question', 'to'])   # the words of the pack and nothing of the check that failed
        no_2 = answer(k, x2, 'FALSE', CHECKER, execute=True); no_3 = answer(k, issued(no_2), 'FALSE', CHECKER, execute=True)
        self.assertEqual((st(no_3), s.budget['attention'], s.providers['checker-channel']), ([('REFUSED', [], None, None, ['REFUSED'])], 0, 0))   # three tries, then the goal is refused
        s, k, x1 = self.asked(names); x2 = issued(answer(k, x1, 'FALSE', CHECKER, execute=True))
        yes = answer(k, x2, 'TRUE', CHECKER, execute=True)['runs'][0]   # a yes to try 2: the letter holds only through the rule, and the gate reads stored rows
        self.assertEqual((yes['status'], yes['stopped'], said(s, 'draft_2_passes'), said(s), said(s, 'letter_queued')),
                         ('STEP_STOPPED', {'method': QUEUE, 'reason': 'Prerequisite not true before effect: letter_drafted'}, ('TRUE', 'STAMP:' + CHECKER, True), ('UNKNOWN', None, False), ('UNKNOWN', None, False)))
        s, k, x1 = self.asked(names)   # the same three asks with rows in place of stamps: the look waits on the first question for good
        for n in (1, 2, 3):
            out = k.on_event({'predicate': 'draft_1_passes', 'truth': 'FALSE', 'verified': True, 'source': CHECKER, 'version': f'check-{n}'}, execute=True)
            self.assertEqual((st(out), list(open_asks(s))), ([('WAITING', [], [QUEUE], ['ask-checker-about-draft-1@1'], [])], [SCOPE + '|draft_1_passes']))

    # T7 and T8: the lab's ORDINARY step (the built-in kind simulate_fact), which T1 to T6 did not try. The first review round of this version tried it; it is recorded here
    # as unit tests, with packs built in the test (no scenario file and no recorded sequence holds it). No method below is of the new kind, and the kind keeps no books for them.
    def went(self, look): return [(r['goal'], r['status'], r['actions']) for r in look['runs']]

    def test_t7_an_ordinary_step_gives_a_second_try_on_a_row_and_a_yes_that_rests_on_what_was_read_but_it_blocks_and_its_receipt_names_no_try(self):
        give = extra('t-give', goals=['letter_queued', 'letter_with_hand'], grants=['action:give-letter-to-model@t'], providers={'letter-model': 3},   # the hand-over as a fact of its own, made by a step
                     methods=[method('give-letter-to-model@t', 'letter_with_hand', ['loan_on_book'], provider='letter-model', cost={'compute': 2, 'money': 0, 'attention': 0})])
        s = world(DESK, give); k = Kernel(s); self.assertEqual(sorted({m['action'] for m in s.methods.values()}), ['simulate_fact'])
        failed = lambda version, why: k.on_event({'predicate': 'letter_with_hand', 'truth': 'FALSE', 'verified': True, 'source': CHECKER, 'version': version, 'why': why, 'depends_on': ON_BOOK}, execute=True)
        first = k.run_standing(execute=True); x1 = first['runs'][1]['model_receipts'][0]
        self.assertEqual((self.went(first), s.budget['compute'], s.providers['letter-model']),
                         ([('letter_queued', 'QUERY_EVIDENCE', []), ('letter_with_hand', DONE, ['give-letter-to-model@t'])], 8, 2))   # a try is paid and takes a slot; the goal that needs the letter is BLOCKED while the hand works, where a hand-off waits (C1)
        self.assertEqual(sorted(x1), ['action', 'method', 'model_effect', 'scope', 'sha256', 'status'])   # the receipt of an ordinary step: no number of a try, nothing of a check
        again = failed('letter-a', WRONG); x2 = again['runs'][0]['model_receipts'][0]   # the checker's FALSE on the hand-over: the same look hands over again, and nobody stamped anything
        self.assertEqual((self.went(again), s.budget['compute'], s.providers['letter-model'], x2 == x1), ([('letter_with_hand', DONE, ['give-letter-to-model@t'])], 6, 1, True))   # a second try on a row; its receipt is the first one's, letter for letter
        late = failed('letter-a-late', 'a late copy of the first draft')   # any FALSE on that fact is a failed check here: a late copy spends the last try (the kind: C5)
        self.assertEqual((self.went(late), s.budget['compute'], s.providers['letter-model']), ([('letter_with_hand', DONE, ['give-letter-to-model@t'])], 4, 0))
        self.assertEqual(self.went(failed('letter-c', WRONG)), [('letter_with_hand', 'PROVIDER_REQUIRED', [])])   # the provider's capacity bounds the tries here too, at the kernel's own gate
        out = k.on_event(says('TRUE', 'letter-right', depends_on=ON_BOOK), execute=True)   # the checker's TRUE on the letter: queued, and what is made rests on that row at its version
        self.assertEqual((self.went(out), said(s, 'letter_queued'), s.evidence[SCOPE + '|letter_queued']['depends_on']),
                         ([('letter_queued', DONE, [QUEUE])], ('TRUE', 'LOCAL_MODEL:' + QUEUE, False), [{'predicate': 'letter_drafted', 'version': 'letter-right'}]))
        k.on_event(BOOK_2, execute=True)   # the book changes: neither the letter nor what was made on it stands (T3's stamped yes outlives the book)
        self.assertEqual((said(s), said(s, 'letter_queued'), 'handoff' in s.active_work), (('UNKNOWN', None, False), ('UNKNOWN', None, False), False))   # and the kind kept no books: no step here was a hand-off

    def test_t8_tries_written_out_as_steps_name_their_try_and_tell_nothing_of_a_check_and_three_asks_without_a_rule_complete_on_a_yes(self):
        tries = extra('t-tries', goals=['letter_queued', 'letter_with_hand'], grants=[f'action:give-draft-{n}@t' for n in (1, 2, 3)], providers={f'model-try-{n}': 1 for n in (1, 2, 3)},   # one step, one fact and one slot for each try
                      rules=[{'id': 'R-LETTER-WITH-HAND@t', 'head': 'letter_with_hand', 'branches': [[f'draft_{n}_with_model'] for n in (1, 2, 3)], 'approved': True, 'source': 'reviewed/letters-desk'}],
                      methods=[method(f'give-draft-{n}@t', f'draft_{n}_with_model', ['loan_on_book'], provider=f'model-try-{n}', cost={'compute': 2, 'money': 0, 'attention': 0}) for n in (1, 2, 3)])
        s = world(DESK, tries); k = Kernel(s); paid = lambda: (s.budget['compute'], sum(s.providers[f'model-try-{n}'] for n in (1, 2, 3)))
        failed = lambda n, version, why: k.on_event({'predicate': f'draft_{n}_with_model', 'truth': 'FALSE', 'verified': True, 'source': CHECKER, 'version': version, 'why': why, 'depends_on': ON_BOOK}, execute=True)
        first = k.run_standing(execute=True); x1 = first['runs'][1]['model_receipts'][0]
        self.assertEqual((self.went(first), paid()), ([('letter_queued', 'QUERY_EVIDENCE', []), ('letter_with_hand', DONE, ['give-draft-1@t'])], (8, 2)))   # blocked again, where a hand-off waits
        again = failed(1, 'letter-a', WRONG); x2 = again['runs'][0]['model_receipts'][0]
        self.assertEqual((self.went(again), paid(), x1['method'], x2['method'], sorted(x2)), ([('letter_with_hand', DONE, ['give-draft-2@t'])], (6, 1), 'give-draft-1@t', 'give-draft-2@t',
                                                                                             ['action', 'method', 'model_effect', 'scope', 'sha256', 'status']))   # each receipt names its step, and so its try; none says what an earlier check found
        late = failed(1, 'letter-a-late', 'a late copy of the first draft')   # a late copy of the first check is a row on the first try's own fact: it spends nothing
        self.assertEqual((self.went(late), paid()), ([('letter_with_hand', 'SUPPORTED_BY_EVIDENCE', [])], (6, 1)))
        out = k.on_event(says('TRUE', 'the-first-letter-after-all', depends_on=ON_BOOK + [{'predicate': 'draft_1_with_model', 'version': 'local-sim-1'}]), execute=True)   # a TRUE that rests on the failed first try does not read
        self.assertEqual((self.went(out), said(s)), ([('letter_queued', 'QUERY_EVIDENCE', [])], ('UNKNOWN', None, False)))
        self.assertEqual(self.went(failed(2, 'letter-b', 'the letter does not name the loan L-17')), [('letter_with_hand', DONE, ['give-draft-3@t'])])
        self.assertEqual({key.split('|')[1]: row['why'] for key, row in s.evidence.items() if 'why' in row},   # one row a try: the reason of each try's last check stays stored
                         {'draft_1_with_model': 'a late copy of the first draft', 'draft_2_with_model': 'the letter does not name the loan L-17'})
        self.assertEqual((self.went(failed(3, 'letter-c', WRONG)), paid()), ([('letter_with_hand', 'PROVIDER_REQUIRED', [])], (4, 0)))   # the tries that were written are used up
        self.assertEqual(self.went(k.on_event(BOOK_2, execute=True)), [('letter_queued', 'QUERY_EVIDENCE', []), ('letter_with_hand', 'PROVIDER_REQUIRED', [])])   # and a changed book opens no new hand-over (the kind: C8)
        p = pack('217_three_asks')   # T6 without its rule: the three asks of pack 217 and one queueing step for each draft. A yes to try 2 completes, so T6's stop comes from a rule's head as a prerequisite
        asks = extra('t-three-asks-no-rule', methods=p['methods'] + [method(f'queue-letter-on-draft-{n}@t', 'letter_queued', [f'draft_{n}_passes']) for n in (1, 2, 3)], providers=p['providers'],
                     grants=p['grants'] + [f'action:queue-letter-on-draft-{n}@t' for n in (1, 2, 3)])
        s = world(DESK, asks); k = Kernel(s); x1 = issued(k.run_standing(execute=True)); x2 = issued(answer(k, x1, 'FALSE', CHECKER, execute=True))
        self.assertEqual((x2['method'], sorted(x2['ask'])), ('ask-checker-about-draft-2@1', ['asked_in', 'predicate', 'question', 'to']))   # still the words of the pack and nothing of the check that failed
        yes = answer(k, x2, 'TRUE', CHECKER, execute=True)
        self.assertEqual((self.went(yes), said(s, 'letter_queued')), ([('letter_queued', DONE, ['queue-letter-on-draft-2@t'])], ('TRUE', 'LOCAL_MODEL:queue-letter-on-draft-2@t', False)))


class ClaimTests(unittest.TestCase):
    def test_c1_the_step_parks_and_a_later_look_waits_and_pays_nothing(self):
        s, k, x = handed(); before = held(s)
        for execute in (True, False, True):
            r = k.run_standing(execute=execute)['runs'][0]
            self.assertEqual((r['status'], r['work_state'], r['actions'], r['pending'], r['waits'], r['model_receipts'], r['cost']),
                             ('WAITING', 'waiting', [], [QUEUE], [MODEL_M], [], {'compute': 0, 'money': 0, 'attention': 0}))
            self.assertEqual(matched(r), [('METHOD_MATCH', QUEUE), ('METHOD_PENDING', MODEL_M)])   # the plan waits on the method whose work is out
        self.assertEqual((held(s), list(open_handoffs(s).values())[0]['receipt']), (before, x['sha256']))   # the same hand-over is out; nothing was paid, and no slot was taken

    def test_c2_there_is_no_stamp_for_a_hand_off(self):
        s, k, x = handed(); before = held(s)
        for party in (HAND, CHECKER, OFFICER, 'owner', ''):
            for truth in ('TRUE', 'FALSE'):
                with self.assertRaisesRegex(ValueError, 'An answer is TRUE or FALSE, from a named party, to an ask receipt'): answer(k, x, truth, party, execute=True)
        dressed = dict(x, ask={'predicate': 'letter_drafted', 'question': WORK, 'to': HAND})   # the receipt dressed up as a question: none is out
        with self.assertRaisesRegex(ValueError, 'No open ask matches this receipt'): answer(k, dressed, 'TRUE', HAND, execute=True)
        self.assertEqual((held(s), open_asks(s), looks(s)), (before, {}, WAITS))

    def test_c3_the_checkers_row_that_names_the_receipt_confirms_the_work_and_the_next_step_runs(self):
        s, k, x = handed(); out = passes(k, x); r = out['runs'][0]
        self.assertEqual((out['status'], out['affected'], r['status'], r['actions'], r['cost']), ('RECONCILED', ['letter_queued'], DONE, [QUEUE], {'compute': 1, 'money': 0, 'attention': 0}))
        self.assertEqual(closed(out), [{'handoff': KEY, 'receipt': x['sha256'], 'tries': 1, 'truth': 'TRUE', 'source': CHECKER, 'version': 'letter-right', 'checks': x['sha256'], 'confirmed': True}])
        self.assertEqual([e['operation'] for e in r['trace']][-3:], ['LOCAL_EFFECT', 'HANDOFF_CLOSED', 'TERMINAL'])   # the line is in the run's hash chain, after the plan's rows
        self.assertEqual((said(s), said(s, 'letter_queued'), open_handoffs(s), s.active_work), (('TRUE', CHECKER, False), ('TRUE', 'LOCAL_MODEL:' + QUEUE, False), {}, {'handoff': {}}))
        self.assertEqual(s.evidence[SCOPE + '|letter_queued']['depends_on'], [{'predicate': 'letter_drafted', 'version': 'letter-right'}])   # what is made on the letter rests on the checker's row at its version
        self.assertEqual((looks(s), s.budget), ([('SUPPORTED_BY_EVIDENCE', [], None, None, [])], {'compute': 7, 'money': 5, 'attention': 3}))   # and nothing is handed over or paid again

    def test_c4_a_failed_check_hands_the_work_over_again_and_the_next_try_is_told_what_happened(self):
        s, k, x1 = handed(); out = fails(k, x1, 'letter-a'); x2 = issued(out)
        self.assertEqual((out['status'], st(out)), ('RECONCILED', HANDS))   # the same look that took the failed check hands the work over again
        self.assertEqual(told(x2), {'predicate': 'letter_drafted', 'to': HAND, 'instruction': WORK, 'verified_by': CHECKER, 'try': 2,
                                    'before': [{'try': 1, 'to': HAND, 'receipt': x1['sha256'], 'checked': {'truth': 'FALSE', 'source': CHECKER, 'version': 'letter-a', 'why': WRONG}}]})
        self.assertNotEqual(x1['handoff']['handed_in'], x2['handoff']['handed_in'])
        self.assertEqual((s.budget, s.providers['letter-model'], closed(out)), ({'compute': 6, 'money': 5, 'attention': 3}, 1, []))   # every try is paid and takes a slot; nothing is closed
        self.assertEqual((open_handoffs(s)[KEY]['receipt'], open_handoffs(s)[KEY]['failed'], said(s)), (x2['sha256'], None, ('FALSE', CHECKER, False)))   # the books hold the try that is out
        out = fails(k, x2, 'letter-b', why='the letter does not name the loan L-17'); x3 = issued(out)
        self.assertEqual((x3['handoff']['try'], [(t['try'], t['to'], t['receipt'], t['checked']['version'], t['checked']['why']) for t in x3['handoff']['before']]),
                         (3, [(1, HAND, x1['sha256'], 'letter-a', WRONG), (2, HAND, x2['sha256'], 'letter-b', 'the letter does not name the loan L-17')]))
        out = passes(k, x3)   # the third try passes: one line says how many tries it took
        self.assertEqual((st(out), [(c['tries'], c['receipt'], c['confirmed']) for c in closed(out)]), ([(DONE, [QUEUE], None, None, [])], [(3, x3['sha256'], True)]))

    def test_c5_only_a_row_of_the_named_checker_that_names_the_receipt_of_the_try_that_is_out_is_its_check(self):
        rows = {'another source': lambda x: says('FALSE', 'v1', x['sha256'], source='checker:other', why=WRONG),
                'the hand itself': lambda x: says('FALSE', 'v1', x['sha256'], source=HAND, why=WRONG),
                'no receipt named': lambda x: says('FALSE', 'v1', why=WRONG),
                'another receipt': lambda x: says('FALSE', 'v1', '0' * 64, why=WRONG),
                'a row that reads UNKNOWN': lambda x: says('UNKNOWN', 'v1', x['sha256'], why='the letter could not be read'),
                'a row that rests on a book that is gone': lambda x: says('FALSE', 'v1', x['sha256'], why=WRONG, depends_on=[{'predicate': 'loan_on_book', 'version': 'another-book'}])}
        for name, row in rows.items():
            s, k, x = handed(); out = k.on_event(row(x), execute=True)
            self.assertEqual((st(out), s.providers['letter-model'], s.budget['compute'], open_handoffs(s)[KEY]['receipt'], open_handoffs(s)[KEY]['failed']), (WAITS, 2, 8, x['sha256'], None), name)
        s, k, x1 = handed(); x2 = issued(fails(k, x1, 'letter-a'))   # a late check of the first try while the second is out: no try is used
        out = k.on_event(says('FALSE', 'letter-a-late', x1['sha256'], why='a late copy of the first draft', depends_on=ON_BOOK), execute=True)
        self.assertEqual((st(out), s.providers['letter-model'], open_handoffs(s)[KEY]['receipt'], open_handoffs(s)[KEY]['failed']), (WAITS, 1, x2['sha256'], None))
        out = fails(k, x2, 'letter-b')   # the check of the try that is out does use one
        self.assertEqual((st(out), issued(out)['handoff']['try'], s.providers['letter-model']), (HANDS, 3, 0))

    def test_c6_the_capacity_of_the_hands_provider_is_the_number_of_tries(self):
        self.assertEqual(pack('211_hand_to_model')['providers'], {'letter-model': 3})   # stated in the pack
        s, k, x = handed(); receipts = [x]
        for n in (1, 2, 3):
            out = fails(k, receipts[-1], f'letter-{n}')
            if n < 3: receipts.append(issued(out))
        r = out['runs'][0]
        self.assertEqual(([y['handoff']['try'] for y in receipts], r['status'], r['work_state'], r['model_receipts'], r['stop_reasons']), ([1, 2, 3], 'PROVIDER_REQUIRED', 'blocked', [], ['PROVIDER_REQUIRED']))
        self.assertEqual(admissions(r), [([MODEL_M, QUEUE], False, ['PROVIDER_REQUIRED'])])   # the method is planned as a step, and the kernel's own gate turns it down
        self.assertEqual((s.budget, s.providers['letter-model']), ({'compute': 4, 'money': 5, 'attention': 3}, 0))   # three tries were paid; the fourth is not
        before = held(s)
        self.assertEqual((looks(s, execute=False), looks(s), held(s)), (NO_SLOT, NO_SLOT, before))   # dry or executed, the look says the same and pays nothing
        out_of = open_handoffs(s)[KEY]
        self.assertEqual((out_of['issued']['handoff']['try'], out_of['failed']['truth'], out_of['failed']['version'], out_of['failed']['why']), (3, 'FALSE', 'letter-3', WRONG))   # the books say which try failed and why
        s.apply(extra('t-fresh-slot', providers={'letter-model': 1}))   # a pack states a new level for the hand: the next look hands the work over, as try 4
        x4 = issued(Kernel(s).run_standing(execute=True))
        self.assertEqual((x4['handoff']['try'], [t['try'] for t in x4['handoff']['before']], s.providers['letter-model']), (4, [1, 2, 3], 0))

    def test_c7_when_the_first_hand_has_no_slot_the_next_method_takes_the_next_try(self):
        s, k, x = handed(BOTH); self.assertEqual(x['method'], MODEL_M)   # attention is saved first: the model is handed the letter while it has a slot
        r = k.run_standing(execute=True)['runs'][0]   # while the model's try is out and has not failed, the officer is not handed the letter
        self.assertEqual((r['status'], r['waits'], r['model_receipts'], matched(r)), ('WAITING', [MODEL_M], [], [('METHOD_MATCH', QUEUE), ('METHOD_PENDING', MODEL_M), ('METHOD_MATCH', OFFICER_M)]))
        self.assertEqual(admissions(r), [([QUEUE], True, []), ([OFFICER_M, QUEUE], True, [])])   # the officer's way was open and affordable; the wait costs nothing and wins
        for n in (1, 2, 3):
            out = fails(k, x, f'letter-{n}'); x = issued(out)
        self.assertEqual((x['method'], x['handoff']['to'], x['handoff']['try'], [(t['try'], t['to']) for t in x['handoff']['before']]), (OFFICER_M, OFFICER, 4, [(1, HAND), (2, HAND), (3, HAND)]))
        self.assertEqual(admissions(out['runs'][0])[:2], [([MODEL_M, QUEUE], False, ['PROVIDER_REQUIRED']), ([OFFICER_M, QUEUE], True, [])])
        self.assertEqual((open_handoffs(s)[KEY]['method'], s.budget, s.providers), (OFFICER_M, {'compute': 4, 'money': 5, 'attention': 2}, {'local-provider': 4, 'letter-model': 0, 'collections-officer': 0}))
        out = passes(k, x)
        self.assertEqual((st(out), [(c['tries'], c['receipt'], c['confirmed']) for c in closed(out)]), ([(DONE, [QUEUE], None, None, [])], [(4, x['sha256'], True)]))

    def test_c8_a_confirmation_rests_on_what_the_checker_read(self):
        s, k, x = handed(); passes(k, x)
        self.assertEqual((said(s), said(s, 'letter_queued')), (('TRUE', CHECKER, False), ('TRUE', 'LOCAL_MODEL:' + QUEUE, False)))
        out = k.on_event(BOOK_2, execute=True); y = issued(out)   # the loan book changes
        self.assertEqual((said(s), said(s, 'letter_queued')), (('UNKNOWN', None, False), ('UNKNOWN', None, False)))   # neither the letter nor what was made on it stands
        self.assertEqual((st(out), told(y)['try'], told(y)['before'], y['sha256'] != x['sha256'], s.providers['letter-model']), (HANDS, 1, [], True, 1))   # handed over again, as a new hand-over
        late = k.on_event(says('FALSE', 'old-letter-new-book', x['sha256'], why='the letter says an overdue amount of 240; the loan book says 180', depends_on=[{'predicate': 'loan_on_book', 'version': BOOK_2['version']}]), execute=True)
        self.assertEqual((st(late), s.providers['letter-model'], open_handoffs(s)[KEY]['receipt']), (WAITS, 1, y['sha256']))   # the old letter's check names the old receipt: it uses no try of the new hand-over

    def test_c9_at_the_journals_door_one_check_is_one_entry_and_one_look_and_a_restart_keeps_the_hand_over(self):
        with tempfile.TemporaryDirectory() as tmp:
            run = J.start(['simulate_fact', 'handoff'], [CHECKER], name='t-letter')
            for n in ('210_letters_desk', '211_hand_to_model'): run.add('pack', {'pack': pack(n)})
            keep_book(tmp, 240); rows = check(tmp); self.assertEqual([r['predicate'] for r in rows], ['loan_on_book'])
            e = run.add('event', {'row': rows[0], 'execute': True}); x1 = issued(run.detail[e['seq']]); n = len(run.journal)
            own = dict(says('TRUE', 'the-hands-own-word', x1['sha256'], source=HAND))
            door = 'The event door lets in only verified rows that are not decisions, from a checker the header names'
            stamp = 'An answer is TRUE or FALSE, from a named party, to an ask receipt'
            for kind, body, words in (('answer', {'receipt': x1, 'truth': 'TRUE', 'source': HAND, 'execute': True}, stamp), ('answer', {'receipt': x1, 'truth': 'TRUE', 'source': CHECKER, 'execute': True}, stamp),
                                      ('event', {'row': own, 'execute': True}, door), ('event', {'row': dict(own, source=CHECKER, final=True), 'execute': True}, door),
                                      ('event', {'row': dict(own, source=CHECKER, verified=False), 'execute': True}, door)):
                with self.assertRaisesRegex(ValueError, words): run.add(kind, body)
            self.assertEqual((len(run.journal), list(open_handoffs(run.state))), (n, [KEY]))   # nothing was sealed, and the hand-over is out as before
            self.assertEqual(draft(tmp, x1, believes=2400), 2400); rows = check(tmp)
            e = run.add('event', {'row': rows[1], 'execute': True}); x2 = issued(run.detail[e['seq']])
            self.assertEqual((e['seq'], e['kind'], len(e['result']['briefs']), e['result']['briefs'][0]['status'], x2['handoff']['try']), (n, 'event', 1, 'WAITING', 2))   # one check: one entry, one look
            keep = J.Keep(); head = J.save(run, keep); again = J.restart(keep)   # a new process: the kept text and the kept head, nothing else
            self.assertEqual((again.base, again.cut, again.notice, open_handoffs(again.state), J.state_digest(again.state)), (head, 0, [], open_handoffs(run.state), J.state_digest(run.state)))
            self.assertEqual(draft(tmp, x2, believes=2400), 240); rows = check(tmp)   # the hand reads what it was told
            e = again.add('event', {'row': rows[1], 'execute': True}); out = again.detail[e['seq']]
            self.assertEqual((st(out), [(c['tries'], c['confirmed'], c['checks']) for c in closed(out)]), ([(DONE, [QUEUE], None, None, [])], [(2, True, x2['sha256'])]))
            self.assertEqual(e['result']['briefs'][0]['settled'], [{'operation': 'HANDOFF_CLOSED', 'data': closed(out)[0]}])   # the journal's entry keeps the line the kind wrote
            head = J.save(again, keep); third = J.restart(keep)   # replay computes every result again: the same head, the same State
            self.assertEqual((third.base, J.state_digest(third.state), open_handoffs(third.state)), (head, J.state_digest(again.state), {}))


class CheckerTests(unittest.TestCase):
    """The stand-ins of the example. The checker's rows are computed from the two files and from nothing else."""
    def letter(self, tmp, text): (Path(tmp) / 'letter.txt').write_bytes(text.encode('utf-8'))

    def test_the_checker_says_true_only_of_a_letter_that_names_borrower_loan_and_the_books_amount(self):
        cite = 'for hand-over ' + 'a' * 64 + '\n'
        with tempfile.TemporaryDirectory() as tmp:
            keep_book(tmp, 240); book = check(tmp)
            self.assertEqual([(r['predicate'], r['truth'], r['source'], r['verified']) for r in book], [('loan_on_book', 'TRUE', CHECKER, True)])   # no letter: no row on the letter
            cases = [('Dear A. Rao, your loan L-17 is overdue by 240. Please pay.', None),
                     ('Dear A. Rao, your loan L-17 is overdue by 2400. Please pay.', WRONG),
                     ('Dear A. Rao, your loan L-17 is overdue by 240, or overdue by 24.', 'the letter says an overdue amount of 240 and 24; the loan book says 240'),
                     ('Dear A. Rao, your loan L-17 is overdue.', 'the letter says an overdue amount of nothing; the loan book says 240'),
                     ('Dear B. Shah, your loan L-17 is overdue by 240.', 'the letter does not name the borrower A. Rao'),
                     ('Dear A. Rao, your loan L-71 is overdue by 240.', 'the letter does not name the loan L-17'),
                     ('', 'the letter does not name the borrower A. Rao; the letter does not name the loan L-17; the letter says an overdue amount of nothing; the loan book says 240')]
            for body, why in cases:
                self.letter(tmp, cite + body + '\n'); row = check(tmp)[1]
                self.assertEqual((row['truth'], row.get('why'), row['checks'], row['source'], row['verified'], row['depends_on']),
                                 ('FALSE' if why else 'TRUE', why, 'a' * 64, CHECKER, True, [{'predicate': 'loan_on_book', 'version': book[0]['version']}]), body)
                self.assertNotIn('final', row)
            self.letter(tmp, 'Dear A. Rao, your loan L-17 is overdue by 240.\n')   # a letter that cites no hand-over: the row names none
            self.assertEqual((check(tmp)[1]['truth'], check(tmp)[1]['checks']), ('TRUE', None))

    def test_the_versions_are_digests_of_what_was_read(self):
        with tempfile.TemporaryDirectory() as tmp:
            keep_book(tmp, 240); self.letter(tmp, 'for hand-over ' + 'a' * 64 + '\nDear A. Rao, your loan L-17 is overdue by 240.\n'); a = check(tmp)
            book = (Path(tmp) / 'loan_book.json').read_bytes(); text = (Path(tmp) / 'letter.txt').read_bytes()
            self.assertEqual((a[0]['version'], a[1]['version']), ('book-' + hashlib.sha256(book).hexdigest()[:16], 'letter-' + hashlib.sha256(text + b'\n' + book).hexdigest()[:16]))
            self.assertEqual(check(tmp), a)   # the same files, the same rows
            self.letter(tmp, 'for hand-over ' + 'a' * 64 + '\nDear A. Rao, your loan L-17 is overdue by 240. \n'); b = check(tmp)
            self.assertEqual((b[0] == a[0], b[1]['version'] == a[1]['version'], b[1]['truth']), (True, False, 'TRUE'))   # one more character in the letter: another version
            keep_book(tmp, 180); c = check(tmp)   # another book: both versions move, and the letter's row rests on the new book's row
            self.assertEqual((c[0]['version'] == a[0]['version'], c[1]['version'] == b[1]['version'], c[1]['truth'], c[1]['depends_on']), (False, False, 'FALSE', [{'predicate': 'loan_on_book', 'version': c[0]['version']}]))

    def test_the_hand_never_reads_the_book_and_reads_what_its_receipt_tells_it(self):
        first = {'sha256': 'b' * 64, 'handoff': {'before': []}}
        later = {'sha256': 'c' * 64, 'handoff': {'before': [{'try': 1, 'to': HAND, 'receipt': 'b' * 64, 'checked': {'truth': 'FALSE', 'source': CHECKER, 'version': 'v', 'why': WRONG}}]}}
        untold = {'sha256': 'd' * 64, 'handoff': {'before': [{'try': 1, 'to': HAND, 'receipt': 'b' * 64, 'checked': None}]}}
        with tempfile.TemporaryDirectory() as tmp:   # no loan book in the folder at all: the hand writes its letter all the same
            self.assertEqual((draft(tmp, first, believes=2400), (Path(tmp) / 'letter.txt').read_text(encoding='utf-8')),
                             (2400, 'for hand-over ' + 'b' * 64 + '\nDear A. Rao, your loan L-17 is overdue by 2400. Please pay within 14 days.\n'))
            self.assertEqual((draft(tmp, later, believes=2400), draft(tmp, later, believes=2400, reads_before=False), draft(tmp, untold, believes=7)), (240, 2400, 7))
            self.assertEqual(sorted(p.name for p in Path(tmp).iterdir()), ['letter.txt'])

    def test_the_hand_reads_the_last_check_it_was_told_and_the_last_amount_it_names_and_a_check_told_without_a_reason_tells_it_nothing(self):
        receipt = lambda *checked: {'sha256': 'e' * 64, 'handoff': {'before': [{'try': n + 1, 'to': HAND, 'receipt': 'b' * 64, 'checked': c} for n, c in enumerate(checked)]}}
        why = lambda text: {'truth': 'FALSE', 'source': CHECKER, 'version': 'v', 'why': text}
        bare = {'truth': 'FALSE', 'source': CHECKER, 'version': 'v'}   # what the kind tells of a check that gave no reason, or a list of reasons (L8)
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(draft(tmp, receipt(why('the letter says an overdue amount of 2400; the loan book says 999'), why('the letter says an overdue amount of 999; the loan book says 240')), believes=7), 240)   # the words of the last check, not of the first
            self.assertEqual(draft(tmp, receipt(why('the loan book says 111; read again, the loan book says 240')), believes=7), 240)   # and the last amount those words name
            self.assertEqual((draft(tmp, receipt(bare), believes=7), draft(tmp, receipt(why(WRONG), bare), believes=7)), (7, 240))   # a check told without a reason tells the hand nothing; the last check that gave one is read
            self.assertEqual(draft(tmp, receipt(why('the letter does not name the loan L-17')), believes=7), 7)   # a reason that names no amount: the hand writes what it believes


class WalkTests(unittest.TestCase):
    def test_in_seeded_walks_the_letter_is_queued_only_on_the_checkers_row_and_tries_never_pass_the_capacity(self):
        steps = ('look', 'dry', 'fail', 'late', 'foreign', 'unnamed', 'pass')
        for seed in range(120):
            rng = random.Random(seed); s, k, x = handed(BOTH); receipts = [x]; queued = False
            for n in range(rng.randrange(4, 14)):
                what = rng.choice(steps); now = receipts[-1]
                if what in ('look', 'dry'): out = k.run_standing(execute=what == 'look')
                elif what == 'fail': out = fails(k, now, f'letter-{seed}-{n}')
                elif what == 'late': out = k.on_event(says('FALSE', f'late-{seed}-{n}', rng.choice(receipts[:-1])['sha256'] if len(receipts) > 1 else '0' * 64, why=WRONG, depends_on=ON_BOOK), execute=True)
                elif what == 'foreign': out = k.on_event(says('FALSE', f'foreign-{seed}-{n}', now['sha256'], source='checker:other', why=WRONG), execute=True)
                elif what == 'unnamed': out = k.on_event(says('FALSE', f'unnamed-{seed}-{n}', why=WRONG), execute=True)
                else: out = passes(k, now, f'right-{seed}-{n}')
                for r in out['runs']:
                    for y in r['model_receipts']:
                        if 'handoff' in y: receipts.append(y)
                    self.assertEqual(QUEUE in r['actions'] and r['work_state'] == 'completed', what == 'pass' and not queued, (seed, n, what))   # queued in the look that took the checker's TRUE, and in no other
                    if what == 'pass' and not queued:
                        self.assertEqual([(c['confirmed'], c['source'], c['checks'], c['tries']) for c in closed(out)], [(True, CHECKER, now['sha256'], now['handoff']['try'])], (seed, n))
                if what == 'pass': queued = True
                if queued: break
            tries = [y['handoff']['try'] for y in receipts]
            self.assertEqual(tries, list(range(1, len(tries) + 1)), seed)   # the tries are numbered on, each receipt once
            self.assertEqual([len(y['handoff']['before']) for y in receipts], [t - 1 for t in tries], seed)   # and every try is told of all the tries before it
            self.assertLessEqual(len([y for y in receipts if y['method'] == MODEL_M]), 3, seed); self.assertLessEqual(len([y for y in receipts if y['method'] == OFFICER_M]), 1, seed)
            self.assertEqual((s.providers['letter-model'], s.providers['collections-officer']), (3 - len([y for y in receipts if y['method'] == MODEL_M]), 1 - len([y for y in receipts if y['method'] == OFFICER_M])), seed)
            self.assertEqual(said(s, 'letter_queued')[0] == 'TRUE', queued, seed)


class SequenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        made = scenes(); cls.e, cls.q = made['handoff_existing'], made['handoff_letter']
        cls.data = json.loads((ROOT / 'results' / 'actual_run_records.json').read_text(encoding='utf-8'))

    def step(self, steps): return [(x['entry'], x['result']['event']['predicate'], x['result']['event']['truth'], st(x['result'])) for x in steps]

    def test_the_record_on_disk_holds_both_sequences(self):
        for name, made in (('handoff_existing', self.e), ('handoff_letter', self.q)):
            self.assertEqual(json.dumps(made, sort_keys=True), json.dumps(self.data['scenes'][name], sort_keys=True), name)
        self.assertEqual(self.data['action_handlers']['handoff'], {'module': 'kinds.handoff', 'file': 'kinds/handoff.py', 'sha256': hashlib.sha256((ROOT / 'kinds' / 'handoff.py').read_bytes()).hexdigest()})
        self.assertEqual([(c['id'], (c['outcome'] or c['run'])['status']) for c in self.data['cases'] if c['id'][:2] in ('84', '85', '86', '87')],
                         [('84_handed_over', 'WAITING'), ('85_no_step', 'QUERY_EVIDENCE'), ('86_no_slot_left', 'PROVIDER_REQUIRED'), ('87_next_hand', 'WAITING')])

    def test_existing_parts_the_doers_word_closes_an_ask_put_to_the_doer(self):
        d = self.e['doer_asked']; self.assertEqual(list(self.e), ['doer_asked', 'checker_asked', 'checker_stamps_yes', 'checker_rows', 'no_step', 'three_asks'])
        self.assertEqual((st(d['look']), st(d['doer_says_done']), d['checker_says_no']['status'], d['checker_says_no']['runs']),
                         ([('WAITING', [ASK_DOER], [QUEUE], [ASK_DOER], [])], [(DONE, [QUEUE], None, None, [])], 'DECISION_STANDS', []))
        self.assertEqual((d['after']['letter_drafted'], d['after']['letter_queued']['truth'], d['after'] == d['after_done']),
                         ({'truth': 'TRUE', 'source': 'STAMP:' + HAND, 'final': True, 'version': d['after_done']['letter_drafted']['version']}, 'TRUE', True))

    def test_existing_parts_an_ask_put_to_the_checker_ends_on_a_no_and_a_stamped_yes_outlives_the_book(self):
        c, y = self.e['checker_asked'], self.e['checker_stamps_yes']
        self.assertEqual((c['doer_says_done'], c['second_draft_stamp']), ({'party': HAND, 'truth': 'TRUE', 'refused': 'The answer does not come from the party that was asked'},
                                                                           {'party': CHECKER, 'truth': 'TRUE', 'refused': 'No open ask matches this receipt'}))
        self.assertEqual((st(c['checker_says_no']), c['second_draft_row']['status'], st(c['look_again']), c['after']['letter_drafted']['source'], c['after']['budget'], c['after']['providers']),
                         ([('REFUSED', [], None, None, ['REFUSED'])], 'DECISION_STANDS', [('REFUSED', [], None, None, ['REFUSED'])], 'STAMP:' + CHECKER, {'compute': 10, 'money': 5, 'attention': 2}, {'local-provider': 4, 'checker-channel': 2}))
        self.assertEqual((st(y['checker_says_yes']), st(y['book_changes']), y['checker_says_no']['status'], y['after'] == y['after_yes'], y['after']['letter_drafted']['final'], y['after']['letter_queued']['truth']),
                         ([(DONE, [QUEUE], None, None, [])], [('SUPPORTED_BY_EVIDENCE', [], None, None, [])], 'DECISION_STANDS', True, True, 'TRUE'))

    def test_existing_parts_rows_under_an_ask_and_no_step_at_all(self):
        w, n = self.e['checker_rows'], self.e['no_step']
        self.assertEqual([(st(f['check']), f['check']['runs'][0]['model_receipts'], f['after']['budget'], f['after']['providers'], list(f['after']['open_asks'])) for f in w['failed_checks']],
                         [([('WAITING', [], [QUEUE], [ASK_CHECKER], [])], [], w['after_look']['budget'], w['after_look']['providers'], [KEY])] * 3)
        self.assertEqual((st(w['passing_check']), w['after']['letter_drafted']['source'], list(w['after']['open_asks'])), ([(DONE, [QUEUE], None, None, [])], CHECKER, [KEY]))
        self.assertEqual((st(n['look']), st(n['failed_check']), st(n['passing_check']), n['after']['budget'], n['after']['providers']),
                         ([('QUERY_EVIDENCE', [], None, None, ['QUERY_EVIDENCE'])], [('METHOD_ABSENT', [], None, None, ['METHOD_ABSENT'])], [(DONE, [QUEUE], None, None, [])], {'compute': 9, 'money': 5, 'attention': 3}, {'local-provider': 3}))
        self.assertEqual([x for part in (n['look'], n['failed_check']) for r in part['runs'] for x in r['model_receipts']], [])   # no receipt names a hand

    def test_existing_parts_three_asks_under_a_rule(self):
        t = self.e['three_asks']; asks = [f'ask-checker-about-draft-{n}@1' for n in (1, 2, 3)]
        self.assertEqual([st(t[key]) for key in ('look', 'no_to_try_1', 'no_to_try_2', 'no_to_try_3')],
                         [[('WAITING', [asks[0]], [QUEUE], [asks[0]], [])], [('WAITING', [asks[1]], [QUEUE], [asks[1]], [])], [('WAITING', [asks[2]], [QUEUE], [asks[2]], [])], [('REFUSED', [], None, None, ['REFUSED'])]])
        self.assertEqual([sorted(issued(t[key])['ask']) for key in ('no_to_try_1', 'no_to_try_2')], [['asked_in', 'predicate', 'question', 'to']] * 2)
        stop = t['yes']['yes_to_try_2']['runs'][0]
        self.assertEqual((stop['status'], stop['stopped'], t['yes']['draft_2_passes']['truth'], t['yes']['after']['letter_drafted']['truth'], t['yes']['after']['letter_queued']['truth']),
                         ('STEP_STOPPED', {'method': QUEUE, 'reason': 'Prerequisite not true before effect: letter_drafted'}, 'TRUE', 'UNKNOWN', 'UNKNOWN'))

    def test_letter_two_tries_a_restart_and_a_book_that_changes(self):
        t = self.q['tries']; self.assertEqual((list(self.q), t['packs'], t['kinds'], t['checkers']), (['tries', 'spent'], ['210_letters_desk', '211_hand_to_model'], ['simulate_fact', 'handoff'], [CHECKER]))
        self.assertEqual((t['before_the_book']['entry'], st(t['before_the_book']['result'])), (3, [('QUERY_EVIDENCE', [], None, None, ['QUERY_EVIDENCE'])]))   # the book has not been read: nothing is handed over
        self.assertEqual(self.step(t['handed_over']), [(4, 'loan_on_book', 'TRUE', HANDS)]); x1 = issued(t['handed_over'][-1]['result'])
        self.assertEqual(t['at_the_door'], {'a_stamp_from_the_hand': 'An answer is TRUE or FALSE, from a named party, to an ask receipt',
                                            'a_stamp_from_the_checker': 'An answer is TRUE or FALSE, from a named party, to an ask receipt',
                                            'the_hands_own_row': 'The event door lets in only verified rows that are not decisions, from a checker the header names',
                                            'a_decision_under_the_checkers_name': 'The event door lets in only verified rows that are not decisions, from a checker the header names'})
        self.assertEqual((t['second_look']['entry'], st(t['second_look']['result']), t['after_second_look'], t['after_handed_over']['budget'], t['after_handed_over']['providers']),
                         (5, WAITS, t['after_handed_over'], {'compute': 8, 'money': 5, 'attention': 3}, {'local-provider': 4, 'letter-model': 2}))
        self.assertEqual((t['wrote_1'], self.step(t['failed_check'])), (2400, [(6, 'letter_drafted', 'FALSE', HANDS)])); x2 = issued(t['failed_check'][-1]['result'])
        self.assertEqual((t['failed_check'][-1]['result']['event']['checks'], told(x2)['try'], told(x2)['before']),
                         (x1['sha256'], 2, [{'try': 1, 'to': HAND, 'receipt': x1['sha256'], 'checked': {'truth': 'FALSE', 'source': CHECKER, 'version': t['failed_check'][-1]['result']['event']['version'], 'why': WRONG}}]))
        self.assertEqual((t['restarted'], t['head_kept']['length'], st(t['look_after_restart']['result'])), ({'head': t['head_kept'], 'cut': 0, 'notice': [], 'after': t['after_failed_check']}, 7, WAITS))
        late = t['late_copy'][-1]['result']['event']   # a late copy of the first draft names the first receipt: the look waits and no try is used
        self.assertEqual((self.step(t['late_copy']), late['checks'], t['after_late_copy']['providers'], t['after_late_copy']['budget'], list(t['after_late_copy']['open_handoffs'].values())[0]['receipt']),
                         ([(8, 'letter_drafted', 'FALSE', WAITS)], x1['sha256'], t['after_failed_check']['providers'], t['after_failed_check']['budget'], x2['sha256']))
        self.assertEqual((t['wrote_2'], self.step(t['passing_check'])), (240, [(9, 'letter_drafted', 'TRUE', [(DONE, [QUEUE], None, None, [])])]))   # the hand read what it was told
        self.assertEqual([(c['tries'], c['receipt'], c['checks'], c['source'], c['confirmed']) for c in closed(t['passing_check'][-1]['result'])], [(2, x2['sha256'], x2['sha256'], CHECKER, True)])
        self.assertEqual((t['after_passing_check']['budget'], t['after_passing_check']['providers'], t['after_passing_check']['open_handoffs'], t['after_passing_check']['letter_queued']['truth']),
                         ({'compute': 5, 'money': 5, 'attention': 3}, {'local-provider': 3, 'letter-model': 1}, {}, 'TRUE'))
        self.assertEqual(self.step(t['book_changed']), [(10, 'loan_on_book', 'TRUE', HANDS), (11, 'letter_drafted', 'FALSE', WAITS)]); x3 = issued(t['book_changed'][0]['result'])
        self.assertEqual((told(x3)['try'], told(x3)['before'], x3['sha256'] not in (x1['sha256'], x2['sha256']), t['book_changed'][1]['result']['event']['checks'], t['book_changed'][1]['result']['event']['why']),
                         (1, [], True, x2['sha256'], 'the letter says an overdue amount of 240; the loan book says 180'))
        a = t['after_book_changed']
        self.assertEqual((a['letter_queued']['truth'], a['providers'], a['budget'], list(a['open_handoffs'].values())[0]['receipt'], list(a['open_handoffs'].values())[0]['failed'], t['head']['length']),
                         ('UNKNOWN', {'local-provider': 3, 'letter-model': 0}, {'compute': 3, 'money': 5, 'attention': 3}, x3['sha256'], None, 12))

    def test_letter_a_hand_that_is_spent_and_the_next_hand(self):
        p = self.q['spent']; w = p['wrong_letters']; self.assertEqual(self.step(p['handed_over']), [(3, 'loan_on_book', 'TRUE', HANDS)])
        self.assertEqual([(x['wrote'], self.step(x['check'])) for x in w], [(2400, [(4, 'letter_drafted', 'FALSE', HANDS)]), (24, [(5, 'letter_drafted', 'FALSE', HANDS)]), (204, [(6, 'letter_drafted', 'FALSE', NO_SLOT)])])
        self.assertEqual([(x['after']['providers']['letter-model'], x['after']['budget']['compute']) for x in w], [(1, 6), (0, 4), (0, 4)])
        out_of = list(w[2]['after']['open_handoffs'].values())[0]
        self.assertEqual((out_of['issued']['handoff']['try'], out_of['failed']['why']), (3, 'the letter says an overdue amount of 204; the loan book says 240'))
        self.assertEqual((st(p['dry_look']['result']), p['next_hand'], st(p['officer']['result'])), (NO_SLOT, '214_hand_to_officer', [('WAITING', [OFFICER_M], [QUEUE], [OFFICER_M], [])]))
        x4 = issued(p['officer']['result'])
        self.assertEqual((told(x4)['to'], told(x4)['try'], [(b['try'], b['to'], b['checked']['why']) for b in told(x4)['before']]),
                         (OFFICER, 4, [(1, HAND, WRONG), (2, HAND, 'the letter says an overdue amount of 24; the loan book says 240'), (3, HAND, 'the letter says an overdue amount of 204; the loan book says 240')]))
        self.assertEqual((p['officer_wrote'], self.step(p['passing_check'])[0][2:], [(c['tries'], c['receipt'], c['confirmed']) for c in closed(p['passing_check'][-1]['result'])]),
                         (240, ('TRUE', [(DONE, [QUEUE], None, None, [])]), [(4, x4['sha256'], True)]))
        self.assertEqual((p['after']['budget'], p['after']['providers'], p['after']['open_handoffs']), ({'compute': 3, 'money': 5, 'attention': 2}, {'local-provider': 3, 'letter-model': 0, 'collections-officer': 0}, {}))

    def test_every_run_names_the_packs_it_stood_on(self):
        for name, body in self.e.items():
            for r in self.runs(body): self.assertEqual([x['pack'] for x in r['provenance']], body['packs'], name)
        t, p = self.q['tries'], self.q['spent']
        for r in self.runs(t): self.assertEqual([x['pack'] for x in r['provenance']], t['packs'])
        late = self.runs({k: p[k] for k in ('officer', 'passing_check')})
        for r in self.runs(p): self.assertEqual([x['pack'] for x in r['provenance']], p['packs'] + ([p['next_hand']] if r in late else []))

    def runs(self, v):
        out = []
        def walk(x):
            if type(x) is dict:
                if 'trace' in x and 'trace_root_sha256' in x: out.append(x)
                for y in x.values(): walk(y)
            elif type(x) is list:
                for y in x: walk(y)
        walk(v); return out


class CheckTests(unittest.TestCase):
    """The independent checks of this version, run as the verifier runs a check module: in a process of its own, on the record handed in."""
    S140, S141 = 'S140_the_record_of_a_hand_off_holds_what_the_version_claims', 'S141_each_test_of_the_hand_off_refuses_a_forgery_of_its_own'

    @classmethod
    def setUpClass(cls):
        spec = importlib.util.spec_from_file_location('independent_verify_for_handoff', ROOT / 'qa' / 'independent_verify.py')
        cls.v = importlib.util.module_from_spec(spec); spec.loader.exec_module(cls.v)
        cls.data = json.loads((ROOT / 'results' / 'actual_run_records.json').read_text(encoding='utf-8'))
        cls.module = ROOT / 'qa' / 'checks' / 'handoff.py'

    def rows(self, data):
        got, why = self.v.module_rows(self.module, data, ROOT, set())
        self.assertIsNone(why); return {cid: (ok, detail) for cid, ok, detail in got}

    def forged(self, change):
        d = json.loads(json.dumps(self.data)); change(d)
        d['added']['scenes']['handoff_letter'] = self.v.sha(d['scenes']['handoff_letter'])   # the seal is a checksum in the same record: whoever changes the sequence makes it again
        return d

    def retold(self, r, change):   # what a forger can do without any secret: change a run and hash its chain again
        change(r); prev = 'GENESIS'
        for n, e in enumerate(r['trace']):
            e.update(seq=n + 1, prev_sha256=prev); e['sha256'] = prev = self.v.sha({k: v for k, v in e.items() if k != 'sha256'})
        r['trace_root_sha256'] = prev

    def test_s140_and_s141_hold_on_the_built_record(self):
        self.assertEqual(self.rows(self.data), {self.S140: (True, ''), self.S141: (True, '')})
        self.assertIsNone(self.v.guard(self.module.read_text(encoding='utf-8')))   # the module passes the parser guard: it imports json and nothing of the lab
        ns = {'__name__': 'qa_checks_handoff_read'}; exec(compile(self.module.read_text(encoding='utf-8'), str(self.module), 'exec'), ns)   # read here only to count what it lists
        listed = [target for target, _ in ns['FORGERIES']]
        self.assertEqual((len(ns['NAMES']), len(listed), sorted(set(listed)) == sorted(ns['NAMES']), min(listed.count(n) for n in ns['NAMES'])), (16, 48, True, 2))

    def test_a_record_retold_on_the_hands_word_passes_the_checks_the_lab_had_and_s140_refuses_it(self):
        def on_the_hands_word(d):   # the officer's passing check re-told as the hand's own row; the closing line made to match, the chain hashed again, the sequence sealed again
            look = d['scenes']['handoff_letter']['spent']['passing_check'][0]['result']; look['event']['source'] = OFFICER
            self.retold(look['runs'][0], lambda r: [e['data'] for e in r['trace'] if e['operation'] == 'HANDOFF_CLOSED'][0].update(source=OFFICER, confirmed=False))
        d = self.forged(on_the_hands_word)
        got = self.rows(d)
        self.assertEqual((got[self.S140], got[self.S141][0]), ((False, 'needs'), False))   # the letter was queued in a look that did not take the checker's TRUE on the try that was out
        v = self.v; kept = v.delivered_rows; v.delivered_rows = lambda data, root: []   # the checks the lab had before any version's own: the built-in ones and those of the add-on points
        try:
            failing = sorted(t['id'] for t in v.inspect(d)['checks'] if not t['pass'])
            honest = sorted(t['id'] for t in v.inspect(self.data)['checks'] if not t['pass'])
        finally: v.delivered_rows = kept
        # Every run of the forged record is whole and its sequence is sealed again: none of those checks refuses it. S202 is left out: once a later version
        # has pinned this sequence it refuses any change of it, by sha256, whatever the change says.
        self.assertEqual((self.read_here(failing), honest), ([], []))
        self.assertEqual(self.read_here(['S202_x', 'S59_x', 'S60_x', 'S140_x', 'S141_x', 'S142_x', 'S200_x', 'S219_x', 'S220_x', 'qa/checks/x.py']), ['S59_x', 'S140_x', 'S141_x', 'S200_x', 'S219_x'])

    def read_here(self, ids):
        """Of what the whole verifier fails on a forged record, a test of this version reads the checks the lab had before any version (numbers below 60) and those of
        the add-on base (200 to 219, without 202: S202 pins every earlier record by sha256, and once a later version has pinned this version's sequences it refuses any
        change of them, whatever the change says), and this version's own two. A check of a version that is laid on top of this one is not this test's to read."""
        number = lambda cid: int(cid[1:].split('_')[0]) if cid[:1] == 'S' and cid[1:].split('_')[0].isdigit() else None
        return [cid for cid in ids if number(cid) is not None and (number(cid) < 60 or (200 <= number(cid) <= 219 and number(cid) != 202) or number(cid) in (140, 141))]


class ClauseTests(unittest.TestCase):
    """The check module's own functions, called in this process on forged records (CheckTests run the module as the verifier does, in a process of its own).
    The first review round changed the module one clause at a time and found changes that every test let pass. Here one forged record stands for one such clause: it
    changes what that clause reads, and the test asserts WHICH of the sixteen tests of S140 refuse it, word for word as S140 lists them in its detail. An empty answer
    pins what S140 does NOT read (limit L13). S141's forgeries live in the check module and are not added to: these records are the unit tests' own."""
    @classmethod
    def setUpClass(cls):
        spec = importlib.util.spec_from_file_location('independent_verify_for_handoff_clauses', ROOT / 'qa' / 'independent_verify.py')
        cls.v = importlib.util.module_from_spec(spec); spec.loader.exec_module(cls.v)
        cls.text = (ROOT / 'qa' / 'checks' / 'handoff.py').read_text(encoding='utf-8')
        cls.ns = cls.module(cls.text)
        cls.data = json.loads((ROOT / 'results' / 'actual_run_records.json').read_text(encoding='utf-8'))
        cls.packs = {f.stem: json.loads(f.read_text(encoding='utf-8')) for f in sorted((ROOT / 'scenarios').glob('21*.json'))}

    @staticmethod
    def module(text):
        ns = {'__name__': 'qa_checks_handoff_clauses'}; exec(compile(text, 'qa/checks/handoff.py', 'exec'), ns); return ns

    def refused(self, change):
        """The tests of S140 that refuse one forged record. `change` is handed what the module's tests read of the record (the four cases and the two sequences)
        and the pack files, as the module's own forgeries are."""
        ns = self.ns
        m = json.loads(json.dumps({'cases': [c for c in self.data['cases'] if c['id'] in ns['CASES']], 'scenes': {n: self.data['scenes'][n] for n in (ns['LETTER'], ns['OLD'])}}))
        p = json.loads(json.dumps(self.packs)); change(m, p)
        return ' '.join(sorted(name for name, ok in ns['tests'](m, p, self.v.sha, self.v.check_chain).items() if not ok))

    def test_the_record_as_built_is_refused_by_none_of_the_sixteen(self):
        self.assertEqual((self.refused(lambda m, p: None), len(self.ns['NAMES'])), ('', 16))

    def test_one_forged_record_for_one_clause_is_refused_by_the_tests_named(self):
        ns, sha = self.ns, self.v.sha
        T, P, O, C, run, retold, line, KIND = ns['T'], ns['P'], ns['O'], ns['C'], ns['run_of'], ns['retold'], ns['line_of'], ns['KIND']   # the module's own readers of the record
        receipt = lambda step: run(step)['model_receipts'][0]
        event = lambda step: step['result']['event']
        copy = lambda x: json.loads(json.dumps(x))
        book = lambda m: copy(event(P(m)['handed_over'][0]))   # the book's row as the walk `spent` let it in
        passing = lambda m: T(m)['passing_check'][0]
        snaps = lambda part, keys, change: [change(part[k]) for k in keys]
        def moved(r, name, to):   # one line of a run's chain moved to another place, the chain hashed again
            def change(x):
                at = [e['operation'] for e in x['trace']].index(name); row = x['trace'].pop(at); x['trace'].insert(to if to >= 0 else len(x['trace']) + 1 + to, row)
            retold(r, sha, change)
        def twice(r, name):   # one line of a run's chain written twice, the chain hashed again
            def change(x):
                at = [e['operation'] for e in x['trace']].index(name); x['trace'].insert(at, copy(x['trace'][at]))
            retold(r, sha, change)
        doer, asked, yes, rows, none, three = (lambda m: O(m, 'doer_asked')), (lambda m: O(m, 'checker_asked')), (lambda m: O(m, 'checker_stamps_yes')), (lambda m: O(m, 'checker_rows')), (lambda m: O(m, 'no_step')), (lambda m: O(m, 'three_asks'))
        first = lambda part, look='look': part[look]['runs'][0]
        def short(m, p):   # the walk `tries` without its last two entries (the book that changed), the head and the last books re-told to fit
            t = T(m); t.pop('book_changed'); t['head'].update(length=10); t['after_book_changed'].update(providers=copy(t['after_passing_check']['providers']), budget=copy(t['after_passing_check']['budget']))
        table = [
            # ---- the rule for a check (is_check), what a later try is told (told) and the walk (follow)
            ('closes needs', 'a decision under the checker\'s name taken as the check', lambda m, p: event(passing(m)).update(final=True)),
            ('closes needs', 'the passing row comes from the hand', lambda m, p: event(passing(m)).update(source=HAND)),
            ('closes needs receipts', 'the hand-over that was out names another fact than the row is on', lambda m, p: receipt(P(m)['officer'])[KIND].update(predicate='letter_signed')),
            ('bound tries waits', 'the book moved while a failed check stood: that check no longer reads', lambda m, p: P(m)['dry_look']['result'].update(event=dict(book(m), version='book-moved'))),
            ('', 'the same book row let in again while a failed check stood: the check still reads', lambda m, p: P(m)['dry_look']['result'].update(event=book(m))),
            ('', 'a row on another fact, at another version, while a failed check stood: the check still reads', lambda m, p: P(m)['dry_look']['result'].update(event=dict(book(m), predicate='notice_ready', version='book-moved'))),
            ('', 'a failed check that gives a list of reasons, and a next try that is told none (L8)', lambda m, p: (event(T(m)['failed_check'][0]).update(why=['a', 'b']), receipt(T(m)['failed_check'][0])[KIND]['before'][0]['checked'].pop('why'))),
            ('', 'a failed check that gives no reason, and a next try that is told none (L8)', lambda m, p: (event(T(m)['failed_check'][0]).pop('why'), receipt(T(m)['failed_check'][0])[KIND]['before'][0]['checked'].pop('why'))),
            ('', 'a failed check whose version is a number, and a next try that is told that number', lambda m, p: (event(T(m)['failed_check'][0]).update(version=7), receipt(T(m)['failed_check'][0])[KIND]['before'][0]['checked'].update(version=7))),
            ('', 'a row of the checker that names the try that is out and reads UNKNOWN: no check, and the look waits', lambda m, p: event(T(m)['late_copy'][0]).update(truth='UNKNOWN', checks=receipt(T(m)['failed_check'][0])['sha256'])),
            ('', 'a failed check that rests on nothing, and the book moved after it: the check still reads', lambda m, p: (event(P(m)['wrong_letters'][2]['check'][0]).pop('depends_on'), P(m)['dry_look']['result'].update(event=dict(book(m), version='book-moved')))),
            ('bound tries waits', 'a failed check that rests on two rows, one of which moved: that check no longer reads', lambda m, p: (event(P(m)['wrong_letters'][2]['check'][0])['depends_on'].append({'predicate': 'notice_ready', 'version': '1'}), P(m)['dry_look']['result'].update(event=dict(book(m), version='book-moved')))),
            # ---- receipts
            ('receipts', 'a key more on a receipt', lambda m, p: receipt(P(m)['officer']).update(note='x')),
            ('receipts', 'a receipt with another status', lambda m, p: receipt(P(m)['officer']).update(status='DONE')),
            ('receipts', 'a key more in what was handed over', lambda m, p: receipt(P(m)['officer'])[KIND].update(note='x')),
            ('receipts', 'handed to another hand than the method names', lambda m, p: receipt(P(m)['officer'])[KIND].update(to=HAND)),
            ('cases receipts', 'the hand and the checker under one name, in the pack file and in both receipts of that method', lambda m, p: (receipt(P(m)['officer'])[KIND].update(to=CHECKER), first(C(m, '87_next_hand'), 'run')['model_receipts'][0][KIND].update(to=CHECKER), p['214_hand_to_officer']['methods'][0].update(handoff_to=CHECKER))),
            ('receipts', 'a short text where the digest of the State stands', lambda m, p: receipt(P(m)['officer'])[KIND].update(handed_in='short')),
            ('receipts tries', 'a list of 64 items where the digest of the State stands', lambda m, p: receipt(P(m)['officer'])[KIND].update(handed_in=['a'] * 64)),
            ('receipts', 'the method of a hand-over is of another kind in its pack file', lambda m, p: p['214_hand_to_officer']['methods'][0].update(action='simulate_fact')),
            # ---- tries
            ('tries', 'the number of a first try is true, not 1', lambda m, p: receipt(T(m)['book_changed'][0])[KIND].update({'try': True})),
            ('tries', 'a first hand-over is numbered 0', lambda m, p: receipt(T(m)['book_changed'][0])[KIND].update({'try': 0})),
            ('chains tries waits', 'a walk that ends before its third hand-over, its head and its last books made to match', short),
            ('tries', 'a next try after a check that passed, and told so', lambda m, p: (event(T(m)['failed_check'][0]).update(truth='TRUE'), receipt(T(m)['failed_check'][0])[KIND]['before'][0]['checked'].update(truth='TRUE'))),
            ('tries', 'two hand-overs of one walk bound to the same State', lambda m, p: receipt(T(m)['book_changed'][0])[KIND].update(handed_in=receipt(T(m)['handed_over'][0])[KIND]['handed_in'])),
            ('closes tries', 'the number of a second try is 2.0', lambda m, p: receipt(T(m)['failed_check'][0])[KIND].update({'try': 2.0})),
            # ---- closes
            ('closes', 'the closing line names another hand-off', lambda m, p: retold(run(passing(m)), sha, lambda r: line(r).update(handoff='lendco/other|letter_drafted'))),
            ('closes', 'the closing line says another truth than the row', lambda m, p: retold(run(passing(m)), sha, lambda r: line(r).update(truth='FALSE'))),
            ('closes', 'the closing line names another version than the row', lambda m, p: retold(run(passing(m)), sha, lambda r: line(r).update(version='other'))),
            ('closes', 'the closing line names another receipt as checked than the row', lambda m, p: retold(run(passing(m)), sha, lambda r: line(r).update(checks=None))),
            ('closes needs', 'confirmed said of the checker\'s FALSE on the try that was out', lambda m, p: (event(passing(m)).update(truth='FALSE'), retold(run(passing(m)), sha, lambda r: line(r).update(truth='FALSE')))),
            ('closes', 'the closing line before the rows of the plan', lambda m, p: moved(run(passing(m)), 'HANDOFF_CLOSED', 0)),
            ('closes', 'the closing line after the last row', lambda m, p: moved(run(passing(m)), 'HANDOFF_CLOSED', -1)),
            ('closes needs', 'the closing line twice in one run', lambda m, p: twice(run(passing(m)), 'HANDOFF_CLOSED')),
            # ---- needs
            ('needs', 'the look that queued the letter is said to be a plan only', lambda m, p: run(passing(m)).update(status='PLAN_READY')),
            ('bound needs', 'the officer\'s letter passed and nothing was queued in that look', lambda m, p: run(P(m)['passing_check'][0]).update(model_receipts=[])),
            ('', 'a hand-off method whose own prerequisite is made by a step that is no hand-off: only a step that needs handed-over work is held to the checker\'s TRUE', lambda m, p: p['214_hand_to_officer']['methods'][0].update(requires=['letter_queued'])),
            ('', 'the asks of the attempt lead to another fact: the hand-off methods alone say which work is handed over', lambda m, p: [p[n]['methods'][0].update(effect='letter_signed') for n in ('215_ask_the_drafter', '216_ask_the_checker')]),
            # ---- waits
            ('waits', 'a look that waits lists an action', lambda m, p: run(T(m)['second_look']).update(actions=['x'])),
            ('waits', 'a look that waits is said to be ready', lambda m, p: run(T(m)['second_look']).update(work_state='ready')),
            ('waits', 'a look that waits is said to be a plan', lambda m, p: run(T(m)['second_look']).update(status='PLAN_READY')),
            ('waits', 'a look that hands the work over again is said to be a plan', lambda m, p: run(T(m)['failed_check'][0]).update(status='PLAN_READY')),
            ('waits', 'a look that hands the work over again waits on nothing', lambda m, p: run(T(m)['failed_check'][0]).update(waits=[])),
            ('waits', 'a look that the gate turned down is said to wait', lambda m, p: run(P(m)['dry_look']).update(work_state='waiting')),
            ('waits', 'a look turned down for want of a method, not by the gate', lambda m, p: run(P(m)['dry_look']).update(status='METHOD_ABSENT')),
            ('waits', 'a look that the gate turned down lists an action', lambda m, p: run(P(m)['dry_look']).update(actions=['x'])),
            ('chains waits', 'a look that waited is left out of the walk', lambda m, p: T(m).pop('second_look')),
            ('bound needs waits', 'a look that hands the work over again holds a second receipt', lambda m, p: run(T(m)['failed_check'][0])['model_receipts'].append(copy(run(passing(m))['model_receipts'][0]))),
            ('bound needs waits', 'a look that the gate turned down holds a receipt', lambda m, p: run(P(m)['dry_look'])['model_receipts'].append(copy(run(P(m)['passing_check'][0])['model_receipts'][0]))),
            # ---- bound
            ('bound', 'more hand-overs than the packs of the walk give slots, and the last books made to match', lambda m, p: (T(m)['packs'].append('213_model_spent'), T(m)['after_book_changed']['providers'].update({'letter-model': -3}))),
            ('bound waits', 'turned down for the provider while slots are left and no check failed', lambda m, p: run(T(m)['second_look']).update(status='PROVIDER_REQUIRED')),
            ('bound waits', 'turned down for the provider at the second try, with a slot left', lambda m, p: run(P(m)['wrong_letters'][0]['check'][0]).update(status='PROVIDER_REQUIRED')),
            ('bound tries', 'turned down for the provider after a check that passed', lambda m, p: event(P(m)['wrong_letters'][2]['check'][0]).update(truth='TRUE')),
            ('bound', 'no look of either walk is turned down for the provider', lambda m, p: (run(P(m)['wrong_letters'][2]['check'][0]).update(status='RESOURCE_REQUIRED'), run(P(m)['dry_look']).update(status='RESOURCE_REQUIRED'))),
            ('', 'a walk that loaded a second hand and never used it: its slot is still there at the end', lambda m, p: (T(m)['packs'].append('214_hand_to_officer'), T(m)['after_book_changed']['providers'].update({'collections-officer': 1}))),
            ('', 'the desk\'s pack states no budget and the last books are made to match: a State starts with ten tokens, ten of money and three of attention', lambda m, p: (p['210_letters_desk'].pop('budget'), T(m)['after_book_changed']['budget'].update(money=10), P(m)['after']['budget'].update(money=10))),
            # ---- door
            ('door', 'the second look changed the books', lambda m, p: T(m)['after_second_look']['budget'].update(compute=0)),
            ('door', 'the journal\'s head is longer than its entries', lambda m, p: T(m)['head'].update(length=99)),
            ('door', 'a look that is no entry of the journal', lambda m, p: T(m).update(stray={'runs': []})),
            ('door', 'an entry numbered 5.0', lambda m, p: T(m)['second_look'].update(entry=5.0)),
            ('chains door waits', 'two runs in one entry', lambda m, p: P(m)['dry_look']['result']['runs'].append(copy(run(P(m)['dry_look'])))),
            ('door', 'the restart gave a notice', lambda m, p: T(m)['restarted'].update(notice=['cut'])),
            ('door', 'the restart found other books', lambda m, p: T(m)['restarted']['after']['budget'].update(compute=0)),
            ('door', 'the kept head is shorter than the head the restart found', lambda m, p: T(m)['head_kept'].update(length=3)),
            ('door', 'the header names one kind', lambda m, p: T(m).update(kinds=['simulate_fact'])),
            ('door', 'the checker\'s stamp is said to be let in', lambda m, p: T(m)['at_the_door'].update(a_stamp_from_the_checker=None)),
            ('door', 'a decision is said to be let in', lambda m, p: T(m)['at_the_door'].update(a_decision_under_the_checkers_name=None)),
            ('door', 'what the door refused is not in the record: a test that cannot read what it needs does not hold', lambda m, p: T(m).pop('at_the_door')),
            # ---- cases
            ('cases', 'case 85 is said to be blocked for want of a method', lambda m, p: first(C(m, '85_no_step'), 'run').update(status='METHOD_ABSENT')),
            ('cases', 'case 85 holds a hand-over', lambda m, p: first(C(m, '85_no_step'), 'run')['model_receipts'].append(copy(first(C(m, '84_handed_over'), 'run')['model_receipts'][0]))),
            ('cases', 'case 86 holds a hand-over', lambda m, p: first(C(m, '86_no_slot_left'), 'run')['model_receipts'].append(copy(first(C(m, '84_handed_over'), 'run')['model_receipts'][0]))),
            ('cases', 'case 85 holds the receipt of an ordinary step', lambda m, p: first(C(m, '85_no_step'), 'run')['model_receipts'].append(copy(run(passing(m))['model_receipts'][0]))),
            ('cases', 'case 84 has nothing pending', lambda m, p: first(C(m, '84_handed_over'), 'run').update(pending=[])),
            ('cases', 'case 87 has nothing pending', lambda m, p: first(C(m, '87_next_hand'), 'run').update(pending=[])),
            ('cases receipts', 'case 84 hands the letter to the officer', lambda m, p: first(C(m, '84_handed_over'), 'run')['model_receipts'][0][KIND].update(to=OFFICER)),
            ('cases', 'case 85 paid a token', lambda m, p: C(m, '85_no_step')['derived_state']['budget_after'].update(compute=9)),
            ('cases', 'case 87 holds a row on the letter', lambda m, p: C(m, '87_next_hand')['derived_state']['facts'].update({KEY: {'truth': 'TRUE'}})),
            # ---- chains
            ('chains old_no_step old_parts', 'a run of the attempt is left out', lambda m, p: none(m).pop('failed_check')),
            # ---- old_doer (T1)
            ('old_doer', 'the ask is put to the checker', lambda m, p: first(doer(m))['model_receipts'][-1]['ask'].update(to=CHECKER)),
            ('old_doer', 'the first look is a plan', lambda m, p: first(doer(m)).update(status='PLAN_READY')),
            ('old_doer', 'the doer said no', lambda m, p: doer(m)['doer_says_done']['event'].update(truth='FALSE')),
            ('old_doer', 'the doer\'s answer is no decision', lambda m, p: doer(m)['doer_says_done']['event'].update(final=False)),
            ('old_doer', 'the answer is stamped by the checker', lambda m, p: doer(m)['doer_says_done']['event'].update(source='STAMP:' + CHECKER)),
            ('old_doer', 'the letter is not queued on the doer\'s word', lambda m, p: first(doer(m), 'doer_says_done').update(status='WAITING')),
            ('old_doer', 'the letter is not queued at the end', lambda m, p: snaps(doer(m), ('after', 'after_done'), lambda s: s['letter_queued'].update(truth='UNKNOWN'))),
            ('old_doer', 'the checker\'s FALSE changed the books', lambda m, p: doer(m)['after']['budget'].update(compute=0)),
            ('', 'the look that turned the checker\'s FALSE away is said to have touched the goal: of that look S140 reads its status and that it started no run', lambda m, p: doer(m)['checker_says_no'].update(affected=['letter_queued'])),
            # ---- old_checker_no (T2)
            ('old_checker_no', 'the ask is put to the doer', lambda m, p: first(asked(m))['model_receipts'][-1]['ask'].update(to=HAND)),
            ('old_checker_no', 'the doer\'s answer is taken', lambda m, p: asked(m)['doer_says_done'].update(refused=None)),
            ('old_checker_no', 'the no does not refuse the goal', lambda m, p: first(asked(m), 'checker_says_no').update(status='WAITING')),
            ('old_checker_no', 'the row on the second draft is let in', lambda m, p: asked(m)['second_draft_row'].update(status='RECONCILED')),
            ('old_checker_no', 'the letter reads TRUE at the end', lambda m, p: asked(m)['after']['letter_drafted'].update(truth='TRUE')),
            ('old_checker_no', 'no try was paid', lambda m, p: asked(m)['after']['budget'].update(attention=3)),
            ('old_checker_no', 'no slot was taken', lambda m, p: asked(m)['after']['providers'].update({'checker-channel': 3})),
            # ---- old_stamped_yes (T3)
            ('old_stamped_yes', 'the stamped yes rests on the book', lambda m, p: yes(m)['checker_says_yes']['event'].update(depends_on=ON_BOOK)),
            ('old_stamped_yes', 'the yes is no decision', lambda m, p: yes(m)['checker_says_yes']['event'].update(final=False)),
            ('old_stamped_yes', 'the yes does not queue the letter', lambda m, p: first(yes(m), 'checker_says_yes').update(status='WAITING')),
            ('old_stamped_yes', 'another fact changed, not the book', lambda m, p: yes(m)['book_changes']['event'].update(predicate='notice_ready')),
            ('old_stamped_yes', 'the changed book re-opened the goal', lambda m, p: first(yes(m), 'book_changes').update(status='WAITING', work_state='waiting')),
            ('old_stamped_yes', 'the letter stands on a row of the checker, in every snapshot', lambda m, p: snaps(yes(m), ('after', 'after_yes', 'after_book'), lambda s: s['letter_drafted'].update(source=CHECKER))),
            ('old_stamped_yes', 'the letter is not queued, in every snapshot', lambda m, p: snaps(yes(m), ('after', 'after_yes', 'after_book'), lambda s: s['letter_queued'].update(truth='UNKNOWN'))),
            ('old_stamped_yes', 'the FALSE that was turned away changed the books', lambda m, p: yes(m)['after']['budget'].update(compute=0)),
            ('old_stamped_yes', 'the changed book changed the books', lambda m, p: yes(m)['after_book']['budget'].update(compute=0)),
            ('', 'the changed book of T3 carries the version it had: of that row S140 reads the fact it is on', lambda m, p: yes(m)['book_changes']['event'].update(version='book-fixture')),
            # ---- old_rows (T4)
            ('chains old_parts old_rows', 'two failed checks, not three', lambda m, p: rows(m)['failed_checks'].pop()),
            ('old_rows', 'a failed check made a plan', lambda m, p: first(rows(m)['failed_checks'][0], 'check').update(status='PLAN_READY')),
            ('old_rows', 'a failed check that reads TRUE', lambda m, p: rows(m)['failed_checks'][1]['check']['event'].update(truth='TRUE')),
            ('old_rows', 'a failed check that is a decision', lambda m, p: rows(m)['failed_checks'][1]['check']['event'].update(final=True)),
            ('old_rows', 'a failed check after which the look waits on another question', lambda m, p: first(rows(m)['failed_checks'][2], 'check').update(waits=[ASK_DOER])),
            ('old_rows', 'a failed check whose run was paid', lambda m, p: first(rows(m)['failed_checks'][2], 'check')['cost'].update(attention=1)),
            ('old_rows', 'a failed check that took a slot', lambda m, p: rows(m)['failed_checks'][0]['after']['providers'].update({'checker-channel': 1})),
            ('old_rows', 'a failed check that closed the question', lambda m, p: rows(m)['failed_checks'][0]['after']['open_asks'].clear()),
            ('old_rows', 'the passing row does not queue the letter', lambda m, p: first(rows(m), 'passing_check').update(status='WAITING')),
            ('old_rows', 'the letter stands on a stamp', lambda m, p: rows(m)['after']['letter_drafted'].update(source='STAMP:' + CHECKER)),
            ('old_rows', 'another question is out at the end', lambda m, p: [x.update(receipt='0' * 64) for x in rows(m)['after']['open_asks'].values()]),
            ('old_rows', 'two questions are out all along', lambda m, p: [s['open_asks'].update(other={'receipt': '0' * 64}) for s in [rows(m)['after_look'], rows(m)['after']] + [f['after'] for f in rows(m)['failed_checks']]]),
            ('', 'a failed check of T4 is said to come from the hand: of the rows of the attempt S140 reads their truth and that they are no decisions', lambda m, p: rows(m)['failed_checks'][1]['check']['event'].update(source=HAND)),
            # ---- old_no_step (T5)
            ('old_no_step old_parts', 'a pack of the walk holds a step that leads to the letter', lambda m, p: none(m)['packs'].append('216_ask_the_checker')),
            ('old_no_step', 'the failed check leaves the look blocked for want of evidence', lambda m, p: first(none(m), 'failed_check').update(status='QUERY_EVIDENCE')),
            ('old_no_step', 'with no step, the passing row does not queue the letter', lambda m, p: first(none(m), 'passing_check').update(status='WAITING')),
            ('old_no_step', 'nothing was paid at the end', lambda m, p: none(m)['after']['budget'].update(compute=10)),
            ('old_no_step', 'a question is out at the end', lambda m, p: none(m)['after']['open_asks'].update(other={})),
            # ---- old_three_asks (T6)
            ('old_three_asks', 'a later ask asks other words than its pack', lambda m, p: first(three(m), 'no_to_try_2')['model_receipts'][-1]['ask'].update(question='Try 3: is it right now?')),
            ('old_three_asks', 'a later ask is put to the hand', lambda m, p: first(three(m), 'no_to_try_2')['model_receipts'][-1]['ask'].update(to=HAND)),
            ('old_three_asks', 'the third no leaves the goal waiting', lambda m, p: first(three(m), 'no_to_try_3').update(status='WAITING')),
            ('old_three_asks', 'the second no asks the second try again', lambda m, p: (lambda a, b: (b.update(method=a['method']), b['ask'].update(question=a['ask']['question'])))(first(three(m), 'no_to_try_1')['model_receipts'][-1], first(three(m), 'no_to_try_2')['model_receipts'][-1])),
            ('old_three_asks', 'the step stopped for another reason', lambda m, p: first(three(m)['yes'], 'yes_to_try_2')['stopped'].update(reason='Handler failed: KeyError')),
            ('old_three_asks', 'the yes reads FALSE', lambda m, p: three(m)['yes']['draft_2_passes'].update(truth='FALSE')),
            ('old_three_asks', 'the yes to the second try is no decision', lambda m, p: three(m)['yes']['draft_2_passes'].update(final=None)),
            ('old_three_asks', 'the letter is queued after the yes', lambda m, p: three(m)['yes']['after']['letter_queued'].update(truth='TRUE')),
            ('', 'the first no of T6 is said to be a row of the checker and no stamp: of the three answers S140 reads what their looks did', lambda m, p: three(m)['no_to_try_1']['event'].update(final=False, source=CHECKER)),
            # ---- old_parts
            ('old_parts', 'a line of the kind stands in a run of the attempt', lambda m, p: retold(first(none(m)), sha, lambda r: r['trace'].insert(1, dict(copy(r['trace'][0]), operation='HANDOFF_CLOSED')))),
            ('old_parts', 'a line named HANDOFF stands in a run of the attempt', lambda m, p: retold(first(none(m)), sha, lambda r: r['trace'].insert(1, dict(copy(r['trace'][0]), operation='HANDOFF')))),
            ('old_parts', 'a walk of the attempt names a pack more than its runs stood on', lambda m, p: doer(m)['packs'].append('213_model_spent')),
        ]
        self.assertEqual((len({name for _, name, _ in table}), len(table), len([name for want, name, _ in table if want == ''])), (134, 134, 15))   # the numbers the passage gives
        for want, name, change in table:
            self.assertEqual(self.refused(change), want, name)

    def test_s141_fails_when_a_listed_forgery_is_not_refused_by_its_test_or_a_test_has_no_forgery_of_its_own(self):
        """S141's two sentences, held on copies of the module in which the list of forgeries is changed (the list in the file is as it was: FORGERIES is the module's own code)."""
        S140, S141 = self.ns['IDS']; v = self.v
        def rows_with(change):
            ns = self.module(self.text); change(ns['FORGERIES'], ns); return ns['checks'](self.data, ROOT, v.sha, v.check_chain)
        self.assertEqual(rows_with(lambda listed, ns: None), [(S140, True, ''), (S141, True, '')])
        nothing = lambda m, p, sha: None
        self.assertEqual(rows_with(lambda listed, ns: listed.__setitem__(0, ('receipts', nothing))),   # the first listed forgery changes nothing: no test refuses it
                         [(S140, True, ''), (S141, False, "{'not refused by its own test': {0: []}, 'tests without a forgery of their own': []}")])
        self.assertEqual(rows_with(lambda listed, ns: listed.__setitem__(0, ('receipts', lambda m, p, sha: 1 // 0))),   # a forgery that cannot be made counts as not refused
                         [(S140, True, ''), (S141, False, "{'not refused by its own test': {0: None}, 'tests without a forgery of their own': []}")])
        self.assertEqual(rows_with(lambda listed, ns: listed.__setitem__(0, ('receipts', lambda m, p, sha: ns['T'](m)['head'].update(length=99)))),   # refused, but by another test than the one it is listed for
                         [(S140, True, ''), (S141, False, "{'not refused by its own test': {0: ['door']}, 'tests without a forgery of their own': []}")])
        def no_lone(listed, ns):   # every forgery listed for `chains` replaced by one that `chains` refuses together with another test
            listed[:] = [x for x in listed if x[0] != 'chains'] + [('chains', lambda m, p, sha: ns['T'](m).pop('second_look'))]
        self.assertEqual(rows_with(no_lone), [(S140, True, ''), (S141, False, "{'not refused by its own test': {}, 'tests without a forgery of their own': ['chains']}")])
        self.assertEqual(rows_with(lambda listed, ns: listed.__setitem__(slice(None), [x for x in listed if x[0] != 'chains']))[1][1:],   # no forgery listed for `chains` at all
                         (False, "{'not refused by its own test': {}, 'tests without a forgery of their own': ['chains']}"))

    def test_a_record_that_cannot_be_read_fails_both_checks_and_a_test_that_raises_does_not_hold(self):
        S140, S141 = self.ns['IDS']; v = self.v; checks = lambda d: self.ns['checks'](d, ROOT, v.sha, v.check_chain)
        cannot = 'the cases, the two sequences or the pack files of the hand-off cannot be read: '
        d = json.loads(json.dumps(self.data)); del d['scenes']['handoff_existing']   # a sequence is missing from the record
        self.assertEqual(checks(d), [(S140, False, cannot + 'KeyError'), (S141, False, cannot + 'KeyError')])
        d = json.loads(json.dumps(self.data)); d['scenes']['handoff_letter']['tries']['second_look']['result']['runs'] = [None]   # a walk that cannot be followed: none of the sixteen holds
        got = checks(d); self.assertEqual((got[0], got[1][1]), ((S140, False, ' '.join(sorted(self.ns['NAMES']))), False))
        d = json.loads(json.dumps(self.data)); del d['scenes']['handoff_letter']['tries']['at_the_door']   # one test cannot read what it needs: that test does not hold, the others do
        got = checks(d); self.assertEqual((got[0], got[1][1]), ((S140, False, 'door'), False))


class LimitTests(unittest.TestCase):
    """What this version does not hold, pinned as it is. Each is a need of its own, owed when a case needs it (ruling R35)."""
    def test_l1_outside_the_journals_door_the_kernel_takes_the_hands_own_row(self):
        s, k, x = handed()   # a State that no journal stands in front of: the kernel's own event door takes any verified row
        out = k.on_event(says('TRUE', 'the-hands-own-word', x['sha256'], source=HAND), execute=True); r = out['runs'][0]
        self.assertEqual((r['status'], r['actions'], said(s), said(s, 'letter_queued')[0]), (DONE, [QUEUE], ('TRUE', HAND, False), 'TRUE'))   # the letter is queued on the hand's word, and the status is the one of a confirmed run
        self.assertEqual(closed(out), [{'handoff': KEY, 'receipt': x['sha256'], 'tries': 1, 'truth': 'TRUE', 'source': HAND, 'version': 'the-hands-own-word', 'checks': x['sha256'], 'confirmed': False}])   # only the line says it

    def test_l2_the_checker_is_a_name(self):
        run = J.start(['simulate_fact', 'handoff'], [CHECKER], name='t-name')
        for n in MODEL: run.add('pack', {'pack': pack(n)})
        e = run.add('look', {'execute': True}); x = issued(run.detail[e['seq']])
        e = run.add('event', {'row': says('TRUE', 'typed-by-hand', x['sha256']), 'execute': True})   # a row typed by hand under the checker's name: no letter and no book were read
        self.assertEqual([(c['confirmed'], c['source']) for c in closed(run.detail[e['seq']])], [(True, CHECKER)])
        alias = dict(pack('211_hand_to_model')['methods'][0], id='hand-letter-alias@t', grant='action:hand-letter-alias@t', verified_by=HAND + ' ')   # the hand under another spelling, as its own checker
        s = State.from_packs([pack('210_letters_desk'), pack('212_book_read'), extra('t-alias', methods=[alias], providers={'letter-model': 1}, grants=['action:hand-letter-alias@t'])])
        self.assertEqual(issued(Kernel(s).run_standing(execute=True))['handoff']['verified_by'], HAND + ' ')   # applied and handed over; nothing names it

    def test_l3_the_tries_belong_to_the_hands_provider_not_to_the_piece_of_work(self):
        reminder = extra('t-reminder', goals=['letter_queued', 'reminder_drafted'], grants=['action:hand-reminder-to-model@t'],
                         methods=[method('hand-reminder-to-model@t', 'reminder_drafted', ['loan_on_book'], provider='letter-model', cost={'compute': 1, 'money': 0, 'attention': 0}, action='handoff',
                                         handoff_to=HAND, instruction='Draft the reminder for loan L-17.', verified_by=CHECKER)])
        s = world(MODEL, reminder); k = Kernel(s); first = k.run_standing(execute=True)
        self.assertEqual([(r['goal'], r['status'], r['actions']) for r in first['runs']], [('letter_queued', 'WAITING', [MODEL_M]), ('reminder_drafted', 'WAITING', ['hand-reminder-to-model@t'])])
        x = first['runs'][0]['model_receipts'][0]; out = fails(k, x, 'letter-1')   # the letter fails once: the last slot of the model goes to its second try
        self.assertEqual((issued(out)['handoff']['try'], s.providers['letter-model']), (2, 0))
        r2 = first['runs'][1]['model_receipts'][0]
        out = k.on_event({'predicate': 'reminder_drafted', 'truth': 'FALSE', 'verified': True, 'source': CHECKER, 'version': 'reminder-1', 'checks': r2['sha256'], 'why': 'the reminder names no loan'}, execute=True)
        self.assertEqual([(r['goal'], r['status'], r['stop_reasons']) for r in out['runs']], [('reminder_drafted', 'PROVIDER_REQUIRED', ['PROVIDER_REQUIRED'])])   # the reminder was tried once and has no second try: the letter used the slot

    def test_l4_a_wait_never_ends_by_itself_and_nothing_counts_the_looks(self):
        s, k, x = handed(); before = held(s)
        for n in range(40): self.assertEqual(st(k.run_standing(execute=True)), WAITS)
        self.assertEqual((held(s), list(open_handoffs(s).values())[0]['receipt'], len(s.event_journal)), (before, x['sha256'], 41))   # a hand that never delivers: forty looks, nothing but journal rows

    def test_l5_a_checker_that_names_no_receipt_can_let_the_plan_go_on_and_can_fail_no_try(self):
        s, k, x = handed()
        for n in range(5): self.assertEqual(st(k.on_event(says('FALSE', f'unnamed-{n}', why=WRONG, depends_on=ON_BOOK), execute=True)), WAITS)   # five failed checks that name no receipt: no try is failed
        self.assertEqual((s.providers['letter-model'], open_handoffs(s)[KEY]['failed']), (2, None))
        out = k.on_event(says('TRUE', 'unnamed-right', depends_on=ON_BOOK), execute=True)   # its TRUE is read by the kernel like any row: the letter is queued, and the line says not confirmed
        self.assertEqual((st(out), closed(out)), ([(DONE, [QUEUE], None, None, [])],
                                                   [{'handoff': KEY, 'receipt': x['sha256'], 'tries': 1, 'truth': 'TRUE', 'source': CHECKER, 'version': 'unnamed-right', 'checks': None, 'confirmed': False}]))
        s, k, x1 = handed(); x2 = issued(fails(k, x1, 'letter-a'))   # the second try is out and the checker's TRUE names the first: the plan goes on, and the line says not confirmed
        out = k.on_event(says('TRUE', 'the-first-letter-after-all', x1['sha256'], depends_on=ON_BOOK), execute=True)
        self.assertEqual((st(out), [(c['receipt'], c['checks'], c['tries'], c['confirmed']) for c in closed(out)]), ([(DONE, [QUEUE], None, None, [])], [(x2['sha256'], x1['sha256'], 2, False)]))

    def test_l6_a_local_way_to_the_same_fact_that_costs_nothing_is_taken_over_the_wait(self):
        s, k, x = handed()
        s.apply(extra('t-local-way', methods=[method('assume-letter-drafted@t', 'letter_drafted', [], cost={'compute': 0, 'money': 0, 'attention': 0})], grants=['action:assume-letter-drafted@t']))
        out = k.run_standing(execute=True)   # which ways lead to a fact is what the packs say: the kernel makes the letter true in its own model
        self.assertEqual((st(out), said(s), [(c['confirmed'], c['source']) for c in closed(out)]),
                         ([(DONE, ['assume-letter-drafted@t', QUEUE], None, None, [])], ('TRUE', 'LOCAL_MODEL:assume-letter-drafted@t', False), [(False, 'LOCAL_MODEL:assume-letter-drafted@t')]))

    def test_l7_a_decision_on_the_fact_ends_the_hand_off_whoever_makes_it(self):
        s, k, x = handed()
        out = k.on_event(dict(says('FALSE', 'owner-says-no', source='owner'), final=True), execute=True)   # a no from any channel: the goal is refused and the hand-over is closed
        self.assertEqual((st(out), [(c['truth'], c['source'], c['confirmed']) for c in closed(out)], open_handoffs(s)), ([('REFUSED', [], None, None, ['REFUSED'])], [('FALSE', 'owner', False)], {}))
        late = passes(k, x)   # the checker's TRUE on the work that was out is turned away
        self.assertEqual((late['status'], said(s)), ('DECISION_STANDS', ('FALSE', 'owner', True)))
        s, k, x = handed()
        out = k.on_event(dict(says('TRUE', 'checker-decides', x['sha256']), final=True), execute=True)   # a decision under the checker's own name that names the receipt: closed, queued, not confirmed
        self.assertEqual((st(out), [(c['truth'], c['source'], c['checks'], c['confirmed']) for c in closed(out)]), ([(DONE, [QUEUE], None, None, [])], [('TRUE', CHECKER, x['sha256'], False)]))

    def test_l8_the_next_try_is_told_one_text_and_nothing_else_of_the_checkers_row(self):
        s, k, x = handed()
        out = k.on_event(says('FALSE', 'letter-a', x['sha256'], why=['the amount is wrong', 'the name is wrong'], found={'amount': 2400}, depends_on=ON_BOOK), execute=True)
        self.assertEqual(issued(out)['handoff']['before'], [{'try': 1, 'to': HAND, 'receipt': x['sha256'], 'checked': {'truth': 'FALSE', 'source': CHECKER, 'version': 'letter-a'}}])   # a list of reasons is left out, and so is every other key
        s, k, x = handed(); out = k.on_event(says('FALSE', 'letter-a', x['sha256'], depends_on=ON_BOOK), execute=True)   # a check that gives no reason: the next try knows that it failed, and its version
        self.assertEqual(issued(out)['handoff']['before'][0]['checked'], {'truth': 'FALSE', 'source': CHECKER, 'version': 'letter-a'})

    def test_l9_a_failed_check_counts_only_while_the_row_it_rests_on_stands(self):
        s, k, x = handed(SPENT + ['214_hand_to_officer'])   # the model is spent, the officer is handed the letter and has one slot
        out = fails(k, x, 'letter-a'); self.assertEqual((st(out), open_handoffs(s)[KEY]['failed']['version']), (NO_SLOT, 'letter-a'))   # its one try fails: no slot is left
        out = k.on_event(BOOK_2, execute=True)   # the book changes: the failed check rested on the old book and no longer reads, so the look waits on that same try
        self.assertEqual((st(out), said(s), open_handoffs(s)[KEY]['failed']), ([('WAITING', [], [QUEUE], [OFFICER_M], [])], ('UNKNOWN', None, False), None))
        s.apply(extra('t-fresh-slot', providers={'collections-officer': 1}))
        self.assertEqual(looks(s), [('WAITING', [], [QUEUE], [OFFICER_M], [])])   # a fresh slot hands nothing over: the work is out, and its check has to be stated again
        out = k.on_event(says('FALSE', 'letter-a-new-book', x['sha256'], why=WRONG, depends_on=[{'predicate': 'loan_on_book', 'version': BOOK_2['version']}]), execute=True)
        self.assertEqual((st(out), issued(out)['handoff']['try']), ([('WAITING', [OFFICER_M], [QUEUE], [OFFICER_M], [])], 2))

    def test_l10_two_pieces_of_work_under_one_goal_are_handed_over_one_after_the_other(self):
        both = extra('t-two-letters', scope='lendco/collections-letters-two', goals=['both_queued'], budget={'compute': 10, 'money': 5, 'attention': 3},
                     evidence=[{'predicate': 'loan_on_book', 'truth': 'TRUE', 'verified': True, 'source': CHECKER, 'version': 'book-fixture'}], providers={'letter-model': 4, 'local-provider': 2},
                     grants=['action:hand-a@t', 'action:hand-b@t', 'action:queue-both@t'],
                     methods=[method('hand-a@t', 'letter_a_drafted', ['loan_on_book'], provider='letter-model', action='handoff', handoff_to=HAND, instruction='Draft letter A.', verified_by=CHECKER),
                              method('hand-b@t', 'letter_b_drafted', ['loan_on_book'], provider='letter-model', action='handoff', handoff_to=HAND, instruction='Draft letter B.', verified_by=CHECKER),
                              method('queue-both@t', 'both_queued', ['letter_a_drafted', 'letter_b_drafted'])])
        s = State.from_packs([both]); k = Kernel(s); r = k.run_standing(execute=True)['runs'][0]
        self.assertEqual((r['status'], r['actions'], r['pending']), ('WAITING', ['hand-a@t'], ['hand-b@t', 'queue-both@t']))
        r = k.run_standing(execute=True)['runs'][0]   # a goal that waits runs none of its other steps (the kernel's rule): letter B is not handed over while A is out
        self.assertEqual((r['status'], r['actions'], r['pending'], r['waits'], list(open_handoffs(s))), ('WAITING', [], ['hand-b@t', 'queue-both@t'], ['hand-a@t'], ['lendco/collections-letters-two|letter_a_drafted']))

    def test_l11_no_line_of_the_blocked_look_says_that_a_try_failed(self):
        s, k, x = handed(SPENT + ['214_hand_to_officer']); out = fails(k, x, 'letter-a'); r = out['runs'][0]
        self.assertEqual((r['status'], [e['operation'] for e in r['trace'] if e['operation'].startswith('HANDOFF')], r['model_receipts']), ('PROVIDER_REQUIRED', [], []))
        self.assertEqual((out['event']['truth'], out['event']['checks'], open_handoffs(s)[KEY]['failed']['why']), ('FALSE', x['sha256'], WRONG))   # the failed check stands in the event's row and in the books

    def test_l12_two_states_with_the_same_packs_and_history_issue_the_same_receipt(self):
        a, b = handed()[2], handed()[2]; self.assertEqual(a, b)
        s = world(MODEL); k = Kernel(s); k.run_standing(); c = issued(k.run_standing(execute=True))   # one dry look more: another history, another receipt for the same try
        self.assertEqual((c['sha256'] != a['sha256'], told(c) == told(a)), (True, True))

    def test_l13_s140_reads_this_versions_cases_and_sequences_by_name_and_what_its_tests_read_of_them(self):
        spec = importlib.util.spec_from_file_location('independent_verify_for_handoff_limits', ROOT / 'qa' / 'independent_verify.py')
        v = importlib.util.module_from_spec(spec); spec.loader.exec_module(v)
        d = json.loads((ROOT / 'results' / 'actual_run_records.json').read_text(encoding='utf-8')); t = d['scenes']['handoff_letter']['tries']
        d['scenes']['a_later_sequence'] = json.loads(json.dumps(d['scenes']['handoff_letter']))   # another sequence that uses the kind, with a closing line that says confirmed of the hand's own row
        look = d['scenes']['a_later_sequence']['spent']['passing_check'][0]['result']; look['event']['source'] = OFFICER
        t['head']['sha256'] = '0' * 64                                             # a journal head: only its length is read
        t['book_changed'][1]['result']['event']['why'] = 'another reason'          # the words of a check that no later try was told of
        t['after_late_copy']['budget']['compute'] = 0                              # a snapshot that is not the last of its walk and that no test compares
        got, why = v.module_rows(ROOT / 'qa' / 'checks' / 'handoff.py', d, ROOT, set())
        self.assertEqual((why, [(ok, detail) for _, ok, detail in got]), (None, [(True, ''), (True, '')]))
        # A walk re-told from end to end in agreement with the rule: the reason of the first failed check re-worded, in its row and in the receipt that
        # tells the next try; that receipt hashed again and its new sha256 carried to every place that names it; every chain hashed again.
        d = json.loads((ROOT / 'results' / 'actual_run_records.json').read_text(encoding='utf-8'))
        t = json.loads(json.dumps(d['scenes']['handoff_letter']['tries'], ensure_ascii=False).replace(WRONG, 'the letter is fine as it is'))
        x2 = t['failed_check'][0]['result']['runs'][0]['model_receipts'][0]; was = x2['sha256']
        self.assertEqual(x2['handoff']['before'][0]['checked']['why'], 'the letter is fine as it is')
        t = json.loads(json.dumps(t, ensure_ascii=False).replace(was, v.sha({k: val for k, val in x2.items() if k != 'sha256'})))
        for look in [x['result'] for key in t for x in (t[key] if type(t[key]) is list else [t[key]]) if type(x) is dict and 'result' in x]:
            for r in look['runs']:
                prev = 'GENESIS'
                for n, e in enumerate(r['trace']):
                    e.update(seq=n + 1, prev_sha256=prev); e['sha256'] = prev = v.sha({k: val for k, val in e.items() if k != 'sha256'})
                r['trace_root_sha256'] = prev
        d['scenes']['handoff_letter']['tries'] = t
        got, why = v.module_rows(ROOT / 'qa' / 'checks' / 'handoff.py', d, ROOT, set())
        self.assertEqual((why, [(ok, detail) for _, ok, detail in got], was in json.dumps(t)), (None, [(True, ''), (True, '')], False))   # the checks follow the record with a rule; they do not run the kernel

    def test_l13_s140_reads_of_a_check_its_fact_source_receipt_and_truth_and_of_a_walk_its_runs_its_entries_and_its_last_books(self):
        """What the first review round found open in S140, pinned as it is: one forged record that holds all of it at once passes S140 and S141 (each field alone passes too:
        ClauseTests). The unit test that makes the record again (test_the_record_on_disk_holds_both_sequences) holds every one of these fields."""
        spec = importlib.util.spec_from_file_location('independent_verify_for_handoff_unread', ROOT / 'qa' / 'independent_verify.py')
        v = importlib.util.module_from_spec(spec); spec.loader.exec_module(v)
        true = json.loads((ROOT / 'results' / 'actual_run_records.json').read_text(encoding='utf-8'))
        d = json.loads(json.dumps(true)); t, p = d['scenes']['handoff_letter']['tries'], d['scenes']['handoff_letter']['spent']
        passing, failing = t['passing_check'][0]['result'], t['failed_check'][0]['result']
        passing['event'].update(verified=False, scope='lendco/another-desk')        # the row that confirmed the work: not verified, and of another desk
        passing['event']['depends_on'][0]['version'] = 'a-book-that-never-stood'      # and resting on a row that never stood (by the lab's rule it reads UNKNOWN and confirms nothing)
        passing.update(status='DECISION_STANDS', affected=[])                        # its own look says that it was turned away
        failing['event'].update(verified=False); del failing['event']['depends_on']  # the failed check that opened the second try: not verified, resting on nothing
        t['handed_over'][0]['result']['event']['source'] = HAND                      # the book's row said to come from the hand
        t['handed_over'][0]['result']['runs'][0]['model_receipts'][0].update(scope='lendco/another-desk')   # a hand-over receipt's scope (not hashed again: S140 reads no receipt's own hash)
        t['handed_over'][0]['result']['runs'][0]['model_receipts'][0]['handoff']['handed_in'] = 'f' * 64     # and the digest that binds it to its State: another text of 64 characters
        t.update(wrote_1=240, wrote_2=2400)                                          # what the hand wrote at each try (C4 cites both)
        t['after_book_changed'].update(open_handoffs={}); t['after_book_changed']['letter_queued']['truth'] = 'TRUE'   # the last snapshot of the walk: still queued, nothing out
        t['head_kept']['length'] = t['restarted']['head']['length'] = 3              # the kept head and the head the restart found, changed together
        t['head']['sha256'] = '0' * 64
        p['after']['letter_queued']['truth'] = 'UNKNOWN'; p['after']['letter_drafted']['source'] = HAND   # the last snapshot of the other walk: not queued, and the letter's row the hand's
        p['head'].update(length=99, sha256='0' * 64); p['dry_look']['entry'] = 8; p['officer_wrote'] = 0
        for out_of in p['wrong_letters'][2]['after']['open_handoffs'].values(): out_of['failed'] = None   # the books said to hold no failed try (C6 cites them)
        d['added']['scenes']['handoff_letter'] = v.sha(d['scenes']['handoff_letter'])
        got, why = v.module_rows(ROOT / 'qa' / 'checks' / 'handoff.py', d, ROOT, set())
        self.assertEqual((why, [(ok, detail) for _, ok, detail in got]), (None, [(True, ''), (True, '')]))
        # S140 reads a walk in the order its keys stand in the record's text. The same record with its keys in sorted order has every seal as it was (a seal is hashed with
        # sorted keys) and FAILS S140: a false alarm, not a forged pass. The verifier hands S140 the record as the build wrote it.
        d = json.loads(json.dumps(true, sort_keys=True))
        self.assertEqual([v.sha(d['scenes'][n]) == d['added']['scenes'][n] for n in ('handoff_existing', 'handoff_letter')], [True, True])
        got, why = v.module_rows(ROOT / 'qa' / 'checks' / 'handoff.py', d, ROOT, set())
        self.assertEqual((why, [(ok, detail) for _, ok, detail in got][0]), (None, (False, 'bound closes door needs tries waits')))
        # The module reads every scenario file whose name begins with 21: the eight packs of this version and one pack the lab had before, which holds no method.
        self.assertIn('21_enquiry_theory', [f.stem for f in (ROOT / 'scenarios').glob('21*.json')])
        self.assertEqual(pack('21_enquiry_theory').get('methods', []), [])

    def test_l14_a_failed_check_is_forgotten_as_soon_as_a_later_row_of_the_checker_on_the_fact_is_not_that_check(self):
        """The widest limit, found by both refuters of the first review round, pinned here by their own repro. The kind keeps no memory of a failed check: it reads it
        from the row the fact reads from, at every look. The cure (the failed check kept on the kind's books) is new code and is owed to the kind's next version."""
        def spent():   # the model's three tries, each failed by the checker: the gate turns the fourth down, and the books say which try failed and why (C6)
            s, k, x = handed(); receipts = [x]
            for n in (1, 2, 3):
                out = fails(k, receipts[-1], f'letter-{n}', why=f'wrong {n}')
                if n < 3: receipts.append(issued(out))
            self.assertEqual((st(out), open_handoffs(s)[KEY]['failed']['why'], s.providers['letter-model']), (NO_SLOT, 'wrong 3', 0))
            return s, k, receipts
        s, k, receipts = spent()
        late = k.on_event(says('FALSE', 'letter-1-late', receipts[0]['sha256'], why='a late copy of the first draft', depends_on=ON_BOOK), execute=True)   # the checker's late copy of draft 1 (the row of tries.late_copy)
        self.assertEqual((st(late), open_handoffs(s)[KEY]['failed'], open_handoffs(s)[KEY]['issued']['handoff']['try'], said(s)), (WAITS, None, 3, ('FALSE', CHECKER, False)))   # the look waits on the failed third try again; the books say nothing of the failure
        s.apply(pack('214_hand_to_officer')); before = held(s)   # the next hand is loaded
        self.assertEqual((looks(s), looks(s, execute=False), looks(s), held(s) == before, s.providers), (WAITS, WAITS, WAITS, True, {'local-provider': 4, 'letter-model': 0, 'collections-officer': 1}))   # and is never handed the work
        out = fails(k, receipts[2], 'letter-3-again', why='wrong 3, stated again'); x4 = issued(out)   # only the check of the try that is out, stated again, frees the work
        self.assertEqual((st(out), x4['handoff']['to'], x4['handoff']['try'], [(b['try'], b['checked']['why']) for b in x4['handoff']['before']], s.providers['collections-officer']),
                         ([('WAITING', [OFFICER_M], [QUEUE], [OFFICER_M], [])], OFFICER, 4, [(1, 'wrong 1'), (2, 'wrong 2'), (3, 'wrong 3, stated again')], 0))
        s, k, receipts = spent(); s.apply(pack('214_hand_to_officer'))   # without the late copy the officer is handed the letter at once (C7)
        self.assertEqual(issued(k.run_standing(execute=True))['handoff']['to'], OFFICER)
        rows = {'a failed check that names no receipt': lambda r: says('FALSE', 'unnamed', why=WRONG, depends_on=ON_BOOK),
                'a row of the checker that reads UNKNOWN': lambda r: says('UNKNOWN', 'unread', r[2]['sha256'], why='the letter could not be read')}
        for name, row in rows.items():
            s, k, receipts = spent(); out = k.on_event(row(receipts), execute=True)
            s.apply(pack('214_hand_to_officer')); s.apply(extra('t-fresh-slot', providers={'letter-model': 1}))   # the next hand is loaded AND the first hand is given a fresh slot
            self.assertEqual((st(out), open_handoffs(s)[KEY]['failed'], looks(s), s.providers['letter-model'], s.providers['collections-officer']), (WAITS, None, WAITS, 1, 1), name)   # no next try and no next hand
        s, k, x = handed()   # the same before any try was acted on: a failed check let in by a dry event (the dry look plans the next try), then a row of the checker that names no receipt
        dry = k.on_event(says('FALSE', 'letter-a', x['sha256'], why=WRONG, depends_on=ON_BOOK), execute=False)
        self.assertEqual((st(dry), open_handoffs(s)[KEY]['failed']['why']), ([('PLAN_READY', [MODEL_M, QUEUE], None, None, [])], WRONG))
        out = k.on_event(says('FALSE', 'letter-a-again', why=WRONG, depends_on=ON_BOOK), execute=True)
        self.assertEqual((st(out), open_handoffs(s)[KEY]['failed'], s.providers['letter-model'], looks(s)), (WAITS, None, 2, WAITS))   # two slots are free and the work is never handed over again

    def test_l15_when_nothing_is_out_a_row_that_takes_the_fact_back_re_opens_the_work_as_a_new_paid_hand_over_that_is_told_nothing(self):
        def confirmed():   # two tries of the model, the second confirmed: the hand-off is closed, the letter queued, nothing is out
            s, k, x1 = handed(); x2 = issued(fails(k, x1, 'letter-a')); out = passes(k, x2)
            self.assertEqual(([(c['tries'], c['confirmed']) for c in closed(out)], s.budget['compute'], s.providers['letter-model'], said(s, 'letter_queued')[0], open_handoffs(s)), ([(2, True)], 5, 1, 'TRUE', {}))
            return s, k, x1, x2
        rows = {'the late copy of the first draft (it fails no try while a try is out: C5)': lambda x1, x2: says('FALSE', 'letter-a-late', x1['sha256'], why='a late copy of the first draft', depends_on=ON_BOOK),
                'a FALSE of the checker on the try it confirmed': lambda x1, x2: says('FALSE', 'on-a-second-reading', x2['sha256'], why=WRONG, depends_on=ON_BOOK),
                'a FALSE of the checker that names no receipt': lambda x1, x2: says('FALSE', 'unnamed', why=WRONG, depends_on=ON_BOOK),
                'a row of the checker that reads UNKNOWN': lambda x1, x2: says('UNKNOWN', 'unread', x2['sha256'])}
        for name, row in rows.items():
            s, k, x1, x2 = confirmed(); out = k.on_event(row(x1, x2), execute=True); y = issued(out)
            self.assertEqual((st(out), told(y)['try'], told(y)['before'], y['sha256'] not in (x1['sha256'], x2['sha256']), s.budget['compute'], s.providers['letter-model'], said(s, 'letter_queued')),
                             (HANDS, 1, [], True, 3, 0, ('UNKNOWN', None, False)), name)   # the letter is taken back; a new hand-over, try 1, told nothing of the two tries or of this row; two tokens and the last slot

    def test_l16_a_check_that_states_nothing_it_rests_on_confirms_and_outlives_the_book(self):
        s, k, x = handed(); out = k.on_event(says('TRUE', 'typed-by-hand', x['sha256']), execute=True)   # the checker's TRUE on the try that is out, with no depends_on
        self.assertEqual(([(c['confirmed'], c['version']) for c in closed(out)], 'depends_on' in s.evidence[KEY]), ([(True, 'typed-by-hand')], False))   # the kind asks nothing of what a check rests on
        out = k.on_event(BOOK_2, execute=True)   # the loan book changes: the letter still counts as drafted and stays queued, as under T3's stamped yes
        self.assertEqual((st(out), said(s), said(s, 'letter_queued'), open_handoffs(s), s.providers['letter-model']),
                         ([('SUPPORTED_BY_EVIDENCE', [], None, None, [])], ('TRUE', CHECKER, False), ('TRUE', 'LOCAL_MODEL:' + QUEUE, False), {}, 2))

    def test_l17_the_budget_of_the_whole_plan_can_end_the_tries_before_the_capacity_does(self):
        s, k, x = handed(MODEL, extra('t-six-tokens', budget={'compute': 6})); self.assertEqual((s.budget['compute'], s.providers['letter-model']), (4, 2))
        out = fails(k, x, 'letter-1'); x2 = issued(out); self.assertEqual((st(out), x2['handoff']['try'], s.budget['compute'], s.providers['letter-model']), (HANDS, 2, 2, 1))
        r = fails(k, x2, 'letter-2')['runs'][0]   # a slot is left and the price of a try (two tokens) is there: the plan is admitted whole, with the queueing step, and that costs three
        self.assertEqual((r['status'], r['work_state'], r['model_receipts'], r['stop_reasons'], admissions(r), s.budget['compute'], s.providers['letter-model']),
                         ('RESOURCE_REQUIRED', 'blocked', [], ['RESOURCE_REQUIRED'], [([MODEL_M, QUEUE], False, ['RESOURCE_REQUIRED'])], 2, 1))
        self.assertEqual((open_handoffs(s)[KEY]['issued']['handoff']['try'], open_handoffs(s)[KEY]['failed']['version']), (2, 'letter-2'))

    def test_l18_through_the_journals_pack_door_the_hands_own_row_is_sealed_also_as_a_decision(self):
        door = 'The event door lets in only verified rows that are not decisions, from a checker the header names'
        for final in ({}, {'final': True}):
            run = J.start(['simulate_fact', 'handoff'], [CHECKER], name='t-pack-door')
            for n in MODEL: run.add('pack', {'pack': pack(n)})
            x = issued(run.detail[run.add('look', {'execute': True})['seq']]); n = len(run.journal)
            own = dict(says('TRUE', 'the-hands-own-word', x['sha256'], source=HAND), **final)
            with self.assertRaisesRegex(ValueError, door): run.add('event', {'row': own, 'execute': True})   # as an event the row is refused (C9)
            e = run.add('pack', {'pack': extra('t-the-hands-word', evidence=[own])})   # as evidence of a pack it is taken and sealed: the journal's own stated limit (a pack may carry any row, a decision too)
            out = run.detail[run.add('look', {'execute': True})['seq']]
            self.assertEqual((e['kind'], len(run.journal), run.head()['length'], st(out), [(c['source'], c['confirmed']) for c in closed(out)], said(run.state)),
                             ('pack', n + 2, n + 2, [(DONE, [QUEUE], None, None, [])], [(HAND, False)], ('TRUE', HAND, bool(final))), str(final))   # the letter is queued on the hand's word; the line says not confirmed

    def test_l19_the_closing_line_stands_in_the_first_executed_run_of_the_scope_after_the_row(self):
        lines = lambda look: [(r['goal'], r['status'], r['actions'], len([e for e in r['trace'] if e['operation'] == 'HANDOFF_CLOSED'])) for r in look['runs']]
        notice = extra('t-notice', goals=['notice_filed', 'letter_queued'], grants=['action:file-notice@t'], methods=[method('file-notice@t', 'notice_filed', ['notice_ready'])],
                       evidence=[{'predicate': 'notice_ready', 'truth': 'TRUE', 'verified': True, 'source': 'fixture/notice', 'version': '1'}])   # a second goal that never needs the letter, first in the list
        s = world(MODEL, notice); k = Kernel(s); x = k.run_standing(execute=True)['runs'][1]['model_receipts'][0]
        dry = k.on_event(says('TRUE', 'letter-right', x['sha256'], depends_on=ON_BOOK), execute=False)   # the checker's TRUE let in by a dry event: no executed run, so nothing is closed
        self.assertEqual((lines(dry), list(s.active_work['handoff'])), ([('letter_queued', 'PLAN_READY', [QUEUE], 0)], [KEY]))
        self.assertEqual(lines(k.run_standing(execute=True)), [('notice_filed', 'SUPPORTED_BY_EVIDENCE', [], 1), ('letter_queued', DONE, [QUEUE], 0)])   # the line stands in the run of the goal that never needed the letter; the run that queues has none
        filed = extra('t-filed', goals=['letter_filed', 'letter_queued'], grants=['action:file-letter@t'], methods=[method('file-letter@t', 'letter_filed', ['letter_drafted'])])   # two goals that need the letter
        s = world(MODEL, filed); k = Kernel(s); first = k.run_standing(execute=True); x = first['runs'][0]['model_receipts'][0]
        self.assertEqual([(r['goal'], r['status'], len(r['model_receipts'])) for r in first['runs']], [('letter_filed', 'WAITING', 1), ('letter_queued', 'WAITING', 0)])   # handed over once; both wait on it
        self.assertEqual(lines(passes(k, x)), [('letter_filed', DONE, ['file-letter@t'], 1), ('letter_queued', DONE, [QUEUE], 0)])   # one line, in the first goal's run

    def test_l20_the_stand_in_checker_looks_for_two_names_as_text_and_for_the_digits_after_overdue_by(self):
        cite = 'for hand-over ' + 'a' * 64 + '\n'
        with tempfile.TemporaryDirectory() as tmp:
            keep_book(tmp, 240)
            taken = ['Dear A. Rao, your loan L-170 is overdue by 240.',                               # another loan, whose number begins with the book's
                     'Dear A. Raoul, your loan L-17 is overdue by 240,000.',                         # another borrower and a thousand times the amount
                     'Dear A. Rao, your loan L-17 is overdue by 240.99.',
                     'Dear A. Rao, your loan L-17 is not overdue by 240.',                           # the letter says the opposite
                     'Dear B. Shah, about A. Rao: loan L-99 (not L-17) is not overdue by 240.75',    # a letter to somebody else about another loan
                     'Dear A. Rao, your loan L-17 is overdue by 240 and you owe 9000 in fees.']
            for body in taken:
                (Path(tmp) / 'letter.txt').write_bytes((cite + body + '\n').encode('utf-8')); row = check(tmp)[1]
                self.assertEqual((row['truth'], 'why' in row), ('TRUE', False), body)
            for body, why in (('Dear A. Rao, your loan L-17 is overdue by 0240.', 'the letter says an overdue amount of 0240; the loan book says 240'),   # the digits are compared as text
                              ('Dear A. Rao, your loan L-17 is OVERDUE BY 240.', 'the letter says an overdue amount of nothing; the loan book says 240')):
                (Path(tmp) / 'letter.txt').write_bytes((cite + body + '\n').encode('utf-8')); row = check(tmp)[1]
                self.assertEqual((row['truth'], row['why']), ('FALSE', why), body)

    def test_l22_a_passing_check_stated_again_under_another_version_runs_and_pays_again_what_was_made_on_it(self):
        s, k, x = handed(); passes(k, x); before = held(s)
        self.assertEqual((st(passes(k, x)), held(s)), ([('SUPPORTED_BY_EVIDENCE', [], None, None, [])], before))   # the same row again, letter for letter: nothing runs
        out = passes(k, x, 'letter-right-read-again')   # the checker states its TRUE again under another version: what was made on the first one rests on that version and no longer reads
        self.assertEqual((st(out), closed(out), s.budget['compute'], s.providers['local-provider'], s.providers['letter-model'], open_handoffs(s)),
                         ([(DONE, [QUEUE], None, None, [])], [], 6, 2, 2, {}))   # the queueing step runs and is paid a second time; the hand-off stays closed and nothing is handed over again

    def test_l21_of_a_row_that_is_refused_or_turned_away_the_record_keeps_the_labs_answer_and_not_the_row(self):
        scenes = json.loads((ROOT / 'results' / 'actual_run_records.json').read_text(encoding='utf-8'))['scenes']
        door = scenes['handoff_letter']['tries']['at_the_door']   # four refusals, in two sentences; the unverified row that test C9 presents is not among them
        self.assertEqual((sorted(door), len(set(door.values()))), (['a_decision_under_the_checkers_name', 'a_stamp_from_the_checker', 'a_stamp_from_the_hand', 'the_hands_own_row'], 2))
        for part, key in (('doer_asked', 'checker_says_no'), ('checker_asked', 'second_draft_row'), ('checker_stamps_yes', 'checker_says_no')):   # T1, T2, T3: the rows a decision turned away
            self.assertEqual(scenes['handoff_existing'][part][key], {'status': 'DECISION_STANDS', 'affected': [], 'runs': []}, part)


if __name__ == '__main__':
    unittest.main()
