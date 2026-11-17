"""Recorded sequence of 0.21.0-doors: which source may state which fact, and a stop for want of a place, as the program's own records
showed them (needs N1, N2 and N3 of the version; ruling R35 of the program). scene(lab) -> the dict kept in the record under scenes.doors.
Every pack loaded here is a scenario file. Nothing real is called: the rows and the answers are written here, as the program's users wrote
theirs into the journals the judge cited (examples 1, 2 and 5 of the program, and the journals of its runners).

Each session is one journal. A session made of the same moves is kept twice: `before`, a journal started as every journal was started until
this version (its header holds no door), and `after`, the same moves in a journal started with door='plan'. A move is one thing handed to
the journal's doors; a move that names a receipt (a check, an answer) names the one the session has out at that moment, so the same move
can be made on both journals. A step is {move, entry, result} for a move the door took and {move, refused} for a move it refused (nothing
is sealed then).

  refund_desk_1   example 1 (c0bc): the loan book states finance's yes before it states that the refund is due.
  refund_desk_2   example 1 (c345): the refund is due and finance is asked; the loan book states finance's yes; finance answers no.
  refund_desk_3   example 1 (b403): the refund is due; the payment bounced, so it is not; the loan book states that the refund was sent.
  payouts_1       example 5 (ea6c): a payout on loan 101; the loan book states the payout reconciled and paid; payouts on loans 102 and 103.
  payouts_2       example 5 (43e9): payouts on loans 101 to 103; the owner is asked about a cheaper way; the loan book states the owner's
                  yes; a payout on loan 104; the owner answers no; a payout on loan 105.
  batch_1         example 2 (c5b3): the reconciliation ledger states the batch reconciled with no work out; the posting log checks
                  whatever posting is out; one look more.
  batch_2         example 2 (23ae): the posting log states the batch posted with no work out; the reconciliation ledger checks
                  whatever reconciliation is out; one look more.
  batch_3         example 2 (ecd6): a look; the posting log states the batch posted with no work out; a dry look; the
                  reconciliation ledger checks the reconciliation that is out.
  batch_4         example 2 (1071): a look; the reconciliation ledger fails two tries ("the run timed out"), so the script has
                  no place left; the posting log states the batch reconciled.
  file_review     the runners' journals (runner-1): the review of a loan file is five hand-overs to one reviewer with one place;
                  a look, and a dry look.
  proposals       what the learn feature (extensions/learn.py) says of the records: `before` (the ten before-sessions) and `after`
                  (the ten after-sessions), each read together with least 2.
  stops           the six runs that stopped for want of a place (file_review entries 2 and 3, before and after; batch_4 entry 4,
                  before and after), each read with what the journal keeps and with the parts the lab had: the brief the journal
                  keeps (under the plan door it names the doers that are short, `short`), the record adapter's ledger row, the
                  shortfall of extensions/numbers_lint.py, what a Learner says, and the decision-provenance rows of
                  extensions/queue_provenance.py, handed the run as the journal replays it and the books before the entry."""
LOOKS = 62   # every dict that holds a list under `runs`: one for every move a door took (looks, rows, answers); a refused move has none
RUNS = 62    # the runs in them: one in each, since every look and row here looks at one goal

LOAN_BOOK, FINANCE, OWNER, READER = 'system:lendco/loan-book', 'system:lendco/finance', 'owner:lendco', 'adapter:reader'
RECON, POSTING, NOTES = 'checker:reconciliation-ledger', 'checker:posting-log', 'checker:review-notes'
DESKS = ['simulate_fact', 'ask']               # the kinds of the refund and payout desks (examples 1 and 5)
BATCH = ['simulate_fact', 'handoff']           # the kinds of the batch (example 2)
AGENT = ['ask', 'handoff', 'simulate_fact']    # the kinds of a runner's journal


def row(fact, truth, source, version, **more):
    return dict({'predicate': fact, 'truth': truth, 'verified': True, 'source': source, 'version': version}, **more)


def refund_desk_1(do, out, asked):
    do('event', {'row': row('refund_approved_by_finance', 'TRUE', LOAN_BOOK, 'stated in the loan book'), 'execute': True}, "the loan book states finance's yes")
    do('event', {'row': row('refund_due', 'TRUE', LOAN_BOOK, 'loan L-17, instalment 7'), 'execute': True}, 'the loan book states the refund is due')


def refund_desk_2(do, out, asked):
    do('event', {'row': row('refund_due', 'TRUE', LOAN_BOOK, 'loan L-17, instalment 7'), 'execute': True}, 'the loan book states the refund is due')
    do('event', {'row': row('refund_approved_by_finance', 'TRUE', LOAN_BOOK, 'stated in the loan book'), 'execute': True}, "the loan book states finance's yes")
    do('answer', {'receipt': asked('refund_approved_by_finance'), 'truth': 'FALSE', 'source': FINANCE, 'execute': True}, 'finance answers no')


def refund_desk_3(do, out, asked):
    do('event', {'row': row('refund_due', 'TRUE', LOAN_BOOK, 'loan L-17, instalment 7'), 'execute': True}, 'the loan book states the refund is due')
    do('event', {'row': row('refund_due', 'FALSE', LOAN_BOOK, 'loan L-17, instalment 7, bounced', why='the payment bounced'), 'execute': True},
       'the loan book states the refund is not due: the payment bounced')
    do('event', {'row': row('refund_sent', 'TRUE', LOAN_BOOK, 'stated in the loan book'), 'execute': True}, 'the loan book states the refund was sent')


def payouts_1(do, out, asked):
    do('event', {'row': row('payout_due', 'TRUE', LOAN_BOOK, 'loan 101'), 'execute': True}, 'a payout is due on loan 101')
    do('event', {'row': row('payout_reconciled', 'TRUE', LOAN_BOOK, 'stated in the loan book'), 'execute': True}, 'the loan book states the payout reconciled')
    do('event', {'row': row('payout_paid', 'TRUE', LOAN_BOOK, 'stated in the loan book'), 'execute': True}, 'the loan book states the payout paid')
    do('event', {'row': row('payout_due', 'TRUE', LOAN_BOOK, 'loan 102'), 'execute': True}, 'a payout is due on loan 102')
    do('event', {'row': row('payout_due', 'TRUE', LOAN_BOOK, 'loan 103'), 'execute': True}, 'a payout is due on loan 103')


def payouts_2(do, out, asked):
    for loan in ('101', '102', '103'):
        do('event', {'row': row('payout_due', 'TRUE', LOAN_BOOK, 'loan ' + loan), 'execute': True}, 'a payout is due on loan ' + loan)
    do('pack', {'pack': '317_door_change_approval'}, 'the owner is to be asked about a cheaper way')
    do('event', {'row': row('payout_chain_repeated', 'TRUE', READER, 'the three steps ran for loans 101, 102 and 103'), 'execute': True}, 'the reader states the steps repeat')
    do('event', {'row': row('cheaper_way_approved', 'TRUE', LOAN_BOOK, 'stated in the loan book'), 'execute': True}, "the loan book states the owner's yes")
    do('event', {'row': row('payout_due', 'TRUE', LOAN_BOOK, 'loan 104'), 'execute': True}, 'a payout is due on loan 104')
    do('answer', {'receipt': asked('cheaper_way_approved'), 'truth': 'FALSE', 'source': OWNER, 'execute': True}, 'the owner answers no')
    do('event', {'row': row('payout_due', 'TRUE', LOAN_BOOK, 'loan 105'), 'execute': True}, 'a payout is due on loan 105')


def check(fact, truth, source, why=None):   # a checker's row on whatever try of the fact is out (none: it names no receipt)
    def made(out):
        return row(fact, truth, source, 'check of ' + str(out(fact))[:16], checks=out(fact), **({'why': why} if why else {}))
    return made


def batch_1(do, out, asked):
    do('event', {'row': row('batch_reconciled', 'TRUE', RECON, 'stated by the ledger'), 'execute': True}, 'the reconciliation ledger states the batch reconciled')
    do('event', {'row': check('batch_posted', 'TRUE', POSTING)(out), 'execute': True}, 'the posting log checks the posting that is out')
    do('look', {'execute': True}, 'one look more')


def batch_2(do, out, asked):
    do('event', {'row': row('batch_posted', 'TRUE', POSTING, 'stated by the log'), 'execute': True}, 'the posting log states the batch posted')
    do('event', {'row': check('batch_reconciled', 'TRUE', RECON)(out), 'execute': True}, 'the reconciliation ledger checks the reconciliation that is out')
    do('look', {'execute': True}, 'one look more')


def batch_3(do, out, asked):
    do('look', {'execute': True}, 'a look')
    do('event', {'row': row('batch_posted', 'TRUE', POSTING, 'stated by the log'), 'execute': True}, 'the posting log states the batch posted')
    do('look', {'execute': False}, 'a dry look')
    do('event', {'row': check('batch_reconciled', 'TRUE', RECON)(out), 'execute': True}, 'the reconciliation ledger checks the reconciliation that is out')


def batch_4(do, out, asked):
    do('look', {'execute': True}, 'a look')
    do('event', {'row': check('batch_reconciled', 'FALSE', RECON, 'the run timed out')(out), 'execute': True}, 'the reconciliation ledger fails try 1')
    do('event', {'row': check('batch_reconciled', 'FALSE', RECON, 'the run timed out')(out), 'execute': True}, 'the reconciliation ledger fails try 2')
    do('event', {'row': row('batch_reconciled', 'TRUE', POSTING, 'stated by the log'), 'execute': True}, 'the posting log states the batch reconciled')


def file_review(do, out, asked):
    do('look', {'execute': True}, 'a look')
    do('look', {'execute': False}, 'a dry look')


SESSIONS = [   # name, the session's moves, its kinds, the checkers its header names, its packs
    ('refund_desk_1', refund_desk_1, DESKS, [LOAN_BOOK], ['315_door_refund_desk']),
    ('refund_desk_2', refund_desk_2, DESKS, [LOAN_BOOK], ['315_door_refund_desk']),
    ('refund_desk_3', refund_desk_3, DESKS, [LOAN_BOOK], ['315_door_refund_desk']),
    ('payouts_1', payouts_1, DESKS, [LOAN_BOOK, READER], ['316_door_payout_desk']),
    ('payouts_2', payouts_2, DESKS, [LOAN_BOOK, READER], ['316_door_payout_desk']),
    ('batch_1', batch_1, BATCH, [RECON, POSTING], ['318_door_batch_landing']),
    ('batch_2', batch_2, BATCH, [RECON, POSTING], ['318_door_batch_landing']),
    ('batch_3', batch_3, BATCH, [RECON, POSTING], ['318_door_batch_landing']),
    ('batch_4', batch_4, BATCH, [RECON, POSTING], ['318_door_batch_landing']),
    ('file_review', file_review, AGENT, [NOTES], ['319_door_file_review'])]


def session(J, pack, name, moves, kinds, checkers, packs, door=''):
    """One journal: the packs, then the moves. Returns {name, door, steps, text, head, budget, providers}."""
    run = J.start(kinds, checkers, name=name + ('-' + door if door else ''), **({'door': door} if door else {}))
    for n in packs:
        run.add('pack', {'pack': pack(n)})
    steps = []

    def do(kind, body, move):
        if kind == 'pack':
            body = {'pack': pack(body['pack'])}
        try:
            e = run.add(kind, body)
        except ValueError as why:
            steps.append({'move': move, 'refused': str(why)})
            return
        if kind != 'pack':
            steps.append({'move': move, 'entry': e['seq'], 'result': run.detail[e['seq']]})

    def out(fact):   # the receipt of the try out on the fact in the State's scope, as the hand-over kind keeps it in its books
        entry = run.state.active_work.get('handoff', {}).get(run.state.key(fact))
        return entry['receipt'] if entry else None

    def asked(fact):   # the receipt of the question out on the fact, as the ask kind keeps it in its books
        entry = run.state.active_work.get('ask', {}).get(run.state.key(fact))
        return entry['issued'] if entry else None
    moves(do, out, asked)
    keep = J.Keep()
    head = J.save(run, keep)
    return {'name': name, 'door': door or None, 'steps': steps, 'text': keep.text, 'head': head,
            'budget': dict(run.state.budget), 'providers': dict(run.state.providers)}


def stop(J, R, Q, Learner, shortfall, kept, at):
    """One run that stopped for want of a place, read from what the journal keeps (the brief, the ledger row) and with the parts the lab
    had: the budget's shortfall, a Learner, and the decision-provenance rows of the run as the journal replays it, with the books before
    the entry."""
    text, head = kept['text'], kept['head']
    entries = J.parse(text)
    before = J.replay(entries[:at], {'length': at, 'sha256': entries[at - 1]['sha256']})
    books = Q.books(before.state)
    runs = J.replay(entries[:at + 1], {'length': at + 1, 'sha256': entries[at]['sha256']}).detail[at]['runs']
    left = dict(before.state.budget)
    return {'session': kept['name'], 'door': kept['door'], 'entry': at, 'brief': entries[at]['result']['briefs'],
            'ledger': [r for r in R.ledger([(text, head)]) if r['what'] == 'ran' and r['entry'] == at],
            'shortfall': [shortfall(r, left) for r in runs], 'learner': [Learner(True).learn(r) for r in runs],
            'decisions': Q.decisions(runs, books)}


def scene(lab):
    from extensions import journal as J
    from extensions import journal_record as R
    from extensions import learn
    from extensions import queue_provenance as Q
    from extensions.numbers_lint import shortfall
    pack, Learner = lab['pack'], lab['Learner']
    before = {name: session(J, pack, name, moves, kinds, checkers, packs) for name, moves, kinds, checkers, packs in SESSIONS}
    after = {name: session(J, pack, name, moves, kinds, checkers, packs, door='plan') for name, moves, kinds, checkers, packs in SESSIONS}
    records = lambda kept: [[(k['text'], k['head'])] for k in kept.values()]
    stops = [stop(J, R, Q, Learner, shortfall, side['file_review'], at) for side in (before, after) for at in (2, 3)]
    stops += [stop(J, R, Q, Learner, shortfall, side['batch_4'], 4) for side in (before, after)]
    return {'packs': ['315_door_refund_desk', '316_door_payout_desk', '317_door_change_approval', '318_door_batch_landing', '319_door_file_review'],
            'before': before, 'after': after,
            'proposals': {'before': learn.proposals(records(before), 2), 'after': learn.proposals(records(after), 2)},
            'stops': stops}
