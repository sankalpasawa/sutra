"""Evidence adapter (0.5.0-standards): a checklist over a workflow JSON becomes verified evidence rows.
The kernel never opens a file and never runs a checker. A pack carries the rows this adapter produced, with the adapter
as their source and the digest of what was checked as their version. A standard is then an ordinary approved rule over
those predicates, so "does this workflow meet the standard" is a goal like any other: it is supported by evidence,
or it blocks with a named reason, or a reviewed method repairs it."""
from __future__ import annotations
from kernel.core import digest

SOURCE='adapter:standards/workflow@1'
CHECKS={  # predicate: (the question in plain words, the test)
 'has_trigger':('the workflow says what starts it',lambda w:bool((w.get('trigger') or {}).get('kind'))),
 'every_step_has_check':('every step carries a check of its own',lambda w:bool(w.get('steps')) and all(s.get('verify') for s in w['steps'])),
 'has_overall_verify':('the workflow says how the whole is verified',lambda w:bool(w.get('verify'))),
}

def workflow_facts(workflow:dict)->list[dict]:
    """One verified row per check. FALSE is a finding, not an error; the version changes when the workflow changes."""
    version='wf-'+digest(workflow)[:12]
    return [{'predicate':p,'truth':'TRUE' if test(workflow) else 'FALSE','verified':True,'source':SOURCE,
             'version':version,'checked':workflow.get('id'),'question':q} for p,(q,test) in CHECKS.items()]
