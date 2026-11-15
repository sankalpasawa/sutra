# Time (0.13.0-time, matrix gap 6, row R58, ruling R23): time is evidence a clock adapter states at a tick; the kernel has no word of it.
# A timed row rests on a window the clock publishes; a time-boxed permission is a grant with a box; an allowance is a name in the grant set.
# The clock packs below are authored by the adapter itself, as the standards rows are: `chain` walks one State through the moments of a
# recorded walk and writes every pack a tick states there, name and all (`<label>clock@<moment>`). It is a second, shorter telling of the
# walks than the scene's (tools/scenes/clock.py: only what the clock's packs depend on), and the two must agree: the scene ticks live and
# stops the build when a tick states anything but the pack its scenario file holds.
import json
from pathlib import Path
import kernel.core as _core
from kernel.core import State, Kernel
from extensions.clock import timed, due, box, allowance, tick, misnamed

_FILES = Path(_core.__file__).resolve().parents[1] / 'scenarios'   # the lab's scenario files: the built-in packs stand there already
_OWN = {}                                                           # the packs this file authors, by name


def _pack(name, **fields):
    """Author one pack of this file. A grant name that begins like a box or an allowance and is not one stops the build."""
    made = {'schema': 'sutra-extension/2', 'id': name, **fields}
    if misnamed(made):
        raise ValueError(f'REFUSED tools/packs/clock.py: {name} names {misnamed(made)}, which is no box and no allowance')
    pack(name, **fields)
    _OWN[name] = made


def _read(name):
    return _OWN[name] if name in _OWN else json.loads((_FILES / (name + '.json')).read_text())


def chain(label, before, *steps):
    """The clock's packs along one walk, authored as scenario files: the State the packs `before` make, then each step in turn. A step
    is a moment (a tick there: every pack it states is authored), the name of a pack (it arrives) or a row (it arrives as an event).
    A pack another chain authored already must be the same pack: the name of a clock pack says all that it holds."""
    s = State.from_packs([_read(n) for n in before])
    for step in steps:
        if type(step) is int:
            out = tick(Kernel(s), step, label=label)
            for made in ([out['clock_pack']] + out.get('more_clock_packs', []) if 'clock_pack' in out else []):
                if made['id'] not in _OWN:
                    _pack(made['id'], **{k: v for k, v in made.items() if k not in ('schema', 'id')})
                elif _OWN[made['id']] != made:
                    raise ValueError(f"REFUSED tools/packs/clock.py: two walks state another pack under the name {made['id']}")
        elif type(step) is str:
            s.apply(_read(step))
        else:
            s.observe(step)


ORDER = ['00_goal', '01_domain', '02_methods', '04_admission', '160_timed_approval']
GATES = ['00_goal', '01_domain', '02_methods', '03_approval', '04_admission']
G = 'action:disburse-loan@1'
by_hand = lambda predicate, truth, version, **more: dict({'predicate': predicate, 'truth': truth, 'verified': True, 'source': 'fixture/written-by-hand', 'version': version}, **more)

# A deadline and an approval that ran out (cases 67 and 67a): the approval counts until day 3 and the order is due by day 5.
_pack('160_timed_approval', evidence=[timed(fact('customer_approved', 'TRUE', version='approval-v1', source='fixture/customer-approval'), 3),
                                      due('order_complete', 5, source='fixture/owner-due-by')])
chain('160_', ORDER, 2, 4, 6)      # the walk `order`; its day 2 is the last pack of case 67a (the order ships in time)
chain('160_', ORDER, 6)            # first looked at on day 6: the last pack of case 67. The same pack as the walk's on day 6: a clock pack follows from the windows in use and the moment
chain('160_', ORDER, 2, 3)         # the walk `refusals`: the refused ticks between day 2 and day 3 state nothing
chain('160_', ORDER, 2, fact('customer_approved', 'FALSE', version='approval-withdrawn', source='fixture/customer-approval'), 6)   # the walk `withdrawn`: a window that only its own stored row names is still closed at its time

# An allowance that comes back (case 68): the budget case 24 ran out of is two units of compute and of money a day.
_pack('161_allowance', grants=[allowance('compute', 2, 1), allowance('money', 2, 1)])   # an allowance is a name in the grant set: only a pack gives it, never an evidence row or an event
chain('161_', GATES + ['15_low_budget', '161_allowance'], 1)

# The lending example. A bureau report that counts until day 30, a sanction that admits disbursal until day 15 (a boxed grant: the box is
# a name in the grant set beside the grant), disbursal due by day 7. Case 69 is this pack first looked at on day 16: the permission ran out.
_pack('162_loan', scope='orgA/lending', goals=['loan_disbursed'], budget={'compute': 10, 'money': 10, 'attention': 3}, preference=['compute', 'money', 'attention'],
      evidence=[timed(fact('bureau_report_clean', 'TRUE', version='report-1', source='fixture/bureau-report'), 30), due('loan_disbursed', 7, source='fixture/owner-due-by')],
      methods=[method('disburse-loan@1', 'loan_disbursed', ['bureau_report_clean'])],
      providers={'local-provider': 5}, grants=[G, box(G, 15)])
# Past day 30 the report has run out and the disbursal made on it reads unknown again. A fresh report and a fresh sanction then disburse a second time (a stated limit).
_pack('162_renewal', evidence=[timed(fact('bureau_report_clean', 'TRUE', version='report-2', source='fixture/bureau-report'), 60)], grants=[G, box(G, 45)])
chain('162_', ['162_loan'], 5, 15, 16, 31, '162_renewal', 31)   # the walk `loan`
chain('162_', ['162_loan'], 16)                                 # the walk `loan_late`: the last pack of case 69
# Two boxes on one grant: the later one counts. Given again with no fresh box, the grant admits until the next tick takes it away again.
_pack('162_second_box', grants=[box(G, 20)])
_pack('162_sanction_again', grants=[G])
chain('162_two_boxes_', ['162_loan', '162_second_box'], 16, 20, 21, '162_sanction_again', 21)

# A bureau that allows two report pulls a day, with three applicants waiting.
_pack('163_bureau_pulls', scope='orgA/lending', goals=['report_pulled_a', 'report_pulled_b', 'report_pulled_c'],
      budget={'compute': 10, 'money': 10, 'attention': 3, 'pulls': 2}, preference=['compute', 'money', 'attention', 'pulls'],
      methods=[method(f'pull-report-{x}@1', f'report_pulled_{x}', cost={'compute': 1, 'money': 0, 'attention': 0, 'pulls': 1}) for x in 'abc'],
      providers={'local-provider': 5}, grants=[f'action:pull-report-{x}@1' for x in 'abc'] + [allowance('pulls', 2, 1)])
chain('163_', ['163_bureau_pulls'], 0, 1)
# One pull a week: a period longer than one moment. The allowance is boxed until day 13; a smaller allowance on the same dimension and an
# allowance for a dimension the budget does not have stand beside it.
_WEEKLY = allowance('pulls', 1, 7)
_pack('163_weekly_pulls', scope='orgA/lending', goals=['report_pulled_a', 'report_pulled_b', 'report_pulled_c'],
      budget={'compute': 10, 'money': 10, 'attention': 3, 'pulls': 0}, preference=['compute', 'money', 'attention', 'pulls'],
      methods=[method(f'pull-weekly-{x}@1', f'report_pulled_{x}', cost={'compute': 1, 'money': 0, 'attention': 0, 'pulls': 1}) for x in 'abc'],
      providers={'local-provider': 5}, grants=[f'action:pull-weekly-{x}@1' for x in 'abc'] + [_WEEKLY, box(_WEEKLY, 13), allowance('pulls', 0, 7), allowance('energy', 5, 7)])
_pack('163_branch', scope='orgA/branch')      # the State moves to a scope that holds no row
_pack('163_lending', scope='orgA/lending')    # and back
chain('163_weekly_', ['163_weekly_pulls'], 6, 7, 13, by_hand('now', 'TRUE', 0, final=True, at=0), 13, '163_branch', 13, '163_lending', 14)

# A due-by with nothing else timed: the order of case 04, due by day 5. The due row carries its owner's own version.
_pack('164_due_by', evidence=[due('order_complete', 5, source='fixture/owner-due-by', version='due-by-1')])
chain('164_', GATES + ['164_due_by'], 6, 7)
# A due row its owner states as passed: late is whatever the due row reads.
_pack('164_called_late', evidence=[fact('in-time:order_complete', 'FALSE', source='fixture/owner-due-by')])
chain('164_called_', ['00_goal', '01_domain', '02_methods', '04_admission', '164_called_late'], 1)

# Two standing goals, where the first run makes the second hold: the shipment is a goal of its own, ahead of the order it completes.
_pack('165_two_goals', goals=['replacement_delivered', 'order_complete'])
chain('165_', GATES + ['164_due_by', '165_two_goals'], 6)

# Two scopes on one State (no pack of its own, so the label is a bare number): the order is ticked on days 2 and 3, the State moves to
# the loan, and the tick made there on day 6 states the windows of the order's scope too.
chain('166_', ORDER, 2, 3, '162_loan', 6)

# A rule and a step that name a window directly, beside a decision that does not lapse: the offer stands open until day 3 and may ship
# until day 4. The pack also holds a step whose effect is the rule's window: once the clock has closed the window no plan runs it.
_pack('167_offer', scope='orgA/offers', goals=['offer_shipped', 'offer_open'], budget={'compute': 10, 'money': 10, 'attention': 3}, preference=['compute', 'money', 'attention'],
      evidence=[dict(fact('offer_approved', 'TRUE', source='fixture/owner-decision'), final=True)],
      rules=[rule('R-OFFER@1', 'offer_open', [['offer_approved', 'until:3']])],
      methods=[method('ship-offer@1', 'offer_shipped', ['offer_approved', 'until:4']),
               method('reopen-offer@1', 'until:3', cost={'compute': 0, 'money': 0, 'attention': 0})],
      providers={'local-provider': 2}, grants=['action:ship-offer@1', 'action:reopen-offer@1'])
chain('167_', ['167_offer'], 2, 4, 5)

# Something new at a moment the clock has already stated: a stock hold that counts until day 8 arrives on day 2, after the day's tick.
# Its window was never published, so the hold is not believed until the next tick, which states a second pack for day 2 under a name of its own.
_pack('168_stock_hold', evidence=[timed(fact('stock_reserved', 'TRUE', source='fixture/warehouse'), 8)])
chain('168_', ORDER, 2, '168_stock_hold', 2)

# Rows written by hand on the clock's own names arrive as events (the walk `planted`; the scene holds the rows): a decision on `now`
# and a decision on a window no moment can pass. Neither stops the clock. Then the clock's own row for day 5, written by hand word
# for word before the clock says it: the tick of day 5 still states its pack, so the record of packs carries the moment.
chain('169_', ORDER, 2, by_hand('now', 'TRUE', 99, final=True, at=99), by_hand('until:999999999999999999', 'FALSE', 'closed', final=True), 4, 4,
      {'predicate': 'now', 'truth': 'TRUE', 'verified': True, 'final': True, 'source': 'adapter:clock@1', 'version': 5, 'at': 5, 'scope': 'orgA/fulfillment'}, 5)

# One row that names seventy windows (the walk `crowd`): more rows than one clock pack carries, so the tick states them in two packs,
# what closes first. However many windows a row names, the clock states them all and time goes on. The shipping grant is boxed until
# day 5 here, so the tick of day 6 has a grant to take away as well: the revoke goes with the first of its two packs.
_pack('169_shipping_pass', grants=[box('action:ship-replacement@1', 5)])
chain('169_crowd_', ORDER + ['169_shipping_pass'], 2, dict(fact('fleet_ready', 'TRUE', source='fixture/depot'), depends_on=[{'predicate': f'until:{n}', 'version': 'window'} for n in range(5, 75)]), 4, 6)
