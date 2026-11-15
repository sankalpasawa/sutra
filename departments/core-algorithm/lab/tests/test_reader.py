"""0.19.0-reader: learning from past runs (ruling R27 of the program, tried under R35). The reader (extensions/reader.py), the packs of
three desks of a lender, cases 88 to 91 and the recorded sequences `reader_lesson`, `reader_one_way` and `reader_answers`.
A test named test_cN_... pins claim CN of the README passage and a test named test_lN_... pins limit LN as the build behaves today.
The class Existing holds what the parts the lab had make of the same record: the attempt ruling R35 asks for before a part is added
(for the stops and the chain in memory; what the three sequences record of it, the answers too, is held in the class Sequences).
The sequences are compared with the built record (results/actual_run_records.json), so these tests run after tools/run_all.py.
A test or a block of lines marked `added when the confirming round was settled` pins what the confirming review found, as the version behaves
today (rulings R19 and R34 of the program): no code, pack, case or scene of the version was changed for it."""
from pathlib import Path
import unittest, sys, json, ast, re, subprocess, hashlib, importlib.util
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from kernel.core import State, Kernel, digest
from tools.run_all import CASES, pack
from extensions import journal as J
from extensions import journal_record as R
from extensions import reader
from extensions.asks import answer, open_asks
from extensions.reflection import Learner, reflect

BOOK, POLICY, FINANCE = 'fixture/loan-book', 'fixture/change-policy', 'system:lendco/finance'
SCOPE_C, SCOPE_P, DONE = 'lendco/collections', 'lendco/payouts', 'LOCAL_MODEL_EFFECTS_RECORDED'
C_DESK, P_DESK = ['220_collections_desk', '221_collections_changes'], ['224_payout_desk', '225_payout_changes']
REMIND, PHONE, OWN_L, CHECK_L = 'send-reminder@1', 'send-reminder-by-phone@1', 'approve-own-reminder-lesson@1', 'check-reminder-lesson-independently@1'
CHAIN, ONE, OWN_P, CHECK_P = ['check-payout-payee@1', 'pay-payout@1', 'reconcile-payout@1'], 'settle-payout-in-one@1', 'approve-own-payout-way@1', 'check-payout-way-independently@1'
WHY = 'Prerequisite not true before effect: borrower_reachable'
CHAIN_COST, ONE_COST, TOKEN = {'compute': 5, 'money': 1, 'attention': 0}, {'compute': 2, 'money': 1, 'attention': 0}, {'compute': 1, 'money': 0, 'attention': 0}
QUESTION = 'May the late fee of this loan be waived?'
ALL_PACKS = ['220_collections_desk', '221_collections_changes', '222_reminder_lesson', '223_lesson_judged_weighty', '224_payout_desk', '225_payout_changes', '226_payout_in_one',
             '227_checker_away', '228_waiver_desk', '229_own_waivers']   # every pack this version brings
MAY_WAIVE, OWN_WAIVERS, SCOPE_W = 'May the late fee of this loan be waived?', 'ask-finance-own-waivers@1', 'lendco/waivers'
ASKS, WAIVES = [f'ask-finance-waiver-{n}@1' for n in (201, 202, 203)], [f'waive-late-fee-{n}@1' for n in (201, 202, 203)]
OWN_204, WAIVE_204 = 'approve-own-waiver-204@1', 'waive-late-fee-204@1'
RISK, FREE = 'system:lendco/risk', {'compute': 0, 'money': 0, 'attention': 0}


def overdue(day):
    return {'predicate': 'instalment_overdue', 'truth': 'TRUE', 'verified': True, 'source': BOOK, 'version': f'loan-7-day-{day}'}


def due(loan):
    return {'predicate': 'payout_due', 'truth': 'TRUE', 'verified': True, 'source': BOOK, 'version': f'loan-{loan}'}


def extra(id, **fields):   # a pack made in memory, for one test
    return {'schema': 'sutra-extension/2', 'id': id, **fields}


def started(packs, name, kinds=('simulate_fact',)):   # a journal with its packs handed in; a pack is a scenario file's name or a pack made in memory
    run = J.start(list(kinds), [BOOK, reader.SOURCE], name=name)
    for p in packs:
        run.add('pack', {'pack': pack(p) if type(p) is str else p})
    return run


def look(run, execute=True):
    return run.detail[run.add('look', {'execute': execute})['seq']]['runs']


def event(run, row):
    return run.detail[run.add('event', {'row': row, 'execute': True})['seq']]['runs']


def kept(run):   # the journal as a keeper holds it: its text and its head
    return [(J.dump(run.journal), {'length': len(run.journal), 'sha256': run.journal[-1]['sha256']})]


def collections(days=3):   # the collections desk after so many days: one look, then the instalment restated day by day
    run = started(C_DESK, 'collections')
    look(run)
    for day in range(2, days + 1):
        event(run, overdue(day))
    return run


def payouts(loans=3):   # the payout desk after so many loans
    run = started(P_DESK, 'payouts')
    look(run)
    for loan in range(102, 101 + loans):
        event(run, due(loan))
    return run


def waivers():   # the waiver desk of pack 228: three loans, one question each to finance, three times yes
    run = started(['228_waiver_desk'], 'waivers', kinds=('simulate_fact', 'ask'))
    for r in look(run)[:3]:
        run.add('answer', {'receipt': r['model_receipts'][-1], 'truth': 'TRUE', 'source': FINANCE, 'execute': True})
    return run


def cites(run, *entries, runs=True):   # what a proposal says of the entries it rests on
    j = run.journal[0]['sha256'][:12]
    return [dict({'journal': j, 'entry': n, 'sha256': run.journal[n]['sha256']}, **({'run': f'{j}:{n}.0'} if runs else {})) for n in entries]


def st(runs):
    return [(r['goal'], r['status'], r['actions']) for r in runs]


def said(s, name):   # the stored row of a yes, as a look reads it
    x = s.fact(name)
    return (x['truth'], x.get('source'), x.get('depends_on'))


def admissions(r):
    return [(e['data']['methods'], e['data']['accepted'], e['data']['blockers']) for e in r['trace'] if e['operation'] == 'ADMISSION']


def answers(s):
    return {a: s.fact('change_weight=' + a)['truth'] for a in ('small', 'weighty')}


def value(v):   # the value row of the axis alone, as a pack
    return extra('t-reader-value-' + v, evidence=[{'predicate': 'change_weight', 'truth': 'TRUE', 'verified': True, 'source': POLICY, 'version': v}])


def exactly(words):   # a refusal in exactly these words
    return '^' + re.escape(words) + '$'


def rechained(run, n, change):   # the kept journal with entry n changed and every entry from it on chained again, under a head of its own: a forger's text
    entries = [json.loads(line) for line in kept(run)[0][0].split('\n')[:-1]]
    change(entries)
    prev = entries[n - 1]['sha256']
    for e in entries[n:]:
        e['prev_sha256'] = prev
        e['sha256'] = prev = digest({k: e[k] for k in ('seq', 'prev_sha256', 'kind', 'body', 'result')})
    return [(J.dump(entries), {'length': len(entries), 'sha256': prev})]


def sequence(name, old=None, new=None):   # one recorded sequence made again, as tools/run_all.py makes it; with `old`, from the scene's text with that one line changed
    text = (ROOT / 'tools' / 'scenes' / (name + '.py')).read_text()
    if old is not None:
        assert text.count(old) == 1, old
        text = text.replace(old, new)
    ns = {'__name__': 'tools.scenes.' + name}
    exec(compile(text, name, 'exec'), ns)
    made = ns['scene']({'State': State, 'Kernel': Kernel, 'pack': pack, 'answer': answer, 'open_asks': open_asks, 'Learner': Learner, 'digest': digest})
    return json.loads(json.dumps(made, ensure_ascii=False, allow_nan=False))


class Reading(unittest.TestCase):
    """C1 to C3: what the reader says of a kept journal."""
    def test_c1_three_stops_for_one_reason_are_one_proposal_that_names_its_entries(self):
        run = collections(3)
        self.assertEqual([e['kind'] for e in run.journal], ['header', 'pack', 'pack', 'look', 'event', 'event'])
        self.assertEqual(reader.proposals(kept(run), 3), [{'kind': 'REPEATED_STOP', 'scope': SCOPE_C, 'goal': 'reminder_sent', 'step': REMIND, 'reason': WHY,
                                                           'support': 3, 'at': cites(run, 3, 4, 5), 'status': 'PROPOSED_ONLY'}])

    def test_c1_runs_are_counted_by_entry_never_by_trace_root(self):
        run = started(C_DESK, 'same-look')
        roots = [look(run)[0]['trace_root_sha256'] for _ in range(3)]   # three looks at a State that was handed nothing in between
        self.assertEqual(len(set(roots)), 1)
        self.assertEqual([(p['support'], p['at']) for p in reader.proposals(kept(run), 3)], [(3, cites(run, 3, 4, 5))])

    def test_c1_two_stops_are_not_three_and_the_number_is_the_callers(self):
        run = collections(2)
        self.assertEqual(reader.proposals(kept(run), 3), [])
        self.assertEqual([(p['kind'], p['support'], p['at']) for p in reader.proposals(kept(run), 2)], [('REPEATED_STOP', 2, cites(run, 3, 4))])
        for least in (1, 0, -3, True, 2.0, '3', None):
            with self.assertRaisesRegex(ValueError, exactly('A repeat is two times or more: `least` is a whole number, 2 or more')):
                reader.proposals(kept(run), least)
        with self.assertRaises(TypeError):   # the reader holds no number of its own
            reader.proposals(kept(run))

    def test_c1_a_stop_for_another_reason_ends_the_row_though_the_step_is_the_same(self):
        desk = pack('220_collections_desk')   # the same desk, its reminder waiting on two facts that each hold only through a rule
        desk['rules'].append({'id': 'R-NOTE@t', 'head': 'fee_note_ready', 'branches': [['phone_on_file']], 'approved': True, 'source': 'fixture/reviewed-domain-theory'})
        desk['methods'][0]['requires'].append('fee_note_ready')
        run = started([desk], 'two-reasons')
        look(run)
        event(run, overdue(2))
        third = event(run, {'predicate': 'borrower_reachable', 'truth': 'TRUE', 'verified': True, 'source': BOOK, 'version': 'called-1'})   # one of the two is stated: the reason changes
        self.assertEqual([run.detail[n]['runs'][0]['stopped']['reason'] for n in (2, 3)], [WHY + ' fee_note_ready'] * 2)
        self.assertEqual(third[0]['stopped'], {'method': REMIND, 'reason': 'Prerequisite not true before effect: fee_note_ready'})
        self.assertEqual(R.counts(kept(run))['steps'][SCOPE_C + '|' + REMIND]['stopped'], 3)   # the count the lab had: three stops of the step
        self.assertEqual((reader.proposals(kept(run), 3), reader.proposals(kept(run), 2)), ([], []))   # two for one reason, then one for another: no row of two
        event(run, overdue(3))
        event(run, overdue(4))
        self.assertEqual([(p['reason'], p['support'], p['at']) for p in reader.proposals(kept(run), 3)],
                         [('Prerequisite not true before effect: fee_note_ready', 3, cites(run, 4, 5, 6))])

    def test_c1_a_dry_look_and_a_run_in_which_nothing_ran_neither_count_nor_break_the_row(self):
        run = started(C_DESK, 'passed-over')
        look(run)                                                                                   # entry 3: a stop
        self.assertEqual(st(look(run, execute=False))[0], ('reminder_sent', 'PLAN_READY', [REMIND]))   # entry 4: a dry look offers the plan and runs nothing
        run.add('pack', {'pack': extra('t-reader-grant-away', revoke_grants=['action:' + REMIND])})  # entry 5
        blocked = event(run, overdue(2))                                                             # entry 6: blocked, nothing ran and nothing stopped
        self.assertEqual((st(blocked), blocked[0]['stop_reasons']), ([('reminder_sent', 'QUERY_EVIDENCE', [])], ['AUTHORITY_REQUIRED', 'QUERY_EVIDENCE']))
        run.add('pack', {'pack': extra('t-reader-grant-back', grants=['action:' + REMIND])})         # entry 7
        event(run, overdue(3))                                                                      # entry 8: a stop
        self.assertEqual(reader.proposals(kept(run), 3), [])
        event(run, overdue(4))                                                                      # entry 9: a stop
        self.assertEqual([(p['support'], p['at']) for p in reader.proposals(kept(run), 3)], [(3, cites(run, 3, 8, 9))])

    def test_c1_a_run_that_reads_the_goal_done_with_no_step_neither_counts_nor_breaks_the_row(self):
        run = collections(2)   # entries 3 and 4: two stops
        by_letter = {'predicate': 'reminder_sent', 'truth': 'TRUE', 'verified': True, 'source': BOOK, 'version': 'by-letter-day-2',
                     'depends_on': [{'predicate': 'instalment_overdue', 'version': 'loan-7-day-2'}]}   # the branch sent a letter: the loan book says so, for that day's instalment
        met = event(run, by_letter)   # entry 5: the goal reads done, no step ran and none stopped
        self.assertEqual((st(met), met[0]['work_state'], met[0]['model_receipts'], 'stopped' in met[0]), ([('reminder_sent', 'SUPPORTED_BY_EVIDENCE', [])], 'completed', [], False))
        self.assertEqual([(p['support'], p['at']) for p in reader.proposals(kept(run), 2)], [(2, cites(run, 3, 4))])   # the two stops are still the newest runs
        third = event(run, overdue(3))   # entry 6: a new day, the letter's row no longer reads, and the step stops again
        self.assertEqual(third[0]['stopped'], {'method': REMIND, 'reason': WHY})
        self.assertEqual([(p['kind'], p['support'], p['at']) for p in reader.proposals(kept(run), 3)], [('REPEATED_STOP', 3, cites(run, 3, 4, 6))])   # stop, stop, done by a row, stop: a row of three

    def test_c1_a_stop_at_another_step_for_the_same_reason_is_no_stop_of_the_row(self):
        run = started(['220_collections_desk'], 'another-step')
        look(run)   # entry 2: send-reminder@1 stops
        letter = {'id': 'send-letter@t', 'effect': 'reminder_sent', 'requires': ['instalment_overdue', 'borrower_reachable'], 'provider': 'local-provider',
                  'grant': 'action:send-letter@t', 'cost': TOKEN, 'action': 'simulate_fact', 'approved': True}
        run.add('pack', {'pack': extra('t-reader-by-letter', methods=[letter], grants=['action:send-letter@t'], revoke_grants=['action:' + REMIND])})   # entry 3: another step, the same prerequisites
        stops = [event(run, overdue(day))[0]['stopped'] for day in (2, 3)]   # entries 4 and 5: send-letter@t stops
        self.assertEqual(([run.detail[2]['runs'][0]['stopped']] + stops), [{'method': REMIND, 'reason': WHY}] + [{'method': 'send-letter@t', 'reason': WHY}] * 2)   # three stops, one reason, two steps
        self.assertEqual(reader.proposals(kept(run), 3), [])   # alike is the step and the reason: no row of three
        self.assertEqual([(p['step'], p['reason'], p['support'], p['at']) for p in reader.proposals(kept(run), 2)], [('send-letter@t', WHY, 2, cites(run, 4, 5))])

    def test_c1_a_goal_named_twice_runs_twice_in_one_entry_and_both_runs_count(self):
        desk = pack('220_collections_desk')
        desk['goals'] = desk['goals'] * 2   # a pack that names the goal twice: one look gives two runs of it
        run = started([desk], 'named-twice')
        self.assertEqual(st(look(run)), [('reminder_sent', 'STEP_STOPPED', [])] * 2)
        j = run.journal[0]['sha256'][:12]
        self.assertEqual([(p['support'], p['at']) for p in reader.proposals(kept(run), 2)],   # a repeat after ONE look: counted by run of an entry, not by entry
                         [(2, [{'journal': j, 'entry': 2, 'sha256': run.journal[2]['sha256'], 'run': f'{j}:2.{i}'} for i in (0, 1)])])

    def test_c1_stops_and_chains_are_listed_before_answers_whatever_came_first_in_the_journal(self):
        run = waivers()   # entries 3, 4 and 5: three times yes
        note = {'id': 'file-fee-note@t', 'effect': 'fee_note_filed', 'requires': ['note_ready'], 'provider': 'local-provider', 'grant': 'action:file-fee-note@t',
                'cost': TOKEN, 'action': 'simulate_fact', 'approved': True}
        run.add('pack', {'pack': extra('t-reader-fee-note', goals=pack('228_waiver_desk')['goals'] + ['fee_note_filed'], methods=[note], grants=['action:file-fee-note@t'],   # entry 6: a goal whose step stops
                                       rules=[{'id': 'R-NOTE@t', 'head': 'note_ready', 'branches': [['waiver_requested_201']], 'approved': True, 'source': 'fixture/reviewed-domain-theory'}])})
        for _ in range(3):   # entries 7, 8 and 9: three stops, all after the answers
            self.assertEqual(st(look(run))[-1], ('fee_note_filed', 'STEP_STOPPED', []))
        self.assertEqual([(p['kind'], [a['entry'] for a in p['at']]) for p in reader.proposals(kept(run), 3)], [('REPEATED_STOP', [7, 8, 9]), ('REPEATED_ANSWER', [3, 4, 5])])

    def test_c1_a_stop_counts_whatever_ran_before_it(self):   # added when the confirming round was settled: stops are alike by the step and the reason, not by the steps that ran before the stop
        desk = pack('224_payout_desk')   # the payout desk, its reconcile step waiting on a fact that holds only through a rule: it stops at its turn
        desk['rules'] = [{'id': 'R-LEDGER@t', 'head': 'ledger_open', 'branches': [['payout_due']], 'approved': True, 'source': 'fixture/reviewed-domain-theory'}]
        desk['methods'][2]['requires'].append('ledger_open')
        run = started([desk], 'stop-after-steps')
        stops = [look(run)[0] for _ in range(3)]   # entry 2: check and pay run and are paid, then reconcile stops; entries 3 and 4: reconcile stops at once
        self.assertEqual([(r['status'], r['actions'], r['cost'], r['stopped']['method']) for r in stops],
                         [('STEP_STOPPED', CHAIN[:2], {'compute': 3, 'money': 1, 'attention': 0}, CHAIN[2]), ('STEP_STOPPED', [], FREE, CHAIN[2]), ('STEP_STOPPED', [], FREE, CHAIN[2])])
        self.assertEqual([(p['kind'], p['step'], p['reason'], p['support'], p['at']) for p in reader.proposals(kept(run), 3)],
                         [('REPEATED_STOP', CHAIN[2], 'Prerequisite not true before effect: ledger_open', 3, cites(run, 2, 3, 4))])   # one row of three: two steps ran before the first stop and none before the others

    def test_c1_a_run_that_put_a_question_ends_the_row(self):   # added when the confirming round was settled
        ask = {'id': 'ask-finance-call@t', 'effect': 'call_allowed', 'requires': [], 'provider': 'finance-channel', 'grant': 'action:ask-finance-call@t',
               'cost': {'compute': 0, 'money': 0, 'attention': 1}, 'action': 'ask', 'approved': True, 'question': 'May the desk call this borrower?', 'ask_to': FINANCE}
        run = started(['220_collections_desk'], 'asked-between', kinds=('simulate_fact', 'ask'))
        look(run)
        event(run, overdue(2))   # entries 2 and 3: two stops
        self.assertEqual([(p['support'], p['at']) for p in reader.proposals(kept(run), 2)], [(2, cites(run, 2, 3))])
        run.add('pack', {'pack': extra('t-reader-call-allowed', budget={'attention': 1}, providers={'finance-channel': 1}, grants=['action:ask-finance-call@t'], methods=[ask],   # entry 4: the borrower can be reached only when finance allows the call
                                       rules=[{'id': 'R-REACHABLE-2@t', 'head': 'borrower_reachable', 'branches': [['phone_on_file', 'call_allowed']], 'approved': True,
                                               'source': 'fixture/reviewed-domain-theory', 'replaces': 'R-REACHABLE@1'}])})
        asked = event(run, overdue(3))   # entry 5: the run puts the question to finance and waits: a step ran (it left one receipt) and nothing stopped
        self.assertEqual((st(asked), asked[0]['work_state'], len(asked[0]['model_receipts']), 'stopped' in asked[0]), ([('reminder_sent', 'WAITING', ['ask-finance-call@t'])], 'waiting', 1, False))
        run.add('answer', {'receipt': asked[0]['model_receipts'][-1], 'truth': 'TRUE', 'source': FINANCE, 'execute': True})   # entry 6: finance says yes, and the reminder step stops again for the same reason
        self.assertEqual(run.detail[6]['runs'][0]['stopped'], {'method': REMIND, 'reason': WHY})
        self.assertEqual((reader.proposals(kept(run), 3), reader.proposals(kept(run), 2)), ([], []))   # stop, stop, a run that asked, stop: the run that asked ended the row, and the newest stop stands alone
        event(run, overdue(4))   # entry 7: one more stop
        self.assertEqual([(p['support'], p['at']) for p in reader.proposals(kept(run), 2)], [(2, cites(run, 6, 7))])   # the row starts again after the run that asked

    def test_c2_a_chain_of_two_journals_is_read_as_one_record_and_the_last_journal_alone_is_refused(self):
        first, keep = collections(2), J.Keep()   # two stops in the first journal
        J.save(first, keep)
        second = J.start(['simulate_fact'], [BOOK, reader.SOURCE], name='collections-2', continues=first, keep=keep)   # the journal that continues it
        event(second, overdue(3))                # the third stop
        self.assertEqual(([e['kind'] for e in first.journal], [e['kind'] for e in second.journal]), (['header', 'pack', 'pack', 'look', 'event', 'close'], ['header', 'event']))
        chain = [keep.read()] + kept(second)
        self.assertEqual(reader.proposals(chain, 3), [{'kind': 'REPEATED_STOP', 'scope': SCOPE_C, 'goal': 'reminder_sent', 'step': REMIND, 'reason': WHY, 'support': 3,
                                                       'at': cites(first, 3, 4) + cites(second, 1), 'status': 'PROPOSED_ONLY'}])   # one proposal, its three entries in two journals
        self.assertEqual((reader.proposals(chain[:1], 3), [p['at'] for p in reader.proposals(chain[:1], 2)]), ([], [cites(first, 3, 4)]))   # the first journal alone: two stops
        for part in (chain[1:], chain[::-1]):   # the last journal alone, and the two the wrong way round: refused in the adapter's words
            with self.assertRaisesRegex(ValueError, exactly('This record starts in the middle: its first journal continues another')):
                reader.proposals(part, 3)
        self.assertEqual(st(event(second, reader.row(reader.proposals(chain, 3)[0], 'reminder_stop_repeated'))), [('reminder_lesson_approved', DONE, [OWN_L])])   # and the yes is given in the second journal
        first, keep = payouts(2), J.Keep()       # a chain of steps over two journals: the one step is worded from the packs of the first journal
        J.save(first, keep)
        second = J.start(['simulate_fact'], [BOOK, reader.SOURCE], name='payouts-2', continues=first, keep=keep)
        event(second, due(103))
        self.assertEqual([(p['kind'], p['as_one'], p['at']) for p in reader.proposals([keep.read()] + kept(second), 3)],
                         [('REPEATED_CHAIN', {'effect': 'payout_reconciled', 'requires': ['payout_due']}, cites(first, 3, 4) + cites(second, 1))])

    def test_c2_the_methods_are_read_from_every_journal_of_a_chain(self):   # added when the confirming round was settled: the methods are read from every journal of a chain
        desk = pack('224_payout_desk')
        first, keep = started([extra('t-reader-desk-without-ways', **{k: desk[k] for k in ('scope', 'goals', 'budget', 'preference', 'evidence', 'providers')})], 'payouts-no-ways'), J.Keep()
        self.assertEqual((st(look(first)), first.detail[2]['runs'][0]['model_receipts']), ([('payout_reconciled', 'SEMANTICS_MISSING', [])], []))   # the first journal: the desk with no way to pay out, so nothing runs
        J.save(first, keep)
        second = J.start(['simulate_fact'], [BOOK, reader.SOURCE], name='payouts-ways', continues=first, keep=keep)   # the journal that continues it brings the three steps in a pack
        second.add('pack', {'pack': extra('t-reader-ways', methods=desk['methods'], grants=desk['grants'])})
        look(second)
        event(second, due(102))   # two payouts by the chain, both in the second journal
        self.assertEqual(([e['kind'] for e in first.journal], [e['kind'] for e in second.journal]), (['header', 'pack', 'look', 'close'], ['header', 'pack', 'look', 'event']))
        self.assertEqual([(p['kind'], p['steps'], p['as_one'], p['support'], p['at']) for p in reader.proposals([keep.read()] + kept(second), 2)],
                         [('REPEATED_CHAIN', CHAIN, {'effect': 'payout_reconciled', 'requires': ['payout_due']}, 2, cites(second, 2, 3))])   # the one step is worded from the pack of the second journal

    def test_c2_the_same_text_and_head_give_the_same_bytes_in_a_process_that_holds_no_kernel(self):
        run, keep = collections(3), J.Keep()
        head = J.save(run, keep)
        first = reader.proposals([keep.read()], 3)
        self.assertEqual(json.dumps(first), json.dumps(reader.proposals([keep.read()], 3)))
        self.assertEqual(first, reader.proposals(kept(J.restart(keep)), 3))   # a process that has only the kept text and head
        code = ("import sys,json;sys.path.insert(0,sys.argv[1]);from extensions import reader;text,head=json.loads(sys.stdin.read());"
                "print(json.dumps(reader.proposals([(text,head)],3),sort_keys=True));"
                "print(json.dumps(sorted(m for m in sys.modules if m.split('.')[0] in ('kernel','extensions','tools'))))")
        out = subprocess.run([sys.executable, '-I', '-B', '-c', code, str(ROOT)], input=json.dumps([keep.text, head]), capture_output=True, text=True, check=True).stdout.splitlines()
        self.assertEqual(out[0], json.dumps(first, sort_keys=True))
        self.assertEqual(json.loads(out[1]), ['extensions', 'extensions.journal_record', 'extensions.reader'])   # no kernel, no State, not the journal's writer

    def test_c2_the_reader_imports_the_record_adapter_and_nothing_else_of_the_lab(self):
        tree = ast.parse((ROOT / 'extensions' / 'reader.py').read_text())
        names = {a.name for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names} | {f'{n.module}.{a.name}' for n in ast.walk(tree) if isinstance(n, ast.ImportFrom) for a in n.names}
        self.assertEqual(sorted(names), ['__future__.annotations', 'extensions.journal_record', 'hashlib', 'json'])
        self.assertEqual([n.id for n in ast.walk(tree) if isinstance(n, ast.Name) and n.id in ('open', 'exec', 'eval', 'globals', 'State', 'Kernel')], [])

    def test_c2_it_reads_up_to_the_head_it_is_given(self):
        run = collections(3)
        text, head = kept(run)[0]
        day_two = {'length': 5, 'sha256': run.journal[4]['sha256']}
        self.assertEqual(reader.proposals([(text, day_two)], 3), [])
        self.assertEqual(reader.proposals([(text, day_two)], 2), reader.proposals(kept(collections(2)), 2))   # the same as the journal that ends there
        self.assertEqual(reader.proposals([(text + 'not an entry\n', head)], 3), reader.proposals([(text, head)], 3))   # what stands past the head is not read

    def test_c2_a_journal_that_is_broken_or_comes_without_its_head_is_refused_in_the_adapters_words(self):
        text, head = kept(collections(3))[0]
        for bad, why in (((text.replace('loan-7-day-2', 'loan-7-day-9'), head), 'The journal is broken at entry 4'),
                         ((text, dict(head, sha256='0' * 64)), 'The journal does not end on the hash its head names'), ((text, None), 'No head, no read')):
            with self.assertRaisesRegex(ValueError, why):
                reader.proposals([bad], 3)

    def test_c3_three_runs_of_one_chain_are_one_proposal_with_what_each_run_paid_and_the_chain_as_one_step(self):
        run = payouts(3)
        self.assertEqual(reader.proposals(kept(run), 3), [{'kind': 'REPEATED_CHAIN', 'scope': SCOPE_P, 'goal': 'payout_reconciled', 'steps': CHAIN, 'paid': CHAIN_COST,
                                                           'as_one': {'effect': 'payout_reconciled', 'requires': ['payout_due']},
                                                           'support': 3, 'at': cites(run, 3, 4, 5), 'status': 'PROPOSED_ONLY'}])
        self.assertEqual([r['cost'] for r in R.ledger(kept(run)) if r['what'] == 'ran' and r['goal'] == 'payout_reconciled'], [CHAIN_COST] * 3)   # `paid` is the ledger's cost of each run
        self.assertEqual(reader.proposals(kept(payouts(2)), 3), [])

    def test_c3_a_run_counts_by_what_ran_not_by_what_was_planned(self):
        desk = pack('224_payout_desk')   # the same desk, written so that only the first step names the payout
        for m in desk['methods'][1:]:
            m['requires'].remove('payout_due')
        run = started([desk], 'in-part')
        look(run)
        event(run, due(102))
        event(run, due(103))
        ran = [run.detail[n]['runs'][0] for n in (2, 3, 4)]
        self.assertEqual([(r['actions'], r.get('skipped')) for r in ran], [(CHAIN, None), (CHAIN[:1], CHAIN[1:]), (CHAIN[:1], CHAIN[1:])])   # the steps ran 3, 1, 1
        self.assertEqual((reader.proposals(kept(run), 3), reader.proposals(kept(run), 2)), ([], []))   # one step that ran is no chain
        learner = Learner(True)
        self.assertEqual([learner.learn(r)[0]['observations'] for r in ran], [1, 2, 3])   # the Learner counts the plan: three times the chain of three
        desk = pack('224_payout_desk')   # written the other way: the check of the payee names no payout, so it is made once and stands
        desk['methods'][0]['requires'] = []
        desk['methods'][1]['requires'] += ['limit_ok', 'kyc_done', 'account_open']   # and the pay step needs three facts more from outside the chain
        desk['evidence'] += [{'predicate': f, 'truth': 'TRUE', 'verified': True, 'source': BOOK, 'version': 'borrower-1'} for f in ('limit_ok', 'kyc_done', 'account_open')]
        run = started([desk], 'first-stands')
        look(run)
        event(run, due(102))
        event(run, due(103))
        self.assertEqual([r['actions'] for n in (2, 3, 4) for r in run.detail[n]['runs']], [CHAIN, CHAIN[1:], CHAIN[1:]])
        self.assertEqual([(x['steps'], x['paid'], x['as_one'], x['support'], x['at']) for x in reader.proposals(kept(run), 2)],   # the two steps that ran twice
                         [(CHAIN[1:], {'compute': 3, 'money': 1, 'attention': 0}, {'effect': 'payout_reconciled', 'requires': ['account_open', 'kyc_done', 'limit_ok', 'payee_checked', 'payout_due']}, 2, cites(run, 3, 4))])

    def test_c3_a_run_that_stopped_after_the_same_steps_is_no_run_of_the_chain(self):
        theory = lambda id, head, branches: {'id': id, 'head': head, 'branches': branches, 'approved': True, 'source': 'fixture/reviewed-domain-theory'}
        desk = pack('224_payout_desk')   # two ways to done: reconciled (that step stops: its ledger fact holds only through a rule), or paid in an open month
        desk['goals'] = ['payout_done']
        desk['rules'] = [theory('R-DONE@t', 'payout_done', [['payout_reconciled'], ['payout_paid', 'month_open']]), theory('R-LEDGER@t', 'ledger_open', [['payout_due']])]
        desk['methods'][2]['requires'].append('ledger_open')
        run = started([desk], 'stopped-first')
        first = look(run)[0]   # entry 2: check and pay run and are paid, reconcile stops
        self.assertEqual((first['status'], first['actions'], first['cost'], first['stopped']['method']), ('STEP_STOPPED', CHAIN[:2], {'compute': 3, 'money': 1, 'attention': 0}, CHAIN[2]))
        run.add('pack', {'pack': extra('t-reader-month-open', evidence=[{'predicate': 'month_open', 'truth': 'TRUE', 'verified': True, 'source': BOOK, 'version': 'month-11'}])})
        done = [event(run, due(loan))[0] for loan in (102, 103, 104)]   # entries 4, 5, 6: done by check and pay alone
        self.assertEqual([(r['status'], r['actions'], r['cost']) for r in done], [(DONE, CHAIN[:2], {'compute': 3, 'money': 1, 'attention': 0})] * 3)
        self.assertEqual([(x['kind'], x['steps'], x['as_one'], x['support'], x['at']) for x in reader.proposals(kept(run), 3)],
                         [('REPEATED_CHAIN', CHAIN[:2], {'effect': 'payout_paid', 'requires': ['payout_due']}, 3, cites(run, 4, 5, 6))])
        self.assertEqual(reader.proposals(kept(run), 4), [])   # four runs ran the same two steps at the same cost; the first of them stopped
        run = started(['224_payout_desk', '226_payout_in_one'], 'another-way-first')   # a run that completed by other steps is no run of the chain either
        self.assertEqual(st(look(run)), [('payout_reconciled', DONE, [ONE])])           # entry 3: the one step
        run.add('pack', {'pack': extra('t-reader-one-step-away', revoke_grants=['action:' + ONE])})
        event(run, due(102))
        event(run, due(103))                                                            # entries 5 and 6: the chain
        self.assertEqual(([(x['steps'], x['support'], x['at']) for x in reader.proposals(kept(run), 2)], reader.proposals(kept(run), 3)), ([(CHAIN, 2, cites(run, 5, 6))], []))

    def test_c3_the_same_steps_in_another_order_or_with_another_step_are_no_runs_of_the_chain(self):   # added when the confirming round was settled
        theory = lambda id, order, **more: dict({'id': id, 'head': 'payout_done', 'branches': [order], 'approved': True, 'source': 'fixture/reviewed-domain-theory'}, **more)
        desk = pack('224_payout_desk')   # the desk with a goal of two facts: the payee is told, and the payout is reconciled
        desk['goals'] = ['payout_done']
        desk['rules'] = [theory('R-DONE@t', ['payee_told', 'payout_reconciled'])]
        desk['methods'].append({'id': 'tell-payee@t', 'effect': 'payee_told', 'requires': ['payout_due'], 'provider': 'local-provider', 'grant': 'action:tell-payee@t',
                                'cost': TOKEN, 'action': 'simulate_fact', 'approved': True})
        desk['grants'].append('action:tell-payee@t')
        run = started([desk], 'another-order')
        look(run)
        event(run, due(102))   # entries 2 and 3: the payee is told first, then the three steps
        told_first = ['tell-payee@t'] + CHAIN
        self.assertEqual([(p['steps'], p['support'], p['at']) for p in reader.proposals(kept(run), 2)], [(told_first, 2, cites(run, 2, 3))])
        run.add('pack', {'pack': extra('t-reader-other-order', rules=[theory('R-DONE-2@t', ['payout_reconciled', 'payee_told'], replaces='R-DONE@t')])})   # entry 4: the rule names the two facts the other way round
        third = event(run, due(103))[0]   # entry 5: the same four steps at the same cost, the payee told last
        self.assertEqual((third['status'], third['actions'], third['cost'], sorted(third['actions']) == sorted(told_first)), (DONE, CHAIN + ['tell-payee@t'], {'compute': 6, 'money': 1, 'attention': 0}, True))
        self.assertEqual((reader.proposals(kept(run), 3), reader.proposals(kept(run), 2)), ([], []))   # the same steps in another order are no run of that chain: no row of three, and the row of two has ended
        desk = pack('224_payout_desk')   # the desk as it is, and a second pay step that is granted for one loan only
        fast = dict(desk['methods'][1], id='pay-payout-fast@t', grant='action:pay-payout-fast@t')
        run = started([desk, extra('t-reader-fast-pay', methods=[fast])], 'another-step')
        look(run)                                                                                                                              # entry 3: the chain
        run.add('pack', {'pack': extra('t-reader-fast-on', grants=['action:pay-payout-fast@t'], revoke_grants=['action:pay-payout@1'])})
        other = event(run, due(102))[0]                                                                                                        # entry 5: check, the other pay step, reconcile
        run.add('pack', {'pack': extra('t-reader-fast-off', grants=['action:pay-payout@1'], revoke_grants=['action:pay-payout-fast@t'])})
        event(run, due(103))
        event(run, due(104))                                                                                                                   # entries 7 and 8: the chain
        self.assertEqual((other['status'], other['actions'], other['cost']), (DONE, [CHAIN[0], 'pay-payout-fast@t', CHAIN[2]], CHAIN_COST))    # the same first step, as many steps, the same cost: another step in the middle
        self.assertEqual((reader.proposals(kept(run), 3), [(p['steps'], p['support'], p['at']) for p in reader.proposals(kept(run), 2)]), ([], [(CHAIN, 2, cites(run, 7, 8))]))   # four payouts; only the two newest are runs of this chain

    def test_c3_a_chain_that_is_not_one_line_gets_no_single_step(self):
        for order in (['payee_told', 'payout_reconciled'], ['payout_reconciled', 'payee_told']):
            desk = pack('224_payout_desk')   # the same desk with a goal of two facts: the payee is told, and the payout is reconciled
            desk['goals'] = ['payout_done']
            desk['rules'] = [{'id': 'R-DONE@t', 'head': 'payout_done', 'branches': [order], 'approved': True, 'source': 'fixture/reviewed-domain-theory'}]
            desk['methods'].append({'id': 'tell-payee@t', 'effect': 'payee_told', 'requires': ['payout_due'], 'provider': 'local-provider', 'grant': 'action:tell-payee@t',
                                    'cost': TOKEN, 'action': 'simulate_fact', 'approved': True})
            desk['grants'].append('action:tell-payee@t')
            run = started([desk], 'two-facts')
            look(run)
            event(run, due(102))
            p = reader.proposals(kept(run), 2)
            steps = ['tell-payee@t'] + CHAIN if order[0] == 'payee_told' else CHAIN + ['tell-payee@t']   # a fact nothing later needs: made first, or made second to last
            self.assertEqual([(x['kind'], x['goal'], x['steps'], x['paid'], x['support'], 'as_one' in x) for x in p],
                             [('REPEATED_CHAIN', 'payout_done', steps, {'compute': 6, 'money': 1, 'attention': 0}, 2, False)])
            self.assertEqual(reader.fits(p[0], pack('226_payout_in_one')['methods'][0]), ['the chain is not one line: no single step stands for it'])

    def test_c3_a_way_a_person_wrote_is_held_to_the_chain_it_is_said_to_replace(self):
        p = reader.proposals(kept(payouts(3)), 3)[0]
        way = pack('226_payout_in_one')['methods'][0]
        self.assertEqual((way['id'], way['cost'], reader.fits(p, way)), (ONE, ONE_COST, []))
        for change, why in (({'cost': {'compute': 6, 'money': 1, 'attention': 0}}, ['it is dearer on compute', 'it is cheaper on no line']),
                            ({'cost': {'compute': 6, 'money': 0, 'attention': 0}}, ['it is dearer on compute']),
                            ({'cost': dict(CHAIN_COST)}, ['it is cheaper on no line']),
                            ({'cost': {'compute': 2, 'money': 2, 'attention': 0}}, ['it is dearer on money']),
                            ({'cost': {'compute': 5, 'money': 1, 'attention': 1}}, ['it is dearer on attention', 'it is cheaper on no line']),
                            ({'cost': {'money': 2, 'hours': 1, 'compute': 6, 'attention': 1, 'calls': 1}},
                             ['it is dearer on attention', 'it is dearer on calls', 'it is dearer on compute', 'it is dearer on hours', 'it is dearer on money', 'it is cheaper on no line']),
                            ({'cost': {'compute': 5}}, []),                                    # money is not named: nothing, where the chain paid one
                            ({'cost': {'compute': 5, 'money': 1}}, ['it is cheaper on no line']),   # attention is not named: nothing, as the chain paid
                            ({'cost': {'compute': 2, 'money': 1, 'attention': 0, 'hours': 1}}, ['it is dearer on hours']),   # a line the chain never paid on
                            ({'cost': {'compute': 5, 'money': 1, 'attention': 0, 'hours': 0}}, ['it is cheaper on no line']),
                            ({'effect': 'payout_paid'}, ['it makes another fact']),
                            ({'requires': []}, ['it requires other facts']),
                            ({'requires': ['payout_due', 'payee_checked']}, ['it requires other facts']),
                            ({'effect': 'payout_paid', 'requires': [], 'cost': {'compute': 9}}, ['it makes another fact', 'it requires other facts', 'it is dearer on compute'])):
            self.assertEqual(reader.fits(p, dict(way, **change)), why, change)
        self.assertEqual(reader.fits(p, dict(way, cost={'compute': 2})), [])   # a line the way does not name costs nothing
        stop = reader.proposals(kept(collections(3)), 3)[0]
        for bad in ((stop, way), (None, way), (p, None)):
            with self.assertRaisesRegex(ValueError, exactly('A way is held to a proposal of the kind REPEATED_CHAIN')):
                reader.fits(*bad)

    def test_c3_a_way_is_held_to_the_outside_facts_as_a_set_whatever_their_order(self):
        desk = pack('224_payout_desk')   # the same desk; its pay step needs one fact more from outside the chain
        desk['methods'][1]['requires'].append('kyc_done')
        desk['evidence'].append({'predicate': 'kyc_done', 'truth': 'TRUE', 'verified': True, 'source': BOOK, 'version': 'borrower-1'})
        run = started([desk], 'two-outside-facts')
        look(run)
        event(run, due(102))
        p = reader.proposals(kept(run), 2)[0]
        self.assertEqual(p['as_one'], {'effect': 'payout_reconciled', 'requires': ['kyc_done', 'payout_due']})
        way = pack('226_payout_in_one')['methods'][0]
        for requires in (['kyc_done', 'payout_due'], ['payout_due', 'kyc_done'], ['payout_due', 'kyc_done', 'payout_due']):   # the same facts in any order, one named twice
            self.assertEqual(reader.fits(p, dict(way, requires=requires)), [], requires)
        self.assertEqual(reader.fits(p, dict(way, requires=['payout_due'])), ['it requires other facts'])

    def test_c3_a_key_the_way_leaves_out_is_read_as_nothing(self):   # added when the confirming round was settled
        p = reader.proposals(kept(payouts(3)), 3)[0]
        way = pack('226_payout_in_one')['methods'][0]
        without = lambda key: {k: v for k, v in way.items() if k != key}   # the one step of pack 226 with one of its keys left out altogether
        self.assertEqual(reader.fits(p, without('requires')), ['it requires other facts'])   # read as requiring nothing, which is not what the chain requires from outside
        self.assertEqual(reader.fits(p, without('effect')), ['it makes another fact'])       # a way that names no fact does not make the chain's
        self.assertEqual(reader.fits(p, without('cost')), [])                                # a way that names no cost is read as costing nothing on every line: the look gives no reason

    def test_c2_a_journal_that_is_whole_and_in_order_and_does_not_hold_what_is_read_is_refused_in_the_readers_words(self):
        def no_methods(entries):
            entries[1]['body']['pack']['methods'] = []

        def odd_methods(entries):
            entries[1]['body']['pack']['methods'] = [3]

        def no_effect(entries):
            del entries[1]['body']['pack']['methods'][0]['effect']
        for change in (no_methods, odd_methods, no_effect):   # the pack entry that brought the chain's methods, changed and chained again
            with self.assertRaisesRegex(ValueError, exactly('The journal does not hold what the reader reads from it')):
                reader.proposals(rechained(payouts(3), 1, change), 3)
        self.assertEqual(reader.proposals(rechained(payouts(2), 1, no_methods), 3), [])   # nothing repeated: the methods are not read at all

    def test_c2_the_words_of_a_refusal_go_by_what_was_changed(self):   # added when the confirming round was settled
        adapter = lambda n: f'^Entry {n} of journal [0-9a-f]{{12}} does not hold what the record reads from it$'   # the record adapter's words for an entry its ledger cannot read
        run = payouts(3)

        def pack_entry(change):   # the pack entry that brought the chain's methods, changed and chained again under a head of its own
            def changed(entries):
                change(entries[1]['body'])
            return rechained(run, 1, changed)
        for change in (lambda b: b.update(pack=[]), lambda b: b.update(pack='x')):   # a pack that is no object: the adapter's words, not the reader's
            with self.assertRaisesRegex(ValueError, adapter(1)):
                reader.proposals(pack_entry(change), 3)
        for change in (lambda b: b['pack'].pop('methods'), lambda b: b['pack']['methods'][2].update(id='other@1'), lambda b: b['pack']['methods'][2].update(requires=5)):
            with self.assertRaisesRegex(ValueError, exactly(reader.NOT_READ)):   # no methods, a method renamed, requires that are a number: the reader's words
                reader.proposals(pack_entry(change), 3)
        for change in (lambda b: b.pop('pack'), lambda b: b.clear()):   # a body without its pack: the adapter reads a broken journal
            with self.assertRaisesRegex(ValueError, exactly('The journal is broken at entry 1')):
                reader.proposals(pack_entry(change), 3)
        one_step = lambda change: [p.get('as_one') for p in reader.proposals(pack_entry(change), 3)]
        self.assertEqual(one_step(lambda b: b['pack']['methods'][2].update(effect='paid_twice')), [{'effect': 'paid_twice', 'requires': ['payout_due']}])   # read: the one step is worded with the forger's fact (limit L10)
        self.assertEqual((one_step(lambda b: b['pack']['methods'][2].update(requires=[])), one_step(lambda b: b['pack']['methods'][2].update(requires='payout_due'))), ([None], [None]))   # read: the chain is then no line, and no one step is worded
        run = waivers()
        whole = reader.proposals(kept(run), 3)

        def answer_entry(change):   # the first answer entry, changed and chained again
            def changed(entries):
                change(entries[3])
            return rechained(run, 3, changed)
        for change in (lambda e: e['body'].update(receipt={}), lambda e: e['body'].update(receipt='x'), lambda e: e.update(result={})):   # a receipt that holds no question, a result that holds nothing: the adapter's words
            with self.assertRaisesRegex(ValueError, adapter(3)):
                reader.proposals(answer_entry(change), 3)
        with self.assertRaisesRegex(ValueError, exactly(reader.NOT_READ)):   # a receipt that no entry issued: the reader's words (the test of C9 named for it holds the same on another desk)
            reader.proposals(answer_entry(lambda e: e['body']['receipt'].update(sha256='0' * 64)), 3)
        for change in (lambda e: e['body'].pop('receipt'), lambda e: e['body'].pop('truth')):   # a body without its receipt or its truth: a broken journal
            with self.assertRaisesRegex(ValueError, exactly('The journal is broken at entry 3')):
                reader.proposals(answer_entry(change), 3)
        no = lambda e: e['body'].update(truth='FALSE')
        self.assertEqual((reader.proposals(answer_entry(no), 3), reader.proposals(answer_entry(no), 2)), ([], []))   # read: a yes reworded as a no ends the question (limit L10)
        for change in (lambda e: e['body'].update(source=RISK), lambda e: e['body']['receipt']['ask'].update(to=RISK), lambda e: e['body']['receipt']['ask'].update(question='Another question?')):
            got = reader.proposals(answer_entry(change), 3)   # read, and the proposal is the same but for the hashes of its entries: the party and the words are read from the entry of the question
            self.assertEqual([dict(p, at=[a['entry'] for a in p['at']]) for p in got], [dict(p, at=[a['entry'] for a in p['at']]) for p in whole])

    def test_c4_the_row_is_worded_for_one_proposal_and_its_version_is_that_proposals_digest(self):
        p = reader.proposals(kept(collections(3)), 3)[0]
        row = reader.row(p, 'reminder_stop_repeated')
        self.assertEqual(row, {'predicate': 'reminder_stop_repeated', 'truth': 'TRUE', 'verified': True, 'source': 'adapter:reader', 'version': digest(p)})
        self.assertEqual((reader.digest(p), reader.SOURCE), (digest(p), 'adapter:reader'))   # the kernel's own digest
        four = reader.proposals(kept(collections(4)), 3)[0]
        self.assertEqual((four['support'], reader.row(four, 'reminder_stop_repeated')['version'] == row['version']), (4, False))   # four stops are another proposal
        for bad in ((None, 'x'), ({}, 'x'), (dict(p, kind='REUSE_COMPOSITION'), 'x'), (dict(p, status='APPROVED'), 'x'), (dict(p, at=[]), 'x'), (dict(p, at='x'), 'x'),
                    (dict(p, at={'a': 1}), 'x'), (p, ''), (p, None), (p, 5), (p, ['x'])):
            with self.assertRaisesRegex(ValueError, exactly('A row is worded for one proposal of the reader and one named fact')):
                reader.row(*bad)

    def test_c4_the_row_of_a_proposal_with_a_character_outside_ascii_carries_the_kernels_digest(self):
        desk = pack('220_collections_desk')
        desk['scope'] = 'lendco/zürich'   # a branch whose name is not ASCII
        run = started([desk], 'zurich')
        look(run)
        event(run, overdue(2))
        p = reader.proposals(kept(run), 2)[0]
        row = reader.row(p, 'reminder_stop_repeated')
        self.assertEqual((p['scope'], row['version'], reader.digest(p)), ('lendco/zürich', digest(p), digest(p)))   # characters as they are, as the kernel hashes them
        self.assertNotEqual(row['version'], hashlib.sha256(json.dumps(p, sort_keys=True, separators=(',', ':')).encode()).hexdigest())   # and not the escaped form
        event(run, row)
        self.assertEqual(run.state.fact('reminder_stop_repeated')['version'], digest(p))   # the stored row carries it

class Walk(unittest.TestCase):
    """C4 to C8: what follows a proposal, with parts the lab had: a row at the event door, a yes that is a step, a pack at the pack door."""
    def lesson(self):   # three stops, the proposal, its row in: the yes
        run = collections(3)
        p = reader.proposals(kept(run), 3)[0]
        return run, p, event(run, reader.row(p, 'reminder_stop_repeated'))

    def way(self):   # three chains, the proposal, its row in: the yes
        run = payouts(3)
        p = reader.proposals(kept(run), 3)[0]
        return run, p, event(run, reader.row(p, 'payout_chain_repeated'))

    def test_c4_before_the_row_the_yes_waits_as_missing_evidence(self):
        run = collections(3)
        r = run.detail[3]['runs'][1]
        self.assertEqual((r['goal'], r['status'], r['stop_reasons'], run.state.budget['compute']), ('reminder_lesson_approved', 'QUERY_EVIDENCE', ['QUERY_EVIDENCE'], 12))
        self.assertEqual([e['result']['affected'] for e in run.journal[4:]], [['reminder_sent']] * 2)   # a new day wakes the work, not the yes

    def test_c4_the_yes_is_a_step_and_its_row_says_who_gave_it_and_what_it_rests_on(self):
        run, p, yes = self.lesson()
        self.assertEqual((st(yes), yes[0]['cost']), ([('reminder_lesson_approved', DONE, [OWN_L])], TOKEN))   # a small change: the desk's own yes, one token
        self.assertEqual(said(run.state, 'reminder_lesson_approved'),
                         ('TRUE', 'LOCAL_MODEL:' + OWN_L, [{'predicate': 'reminder_stop_repeated', 'version': digest(p)}, {'predicate': 'change_weight=small', 'version': 'small'}]))
        row = [r for r in R.ledger(kept(run)) if r['what'] == 'ran'][-1]   # the kept text says it too: the entry of the yes holds the step and its receipt
        self.assertEqual((row['entry'], row['goal'], row['actions'], len(row['receipts'])), (6, 'reminder_lesson_approved', [OWN_L], 1))
        self.assertEqual(run.journal[6]['body']['row']['version'], digest(p))

    def test_c4_a_weighty_change_gets_the_independent_checkers_yes_and_the_desks_own_yes_is_not_offered(self):
        run, p, yes = self.way()
        self.assertEqual((st(yes), yes[0]['cost']), ([('payout_way_approved', DONE, [CHECK_P])], {'compute': 5, 'money': 0, 'attention': 0}))
        self.assertEqual({tuple(m) for m, _, _ in admissions(yes[0])}, {(CHECK_P,)})   # the cheaper own yes was never a plan
        self.assertEqual([e['data'] for e in yes[0]['trace'] if e['operation'] == 'METHOD_ABSENT'], [{'predicate': 'change_weight=small'}])
        self.assertEqual(said(run.state, 'payout_way_approved'),
                         ('TRUE', 'LOCAL_MODEL:' + CHECK_P, [{'predicate': 'payout_chain_repeated', 'version': digest(p)}, {'predicate': 'change_weight=weighty', 'version': 'weighty'}]))
        self.assertEqual((run.state.methods[CHECK_P]['provider'], run.state.methods[CHAIN[1]]['provider'], run.state.providers['independent-checker']), ('independent-checker', 'local-provider', 0))

    def test_c4_without_the_tokens_for_the_checker_there_is_no_yes(self):
        run = payouts(3)
        run.add('pack', {'pack': extra('t-reader-few-tokens', budget={'compute': 4})})
        yes = event(run, reader.row(reader.proposals(kept(run), 3)[0], 'payout_chain_repeated'))
        self.assertEqual((st(yes), yes[0]['stop_reasons']), ([('payout_way_approved', 'RESOURCE_REQUIRED', [])], ['METHOD_ABSENT', 'RESOURCE_REQUIRED']))
        self.assertEqual((said(run.state, 'payout_way_approved')[0], run.state.budget['compute']), ('UNKNOWN', 4))

    def test_c4_with_the_checker_away_no_yes_is_given(self):
        run = payouts(3)
        run.add('pack', {'pack': pack('227_checker_away')})
        yes = event(run, reader.row(reader.proposals(kept(run), 3)[0], 'payout_chain_repeated'))
        self.assertEqual((st(yes), yes[0]['stop_reasons']), ([('payout_way_approved', 'PROVIDER_REQUIRED', [])], ['METHOD_ABSENT', 'PROVIDER_REQUIRED']))
        self.assertEqual((said(run.state, 'payout_way_approved')[0], run.state.budget['compute']), ('UNKNOWN', 15))

    def test_c5_until_the_pack_is_in_the_state_holds_the_row_and_nothing_of_the_proposal(self):
        run, p, yes = self.way()
        held = json.dumps(J.views(run.state))
        self.assertEqual([w for w in ('REPEATED_CHAIN', 'PROPOSED_ONLY', 'as_one', ONE) if w in held], [])   # no word of the proposal, and no way it could bring
        self.assertEqual(run.state.fact('payout_chain_repeated'),
                         {'predicate': 'payout_chain_repeated', 'truth': 'TRUE', 'verified': True, 'source': 'adapter:reader', 'version': digest(p), 'scope': SCOPE_P})
        self.assertEqual(sorted(run.state.methods), sorted(CHAIN + [OWN_P, CHECK_P]))   # the methods are the two packs' own
        run.add('pack', {'pack': pack('226_payout_in_one')})
        self.assertEqual(sorted(run.state.methods), sorted(CHAIN + [OWN_P, CHECK_P, ONE]))   # the change arrives under a method id of its own

    def test_c5_the_change_goes_in_at_the_pack_door_and_the_kernel_takes_the_cheaper_way(self):
        run, p, yes = self.way()
        run.add('pack', {'pack': pack('226_payout_in_one')})
        r = event(run, due(104))[0]
        self.assertEqual([e['kind'] for e in run.journal], ['header', 'pack', 'pack', 'look', 'event', 'event', 'event', 'pack', 'event'])   # the yes (entry 6) stands before the pack (entry 7)
        self.assertEqual((r['status'], r['actions'], r['cost'], r['pareto_options']), (DONE, [ONE], ONE_COST, 1))
        self.assertEqual(sorted({tuple(m) for m, ok, _ in admissions(r) if ok}), [tuple(CHAIN), (ONE,)])   # both ways were open; the chain is dominated
        self.assertEqual(run.state.budget, {'compute': 8, 'money': 2, 'attention': 0})   # 30 less three chains (15), the checker (5) and the one step (2)
        self.assertEqual(st(look(run)), [('payout_reconciled', 'SUPPORTED_BY_EVIDENCE', [])])   # the change is no standing goal any more

    def test_c5_the_lesson_takes_the_way_that_stops_away_and_the_reminder_is_sent(self):
        run, p, yes = self.lesson()
        run.add('pack', {'pack': pack('222_reminder_lesson')})
        r = event(run, overdue(4))[0]
        self.assertEqual((r['status'], r['actions'], r['cost']), (DONE, [PHONE], TOKEN))
        self.assertEqual(admissions(r)[:2], [([REMIND], False, ['AUTHORITY_REQUIRED']), ([PHONE], True, [])])
        self.assertEqual((sorted(run.state.grants), run.state.goals),
                         (['action:' + OWN_L, 'action:' + CHECK_L, 'action:' + PHONE], ['reminder_sent']))
        other, _, _ = self.lesson()   # the yes alone changes no way: without the pack the fourth day stops like the first three
        self.assertEqual(event(other, overdue(4))[0]['stopped'], {'method': REMIND, 'reason': WHY})

    def test_c6_when_the_newest_run_is_of_another_kind_the_row_has_ended(self):
        run, p, yes = self.lesson()
        run.add('pack', {'pack': pack('222_reminder_lesson')})
        self.assertEqual(reader.proposals(kept(run), 3), [p])   # the pack is in and nothing ran yet: the row still stands (limit L5)
        event(run, overdue(4))
        self.assertEqual(reader.proposals(kept(run), 3), [])
        run, p, yes = self.way()
        run.add('pack', {'pack': pack('226_payout_in_one')})
        self.assertEqual(reader.proposals(kept(run), 3), [p])
        event(run, due(104))
        self.assertEqual((reader.proposals(kept(run), 3), reader.proposals(kept(run), 2)), ([], []))

    def test_c6_a_way_that_was_handed_in_and_then_stops_is_read_like_any_stop(self):
        desk, one = pack('224_payout_desk'), pack('226_payout_in_one')
        desk['rules'] = [{'id': 'R-LEDGER@t', 'head': 'ledger_open', 'branches': [['payout_due']], 'approved': True, 'source': 'fixture/reviewed-domain-theory'}]
        one['methods'][0]['requires'].append('ledger_open')   # the one step as a person might get it wrong: it needs a fact that holds only through a rule
        run = started([desk, one], 'one-step-stops')
        stops = [look(run)[0]] + [event(run, due(loan))[0] for loan in (102, 103)]
        self.assertEqual([(r['status'], r['stopped']['method'], r['cost']['compute']) for r in stops], [('STEP_STOPPED', ONE, 0)] * 3)   # offered at every look, though the chain would complete
        p = reader.proposals(kept(run), 3)
        self.assertEqual([(x['kind'], x['step'], x['reason'], x['support']) for x in p], [('REPEATED_STOP', ONE, 'Prerequisite not true before effect: ledger_open', 3)])
        run.add('pack', {'pack': extra('t-reader-one-step-away', revoke_grants=['action:' + ONE])})   # taking the way back is a pack like any other
        self.assertEqual((st(event(run, due(104))), reader.proposals(kept(run), 3)), ([('payout_reconciled', DONE, CHAIN)], []))

    def test_l5_a_stop_or_a_chain_stays_proposed_through_blocked_runs(self):   # added when the confirming round was settled
        run, p, yes = self.lesson()   # three stops, the proposal, the desk's own yes
        run.add('pack', {'pack': pack('222_reminder_lesson')})                           # the lesson is in: the grant of the step that stopped is gone
        run.add('pack', {'pack': extra('t-reader-no-tokens', budget={'compute': 0})})   # and the tokens are gone
        later = [event(run, overdue(day))[0] for day in (4, 5, 6)]
        self.assertEqual([(r['status'], r['actions'], r['model_receipts'], 'stopped' in r) for r in later], [('QUERY_EVIDENCE', [], [], False)] * 3)   # three more runs of the goal, each blocked: nothing ran and nothing stopped
        self.assertEqual((reader.proposals(kept(run), 3), 'action:' + REMIND in run.state.grants), ([p], False))   # the same proposal still stands, at a step whose grant is gone: a blocked run does not end a row
        run.add('pack', {'pack': extra('t-reader-tokens-back', budget={'compute': 3})})
        self.assertEqual((st(event(run, overdue(7))), reader.proposals(kept(run), 3)), ([('reminder_sent', DONE, [PHONE])], []))   # it ends with the next run of the goal in which a step runs
        run, p, yes = self.way()      # the same at the payout desk: three chains, the proposal, the checker's yes, the one step handed in, and no tokens
        run.add('pack', {'pack': pack('226_payout_in_one')})
        run.add('pack', {'pack': extra('t-reader-no-tokens', budget={'compute': 0})})
        self.assertEqual(([st(event(run, due(loan))) for loan in (104, 105)], reader.proposals(kept(run), 3)), ([[('payout_reconciled', 'RESOURCE_REQUIRED', [])]] * 2, [p]))

    def test_l12_a_way_that_names_no_input_is_taken_on_the_yes_runs_once_and_then_every_payout_reads_done(self):
        run, p, yes = self.way()   # three chains, the proposal, and the checker's yes on the books
        loose = pack('226_payout_in_one')
        loose['methods'][0]['requires'] = []   # the one step as a person might get it wrong: it names no payout
        self.assertEqual(reader.fits(p, loose['methods'][0]), ['it requires other facts'])   # the look says so, and nothing asks the look
        run.add('pack', {'pack': loose})       # handed in all the same, on the yes that was given
        first = event(run, due(104))[0]
        self.assertEqual((first['status'], first['actions'], first['cost']), (DONE, [ONE], ONE_COST))   # loan 104: the one step is chosen, two tokens against five
        later = [event(run, due(loan))[0] for loan in (105, 106)]
        self.assertEqual([(r['status'], r['actions'], r['cost'], r['model_receipts'], r.get('stopped')) for r in later], [('SUPPORTED_BY_EVIDENCE', [], FREE, [], None)] * 2)   # loans 105 and 106 read done: nothing runs, nothing is paid
        done = run.state.fact('payout_reconciled')
        self.assertEqual((done['truth'], done['source'], done['depends_on'], run.state.budget), ('TRUE', 'LOCAL_MODEL:' + ONE, [], {'compute': 8, 'money': 2, 'attention': 0}))   # the one step's row rests on nothing, so no new payout un-reads it
        self.assertEqual((reader.proposals(kept(run), 3), reader.proposals(kept(run), 2)), ([], []))   # and the reader sees no stop: a run in which nothing ran is passed over
        fitting = self.way()[0]                # beside it, the way that fits (pack 226 as it is): every payout runs the one step and is paid
        fitting.add('pack', {'pack': pack('226_payout_in_one')})
        self.assertEqual([(r['status'], r['actions']) for r in (event(fitting, due(loan))[0] for loan in (104, 105, 106))], [(DONE, [ONE])] * 3)

    def test_l12_a_misfit_is_chosen_when_it_is_cheaper_on_the_line_saved_first_or_costs_the_same_under_an_earlier_id_or_the_chain_cannot_run(self):
        def handed_in(cost, id=ONE):   # the checker's yes on the books, then a way that does not fit, handed in all the same; the next payout
            run, p, yes = self.way()
            way = pack('226_payout_in_one')
            way['methods'][0].update(id=id, grant='action:' + id, cost=cost)
            way['grants'] = ['action:' + id]
            run.add('pack', {'pack': way})
            return reader.fits(p, way['methods'][0]), event(run, due(104))[0], run
        why, r, run = handed_in({'compute': 2, 'money': 2, 'attention': 0})   # cheaper in tokens, which this desk saves first, and dearer in money
        self.assertEqual((why, r['status'], r['actions'], r['cost'], r['pareto_options']),
                         (['it is dearer on money'], DONE, [ONE], {'compute': 2, 'money': 2, 'attention': 0}, 2))   # not dominated, and chosen: two units of money where the chain paid one
        why, r, run = handed_in(dict(CHAIN_COST), id='a-settle-payout@t')   # the chain's own cost, under an id that sorts before the chain's first step
        self.assertEqual((why, r['actions'], r['cost'], r['pareto_options']), (['it is cheaper on no line'], ['a-settle-payout@t'], CHAIN_COST, 2))   # chosen: between two ways of one cost the spelling of the id decides
        why, r, run = handed_in(dict(CHAIN_COST))                           # the same cost under the id of pack 226, which sorts after it
        self.assertEqual((why, r['actions'], r['pareto_options']), (['it is cheaper on no line'], CHAIN, 2))
        why, r, run = handed_in({'compute': 5, 'money': 2, 'attention': 0}, id='a-settle-payout@t')   # dearer on a line and cheaper on none
        self.assertEqual((why, r['actions'], r['cost'], r['pareto_options']), (['it is dearer on money', 'it is cheaper on no line'], CHAIN, CHAIN_COST, 1))   # not taken while the chain can run: the chain dominates it (the next test shows two more misfits that are not taken)
        self.assertEqual([(x['support'], [a['entry'] for a in x['at']]) for x in reader.proposals(kept(run), 3)], [(4, [3, 4, 5, 8])])   # and the chain's row goes on
        run.add('pack', {'pack': extra('t-reader-one-slot', providers={'local-provider': 1})})   # one slot left at the desk's provider: the chain of three steps cannot run
        r = event(run, due(105))[0]
        self.assertEqual((r['status'], r['actions'], r['cost']), (DONE, ['a-settle-payout@t'], {'compute': 5, 'money': 2, 'attention': 0}))   # then the dominated way is taken too

    def test_l12_two_more_misfits_are_not_chosen_and_one_that_makes_a_fact_inside_the_chain_is(self):   # added when the confirming round was settled
        def handed_in(id=ONE, **change):   # the checker's yes on the books, then a way that does not fit, handed in all the same; the next payout
            run, p, yes = self.way()
            way = pack('226_payout_in_one')
            way['methods'][0].update(change, id=id, grant='action:' + id)
            way['grants'] = ['action:' + id]
            run.add('pack', {'pack': way})
            return reader.fits(p, way['methods'][0]), event(run, due(104))[0], run
        for id in (ONE, 'a-settle-payout@t'):   # six tokens and no money: dearer in tokens, which this desk saves first, and cheaper in money; under the id of pack 226 and under one that sorts before the chain's first step
            why, r, run = handed_in(id, cost={'compute': 6, 'money': 0, 'attention': 0})
            self.assertEqual((why, r['actions'], r['cost'], r['pareto_options']), (['it is dearer on compute'], CHAIN, CHAIN_COST, 2), id)   # not dominated (two options stand) and not chosen: the chain is cheaper on the line saved first
            self.assertEqual({tuple(CHAIN), (id,)} - {tuple(m) for m, ok, _ in admissions(r) if ok}, set(), id)   # both ways were open
            self.assertEqual([(x['support'], [a['entry'] for a in x['at']]) for x in reader.proposals(kept(run), 3)], [(4, [3, 4, 5, 8])], id)   # and the chain's row goes on
        why, r, run = handed_in(requires=['payout_due', 'payee_vetted'])   # a way that requires a fact that nobody states
        self.assertEqual((why, r['actions'], r['cost'], r['pareto_options'], [m for m, _, _ in admissions(r) if ONE in m]), (['it requires other facts'], CHAIN, CHAIN_COST, 1, []))   # its plan is never offered, so the chain runs
        why, r, run = handed_in(effect='payout_paid', cost=dict(TOKEN))   # a way that makes a fact INSIDE the chain: the fact the pay step makes, for one token and no money
        self.assertEqual((why, r['status'], r['actions'], r['cost'], r['pareto_options']), (['it makes another fact'], DONE, [ONE, CHAIN[2]], {'compute': 3, 'money': 0, 'attention': 0}, 1))   # chosen in place of the check and the pay step: the chain is dominated
        self.assertEqual({f: run.state.fact(f)['truth'] for f in ('payee_checked', 'payout_paid', 'payout_reconciled')}, {'payee_checked': 'UNKNOWN', 'payout_paid': 'TRUE', 'payout_reconciled': 'TRUE'})   # the payee was not checked, no money was paid, and the payout reads reconciled
        self.assertEqual((run.state.fact('payout_paid')['source'], reader.proposals(kept(run), 3), reader.proposals(kept(run), 2)), ('LOCAL_MODEL:' + ONE, [], []))   # the reader proposes nothing: for it the row of chains has ended, as it does after a way that fits

    def test_c7_one_value_row_and_its_answers_read_as_one_answer(self):
        s = State.from_packs([pack(n) for n in C_DESK])
        self.assertEqual(answers(s), {'small': 'TRUE', 'weighty': 'FALSE'})
        self.assertEqual([(k.split('|')[1], row['version'], row.get('depends_on')) for k, row in s.evidence.items() if 'change_weight' in k],
                         [('change_weight', 'small', None), ('change_weight=small', 'small', [{'predicate': 'change_weight', 'version': 'small'}]),
                          ('change_weight=weighty', 'small', [{'predicate': 'change_weight', 'version': 'small'}])])
        s.apply(pack('223_lesson_judged_weighty'))   # one pack restates the value and its answers
        self.assertEqual(answers(s), {'small': 'FALSE', 'weighty': 'TRUE'})
        s.apply(value('small'))                      # the value alone: the answers written for `weighty` no longer read
        self.assertEqual(answers(s), {'small': 'UNKNOWN', 'weighty': 'UNKNOWN'})
        s.apply(value('weighty'))                    # and read again when the value is the one they were written for
        self.assertEqual(answers(s), {'small': 'FALSE', 'weighty': 'TRUE'})

    def test_c7_the_two_approvers_read_one_answer(self):
        run, p, yes = self.lesson()   # small: the desk's own yes
        self.assertEqual((st(yes), run.state.providers['independent-checker']), ([('reminder_lesson_approved', DONE, [OWN_L])], 1))
        run = collections(3)          # the same lesson judged weighty first: the checker's yes, and the own yes is no plan
        run.add('pack', {'pack': pack('223_lesson_judged_weighty')})
        yes = event(run, reader.row(p, 'reminder_stop_repeated'))
        self.assertEqual((st(yes), yes[0]['cost']['compute'], {tuple(m) for m, _, _ in admissions(yes[0])}), ([('reminder_lesson_approved', DONE, [CHECK_L])], 5, {(CHECK_L,)}))
        run = collections(3)          # the value restated alone: no answer reads, and no yes is offered
        run.add('pack', {'pack': value('weighty')})
        yes = event(run, reader.row(p, 'reminder_stop_repeated'))
        self.assertEqual((st(yes), yes[0]['stop_reasons'], run.state.budget['compute']), ([('reminder_lesson_approved', 'QUERY_EVIDENCE', [])], ['QUERY_EVIDENCE'], 12))

    def test_c8_a_chain_run_again_on_a_new_input_runs_and_pays_every_step(self):
        run = payouts(3)
        self.assertEqual([(r['actions'], r['cost'], r.get('skipped')) for n in (3, 4, 5) for r in run.detail[n]['runs'][:1]], [(CHAIN, CHAIN_COST, None)] * 3)
        self.assertEqual((run.state.budget, run.state.providers['local-provider']), ({'compute': 15, 'money': 3, 'attention': 0}, 3))
        self.assertEqual({k.split('|')[1]: (v['ran'], v['skipped']) for k, v in R.counts(kept(run))['steps'].items()}, {m: (3, 0) for m in CHAIN})
        self.assertEqual([m['requires'][0] for m in pack('224_payout_desk')['methods']], ['payout_due'] * 3)   # every step names the payout it works on

    def test_c8_no_step_of_the_work_requires_the_readers_row_or_an_answer_of_the_weight(self):
        methods = [m for n in ALL_PACKS for m in pack(n).get('methods', [])]
        guarded = sorted(m['id'] for m in methods if any('change_weight' in r or r.endswith('_repeated') for r in m['requires']))
        self.assertEqual(guarded, sorted([OWN_L, CHECK_L, OWN_P, CHECK_P, OWN_WAIVERS]))   # the four steps that give a yes and the one that asks for it, and no step of the work
        self.assertEqual(sorted(m['id'] for m in methods), sorted([REMIND, PHONE, ONE, OWN_L, CHECK_L, OWN_P, CHECK_P, OWN_WAIVERS, OWN_204, WAIVE_204] + CHAIN + ASKS + WAIVES))

    def test_c8_after_the_hand_in_a_restated_guard_reopens_nothing(self):
        run, p, yes = self.lesson()
        run.add('pack', {'pack': pack('222_reminder_lesson')})
        event(run, overdue(4))
        before = dict(run.state.budget), dict(run.state.providers)
        e = run.add('event', {'row': dict(reader.row(p, 'reminder_stop_repeated'), version='read-again'), 'execute': True})   # the reader's row restated
        self.assertEqual((e['result']['status'], e['result']['affected'], e['result']['briefs']), ('RECONCILED', [], []))
        run.add('pack', {'pack': pack('223_lesson_judged_weighty')})                                                    # the weight restated
        self.assertEqual(st(look(run)), [('reminder_sent', 'SUPPORTED_BY_EVIDENCE', [])])
        self.assertEqual(((dict(run.state.budget), dict(run.state.providers)), run.state.fact('reminder_lesson_approved')['truth'], run.state.fact('reminder_sent')['truth']),
                         (before, 'UNKNOWN', 'TRUE'))   # the yes no longer reads and nobody plans it; the work stands and nothing was paid
        run, p, yes = self.way()
        run.add('pack', {'pack': pack('226_payout_in_one')})
        event(run, due(104))
        before = dict(run.state.budget)
        run.add('pack', {'pack': value('small')})
        run.add('event', {'row': dict(reader.row(p, 'payout_chain_repeated'), version='read-again'), 'execute': True})
        self.assertEqual((st(look(run)), dict(run.state.budget)), ([('payout_reconciled', 'SUPPORTED_BY_EVIDENCE', [])], before))


class Answers(unittest.TestCase):
    """C9 and C10: a question answered the same way each time, and a yes asked of another system. The recorded sequence `reader_answers` shows the
    waiver desk of pack 228; the desk made here, where every loan is a scope of its own, is held by these tests alone."""
    def desk(self, loans=3, last='TRUE', parties=None):   # a desk that asks about each loan's late fee; every loan is a scope of its own
        waive = {'id': 'waive-late-fee@t', 'effect': 'fee_waived', 'requires': ['waiver_requested', 'waiver_approved'], 'provider': 'local-provider',
                 'grant': 'action:waive-late-fee@t', 'cost': TOKEN, 'action': 'simulate_fact', 'approved': True}
        ask = lambda id, to: {'id': id, 'effect': 'waiver_approved', 'requires': [], 'provider': 'finance-channel', 'grant': 'action:' + id,
                              'cost': {'compute': 0, 'money': 0, 'attention': 1}, 'action': 'ask', 'approved': True, 'question': QUESTION, 'ask_to': to}
        step = {FINANCE: 'ask-finance-waiver@t', RISK: 'ask-risk-waiver@t'}   # the same words, put to finance or to risk: the grant that is held says who is asked
        truths = last if type(last) is list else ['TRUE'] * (loans - 1) + [last]   # what is answered, loan by loan
        parties = parties or [FINANCE] * len(truths)
        requested = lambda loan: [{'predicate': 'waiver_requested', 'truth': 'TRUE', 'verified': True, 'source': BOOK, 'version': f'loan-{loan}'}]
        run = started([extra('t-reader-waivers', scope='lendco/collections/loan-201', goals=['fee_waived'], budget={'compute': 12, 'money': 0, 'attention': 6},
                             preference=['compute', 'money', 'attention'], evidence=requested(201), methods=[waive] + [ask(id, to) for to, id in step.items() if to in parties],
                             providers={'local-provider': 6, 'finance-channel': 6}, grants=['action:waive-late-fee@t', 'action:' + step[parties[0]]])],
                      'waivers', kinds=('simulate_fact', 'ask'))
        entries = []
        for i, (truth, party) in enumerate(zip(truths, parties)):
            if i:
                moved = {} if party == parties[i - 1] else {'grants': ['action:' + step[party]], 'revoke_grants': ['action:' + step[parties[i - 1]]]}
                run.add('pack', {'pack': extra(f't-reader-loan-{201 + i}', scope=f'lendco/collections/loan-{201 + i}', evidence=requested(201 + i), **moved)})
            asked = look(run)
            self.assertEqual((asked[0]['status'], asked[0]['waits'], asked[0]['model_receipts'][-1]['ask']['to']), ('WAITING', [step[party]], party))
            e = run.add('answer', {'receipt': asked[0]['model_receipts'][-1], 'truth': truth, 'source': party, 'execute': True})
            entries.append(e['seq'])
        return run, entries

    def waivers(self):   # the waiver desk of pack 228: three loans, one question each to finance, three times yes
        return waivers()

    def test_c9_three_loans_asked_in_the_same_words_and_answered_yes_are_one_proposal(self):
        run = self.waivers()
        self.assertEqual([e['kind'] for e in run.journal], ['header', 'pack', 'look', 'answer', 'answer', 'answer'])
        self.assertEqual(reader.proposals(kept(run), 3), [{'kind': 'REPEATED_ANSWER', 'to': FINANCE, 'question': MAY_WAIVE, 'truth': 'TRUE', 'support': 3,
                                                           'at': cites(run, 3, 4, 5, runs=False), 'status': 'PROPOSED_ONLY'}])
        self.assertEqual([(r['predicate'], r['question'], r['to']) for r in R.ledger(kept(run)) if r['what'] == 'asked'], [(f'waiver_approved_{n}', MAY_WAIVE, FINANCE) for n in (201, 202, 203)])
        self.assertEqual(reader.proposals([(kept(run)[0][0], {'length': 5, 'sha256': run.journal[4]['sha256']})], 3), [])   # as of the second answer: two are not three

    def test_c10_before_the_readers_row_the_question_to_finance_is_not_put(self):
        run = self.waivers()
        r = run.detail[2]['runs'][3]
        self.assertEqual((r['goal'], r['status'], r['stop_reasons'], sorted(open_asks(run.state))), ('own_waivers_approved', 'QUERY_EVIDENCE', ['QUERY_EVIDENCE'], []))
        self.assertEqual(st(look(run))[3], ('own_waivers_approved', 'QUERY_EVIDENCE', []))   # and not at a later look either

    def test_c10_the_yes_to_the_change_is_asked_of_another_system_and_only_its_answer_gives_it(self):
        run = self.waivers()
        p = reader.proposals(kept(run), 3)[0]
        asked = event(run, reader.row(p, 'waiver_answer_repeated'))
        receipt = asked[0]['model_receipts'][-1]
        self.assertEqual((st(asked), asked[0]['waits'], receipt['ask']['to'], receipt['ask']['predicate'], sorted(open_asks(run.state))),
                         ([('own_waivers_approved', 'WAITING', [OWN_WAIVERS])], [OWN_WAIVERS], FINANCE, 'own_waivers_approved', [SCOPE_W + '|own_waivers_approved']))
        for party in ('system:lendco/waivers', 'adapter:reader', ''):   # the desk cannot answer its own question, and neither can the reader
            with self.assertRaisesRegex(ValueError, 'The answer does not come from the party that was asked'):
                run.add('answer', {'receipt': receipt, 'truth': 'TRUE', 'source': party, 'execute': True})
        self.assertEqual(run.state.fact('own_waivers_approved')['truth'], 'UNKNOWN')
        yes = run.add('answer', {'receipt': receipt, 'truth': 'TRUE', 'source': FINANCE, 'execute': True})
        row = run.state.fact('own_waivers_approved')
        self.assertEqual((row['truth'], row['source'], row['final'], row['answers'], yes['seq']), ('TRUE', 'STAMP:' + FINANCE, True, receipt['sha256'], 7))   # who said yes is on the row
        self.assertEqual([(r['entry'], r['predicate'], r['truth'], r['by']) for r in R.ledger(kept(run)) if r['what'] == 'decided'][-1], (7, 'own_waivers_approved', 'TRUE', FINANCE))

    def test_c10_the_rule_that_came_of_the_answers_the_next_loan_is_waived_on_the_desks_own_yes(self):
        run = self.waivers()
        asked = event(run, reader.row(reader.proposals(kept(run), 3)[0], 'waiver_answer_repeated'))
        run.add('answer', {'receipt': asked[0]['model_receipts'][-1], 'truth': 'TRUE', 'source': FINANCE, 'execute': True})
        run.add('pack', {'pack': pack('229_own_waivers')})
        r = look(run)
        self.assertEqual((st(r), r[0]['cost'], open_asks(run.state)), ([('fee_waived_204', DONE, [OWN_204, WAIVE_204])], {'compute': 2, 'money': 0, 'attention': 0}, {}))
        self.assertEqual(said(run.state, 'waiver_approved_204')[:2], ('TRUE', 'LOCAL_MODEL:' + OWN_204))
        self.assertEqual(len([x for x in R.ledger(kept(run)) if x['what'] == 'asked']), 4)   # three loans and the change: finance was asked nothing about loan 204
        self.assertEqual([m['id'] for m in pack('229_own_waivers')['methods']], [OWN_204, WAIVE_204])   # the rule is a pack for one loan: the lab has no parameters

    def test_l13_a_yes_that_was_asked_for_is_a_decision_and_rests_on_nothing(self):
        run = self.waivers()
        p = reader.proposals(kept(run), 3)[0]
        asked = event(run, reader.row(p, 'waiver_answer_repeated'))
        run.add('answer', {'receipt': asked[0]['model_receipts'][-1], 'truth': 'TRUE', 'source': FINANCE, 'execute': True})
        row = run.state.fact('own_waivers_approved')
        self.assertEqual((row.get('depends_on'), digest(p) in json.dumps([row, asked[0]['model_receipts'][-1]])), (None, False))   # neither the yes nor the question names the proposal
        again = event(run, dict(reader.row(p, 'waiver_answer_repeated'), version='read-again'))   # the reader's row under another version: this yes stands (the step's yes of L2 does not)
        self.assertEqual((st(again), run.state.fact('own_waivers_approved')['truth']), ([('own_waivers_approved', 'SUPPORTED_BY_EVIDENCE', [])], 'TRUE'))

    def test_c9_one_question_answered_the_same_way_three_times_is_one_proposal_that_names_the_answers(self):
        run, entries = self.desk(3)
        self.assertEqual(entries, [3, 6, 9])
        self.assertEqual(reader.proposals(kept(run), 3), [{'kind': 'REPEATED_ANSWER', 'to': FINANCE, 'question': QUESTION, 'truth': 'TRUE', 'support': 3,
                                                           'at': cites(run, 3, 6, 9, runs=False), 'status': 'PROPOSED_ONLY'}])
        self.assertEqual([r['scope'] for r in R.ledger(kept(run)) if r['what'] == 'ran' and r['actions'] == ['waive-late-fee@t']], [f'lendco/collections/loan-{n}' for n in (201, 202, 203)])
        row = reader.row(reader.proposals(kept(run), 3)[0], 'waiver_answer_repeated')
        self.assertEqual((row['source'], row['version']), ('adapter:reader', digest(reader.proposals(kept(run), 3)[0])))

    def test_c9_two_answers_are_not_three_and_one_other_answer_ends_it(self):
        self.assertEqual(reader.proposals(kept(self.desk(2)[0]), 3), [])
        run, entries = self.desk(4, last='FALSE')
        self.assertEqual((reader.proposals(kept(run), 3), reader.proposals(kept(run), 2)), ([], []))   # three times yes, then a no: not the same way every time
        self.assertEqual(reader.proposals([(kept(run)[0][0], {'length': 10, 'sha256': run.journal[9]['sha256']})], 3)[0]['support'], 3)   # as of the head the third yes left

    def test_c9_every_answer_in_the_record_counts_so_an_other_answer_before_the_repeats_ends_it_too(self):
        run, entries = self.desk(last=['FALSE', 'TRUE', 'TRUE', 'TRUE'])   # finance says no about the first loan, then yes three times
        self.assertEqual(([(r['entry'], r['truth']) for r in R.ledger(kept(run)) if r['what'] == 'decided'], entries), ([(3, 'FALSE'), (6, 'TRUE'), (9, 'TRUE'), (12, 'TRUE')], [3, 6, 9, 12]))
        self.assertEqual((reader.proposals(kept(run), 3), reader.proposals(kept(run), 2)), ([], []))   # unlike stops and chains, answers are not counted back from the newest: the old no ends the question for good
        run, entries = self.desk(last=['FALSE'] + ['TRUE'] * 5)
        self.assertEqual(reader.proposals(kept(run), 2), [])   # however many times yes follows

    def test_c9_the_same_words_put_to_two_parties_are_two_questions(self):
        run, entries = self.desk(parties=[FINANCE, RISK, FINANCE])   # the same words: finance, then risk, then finance again; yes each time
        self.assertEqual(([(r['entry'], r['by'], r['truth']) for r in R.ledger(kept(run)) if r['what'] == 'decided'], {r['question'] for r in R.ledger(kept(run)) if r['what'] == 'asked'}),
                         ([(3, FINANCE, 'TRUE'), (6, RISK, 'TRUE'), (9, FINANCE, 'TRUE')], {QUESTION}))
        self.assertEqual(reader.proposals(kept(run), 3), [])   # three equal answers to the same words, and no question that was answered three times
        self.assertEqual([(p['to'], p['support'], p['at']) for p in reader.proposals(kept(run), 2)], [(FINANCE, 2, cites(run, 3, 9, runs=False))])   # finance's two; the answer of risk is another question's

    def test_c9_questions_are_listed_in_the_order_they_were_first_answered(self):   # added when the confirming round was settled
        run, entries = self.desk(4, parties=[RISK, RISK, FINANCE, FINANCE])   # the same words: risk is asked about two loans, then finance about two; yes each time
        self.assertEqual([(p['to'], p['support'], p['at']) for p in reader.proposals(kept(run), 2)],
                         [(RISK, 2, cites(run, *entries[:2], runs=False)), (FINANCE, 2, cites(run, *entries[2:], runs=False))])
        run, entries = self.desk(4, parties=[FINANCE, RISK, RISK, FINANCE])   # finance first and last, risk in between
        self.assertEqual([(p['to'], [a['entry'] for a in p['at']]) for p in reader.proposals(kept(run), 2)], [(FINANCE, [entries[0], entries[3]]), (RISK, entries[1:3])])   # by the first answer of each question, not by its last

    def test_c9_an_answer_to_a_receipt_the_record_never_asked_is_refused_in_the_readers_words(self):
        run, entries = self.desk(2)

        def other(entries):   # a forger's text: the first answer presents a receipt that no entry issued
            entries[3]['body']['receipt']['sha256'] = '0' * 64
        self.assertEqual(reader.proposals(kept(run), 2)[0]['support'], 2)
        with self.assertRaisesRegex(ValueError, exactly('The journal does not hold what the reader reads from it')):
            reader.proposals(rechained(run, 3, other), 2)

    def test_l5_a_repeated_answer_stays_proposed_whatever_is_done_about_it(self):
        run, entries = self.desk(3)
        p = reader.proposals(kept(run), 3)
        run.add('pack', {'pack': extra('t-reader-any-change', budget={'attention': 9})})
        self.assertEqual(st(look(run)), [('fee_waived', 'SUPPORTED_BY_EVIDENCE', [])])
        self.assertEqual(reader.proposals(kept(run), 3), p)   # the reader does not see whether a proposal was acted on

    def test_l6_on_one_scope_a_question_is_asked_once_so_a_repeat_needs_a_scope_for_each_case(self):
        run, entries = self.desk(1)
        self.assertEqual(st(look(run)), [('fee_waived', 'SUPPORTED_BY_EVIDENCE', [])])   # the yes stands as a decision in this scope
        run.add('event', {'row': {'predicate': 'waiver_requested', 'truth': 'TRUE', 'verified': True, 'source': BOOK, 'version': 'loan-201-again'}, 'execute': True})
        asked = [r for r in R.ledger(kept(run)) if r['what'] == 'asked']
        self.assertEqual((len(asked), open_asks(run.state)), (1, {}))   # a new request in the same scope: waived again, and finance is not asked again
        self.assertEqual(reader.proposals(kept(run), 2), [])


class Existing(unittest.TestCase):
    """The attempt ruling R35 asks for: the same records read with the parts the lab had before this version."""
    def test_the_learner_fed_every_run_in_journal_order_says_nothing_of_three_stops(self):
        run, keep = collections(3), J.Keep()
        J.save(run, keep)
        again = J.restart(keep)   # a new process: the kept text and head
        runs = [r for n in sorted(again.detail) for r in again.detail[n]['runs']]
        learner = Learner(True)
        self.assertEqual([(r['goal'], r['status'], learner.learn(r)) for r in runs if r['goal'] == 'reminder_sent'], [('reminder_sent', 'STEP_STOPPED', [])] * 3)
        self.assertEqual(reflect(runs)['candidates'], [])
        count = R.counts([keep.read()])['steps'][SCOPE_C + '|' + REMIND]
        self.assertEqual((count['ran'], count['stopped'], count['skipped'], [a['entry'] for a in count['at']]), (0, 3, 0, [3, 4, 5]))
        self.assertNotIn('reason', json.dumps(R.counts([keep.read()])))   # the count names the entries and no reason; it proposes nothing

    def test_the_kernel_alone_offers_the_stopping_plan_at_every_look(self):
        s = State.from_packs([pack(n) for n in C_DESK])
        for _ in range(3):
            r = Kernel(s).run_standing(execute=True)['runs'][0]
            self.assertEqual((r['status'], r['pending'], r['stopped']), ('STEP_STOPPED', [REMIND], {'method': REMIND, 'reason': WHY}))
        self.assertEqual(s.budget['compute'], 12)

    def test_the_learner_counts_a_chain_in_memory_and_names_no_entry(self):
        run, keep = payouts(3), J.Keep()
        J.save(run, keep)
        again = J.restart(keep)
        work = [r for n in sorted(again.detail) for r in again.detail[n]['runs'] if r['goal'] == 'payout_reconciled']
        learner = Learner(True)
        told = [learner.learn(r) for r in work]
        self.assertEqual([(t[0]['kind'], t[0]['signature'], t[0]['observations']) for t in told], [('REUSE_COMPOSITION', ' -> '.join(CHAIN), n) for n in (1, 2, 3)])
        self.assertEqual(Learner(True).learn(work[-1])[0]['observations'], 1)   # a Learner that was not fed the runs before says one
        self.assertEqual(sorted(told[-1][0]), ['gate', 'kind', 'observations', 'signature', 'status'])   # no entry, no journal
        self.assertEqual([(c['kind'], c['support'], sorted(c)) for c in reflect(work)['candidates'] if c['kind'] == 'COMPRESSION_CANDIDATE'],
                         [('COMPRESSION_CANDIDATE', 3, ['gate', 'kind', 'reexpandable', 'signature', 'source_traces', 'status', 'support'])])   # trace roots, no entries

    def test_the_ledger_holds_each_stop_with_its_reason_each_run_with_its_steps_and_cost_and_each_answer_and_groups_nothing(self):
        run = collections(3)   # the record adapter's ledger is what the reader itself reads: every stop with its entry, its hash, its step and its reason
        self.assertEqual([(x['entry'], x['sha256'], x['stopped']) for x in R.ledger(kept(run)) if x.get('stopped')],
                         [(n, run.journal[n]['sha256'], {'method': REMIND, 'reason': WHY}) for n in (3, 4, 5)])
        run = payouts(3)       # every run with its steps and its cost
        rows = [x for x in R.ledger(kept(run)) if x['what'] == 'ran' and x['goal'] == 'payout_reconciled']
        self.assertEqual([(x['entry'], x['actions'], x['cost']) for x in rows], [(n, CHAIN, CHAIN_COST) for n in (3, 4, 5)])
        work = [r for n in sorted(run.detail) for r in run.detail[n]['runs'] if r['goal'] == 'payout_reconciled']
        entry_of = {x['trace_root_sha256']: x['entry'] for x in rows}   # three payouts, three trace roots: the ledger maps each to its entry
        self.assertEqual([(c['support'], c['status'], [entry_of[t] for t in c['source_traces']]) for c in reflect(work)['candidates'] if c['kind'] == 'COMPRESSION_CANDIDATE'],
                         [(3, 'PROPOSED_ONLY', [3, 4, 5])])   # so `reflect` joined with the ledger names the chain's entries
        led = R.ledger(kept(waivers()))   # every question with its words and its party, every answer with the entry of its question
        self.assertEqual([(x['entry'], x['question'], x['to']) for x in led if x['what'] == 'asked'], [(2, MAY_WAIVE, FINANCE)] * 3)
        self.assertEqual([(x['entry'], x['truth'], x['by'], x['asked_at']['entry']) for x in led if x['what'] == 'decided'], [(n, 'TRUE', FINANCE, 2) for n in (3, 4, 5)])
        # What these parts do not say: that the newest runs of a goal are alike so many times, how often a question was answered one way, a chain worded as one step.
        counts = R.counts(kept(waivers()))
        self.assertEqual((sorted(counts), sorted({k for g in counts['goals'].values() for k in g}), sorted({k for s in counts['steps'].values() for k in s})),
                         (['goals', 'steps'], ['at', 'executed', 'looked', 'statuses', 'trace_roots'], ['at', 'ran', 'skipped', 'stopped']))   # counts over the whole record, per goal and per step: nothing of answers
        candidate = [c for c in reflect(work)['candidates'] if c['kind'] == 'COMPRESSION_CANDIDATE'][0]
        self.assertEqual([w for w in ('as_one', 'requires', 'effect') if w in json.dumps(candidate)], [])   # the candidate names a signature and trace roots: no step that stands for the chain

    def test_the_three_recorded_flows_come_out_when_the_caller_counts_the_ledger_and_words_the_row(self):   # added when the confirming round was settled
        ADAPTER = 'adapter:journal-record'   # the caller's row goes in under a name of its own, which these journals' headers list where the recorded ones list the reader's
        word = lambda fact, of: {'predicate': fact, 'truth': 'TRUE', 'verified': True, 'source': ADAPTER, 'version': digest(of)}

        def desk(names, kinds=('simulate_fact',)):
            run = J.start(list(kinds), [BOOK, ADAPTER], name='no-reader')
            for n in names:
                run.add('pack', {'pack': pack(n)})
            return run
        count = lambda run: R.counts(kept(run))['steps'][SCOPE_C + '|' + REMIND]
        run = desk(C_DESK)   # the collections desk: the record adapter's count of the step, compared with three by the caller
        look(run)
        event(run, overdue(2))
        self.assertEqual((count(run)['stopped'], [a['entry'] for a in count(run)['at']]), (2, [3, 4]))   # two stops: the caller words no row
        event(run, overdue(3))
        self.assertEqual((count(run)['stopped'], [a['entry'] for a in count(run)['at']]), (3, [3, 4, 5]))
        self.assertEqual(st(event(run, word('reminder_stop_repeated', count(run)['at']))), [('reminder_lesson_approved', DONE, [OWN_L])])   # three stops counted: the row goes in, and the desk's own yes is given
        run.add('pack', {'pack': pack('222_reminder_lesson')})
        self.assertEqual(st(event(run, overdue(4))), [('reminder_sent', DONE, [PHONE])])   # the lesson is handed in and the reminder is sent, as in `reader_lesson`
        run = desk(P_DESK)   # the payout desk: `reflect` joined with the ledger
        look(run)
        event(run, due(102))
        event(run, due(103))
        work = [r for n in sorted(run.detail) for r in run.detail[n]['runs'] if r['goal'] == 'payout_reconciled']
        entry_of = {x['trace_root_sha256']: x['entry'] for x in R.ledger(kept(run)) if x['what'] == 'ran'}
        chain = [c for c in reflect(work)['candidates'] if c['kind'] == 'COMPRESSION_CANDIDATE'][0]
        self.assertEqual((chain['signature'], chain['support'], [entry_of[t] for t in chain['source_traces']]), (' -> '.join(CHAIN), 3, [3, 4, 5]))
        self.assertEqual(st(event(run, word('payout_chain_repeated', chain))), [('payout_way_approved', DONE, [CHECK_P])])   # the row goes in, and the independent checker's yes is given
        run.add('pack', {'pack': pack('226_payout_in_one')})
        fourth = event(run, due(104))[0]
        self.assertEqual((fourth['actions'], fourth['cost'], run.state.budget), ([ONE], ONE_COST, {'compute': 8, 'money': 2, 'attention': 0}))   # the fourth payout by the one step, and the books as `reader_one_way` leaves them
        run = desk(['228_waiver_desk'], kinds=('simulate_fact', 'ask'))   # the waiver desk: the ledger's rows of the answers, counted in one line
        for r in look(run)[:3]:
            run.add('answer', {'receipt': r['model_receipts'][-1], 'truth': 'TRUE', 'source': FINANCE, 'execute': True})
        yes = [x['entry'] for x in R.ledger(kept(run)) if x['what'] == 'decided' and x['by'] == FINANCE and x['truth'] == 'TRUE']
        self.assertEqual(yes, [3, 4, 5])
        asked = event(run, word('waiver_answer_repeated', yes))
        self.assertEqual((st(asked), asked[0]['model_receipts'][-1]['ask']['to']), ([('own_waivers_approved', 'WAITING', [OWN_WAIVERS])], FINANCE))   # the row goes in, and the question about the change goes to finance
        run.add('answer', {'receipt': asked[0]['model_receipts'][-1], 'truth': 'TRUE', 'source': FINANCE, 'execute': True})
        run.add('pack', {'pack': pack('229_own_waivers')})
        self.assertEqual((st(look(run)), open_asks(run.state)), ([('fee_waived_204', DONE, [OWN_204, WAIVE_204])], {}))   # finance's yes, the rule handed in, and loan 204 waived with nobody asked, as in `reader_answers`
        self.assertEqual(json.loads(kept(run)[0][0].split('\n')[0])['body']['checkers'], [BOOK, ADAPTER])   # no row of these three journals came in under the reader's name

    def test_a_rehearsal_on_a_copy_of_the_kept_journal_shows_what_the_kernel_does_with_a_way(self):   # added when the confirming round was settled
        run, keep = payouts(3), J.Keep()
        J.save(run, keep)
        p = reader.proposals([keep.read()], 3)[0]
        before = keep.read()

        def rehearsed(loans, **change):   # a second process replays a COPY of the kept journal, takes the way there and is handed more payouts: parts of the journal version and the kernel's own choice
            way = pack('226_payout_in_one')
            way['methods'][0].update(change)
            copy = J.restart(J.Keep(*keep.read()))
            copy.add('pack', {'pack': way})
            return reader.fits(p, way['methods'][0]), [(r['status'], r['actions'], r['cost']) for loan in loans for r in event(copy, due(loan))]
        paid = (DONE, [ONE], ONE_COST)
        self.assertEqual(rehearsed((104, 105)), ([], [paid, paid]))   # pack 226 as it is: `fits` gives no reason, and both rehearsed payouts run the one step
        self.assertEqual(rehearsed((104, 105), requires=[]), (['it requires other facts'], [paid, ('SUPPORTED_BY_EVIDENCE', [], FREE)]))   # a way that names no input: the rehearsal shows the fault itself, the second payout reads done and nothing runs (limit L12)
        self.assertEqual(rehearsed((104,), cost={'compute': 2, 'money': 2, 'attention': 0}), (['it is dearer on money'], [(DONE, [ONE], {'compute': 2, 'money': 2, 'attention': 0})]))   # dearer in money: it is chosen and pays two
        self.assertEqual(rehearsed((104,), cost={'compute': 6, 'money': 0, 'attention': 0}), (['it is dearer on compute'], [(DONE, CHAIN, CHAIN_COST)]))   # dearer in tokens: it is not chosen, the chain runs
        self.assertEqual(rehearsed((104,), effect='payout_paid', cost=dict(TOKEN)), (['it makes another fact'], [(DONE, [ONE, CHAIN[2]], {'compute': 3, 'money': 0, 'attention': 0})]))   # makes a fact inside the chain: it stands in for the steps before it
        self.assertEqual(keep.read(), before)   # the kept journal is as it was: nothing was handed in at the desk


class Sequences(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.lesson, cls.way, cls.answers = sequence('reader_lesson'), sequence('reader_one_way'), sequence('reader_answers')
        cls.data = json.loads((ROOT / 'results' / 'actual_run_records.json').read_text())

    def runs(self, step):
        return [(r['goal'], r['status'], r['actions']) for r in step['result']['runs']]

    def test_the_record_on_disk_holds_the_three_sequences(self):
        for name, made in (('reader_lesson', self.lesson), ('reader_one_way', self.way), ('reader_answers', self.answers)):
            self.assertEqual(json.dumps(made, sort_keys=True), json.dumps(self.data['scenes'][name], sort_keys=True), name)

    def test_lesson_three_stops_one_proposal_the_desks_own_yes_the_pack_and_the_reminder(self):
        q = self.lesson
        self.assertEqual([self.runs(d)[0] for d in q['three_days']], [('reminder_sent', 'STEP_STOPPED', [])] * 3)
        self.assertEqual([d['result']['runs'][0]['stopped'] for d in q['three_days']], [{'method': REMIND, 'reason': WHY}] * 3)
        self.assertEqual((q['after_two'], len(q['proposals']), q['proposals_after']), ([], 1, []))
        p = q['proposals'][0]
        self.assertEqual((p['kind'], p['step'], p['reason'], p['support'], [a['entry'] for a in p['at']]), ('REPEATED_STOP', REMIND, WHY, 3, [3, 4, 5]))
        self.assertEqual(q['proposals'], reader.proposals([(q['text'], q['head_after_three'])], 3))   # read again from the text the record holds
        self.assertEqual((q['after_two'], q['proposals_after']), (reader.proposals([(q['text'], q['head_after_two'])], 3), reader.proposals([(q['text'], q['head'])], 3)))
        self.assertEqual(q['row'], reader.row(p, 'reminder_stop_repeated'))
        self.assertEqual((self.runs(q['yes']), q['approved']['source'], q['approved']['depends_on'][0]),
                         ([('reminder_lesson_approved', DONE, [OWN_L])], 'LOCAL_MODEL:' + OWN_L, {'predicate': 'reminder_stop_repeated', 'version': digest(p)}))
        self.assertEqual((q['yes']['entry'], q['handed_in'], q['day_four']['entry']), (6, {'entry': 7, 'pack': '222_reminder_lesson'}, 8))
        self.assertEqual((self.runs(q['day_four']), q['after_hand_in']['goals']), ([('reminder_sent', DONE, [PHONE])], ['reminder_sent']))
        self.assertEqual([json.loads(line)['kind'] for line in q['text'].split('\n')[:-1]], ['header', 'pack', 'pack', 'look', 'event', 'event', 'event', 'pack', 'event'])

    def test_lesson_judged_weighty_the_same_row_gets_the_checkers_yes(self):
        w = self.lesson['judged_weighty']
        self.assertEqual((self.runs(w['yes']), w['approved']['source'], w['approved']['depends_on'], w['answers']),
                         ([('reminder_lesson_approved', DONE, [CHECK_L])], 'LOCAL_MODEL:' + CHECK_L,
                          [{'predicate': 'reminder_stop_repeated', 'version': self.lesson['row']['version']}, {'predicate': 'change_weight=weighty', 'version': 'weighty'}],
                          {'small': 'FALSE', 'weighty': 'TRUE'}))
        self.assertEqual((w['after']['budget']['compute'], w['after']['providers']['independent-checker'], self.lesson['after_three']['budget']['compute']), (7, 0, 12))

    def test_lesson_what_the_parts_the_lab_had_say_of_the_same_record(self):
        x = self.lesson['existing_parts']
        self.assertEqual(x['learner_fed_in_journal_order'], [[], [{'kind': 'INVESTIGATE_GAP', 'gap': 'QUERY_EVIDENCE', 'status': 'PROPOSED_ONLY', 'gate': 'independent evidence + authorization'}], [], []])
        self.assertEqual((x['reflect'], x['count_of_the_step']['stopped'], [a['entry'] for a in x['count_of_the_step']['at']]), ([], 3, [3, 4, 5]))

    def test_one_way_three_chains_one_proposal_the_checkers_yes_the_pack_and_the_one_step(self):
        q = self.way
        self.assertEqual([self.runs(d)[0] for d in q['three_payouts']], [('payout_reconciled', DONE, CHAIN)] * 3)
        self.assertEqual([d['result']['runs'][0]['cost'] for d in q['three_payouts']], [CHAIN_COST] * 3)
        p = q['proposals'][0]
        self.assertEqual((len(q['proposals']), p['kind'], p['steps'], p['paid'], p['as_one'], p['support'], [a['entry'] for a in p['at']]),
                         (1, 'REPEATED_CHAIN', CHAIN, CHAIN_COST, {'effect': 'payout_reconciled', 'requires': ['payout_due']}, 3, [3, 4, 5]))
        self.assertEqual((q['proposals'], q['proposals_after']), (reader.proposals([(q['text'], q['head_after_three'])], 3), reader.proposals([(q['text'], q['head'])], 3)))
        self.assertEqual((q['way'], q['fits'], q['row']), (pack('226_payout_in_one')['methods'][0], [], reader.row(p, 'payout_chain_repeated')))
        self.assertEqual((self.runs(q['yes']), q['approved']['source'], q['approved']['depends_on']),
                         ([('payout_way_approved', DONE, [CHECK_P])], 'LOCAL_MODEL:' + CHECK_P,
                          [{'predicate': 'payout_chain_repeated', 'version': digest(p)}, {'predicate': 'change_weight=weighty', 'version': 'weighty'}]))
        self.assertEqual((q['yes']['entry'], q['handed_in'], q['loan_104']['entry'], q['proposals_after']), (6, {'entry': 7, 'pack': '226_payout_in_one'}, 8, []))
        self.assertEqual((self.runs(q['loan_104']), q['loan_104']['result']['runs'][0]['cost'], q['after']['budget']), ([('payout_reconciled', DONE, [ONE])], ONE_COST, {'compute': 8, 'money': 2, 'attention': 0}))

    def test_one_way_no_yes_no_hand_in_and_the_proposal_then_rests_on_four_entries(self):
        n = self.way['no_yes']
        self.assertEqual((self.runs(n['yes']), n['approved'], n['handed_in']),
                         ([('payout_way_approved', 'PROVIDER_REQUIRED', [])], {'truth': 'UNKNOWN', 'source': None, 'depends_on': None}, {'entry': None, 'pack': '226_payout_in_one'}))
        self.assertEqual((self.runs(n['loan_104']), n['loan_104']['result']['runs'][0]['cost'], n['after']['budget']), ([('payout_reconciled', DONE, CHAIN)], CHAIN_COST, {'compute': 10, 'money': 2, 'attention': 0}))
        p = n['proposals_after']
        self.assertEqual(([(x['support'], [a['entry'] for a in x['at']]) for x in p], p == reader.proposals([(n['text'], n['head'])], 3)), ([(4, [3, 4, 5, 8])], True))
        self.assertNotEqual(reader.row(p[0], 'payout_chain_repeated')['version'], self.way['row']['version'])   # four entries are another proposal: a yes would rest on that one
        self.assertEqual([json.loads(line)['kind'] for line in n['text'].split('\n')[:-1]], ['header', 'pack', 'pack', 'look', 'event', 'event', 'pack', 'event', 'event'])
        self.assertEqual([x['pack'] for x in n['loan_104']['result']['runs'][0]['provenance']], P_DESK + ['227_checker_away'])

    def test_one_way_what_the_parts_the_lab_had_say_of_the_same_record(self):
        x = self.way['existing_parts']
        self.assertEqual([t[0]['observations'] for t in x['one_learner_fed_in_journal_order']], [1, 2, 3])
        self.assertEqual((x['a_new_learner_on_the_last_run'][0]['observations'], [c['support'] for c in x['reflect']]), (1, [3]))
        self.assertEqual({m: (c['ran'], c['skipped']) for m, c in x['counts_of_the_steps'].items()}, {m: (3, 0) for m in CHAIN})
        self.assertNotIn('entry', json.dumps([x['one_learner_fed_in_journal_order'], x['a_new_learner_on_the_last_run'], x['reflect']]))

    def test_every_run_of_both_sequences_names_the_packs_it_stood_on(self):
        for q, extra_pack in ((self.lesson, '222_reminder_lesson'), (self.way, '226_payout_in_one')):
            for key in ('three_days', 'three_payouts'):
                for d in q.get(key, []):
                    for r in d['result']['runs']:
                        self.assertEqual([x['pack'] for x in r['provenance']], q['packs'])
            last = q.get('day_four') or q.get('loan_104')
            self.assertEqual([x['pack'] for x in last['result']['runs'][0]['provenance']], q['packs'] + [extra_pack])
        self.assertEqual([x['pack'] for x in self.lesson['judged_weighty']['yes']['result']['runs'][0]['provenance']], C_DESK + ['223_lesson_judged_weighty'])
        for text in (self.lesson['text'], self.way['text'], self.way['no_yes']['text']):   # a State of these journals has one action kind: no step of it can ask anybody
            header = json.loads(text.split('\n')[0])['body']
            self.assertEqual((header['kinds'], header['checkers']), (['simulate_fact'], [BOOK, 'adapter:reader']))
        header = json.loads(self.answers['text'].split('\n')[0])['body']
        self.assertEqual((header['kinds'], header['checkers']), (['simulate_fact', 'ask'], [BOOK, 'adapter:reader']))

    def test_answers_three_yes_one_proposal_finances_yes_the_pack_and_the_desks_own_yes(self):
        q = self.answers
        self.assertEqual(self.runs(q['asked']), [(f'fee_waived_{n}', 'WAITING', [f'ask-finance-waiver-{n}@1']) for n in (201, 202, 203)] + [('own_waivers_approved', 'QUERY_EVIDENCE', [])])
        self.assertEqual({(r['model_receipts'][-1]['ask']['question'], r['model_receipts'][-1]['ask']['to']) for r in q['asked']['result']['runs'][:3]}, {(MAY_WAIVE, FINANCE)})
        self.assertEqual([self.runs(a) for a in q['answered']], [[(f'fee_waived_{n}', DONE, [f'waive-late-fee-{n}@1'])] for n in (201, 202, 203)])
        p = q['proposals'][0]
        self.assertEqual((q['after_two'], len(q['proposals']), p['kind'], p['to'], p['question'], p['truth'], p['support'], [a['entry'] for a in p['at']]),
                         ([], 1, 'REPEATED_ANSWER', FINANCE, MAY_WAIVE, 'TRUE', 3, [3, 4, 5]))
        self.assertEqual((q['proposals'], q['after_two'], q['proposals_after']),
                         (reader.proposals([(q['text'], q['head_after_three'])], 3), reader.proposals([(q['text'], q['heads_after_each_answer'][1])], 3), reader.proposals([(q['text'], q['head'])], 3)))
        self.assertEqual((q['row'], q['proposals_after']), (reader.row(p, 'waiver_answer_repeated'), q['proposals']))   # the proposal still stands at the end (limit L5)
        ask = q['question']['result']['runs'][0]
        self.assertEqual((ask['status'], ask['actions'], ask['model_receipts'][-1]['ask']['to'], q['after_question']['open_asks']),
                         ('WAITING', [OWN_WAIVERS], FINANCE, [SCOPE_W + '|own_waivers_approved']))
        self.assertEqual((self.runs(q['yes']), q['approved']), ([('own_waivers_approved', 'SUPPORTED_BY_EVIDENCE', [])], {'truth': 'TRUE', 'source': 'STAMP:' + FINANCE, 'final': True}))
        self.assertEqual((q['question']['entry'], q['yes']['entry'], q['handed_in'], q['loan_204']['entry']), (6, 7, {'entry': 8, 'pack': '229_own_waivers'}, 9))
        self.assertEqual((self.runs(q['loan_204']), q['after']['open_asks'], q['after']['budget']), ([('fee_waived_204', DONE, [OWN_204, WAIVE_204])], [], {'compute': 3, 'money': 0, 'attention': 0}))
        self.assertEqual([json.loads(line)['kind'] for line in q['text'].split('\n')[:-1]], ['header', 'pack', 'look', 'answer', 'answer', 'answer', 'event', 'answer', 'pack', 'look'])

    def test_answers_a_no_from_finance_is_a_decision_and_nothing_is_handed_in(self):
        n = self.answers['no']
        self.assertEqual((self.runs(n['answer']), n['approved'], n['handed_in']),
                         ([('own_waivers_approved', 'REFUSED', [])], {'truth': 'FALSE', 'source': 'STAMP:' + FINANCE, 'final': True}, {'entry': None, 'pack': '229_own_waivers'}))
        self.assertEqual((self.runs(n['look_after'])[3], n['after']['goals'][3], n['after']['budget'], n['after']['open_asks']),
                         (('own_waivers_approved', 'REFUSED', []), 'own_waivers_approved', self.answers['after_question']['budget'], []))

    def test_the_kept_text_of_each_sequence_states_the_sha256_of_the_code_it_was_written_under(self):
        sha = lambda rel: hashlib.sha256((ROOT / rel).read_bytes()).hexdigest()
        q = self.data['scenes']   # the record on disk
        texts = [(q['reader_lesson']['text'], False), (q['reader_one_way']['text'], False), (q['reader_one_way']['no_yes']['text'], False), (q['reader_answers']['text'], True)]
        for text, asks in texts:   # the first entry of a kept journal states the code it was written under: the kernel, the journal's file, and the file of each kind that is not the kernel's
            stated = json.loads(text.split('\n')[0])['stated']['code']
            self.assertEqual((stated['kernel.core'], stated['extensions.journal'], stated.get('extensions.asks')),
                             (sha('kernel/core.py'), sha('extensions/journal.py'), sha('extensions/asks.py') if asks else None))
            self.assertEqual(sorted(stated), ['extensions.asks', 'extensions.journal', 'kernel.core'] if asks else ['extensions.journal', 'kernel.core'])   # these files and no other (added when the confirming round was settled)
        # So a byte changed in kernel/core.py or extensions/journal.py gives another text in all three sequences, whatever the change is, and a byte changed in extensions/asks.py
        # gives another text in `reader_answers` alone. An edit version declares as moved the sequences whose kept texts state a file it changes, and no other: the base's check
        # S202 fails a declared move of a thing that did not move.

    def test_one_way_the_books_after_the_fourth_payout_with_the_change_and_without_it(self):   # added when the confirming round was settled
        q, n = self.way, self.way['no_yes']
        self.assertEqual((q['after_three']['budget']['compute'], q['yes']['result']['runs'][0]['cost'], q['loan_104']['result']['runs'][0]['cost'], n['loan_104']['result']['runs'][0]['cost']),
                         (15, {'compute': 5, 'money': 0, 'attention': 0}, ONE_COST, CHAIN_COST))   # fifteen tokens after three payouts; the checker's yes costs five; the one step two, the chain five
        self.assertEqual((q['after']['budget'], q['after']['providers']['local-provider']), ({'compute': 8, 'money': 2, 'attention': 0}, 2))    # with the change: 15 less the yes and the one step; two slots left at the desk's provider
        self.assertEqual((n['after']['budget'], n['after']['providers']['local-provider']), ({'compute': 10, 'money': 2, 'attention': 0}, 0))   # without it: 15 less the chain; no slot left at the desk's provider

    def test_c5_no_yes_no_pack_is_shown_by_two_recorded_branches_and_the_drivers_look_at_fits_by_none(self):
        same = lambda name, old, new: json.dumps(sequence(name, old, new), sort_keys=True) == json.dumps(self.data['scenes'][name], sort_keys=True)
        always = "return run.add('pack', {'pack': pack('226_payout_in_one')})['seq'] if yes_row['truth'] == 'TRUE' and not fits else None"
        self.assertEqual((self.way['fits'], self.way['handed_in']['entry'], self.way['no_yes']['handed_in']['entry']), ([], 7, None))
        self.assertTrue(same('reader_one_way', ' and not fits', ''))   # the driver's look at `fits` taken out: the same record, because the recorded way fits (limit L12)
        self.assertFalse(same('reader_one_way', always, always.split(' if ')[0]))   # the driver's look at the yes taken out: the branch `no_yes` would hand the pack in
        self.assertFalse(same('reader_answers', " if yes_row['truth'] == 'TRUE' else None", ''))   # and the branch `no` of the waiver desk would too
        self.assertTrue(same('reader_lesson', "if approved['truth'] == 'TRUE':", 'if True:'))   # `reader_lesson` has no branch without a yes: what it records is the order, entry 6 then entry 7

    def test_answers_what_the_parts_the_lab_had_say_of_the_same_record(self):
        x = self.answers['existing_parts']
        self.assertEqual([[(t['kind'], t.get('observations')) for t in told] for told in x['learner_fed_in_journal_order']],
                         [[], [], [], [('INVESTIGATE_GAP', None)], [('REUSE_COMPOSITION', 1)], [('REUSE_COMPOSITION', 1)], [('REUSE_COMPOSITION', 1)]])   # nothing of a question or an answer
        self.assertEqual([(r['entry'], r['predicate'], r['truth'], r['by']) for r in x['ledger_rows_of_the_answers']],
                         [(n, f'waiver_approved_{loan}', 'TRUE', FINANCE) for n, loan in ((3, 201), (4, 202), (5, 203))])   # the ledger holds each answer with its entry; nothing counts them


class Cases(unittest.TestCase):
    def test_the_four_cases_stand_in_the_table_with_their_packs(self):
        table = {c[0]: (c[3], c[4], c[5]) for c in CASES}
        area = 'Learning from past runs'
        self.assertEqual([table[i] for i in ('88_reminder_stops', '89_reminder_lesson_in', '90_payout_chain', '91_payout_in_one')],
                         [(C_DESK, True, area), (C_DESK + ['222_reminder_lesson'], True, area), (P_DESK, True, area), (P_DESK + ['226_payout_in_one'], True, area)])

    def test_what_one_look_makes_of_each_case(self):
        def one(names):
            s = State.from_packs([pack(n) for n in names])
            return [(r['goal'], r['status'], r['actions'], r['cost']) for r in Kernel(s).run_standing(execute=True)['runs']], s.budget['compute']
        self.assertEqual(one(C_DESK), ([('reminder_sent', 'STEP_STOPPED', [], {'compute': 0, 'money': 0, 'attention': 0}), ('reminder_lesson_approved', 'QUERY_EVIDENCE', [], None)], 12))
        self.assertEqual(one(C_DESK + ['222_reminder_lesson']), ([('reminder_sent', DONE, [PHONE], TOKEN)], 11))
        self.assertEqual(one(P_DESK), ([('payout_reconciled', DONE, CHAIN, CHAIN_COST), ('payout_way_approved', 'QUERY_EVIDENCE', [], None)], 25))
        self.assertEqual(one(P_DESK + ['226_payout_in_one']), ([('payout_reconciled', DONE, [ONE], ONE_COST)], 28))

    def test_the_packs_bring_no_kind_and_no_key_of_their_own(self):
        packs = [pack(n) for n in ALL_PACKS]
        self.assertEqual({m['action'] for p in packs for m in p.get('methods', [])}, {'simulate_fact', 'ask'})   # the two kinds the lab had: no kind of this version's own
        self.assertEqual(sorted(m['id'] for p in packs for m in p.get('methods', []) if m['action'] == 'ask'), sorted(ASKS + [OWN_WAIVERS]))
        self.assertEqual([k for p in packs for k in p if k not in ('schema', 'id', 'scope', 'goals', 'budget', 'preference', 'evidence', 'rules', 'methods', 'providers', 'grants', 'revoke_grants')], [])
        self.assertEqual([row.get('final') for p in packs for row in p.get('evidence', [])], [None] * 16)   # no pack carries a decision


class Limits(unittest.TestCase):
    """What this version does not hold, pinned as it is."""
    def test_l1_the_pack_door_takes_the_change_with_no_yes_on_the_books(self):
        run = collections(1)   # one stop: nothing repeated, no row is in, nobody said yes
        run.add('pack', {'pack': pack('222_reminder_lesson')})
        self.assertEqual((st(event(run, overdue(2))), run.state.fact('reminder_lesson_approved')['truth']), ([('reminder_sent', DONE, [PHONE])], 'UNKNOWN'))
        s = State.from_packs([pack(n) for n in P_DESK + ['226_payout_in_one']])   # and so does the kernel's own door: cases 89 and 91 load the change from the files
        self.assertEqual(st(Kernel(s).run_standing(execute=True)['runs']), [('payout_reconciled', DONE, [ONE])])
        for names, approval, read in ((C_DESK + ['222_reminder_lesson'], 'reminder_lesson_approved', 'reminder_stop_repeated'),   # the States of cases 89 and 91:
                                      (P_DESK + ['226_payout_in_one'], 'payout_way_approved', 'payout_chain_repeated')):          # no row read from the record, and no yes
            s = State.from_packs([pack(n) for n in names])
            Kernel(s).run_standing(execute=True)
            self.assertEqual((s.fact(approval)['truth'], s.fact(read)['truth']), ('UNKNOWN', 'UNKNOWN'), names)

    def test_l2_before_the_hand_in_a_further_repeat_or_the_weight_restated_makes_the_yes_unread_and_it_is_given_and_paid_again(self):
        run = collections(3)
        word = lambda: reader.row(reader.proposals(kept(run), 3)[0], 'reminder_stop_repeated')   # a driver that words the row at every read
        first = word()
        event(run, first)
        self.assertEqual(run.state.budget['compute'], 11)
        event(run, overdue(4))   # no pack was handed in, so the fourth day stops too: the proposal now rests on four entries, which is another digest
        second = word()
        self.assertNotEqual(second['version'], first['version'])
        again = event(run, second)   # the row worded again: the yes rested on the first one
        self.assertEqual((st(again), run.state.budget['compute']), ([('reminder_lesson_approved', DONE, [OWN_L])], 10))   # the desk's own yes, given and paid a second time
        run.add('pack', {'pack': pack('223_lesson_judged_weighty')})   # the weight restated: the yes rested on the answer `small`
        self.assertEqual(run.state.fact('reminder_lesson_approved')['truth'], 'UNKNOWN')
        self.assertEqual((st(look(run)), run.state.budget['compute']), ([('reminder_sent', 'STEP_STOPPED', []), ('reminder_lesson_approved', DONE, [CHECK_L])], 5))

    def test_l2_at_the_payout_desk_the_yes_that_a_further_repeat_makes_unread_is_lost_until_a_pack_restates_the_checkers_slots(self):
        run = payouts(3)
        word = lambda: reader.row(reader.proposals(kept(run), 3)[0], 'payout_chain_repeated')
        first = word()
        self.assertEqual((st(event(run, first)), run.state.budget['compute'], run.state.providers['independent-checker']), ([('payout_way_approved', DONE, [CHECK_P])], 10, 0))   # the checker's yes: five tokens, its one slot
        event(run, due(104))   # one more payout by the chain before any pack is handed in
        second = word()
        self.assertNotEqual(second['version'], first['version'])
        again = event(run, second)
        self.assertEqual((st(again), again[0]['stop_reasons'], run.state.fact('payout_way_approved')['truth'], run.state.budget['compute']),
                         ([('payout_way_approved', 'PROVIDER_REQUIRED', [])], ['METHOD_ABSENT', 'PROVIDER_REQUIRED'], 'UNKNOWN', 5))   # the yes no longer reads and is NOT given again: five tokens paid and no yes stands
        self.assertEqual(st(look(run)), [('payout_reconciled', 'SUPPORTED_BY_EVIDENCE', []), ('payout_way_approved', 'PROVIDER_REQUIRED', [])])   # nor at the next look: a driver that waits for the yes never hands in
        run.add('pack', {'pack': extra('t-reader-checker-back', providers={'independent-checker': 1})})   # until a pack restates the checker's slots
        self.assertEqual((st(look(run)), run.state.budget['compute']), ([('payout_reconciled', 'SUPPORTED_BY_EVIDENCE', []), ('payout_way_approved', DONE, [CHECK_P])], 0))   # then it is given and paid a second time

    def test_l3_a_loose_answer_row_gives_two_answers_and_the_desks_own_yes_approves_a_weighty_change(self):
        run = payouts(3)
        run.add('pack', {'pack': extra('t-reader-loose', evidence=[{'predicate': 'change_weight=small', 'truth': 'TRUE', 'verified': True, 'source': 'someone-else', 'version': 'x'}])})
        self.assertEqual(answers(run.state), {'small': 'TRUE', 'weighty': 'TRUE'})   # nothing refused the row, and nothing checks the axis after an entry
        yes = event(run, reader.row(reader.proposals(kept(run), 3)[0], 'payout_chain_repeated'))
        self.assertEqual((st(yes), yes[0]['cost'], said(run.state, 'payout_way_approved')[2][1]),
                         ([('payout_way_approved', DONE, [OWN_P])], TOKEN, {'predicate': 'change_weight=small', 'version': 'x'}))

    def test_l4_the_event_door_takes_a_row_under_the_readers_name_without_reading_the_record(self):
        run = collections(1)
        self.assertEqual(reader.proposals(kept(run), 2), [])   # one stop: nothing repeated
        made_up = {'predicate': 'reminder_stop_repeated', 'truth': 'TRUE', 'verified': True, 'source': reader.SOURCE, 'version': 'made-up'}
        self.assertEqual(st(event(run, made_up)), [('reminder_lesson_approved', DONE, [OWN_L])])   # the yes is given all the same
        with self.assertRaisesRegex(ValueError, 'The event door lets in only verified rows that are not decisions, from a checker the header names'):
            run.add('event', {'row': dict(made_up, source='someone-else'), 'execute': True})
        with self.assertRaisesRegex(ValueError, 'The event door lets in only verified rows that are not decisions, from a checker the header names'):
            run.add('event', {'row': dict(made_up, final=True), 'execute': True})

    def test_l7_the_one_step_makes_the_chains_last_fact_only(self):
        run = payouts(3)
        run.add('pack', {'pack': pack('226_payout_in_one')})
        event(run, due(104))
        self.assertEqual({f: run.state.fact(f)['truth'] for f in ('payee_checked', 'payout_paid', 'payout_reconciled')},
                         {'payee_checked': 'UNKNOWN', 'payout_paid': 'UNKNOWN', 'payout_reconciled': 'TRUE'})

    def test_l8_the_record_cannot_tell_one_runs_output_from_anothers(self):
        run = payouts(3)
        receipts = [run.detail[n]['runs'][0]['model_receipts'] for n in (3, 4, 5)]
        self.assertEqual((receipts[0], receipts[1]), (receipts[1], receipts[2]))   # three loans, the same three receipts byte for byte
        self.assertEqual(sorted(receipts[0][0]), ['action', 'method', 'model_effect', 'scope', 'sha256', 'status'])   # no input and no output stands on a receipt
        self.assertEqual(sorted(reader.proposals(kept(run), 3)[0]), ['as_one', 'at', 'goal', 'kind', 'paid', 'scope', 'status', 'steps', 'support'])   # the proposal rests on runs, steps and cost

    def test_l9_a_row_is_per_goal_and_scope_and_a_chain_is_told_by_its_steps_and_its_cost(self):
        run = payouts(2)   # two chains; then the budget is restated (no price moves), and a third chain
        run.add('pack', {'pack': extra('t-reader-level', budget={'compute': 40})})
        event(run, due(103))
        self.assertEqual([(p['support'], p['scope'], p['goal']) for p in reader.proposals(kept(run), 3)], [(3, SCOPE_P, 'payout_reconciled')])
        other = started(P_DESK, 'two-scopes')   # one chain in one scope, then two in another: the same goal and the same steps, and two rows
        look(other)
        other.add('pack', {'pack': extra('t-reader-other-scope', scope='lendco/payouts-north', evidence=[due(201)])})
        look(other)
        event(other, due(202))
        self.assertEqual([r['scope'] for r in R.ledger(kept(other)) if r['what'] == 'ran' and r['actions'] == CHAIN], [SCOPE_P, 'lendco/payouts-north', 'lendco/payouts-north'])
        self.assertEqual(([(p['support'], p['scope']) for p in reader.proposals(kept(other), 2)], reader.proposals(kept(other), 3)), ([(2, 'lendco/payouts-north')], []))
        logged = extra('t-reader-two-goals', goals=['reminder_sent', 'reminder_logged'],   # two goals that stop at the same step for the same reason are two proposals
                       rules=[{'id': 'R-LOGGED@t', 'head': 'reminder_logged', 'branches': [['reminder_sent']], 'approved': True, 'source': 'fixture/reviewed-domain-theory'}])
        both = started(['220_collections_desk', logged], 'two-goals')
        look(both)
        event(both, overdue(2))
        self.assertEqual([(p['goal'], p['step'], p['support'], [a['run'][-3:] for a in p['at']]) for p in reader.proposals(kept(both), 2)],
                         [('reminder_sent', REMIND, 2, ['3.0', '4.0']), ('reminder_logged', REMIND, 2, ['3.1', '4.1'])])

    def test_l10_the_reader_does_not_replay_what_it_reads(self):
        run = collections(3)

        def reworded(entries):   # a forger rewords the three stops
            for e in entries[3:]:
                e['result']['briefs'][0]['stopped']['reason'] = 'Handler refused: the borrower asked not to be called'
        forged = rechained(run, 3, reworded)
        self.assertEqual([(p['reason'], p['support']) for p in reader.proposals(forged, 3)], [('Handler refused: the borrower asked not to be called', 3)])
        with self.assertRaisesRegex(ValueError, 'The journal does not replay at entry 3: the result differs'):   # only a replay refuses it
            J.replay(J.parse(forged[0][0]), forged[0][1])

    def test_l11_no_check_holds_what_a_sequence_keeps_beside_its_runs_so_one_made_again_with_its_seal_passes_the_base_checks(self):
        spec = importlib.util.spec_from_file_location('independent_verify_for_the_reader', ROOT / 'qa' / 'independent_verify.py')
        v = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(v)
        v.delivered_rows = lambda data, root: []   # the check modules that versions deliver are not run: what one of them says of this forgery is that version's (and this version brings none)

        def failing(data):   # the checks of the base that fail: the built-in ones (numbers below 60) and those of the add-on base (200 to 219), without S202
            base = lambda n: n < 60 or (200 <= n <= 219 and n != 202)   # S202 is the pin: once a later version has pinned this version's record, it shows that a pinned sequence was changed
            numbers = [(t['id'], re.match(r'S(\d+)', t['id'])) for t in v.inspect(json.loads(json.dumps(data)))['checks'] if not t['pass']]
            return sorted(id for id, n in numbers if n and base(int(n.group(1))))
        forged = json.loads((ROOT / 'results' / 'actual_run_records.json').read_text())
        lesson, way, asked = (forged['scenes'][name] for name in ('reader_lesson', 'reader_one_way', 'reader_answers'))
        lesson['proposals'][0].update(support=4, reason='another reason')   # the proposals
        lesson['proposals_after'] = lesson['proposals']
        way['proposals'][0].update(paid={'compute': 9, 'money': 9, 'attention': 9})
        way['fits'] = ['it is dearer on compute']
        asked['proposals'][0].update(support=30, truth='FALSE')
        lesson['row']['version'] = 'made-up'                                # the row
        lesson['approved']['source'] = 'LOCAL_MODEL:' + CHECK_L             # who gave the yes: the independent checker is said to have approved the lesson
        asked['no']['approved']['truth'] = 'TRUE'                           # finance's no reads as a yes
        lesson['yes']['entry'], lesson['handed_in']['entry'] = 7, 6         # the entry numbers: the pack stands before the yes
        way['no_yes']['handed_in']['entry'] = 7                             # and a pack is handed in where no yes was given
        lesson['text'], lesson['head']['length'] = lesson['text'] + 'not an entry\n', 99   # the kept text and its head
        for name in ('reader_lesson', 'reader_one_way', 'reader_answers'):   # the seal no longer fits (the base's check S201 holds a sequence to it), so the forger makes it again: a checksum, not a secret
            self.assertNotEqual(forged['added']['scenes'][name], digest(forged['scenes'][name]))
            forged['added']['scenes'][name] = digest(forged['scenes'][name])
        self.assertEqual(failing(forged), [])
        for name in ('reader_lesson', 'reader_one_way', 'reader_answers'):   # caught only by making the record again
            self.assertNotEqual(json.dumps(forged['scenes'][name], sort_keys=True), json.dumps(sequence(name), sort_keys=True))

    def test_l14_a_verified_row_on_the_approval_itself_reads_true_with_no_step_no_receipt_and_no_answer(self):
        yes = lambda fact, source: {'predicate': fact, 'truth': 'TRUE', 'verified': True, 'source': source, 'version': 'x'}   # a row on the approval itself
        door = 'The event door lets in only verified rows that are not decisions, from a checker the header names'
        for source in (reader.SOURCE, BOOK):   # the two names the journal's header lists: the reader's own, which this version adds as a checker, and the loan book's
            run = waivers()
            asked = event(run, reader.row(reader.proposals(kept(run), 3)[0], 'waiver_answer_repeated'))   # finance's question about the change is out
            books = dict(run.state.budget), dict(run.state.providers), sorted(open_asks(run.state))
            e = run.add('event', {'row': yes('own_waivers_approved', source), 'execute': True})
            r = run.detail[e['seq']]['runs']
            self.assertEqual((e['result']['status'], st(r), r[0]['model_receipts'], r[0]['cost']), ('RECONCILED', [('own_waivers_approved', 'SUPPORTED_BY_EVIDENCE', [])], [], FREE))
            row = run.state.fact('own_waivers_approved')
            self.assertEqual((row['truth'], row['source'], row.get('final'), row.get('answers')), ('TRUE', source, None, None))   # the approval reads TRUE under that name: no step, no receipt, no answer
            self.assertEqual((dict(run.state.budget), dict(run.state.providers), sorted(open_asks(run.state))), books)       # nothing was paid, and the question to finance is still out
            run.add('pack', {'pack': pack('229_own_waivers')})   # the driver's rule reads TRUE and hands the rule in
            self.assertEqual(st(look(run)), [('fee_waived_204', DONE, [OWN_204, WAIVE_204])])   # loan 204 is waived on the desk's own yes
            no = run.add('answer', {'receipt': asked[0]['model_receipts'][-1], 'truth': 'FALSE', 'source': FINANCE, 'execute': True})   # then finance answers: no
            row = run.state.fact('own_waivers_approved')
            self.assertEqual((no['result']['status'], row['truth'], row['source'], row['final']), ('RECONCILED', 'FALSE', 'STAMP:' + FINANCE, True))   # the no is taken and stands
            self.assertEqual((run.state.fact('fee_waived_204')['truth'], OWN_204 in run.state.methods, 'action:' + OWN_204 in run.state.grants, st(look(run))),
                             ('TRUE', True, True, [('fee_waived_204', 'SUPPORTED_BY_EVIDENCE', [])]))   # and takes nothing back: the fee stays waived and the rule stays in force
        run = started(['228_waiver_desk'], 'waivers', kinds=('simulate_fact', 'ask'))   # the same row before any row of the reader and before any question
        run.add('event', {'row': yes('own_waivers_approved', reader.SOURCE), 'execute': True})
        self.assertEqual((reader.proposals(kept(run), 2), run.state.fact('own_waivers_approved')['truth'], st(look(run))[3]), ([], 'TRUE', ('own_waivers_approved', 'SUPPORTED_BY_EVIDENCE', [])))
        self.assertEqual([r['predicate'] for r in R.ledger(kept(run)) if r['what'] == 'asked'], [f'waiver_approved_{n}' for n in (201, 202, 203)])   # finance is never asked about the change
        run = payouts(3)   # the payout desk, the independent checker away and four tokens left: no step can give the yes (C4)
        run.add('pack', {'pack': pack('227_checker_away')})
        run.add('pack', {'pack': extra('t-reader-few-tokens', budget={'compute': 4})})
        run.add('event', {'row': yes('payout_way_approved', reader.SOURCE), 'execute': True})
        row = run.state.fact('payout_way_approved')
        self.assertEqual((row['truth'], row['source'], row.get('depends_on'), run.state.budget['compute'], run.state.providers['independent-checker']), ('TRUE', reader.SOURCE, None, 4, 0))
        run = collections(1)   # carried by a pack: the pack door asks for no name at all
        run.add('pack', {'pack': extra('t-reader-yes-in-a-pack', evidence=[yes('reminder_lesson_approved', 'someone-else')])})
        self.assertEqual((run.state.fact('reminder_lesson_approved')['truth'], run.state.fact('reminder_lesson_approved')['source'], st(look(run))[1], run.state.budget['compute']),
                         ('TRUE', 'someone-else', ('reminder_lesson_approved', 'SUPPORTED_BY_EVIDENCE', []), 12))
        run = waivers()   # what the event door does hold: a name the header does not list, a decision, a row that is not verified
        for row in (yes('own_waivers_approved', 'system:lendco/waivers'), yes('own_waivers_approved', FINANCE), yes('own_waivers_approved', 'STAMP:' + FINANCE),
                    dict(yes('own_waivers_approved', reader.SOURCE), final=True), dict(yes('own_waivers_approved', reader.SOURCE), verified=False)):
            with self.assertRaisesRegex(ValueError, exactly(door)):
                run.add('event', {'row': row, 'execute': True})
        with self.assertRaisesRegex(ValueError, exactly(door)):   # and with no checker named in the header the reader's name is refused too
            J.start(['simulate_fact', 'ask'], [], name='no-checker').add('event', {'row': yes('own_waivers_approved', reader.SOURCE), 'execute': True})
        self.assertEqual(run.state.fact('own_waivers_approved')['truth'], 'UNKNOWN')

    def test_l14_a_pack_may_carry_a_decision_on_the_approval(self):   # added when the confirming round was settled
        decision = lambda source: extra('t-reader-decision-in-a-pack', evidence=[{'predicate': 'own_waivers_approved', 'truth': 'TRUE', 'verified': True, 'final': True, 'source': source, 'version': 'x'}])
        read = lambda run: tuple(run.state.fact('own_waivers_approved').get(k) for k in ('truth', 'source', 'final', 'answers'))

        def asked():   # the waiver desk with finance's question about the change out: the run, and the receipt of that question
            run = waivers()
            return run, event(run, reader.row(reader.proposals(kept(run), 3)[0], 'waiver_answer_repeated'))[0]['model_receipts'][-1]
        for source in ('system:lendco/waivers', 'someone-else', FINANCE, 'STAMP:' + FINANCE):   # the desk's own name, any name, finance's name, the form of finance's stamp
            run, receipt = asked()
            books = dict(run.state.budget), dict(run.state.providers)
            self.assertEqual(sorted(open_asks(run.state)), [SCOPE_W + '|own_waivers_approved'])
            run.add('pack', {'pack': decision(source)})   # the pack door takes a decision, under any name
            self.assertEqual((read(run), sorted(open_asks(run.state)), (dict(run.state.budget), dict(run.state.providers)) == books), (('TRUE', source, True, None), [], True), source)   # the approval is decided under that name, and finance's question is closed without finance
            for truth in ('FALSE', 'TRUE'):   # finance's answer, a no or a yes, is then refused at the answer door: it stands nowhere
                with self.assertRaisesRegex(ValueError, exactly('No open ask matches this receipt')):
                    run.add('answer', {'receipt': receipt, 'truth': truth, 'source': FINANCE, 'execute': True})
            self.assertEqual(([e['kind'] for e in run.journal], [r['predicate'] for r in R.ledger(kept(run)) if r['what'] == 'decided']),
                             (['header', 'pack', 'look', 'answer', 'answer', 'answer', 'event', 'pack'], [f'waiver_approved_{n}' for n in (201, 202, 203)]), source)   # the ledger holds no decision on the approval: its rows name nobody who gave this yes
            J.replay(J.parse(kept(run)[0][0]), kept(run)[0][1])   # and the journal replays
            run.add('pack', {'pack': pack('229_own_waivers')})   # the driver's rule reads TRUE and hands the rule in
            self.assertEqual(st(look(run)), [('fee_waived_204', DONE, [OWN_204, WAIVE_204])], source)
        run, receipt = asked()   # after finance's no
        run.add('answer', {'receipt': receipt, 'truth': 'FALSE', 'source': FINANCE, 'execute': True})
        no = ('FALSE', 'STAMP:' + FINANCE, True, receipt['sha256'])
        self.assertEqual(read(run), no)
        e = run.add('event', {'row': {'predicate': 'own_waivers_approved', 'truth': 'TRUE', 'verified': True, 'source': reader.SOURCE, 'version': 'x'}, 'execute': True})
        self.assertEqual((e['result']['status'], read(run)), ('DECISION_STANDS', no))   # what does hold: an ordinary row under the reader's name is turned away at the event door
        run.add('pack', {'pack': extra('t-reader-row-in-a-pack', evidence=[{'predicate': 'own_waivers_approved', 'truth': 'TRUE', 'verified': True, 'source': 'someone-else', 'version': 'x'}])})
        self.assertEqual(read(run), no)   # and an ordinary row carried by a pack changes nothing either: the no stands
        run.add('pack', {'pack': decision('someone-else')})
        self.assertEqual(read(run), ('TRUE', 'someone-else', True, None))   # a decision carried by a pack replaces finance's no: the driver's rule would read TRUE and hand the rule in
        J.replay(J.parse(kept(run)[0][0]), kept(run)[0][1])   # this journal replays too

    def test_l16_seven_landings_under_goals_and_steps_of_their_own_give_no_proposal(self):   # added when the confirming round was settled: the limit the first real use of the lab met
        names = ['journal', 'numbers', 'time', 'pages', 'refusals', 'ordered', 'queue']   # seven versions landed one after another, each by a test loop and then a ship
        step = lambda id, effect, requires: {'id': id, 'effect': effect, 'requires': requires, 'provider': 'local-provider', 'grant': 'action:' + id, 'cost': TOKEN, 'action': 'simulate_fact', 'approved': True}
        books = dict(budget={'compute': 20, 'money': 0, 'attention': 0}, preference=['compute', 'money', 'attention'], providers={'local-provider': 20})
        candidate = lambda fact, version: {'predicate': fact, 'truth': 'TRUE', 'verified': True, 'source': BOOK, 'version': version}
        shared = [step('loop@t', 'tested', ['candidate']), step('ship@t', 'landed', ['candidate', 'tested'])]
        run = started([], 'train')   # as a user writes it: every landing is a goal of its own, with a loop step and a ship step of its own
        for i, name in enumerate(names):
            ways = [step(f'loop-{name}@t', f'tested_{name}', [f'candidate_{name}']), step(f'ship-{name}@t', f'landed_{name}', [f'candidate_{name}', f'tested_{name}'])]
            run.add('pack', {'pack': extra(f't-reader-landing-{name}', goals=[f'landed_{n}' for n in names[:i + 1]], methods=ways, grants=[m['grant'] for m in ways],
                                           evidence=[candidate(f'candidate_{name}', 'built')], **(dict(books, scope='lab/release-train') if not i else {}))})
            self.assertEqual([(r['goal'], r['status'], r['actions']) for r in look(run) if r['actions']], [(f'landed_{name}', DONE, [f'loop-{name}@t', f'ship-{name}@t'])])
        rows = [r for r in R.ledger(kept(run)) if r['what'] == 'ran' and r['receipts']]
        self.assertEqual((len(rows), len({r['goal'] for r in rows}), {r['scope'] for r in rows}, {len(r['actions']) for r in rows}), (7, 7, {'lab/release-train'}, {2}))   # seven runs of two steps in one scope: seven goals, seven chains
        self.assertEqual((reader.proposals(kept(run), 3), reader.proposals(kept(run), 2)), ([], []))   # seven rows of one run each: nothing repeated, whatever the number
        learner = Learner(True)
        self.assertEqual([learner.learn(r)[0]['observations'] for n in sorted(run.detail) for r in run.detail[n]['runs'] if r['actions']], [1] * 7)   # the Learner the lab had says "seen once" seven times, for the same reason
        one = started([extra('t-reader-one-goal', scope='lab/release-train', goals=['landed'], methods=shared, grants=[m['grant'] for m in shared], evidence=[candidate('candidate', names[0])], **books)], 'train-one-goal')
        look(one)   # the same seven landings written as ONE goal run on a new input each time, by one shared pair of steps
        for name in names[1:]:
            event(one, candidate('candidate', name))
        self.assertEqual([(p['kind'], p['steps'], p['support'], p['as_one']) for p in reader.proposals(kept(one), 3)],
                         [('REPEATED_CHAIN', ['loop@t', 'ship@t'], 7, {'effect': 'landed', 'requires': ['candidate']})])   # written so they are one row of seven: what the lab lacks is a way to say that two steps are the same step
        per = started([], 'train-scopes')   # one scope a version, the same goal and the shared steps: seven scopes are seven rows of one too (limit L9)
        for i, name in enumerate(names):
            first = dict(books, goals=['landed'], methods=shared, grants=[m['grant'] for m in shared]) if not i else {}
            per.add('pack', {'pack': extra(f't-reader-scope-{name}', scope=f'lab/release-train/{name}', evidence=[candidate('candidate', name)], **first)})
            self.assertEqual(st(look(per)), [('landed', DONE, ['loop@t', 'ship@t'])], name)
        self.assertEqual((len({r['scope'] for r in R.ledger(kept(per)) if r['what'] == 'ran' and r['receipts']}), reader.proposals(kept(per), 2)), (7, []))

    def test_l15_a_forged_look_entry_is_refused_in_the_adapters_words_or_in_pythons_and_no_journal_at_all_is_read_as_nothing(self):
        run = payouts(3)

        def forged(change):   # the brief of the newest run changed, and the journal chained again under a head of its own: whole and in order
            def changed(entries):
                change(entries[5]['result']['briefs'][0])
            return rechained(run, 5, changed)
        with self.assertRaisesRegex(ValueError, '^Entry 5 of journal [0-9a-f]{12} does not hold what the record reads from it$'):   # the adapter's words: its ledger could not read the entry
            reader.proposals(forged(lambda b: b.pop('goal')), 3)
        for cost in ('abc', ['abc']):   # a cost that is no object: Python's own words, which the reader does not reword
            with self.assertRaisesRegex(ValueError, '^dictionary update sequence element #0 has length [13]; 2 is required$'):
                reader.proposals(forged(lambda b: b.update(cost=cost)), 3)
        for cost in (None, 5):          # a cost that is nothing or a number: the reader's words
            with self.assertRaisesRegex(ValueError, exactly(reader.NOT_READ)):
                reader.proposals(forged(lambda b: b.update(cost=cost)), 3)
        self.assertEqual([p['paid'] for p in reader.proposals(forged(lambda b: b.update(cost=['ab', 'cd'])), 3)], [{'a': 'b', 'c': 'd'}])   # and a cost that reads as pairs is read (limit L10)
        self.assertEqual((reader.proposals([], 3), R.ledger([])), ([], []))   # no journal at all is no refusal: nothing repeated
        # Added when the confirming round was settled. The entry forged above, entry 5, is an EVENT entry: it holds the newest run of the row. The look entry (entry 3) and the
        # event entry before it (entry 4) hold the older runs of the row, and for them the words are the adapter's or there is no refusal at all:
        self.assertEqual([e['kind'] for e in run.journal[3:]], ['look', 'event', 'event'])
        whole = reader.proposals(kept(run), 3)

        def older(n, change):   # the brief of an older run of the row changed, in the look entry or in the first event entry
            def changed(entries):
                change(entries[n]['result']['briefs'][0])
            return rechained(run, n, changed)
        for n in (3, 4):
            with self.assertRaisesRegex(ValueError, f'^Entry {n} of journal [0-9a-f]{{12}} does not hold what the record reads from it$'):   # a run without its goal: the adapter's words, for a look entry as for an event entry
                reader.proposals(older(n, lambda b: b.pop('goal')), 3)
            for cost in ('abc', ['abc'], None, 5, ['ab', 'cd'], {'compute': 9, 'money': 9, 'attention': 9}):   # a cost changed in an older run is not read at all: `paid` is the cost of the newest run alone
                got = reader.proposals(older(n, lambda b: b.update(cost=cost)), 3)
                self.assertEqual([dict(p, at=[a['entry'] for a in p['at']]) for p in got], [dict(p, at=[a['entry'] for a in p['at']]) for p in whole], (n, cost))
        self.assertEqual([p['paid'] for p in reader.proposals(forged(lambda b: b.update(cost={'compute': 9, 'money': 9, 'attention': 9})), 3)], [{'compute': 9, 'money': 9, 'attention': 9}])   # and another cost in the newest run is read as what each run paid (limit L10)

if __name__ == '__main__':
    unittest.main()
