"""Recorded sequence of 0.20.0-learn: every check with the checker's own words (need N1 of the version; ruling R35 of the program).
scene(lab) -> the dict kept in the record under scenes.learn_checks. Every pack loaded here is a scenario file.

A lender's servicing desk keeps a journal. The annual statement of loan L-31 is handed to a writer and checked by the statement review
against the loan book (pack 310); the program above the desk has the servicing lead give an account of the month, which a judge of the
program checks (pack 311). Nothing real is called: the checkers' rows are written here and enter at the journal's event door, whose
header names the two checkers and the loan book.

A step is {entry, result}: the number of the journal entry it sealed and what the kernel returned for it. What is recorded:

  steps            the first look (the statement is handed over, try 1); the review's row on try 1, FALSE with the words OLD_RATE
                   (try 2 goes out in the same entry); its row on try 2, FALSE with the same words (try 3 goes out); its row on
                   try 3, TRUE with words that carry what is still open (the account of the month goes out to the servicing lead);
                   the judge's row on that account, TRUE, its verdict in its words.
  existing_parts   the same kept text read with the parts the lab had, by a second process that has only the kept text and head:
                   the reader's proposals (least 2), what one Learner says of every run fed in journal order, what `reflect`
                   proposes of those runs, the record adapter's ledger rows of the four check rows and its counts of the two steps.
  proposals        what the learn feature says of the same kept text (least 2).
  text, head       the journal as it is kept, and its head."""
LOOKS = 5   # every dict that holds a list under `runs`: the first look and the four rows
RUNS = 9    # every dict with `trace` and `trace_root_sha256`: two runs (the statement, the month) in each look but the judge's row, which moves the month only

OLD_RATE = 'the statement shows the old rate of 8.4 percent; the loan book says 7.9 percent'
SENT = 'sent with the rate of 7.9 percent; the fee line still shows last year\'s fee and needs a second look'
VERDICT = ('the statement went out right on the third try; the first two failed on one line, the rate, which the writer was never told '
           'was changed; the fee line was passed with a note and is still open')


def scene(lab):
    from extensions import journal as J
    from extensions import journal_record as R
    from extensions import reader, learn
    from extensions.reflection import reflect
    pack, Learner = lab['pack'], lab['Learner']
    BOOK, REVIEW, JUDGE = 'fixture/loan-book', 'checker:statement-review', 'checker:program-judge'
    PACKS = ['310_learn_statements', '311_learn_month_judged']

    def step(run, kind, body):
        e = run.add(kind, body)
        return {'entry': e['seq'], 'result': run.detail[e['seq']]}

    def handed(at, goal):   # the receipt of the hand-over the look of this step issued for this goal
        return next(r['model_receipts'][-1]['sha256'] for r in at['result']['runs'] if r['goal'] == goal)

    def check(fact, receipt, truth, why, by, n):
        return {'predicate': fact, 'truth': truth, 'verified': True, 'source': by, 'version': f'{by}-row-{n}', 'checks': receipt, 'why': why}

    run = J.start(['simulate_fact', 'handoff'], [BOOK, REVIEW, JUDGE], name='servicing')
    for n in PACKS:
        run.add('pack', {'pack': pack(n)})
    steps = [step(run, 'look', {'execute': True})]
    for n, (truth, why) in enumerate((('FALSE', OLD_RATE), ('FALSE', OLD_RATE), ('TRUE', SENT)), start=1):
        steps.append(step(run, 'event', {'row': check('statement_sent', handed(steps[-1], 'statement_sent'), truth, why, REVIEW, n), 'execute': True}))
    steps.append(step(run, 'event', {'row': check('servicing_month_judged', handed(steps[-1], 'servicing_month_judged'), 'TRUE', VERDICT, JUDGE, 4), 'execute': True}))
    keep = J.Keep()
    head = J.save(run, keep)
    del run

    # A second process: all it has is the kept text and the kept head. The parts the lab had read it first.
    again = J.restart(keep)
    kept = [keep.read()]
    work = [r for seq in sorted(again.detail) for r in again.detail[seq]['runs']]
    learner = Learner(True)
    rows = R.ledger(kept)
    existing = {'reader': reader.proposals(kept, 2),
                'one_learner_fed_in_journal_order': [learner.learn(r) for r in work],
                'reflect': reflect(work)['candidates'],
                'ledger_rows_of_the_checks': [r for r in rows if r['what'] == 'handed_in' and 'row' in r],
                'counts_of_the_steps': {k: {x: v[x] for x in ('ran', 'stopped', 'skipped')} for k, v in R.counts(kept)['steps'].items()}}
    return {'packs': PACKS, 'checkers': [BOOK, REVIEW, JUDGE], 'steps': steps, 'existing_parts': existing,
            'proposals': learn.proposals([kept], 2), 'text': keep.text, 'head': head}
