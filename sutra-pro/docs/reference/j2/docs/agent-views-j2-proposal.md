# Agent-readable views in live runs: a proposal for j2.py

**Status**: proposal only. j2.py is not changed by the agent-readable-views branch; `python3 j2_agent_views.py build <run_dir>` builds every JSON from a saved run folder today. This note says where j2.py would write the same JSON during a live run, behind one flag, so a running run's Artifacts pane shows the Agent-readable tab as it goes.

## The flag

`J2_AGENT_VIEWS=1` (default off). Read per call like `artifact_schema_on()` (j2.py:446), so tests can switch it:

```python
def agent_views_on():
    """J2_AGENT_VIEWS=1 (default off): every artifact the run writes also gets its agent-readable JSON (agent-views/1)."""
    return os.environ.get("J2_AGENT_VIEWS") == "1"
```

With the flag off nothing changes. With it on, j2.py calls into `j2_agent_views` at four points; every call is wrapped so a failure never changes the run (the pattern `_save_summary` already uses for the atom/1 views at j2.py:9549).

## Where

| When | Where in j2.py | What is written | By |
|---|---|---|---|
| A builder's data passed its three layers | after `_artifact_receipts` in the build loop (j2.py:7321), where the artifact-schema data is saved beside the document | `prd.json` / `hld.json` / `lld.json` / `design.json` gain `model`, `valid`, `validation`; a website section gets `site/sections/<id>.json` from the reply itself (so `implements` and `facts_used` are recorded, which the saved-run build cannot recover) | `j2_agent_views.build_documents(d, decs)`, `build_design`, `build_sections` (or a per-section writer taking the reply, see below) |
| A guide is filed | where a planning workflow's `.md` output is written under `artifacts/` | `artifacts/<name>.json` | `j2_agent_views.build_guides(d, workflows, facts)` |
| An audit ends | `_save_audits` (j2.py:8069, `self.save("audits.json", ...)`) | `agent/audits/A-<n>.json` for the new audit | `j2_agent_views.build_audits(d, goal)` |
| The run ends | `_save_summary` (j2.py:9541), beside `summary.json` | `agent/goal.json`, `agent/workflows.json`, `agent/receipts.json`, `agent/conditions.json`, and a last pass over everything (`build(d)`) | `j2_agent_views.build(d, quiet=True)` |

The Documents group and the audit rows need nothing live: `j2_artifacts.groups()` reads the folder.

## Two small changes to j2_agent_views.py when j2.py calls it

1. `build_sections(d, decs, reply=None, section_id=None)`: when j2.py hands over the builder's reply for one section, write that section's JSON from the reply, not from the page, so `implements` and `facts_used` are kept. The saved-run path stays as the fallback.
2. `build_guides` takes the one file just written instead of scanning `artifacts/`, so a long run does not rebuild every guide on each write.

## Not in this proposal (follow-ups)

- Template families for guides and audits in the template library (`ARTIFACTS` stays the five artifact types for now): a `guide` family whose generic is `j2_agent_models.Guide` and whose specialised templates a planning workflow could extend, and an `audit` family from `AuditResult`. Both would show in the library's By artifact view with the same Agent-readable / Human-readable tabs.
- Live `valid` for the summary (`agent/summary.json`): `summary.json` has no model yet.

## Cost

One `json.dump` per artifact write, no AI call, no new dependency (Pydantic 2 is already required). The writer never reads `.env`, `calls.jsonl` or any secret.
