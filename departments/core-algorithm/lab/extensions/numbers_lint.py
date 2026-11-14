"""The authoring conventions for packs that carry numbers (matrix gap 9, ruling R22), held OUTSIDE the kernel: when the
packs are authored (tools/packs/numbers.py), in the tests, and again by the independent checks in their own words. The
kernel accepts every pack this lint refuses: what the lint holds is a convention, not a kernel guarantee.
  problems(packs)          the ordered packs of one case -> what is wrong, in plain words ([] when nothing is)
  ranked(goals, impact)    the order of a pack's goals: higher impact first
  shortfall(result, left)  for a look that stopped because a plan did not fit: the dimension, the need and what was left
  attach_shortfall(run, budget_after)   write that into every such run of a standing evaluation
The lint does not keep books of its own: it hands every evidence row of the packs, in order, to the kernel's own evidence
door (`State.observe`) and reads what the door stored. So a row that is not verified is ignored here as there, a decision
stands here as there, and every row is held in its own scope. Ranking and the ceiling are pack conventions: they add no
line to extensions/numbers.py and none to the kernel."""
from __future__ import annotations
from kernel.core import State, digest
from extensions.numbers import SOURCE, exact, measured, compared, band

BASE = ('compute', 'money', 'attention')   # the dimensions every State starts with


def ranked(goals, impact) -> list:
    """Higher impact first; an impact is exact text, as every number here. Goals with equal impact must already be listed
    by name, so the order is the same whether it is read as "by name" or as "in the order given"."""
    if (type(goals) is not list or type(impact) is not dict or any(type(g) is not str for g in goals)
            or len(set(goals)) != len(goals) or set(goals) != set(impact)):
        raise ValueError('Every goal has one impact')
    order = sorted(goals, key=lambda g: -exact(impact[g]))   # a stable sort: equal impacts keep the order given
    if order != sorted(goals, key=lambda g: (-exact(impact[g]), g)):
        raise ValueError('Goals with equal impact are listed by name')
    return order


def shortfall(result, left) -> list:
    """For a look that stopped on RESOURCE_REQUIRED: per admission row, each dimension in which the plan needed more than
    was left (that is what the kernel's RESOURCE_REQUIRED says of a row). `left` is the budget the State had at that look
    (the kernel's ADMISSION row carries the cost only)."""
    return [{'methods': list(e['data']['methods']), 'dimension': dim, 'need': need, 'left': left[dim]}
            for e in result.get('trace', []) if e['operation'] == 'ADMISSION' for dim, need in e['data']['cost'].items() if need > left[dim]]


def attach_shortfall(run, budget_after) -> dict:
    """Walk the looks of one standing evaluation backwards from the budget left at its end, so each look is set against
    the budget it saw: what is left at the end plus what the later looks paid."""
    left = dict(budget_after)
    for r in reversed(run.get('runs', [])):
        if r.get('model_receipts'):
            for dim, paid in r['cost'].items():
                left[dim] += paid
        if r.get('status') == 'RESOURCE_REQUIRED':
            r['shortfall'] = shortfall(r, left)
    return run


def _marked(row) -> bool:   # a row that carries one of the adapter's marks: it is held to be exactly what the adapter makes
    return ('value' in row or row.get('evidence_kind') in ('NUMBER', 'COMPARISON') or row.get('source') == SOURCE or 'compares' in row)


def problems(packs) -> list:
    """What is wrong with the ordered packs of one case. On the books the kernel's door leaves: a `value` that is not exact
    text or sits on a row the adapter did not make; a comparison row that is not what the adapter makes from the numbers
    on the books of its scope (a flipped verdict, a dropped dependency, half a band, a number made again without its
    comparisons); a row with one of the adapter's marks that the door does not store (it is not verified, or a decision
    stands on its fact); a row the adapter did not make (a decision, another writer's row) standing where these packs
    carry a number or a comparison. Of the methods and rules: a method whose effect is a number or a comparison, a rule
    whose head is one, a step that requires a rule head standing over a comparison, and a step that requires the effect
    of a step made on a number or a comparison without requiring that row itself (what it makes would come back when
    the first step runs again on another number). Of the budget: a pack that adds a dimension without a preference; a
    ceiling (`ceilings`: ceiling dimension -> capped dimension) that is not two dimensions of the budget; a method under
    a declared ceiling that does not cost the ceiling the same; a later pack that sets the ceiling again. Of the order:
    once a pack has carried an `impact` table, every pack that sets `goals` lists them in the order of the last table."""
    out, rules, methods, ceilings, dims, table = [], {}, [], {}, set(BASE), None
    door, used = State(), []   # the kernel's own evidence door, and the places where these packs write a number or a comparison
    for pack in packs:
        name = pack.get('id')
        if type(pack.get('scope')) is str and pack['scope']:   # a pack names the scope before its rows
            door.scope = pack['scope']
        for row in pack.get('evidence', []):
            try:
                kept, marked, key = door.observe(row), _marked(row), door.key(row['predicate'], row.get('scope'))
            except (ValueError, KeyError, TypeError, AttributeError):
                out.append(f'{name}: carries a row the kernel refuses')
                continue
            if marked and not kept:
                out.append(f'{key}: the kernel does not store this row of {name} (it is not verified, or a decision stands on its fact)')
            elif marked and key not in used:
                used.append(key)
        for r in pack.get('rules', []):
            if r.get('approved'):
                rules[r.get('head')] = r
        methods += pack.get('methods', [])
        budget = pack.get('budget', {})
        added = sorted(set(budget) - dims)   # new to the State: a pack that sets a known dimension again adds nothing
        dims |= set(budget)
        if added and 'preference' not in pack:
            out.append(f"{name}: adds the budget dimension {', '.join(added)} without a preference that names it")
        out += [f'{name}: sets the ceiling {dim} again' for dim in budget if dim in ceilings]
        declared = pack.get('ceilings', {})   # the pack that declares a ceiling is the one that sets it
        if type(declared) is not dict or any(type(top) is not str or type(cap) is not str or top == cap for top, cap in declared.items()):
            out.append(f'{name}: a ceiling names its own dimension and the dimension it caps')
        else:
            ceilings.update(declared)
        if 'impact' in pack:
            table = pack['impact']
        if table is not None and ('goals' in pack or 'impact' in pack):   # the kernel takes the goals of the last pack that sets them: each such pack keeps the order
            try:
                if ranked(pack.get('goals'), table) != pack.get('goals'):
                    out.append(f'{name}: the goals are not in the order of their impact')
            except ValueError as e:
                out.append(f'{name}: {e}')
    rows, numbers, made = door.evidence, {}, {}   # scope|predicate -> the row the door stored, with its scope
    for key, row in rows.items():
        if 'value' in row or row.get('evidence_kind') == 'NUMBER':
            try:
                again = measured(row.get('predicate'), row.get('value'), row.get('source'), row.get('label'), row.get('unit'), row.get('scope'))
                if digest(again) != digest(row):
                    raise ValueError('its version is not the digest of its reading')
                numbers[key] = row
            except ValueError as e:
                out.append(f'{key}: carries a value but is not a number row the adapter made ({e})')
        elif row.get('source') == SOURCE or 'compares' in row or row.get('evidence_kind') == 'COMPARISON':
            made[key] = row
    for key, row in made.items():
        try:
            c, at = row['compares'], lambda p: row['scope'] + '|' + p
            number = numbers[at(c['number']['predicate'])]
            bound = numbers[at(c['bound']['predicate'])] if 'predicate' in c['bound'] else c['bound']['literal']
            if 'partner' in c:
                pair = band(number, c['op'], bound, row['predicate'], c['partner'])
                good = digest(pair[0]) == digest(row) and digest(pair[1]) == digest(rows.get(at(c['partner'])))
            else:
                good = digest(compared(number, c['op'], bound, row['predicate'])) == digest(row)
            if not good:
                out.append(f'{key}: is not the comparison the adapter makes from the numbers in these packs')
        except (KeyError, TypeError, ValueError):
            out.append(f'{key}: compares a number that is not in these packs, or is not a comparison row the adapter made')
    out += [f'{key}: a row the adapter did not make (a decision, or another writer\'s row) stands where these packs carry a number or a comparison'
            for key in used if not _marked(rows[key])]
    held = {key.split('|', 1)[1] for key in list(numbers) + list(made)}   # the facts only the adapter makes, in whatever scope
    compared_facts = {key.split('|', 1)[1] for key in made}

    out += [f'the ceiling {top} over {cap} names a dimension the budget does not have' for top, cap in ceilings.items() if top not in dims or cap not in dims]
    out += [f"{r.get('id')}: derives {head}, a row only the adapter makes" for head, r in rules.items() if head in held]

    def over(p, seen=()):   # a rule head that stands over a comparison, through any chain of rules
        r = rules.get(p)
        return bool(r) and p not in seen and any(c in compared_facts or over(c, seen + (p,)) for branch in r['branches'] for c in branch)
    for m in methods:
        needs = m.get('requires', [])
        if m.get('effect') in held:
            out.append(f"{m.get('id')}: makes {m.get('effect')}, a row only the adapter makes")
        for req in needs:
            if over(req):
                out.append(f"{m.get('id')}: requires the rule head {req}, which stands over a comparison; a step requires the comparison row itself")
            for first in methods:   # a step made on the effect of another step: the row it writes cites that effect at the one version a handler gives it
                if first.get('effect') == req:
                    out += [f"{m.get('id')}: requires {req}, which {first.get('id')} makes on {under}, without requiring {under} itself; what it makes would come back when {req} is made again on another number"
                            for under in first.get('requires', []) if under in held and under not in needs]
        for top, cap in ceilings.items():
            if m.get('cost', {}).get(cap, 0) != m.get('cost', {}).get(top, 0):
                out.append(f"{m.get('id')}: costs {cap} without costing the ceiling {top} the same")
    return out
