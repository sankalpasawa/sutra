"""project_import.py -- every project you have worked in becomes a department.

WHY THIS EXISTS
A new operator installs Sutra and the Org screen is empty. The registry is real
but unpopulated, so the one surface that makes Sutra different from a chat
client has nothing in it. Meanwhile the machine already knows what this person
works on: ~/.claude/projects holds one folder per working directory, and the
transcripts inside carry the real path. Founder direction 2026-09-08: every
Claude project becomes a department on install; a project seen again LINKS to
its existing department rather than minting a second one.

WHY NOT DECODE THE FOLDER NAME
~/.claude/projects/<encoded-cwd> replaces every "/" with "-", and directory
names contain "-" themselves. "-Users-x-Desktop-development-ai-dev-manager" is
`/Users/x/Desktop/development/ai-dev-manager` -- but it is equally readable as
`.../ai/dev/manager`, and nothing in the name says which. The decode is lossy
and there is no need to guess: the transcript's own JSONL carries `cwd` as a
field (session_reader.py:97 already reads it this way). We read the file.

WHY THIS IS NOT IN org_api.py
org_api.py is read-mostly by design and test_forbidden_calls.py greps it for
`mint_domain` and fails the build if it appears (test_forbidden_calls.py:27-37).
That gate covers exactly two modules -- org_api.py and reorg_sim.py -- so the
importer lives here, in its own module, and calls the engine's mint verb
directly. Keeping it out of org_api.py preserves that provable negative rather
than working around it.

IDEMPOTENCY IS THE ENGINE'S, NOT OURS
mint_domain re-checks under its lock for a live sibling with the same
normalised name under the same parent and returns (existing_ref, False)
(placement_engine.py:386-390). So "link if it already exists" needs no
bookkeeping here: we mint unconditionally and report what the engine says it
did. Running this twice creates nothing the second time.
"""
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

_LIB_DIR = str(Path(__file__).resolve().parents[1] / "lib")
if _LIB_DIR not in sys.path:
    sys.path.insert(0, _LIB_DIR)

import placement_engine as E  # noqa: E402  (path insert must precede this import)

CLAUDE_PROJECTS = Path(os.path.expanduser("~/.claude/projects"))

#: The desktop app's own session store -- one JSON file per session, holding
#: `cwd` and `originCwd`. THIS IS THE SOURCE THE APP'S OWN PROJECT LIST IS
#: BUILT FROM, and reading only ~/.claude/projects missed it entirely: on the
#: founder's machine that omission lost bahi-khata, cover-letter and
#: lenovo-case-study (desktop-only) and every project whose sessions ran
#: without leaving a CLI transcript.
DESKTOP_SESSIONS = Path(os.path.expanduser(
    "~/Library/Application Support/Claude/claude-code-sessions"))

#: The CLI's own config. Its `projects` map is keyed by ABSOLUTE PATH, so it
#: needs no decoding, and it remembers a project that has no session left on
#: disk -- hokage-desk, kaguya, nakama-cli-suite and sovereign-ai are known
#: only here.
CLAUDE_CONFIG = Path(os.path.expanduser("~/.claude.json"))

#: A worktree is a checkout OF a repo, not a project beside it. `originCwd`
#: already resolves this in the desktop store; ~/.claude.json stores the raw
#: worktree path, so it is collapsed here too -- otherwise one repo shows up as
#: several departments named after generated branch slugs.
_WORKTREE_RE = re.compile(r"^(?P<repo>.+?)/\.(?:claude|git)/worktrees/[^/]+/?$")

#: A working directory under one of these is scratch, not a department. The
#: /private/tmp entries are this harness's own per-session scratchpads -- 13 of
#: the 38 folders on the founder's machine on 2026-09-08 -- and importing them
#: would bury the real projects under throwaways named "scratchpad-triage-wd".
JUNK_PREFIXES = ("/private/tmp", "/tmp", "/var/folders")

#: Words that look wrong in Title Case. Extend freely -- a miss is cosmetic.
ACRONYMS = {"ui", "ux", "ai", "api", "cp", "seo", "os", "cli", "db", "qa",
            "ci", "cd", "pr", "sdk", "mcp", "llm", "id"}

#: How many lines of a transcript to scan for `cwd`. It appears on line 2 in
#: practice; 40 is slack for a preamble, and bounds the read on a 900-session
#: folder to something that costs nothing.
CWD_SCAN_LINES = 40


def _real_cwd(session_file):
    """The working directory a transcript was recorded in, or "" if the file
    does not say. Read from the JSONL body, never decoded from the folder
    name -- see the module docstring on why the folder name is lossy."""
    try:
        with open(session_file, "r", encoding="utf-8", errors="replace") as fh:
            for i, line in enumerate(fh):
                if i >= CWD_SCAN_LINES:
                    break
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except ValueError:
                    continue
                cwd = rec.get("cwd")
                if cwd:
                    return cwd
    except OSError:
        pass
    return ""


def _is_junk(cwd, home):
    """A path we refuse to turn into a department, with the reason.

    The home directory itself is excluded deliberately: `claude` run from ~
    produces a folder like any project, but "tchandrakar" is not a department
    -- it is every department at once, and importing it creates a node that
    would parent everything under it by the containment rule below."""
    if not cwd:
        return "no working directory recorded"
    if any(cwd == p or cwd.startswith(p + os.sep) for p in JUNK_PREFIXES):
        return "scratch path"
    if os.path.normpath(cwd) == os.path.normpath(home):
        return "home directory, not a project"
    return None


def _collapse_worktree(path):
    """A worktree path folded back onto the repo it is a checkout of."""
    m = _WORKTREE_RE.match(path.rstrip(os.sep))
    return m.group("repo") if m else path


def _from_desktop(root):
    """{cwd: session count} from the desktop app's session store."""
    out = {}
    if not root.is_dir():
        return out
    for f in root.glob("*/*/*.json"):
        try:
            with open(f, "r", encoding="utf-8", errors="replace") as fh:
                rec = json.load(fh)
        except (OSError, ValueError):
            continue
        if not isinstance(rec, dict):
            continue
        # originCwd first: for a worktree session it names the real repo, which
        # is why the app's own list shows one entry per repo and not one per
        # generated branch slug.
        cwd = rec.get("originCwd") or rec.get("cwd")
        if cwd:
            cwd = _collapse_worktree(cwd)
            out[cwd] = out.get(cwd, 0) + 1
    return out


def _from_config(path):
    """{cwd: 0} for every project the CLI config remembers. Count is 0 because
    the config records that a project EXISTS, not how much work is in it; real
    counts come from the two session stores and are summed on top."""
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            cfg = json.load(fh)
    except (OSError, ValueError):
        return {}
    projects = cfg.get("projects")
    if not isinstance(projects, dict):
        return {}
    return {_collapse_worktree(p): 0 for p in projects if p}


def _from_cli_transcripts(root):
    """{cwd: transcript count} from ~/.claude/projects. The cwd is read out of
    each transcript body rather than decoded from the folder name -- see the
    module docstring on why the folder name is lossy."""
    out = {}
    if not root.is_dir():
        return out
    for folder in sorted(root.iterdir()):
        if not folder.is_dir():
            continue
        sessions = sorted(folder.glob("*.jsonl"))
        if not sessions:
            continue
        cwd = ""
        for f in sorted(sessions, key=lambda p: p.stat().st_mtime, reverse=True):
            cwd = _real_cwd(f)
            if cwd:
                break
        if cwd:
            cwd = _collapse_worktree(cwd)
            out[cwd] = out.get(cwd, 0) + len(sessions)
    return out


def discover(projects_dir=None, home=None, desktop_dir=None, config_path=None):
    """Every project this machine knows about, from ALL THREE stores.

    ONE STORE IS NOT ENOUGH, and that is the whole point of this function.
    ~/.claude/projects alone -- what this read until 2026-09-08 -- found 12
    projects on the founder's machine where the union finds 26. It cannot see a
    project whose sessions ran in the desktop app (bahi-khata, cover-letter,
    lenovo-case-study) and it cannot see one the CLI merely remembers
    (hokage-desk, kaguya, nakama-cli-suite, sovereign-ai). A department list
    built from it disagrees with the project list the operator is looking at in
    Claude, which is the bug this exists to prevent.

    Returns (kept, skipped). Rows are {cwd, sessions, sources}; skipped rows
    carry a `why`, so the caller can state what it dropped rather than
    silently importing a subset."""
    home = home or os.path.expanduser("~")
    per_source = {
        "desktop": _from_desktop(Path(desktop_dir or DESKTOP_SESSIONS)),
        "config":  _from_config(Path(config_path or CLAUDE_CONFIG)),
        "cli":     _from_cli_transcripts(Path(projects_dir or CLAUDE_PROJECTS)),
    }
    merged = {}
    for name, found in per_source.items():
        for cwd, n in found.items():
            row = merged.setdefault(os.path.normpath(cwd),
                                    {"cwd": os.path.normpath(cwd),
                                     "sessions": 0, "sources": []})
            row["sessions"] += n
            row["sources"].append(name)

    kept, skipped = [], []
    for cwd in sorted(merged):
        row = merged[cwd]
        row["sources"] = sorted(row["sources"])
        why = _is_junk(cwd, home)
        if why:
            skipped.append(dict(row, why=why))
        else:
            kept.append(row)
    return kept, skipped


def repo_name(cwd, _run=None):
    """The GitHub repo this directory IS, or "" — never the repo it is merely
    inside.

    WHY AT ALL. Claude's own project list names a project by its git remote:
    the founder's folder `live-contest-event-leaderboard` shows there as
    `live-contest-event-dashboard`, which is the repo name on GitHub. Sutra
    naming the same project after the folder is a visible disagreement between
    two lists of the same thing.

    WHY ONLY AT THE REPO ROOT, and this is the whole rule. A subdirectory of a
    repo reports its PARENT's remote, so a naive "use the remote" would have
    renamed `sovereign-ai/plans` to "Sovereign AI" and
    `sutra/marketplace/plugin/sutra-ui` to "Sutra" -- each colliding with the
    real department of that name, and mint_domain would then fold the child
    INTO its parent by name-dedupe. Measured on the founder's machine before
    this guard existed: 3 projects would have been renamed, 2 of them wrongly.
    So the remote wins only when `rev-parse --show-toplevel` is the project
    directory itself.

    Fails soft to "" (folder name wins): no git binary, not a repo, no remote,
    a deleted directory, or a slow filesystem all mean "we did not learn a
    better name", never an error."""
    run = _run or (lambda args: subprocess.run(
        args, capture_output=True, text=True, timeout=5))
    try:
        top = run(["git", "-C", cwd, "rev-parse", "--show-toplevel"]).stdout.strip()
        if not top or os.path.realpath(top) != os.path.realpath(cwd):
            return ""                       # a subdirectory, not the repo
        url = run(["git", "-C", cwd, "remote", "get-url", "origin"]).stdout.strip()
    except Exception:                                      # noqa: BLE001
        return ""
    if not url:
        return ""
    # Handles git@host:owner/repo.git, https://host/owner/repo(.git), git://,
    # and a local path remote. The last path segment is the repo either way.
    name = url.rstrip("/").rsplit("/", 1)[-1]
    if name.endswith(".git"):
        name = name[:-4]
    # "git@github.com:repo" with no owner leaves the host glued on.
    if ":" in name:
        name = name.rsplit(":", 1)[-1]
    return name.strip()


def humanize(path):
    """A department name from a directory basename.

    "asawa-holding" -> "Asawa Holding"; "sutra-ui" -> "Sutra UI";
    "UI-design-documents-" -> "UI Design Documents". Trailing separators are
    dropped rather than rendered as an empty word."""
    base = os.path.basename(path.rstrip(os.sep)) or path
    words = [w for w in re.split(r"[-_\s.]+", base) if w]
    out = []
    for w in words:
        if w.lower() in ACRONYMS:
            out.append(w.upper())
        elif w.isupper() and len(w) <= 4:
            out.append(w)              # already an acronym the caller chose
        else:
            out.append(w[:1].upper() + w[1:])
    return " ".join(out) or base


def build_forest(kept):
    """Nest projects by path containment, so the tree reads the way the disk
    does: `.../development/sutra/marketplace/plugin/sutra-ui` becomes a child
    of `.../development/sutra`, which becomes a child of `.../development`.

    A project's parent is the LONGEST other project path that is a proper
    ancestor of it. Longest wins so a deep project attaches to its nearest
    imported ancestor rather than to the shallowest one -- attaching sutra-ui
    to `development` instead of to `sutra` would be technically a containment
    but semantically wrong.

    Returns rows with `parent_cwd` (None = top level) and `depth`, ordered
    parents-before-children so a single pass can mint them."""
    by_cwd = {r["cwd"]: dict(r) for r in kept}
    paths = list(by_cwd)
    for cwd, row in by_cwd.items():
        ancestors = [p for p in paths
                     if p != cwd and cwd.startswith(p.rstrip(os.sep) + os.sep)]
        row["parent_cwd"] = max(ancestors, key=len) if ancestors else None
        # The repo name when this directory IS a repo root (Claude labels
        # projects that way), else the folder name. See repo_name().
        row["name"] = humanize(repo_name(cwd) or cwd)

    def depth(cwd):
        n, seen = 0, set()
        while by_cwd[cwd]["parent_cwd"] and cwd not in seen:
            seen.add(cwd)
            cwd = by_cwd[cwd]["parent_cwd"]
            n += 1
        return n

    for cwd, row in by_cwd.items():
        row["depth"] = depth(cwd)
    return sorted(by_cwd.values(), key=lambda r: (r["depth"], r["cwd"]))


# -------------------------------------------------------------- identity ---

#: Last resort when the machine will not say who it belongs to. Deliberately
#: generic: a wrong company name is worse than an obviously-unset one, because
#: it reads as a fact the operator never entered.
FALLBACK_ORG_NAME = "My Company"


def default_org_name():
    """The company name for a fresh install, read off the machine.

    WHY THIS IS DERIVED AND NOT A CONSTANT. It used to be the literal string
    "Asawa Inc." -- the founder's own holding -- so a stranger who installed
    Sutra was shown someone else's company as the root of THEIR org, and the
    identity footer offered them "CEO of Asawa Inc." as their role. That is
    not a default, it is a mislabel (founder, 2026-09-09).

    ORDER, STATED FIRST THEN DERIVED. SUTRA_ORG_NAME wins outright: it is the
    operator SAYING what their company is, and an explicit statement must beat
    a guess read off the account record -- otherwise the one lever that fixes a
    wrong name does nothing on any machine that has a full name set (which is
    every stock macOS install). Then the account's full name (pw_gecos,
    "Tishant" on the founder's machine), then the login name, then the
    constant. All rungs are local, offline and deterministic -- onboarding runs
    this at boot with no operator and no model in the loop.

    pw_gecos is comma-separated on some systems (the historical GECOS format,
    "Full Name,Office,Phone"); only the first field is a name."""
    stated = (os.environ.get("SUTRA_ORG_NAME") or "").strip()
    if stated:
        return stated
    try:
        import pwd
        ent = pwd.getpwuid(os.getuid())
        gecos = (ent.pw_gecos or "").split(",")[0].strip()
        if gecos:
            return gecos
        name = (ent.pw_name or "").strip()
        if name:
            return name
    except Exception:                                      # noqa: BLE001
        pass
    # Non-POSIX, or an account record we could not read at all.
    for var in ("USER", "LOGNAME"):
        val = (os.environ.get(var) or "").strip()
        if val:
            return val
    return FALLBACK_ORG_NAME


# ------------------------------------------------------------------ wipe ---

def wipe_registry(home_dir=None):
    """Delete every domain, charter and placement.

    DESTRUCTIVE AND NOT UNDOABLE from inside the app. The engine's own model is
    retire-never-delete (I-D5), so this deliberately steps outside it: the
    founder asked for a registry rebuilt from projects, and retired tombstones
    would keep voting in `_adjacent_domain_votes` and keep showing in history.
    The caller is expected to have tarred SUTRA_NATIVE_HOME first; `main()`
    refuses to run this without --i-have-a-backup.

    Returns a count per directory removed."""
    root = Path(home_dir or os.environ.get("SUTRA_NATIVE_HOME")
                or os.path.expanduser("~/.sutra-native/user-kit"))
    removed = {}
    for sub in ("domains", "charters", "placements"):
        d = root / sub
        if not d.is_dir():
            removed[sub] = 0
            continue
        n = 0
        for entry in d.iterdir():
            # Lock files are the engine's, not data. Removing them mid-flight
            # would orphan a flock another process is holding.
            if entry.name.endswith(".lock"):
                continue
            if entry.is_dir():
                shutil.rmtree(entry, ignore_errors=True)
            else:
                entry.unlink(missing_ok=True)
            n += 1
        removed[sub] = n
    return removed


# ----------------------------------------------------------------- apply ---

SYSTEM_ROOT_NAME = "Sutra"      # D76: the one root is named for the system, never for a person or a company
DESKTOP_NAME = "Desktop"        # D76: the app instance on this machine; every top-level import lives under it


def _existing_root_ref(preferred_name):
    """The live root to hang imports off: an active parent-less domain named
    `preferred_name` if there is one, else the ROOTED active parent-less domain
    (the engine's own `active_roots` order: largest subtree, then oldest), else
    None on an empty registry. Never mints. Preferring the name matters while a
    registry still carries two roots; the engine's order matters for the same
    reason -- a childless stray whose ref sorts first must not become the
    parent of every import (2026-09-13)."""
    domains = E.load_domains()
    roots = E.active_roots(domains)
    for ref in roots:
        if (domains[ref].get("name") or "").strip().lower() == preferred_name.strip().lower():
            return ref
    return roots[0] if roots else None


def apply_forest(forest, tenant_id="T-local", root_name=None):
    """Mint a department per project, parents first.

    Every node also gets `cwd` and `source` written onto its domain record.
    `cwd` is the join key the chat layer needs: a chat knows its working
    directory (chat_store.py:189) and this is what lets that directory resolve
    to a department without re-running classification.

    Returns (root_ref, rows) where each row says whether it was created or
    linked to an existing department."""
    # D76 (founder, 2026-09-12): THE ROOT IS THE SYSTEM'S, NOT THE ACCOUNT'S, AND
    # IMPORTS NEVER REACH THE TOP. This used to mint a root named after the
    # operator's company (default_org_name: SUTRA_ORG_NAME, else the macOS
    # account's full name). On the founder's own machine that minted a second
    # root carrying the account name next to the real organisation, and nine
    # imported folders under it duplicated departments that already existed.
    # Now: reuse the live root whatever it is called (prefer one named
    # SYSTEM_ROOT_NAME, else the first active parent-less domain), mint
    # SYSTEM_ROOT_NAME only on a registry with no root at all, and hang every
    # top-level import under a DESKTOP_NAME node: the app instance on this
    # machine. default_org_name still names the operator's organisation
    # elsewhere; it no longer names the root.
    root_name = root_name or os.environ.get("PLACEMENT_ROOT_NAME") or SYSTEM_ROOT_NAME
    root_ref = _existing_root_ref(root_name)
    if root_ref is None:
        root_ref, _ = E.mint_domain(None, root_name, ["root"], tenant_id,
                                    origin="project-import")
    root_tenant = (E.load_domains().get(root_ref) or {}).get("tenant_id") or tenant_id
    desktop_ref, _ = E.mint_domain(root_ref, DESKTOP_NAME,
                                   ["desktop instance on this machine"],
                                   root_tenant, origin="project-import")

    # A DEPARTMENT'S IDENTITY IS ITS cwd, NOT ITS NAME. mint_domain dedupes by
    # (parent, name), which is right for a hand-made org and wrong here: the
    # LABEL of an imported project can change while the project does not. The
    # first time repo_name() started naming projects after their git remote,
    # `live-contest-event-leaderboard` was renamed to "Live Contest Event
    # Dashboard" -- and minting by name produced a SECOND department, leaving
    # the old one orphaned and two domains claiming the same cwd, which makes
    # department_for_cwd resolve arbitrarily between them.
    # So: match on cwd first and rename in place; mint only what is genuinely new.
    #
    # A RETIRED cwd IS NOT A NEW cwd (DIR-14, 2026-09-12/13). The operator merged
    # the imported "Asawa Holding" into Asawa Inc., "Sutra" into Sutra OS and five
    # more; each tombstone names its successor. This loop matched ACTIVE records
    # only, so on the next start every one of those folders looked new and was
    # minted again under Desktop -- a nested chain of twins beside the real
    # departments, on every launch, forever. Now a retired cwd resolves through
    # the tombstone's successor chain (E.live_destination) and LINKS there; with
    # no live successor it is skipped. Nothing is ever minted for a cwd the
    # registry already knows.
    all_domains = E.load_domains()
    existing_by_cwd, retired_by_cwd = {}, {}
    for _ref, _d in sorted(all_domains.items()):      # sorted: a tie on stamps resolves the same way every run
        if not _d.get("cwd"):
            continue
        _key = os.path.normpath(_d["cwd"])
        if _d.get("status", "active") == "active":
            # "Minted by the importer FOR THIS FOLDER" is the join, not the
            # origin: the root and the Desktop node are importer-minted too
            # (origin project-import) and can be a folder's successor, and a
            # successor must never be renamed after the folder's label. The
            # importer records the cwd as mint evidence, so that is the key.
            _ev = [os.path.normpath(e) for e in (_d.get("mint_evidence") or []) if isinstance(e, str)]
            existing_by_cwd[_key] = (_ref, _d.get("name") or "",
                                     _d.get("origin") == "project-import" and _key in _ev)
        else:
            # the newest tombstone carries the current successor
            _prev = retired_by_cwd.get(_key)
            if _prev is None or ((_d.get("retired_at_ms") or _d.get("ts_minted_ms") or 0)
                                 >= (all_domains[_prev].get("retired_at_ms")
                                     or all_domains[_prev].get("ts_minted_ms") or 0)):
                retired_by_cwd[_key] = _ref

    ref_by_cwd, rows = {}, []
    for row in forest:
        parent_ref = ref_by_cwd.get(row["parent_cwd"], desktop_ref)
        key = os.path.normpath(row["cwd"])
        prior = existing_by_cwd.get(key)
        # A department the importer did not mint (an organisation node that
        # absorbed a folder, see below) owns its name, source and description;
        # the importer only keeps its cwd join key and session count current.
        imported = True
        if prior:
            ref, created = prior[0], False
            imported = prior[2]
            if imported and prior[1] != row["name"]:
                # A rename, not a new department. set_domain_fields keeps the
                # ref, so every placement and collapse key that names it stays
                # valid -- the whole reason to rename rather than re-mint.
                try:
                    E.set_domain_fields(ref, name=row["name"])
                    row["renamed_from"] = prior[1]
                except Exception as exc:                   # noqa: BLE001
                    row["rename_error"] = str(exc)
        elif key in retired_by_cwd:
            tomb = retired_by_cwd[key]
            dest, how = E.live_destination(tomb, all_domains, root_ref)
            dest_doc = all_domains.get(dest) if dest else None
            # Only an EXPLICIT successor chain counts. live_destination falls
            # back to the nearest live ancestor and then to the root, which is
            # right for re-homing filed work and wrong here: a folder retired
            # outright (dormant, out of scope) would come back as Desktop's cwd.
            if how != "successor" or dest_doc is None or dest_doc.get("status", "active") != "active":
                why = "frozen" if all_domains[tomb].get("status") == "frozen" else "retired-no-successor"
                rows.append(dict(row, ref=None, parent_ref=parent_ref, created=False,
                                 skipped=why, retired_ref=tomb))
                continue
            # The successor is somebody else's department (an organisation node
            # or the Desktop instance): it takes the cwd join key and the session
            # count only if it has no cwd of its own, and never the importer's
            # name, source or description. Children of this folder resolve their
            # parent to the successor, the same way a merge re-parents them.
            ref_by_cwd[row["cwd"]] = dest
            kept = bool(dest_doc.get("cwd"))
            if not kept:
                try:
                    E.set_domain_fields(dest, cwd=row["cwd"], sessions=row.get("sessions", 0))
                    # Keep the in-loop snapshot current: two retired folders can
                    # share one successor (Sutra UI and Sutra UI Workspace both
                    # merged into Sutra Desktop), and the second must see the
                    # cwd the first just wrote, not overwrite it (codex P2).
                    dest_doc["cwd"] = row["cwd"]
                except Exception as exc:                   # noqa: BLE001
                    row["field_error"] = str(exc)
            # A second folder onto the same successor leaves BOTH the cwd and the
            # session count alone: the count belongs to the folder the successor
            # answers for, not to whichever absorbed row ran last.
            rows.append(dict(row, ref=dest, parent_ref=parent_ref, created=False,
                             via="successor", retired_ref=tomb, cwd_kept=kept))
            continue
        else:
            ref, created = E.mint_domain(parent_ref, row["name"], [row["cwd"]],
                                         tenant_id, origin="project-import")
        ref_by_cwd[row["cwd"]] = ref
        try:
            # THE TRUE TOTAL, across all three stores -- not the number of
            # chats the panel happens to have paged in. The heading used to
            # count the loaded page and read "Asawa Holding 90" for a
            # project with 941 sessions; a count wrong by 10x is worse than
            # no count. Written at mint and refreshed on every boot by
            # sync(), so it is at most one session stale.
            fields = {"cwd": row["cwd"], "sessions": row.get("sessions", 0)}
            if imported:
                fields.update(source="claude-project",
                              description="Work in %s" % row["cwd"])
            E.set_domain_fields(ref, **fields)
        except Exception as exc:                       # noqa: BLE001
            # A field write failing must not abort the import: the domain
            # exists and is usable; only the cwd join key is missing, and a
            # re-run repairs it.
            row["field_error"] = str(exc)
        rows.append(dict(row, ref=ref, parent_ref=parent_ref,
                         created=created))
    return root_ref, rows


# ------------------------------------------------------------------ sync ---

def sync(tenant_id="T-local", root_name=None):
    """Bring the department tree level with the projects on this machine.

    THIS IS THE ONBOARDING PATH, and it is deliberately plain code: the app
    calls it at startup, so a new install has departments before anyone types
    anything, and a project started later becomes a department on the next
    launch without a human or a model being asked. Nothing here reads a prompt
    or calls a model (founder, 2026-09-08).

    NEVER WIPES. `wipe_registry` is reachable only from the CLI behind an
    explicit --wipe --i-have-a-backup, because an automatic boot path that can
    delete a registry is one crash-loop away from deleting it repeatedly. sync
    only ever ADDS: mint_domain returns the existing ref for a department that
    is already there (placement_engine.py:386), so re-running is free and a
    department the operator renamed or restructured by hand is left alone.

    Returns {"created": [...], "linked": n, "absorbed": [...], "skipped": n} --
    created and absorbed are lists of names (absorbed = folders whose department
    was retired into a successor and now resolve there, DIR-14), so a caller can
    log what appeared rather than a bare count.
    """
    kept, skipped = discover()
    forest = build_forest(kept)
    _root, rows = apply_forest(forest, tenant_id=tenant_id, root_name=root_name)
    # Org BUILD-PLAN S94: rows minted before `node_kind` existed get it once,
    # here, on the same startup path that already writes the registry. Fills
    # only the missing field; a row that has one is never touched. Never fails
    # the sync: the tree is more important than the kind label.
    try:
        E.backfill_node_kind()
    except Exception:                          # noqa: BLE001 -- best effort, logged by the engine's own writes
        pass
    return {"created": [r["name"] for r in rows if r["created"]],
            "linked": sum(1 for r in rows if not r["created"] and r.get("ref") and r.get("via") != "successor"),
            "absorbed": [r["name"] for r in rows if r.get("via") == "successor"],
            "skipped": len(skipped) + sum(1 for r in rows if r.get("skipped"))}


# --------------------------------------------------------------- resolve ---

def imported_departments(tenant_id="T-local"):
    """{cwd: domain record} for every live department this importer minted.

    Keyed by cwd because that is the only question the chat layer asks. Nodes
    without a cwd (the tenant root, anything minted by another path) are not
    addressable this way and are left out rather than given a placeholder."""
    out = {}
    for ref, d in E.load_domains().items():
        if d.get("status", "active") != "active":
            continue
        cwd = d.get("cwd")
        if cwd:
            out[os.path.normpath(cwd)] = dict(d, ref=ref)
    return out


def department_for_cwd(cwd, departments=None):
    """The department that owns a working directory, or None.

    LONGEST PREFIX WINS, and that is the whole rule. A chat opened in
    `.../sutra/marketplace/plugin/sutra-ui` belongs to Sutra UI, not to Sutra
    and not to Development, even though all three contain it -- the nearest
    imported ancestor is the specific answer and the others are merely true.

    An exact match is just the longest prefix, so it needs no special case.
    A path under no imported project returns None: the caller shows a chat
    with no department rather than filing it under a guess, which is the same
    rule teamsutra states for tasks (teamsutra.py:110)."""
    if not cwd:
        return None
    departments = imported_departments() if departments is None else departments
    target = os.path.normpath(cwd)
    best = None
    for dcwd, rec in departments.items():
        if target == dcwd or target.startswith(dcwd.rstrip(os.sep) + os.sep):
            if best is None or len(dcwd) > len(best[0]):
                best = (dcwd, rec)
    return best[1] if best else None


# ------------------------------------------------------------------ main ---

def _print_tree(forest, kept_by_cwd):
    by_parent = {}
    for r in forest:
        by_parent.setdefault(r["parent_cwd"], []).append(r)

    def walk(parent, indent):
        for r in sorted(by_parent.get(parent, []), key=lambda x: -x["sessions"]):
            print("%s%-34s %4d sessions   %s"
                  % (indent, r["name"], r["sessions"], r["cwd"]))
            walk(r["cwd"], indent + "    ")
    walk(None, "  ")


def main(argv):
    dry = "--apply" not in argv
    do_wipe = "--wipe" in argv
    backed_up = "--i-have-a-backup" in argv

    kept, skipped = discover()
    forest = build_forest(kept)

    print("=" * 72)
    print("CLAUDE PROJECTS -> DEPARTMENTS   (%s)"
          % ("DRY RUN -- nothing will be written" if dry else "APPLYING"))
    print("=" * 72)
    print("\nDEPARTMENTS TO CREATE (%d):" % len(forest))
    _print_tree(forest, {r["cwd"]: r for r in kept})

    print("\nSKIPPED (%d):" % len(skipped))
    for s in sorted(skipped, key=lambda x: x.get("why", "")):
        print("  %-52s %s" % (s["cwd"][:52], s.get("why", "?")))

    if dry:
        print("\nDry run. Re-run with --apply (and --wipe --i-have-a-backup "
              "to clear the registry first).")
        return 0

    if do_wipe:
        if not backed_up:
            print("\nREFUSED: --wipe deletes every domain, charter and "
                  "placement and cannot be undone from here.\n"
                  "Tar $SUTRA_NATIVE_HOME first, then pass "
                  "--i-have-a-backup.", file=sys.stderr)
            return 2
        removed = wipe_registry()
        print("\nWIPED: %s" % ", ".join("%s=%d" % kv for kv in sorted(removed.items())))

    root_ref, rows = apply_forest(forest)
    made = sum(1 for r in rows if r["created"])
    print("\nROOT: %s" % root_ref)
    print("DEPARTMENTS: %d created, %d linked to existing"
          % (made, len(rows) - made))
    for r in rows:
        print("  %-8s %-34s %s" % ("created" if r["created"] else "linked",
                                   r["name"], r["ref"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
