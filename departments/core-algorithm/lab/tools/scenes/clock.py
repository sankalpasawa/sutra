"""Time, recorded (0.13.0-time): time moves only at a tick (extensions/clock.py). Eighteen walks, each on one State. Every step is kept
with what stood after it: the moment, the scope, the budget, the grants, the packs on the record, what the watched facts read, their
stored rows, how many rows the kernel turned away and a digest of the books.
  order        the timed approval of pack 160. Day 2 ships (the tick of case 67a); a second look on day 2 states nothing; a tick back to
               day 1 is refused; a `now` row written by hand is turned away; on day 4 the approval has run out and what was shipped on it
               reads unknown again; a row that says the window is open again and the clock's own pack of day 2 applied again reopen
               nothing; an approval that ended on day 3 is not believed when it arrives on day 4, by event, in its own pack applied again
               or handed to observe; day 6 is a dry look, past the due-by.
  late_order   the same packs first looked at on day 6: the tick whose pack is the last pack of case 67.
  allowance    the budget case 24 ran out of, with an allowance of two a day, on day 1: the tick whose pack is the last pack of case 68.
  loan         a sanction boxed until day 15, a report that counts until day 30, a due-by on day 7. Day 5 disburses; a row written by hand
               that names a longer box changes no grant; day 15 is the last day of the box; on day 16 the clock's pack takes the grant
               away and the disbursal stands; on day 31 the report has run out and the disbursal reads unknown; a fresh report and a fresh
               sanction arrive and the loan is disbursed a second time (a stated limit, on the record).
  loan_late    the same pack first looked at on day 16: no grant, nothing runs, late. The tick whose pack is the last pack of case 69.
  two_boxes    two boxes on the sanction: the later one counts (days 16, 20, 21); given again with no fresh box the grant admits until
               the next tick, whose pack carries the revoke alone.
  pulls        two bureau pulls a day for three applicants. Day 0 pulls two; a second look on day 0 gives nothing back; day 1 pulls the
               third; the clock's own pack of day 0 applied again moves no moment, but its budget line applies like any pack's.
  weekly       one pull a week (a period of seven): days 6, 7 and 13; a decision by hand that says it is day 0 and a first tick in another
               scope give nothing; on day 14 the allowance's own box has ended, so it is taken away and gives nothing more.
  due          the order of case 04 with a due-by on day 5, first looked at on day 6. The dry look is late; the look that ships it is late
               too (it was overdue as that look began); on day 7 it holds and is not.
  two_goals    the same due-by with the shipment as a standing goal ahead of the order: the first run makes the second goal hold, and
               the order is still reported late, because it did not hold as the look began.
  called_late  a due row its owner states as passed (it reads FALSE): the blocked order is late on day 1.
  two_scopes   the order is looked at on days 2 and 3 (the same look at two moments: one trace root, two provenances), the State moves to
               the loan's scope and is ticked there on day 6, then moves back: the tick made in the loan's scope closed the order's windows
               too, so the look that follows ships nothing on the approval that ended on day 3.
  offer        a rule that names one window and a step that names another, beside a decision and a step whose effect is the rule's
               window. Before any tick a look offers that step (a stated limit); on day 2 both are open; on day 4 the rule's window is
               closed and the goal it derives is refused while the step's is still offered; on day 5 both are refused; the decision stands.
  same_moment  day 2 is stated; a stock hold that counts until day 8 arrives in a pack and is not believed (its window was never
               published); the next tick on day 2 states a second pack for that day under a name of its own, and the hold reads true;
               one more tick on day 2 states nothing.
  planted      a decision written by hand on `now` and one on a window no moment can pass arrive as events: the next tick goes through,
               and a second tick at that moment states nothing (the clock's row for the window closed by hand is turned away: nothing
               new). Then the clock's own row for day 5 arrives by hand, word for word: the tick of day 5 still states its pack.
  refusals     between day 2 and day 3: a moment that is not whole, is negative, is true, is text, is missing or is too large, a label
               with the clock's mark or that is no text, an execute that is not true or false. Each is refused and changes nothing.
  withdrawn    the approval is withdrawn on day 2, so no row names its window any more: the window still closes at its time, and an
               approval that arrives later resting on it is not believed.
  crowd        one row that names seventy windows arrives: the next tick states seventy-two rows in two packs, what closes first, and
               the row is believed; on day 6 one of its windows has closed and it is not, and the grant whose box ended on day 5 is
               taken away by the first of that tick's two packs.
A tick that states a pack must state exactly the pack its scenario file holds (tools/packs/clock.py authors them): the scene stops otherwise.
LOOKS and RUNS are the true counts of what the scene records (a look: a dict holding a list under `runs`, made by a tick, an event or a
look without a tick; a run: a dict with `trace` and `trace_root_sha256`); the scene stops when what it made has other counts."""
import json

LOOKS = 66
RUNS = 81

ORDER = ['00_goal', '01_domain', '02_methods', '04_admission', '160_timed_approval']
GATES = ['00_goal', '01_domain', '02_methods', '03_approval', '04_admission']
G = 'action:disburse-loan@1'


def tick(key, now, execute=False):
    return {'key': key, 'kind': 'tick', 'now': now, 'execute': execute}


def refused(key, now, **how):   # a tick that must be refused; `how` may give another execute or another label than the walk's
    return dict({'key': key, 'kind': 'refused', 'now': now}, **how)


def event(key, row, execute=False):
    return {'key': key, 'kind': 'event', 'row': row, 'execute': execute}


def observe(key, row):
    return {'key': key, 'kind': 'observe', 'row': row}


def load(key, name):
    return {'key': key, 'kind': 'pack', 'pack': name}


def look(key, execute=False):
    return {'key': key, 'kind': 'look', 'execute': execute}


def walks(c):
    """The script: (name, packs, label, watched facts, steps) for each walk. `c` is the clock adapter, whose helpers word the rows."""
    fact = lambda predicate, truth, version, source, **more: dict({'predicate': predicate, 'truth': truth, 'verified': True, 'source': source, 'version': version}, **more)
    by_hand = lambda predicate, truth, version, **more: fact(predicate, truth, version, 'fixture/written-by-hand', **more)
    approval = lambda version: c.timed(fact('customer_approved', 'TRUE', version, 'fixture/customer-approval'), 3)
    order = ['now', 'customer_approved', 'replacement_delivered', 'until:3', 'until:5', 'in-time:order_complete']
    loan = ['now', 'loan_disbursed', 'bureau_report_clean', 'until:7', 'until:30', 'until:60', 'in-time:loan_disbursed']
    pulls = ['now', 'report_pulled_a', 'report_pulled_b', 'report_pulled_c']
    return [
        ('order', ORDER, '160_', order,
         [tick('day_2', 2, True), tick('day_2_again', 2, True), refused('day_1', 1), event('now_by_hand', by_hand('now', 'TRUE', 9, at=9)),
          tick('day_4', 4, True), event('reopen', by_hand('until:3', 'TRUE', 'window'), True), load('day_2_pack_again', '160_clock@2'),
          event('late_approval', approval('approval-v2'), True), load('original_pack_again', '160_timed_approval'), observe('late_by_observe', approval('approval-v3')),
          look('after_the_late_rows', True), tick('day_6', 6)]),
        ('late_order', ORDER, '160_', order, [tick('day_6', 6, True)]),
        ('allowance', GATES + ['15_low_budget', '161_allowance'], '161_', ['now', 'customer_approved', 'replacement_delivered'], [tick('day_1', 1, True)]),
        ('loan', ['162_loan'], '162_', loan,
         [tick('day_5', 5, True), event('box_by_hand', by_hand(c.box(G, 20), 'TRUE', '1'), True), tick('day_15', 15, True), tick('day_16', 16, True),
          tick('day_31', 31, True), load('renewal', '162_renewal'), tick('day_31_renewed', 31, True)]),
        ('loan_late', ['162_loan'], '162_', loan, [tick('day_16', 16, True)]),
        ('two_boxes', ['162_loan', '162_second_box'], '162_two_boxes_', loan,
         [tick('day_16', 16), tick('day_20', 20), tick('day_21', 21), load('sanction_again', '162_sanction_again'), look('admitted_until_the_next_tick'), tick('day_21_again', 21)]),
        ('pulls', ['163_bureau_pulls'], '163_', pulls,
         [tick('day_0', 0, True), tick('day_0_again', 0, True), tick('day_1', 1, True), load('day_0_pack_again', '163_clock@0'), refused('day_0_once_more', 0)]),
        ('weekly', ['163_weekly_pulls'], '163_weekly_', pulls,
         [tick('day_6', 6, True), tick('day_7', 7, True), tick('day_13', 13, True), event('now_by_hand_says_day_0', by_hand('now', 'TRUE', 0, final=True, at=0)),
          tick('day_13_again', 13, True), load('to_the_branch', '163_branch'), tick('day_13_in_the_branch', 13, True), load('back_to_lending', '163_lending'), tick('day_14', 14, True)]),
        ('due', GATES + ['164_due_by'], '164_', ['now', 'customer_approved', 'replacement_delivered', 'until:5', 'in-time:order_complete'],
         [tick('day_6_dry', 6), tick('day_6', 6, True), tick('day_7', 7)]),
        ('two_goals', GATES + ['164_due_by', '165_two_goals'], '165_', ['now', 'customer_approved', 'replacement_delivered', 'until:5', 'in-time:order_complete'],
         [tick('day_6', 6, True)]),
        ('called_late', ['00_goal', '01_domain', '02_methods', '04_admission', '164_called_late'], '164_called_', ['now', 'customer_approved', 'in-time:order_complete'], [tick('day_1', 1)]),
        ('two_scopes', ORDER, '166_', ['now', 'customer_approved', 'replacement_delivered', 'until:3', 'until:5', 'until:7', 'until:30'],
         [tick('day_2', 2), tick('day_3', 3), load('to_the_loan', '162_loan'), tick('day_6', 6), load('back_to_the_order', '00_goal'), look('after', True)]),
        ('offer', ['167_offer'], '167_', ['now', 'offer_approved', 'offer_shipped', 'offer_open', 'until:3', 'until:4'],
         [look('before_any_tick'), tick('day_2', 2), tick('day_4', 4), tick('day_5', 5)]),
        ('same_moment', ORDER, '168_', ['now', 'customer_approved', 'stock_reserved', 'until:3', 'until:5', 'until:8'],
         [tick('day_2', 2), tick('day_2_again', 2), load('hold_arrives', '168_stock_hold'), tick('day_2_new', 2), tick('day_2_once_more', 2)]),
        ('planted', ORDER, '169_', ['now', 'customer_approved', 'until:3', 'until:5', 'until:999999999999999999'],
         [tick('day_2', 2), event('decision_on_now', by_hand('now', 'TRUE', 99, final=True, at=99)),
          event('decision_on_a_window', by_hand('until:999999999999999999', 'FALSE', 'closed', final=True)), tick('day_4', 4, True), tick('day_4_again', 4),
          event('day_5_word_for_word', fact('now', 'TRUE', 5, c.SOURCE, final=True, at=5, scope='orgA/fulfillment')), tick('day_5', 5)]),
        ('refusals', ORDER, '160_', order,
         [tick('day_2', 2), refused('half_a_day', 2.5), refused('two_as_a_fraction', 2.0), refused('below_zero', -1), refused('true_for_a_moment', True),
          refused('text_for_a_moment', '3'), refused('no_moment', None), refused('too_far', 10 ** 18), refused('a_label_with_the_mark', 3, label='day clock@1 '),
          refused('a_label_that_is_no_text', 3, label=5), refused('execute_as_text', 3, execute='yes'), refused('execute_as_a_number', 3, execute=1), tick('day_3', 3)]),
        ('withdrawn', ORDER, '160_', order,
         [tick('day_2', 2), event('approval_withdrawn', fact('customer_approved', 'FALSE', 'approval-withdrawn', 'fixture/customer-approval')), tick('day_6', 6),
          event('late_approval', approval('approval-v2'), True)]),
        ('crowd', ORDER + ['169_shipping_pass'], '169_crowd_', ['now', 'fleet_ready', 'until:3', 'until:5', 'until:6', 'until:74'],
         [tick('day_2', 2), event('seventy_windows', fact('fleet_ready', 'TRUE', '1', 'fixture/depot', depends_on=[{'predicate': f'until:{n}', 'version': 'window'} for n in range(5, 75)])),
          tick('day_4', 4), tick('day_6', 6)]),
    ]


def counted(v, looks=0, runs=0):
    """(looks, runs) in plain data: a look is a dict holding a list under `runs`; a run is a dict with `trace` and `trace_root_sha256`."""
    if type(v) is dict:
        looks, runs = looks + (type(v.get('runs')) is list), runs + ('trace' in v and 'trace_root_sha256' in v)
        for x in v.values():
            looks, runs = counted(x, looks, runs)
    elif type(v) is list:
        for x in v:
            looks, runs = counted(x, looks, runs)
    return looks, runs


def walk(c, lab, files, label, watch, steps):
    """One walk on one State: every step with its result and what stood after it."""
    State, Kernel, pack, digest = lab['State'], lab['Kernel'], lab['pack'], lab['digest']

    def stood(s):   # what stands after a step, as plain data of its own
        return json.loads(json.dumps({
            'moment': c.moment(s), 'scope': s.scope, 'budget': s.budget, 'grants': sorted(s.grants), 'loaded': [e['pack'] for e in s.loaded],
            'reads': {p: s.fact(p)['truth'] for p in watch}, 'stored': {p: s.evidence.get(s.key(p)) for p in watch},
            'turned_away': sum(j.get('status') == 'DECISION_STANDS' for j in s.event_journal),
            'books': digest({'e': s.evidence, 'g': sorted(s.grants), 'b': s.budget, 'p': s.providers, 'l': s.loaded, 'j': s.event_journal, 'a': s.active_work})}))

    s = State.from_packs([pack(n) for n in files])
    k = Kernel(s)
    start = stood(s)
    done = []
    for asked in steps:
        step, kind = dict(asked), asked['kind']
        if kind == 'tick':
            result = c.tick(k, step['now'], execute=step['execute'], label=label)
            for stated in ([result['clock_pack']] + result.get('more_clock_packs', []) if 'clock_pack' in result else []):
                try:
                    held = pack(stated['id'])
                except OSError:
                    held = None
                if held != stated:
                    raise RuntimeError(f"{step['key']}: the tick stated {stated['id']}, which is not the pack its scenario file holds")
        elif kind == 'refused':
            try:
                c.tick(k, step['now'], execute=step.get('execute', True), label=step.get('label', label))
                result = {'refused': None}
            except ValueError as e:
                result = {'refused': str(e)}
        elif kind == 'event':
            result = k.on_event(step['row'], execute=step['execute'])
        elif kind == 'observe':
            result = {'stored': s.observe(step['row'])}
        elif kind == 'pack':
            s.apply(pack(step['pack']))
            result = {'applied': step['pack']}
        else:   # a look made without a tick
            result = k.run_standing(execute=step['execute'])
        step.update(result=result, after=stood(s))
        done.append(step)
    return {'packs': list(files), 'label': label, 'watch': list(watch), 'start': start, 'steps': done}


def scene(lab):
    import extensions.clock as c
    made = {'walks': {name: walk(c, lab, files, label, watch, steps) for name, files, label, watch, steps in walks(c)}}
    if counted(json.loads(json.dumps(made))) != (LOOKS, RUNS):   # counted as the record will hold it
        raise RuntimeError(f'the scene states LOOKS = {LOOKS} and RUNS = {RUNS} and recorded {counted(json.loads(json.dumps(made)))}')
    return made
