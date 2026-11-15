"""Recorded sequence of 0.19.0-reader: a repeated chain proposed as one cheaper way (ruling R27 of the program, tried under R35).
scene(lab) -> the dict kept in the record under scenes.reader_one_way. Every pack loaded here is a scenario file.

A lender's payout desk keeps a journal. Three loans are paid out, each by the same three steps: check the payee, pay,
reconcile. A "process" here holds nothing but what it was given: the first builds its State through the journal and
ends; the second has the kept text and the kept head and nothing else.

A step is {entry, result}: the number of the journal entry it sealed and what the kernel returned for it. What is recorded:

  three_payouts         process 1: two packs, one executed look (loan 101), then loan 102 and loan 103 (the loan
                        book's row, in at the event door). Each payout runs and pays all three steps.
  existing_parts        the same record read with the parts the lab had, by process 2 after the restart: what one
                        Learner says when it is fed every run in journal order, what a new Learner says of the last
                        run alone, what `reflect` proposes, and the record adapter's counts of the three steps.
  proposals             what the reader says at the head loan 103 left: the chain, the three entries, what each run
                        paid, and the chain worded as one step.
  way, fits             the way a person wrote (pack 226), and why it is not that chain as one cheaper step: no reason.
                        So the driver's look at `fits` below turns no way away in this sequence, in either branch.
  row, yes, approved    the row the reader words for the proposal goes in at the event door; a new way to pay out is
                        a weighty change, so the yes is the independent checker's step; the stored row of the yes
                        says who gave it and what it rests on.
  handed_in             the pack goes in at the pack door, after the yes reads TRUE and not before: the driver's line
                        below and no door's. The branch `no_yes` shows it keep the pack back.
  loan_104              the next payout: both ways are open, and the kernel takes the one step.
  proposals_after       the reader at the last head: the row of chains has ended, so nothing is proposed.
  text, head            the journal as it is kept at the end, and its head.
  no_yes                from the head loan 103 left, a third process: the independent checker is away (one pack
                        restates its slots to none). The same row goes in and no yes is given, so the pack is not
                        handed in; loan 104 is paid out by the chain again, and the reader's proposal now rests on
                        four entries. With its own text and head."""
LOOKS = 7   # every dict that holds a list under `runs`: the look, loan 102, loan 103, the yes, loan 104; and with no yes: the row, loan 104
RUNS = 8    # every dict with `trace` and `trace_root_sha256`: the first look has two (the work, and the yes that waits), the others one each


def scene(lab):
    from extensions import journal as J
    from extensions import journal_record as R
    from extensions import reader
    from extensions.reflection import reflect
    pack, Learner = lab['pack'], lab['Learner']
    BOOK = 'fixture/loan-book'
    DESK = ['224_payout_desk', '225_payout_changes']
    CHAIN = ['check-payout-payee@1', 'pay-payout@1', 'reconcile-payout@1']
    due = lambda loan: {'predicate': 'payout_due', 'truth': 'TRUE', 'verified': True, 'source': BOOK, 'version': f'loan-{loan}'}
    snap = lambda s: {'budget': dict(s.budget), 'providers': dict(s.providers), 'goals': list(s.goals), 'grants': sorted(s.grants)}

    def step(run, kind, body):
        e = run.add(kind, body)
        return {'entry': e['seq'], 'result': run.detail[e['seq']]}

    def said(s, name):   # the stored row of a yes, as a look reads it: who gave it and what it rests on
        x = s.fact(name)
        return {k: x.get(k) for k in ('truth', 'source', 'depends_on')}

    # Process 1: three payouts. Then it ends.
    keep = J.Keep()
    p1 = J.start(['simulate_fact'], [BOOK, reader.SOURCE], name='payouts')
    for n in DESK:
        p1.add('pack', {'pack': pack(n)})
    payouts = [step(p1, 'look', {'execute': True})]
    for loan in (102, 103):
        payouts.append(step(p1, 'event', {'row': due(loan), 'execute': True}))
    head_three, after_three = J.save(p1, keep), snap(p1.state)
    at_three = J.Keep(*keep.read())   # what is kept at this point, a second time: the branch where no yes is given starts here
    del p1

    # Process 2: all it has is the kept text and the kept head. First the record is read with the parts the lab had.
    p2 = J.restart(keep)
    kept = [keep.read()]
    learner = Learner(True)
    work = [r for seq in sorted(p2.detail) for r in p2.detail[seq]['runs'] if r['goal'] == 'payout_reconciled']
    counts = R.counts(kept)['steps']
    existing = {'one_learner_fed_in_journal_order': [learner.learn(r) for r in work],
                'a_new_learner_on_the_last_run': Learner(True).learn(work[-1]),
                'reflect': [c for c in reflect(work)['candidates'] if c['kind'] == 'COMPRESSION_CANDIDATE'],
                'counts_of_the_steps': {m: counts['lendco/payouts|' + m] for m in CHAIN}}

    # The reader: a function of the kept text and its head.
    found = reader.proposals(kept, 3)
    way = pack('226_payout_in_one')['methods'][0]
    fits = reader.fits(found[0], way)
    row = reader.row(found[0], 'payout_chain_repeated')
    yes = step(p2, 'event', {'row': row, 'execute': True})
    approved = said(p2.state, 'payout_way_approved')

    def hand_in(run, yes_row):   # the driver's rule: the pack goes in at the ordinary door, after the yes reads TRUE and not before, and only a way that fits
        return run.add('pack', {'pack': pack('226_payout_in_one')})['seq'] if yes_row['truth'] == 'TRUE' and not fits else None

    handed_in = hand_in(p2, approved)
    after_hand_in = snap(p2.state)
    loan_104 = step(p2, 'event', {'row': due(104), 'execute': True})
    head = J.save(p2, keep)
    after = reader.proposals([keep.read()], 3)

    # No yes, no hand-in: the checker is away. The same row goes in; the fourth payout runs the chain again.
    p3 = J.restart(at_three)
    p3.add('pack', {'pack': pack('227_checker_away')})
    not_given = step(p3, 'event', {'row': row, 'execute': True})
    not_approved = said(p3.state, 'payout_way_approved')
    not_handed_in = hand_in(p3, not_approved)
    by_the_chain = step(p3, 'event', {'row': due(104), 'execute': True})
    head_no_yes = J.save(p3, at_three)
    no_yes = {'pack': '227_checker_away', 'yes': not_given, 'approved': not_approved, 'handed_in': {'entry': not_handed_in, 'pack': '226_payout_in_one'},
              'loan_104': by_the_chain, 'after': snap(p3.state), 'proposals_after': reader.proposals([at_three.read()], 3), 'text': at_three.text, 'head': head_no_yes}

    return {'packs': DESK, 'checkers': [BOOK, reader.SOURCE],
            'three_payouts': payouts, 'head_after_three': head_three, 'after_three': after_three,
            'existing_parts': existing, 'proposals': found, 'way': way, 'fits': fits,
            'row': row, 'yes': yes, 'approved': approved, 'handed_in': {'entry': handed_in, 'pack': '226_payout_in_one'}, 'after_hand_in': after_hand_in,
            'loan_104': loan_104, 'after': snap(p2.state), 'proposals_after': after, 'text': keep.text, 'head': head, 'no_yes': no_yes}
