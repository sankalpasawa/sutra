"""The families of the interface, as discriminated unions (A4.4, rule R8).

`AskForm` is the one the core has: a family of `identity.ask`, one child for each kind of ask. A child adds the tag (a `kind`
that holds exactly one value) and nothing that rejects, so a value of a known kind is judged the same through the family as by
`identity.ask` itself (R2 and R3 hold by construction, and `rules.check_class` proves R2 when each child is made), and `identity.ask`
does not change (A4-18). The union is registered as `identity.ask.form` for the editor's graph; it is not one of the 130
definitions and is never exported."""
from typing import Annotated, Any, Literal, Union

from pydantic import Field, create_model
from pydantic_core import core_schema

import layer_consts as K
from . import registry
from .base import Open
from .identity import IdentityAsk
from .types import Enum


class Tag(Enum):
    """The tag of a child of a family: an enum of one value that is also a literal, so the union can dispatch on it."""

    def __get_pydantic_core_schema__(self, source, handler):
        return core_schema.literal_schema(list(self.values))


class AskForm(IdentityAsk):
    """The family: the abstract base of the forms (R4: abstract, so a value is never validated against it)."""
    __abstract__ = True


def _child(kind):
    return create_model('AskForm' + ''.join(p.capitalize() for p in kind.split('_')), __base__=AskForm,
                        __module__=__name__, kind=(Annotated[Literal[kind], Tag(kind)], ...))


#: one child for each kind of ask, in the order ASK_KINDS lists them
CHILDREN = {kind: _child(kind) for kind in K.ASK_KINDS}

ASK_FORM = Annotated[Union[tuple(CHILDREN.values())], Field(discriminator='kind')]

registry.register('identity.ask.form', ASK_FORM)

DEFINES = {}                # nothing here is one of the 130: the family is registered above, for the editor and for R8's test
__all__ = ['ASK_FORM', 'AskForm', 'CHILDREN', 'Tag']
