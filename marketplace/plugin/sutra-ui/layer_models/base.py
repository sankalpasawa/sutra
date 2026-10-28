"""The base classes of every model: SutraModel, Closed, Open and Mixin (A4.4.1).

A class is abstract exactly when its own body says `__abstract__ = True`; the attribute is not inherited, so a child that
does not repeat it is concrete (rule R4). The guard is a custom __init__, which pydantic's adapter calls too, so validating a
value against an abstract class raises as well as making one does (G11)."""
from pydantic import BaseModel, ConfigDict


def is_abstract(cls):
    return bool(cls.__dict__.get('__abstract__', False))


class SutraModel(BaseModel):
    """Every interface model. `__def__` is the definition name a class answers to (None for a helper), `__extensible__` says
    an owner may build on it, `__version__` is the model's own version (R10)."""
    model_config = ConfigDict(hide_input_in_errors=True, protected_namespaces=())
    __abstract__ = True
    __def__ = None
    __extensible__ = False
    __version__ = 1

    def __init__(self, /, **data):
        if is_abstract(type(self)):
            raise TypeError('%s is abstract' % type(self).__name__)
        super().__init__(**data)

    @classmethod
    def __pydantic_init_subclass__(cls, **kw):
        # fields exist only now (not in __init_subclass__), so the class rules are checked here
        super().__pydantic_init_subclass__(**kw)
        if cls.__module__ == __name__:
            return                                  # the roots below: the rules import this module
        from . import rules
        rules.check_class(cls)


class Closed(SutraModel):
    """A closed object: a key that is not a field is a fault (additionalProperties false)."""
    model_config = ConfigDict(extra='forbid')
    __abstract__ = True


class Open(SutraModel):
    """An open object: an unknown key passes and is kept."""
    model_config = ConfigDict(extra='allow')
    __abstract__ = True


class Mixin(SutraModel):
    """An abstract group of fields (R5). Never a definition."""
    __abstract__ = True
