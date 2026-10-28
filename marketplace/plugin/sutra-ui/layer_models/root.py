"""Root's records (A1.6, A1.7): the pins and the born engine template."""
from pydantic import ConfigDict
from .base import Closed, Open
from .common import keep_order, WORD, BARE, NULLABLE, T, I, C, L, Impl


class RootPins(Closed):
    __def__ = 'root.pins'
    root: Impl = None
    identity: Impl = None
    adaptation: Impl = None
    priority: Impl = None
    coordination: Impl = None
    audit: Impl = None


class EngineTemplateMadeBy(Open):
    __inline__ = True
    by: C('Adaptation')
    dept: T(200) = None
    at: T(40) = None
    idea: NULLABLE(T(300)) = None


class EngineTemplate(Open):
    __def__ = 'engine.template'
    model_config = ConfigDict(json_schema_extra=keep_order(('id', 'name', 'version', 'use_case', 'description', 'instruction', 'reads', 'writes', 'made_by', 'start', 'steps', 'needs', 'kind', 'form')))
    id: WORD('^engine/[a-z0-9][a-z0-9-]*$', 80)
    name: T(40, 1)
    use_case: T(300, 1)
    made_by: EngineTemplateMadeBy
    version: I(1) = None
    description: T(300) = None
    instruction: T(4000) = None
    reads: T(200) = None
    writes: T(40) = None
    start: BARE = None
    steps: L(BARE) = None
    needs: L(T(40)) = None
    kind: C('work') = None
    form: T(60, 1) = None


DEFINES = {
    'root.pins': RootPins,
    'engine.template': EngineTemplate,
}
__all__ = [
    'EngineTemplate', 'RootPins', 'DEFINES',
]
