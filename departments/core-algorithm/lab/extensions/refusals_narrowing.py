"""Narrowing check (0.15.0-refusals, matrix row R37): a child narrows and never relaxes.

`relaxations(parents, child)` reads a child pack against the packs that stand before it (a department's packs, then a team's;
a practice pick, then the owner's own rules) and names what the child would relax. It folds the parents, and the parents with
the child, with the kernel's own `State`, and compares the two: nothing here re-implements how a pack applies. A child may add
conditions, refusals, questions and steps for facts nobody served, and may lower a ceiling. What it may not do, each named:

  CONDITION_DROPPED  rule      a rule that replaces its parent has an alternative that keeps no alternative of the parent whole
                               (the branch subset test: every way to satisfy the child must be a way to satisfy the parent)
                     method    a new step for a fact the parent already has steps for keeps none of them whole: it must keep
                               the prerequisites, the grant and the provider of one of them, and cost no less
                     shadow    a new rule on a fact the parent serves by steps: the kernel then never consults them
                     derived   a new rule on a fact a rule of the parent names as a condition and the parent leaves to
                               evidence: the condition can then hold with nothing observed, granted, run or paid
  REFUSAL_DROPPED    decision  a FALSE decision of the parent is replaced by a TRUE decision
                     scope     the pack moves the scope, so a FALSE decision of the parent stays behind
                     grant     a grant the parent revoked is granted again
                     looser    a step or a rule for a fact the parent refuses (the kernel will not use it; named for the author)
  ASK_DROPPED        answer    the pack carries a TRUE row on a fact the parent asks about (also one that reads only later,
                               when what it rests on arrives)
                     method    another step for a fact the parent asks about (the kernel may take it instead of the question)
                     rule      a rule on a fact the parent asks about (the kernel then never asks)
  CEILING_RAISED     budget    a budget dimension is raised
                     provider  a provider's capacity is raised

Thirteen ways, a closed list: the check is structural and names are compared, not meanings (J2 Pro compares normalised lines
the same way: practice.py `rule_faults`). What it does not read is listed in the README. `verdict` turns the result into one
evidence row, a decision named by the child and by the digest of the packs compared, and `install_rule` is the rule that
rests installing that child over those parents on that row: so "may this pack be installed over those" is a goal like any
other (the pattern of extensions/standards.py), and the review of another child, or of another text of the same child, is
another fact and cannot stand in. The check runs when a pack is authored or reviewed; the kernel does not call it."""
from __future__ import annotations
from kernel.core import State, digest
import extensions.asks, extensions.constructor   # the action kinds the lab's packs use: registered, so the kernel can fold any of them

SOURCE = 'adapter:refusals/narrowing@1'
KINDS = ('CONDITION_DROPPED', 'REFUSAL_DROPPED', 'ASK_DROPPED', 'CEILING_RAISED')


def _folded(parents, child):
    parents = [parents] if type(parents) is dict else parents
    if type(parents) is not list:
        raise ValueError('The parents are one pack or a list of packs, in load order')
    try:
        return parents, State.from_packs(parents), State.from_packs(parents + [child])
    except ValueError as e:
        raise ValueError(f'The kernel refuses these packs: {e}') from None


def relaxations(parents, child: dict) -> list[dict]:
    """What `child` would relax of what stands after `parents` (one pack or a list, in load order): a list of findings
    {kind, how, ..., line}, in the order of KINDS; [] when the child only narrows. Packs the kernel refuses are refused here."""
    parents, was, now = _folded(parents, child)
    found = []

    def name(kind, how, line, **what):
        found.append({'kind': kind, 'how': how, **what, 'line': line})

    def ways(fact):   # the parent's steps for a fact
        return [m for m in was.methods.values() if m['effect'] == fact and m.get('approved', True)]

    def lacks(m, way):   # what a new step lacks of a step of the parent: prerequisites, its grant, its provider, some of its cost. All four empty: it keeps that step whole
        dims = sorted(set(m.get('cost', {})) | set(way.get('cost', {})))
        return {'dropped': sorted(set(way.get('requires', [])) - set(m.get('requires', []))),
                'grant': None if m['grant'] == way['grant'] else m['grant'],
                'provider': None if m['provider'] == way['provider'] else m['provider'],
                'cheaper': [d for d in dims if m.get('cost', {}).get(d, 0) < way.get('cost', {}).get(d, 0)]}

    asked = {m['effect'] for m in was.methods.values() if m.get('action') == 'ask' and m.get('approved', True)}
    refused = sorted(key for key, row in was.evidence.items() if row.get('final') and row['truth'] == 'FALSE')
    conditions = {c for r in was.rules.values() for branch in r['branches'] for c in branch}

    for head, r in now.rules.items():
        old = was.rules.get(head)
        if old is not None:   # the rule that stood on this fact: every alternative of the child must keep one of its alternatives whole
            for i, branch in enumerate(r['branches'], 1):
                if not any(set(a) <= set(branch) for a in old['branches']):
                    near = min(old['branches'], key=lambda a: (-len(set(a) & set(branch)), len(set(a) - set(branch))))   # the alternative of the parent it shares most with
                    dropped = sorted(set(near) - set(branch))
                    name('CONDITION_DROPPED', 'rule', f"{r['id']} replaces {old['id']}: its alternative {i} keeps no alternative of the parent whole; the nearest loses {', '.join(dropped)}",
                         rule=r['id'], replaces=old['id'], head=head, alternative=i, dropped=dropped)
        elif head in asked:
            name('ASK_DROPPED', 'rule', f"{r['id']} puts a rule on {head}, which the parent asks about: the kernel then never asks", rule=r['id'], fact=head)
        elif was.key(head) in refused:
            name('REFUSAL_DROPPED', 'looser', f"{r['id']} is a rule for {head}, which the parent refuses: it says the refusal more loosely (the kernel will not use it while the decision stands)",
                 rule=r['id'], fact=head)
        elif ways(head):
            shadowed = sorted(m['id'] for m in ways(head))
            name('CONDITION_DROPPED', 'shadow', f"{r['id']} puts a rule on {head}: the kernel then never consults {', '.join(shadowed)}, so their prerequisites, grants and costs no longer apply",
                 rule=r['id'], head=head, methods=shadowed)
        elif head in conditions:
            name('CONDITION_DROPPED', 'derived', f"{r['id']} puts a rule on {head}, a condition the parent leaves to evidence: it can then hold with nothing observed, granted, run or paid",
                 rule=r['id'], head=head)

    for mid, m in now.methods.items():
        if mid in was.methods or not m.get('approved', True):
            continue
        fact, before = m['effect'], ways(m['effect'])
        if fact in asked:
            name('ASK_DROPPED', 'method', f"{mid} is another way to {fact}, which the parent asks about: the kernel may take it instead of the question", method=mid, fact=fact)
        elif was.key(fact) in refused:
            name('REFUSAL_DROPPED', 'looser', f"{mid} is a method for {fact}, which the parent refuses: it says the refusal more loosely (the kernel will not use it while the decision stands)",
                 method=mid, fact=fact)
        elif fact not in now.rules and before and all(any(lacks(m, way).values()) for way in before):
            near = min(before, key=lambda way: (-len(set(way.get('requires', [])) & set(m.get('requires', []))), len(lacks(m, way)['dropped'])))   # the step of the parent it shares most prerequisites with
            gap = lacks(m, near)
            said = ([f"drops {', '.join(gap['dropped'])}"] if gap['dropped'] else []) + ([f"is under the grant {gap['grant']}, not {near['grant']}"] if gap['grant'] else []) \
                + ([f"uses the provider {gap['provider']}, not {near['provider']}"] if gap['provider'] else []) + ([f"costs less {', '.join(gap['cheaper'])}"] if gap['cheaper'] else [])
            name('CONDITION_DROPPED', 'method', f"{mid} is a new way to {fact} that keeps no way of the parent whole; beside {near['id']} it {'; '.join(said)}",
                 method=mid, effect=fact, beside=near['id'], **gap)

    for key in refused:
        scope, _, fact = key.partition('|')
        there = now.evidence.get(now.key(fact), {})
        if now.evidence[key]['truth'] == 'TRUE':
            name('REFUSAL_DROPPED', 'decision', f"the parent refuses {fact} (a FALSE decision in {scope}); the pack replaces it with a TRUE decision",
                 fact=fact, scope=scope, source=now.evidence[key].get('source'))
        elif now.scope != was.scope and scope == was.scope and not (there.get('final') and there.get('truth') == 'FALSE'):
            name('REFUSAL_DROPPED', 'scope', f"the pack moves the scope from {was.scope} to {now.scope}: the refusal of {fact} stays behind", fact=fact, scope=scope, moved_to=now.scope)
    for grant in sorted(({g for p in parents for g in p.get('revoke_grants', [])} - was.grants) & now.grants):
        name('REFUSAL_DROPPED', 'grant', f"the parent revoked the grant {grant}; the pack grants it again", grant=grant)

    for fact in sorted(asked):   # the stored row, not what it reads now: a yes that rests on a row still to come answers the question the day that row arrives
        row = now.evidence.get(now.key(fact))
        if row is not None and row['truth'] == 'TRUE' and row != was.evidence.get(was.key(fact)) and was.fact(fact)['truth'] != 'TRUE':
            reads = now.fact(fact)['truth']
            name('ASK_DROPPED', 'answer', f"the pack carries a TRUE row on {fact}, which the parent asks about: it answers for the party that was to be asked"
                 + ('' if reads == 'TRUE' else ' (it reads once what it rests on arrives)'), fact=fact, source=row.get('source'), reads=reads)

    for dim in sorted(was.budget):
        if now.budget[dim] > was.budget[dim]:
            name('CEILING_RAISED', 'budget', f"the pack raises the budget for {dim} from {was.budget[dim]} to {now.budget[dim]}", dimension=dim, was=was.budget[dim], now=now.budget[dim])
    for provider in sorted(was.providers):
        if now.providers[provider] > was.providers[provider]:
            name('CEILING_RAISED', 'provider', f"the pack raises the capacity of {provider} from {was.providers[provider]} to {now.providers[provider]}",
                 provider=provider, was=was.providers[provider], now=now.providers[provider])
    return sorted(found, key=lambda f: KINDS.index(f['kind']))


def _pair(parents, child):   # one comparison: the digest of exactly the packs compared, and with the child's id its name
    version = 'pair-' + digest([parents, child])[:12]
    return version, f"{child['id']}@{version}"


def verdict(parents, child: dict) -> dict:
    """The result as evidence: one row, TRUE when the child relaxes nothing, FALSE with what it relaxed. It is a decision
    (final): a review stands until another review of the same packs replaces it, and no rule, method or ordinary row may
    overturn a no. It is named by the child and the digest of the packs compared: the review of another child, of other
    parents or of another text of this child is another fact. Source = this adapter."""
    found = relaxations(parents, child)
    parents = [parents] if type(parents) is dict else parents
    version, pair = _pair(parents, child)
    return {'predicate': 'narrows:' + pair, 'truth': 'FALSE' if found else 'TRUE', 'verified': True, 'final': True, 'source': SOURCE, 'version': version,
            'child': child['id'], 'parents': [p['id'] for p in parents], 'relaxed': found}


def install_rule(parents, child: dict) -> dict:
    """The rule that rests installing this child over these parents on the verdict of exactly this comparison."""
    parents = _folded(parents, child)[0]   # packs the kernel refuses get no rule
    pair = _pair(parents, child)[1]
    return {'id': 'R-INSTALL:' + pair, 'head': 'installable:' + pair, 'branches': [['narrows:' + pair]], 'approved': True, 'source': 'reviewed/child-narrows-never-relaxes'}
