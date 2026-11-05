"""Follow-up after a finished document chain (work package GAP-E1B, gap G15, engine design 4.8 and phase E1-b).

The mock design-docs scenario (PRD, HLD, LLD, then the website) and a documents-only chain run to Done in J2, then a new
`J2Run` rehydrates the folder and takes a change request; the host does the same from a task with `seed_from`. The J2 run
that stayed alive is the oracle: the rehydrated run must hold the chain state the way J2 held it after Done. Helpers come
from the rehydrate and host test files (this folder has no __init__.py, so pytest puts it on sys.path)."""
import itertools
import json
import os
import shutil
from pathlib import Path

import pytest

from test_engine_host import QUIET, Running, chat, events, fresh_j2 as host_fresh_j2, systems
from test_engine_rehydrate import HOST_SENTINELS, edit_json, refused, say, tree_sha

CHANGE = "make the HLD mention a CDN"
BREW = ("A one-page website for Brew Lab, a small specialty coffee shop in Indiranagar, Bengaluru. Visitors should see the "
        "menu with prices, the opening hours, and where to find us, and be able to pre-order a coffee for pickup. It should "
        "feel warm and modern and work well on a phone. Include a section about our beans and the farms they come from, "
        "and a simple loyalty-card explainer (buy 9, get the 10th free).")
FACTS = (" Users: coffee lovers and office staff. Problem: people can't see the menu or order ahead. Must-have features: "
         "see the menu with prices, pre-order a coffee, find the shop, read the opening hours. Constraints: one page only. "
         "Success: 30 pre-orders per week.")
WITH_SITE = BREW + " Write the design docs first." + FACTS           # the recorded design_docs scenario: PRD, HLD, LLD, website
DOCS_ONLY = ("Write the PRD, the HLD and the LLD for Brew Lab, a small specialty coffee shop's one-page ordering page." + FACTS)
CHAIN_SETTINGS = {**QUIET, "J2_FIXES": "0", "J2_BUDGET": "900"}
RUN_A, RUN_B = "j2-20261104-100001-7f3a", "j2-20261104-100002-7f3a"


@pytest.fixture(scope="module")
def j2(tmp_path_factory):
    """The vendored J2 in mock mode. J2 reads J2_BUDGET when it is imported, so the chain's budget is set on the module."""
    with host_fresh_j2(tmp_path_factory.mktemp("j2-chain-env")) as mod:
        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(mod, "BUDGET", 900)
            mp.setattr(mod, "BUDGET_CAP", 1800)
            yield mod


@pytest.fixture(autouse=True)
def mock_mode(llm_reset):
    llm_reset.configure(mock=True)
    return llm_reset


def make_finished(j2, base: Path, name: str, brief: str):
    """A J2Run in `<base>/runs/<name>` that has run `brief` to Done (the object stays alive as the oracle)."""
    folder = base / "runs" / name
    folder.mkdir(parents=True)
    run = j2.J2Run(run_dir=folder)
    say(run, brief, timeout=120)
    assert run.outcome.startswith("Done"), run.outcome
    return run


@pytest.fixture(scope="module")
def site_chain(j2, tmp_path_factory):
    """A finished PRD, HLD, LLD and website chain (J2's own object, still alive)."""
    return make_finished(j2, tmp_path_factory.mktemp("chain-site"), RUN_A, WITH_SITE)


@pytest.fixture(scope="module")
def docs_chain(j2, tmp_path_factory):
    """A finished PRD, HLD, LLD chain with no website: the last stage is a document."""
    return make_finished(j2, tmp_path_factory.mktemp("chain-docs"), RUN_B, DOCS_ONLY)


@pytest.fixture
def new_run(j2, tmp_path):
    """A fresh J2Run in a new run folder that holds the files the host makes (task.json and friends)."""
    counter = itertools.count(1)

    def make():
        folder = tmp_path / "runs" / f"j2-20261104-2000{next(counter):02d}-7f3a"
        folder.mkdir(parents=True)
        for name, text in HOST_SENTINELS.items():
            (folder / name).write_text(text)
        return j2.J2Run(run_dir=folder)
    return make


def copy_of(run, tmp_path) -> Path:
    target = tmp_path / "source" / os.path.basename(run.dir)
    shutil.copytree(run.dir, target)
    return target


def plain(value):
    """What the same value is after a trip through a JSON file."""
    return json.loads(json.dumps(value))


CHAIN_ATTRS = ("docset", "stages", "stage_i", "docs", "chain", "stage_archive", "site_tag", "output", "doc", "blueprint",
               "lld_revisions", "goal", "sections", "sites", "audits")


# ---- the state J2 holds after Done ---------------------------------------------------------------------------------------
@pytest.mark.parametrize("which", ["site_chain", "docs_chain"])
def test_rehydrate_restores_the_chain_as_j2_holds_it_after_done(which, request, j2, new_run):
    old = request.getfixturevalue(which)
    follow = new_run()
    info = follow.rehydrate(old.dir)
    for name in CHAIN_ATTRS:
        assert plain(getattr(follow, name)) == plain(getattr(old, name)), name
    assert follow.stage_i == len(follow.stages) - 1 and follow.stage_kind == old.stage_kind
    assert follow.out is old.out and follow.WF_FMT == old.WF_FMT and follow.GRANT_FMT == old.GRANT_FMT
    assert follow.ATOM_RULES == old.ATOM_RULES
    assert [w["id"] for w in follow.past_workflows] == [w["id"] for w in old.past_workflows] != []
    assert [w["id"] for w in follow.workflows] == [w["id"] for w in old.workflows] != []
    assert plain(follow.past_workflows + follow.workflows) == plain(old.past_workflows + old.workflows)
    assert follow.stage_calls0 == old.stage_calls0 and follow.done and follow.status == "waiting"
    assert info["workflows"] == len(old.past_workflows) + len(old.workflows) and info["sites"] == len(old.sites)
    assert info["messages"] == len(old.chat)


def test_the_website_chain_keeps_the_lld_as_its_blueprint_and_the_document_chain_ends_on_a_document(site_chain, docs_chain,
                                                                                                    new_run):
    site, docs = new_run(), new_run()
    site.rehydrate(site_chain.dir)
    docs.rehydrate(docs_chain.dir)
    assert site.stages == ["prd", "hld", "lld", "website"] and site.doc is False and site.blueprint and site.site_tag == "website-"
    assert '"lld_sections"' in site.WF_FMT and '"lld_sections"' in site.GRANT_FMT
    assert docs.stages == ["prd", "hld", "lld"] and docs.doc is True and docs.output == "lld" and docs.blueprint is None
    assert docs.site_tag == "lld-" and docs.sites and all(t.startswith("# ") for t in docs.sites)
    assert len(docs.sites) == len(list((Path(docs_chain.dir) / "site").glob("lld-v*.md")))


def test_the_document_files_of_the_chain_are_copied_and_the_hosts_own_are_not(site_chain, new_run):
    follow = new_run()
    follow.rehydrate(site_chain.dir)
    new, old = tree_sha(Path(follow.dir)), tree_sha(Path(site_chain.dir))
    for name in ("prd.md", "prd.docx", "hld.md", "hld.docx", "lld.md", "lld.docx", "documents.json", "chain.json", "stage-prd.json",
                 "stage-website.json", "site/prd-v1.md", "site/hld-v1.md", "site/lld-v1.md", "site/v1.html"):
        assert new[name] == old[name], f"{name} is copied byte for byte"
    for name, text in HOST_SENTINELS.items():
        assert (Path(follow.dir) / name).read_text() == text, f"{name} belongs to the new run"
    assert "report.md" not in new


def test_rehydrate_sets_exactly_the_listed_attributes_for_a_chain(site_chain, new_run):
    from sutra_app.engine import rehydrate as R
    follow = new_run()
    before = dict(vars(follow))
    follow.rehydrate(site_chain.dir)
    after = vars(follow)
    changed = {k for k in after if after[k] is not before.get(k) and after[k] != before.get(k)}
    assert changed <= set(R.RESTORED) | set(R.RESTORED_CHAIN)
    assert {"docset", "stages", "stage_i", "docs", "chain", "stage_archive", "past_workflows", "site_tag", "blueprint"} <= changed
    assert set(after) == set(before)


# ---- the change request continues the chain -------------------------------------------------------------------------------
def test_a_change_after_a_finished_chain_adds_a_site_version_and_keeps_the_documents(site_chain, new_run):
    old_dir = Path(site_chain.dir)
    before = tree_sha(old_dir)
    follow = new_run()
    follow.rehydrate(old_dir)
    n_wf, n_sites, n_archive, n_chat = len(follow.workflows), len(follow.sites), len(follow.stage_archive), len(follow.chat)
    say(follow, CHANGE, timeout=120)
    assert follow.outcome.startswith("Done"), follow.outcome
    assert len(follow.workflows) == n_wf + 1 and len(follow.sites) == n_sites + 1, "a new version of the output"
    assert follow.stages == ["prd", "hld", "lld", "website"] and follow.docset == ["prd", "hld", "lld"], "not a new chain"
    texts = [m["text"] for m in follow.chat[n_chat:]]
    assert texts[0] == CHANGE and not any(t.startswith("Documents asked for") for t in texts)
    assert follow.chat[n_chat]["change"] is True
    assert len(follow.stage_archive) == n_archive + 1, "the last stage is archived again, as J2 does"
    new = tree_sha(Path(follow.dir))
    assert f"site/v{n_sites + 1}.html" in new and f"site/v{n_sites + 1}.html" not in before
    for name in before:                                                  # every file of the source is in the new folder
        if name.startswith(("site/v", "site/prd-", "site/hld-", "site/lld-")) or name in (
                "prd.md", "hld.md", "lld.md", "prd.docx", "hld.docx", "lld.docx", "stage-prd.json", "stage-hld.json", "stage-lld.json"):
            assert new[name] == before[name], f"{name} is unchanged"
    documents = json.loads((Path(follow.dir) / "documents.json").read_text())
    assert list(documents) == ["prd", "hld", "lld"]
    summary = json.loads((Path(follow.dir) / "summary.json").read_text())
    assert summary["status"] == "done" and summary["change_requests"] == [CHANGE]
    assert summary["design_documents"]["stages"] == ["prd", "hld", "lld", "website"]
    assert tree_sha(old_dir) == before, "the old folder is never written again"
    workflows = json.loads((Path(follow.dir) / "workflows.json").read_text())
    assert len(workflows) == len(follow.past_workflows) + len(follow.workflows) == len(site_chain.past_workflows) + n_wf + 1


def test_a_change_after_a_documents_only_chain_runs_j2s_document_change_flow(docs_chain, new_run):
    """J2's mock Adaptation proposes nothing for a change to a document (a real model writes the new version), so the run
    goes straight to Audit and ends Done again, as the live J2 run does; the chain and every version stay as they were."""
    old_dir = Path(docs_chain.dir)
    follow = new_run()
    follow.rehydrate(old_dir)
    before_files = tree_sha(old_dir)
    n_chat = len(follow.chat)
    say(follow, CHANGE, timeout=120)
    texts = [m["text"] for m in follow.chat[n_chat:]]
    assert follow.outcome.startswith("Done: the design documents are workable"), follow.outcome
    assert texts[0] == CHANGE and any("Adaptation proposed no workflows" in t for t in texts)
    assert any("The LLD is workable" in t for t in texts), "Audit re-checked the last document (LLD v5)"
    site = Path(follow.dir) / "site"
    for name in before_files:
        if name.startswith("site/") or name in ("prd.md", "hld.md", "lld.md"):
            assert tree_sha(Path(follow.dir))[name] == before_files[name], f"{name} is unchanged"
    assert sorted(p.name for p in site.glob("*-v*.md")) == sorted(p.name for p in (old_dir / "site").glob("*-v*.md"))
    assert (Path(follow.dir) / "lld.docx").is_file()
    assert follow.stages == ["prd", "hld", "lld"] and set(follow.docs) == {"prd", "hld", "lld"}
    old_docs = json.loads((old_dir / "documents.json").read_text())
    assert follow.docs["prd"] == old_docs["prd"] and follow.docs["hld"] == old_docs["hld"]
    assert {k: v for k, v in follow.docs["lld"].items() if k != "calls"} == {k: v for k, v in old_docs["lld"].items() if k != "calls"}
    assert follow.docs["lld"]["calls"]["from"] == old_docs["lld"]["calls"]["from"], "stage_calls0 was restored"


# ---- the host: the Continuing line and the seed -----------------------------------------------------------------------------
def test_the_host_continues_a_finished_chain_and_says_so(j2, make_run_dir, clean_env, tmp_path):
    saved = dict(os.environ)
    clean_env.setenv("SUTRA_HEARTBEAT_S", "0.2")
    clean_env.setenv("SUTRA_NODES", "off")
    clean_env.setenv("SUTRA_ENV_FILE", str(tmp_path / "none.env"))
    try:
        host_follow_up(make_run_dir)
    finally:
        os.environ.clear()
        os.environ.update(saved)


def host_follow_up(make_run_dir):
    old = make_run_dir(run_id=RUN_A, user_text=WITH_SITE, settings=CHAIN_SETTINGS)
    assert Running(old, "--mock").wait(120) == 0
    assert events(old)[-1]["status"] in ("done", "done_with_open_items")
    before = tree_sha(old)
    new = make_run_dir(run_id="j2-20261104-110000-aaaa", user_text=CHANGE, settings=CHAIN_SETTINGS, seed_from=old.name)
    assert Running(new, "--mock").wait(120) == 0
    rows = events(new)
    assert rows[0]["t"] == "run.started" and rows[0]["seed"] == "rehydrated" and rows[-1]["status"] in ("done", "done_with_open_items")
    line = (f"Continuing from run {old.name}: the team keeps its charter, workflows, findings and site and treats your "
            "message as a change request.")
    assert chat(new)[len(chat(old))]["text"] == line and line in systems(new)
    assert chat(new)[len(chat(old)) + 1]["text"] == CHANGE
    assert not (new / "upstream").exists(), "continued, not started fresh"
    assert (new / "hld.md").read_bytes() == (old / "hld.md").read_bytes() and (new / "site" / "hld-v1.md").is_file()
    assert len(list((new / "site").glob("v*.html"))) == len(list((old / "site").glob("v*.html"))) + 1
    assert tree_sha(old) == before


# ---- what is still refused --------------------------------------------------------------------------------------------------
@pytest.fixture
def source(site_chain, tmp_path):
    return copy_of(site_chain, tmp_path)


@pytest.mark.parametrize("status,reason", [("stopped", "the earlier run was stopped before it finished"),
                                           ("crashed", "the earlier run crashed")])
def test_an_unfinished_chain_is_still_refused(source, new_run, status, reason):
    edit_json(source / "summary.json", status=status)
    assert refused(new_run(), source) == reason


def test_a_chain_without_a_summary_is_still_refused(source, new_run):
    (source / "summary.json").unlink()
    assert refused(new_run(), source) == "the earlier run left no summary, so it never finished"


def test_a_chain_whose_summary_does_not_describe_it_is_refused(source, new_run):
    summary = json.loads((source / "summary.json").read_text())
    del summary["design_documents"]
    (source / "summary.json").write_text(json.dumps(summary))
    assert refused(new_run(), source) == "the earlier run's document chain cannot be read (summary.json has no design_documents)"


def test_a_chain_with_an_unknown_stage_is_refused(source, new_run):
    summary = json.loads((source / "summary.json").read_text())
    summary["design_documents"]["requested"] = ["prd", "poem"]
    (source / "summary.json").write_text(json.dumps(summary))
    assert refused(new_run(), source) == "the earlier run's document chain cannot be read (summary.json names unknown stages)"


def test_a_requested_document_that_is_not_a_stage_is_refused(source, new_run):
    summary = json.loads((source / "summary.json").read_text())
    summary["design_documents"]["stages"] = ["prd", "lld", "website"]
    (source / "summary.json").write_text(json.dumps(summary))
    assert refused(new_run(), source) == "the earlier run's document chain cannot be read (summary.json names unknown stages)"


def test_the_lld_revisions_of_the_summary_come_back(source, new_run):
    summary = json.loads((source / "summary.json").read_text())
    summary["design_documents"]["lld_revisions"] = [{"section": "S2", "reason": "no such element"}]
    (source / "summary.json").write_text(json.dumps(summary))
    follow = new_run()
    follow.rehydrate(source)
    assert follow.lld_revisions == [{"section": "S2", "reason": "no such element"}]


def test_a_chain_without_documents_json_is_refused(source, new_run):
    (source / "documents.json").unlink()
    assert refused(new_run(), source) == "the earlier run's document chain has no documents.json"


def test_a_chain_missing_a_requested_document_is_refused(source, new_run):
    documents = json.loads((source / "documents.json").read_text())
    del documents["hld"]
    (source / "documents.json").write_text(json.dumps(documents))
    assert refused(new_run(), source) == "documents.json has no HLD (the document chain is incomplete)"


@pytest.mark.parametrize("name", ["documents.json", "stage-hld.json"])
def test_an_unreadable_chain_file_is_refused(source, new_run, name):
    (source / name).write_text("{not json")
    assert refused(new_run(), source) == f"{name} cannot be read"


def test_stage_files_alone_are_a_chain_that_summary_json_must_describe(source, new_run):
    """The strict xfail of E1 wrote a stray documents.json and stage-prd.json next to a website run: still not a chain."""
    for name in ("documents.json", "stage-prd.json", "stage-hld.json", "stage-lld.json", "stage-website.json"):
        (source / name).write_text("{}")
    summary = json.loads((source / "summary.json").read_text())
    del summary["design_documents"]
    (source / "summary.json").write_text(json.dumps(summary))
    assert "document chain" in refused(new_run(), source)


def test_a_chain_run_may_start_with_a_document_output_but_a_plain_document_run_may_not(source, new_run, tmp_path):
    rows = (source / "chat.jsonl").read_text().splitlines()
    rows[0] = json.dumps({**json.loads(rows[0]), "output": "prd"})
    (source / "chat.jsonl").write_text("\n".join(rows) + "\n")
    new_run().rehydrate(source)                                    # the header is the first message's, the chain is the state
    plain_doc = tmp_path / "plain"
    shutil.copytree(source, plain_doc)
    for p in list(plain_doc.glob("stage-*.json")) + [plain_doc / "documents.json"]:
        p.unlink()
    assert refused(new_run(), plain_doc) == "the earlier run built a prd, not a website"


# ---- the split of the workflows ---------------------------------------------------------------------------------------------
def test_send_deed_workflows_belong_to_the_earlier_stages(source, new_run):
    """A send deed (or a milestone email) is a workflow of no document and not of the website: J2 keeps it in past_workflows."""
    workflows = json.loads((source / "workflows.json").read_text())
    deed = json.loads(json.dumps(workflows[-1]))
    deed.update(id="W-99", name="Send the document", atoms=[{"id": "W-99.a1", "verification": [{"type": "deed-send"}]}])
    workflows.append(deed)
    (source / "workflows.json").write_text(json.dumps(workflows))
    follow = new_run()
    follow.rehydrate(source)
    assert follow.past_workflows[-1]["id"] == "W-99" and "W-99" not in [w["id"] for w in follow.workflows]
    assert [w["id"] for w in follow.workflows] == [w["id"] for w in workflows if w["id"] not in
                                                   [p["id"] for p in follow.past_workflows]]
