"""layers/identity/v1.py -- Identity, version 1: the implementation behind the interface's identity entries (PRD A1.18).

Its recipe is v1.json beside it: the Identity engine object, moved byte for byte from engine_defs/website.json in wave 0.
Wave 0 holds the stub: the four dicts are empty, so every code, prompt, draft and check name the recipe uses is
engine_runtime's own (the legacy registries) until this layer's package moves a body here, and WORDS and LAYOUT are
empty, so its prompts are still read from the .md bundle. view() returns the pane's read model by reference.
"""
from layers import R, W, J, S, FV, ref_to  # noqa: F401 -- lazy proxies: tests reload engine_runtime, so never a module object

LAYER = 'identity'
VERSION = 1
IMPLEMENTS = 1
RECIPE = 'v1.json'
CODE, PROMPT, DRAFT, CHECK = {}, {}, {}, {}
WORDS, LAYOUT = {}, {}


def view(ref, d, events, asks):
    """Identity's pane (S.VIEWS['identity']): functions_view's read model, by reference until this layer holds its own."""
    return FV._j2_part(ref, d, 'Identity', events, asks)
