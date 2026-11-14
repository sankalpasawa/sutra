"""Numbers at the evidence door (matrix gap 9, ruling R22): an adapter OUTSIDE the kernel, in the pattern of standards.py.

The kernel never reads a number and never compares one. This module makes the rows a pack or an event carries, and reads
the kernel's own record:
  measured       a number as evidence: a verified TRUE row ("the number is known") whose `value` is exact text and whose
                 version this adapter sets as the digest of the reading (predicate, value, unit, label, source). A new
                 value is a new version, whatever label the caller reuses; one number spelled two ways is one version.
  compared       one comparison as evidence: a verified TRUE or FALSE row with this adapter as its source, a version that
                 is the digest of what it compared (the number and its version, the operator, the bound, every number in
                 lowest terms), `depends_on` the number row (and the bound row, when the bound is another number row) at
                 its version, and under `compares` the recipe to redo it. The kernel reads it like any row: when the
                 number changes, the comparison and everything made on it read UNKNOWN.
  band           both rows of a band from ONE bound in one call: the operator and its negation, so exactly one is TRUE.
                 Each row names the other under `compares.partner`; the name is no part of the row's version, so one
                 comparison has one version whether `compared` or `band` made it.
  renumber       a new reading while a State is running, all or nothing: the number is stored, every stored comparison
                 that cites it is made again from the numbers on the books, and the kernel takes one look per standing
                 goal the number affects. All of it happens on a copy first: a reading the State cannot take whole, or
                 a look that raises, changes nothing.
  comparisons    the comparison rows a run's trace names, with number, operator, bound and verdict; `attach` writes them
                 into the run record bound to its trace root (the kernel's trace carries source and version only). A
                 comparison under a row the run held (a finding filed earlier) is not named in the trace and not listed.
  amount         a fraction of cost as a whole number of a smaller unit (usd 0.42 is 42 `usd_cents`); the kernel's
                 amounts stay whole numbers below 10**18, and an amount the kernel would refuse is refused here.
  cost_receipts  what each executed step cost, read from the gate's own ADMISSION row of a trace that hashes to its
                 root; a `cost` a handler wrote into its receipt is never read.
A number is exact text: ASCII digits with one optional point ('0.8'), or digits/digits ('4/5'); at most 64 characters; no
sign, no exponent, no spaces; never a float. Numbers are compared as exact ratios: '0.30' equals '0.3', '4/5' equals '0.8'.
All of this is local model evidence: the adapter does not measure anything, it records the number it is handed.
It registers no action kind and imports the standard library and the kernel's `digest`, nothing else."""
from __future__ import annotations
import copy
from fractions import Fraction
from kernel.core import digest

SOURCE = 'adapter:numbers/compare@1'
NEGATED = {'<': '>=', '<=': '>', '>': '<=', '>=': '<', '==': '!=', '!=': '=='}   # the six operators, each with the one that says the opposite
_HOLDS = {'<': lambda a, b: a < b, '<=': lambda a, b: a <= b, '>': lambda a, b: a > b, '>=': lambda a, b: a >= b,
          '==': lambda a, b: a == b, '!=': lambda a, b: a != b}
_DIGITS = frozenset('0123456789')
LIMIT = 10 ** 18   # the kernel takes an amount (a cost, a budget entry, a provider capacity) only below this


def exact(text) -> Fraction:
    """The adapter's own closed grammar: digits, digits.digits, or digits/digits with a divisor that is not zero. It never
    calls the standard library's parser, which also takes signs, exponents, spaces and, on newer interpreters, underscores."""
    if type(text) is str and 0 < len(text) <= 64:
        marks = [ch for ch in text if ch not in _DIGITS]
        if not marks:
            return Fraction(int(text))
        head, _, tail = text.partition(marks[0])
        if len(marks) == 1 and marks[0] in './' and head and tail and (marks[0] == '.' or int(tail)):
            return Fraction(int(head), int(tail)) if marks[0] == '/' else Fraction(int(head + tail), 10 ** len(tail))
    raise ValueError('A number is exact text: digits with one optional point, or digits/digits')


def _lowest(n: Fraction) -> str:   # one spelling per number: '0.8', '0.80' and '4/5' are all '4/5'
    return f'{n.numerator}/{n.denominator}'


def _names(**given) -> None:
    for name, text in given.items():
        if type(text) is not str or not text:
            raise ValueError(f'The {name} of a number row is a name')


def measured(predicate, value, source, label, unit='1', scope=None) -> dict:
    """A number as evidence. `label` is the caller's name for the reading (a run, a day); the version is not the label but
    the digest of the whole reading, so two readings with different values never share a version."""
    n = exact(value)
    _names(predicate=predicate, source=source, label=label, unit=unit)
    if source == SOURCE:
        raise ValueError('A number does not come from the comparison adapter')
    reading = {'predicate': predicate, 'value': _lowest(n), 'unit': unit, 'label': label, 'source': source}
    row = {'predicate': predicate, 'truth': 'TRUE', 'verified': True, 'source': source, 'version': 'num-' + digest(reading)[:16],
           'value': value, 'unit': unit, 'label': label, 'evidence_kind': 'NUMBER'}
    if scope is not None:
        _names(scope=scope)
        row['scope'] = scope
    return row


def _number(row) -> tuple:
    """A row `measured` made, read again by exact type and rebuilt here: the adapter works on its own copy, never the
    caller's, and a row with a key that is not plain text is refused before anything of it is read."""
    try:
        if type(row) is not dict or any(type(k) is not str for k in row):
            raise ValueError
        again = measured(row.get('predicate'), row.get('value'), row.get('source'), row.get('label'), row.get('unit'), row.get('scope'))
        if set(row) != set(again) or any(type(row[k]) is not type(v) or row[k] != v for k, v in again.items()):
            raise ValueError
    except ValueError:
        raise ValueError('Not a number row this adapter made') from None
    return again, exact(again['value'])


def _same_number(recipe) -> dict:
    """The recipe with every number in its one spelling (lowest terms). A comparison's version is the digest of this, so
    the same numbers spelled another way are the same comparison and nothing made on it is undone."""
    one = lambda part: {k: (_lowest(exact(v)) if k in ('value', 'literal') else v) for k, v in part.items()}
    return dict(recipe, number=one(recipe['number']), bound=one(recipe['bound']))


def _compare(number, op, bound, predicate, partner=None) -> dict:
    number, left = _number(number)
    _names(predicate=predicate)
    if type(op) is not str or op not in NEGATED:
        raise ValueError('An operator is one of < <= > >= == !=')
    cites = [{'predicate': number['predicate'], 'version': number['version']}]
    if type(bound) is dict:   # the bound is another number row (a threshold kept as policy): the comparison rests on both
        bound, right = _number(bound)
        if bound.get('scope') != number.get('scope') or bound['unit'] != number['unit'] or bound['predicate'] == number['predicate']:
            raise ValueError('A bound row is another number of the same scope and unit')
        cites.append({'predicate': bound['predicate'], 'version': bound['version']})
        against = {'predicate': bound['predicate'], 'value': bound['value'], 'version': bound['version']}
    else:                     # a literal bound is read in the number's unit
        right = exact(bound)
        against = {'literal': bound}
    if predicate in (number['predicate'], against.get('predicate')):
        raise ValueError('A comparison has a predicate of its own')
    recipe = {'number': {'predicate': number['predicate'], 'value': number['value'], 'version': number['version']}, 'op': op, 'bound': against}
    version = 'cmp-' + digest(_same_number(recipe))[:16]   # the digest of what was compared and of nothing else: the name of a band's other row is no part of it
    if partner is not None:
        recipe['partner'] = partner
    row = {'predicate': predicate, 'truth': 'TRUE' if _HOLDS[op](left, right) else 'FALSE', 'verified': True, 'source': SOURCE,
           'version': version, 'depends_on': cites, 'compares': recipe, 'evidence_kind': 'COMPARISON'}
    if 'scope' in number:
        row['scope'] = number['scope']
    return row


def compared(number, op, bound, predicate) -> dict:
    """One comparison as evidence: `number op bound`, where `number` is a row `measured` made and `bound` is exact text or
    another such row. FALSE is a finding, not an error."""
    return _compare(number, op, bound, predicate)


def band(number, op, bound, inside, outside) -> list:
    """Both rows of a band from one bound in one call: `inside` reads `number op bound`, `outside` reads the negated
    operator on the same number and bound, and each names the other, so they are made again together or not at all."""
    _names(inside=inside, outside=outside)
    if inside == outside or type(op) is not str or op not in NEGATED:
        raise ValueError('A band is two predicates and one operator of < <= > >= == !=')
    return [_compare(number, op, bound, inside, outside), _compare(number, NEGATED[op], bound, outside, inside)]


def _mates(c, d, p, q) -> bool:   # two stored recipes are the two rows of one band: one number, one bound, opposite operators, each naming the other
    side = lambda x: (x['number']['predicate'], x['bound'].get('predicate'), x['bound'].get('literal'))
    return c.get('partner') == q and d.get('partner') == p and side(c) == side(d) and d['op'] == NEGATED.get(c['op'])


def renumber(kernel, row, execute: bool = False) -> dict:
    """A new reading of a number (also of a number row that comparisons use as their bound) while a State is running.
    Refused with ValueError, and then no stored row and no journal row has changed, when the row is not a number row this
    adapter made, is for another scope, would take the place of a row that is not a number or change its unit, when a
    decision stands on its fact or on a comparison it feeds, or when a comparison it feeds cannot be made again whole (a
    band whose other row is gone, a second number that is no longer on the books). Otherwise the number and the
    comparisons made again are stored on a copy of the State and the kernel takes its look there; only when the look has
    returned does the State take the copy's place, so a look that raises leaves the State as it was too (also the
    kernel's own refusal of an `execute` that is not exactly true or false). It returns what `Kernel.on_event` returns
    for the number, with `remade` naming the comparisons made again. The adapter keeps no order of readings: the one
    handed in last stands, also an older one delivered late (time is evidence the caller compares first)."""
    try:
        s = kernel.s
        new, _ = _number(row)
        new = dict(new, scope=new.get('scope', s.scope))
        if new['scope'] != s.scope:
            raise ValueError('A number for another scope is not taken here')
        mine = s.scope + '|'
        books = {k[len(mine):]: r for k, r in s.evidence.items() if k.startswith(mine)}
        old = books.get(new['predicate'])
        if old is not None and old.get('final'):
            raise ValueError('A decision stands on this number')
        if old is not None:
            try:
                unit = _number(old)[0]['unit']
            except ValueError:
                raise ValueError('A number takes the place of a number only') from None
            if unit != new['unit']:
                raise ValueError('A new reading keeps the unit of the number it replaces')
        cites = lambda r: (r.get('source') == SOURCE and type(r.get('compares')) is dict
                           and new['predicate'] in (r['compares']['number']['predicate'], r['compares']['bound'].get('predicate')))
        now = lambda ref: new if ref == new['predicate'] else books.get(ref)   # the new reading, or the number on the books
        again = []
        for p, old in books.items():
            if not cites(old):
                continue
            c = old['compares']
            mate = c.get('partner')
            if mate is not None and not (mate in books and cites(books[mate]) and _mates(c, books[mate]['compares'], p, mate)):
                raise ValueError('A band is made again whole or not at all')
            bound = now(c['bound']['predicate']) if 'predicate' in c['bound'] else c['bound']['literal']
            again.append(_compare(now(c['number']['predicate']), c['op'], bound, p, mate))
        rows = [new] + again   # the number first, then the comparisons made on it
        trial = copy.deepcopy(s, {id(s.actions): s.actions})   # the kernel's own door, on a copy, before the State is touched (the registry is shared, as in `apply`)
        if not all(trial.observe(r) for r in rows):   # a decision stands on a row of the band, also one made under this adapter's name
            raise ValueError('The kernel would turn this number or a comparison away')
    except (KeyError, TypeError, AttributeError) as e:
        raise ValueError(f'Not a number this State can take: {e!r}') from None
    kernel.s = trial   # the look is taken on the copy as well: one journal row per standing goal the number affects
    try:
        out = kernel.on_event(new, execute=execute)
    finally:
        kernel.s = s
    s.__dict__.update(trial.__dict__)   # all of it or none of it, as `State.apply` does
    return dict(out, remade=[r['predicate'] for r in again])


def comparisons(result, state) -> list:
    """The comparisons a run's trace names: every stored comparison row whose predicate the trace names in a row where
    the kernel read it (a CYCLE_LIMIT row names a predicate the kernel did not read), in the order the trace names
    them, with what was compared, the verdict as stored, and what the kernel reads (`reads` is UNKNOWN when a number
    the row cites is not on the books at the cited version). A comparison that stands under a row the run held (the
    finding an earlier look filed) is not named in the trace and is not listed. Made right after the run, on the State
    the run was made on: refused with ValueError when the State is in another scope, or when the run's own trace shows
    that the books have moved on (a comparison the run held, by its RETAIN row, no longer reads TRUE at that version,
    or one it did not hold reads TRUE now). A run that held no comparison cannot show it: made late, its block states
    the numbers that are on the books then."""
    if state.scope != result.get('scope'):
        raise ValueError('The State has moved to another scope since this run')
    held = {e['data'].get('predicate'): e['data'].get('version') for e in result.get('trace', []) if e['operation'] == 'RETAIN'}
    out = []
    for p in dict.fromkeys(e['data'].get('predicate') for e in result.get('trace', []) if e['operation'] != 'CYCLE_LIMIT'):
        row = state.evidence.get(state.key(p)) if type(p) is str else None
        if row is not None and row.get('source') == SOURCE and type(row.get('compares')) is dict:
            c, reads = row['compares'], state.fact(p)['truth']
            if (reads == 'TRUE') != (p in held) or (p in held and held[p] != row.get('version')):
                raise ValueError('The books have moved on since this run')
            out.append({'predicate': p, 'number': c.get('number'), 'operator': c.get('op'), 'bound': c.get('bound'), 'verdict': row['truth'],
                        'source': SOURCE, 'version': row.get('version'), 'reads': reads})
    return copy.deepcopy(out)


def attach(run, state) -> dict:
    """Write each run's comparisons into its record, bound to the kernel's hash-chained trace (trace root + sha256 of the
    list), the way the Learner binds a learning list. A run whose trace names no comparison gets no block."""
    for r in run.get('runs', []):
        rows = comparisons(r, state)
        if rows:
            r['comparisons'] = rows
            r['comparisons_record'] = {'source_trace': r.get('trace_root_sha256'), 'comparisons_sha256': digest(rows)}
    return run


def amount(value, per_unit) -> int:
    """A fraction of cost as a whole number of a smaller unit: amount('0.42', 100) is 42 (usd as `usd_cents`). Refused when
    the unit cannot hold the value exactly, and when the result is not an amount the kernel takes (below 10**18). The
    unit belongs in the dimension's name; the kernel refuses a cost in a dimension the budget does not have."""
    if type(per_unit) is not int or per_unit < 1:
        raise ValueError('A unit is a whole number of parts, one or more')
    n = exact(value) * per_unit
    if n.denominator != 1:
        raise ValueError('The unit cannot hold this amount exactly')
    if n.numerator >= LIMIT:
        raise ValueError('The kernel takes an amount below 10**18')
    return n.numerator


def cost_receipts(result) -> dict:
    """What each executed step cost, from the kernel's own record: for every LOCAL_EFFECT row of the trace, the cost on the
    accepted ADMISSION row that sits directly before it and names only that step. Bound to the trace root. Raises
    ValueError when the trace does not hash to its root, when that pairing does not hold, or when the steps do not add up
    to the cost of the run (numbers are compared as JSON: 1 is not 1.0, and a row numbered 2.0 is not row 2); and when
    what it is handed is no run record at all (a row without its fields, a step without its receipt)."""
    try:
        return _receipts(result)
    except (KeyError, TypeError, AttributeError, IndexError) as e:
        raise ValueError(f'Not a run record with a trace: {e!r}') from None


def _receipts(result) -> dict:
    trace = result.get('trace', [])
    prev = 'GENESIS'
    for i, e in enumerate(trace):
        if type(e.get('seq')) is not int or e['seq'] != i + 1 or e.get('prev_sha256') != prev or e.get('sha256') != digest({k: v for k, v in e.items() if k != 'sha256'}):
            raise ValueError('The trace does not hash to its root')
        prev = e['sha256']
    if result.get('trace_root_sha256') != prev:
        raise ValueError('The trace does not hash to its root')
    steps = []
    for i, e in enumerate(trace):
        if e['operation'] != 'LOCAL_EFFECT':
            continue
        receipt = e['data']['receipt']
        gate = trace[i - 1] if i else {'operation': None}
        if gate['operation'] != 'ADMISSION' or gate['data'].get('methods') != [receipt['method']] or gate['data'].get('accepted') is not True:
            raise ValueError('No accepted admission row sits directly before this step')
        steps.append({'method': receipt['method'], 'receipt': receipt['sha256'], 'cost': dict(gate['data']['cost'])})
    if [x['receipt'] for x in steps] != [x['sha256'] for x in result.get('model_receipts', [])]:
        raise ValueError('The receipts of the run are not the receipts of its trace')
    total = {dim: sum(x['cost'][dim] for x in steps) for dim in (steps[0]['cost'] if steps else {})}
    if steps and digest(total) != digest(result.get('cost')):
        raise ValueError('The step costs do not add up to the cost of the run')
    return {'steps': steps, 'total': total, 'source_trace': result.get('trace_root_sha256'), 'steps_sha256': digest(steps)}
