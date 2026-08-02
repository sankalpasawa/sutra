#!/usr/bin/env python3
"""fixture_seed.py -- writes a complete on-disk Sutra registry fixture for dev/test.

Translates the deliberate-defect scenario in
the reviewed seed fixture into the REAL on-disk
schema placement_engine.py actually reads: per-file domains/<ref>.json,
per-file charters/<C-id>.json (hashed body) + <C-id>.page.json (mutable
sidecar, S2.2 split), placements/PL-<id>.json + placements/CURRENT.jsonl,
and domains/INDEX.jsonl.

USAGE
    python3 fixture_seed.py <target_dir>

SAFETY
    This script writes ONLY inside <target_dir>. It never reads or writes
    SUTRA_NATIVE_HOME, never touches ~/.sutra-native. Callers are responsible
    for pointing SUTRA_NATIVE_HOME at <target_dir> for any process that then
    reads the fixture back (e.g. via placement_engine.load_domains()).

    This script does NOT import placement_engine and does NOT call
    mint_domain / write_placement / restructure / retire / any mutator -- it
    writes the on-disk JSON shapes directly so the seeded ids/timestamps are
    exactly reproducible across runs (content-addressed charter ids are
    computed with the SAME hash rule placement_engine.py uses, so the fixture
    is byte-identical to what the real engine would have produced).
"""
import hashlib
import json
import os
import sys

DAY = 86400000
NOW = 1785542400000  # 2026-08-01T00:00:00Z -- fixed so every derived band is deterministic

CHARTER_SCHEMA = 2


def _canonical(obj):
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _sha(obj):
    return hashlib.sha256(_canonical(obj).encode("utf-8")).hexdigest()


def charter_id_of(body):
    """Mirrors placement_engine.charter_id_of: sha256 of the body with `id` excluded."""
    return "C-" + _sha(dict((k, v) for k, v in body.items() if k != "id"))[:16]


# ---------------------------------------------------------------- domains ---
# Shape = real on-disk schema (placement_engine.py mint_domain / _save_domain,
# post-Phase-0 lifecycle fields). Translated 1:1 from seed.js DOMAINS.

DOMAINS = [
    {"ref": "dref-1a0f4c2b9e7d6053", "parent_ref": None, "name": "Sutra Labs",
     "tenant_id": "T-local", "status": "active", "origin": "operator",
     "touched_by_operator": True, "accountable": "tenant_owner", "authority": {},
     "principles": [],
     "mint_evidence": ["sutra", "labs", "root", "company"],
     "ts_minted_ms": NOW - 400 * DAY,
     "successor_refs": [], "disposition_event_id": None, "retired_at_ms": None,
     "retire_reason_code": None, "retire_note": None},

    {"ref": "dref-2b7e91c04d3a8f16", "parent_ref": "dref-1a0f4c2b9e7d6053", "name": "Research",
     "tenant_id": "T-local", "status": "active", "origin": "operator",
     "touched_by_operator": True, "accountable": "tenant_owner", "authority": {},
     "principles": [],
     "mint_evidence": ["research", "market", "competitor", "landscape", "pricing"],
     "ts_minted_ms": NOW - 360 * DAY,
     "successor_refs": [], "disposition_event_id": None, "retired_at_ms": None,
     "retire_reason_code": None, "retire_note": None},

    {"ref": "dref-3c8f02d15e4b9a27", "parent_ref": "dref-1a0f4c2b9e7d6053", "name": "Engine",
     "tenant_id": "T-local", "status": "active", "origin": "operator",
     "touched_by_operator": True, "accountable": "tenant_owner", "authority": {},
     "principles": [],
     "mint_evidence": ["engine", "placement", "classify", "routing", "score"],
     "ts_minted_ms": NOW - 355 * DAY,
     "successor_refs": [], "disposition_event_id": None, "retired_at_ms": None,
     "retire_reason_code": None, "retire_note": None},

    {"ref": "dref-4d9013e26f5cab38", "parent_ref": "dref-1a0f4c2b9e7d6053", "name": "Client Delivery",
     "tenant_id": "T-local", "status": "active", "origin": "operator",
     "touched_by_operator": True, "accountable": "tenant_owner", "authority": {},
     "principles": [],
     "mint_evidence": ["client", "delivery", "acme", "onboarding", "report", "invoice"],
     "ts_minted_ms": NOW - 350 * DAY,
     "successor_refs": [], "disposition_event_id": None, "retired_at_ms": None,
     "retire_reason_code": None, "retire_note": None},

    {"ref": "dref-5ea124f3706dbc49", "parent_ref": "dref-1a0f4c2b9e7d6053", "name": "Platform",
     "tenant_id": "T-local", "status": "active", "origin": "operator",
     "touched_by_operator": True, "accountable": "tenant_owner", "authority": {},
     "principles": [],
     "mint_evidence": ["platform", "infra", "runtime", "deploy", "oncall", "recovery"],
     "ts_minted_ms": NOW - 348 * DAY,
     "successor_refs": [], "disposition_event_id": None, "retired_at_ms": None,
     "retire_reason_code": None, "retire_note": None},

    # DEFECT 1 -- retired domain with PLURAL successor_refs.
    {"ref": "dref-6fb235047817cd5a", "parent_ref": "dref-1a0f4c2b9e7d6053", "name": "Agent Ops",
     "tenant_id": "T-local", "status": "retired", "origin": "operator",
     "touched_by_operator": True, "accountable": "tenant_owner", "authority": {},
     "principles": [],
     "mint_evidence": ["ops", "oncall", "rota", "fleet", "incident"],
     "ts_minted_ms": NOW - 340 * DAY,
     "successor_refs": ["dref-5ea124f3706dbc49", "dref-3c8f02d15e4b9a27"],
     "disposition_event_id": "plan-2026-06-14-dissolve-agent-ops",
     "retired_at_ms": NOW - 48 * DAY, "retire_reason_code": "merged",
     "retire_note": "Fleet work absorbed by Platform; routing work by Engine."},

    # Name reuse: same name, same parent, distinct ref (legal -- retired sibling).
    {"ref": "dref-7ac346158928de6b", "parent_ref": "dref-1a0f4c2b9e7d6053", "name": "Agent Ops",
     "tenant_id": "T-local", "status": "active", "origin": "operator",
     "touched_by_operator": True, "accountable": "tenant_owner", "authority": {},
     "principles": [],
     "mint_evidence": ["agent", "ops", "fleet", "supervision"],
     "ts_minted_ms": NOW - 20 * DAY,
     "successor_refs": [], "disposition_event_id": None, "retired_at_ms": None,
     "retire_reason_code": None, "retire_note": None},

    # DEFECT 2 -- overlapping descriptions (ORG-001 warn pair).
    {"ref": "dref-8bd457269a39ef7c", "parent_ref": "dref-2b7e91c04d3a8f16", "name": "Market Intel",
     "tenant_id": "T-local", "status": "active", "origin": "operator",
     "touched_by_operator": True, "accountable": "tenant_owner", "authority": {},
     "principles": [],
     "mint_evidence": ["competitor", "pricing", "market", "landscape", "analysis", "research"],
     "ts_minted_ms": NOW - 300 * DAY,
     "successor_refs": [], "disposition_event_id": None, "retired_at_ms": None,
     "retire_reason_code": None, "retire_note": None},

    {"ref": "dref-9ce568370ab4f08d", "parent_ref": "dref-2b7e91c04d3a8f16", "name": "Synthesis",
     "tenant_id": "T-local", "status": "active", "origin": "operator",
     "touched_by_operator": True, "accountable": "tenant_owner", "authority": {},
     "principles": [],
     "mint_evidence": ["synthesis", "brief", "summary", "market", "landscape", "competitor", "pricing"],
     "ts_minted_ms": NOW - 298 * DAY,
     "successor_refs": [], "disposition_event_id": None, "retired_at_ms": None,
     "retire_reason_code": None, "retire_note": None},

    {"ref": "dref-adf679481bc5019e", "parent_ref": "dref-3c8f02d15e4b9a27", "name": "Placement Engine",
     "tenant_id": "T-local", "status": "active", "origin": "operator",
     "touched_by_operator": True, "accountable": "tenant_owner", "authority": {},
     "principles": [],
     "mint_evidence": ["classify", "score", "floor", "flock", "placement", "engine"],
     "ts_minted_ms": NOW - 290 * DAY,
     "successor_refs": [], "disposition_event_id": None, "retired_at_ms": None,
     "retire_reason_code": None, "retire_note": None},

    # system-minted -> no description key. origin=system-minted, touched=False.
    {"ref": "dref-be078a592cd612af", "parent_ref": "dref-3c8f02d15e4b9a27", "name": "Evaluation",
     "tenant_id": "T-local", "status": "active", "origin": "system-minted",
     "touched_by_operator": False, "accountable": "tenant_owner", "authority": {},
     "principles": [],
     "mint_evidence": ["eval", "harness", "rubric", "benchmark"],
     "ts_minted_ms": NOW - 60 * DAY,
     "successor_refs": [], "disposition_event_id": None, "retired_at_ms": None,
     "retire_reason_code": None, "retire_note": None},

    {"ref": "dref-cf189b6a3de723b0", "parent_ref": "dref-4d9013e26f5cab38", "name": "Onboarding",
     "tenant_id": "T-local", "status": "active", "origin": "operator",
     "touched_by_operator": True, "accountable": "tenant_owner", "authority": {},
     "principles": [],
     "mint_evidence": ["onboarding", "migration", "cutover", "acme"],
     "ts_minted_ms": NOW - 200 * DAY,
     "successor_refs": [], "disposition_event_id": None, "retired_at_ms": None,
     "retire_reason_code": None, "retire_note": None},

    # system-minted, no description, ZERO charters -> ORG-008
    {"ref": "dref-d029ac7b4ef834c1", "parent_ref": "dref-4d9013e26f5cab38", "name": "Support QA",
     "tenant_id": "T-local", "status": "active", "origin": "system-minted",
     "touched_by_operator": False, "accountable": "tenant_owner", "authority": {},
     "principles": [],
     "mint_evidence": ["support", "escalation", "qa", "ticket"],
     "ts_minted_ms": NOW - 11 * DAY,
     "successor_refs": [], "disposition_event_id": None, "retired_at_ms": None,
     "retire_reason_code": None, "retire_note": None},

    # DEFECT 6 -- live namesake under a DIFFERENT parent (ORG-018 demonstrable, not itself a violation).
    {"ref": "dref-b41c7e92af508d63", "parent_ref": "dref-4d9013e26f5cab38", "name": "Evaluation",
     "tenant_id": "T-local", "status": "active", "origin": "operator",
     "touched_by_operator": True, "accountable": "tenant_owner", "authority": {},
     "principles": [],
     "mint_evidence": ["evaluation", "review", "outcome", "retro", "client"],
     "ts_minted_ms": NOW - 9 * DAY,
     "successor_refs": [], "disposition_event_id": None, "retired_at_ms": None,
     "retire_reason_code": None, "retire_note": None},

    {"ref": "dref-e13abd8c50f945d2", "parent_ref": "dref-5ea124f3706dbc49", "name": "Infrastructure",
     "tenant_id": "T-local", "status": "active", "origin": "operator",
     "touched_by_operator": True, "accountable": "tenant_owner", "authority": {},
     "principles": [],
     "mint_evidence": ["terraform", "runbook", "backup", "restore", "infra"],
     "ts_minted_ms": NOW - 330 * DAY,
     "successor_refs": [], "disposition_event_id": None, "retired_at_ms": None,
     "retire_reason_code": None, "retire_note": None},

    # DEFECT 6 -- second tenant, commingled root (T-acme, parent_ref None).
    {"ref": "dref-f24bce9d610a56e3", "parent_ref": None, "name": "Client Success",
     "tenant_id": "T-acme", "status": "active", "origin": "operator",
     "touched_by_operator": True, "accountable": "tenant_owner", "authority": {},
     "principles": [],
     "mint_evidence": ["acme", "success", "qbr", "renewal"],
     "ts_minted_ms": NOW - 40 * DAY,
     "successor_refs": [], "disposition_event_id": None, "retired_at_ms": None,
     "retire_reason_code": None, "retire_note": None},
]

_DESCRIPTIONS = {
    "dref-1a0f4c2b9e7d6053": "The company root. Holds the operating charter and the unfiled queue.",
    "dref-2b7e91c04d3a8f16": "Everything upstream of a decision: market landscape, competitors, pricing.",
    "dref-3c8f02d15e4b9a27": "The placement engine and everything that decides where work goes.",
    "dref-4d9013e26f5cab38": "Client-facing engagements: onboarding, reporting, escalations.",
    "dref-5ea124f3706dbc49": "Runtime the agents execute on: infrastructure, on-call, disaster recovery.",
    "dref-6fb235047817cd5a": "Ran the agent fleet. Dissolved into Platform and Engine.",
    "dref-7ac346158928de6b": "Re-minted after the dissolution proved premature. Different ref, same name.",
    "dref-8bd457269a39ef7c": "Competitor and pricing analysis, market landscape research for the quarter.",
    "dref-9ce568370ab4f08d": "Market landscape research and competitor briefs, pricing analysis synthesis.",
    "dref-adf679481bc5019e": "classify(), score_domains(), the 0.45 floor and the locks around them.",
    "dref-be078a592cd612af": None,
    "dref-cf189b6a3de723b0": "New client cutovers, migration plans, first-90-days runbooks.",
    "dref-d029ac7b4ef834c1": None,
    "dref-b41c7e92af508d63": "Post-delivery review of client outcomes against what the engagement promised.",
    "dref-e13abd8c50f945d2": "Terraform, runbooks, backup and restore.",
    "dref-f24bce9d610a56e3": "Acme's own department. Should not be visible here.",
}

_SEED_CHARTERS = [
    {"seed_id": "C-04ee71", "title": "Sutra Labs operating charter",
     "purpose": "Catch-all mandate for work no department yet owns.",
     "domain_ref": "dref-1a0f4c2b9e7d6053", "kind": "standing", "status": "active",
     "scope_in": ["unclassified work", "new capability probes"], "scope_out": ["client delivery"],
     "linked_domain_refs": [], "supersedes": None, "artifacts": [], "ts_ms": NOW - 400 * DAY},

    {"seed_id": "C-3f9a11", "title": "Quarterly client reporting",
     "purpose": "Produce and ship the quarterly client report.",
     "domain_ref": "dref-4d9013e26f5cab38", "kind": "standing", "status": "active",
     "scope_in": ["quarterly report", "invoice summary", "client escalation"], "scope_out": ["migration work"],
     "linked_domain_refs": ["dref-cf189b6a3de723b0"], "supersedes": None,
     "artifacts": ["reports/q3-acme-summary.md"], "ts_ms": NOW - 350 * DAY},

    {"seed_id": "C-77b104", "title": "Acme migration",
     "purpose": "Move Acme onto the new runtime.",
     "domain_ref": "dref-cf189b6a3de723b0", "kind": "project", "status": "shipped",
     "scope_in": ["acme migration", "cutover checklist"], "scope_out": ["ongoing support"],
     "linked_domain_refs": ["dref-4d9013e26f5cab38"], "supersedes": None,
     "artifacts": ["clients/acme/migration-plan.md"], "ts_ms": NOW - 190 * DAY},

    {"seed_id": "C-2c4e90", "title": "Market intel sweep",
     "purpose": "Continuous competitor and pricing watch.",
     "domain_ref": "dref-8bd457269a39ef7c", "kind": "standing", "status": "active",
     "scope_in": ["competitor analysis", "pricing analysis", "market landscape"], "scope_out": ["customer briefs"],
     "linked_domain_refs": ["dref-9ce568370ab4f08d"], "supersedes": None, "artifacts": [],
     "ts_ms": NOW - 300 * DAY},

    {"seed_id": "C-9d13a7", "title": "Synthesis briefs",
     "purpose": "Turn raw intel into weekly briefs.",
     "domain_ref": "dref-9ce568370ab4f08d", "kind": "standing", "status": "active",
     "scope_in": ["competitor analysis", "pricing analysis", "weekly brief"], "scope_out": ["raw scraping"],
     "linked_domain_refs": ["dref-8bd457269a39ef7c"], "supersedes": None, "artifacts": [],
     "ts_ms": NOW - 298 * DAY},

    {"seed_id": "C-5a7b22", "title": "Placement engine maintenance",
     "purpose": "Keep classify() calibrated and the locks correct.",
     "domain_ref": "dref-adf679481bc5019e", "kind": "standing", "status": "active",
     "scope_in": ["classifier calibration", "lock correctness", "confidence floor"], "scope_out": ["UI"],
     "linked_domain_refs": [], "supersedes": None, "artifacts": ["engine/placement_engine.py"],
     "ts_ms": NOW - 290 * DAY},

    {"seed_id": "C-b41f08", "title": "Eval harness v2",
     "purpose": "Rebuild the routing eval harness.",
     "domain_ref": "dref-be078a592cd612af", "kind": "project", "status": "active",
     "scope_in": ["eval harness", "rubric", "benchmark set"], "scope_out": ["production routing"],
     "linked_domain_refs": [], "supersedes": None, "artifacts": ["eval/harness-v2-spec.md"],
     "ts_ms": NOW - 55 * DAY},

    {"seed_id": "C-6e0d35", "title": "Infra runbook v2",
     "purpose": "On-call and restore procedures, current revision.",
     "domain_ref": "dref-e13abd8c50f945d2", "kind": "standing", "status": "active",
     "scope_in": ["oncall runbook", "terraform", "restore drill"], "scope_out": ["client comms"],
     "linked_domain_refs": [], "supersedes": "C-1b2c44", "artifacts": ["infra/runbook-oncall.md"],
     "ts_ms": NOW - 30 * DAY,
     "handoff": {"from_domain_ref": "dref-6fb235047817cd5a", "from_charter_id": "C-8812f0",
                 "open_placements_n": 1, "artifacts": ["ops/oncall-rota-2026.md"],
                 "reason": "merged", "ts_ms": NOW - 48 * DAY}},

    {"seed_id": "C-1b2c44", "title": "Infra runbook",
     "purpose": "On-call and restore procedures.",
     "domain_ref": "dref-e13abd8c50f945d2", "kind": "standing", "status": "retired",
     "scope_in": ["oncall runbook", "restore drill"], "scope_out": [],
     "linked_domain_refs": [], "supersedes": None, "artifacts": [], "ts_ms": NOW - 320 * DAY},

    # DEFECT 3 -- charter on a tombstone (status active, domain retired).
    {"seed_id": "C-8812f0", "title": "On-call rota",
     "purpose": "Who is on call, and when.",
     "domain_ref": "dref-6fb235047817cd5a", "kind": "standing", "status": "active",
     "scope_in": ["oncall rota", "escalation ladder"], "scope_out": [],
     "linked_domain_refs": [], "supersedes": None, "artifacts": ["ops/oncall-rota-2026.md"],
     "ts_ms": NOW - 340 * DAY},

    # DEFECT 5 -- stale standing charter (newest placement 214d old).
    {"seed_id": "C-0a41cd", "title": "Disaster recovery drill",
     "purpose": "Prove the restore path quarterly.",
     "domain_ref": "dref-5ea124f3706dbc49", "kind": "standing", "status": "active",
     "scope_in": ["disaster recovery", "restore drill", "failover"], "scope_out": ["routine backup"],
     "linked_domain_refs": ["dref-e13abd8c50f945d2"], "supersedes": None, "artifacts": [],
     "ts_ms": NOW - 330 * DAY, "attested_ms": None},

    # second tenant's charter, commingled.
    {"seed_id": "C-e5f7b9", "title": "Client success playbook",
     "purpose": "Acme renewal and QBR motion.",
     "domain_ref": "dref-f24bce9d610a56e3", "kind": "standing", "status": "active",
     "scope_in": ["qbr", "renewal", "success plan"], "scope_out": [],
     "linked_domain_refs": [], "supersedes": None, "artifacts": [], "ts_ms": NOW - 40 * DAY},
]

_SEED_PLACEMENTS = [
    {"seed_id": "p-01", "work_ref": {"kind": "file", "id": "reports/q3-acme-summary.md"},
     "domain_ref": "dref-4d9013e26f5cab38", "charter_seed_id": "C-3f9a11", "confidence": 0.81,
     "origin": "hook", "phase": "open", "tenant_id": "T-local", "supersedes_seed": None, "ts_ms": NOW - 2 * DAY},
    {"seed_id": "p-02", "work_ref": {"kind": "file", "id": "clients/acme/migration-plan.md"},
     "domain_ref": "dref-cf189b6a3de723b0", "charter_seed_id": "C-77b104", "confidence": 0.88,
     "origin": "hook", "phase": "closed", "tenant_id": "T-local", "supersedes_seed": None, "ts_ms": NOW - 3 * DAY},
    {"seed_id": "p-03", "work_ref": {"kind": "file", "id": "clients/acme/cutover-checklist.md"},
     "domain_ref": "dref-cf189b6a3de723b0", "charter_seed_id": "C-77b104", "confidence": 0.79,
     "origin": "hook", "phase": "open", "tenant_id": "T-local", "supersedes_seed": None, "ts_ms": NOW - 5 * DAY},
    {"seed_id": "p-04", "work_ref": {"kind": "file", "id": "research/competitor-pricing-2026.md"},
     "domain_ref": "dref-8bd457269a39ef7c", "charter_seed_id": "C-2c4e90", "confidence": 0.74,
     "origin": "hook", "phase": "open", "tenant_id": "T-local", "supersedes_seed": None, "ts_ms": NOW - 1 * DAY},
    {"seed_id": "p-05", "work_ref": {"kind": "file", "id": "research/landscape-scan.md"},
     "domain_ref": "dref-8bd457269a39ef7c", "charter_seed_id": "C-2c4e90", "confidence": 0.69,
     "origin": "hook", "phase": "closed", "tenant_id": "T-local", "supersedes_seed": None, "ts_ms": NOW - 4 * DAY},
    {"seed_id": "p-06", "work_ref": {"kind": "file", "id": "research/weekly-brief-31.md"},
     "domain_ref": "dref-9ce568370ab4f08d", "charter_seed_id": "C-9d13a7", "confidence": 0.72,
     "origin": "hook", "phase": "open", "tenant_id": "T-local", "supersedes_seed": None, "ts_ms": NOW - 0 * DAY},
    {"seed_id": "p-07", "work_ref": {"kind": "file", "id": "research/weekly-brief-30.md"},
     "domain_ref": "dref-9ce568370ab4f08d", "charter_seed_id": "C-9d13a7", "confidence": 0.70,
     "origin": "hook", "phase": "closed", "tenant_id": "T-local", "supersedes_seed": None, "ts_ms": NOW - 7 * DAY},
    {"seed_id": "p-08", "work_ref": {"kind": "file", "id": "engine/placement_engine.py"},
     "domain_ref": "dref-adf679481bc5019e", "charter_seed_id": "C-5a7b22", "confidence": 0.91,
     "origin": "hook", "phase": "open", "tenant_id": "T-local", "supersedes_seed": None, "ts_ms": NOW - 2 * DAY},
    {"seed_id": "p-09", "work_ref": {"kind": "file", "id": "engine/classify_tests.py"},
     "domain_ref": "dref-adf679481bc5019e", "charter_seed_id": "C-5a7b22", "confidence": 0.85,
     "origin": "hook", "phase": "closed", "tenant_id": "T-local", "supersedes_seed": None, "ts_ms": NOW - 6 * DAY},
    {"seed_id": "p-10", "work_ref": {"kind": "file", "id": "engine/lock_fix.py"},
     "domain_ref": "dref-adf679481bc5019e", "charter_seed_id": "C-5a7b22", "confidence": 0.83,
     "origin": "operator", "phase": "closed", "tenant_id": "T-local", "supersedes_seed": None, "ts_ms": NOW - 12 * DAY},
    {"seed_id": "p-11", "work_ref": {"kind": "file", "id": "eval/harness-v2-spec.md"},
     "domain_ref": "dref-be078a592cd612af", "charter_seed_id": "C-b41f08", "confidence": 0.77,
     "origin": "hook", "phase": "open", "tenant_id": "T-local", "supersedes_seed": None, "ts_ms": NOW - 44 * DAY},
    {"seed_id": "p-12", "work_ref": {"kind": "file", "id": "eval/rubric-draft.md"},
     "domain_ref": "dref-be078a592cd612af", "charter_seed_id": "C-b41f08", "confidence": 0.66,
     "origin": "hook", "phase": "open", "tenant_id": "T-local", "supersedes_seed": None, "ts_ms": NOW - 51 * DAY},
    {"seed_id": "p-13", "work_ref": {"kind": "file", "id": "infra/runbook-oncall.md"},
     "domain_ref": "dref-e13abd8c50f945d2", "charter_seed_id": "C-6e0d35", "confidence": 0.80,
     "origin": "hook", "phase": "open", "tenant_id": "T-local", "supersedes_seed": None, "ts_ms": NOW - 3 * DAY},
    {"seed_id": "p-14", "work_ref": {"kind": "file", "id": "infra/terraform/main.tf"},
     "domain_ref": "dref-e13abd8c50f945d2", "charter_seed_id": "C-6e0d35", "confidence": 0.76,
     "origin": "hook", "phase": "closed", "tenant_id": "T-local", "supersedes_seed": None, "ts_ms": NOW - 9 * DAY},
    {"seed_id": "p-15", "work_ref": {"kind": "file", "id": "infra/backup-restore.md"},
     "domain_ref": "dref-e13abd8c50f945d2", "charter_seed_id": "C-1b2c44", "confidence": 0.68,
     "origin": "hook", "phase": "closed", "tenant_id": "T-local", "supersedes_seed": None, "ts_ms": NOW - 140 * DAY},
    {"seed_id": "p-16", "work_ref": {"kind": "file", "id": "platform/dr-drill-2025.md"},
     "domain_ref": "dref-5ea124f3706dbc49", "charter_seed_id": "C-0a41cd", "confidence": 0.71,
     "origin": "hook", "phase": "closed", "tenant_id": "T-local", "supersedes_seed": None, "ts_ms": NOW - 214 * DAY},

    # DEFECT 4 -- below-floor rows, held at root (Research/Engine hold no charter).
    {"seed_id": "p-17", "work_ref": {"kind": "utterance", "id": "w-1785455000000"},
     "domain_ref": "dref-1a0f4c2b9e7d6053", "charter_seed_id": "C-04ee71", "confidence": 0.38,
     "origin": "hook", "phase": "open", "tenant_id": "T-local", "supersedes_seed": None, "ts_ms": NOW - 0 * DAY},
    {"seed_id": "p-18", "work_ref": {"kind": "utterance", "id": "w-1785368600000"},
     "domain_ref": "dref-1a0f4c2b9e7d6053", "charter_seed_id": "C-04ee71", "confidence": 0.42,
     "origin": "hook", "phase": "open", "tenant_id": "T-local", "supersedes_seed": None, "ts_ms": NOW - 1 * DAY},
    {"seed_id": "p-19", "work_ref": {"kind": "file", "id": "notes/pricing-vs-packaging.md"},
     "domain_ref": "dref-1a0f4c2b9e7d6053", "charter_seed_id": "C-04ee71", "confidence": 0.31,
     "origin": "hook", "phase": "open", "tenant_id": "T-local", "supersedes_seed": None, "ts_ms": NOW - 6 * DAY},

    {"seed_id": "p-20", "work_ref": {"kind": "file", "id": "clients/acme/support-escalation.md"},
     "domain_ref": "dref-4d9013e26f5cab38", "charter_seed_id": "C-3f9a11", "confidence": 0.58,
     "origin": "hook", "phase": "open", "tenant_id": "T-local", "supersedes_seed": None, "ts_ms": NOW - 8 * DAY},
    {"seed_id": "p-21", "work_ref": {"kind": "file", "id": "reports/q2-acme-summary.md"},
     "domain_ref": "dref-4d9013e26f5cab38", "charter_seed_id": "C-3f9a11", "confidence": 0.77,
     "origin": "hook", "phase": "closed", "tenant_id": "T-local", "supersedes_seed": None, "ts_ms": NOW - 95 * DAY},

    # superseding pair written by retire(): p-22 on the tombstone, p-23 repointing post-close.
    {"seed_id": "p-22", "work_ref": {"kind": "file", "id": "ops/oncall-rota-2026.md"},
     "domain_ref": "dref-6fb235047817cd5a", "charter_seed_id": "C-8812f0", "confidence": 0.64,
     "origin": "hook", "phase": "closed", "tenant_id": "T-local", "supersedes_seed": None, "ts_ms": NOW - 120 * DAY},
    {"seed_id": "p-23", "work_ref": {"kind": "file", "id": "ops/oncall-rota-2026.md"},
     "domain_ref": "dref-5ea124f3706dbc49", "charter_seed_id": "C-6e0d35", "confidence": 0.64,
     "origin": "operator", "phase": "post-close", "tenant_id": "T-local", "supersedes_seed": "p-22",
     "ts_ms": NOW - 48 * DAY},

    # second-tenant placement, commingled.
    {"seed_id": "p-24", "work_ref": {"kind": "file", "id": "clients/acme/qbr-deck.md"},
     "domain_ref": "dref-f24bce9d610a56e3", "charter_seed_id": "C-e5f7b9", "confidence": 0.73,
     "origin": "hook", "phase": "open", "tenant_id": "T-acme", "supersedes_seed": None, "ts_ms": NOW - 5 * DAY},
]


def _write_json(path, obj):
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(obj, fh, sort_keys=True, indent=2)


def _append_jsonl(path, row):
    line = json.dumps(row, separators=(",", ":"), ensure_ascii=False) + "\n"
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(line)


def seed(target_dir):
    domains_dir = os.path.join(target_dir, "domains")
    charters_dir = os.path.join(target_dir, "charters")
    placements_dir = os.path.join(target_dir, "placements")
    plans_dir = os.path.join(target_dir, "plans")
    for d in (domains_dir, charters_dir, placements_dir, plans_dir):
        os.makedirs(d, exist_ok=True)

    for d in DOMAINS:
        row = dict(d)
        desc = _DESCRIPTIONS.get(d["ref"])
        if desc is not None:
            row["description"] = desc
        _write_json(os.path.join(domains_dir, d["ref"] + ".json"), row)

    domain_index_rows = [
        {"event": "domain_restructured", "op": "rename", "ref": "dref-5ea124f3706dbc49",
         "target": None, "placements_repointed": 0, "ts_ms": NOW - 260 * DAY},
        {"event": "domain_minted", "ref": "dref-be078a592cd612af", "name": "Evaluation",
         "parent_ref": "dref-3c8f02d15e4b9a27", "origin": "system-minted",
         "tenant_id": "T-local", "ts_ms": NOW - 60 * DAY},
        {"event": "domain_minted", "ref": "dref-f24bce9d610a56e3", "name": "Client Success",
         "parent_ref": None, "origin": "operator", "tenant_id": "T-acme", "ts_ms": NOW - 40 * DAY},
        {"event": "domain_restructured", "reorg_id": "plan-2026-06-14-dissolve-agent-ops",
         "op": "retire", "ref": "dref-6fb235047817cd5a", "target": "dref-5ea124f3706dbc49",
         "placements_repointed": 1, "retire_reason_code": "merged",
         "before": {"name": "Agent Ops", "description": "Ran the agent fleet.",
                    "parent_ref": "dref-1a0f4c2b9e7d6053", "status": "active",
                    "successor_refs": [], "d_path": "D6"},
         "after": {"name": "Agent Ops",
                    "description": "Ran the agent fleet. Dissolved into Platform and Engine.",
                    "parent_ref": "dref-1a0f4c2b9e7d6053", "status": "retired",
                    "successor_refs": ["dref-5ea124f3706dbc49", "dref-3c8f02d15e4b9a27"],
                    "d_path": "D6"},
         "disposition": {"charters": [{"id": "C-8812f0", "to": None}], "children": []},
         "ts_ms": NOW - 48 * DAY},
        {"event": "domain_minted", "ref": "dref-7ac346158928de6b", "name": "Agent Ops",
         "parent_ref": "dref-1a0f4c2b9e7d6053", "origin": "operator",
         "tenant_id": "T-local", "ts_ms": NOW - 20 * DAY},
        {"event": "domain_minted", "ref": "dref-d029ac7b4ef834c1", "name": "Support QA",
         "parent_ref": "dref-4d9013e26f5cab38", "origin": "system-minted",
         "tenant_id": "T-local", "ts_ms": NOW - 11 * DAY},
    ]
    index_path = os.path.join(domains_dir, "INDEX.jsonl")
    if os.path.exists(index_path):
        os.remove(index_path)
    for row in domain_index_rows:
        _append_jsonl(index_path, row)

    seed_to_real = {}
    bodies = {}
    for c in _SEED_CHARTERS:
        body = {
            "title": c["title"][:60],
            "domain_ref": c["domain_ref"],
            "purpose": c["purpose"],
            "scope_in": c["scope_in"],
            "scope_out": c["scope_out"],
            "obligations": [],
            "obligations_empty_reason":
                "auto-minted stub: obligations are commitments and are never "
                "system-generated (ADR-028 Decision 5). Fill via B20 or by hand.",
            "invariants": [], "success_metrics": [], "constraints": [],
            "acl": [{"tenant_id": "T-acme" if c["domain_ref"] == "dref-f24bce9d610a56e3" else "T-local",
                     "access": "rw"}],
            "cutover_contract": None, "authority": {}, "termination": {},
            "tenant_id": "T-acme" if c["domain_ref"] == "dref-f24bce9d610a56e3" else "T-local",
            "kind": c["kind"],
            "supersedes": None,
            "schema": CHARTER_SCHEMA,
        }
        cid = charter_id_of(body)
        body["id"] = cid
        seed_to_real[c["seed_id"]] = cid
        bodies[c["seed_id"]] = body

    for c in _SEED_CHARTERS:
        body = bodies[c["seed_id"]]
        if c.get("supersedes"):
            real_super = seed_to_real.get(c["supersedes"])
            if body["supersedes"] != real_super:
                body["supersedes"] = real_super
                new_body = dict(body)
                del new_body["id"]
                cid = charter_id_of(new_body)
                new_body["id"] = cid
                seed_to_real[c["seed_id"]] = cid
                bodies[c["seed_id"]] = new_body

    for c in _SEED_CHARTERS:
        body = bodies[c["seed_id"]]
        cid = body["id"]
        _write_json(os.path.join(charters_dir, cid + ".json"), body)

        sidecar = {"status": c["status"], "artifacts": list(c.get("artifacts") or []),
                   "linked_domain_refs": list(c.get("linked_domain_refs") or []),
                   "goals": [], "metrics": [], "milestones": [], "todos": [],
                   "ts_ms": c["ts_ms"]}
        if c.get("handoff"):
            handoff = dict(c["handoff"])
            if handoff.get("from_charter_id") in seed_to_real:
                handoff["from_charter_id"] = seed_to_real[handoff["from_charter_id"]]
            sidecar["handoff"] = handoff
        if "attested_ms" in c:
            sidecar["attested_ms"] = c["attested_ms"]
        _write_json(os.path.join(charters_dir, cid + ".page.json"), sidecar)

    charter_index_rows = [
        {"event": "charter_minted", "id": bodies[c["seed_id"]]["id"], "domain_ref": c["domain_ref"],
         "tenant_id": bodies[c["seed_id"]]["tenant_id"], "ts_ms": c["ts_ms"]}
        for c in _SEED_CHARTERS
    ]
    cindex_path = os.path.join(charters_dir, "INDEX.jsonl")
    if os.path.exists(cindex_path):
        os.remove(cindex_path)
    for row in charter_index_rows:
        _append_jsonl(cindex_path, row)

    seq = 0
    pid_by_seed = {}
    bodies_p = {}
    for p in _SEED_PLACEMENTS:
        seq += 1
        charter_id = seed_to_real[p["charter_seed_id"]]
        body = {
            "work_ref": p["work_ref"],
            "domain_ref": p["domain_ref"],
            "charter_id": charter_id,
            "origin": p["origin"],
            "confidence": round(float(p["confidence"]), 4),
            "created": {"domains": [], "charters": []},
            "supersedes": None,
            "phase": p["phase"],
            "tenant_id": p["tenant_id"],
            "ts_ms": p["ts_ms"],
            "seq": seq,
            "pid": 40000 + seq,
        }
        pid = "PL-" + _sha(body)[:16]
        body["id"] = pid
        pid_by_seed[p["seed_id"]] = pid
        bodies_p[p["seed_id"]] = body

    for p in _SEED_PLACEMENTS:
        if p.get("supersedes_seed"):
            body = bodies_p[p["seed_id"]]
            real_super = pid_by_seed.get(p["supersedes_seed"])
            if body["supersedes"] != real_super:
                body["supersedes"] = real_super
                new_body = dict(body)
                del new_body["id"]
                pid = "PL-" + _sha(new_body)[:16]
                new_body["id"] = pid
                pid_by_seed[p["seed_id"]] = pid
                bodies_p[p["seed_id"]] = new_body

    current_path = os.path.join(placements_dir, "CURRENT.jsonl")
    if os.path.exists(current_path):
        os.remove(current_path)
    for p in _SEED_PLACEMENTS:
        body = bodies_p[p["seed_id"]]
        pid = body["id"]
        _write_json(os.path.join(placements_dir, pid + ".json"), body)
        _append_jsonl(current_path, {
            "work_ref_id": body["work_ref"].get("id"),
            "work_ref_kind": body["work_ref"].get("kind"),
            "tenant_id": body["tenant_id"],
            "placement_id": pid,
            "domain_ref": body["domain_ref"],
            "ts_ms": body["ts_ms"],
        })

    return {
        "domains": len(DOMAINS),
        "charters": len(_SEED_CHARTERS),
        "placements": len(_SEED_PLACEMENTS),
        "seed_to_real_charter_id": seed_to_real,
        "seed_to_real_placement_id": pid_by_seed,
    }


def main(argv):
    if len(argv) < 2:
        sys.stderr.write("usage: fixture_seed.py <target_dir>\n")
        return 2
    target = os.path.abspath(argv[1])
    os.makedirs(target, exist_ok=True)
    result = seed(target)
    print(json.dumps({"target": target, **{k: v for k, v in result.items()
                                            if not k.startswith("seed_to_real")}}, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
