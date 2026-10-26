"""layers/priority/v1.py -- Priority, version 1: the implementation behind the interface's priority entries (PRD A1.18).

Its recipe is v1.json beside it: the Priority engine object, moved byte for byte from engine_defs/website.json in wave 0.
Every code, prompt, draft and check name the recipe uses is registered below, by reference to engine_runtime's own body
until a body moves here (move on touch: the body is copied into this module to be changed, and engine_runtime's copy
stays until W3-PROOF deletes the dead copies). WORDS and LAYOUT are empty, so its prompts are still read from the .md
bundle. view() returns the pane's read model by reference.
"""
from layers import R, W, J, S, FV, ref_to  # noqa: F401 -- lazy proxies: tests reload engine_runtime, so never a module object

LAYER = 'priority'
VERSION = 1
IMPLEMENTS = 1
RECIPE = 'v1.json'
CODE = {
    'priority_envelope': ref_to('priority_envelope'),
    'priority_read': ref_to('priority_read'),
    'priority_post': ref_to('priority_post'),
    'priority_grant': ref_to('priority_grant'),
}
PROMPT = {
    'priority_bargain': ref_to('p_priority_bargain'),
}
DRAFT = {
    'priority_bargain_draft': ref_to('d_priority_bargain'),
}
CHECK = {
    'gate_answer_is_known': ref_to('c_gate_answer_is_known'),
    'facts_are_closed': ref_to('c_facts_are_closed'),
    'answer_has_its_price': ref_to('c_answer_has_its_price'),
    'said_what_it_did': ref_to('c_said_what_it_did'),
}
WORDS, LAYOUT = {}, {}


def view(ref, d, events, asks):
    """Priority's pane (S.VIEWS['priority']): functions_view's read model, by reference until this layer holds its own."""
    return FV._j2_part(ref, d, 'Priority', events, asks)
