"""Recorded sequence of 0.20.0-learn: several records read at once (need N2 of the version; ruling R35 of the program).
scene(lab) -> the dict kept in the record under scenes.learn_across. Every pack loaded here is a scenario file.

A lender's collections desk calls a borrower whose instalment is in arrears. The call is handed to a collector and checked against the
call log (pack 312). The desk's own pack gives the collector no place; the day's roster (pack 313) gives it two. Every morning the desk
starts a new session, a journal of its own, so three mornings are three records that do not continue one another. Nothing real is called:
the call log's rows are written here and enter at the journal's event door.

A step is {entry, result}. What is recorded:

  days             three sessions, each {name, steps, text, head}. Day 1: a look blocked for want of a place, a second look blocked
                   again, the roster, a look that hands the call over (try 1), the call log's row FALSE with the words NO_NUMBER (try 2
                   goes out), its row TRUE. Day 2: one blocked look, the roster, try 1, FALSE with the same words, try 2, TRUE. Day 3:
                   one blocked look, the roster, try 1, TRUE.
  existing_parts   the three kept texts read with the parts the lab had: the reader handed the three as one record (refused: they
                   do not continue one another, in the record adapter's words), the reader on each record alone, what one Learner
                   says of every run of the three records fed in order, and the record adapter's counts of the goal in each record.
  proposals        what the learn feature says of the three records read together (least 2)."""
LOOKS = 12   # every dict that holds a list under `runs`: day 1 has five (two blocked looks, the look after the roster, two rows), day 2 four, day 3 three
RUNS = 12    # one run in each: the desk has one goal

NO_NUMBER = 'the borrower\'s number is no longer in service'
REACHED = 'reached the borrower on the second number on file; a promise to pay by Friday'


def scene(lab):
    from extensions import journal as J
    from extensions import journal_record as R
    from extensions import reader, learn
    pack, Learner = lab['pack'], lab['Learner']
    BOOK, LOG = 'fixture/loan-book', 'checker:call-log'

    def step(run, kind, body):
        e = run.add(kind, body)
        return {'entry': e['seq'], 'result': run.detail[e['seq']]}

    def call(receipt, truth, why, n):
        return {'predicate': 'arrears_call_made', 'truth': truth, 'verified': True, 'source': LOG, 'version': f'call-log-{n}', 'checks': receipt, 'why': why}

    def day(name, blocked_looks, checks):
        run = J.start(['simulate_fact', 'handoff'], [BOOK, LOG], name=name)
        run.add('pack', {'pack': pack('312_learn_collections')})
        steps = [step(run, 'look', {'execute': True}) for _ in range(blocked_looks)]
        run.add('pack', {'pack': pack('313_learn_roster')})
        steps.append(step(run, 'look', {'execute': True}))
        for n, (truth, why) in enumerate(checks, start=1):
            receipt = steps[-1]['result']['runs'][0]['model_receipts'][-1]['sha256']
            steps.append(step(run, 'event', {'row': call(receipt, truth, why, n), 'execute': True}))
        keep = J.Keep()
        head = J.save(run, keep)
        return {'name': name, 'steps': steps, 'text': keep.text, 'head': head}

    days = [day('collections-day-1', 2, [('FALSE', NO_NUMBER), ('TRUE', REACHED)]),
            day('collections-day-2', 1, [('FALSE', NO_NUMBER), ('TRUE', REACHED)]),
            day('collections-day-3', 1, [('TRUE', REACHED)])]
    records = [[(d['text'], d['head'])] for d in days]

    def refused(do):
        try:
            do()
        except ValueError as why:
            return str(why)
        return None

    learner, said = Learner(True), []
    for d in days:   # every run of the three records, fed in order to one Learner: a second process, from the kept text alone
        again = J.Keep(d['text'], d['head'])
        run = J.restart(again)
        said.append([learner.learn(r) for seq in sorted(run.detail) for r in run.detail[seq]['runs']])
    existing = {'reader_on_the_three_as_one_record': refused(lambda: reader.proposals([k[0] for k in records], 2)),
                'reader_on_each_record': [reader.proposals(k, 2) for k in records],
                'one_learner_fed_every_run_in_order': said,
                'counts_of_the_goal': [{g: {'looked': v['looked'], 'statuses': v['statuses']} for g, v in R.counts(k)['goals'].items()} for k in records]}
    return {'packs': ['312_learn_collections', '313_learn_roster'], 'checkers': [BOOK, LOG], 'days': days, 'existing_parts': existing,
            'proposals': learn.proposals(records, 2)}
