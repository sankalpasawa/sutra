"""Is a newer Sutra Pro out? One question, asked only when the owner asks (gap package welcome-settings, item 2; the old app's update check, cut down).

    check(current, fetch=None, url=RELEASE_API, how=None) -> Answer        never raises
    sutra-pro update-check [--json]                                        the same on the command line (`register`)
    POST /api/ops/update-check                                             the Settings -> About button (ops/update_api.py)

NOTHING HERE RUNS ON IMPORT, ON BOOT OR ON A TIMER. The outbound requests of the app are made inside `check` (and `plan`, which is `check` plus the asset
of one platform), and they are called only by the owner's click, the owner's command, or the desktop app's own timer asking POST /api/ops/update-plan
while "Check for updates automatically" is on (ops/update_api.py; gap package autoupdate). It is ONE request while the newest Sutra Pro release is on the first page of the list; the list is shared with the older
product, whose releases are many and large, so a further page (at most MAX_PAGES in all) is asked only when the pages so far held no Sutra Pro release. It downloads and installs nothing (D34; the desktop app's updater does that, and it
is told here only the facts of the matching release's assets): it reads the list of releases and says what it found, with the one line the
owner follows for their kind of install. It sends nothing but the GET itself (no cookie, no identifier, no version header beyond a fixed User-Agent).

The feed is the Sutra repository's release list, filtered here (D100): a Sutra Pro tag is exactly `sutra-pro-vX.Y.Z` or `sutra-pro-vX.Y.Z-beta.N`, never
starts with `v`, and a release is never "Latest", so `releases/latest` (which belongs to the older product) is never asked. Drafts are dropped; a
pre-release counts only when the running version is itself a beta. Versions compare as tuples; a version that cannot be read never looks newer.

`check` never raises: a network error, a server error, a body that is cut off, a body that is not the list, an empty list each give an Answer with
`error` set to a sentence for the owner. `fetch(url, timeout) -> bytes` is injectable (tests pass a fake and never touch the network); the default
reads at most `MAX_BODY` bytes with `urllib`, with a timeout, through the system's proxy settings like any other program of the owner's.
"""
import argparse
import http.client
import json
import re
import sys
import urllib.error
import urllib.request
from collections.abc import Callable
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict

import sutra_app
from sutra_app.ops import cli

__all__ = ["check", "plan", "Answer", "Plan", "AssetFact", "ASSET_NAMES", "PLATFORM_ASSETS", "MAX_ASSET_BYTES", "install_kind", "how_to_update", "parse_tag", "default_fetch", "register", "REPO", "RELEASE_API", "RELEASES_PAGE",
           "TIMEOUT_S", "MAX_BODY", "PER_PAGE", "MAX_PAGES", "NET_ERRORS"]

REPO = "sankalpasawa/sutra"
PER_PAGE = 30                         # the old product's releases are about 28 KB each in the list: 30 of them stay far under MAX_BODY (50 took 70% of it, 100 does not fit)
MAX_PAGES = 6                         # newest first: 180 releases, then "no Sutra Pro release" rather than an endless walk
RELEASE_API = f"https://api.github.com/repos/{REPO}/releases?per_page={PER_PAGE}"
RELEASES_PAGE = f"https://github.com/{REPO}/releases?q=sutra-pro"
TIMEOUT_S = 8.0
MAX_BODY = 2 * 1024 * 1024
USER_AGENT = "sutra-pro-update-check"
# HTTPException is not an OSError (a body that stops short raises IncompleteRead), and a body that is not JSON is a ValueError
NET_ERRORS = (urllib.error.URLError, http.client.HTTPException, OSError, ValueError, TimeoutError)

_NUM = r"(?:0|[1-9][0-9]{0,8})"          # at most 9 digits: a longer number is no version of ours (int() refuses 4300+ digits, and a beta number must stay below the stable rank in `_key`)
_SAFE_PAGE = re.compile(r"https://github\.com/[A-Za-z0-9._~%/+@:=,;&?#-]{0,300}")      # no space, quote, angle bracket or control character: the link is printed and drawn
TAG_RE = re.compile(rf"sutra-pro-v(?P<v>{_NUM}\.{_NUM}\.{_NUM})(?:-beta\.(?P<beta>{_NUM}))?")
VERSION_RE = re.compile(rf"(?P<v>{_NUM}\.{_NUM}\.{_NUM})(?:(?:-beta\.|b)(?P<beta>{_NUM}))?")     # 0.2.0, 0.2.0-beta.1 and PEP 440's 0.2.0b1

Fetch = Callable[[str, float], bytes]

# The assets the desktop app's updater may take (D100's stable, version-free names): one disk image per Mac architecture, the per-user Windows installer.
# Each has a `<name>.sha256` beside it on the release (`shasum -a 256 <name>`: "<hex>  <name>").
ASSET_NAMES = ("Sutra-Pro-arm64.dmg", "Sutra-Pro-x86_64.dmg", "Sutra-Pro-Setup-x64.exe")
PLATFORM_ASSETS = {("darwin", "arm64"): "Sutra-Pro-arm64.dmg", ("darwin", "x64"): "Sutra-Pro-x86_64.dmg", ("win32", "x64"): "Sutra-Pro-Setup-x64.exe"}
MAX_ASSET_BYTES = 1 << 30             # 1 GB: a larger asset is no build of ours
MAX_CHECKSUM_BYTES = 4096             # a .sha256 file is one line


class AssetFact(BaseModel):
    """One downloadable file of a release, as the feed states it and only after every field passed its check (see `_asset_facts`)."""

    model_config = ConfigDict(extra="forbid")
    name: str
    url: str                             # https://github.com/<repo>/releases/download/<tag>/<name>, exactly
    size: int                            # bytes, 1 .. MAX_ASSET_BYTES
    sha256_url: str                      # the same, for `<name>.sha256`


class Answer(BaseModel):
    """What the check found. `error` is a sentence for the owner when the question could not be answered (every other field is then as far as it got)."""

    model_config = ConfigDict(extra="forbid")
    current: str
    latest: str | None = None            # the newest release this install may take, "0.2.0" or "0.2.0-beta.1"
    newer: bool = False
    url: str = RELEASES_PAGE             # where the owner downloads it
    notes_url: str | None = None         # the release's own page
    how: str = ""                        # the one line for this install
    kind: str = "command"
    error: str | None = None
    tag: str | None = None               # the tag of `latest`, "sutra-pro-v0.2.0"
    assets: dict[str, AssetFact] = {}    # the usable assets of that release by name (empty when the feed lists none that passed), newer or not


class Plan(Answer):
    """What the desktop app's updater needs: the answer plus the asset for ITS platform and architecture. `asset` is set only when `newer` and no `error`."""

    channel: str = "stable"              # "beta" when the running version is a beta (it is offered newer betas and stables), else "stable" (stables only)
    asset: AssetFact | None = None


def parse_tag(tag: object, *, beta_ok: bool = True) -> tuple[tuple[int, int, int, int], str] | None:
    """`sutra-pro-v0.2.0` -> ((0, 2, 0, inf-ish), "0.2.0"); `-beta.N` sorts BEFORE its stable version. None for any other tag."""
    found = TAG_RE.fullmatch(tag) if isinstance(tag, str) else None
    if found is None or (found.group("beta") is not None and not beta_ok):
        return None
    return _key(found), found.group("v") + (f"-beta.{found.group('beta')}" if found.group("beta") is not None else "")


def _key(found: re.Match) -> tuple[int, int, int, int]:
    major, minor, patch = (int(x) for x in found.group("v").split("."))
    beta = found.group("beta")
    return major, minor, patch, (int(beta) if beta is not None else 10 ** 9)           # a beta is older than its stable release


def _running(current: str) -> tuple[tuple[int, int, int, int], bool] | None:
    found = VERSION_RE.fullmatch(current.strip()) if isinstance(current, str) else None
    return None if found is None else (_key(found), found.group("beta") is not None)


# ---- the line for this install -------------------------------------------------------------------------------------------------

def install_kind(executable: str | None = None, package_dir: Path | None = None, platform: str | None = None) -> str:
    """`mac-app`, `windows-app`, `checkout` or `command` (uv tool install). The arguments are for a test; the defaults read this process."""
    exe = (executable if executable is not None else sys.executable).replace("\\", "/")
    where = package_dir if package_dir is not None else Path(sutra_app.__file__).resolve().parent.parent
    system = platform if platform is not None else sys.platform
    if system == "darwin" and ".app/Contents/" in exe:
        return "mac-app"
    if system == "win32" and exe.rsplit("/", 1)[-1].lower().startswith("sutrapro"):          # desktop.py: `SutraPro.exe -X utf8 -m sutra_app.desktop`
        return "windows-app"
    if (where / ".git").exists() or (where.parent / ".git").exists():
        return "checkout"
    return "command"


_HOW = {
    "mac-app": "Download the new Sutra-Pro .dmg from the release page and drag it over the app in Applications.",
    "windows-app": "Download the new Sutra-Pro-Setup .exe from the release page and run it.",
    "command": "Run `uv tool install --reinstall` with the address of the new wheel from the release page, then start Sutra Pro again.",
    "checkout": "Run `git pull` in your checkout, then `uv pip install -e .` and start Sutra Pro again.",
}


def how_to_update(kind: str) -> str:
    return _HOW.get(kind, _HOW["command"])


# ---- the question --------------------------------------------------------------------------------------------------------------

def default_fetch(url: str, timeout: float) -> bytes:
    """GET `url`: at most MAX_BODY bytes, a `User-Agent` and an `Accept`, nothing else. Raises a NET_ERRORS member on any failure."""
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/vnd.github+json"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        body = response.read(MAX_BODY + 1)
    if len(body) > MAX_BODY:
        raise ValueError("the answer is larger than expected")
    return body


Picked = tuple[tuple[int, int, int, int], str, str, str, dict[str, AssetFact]]


def _size_ok(value: Any, high: int) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and 1 <= value <= high


def _asset_facts(item: dict, tag: str) -> dict[str, AssetFact]:
    """The usable assets of one release. An asset is kept only when its name is one of ASSET_NAMES, GitHub says it is uploaded, its address is EXACTLY
    https://github.com/<repo>/releases/download/<tag>/<name> (built here from the release's own tag, never taken from the feed's text), its size is a
    sane whole number, and the release carries `<name>.sha256` the same way. Anything else drops that one asset: a feed cannot point the updater elsewhere."""
    listed = item.get("assets")
    if not isinstance(listed, list):
        return {}
    uploaded: dict[str, tuple[str, Any]] = {}
    for entry in listed:
        if isinstance(entry, dict) and isinstance(entry.get("name"), str) and entry.get("state") == "uploaded" and entry["name"] not in uploaded:
            url = entry.get("browser_download_url")
            uploaded[entry["name"]] = (url if isinstance(url, str) else "", entry.get("size"))
    base = f"https://github.com/{REPO}/releases/download/{tag}/"
    facts: dict[str, AssetFact] = {}
    for name in ASSET_NAMES:
        main, side = uploaded.get(name), uploaded.get(name + ".sha256")
        if main is None or side is None:
            continue
        if main[0] != base + name or side[0] != base + name + ".sha256" or not _size_ok(main[1], MAX_ASSET_BYTES) or not _size_ok(side[1], MAX_CHECKSUM_BYTES):
            continue
        facts[name] = AssetFact(name=name, url=base + name, size=main[1], sha256_url=base + name + ".sha256")
    return facts


def _pick(releases: Any, beta_ok: bool) -> Picked | None:
    """The newest (key, version, release page, tag, assets) among the Sutra Pro releases of a list, or None."""
    if not isinstance(releases, list):
        raise ValueError("the release list is not a list")
    best = None
    for item in releases:
        if not isinstance(item, dict) or item.get("draft") is True:
            continue
        parsed = parse_tag(item.get("tag_name"), beta_ok=beta_ok)
        if parsed is None or (item.get("prerelease") is True and not beta_ok):
            continue
        if best is None or parsed[0] > best[0]:
            page = item.get("html_url")
            best = (parsed[0], parsed[1], page if isinstance(page, str) and _SAFE_PAGE.fullmatch(page) else RELEASES_PAGE, item["tag_name"],
                    _asset_facts(item, item["tag_name"]))
    return best


def _page_url(url: str, page: int) -> str:
    return url if page == 1 else url + ("&" if "?" in url else "?") + f"page={page}"


def _newest(fetch: Fetch, url: str, beta_ok: bool) -> Picked | None:
    """The newest Sutra Pro release, reading the list newest first and going on to the next page only while a full page held none."""
    for page in range(1, MAX_PAGES + 1):
        releases = json.loads(fetch(_page_url(url, page), TIMEOUT_S))
        picked = _pick(releases, beta_ok)                       # raises ValueError when the answer is not a list
        if picked is not None or len(releases) < PER_PAGE:
            return picked
    return None


def check(current: str, fetch: Fetch | None = None, url: str = RELEASE_API, how: str | None = None) -> Answer:
    """Ask the release feed whether something newer than `current` is out. Never raises."""
    kind = how if how is not None else install_kind()
    answer = Answer(current=str(current), kind=kind, how=how_to_update(kind))
    running = _running(current)
    try:
        picked = _newest(fetch or default_fetch, url, beta_ok=running is not None and running[1])
    except NET_ERRORS as exc:
        return answer.model_copy(update={"error": _words(exc)})
    except Exception:                                                                # noqa: BLE001  (a check must never break the page or the command)
        return answer.model_copy(update={"error": "The answer from GitHub could not be read."})
    if picked is None:
        return answer.model_copy(update={"error": "No Sutra Pro release was found on GitHub yet."})
    key, version, page, tag, assets = picked
    newer = running is not None and key > running[0]
    return answer.model_copy(update={"latest": version, "newer": newer, "notes_url": page, "url": page if newer else RELEASES_PAGE, "tag": tag, "assets": assets})


def plan(current: str, platform: str | None, arch: str | None, fetch: Fetch | None = None, url: str = RELEASE_API, how: str | None = None) -> Plan:
    """`check` plus the asset of `(platform, arch)` (Node's names: darwin/win32, arm64/x64) for the desktop app's updater. Never raises. One request
    while the newest release is on the first page, like `check`. No asset for a platform that has none, and none when nothing newer is out."""
    answer = check(current, fetch=fetch, url=url, how=how)
    running = _running(current)
    asset = None
    if answer.newer and not answer.error:
        wanted = PLATFORM_ASSETS.get((platform, arch)) if isinstance(platform, str) and isinstance(arch, str) else None
        asset = answer.assets.get(wanted) if wanted else None
    return Plan(**answer.model_dump(), channel="beta" if running is not None and running[1] else "stable", asset=asset)


def _words(exc: BaseException) -> str:
    if isinstance(exc, urllib.error.HTTPError):
        return f"GitHub answered {exc.code}. Try again later."
    if isinstance(exc, ValueError):
        return "The answer from GitHub could not be read."
    return "Could not reach GitHub. Check your connection and try again."


def sentence(answer: Answer) -> str:
    """The answer in one line for the owner, the same words on the page and in the terminal."""
    if answer.error:
        return answer.error
    if answer.newer:
        return f"You have {answer.current}; {answer.latest} is out."
    return f"You have {answer.current}: up to date."


# ---- the command ---------------------------------------------------------------------------------------------------------------

def cmd_update_check(args: argparse.Namespace) -> int:
    """Exit 0 when up to date or newer is out (a question answered), 1 when it could not be answered. Offline mode (SUTRA_OFFLINE) refuses."""
    settings = cli.load_settings(args)
    if settings is None:
        return 2
    if settings.offline or settings.connector == "stub":
        print("sutra-pro: update-check is not available in offline mode (no request is made).", file=sys.stderr)
        return 1
    answer = check(sutra_app.__version__)
    lines = [sentence(answer)]
    if answer.newer:
        lines += [f"Release notes and downloads: {answer.url}", answer.how]
    cli.emit(args, answer.model_dump(), lines)
    return 1 if answer.error else 0


def register(sub: Any) -> None:
    """Add `update-check` to the CLI's subparsers (the `register(sub)` contract of ops.cli)."""
    p = sub.add_parser("update-check", parents=[cli.common_parser()],
                       help="ask GitHub whether a newer Sutra Pro release is out (downloads and installs nothing)")
    p.set_defaults(func=cmd_update_check)
