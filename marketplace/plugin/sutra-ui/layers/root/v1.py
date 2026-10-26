"""layers/root/v1.py -- Root, version 1: the implementation behind the interface's root entries (PRD A1.18).

Its recipe is the Library's Setup template (engine-templates/setup.json), which A1 does not move, named here by
RECIPE_TEMPLATE. Wave 0 holds the stub: the four dicts are empty, so every code, prompt, draft and check name Setup
uses is engine_runtime's own (the legacy registries) until W1-ROOT moves a body here, and WORDS and LAYOUT are empty,
so the setup prompts are still built inline (p_setup_converse, p_setup_shape). Root has no pane of its own.
"""
from layers import R, W, J, S, FV, ref_to  # noqa: F401 -- lazy proxies: tests reload engine_runtime, so never a module object

LAYER = 'root'
VERSION = 1
IMPLEMENTS = 1
RECIPE_TEMPLATE = 'Setup'
CODE, PROMPT, DRAFT, CHECK = {}, {}, {}, {}
WORDS, LAYOUT = {}, {}
