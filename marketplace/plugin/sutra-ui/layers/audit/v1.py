"""layers/audit/v1.py -- Audit, version 1: the implementation behind the interface's audit entries (PRD A1.18).

Its recipe is v1.json beside it: the Audit engine object, moved byte for byte from engine_defs/website.json in wave 0.
Every code, prompt, draft and check name the recipe uses is provided here by reference (ref_to): the body stays in
engine_runtime's Audit region until it moves, and a name the layer changes is copied into this module and changed here
(PRD A1.19). WORDS and LAYOUT are empty, so its prompts are still read from the .md bundle. view() returns the pane's
read model by reference.
"""
from layers import R, W, J, S, FV, ref_to  # noqa: F401 -- lazy proxies: tests reload engine_runtime, so never a module object

LAYER = 'audit'
VERSION = 1
IMPLEMENTS = 1
RECIPE = 'v1.json'
CODE = {
    'audit_pick': ref_to('audit_pick'),
    'audit_mechanical': ref_to('audit_mechanical'),
    'audit_file': ref_to('audit_file'),
}
PROMPT = {
    'audit_judge': ref_to('p_audit_judge'),
}
DRAFT = {
    'audit_judge_draft': ref_to('d_audit_judge'),
}
CHECK = {
    'picked_a_sample': ref_to('c_picked_a_sample'),
    'has_a_verdict': ref_to('c_has_a_verdict'),
    'findings_name_where_and_what': ref_to('c_findings_name_where_and_what'),
    'said_what_it_did': ref_to('c_said_what_it_did'),
}
WORDS, LAYOUT = {}, {}


def view(ref, d, events, asks):
    """Audit's pane (S.VIEWS['audit']): functions_view's read model, by reference until this layer holds its own."""
    return FV._j2_part(ref, d, 'Audit', events, asks)
