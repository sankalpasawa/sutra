# Numbers at the evidence door (matrix gap 9, ruling R22). Packs 150 to 159 (two numbers carry a second pack: 152 and 158).
# The kernel reads no number: the adapter writes the number, the band kept as policy and both comparison rows.
# Every pack is built here first, the packs of each recorded look are linted together, and only then is a file written:
# a pack that breaks a convention is not written without a word.
import json
from extensions.numbers import measured, compared, band, amount
from extensions.numbers_lint import problems, ranked

_PACKS = {}


def _pack(name, **fields):
    _PACKS[name] = fields


_BAND = measured('fitness_band', '0.9', source='policy:routine/conformance-band', label='band-v1', unit='ratio')


def _fitness(value, label):
    """One reading of a run's fitness (the share of its routine's written steps found in the run's log) with both rows of the band, made in one call."""
    n = measured('run_fitness', value, source='adapter:conformance/log@1', label=label, unit='ratio')
    return [n] + band(n, '>=', _BAND, 'fitness_in_band', 'fitness_below_band')


# A conformance check: a run is judged against the band of its routine. In band: the goal is supported by evidence. Below: a finding is filed.
_pack('150_conformance_goal', scope='sutra/workflows', goals=['run_judged'], budget={'compute': 5, 'money': 5, 'attention': 2}, preference=['compute', 'money', 'attention'])
_pack('151_conformance_theory', rules=[rule('R-CONFORMS@1', 'run_judged', [['fitness_in_band'], ['finding_filed']], source='reviewed/conformance-check')], evidence=[_BAND])
_pack('152_run_fitness', evidence=_fitness('0.8', 'run-0001'))   # four of the routine's five written steps are in the run's log: the check step was skipped
# The finding's text carries no number (a method is permanent on a State): it points at the comparison row the finding rests on, which is on the books of every record.
_pack('153_finding_method', methods=[method('file-finding@1', 'finding_filed', ['fitness_below_band'], cost={'compute': 1, 'money': 0, 'attention': 1}, action='emit_artifact',
                                            artifact_title='Conformance finding: the run fitness is below the band of its routine; the numbers are on the comparison row this finding rests on (fitness_below_band)')],
      providers={'local-provider': 2}, grants=['action:file-finding@1'])
_pack('154_run_fitness_in_band', evidence=_fitness('1.0', 'run-0002'))   # every written step is in the log
# The same reading with no comparison row beside it: all the lab could say before this version. The goal asks for evidence whatever the number is.
# Brought to a State that already holds comparisons, this pack is what the lint calls a number made again without its comparisons.
_pack('152_number_alone', evidence=_fitness('0.8', 'run-0001')[:1])
# One row authored alone, against a bound written into the comparison: the reading is below the bound and nobody wrote the row that says so.
# The goal cannot file the finding and asks for evidence: the hole that two rows authored apart can have and a band cannot.
_ALONE = measured('run_fitness', '0.85', source='adapter:conformance/log@1', label='run-0004', unit='ratio')
_pack('159_one_row_alone', evidence=[_ALONE, compared(_ALONE, '>=', '0.9', 'fitness_in_band')])
# Fractions of cost as whole units: usd 0.42 of usd 2.00 is 42 of 200 `usd_cents`. A pack that adds a budget dimension names it in its preference.
_pack('155_loan_goal', scope='orgA/lending', goals=['loan_file_reviewed'], budget={'usd_cents': amount('2.00', 100), 'tokens': 10000},
      preference=['usd_cents', 'tokens', 'compute', 'money', 'attention'])
_pack('156_loan_review', evidence=[fact('loan_file_received', 'TRUE', source='fixture/loan-intake')],
      methods=[method('review-loan-file@1', 'loan_file_reviewed', ['loan_file_received'], provider='review-model', cost={'usd_cents': amount('0.42', 100), 'tokens': 3340})],
      providers={'review-model': 1}, grants=['action:review-loan-file@1'])
# A queue ranked by impact under a department ceiling. Both are pack conventions: the order of `goals` is written when the pack is authored, and the
# ceiling is a second dimension that every method under it costs the same as the capped one. The lint holds them; the kernel does not know them.
_IMPACT = {'big_loan_reviewed': '9', 'small_loan_reviewed': '1'}
_pack('157_review_queue', scope='orgA/lending', goals=ranked(['small_loan_reviewed', 'big_loan_reviewed'], _IMPACT), impact=_IMPACT,
      budget={'usd_cents': 200, 'dept_usd_cents': 60}, ceilings={'dept_usd_cents': 'usd_cents'}, preference=['usd_cents', 'dept_usd_cents', 'compute', 'money', 'attention'])
_pack('158_queue_reviews', methods=[method('review-big-loan@1', 'big_loan_reviewed', provider='review-model', cost={'usd_cents': 42, 'dept_usd_cents': 42}),
                                    method('review-small-loan@1', 'small_loan_reviewed', provider='review-model', cost={'usd_cents': 42, 'dept_usd_cents': 42})],
      providers={'review-model': 2}, grants=['action:review-big-loan@1', 'action:review-small-loan@1'])
# The next run: its pack sets the run cap again and leaves the ceiling alone. This is what makes the second dimension a ceiling over runs.
_pack('158_run_cap_again', budget={'usd_cents': 200})

# The authoring lint, on the packs of each recorded look exactly as their files will read (the same JSON).
for _case in (['150_conformance_goal', '151_conformance_theory', '152_run_fitness', '153_finding_method'],
              ['150_conformance_goal', '151_conformance_theory', '154_run_fitness_in_band', '153_finding_method'],
              ['150_conformance_goal', '151_conformance_theory', '152_number_alone', '153_finding_method'],
              ['150_conformance_goal', '151_conformance_theory', '159_one_row_alone', '153_finding_method'],
              ['155_loan_goal', '156_loan_review'], ['157_review_queue', '158_queue_reviews'], ['157_review_queue', '158_queue_reviews', '158_run_cap_again']):
    _found = problems(json.loads(json.dumps([{'schema': 'sutra-extension/2', 'id': _n, **_PACKS[_n]} for _n in _case])))
    if _found:
        raise SystemExit('pack lint: ' + '; '.join(_found))
# Only now is a file written, each pack under its own name in plain sight (the applier reads the names of the packs a file authors off these calls).
pack('150_conformance_goal', **_PACKS.pop('150_conformance_goal'))
pack('151_conformance_theory', **_PACKS.pop('151_conformance_theory'))
pack('152_run_fitness', **_PACKS.pop('152_run_fitness'))
pack('152_number_alone', **_PACKS.pop('152_number_alone'))
pack('153_finding_method', **_PACKS.pop('153_finding_method'))
pack('154_run_fitness_in_band', **_PACKS.pop('154_run_fitness_in_band'))
pack('155_loan_goal', **_PACKS.pop('155_loan_goal'))
pack('156_loan_review', **_PACKS.pop('156_loan_review'))
pack('157_review_queue', **_PACKS.pop('157_review_queue'))
pack('158_queue_reviews', **_PACKS.pop('158_queue_reviews'))
pack('158_run_cap_again', **_PACKS.pop('158_run_cap_again'))
pack('159_one_row_alone', **_PACKS.pop('159_one_row_alone'))
if _PACKS:
    raise SystemExit('pack file numbers: built and not written: ' + ', '.join(sorted(_PACKS)))
