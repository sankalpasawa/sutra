"""The recorded sequence of numbers at the evidence door (matrix gap 9, ruling R22), kept in the record under scenes.numbers.

looks     the four recorded cases of this version (63 to 66) taken again, each on a State built from the case's own pack
          files: the same look, hash chain for hash chain. The code that records a case is not this version's, so what it
          cannot write is written here: the comparisons block of every run whose trace names a comparison, the
          shortfall of a look that did not fit under a declared ceiling, and after the look the budget, the provider
          slots, the length of the journal and the evidence on the books.
next_run  the State of the look of case 66, one run later: a pack sets the run cap again and leaves the ceiling alone.
          The review that ran stands on its evidence; the other still stops on the ceiling, with the same shortfall,
          although the run cap is whole again. This is what makes the second dimension a ceiling over runs.
bare      the number with no comparison row beside it (pack 152_number_alone): the same goal, rule, number and method
          as case 63 end asking for evidence at 0.8, and again after a reading of 1.0 that nothing compares.
alone     one comparison row authored alone, against a bound written into the comparison (pack 159): the reading is below
          the bound and no row says so, so the goal cannot file the finding and asks for evidence; then a new reading
          arrives through `renumber`: the one row is made again and the goal still asks.
events    a number changes while a State is running. On one State: the first look files the finding on fitness 0.8; a
          reading of 0.95 arrives through `renumber` (one look ends supported by evidence, and the finding made on the old
          comparison reads UNKNOWN); a reading of 0.7 (the finding is filed and paid again); the same reading once more
          (nothing runs); the band itself moves to 0.6 (the comparisons that use it as their bound are made again). On a
          second State the reading of 0.95 is handed to the kernel alone: the comparisons read UNKNOWN and the look asks
          for evidence; six readings the State cannot take are refused, each in the adapter's words, and leave no mark;
          the same reading through `renumber` makes the comparisons again; then a reading arrives in a pack, with no
          comparison beside it (pack 152_number_alone: the first reading, 0.8, delivered late; the adapter keeps no
          order of readings): the comparisons, made again on 0.95, read UNKNOWN and the look asks for evidence
          instead of standing on the verdict of 0.95. After each step: the same four things as after a look.
Every look, in all five parts, carries `cost_receipts`: for each of its runs, what each executed step cost, read from the
gate's own row. Every pack loaded here is a scenario file, so the verifier holds every run to its trace and its packs.
The sequence records nineteen looks (a look is a dict that holds a list under `runs`: the four cases, the next run, the
three of `bare` with the reading that nothing compares, the two of `alone`, the nine of `events`) and twenty runs (a run is a
dict with `trace` and `trace_root_sha256`); the two lines below state it, and the build holds the record to them."""
LOOKS = 19
RUNS = 20

RETAKEN = {'63_conformance_finding': ['150_conformance_goal', '151_conformance_theory', '152_run_fitness', '153_finding_method'],
           '64_conformance_in_band': ['150_conformance_goal', '151_conformance_theory', '154_run_fitness_in_band', '153_finding_method'],
           '65_loan_review_cost': ['155_loan_goal', '156_loan_review'],
           '66_review_queue': ['157_review_queue', '158_queue_reviews']}   # the four cases of this version, each taken again on its own packs
CONFORM = RETAKEN['63_conformance_finding']
ALONE = ['150_conformance_goal', '151_conformance_theory', '159_one_row_alone', '153_finding_method']
BARE = ['150_conformance_goal', '151_conformance_theory', '152_number_alone', '153_finding_method']
LOG = 'adapter:conformance/log@1'


def scene(lab):
    import copy
    from extensions.numbers import measured, renumber, cost_receipts, attach
    from extensions.numbers_lint import attach_shortfall
    State, Kernel, pack = lab['State'], lab['Kernel'], lab['pack']
    snap = lambda s: {'budget': dict(s.budget), 'providers': dict(s.providers), 'journal': len(s.event_journal), 'facts': copy.deepcopy(s.evidence)}
    priced = lambda out: dict(out, cost_receipts=[cost_receipts(r) for r in out['runs']])   # one per run: what each executed step cost
    reading = lambda value, label, **kw: measured('run_fitness', value, source=LOG, label=label, unit='ratio', **kw)

    def look(names):
        packs = [pack(n) for n in names]
        s = State.from_packs(packs)
        k = Kernel(s)
        run = attach(k.run_standing(execute=True), s)   # the comparisons a run rested on or stopped on; a run that names none gets no block
        if any('ceilings' in p for p in packs):
            attach_shortfall(run, s.budget)   # under a declared ceiling, a look that did not fit says which dimension, the need and what was left
        return {'packs': list(names), 'look': priced(run), 'after': snap(s)}, s, k

    def next_run(names, s, k):   # one run later on the State of the look of case 66
        s.apply(pack('158_run_cap_again'))
        run = attach_shortfall(attach(k.run_standing(execute=True), s), s.budget)
        return {'packs': list(names) + ['158_run_cap_again'], 'look': priced(run), 'after': snap(s)}

    def bare():
        s = State.from_packs([pack(n) for n in BARE])
        k = Kernel(s)
        first, after = priced(attach(k.run_standing(execute=True), s)), snap(s)
        event = renumber(k, reading('1.0', 'run-0002'), execute=True)   # a reading that nothing compares: stored, and no goal is named as affected
        return {'packs': list(BARE), 'look': first, 'after': after, 'event': event, 'again': priced(attach(k.run_standing(execute=True), s)), 'after_again': snap(s)}

    def alone():
        s = State.from_packs([pack(n) for n in ALONE])
        k = Kernel(s)
        first, after = priced(attach(k.run_standing(execute=True), s)), snap(s)
        again = priced(attach(renumber(k, reading('0.7', 'run-0005'), execute=True), s))
        return {'packs': list(ALONE), 'look': first, 'after': after, 'again': again, 'after_again': snap(s)}

    def start():
        s = State.from_packs([pack(n) for n in CONFORM])
        k = Kernel(s)
        return s, k, priced(attach(k.run_standing(execute=True), s))

    def refused(k, row, **kw):   # a reading the State cannot take: the adapter's own words, or none when it was taken after all
        try:
            renumber(k, row, **kw)
            return ''
        except ValueError as e:
            return str(e)

    looks, running = {}, {}
    for cid, names in RETAKEN.items():
        looks[cid], state, kernel = look(names)
        running[cid] = (state, kernel)   # the State of each look, kept so that the next run of case 66 is taken on it
    ev = {}
    s, k, ev['first'] = start()
    ev['after_first'] = snap(s)
    for key, row in (('in_band', reading('0.95', 'run-0002')), ('below_again', reading('0.7', 'run-0003')), ('same_again', reading('0.7', 'run-0003')),
                     ('band_moved', measured('fitness_band', '0.6', source='policy:routine/conformance-band', label='band-v2', unit='ratio'))):
        ev[key] = priced(attach(renumber(k, row, execute=True), s))
        ev['after_' + key] = snap(s)
    s2, k2, ev['first_bare'] = start()
    ev['after_first_bare'] = snap(s2)
    ev['bare_event'] = priced(attach(k2.on_event(reading('0.95', 'run-0002'), execute=True), s2))   # without renumber
    ev['after_bare_event'] = snap(s2)
    ev['refused'] = {'another scope': refused(k2, reading('0.95', 'run-0002', scope='orgB/workflows'), execute=True),
                     'not a row the adapter made': refused(k2, {'predicate': 'run_fitness', 'truth': 'TRUE', 'verified': True, 'source': LOG, 'version': 'by-hand-2', 'value': '0.95'}, execute=True),
                     'another unit': refused(k2, measured('run_fitness', '95', source=LOG, label='run-0002', unit='percent'), execute=True),
                     'in the place of a comparison': refused(k2, measured('fitness_in_band', '0.95', source=LOG, label='run-0002', unit='ratio'), execute=True),
                     'in the place of a row that is no number': refused(k2, measured('finding_filed', '1', source=LOG, label='run-0002', unit='ratio'), execute=True),
                     'execute is not true or false': refused(k2, reading('0.95', 'run-0002'), execute=1)}
    ev['after_refused'] = snap(s2)
    ev['repaired'] = priced(attach(renumber(k2, reading('0.95', 'run-0002'), execute=True), s2))
    ev['after_repaired'] = snap(s2)
    s2.apply(pack('152_number_alone'))   # a reading arrives in a pack, with no comparison beside it
    ev['pack_event'] = priced(attach(k2.run_standing(execute=True), s2))
    ev['after_pack_event'] = snap(s2)
    return {'looks': looks, 'next_run': next_run(RETAKEN['66_review_queue'], *running['66_review_queue']), 'bare': bare(), 'alone': alone(), 'events': ev}
