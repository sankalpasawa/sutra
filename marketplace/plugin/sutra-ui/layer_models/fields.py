"""The prompt fields and the owner's values (A1.16)."""
from .base import Open
from .common import FIELD, ANY, T, C, L, M


FieldTask = FIELD(1200, 1, multiline=True)


FieldGuidance = FIELD(2000, 0, multiline=True)


FieldText = FIELD(400, 1)


FieldNote = FIELD(4000, 0, multiline=True)


FieldItems = L(FIELD(160, 1), 12, 1)


class InstructionsValuesValueValueValueValue(Open):
    __inline__ = True
    value: ANY
    at: T(40) = None
    ask: T(40) = None


class Instructions(Open):
    __def__ = 'instructions'
    schema_version: C(1)
    values: M(M(M(M(InstructionsValuesValueValueValueValue))))


DEFINES = {
    'field.task': FieldTask,
    'field.guidance': FieldGuidance,
    'field.text': FieldText,
    'field.note': FieldNote,
    'field.items': FieldItems,
    'instructions': Instructions,
}
__all__ = [
    'FieldGuidance', 'FieldItems', 'FieldNote', 'FieldTask', 'FieldText', 'Instructions', 'DEFINES',
]
