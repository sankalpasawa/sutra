"""Recorded sequence of 0.19.0-reader: a question answered the same way each time, and a yes asked of another system
(ruling R27 of the program, tried under R35). scene(lab) -> the dict kept in the record under scenes.reader_answers.
Every pack loaded here is a scenario file.

A lender's waiver desk keeps a journal. For three loans it asks finance whether the late fee may be waived, in the
same words each time, and finance says yes each time. A "process" here holds nothing but what it was given: the first
builds its State through the journal and ends; the later ones have the kept text and the kept head and nothing else.

A step is {entry, result}: the number of the journal entry it sealed and what the kernel returned for it. What is recorded:

  asked, answered       process 1: one pack, one executed look that puts the three questions to finance (the fourth
                        goal, the yes to a change of the desk's ways, waits for a row), then finance's three answers,
                        each presenting the receipt of its question. Every yes waives that loan's fee.
  existing_parts        the same record read with the parts the lab had, by process 2 after the restart: what a
                        Learner says when it is fed every run in journal order, and the ledger's rows of the answers.
  after_two, proposals  what the reader says at the head the second answer left (nothing: two are not three) and at
                        the head the third answer left: one proposal, naming the three answer entries. The head the
                        second answer left was quoted by process 1 and is carried over in memory: no keeper held it.
  row, question         the row the reader words for that proposal goes in at the event door; the yes to the change
                        is asked of another system: the step that requires the row puts the question to finance.
  yes, approved         finance's yes, presenting that receipt: a decision, and its stored row says who gave it.
  handed_in, loan_204   the pack with the desk's own yes goes in at the pack door, after the yes reads TRUE and not
                        before; the next loan's fee is waived on the desk's own yes, and nobody is asked.
  proposals_after       the reader at the last head: the same proposal still (it does not see what was done about it).
  text, head            the journal as it is kept at the end, and its head.
  no                    from the head the question left, a third process: finance says no. The no is a decision, the
                        driver hands nothing in, and the look after it runs nothing."""
LOOKS = 9    # every dict that holds a list under `runs`: the look, three answers, the row, the yes, loan 204; and with a no: the answer, the look after it
RUNS = 15    # every dict with `trace` and `trace_root_sha256`: the first look has four, each answer one, the row one, the yes one, loan 204 one; the no one, the look after it four


def scene(lab):
    from extensions import journal as J
    from extensions import journal_record as R
    from extensions import reader
    pack, Learner, open_asks = lab['pack'], lab['Learner'], lab['open_asks']
    BOOK, FINANCE = 'fixture/loan-book', 'system:lendco/finance'
    snap = lambda s: {'budget': dict(s.budget), 'providers': dict(s.providers), 'goals': list(s.goals), 'open_asks': sorted(open_asks(s))}

    def step(run, kind, body):
        e = run.add(kind, body)
        return {'entry': e['seq'], 'result': run.detail[e['seq']]}

    def says(receipt, truth):   # finance's answer to one question: it presents the receipt of that question
        return {'receipt': receipt, 'truth': truth, 'source': FINANCE, 'execute': True}

    def said(s, name):   # the stored row of a yes or a no, as a look reads it
        x = s.fact(name)
        return {k: x.get(k) for k in ('truth', 'source', 'final')}

    # Process 1: three questions, three answers. Then it ends.
    keep = J.Keep()
    p1 = J.start(['simulate_fact', 'ask'], [BOOK, reader.SOURCE], name='waivers')
    p1.add('pack', {'pack': pack('228_waiver_desk')})
    asked = step(p1, 'look', {'execute': True})
    answered, heads = [], []
    for run in asked['result']['runs'][:3]:
        answered.append(step(p1, 'answer', says(run['model_receipts'][-1], 'TRUE')))
        heads.append(p1.head())
    head_three, after_three = J.save(p1, keep), snap(p1.state)
    del p1

    # Process 2: all it has is the kept text and the kept head. First the record is read with the parts the lab had.
    p2 = J.restart(keep)
    kept = [keep.read()]
    learner = Learner(True)
    existing = {'learner_fed_in_journal_order': [learner.learn(r) for seq in sorted(p2.detail) for r in p2.detail[seq]['runs']],
                'ledger_rows_of_the_answers': [r for r in R.ledger(kept) if r['what'] == 'decided']}

    # The reader, then the yes of another system: the question to finance goes out once the row is in.
    after_two = reader.proposals([(keep.text, heads[1])], 3)
    found = reader.proposals(kept, 3)
    row = reader.row(found[0], 'waiver_answer_repeated')
    question = step(p2, 'event', {'row': row, 'execute': True})
    receipt = question['result']['runs'][0]['model_receipts'][-1]
    head_question, after_question = J.save(p2, keep), snap(p2.state)
    at_question = J.Keep(*keep.read())   # what is kept at this point, a second time: the branch where finance says no starts here
    yes = step(p2, 'answer', says(receipt, 'TRUE'))
    approved = said(p2.state, 'own_waivers_approved')

    def hand_in(run, yes_row):   # the driver's rule: the pack goes in at the ordinary door, after the yes reads TRUE and not before
        return run.add('pack', {'pack': pack('229_own_waivers')})['seq'] if yes_row['truth'] == 'TRUE' else None

    handed_in = hand_in(p2, approved)
    loan_204 = step(p2, 'look', {'execute': True})
    head = J.save(p2, keep)

    # Finance says no instead: a decision. Nothing is handed in.
    p3 = J.restart(at_question)
    no = step(p3, 'answer', says(receipt, 'FALSE'))
    refused = said(p3.state, 'own_waivers_approved')
    not_handed_in = hand_in(p3, refused)
    look_after = step(p3, 'look', {'execute': True})

    return {'packs': ['228_waiver_desk'], 'kinds': ['simulate_fact', 'ask'], 'checkers': [BOOK, reader.SOURCE],
            'asked': asked, 'answered': answered, 'heads_after_each_answer': heads, 'head_after_three': head_three, 'after_three': after_three,
            'existing_parts': existing, 'after_two': after_two, 'proposals': found,
            'row': row, 'question': question, 'head_after_question': head_question, 'after_question': after_question,
            'yes': yes, 'approved': approved, 'handed_in': {'entry': handed_in, 'pack': '229_own_waivers'},
            'loan_204': loan_204, 'after': snap(p2.state), 'proposals_after': reader.proposals([keep.read()], 3), 'text': keep.text, 'head': head,
            'no': {'answer': no, 'approved': refused, 'handed_in': {'entry': not_handed_in, 'pack': '229_own_waivers'}, 'look_after': look_after, 'after': snap(p3.state)}}
