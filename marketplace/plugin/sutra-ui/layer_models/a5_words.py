"""The words the J2 page says for a department that is not a website (A5.1.3, A5.1.4).

`PageWords` holds only the keys the page's S4 table reads; an omitted key means the prototype's own text, so the website's entry is
the empty object. `KIND_WORDS` is validated once, at import (STR-7); `kind_words(kind)` returns the validated entry or the fallback."""
from pydantic import TypeAdapter

from .base import Closed
from .common import B, E, L, T, WORD
from .a5_types import KIND

TABS = ('docs', 'style', 'lessons', 'playbooks', 'preview')


class PageWords(Closed):
    __def__ = 'page.words'
    team: T(80, 1) = None
    noun: WORD(r'^[a-z][a-z ]{0,38}$', 40) = None
    describe: T(120) = None
    describe_long: T(200) = None
    start: T(200) = None
    ready: T(120) = None
    built: T(40) = None
    rubric: T(80) = None
    style_empty: T(200) = None
    memory_off: T(200) = None
    go_preview: T(60) = None
    new_task: T(60) = None
    retry: T(40) = None
    frame_title: T(80) = None
    steps: L(T(80), 9, 9) = None
    examples: L(T(160), 5) = None
    follow_ups: L(T(80), 4) = None
    pick: B = None
    can_open: B = None
    can_download: B = None
    hide_tabs: L(E(*TABS), 5, 0, True) = None


_STEPS = ['Reading your request…', 'Reading your request…', 'Planning the work…', 'Planning the work…', 'Planning the work…',
          'Planning the work…', 'Doing the work…', 'Checking the result…', 'Almost there…']
_COMMON = {'pick': False, 'can_open': True, 'can_download': False, 'hide_tabs': ['docs', 'style', 'lessons', 'playbooks'],
           'go_preview': 'Open the preview', 'rubric': 'Quality checks', 'built': 'work', 'frame_title': 'Preview',
           'memory_off': 'This department keeps its lessons in its own records.',
           'style_empty': 'No style guide has been filed for this department.', 'new_task': 'Give it another task',
           'retry': 'Try again', 'steps': _STEPS}

#: the fallback is separate from the kind map, so a Library kind named `fallback` cannot collide with it
FALLBACK_WORDS = PageWords(**dict(_COMMON, noun='work'))

_KIND_TABLE = {
    'website': {},                                        # the prototype's own text
    'default': dict(_COMMON, noun='result'),
    'organic': dict(_COMMON, noun='work'),
    'root': dict(_COMMON, noun='department'),
}
_KIND_ADAPTER = TypeAdapter(dict[KIND, PageWords])
#: {kind id: PageWords}, validated once, here (STR-7): a wrong entry stops the import, never a poll
KIND_WORDS = _KIND_ADAPTER.validate_python(_KIND_TABLE)


def kind_words(kind):
    """The validated words of a kind, or the fallback for a kind with none (never None)."""
    return KIND_WORDS[kind] if isinstance(kind, str) and kind in KIND_WORDS else FALLBACK_WORDS


DEFINES = {'page.words': PageWords}
