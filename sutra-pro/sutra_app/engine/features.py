"""Nothing of J2 is lost: engine design section 8 as data (ENG-02).

`FEATURES` lists the eight steps of J2's loop (J2.a .. J2.h), the fifteen chips of the diagram and one row of extras. For each:

    files     paths relative to `sutra_app/engine/`; a name ending in `/` is a folder (package data)
    symbols   (file, name) pairs: a def, class or constant that file defines (J2's names; its line numbers move)
    flags     the `EngineSettings` fields that switch the feature
    later     (file, name) pairs that live in files of LATER work packages (the views, the FastAPI adapter), so a check run
              before those merge leaves them out

`tests/engine/test_engine_features.py` (WP E1) checks that every file and symbol exists once the vendored J2 is there.
"""
from dataclasses import dataclass

__all__ = ["Feature", "FEATURES", "by_id", "STEP_IDS"]


@dataclass(frozen=True)
class Feature:
    id: str
    kind: str                                   # "step" | "chip" | "extra"
    chip: str                                   # the row's label in the design
    files: tuple[str, ...]
    symbols: tuple[tuple[str, str], ...] = ()
    flags: tuple[str, ...] = ()
    later: tuple[tuple[str, str], ...] = ()


def _s(file: str, *names: str) -> tuple[tuple[str, str], ...]:
    return tuple((file, name) for name in names)


STEP_IDS = ("J2.a", "J2.b", "J2.c", "J2.d", "J2.e", "J2.f", "J2.g", "J2.h")

FEATURES: tuple[Feature, ...] = (
    Feature("J2.a", "step", "J2.a Identity: enough to start?", ("j2.py", "agents/j2/identity.md"),
            _s("j2.py", "_identity_intake", "CHARTER_FMT")),
    Feature("J2.b", "step", "J2.b Adaptation proposes", ("j2.py", "agents/j2/adaptation.md"),
            _s("j2.py", "_turn_adaptation", "_realization_plan"), ("realization",)),
    Feature("J2.c", "step", "J2.c Priority prices", ("j2.py", "agents/j2/priority.md", "agents/j2/rates.json"),
            _s("j2.py", "_turn_priority"), ("rates",)),
    Feature("J2.d", "step", "J2.d Identity resolves conflicts", ("j2.py",),
            _s("j2.py", "_turn_dispute", "_identity_resolve", "_settle")),
    Feature("J2.e", "step", "J2.e Validator registers", ("j2.py",), _s("j2.py", "_agree", "_register", "atom_missing")),
    Feature("J2.f", "step", "J2.f Coordination schedules, builders run", ("j2.py", "agents/j2/coordination.md"),
            _s("j2.py", "_turn_coordination", "_priority_envelope", "_turn_workflow_agent")),
    Feature("J2.g", "step", "J2.g Audit checks", ("j2.py", "agents/j2/audit.md"),
            _s("j2.py", "_turn_audit", "_audit_site", "_audit_doc")),
    Feature("J2.h", "step", "J2.h Identity: workable?", ("j2.py",),
            _s("j2.py", "_identity_audit", "workable", "_identity_limit")),

    Feature("builders", "chip", "Workflow builder agents", ("j2.py", "agents/j2/builder.md"),
            _s("j2.py", "_turn_workflow_agent", "_run_artifact", "_route_template", "_builder_for"),
            ("template_library",)),
    Feature("validator", "chip", "Code validator", ("j2.py", "j2_rules.py", "j2_artifact_models.py"),
            _s("j2.py", "check_problems", "expected_problems", "run_check") + _s("j2_rules.py", "run_rules"),
            ("artifact_schema",)),
    Feature("judge", "chip", "Confidence judge",
            ("j2_realization.py", "j2_change.py", "agents/j2/confidence-judge.md", "agents/j2/stages.json"),
            _s("j2_realization.py", "judge_system", "plan_goal", "Session"), ("realization", "change")),
    Feature("budget", "chip", "Budget and rate card", ("j2.py", "agents/j2/rates.json"),
            _s("j2.py", "BUDGET", "BUDGET_CAP", "load_rates", "price", "granted"), ("rates", "budget")),
    Feature("memory", "chip", "Memory", ("j2.py",),
            _s("j2.py", "load_lessons", "save_playbook", "_learn", "_save_playbook"), ("memory",)),
    Feature("board", "chip", "Message board", ("j2_board.py", "j2.py"), _s("j2.py", "_ask_board"), ("board",)),
    Feature("documents", "chip", "Document chain",
            ("j2.py", "conditions/prd.json", "conditions/hld.json", "conditions/lld.json"),
            _s("j2.py", "_plan_stages", "_begin_stage", "_next_stage")),
    Feature("site", "chip", "Site build and checks", ("j2.py", "j2_check.py", "conditions/website.json"),
            _s("j2.py", "assemble", "PageScan"), ("chrome", "tap_min")),
    Feature("sends", "chip", "Sends and deeds", ("j2_send.py", "j2.py"), _s("j2.py", "_deed_stage", "_milestone"),
            ("send_mode", "send_cap", "milestone_emails")),
    Feature("views", "chip", "Run views", ("j2_map.py", "j2_schema.py", "j2.py"),
            _s("j2_map.py", "build") + _s("j2_schema.py", "run_views") + _s("j2.py", "lanes", "snapshot", "saved_snapshot")),
    Feature("library", "chip", "Template library", ("j2_template_lib.py", "templates/", "seed/library/"),
            _s("j2_template_lib.py", "route", "store", "library_view"), ("template_library",)),
    Feature("change", "chip", "Charter change", ("j2_change.py", "j2.py"),
            _s("j2.py", "_turn_change", "_change_relay"), ("change",)),
    Feature("schemas", "chip", "Artifact schemas",
            ("j2_artifact_models.py", "j2_rules.py", "j2_artifacts.py", "artifacts/types.json"), (), ("artifact_schema",)),
    Feature("story", "chip", "Story and agent views", ("j2_story.py", "j2_agent.py"),
            _s("j2_story.py", "build") + _s("j2_agent.py", "view")),
    Feature("plan", "chip", "Plan and priorities", ("j2_map.py", "j2.py"),
            _s("j2_map.py", "plan_view") + _s("j2.py", "_turn_priority")),

    Feature("extras", "extra",
            "Also: run report and reviewer, owner override, test switches, docx export, redaction, saved runs", ("j2.py",),
            _s("j2.py", "_make_report", "_review", "_override", "export_docx", "list_runs"),
            ("force_audit_fail", "force_audit_note", "force_question"), _s("api/reply.py", "redact")),
)


def by_id() -> dict[str, Feature]:
    return {feature.id: feature for feature in FEATURES}
