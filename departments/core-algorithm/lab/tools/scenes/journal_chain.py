"""Recorded sequence of the journal version (matrix gap 1, rows R07 and R11): two journals that read as one record.
scene(lab) -> the dict kept in the record under scenes.journal_chain. Every pack loaded here is a scenario file.

The packs are those of case 04: the approval is there, so the first executed look ships the replacement.

  first    journal 1: five packs and one executed look. The replacement ships (compute 8, money 8). Saved at
           `head_before_closing`. Then it is continued, which is a write to it: its closing entry names journal 2
           and is saved by compare-and-append. `head` and `text` are journal 1 as it is kept after that.
  late_writer        a second process had replayed journal 1 from the same head before it was closed. On its State
                     the parcel comes back and the replacement ships a second time, in memory. Its save is refused
                     and changes nothing that is kept. It replays: the journal is closed, takes no entry, and is
                     continued by no journal but the one it names.
  second   journal 2: its header cites the head of journal 1 and it starts from that State, not from the packs.
           Its look finds the delivery made and runs nothing. Then the courier's row says the parcel came back:
           the replacement ships a second time and is paid a second time. One more look runs nothing.
  restarted          a new process replays the chain (journal 1, then journal 2 on top of it): the same State, and its
                     look runs nothing.
  refused            journal 2 handed in without journal 1; journal 2 handed in after journal 1 as it was before it
                     was closed; a pack that journal 1 let in, handed over again in journal 2.
  ledger, counts     read from the two texts alone by extensions/journal_record.py: the shipment ran twice, each time
                     cited by journal, entry number and entry hash; the goal was looked at five times with two trace
                     roots between them, because the two shipments are one trace and so are the three looks that
                     found nothing to do. A count by trace root would say two.
  counts_after_first the same read at the head of journal 1 alone.
  from_packs_alone   a new process with the packs and no journal: it ships again and pays again."""
LOOKS = 7   # the looks scene(lab) records: every dict that holds a list under `runs`
RUNS = 7   # the runs in them: every dict with `trace` and `trace_root_sha256`


def scene(lab):
    from extensions import journal as J
    from extensions import journal_record as R
    State, Kernel, pack, open_asks = lab['State'], lab['Kernel'], lab['pack'], lab['open_asks']
    PACKS = ['00_goal', '01_domain', '02_methods', '03_approval', '04_admission']
    KINDS, CHECKERS = ['simulate_fact'], ['fixture/courier']
    LOST = {'predicate': 'replacement_delivered', 'truth': 'FALSE', 'version': 'returned-1', 'verified': True, 'source': 'fixture/courier'}
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

    # Journal 1, and the process that wrote it ends.
    keep1 = J.Keep()
    j1 = J.start(KINDS, CHECKERS, name='orders-1')
    for n in PACKS:
        j1.add('pack', {'pack': pack(n)})
    shipped = step(j1, 'look', {'execute': True})
    first = {'look': shipped, 'after': snap(j1.state), 'head_before_closing': J.save(j1, keep1)}
    del j1

    # Two processes replay journal 1 from that head. One of them continues it: a write to journal 1, by compare-and-append.
    a, b = J.restart(keep1), J.restart(keep1)
    keep2 = J.Keep()
    j2 = J.start(KINDS, CHECKERS, name='orders-2', continues=a, keep=keep1)
    first['head'], first['text'] = dict(keep1.head), keep1.text
    del a

    # The other one has not seen that. On its State the parcel comes back and the replacement ships again; its save is refused.
    late = {'step': step(b, 'event', {'row': LOST, 'execute': True}), 'after_step': snap(b.state), 'refused': refused(lambda: J.save(b, keep1)),
            'kept_head': dict(keep1.head), 'kept_text': keep1.text}
    del b
    b = J.restart(keep1)   # it replays, as a loser does: the journal is closed
    late['restarted_at'] = dict(b.base)
    late['entry_refused'] = refused(lambda: b.add('event', {'row': LOST, 'execute': True}))
    late['another_journal_refused'] = refused(lambda: J.start(KINDS, CHECKERS, name='orders-2b', continues=b, keep=keep1))
    late['after_restart'] = snap(b.state)
    late['kept_head_after'], late['kept_text_after'] = dict(keep1.head), keep1.text
    del b

    # Journal 2 goes on where journal 1 stopped.
    second = {'look': step(j2, 'look', {'execute': True}), 'after_look': snap(j2.state)}
    second['came_back'] = step(j2, 'event', {'row': LOST, 'execute': True})
    second['after_came_back'] = snap(j2.state)
    second['look_again'] = step(j2, 'look', {'execute': True})
    pack_again = refused(lambda: j2.add('pack', {'pack': pack('03_approval')}))
    J.save(j2, keep2)
    second['state_before_the_restart'] = J.state_digest(j2.state)
    del j2

    # A new process replays the chain.
    r2 = J.restart(keep2, before=J.restart(keep1))
    restarted = {'state': J.state_digest(r2.state), 'after': snap(r2.state), 'look': step(r2, 'look', {'execute': True}), 'after_look': snap(r2.state)}
    second['head'] = J.save(r2, keep2)
    second['text'] = keep2.text

    open_first = J.Keep(''.join(line + '\n' for line in keep1.text.split('\n')[:7]), first['head_before_closing'])   # journal 1 as it was kept before it was closed: whole, with a true head of its own
    refusals = {'without_the_first': refused(lambda: J.restart(keep2)),
                'after_a_first_that_is_not_closed': refused(lambda: J.restart(keep2, before=J.restart(open_first))),
                'pack_again': pack_again}

    s = State.from_packs([pack(n) for n in PACKS])
    alone = {'look': Kernel(s).run_standing(execute=True), 'after': snap(s)}

    kept = [(first['text'], first['head']), (second['text'], second['head'])]
    return {'packs': PACKS, 'kinds': KINDS, 'checkers': CHECKERS, 'first': first, 'late_writer': late, 'second': second, 'restarted': restarted, 'refused': refusals,
            'ledger': R.ledger(kept), 'counts': R.counts(kept), 'counts_after_first': R.counts(kept[:1]), 'from_packs_alone': alone}
