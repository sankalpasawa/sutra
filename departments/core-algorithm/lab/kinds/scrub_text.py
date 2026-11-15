"""The action kind `scrub_text` (0.16.0-ordered, matrix row R73): the scrub as a step whose effect is real code.

The row: a person's words are scrubbed, written locally and then sent, in that order, and a sanitizer error stops
everything after it. The order needs no code: it is what the methods require (pack 120). What a pack cannot say is
that a step FAILED while it ran. That takes a step whose effect is real code, so this file declares one kind.

A kind file registers, with the kernel's register, exactly the kind it is named after. The lab loads it before any
pack file runs, so every State knows the kind, and the record lists this file as the kind's handler, by sha256.

  _check       the kind's hook, run when a pack is applied: a scrub names the row it reads (`scrubs`), and that row
               is one of its method's prerequisites.
  scrub_step   the handler. It reads the words from that prerequisite, runs the sanitizer
               (`scrub` in extensions/ordered_effects.py) and only then writes its effect row, whose version is the
               digest of the clean text: what is written and sent afterwards cites that version. A sanitizer error
               is the handler's own refusal: the kernel's Stop, raised with one text BEFORE anything is written, so
               the kernel records the stop (`Handler refused: sanitizer error: ...`), pays nothing for the step
               and runs nothing after it. A decision that stands on the effect is refused the same way.

Everything here is a local model: no file is written and nothing is sent. The effect is an evidence row."""
from __future__ import annotations
from kernel.core import register, Stop, digest
from extensions.ordered_effects import scrub, SanitizerError

SOURCE = 'LOCAL_SCRUB'


def _check(m):
    if type(m.get('scrubs')) is not str or m['scrubs'] not in m.get('requires', []):
        raise ValueError('A scrub names the row it reads, and that row is one of its prerequisites')


@register('scrub_text', check=_check)
def scrub_step(s, m, mid, deps):
    words = s.fact(m['scrubs'])   # a prerequisite: the kernel has just checked that it reads TRUE
    try:
        clean, redactions = scrub(words.get('text'))
    except SanitizerError as e:
        raise Stop(f'sanitizer error: {e}') from None   # fail closed: nothing has been written yet
    if not s.observe({'predicate': m['effect'], 'truth': 'TRUE', 'verified': True, 'source': f'{SOURCE}:{mid}', 'version': 'scrub-' + digest(clean)[:12],
                      'evidence_kind': 'SIMULATED_LOCAL', 'depends_on': deps, 'clean_text': clean, 'redactions': redactions}):
        raise Stop('A decision stands on this effect')
    return {'model_effect': m['effect'], 'redactions': redactions, 'clean_sha256': digest(clean)}
