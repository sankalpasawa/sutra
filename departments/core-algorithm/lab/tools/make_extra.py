"""Cross-cutting extensions applied to actual immutable recorded traces."""
from __future__ import annotations
from pathlib import Path
import sys,json
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from extensions.knowledge import compile_pattern,signal_priority
from extensions.reflection import reflect,minimal_graph_diff
from extensions.j2_projection import to_j2_proposed_atom_views
from extensions.implementation import to_implementation
from kernel.core import digest,State
from tools.run_all import pack
source=json.loads((ROOT/'results'/'actual_run_records.json').read_text())
runs=[r['outcome'] for r in source['cases'] if r['outcome']]
def state_of(case_index):
    return State.from_packs([pack(n) for n in source['cases'][case_index]['packs']])
pattern={'id':'R-PATTERN-ENQUIRY','slots':['S','B'],'head':'enquiry_complete_${S}',
         'branches':[['received_${S}','retrievable_${B}'],['inbox_record_${B}']],
         'source':'reviewed/pattern-catalogue','source_version':'1'}
unsigned=compile_pattern(pattern,{'S':'siteA','B':'teamA'})
reviewed=compile_pattern(pattern,{'S':'siteA','B':'teamA'},
        {'approved':True,'pattern_hash':digest(pattern),'reviewer':'external-reviewer-fixture'})
signals=signal_priority([
 {'id':'f1','source':'synthetic:CRM-problem','decision_impact':9,'applicable':True},
 {'id':'f2','source':'synthetic:font-color','decision_impact':1,'applicable':True},
 {'id':'f3','source':'synthetic:other-region-law','decision_impact':10,'applicable':False}])
source['meta_extensions']={
  'knowledge_compiler':{'unreviewed_rule':unsigned,'reviewed_rule':reviewed,'signals_ranked':signals},
  'reflection':reflect(runs),
  'graph_diff_nuance':minimal_graph_diff(runs[4],runs[6]),
  'j2_projection':to_j2_proposed_atom_views(runs[14]),
  # Implementation version (program rung L1): the order plan with the notification rule (case 06) and the
  # enquiry plan with the privacy rule (case 14), each turned into a runnable workflow shape + scaffold + page.
  'implementation':to_implementation(runs[6],state_of(6)),
  'implementation_enquiry':to_implementation(runs[14],state_of(14)),
  'stage_boundary':{'implemented':'Finite local rule interpreter, predeclared components, and a proposal-only implementation generator (workflow shape, atoms, scaffold, page)',
                    'proposed':'Knowledge extraction from unstructured information, true domain autonomy, real J2 adapter, running a generated workflow in the daemon, external effect verification, open-world federation, Native v1-v5 claims'}
}
(ROOT/'results'/'actual_run_records.json').write_text(json.dumps(source,indent=2,ensure_ascii=False)+'\n')
print('ADDED five lenses: reviewed knowledge compilation, graph diff, reflection, proposed J2 projection, proposal-only implementation versions (2)')
