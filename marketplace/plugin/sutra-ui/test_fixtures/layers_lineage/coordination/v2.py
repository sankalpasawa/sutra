"""test_fixtures/layers_lineage/coordination/v2.py -- A2's fixture child of coordination/v1. It lives under test_fixtures/,
never under layers/ (test_every_layer_has_its_version_1_on_disk), and the tests load it with importlib.util.spec_from_file_location
under the name 'layers.coordination.v2' and put it in layers._LOADED. It adds one step after coord.table (the patch), renames
coord.table (an overlay of a free field), overlays one field of the take-tie words, and inherits everything else."""
from layers import R, W, J, S, FV, ref_to, inherit  # noqa: F401 -- lazy proxies; `inherit` is the registry helper (A2)

LAYER = 'coordination'
VERSION = 2
IMPLEMENTS = 2
PARENT = 'coordination/v1'
RECIPE_PATCH = 'v2.patch.json'


def coord_probe(ctx, step, item):
    """The step the patch adds: it says it ran (the check said_what_it_did reads `said`)."""
    return {'said': 'probe'}


globals().update(inherit(PARENT, code={'coord_probe': coord_probe},
                         words={'tie': {'tie': {'task': 'Several functions are ready, and one runs at a time. Say who goes first (version 2).'}}}))
