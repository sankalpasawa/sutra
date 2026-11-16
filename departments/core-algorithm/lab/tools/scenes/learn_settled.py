"""Recorded sequence of 0.20.0-learn: who stated a fact, against what the plan says (need N3 of the version; ruling R35 of the program).
scene(lab) -> the dict kept in the record under scenes.learn_settled. Every pack loaded here is a scenario file.

A lender's refund desk sends a refund of an overpaid instalment (pack 314). Its plan gives every fact to someone: the yes to finance, a
question put to another system; the check of the amount to the reconciliation checker, through a hand-over to a reconciler; the refund
to the desk's own step. The journal's event door lets in the loan book, the reconciliation checker and an auditor, so any of them can
hand in a row on any fact. Two sessions, each a journal of its own (two records). Nothing real is called: the rows are written here.

A step is {entry, result}. What is recorded:

  first            session A: the look puts the question to finance; the loan book's row says the refund is approved (no answer of
                   finance came), and the work of reconciliation is handed over (try 1); the reconciliation checker's row says the
                   refund is reconciled but names no receipt; the refund step runs; the loan book's row says the refund was sent.
  second           session B: the look puts the question; finance answers no, a decision; the loan book's row on the approval is
                   turned away at the door (the decision stands); the reconciliation checker's row says the refund is reconciled,
                   when no work was ever handed over; the auditor's row says the same.
  existing_parts   the two kept texts read with the parts the lab had: the reader's proposals of each, what one Learner says of
                   every run of each fed in journal order, and the record adapter's ledger rows of what was handed in at the
                   event door.
  proposals        what the learn feature says of the two records read together (least 2).
  Each session also keeps its text and head."""
LOOKS = 9    # every dict that holds a list under `runs`: session A four (the look and three rows), session B five (the look, the answer, three rows)
RUNS = 8     # one run in each but the row the door turned away, which runs nothing

FINANCE = 'system:lendco/finance'


def scene(lab):
    from extensions import journal as J
    from extensions import journal_record as R
    from extensions import reader, learn
    pack, Learner = lab['pack'], lab['Learner']
    BOOK, RECON, AUDIT = 'fixture/loan-book', 'checker:reconciliation', 'checker:audit'

    def step(run, kind, body):
        e = run.add(kind, body)
        return {'entry': e['seq'], 'result': run.detail[e['seq']]}

    def row(fact, source, version):
        return {'predicate': fact, 'truth': 'TRUE', 'verified': True, 'source': source, 'version': version}

    def begin(name):
        run = J.start(['simulate_fact', 'ask', 'handoff'], [BOOK, RECON, AUDIT], name=name)
        run.add('pack', {'pack': pack('314_learn_refunds')})
        return run

    def kept(run):
        keep = J.Keep()
        head = J.save(run, keep)
        return keep, head

    a = begin('refunds-a')
    first = [step(a, 'look', {'execute': True}),
             step(a, 'event', {'row': row('refund_approved', BOOK, 'loan-17-approved-in-the-book'), 'execute': True}),
             step(a, 'event', {'row': row('refund_reconciled', RECON, 'reconciliation-loan-17'), 'execute': True}),
             step(a, 'event', {'row': row('refund_sent', BOOK, 'loan-17-refund-in-the-book'), 'execute': True})]
    keep_a, head_a = kept(a)

    b = begin('refunds-b')
    second = [step(b, 'look', {'execute': True})]
    question = second[0]['result']['runs'][0]['model_receipts'][-1]
    second += [step(b, 'answer', {'receipt': question, 'truth': 'FALSE', 'source': FINANCE, 'execute': True}),
               step(b, 'event', {'row': row('refund_approved', BOOK, 'loan-17-approved-in-the-book'), 'execute': True}),
               step(b, 'event', {'row': row('refund_reconciled', RECON, 'reconciliation-loan-17'), 'execute': True}),
               step(b, 'event', {'row': row('refund_reconciled', AUDIT, 'audit-loan-17'), 'execute': True})]
    keep_b, head_b = kept(b)
    records = [[keep_a.read()], [keep_b.read()]]

    existing = {'reader_on_each_record': [reader.proposals(k, 2) for k in records], 'one_learner_on_each_record': [],
                'ledger_rows_handed_in_at_the_event_door': [[r for r in R.ledger(k) if r['what'] == 'handed_in' and 'row' in r] for k in records]}
    for keep in (keep_a, keep_b):   # a second process: all it has is the kept text and the kept head
        again, learner = J.restart(keep), Learner(True)
        existing['one_learner_on_each_record'].append([learner.learn(r) for seq in sorted(again.detail) for r in again.detail[seq]['runs']])
    return {'packs': ['314_learn_refunds'], 'checkers': [BOOK, RECON, AUDIT],
            'first': {'name': 'refunds-a', 'steps': first, 'text': keep_a.text, 'head': head_a},
            'second': {'name': 'refunds-b', 'steps': second, 'text': keep_b.text, 'head': head_b},
            'existing_parts': existing, 'proposals': learn.proposals(records, 2)}
