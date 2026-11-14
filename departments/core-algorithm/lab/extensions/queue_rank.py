"""Rank a queue by impact (matrix row R31b), OUTSIDE the kernel.

The kernel runs a State's standing goals in list order over one budget (Kernel.run_standing), so the goal listed first is
served first, whatever it is worth. This module orders the list before a look, and nothing else.

  declared   the impact of a goal is declared where its meaning is: a whole number, not negative, on the approved rule
             that defines the goal (`impact` on the rule: pack content the kernel keeps and never reads). A rule that is
             only proposed declares nothing, and a replacing rule brings its own impact with it.
  ranked     highest impact first; goals of equal impact keep the order they had in the queue.
  kept       the ranking is a pack: the goals in their new order, and under `ranked_by` the impact and the rule that
             put each goal where it is. It enters the State through State.apply like any pack, so every run after it
             names the ranking among the packs it rests on. A ranking that is already the State's last pack, with the
             queue still in its order, changes nothing and is not applied a second time.
  refused    a queue with a goal that has no declared impact is not ranked at all (ValueError): the State stays as it
             was. An undeclared goal is never quietly put first or last.

The kernel is not asked anything and is not changed: how a goal is planned and how the gate decides stay inside
Kernel.resolve, at the goal's turn, on the books as they stand then. What the order does change is those books: a goal
that comes later finds what the goals before it left. So the order decides who gets a budget that does not cover
everyone, and it can also give a goal another route, or hold a goal that the listed order would have run.

A ranking is a snapshot of the impacts as they were declared when it was made. A later rule or goals pack does not rank
the queue again, and a run goes on naming the ranking whether or not it still orders the queue: rank again after a change.
All of this is a local model: impact is a number somebody declared, not a measured outcome."""
from __future__ import annotations
from kernel.core import digest   # how State.loaded names a pack: the one thing read from the kernel, and it neither plans nor gates


def _whole(v) -> bool:   # a whole number that is not negative (true and 2.0 are not numbers here)
    return type(v) is int and v >= 0


def impacts(state) -> list:
    """One line per standing goal, in queue order: the goal, its declared impact and the rule that declared it.
    Refused (ValueError) when a standing goal has no approved rule, or its rule declares no whole, non-negative impact."""
    lines = []
    for goal in state.goals:
        rule = state.rules.get(goal)
        if rule is None or not _whole(rule.get('impact')):
            raise ValueError(f'No declared impact for standing goal: {goal}')
        lines.append({'goal': goal, 'impact': rule['impact'], 'rule': rule['id']})
    return lines


def ranking(state, id: str = 'queue-ranked') -> dict:
    """The ranking of this State's queue as a pack: highest impact first, equal impacts in queue order. Changes nothing."""
    lines = sorted(impacts(state), key=lambda line: -line['impact'])   # sorted is stable: ties keep their queue order
    return {'schema': 'sutra-extension/2', 'id': id, 'goals': [line['goal'] for line in lines], 'ranked_by': lines}


def rank(state, id: str = 'queue-ranked') -> dict:
    """Rank the queue now: apply the ranking pack through the State's own door (all or nothing) and return it.
    When that very pack (the same id and content) is already the State's last pack and the queue is still in its order,
    nothing is applied: ranking twice leaves one entry in the list of packs, not two."""
    pack = ranking(state, id)
    last = state.loaded[-1] if state.loaded else {}
    if not (last.get('pack') == id and last.get('sha256') == digest(pack) and state.goals == pack['goals']):
        state.apply(pack)   # a name the State's door refuses (not a text, empty) is refused there, and nothing is applied
    return pack
