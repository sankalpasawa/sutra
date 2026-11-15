"""Authoring-time check for a tiered rule set (0.16.0-ordered, matrix row R80): per-tier rules that do not leak.

One rule set serves several tiers when the goal's rule has one alternative per tier and each alternative opens with
that tier's row (`tier_internal`, `tier_project`, ...): the tier is an evidence row, set by the tier's own pack. Two
locks then keep one tier from using another tier's way, and a pack cannot state either about the OTHER packs:

  the row    every step of the rule set requires exactly one tier row, and no step and no rule makes one. A State
             whose tier row is FALSE cannot run that step, whatever grants it holds.
  the grant  the grant of a step is given by the pack of the step's tier and by nothing else: not by another tier
             pack and not by the rule set, which every tier loads. A State handed another tier's row still lacks that
             tier's grant.

Both locks hold only while each kind of pack carries what it is for, so the check works from a closed list, not from
a list of known mistakes:

  the rule set   goals, rules and methods, and nothing else: one approved rule, the goal's. A grant, a scope, an
                 evidence row or a provider slot written here would reach every tier.
  a tier pack    a scope, evidence rows, grants and provider slots, and nothing else: no step and no rule of its own
                 (either would be a way around the rule set). Its rows are the tier rows, all of them, verified, one
                 TRUE; every other row says what has not happened yet (a verified FALSE row), no row names a
                 scope of its own and no fact is stated twice. Its grants are exactly the ones the steps of its
                 tier need.

`tier_faults` reads the rule set and all its tier packs together and lists what breaks this. The pack file calls it
before it writes the packs and refuses to author a set with faults. It runs when packs are authored, never in the
kernel, and it judges only the packs it is given: a row, a grant or a step that reaches a State from another pack or
from an event is not its business."""
from __future__ import annotations

RULE_SET_HOLDS = {'schema', 'id', 'goals', 'rules', 'methods'}
TIER_PACK_HOLDS = {'schema', 'id', 'scope', 'evidence', 'grants', 'providers'}


def tier_faults(rule_set: dict, tier_packs: list, head: str) -> list:
    """The faults of a tiered rule set and its tier packs, as plain lines. An empty list: no tier can use another tier's way."""
    name = rule_set.get('id')
    faults = []
    more = sorted(set(rule_set) - RULE_SET_HOLDS)
    if more:
        faults.append(f'{name} carries {more}: a rule set is goals, rules and methods, because what it holds reaches every tier')
    rules = rule_set.get('rules', [])
    if len(rules) != 1 or rules[0].get('head') != head or rules[0].get('approved') is not True:
        return faults + [f'{name} holds one approved rule, the rule for {head}, and no other']
    if rule_set.get('goals') != [head]:
        faults.append(f'{name} names {head} as its one goal')
    tiers = [branch[0] for branch in rules[0]['branches']]
    if len(set(tiers)) != len(tiers):
        faults.append('two alternatives of the rule open with the same tier row')
    owner = {}   # tier row -> the pack that sets it TRUE
    for p in tier_packs:
        pid = p.get('id')
        more = sorted(set(p) - TIER_PACK_HOLDS)
        if more:
            faults.append(f'{pid} carries {more}: a tier pack is a scope, evidence rows, grants and provider slots, with no step or rule of its own')
        evidence = p.get('evidence', [])
        rows = {e.get('predicate'): e for e in evidence if e.get('predicate') in tiers}
        true = [t for t in tiers if rows.get(t, {}).get('truth') == 'TRUE']
        if any('scope' in e for e in evidence):
            faults.append(f'{pid} gives a row a scope of its own')
        if len({e.get('predicate') for e in evidence}) != len(evidence):
            faults.append(f'{pid} states a fact twice')
        stated = sorted(str(e.get('predicate')) for e in evidence if e.get('predicate') not in tiers and (e.get('truth') != 'FALSE' or e.get('verified') is not True))
        if stated:
            faults.append(f'{pid} states {stated} as more than a verified FALSE row: beside its tier a tier pack says only what has not happened yet')
        if set(rows) != set(tiers) or len(true) != 1 or any(e.get('truth') not in ('TRUE', 'FALSE') or e.get('verified') is not True for e in rows.values()):
            faults.append(f'{pid} does not set every tier row, verified, with exactly one TRUE')
        elif true[0] in owner:
            faults.append(f'{pid} and {owner[true[0]]} are both the pack of {true[0]}')
        else:
            owner[true[0]] = pid
    faults += [f'no pack is the pack of {t}' for t in tiers if t not in owner]
    scopes = [p.get('scope') for p in tier_packs]
    if None in scopes or len(set(scopes)) != len(scopes):
        faults.append('every tier pack names a scope of its own')
    needs = {}   # tier row -> the grants its steps need
    for m in rule_set.get('methods', []):
        if m.get('effect') in tiers:
            faults.append(f'{m.get("id")} would make the tier row {m.get("effect")}: a tier is observed, never made')
        own = [r for r in m.get('requires', []) if r in tiers]
        if len(own) != 1:
            faults.append(f'{m.get("id")} requires {len(own)} tier rows, not exactly one')
            continue
        needs.setdefault(own[0], set()).add(m.get('grant'))
        holders = sorted(str(p.get('id')) for p in tier_packs if m.get('grant') in p.get('grants', []))
        if type(m.get('grant')) is not str or holders != [owner.get(own[0])]:
            faults.append(f'{m.get("id")} belongs to {own[0]} but its grant {m.get("grant")} is held by {holders}')
    for tier, pid in owner.items():
        held = next(p for p in tier_packs if p.get('id') == pid).get('grants', [])
        stray = sorted(set(held) - needs.get(tier, set()))
        if stray:
            faults.append(f'{pid} holds {stray}, which no step of its tier needs')
    return faults
