"""The core base of a standalone owner record: an open object with an id. A4-PORT's definitions may register their own `record`;
the registry prefers that one and falls back to this (registry.core_map)."""
from typing import Annotated

from .base import Open
from .types import Str


class OwnerRecord(Open):
    """The base of every standalone record an owner defines: an id, and any key the owner's fields do not name (kept)."""
    __abstract__ = True
    __def__ = None
    __extensible__ = True
    id: Annotated[str, Str(40, 1, pattern=r'^[a-z0-9][a-z0-9_-]*$', word=True)]


#: the id of every record, which a link by id (R7) holds
ID_PATTERN = r'^[a-z0-9][a-z0-9_-]*$'
