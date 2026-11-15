"""Recorded sequence of 0.19.0-reader: a lesson read from past runs (ruling R27 of the program, tried under R35).
scene(lab) -> the dict kept in the record under scenes.reader_lesson. Every pack loaded here is a scenario file.

A lender's collections desk keeps a journal. On three days in a row its reminder step stops for the same reason. A
"process" here holds nothing but what it was given: the first builds its State through the journal and ends; the
second has the kept text and the kept head and nothing else.

A step is {entry, result}: the number of the journal entry it sealed and what the kernel returned for it. What is recorded:

  three_days            process 1: two packs, one executed look, then the instalment restated on day 2 and day 3
                        (the loan book's row, in at the event door). The reminder step stops three times.
  existing_parts        the same record read with the parts the lab had, by process 2 after the restart: what the
                        Learner says when it is fed every run in journal order, what `reflect` proposes, and the
                        record adapter's count of the step.
  after_two, proposals  what the reader says at the head day 2 left (nothing: two stops are not three) and at the
                        head day 3 left: one proposal, naming the three entries. The head day 2 left was quoted by
                        process 1 and is carried over in memory: no keeper held it. The text it is read from is kept.
  row, yes, approved    the row the reader words for that proposal goes in at the event door; the desk's own yes is a
                        step that requires it and runs at once; the stored row of the yes says who gave it and what
                        it rests on.
  handed_in             the lesson pack goes in at the pack door, after the yes reads TRUE. That is the driver's line
                        below and no door's; this sequence has no branch without a yes, so it records the order only.
  day_four              the instalment restated once more: the reminder is sent by the way the lesson brought.
  proposals_after       the reader at the last head: the row of stops has ended, so nothing is proposed.
  text, head            the journal as it is kept at the end, and its head.
  judged_weighty        from the head day 3 left, a third process: the same lesson is judged weighty first (one pack
                        restates the value row and its answers). The same row then gets the independent checker's
                        yes, five tokens, and the desk's own yes is not offered."""
LOOKS = 6   # every dict that holds a list under `runs`: the look, day 2, day 3, the yes, day 4, and the yes of the checker
RUNS = 7    # every dict with `trace` and `trace_root_sha256`: the first look has two (the work, and the yes that waits), the others one each


def scene(lab):
    from extensions import journal as J
    from extensions import journal_record as R
    from extensions import reader
    from extensions.reflection import reflect
    pack, Learner = lab['pack'], lab['Learner']
    BOOK = 'fixture/loan-book'
    DESK = ['220_collections_desk', '221_collections_changes']
    overdue = lambda day: {'predicate': 'instalment_overdue', 'truth': 'TRUE', 'verified': True, 'source': BOOK, 'version': f'loan-7-day-{day}'}
    snap = lambda s: {'budget': dict(s.budget), 'providers': dict(s.providers), 'goals': list(s.goals), 'grants': sorted(s.grants)}

    def step(run, kind, body):
        e = run.add(kind, body)
        return {'entry': e['seq'], 'result': run.detail[e['seq']]}

    def said(s, name):   # the stored row of a yes, as a look reads it: who gave it and what it rests on
        x = s.fact(name)
        return {k: x.get(k) for k in ('truth', 'source', 'depends_on')}

    # Process 1: the desk works three days. Then it ends.
    keep = J.Keep()
    p1 = J.start(['simulate_fact'], [BOOK, reader.SOURCE], name='collections')
    for n in DESK:
        p1.add('pack', {'pack': pack(n)})
    days = [step(p1, 'look', {'execute': True})]
    days.append(step(p1, 'event', {'row': overdue(2), 'execute': True}))
    head_two = p1.head()
    days.append(step(p1, 'event', {'row': overdue(3), 'execute': True}))
    head_three, after_three = J.save(p1, keep), snap(p1.state)
    at_three = J.Keep(*keep.read())   # what is kept at this point, a second time: the branch where the lesson is judged weighty starts here
    del p1

    # Process 2: all it has is the kept text and the kept head. First the record is read with the parts the lab had.
    p2 = J.restart(keep)
    kept = [keep.read()]
    learner = Learner(True)
    runs = [r for seq in sorted(p2.detail) for r in p2.detail[seq]['runs']]
    existing = {'learner_fed_in_journal_order': [learner.learn(r) for r in runs],
                'reflect': reflect([dict(r) for r in runs])['candidates'],
                'count_of_the_step': R.counts(kept)['steps']['lendco/collections|send-reminder@1']}

    # The reader: a function of the kept text and its head.
    after_two = reader.proposals([(keep.text, head_two)], 3)
    found = reader.proposals(kept, 3)
    row = reader.row(found[0], 'reminder_stop_repeated')
    yes = step(p2, 'event', {'row': row, 'execute': True})
    approved = said(p2.state, 'reminder_lesson_approved')
    handed_in = None
    if approved['truth'] == 'TRUE':   # the driver's rule: the pack goes in after the yes, at the ordinary door
        handed_in = p2.add('pack', {'pack': pack('222_reminder_lesson')})['seq']
    after_hand_in = snap(p2.state)
    day_four = step(p2, 'event', {'row': overdue(4), 'execute': True})
    head = J.save(p2, keep)
    after = reader.proposals([keep.read()], 3)

    # The same lesson judged weighty before the row arrives: the independent checker's yes.
    p3 = J.restart(at_three)
    p3.add('pack', {'pack': pack('223_lesson_judged_weighty')})
    weighty_yes = step(p3, 'event', {'row': row, 'execute': True})
    weighty = {'pack': '223_lesson_judged_weighty', 'yes': weighty_yes, 'approved': said(p3.state, 'reminder_lesson_approved'), 'after': snap(p3.state),
               'answers': {a: p3.state.fact('change_weight=' + a)['truth'] for a in ('small', 'weighty')}}

    return {'packs': DESK, 'checkers': [BOOK, reader.SOURCE],
            'three_days': days, 'head_after_two': head_two, 'head_after_three': head_three, 'after_three': after_three,
            'existing_parts': existing, 'after_two': after_two, 'proposals': found,
            'row': row, 'yes': yes, 'approved': approved, 'handed_in': {'entry': handed_in, 'pack': '222_reminder_lesson'}, 'after_hand_in': after_hand_in,
            'day_four': day_four, 'proposals_after': after, 'text': keep.text, 'head': head,
            'judged_weighty': weighty}
