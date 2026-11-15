"""Recorded sequence of the journal version (matrix gap 1, rows R07 and R11): a restart.
scene(lab) -> the dict kept in the record under scenes.journal_restart. Every pack loaded here is a scenario file.

The packs are those of case 29: the customer's approval is unknown and a reviewed method may ask for it. A "process"
here is a run that holds nothing but what it was given: the first builds its State through the journal, the later ones
get the kept text and the kept head and nothing else (J.restart), or the packs alone (no journal).

A step is {entry, result}: the number of the journal entry it sealed and what the kernel returned for it. A snapshot is
{budget, providers, open_asks}. What is recorded:

  first, head_after_first, after_first      process 1: five packs, one executed look. It asks the customer and stops.
  restarted                                 process 2, from the text and the head: nothing past the head, no notice,
                                            the State digest of process 1's last entry, the question still out.
  again, after_again                        its look waits, runs nothing and charges nothing.
  answered_yes, after_yes                   the customer's yes, presenting the receipt process 1 issued: the plan goes on.
  later, after_later                        process 3, restarted once more: what ran is not run again.
  text, head                                the journal as it is kept at the end, and its head.
  twin_head, twin_text                      the same nine things done by one process that never stopped: its head and
                                            its journal as text, to be compared with `head` and `text` byte for byte.
  ledger, counts, counts_at_first           read from the text alone by extensions/journal_record.py, at the last head
                                            and at the head process 1 left.
  from_packs_alone                          the same walk with no journal: the first receipt is refused, the customer
                                            is asked and charged a second time, then the answer is taken.
  no                                        from the head process 1 left, the customer says no: the next process
                                            reads REFUSED and a later yes is refused. From the packs alone the no is
                                            forgotten and a later yes ships.
  one_dry_look_more                         the promise names the journal, not the packs: a journal with the same header
                                            and the same five packs takes one dry look before its executed look. The
                                            question then carries another receipt (bound to another history) under the
                                            same provenance; the receipt of process 1 does not answer it; its own does.
  line_marks                                the same ask with a question that holds U+2028, U+2029 and U+0085 (pack
                                            141): the text is cut at line feeds only, and the question comes back whole."""
LOOKS = 14   # the looks scene(lab) records: every dict that holds a list under `runs`
RUNS = 14   # the runs in them: every dict with `trace` and `trace_root_sha256`


def scene(lab):
    from extensions import journal as J
    from extensions import journal_record as R
    State, Kernel, pack, answer, open_asks = lab['State'], lab['Kernel'], lab['pack'], lab['answer'], lab['open_asks']
    PACKS = ['00_goal', '01_domain', '02_methods', '04_admission', '80_ask_method']
    KINDS = ['simulate_fact', 'ask']
    snap = lambda s: {'budget': dict(s.budget), 'providers': dict(s.providers), 'open_asks': open_asks(s)}

    def step(run, kind, body):
        e = run.add(kind, body)
        return {'entry': e['seq'], 'result': run.detail[e['seq']]}

    def refused(do):
        try:
            do()
        except ValueError as why:
            return str(why)
        return None

    def yes(receipt):
        return {'receipt': receipt, 'truth': 'TRUE', 'source': 'customer', 'execute': True}

    # Process 1: the packs are handed over, one look is taken, the journal is saved. Then it ends.
    keep = J.Keep()
    p1 = J.start(KINDS, name='restart')
    for n in PACKS:
        p1.add('pack', {'pack': pack(n)})
    first = step(p1, 'look', {'execute': True})
    head_first, after_first = J.save(p1, keep), snap(p1.state)
    receipt = first['result']['runs'][0]['model_receipts'][0]
    kept_first = J.Keep(*keep.read())   # what is kept at this point, a second time: the branch where the customer says no starts here
    del p1

    # Process 2: all it has is the kept text and the kept head.
    p2 = J.restart(keep)
    restarted = {'head': dict(p2.base), 'cut': p2.cut, 'notice': p2.notice, 'state': J.state_digest(p2.state), 'after': snap(p2.state)}
    again = step(p2, 'look', {'execute': True})
    after_again = snap(p2.state)
    answered = step(p2, 'answer', yes(receipt))
    after_yes = snap(p2.state)
    J.save(p2, keep)
    del p2

    # Process 3: what ran is not run again.
    p3 = J.restart(keep)
    later = step(p3, 'look', {'execute': True})
    after_later = snap(p3.state)
    head = J.save(p3, keep)

    # The twin: one process that never stopped does the same nine things.
    twin = J.start(KINDS, name='restart')
    for n in PACKS:
        twin.add('pack', {'pack': pack(n)})
    for kind, body in (('look', {'execute': True}), ('look', {'execute': True}), ('answer', yes(receipt)), ('look', {'execute': True})):
        twin.add(kind, body)

    # The same walk from the packs alone: a new process that has no journal.
    s = State.from_packs([pack(n) for n in PACKS])
    k = Kernel(s)
    alone = {'answer_refused': refused(lambda: answer(k, receipt, 'TRUE', 'customer', execute=True)), 'after_refusal': snap(s)}
    alone['look'] = k.run_standing(execute=True)
    alone['after_look'] = snap(s)
    alone['answered_yes'] = answer(k, receipt, 'TRUE', 'customer', execute=True)
    alone['after_yes'] = snap(s)

    # The customer says no instead, to the process that restarted from the head process 1 left.
    n2 = J.restart(kept_first)
    said_no = step(n2, 'answer', {'receipt': receipt, 'truth': 'FALSE', 'source': 'customer', 'execute': True})
    after_no = snap(n2.state)
    J.save(n2, kept_first)
    del n2
    n3 = J.restart(kept_first)
    no_look = step(n3, 'look', {'execute': True})
    later_yes = refused(lambda: n3.add('answer', yes(receipt)))
    after_no_look = snap(n3.state)
    head_no = J.save(n3, kept_first)
    s2 = State.from_packs([pack(n) for n in PACKS])   # what the no was said to is gone: this process has the packs alone
    k2 = Kernel(s2)
    forgot_look = k2.run_standing(execute=True)
    forgot_yes = answer(k2, receipt, 'TRUE', 'customer', execute=True)

    # The same header and the same packs, and one dry look before the executed one: another journal, so another answer.
    dry_keep = J.Keep()
    d = J.start(KINDS, name='restart')
    for n in PACKS:
        d.add('pack', {'pack': pack(n)})
    more = {'dry': step(d, 'look', {'execute': False}), 'after_dry': snap(d.state)}
    more['look'] = step(d, 'look', {'execute': True})
    more['after_look'] = snap(d.state)
    more['first_receipt_refused'] = refused(lambda: d.add('answer', yes(receipt)))
    more['answered_yes'] = step(d, 'answer', yes(more['look']['result']['runs'][0]['model_receipts'][0]))
    more['after_yes'] = snap(d.state)
    more['head'] = J.save(d, dry_keep)
    more['text'] = dry_keep.text

    # A question with line marks in it, through the text and back.
    MARKS = ['00_goal', '01_domain', '02_methods', '04_admission', '141_ask_with_line_marks']
    marks_keep = J.Keep()
    m1 = J.start(KINDS, name='line-marks')
    for n in MARKS:
        m1.add('pack', {'pack': pack(n)})
    marked = step(m1, 'look', {'execute': True})
    J.save(m1, marks_keep)
    del m1
    m2 = J.restart(marks_keep)
    out = list(open_asks(m2.state).values())

    kept = [(keep.text, head)]
    return {'packs': PACKS, 'kinds': KINDS,
            'first': first, 'head_after_first': head_first, 'after_first': after_first,
            'restarted': restarted, 'again': again, 'after_again': after_again, 'answered_yes': answered, 'after_yes': after_yes,
            'later': later, 'after_later': after_later, 'text': keep.text, 'head': head,
            'twin_head': twin.head(), 'twin_text': J.dump(twin.journal),
            'ledger': R.ledger(kept), 'counts': R.counts(kept), 'counts_at_first': R.counts([(keep.text, head_first)]),
            'from_packs_alone': alone,
            'no': {'answered_no': said_no, 'after_no': after_no, 'look': no_look, 'later_yes_refused': later_yes, 'after_look': after_no_look,
                   'text': kept_first.text, 'head': head_no,
                   'from_packs_alone': {'look': forgot_look, 'answered_yes': forgot_yes, 'after_yes': snap(s2)}},
            'one_dry_look_more': more,
            'line_marks': {'packs': MARKS, 'look': marked, 'text': marks_keep.text, 'head': dict(marks_keep.head),
                           'state_after_restart': J.state_digest(m2.state), 'question_after_restart': out[0]['issued']['ask']['question'] if out else None}}
