"""layers/coordination/v1.py -- Coordination, version 1: the implementation behind the interface's coordination entries (PRD A1.18).

Its recipe is v1.json beside it: the Coordination engine object, moved byte for byte from engine_defs/website.json in wave 0.
Every code, prompt, draft and check name the recipe uses is provided here by reference (A1 K1): a late-bound delegate to
the body in engine_runtime's Coordination region (ref_to), so the module names what its recipe needs and no behaviour
changes. A body moves into this module when this layer changes it (move on touch); engine_runtime's copy stays until W3-PROOF.
WORDS and LAYOUT are empty until K2, so its prompts are still read from the .md bundle. view() returns the pane's read model
by reference.
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
WORDS, LAYOUT = {}, {}


def view(ref, d, events, asks):
    """Coordination's pane (S.VIEWS['coordination']): functions_view's read model, by reference until this layer holds its own."""
    return FV._j2_part(ref, d, 'Coordination', events, asks)
