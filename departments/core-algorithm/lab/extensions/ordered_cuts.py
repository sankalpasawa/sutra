"""Evidence adapter for a cut proposal (0.16.0-ordered, matrix row R82): data before cuts.

A cut (a change that removes cost or time) may ship only with a cited baseline, at least 100 samples behind that
baseline, its guardrails holding, and its own approval. The first three are measurements, so they come from this
adapter: a proposal becomes three verified evidence rows, `<cut>_baseline_cited`, `<cut>_samples_ge_100` and
`<cut>_guardrails_hold`. The kernel never reads a number; the adapter compares them and the kernel reasons over the
rows (as `extensions/standards.py` does for a workflow). The fourth part, the approval, is not a measurement: it is a
question to the founder, one per cut (the `ask` kind).

Each row carries what was measured (`measured`), and its truth follows from that alone, so a reader of the record can
check the row without this file. FALSE is a finding, not an error: a proposal that leaves a part out, or gives it in
another shape, gets FALSE for that part. That holds for what a proposal says it touches too: the list must be there
and every entry a plain name (small letters, digits, dashes); a list that is empty, or holds anything else, fails the
guardrail part, because nobody can tell from it whether something on the will-not-cut list is touched.

The version of a row names its verdict, not its numbers: `cut-` + the digest of the row's name, its truth and the
floors it was tested against. A part measured again with other numbers and the same verdict keeps its version, so
what was made on it (a shipped cut) is not made again; the new numbers are kept in `measured`. A verdict that changes
is a new version, and what was made on the old one no longer counts.

Sources of the three tests: the Speed charter's Iron Rule (no improvement ships without a cited baseline from the
charter's data) and its first principle (no optimization ships without at least 100 samples of its baseline); the
Tokens charter's guardrails (the override count must not rise after a cut, triage accuracy stays at 90 or more, and
four things are never cut)."""
from __future__ import annotations
import re
from kernel.core import digest

SOURCE = 'adapter:ordered/cut@1'
SAMPLE_FLOOR = 100
TRIAGE_FLOOR = 90
DO_NOT_CUT = ('proto-000-text', 'boundary-enforcement-preamble', 'policy-coverage-markers', 'coverage-evidence-requirements')
NAME = re.compile(r'[a-z0-9]+(?:-[a-z0-9]+)*')   # how a proposal names one thing it touches


def _whole(v) -> bool:
    return type(v) is int and v >= 0


def _part(p, name) -> dict:
    return p.get(name) if isinstance(p.get(name), dict) else {}


def _baseline(p) -> dict:
    b = _part(p, 'baseline')
    return {'source': b.get('source'), 'metric': b.get('metric'), 'value': b.get('value')}


def _sample(p) -> dict:
    return {'samples': _part(p, 'baseline').get('samples'), 'floor': SAMPLE_FLOOR}


def _guardrails(p) -> dict:
    g = _part(p, 'guardrails')
    overrides = _part(g, 'override_count_total')
    touches = p.get('touches')
    named = isinstance(touches, list) and bool(touches) and all(type(t) is str and NAME.fullmatch(t) is not None for t in touches)
    return {'override_count_before': overrides.get('before'), 'override_count_now': overrides.get('now'),
            'triage_correct_pct': g.get('triage_correct_pct'), 'triage_floor': TRIAGE_FLOOR,
            'touches_do_not_cut': sorted(set(t for t in touches if t in DO_NOT_CUT)) if named else None}   # None: the proposal does not say, in plain names, what it touches


CHECKS = {  # part: (the question in plain words, what is read from the proposal, the test on what was read)
    'baseline_cited': ('the proposal cites a measured baseline: where it was measured, which metric, what value', _baseline,
                       lambda m: all(type(m[k]) is str and bool(m[k].strip()) for k in ('source', 'metric')) and _whole(m['value'])),
    'samples_ge_100': ('the baseline rests on at least 100 samples', _sample,
                       lambda m: _whole(m['samples']) and m['samples'] >= m['floor']),
    'guardrails_hold': ('the override count has not risen, triage accuracy is 90 or more, and nothing on the do-not-cut list is touched', _guardrails,
                        lambda m: _whole(m['override_count_before']) and _whole(m['override_count_now']) and m['override_count_now'] <= m['override_count_before']
                        and _whole(m['triage_correct_pct']) and m['triage_correct_pct'] >= m['triage_floor'] and m['touches_do_not_cut'] == []),
}


def cut_facts(proposal: dict) -> list:
    """One verified row per measured part of a cut proposal. The proposal names its cut; the rows are `<cut>_<part>`."""
    cut = proposal.get('cut') if isinstance(proposal, dict) else None
    if type(cut) is not str or not cut.replace('_', '').isalnum():
        raise ValueError('A cut proposal names its cut in letters, digits and underscores')
    rows = []
    for part, (question, read, test) in CHECKS.items():
        measured = read(proposal)
        name, truth = f'{cut}_{part}', 'TRUE' if test(measured) else 'FALSE'
        verdict = {'row': name, 'truth': truth, 'floors': {k: v for k, v in measured.items() if k.endswith('floor')}}
        rows.append({'predicate': name, 'truth': truth, 'verified': True, 'source': SOURCE, 'version': 'cut-' + digest(verdict)[:12],
                     'checked': proposal.get('id'), 'question': question, 'measured': measured})
    return rows
