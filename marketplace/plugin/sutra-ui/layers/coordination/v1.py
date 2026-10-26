"""layers/coordination/v1.py -- Coordination, version 1: the implementation behind the interface's coordination entries (PRD A1.18).

Its recipe is v1.json beside it: the Coordination engine object, moved byte for byte from engine_defs/website.json in wave 0.
Every code, prompt, draft and check name the recipe uses is provided here by reference (A1 K1): a late-bound delegate to
the body in engine_runtime's Coordination region (ref_to), so the module names what its recipe needs and no behaviour
changes. A body moves into this module when this layer changes it (move on touch); engine_runtime's copy stays until W3-PROOF.
WORDS and LAYOUT hold Coordination's two prompt files, goal (does, skills) and tie (tie), so layers.prompt serves them from here
and the .md bundle is read for none of its parts (K2). view() and engine_card() return the pane's and the card's read
models by reference (K4).
"""
from layers import R, W, J, S, FV, ref_to  # noqa: F401 -- lazy proxies: tests reload engine_runtime, so never a module object

LAYER = 'coordination'
VERSION = 1
IMPLEMENTS = 1
RECIPE = 'v1.json'
CODE = {name: ref_to(name) for name in (
    'coord_busy', 'coord_pick', 'coord_edge', 'coord_verdict', 'coord_bounds', 'coord_alarm',   # the rules
    'coord_chain',                                                                              # the gate
    'coord_heard', 'coord_table',                                                               # the handlers: a verdict, an engine born
    'coord_ready', 'coord_record',                                                              # the steps
)}
PROMPT = {'coord_tie': ref_to('p_coord_tie')}
DRAFT = {'coord_tie_draft': ref_to('d_coord_tie')}
CHECK = {name: ref_to(body) for name, body in (
    ('one_run_at_a_time', 'c_one_run_at_a_time'),
    ('names_who_goes_first', 'c_names_who_goes_first'),
    ('chain_under_its_limit', 'c_chain_under_its_limit'),
    ('gate_answer_is_known', 'c_gate_answer_is_known'),        # shared (S.SHARED_CHECKS)
    ('said_what_it_did', 'c_said_what_it_did'),
    ('facts_are_closed', 'c_facts_are_closed'),
)}
#: A1.16: the default words of each prompt part and the layout that arranges them, by the split rule (`python -m layers.prompts
#: --extract coordination`); an owner's change is a typed value over these (instructions.json), never an edit here
WORDS = {
    'goal': {
        'does': {
            'text': (
                'keeps what engines share: one run at a time, who goes first when several are ready, who may post '
                "to whom, the chain's limit, a thread's bounds, and the alarm. Its own agent says who goes first "
                'when several functions are ready at once'
            ),
        },
        'skills': {
            'items': [
                'keep one run at a time',
                'say who goes first',
                'check who may post what to whom',
                'stop a chain at its limit',
                'close a thread at its bound',
                'raise an alarm',
                'say who goes first among equals',
            ],
        },
    },
    'tie': {
        'tie': {
            'task': 'Several functions of the department are ready at once, and one runs at a time. Say who goes first.',
        },
    },
}
LAYOUT = {
    'goal': {
        'does': '{text}',
        'skills': '{items}',
    },
    'tie': {
        'tie': (
            '{task}\n'
            'READY NOW: {{ready}}\n'
            'WHAT EACH DOES: {{what}}\n'
            "COORDINATION'S TABLE, THE USUAL ORDER: {{order}}\n"
            'WAITING FOR THE OWNER: {{waiting}}\n'
            '\n'
            '{returns}'
        ),
    },
}

# ---- the function template's words (A3.4.5, A3-FUNCTIONS F1) ---------------------------------------------------------
# Parts of the goal group that S.ADDED_PARTS lists (they have no .md part), and the layout of the role block the card
# carries (A3.4.3). What the function is not, what it never does and who it hands on to are S.FUNCTION_TEMPLATE's, not
# words: no version drops one.
WORDS['goal']['done'] = {'text': (
    'every ready engine had its turn by the rule the table declares, one run at a time, and no chain, '
    'window or lost request went unanswered'
)}
WORDS['goal']['role_is'] = {'text': (
    "the department's operating timetable; it decides which registered engine is ready, what must "
    'happen before it, and how work that happens at the same time stays apart'
)}
WORDS['goal']['role_may'] = {'items': [
    'name which ready engine goes first, and the rule it used',
    'hold a run and say exactly what is missing',
    'schedule another ready engine instead of stopping the department when one is held',
    'give each engine a slot, and record who makes and who reads each thing',
    'raise an alarm to Identity when a run is past its window, and say a request nobody answered back',
]}
WORDS['goal']['role_procedure'] = {'items': [
    'Consider only workflows that are registered and have a limit.',
    'Check their triggers and what they wait for.',
    'Check locks, shared writers and actions that cannot happen together.',
    'Pick the next one by the rule the table declares.',
    'Record its slot, its hand-offs and what blocks it.',
    'If it cannot run, hold it and name the exact condition that is missing.',
    'If another ready workflow exists, schedule it rather than stopping the department.',
]}
WORDS['goal']['role_patterns'] = {'items': [
    'Scheduling something that is not registered.',
    "Taking 'most important' as permission to break a dependency.",
    'Stopping all work because one workflow is held.',
    'Choosing who goes first without saying the rule.',
    'Becoming a project manager who changes scope.',
]}
WORDS['goal']['role_block'] = {}
LAYOUT['goal'].update({'done': '{text}', 'role_is': '{text}', 'role_may': '{items}', 'role_procedure': '{items}',
                      'role_patterns': '{items}', 'role_block': S.ROLE_BLOCK_LAYOUT})


def view(ref, d, events, asks):
    """Coordination's pane (S.VIEWS['coordination'], screen S7): functions_view's read model of its own state, by reference
    (A1.11, A1.17). It reads the record and the table, never the events, and writes nothing."""
    return FV.coordination(ref, d, ak=asks)


def engine_card(ref, name):
    """One engine's card (S.VIEWS['engine_card'], screen S17): its place in the timetable, the motor's facts and one row for
    each of the five, by reference (A1.17). None for a department not on the engine runtime."""
    return FV.engine_card(ref, name)
