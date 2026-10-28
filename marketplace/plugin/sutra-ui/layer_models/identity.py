"""Identity's records (A1.6, A1.8): the done-when item, the rule and the ask."""
from pydantic import Field
import layer_consts as K
from .base import Closed, Open
from .common import ANYOF, NULLABLE, T, I, B, E, L, IdItem, Option


class IdentityDoneItem(Closed):
    __def__ = 'identity.done_item'
    id: IdItem
    text: T(300, 1)
    how: T(200) = None
    level: T(200) = None
    confirm: T(200) = None


class IdentityRule(Open):
    __def__ = 'identity.rule'
    line: T(2000)
    id: T(80) = None
    tag: NULLABLE(T(20)) = None
    since: NULLABLE(T(40)) = None
    from_: NULLABLE(T(8000)) = Field(default=None, alias='from')
    scope: T(20) = None


class IdentityAskChosen(Open):
    __inline__ = True
    id: T(64) = None
    label: T(120) = None
    at: T(40) = None
    by: T(80) = None
    words: NULLABLE(T(2000)) = None


class IdentityAskDoubt(Open):
    __inline__ = True
    engine: T(40) = None
    doubt: T(600) = None
    shown: T(600) = None
    fallback: T(600) = None
    line: NULLABLE(I(0)) = None
    answered: ANYOF(I(0), B) = None


class IdentityAsk(Open):
    __def__ = 'identity.ask'
    id: T(40, 1)
    kind: E(*K.ASK_KINDS)
    status: E(*K.ASK_STATUSES)
    text: T(4000) = None
    created: T(40) = None
    decided: NULLABLE(T(40)) = None
    by: NULLABLE(T(80)) = None
    engine: NULLABLE(T(60)) = None
    thread: NULLABLE(T(80)) = None
    options: L(Option, 3) = None
    chosen: NULLABLE(IdentityAskChosen) = None
    items: L(IdentityDoneItem, 12) = None
    cycle_id: NULLABLE(T(80)) = None
    doubt: IdentityAskDoubt = None


DEFINES = {
    'identity.done_item': IdentityDoneItem,
    'identity.rule': IdentityRule,
    'identity.ask': IdentityAsk,
}
__all__ = [
    'IdentityAsk', 'IdentityDoneItem', 'IdentityRule', 'DEFINES',
]
