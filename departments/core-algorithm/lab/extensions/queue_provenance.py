"""The decision-provenance row (matrix row R91), projected from a run's trace OUTSIDE the kernel.

The kernel's gate writes one ADMISSION line into a run's hash chain each time it is asked: once for every complete plan
before one is chosen, and once more for each step just before its effect. The line says which methods, whether they
were accepted, the blockers and the cost. This module reads those lines and says each one in the words of the
decision-provenance row (sutra/os/native/schemas/decision-provenance-row.schema.json), one row per gate decision:

  granted        the gate accepted: every grant is held, every provider has a free slot, every cost fits the budget.
  denied         the gate did not accept. The row names each line that failed: the grant that is missing, the provider
                 that is short, the budget dimension that does not fit, with what was needed and what was there.
                 A standing decision that says no (the kernel's REFUSED line: a final FALSE row) reads as denied too.
  escalated      the gate accepted a step and the step parked on a question to a named party (an ask, 0.8.0): the
                 decision is that party's now. The row cites the ask receipt (approval_ref) and names who was asked.
  not_evaluated  the run never reached the gate (it blocked before any plan existed): one row, with the block reason.

The lines that decided are the row's `factors`, each {type, value, source_ref}; source_ref is the trace line the factor
explains. `method` (what was asked for), `grant_held` or `grant_missing`, `provider_free` or `provider_short`,
`budget_fits` or `budget_short` are the gate's own lines. Beyond the gate:

  asked     on an escalated row: who was asked what, citing the receipt line.
  stopped   on a step the gate admitted and that then did not run (a prerequisite that is not true at its turn, the
            handler's refusal or failure, a return that cannot be a receipt): the reason the kernel logged, citing its
            STEP_STOPPED line. The row still reads granted, and has no receipt. A step the kernel stopped before it
            asked the gate (its method was gone by then) has no gate line, and so no row: nothing here says it stopped.
  decision  a yes or a no somebody gave. A no is the kernel's REFUSED line. A yes is cited on every granted row one of
            whose methods requires the decided fact, when this run's chain read that fact as true (RETAIN, the line
            cited) and a chain closed the question on it with a yes from the same source (ASK_CLOSED, in this run or
            in an earlier run of the same call). Where no chain handed in closes the question, nothing proves the
            fact was a decision, and the row cites none.
  blocked   on the not_evaluated row: the block reason.

approval_ref is the receipt of a question: on an escalated row the question just asked, on a granted row the question
whose yes it rests on (the first, when there are several), on a no the question it answered (when a chain handed in
closes it). output_ref is the receipt of a granted step that ran. channels names who was asked, or the source of the
decision as the chain gives it.

A trace does not say which grant, which provider or how much budget was there: the gate's books do. So the projection
is handed the books as they stood before the first run and keeps them itself, paying each receipt as the kernel does.
It runs nothing. The caller reads the books, looks, and hands both in:

    before = books(kernel.s)                        # first: the books the gate is about to use
    result = kernel.run_standing(execute=True)      # the look is the caller's, whatever the projection then says
    rows = decisions(result['runs'], before)

It refuses (ValueError) books that do not explain the trace: every line it finds failing must be a blocker the kernel
logged, and every cost the methods' own. The books it keeps change only by receipts, so a gate that a handler changed
in the middle of a run is not explained either. It refuses a trace whose hash chain does not hold, a step at the gate
that is followed by neither its effect nor its stop, and anything that is not plain data. Each run, and the books, is
copied on its own (at most 100000 items each, the kernel's bound for anything handed in), so a long look is read run
by run. A copy goes sixteen levels below the run, and a receipt stands four levels down in its run's trace: what a
handler returned is read twelve levels deep, and a run that holds a deeper receipt is refused as not plain data.
It changes nothing: not the runs and not the books it was handed.

The row carries the schema's seventeen names, in its order. Seven of them the lab cannot compute and leaves null: ts
(the lab has no clock), operator_id, charter_ref, domain_ref, task_tier, intent_type and reversibility. With ts and
operator_id null the row is not a valid row of that schema as it stands. turn_id is the run's trace root, so two runs
with the same hash chain (the same blocked goal looked at twice) give rows with the same turn_id and decision_seq.
All of this is a reading of a local model's own record: nothing is appended to any log."""
from __future__ import annotations
from kernel.core import plain, digest, canonical

FIELDS = ('schema_version', 'turn_id', 'decision_seq', 'ts', 'operator_id', 'charter_ref', 'domain_ref', 'task_tier', 'phase',
          'intent_type', 'factors', 'authority_verdict', 'reversibility', 'approval_ref', 'work_ref', 'output_ref', 'channels')
VERSION = 'lab-decision-provenance/1'
BOUND = 100000   # the most one copy may hold, keys and containers counted: kernel.core.plain's bound for anything handed in
UNEXPLAINED = 'These books do not explain this trace'
BROKEN = 'The hash chain of this trace does not hold'
NOT_KERNEL = 'This is not a trace the kernel writes'
NOT_DATA = 'Not run records and the books they started from'
TOO_LARGE = 'Too large to read: one run, or the books, holds more than 100000 items'


def books(state) -> dict:
    """The gate's books as they stand, as plain data: the grants held, the provider slots free, the budget left, and for
    each method the grant, the provider and the cost the gate reads, and the facts its step requires."""
    return {'grants': sorted(state.grants), 'providers': dict(state.providers), 'budget': dict(state.budget),
            'methods': {mid: {'grant': m['grant'], 'provider': m['provider'], 'cost': dict(m.get('cost', {})), 'requires': list(m.get('requires', []))}
                        for mid, m in state.methods.items()}}


def _copy(v) -> dict:
    """A plain copy of one run, or of the books: only data is read and nothing handed in is changed."""
    left = [BOUND]   # plain counts down in this list, so afterwards it says whether the size or the kind of data was the trouble
    try:
        if type(v) is not dict:
            raise ValueError
        return plain(v, 16, left)
    except ValueError:
        raise ValueError(TOO_LARGE if left[0] < 0 else NOT_DATA) from None


def _chain(run) -> bool:
    trace = run['trace']
    return (bool(trace) and run['trace_root_sha256'] == trace[-1]['sha256']
            and all(row['seq'] == i + 1 and row['prev_sha256'] == (trace[i - 1]['sha256'] if i else 'GENESIS')
                    and row['sha256'] == digest({k: v for k, v in row.items() if k != 'sha256'}) for i, row in enumerate(trace)))


def _row(run, seq, verdict, phase, factors, approval=None, output=None, channels=()):
    return {'schema_version': VERSION, 'turn_id': run['trace_root_sha256'], 'decision_seq': seq, 'ts': None, 'operator_id': None,
            'charter_ref': None, 'domain_ref': None, 'task_tier': None, 'phase': phase, 'intent_type': None, 'factors': factors,
            'authority_verdict': verdict, 'reversibility': None, 'approval_ref': approval, 'work_ref': run['goal'],
            'output_ref': output, 'channels': list(channels)}


def _admission(d, ref, table, held, free, left):
    """The lines the gate read for one ADMISSION, and the blockers they give. Refused when they are not the kernel's."""
    methods = d['methods']
    factors = [{'type': 'method', 'value': m, 'source_ref': ref} for m in methods]
    failed, use = set(), {}
    for m in methods:
        grant, provider = table[m]['grant'], table[m]['provider']
        factors.append({'type': 'grant_held' if grant in held else 'grant_missing', 'value': grant, 'source_ref': ref})
        if grant not in held:
            failed.add('AUTHORITY_REQUIRED')
        use[provider] = use.get(provider, 0) + 1
    for provider, need in use.items():
        has = free.get(provider, 0)
        factors.append({'type': 'provider_free' if has >= need else 'provider_short', 'value': f'{provider}: needs {need}, has {has}', 'source_ref': ref})
        if has < need:
            failed.add('PROVIDER_REQUIRED')
    for dim, need in d['cost'].items():
        factors.append({'type': 'budget_fits' if need <= left[dim] else 'budget_short', 'value': f'{dim}: needs {need}, has {left[dim]}', 'source_ref': ref})
        if need > left[dim]:
            failed.add('RESOURCE_REQUIRED')
    summed = {dim: sum(table[m]['cost'].get(dim, 0) for m in methods) for dim in left}
    if canonical(summed) != canonical(d['cost']) or sorted(failed) != d['blockers'] or d['accepted'] is not (not failed):
        raise ValueError(UNEXPLAINED)
    return factors, failed


def _rows_of(run, table, held, free, left, closed) -> list:
    """The rows of one run. The books (held, free, left) and the questions closed so far (closed) are the call's running copies:
    this run's receipts are paid in them and the questions its chain closes are added."""
    if not _chain(run):
        raise ValueError(BROKEN)
    trace, scope = run['trace'], run['scope']
    read = {}   # where this run's chain first read each fact as true: fact -> its RETAIN line
    for e in trace:
        if e['operation'] == 'ASK_CLOSED':
            closed[e['data']['ask']] = e['data']   # 'scope|fact', as the ask kind's books name a question: the receipt it closed, the answer, who gave it
        elif e['operation'] == 'RETAIN':
            read.setdefault(e['data']['predicate'], e)

    def answered(fact, truth, source):   # the receipt of the question on this fact that a chain closed with this answer from this source, or None
        end = closed.get(f'{scope}|{fact}')
        return end['receipt'] if end is not None and end['truth'] == truth and end.get('source') == source else None

    mine, selected = [], False
    for i, e in enumerate(trace):
        op, d, ref = e['operation'], e['data'], f"trace:{e['seq']}"
        if op == 'SELECT':
            selected = True   # before the selection the gate is asked about whole plans, after it about one step at a time
        elif op == 'ADMISSION':
            factors, failed = _admission(d, ref, table, held, free, left)
            receipt = stop = after = None
            if selected:      # one step of the plan the gate admitted: the kernel's very next line is its effect (a receipt) or its stop
                after = trace[i + 1]
                one = len(d['methods']) == 1 and not failed   # on books that only receipts change, a step of an admitted plan is never turned away
                if one and after['operation'] == 'LOCAL_EFFECT' and after['data']['receipt']['method'] == d['methods'][0]:
                    receipt = after['data']['receipt']
                elif one and after['operation'] == 'STEP_STOPPED' and after['data']['method'] == d['methods'][0]:
                    stop = after
                else:
                    raise ValueError(NOT_KERNEL)
            phase = 'step' if selected else 'plan'
            asked = receipt.get('ask') if receipt and receipt.get('parked') is True else None
            if failed:
                mine.append(_row(run, len(mine), 'denied', phase, factors))
            elif isinstance(asked, dict):
                factors.append({'type': 'asked', 'value': f"{asked['to']}: {asked['predicate']}", 'source_ref': f"trace:{after['seq']}"})
                mine.append(_row(run, len(mine), 'escalated', phase, factors, approval=receipt['sha256'], channels=[asked['to']]))
            else:
                cited, who = [], []   # the yeses this row rests on: a prerequisite this run read as true, whose question a chain closed with a yes from the same source
                for fact in dict.fromkeys(fact for m in d['methods'] for fact in table[m]['requires']):
                    seen = read.get(fact)
                    source = seen['data'].get('source') if seen is not None else None
                    question = answered(fact, 'TRUE', source) if seen is not None else None
                    if question is not None:
                        factors.append({'type': 'decision', 'value': f"{fact}: TRUE, decided by {source}", 'source_ref': f"trace:{seen['seq']}"})
                        cited.append(question)
                        who += [source] if type(source) is str else []
                if stop:
                    factors.append({'type': 'stopped', 'value': stop['data']['reason'], 'source_ref': f"trace:{stop['seq']}"})
                mine.append(_row(run, len(mine), 'granted', phase, factors, approval=cited[0] if cited else None,
                                 output=receipt['sha256'] if receipt else None, channels=dict.fromkeys(who)))
        elif op == 'REFUSED':   # a standing decision says no: nobody is asked again, and no method may overturn it
            said = d.get('source')
            mine.append(_row(run, len(mine), 'denied', 'decision', [{'type': 'decision', 'value': f"{d['predicate']}: FALSE, decided by {said}", 'source_ref': ref}],
                             approval=answered(d['predicate'], 'FALSE', said), channels=[said] if type(said) is str else []))
        elif op == 'LOCAL_EFFECT':   # a receipt exists, so the step is paid: its cost and one slot of its provider, as the kernel does
            m = table[d['receipt']['method']]
            for dim, v in m['cost'].items():
                left[dim] -= v
            free[m['provider']] -= 1
    if not mine:
        block = next((e for e in trace if e['operation'] == 'BLOCK'), None)
        mine.append(_row(run, 0, 'not_evaluated', None, [{'type': 'blocked', 'value': block['data']['reason'], 'source_ref': f"trace:{block['seq']}"}] if block else []))
    return mine


def decisions(runs, books) -> list:
    """One row per gate decision of these runs, in the order the kernel made them. `runs` is a list of run records in the order
    they ran on one State; `books` is books(state) as it stood before the first of them. Runs nothing and changes nothing."""
    if type(runs) is not list:
        raise ValueError(NOT_DATA)
    b = _copy(books)
    try:
        if type(b['grants']) is not list:
            raise TypeError
        left, free, held, table, closed = b['budget'], b['providers'], b['grants'], b['methods'], {}   # b is this call's own copy: paying in it touches nothing of the caller's
        rows = []
        for run in runs:
            rows += _rows_of(_copy(run), table, held, free, left, closed)   # a plain copy of each run on its own: the bound is per run, not per look
        return rows
    except (KeyError, TypeError, AttributeError, IndexError):
        raise ValueError(NOT_DATA) from None
