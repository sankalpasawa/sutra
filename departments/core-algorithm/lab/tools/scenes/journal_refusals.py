"""Recorded sequence of the journal version (matrix gap 1): what the journal refuses, and what it cuts.
scene(lab) -> the dict kept in the record under scenes.journal_refusals. Every pack loaded here is a scenario file.

`text` and `head` are a kept journal of seven entries: the packs of case 29 and one executed look (`look`: entry 6
and what the kernel returned for it), so the customer's question is out. Every part below starts from it. A refusal
is recorded in the journal's own words (`refused`).

  tampered        the kept text changed by someone who does not write through the door, each with the head that is
                  presented and the words the restart refuses it with: cut short; an entry changed, dropped, doubled;
                  two entries swapped; a head for another hash; no head; one re-chained by a forger (the charge
                  for the question taken back, every hash made again, a head of its own), which is refused where the
                  result does not come out again; and an entry replaced by a line that nests a thousand deep, which
                  no reader can take apart: refused by its number as a broken entry, not as a failure of the process.
  past_the_head   one more entry stands in the text and the head was not moved (a writer that died between the entry
                  and the head, or a forger's yes; `writer` is that entry's number and what the kernel returned to
                  the writer): the restart reports it and does not run it; the next save cuts it.
  second_writer   two processes restart from the same head. The first saves the customer's no. The save of the second
                  is refused and changes nothing that is kept (`kept_text`, `kept_head`: what is kept right after the
                  refusal); it restarts and its row is then looked at under the no.
  pack_twice      another journal (the packs of case 04, a shipment, the level pack 140, the parcel comes back, a
                  second shipment): the level pack handed over again is refused at the door. Beside it the kernel
                  alone, which takes the pack twice, and a journal that holds the pack twice, which does not replay.
  outside         an answer given straight to the kernel, past the journal: the next entry is refused, and after a
                  restart the bypass never happened.
  doors           bodies the doors refuse, each with the words; the journal and the State are as they were after all."""
LOOKS = 11   # the looks scene(lab) records: every dict that holds a list under `runs`
RUNS = 11   # the runs in them: every dict with `trace` and `trace_root_sha256`
import json


def scene(lab):
    from extensions import journal as J
    State, Kernel, pack, answer, open_asks, sha = lab['State'], lab['Kernel'], lab['pack'], lab['answer'], lab['open_asks'], lab['digest']
    PACKS = ['00_goal', '01_domain', '02_methods', '04_admission', '80_ask_method']
    KINDS = ['simulate_fact', 'ask']
    RECOUNT = {'predicate': 'substitute_stock', 'truth': 'TRUE', 'version': '2', 'verified': True, 'source': 'fixture/stock-recount'}
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

    def chained(entries):   # what a forger can do without any secret: number the entries and hash the chain again
        out, prev = [], 'GENESIS'
        for n, e in enumerate(entries):
            e = dict(json.loads(json.dumps(e)), seq=n, prev_sha256=prev)
            e['sha256'] = sha({k: e[k] for k in J.COVERED})
            out.append(e)
            prev = e['sha256']
        return out, {'length': len(out), 'sha256': prev}

    base = J.start(KINDS, checkers=['fixture/stock-recount'], name='refusals')
    for n in PACKS:
        base.add('pack', {'pack': pack(n)})
    look = step(base, 'look', {'execute': True})
    receipt = look['result']['runs'][0]['model_receipts'][0]
    keep = J.Keep()
    head = J.save(base, keep)
    text, entries = keep.text, J.parse(keep.text)
    kept = lambda: J.Keep(text, head)
    yes = {'receipt': receipt, 'truth': 'TRUE', 'source': 'customer', 'execute': True}

    # ---- the kept text changed past the door
    def tamper(what, changed, presented=head):
        t = J.dump(changed)
        return {'what': what, 'text': t, 'head': presented, 'refused': refused(lambda: J.restart(J.Keep(t, presented)))}
    edited = json.loads(json.dumps(entries))
    edited[5]['body']['pack']['methods'][0]['ask_to'] = 'someone-else'   # who is asked, changed in the pack as it was handed in
    forged = json.loads(json.dumps(entries))
    forged[6]['result']['budget']['attention'] = 3                       # the charge for the question taken back
    tampered = [tamper('cut short', entries[:-1]),
                tamper('an entry changed', edited),
                tamper('an entry dropped', entries[:3] + entries[4:]),
                tamper('an entry dropped and the head moved back to match', entries[:3] + entries[4:], {'length': 6, 'sha256': head['sha256']}),
                tamper('an entry doubled', entries[:4] + entries[3:]),
                tamper('two entries swapped', entries[:2] + [entries[3], entries[2]] + entries[4:]),
                tamper('a head that names another hash', entries, {'length': 7, 'sha256': entries[5]['sha256']}),
                tamper('no head', entries, None),
                tamper('re-chained by a forger', *chained(forged))]
    deep = text.split('\n')
    deep[3] = '[' * 1000 + ']' * 1000                                    # entry 3 replaced by a line that nests deeper than any entry can
    tampered.append({'what': 'an entry that nests a thousand deep', 'text': '\n'.join(deep), 'head': head, 'refused': refused(lambda: J.restart(J.Keep('\n'.join(deep), head)))})

    # ---- an entry past the head
    writer = J.restart(kept())
    wrote = step(writer, 'answer', yes)                      # the entry exists ...
    stray = J.Keep(text + J.dump(writer.journal[7:]), head)  # ... and stands in the text, but the head was never moved
    del writer
    r = J.restart(stray)
    past = {'writer': wrote, 'text': stray.text, 'head': head, 'cut': r.cut, 'after_restart': snap(r.state), 'look': step(r, 'look', {'execute': True})}
    past['head_after_save'] = J.save(r, stray)
    past['text_after_save'] = stray.text

    # ---- two writers from one head
    shared = kept()
    a, b = J.restart(shared), J.restart(shared)
    first = step(a, 'answer', {'receipt': receipt, 'truth': 'FALSE', 'source': 'customer', 'execute': True})
    head_first = J.save(a, shared)
    second = step(b, 'event', {'row': RECOUNT, 'execute': True})   # b has not seen the no: on its State the question is still out
    lost = refused(lambda: J.save(b, shared))
    kept_after = (shared.text, dict(shared.head))
    del a, b
    b2 = J.restart(shared)
    again = step(b2, 'event', {'row': RECOUNT, 'execute': True})
    later_yes = refused(lambda: b2.add('answer', yes))
    writers = {'base': head, 'first': {'step': first, 'head': head_first},
               'second': {'step': second, 'refused': lost, 'kept_head': kept_after[1], 'kept_text': kept_after[0]},
               'again': {'restarted_at': dict(b2.base), 'step': again, 'later_yes_refused': later_yes}}
    writers['head'] = J.save(b2, shared)
    writers['text'] = shared.text

    # ---- a pack id passes the door once
    ORDER = ['00_goal', '01_domain', '02_methods', '03_approval', '04_admission']
    LOST = {'predicate': 'replacement_delivered', 'truth': 'FALSE', 'version': 'returned-1', 'verified': True, 'source': 'fixture/courier'}
    once = J.start(['simulate_fact'], checkers=['fixture/courier'], name='once')
    for n in ORDER:
        once.add('pack', {'pack': pack(n)})
    walk = {'shipped': step(once, 'look', {'execute': True}), 'after_shipped': snap(once.state)}
    walk['levels_entry'] = once.add('pack', {'pack': pack('140_levels_restated')})['seq']
    walk['after_levels'] = snap(once.state)
    walk['came_back'] = step(once, 'event', {'row': LOST, 'execute': True})
    walk['after_came_back'] = snap(once.state)
    walk['refused'] = refused(lambda: once.add('pack', {'pack': pack('140_levels_restated')}))
    walk['after_refusal'] = snap(once.state)
    once_keep = J.Keep()
    walk['head'] = J.save(once, once_keep)
    walk['text'] = once_keep.text
    s = State.from_packs([pack(n) for n in ORDER])   # the kernel alone: no door that lets a pack id in once
    k = Kernel(s)
    alone = {'shipped': k.run_standing(execute=True), 'budgets': [dict(s.budget)]}
    s.apply(pack('140_levels_restated'))
    alone['budgets'].append(dict(s.budget))
    alone['came_back'] = k.on_event(LOST, execute=True)
    alone['budgets'].append(dict(s.budget))
    s.apply(pack('140_levels_restated'))
    alone['budgets'].append(dict(s.budget))
    alone['loaded'] = [p['pack'] for p in s.loaded]
    walk['kernel_alone'] = alone
    twice = J.parse(once_keep.text)
    again_in = json.loads(json.dumps(twice[walk['levels_entry']]))   # the entry that let the level pack in, a second time, with the levels it would have set
    again_in['result']['state'] = twice[-1]['result']['state']
    held, held_head = chained(twice + [again_in])
    walk['holds_it_twice'] = {'text': J.dump(held), 'head': held_head, 'refused': refused(lambda: J.restart(J.Keep(J.dump(held), held_head)))}

    # ---- the State changed outside the journal
    o = J.restart(kept())
    outside = {'bypass': answer(Kernel(o.state), receipt, 'TRUE', 'customer', execute=True), 'after_bypass': snap(o.state),
               'refused': refused(lambda: o.add('look', {'execute': True})), 'no_head': refused(lambda: o.head()), 'entries': len(o.journal)}
    del o
    outside['after_restart'] = snap(J.restart(kept()).state)

    # ---- bodies the doors refuse
    d = J.restart(kept())
    other = json.loads(json.dumps(receipt))
    other['ask']['to'] = 'someone-else'
    tried = [('look', {'execute': 'false'}),
             ('look', {'execute': 1}),
             ('look', {'execute': True, 'note': 'x'}),
             ('look', {}),
             ('pack', {'pack': pack('80_ask_method')}),
             ('event', {'row': dict(RECOUNT, source='the-hand'), 'execute': True}),
             ('event', {'row': dict(RECOUNT, predicate='customer_approved', final=True), 'execute': True}),
             ('event', {'row': dict(RECOUNT, verified=False), 'execute': True}),
             ('event', {'row': RECOUNT}),
             ('answer', {'receipt': other, 'truth': 'TRUE', 'source': 'someone-else', 'execute': True}),
             ('answer', {'receipt': receipt, 'truth': 'TRUE', 'source': 'someone-else', 'execute': True}),
             ('answer', {'receipt': receipt, 'truth': 'TRUE', 'source': 'customer', 'execute': 'yes'}),
             ('answer', {'fact': 'customer_approved', 'truth': 'TRUE', 'source': 'customer', 'execute': True}),
             ('resume', {'head': head}),
             ('header', {'kinds': KINDS, 'checkers': []}),
             ('close', {}),
             ('close', {'next': {'kinds': ['ask'], 'checkers': []}})]
    doors = [{'kind': kind, 'body': body, 'refused': refused(lambda: d.add(kind, body))} for kind, body in tried]

    return {'packs': PACKS, 'kinds': KINDS, 'text': text, 'head': head, 'look': look,
            'tampered': tampered, 'past_the_head': past, 'second_writer': writers, 'pack_twice': dict(walk, packs=ORDER),
            'outside': outside, 'doors': doors, 'after_doors': {'head': d.head(), 'state': J.state_digest(d.state), 'after': snap(d.state)}}
