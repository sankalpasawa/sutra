"""0.20.0-learn: the learn feature reads every check with the checker's own words, several records at once, and who stated a fact against
what the plan says (extensions/learn.py), with the packs of three desks of a lender (310 to 314), cases 160 to 162 and the recorded sequences
learn_checks, learn_across and learn_settled. A test named test_cN_... pins claim CN of the README passage and a test named test_lN_... pins
limit LN as the build behaves today. The class Existing holds what the parts the lab had make of the same records: the attempt ruling R35 of
the program asks for before a part is added; the class Sequences holds what the sequences record of it. The sequences are compared with the
built record (results/actual_run_records.json), so these tests run after tools/run_all.py."""
from pathlib import Path
import unittest, sys, json, ast, subprocess, random, copy
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from kernel.core import State, Kernel, digest
from tools.run_all import CASES, pack   # importing the lab's tools loads the kind files: handoff is registered from kinds/handoff.py
from tools.make_packs import method
from extensions.asks import answer, open_asks
from extensions import journal as J
from extensions import journal_record as R
from extensions import reader, learn
from extensions.reflection import Learner, reflect

HANDOFF = sys.modules['kinds.handoff']
open_handoffs = HANDOFF.open_handoffs
BOOK, REVIEW, JUDGE, LOG = 'fixture/loan-book', 'checker:statement-review', 'checker:program-judge', 'checker:call-log'
RECON, AUDIT, FINANCE, HOLD = 'checker:reconciliation', 'checker:audit', 'system:lendco/finance', 'fixture/legal-hold'
KINDS = ['simulate_fact', 'ask', 'handoff']
S_DESK, C_DESK, R_DESK = ['310_learn_statements', '311_learn_month_judged'], ['312_learn_collections'], ['314_learn_refunds']
SERVICING, OTHER = 'lendco/servicing', 'lendco/servicing-loan-32'   # the servicing desk's loan, and another loan the desk moves to
SEND, CALL, ASK, RECONCILE, REFUND = 'learn-send-statement@1', 'learn-call-borrower@1', 'learn-ask-finance-refund@1', 'learn-reconcile-refund@1', 'learn-send-refund@1'
OFFICER = 'learn-send-statement-by-officer-audited@1'   # a second way to the statement, in a pack made in memory: an officer, checked by the audit
OLD = 'the statement shows the old rate of 8.4 percent; the loan book says 7.9 percent'
SENT = "sent with the rate of 7.9 percent; the fee line still shows last year's fee and needs a second look"
FEE = "the fee line shows last year's fee"
ALL_PACKS = ['310_learn_statements', '311_learn_month_judged', '312_learn_collections', '313_learn_roster', '314_learn_refunds']


def started(packs, name, checkers):   # a journal with its packs handed in; a pack is a scenario file's name or a pack made in memory
    run = J.start(KINDS, checkers, name=name)
    for p in packs:
        run.add('pack', {'pack': pack(p) if type(p) is str else p})
    return run


def look(run, execute=True):
    return run.detail[run.add('look', {'execute': execute})['seq']]


def event(run, row):
    return run.detail[run.add('event', {'row': row, 'execute': True})['seq']]


def kept(run):   # one record: the journal as a keeper holds it, its text and its head
    return [(J.dump(run.journal), {'length': len(run.journal), 'sha256': run.journal[-1]['sha256']})]


def row(fact, truth, by, version, **more):
    return dict({'predicate': fact, 'truth': truth, 'verified': True, 'source': by, 'version': version}, **more)


def receipt(run, fact):   # the receipt of the try that is out on a fact
    return open_handoffs(run.state)[run.state.scope + '|' + fact]['receipt']


def cite(run, n, i=None, evidence=None):   # what a proposal says of an entry it rests on (of a run of it, with i; of a row of its pack, with evidence)
    j = run.journal[0]['sha256'][:12]
    return dict({'journal': j, 'entry': n, 'sha256': run.journal[n]['sha256']}, **({'run': f'{j}:{n}.{i}'} if i is not None else {}),
                **({'evidence': evidence} if evidence is not None else {}))


def of(props, kind):
    return [p for p in props if p['kind'] == kind]


def extra(id, **fields):   # a pack made in memory, for one test
    return {'schema': 'sutra-extension/2', 'id': id, **fields}


def rows_in_a_pack(run, id, *rows):   # rows handed in as the evidence of a pack made in memory
    run.add('pack', {'pack': extra(id, evidence=list(rows))})


def closed(detail):   # what the kind's HANDOFF_CLOSED lines of one entry say: (receipt, tries, confirmed)
    return [(x['data']['receipt'], x['data']['tries'], x['data']['confirmed']) for r in detail['runs'] for x in r['trace'] if x['operation'] == 'HANDOFF_CLOSED']


def before(detail):   # what the receipts one entry handed out tell their try under `before`
    return [b for r in detail['runs'] for x in r['model_receipts'] if 'handoff' in x for b in x['handoff']['before']]


def statements(*checks, name='servicing'):
    """The servicing desk: one look (try 1 goes out), then one row of the statement review per (truth, words) on the try that is out."""
    run = started(S_DESK, name, [BOOK, REVIEW, JUDGE])
    look(run)
    for n, (truth, words) in enumerate(checks, start=1):
        event(run, row('statement_sent', truth, REVIEW, f'review-{n}', checks=receipt(run, 'statement_sent'), why=words))
    return run


def collections(name, blocked=1, checks=()):
    """One morning of the collections desk: looks blocked for want of a place, the roster, a look that hands the call over, the call log's rows."""
    run = started(C_DESK, name, [BOOK, LOG])
    for _ in range(blocked):
        look(run)
    run.add('pack', {'pack': pack('313_learn_roster')})
    look(run)
    for n, (truth, words) in enumerate(checks, start=1):
        event(run, row('arrears_call_made', truth, LOG, f'call-log-{n}', checks=receipt(run, 'arrears_call_made'), why=words))
    return run


def refunds(name):   # the refund desk after its first look: the question to finance is out
    run = started(R_DESK, name, [BOOK, RECON, AUDIT])
    look(run)
    return run


def officer(writer_places=None):   # the second way to the statement, checked by the audit; with writer_places the writer's places are set too
    return extra('learn-test-officer-checked-by-the-audit',
                 methods=[method(OFFICER, 'statement_sent', ['statement_due'], provider='person:servicing-officer', cost={'compute': 2, 'money': 0, 'attention': 0},
                                 action='handoff', handoff_to='person:servicing-officer', instruction='Write and send the statement.', verified_by=AUDIT)],
                 providers=dict({'person:servicing-officer': 1}, **({'agent:statement-writer': writer_places} if writer_places is not None else {})),
                 grants=['action:' + OFFICER])


def sequence(name):   # one recorded sequence made again, as tools/run_all.py makes it
    ns = {'__name__': 'tools.scenes.' + name}
    exec(compile((ROOT / 'tools' / 'scenes' / (name + '.py')).read_text(), name, 'exec'), ns)
    made = ns['scene']({'State': State, 'Kernel': Kernel, 'pack': pack, 'answer': answer, 'open_asks': open_asks, 'Learner': Learner, 'digest': digest})
    return json.loads(json.dumps(made, ensure_ascii=False, allow_nan=False))


def forged(run, n, change):   # the record with entry n changed by `change(entry)` and the chain made whole again from there: a forgery the adapter cannot see
    entries = json.loads(json.dumps(run.journal))
    change(entries[n])
    prev = entries[n - 1]['sha256']
    for e in entries[n:]:
        e['prev_sha256'] = prev
        e['sha256'] = R._sha({k: e[k] for k in R.COVERED})
        prev = e['sha256']
    return [(''.join(R._canonical(e) + '\n' for e in entries), {'length': len(entries), 'sha256': prev})]


class Checks(unittest.TestCase):
    """C1 to C3: every check row with the checker's own words, a check that failed again, work handed out again."""
    def test_c1_every_check_row_is_one_proposal_with_the_checkers_words(self):
        run = statements(('FALSE', OLD), ('FALSE', OLD), ('TRUE', SENT))
        props = learn.proposals([kept(run)], 2)
        tries = [receipt_at(run, n) for n in (3, 4, 5)]
        self.assertEqual([(p['kind'], p['fact'], p['checker'], p['step'], p['try'], p['to'], p['receipt'], p['words'], p['support'], p['at'], p['status']) for p in props[:3]],
                         [('CHECK_FAILED', 'statement_sent', REVIEW, SEND, 1, 'agent:statement-writer', tries[0], OLD, 1, [cite(run, 4)], 'PROPOSED_ONLY'),
                          ('CHECK_FAILED', 'statement_sent', REVIEW, SEND, 2, 'agent:statement-writer', tries[1], OLD, 1, [cite(run, 5)], 'PROPOSED_ONLY'),
                          ('CHECK_PASSED', 'statement_sent', REVIEW, SEND, 3, 'agent:statement-writer', tries[2], SENT, 1, [cite(run, 6)], 'PROPOSED_ONLY')])
        self.assertEqual({p['record'] for p in props}, {run.journal[0]['sha256'][:12]})   # a record is named by its first journal

    def test_c1_a_check_in_a_packs_evidence_is_a_check_row(self):
        run = started(['310_learn_statements'], 'servicing', [BOOK, REVIEW])
        look(run)
        first = receipt(run, 'statement_sent')
        rows_in_a_pack(run, 'learn-test-review-in-a-pack', row('statement_sent', 'FALSE', REVIEW, 'review-1', checks=first, why=OLD))   # the review's row comes in a pack
        second = look(run)
        self.assertEqual([(b['try'], b['checked']) for b in before(second)], [(1, {'truth': 'FALSE', 'source': REVIEW, 'version': 'review-1', 'why': OLD})])   # what the kind tells try 2
        rows_in_a_pack(run, 'learn-test-review-again', row('statement_due', 'TRUE', BOOK, 'loan-31-year-2026'),
                       row('statement_sent', 'TRUE', REVIEW, 'review-2', checks=receipt(run, 'statement_sent'), why=SENT))
        self.assertEqual(closed(look(run)), [(receipt_at(run, 4), 2, True)])   # the kind's own account: try 2 confirmed
        self.assertEqual([(p['kind'], p['try'], p['words'], p['at']) for p in learn.proposals([kept(run)], 2) if p['kind'].startswith('CHECK_')],
                         [('CHECK_FAILED', 1, OLD, [cite(run, 3, evidence=0)]), ('CHECK_PASSED', 2, SENT, [cite(run, 5, evidence=1)])])

    def test_c1_a_check_the_door_kept_for_another_scope_is_a_check_in_the_scope_it_names(self):
        run = started(['310_learn_statements'], 'servicing', [BOOK, REVIEW])
        look(run)
        first = receipt(run, 'statement_sent')
        run.add('pack', {'pack': extra('learn-test-next-loan', scope=OTHER)})   # the desk moves on to another loan
        door = event(run, row('statement_sent', 'FALSE', REVIEW, 'review-1', checks=first, why=OLD, scope=SERVICING))   # the review's row on loan 31
        self.assertEqual((door['status'], run.state.evidence[SERVICING + '|statement_sent']['version']), ('OUT_OF_SCOPE', 'review-1'))   # kept for loan 31, nothing run
        run.add('pack', {'pack': extra('learn-test-back-to-loan-31', scope=SERVICING)})
        self.assertEqual([(b['try'], b['checked']['why']) for b in before(look(run))], [(1, OLD)])   # back on loan 31, the kind tells try 2 what the row said
        props = learn.proposals([kept(run)], 2)
        self.assertEqual([(p['kind'], p['scope'], p['try'], p['receipt'], p['at']) for p in of(props, 'CHECK_FAILED')], [('CHECK_FAILED', SERVICING, 1, first, [cite(run, 4)])])
        self.assertEqual([[t['checked'] and t['checked']['truth'] for t in p['tries']] for p in of(props, 'HANDED_OUT_AGAIN')], [['FALSE', None]])

    def test_c1_a_check_in_a_pack_that_names_a_scope_is_read_in_the_scope_the_pack_names(self):
        run = started(['310_learn_statements'], 'servicing', [BOOK, REVIEW])
        look(run)
        first = receipt(run, 'statement_sent')
        run.add('pack', {'pack': extra('learn-test-next-loan', scope=OTHER)})   # the desk moves on to another loan
        run.add('pack', {'pack': extra('learn-test-back-with-the-review', scope=SERVICING,
                                       evidence=[row('statement_sent', 'FALSE', REVIEW, 'review-1', checks=first, why=OLD)])})   # back on loan 31; the row names no scope of its own
        self.assertEqual([(b['try'], b['checked']['truth'], b['checked']['why']) for b in before(look(run))], [(1, 'FALSE', OLD)])   # the kind tells try 2 what the row said
        self.assertEqual([(p['kind'], p['scope'], p.get('try'), p['at']) for p in learn.proposals([kept(run)], 2)],
                         [('CHECK_FAILED', SERVICING, 1, [cite(run, 4, evidence=0)]), ('HANDED_OUT_AGAIN', SERVICING, None, [cite(run, 2, 0), cite(run, 5, 0)])])   # the pack's scope first, then its rows
        self.assertEqual(learn_took(*kept(run)[0]), kind_took(*kept(run)[0]))

    def test_c1_a_row_of_a_pack_with_no_verified_key_is_not_kept_and_is_no_check(self):
        run = started(['310_learn_statements'], 'servicing', [BOOK, REVIEW])
        look(run)
        review = row('statement_sent', 'FALSE', REVIEW, 'review-1', checks=receipt(run, 'statement_sent'), why=OLD)
        del review['verified']   # the review's row on try 1, in a pack, without the key `verified`
        rows_in_a_pack(run, 'learn-test-no-verified-key', review)
        self.assertEqual(run.state.fact('statement_sent')['truth'], 'UNKNOWN')   # the State does not keep it
        self.assertEqual(before(look(run)), [])   # the kind reads no check of try 1: no next try goes out
        self.assertEqual(learn.proposals([kept(run)], 2), [])

    def test_c1_a_decision_and_a_row_a_decision_turned_away_are_no_checks(self):
        run = started(['310_learn_statements'], 'servicing', [BOOK, REVIEW])
        look(run)
        first = receipt(run, 'statement_sent')
        rows_in_a_pack(run, 'learn-test-hold', row('statement_sent', 'FALSE', HOLD, 'hold-1', final=True))   # a decision on the fact, from a source the plan does not name
        self.assertEqual(event(run, row('statement_sent', 'TRUE', REVIEW, 'review-1', checks=first))['status'], 'DECISION_STANDS')
        rows_in_a_pack(run, 'learn-test-review-decides', row('statement_sent', 'TRUE', REVIEW, 'review-2', checks=first, final=True))   # the review's row as a decision
        self.assertEqual(closed(look(run)), [(first, 1, False)])   # the kind closes try 1 on the decision, not confirmed
        props = learn.proposals([kept(run)], 2)
        self.assertEqual([(p['kind'], p.get('source') or p.get('checker'), p['door'], p['at']) for p in props],
                         [('STATED_BY_ANOTHER', HOLD, 'PACK', [cite(run, 3, evidence=0)]), ('STATED_WITHOUT_A_CHECK', REVIEW, 'DECISION_STANDS', [cite(run, 4)]),
                          ('STATED_WITHOUT_A_CHECK', REVIEW, 'PACK', [cite(run, 5, evidence=0)])])

    def test_c1_a_desk_whose_packs_name_no_scope_is_read_in_the_scope_a_new_state_starts_in(self):
        desk = dict({k: v for k, v in pack('310_learn_statements').items() if k != 'scope'}, id='learn-test-no-scope')
        run = started([desk], 'servicing', [BOOK, REVIEW])
        look(run)
        event(run, row('statement_sent', 'FALSE', REVIEW, 'review-1', checks=receipt(run, 'statement_sent'), why=OLD))
        self.assertEqual((run.state.scope, State().scope, learn.FIRST_SCOPE), ('orgA/fulfillment',) * 3)   # the kernel's first scope, which the learn feature holds
        self.assertEqual([(p['kind'], p['scope']) for p in learn.proposals([kept(run)], 2)], [('CHECK_FAILED', 'orgA/fulfillment'), ('HANDED_OUT_AGAIN', 'orgA/fulfillment')])
        refund_desk = dict({k: v for k, v in pack('314_learn_refunds').items() if k != 'scope'}, id='learn-test-no-scope-refunds')
        run = started([refund_desk], 'refunds', [BOOK, RECON])
        event(run, row('refund_approved', 'TRUE', BOOK, 'book-approved'))   # before any run
        self.assertEqual([(p['kind'], p['scope']) for p in learn.proposals([kept(run)], 2)], [('STATED_BY_ANOTHER', 'orgA/fulfillment')])

    def test_c1_a_row_after_the_desks_pack_and_before_any_run_is_read_in_the_scope_the_pack_names(self):
        run = started(R_DESK, 'refunds', [BOOK, RECON])
        event(run, row('refund_approved', 'TRUE', BOOK, 'book-approved'))
        self.assertEqual([(p['kind'], p['scope']) for p in learn.proposals([kept(run)], 2)], [('STATED_BY_ANOTHER', 'lendco/refunds')])

    def test_c1_a_row_of_another_source_that_names_the_receipt_is_no_check(self):
        run = started(S_DESK, 'servicing', [BOOK, REVIEW, JUDGE])
        look(run)
        event(run, row('statement_sent', 'TRUE', BOOK, 'book-1', checks=receipt(run, 'statement_sent')))
        self.assertEqual([(p['kind'], p['source'], p['given']) for p in learn.proposals([kept(run)], 2)],
                         [('STATED_BY_ANOTHER', BOOK, [['checker', REVIEW, SEND]])])

    def test_c1_words_that_are_not_one_text_are_null(self):
        run = statements(('FALSE', ['the rate', 'the fee']))
        self.assertEqual([(p['kind'], p['words']) for p in learn.proposals([kept(run)], 2) if p['kind'].startswith('CHECK_')], [('CHECK_FAILED', None)])

    def test_c1_words_that_are_the_empty_text_are_one_text(self):
        props = learn.proposals([kept(statements(('FALSE', ''), ('FALSE', '')))], 2)
        self.assertEqual([(p['kind'], p['words']) for p in props if p['kind'].startswith('CHECK_')], [('CHECK_FAILED', ''), ('CHECK_FAILED', ''), ('CHECK_FAILED_AGAIN', ['', ''])])
        self.assertEqual(of(props, 'CHECK_FAILED_AGAIN')[0]['same_words'], True)   # the empty text is one text, quoted as it is
        days = [kept(statements(('FALSE', ''), name=f'servicing-{n}')) for n in (1, 2)]
        self.assertEqual([(p['words'], p['records']) for p in of(learn.proposals(days, 2), 'IN_SEVERAL_RECORDS') if p['what'] == 'check_failed'], [('', 2)])

    def test_c1_a_record_of_two_journals_is_read_as_one(self):
        run, keep = started(S_DESK, 'servicing', [BOOK, REVIEW, JUDGE]), J.Keep()
        look(run)   # try 1 goes out in the first journal
        J.save(run, keep)
        later = J.start(KINDS, [BOOK, REVIEW, JUDGE], name='servicing-after-the-close', continues=run, keep=keep)   # the first journal is closed; the books go on
        first = receipt(later, 'statement_sent')
        event(later, row('statement_sent', 'FALSE', REVIEW, 'review-1', checks=first, why=OLD))   # its check comes in the second journal; try 2 goes out there
        record = [keep.read(), (J.dump(later.journal), {'length': len(later.journal), 'sha256': later.journal[-1]['sha256']})]
        ids = (run.journal[0]['sha256'][:12], later.journal[0]['sha256'][:12])
        props = learn.proposals([record], 2)
        self.assertEqual([(p['kind'], p['record'], p.get('try'), p.get('receipt'), p['at']) for p in props if p['kind'] == 'CHECK_FAILED'],
                         [('CHECK_FAILED', ids[0], 1, first, [{'journal': ids[1], 'entry': 1, 'sha256': later.journal[1]['sha256']}])])
        [again] = of(props, 'HANDED_OUT_AGAIN')
        self.assertEqual(([t['try'] for t in again['tries']], [a['run'] for a in again['at']]), ([1, 2], [f'{ids[0]}:3.0', f'{ids[1]}:1.0']))

    def test_c1_in_a_chain_the_plan_and_the_order_of_the_repeats_run_across_the_journals(self):
        run, keep = started(C_DESK, 'collections-week-1', [BOOK, LOG]), J.Keep()
        look(run), look(run)   # blocked twice for want of a place: the plan stands in this journal only
        J.save(run, keep)
        later = J.start(KINDS, [BOOK, LOG], name='collections-week-2', continues=run, keep=keep)
        later.add('pack', {'pack': pack('313_learn_roster')})
        look(later)
        event(later, row('arrears_call_made', 'FALSE', LOG, 'call-log-1', checks=receipt(later, 'arrears_call_made'), why='no answer'))
        event(later, row('arrears_call_made', 'TRUE', BOOK, 'book-1'))   # the loan book on the call the plan gives to the call log
        record = [keep.read(), (J.dump(later.journal), {'length': len(later.journal), 'sha256': later.journal[-1]['sha256']})]
        ids = (run.journal[0]['sha256'][:12], later.journal[0]['sha256'][:12])
        props = learn.proposals([record], 2)
        self.assertEqual([(p['kind'], p['record'], p['at'][0]['journal'], p['at'][0]['entry']) for p in props],
                         [('CHECK_FAILED', ids[0], ids[1], 3), ('STATED_BY_ANOTHER', ids[0], ids[1], 4),
                          ('BLOCKED_AGAIN', ids[0], ids[0], 2), ('HANDED_OUT_AGAIN', ids[0], ids[1], 2)])   # repeats by their first row: journal of the chain, then entry

    def test_c2_the_same_check_failed_again_with_the_same_words(self):
        run = statements(('FALSE', OLD), ('FALSE', OLD), ('TRUE', SENT))
        [again] = of(learn.proposals([kept(run)], 2), 'CHECK_FAILED_AGAIN')
        self.assertEqual({k: again[k] for k in again if k != 'record'},
                         {'kind': 'CHECK_FAILED_AGAIN', 'scope': SERVICING, 'fact': 'statement_sent', 'checker': REVIEW, 'times': 2, 'words': [OLD, OLD],
                          'same_words': True, 'support': 2, 'at': [cite(run, 4), cite(run, 5)], 'status': 'PROPOSED_ONLY'})

    def test_c2_three_failures_are_three_and_the_writer_has_three_places(self):
        run = statements(('FALSE', OLD), ('FALSE', OLD), ('FALSE', FEE))
        self.assertEqual([r['status'] for e in (3, 4, 5, 6) for r in run.detail[e]['runs'] if r['goal'] == 'statement_sent'],
                         ['WAITING', 'WAITING', 'WAITING', 'PROVIDER_REQUIRED'])   # three tries, then no place for a fourth
        [again] = of(learn.proposals([kept(run)], 2), 'CHECK_FAILED_AGAIN')
        self.assertEqual((again['times'], again['words'], again['same_words']), (3, [OLD, OLD, FEE], False))

    def test_c2_same_words_only_when_every_word_is_one_text(self):
        for checks in ((('FALSE', ['the rate']), ('FALSE', ['the fee'])), (('FALSE', None), ('FALSE', None))):   # reasons as lists, and no reason at all
            [again] = of(learn.proposals([kept(statements(*checks))], 2), 'CHECK_FAILED_AGAIN')
            self.assertEqual((again['words'], again['same_words']), ([None, None], False))
        for words, things in ((['the rate'], []), (OLD, [('check_failed', OLD, 2)])):   # across records only words that are one text make one failed check
            days = [kept(statements(('FALSE', words), name=f'servicing-{n}')) for n in (1, 2)]
            self.assertEqual([(p['what'], p['words'], p['records']) for p in of(learn.proposals(days, 2), 'IN_SEVERAL_RECORDS') if p['what'] == 'check_failed'], things)

    def test_c2_failed_again_with_other_words_says_so_and_two_are_not_three(self):
        run = statements(('FALSE', OLD), ('FALSE', FEE), ('TRUE', SENT))
        [again] = of(learn.proposals([kept(run)], 2), 'CHECK_FAILED_AGAIN')
        self.assertEqual((again['words'], again['same_words']), ([OLD, FEE], False))
        self.assertEqual([p['kind'] for p in learn.proposals([kept(run)], 3)], ['CHECK_FAILED', 'CHECK_FAILED', 'CHECK_PASSED', 'HANDED_OUT_AGAIN'])   # the number is the caller's

    def test_c3_work_handed_out_again_names_every_try_and_what_its_check_said(self):
        run = statements(('FALSE', OLD), ('FALSE', OLD))
        [out] = of(learn.proposals([kept(run)], 2), 'HANDED_OUT_AGAIN')
        self.assertEqual((out['fact'], out['times'], out['at']), ('statement_sent', 3, [cite(run, 3, 0), cite(run, 4, 0), cite(run, 5, 0)]))
        self.assertEqual([(t['try'], t['step'], t['to'], t['checked']) for t in out['tries']],
                         [(1, SEND, 'agent:statement-writer', {'truth': 'FALSE', 'words': OLD, 'at': cite(run, 4)}),
                          (2, SEND, 'agent:statement-writer', {'truth': 'FALSE', 'words': OLD, 'at': cite(run, 5)}),
                          (3, SEND, 'agent:statement-writer', None)])   # no check of try 3 came

    def test_c3_tries_are_counted_by_fact_whatever_step_hands_the_work_over(self):
        officer = extra('learn-test-officer', methods=[method('learn-send-statement-by-officer@1', 'statement_sent', ['statement_due'], provider='person:servicing-officer',
                                                              cost={'compute': 1, 'money': 0, 'attention': 0}, action='handoff', handoff_to='person:servicing-officer',
                                                              instruction='Write and send the statement.', verified_by=REVIEW)],
                        providers={'agent:statement-writer': 1, 'person:servicing-officer': 1}, grants=['action:learn-send-statement-by-officer@1'])
        run = started(S_DESK + [officer], 'servicing', [BOOK, REVIEW, JUDGE])
        look(run)
        event(run, row('statement_sent', 'FALSE', REVIEW, 'review-1', checks=receipt(run, 'statement_sent'), why=OLD))
        [out] = of(learn.proposals([kept(run)], 2), 'HANDED_OUT_AGAIN')
        self.assertEqual([(t['try'], t['step'], t['to']) for t in out['tries']],   # the kernel's choice: two ways of one cost, the officer's id sorts first
                         [(1, 'learn-send-statement-by-officer@1', 'person:servicing-officer'), (2, SEND, 'agent:statement-writer')])

    def test_c3_a_try_handed_out_after_the_kind_closed_the_work_is_numbered_by_its_receipt(self):
        run = started(['310_learn_statements'], 'servicing', [BOOK, REVIEW])
        look(run)
        self.assertEqual(closed(event(run, row('statement_sent', 'TRUE', BOOK, 'book-1'))), [(receipt_at(run, 2), 1, False)])   # the book's yes closes try 1
        event(run, row('statement_sent', 'FALSE', BOOK, 'book-2'))   # the book takes it back: the work goes out again, as try 1 of new books
        [out] = of(learn.proposals([kept(run)], 2), 'HANDED_OUT_AGAIN')
        self.assertEqual([(t['try'], t['receipt']) for t in out['tries']], [(1, receipt_at(run, 2)), (1, receipt_at(run, 4))])

    def test_c3_a_try_whose_check_failed_stays_out_and_a_later_row_of_its_checker_on_it_is_a_check(self):
        one_place = extra('learn-test-one-place', providers={'agent:statement-writer': 1})   # the writer has one place: no second try can go out
        run = started(['310_learn_statements', one_place], 'servicing', [BOOK, REVIEW])
        look(run)
        first = receipt(run, 'statement_sent')
        failed = event(run, row('statement_sent', 'FALSE', REVIEW, 'review-1', checks=first, why=OLD))
        self.assertEqual([r['status'] for r in failed['runs']], ['PROVIDER_REQUIRED'])
        self.assertEqual(open_handoffs(run.state)['lendco/servicing|statement_sent']['receipt'], first)   # the kind keeps the failed try out
        passed = event(run, row('statement_sent', 'TRUE', REVIEW, 'review-2', checks=first, why=SENT))   # the same try, checked again, passes
        self.assertEqual(closed(passed), [(first, 1, True)])   # the kind's own account: try 1 confirmed
        self.assertEqual([(p['kind'], p['try'], p['receipt'], p['words'], p['at']) for p in learn.proposals([kept(run)], 2)],
                         [('CHECK_FAILED', 1, first, OLD, [cite(run, 4)]), ('CHECK_PASSED', 1, first, SENT, [cite(run, 5)])])

    def test_c3_what_a_tries_check_said_is_its_last_check_row_as_the_kind_tells_the_next_try(self):
        one_place = extra('learn-test-one-place', providers={'agent:statement-writer': 1})
        run = started(['310_learn_statements', one_place], 'servicing', [BOOK, REVIEW])
        look(run)
        first = receipt(run, 'statement_sent')
        for n, words in enumerate((OLD, FEE), start=1):   # try 1 fails, and with no place for try 2 the review looks again and fails it for another reason
            event(run, row('statement_sent', 'FALSE', REVIEW, f'review-{n}', checks=first, why=words))
        run.add('pack', {'pack': extra('learn-test-a-place-again', providers={'agent:statement-writer': 1})})   # a place again: try 2 goes out at the next look
        second = look(run)['runs'][0]['model_receipts'][-1]['handoff']
        self.assertEqual([(b['try'], b['checked']['truth'], b['checked']['why']) for b in second['before']], [(1, 'FALSE', FEE)])   # what the kind tells try 2
        props = learn.proposals([kept(run)], 2)
        [out] = of(props, 'HANDED_OUT_AGAIN')
        self.assertEqual([(t['try'], t['checked']) for t in out['tries']], [(1, {'truth': 'FALSE', 'words': FEE, 'at': cite(run, 5)}), (2, None)])
        [again] = of(props, 'CHECK_FAILED_AGAIN')
        self.assertEqual((again['times'], again['words'], again['same_words'], again['at']), (2, [OLD, FEE], False, [cite(run, 4), cite(run, 5)]))

    def test_c3_a_try_the_kind_closed_on_another_sources_row_is_out_no_more(self):
        run = started(S_DESK, 'servicing', [BOOK, REVIEW, JUDGE])
        look(run)
        first = receipt(run, 'statement_sent')
        booked = event(run, row('statement_sent', 'TRUE', BOOK, 'book-1'))   # the loan book says the statement went out; the fact reads TRUE
        self.assertEqual([(c[0], c[2]) for c in closed(booked)], [(first, False)])   # the kind closes try 1, not confirmed
        event(run, row('statement_sent', 'TRUE', REVIEW, 'review-1', checks=first, why=SENT))   # the review's row on the closed receipt
        self.assertEqual([(p['kind'], p.get('source') or p.get('checker'), p.get('names'), p.get('out'), p.get('last_check'), p['at'])
                          for p in learn.proposals([kept(run)], 2) if p['fact'] == 'statement_sent'],
                         [('STATED_BY_ANOTHER', BOOK, None, None, None, [cite(run, 4)]), ('STATED_WITHOUT_A_CHECK', REVIEW, first, None, None, [cite(run, 5)])])

    def test_c1_in_random_histories_of_a_desk_the_check_rows_are_the_rows_the_kind_reads(self):
        rows, doors = 0, {}
        for seed in range(200):
            run = random_history(seed)
            text, head = kept(run)[0]
            took = kind_took(text, head)
            self.assertEqual(learn_took(text, head), took, f'seed {seed}')
            rows += len(took)
            for c in took:
                e = run.journal[c['entry']]
                door = 'PACK' if e['kind'] == 'pack' else e['result']['status']
                doors[door] = doors.get(door, 0) + 1
            scope = learn.FIRST_SCOPE   # every run is run in the scope the last pack named, else the first: the scope the learn feature holds as the State's
            for e in run.journal[1:]:
                if e['kind'] == 'pack' and type(e['body']['pack'].get('scope')) is str:
                    scope = e['body']['pack']['scope']
                self.assertEqual({b['scope'] for b in e['result'].get('briefs', [])} - {scope}, set(), f'seed {seed} entry {e["seq"]}')
        self.assertGreater(rows, 250)
        self.assertGreater(min(doors.get(d, 0) for d in ('RECONCILED', 'OUT_OF_SCOPE', 'PACK')), 25)   # check rows came by every door that keeps a row

    def test_c3_every_try_a_next_try_followed_is_told_what_its_last_check_row_said(self):
        texts = [kept(d)[0] for d in desks()] + [kept(random_history(seed))[0] for seed in range(200)]
        told_in_all = 0
        for n, (text, head) in enumerate(texts):
            told, confirmed = kind_told(text, head)
            said = learn_said(text, head)
            self.assertEqual({r: said.get(r) for r in told}, told, f'history {n}')   # what the kind tells a next try under `before` (truth, why)
            self.assertEqual([r for r, yes in confirmed.items() if yes and (said.get(r) or ('',))[0] != 'TRUE'], [], f'history {n}')   # a confirmed close rests on a passed check
            told_in_all += len(told)
        self.assertGreater(told_in_all, 50)


class Blocks(unittest.TestCase):
    """C4 and C5: a goal blocked again in one record, and the same thing in several records."""
    def test_c4_runs_of_one_goal_blocked_in_a_row_for_the_same_reason(self):
        run = collections('day', blocked=3)
        [again] = of(learn.proposals([kept(run)], 2), 'BLOCKED_AGAIN')
        self.assertEqual((again['scope'], again['goal'], again['reason'], again['times'], again['at']),
                         ('lendco/collections-calls', 'arrears_call_made', 'PROVIDER_REQUIRED', 3, [cite(run, 2, 0), cite(run, 3, 0), cite(run, 4, 0)]))

    def test_c4_a_run_blocked_for_another_reason_ends_the_row(self):
        run = started(C_DESK, 'day', [BOOK, LOG])
        look(run)
        event(run, row('arrears_due', 'FALSE', BOOK, 'loan-44-paid'))
        event(run, row('arrears_due', 'TRUE', BOOK, 'loan-44-again'))
        self.assertEqual([r['status'] for e in (2, 3, 4) for r in run.detail[e]['runs']], ['PROVIDER_REQUIRED', 'METHOD_ABSENT', 'PROVIDER_REQUIRED'])
        self.assertEqual(of(learn.proposals([kept(run)], 2), 'BLOCKED_AGAIN'), [])

    def test_c4_a_run_blocked_for_another_reason_starts_the_next_row(self):
        run = started(C_DESK, 'day', [BOOK, LOG])
        look(run)
        for paid in ('loan-44-paid', 'loan-44-paid-in-full'):
            event(run, row('arrears_due', 'FALSE', BOOK, paid))
        self.assertEqual([r['status'] for e in (2, 3, 4) for r in run.detail[e]['runs']], ['PROVIDER_REQUIRED', 'METHOD_ABSENT', 'METHOD_ABSENT'])
        self.assertEqual([(p['scope'], p['reason'], p['times'], p['at']) for p in of(learn.proposals([kept(run)], 2), 'BLOCKED_AGAIN')],
                         [('lendco/collections-calls', 'METHOD_ABSENT', 2, [cite(run, 3, 0), cite(run, 4, 0)])])

    def test_c4_a_run_of_the_goal_that_is_not_blocked_ends_the_row_and_the_roster_gives_two_places(self):
        run = collections('day', blocked=1, checks=[('FALSE', 'no answer'), ('FALSE', 'no answer')])
        self.assertEqual([r['status'] for e in sorted(run.detail) for r in run.detail[e]['runs']], ['PROVIDER_REQUIRED', 'WAITING', 'WAITING', 'PROVIDER_REQUIRED'])
        self.assertEqual(of(learn.proposals([kept(run)], 2), 'BLOCKED_AGAIN'), [])   # blocked, waiting, waiting, blocked: no two in a row

    def test_c5_the_same_thing_in_several_records_is_one_proposal_counted_by_record(self):
        days = [collections('day-1', blocked=2), collections('day-2')]
        props = of(learn.proposals([kept(d) for d in days], 2), 'IN_SEVERAL_RECORDS')
        self.assertEqual([(p['what'], p.get('pack') or p.get('reason'), p['records'], p['support']) for p in props],
                         [('pack', '312_learn_collections', 2, 2), ('blocked', 'PROVIDER_REQUIRED', 2, 3), ('pack', '313_learn_roster', 2, 2)])
        self.assertEqual(props[1]['at'], [cite(days[0], 2, 0), cite(days[0], 3, 0), cite(days[1], 2, 0)])
        self.assertEqual(props[1]['record_ids'], [d.journal[0]['sha256'][:12] for d in days])
        self.assertEqual([[r['pack_sha256'] for r in R.ledger(kept(d)) if r.get('pack') == '312_learn_collections'] for d in days], [[props[0]['pack_sha256']]] * 2)   # the ledger's sha256

    def test_c5_a_step_that_stopped_and_an_answer_are_things_of_several_records_too(self):
        days = []
        for name in ('reminders-day-1', 'reminders-day-2'):   # the reader version's collections desk: its reminder step stops at its turn
            run = started(['220_collections_desk'], name, [BOOK, reader.SOURCE])
            look(run)
            days.append(run)
        props = of(learn.proposals([kept(d) for d in days], 2), 'IN_SEVERAL_RECORDS')
        self.assertEqual([(p['what'], p.get('step'), p.get('reason'), p['records']) for p in props if p['what'] == 'stopped'],
                         [('stopped', 'send-reminder@1', 'Prerequisite not true before effect: borrower_reachable', 2)])
        asked = []
        for name in ('a', 'b'):
            run = refunds(name)
            run.add('answer', {'receipt': run.detail[2]['runs'][0]['model_receipts'][-1], 'truth': 'FALSE', 'source': FINANCE, 'execute': True})
            asked.append(run)
        props = of(learn.proposals([kept(r) for r in asked], 2), 'IN_SEVERAL_RECORDS')
        self.assertEqual([(p['to'], p['truth'], p['records'], p['at']) for p in props if p['what'] == 'answer'], [(FINANCE, 'FALSE', 2, [cite(asked[0], 3), cite(asked[1], 3)])])

    def test_c5_things_that_differ_in_one_part_of_their_key_are_two_things(self):
        def things(runs, what):
            return [p for p in of(learn.proposals([kept(r) for r in runs], 2), 'IN_SEVERAL_RECORDS') if p['what'] == what]
        refused = refunds('refused')
        refused.add('answer', {'receipt': refused.detail[2]['runs'][0]['model_receipts'][-1], 'truth': 'FALSE', 'source': FINANCE, 'execute': True})
        self.assertEqual(things([collections('day-1'), refused], 'blocked'), [])   # blocked for want of a place, and refused: two status words
        yes, no = refunds('yes'), refunds('no')
        for run, truth in ((yes, 'TRUE'), (no, 'FALSE')):
            run.add('answer', {'receipt': run.detail[2]['runs'][0]['model_receipts'][-1], 'truth': truth, 'source': FINANCE, 'execute': True})
        self.assertEqual(things([yes, no], 'answer'), [])   # finance's yes and finance's no
        rosters = [started(C_DESK + [extra('learn-test-roster-of-the-day', providers={'agent:collector': n})], f'day-{n}', [BOOK, LOG]) for n in (1, 2)]
        self.assertEqual([p['pack'] for p in things(rosters, 'pack')], ['312_learn_collections'])   # one id, two contents: two packs
        self.assertEqual(things([statements(('FALSE', OLD), name='s-1'), statements(('FALSE', FEE), name='s-2')], 'check_failed'), [])   # other words
        audited = started(['310_learn_statements', officer(writer_places=0)], 'audited', [BOOK, REVIEW, AUDIT])   # no place for the writer: the officer's way
        look(audited)
        event(audited, row('statement_sent', 'FALSE', AUDIT, 'audit-1', checks=receipt(audited, 'statement_sent'), why=OLD))
        self.assertEqual([p['checker'] for p in of(learn.proposals([kept(audited)], 2), 'CHECK_FAILED')], [AUDIT])
        self.assertEqual(things([statements(('FALSE', OLD), name='s-1'), audited], 'check_failed'), [])   # other checker
        by_book, by_audit = refunds('book'), refunds('audit')
        event(by_book, row('refund_approved', 'TRUE', BOOK, 'book-approved'))
        event(by_audit, row('refund_approved', 'TRUE', AUDIT, 'audit-approved'))
        self.assertEqual(things([by_book, by_audit], 'stated_by_another'), [])   # other source
        wider = started(R_DESK + [extra('learn-test-approval-checked', methods=[method('learn-approve-by-a-clerk@1', 'refund_approved', ['refund_due'], provider='person:clerk',
                                                                                         cost={'compute': 1, 'money': 0, 'attention': 0}, action='handoff', handoff_to='person:clerk',
                                                                                         instruction='Approve the refund.', verified_by=RECON)],
                                                     providers={'person:clerk': 1}, grants=['action:learn-approve-by-a-clerk@1'])], 'wider', [BOOK, RECON, AUDIT])
        event(wider, row('refund_approved', 'TRUE', BOOK, 'book-approved'))
        self.assertEqual([p['given'] for p in of(learn.proposals([kept(wider)], 2), 'STATED_BY_ANOTHER')], [[['asked', FINANCE, ASK], ['checker', RECON, 'learn-approve-by-a-clerk@1']]])
        self.assertEqual(things([by_book, wider], 'stated_by_another'), [])   # the plan gives the fact to others
        recon, audit = refunds('recon'), started(R_DESK + [extra('learn-test-audited-reconciliation', methods=[method(
            'learn-reconcile-by-the-auditor@1', 'refund_reconciled', ['refund_due'], provider='person:auditor', cost={'compute': 1, 'money': 0, 'attention': 0}, action='handoff',
            handoff_to='person:auditor', instruction='Reconcile the refund.', verified_by=AUDIT)], providers={'person:auditor': 1}, grants=['action:learn-reconcile-by-the-auditor@1'])],
            'audit', [BOOK, RECON, AUDIT])
        event(recon, row('refund_reconciled', 'TRUE', RECON, 'recon-1'))
        event(audit, row('refund_reconciled', 'TRUE', AUDIT, 'audit-1'))
        self.assertEqual([p['kind'] for p in learn.proposals([kept(audit)], 2)], ['STATED_WITHOUT_A_CHECK'])
        self.assertEqual(things([recon, audit], 'stated_without_a_check'), [])   # other checker
        rule = dict({k: v for k, v in pack('220_collections_desk').items() if k not in ('evidence', 'rules')}, id='learn-test-overdue-by-a-rule',
                    evidence=[pack('220_collections_desk')['evidence'][1], row('days_late', 'TRUE', BOOK, 'loan-7-day-1')],
                    rules=pack('220_collections_desk')['rules'] + [{'id': 'R-OVERDUE@1', 'head': 'instalment_overdue', 'branches': [['days_late']], 'approved': True,
                                                                   'source': 'fixture/reviewed-domain-theory'}])
        stops = [started([p], f'reminders-{n}', [BOOK, reader.SOURCE]) for n, p in enumerate(('220_collections_desk', rule))]
        self.assertEqual([[r['stopped']['reason'] for r in look(s)['runs']] for s in stops],
                         [['Prerequisite not true before effect: borrower_reachable'], ['Prerequisite not true before effect: instalment_overdue borrower_reachable']])
        self.assertEqual(things(stops, 'stopped'), [])   # one step, two reasons
        self.assertEqual([(p['records'], p['support']) for p in things([statements(('FALSE', OLD), name='s-1'), statements(('FALSE', OLD), ('FALSE', OLD), name='s-2')],
                                                                        'handed_out_again')], [(2, 3)])   # by fact: try 2 in one record, tries 2 and 3 in the other

    def test_c5_things_that_differ_in_the_fact_the_party_the_question_or_the_step_are_two_things(self):
        def things(runs, what):
            return [p for p in of(learn.proposals([kept(r) for r in runs], 2), 'IN_SEVERAL_RECORDS') if p['what'] == what]
        loans = extra('learn-test-two-statements', goals=['statement_sent', 'statement_32_sent'], evidence=[row('statement_32_due', 'TRUE', BOOK, 'loan-32')],
                      methods=[method('learn-send-statement-32@1', 'statement_32_sent', ['statement_32_due'], provider='agent:statement-writer', cost={'compute': 1, 'money': 0, 'attention': 0},
                                      action='handoff', handoff_to='agent:statement-writer', instruction='Write and send the annual statement of loan L-32.', verified_by=REVIEW)],
                      grants=['action:learn-send-statement-32@1'])
        loan_32 = started(['310_learn_statements', loans], 'servicing-32', [BOOK, REVIEW])
        look(loan_32)
        event(loan_32, row('statement_32_sent', 'FALSE', REVIEW, 'review-32', checks=receipt(loan_32, 'statement_32_sent'), why=OLD))   # the same words on loan 32's statement
        self.assertEqual([(p['kind'], p['fact']) for p in learn.proposals([kept(loan_32)], 2)], [('CHECK_FAILED', 'statement_32_sent'), ('HANDED_OUT_AGAIN', 'statement_32_sent')])
        loan_31 = statements(('FALSE', OLD), name='servicing-31')
        self.assertEqual((things([loan_31, loan_32], 'check_failed'), things([loan_31, loan_32], 'handed_out_again')), ([], []))   # other fact
        recon = refunds('recon')
        event(recon, row('refund_reconciled', 'TRUE', RECON, 'recon-1'))
        clerk = started(R_DESK + [extra('learn-test-approval-checked', methods=[method('learn-approve-by-a-clerk@1', 'refund_approved', ['refund_due'], provider='person:clerk',
                                                                                         cost={'compute': 1, 'money': 0, 'attention': 0}, action='handoff', handoff_to='person:clerk',
                                                                                         instruction='Approve the refund.', verified_by=RECON)],
                                                     providers={'person:clerk': 1}, grants=['action:learn-approve-by-a-clerk@1'])], 'clerk', [BOOK, RECON, AUDIT])
        event(clerk, row('refund_approved', 'TRUE', RECON, 'recon-approved'))
        self.assertEqual([(p['kind'], p['fact']) for p in learn.proposals([kept(clerk)], 2)], [('STATED_WITHOUT_A_CHECK', 'refund_approved')])
        self.assertEqual(things([recon, clerk], 'stated_without_a_check'), [])   # the reconciliation checker, on another fact
        desk = pack('314_learn_refunds')

        def asked(name, to, question):   # the refund desk with its question put to another party, or another question; the answer is no
            ask = dict(desk['methods'][0], id=f'learn-test-ask-{name}@1', grant=f'action:learn-test-ask-{name}@1', ask_to=to, question=question)
            run = started([dict(desk, id=f'learn-test-desk-{name}', methods=[ask] + desk['methods'][1:], grants=[ask['grant']] + desk['grants'][1:])], f'refunds-{name}', [BOOK, RECON])
            run.add('answer', {'receipt': look(run)['runs'][0]['model_receipts'][-1], 'truth': 'FALSE', 'source': to, 'execute': True})
            return run
        finance = asked('finance', FINANCE, desk['methods'][0]['question'])
        self.assertEqual(things([finance, asked('again', FINANCE, desk['methods'][0]['question'])], 'answer')[0]['records'], 2)   # one party, one question, one truth: one thing
        self.assertEqual(things([finance, asked('treasury', 'system:lendco/treasury', desk['methods'][0]['question'])], 'answer'), [])   # another party
        self.assertEqual(things([finance, asked('twice', FINANCE, 'Loan L-17 was overpaid twice. May the desk send both refunds?')], 'answer'), [])   # another question
        reminder = pack('220_collections_desk')
        letter = dict(reminder['methods'][0], id='learn-test-send-letter@1', grant='action:learn-test-send-letter@1')
        stops = [started([p], f'reminders-{n}', [BOOK, reader.SOURCE]) for n, p in enumerate(('220_collections_desk', dict(reminder, id='learn-test-letter-desk', methods=[letter],
                                                                                                                              grants=[letter['grant']])))]
        self.assertEqual([[(r['stopped']['method'], r['stopped']['reason']) for r in look(s)['runs']] for s in stops],
                         [[('send-reminder@1', 'Prerequisite not true before effect: borrower_reachable')], [('learn-test-send-letter@1', 'Prerequisite not true before effect: borrower_reachable')]])
        self.assertEqual(things(stops, 'stopped'), [])   # another step, for the same reason

    def test_c5_the_number_is_the_callers_for_every_repeat_and_every_thing(self):
        blocked, handed, days = collections('day', blocked=2), statements(('FALSE', OLD)), [kept(collections('day-1')), kept(collections('day-2'))]
        self.assertEqual([[p['kind'] for p in learn.proposals([kept(r)], 2) if p['kind'] in ('BLOCKED_AGAIN', 'HANDED_OUT_AGAIN')] for r in (blocked, handed)],
                         [['BLOCKED_AGAIN'], ['HANDED_OUT_AGAIN']])   # two of each, and the number is 2
        self.assertEqual([p['what'] for p in of(learn.proposals(days, 2), 'IN_SEVERAL_RECORDS')], ['pack', 'blocked', 'pack'])
        self.assertEqual([[p['kind'] for p in learn.proposals([kept(r)], 3)] for r in (blocked, handed)], [[], ['CHECK_FAILED']])   # the number is 3: two are not three
        self.assertEqual(learn.proposals(days, 3), [])

    def test_c5_a_thing_seen_twice_in_one_record_stands_in_one_record(self):
        run = collections('day-1', blocked=2)
        self.assertEqual(of(learn.proposals([kept(run)], 2), 'IN_SEVERAL_RECORDS'), [])

    def test_c5_a_journal_in_two_records_is_refused_and_twice_in_one_record_the_adapter_refuses(self):
        run = collections('day-1')
        for records, words in (([kept(run), kept(run)], learn.TWICE), ([kept(run) + kept(run)], 'A journal of this record does not continue the one before it')):
            with self.assertRaises(ValueError) as said:
                learn.proposals(records, 2)
            self.assertEqual(str(said.exception), words)


class Stated(unittest.TestCase):
    """C6 and C7: who stated a fact, against what the plan says."""
    def test_c6_a_row_of_the_loan_book_on_the_yes_the_plan_puts_to_finance(self):
        run = refunds('a')
        event(run, row('refund_approved', 'TRUE', BOOK, 'book-approved'))
        self.assertEqual([(p['kind'], p['fact'], p['given'], p['source'], p['truth'], p['door'], p['at']) for p in learn.proposals([kept(run)], 2)],
                         [('STATED_BY_ANOTHER', 'refund_approved', [['asked', FINANCE, ASK]], BOOK, 'TRUE', 'RECONCILED', [cite(run, 3)])])

    def test_c6_a_row_turned_away_because_a_decision_stands_is_read_with_its_door(self):
        run = refunds('b')
        question = run.detail[2]['runs'][0]['model_receipts'][-1]
        run.add('answer', {'receipt': question, 'truth': 'FALSE', 'source': FINANCE, 'execute': True})
        event(run, row('refund_approved', 'TRUE', BOOK, 'book-approved'))
        self.assertEqual([(p['kind'], p['door']) for p in learn.proposals([kept(run)], 2) if p['kind'] != 'BLOCKED_AGAIN'], [('STATED_BY_ANOTHER', 'DECISION_STANDS')])

    def test_c6_a_row_in_a_later_pack_on_a_fact_the_plan_gives_to_someone(self):
        run = refunds('a')
        rows_in_a_pack(run, 'learn-test-the-book-says-no', row('refund_approved', 'FALSE', BOOK, 'book-paid', why='the loan book shows the refund paid on 3 November'))
        self.assertEqual([(p['kind'], p['given'], p['source'], p['truth'], p['door'], p['words'], p['at']) for p in learn.proposals([kept(run)], 2)],
                         [('STATED_BY_ANOTHER', [['asked', FINANCE, ASK]], BOOK, 'FALSE', 'PACK', 'the loan book shows the refund paid on 3 November', [cite(run, 3, evidence=0)])])
        yes = refunds('b')
        rows_in_a_pack(yes, 'learn-test-the-book-says-yes', row('refund_approved', 'TRUE', BOOK, 'book-approved'))
        self.assertEqual(look(yes)['runs'][0]['actions'], [RECONCILE])   # the State reads the yes from the book and the plan goes on, the question unanswered
        self.assertEqual([(p['kind'], p['door']) for p in learn.proposals([kept(yes)], 2)], [('STATED_BY_ANOTHER', 'PACK')])

    def test_c6_a_packs_own_rows_are_read_against_the_plan_before_it(self):
        desk = dict(pack('314_learn_refunds'), id='learn-test-desk-with-its-answer', evidence=pack('314_learn_refunds')['evidence'] + [row('refund_approved', 'TRUE', BOOK, 'book-approved')])
        run = started([desk], 'refunds', [BOOK, RECON])
        look(run)
        self.assertEqual(learn.proposals([kept(run)], 2), [])   # the State takes a pack's evidence before its methods: no plan stood when the row came
        rows_in_a_pack(run, 'learn-test-the-book-again', row('refund_approved', 'TRUE', BOOK, 'book-approved-again'))
        self.assertEqual([(p['kind'], p['door'], p['at']) for p in learn.proposals([kept(run)], 2)], [('STATED_BY_ANOTHER', 'PACK', [cite(run, 3, evidence=0)])])

    def test_c6_a_row_of_a_pack_that_is_not_verified_is_not_read(self):
        run = refunds('a')
        rows_in_a_pack(run, 'learn-test-unverified', row('refund_approved', 'TRUE', BOOK, 'book-draft', verified=False))
        self.assertEqual(run.state.fact('refund_approved')['truth'], 'UNKNOWN')   # the State does not keep it
        self.assertEqual(learn.proposals([kept(run)], 2), [])

    def test_c6_a_row_of_a_pack_a_decision_turned_away_is_read_with_its_door(self):
        run = refunds('b')
        run.add('answer', {'receipt': run.detail[2]['runs'][0]['model_receipts'][-1], 'truth': 'FALSE', 'source': FINANCE, 'execute': True})   # finance's no, a decision
        rows_in_a_pack(run, 'learn-test-the-book-says-yes', row('refund_approved', 'TRUE', BOOK, 'book-approved'))
        self.assertEqual(run.state.fact('refund_approved')['source'], 'STAMP:' + FINANCE)   # the decision stands: the State did not keep the book's row
        self.assertEqual([(p['kind'], p['door'], p['at']) for p in learn.proposals([kept(run)], 2) if p['kind'] != 'BLOCKED_AGAIN'],
                         [('STATED_BY_ANOTHER', 'DECISION_STANDS', [cite(run, 4, evidence=0)])])
        held = refunds('c')
        rows_in_a_pack(held, 'learn-test-hold', row('refund_approved', 'FALSE', HOLD, 'hold-1', final=True))   # a decision in a pack
        rows_in_a_pack(held, 'learn-test-the-book-says-yes', row('refund_approved', 'TRUE', BOOK, 'book-approved'))
        self.assertEqual([(p['source'], p['truth'], p['door']) for p in learn.proposals([kept(held)], 2)], [(HOLD, 'FALSE', 'PACK'), (BOOK, 'TRUE', 'DECISION_STANDS')])

    def test_c6_a_yes_answer_is_a_decision_too_and_turns_away_a_later_row_of_a_pack(self):
        run = refunds('yes')
        run.add('answer', {'receipt': run.detail[2]['runs'][0]['model_receipts'][-1], 'truth': 'TRUE', 'source': FINANCE, 'execute': True})   # finance's yes, a decision
        rows_in_a_pack(run, 'learn-test-the-book-says-yes', row('refund_approved', 'TRUE', BOOK, 'book-approved'))
        self.assertEqual(run.state.fact('refund_approved')['source'], 'STAMP:' + FINANCE)   # the yes stands: the State did not keep the book's row
        self.assertEqual([(p['kind'], p['source'], p['truth'], p['door'], p['at']) for p in learn.proposals([kept(run)], 2)],
                         [('STATED_BY_ANOTHER', BOOK, 'TRUE', 'DECISION_STANDS', [cite(run, 4, evidence=0)])])

    def test_c6_a_row_the_door_kept_for_another_scope_is_read_in_the_scope_it_names(self):
        run = refunds('a')   # loan 17: the question to finance is out
        run.add('pack', {'pack': extra('learn-test-loan-18', scope='lendco/refunds-loan-18')})   # the desk moves on to loan 18
        self.assertEqual(event(run, row('refund_approved', 'TRUE', BOOK, 'book-approved', scope='lendco/refunds'))['status'], 'OUT_OF_SCOPE')
        self.assertEqual([(p['kind'], p['scope'], p['source'], p['door'], p['at']) for p in learn.proposals([kept(run)], 2)],
                         [('STATED_BY_ANOTHER', 'lendco/refunds', BOOK, 'OUT_OF_SCOPE', [cite(run, 4)])])
        run.add('pack', {'pack': extra('learn-test-back-to-loan-17', scope='lendco/refunds')})
        self.assertEqual((look(run)['runs'][0]['actions'], run.state.fact('refund_approved')['source']), ([RECONCILE], BOOK))   # back on loan 17 the State reads the book's yes

    def test_c6_a_row_turned_away_in_another_scope_is_read_in_the_scope_it_names(self):
        run = refunds('b')
        run.add('answer', {'receipt': run.detail[2]['runs'][0]['model_receipts'][-1], 'truth': 'FALSE', 'source': FINANCE, 'execute': True})   # finance's no, a decision
        run.add('pack', {'pack': extra('learn-test-next-loan', scope='lendco/refunds-loan-18')})   # the desk moves on to another loan
        detail = event(run, row('refund_approved', 'TRUE', BOOK, 'book-approved', scope='lendco/refunds'))   # the book's yes on the first loan
        self.assertEqual((detail['status'], run.state.scope), ('DECISION_STANDS', 'lendco/refunds-loan-18'))
        self.assertEqual([(p['kind'], p['scope'], p['given'], p['source'], p['door'], p['at']) for p in of(learn.proposals([kept(run)], 2), 'STATED_BY_ANOTHER')],
                         [('STATED_BY_ANOTHER', 'lendco/refunds', [['asked', FINANCE, ASK]], BOOK, 'DECISION_STANDS', [cite(run, 5)])])

    def test_c6_a_fact_a_step_makes_is_given_to_that_step(self):
        run = refunds('a')
        event(run, row('refund_sent', 'TRUE', BOOK, 'book-sent'))
        self.assertEqual([(p['kind'], p['given']) for p in learn.proposals([kept(run)], 2)], [('STATED_BY_ANOTHER', [['step', REFUND, REFUND]])])

    def test_c6_a_fact_two_methods_make_is_given_to_both(self):
        run = started(['310_learn_statements', officer()], 'servicing', [BOOK, REVIEW, AUDIT])
        event(run, row('statement_sent', 'TRUE', BOOK, 'book-1'))
        self.assertEqual([p['given'] for p in learn.proposals([kept(run)], 2)], [[['checker', REVIEW, SEND], ['checker', AUDIT, OFFICER]]])

    def test_c6_a_fact_no_method_makes_and_a_row_before_the_plan_are_not_read(self):
        run = J.start(KINDS, [BOOK, RECON, AUDIT], name='a')
        event(run, row('refund_approved', 'TRUE', BOOK, 'book-approved'))   # before the pack that puts the question to finance
        run.add('pack', {'pack': pack('314_learn_refunds')})
        look(run)
        event(run, row('refund_due', 'TRUE', BOOK, 'loan-17-again'))   # no method makes it
        self.assertEqual(learn.proposals([kept(run)], 2), [])

    def test_c7_the_checker_states_the_fact_when_no_work_was_out(self):
        run = refunds('b')
        event(run, row('refund_reconciled', 'TRUE', RECON, 'recon-1'))
        self.assertEqual([(p['kind'], p['checker'], p['truth'], p['door'], p['names'], p['out'], p['last_check']) for p in learn.proposals([kept(run)], 2)],
                         [('STATED_WITHOUT_A_CHECK', RECON, 'TRUE', 'RECONCILED', None, None, None)])

    def test_c7_the_checker_states_the_fact_while_a_try_is_out_and_names_none(self):
        run = refunds('a')
        event(run, row('refund_approved', 'TRUE', BOOK, 'book-approved'))
        out = receipt(run, 'refund_reconciled')
        event(run, row('refund_reconciled', 'TRUE', RECON, 'recon-1'))
        self.assertEqual([(p['kind'], p['out']) for p in of(learn.proposals([kept(run)], 2), 'STATED_WITHOUT_A_CHECK')], [('STATED_WITHOUT_A_CHECK', out)])

    def test_c7_a_row_on_the_receipt_of_an_earlier_try_is_no_check(self):
        run = statements(('FALSE', OLD))
        first, second = receipt_at(run, 3), receipt(run, 'statement_sent')
        event(run, row('statement_sent', 'TRUE', REVIEW, 'review-2', checks=first))   # try 1 passed later, on its own receipt, while try 2 is out
        [p] = of(learn.proposals([kept(run)], 2), 'STATED_WITHOUT_A_CHECK')
        self.assertEqual((p['names'], p['out'], p['last_check']), (first, second, {'truth': 'FALSE', 'at': cite(run, 4)}))

    def test_c7_a_confirmed_fact_stated_again_shows_its_last_check(self):
        run = statements(('TRUE', SENT))
        event(run, row('statement_sent', 'TRUE', REVIEW, 'review-2', why='edited after the check'))
        [p] = of(learn.proposals([kept(run)], 2), 'STATED_WITHOUT_A_CHECK')
        self.assertEqual((p['names'], p['out'], p['last_check'], p['words']), (None, None, {'truth': 'TRUE', 'at': cite(run, 4)}, 'edited after the check'))

    def test_c7_last_check_is_the_last_check_row_before_it(self):
        run = statements(('FALSE', OLD), ('FALSE', FEE))
        event(run, row('statement_sent', 'FALSE', REVIEW, 'review-3', why='still the fee line'))   # the review again, naming no try
        [p] = of(learn.proposals([kept(run)], 2), 'STATED_WITHOUT_A_CHECK')
        self.assertEqual((p['truth'], p['out'], p['last_check']), ('FALSE', receipt(run, 'statement_sent'), {'truth': 'FALSE', 'at': cite(run, 5)}))

    def test_c7_a_row_of_another_checker_of_the_plan_on_the_try_that_is_out(self):
        run = started(['310_learn_statements', officer()], 'servicing', [BOOK, REVIEW, AUDIT])
        first = look(run)['runs'][0]['model_receipts'][-1]
        self.assertEqual((first['method'], first['handoff']['verified_by']), (SEND, REVIEW))   # try 1 is the writer's, checked by the review
        self.assertEqual(closed(event(run, row('statement_sent', 'TRUE', AUDIT, 'audit-1', checks=first['sha256'], why='seen at the audit'))), [(first['sha256'], 1, False)])
        self.assertEqual([(p['kind'], p['checker'], p['names'], p['out'], p['words']) for p in learn.proposals([kept(run)], 2)],
                         [('STATED_WITHOUT_A_CHECK', AUDIT, first['sha256'], first['sha256'], 'seen at the audit')])   # the audit checks the officer's work, not the writer's
        mirror = started(['310_learn_statements', officer(writer_places=0)], 'servicing', [BOOK, REVIEW, AUDIT])
        theirs = look(mirror)['runs'][0]['model_receipts'][-1]
        self.assertEqual((theirs['method'], theirs['handoff']['verified_by']), (OFFICER, AUDIT))   # with no place for the writer, try 1 is the officer's
        event(mirror, row('statement_sent', 'TRUE', REVIEW, 'review-1', checks=theirs['sha256']))
        self.assertEqual([(p['kind'], p['checker'], p['out']) for p in learn.proposals([kept(mirror)], 2)], [('STATED_WITHOUT_A_CHECK', REVIEW, theirs['sha256'])])

    def test_c7_an_unknown_row_of_another_checker_of_the_plan_on_the_try_that_is_out_is_stated_without_a_check(self):
        run = started(['310_learn_statements', officer()], 'servicing', [BOOK, REVIEW, AUDIT])
        first = look(run)['runs'][0]['model_receipts'][-1]['sha256']   # try 1 is the writer's, checked by the review
        self.assertEqual(closed(event(run, row('statement_sent', 'UNKNOWN', AUDIT, 'audit-1', checks=first, why='not seen yet'))), [])   # the kind closes nothing
        self.assertEqual([(p['kind'], p['checker'], p['truth'], p['names'], p['out'], p['words']) for p in learn.proposals([kept(run)], 2)],
                         [('STATED_WITHOUT_A_CHECK', AUDIT, 'UNKNOWN', first, first, 'not seen yet')])   # L2 leaves out the UNKNOWN row of the try's own checker only

    def test_c7_a_row_of_the_checker_a_decision_turned_away_on_the_try_that_is_out(self):
        run = started(['310_learn_statements'], 'servicing', [BOOK, REVIEW])
        look(run)
        first = receipt(run, 'statement_sent')
        rows_in_a_pack(run, 'learn-test-hold', row('statement_sent', 'TRUE', HOLD, 'hold-1', final=True))
        self.assertEqual(event(run, row('statement_sent', 'FALSE', REVIEW, 'review-1', checks=first, why=OLD))['status'], 'DECISION_STANDS')
        self.assertEqual([(p['kind'], p.get('truth'), p['door'], p.get('out')) for p in learn.proposals([kept(run)], 2)],
                         [('STATED_BY_ANOTHER', 'TRUE', 'PACK', None), ('STATED_WITHOUT_A_CHECK', 'FALSE', 'DECISION_STANDS', first)])

    def test_c7_a_decision_of_the_checker_in_a_pack(self):
        run = started(['310_learn_statements'], 'servicing', [BOOK, REVIEW])
        look(run)
        first = receipt(run, 'statement_sent')
        rows_in_a_pack(run, 'learn-test-review-decides', row('statement_sent', 'FALSE', REVIEW, 'review-1', checks=first, final=True, why=OLD))
        self.assertEqual([r['status'] for r in look(run)['runs']], ['REFUSED'])   # a no that is a decision: no other try goes out
        self.assertEqual([(p['kind'], p['truth'], p['door'], p['names'], p['out']) for p in learn.proposals([kept(run)], 2)],
                         [('STATED_WITHOUT_A_CHECK', 'FALSE', 'PACK', first, first)])


class Reading(unittest.TestCase):
    """C8 and C9: a function of the kept text, and its refusals."""
    def test_c8_the_same_records_give_the_same_bytes_also_in_a_process_that_holds_no_kernel(self):
        run, keep = statements(('FALSE', OLD), ('FALSE', OLD), ('TRUE', SENT)), J.Keep()
        head = J.save(run, keep)
        first = learn.proposals([[keep.read()]], 2)
        self.assertEqual(json.dumps(first), json.dumps(learn.proposals([kept(J.restart(keep))], 2)))
        code = ("import sys,json;sys.path.insert(0,sys.argv[1]);from extensions import learn;text,head=json.loads(sys.stdin.read());"
                "print(json.dumps(learn.proposals([[(text,head)]],2),sort_keys=True));"
                "print(json.dumps(sorted(m for m in sys.modules if m.split('.')[0] in ('kernel','extensions','tools','kinds'))))")
        out = subprocess.run([sys.executable, '-I', '-B', '-c', code, str(ROOT)], input=json.dumps([keep.text, head]), capture_output=True, text=True, check=True).stdout.splitlines()
        self.assertEqual(out[0], json.dumps(first, sort_keys=True))
        self.assertEqual(json.loads(out[1]), ['extensions', 'extensions.journal_record', 'extensions.learn'])   # no kernel, no State, not the journal's writer, not the reader

    def test_c8_it_imports_the_record_adapter_and_nothing_else_of_the_lab(self):
        tree = ast.parse((ROOT / 'extensions' / 'learn.py').read_text())
        names = {a.name for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names} | {f'{n.module}.{a.name}' for n in ast.walk(tree) if isinstance(n, ast.ImportFrom) for a in n.names}
        self.assertEqual(sorted(names), ['__future__.annotations', 'extensions.journal_record', 'hashlib', 'json'])
        self.assertEqual([n.id for n in ast.walk(tree) if isinstance(n, ast.Name) and n.id in ('open', 'exec', 'eval', 'globals', 'State', 'Kernel')], [])

    def test_c8_it_reads_up_to_the_head_it_is_given(self):
        run = statements(('FALSE', OLD), ('FALSE', OLD))
        early = [(J.dump(run.journal), {'length': 5, 'sha256': run.journal[4]['sha256']})]   # the head after the first failed check
        self.assertEqual([p['kind'] for p in learn.proposals([early], 2)], ['CHECK_FAILED', 'HANDED_OUT_AGAIN'])   # try 2 went out in that entry
        self.assertEqual([p['kind'] for p in learn.proposals([kept(run)], 2)], ['CHECK_FAILED', 'CHECK_FAILED', 'HANDED_OUT_AGAIN', 'CHECK_FAILED_AGAIN'])

    def test_c9_the_number_is_a_whole_number_two_or_more_and_records_are_a_list(self):
        for least in (1, 0, 2.0, '2', True):
            with self.assertRaises(ValueError):
                learn.proposals([], least)
        with self.assertRaises(ValueError) as said:
            learn.proposals((kept(collections('day')),), 2)   # records handed in as a tuple, not a list
        self.assertEqual(str(said.exception), 'The learn feature reads a list of records')
        self.assertEqual(learn.proposals([], 2), [])

    def test_c9_records_that_are_no_list_of_text_and_head_are_refused_in_this_modules_words(self):
        text, head = kept(collections('day'))[0]
        for records in ([(text, head)], ['xy'], [{'a': 1}], [[]], [[(text, head, 'more')]], [[text]]):   # a record handed in bare, a text, an object, nothing, three parts, one
            with self.assertRaises(ValueError) as said:
                learn.proposals(records, 2)
            self.assertEqual(str(said.exception), learn.NO_RECORD, repr(records)[:40])
        self.assertEqual(learn.proposals([[[text, head]]], 2), learn.proposals([[(text, head)]], 2))   # a pair as a list is a pair
        with self.assertRaises(ValueError) as said:
            learn.proposals([['ab']], 2)   # a text of two letters is no pair: refused here, before the record adapter reads it
        self.assertEqual(str(said.exception), learn.NO_RECORD)

    def test_c9_a_broken_journal_is_refused_in_the_adapters_words_and_one_that_does_not_hold_what_is_read_in_this_modules(self):
        run = collections('day')
        text, head = kept(run)[0]
        with self.assertRaises(ValueError) as said:
            learn.proposals([[(text.replace('arrears_due', 'arrears_dux', 1), head)]], 2)
        self.assertEqual(str(said.exception), 'The journal is broken at entry 1')
        checked = statements(('FALSE', OLD))
        for record in (forged(run, 1, lambda e: e['body']['pack'].update(methods={'not': 'a list'})),   # a method that is no object (TypeError where it is read)
                       forged(run, 1, lambda e: e['body'].update(pack=['not', 'a', 'pack'])),       # a pack that is no object (AttributeError)
                       forged(checked, 4, lambda e: e['body']['row'].pop('source'))):             # a row without its source (KeyError)
            with self.assertRaises(ValueError) as said:
                learn.proposals([record], 2)
            self.assertEqual(str(said.exception), learn.NOT_READ)


class Existing(unittest.TestCase):
    """What the parts the lab had make of the same records (ruling R35): the reader, the Learner, reflect and the record adapter."""
    def test_the_reader_the_learner_and_reflect_say_nothing_of_the_check_rows(self):
        run, keep = statements(('FALSE', OLD), ('FALSE', OLD), ('TRUE', SENT)), J.Keep()
        J.save(run, keep)
        again = J.restart(keep)
        work, learner = [r for seq in sorted(again.detail) for r in again.detail[seq]['runs']], Learner(True)
        self.assertEqual((reader.proposals([keep.read()], 2), [x for r in work for x in learner.learn(r)], reflect(work)['candidates']), ([], [], []))

    def test_the_ledger_holds_a_check_row_without_the_checkers_words_or_the_receipt_it_checks(self):
        run = statements(('FALSE', OLD))
        [handed] = [r for r in R.ledger(kept(run)) if r['what'] == 'handed_in' and 'row' in r]
        self.assertEqual(handed['row'], {'predicate': 'statement_sent', 'truth': 'FALSE', 'source': REVIEW, 'version': 'review-1'})

    def test_the_reader_refuses_records_that_do_not_continue_one_another(self):
        days = [collections('day-1'), collections('day-2')]
        with self.assertRaises(ValueError) as said:
            reader.proposals([kept(d)[0] for d in days], 2)
        self.assertEqual(str(said.exception), 'A journal of this record does not continue the one before it')

    def test_one_learner_fed_every_run_of_two_records_says_one_gap_a_blocked_run_and_names_no_entry(self):
        days, learner = [collections('day-1', blocked=2), collections('day-2')], Learner(True)
        said = [learner.learn(r) for d in days for e in sorted(d.detail) for r in d.detail[e]['runs']]
        gaps = [x for s in said for x in s]
        self.assertEqual([x['gap'] for x in gaps], ['PROVIDER_REQUIRED'] * 3)
        self.assertEqual({k for x in gaps for k in x}, {'kind', 'gap', 'status', 'gate'})   # no journal, no entry, no count

    def test_the_record_adapters_counts_count_runs_of_a_goal_by_status_word_in_one_record(self):
        run = collections('day', blocked=2)
        [goal] = R.counts(kept(run))['goals'].values()
        self.assertEqual((goal['statuses'], [a['entry'] for a in goal['at']]), ({'PROVIDER_REQUIRED': 2, 'WAITING': 1}, [2, 3, 5]))   # by status word, not in a row, one record


class Sequences(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.checks, cls.across, cls.settled = sequence('learn_checks'), sequence('learn_across'), sequence('learn_settled')
        cls.data = json.loads((ROOT / 'results' / 'actual_run_records.json').read_text())

    def test_the_record_on_disk_holds_the_three_sequences(self):
        for name, made in (('learn_checks', self.checks), ('learn_across', self.across), ('learn_settled', self.settled)):
            self.assertEqual(json.dumps(made, sort_keys=True), json.dumps(self.data['scenes'][name], sort_keys=True), name)

    def test_the_recorded_proposals_are_what_the_learn_feature_gives_again_for_the_recorded_texts(self):
        q, a, s = self.checks, self.across, self.settled
        self.assertEqual(learn.proposals([[(q['text'], q['head'])]], 2), q['proposals'])
        self.assertEqual(learn.proposals([[(d['text'], d['head'])] for d in a['days']], 2), a['proposals'])
        self.assertEqual(learn.proposals([[(s['first']['text'], s['first']['head'])], [(s['second']['text'], s['second']['head'])]], 2), s['proposals'])

    def test_c1_the_check_rows_are_the_rows_the_hand_over_kind_reads_as_checks(self):
        q, a, s = self.checks, self.across, self.settled
        texts = [(q['text'], q['head'])] + [(d['text'], d['head']) for d in a['days']] + [(s[k]['text'], s[k]['head']) for k in ('first', 'second')]
        texts += [kept(d)[0] for d in desks()]
        said = [(kind_took(*t), learn_took(*t)) for t in texts]
        self.assertEqual([k for k, _ in said], [l for _, l in said])
        self.assertEqual(sum(len(k) for k, _ in said), 9 + 11)   # the sequences hold 9 check rows (4 in learn_checks, 5 in learn_across), the desks 11

    def test_checks_what_the_learn_feature_says(self):
        props = self.checks['proposals']
        self.assertEqual([(p['kind'], p.get('fact'), p.get('try'), p.get('words')) for p in props],
                         [('CHECK_FAILED', 'statement_sent', 1, OLD), ('CHECK_FAILED', 'statement_sent', 2, OLD), ('CHECK_PASSED', 'statement_sent', 3, SENT),
                          ('CHECK_PASSED', 'servicing_month_judged', 1, ('the statement went out right on the third try; the first two failed on one line, the rate, '
                                                                          'which the writer was never told was changed; the fee line was passed with a note and is still open')),
                          ('HANDED_OUT_AGAIN', 'statement_sent', None, None), ('CHECK_FAILED_AGAIN', 'statement_sent', None, [OLD, OLD])])
        self.assertEqual(props[3]['checker'], JUDGE)   # the verdict of the program's judge is a check row like any other

    def test_checks_what_the_parts_the_lab_had_say_of_the_same_record(self):
        ex = self.checks['existing_parts']
        self.assertEqual((ex['reader'], [x for s in ex['one_learner_fed_in_journal_order'] for x in s], ex['reflect']), ([], [], []))
        self.assertEqual([sorted(r['row']) for r in ex['ledger_rows_of_the_checks']], [['predicate', 'source', 'truth', 'version']] * 4)
        self.assertEqual(ex['counts_of_the_steps'], {'lendco/servicing|' + SEND: {'ran': 3, 'stopped': 0, 'skipped': 0},
                                                     'lendco/servicing|learn-judge-servicing-month@1': {'ran': 1, 'stopped': 0, 'skipped': 0}})

    def test_across_what_the_learn_feature_says(self):
        props = self.across['proposals']
        alone = [(p['kind'], p['record']) for p in props if p['kind'] != 'IN_SEVERAL_RECORDS']
        ids = [json.loads(d['text'].split('\n')[0])['sha256'][:12] for d in self.across['days']]
        self.assertEqual(alone, [('CHECK_FAILED', ids[0]), ('CHECK_PASSED', ids[0]), ('BLOCKED_AGAIN', ids[0]), ('HANDED_OUT_AGAIN', ids[0]),
                                 ('CHECK_FAILED', ids[1]), ('CHECK_PASSED', ids[1]), ('HANDED_OUT_AGAIN', ids[1]), ('CHECK_PASSED', ids[2])])
        several = [(p['what'], p['records'], p['support'], p['record_ids']) for p in props if p['kind'] == 'IN_SEVERAL_RECORDS']
        self.assertEqual(several, [('pack', 3, 3, ids), ('blocked', 3, 4, ids), ('pack', 3, 3, ids), ('check_failed', 2, 2, ids[:2]), ('handed_out_again', 2, 2, ids[:2])])

    def test_across_what_the_parts_the_lab_had_say_of_the_same_records(self):
        ex = self.across['existing_parts']
        self.assertEqual((ex['reader_on_the_three_as_one_record'], ex['reader_on_each_record']), ('A journal of this record does not continue the one before it', [[], [], []]))
        self.assertEqual([[x['gap'] for s in day for x in s] for day in ex['one_learner_fed_every_run_in_order']], [['PROVIDER_REQUIRED'] * 2, ['PROVIDER_REQUIRED'], ['PROVIDER_REQUIRED']])
        self.assertEqual([c['lendco/collections-calls|arrears_call_made']['statuses'].get('PROVIDER_REQUIRED') for c in ex['counts_of_the_goal']], [2, 1, 1])   # by status word, not in a row

    def test_settled_what_the_learn_feature_says(self):
        props = self.settled['proposals']
        self.assertEqual([(p['kind'], p.get('what'), p.get('fact'), p.get('source') or p.get('checker'), p.get('door'), p.get('out') is not None) for p in props],
                         [('STATED_BY_ANOTHER', None, 'refund_approved', BOOK, 'RECONCILED', False),
                          ('STATED_WITHOUT_A_CHECK', None, 'refund_reconciled', RECON, 'RECONCILED', True),
                          ('STATED_BY_ANOTHER', None, 'refund_sent', BOOK, 'RECONCILED', False),
                          ('STATED_BY_ANOTHER', None, 'refund_approved', BOOK, 'DECISION_STANDS', False),
                          ('STATED_WITHOUT_A_CHECK', None, 'refund_reconciled', RECON, 'RECONCILED', False),
                          ('STATED_BY_ANOTHER', None, 'refund_reconciled', AUDIT, 'RECONCILED', False),
                          ('BLOCKED_AGAIN', None, None, None, None, False),
                          ('IN_SEVERAL_RECORDS', 'pack', None, None, None, False),
                          ('IN_SEVERAL_RECORDS', 'stated_by_another', 'refund_approved', BOOK, None, False),
                          ('IN_SEVERAL_RECORDS', 'stated_without_a_check', 'refund_reconciled', RECON, None, False)])

    def test_settled_what_the_parts_the_lab_had_say_of_the_same_records(self):
        ex = self.settled['existing_parts']
        self.assertEqual(ex['reader_on_each_record'], [[], []])
        self.assertEqual([[x['kind'] for s in rec for x in s] for rec in ex['one_learner_on_each_record']], [['REUSE_COMPOSITION'], []])
        self.assertEqual([[(r['row']['predicate'], r['row']['source'], r['status']) for r in rec] for rec in ex['ledger_rows_handed_in_at_the_event_door']],
                         [[('refund_approved', BOOK, 'RECONCILED'), ('refund_reconciled', RECON, 'RECONCILED'), ('refund_sent', BOOK, 'RECONCILED')],
                          [('refund_approved', BOOK, 'DECISION_STANDS'), ('refund_reconciled', RECON, 'RECONCILED'), ('refund_reconciled', AUDIT, 'RECONCILED')]])


class Cases(unittest.TestCase):
    def test_the_three_cases_stand_in_the_table_with_their_packs(self):
        table = {c[0]: (c[3], c[4], c[5]) for c in CASES}
        area = 'Learning from checks and records'
        self.assertEqual([table[i] for i in ('160_learn_statement_handed_over', '161_learn_no_place_for_the_call', '162_learn_refund_asked')],
                         [(S_DESK, True, area), (C_DESK, True, area), (R_DESK, True, area)])

    def test_what_one_look_makes_of_each_case(self):
        def one(names):
            return [(r['goal'], r['status'], r['actions']) for r in Kernel(State.from_packs([pack(n) for n in names])).run_standing(execute=True)['runs']]
        self.assertEqual(one(S_DESK), [('statement_sent', 'WAITING', [SEND]), ('servicing_month_judged', 'WAITING', [])])
        self.assertEqual(one(C_DESK), [('arrears_call_made', 'PROVIDER_REQUIRED', [])])
        self.assertEqual(one(R_DESK), [('refund_sent', 'WAITING', [ASK])])

    def test_the_reconciler_has_two_places(self):
        run = refunds('a')
        event(run, row('refund_approved', 'TRUE', BOOK, 'book-approved'))   # the reconciliation is handed over, try 1
        for n in (1, 2):
            event(run, row('refund_reconciled', 'FALSE', RECON, f'recon-{n}', checks=receipt(run, 'refund_reconciled'), why='the amount is off by one instalment'))
        self.assertEqual([r['status'] for e in (4, 5) for r in run.detail[e]['runs']], ['WAITING', 'PROVIDER_REQUIRED'])   # try 2 goes out, no place for a third

    def test_the_packs_bring_no_kind_and_no_key_of_their_own(self):
        packs = [pack(n) for n in ALL_PACKS]
        self.assertEqual({m['action'] for p in packs for m in p.get('methods', [])}, {'simulate_fact', 'ask', 'handoff'})   # kinds the lab had
        self.assertEqual([m['id'] for p in packs for m in p.get('methods', []) if not m['id'].startswith('learn-')], [])
        self.assertEqual([k for p in packs for k in p if k not in ('schema', 'id', 'scope', 'goals', 'budget', 'preference', 'evidence', 'methods', 'providers', 'grants')], [])


class Limits(unittest.TestCase):
    """What this version does not hold, pinned as it is."""
    def test_l1_words_are_quoted_and_compared_whole_never_judged(self):
        run = statements(('FALSE', 'the check as written cannot be met'), ('FALSE', 'this check was written too strictly by me'))
        [again] = of(learn.proposals([kept(run)], 2), 'CHECK_FAILED_AGAIN')
        self.assertEqual((again['same_words'], sorted(again)), (False, ['at', 'checker', 'fact', 'kind', 'record', 'same_words', 'scope', 'status', 'support', 'times', 'words']))
        self.assertEqual(of(learn.proposals([kept(statements(('TRUE', 'passed, with fourteen findings')))], 2), 'CHECK_PASSED')[0]['kind'], 'CHECK_PASSED')   # a pass that carries findings is a pass

    def test_l2_a_row_of_the_checker_that_reads_unknown_on_the_try_that_is_out_is_not_read(self):
        run = started(S_DESK, 'servicing', [BOOK, REVIEW, JUDGE])
        look(run)
        event(run, row('statement_sent', 'UNKNOWN', REVIEW, 'review-1', checks=receipt(run, 'statement_sent'), why='could not be run yet'))
        self.assertEqual(learn.proposals([kept(run)], 2), [])

    def test_l3_a_desks_own_pack_handed_in_at_every_session_is_one_thing_in_several_records(self):
        props = learn.proposals([kept(refunds('a')), kept(refunds('b'))], 2)
        self.assertEqual([(p['kind'], p.get('what'), p.get('pack'), p.get('records')) for p in props], [('IN_SEVERAL_RECORDS', 'pack', '314_learn_refunds', 2)])

    def test_l4_blocked_runs_are_one_thing_by_the_status_word_alone_whatever_the_goal_or_the_desk(self):
        writer_away = extra('learn-test-writer-away', providers={'agent:statement-writer': 0})
        run = started(S_DESK + [writer_away], 'servicing', [BOOK, REVIEW, JUDGE])
        first = look(run)
        props = of(learn.proposals([kept(run), kept(collections('day'))], 2), 'IN_SEVERAL_RECORDS')
        self.assertEqual([(p['what'], p.get('reason'), p['records']) for p in props if p['what'] == 'blocked'], [('blocked', 'PROVIDER_REQUIRED', 2)])
        self.assertEqual([(r['goal'], r['status']) for r in first['runs']], [('statement_sent', 'PROVIDER_REQUIRED'), ('servicing_month_judged', 'PROVIDER_REQUIRED')])

    def test_l5_what_a_step_does_is_not_read_the_same_words_on_two_facts_are_two_things(self):
        loans = extra('learn-test-two-statements', goals=['statement_sent', 'statement_32_sent'], evidence=[{'predicate': 'statement_32_due', 'truth': 'TRUE', 'verified': True, 'source': BOOK, 'version': 'loan-32'}],
                      methods=[method('learn-send-statement-32@1', 'statement_32_sent', ['statement_32_due'], provider='agent:statement-writer', cost={'compute': 1, 'money': 0, 'attention': 0},
                                      action='handoff', handoff_to='agent:statement-writer', instruction='Write and send the annual statement of loan L-32.', verified_by=REVIEW)],
                      grants=['action:learn-send-statement-32@1'])
        run = started(['310_learn_statements', loans], 'servicing', [BOOK, REVIEW])
        look(run)
        for fact in ('statement_sent', 'statement_32_sent'):
            event(run, row(fact, 'FALSE', REVIEW, 'review-' + fact, checks=receipt(run, fact), why=OLD))
        self.assertEqual(of(learn.proposals([kept(run)], 2), 'CHECK_FAILED_AGAIN'), [])

    def test_l6_it_does_not_replay_a_forged_row_that_still_reads_is_read_as_it_says(self):
        run = statements(('FALSE', OLD))
        record = forged(run, 4, lambda e: e['body']['row'].update(source=BOOK))
        self.assertEqual([p['kind'] for p in learn.proposals([record], 2)], ['STATED_BY_ANOTHER', 'HANDED_OUT_AGAIN'])   # the runs still say what they said

    def test_l7_no_check_of_the_verifier_reads_what_the_learn_feature_proposes(self):
        texts = [f.read_text() for f in [ROOT / 'qa' / 'independent_verify.py'] + sorted((ROOT / 'qa' / 'checks').glob('*.py'))]
        self.assertEqual([t for t in texts if 'learn_' in t or 'CHECK_FAILED_AGAIN' in t or 'STATED_BY_ANOTHER' in t or 'existing_parts' in t], [])
        self.assertFalse((ROOT / 'qa' / 'checks' / 'learn.py').exists())

    def test_l8_a_row_of_the_book_on_what_the_desks_step_already_made_is_read_as_stated_by_another(self):
        q = sequence('learn_settled')['first']
        self.assertEqual([r['actions'] for r in q['steps'][2]['result']['runs']], [[REFUND]])   # entry 4: the refund step ran, before the book's row of entry 5
        [p] = [p for p in learn.proposals([[(q['text'], q['head'])]], 2) if p.get('fact') == 'refund_sent']
        self.assertEqual((p['kind'], p['given'], p['at'][0]['entry']), ('STATED_BY_ANOTHER', [['step', REFUND, REFUND]], 5))

    def test_l9_two_records_whose_first_journals_have_one_header_are_one_journal_and_refused(self):
        for name in ('collections', ''):   # two mornings of one desk started under one name, and under none
            days = [collections(name, blocked=2), collections(name, checks=[('TRUE', 'reached')])]
            self.assertNotEqual(kept(days[0])[0][0], kept(days[1])[0][0])   # two journals, two texts
            self.assertEqual(days[0].journal[0]['sha256'], days[1].journal[0]['sha256'])   # one header, so one name
            with self.assertRaises(ValueError) as said:
                learn.proposals([kept(d) for d in days], 2)
            self.assertEqual(str(said.exception), learn.TWICE)
        named = [kept(collections('collections-day-1', blocked=2)), kept(collections('collections-day-2'))]   # a name each: two records
        self.assertEqual([(p['what'], p['records']) for p in learn.proposals(named, 2) if p['kind'] == 'IN_SEVERAL_RECORDS' and p['what'] == 'blocked'], [('blocked', 2)])

    def test_l10_a_check_is_read_from_the_row_as_written_not_from_what_the_state_reads(self):
        run = started(S_DESK, 'servicing', [BOOK, REVIEW, JUDGE])
        look(run)
        first = receipt(run, 'statement_sent')
        stale = [{'predicate': 'statement_due', 'version': 'loan-31-year-2025'}]   # the loan book's row is of 2026: this no longer holds
        event(run, row('statement_sent', 'FALSE', REVIEW, 'review-1', checks=first, why=OLD, depends_on=stale))
        self.assertEqual(run.state.fact('statement_sent')['truth'], 'UNKNOWN')   # the State reads no check ...
        self.assertEqual([(k, v['receipt'], v['failed']) for k, v in open_handoffs(run.state).items() if k.endswith('|statement_sent')],
                         [('lendco/servicing|statement_sent', first, None)])   # ... and the kind still waits on try 1
        event(run, row('statement_sent', 'TRUE', REVIEW, 'review-2', checks=first, why=SENT))
        self.assertEqual([(p['kind'], p['try'], p['receipt']) for p in learn.proposals([kept(run)], 2) if p['kind'].startswith('CHECK_')],
                         [('CHECK_FAILED', 1, first), ('CHECK_PASSED', 1, first)])   # the learn feature reads both rows as written
        self.assertEqual((kind_took(*kept(run)[0]), learn_took(*kept(run)[0])), ([{'entry': 5}], [{'entry': 4}, {'entry': 5}]))   # the kind reads only the second

    def test_l11_a_finding_in_words_enters_at_the_event_door_and_is_read_only_as_a_check_or_a_stated_row(self):
        run = started(S_DESK, 'servicing', [BOOK, REVIEW, JUDGE])
        look(run)
        found = 'found by the servicing officer: the statement writer and the statement review are one agent'
        with self.assertRaises(ValueError) as said:   # in the finder's name alone the event door refuses it: the finder is no checker the header names
            run.add('event', {'row': row('writer_and_review_are_one_agent', 'TRUE', 'person:servicing-officer', 'finding-1', why=found), 'execute': True})
        self.assertEqual(str(said.exception), 'The event door lets in only verified rows that are not decisions, from a checker the header names')
        rows_in_a_pack(run, 'learn-test-finding-in-a-pack', row('writer_and_review_are_one_agent', 'TRUE', 'person:servicing-officer', 'finding-1', why=found))
        self.assertEqual(run.state.fact('writer_and_review_are_one_agent')['source'], 'person:servicing-officer')   # the pack door checks no source: the State keeps it
        handed = found + '; handed in by the program judge'
        self.assertEqual(event(run, row('writer_and_review_are_one_agent', 'TRUE', JUDGE, 'finding-2', why=handed))['status'], 'RECONCILED')
        self.assertEqual(learn.proposals([kept(run)], 2), [])   # both doors took it; on a fact no method makes nothing reads it
        event(run, row('statement_sent', 'TRUE', REVIEW, 'review-1', checks=receipt(run, 'statement_sent'), why=SENT))   # the month's account goes out
        verdict = 'the account leaves one thing out; ' + handed
        event(run, row('servicing_month_judged', 'FALSE', JUDGE, 'verdict-1', checks=receipt(run, 'servicing_month_judged'), why=verdict))
        self.assertEqual([(p['kind'], p['fact'], p['checker'], p['words']) for p in learn.proposals([kept(run)], 2)],
                         [('CHECK_PASSED', 'statement_sent', REVIEW, SENT), ('CHECK_FAILED', 'servicing_month_judged', JUDGE, verdict)])   # as the check of a try it is read, with its words

    def test_l12_a_row_the_asked_party_hands_in_at_the_event_door_is_not_read(self):
        run = started(R_DESK, 'refunds', [BOOK, RECON, AUDIT, FINANCE])   # finance is also a checker the door lets in
        look(run)   # the question to finance is out
        self.assertEqual(event(run, row('refund_approved', 'TRUE', FINANCE, 'finance-row'))['status'], 'RECONCILED')   # finance's yes, at the event door and not as an answer
        self.assertIn('lendco/refunds|refund_approved', open_asks(run.state))   # the question is still out: no answer came
        self.assertEqual(learn.proposals([kept(run)], 2), [])   # it is no answer, and no row of another source

    def test_l13_a_row_handed_in_twice_is_read_twice(self):
        one_place = extra('learn-test-one-place', providers={'agent:statement-writer': 1})
        run = started(['310_learn_statements', one_place], 'servicing', [BOOK, REVIEW])
        look(run)
        first = receipt(run, 'statement_sent')
        for _ in range(2):   # one row of the review, with one version, handed in twice
            event(run, row('statement_sent', 'FALSE', REVIEW, 'review-1', checks=first, why=OLD))
        self.assertEqual(kind_took(*kept(run)[0]), [{'entry': 4}, {'entry': 5}])   # the kind reads each as the check when it is kept
        [again] = of(learn.proposals([kept(run)], 2), 'CHECK_FAILED_AGAIN')
        self.assertEqual((again['times'], again['same_words'], again['at']), (2, True, [cite(run, 4), cite(run, 5)]))   # rows are counted, not checks made

    def test_l14_a_refused_run_is_a_blocked_run_here(self):
        run = refunds('no')
        run.add('answer', {'receipt': run.detail[2]['runs'][0]['model_receipts'][-1], 'truth': 'FALSE', 'source': FINANCE, 'execute': True})   # finance's no, a decision
        look(run)
        runs = [r for e in sorted(run.detail) for r in run.detail[e]['runs']]
        self.assertEqual(([r['status'] for r in runs], [x for r in runs for x in Learner(True).learn(r)]), (['WAITING', 'REFUSED', 'REFUSED'], []))   # the Learner names no gap for a no
        self.assertEqual([(p['kind'], p['reason'], p['times']) for p in learn.proposals([kept(run)], 2)], [('BLOCKED_AGAIN', 'REFUSED', 2)])
        learner = Learner(True)
        self.assertEqual([x for r in runs for x in learner.learn(r)], [])   # one Learner fed every run names no gap for a no either

    def test_l15_a_kept_pack_row_with_no_source_refuses_its_record_and_every_record_handed_in_with_it(self):
        good, noted = statements(('FALSE', OLD), name='servicing-a'), statements(('FALSE', OLD), name='servicing-b')
        rows_in_a_pack(noted, 'learn-test-branch-note', {'predicate': 'branch_note_filed', 'truth': 'TRUE', 'verified': True, 'version': 'note-1'})   # verified, no source, on a fact no method makes
        self.assertEqual((noted.state.fact('branch_note_filed')['truth'], noted.state.fact('branch_note_filed').get('source')), ('TRUE', None))   # the State keeps it
        self.assertEqual([p['kind'] for p in learn.proposals([kept(good)], 2)], ['CHECK_FAILED', 'HANDED_OUT_AGAIN'])
        asked = refunds('asked')
        rows_in_a_pack(asked, 'learn-test-unsigned-yes', {'predicate': 'refund_approved', 'truth': 'TRUE', 'verified': True, 'version': 'unsigned-1'})   # on a fact the plan gives to finance
        self.assertEqual(asked.state.fact('refund_approved')['truth'], 'TRUE')
        for records in ([kept(noted)], [kept(good), kept(noted)], [kept(noted), kept(good)], [kept(asked)]):
            with self.assertRaises(ValueError) as said:
                learn.proposals(records, 2)
            self.assertEqual(str(said.exception), learn.NOT_READ)   # the whole call is refused, a good record handed in with it too
        self.assertEqual((len(R.ledger(kept(noted))), reader.proposals(kept(noted), 2)), (len(R.ledger(kept(good))) + 1, []))   # the record adapter and the reader read it

    def test_l16_a_question_is_one_thing_of_several_records_only_with_its_party_and_its_answers_truth(self):
        def things(runs):
            return [(p['what'], p['records']) for p in of(learn.proposals([kept(r) for r in runs], 2), 'IN_SEVERAL_RECORDS')]

        def answered(name, truth):   # the refund desk after its first look; finance answers its question, or no answer comes
            run = refunds(name)
            if truth is not None:
                run.add('answer', {'receipt': run.detail[2]['runs'][0]['model_receipts'][-1], 'truth': truth, 'source': FINANCE, 'execute': True})
            return run
        self.assertEqual(things([answered('yes', 'TRUE'), answered('no', 'FALSE')]), [('pack', 2)])   # one question, yes in one record and no in the other: no one thing
        self.assertEqual(things([answered('open-1', None), answered('open-2', None)]), [('pack', 2)])   # asked in both and never answered: no one thing
        self.assertEqual(things([answered('yes-1', 'TRUE'), answered('yes-2', 'TRUE')]), [('pack', 2), ('answer', 2)])   # answered alike: one thing
        desk = pack('314_learn_refunds')
        ask = dict(desk['methods'][0], id='learn-test-ask-finance-again@1', grant='action:learn-test-ask-finance-again@1')   # the same question to the same party, by a step of another id
        renamed = dict(desk, id='learn-test-desk-renamed-ask', methods=[ask] + desk['methods'][1:], grants=[ask['grant']] + desk['grants'][1:])
        books = []
        for name, p in (('book-1', '314_learn_refunds'), ('book-2', '314_learn_refunds'), ('book-3', renamed)):
            run = started([p], name, [BOOK, RECON, AUDIT])
            look(run)
            event(run, row('refund_approved', 'TRUE', BOOK, 'book-approved'))   # the loan book states finance's yes
            books.append(run)
        self.assertEqual([p['given'] for p in of(learn.proposals([kept(books[2])], 2), 'STATED_BY_ANOTHER')], [[['asked', FINANCE, 'learn-test-ask-finance-again@1']]])
        self.assertEqual(things(books[:2]), [('pack', 2), ('stated_by_another', 2)])   # one ask: one thing
        self.assertEqual(things([books[0], books[2]]), [])   # whom the plan gives the fact to is keyed with the step's id: two things


def receipt_at(run, n):   # the receipt of the hand-over the run of entry n handed out on the statement
    return next(r['model_receipts'][-1]['sha256'] for r in run.detail[n]['runs'] if r['goal'] == 'statement_sent')


def desks():
    """Desks the claims of the kind's reading are held on, beside the sequences and the random histories: rows at the event door, in packs,
    kept for another scope, turned away because a decision stands, decisions, a row of another checker of the plan, a row handed in twice."""
    out = [statements(('FALSE', OLD), ('FALSE', OLD), ('TRUE', SENT)), statements(('FALSE', OLD))]
    one_place = started(['310_learn_statements', extra('learn-test-one-place', providers={'agent:statement-writer': 1})], 'servicing', [BOOK, REVIEW])
    look(one_place)
    for truth, words in (('FALSE', OLD), ('FALSE', OLD), ('TRUE', SENT)):   # try 1 fails twice with no place for try 2 (one row handed in twice), then passes
        event(one_place, row('statement_sent', truth, REVIEW, 'review-' + truth, checks=receipt_at(one_place, 3), why=words))
    booked = started(S_DESK, 'servicing', [BOOK, REVIEW, JUDGE])
    look(booked)
    event(booked, row('statement_sent', 'TRUE', BOOK, 'book-1'))   # the book closes try 1; the review's row on it comes after
    event(booked, row('statement_sent', 'TRUE', REVIEW, 'review-1', checks=receipt_at(booked, 3)))
    in_packs = started(['310_learn_statements'], 'servicing', [BOOK, REVIEW])   # the review's rows in packs
    look(in_packs)
    rows_in_a_pack(in_packs, 'learn-test-review-in-a-pack', row('statement_sent', 'FALSE', REVIEW, 'review-1', checks=receipt(in_packs, 'statement_sent'), why=OLD))
    look(in_packs)
    rows_in_a_pack(in_packs, 'learn-test-review-again', row('statement_sent', 'TRUE', REVIEW, 'review-2', checks=receipt(in_packs, 'statement_sent'), why=SENT))
    look(in_packs)
    elsewhere = started(['310_learn_statements'], 'servicing', [BOOK, REVIEW])   # the review's rows kept for the loan the desk is not on
    look(elsewhere)
    first = receipt(elsewhere, 'statement_sent')
    elsewhere.add('pack', {'pack': extra('learn-test-loan-32', scope=OTHER, evidence=[row('statement_due', 'TRUE', BOOK, 'loan-32-year-2026')])})
    look(elsewhere)   # loan 32's statement goes out too
    event(elsewhere, row('statement_sent', 'FALSE', REVIEW, 'review-1', checks=first, why=OLD, scope=SERVICING))
    other = receipt(elsewhere, 'statement_sent')
    elsewhere.add('pack', {'pack': extra('learn-test-back-to-loan-31', scope=SERVICING)})
    look(elsewhere)
    event(elsewhere, row('statement_sent', 'TRUE', REVIEW, 'review-2', checks=other, why=SENT, scope=OTHER))
    elsewhere.add('pack', {'pack': extra('learn-test-loan-32-again', scope=OTHER)})
    look(elsewhere)
    decided = started(['310_learn_statements'], 'servicing', [BOOK, REVIEW])   # a decision, a row it turns away, the checker's own decision
    look(decided)
    first = receipt(decided, 'statement_sent')
    rows_in_a_pack(decided, 'learn-test-hold', row('statement_sent', 'FALSE', HOLD, 'hold-1', final=True))
    event(decided, row('statement_sent', 'TRUE', REVIEW, 'review-1', checks=first))
    rows_in_a_pack(decided, 'learn-test-review-decides', row('statement_sent', 'TRUE', REVIEW, 'review-2', checks=first, final=True))
    look(decided)
    two_ways = started(['310_learn_statements', officer()], 'servicing', [BOOK, REVIEW, AUDIT])   # the audit's row on the writer's try
    look(two_ways)
    event(two_ways, row('statement_sent', 'TRUE', AUDIT, 'audit-1', checks=receipt(two_ways, 'statement_sent')))
    return out + [one_place, booked, in_packs, elsewhere, decided, two_ways]


def kind_took(text, head):
    """The rows the hand-over kind reads as the check of the try that is out, each right after the State keeps it, cited as the learn
    feature cites them ({entry} or {entry, evidence}). The journal is put again through its doors on a new run. Before a pack or an event
    entry, a copy of the State keeps its rows one by one as the door would (State.observe; a pack's scope first), and for every row the
    copy keeps, the kind's own reading (kinds/handoff.py, _said) is asked in the row's scope against the try its books hold there."""
    es = R.entries(text, head)
    run, took = J.start(es[0]['body']['kinds'], es[0]['body']['checkers'], name=es[0]['body'].get('name', '')), []
    for e in es[1:]:
        if e['kind'] in ('pack', 'event'):
            twin = copy.deepcopy(run.state, {id(run.state.actions): run.state.actions})
            books = twin.active_work.get('handoff', {})
            body = e['body'].get('pack') or {}
            if type(body.get('scope')) is str:
                twin.scope = body['scope']
            rows = [(r, {'evidence': i}) for i, r in enumerate(body.get('evidence', []))] if e['kind'] == 'pack' else [(e['body']['row'], {})]
            for r, where in rows:
                if twin.observe(r):
                    here, twin.scope = twin.scope, r.get('scope', twin.scope)
                    entry = books.get(twin.scope + '|' + r['predicate'])
                    seen = HANDOFF._said(twin, entry) if entry else None
                    twin.scope = here
                    if seen is not None and dict(seen, scope=None) == dict(r, scope=None):
                        took.append(dict({'entry': e['seq']}, **where))
        if run.add(e['kind'], e['body'])['result'] != e['result']:
            raise AssertionError(f"entry {e['seq']} does not come out again")
    return took


def learn_took(text, head):   # the rows the learn feature reads as check rows, cited as kind_took cites them
    return [{k: p['at'][0][k] for k in ('entry', 'evidence') if k in p['at'][0]} for p in learn.proposals([[(text, head)]], 2) if p['kind'] in ('CHECK_FAILED', 'CHECK_PASSED')]


def kind_told(text, head):
    """What the kind itself tells of the checks, read from the kept text: for every try a later receipt names under `before`, what its
    check said (truth, and why when it is one text), and for every try a HANDOFF_CLOSED line names, whether it was confirmed."""
    told, confirmed = {}, {}
    for e in R.entries(text, head):
        for b in e['result'].get('briefs', []):
            for x in b['receipts']:
                for t in (x.get('handoff') or {}).get('before', []):
                    told[t['receipt']] = t['checked'] and (t['checked']['truth'], t['checked'].get('why'))
            for line in b.get('settled', []):
                if line['operation'] == 'HANDOFF_CLOSED':
                    confirmed[line['data']['receipt']] = line['data']['confirmed']
    return told, confirmed


def learn_said(text, head):   # what the learn feature says each try's check said: its last check row (truth, words), by receipt
    said = {}
    for p in learn.proposals([[(text, head)]], 2):
        if p['kind'] in ('CHECK_FAILED', 'CHECK_PASSED'):
            said[p['receipt']] = ('TRUE' if p['kind'] == 'CHECK_PASSED' else 'FALSE', p['words'])
    return said


def random_history(seed):
    """One history of the servicing desk in random steps, made from a fixed seed: looks run or not; rows of the review, the judge and the
    loan book, reading TRUE, FALSE or UNKNOWN, on a receipt that is out, an earlier one or none, at the event door or in a pack, some
    naming the loan the desk is on and some the other; the desk moving to the other loan and back; places given to the writer again;
    now and then a decision in a pack. No row has `depends_on` (L10)."""
    rnd, run = random.Random(seed), J.start(KINDS, [BOOK, REVIEW, JUDGE], name=f'random-{seed}')
    for p in ['310_learn_statements'] + (['311_learn_month_judged'] if rnd.random() < 0.5 else []):
        run.add('pack', {'pack': pack(p)})
    if rnd.random() < 0.5:
        run.add('pack', {'pack': extra('learn-test-one-place', providers={'agent:statement-writer': 1})})
    known = {REVIEW: [], JUDGE: []}   # every try handed out so far, in either loan, by the checker it names: (loan, receipt)
    for step in range(rnd.randint(10, 24)):
        for key, v in run.state.active_work.get('handoff', {}).items():
            if (key.split('|')[0], v['receipt']) not in known[v['checker']]:
                known[v['checker']].append((key.split('|')[0], v['receipt']))
        what = rnd.choice(['look', 'look', 'look', 'event', 'event', 'event', 'event', 'pack', 'pack', 'book', 'place', 'place', 'move', 'move', 'decide'])
        if what == 'look':
            run.add('look', {'execute': rnd.random() < 0.8})
            continue
        if what == 'place':
            run.add('pack', {'pack': extra(f'learn-test-place-{step}', providers={'agent:statement-writer': rnd.randint(0, 3)})})
            continue
        if what == 'move':
            there = OTHER if run.state.scope == SERVICING else SERVICING
            run.add('pack', {'pack': extra(f'learn-test-move-{step}', scope=there, evidence=[row('statement_due', 'TRUE', BOOK, 'loan-32-year-2026')] if there == OTHER else [])})
            continue
        by = BOOK if what in ('book', 'decide') else rnd.choice([REVIEW, REVIEW, JUDGE])
        fact = 'servicing_month_judged' if by == JUDGE or (by == BOOK and rnd.random() < 0.2) else 'statement_sent'
        r = row(fact, rnd.choice(['TRUE', 'FALSE', 'FALSE', 'FALSE', 'UNKNOWN']), by, f'v{step}', why=rnd.choice(['the rate', 'the fee', None, ['a', 'list']]))
        tries = known[by] if by in known else known[rnd.choice([REVIEW, JUDGE])]   # the loan book names a try of either checker
        if tries and rnd.random() < 0.8:
            loan, r['checks'] = tries[-1] if rnd.random() < 0.7 else rnd.choice(tries)
            if rnd.random() < 0.5:
                r['scope'] = loan   # the row names the loan its try went out on, which may not be the loan the desk is on
        elif rnd.random() < 0.5:
            r['checks'] = 'no-such-receipt'
        if 'scope' not in r and rnd.random() < 0.2:
            r['scope'] = rnd.choice([SERVICING, OTHER])
        if what == 'decide':
            r.update(final=True, truth=rnd.choice(['TRUE', 'FALSE']))
        if what in ('pack', 'decide'):
            more = [dict(r, version=f'v{step}-again', truth=rnd.choice(['TRUE', 'FALSE']))] if what == 'pack' and rnd.random() < 0.3 else []
            run.add('pack', {'pack': extra(f'learn-test-rows-{step}', evidence=[r] + more)})
        else:
            run.add('event', {'row': r, 'execute': rnd.random() < 0.85})
    return run


if __name__ == '__main__':
    unittest.main()
