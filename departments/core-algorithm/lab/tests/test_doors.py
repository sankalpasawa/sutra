"""0.21.0-doors: which source may state which fact at the journal's event door, and a run that stops for want of a place, as the program's
own records showed them (needs N1, N2 and N3 of the version). The packs of five desks of a lender (315 to 319), cases 163 and 164 and the
recorded sequence `doors`. A test named test_cN_... pins claim CN of the README passage and a test named test_lN_... pins limit LN as the
build behaves today. The class Existing holds what the parts the lab had make of the same needs: the attempt ruling R35 of the program asks
for before a part is added. The sequence is compared with the built record (results/actual_run_records.json), so these tests run after
tools/run_all.py."""
from pathlib import Path
import unittest, sys, json
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from kernel.core import State, Kernel, digest
from tools.run_all import CASES, pack   # importing the lab's tools loads the kind files: handoff is registered from kinds/handoff.py
from tools.make_packs import method
from extensions.asks import answer, open_asks
from extensions import journal as J
from extensions import journal_record as R
from extensions import learn
from extensions import reader
from extensions import queue_provenance as Q
from extensions.reflection import Learner

BOOK, FINANCE, OWNER, READER = 'system:lendco/loan-book', 'system:lendco/finance', 'owner:lendco', 'adapter:reader'
RECON, POSTING, NOTES, AUDIT = 'checker:reconciliation-ledger', 'checker:posting-log', 'checker:review-notes', 'checker:audit'
DESKS, BATCH, AGENT = ['simulate_fact', 'ask'], ['simulate_fact', 'handoff'], ['ask', 'handoff', 'simulate_fact']
REFUND, PAYOUTS, CHANGE, LANDING, REVIEW = '315_door_refund_desk', '316_door_payout_desk', '317_door_change_approval', '318_door_batch_landing', '319_door_file_review'
ASK, SEND, RUN_RECON, POST = 'door-ask-finance@1', 'door-send-refund@1', 'door-run-reconciliation@1', 'door-post-batch@1'
STEPS = ['door-read-loan-file@1', 'door-check-instalments@1', 'door-check-arrears@1', 'door-write-findings@1', 'door-close-review@1']
REVIEWER = {'doer': 'agent:file-reviewer', 'has': 1, 'needs': 5, 'steps': STEPS}   # what the brief of the reviewer's first look says under the door
UNDER = 'A journal that continues one under the plan door is under it too: start it with the same door'
HEADER = 'A header holds kinds and checkers (lists of names) and may hold a name and the head it continues'
EVENT_DOOR = 'The event door lets in only verified rows that are not decisions, from a checker the header names'
LEDGER_KEYS = {'journal', 'entry', 'sha256', 'what', 'run', 'executed', 'receipts', 'goal', 'scope', 'status', 'work_state', 'actions', 'cost',
               'trace_root_sha256', 'stop_reasons'}   # a ledger row of a blocked run as the record adapter wrote it before this version


def gives(fact, whom, source):   # the words of the plan door for a row on a fact the plan gives to someone else
    return 'The plan gives ' + fact + ' to ' + whom + ': a row of ' + source + ' on it is refused at the event door'


def no_work(fact, source, steps):   # the words for a checker's row with no try out on the fact
    return ('No work is out on ' + fact + ': ' + source + ' checks it for ' + ' and '.join(steps) + ', and a row of ' + source
            + " on it is taken only as the check of a try that is out, naming that try's receipt under checks")


def other_try(fact, receipt, step, checker, source):   # the words for a row that is not the check of the try that is out
    return ('The try out on ' + fact + ' is the receipt ' + receipt + ' of ' + step + ', checked by ' + checker + ': a row of ' + source
            + ' on it is taken only as that check, from ' + checker + ', naming that receipt under checks')


def desk(packs, checkers, kinds, door='plan', name='t'):   # a journal with its packs handed in; a pack is a scenario file's name or a pack made in memory
    run = J.start(kinds, checkers, name=name, **({'door': door} if door else {}))
    for p in packs:
        run.add('pack', {'pack': pack(p) if type(p) is str else p})
    return run


def row(fact, truth, by, version, **more):
    return dict({'predicate': fact, 'truth': truth, 'verified': True, 'source': by, 'version': version}, **more)


def event(run, r, execute=True):
    return run.detail[run.add('event', {'row': r, 'execute': execute})['seq']]


def look(run, execute=True):
    return run.detail[run.add('look', {'execute': execute})['seq']]


def words(do):
    try:
        do()
    except ValueError as why:
        return str(why)
    return None


def out(run, fact):   # the receipt of the try out on a fact, as the hand-over kind keeps it in its books
    entry = run.state.active_work.get('handoff', {}).get(run.state.key(fact))
    return entry['receipt'] if entry else None


def kept(run):   # one record: the journal's text and its head
    return [(J.dump(run.journal), {'length': len(run.journal), 'sha256': run.journal[-1]['sha256']})]


def statuses(look_or_event):
    return [(r['goal'], r['status']) for r in look_or_event['runs']]


def said(short):   # the brief's `short` in the words of the decision-provenance rows of 0.17.0
    return [s['doer'] + ': needs ' + str(s['needs']) + ', has ' + str(s['has']) for s in short]


def sequence():   # the recorded sequence made again, as tools/run_all.py makes it
    ns = {'__name__': 'tools.scenes.doors'}
    exec(compile((ROOT / 'tools' / 'scenes' / 'doors.py').read_text(), 'doors', 'exec'), ns)
    made = ns['scene']({'State': State, 'Kernel': Kernel, 'pack': pack, 'answer': answer, 'open_asks': open_asks, 'Learner': Learner, 'digest': digest})
    return json.loads(json.dumps(made, ensure_ascii=False, allow_nan=False))


def rechained(entries, n=0):   # entries changed from entry n on, the chain made whole again: a forgery the chain cannot see
    prev = entries[n - 1]['sha256'] if n else 'GENESIS'
    for e in entries[n:]:
        e['prev_sha256'] = prev
        e.pop('sha256', None)
        e['sha256'] = digest({k: e[k] for k in J.COVERED})
        prev = e['sha256']
    return entries


def closing(run, nxt):   # the text of a run's journal with a closing entry that names `nxt`, the chain made whole again
    entries = json.loads(json.dumps(run.journal))
    last = entries[-1]
    entries.append({'seq': len(entries), 'prev_sha256': last['sha256'], 'kind': 'close', 'body': {'next': nxt},
                    'result': {'budget': last['result']['budget'], 'providers': last['result']['providers'], 'state': last['result']['state']}})
    return rechained(entries, len(entries) - 1)


class Sequence(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.made = sequence()
        cls.data = json.loads((ROOT / 'results' / 'actual_run_records.json').read_text())

    def step(self, side, name, move):
        [s] = [s for s in self.made[side][name]['steps'] if s['move'] == move]
        return s

    def test_the_record_on_disk_holds_this_sequence(self):
        self.assertEqual(json.dumps(self.made, sort_keys=True), json.dumps(self.data['scenes']['doors'], sort_keys=True))

    def test_the_recorded_proposals_are_what_the_learn_feature_gives_again_for_the_recorded_texts(self):
        for side in ('before', 'after'):
            records = [[(k['text'], k['head'])] for k in self.made[side].values()]
            self.assertEqual(learn.proposals(records, 2), self.made['proposals'][side], side)

    def test_c1_before_the_loan_books_rows_settle_finances_yes_and_the_steps_and_after_they_are_refused(self):
        b, a = self.made['before'], self.made['after']
        yes = gives('refund_approved_by_finance', FINANCE + ', as the answer to the question of ' + ASK, BOOK)
        # example 1, c0bc: before, the refund is sent on the loan book's yes; after, the row is refused and the desk asks finance
        self.assertEqual(statuses(self.step('before', 'refund_desk_1', 'the loan book states the refund is due')['result']), [('refund_sent', 'LOCAL_MODEL_EFFECTS_RECORDED')])
        self.assertEqual((b['refund_desk_1']['budget']['money'], a['refund_desk_1']['budget']['money']), (2, 3))
        self.assertEqual(self.step('after', 'refund_desk_1', "the loan book states finance's yes")['refused'], yes)
        self.assertEqual(statuses(self.step('after', 'refund_desk_1', 'the loan book states the refund is due')['result']), [('refund_sent', 'WAITING')])
        # example 1, c345: before, the refund goes before finance's no; after, finance's no refuses the goal and nothing was paid
        self.assertEqual(statuses(self.step('before', 'refund_desk_2', "the loan book states finance's yes")['result']), [('refund_sent', 'LOCAL_MODEL_EFFECTS_RECORDED')])
        self.assertEqual(self.step('after', 'refund_desk_2', "the loan book states finance's yes")['refused'], yes)
        self.assertEqual([statuses(self.step(side, 'refund_desk_2', 'finance answers no')['result']) for side in ('before', 'after')], [[('refund_sent', 'REFUSED')]] * 2)
        self.assertEqual((b['refund_desk_2']['budget']['money'], a['refund_desk_2']['budget']['money']), (2, 3))
        # example 1, b403: before, the goal reads reached with no step run; after, the row on the step's fact is refused
        reached = self.step('before', 'refund_desk_3', 'the loan book states the refund was sent')['result']['runs'][0]
        self.assertEqual((reached['status'], reached['model_receipts']), ('SUPPORTED_BY_EVIDENCE', []))
        self.assertEqual(self.step('after', 'refund_desk_3', 'the loan book states the refund was sent')['refused'],
                         gives('refund_sent', 'the step ' + SEND + ', whose receipt makes it', BOOK))
        self.assertEqual((b['refund_desk_3']['budget']['money'], a['refund_desk_3']['budget']['money']), (3, 3))   # the refund read sent before and was never paid
        # example 5, ea6c: before, loans 102 and 103 are never paid; after, both rows are refused and each loan runs the three steps
        for loan in ('102', '103'):
            self.assertEqual(self.step('before', 'payouts_1', 'a payout is due on loan ' + loan)['result']['runs'][0]['model_receipts'], [])
            self.assertEqual([x['method'] for x in self.step('after', 'payouts_1', 'a payout is due on loan ' + loan)['result']['runs'][0]['model_receipts']],
                             ['door-check-payee@1', 'door-pay@1', 'door-reconcile@1'])
        self.assertEqual([self.step('after', 'payouts_1', m)['refused'] for m in ('the loan book states the payout reconciled', 'the loan book states the payout paid')],
                         [gives('payout_reconciled', 'the step door-reconcile@1, whose receipt makes it', BOOK), gives('payout_paid', 'the step door-pay@1, whose receipt makes it', BOOK)])
        self.assertEqual((b['payouts_1']['budget']['money'], a['payouts_1']['budget']['money']), (5, 3))
        # example 5, 43e9: before, the plan goes on without the owner's answer; after, the row is refused and the owner's no refuses the goal
        self.assertEqual(statuses(self.step('before', 'payouts_2', "the loan book states the owner's yes")['result']), [('cheaper_way_approved', 'SUPPORTED_BY_EVIDENCE')])
        self.assertEqual(self.step('after', 'payouts_2', "the loan book states the owner's yes")['refused'],
                         gives('cheaper_way_approved', OWNER + ', as the answer to the question of door-ask-owner@1', BOOK))
        self.assertEqual(statuses(self.step('after', 'payouts_2', 'the owner answers no')['result']), [('cheaper_way_approved', 'REFUSED')])
        # example 2, 1071: before, the posting log's row on the reconciliation closes it unconfirmed and the posting goes out; after, it is refused
        went = self.step('before', 'batch_4', 'the posting log states the batch reconciled')['result']['runs'][0]
        self.assertEqual(([x['method'] for x in went['model_receipts']], [e['data']['confirmed'] for e in went['trace'] if e['operation'] == 'HANDOFF_CLOSED']), ([POST], [False]))
        self.assertEqual(self.step('after', 'batch_4', 'the posting log states the batch reconciled')['refused'],
                         gives('batch_reconciled', RECON + ', as the check of ' + RUN_RECON, POSTING))

    def test_c1_the_loan_book_still_states_what_no_method_makes(self):
        for name, move in (('refund_desk_1', 'the loan book states the refund is due'), ('refund_desk_3', 'the loan book states the refund is not due: the payment bounced'),
                           ('payouts_1', 'a payout is due on loan 102'), ('payouts_2', 'a payout is due on loan 105')):
            self.assertEqual(self.step('after', name, move)['result']['status'], 'RECONCILED', name)

    def test_c2_before_a_checkers_row_with_no_work_out_lands_the_batch_and_after_it_is_refused_and_the_plan_keeps_its_order(self):
        b, a = self.made['before'], self.made['after']
        handed = lambda side, name: [x['method'] for s in self.made[side][name]['steps'] if 'result' in s for r in s['result']['runs'] for x in r['model_receipts']]
        # before: the batch reads landed with the reconciliation (c5b3) or the posting (23ae, ecd6) never handed over
        self.assertEqual([handed('before', n) for n in ('batch_1', 'batch_2', 'batch_3')], [[POST], [RUN_RECON], [RUN_RECON]])
        self.assertEqual([b[n]['steps'][-1]['result']['runs'][0]['status'] for n in ('batch_1', 'batch_2', 'batch_3')], ['SUPPORTED_BY_EVIDENCE'] * 3)
        # after: every row with no work out is refused, in words that say no work is out
        self.assertEqual(self.step('after', 'batch_1', 'the reconciliation ledger states the batch reconciled')['refused'], no_work('batch_reconciled', RECON, [RUN_RECON]))
        self.assertEqual(self.step('after', 'batch_1', 'the posting log checks the posting that is out')['refused'], no_work('batch_posted', POSTING, [POST]))
        self.assertEqual([self.step('after', n, 'the posting log states the batch posted')['refused'] for n in ('batch_2', 'batch_3')], [no_work('batch_posted', POSTING, [POST])] * 2)
        self.assertEqual(self.step('after', 'batch_2', 'the reconciliation ledger checks the reconciliation that is out')['refused'], no_work('batch_reconciled', RECON, [RUN_RECON]))
        # and the plan keeps its order: the reconciliation goes out first, the posting after its check
        self.assertEqual([handed('after', n) for n in ('batch_1', 'batch_2', 'batch_3')], [[RUN_RECON], [RUN_RECON], [RUN_RECON, POST]])
        self.assertEqual([a[n]['steps'][-1]['result']['runs'][0]['status'] for n in ('batch_1', 'batch_2', 'batch_3')], ['WAITING'] * 3)

    def test_c6_the_learn_feature_says_no_row_was_stated_by_another_or_without_a_check_over_the_records_made_after(self):
        kinds = lambda side: sorted({p['kind'] + ('/' + p['what'] if p['kind'] == 'IN_SEVERAL_RECORDS' else '') for p in self.made['proposals'][side]})
        stated = {'STATED_BY_ANOTHER', 'STATED_WITHOUT_A_CHECK', 'IN_SEVERAL_RECORDS/stated_by_another', 'IN_SEVERAL_RECORDS/stated_without_a_check'}
        self.assertEqual(stated - set(kinds('before')), set())
        self.assertEqual(stated & set(kinds('after')), set())
        self.assertEqual([len([p for p in self.made['proposals']['before'] if p['kind'] == k]) for k in ('STATED_BY_ANOTHER', 'STATED_WITHOUT_A_CHECK')], [7, 3])
        self.assertEqual(set(kinds('after')), set(kinds('before')) - stated)   # what else is proposed stays: checks, the failed tries, the blocked looks, the packs

    def test_c7_under_the_door_the_brief_and_the_ledger_row_name_the_doer_that_is_short_its_places_and_the_steps_that_need_it(self):
        stops = self.made['stops']
        self.assertEqual([(s['session'], s['door'], s['entry']) for s in stops],
                         [('file_review', None, 2), ('file_review', None, 3), ('file_review', 'plan', 2), ('file_review', 'plan', 3), ('batch_4', None, 4), ('batch_4', 'plan', 4)])
        recon = {'doer': 'script:reconcile', 'has': 0, 'needs': 1, 'steps': [RUN_RECON]}   # after two failed tries the script has no place left; the posting's script has two and is not named
        for s, short in ((stops[2], [REVIEWER]), (stops[3], [REVIEWER]), (stops[5], [recon])):   # the reviewer's first look, executed and dry; the batch after two failed tries
            self.assertEqual([(b['status'], b['short']) for b in s['brief']], [('PROVIDER_REQUIRED', short)])
            self.assertEqual([(r['status'], r['short']) for r in s['ledger']], [('PROVIDER_REQUIRED', short)])
            self.assertEqual(set(s['ledger'][0]) - LEDGER_KEYS, {'short'})
            self.assertEqual(said(short), [f['value'] for d in s['decisions'] for f in d['factors'] if f['type'] == 'provider_short'])   # the projection of 0.17.0 says the same
        for s in (stops[0], stops[1], stops[4]):   # a journal started without the door keeps the brief it always had
            self.assertEqual([(b['status'], b['stop_reasons'], b['actions'], 'short' in b) for b in s['brief']], [('PROVIDER_REQUIRED', ['PROVIDER_REQUIRED'], [], False)])
            self.assertEqual(set(s['ledger'][0]) - LEDGER_KEYS, set())

    def test_c7_the_shortfall_and_a_learner_say_only_the_status_word_on_both_sides(self):
        for s in self.made['stops']:
            self.assertEqual((s['shortfall'], [[x['gap'] for x in l] for l in s['learner']]), ([[]], [['PROVIDER_REQUIRED']]))

    def test_c7_every_try_takes_a_place_that_does_not_come_back(self):
        for side in ('before', 'after'):
            providers = [s['result']['runs'][0] for s in self.made[side]['batch_4']['steps'][:3]]
            self.assertEqual([[x['handoff']['try'] for x in r['model_receipts']] for r in providers], [[1], [2], []])
        entries = J.parse(self.made['after']['batch_4']['text'])
        self.assertEqual([e['result']['providers']['script:reconcile'] for e in entries[1:]], [2, 1, 0, 0])   # two tries, two places spent, none back

    def test_l11_the_learn_feature_of_0_20_0_still_proposes_the_blocked_looks_since_the_look_still_stops(self):
        for side in ('before', 'after'):
            again = [(p['goal'], p['reason'], p['times']) for p in self.made['proposals'][side] if p['kind'] == 'BLOCKED_AGAIN']
            several = [(p['reason'], p['records']) for p in self.made['proposals'][side] if p['kind'] == 'IN_SEVERAL_RECORDS' and p['what'] == 'blocked' and p['reason'] == 'PROVIDER_REQUIRED']
            self.assertEqual((again, several), ([('loan_file_reviewed', 'PROVIDER_REQUIRED', 2)], [('PROVIDER_REQUIRED', 2)]), side)
            self.assertEqual([k for p in self.made['proposals'][side] if p['kind'] == 'BLOCKED_AGAIN' for k in p if k == 'short'], [], side)


class Rule(unittest.TestCase):
    def test_c1_a_row_on_finances_yes_is_refused_in_words_that_say_whose_fact_it_is_and_nothing_is_sealed_or_paid(self):
        run = desk([REFUND], [BOOK], DESKS)
        head, budget, slots = run.head(), dict(run.state.budget), dict(run.state.providers)
        self.assertEqual(words(lambda: run.add('event', {'row': row('refund_approved_by_finance', 'TRUE', BOOK, 'v'), 'execute': True})),
                         gives('refund_approved_by_finance', FINANCE + ', as the answer to the question of ' + ASK, BOOK))
        self.assertEqual((run.head(), dict(run.state.budget), dict(run.state.providers), run.stopped), (head, budget, slots, False))
        self.assertEqual(statuses(event(run, row('refund_due', 'TRUE', BOOK, 'loan L-17, instalment 7'))), [('refund_sent', 'WAITING')])   # the run goes on
        self.assertEqual([a['issued']['ask']['to'] for a in open_asks(run.state).values()], [FINANCE])

    def test_c1_a_row_on_what_a_step_makes_and_on_another_checkers_fact_is_refused(self):
        run = desk([REFUND], [BOOK], DESKS)
        self.assertEqual(words(lambda: run.add('event', {'row': row('refund_sent', 'TRUE', BOOK, 'v'), 'execute': True})), gives('refund_sent', 'the step ' + SEND + ', whose receipt makes it', BOOK))
        batch = desk([LANDING], [RECON, POSTING], BATCH)
        self.assertEqual(words(lambda: batch.add('event', {'row': row('batch_reconciled', 'TRUE', POSTING, 'v'), 'execute': True})),
                         gives('batch_reconciled', RECON + ', as the check of ' + RUN_RECON, POSTING))

    def test_c1_a_fact_two_methods_make_is_given_to_both_and_the_words_name_both(self):
        run = desk([LANDING, second_way()], [RECON, POSTING, BOOK], BATCH)
        self.assertEqual(words(lambda: run.add('event', {'row': row('batch_reconciled', 'TRUE', BOOK, 'v'), 'execute': True})),
                         gives('batch_reconciled', RECON + ', as the check of ' + RUN_RECON + ' and ' + AUDIT + ', as the check of door-test-reconcile-by-person@1', BOOK))

    def test_c1_a_method_that_is_not_approved_gives_its_fact_to_no_one_and_nothing_is_paid(self):
        unapproved = {'schema': 'sutra-extension/2', 'id': 'door-test-unapproved-ask', 'grants': ['action:door-test-ask-the-book@1'], 'providers': {'book-channel': 1},
                      'methods': [dict(method('door-test-ask-the-book@1', 'refund_approved_by_finance', [], provider='book-channel', cost={'attention': 1}, action='ask',
                                              ask_to=BOOK, question='May the desk send the refund?'), approved=False)]}
        run = desk([REFUND, unapproved], [BOOK], DESKS)
        self.assertEqual(words(lambda: run.add('event', {'row': row('refund_approved_by_finance', 'TRUE', BOOK, 'v'), 'execute': True})),
                         gives('refund_approved_by_finance', FINANCE + ', as the answer to the question of ' + ASK + ' and no one through door-test-ask-the-book@1, which is not approved', BOOK))
        self.assertEqual(statuses(event(run, row('refund_due', 'TRUE', BOOK, 'v'))), [('refund_sent', 'WAITING')])
        self.assertEqual((run.state.budget['money'], [a['issued']['ask']['to'] for a in open_asks(run.state).values()]), (3, [FINANCE]))

    def test_c2_a_checkers_row_is_taken_only_as_the_check_of_the_try_that_is_out_and_the_plan_keeps_its_order(self):
        run = desk([LANDING], [RECON, POSTING], BATCH)
        self.assertEqual(words(lambda: run.add('event', {'row': row('batch_reconciled', 'TRUE', RECON, 'v'), 'execute': True})), no_work('batch_reconciled', RECON, [RUN_RECON]))
        self.assertEqual(words(lambda: run.add('event', {'row': row('batch_posted', 'TRUE', POSTING, 'v', checks='0' * 64), 'execute': True})), no_work('batch_posted', POSTING, [POST]))
        self.assertEqual(statuses(look(run)), [('refund_batch_landed', 'WAITING')])   # the reconciliation goes out first
        first = out(run, 'batch_reconciled')
        self.assertEqual(statuses(event(run, row('batch_reconciled', 'FALSE', RECON, 'c1', checks=first, why='two refunds do not match'))), [('refund_batch_landed', 'WAITING')])
        second = out(run, 'batch_reconciled')
        self.assertEqual(words(lambda: run.add('event', {'row': row('batch_reconciled', 'TRUE', RECON, 'c2', checks=first), 'execute': True})),   # the first try is out no more
                         other_try('batch_reconciled', second, RUN_RECON, RECON, RECON))
        went = event(run, row('batch_reconciled', 'TRUE', RECON, 'c3', checks=second))
        self.assertEqual([x['method'] for x in went['runs'][0]['model_receipts']], [POST])   # then the posting
        closed = [e['data'] for e in went['runs'][0]['trace'] if e['operation'] == 'HANDOFF_CLOSED']
        self.assertEqual([(c['receipt'], c['confirmed']) for c in closed], [(second, True)])
        self.assertEqual(statuses(event(run, row('batch_posted', 'TRUE', POSTING, 'c4', checks=out(run, 'batch_posted')))), [('refund_batch_landed', 'SUPPORTED_BY_EVIDENCE')])

    def test_c2_the_trys_own_checker_naming_no_receipt_or_another_scope_and_another_checker_naming_the_receipt_are_refused(self):
        run = desk([LANDING, second_way()], [RECON, POSTING, AUDIT], BATCH)
        look(run)
        receipt, books = out(run, 'batch_reconciled'), run.state.active_work['handoff'][run.state.key('batch_reconciled')]
        self.assertEqual((books['method'], books['checker']), (RUN_RECON, RECON))   # the reconciliation script's try is out, checked by the ledger
        self.assertEqual(words(lambda: run.add('event', {'row': row('batch_reconciled', 'TRUE', RECON, 'c'), 'execute': True})),   # its own checker, no receipt named
                         other_try('batch_reconciled', receipt, RUN_RECON, RECON, RECON))
        self.assertEqual(words(lambda: run.add('event', {'row': row('batch_reconciled', 'TRUE', AUDIT, 'c', checks=receipt), 'execute': True})),   # the checker of the other way
                         other_try('batch_reconciled', receipt, RUN_RECON, RECON, AUDIT))
        self.assertEqual(words(lambda: run.add('event', {'row': row('batch_reconciled', 'TRUE', RECON, 'c', checks=receipt, scope='lendco/other-batches'), 'execute': True})),
                         no_work('batch_reconciled', RECON, [RUN_RECON]))   # the receipt, in a scope where no work is out
        self.assertEqual((out(run, 'batch_reconciled'), run.state.fact('batch_reconciled')['truth'], len(run.journal)), (receipt, 'UNKNOWN', 4))   # nothing was sealed

    def test_c2_a_checker_that_a_question_on_the_fact_is_put_to_is_held_to_the_try_first(self):
        asked = {'schema': 'sutra-extension/2', 'id': 'door-test-ask-the-ledger', 'grants': ['action:door-test-ask-the-ledger@1'], 'providers': {'ledger-channel': 1},
                 'methods': [method('door-test-ask-the-ledger@1', 'batch_reconciled', ['batch_rehearsed'], provider='ledger-channel', cost={'attention': 1}, action='ask',
                                    ask_to=RECON, question='Is refund batch 2026-11 reconciled?')]}
        run = desk([LANDING, asked], [RECON, POSTING], ['simulate_fact', 'handoff', 'ask'])
        self.assertEqual(words(lambda: run.add('event', {'row': row('batch_reconciled', 'TRUE', RECON, 'v'), 'execute': True})), no_work('batch_reconciled', RECON, [RUN_RECON]))
        self.assertEqual([x['method'] for x in look(run)['runs'][0]['model_receipts']], [RUN_RECON])   # the reconciliation goes out first
        went = event(run, row('batch_reconciled', 'TRUE', RECON, 'c1', checks=out(run, 'batch_reconciled')))
        self.assertEqual([x['method'] for x in went['runs'][0]['model_receipts']], [POST])

    def test_c2_after_the_kind_closed_the_try_a_row_of_its_checker_is_refused(self):
        run = desk([LANDING], [RECON, POSTING], BATCH)
        look(run)
        receipt = out(run, 'batch_reconciled')
        event(run, row('batch_reconciled', 'TRUE', RECON, 'c1', checks=receipt))
        self.assertIsNone(out(run, 'batch_reconciled'))
        for again in (row('batch_reconciled', 'TRUE', RECON, 'c1'), row('batch_reconciled', 'TRUE', RECON, 'c1', checks=receipt)):   # the same confirmation twice, with and without its receipt
            self.assertEqual(words(lambda: run.add('event', {'row': again, 'execute': True})), no_work('batch_reconciled', RECON, [RUN_RECON]))

    def test_c3_the_door_is_written_into_the_sealed_header_and_a_journal_without_it_keeps_the_door_it_was_made_under(self):
        self.assertEqual(J.start(DESKS, [BOOK], name='a', door='plan').journal[0]['body'], {'kinds': DESKS, 'checkers': [BOOK], 'name': 'a', 'door': 'plan'})
        self.assertEqual(J.start(DESKS, [BOOK], name='a').journal[0]['body'], {'kinds': DESKS, 'checkers': [BOOK], 'name': 'a'})
        old = desk([REFUND], [BOOK], DESKS, door='')
        event(old, row('refund_approved_by_finance', 'TRUE', BOOK, 'v'))
        self.assertEqual(statuses(event(old, row('refund_due', 'TRUE', BOOK, 'v'))), [('refund_sent', 'LOCAL_MODEL_EFFECTS_RECORDED')])
        again = J.replay(J.parse(kept(old)[0][0]), kept(old)[0][1])   # and it replays: the rule is read from the header it was sealed under
        self.assertEqual(again.head(), kept(old)[0][1])

    def test_c3_the_rule_holds_at_replay_a_text_under_the_door_that_holds_a_refused_row_does_not_replay(self):
        old = desk([REFUND], [BOOK], DESKS, door='', name='forged')
        event(old, row('refund_approved_by_finance', 'TRUE', BOOK, 'v'))
        entries = J.parse(kept(old)[0][0])
        entries[0]['body']['door'] = 'plan'   # the same text with the door written into its header, the chain made whole again
        forged = rechained(entries)
        self.assertEqual(words(lambda: J.replay(forged, {'length': len(forged), 'sha256': forged[-1]['sha256']})),
                         'The journal does not replay at entry 2: ' + gives('refund_approved_by_finance', FINANCE + ', as the answer to the question of ' + ASK, BOOK))

    def test_c4_a_journal_that_continues_one_under_the_door_is_under_it_too(self):
        first, keep = desk([REFUND], [BOOK], DESKS, name='desk-1'), J.Keep()
        J.save(first, keep)
        head = dict(keep.head)
        self.assertEqual(words(lambda: J.start(DESKS, [BOOK], name='desk-2', continues=first, keep=keep)), UNDER)
        self.assertEqual((first.closed, first.stopped, keep.head), (False, False, head))   # nothing was sealed or kept
        second = J.start(DESKS, [BOOK], name='desk-2', continues=first, keep=keep, door='plan')
        self.assertEqual(second.journal[0]['body']['door'], 'plan')
        self.assertEqual(words(lambda: second.add('event', {'row': row('refund_sent', 'TRUE', BOOK, 'v'), 'execute': True})), gives('refund_sent', 'the step ' + SEND + ', whose receipt makes it', BOOK))
        older, keep2 = desk([REFUND], [BOOK], DESKS, door='', name='old-1'), J.Keep()   # a journal made as before may be continued under the door
        J.save(older, keep2)
        self.assertEqual(J.start(DESKS, [BOOK], name='old-2', continues=older, keep=keep2, door='plan').journal[0]['body']['door'], 'plan')

    def test_c4_a_text_whose_closing_entry_drops_the_door_does_not_replay(self):
        run = desk([REFUND], [BOOK], DESKS, name='closing')
        forged = closing(run, {'kinds': DESKS, 'checkers': [BOOK], 'name': 'next'})
        self.assertEqual(words(lambda: J.replay(forged, {'length': len(forged), 'sha256': forged[-1]['sha256']})), 'The journal does not replay at entry 2: ' + UNDER)

    def test_c5_the_record_adapter_reads_a_journal_under_the_door_and_refuses_a_header_with_another_door(self):
        run = desk([REFUND], [BOOK], DESKS, name='read')
        event(run, row('refund_due', 'TRUE', BOOK, 'v'))
        [(text, head)] = kept(run)
        self.assertEqual([r['what'] for r in R.ledger([(text, head)])], ['handed_in', 'handed_in', 'ran', 'asked'])
        self.assertEqual(R.counts([(text, head)])['goals']['lendco/refund-desk|refund_sent']['statuses'], {'WAITING': 1})
        entries = J.parse(text)
        entries[0]['body']['door'] = 'open'
        forged = rechained(entries)
        self.assertEqual(words(lambda: R.ledger([(J.dump(forged), {'length': len(forged), 'sha256': forged[-1]['sha256']})])), 'The journal is broken at entry 0')

    def test_c5_a_chain_under_the_door_is_read_whole_and_a_closing_entry_with_another_door_is_broken(self):
        first, keep = desk([REVIEW], [NOTES], AGENT, name='review-1'), J.Keep()
        look(first)
        second, keep2 = J.start(AGENT, [NOTES], name='review-2', continues=first, keep=keep, door='plan'), J.Keep()
        look(second)
        J.save(second, keep2)
        chain = [keep.read(), keep2.read()]
        ran = [r for r in R.ledger(chain) if r['what'] == 'ran']
        self.assertEqual([(r['journal'], r['status'], r['short']) for r in ran], [(R.record(chain)[0]['journal'], 'PROVIDER_REQUIRED', [REVIEWER]),
                                                                                 (R.record(chain)[1]['journal'], 'PROVIDER_REQUIRED', [REVIEWER])])
        self.assertEqual(R.counts(chain)['goals']['lendco/file-review|loan_file_reviewed']['statuses'], {'PROVIDER_REQUIRED': 2})
        self.assertEqual([(p['kind'], p['times']) for p in learn.proposals([chain], 2)], [('BLOCKED_AGAIN', 2)])
        self.assertEqual(reader.proposals(chain, 2), [])   # read whole; a blocked run is passed over by the reader
        third = desk([REFUND], [BOOK], DESKS, name='closing-2')
        for door, broken in (('plan', False), ('open', True)):
            forged = closing(third, {'kinds': DESKS, 'checkers': [BOOK], 'name': 'next', 'door': door})
            text, head = J.dump(forged), {'length': len(forged), 'sha256': forged[-1]['sha256']}
            self.assertEqual(words(lambda: R.ledger([(text, head)])), 'The journal is broken at entry 2' if broken else None, door)

    def test_c7_a_run_that_goes_another_way_names_no_doer_though_the_gate_turned_a_way_away_for_want_of_a_place(self):
        ways = {'schema': 'sutra-extension/2', 'id': 'door-test-two-ways', 'scope': 'lendco/letters', 'goals': ['arrears_letter_sent'],
                'budget': {'compute': 5, 'money': 5, 'attention': 0}, 'preference': ['money', 'compute', 'attention'],
                'methods': [method('door-test-letter-by-clerk@1', 'arrears_letter_sent', [], provider='letter-clerk', cost={'compute': 0, 'money': 1}),
                            method('door-test-letter-by-post@1', 'arrears_letter_sent', [], provider='post-desk', cost={'compute': 1, 'money': 2})],
                'providers': {'post-desk': 1}, 'grants': ['action:door-test-letter-by-clerk@1', 'action:door-test-letter-by-post@1']}
        run = desk([ways], [NOTES], DESKS)
        went = look(run)
        self.assertEqual((statuses(went), [x['method'] for x in went['runs'][0]['model_receipts']]),
                         ([('arrears_letter_sent', 'LOCAL_MODEL_EFFECTS_RECORDED')], ['door-test-letter-by-post@1']))
        self.assertEqual([e['data']['blockers'] for e in went['runs'][0]['trace'] if e['operation'] == 'ADMISSION'][0], ['PROVIDER_REQUIRED'])   # the clerk's way, turned away
        self.assertEqual(['short' in b for b in run.journal[-1]['result']['briefs']], [False])

    def test_c7_the_brief_counts_the_places_an_earlier_run_of_the_same_look_spent_and_names_no_doer_that_has_enough(self):
        two = {'schema': 'sutra-extension/2', 'id': 'door-test-two-notices', 'scope': 'lendco/notices', 'goals': ['notice_a_sent', 'notice_b_sent'],
               'budget': {'compute': 4, 'money': 0, 'attention': 0}, 'preference': ['compute', 'money', 'attention'],
               'methods': [method('door-test-send-notice-a@1', 'notice_a_sent', [], provider='notice-desk', cost={'compute': 1}),
                           method('door-test-send-notice-b@1', 'notice_b_sent', [], provider='notice-desk', cost={'compute': 1})],
               'providers': {'notice-desk': 1}, 'grants': ['action:door-test-send-notice-a@1', 'action:door-test-send-notice-b@1']}
        run = desk([two], [NOTES], DESKS)
        books = Q.books(run.state)
        looked = look(run)
        self.assertEqual(statuses(looked), [('notice_a_sent', 'LOCAL_MODEL_EFFECTS_RECORDED'), ('notice_b_sent', 'PROVIDER_REQUIRED')])
        briefs = run.journal[-1]['result']['briefs']
        short = [{'doer': 'notice-desk', 'has': 0, 'needs': 1, 'steps': ['door-test-send-notice-b@1']}]   # the first run spent the one place
        self.assertEqual([b.get('short') for b in briefs], [None, short])
        self.assertEqual(said(short), [f['value'] for d in Q.decisions(looked['runs'], books) for f in d['factors'] if f['type'] == 'provider_short'])

    # Added when the confirming review round was settled (rulings R19 and R34 of the program: no new code). Each test below pins what the
    # door does today where the recorded sequence holds no such move, and each changes its outcome under one mutant the round showed alive.
    def test_c1_a_dry_row_and_a_row_that_reads_unknown_are_held_to_the_plan_too(self):
        run = desk([REFUND], [BOOK], DESKS)   # a dry row of the loan book on finance's yes is refused as an executed one is
        self.assertEqual(words(lambda: run.add('event', {'row': row('refund_approved_by_finance', 'TRUE', BOOK, 'v'), 'execute': False})),
                         gives('refund_approved_by_finance', FINANCE + ', as the answer to the question of ' + ASK, BOOK))
        self.assertEqual(statuses(event(run, row('refund_due', 'TRUE', BOOK, 'v'))), [('refund_sent', 'WAITING')])   # so the row after it pays nothing
        self.assertEqual((run.state.budget['money'], [a['issued']['ask']['to'] for a in open_asks(run.state).values()]), (3, [FINANCE]))
        payouts = desk([PAYOUTS], [BOOK], DESKS)   # a row that reads UNKNOWN on a step's fact is refused too, and the step is not paid again
        self.assertEqual([x['method'] for x in event(payouts, row('payout_due', 'TRUE', BOOK, 'loan 101'))['runs'][0]['model_receipts']],
                         ['door-check-payee@1', 'door-pay@1', 'door-reconcile@1'])
        self.assertEqual(words(lambda: payouts.add('event', {'row': row('payout_paid', 'UNKNOWN', BOOK, 'loan 101, not said yet'), 'execute': True})),
                         gives('payout_paid', 'the step door-pay@1, whose receipt makes it', BOOK))
        self.assertEqual((payouts.state.budget['money'], payouts.state.fact('payout_paid')['truth']), (5, 'TRUE'))

    def test_c1_a_method_without_the_key_approved_gives_its_fact_as_the_kernel_runs_it(self):
        bare = pack(REFUND)   # the refund desk with the key `approved` taken out of every method: the kernel runs such a method
        bare['id'] = 'door-test-desk-without-the-key-approved'
        for m in bare['methods']:
            m.pop('approved')
        run = desk([bare], [BOOK, FINANCE], DESKS)
        self.assertEqual(statuses(event(run, row('refund_due', 'TRUE', BOOK, 'v'))), [('refund_sent', 'WAITING')])
        self.assertEqual(words(lambda: run.add('event', {'row': row('refund_approved_by_finance', 'TRUE', BOOK, 'v'), 'execute': True})),
                         gives('refund_approved_by_finance', FINANCE + ', as the answer to the question of ' + ASK, BOOK))
        self.assertEqual(statuses(event(run, row('refund_approved_by_finance', 'TRUE', FINANCE, 'v'))), [('refund_sent', 'LOCAL_MODEL_EFFECTS_RECORDED')])
        self.assertEqual(run.state.budget['money'], 2)

    def test_c7_a_doer_with_exactly_its_places_is_not_named_and_has_is_the_count_when_the_gate_was_asked(self):
        exact = notice_desk('door-test-notice-exact', ['arrears_notice_sent'], [notice_step('door-test-draft-notice@1', 'notice_drafted', [], 'draft-desk'),
                            notice_step('door-test-post-notice@1', 'arrears_notice_sent', ['notice_drafted'], 'post-desk')], {'draft-desk': 1})
        run = desk([exact], [NOTES], DESKS)
        self.assertEqual(statuses(look(run)), [('arrears_notice_sent', 'PROVIDER_REQUIRED')])
        self.assertEqual([b.get('short') for b in run.journal[-1]['result']['briefs']],   # the draft desk has the one place the plan needs of it: not named
                         [[{'doer': 'post-desk', 'has': 0, 'needs': 1, 'steps': ['door-test-post-notice@1']}]])
        spent = notice_desk('door-test-notice-spent', ['notice_a_sent', 'notice_b_sent'], [notice_step('door-test-draft-a@1', 'notice_a_drafted', [], 'notice-desk'),
                            notice_step('door-test-send-a@1', 'notice_a_sent', ['notice_a_drafted'], 'notice-desk'),
                            notice_step('door-test-send-b@1', 'notice_b_sent', [], 'notice-desk')], {'notice-desk': 1})
        run = desk([spent], [NOTES], DESKS)
        self.assertEqual(statuses(look(run)), [('notice_a_sent', 'PROVIDER_REQUIRED'), ('notice_b_sent', 'LOCAL_MODEL_EFFECTS_RECORDED')])
        self.assertEqual([b.get('short') for b in run.journal[-1]['result']['briefs']],   # the second goal spent the place after the gate turned the first away
                         [[{'doer': 'notice-desk', 'has': 1, 'needs': 2, 'steps': ['door-test-draft-a@1', 'door-test-send-a@1']}], None])
        self.assertEqual(run.state.providers['notice-desk'], 0)

    def test_c7_a_doer_short_in_two_ways_of_a_run_is_named_once_for_each_way(self):
        ways = notice_desk('door-test-notice-two-ways', ['arrears_notice_sent'], [notice_step('door-test-notice-by-post@1', 'notice_posted', [], 'notice-desk'),
                           notice_step('door-test-notice-by-mail@1', 'notice_mailed', [], 'notice-desk')], {},
                           rules=[{'id': 'R-DOOR-TEST-NOTICE@1', 'head': 'arrears_notice_sent', 'branches': [['notice_posted'], ['notice_mailed']], 'approved': True,
                                   'source': 'the desk: a notice is sent by post or by mail'}])
        run = desk([ways], [NOTES], DESKS)
        self.assertEqual(statuses(look(run)), [('arrears_notice_sent', 'PROVIDER_REQUIRED')])
        self.assertEqual([b.get('short') for b in run.journal[-1]['result']['briefs']],
                         [[{'doer': 'notice-desk', 'has': 0, 'needs': 1, 'steps': ['door-test-notice-by-post@1']},
                           {'doer': 'notice-desk', 'has': 0, 'needs': 1, 'steps': ['door-test-notice-by-mail@1']}]])

    def test_c7_a_run_stopped_for_want_of_a_grant_and_of_a_place_names_the_short_doer(self):
        bare = notice_desk('door-test-notice-no-grant', ['arrears_notice_sent'], [notice_step('door-test-post-notice-unheld@1', 'arrears_notice_sent', [], 'post-desk')], {},
                           grants=[])
        run = desk([bare], [NOTES], DESKS)
        self.assertEqual(statuses(look(run)), [('arrears_notice_sent', 'AUTHORITY_REQUIRED')])   # the status word says the grant; the stop reasons say both
        self.assertEqual([(b['stop_reasons'], b['short']) for b in run.journal[-1]['result']['briefs']],
                         [(['AUTHORITY_REQUIRED', 'PROVIDER_REQUIRED'], [{'doer': 'post-desk', 'has': 0, 'needs': 1, 'steps': ['door-test-post-notice-unheld@1']}])])


def second_way():   # a second way to reconcile the batch: by a person, checked by the audit (a pack made in memory)
    return {'schema': 'sutra-extension/2', 'id': 'door-test-second-way', 'grants': ['action:door-test-reconcile-by-person@1'], 'providers': {'person:reconciler': 1},
            'methods': [method('door-test-reconcile-by-person@1', 'batch_reconciled', ['batch_rehearsed'], provider='person:reconciler', cost={'runs': 1}, action='handoff',
                               handoff_to='person:reconciler', instruction='Reconcile the batch by hand.', verified_by=AUDIT)]}


def notice_step(id, effect, requires, doer):   # one step of a notices desk of the tests, done by `doer`
    return method(id, effect, requires, provider=doer, cost={'compute': 1})


def notice_desk(id, goals, steps, places, rules=(), grants=None):   # a notices desk of the tests (a pack made in memory); every step's grant is held unless `grants` says
    return {'schema': 'sutra-extension/2', 'id': id, 'scope': 'lendco/notices', 'goals': goals, 'rules': list(rules), 'methods': steps, 'providers': places,
            'grants': ['action:' + m['id'] for m in steps] if grants is None else grants, 'budget': {'compute': 9, 'money': 9, 'attention': 9},
            'preference': ['compute', 'money', 'attention']}


class Cases(unittest.TestCase):
    def test_163_five_pieces_of_work_for_a_reviewer_with_one_place(self):
        r = Kernel(State.from_packs([pack(REVIEW)])).run_standing(execute=True)['runs'][0]
        self.assertEqual((r['status'], r['stop_reasons'], r['model_receipts']), ('PROVIDER_REQUIRED', ['PROVIDER_REQUIRED'], []))
        self.assertIn(('163_door_file_review_short', 'Five pieces of work for a reviewer with one place'), [c[:2] for c in CASES])

    def test_164_the_reconciliation_goes_out_first(self):
        r = Kernel(State.from_packs([pack(LANDING)])).run_standing(execute=True)['runs'][0]
        self.assertEqual((r['status'], [x['method'] for x in r['model_receipts']], r['pending']), ('WAITING', [RUN_RECON], [POST]))
        self.assertIn(('164_door_batch_in_order', 'A refund batch: the reconciliation goes out first'), [c[:2] for c in CASES])


class Existing(unittest.TestCase):
    """What the parts the lab had make of N1, N2 and N3 (ruling R35): the event door as it was is the before of the sequence; here the one
    form 0.36.0-sources found to hold a fact to its source (every fact asked, a header that names no checker) and its end, and the
    decision-provenance rows of 0.17.0, which name the doer that is short only when a caller hands them a replayed run and its books."""
    def test_existing_n1_every_fact_asked_with_no_checker_named_holds_the_yes_and_cannot_say_a_fact_again(self):
        ask_book = {'schema': 'sutra-extension/2', 'id': 'door-test-ask-the-book', 'grants': ['action:door-test-ask-loan-book@1'], 'providers': {'book-channel': 2},
                    'methods': [method('door-test-ask-loan-book@1', 'refund_due', [], provider='book-channel', cost={'compute': 0, 'money': 0, 'attention': 1}, action='ask',
                                       ask_to=BOOK, question='Is a refund due on loan L-17, instalment 7?')]}
        run = desk([REFUND, ask_book], [], DESKS, door='')
        self.assertEqual(words(lambda: run.add('event', {'row': row('refund_approved_by_finance', 'TRUE', BOOK, 'v'), 'execute': True})), EVENT_DOOR)   # no row enters
        asked = lambda: [a['issued'] for a in open_asks(run.state).values()]
        look(run)
        [due] = asked()
        run.add('answer', {'receipt': due, 'truth': 'TRUE', 'source': BOOK, 'execute': True})
        [yes] = asked()
        went = run.detail[run.add('answer', {'receipt': yes, 'truth': 'TRUE', 'source': FINANCE, 'execute': True})['seq']]
        self.assertEqual(statuses(went), [('refund_sent', 'LOCAL_MODEL_EFFECTS_RECORDED')])
        # the payment bounces: the loan book cannot say so, neither as a row nor as a second answer
        self.assertEqual(words(lambda: run.add('event', {'row': row('refund_due', 'FALSE', BOOK, 'bounced'), 'execute': True})), EVENT_DOOR)
        self.assertIsNotNone(words(lambda: run.add('answer', {'receipt': due, 'truth': 'FALSE', 'source': BOOK, 'execute': True})))
        self.assertEqual(run.state.fact('refund_due')['truth'], 'TRUE')

    def test_existing_n2_a_header_that_names_no_checker_takes_no_check_and_the_work_never_closes(self):
        run = desk([LANDING], [], BATCH, door='')
        look(run)
        self.assertEqual(words(lambda: run.add('event', {'row': row('batch_reconciled', 'TRUE', RECON, 'c', checks=out(run, 'batch_reconciled')), 'execute': True})), EVENT_DOOR)
        self.assertIsNotNone(out(run, 'batch_reconciled'))

    def test_existing_n3_the_projection_of_0_17_0_names_the_short_doer_only_of_a_look_replayed_by_hand_with_its_books(self):
        run = desk([REVIEW], [NOTES], AGENT, door='')
        look(run)
        [(text, head)] = kept(run)
        entries = J.parse(text)
        books = Q.books(J.replay(entries[:2], {'length': 2, 'sha256': entries[1]['sha256']}).state)   # the books before the look, as the journal replays them
        runs = J.replay(entries, head).detail[2]['runs']                                               # the look's run, replayed
        self.assertEqual([[f['value'] for f in d['factors'] if f['type'] == 'provider_short'] for d in Q.decisions(runs, books)], [['agent:file-reviewer: needs 5, has 1']])
        self.assertEqual([(r['status'], set(r) - LEDGER_KEYS) for r in R.ledger([(text, head)]) if r['what'] == 'ran'], [('PROVIDER_REQUIRED', set())])   # what the journal keeps names no doer
        for f in ('extensions/journal.py', 'extensions/journal_record.py', 'extensions/learn.py'):   # and neither the journal, its record adapter nor the learn feature calls the projection
            self.assertNotIn('queue_provenance', (ROOT / f).read_text(), f)

    def test_existing_n3_the_words_of_the_hand_over_say_that_every_try_takes_a_place_and_none_comes_back(self):
        told = ' '.join((ROOT / 'kinds' / 'handoff.py').read_text().split())
        self.assertIn("The kernel takes a slot for every try and returns none, so the capacity a pack states for the hand's provider is the number of tries.", told)


class Limits(unittest.TestCase):
    def test_l1_a_journal_started_as_before_takes_the_loan_books_yes_and_sends_the_refund(self):
        run = desk([REFUND], [BOOK], DESKS, door='')
        self.assertEqual(J.start(DESKS, [BOOK]).journal[0]['body'], {'kinds': DESKS, 'checkers': [BOOK]})   # start() as the conductor and the UI call it: no door
        event(run, row('refund_due', 'TRUE', BOOK, 'v'))
        self.assertEqual(statuses(event(run, row('refund_approved_by_finance', 'TRUE', BOOK, 'v'))), [('refund_sent', 'LOCAL_MODEL_EFFECTS_RECORDED')])
        self.assertEqual(run.state.budget['money'], 2)
        blocked = desk([REVIEW], [NOTES], AGENT, door='')
        look(blocked)
        self.assertEqual([(b['status'], 'short' in b) for b in blocked.journal[-1]['result']['briefs']], [('PROVIDER_REQUIRED', False)])   # and a run that stops for want of a place names no doer

    def test_l2_the_pack_door_takes_any_row_also_under_the_plan_door(self):
        rows = {'schema': 'sutra-extension/2', 'id': 'door-test-rows-in-a-pack', 'evidence': [row('refund_due', 'TRUE', BOOK, 'v'), row('refund_approved_by_finance', 'TRUE', BOOK, 'v')]}
        run = desk([REFUND, rows], [BOOK], DESKS)
        self.assertEqual(statuses(look(run)), [('refund_sent', 'LOCAL_MODEL_EFFECTS_RECORDED')])

    def test_l3_a_fact_no_method_makes_a_rules_head_too_is_given_to_nobody(self):
        run = desk([LANDING], [RECON, POSTING], BATCH)
        landed = event(run, row('refund_batch_landed', 'TRUE', POSTING, 'stated by the log'))
        self.assertEqual((statuses(landed), landed['runs'][0]['model_receipts']), ([('refund_batch_landed', 'SUPPORTED_BY_EVIDENCE')], []))
        self.assertEqual([p['kind'] for p in learn.proposals([kept(run)], 2)], [])

    def test_l4_the_party_a_question_is_put_to_may_state_its_fact_at_the_event_door(self):
        run = desk([REFUND], [BOOK, FINANCE], DESKS)
        event(run, row('refund_due', 'TRUE', BOOK, 'v'))
        self.assertEqual(statuses(event(run, row('refund_approved_by_finance', 'TRUE', FINANCE, 'v'))), [('refund_sent', 'LOCAL_MODEL_EFFECTS_RECORDED')])
        self.assertEqual(len(open_asks(run.state)), 1)   # its question is still out: no answer came

    def test_l5_the_check_of_the_try_that_is_out_is_taken_whatever_it_reads_also_after_a_failed_check_with_no_new_work(self):
        run = desk([LANDING], [RECON, POSTING], BATCH)
        look(run)
        first = out(run, 'batch_reconciled')
        event(run, row('batch_reconciled', 'UNKNOWN', RECON, 'c0', checks=first))   # taken; the kind does not read it as a check and waits
        self.assertEqual(out(run, 'batch_reconciled'), first)
        event(run, row('batch_reconciled', 'FALSE', RECON, 'c1', checks=first, why='timed out'))
        second = out(run, 'batch_reconciled')
        stopped = event(run, row('batch_reconciled', 'FALSE', RECON, 'c2', checks=second, why='timed out'))
        self.assertEqual(statuses(stopped), [('refund_batch_landed', 'PROVIDER_REQUIRED')])   # no place for a third try
        went = event(run, row('batch_reconciled', 'TRUE', RECON, 'c3', checks=second))   # the failed try turned true, no new work (N4, left for the owner)
        self.assertEqual([x['method'] for x in went['runs'][0]['model_receipts']], [POST])

    def test_l6_after_the_kind_closed_a_try_its_checker_cannot_take_the_work_back_or_confirm_it_again_with_a_row(self):
        run = desk([LANDING], [RECON, POSTING], BATCH)
        look(run)
        receipt = out(run, 'batch_reconciled')
        event(run, row('batch_reconciled', 'TRUE', RECON, 'c1', checks=receipt))
        self.assertEqual(words(lambda: run.add('event', {'row': row('batch_reconciled', 'FALSE', RECON, 'c2', checks=receipt, why='a refund was missed'), 'execute': True})),
                         no_work('batch_reconciled', RECON, [RUN_RECON]))
        self.assertEqual(words(lambda: run.add('event', {'row': row('batch_reconciled', 'TRUE', RECON, 'c3, after an edit of the work', checks=receipt), 'execute': True})),
                         no_work('batch_reconciled', RECON, [RUN_RECON]))   # a check again of work edited after it was confirmed
        self.assertEqual(run.state.fact('batch_reconciled')['truth'], 'TRUE')

    def test_l7_a_row_on_an_earlier_receipt_while_a_later_try_is_out_is_refused(self):
        run = desk([LANDING], [RECON, POSTING], BATCH)
        look(run)
        first = out(run, 'batch_reconciled')
        event(run, row('batch_reconciled', 'FALSE', RECON, 'c1', checks=first, why='timed out'))
        second = out(run, 'batch_reconciled')
        self.assertEqual(words(lambda: run.add('event', {'row': row('batch_reconciled', 'FALSE', RECON, 'late copy', checks=first), 'execute': True})),
                         other_try('batch_reconciled', second, RUN_RECON, RECON, RECON))

    def test_l8_a_method_that_is_not_approved_still_holds_its_fact_and_a_later_method_does_not_reach_back(self):
        unapproved = {'schema': 'sutra-extension/2', 'id': 'door-test-unapproved', 'grants': ['action:door-test-book-step@1'],
                      'methods': [dict(method('door-test-book-step@1', 'refund_due', [], provider='refund-desk', cost={'compute': 0, 'money': 1, 'attention': 0}), approved=False)]}
        run = desk([REFUND, unapproved], [BOOK], DESKS)
        self.assertEqual(words(lambda: run.add('event', {'row': row('refund_due', 'TRUE', BOOK, 'v'), 'execute': True})),
                         gives('refund_due', 'no one through door-test-book-step@1, which is not approved', BOOK))
        before = desk([REFUND], [BOOK], DESKS)
        event(before, row('refund_due', 'TRUE', BOOK, 'v'))
        before.add('pack', {'pack': unapproved})   # a method that a later pack brings does not reach back to a row already let in
        self.assertEqual(before.state.fact('refund_due')['source'], BOOK)

    def test_l9_the_header_doors_words_name_no_door(self):
        for bad in ('open', True, ['plan']):
            self.assertEqual(words(lambda: J.start(DESKS, [BOOK], door=bad)), HEADER)

    def test_l10_no_check_module_reads_the_doors_and_a_refused_move_holds_no_run(self):
        book = json.loads((ROOT / 'added.json').read_text())
        [mine] = [a for a in book['applied'] if a['label'] == '0.21.0-doors']
        self.assertEqual([f for f in mine['files'] if f.startswith('qa/')], [])
        made = sequence()
        refused = [s for side in ('before', 'after') for k in made[side].values() for s in k['steps'] if 'refused' in s]
        self.assertEqual((len(refused), {frozenset(s) for s in refused}), (12, {frozenset({'move', 'refused'})}))

    # Added when the confirming review round was settled (rulings R19 and R34 of the program: no new code): limits stated in the passage,
    # each pinned as the door behaves today.
    def test_l4_the_asked_party_may_state_its_fact_before_its_question_is_out_and_while_a_hand_over_try_on_it_is_out(self):
        run = desk([REFUND], [BOOK, FINANCE], DESKS)   # finance's row before its question is out: no question on its yes was put yet
        self.assertEqual(statuses(event(run, row('refund_approved_by_finance', 'TRUE', FINANCE, 'v'))), [('refund_sent', 'QUERY_EVIDENCE')])
        went = event(run, row('refund_due', 'TRUE', BOOK, 'v'))
        self.assertEqual(([x['method'] for x in went['runs'][0]['model_receipts']], run.state.budget['money'], len(open_asks(run.state))), ([SEND], 2, 0))   # never asked
        controller = 'person:controller'   # an approved question on the batch's reconciliation is put to a controller, and the plan prefers the hand-over
        asked = {'schema': 'sutra-extension/2', 'id': 'door-test-ask-the-controller', 'grants': ['action:door-test-ask-the-controller@1'],
                 'providers': {'controller-channel': 1}, 'budget': {'attention': 1},
                 'methods': [method('door-test-ask-the-controller@1', 'batch_reconciled', ['batch_rehearsed'], provider='controller-channel', cost={'attention': 1, 'runs': 2},
                                    action='ask', ask_to=controller, question='Is refund batch 2026-11 reconciled?')]}
        batch = desk([LANDING, asked], [RECON, POSTING, controller], ['simulate_fact', 'handoff', 'ask'])
        self.assertEqual([x['method'] for x in look(batch)['runs'][0]['model_receipts']], [RUN_RECON])   # the reconciliation's try is out
        receipt = out(batch, 'batch_reconciled')
        went = event(batch, row('batch_reconciled', 'TRUE', controller, 'v'))   # the controller's row is taken while that try is out
        self.assertEqual([x['method'] for x in went['runs'][0]['model_receipts']], [POST])   # the posting goes out with no check of the reconciliation
        self.assertEqual([(c['data']['receipt'], c['data']['confirmed']) for c in went['runs'][0]['trace'] if c['operation'] == 'HANDOFF_CLOSED'], [(receipt, False)])
        self.assertEqual(words(lambda: batch.add('event', {'row': row('batch_reconciled', 'TRUE', RECON, 'c1', checks=receipt), 'execute': True})),
                         no_work('batch_reconciled', RECON, [RUN_RECON]))   # and the check of that try, naming its receipt, is refused

    def test_l8_an_approved_method_gives_its_fact_while_its_grant_its_budget_or_its_doers_place_is_missing(self):
        no_grant = pack(REFUND)   # the refund desk without the grant of finance's question: the yes is still finance's
        no_grant['id'], no_grant['grants'] = 'door-test-desk-without-the-grant', ['action:' + SEND]
        run = desk([no_grant], [BOOK], DESKS)
        self.assertEqual(words(lambda: run.add('event', {'row': row('refund_approved_by_finance', 'TRUE', BOOK, 'v'), 'execute': True})),
                         gives('refund_approved_by_finance', FINANCE + ', as the answer to the question of ' + ASK, BOOK))
        self.assertEqual((statuses(event(run, row('refund_due', 'TRUE', BOOK, 'v'))), run.state.budget['money']), ([('refund_sent', 'AUTHORITY_REQUIRED')], 3))
        held = ['action:door-test-ask-the-loan-book@1']   # an approved question on finance's yes put to the loan book, which the kernel cannot run
        for missing, more, first in (('grant', {}, 'WAITING'), ('budget', {'grants': held, 'budget': {'attention': 0}}, 'RESOURCE_REQUIRED'),
                                     ('place', {'grants': held, 'providers': {'book-channel': 0}}, 'WAITING')):
            book_asked = dict({'schema': 'sutra-extension/2', 'id': 'door-test-the-loan-book-asked-' + missing, 'providers': {'book-channel': 1},
                               'methods': [method('door-test-ask-the-loan-book@1', 'refund_approved_by_finance', [], provider='book-channel', cost={'attention': 1},
                                                  action='ask', ask_to=BOOK, question='May the desk send the refund?')]}, **more)
            run = desk([REFUND, book_asked], [BOOK], DESKS)
            self.assertEqual(statuses(event(run, row('refund_due', 'TRUE', BOOK, 'v'))), [('refund_sent', first)], missing)
            self.assertEqual(statuses(event(run, row('refund_approved_by_finance', 'TRUE', BOOK, 'v'))), [('refund_sent', 'LOCAL_MODEL_EFFECTS_RECORDED')], missing)
            self.assertEqual((run.state.budget['money'], [a['issued']['ask']['to'] for a in open_asks(run.state).values()]),
                             (2, [] if missing == 'budget' else [FINANCE]), missing)   # the refund is paid on the loan book's yes, while finance's question is out

    def test_l12_the_door_reads_a_method_that_is_not_approved_as_giving_its_fact_to_no_one_and_the_learn_feature_does_not(self):
        def landing():   # the batch with its reconciliation hand-over not approved
            p = pack(LANDING)
            p['id'] = 'door-test-landing-not-approved'
            p['methods'][0]['approved'] = False
            return p
        run = desk([landing()], [RECON, POSTING], BATCH)
        self.assertEqual(words(lambda: run.add('event', {'row': row('batch_reconciled', 'TRUE', RECON, 'v'), 'execute': True})),
                         gives('batch_reconciled', 'no one through ' + RUN_RECON + ', which is not approved', RECON))   # its checker is held to no try
        asked = {'schema': 'sutra-extension/2', 'id': 'door-test-the-ledger-asked', 'grants': ['action:door-test-ask-the-reconciliation-ledger@1'],
                 'providers': {'ledger-channel': 1},
                 'methods': [method('door-test-ask-the-reconciliation-ledger@1', 'batch_reconciled', ['batch_rehearsed'], provider='ledger-channel', cost={'attention': 1},
                                    action='ask', ask_to=RECON, question='Is refund batch 2026-11 reconciled?')]}
        run = desk([landing(), asked], [RECON, POSTING], ['simulate_fact', 'handoff', 'ask'])
        went = event(run, row('batch_reconciled', 'TRUE', RECON, 'v'))   # the party the approved question is put to: its row is taken, with no work out
        self.assertEqual([x['method'] for x in went['runs'][0]['model_receipts']], [POST])
        self.assertEqual([(p['kind'], p['fact'], p['checker'], p['truth'], p['names'], p['out']) for p in learn.proposals([kept(run)], 2)],
                         [('STATED_WITHOUT_A_CHECK', 'batch_reconciled', RECON, 'TRUE', None, None)])   # the learn feature reads the hand-over as giving the fact to its checker

    def test_l13_under_the_door_a_row_on_a_fact_a_method_makes_is_held_to_the_plan_whatever_scope_it_names(self):
        said, other = [], 'lendco/other-desk'
        for door in ('', 'plan'):
            run = desk([REFUND], [BOOK, FINANCE], DESKS, door=door)
            for fact, by in (('refund_sent', BOOK), ('refund_approved_by_finance', BOOK), ('refund_due', BOOK), ('refund_approved_by_finance', FINANCE)):
                said.append(words(lambda: run.add('event', {'row': row(fact, 'TRUE', by, 'v', scope=other), 'execute': True})) or run.journal[-1]['result']['status'])
            self.assertEqual(run.state.budget['money'], 3, door)
        self.assertEqual(said, ['OUT_OF_SCOPE'] * 4 + [gives('refund_sent', 'the step ' + SEND + ', whose receipt makes it', BOOK),
                                                        gives('refund_approved_by_finance', FINANCE + ', as the answer to the question of ' + ASK, BOOK),
                                                        'OUT_OF_SCOPE', 'OUT_OF_SCOPE'])   # rows for another desk: refused under the door, in words that name this desk's step and party


if __name__ == '__main__':
    unittest.main()
