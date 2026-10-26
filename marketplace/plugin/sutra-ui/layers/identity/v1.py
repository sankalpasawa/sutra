"""layers/identity/v1.py -- Identity, version 1: the implementation behind the interface's identity entries (PRD A1.18).

Its recipe is v1.json beside it: the Identity engine object, moved byte for byte from engine_defs/website.json in wave 0.
Every code, prompt, draft and check name the recipe uses is provided here by reference (ref_to): each is a late-bound
delegate to the body engine_runtime holds today, so the behaviour is exactly what ran before, and a body moves into this
file on touch (A1.19: a name a layer changes is copied here and changed here). WORDS and LAYOUT are empty until I2, so
the prompts are still read from the .md bundle. view() returns the pane's read model by reference (I3).
"""
from layers import R, W, J, S, FV, ref_to  # noqa: F401 -- lazy proxies: tests reload engine_runtime, so never a module object

LAYER = 'identity'
VERSION = 1
IMPLEMENTS = 1
RECIPE = 'v1.json'

#: the steps of v1.json that run code (the gates' rules and every handler's code steps), by the body they name
CODE = {
    'identity_gate': ref_to('identity_gate'),
    'identity_wait_engine': ref_to('identity_wait_engine'),
    'hear': ref_to('hear'),
    'identity_route': ref_to('identity_route'),
    'identity_hand': ref_to('identity_hand'),
    'identity_read': ref_to('identity_read'),
    'identity_file': ref_to('identity_file'),
    'identity_verdict': ref_to('identity_verdict'),
    'identity_rung': ref_to('identity_rung'),
    'identity_apply': ref_to('identity_apply'),
    'identity_drop': ref_to('identity_drop'),
    'identity_finding': ref_to('identity_finding'),
    'identity_alarm': ref_to('identity_alarm'),
    'identity_idea': ref_to('identity_idea'),
    'identity_lost': ref_to('identity_lost'),
    'identity_engine': ref_to('identity_engine'),
    'identity_line': ref_to('identity_line'),
    'identity_closed': ref_to('identity_closed'),
}
#: the prompts its soft steps send, and the plain drafts they fall to offline
PROMPT = {
    'identity_gate_soft': ref_to('p_identity_gate'),
    'identity_recognise': ref_to('p_identity_recognise'),
    'identity_take': ref_to('p_identity_take'),
    'identity_enough': ref_to('p_identity_enough'),
    'identity_answer': ref_to('p_identity_answer'),
    'identity_rule': ref_to('p_identity_rule'),
    'identity_weigh': ref_to('p_identity_weigh'),
    'identity_close': ref_to('p_identity_close'),
}
DRAFT = {
    'identity_gate_draft': ref_to('d_identity_gate'),
    'identity_recognise_draft': ref_to('d_identity_recognise'),
    'identity_take_draft': ref_to('d_identity_take'),
    'identity_enough_draft': ref_to('d_identity_enough'),
    'identity_answer_draft': ref_to('d_identity_answer'),
    'identity_rule_draft': ref_to('d_identity_rule'),
    'identity_weigh_draft': ref_to('d_identity_weigh'),
    'identity_close_draft': ref_to('d_identity_close'),
}
#: its covering checks, the shared ones included (S.SHARED_CHECKS)
CHECK = {
    'gate_answer_is_known': ref_to('c_gate_answer_is_known'),
    'facts_are_closed': ref_to('c_facts_are_closed'),
    'said_what_it_did': ref_to('c_said_what_it_did'),
    'journey_is_known': ref_to('c_journey_is_known'),
    'verdict_is_known': ref_to('c_verdict_is_known'),
    'enough_is_shaped': ref_to('c_enough_is_shaped'),
    'answer_names_its_source': ref_to('c_answer_names_its_source'),
    'rule_is_tagged': ref_to('c_rule_is_tagged'),
    'feedback_says_what_changes': ref_to('c_feedback_says_what_changes'),
    'gate_verdict_is_known': ref_to('c_gate_verdict_is_known'),
    'ruling_is_known': ref_to('c_ruling_is_known'),
}
WORDS, LAYOUT = {}, {}


def view(ref, d, events, asks):
    """Identity's pane (S.VIEWS['identity'], A1.17; M3.7): functions_view's read model of the record, by reference. It
    reads _identity_part and not _j2_part, which reads the layers' views and would come back here."""
    return FV._identity_part(ref, d, events)
