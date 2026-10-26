"""layers/adaptation/v1.py -- Adaptation, version 1: the implementation behind the interface's adaptation entries (PRD A1.18).

Its recipe is v1.json beside it: the Adaptation engine object, moved byte for byte from engine_defs/website.json in wave 0.
Every code, prompt, draft and check name the recipe uses is provided here (A1 step A1): by reference, to the body
engine_runtime still holds, until this layer moves one in to change it (move on touch, A1.19). WORDS and LAYOUT stay
empty until the words move, so the prompts are still read from the .md bundle. view() returns the pane's read model by
reference.
"""
from layers import R, W, J, S, FV, ref_to  # noqa: F401 -- lazy proxies: tests reload engine_runtime, so never a module object

LAYER = 'adaptation'
VERSION = 1
IMPLEMENTS = 1
RECIPE = 'v1.json'
CODE = {name: ref_to(name) for name in (
    'hear', 'adapt_sense', 'adapt_ladder', 'adapt_act', 'adapt_trial', 'adapt_notrial', 'adapt_heard', 'adapt_park', 'adapt_offer',
    'adapt_priced', 'adapt_source', 'adapt_line_offer', 'adapt_line_granted', 'adapt_line_refused', 'adapt_line_counter')}
PROMPT = {'adapt_shape': ref_to('p_adapt_shape'), 'adapt_line': ref_to('p_adapt_line')}
DRAFT = {'adapt_shape_draft': ref_to('d_adapt_shape'), 'adapt_line_draft': ref_to('d_adapt_line')}
CHECK = {name: ref_to('c_' + name) for name in (
    'counted_the_rows', 'moves_name_their_rows', 'said_what_it_did', 'facts_are_closed', 'idea_has_shapes', 'line_is_engines')}
WORDS, LAYOUT = {}, {}


def view(ref, d, events, asks):
    """Adaptation's pane (S.VIEWS['adaptation']): functions_view's read model, by reference until this layer holds its own."""
    return FV._j2_part(ref, d, 'Adaptation', events, asks)
