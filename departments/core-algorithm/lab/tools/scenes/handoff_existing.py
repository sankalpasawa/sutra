"""Recorded sequence of 0.18.0-handoff: the need, stated with the parts the lab had before this version (ruling R35 of the program).
scene(lab) -> the dict kept in the record under scenes.handoff_existing. Every pack loaded here is a scenario file, and no method here
is of the kind this version adds: the asks are the lab's own ask, the rows are let in by the kernel's own event door.

The need: a collections letter for loan L-17 is drafted by a model, and it counts as drafted only when a separate checker, which reads
the loan book, says so; a failed check leaves the work open for another try, within a stated number of tries; the next try is told what
happened before. Five ways to state it with existing parts, and what the algorithm makes of each:

  doer_asked          The model is asked to draft the letter and to say when it is done (pack 215). The look asks and waits. The model
                      says done: its answer is a decision, the letter is queued on it. The checker's FALSE comes after: turned away.
  checker_asked       The checker is asked instead (pack 216). The model's answer is turned away. The checker says no to the first
                      draft: the no is a decision, the goal is refused, and a second draft can be confirmed by no stamp and by no row.
  checker_stamps_yes  The checker says yes: a decision rests on nothing. The loan book changes; the letter still counts as drafted and
                      stays queued, and the checker's FALSE against the new book is turned away.
  checker_rows        The checker never stamps and states rows. Three failed checks: the look waits each time on the same question,
                      nothing is handed over again, nothing is counted, nothing is paid, and nobody is told what failed. A passing row
                      lets the plan go on; the question is still out.
  no_step             No step leads to the letter (pack 210 with the book's row alone): the look is blocked for want of evidence, then
                      for want of a method; a passing row queues the letter. Nobody was named as the hand and nothing was counted.
  three_asks          Three tries written as three asks to the checker under one rule (pack 217). Each no is a decision and the next
                      try is asked; its receipt holds the words of the pack and nothing of the check that failed; after the third no
                      the goal is refused. In a second State the checker says yes to the second try: the step that needs the letter
                      stops, because the letter holds only through the rule and the gate reads stored rows.

A snapshot is {budget, providers, open_asks, letter_drafted, letter_queued}: the last two say what each fact reads and from which row."""
LOOKS = 26   # the looks scene(lab) records (a dict that holds a list under `runs`: a look at the goals, an event, an answer): doer 3, checker 4, stamped 4, rows 5, no step 3, three asks 4 + 3
RUNS = 23    # the runs in them (a dict with `trace` and `trace_root_sha256`): doer 2, checker 3, stamped 3, rows 5, no step 3, three asks 4 + 3; a row that a decision turns away is a look that starts no run


def scene(lab):
    State, Kernel, pack, answer, open_asks = lab['State'], lab['Kernel'], lab['pack'], lab['answer'], lab['open_asks']
    DESK = ['210_letters_desk', '212_book_read']
    HAND, CHECKER = 'model:letter-drafter', 'checker:loan-book'

    def start(names):
        s = State.from_packs([pack(n) for n in names])
        return s, Kernel(s)

    def reads(s, fact):
        seen = s.fact(fact)
        return {key: seen.get(key) for key in ('truth', 'source', 'final', 'version')}

    def snap(s):
        return {'budget': dict(s.budget), 'providers': dict(s.providers), 'open_asks': open_asks(s),
                'letter_drafted': reads(s, 'letter_drafted'), 'letter_queued': reads(s, 'letter_queued')}

    def says(truth, version, fact='letter_drafted', **more):   # a row of the checker, as its check of the letter would state it
        return {'predicate': fact, 'truth': truth, 'verified': True, 'source': CHECKER, 'version': version, **more}

    def turned_away(k, receipt, truth, party):   # an answer the lab does not take: its words are kept, and no look starts
        try:
            answer(k, receipt, truth, party, execute=True)
        except ValueError as why:
            return {'party': party, 'truth': truth, 'refused': str(why)}
        return {'party': party, 'truth': truth, 'refused': None}

    asked = lambda look: look['runs'][0]['model_receipts'][-1]   # the receipt of the question a look asked
    BOOK_2 = {'predicate': 'loan_on_book', 'truth': 'TRUE', 'verified': True, 'source': CHECKER, 'version': 'book-after-a-part-payment'}
    WRONG = 'the letter says an overdue amount of 2400; the loan book says 240'

    # 1. An ask put to the doer.
    names = DESK + ['215_ask_the_drafter']
    s, k = start(names)
    look = k.run_standing(execute=True)
    doer = {'packs': names, 'look': look, 'after_look': snap(s),
            'doer_says_done': answer(k, asked(look), 'TRUE', HAND, execute=True), 'after_done': snap(s),
            'checker_says_no': k.on_event(says('FALSE', 'check-of-draft-1', why=WRONG), execute=True), 'after': snap(s)}

    # 2. An ask put to the checker. The first draft is wrong and the checker says no.
    names = DESK + ['216_ask_the_checker']
    s, k = start(names)
    look = k.run_standing(execute=True)
    checker = {'packs': names, 'look': look, 'after_look': snap(s),
               'doer_says_done': turned_away(k, asked(look), 'TRUE', HAND),
               'checker_says_no': answer(k, asked(look), 'FALSE', CHECKER, execute=True), 'after_no': snap(s),
               'second_draft_stamp': turned_away(k, asked(look), 'TRUE', CHECKER),
               'second_draft_row': k.on_event(says('TRUE', 'check-of-draft-2'), execute=True),
               'look_again': k.run_standing(execute=True), 'after': snap(s)}

    # 3. The checker says yes by its stamp. Then the loan book changes.
    s, k = start(names)
    look = k.run_standing(execute=True)
    stamped = {'packs': names, 'look': look,
               'checker_says_yes': answer(k, asked(look), 'TRUE', CHECKER, execute=True), 'after_yes': snap(s),
               'book_changes': k.on_event(BOOK_2, execute=True), 'after_book': snap(s),
               'checker_says_no': k.on_event(says('FALSE', 'check-against-the-new-book', why='the letter says an overdue amount of 240; the loan book says 180'), execute=True),
               'after': snap(s)}

    # 4. The checker states rows and never stamps.
    s, k = start(names)
    look = k.run_standing(execute=True)
    rows = {'packs': names, 'look': look, 'after_look': snap(s), 'failed_checks': []}
    for n in (1, 2, 3):
        rows['failed_checks'].append({'check': k.on_event(says('FALSE', f'check-of-draft-{n}', why=WRONG), execute=True), 'after': snap(s)})
    rows.update(passing_check=k.on_event(says('TRUE', 'check-of-draft-4', depends_on=[{'predicate': 'loan_on_book', 'version': 'book-fixture'}]), execute=True), after=snap(s))

    # 5. No step at all.
    s, k = start(DESK)
    none = {'packs': DESK, 'look': k.run_standing(execute=True),
            'failed_check': k.on_event(says('FALSE', 'check-of-draft-1', why=WRONG), execute=True),
            'passing_check': k.on_event(says('TRUE', 'check-of-draft-2', depends_on=[{'predicate': 'loan_on_book', 'version': 'book-fixture'}]), execute=True), 'after': snap(s)}

    # 6. Three tries as three asks under one rule. Three noes; and, in a second State, a yes to the second try.
    names = DESK + ['217_three_asks']
    s, k = start(names)
    look = k.run_standing(execute=True)
    no_1 = answer(k, asked(look), 'FALSE', CHECKER, execute=True)
    no_2 = answer(k, asked(no_1), 'FALSE', CHECKER, execute=True)
    three = {'packs': names, 'look': look, 'no_to_try_1': no_1, 'no_to_try_2': no_2,
             'no_to_try_3': answer(k, asked(no_2), 'FALSE', CHECKER, execute=True), 'after': snap(s)}
    s, k = start(names)
    look = k.run_standing(execute=True)
    no_1 = answer(k, asked(look), 'FALSE', CHECKER, execute=True)
    three['yes'] = {'look': look, 'no_to_try_1': no_1, 'yes_to_try_2': answer(k, asked(no_1), 'TRUE', CHECKER, execute=True),
                    'draft_2_passes': reads(s, 'draft_2_passes'), 'after': snap(s)}
    return {'doer_asked': doer, 'checker_asked': checker, 'checker_stamps_yes': stamped, 'checker_rows': rows, 'no_step': none, 'three_asks': three}
