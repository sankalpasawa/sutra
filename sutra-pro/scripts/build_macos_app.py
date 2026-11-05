#!/usr/bin/env python3
"""Build `Sutra Pro.app`: a launcher script + a bundled CPython + the sutra-pro wheel installed into that CPython (D12, D89).

    scripts/py scripts/build_macos_app.py --wheel dist/sutra_pro-0.1.0-py3-none-any.whl --arch arm64 --out build
    scripts/py scripts/build_macos_app.py --wheel W --arch x86_64 --out build --python-archive cpython-...tar.gz   # offline / tests

There is no desktop shell: the app is a thin bundle. Layout of `<out>/Sutra Pro.app`:

    Contents/Info.plist              scripts/macos/Info.plist.tmpl, version taken from the wheel's METADATA
    Contents/PkgInfo                 APPL????
    Contents/MacOS/SutraPro          scripts/macos/launcher.sh (mode 0755)
    Contents/Resources/python/       the python-build-standalone CPython 3.11 (install_only_stripped), the wheel and its
                                     dependencies installed into its site-packages by that interpreter
    Contents/Resources/sutra-pro.icns    the icon (assets/icon/sutra-pro.icns)
    Contents/Resources/build-info.json   what went in (version, arch, archive name and sha256, wheel name and sha256)

The interpreter archive is fetched from the python-build-standalone release PBS_TAG for the arch, verified against a sha256
(PINNED_SHA256 when the name is listed there, else the release's own SHA256SUMS), and cached; a cached file that no longer matches
is deleted and fetched once more. `--python-archive` uses a local file instead (offline builds, tests): the file the caller gives is
trusted, nothing is downloaded. Only the standard library is used. The bundle is built natively (the wheel is installed by running
the bundled interpreter, which a foreign architecture cannot do); this script never signs: the release workflow signs afterwards.

Exit status: 0 built; 1 the build was refused or failed (one `error:` line); 2 bad command line.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import re
import shutil
import stat
import subprocess
import sys
import tarfile
import tempfile
import urllib.request
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

HERE = Path(__file__).resolve().parent
TEMPLATE_DIR = HERE / "macos"
INFO_PLIST_TEMPLATE = TEMPLATE_DIR / "Info.plist.tmpl"
LAUNCHER = TEMPLATE_DIR / "launcher.sh"
ICON = HERE.parent / "assets" / "icon" / "sutra-pro.icns"      # drawn by scripts/make_icons.py; Info.plist names it (CFBundleIconFile)

APP_NAME = "Sutra Pro"
APP_DIR = f"{APP_NAME}.app"
EXECUTABLE = "SutraPro"                      # no space: CFBundleExecutable names a file, and a script path with a space is a trap
BUNDLE_ID = "os.sutra.pro"                   # reverse DNS, in the namespace of the old app (os.sutra.ui); docs/notes/REL-2.md
DISTRIBUTION = "sutra-pro"                   # the Name: a wheel must carry
ARCHES = {"arm64": "aarch64-apple-darwin", "x86_64": "x86_64-apple-darwin"}
# every target the interpreter archive is looked up for: the two Macs, and the Windows app (scripts/build_windows_app.py, D101)
TRIPLES = {**ARCHES, "win-x64": "x86_64-pc-windows-msvc"}

PBS_REPO = "https://github.com/astral-sh/python-build-standalone/releases/download"
PBS_TAG = "20260901"                         # the release the old Sutra's DMG pins (bundle-runtime.sh, checked there 2026-09-13)
PY_SERIES = "3.11"
FLAVOUR = "install_only_stripped"            # runtime only, no debug symbols: the variant meant for redistribution
# Exact archive name -> sha256. A name listed here must match this table (a stronger pin than the release's own SHA256SUMS, which
# a tampered release would change too). Empty until the first CI build prints its digest line ("pin candidate: ...").
PINNED_SHA256: dict[str, str] = {}

VERSION_RE = re.compile(r"(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)")   # CFBundleVersion: three integers
BUNDLE_ID_RE = re.compile(r"[A-Za-z0-9]+(?:[.-][A-Za-z0-9]+)+")
PLACEHOLDER_RE = re.compile(r"@[A-Z_]+@")

Fetch = Callable[[str, Path], None]


class BuildError(Exception):
    """The build was refused or failed; the message is the whole explanation."""


# ---------------------------------------------------------------- small helpers

def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def host_arch() -> str:
    """The architecture this machine runs natively, in the names the DMGs use."""
    machine = platform.machine().lower()
    return {"arm64": "arm64", "aarch64": "arm64", "x86_64": "x86_64", "amd64": "x86_64"}.get(machine, machine)


def default_cache_dir() -> Path:
    override = os.environ.get("SUTRA_BUNDLE_CACHE")
    return Path(override) if override else Path.home() / ".cache" / "sutra-pro-bundle"


def fetch_url(url: str, dest: Path) -> None:
    """Download an https URL to `dest` (through a `.part` file, so an interrupted download is never mistaken for a cached one)."""
    if not url.startswith("https://"):
        raise BuildError(f"refusing to download {url!r}: only https is allowed")
    part = dest.with_name(dest.name + ".part")
    dest.parent.mkdir(parents=True, exist_ok=True)
    try:
        with urllib.request.urlopen(url, timeout=60) as response, part.open("wb") as out:   # noqa: S310 (https checked above)
            shutil.copyfileobj(response, out, 1 << 20)
    except OSError as error:                                   # URLError and HTTPError are OSErrors
        part.unlink(missing_ok=True)
        raise BuildError(f"download failed: {url} ({error})") from error
    part.replace(dest)


# ---------------------------------------------------------------- the wheel

@dataclass(frozen=True)
class WheelInfo:
    path: Path
    name: str
    version: str
    sha256: str


def read_wheel(path: Path) -> WheelInfo:
    """Name and version from the wheel's own METADATA (the file name is not trusted), and its sha256."""
    if not path.is_file():
        raise BuildError(f"wheel not found: {path}")
    try:
        with zipfile.ZipFile(path) as archive:
            metadata = [n for n in archive.namelist() if re.fullmatch(r"[^/]+\.dist-info/METADATA", n)]
            if len(metadata) != 1:
                raise BuildError(f"{path.name} has {len(metadata)} .dist-info/METADATA files, expected exactly one")
            text = archive.read(metadata[0]).decode("utf-8", "replace")
    except zipfile.BadZipFile as error:
        raise BuildError(f"{path.name} is not a wheel (not a zip file)") from error
    headers: dict[str, str] = {}
    for line in text.splitlines():
        if not line.strip():
            break                                              # the body of a METADATA file starts at the first blank line
        key, _, value = line.partition(":")
        headers.setdefault(key.strip().lower(), value.strip())
    name, version = headers.get("name", ""), headers.get("version", "")
    if re.sub(r"[-_.]+", "-", name).lower() != DISTRIBUTION:
        raise BuildError(f"{path.name} is the wheel of {name or 'no name'!r}, not of {DISTRIBUTION!r}")
    if not VERSION_RE.fullmatch(version):
        raise BuildError(f"wheel version {version!r} is not X.Y.Z; an app version must be three integers (cut a release tag)")
    return WheelInfo(path=path, name=name, version=version, sha256=sha256_of(path))


# ---------------------------------------------------------------- Info.plist

def xml_escape(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


def render_info_plist(template: str, *, version: str, bundle_id: str = BUNDLE_ID, executable: str = EXECUTABLE) -> str:
    """Fill the three fields of Info.plist.tmpl. Refuses a version that is not X.Y.Z, a malformed identifier, and a template that
    still has a field or lacks one."""
    if not VERSION_RE.fullmatch(version):
        raise BuildError(f"version {version!r} is not X.Y.Z")
    if not BUNDLE_ID_RE.fullmatch(bundle_id):
        raise BuildError(f"bundle identifier {bundle_id!r} is not reverse-DNS (letters, digits, dots, hyphens)")
    if not re.fullmatch(r"[A-Za-z0-9_-]+", executable):
        raise BuildError(f"executable name {executable!r} must be letters, digits, underscore or hyphen")
    values = {"@VERSION@": version, "@BUNDLE_ID@": bundle_id, "@EXECUTABLE@": executable}
    for field in values:
        if field not in template:
            raise BuildError(f"Info.plist template has no {field} field")
    out = template
    for field, value in values.items():
        out = out.replace(field, xml_escape(value))
    left = PLACEHOLDER_RE.findall(out)
    if left:
        raise BuildError(f"Info.plist template has unknown fields: {sorted(set(left))}")
    return out


# ---------------------------------------------------------------- the interpreter archive

def archive_name_pattern(arch: str) -> re.Pattern[str]:
    return re.compile(
        rf"cpython-({re.escape(PY_SERIES)}\.[0-9]+)\+{re.escape(PBS_TAG)}-{re.escape(TRIPLES[arch])}-{FLAVOUR}\.tar\.gz"
    )


def parse_sums(text: str) -> dict[str, str]:
    """A `SHA256SUMS` file (`<hex>  <name>` or `<hex> *<name>`) as {name: hex}."""
    sums: dict[str, str] = {}
    for line in text.splitlines():
        parts = line.split(None, 1)
        if len(parts) == 2 and re.fullmatch(r"[0-9a-fA-F]{64}", parts[0]):
            sums[parts[1].strip().lstrip("*")] = parts[0].lower()
    return sums


def pick_archive(sums: dict[str, str], arch: str) -> tuple[str, str]:
    """(file name, sha256) of the newest CPython of PY_SERIES for `arch` in a release's SHA256SUMS."""
    pattern = archive_name_pattern(arch)
    found = [(tuple(int(p) for p in m.group(1).split(".")), name) for name in sums if (m := pattern.fullmatch(name))]
    if not found:
        raise BuildError(
            f"python-build-standalone release {PBS_TAG} lists no CPython {PY_SERIES} {FLAVOUR} build for {TRIPLES[arch]}"
        )
    name = max(found)[1]
    return name, sums[name]


def resolve_archive(arch: str, cache_dir: Path, fetch: Fetch = fetch_url) -> tuple[Path, str]:
    """The verified, cached interpreter archive for `arch`: (path, sha256). Nothing unverified is ever returned."""
    cache_dir.mkdir(parents=True, exist_ok=True)
    sums_file = cache_dir / f"SHA256SUMS-{PBS_TAG}"
    if not sums_file.is_file() or sums_file.stat().st_size == 0:
        fetch(f"{PBS_REPO}/{PBS_TAG}/SHA256SUMS", sums_file)
    name, published = pick_archive(parse_sums(sums_file.read_text(encoding="utf-8", errors="replace")), arch)
    pinned = PINNED_SHA256.get(name)
    if pinned is not None and pinned.lower() != published:
        raise BuildError(f"{name}: the release now publishes {published} but this script pins {pinned.lower()}. Refusing to bundle it.")
    expected = pinned.lower() if pinned is not None else published
    target = cache_dir / name
    for attempt in (1, 2):
        if target.is_file() and sha256_of(target) == expected:
            break
        if target.is_file():
            target.unlink()                                    # a stale or damaged cache entry
        if attempt == 2:
            raise BuildError(f"{name} does not match its sha256 {expected} after a fresh download. Refusing to bundle it.")
        fetch(f"{PBS_REPO}/{PBS_TAG}/{name}", target)
    if pinned is None:
        print(f"pin candidate: PINNED_SHA256[{name!r}] = {expected!r}")
    return target, expected


def safe_members(archive: tarfile.TarFile, dest: Path):
    """Members of a tar archive that stay inside `dest`: no absolute names, no `..`, no devices, no link that leaves the tree."""
    root = dest.resolve()
    for member in archive.getmembers():
        name = Path(member.name)
        if name.is_absolute() or ".." in name.parts:
            raise BuildError(f"unsafe path in the interpreter archive: {member.name!r}")
        if member.isdev():
            raise BuildError(f"device file in the interpreter archive: {member.name!r}")
        if member.issym() or member.islnk():
            base = (root / name.parent) if member.issym() else root
            target = (base / member.linkname).resolve()
            if root != target and root not in target.parents:
                raise BuildError(f"link {member.name!r} points outside the archive ({member.linkname!r})")
        yield member


def extract_python(archive_path: Path, resources: Path) -> Path:
    """Unpack a python-build-standalone `install_only` archive (one top folder, `python/`) into Contents/Resources."""
    resources.mkdir(parents=True, exist_ok=True)
    try:
        with tarfile.open(archive_path, "r:*") as archive:
            members = list(safe_members(archive, resources))
            if hasattr(tarfile, "data_filter"):                # 3.11.4+: also drops setuid bits and the like
                archive.extractall(resources, members=members, filter="data")
            else:
                archive.extractall(resources, members=members)
    except (tarfile.TarError, EOFError) as error:
        raise BuildError(f"cannot unpack {archive_path.name}: {error}") from error
    interpreter = resources / "python" / "bin" / "python3"
    if not interpreter.exists():
        raise BuildError(f"{archive_path.name} did not contain python/bin/python3")
    return interpreter


# ---------------------------------------------------------------- the bundle

def clean_env() -> dict[str, str]:
    """The environment the bundled interpreter runs with: nothing of the builder's Python, no user pip config, no user site."""
    env = {k: v for k, v in os.environ.items() if not k.startswith(("PYTHON", "PIP_", "VIRTUAL_ENV", "UV_"))}
    env.update(PYTHONNOUSERSITE="1", PYTHONDONTWRITEBYTECODE="1", PIP_CONFIG_FILE=os.devnull, PIP_DISABLE_PIP_VERSION_CHECK="1")
    return env


def run_bundled(interpreter: Path, args: list[str], what: str) -> subprocess.CompletedProcess:
    try:
        done = subprocess.run([str(interpreter), *args], env=clean_env(), capture_output=True, text=True, timeout=1800)
    except (OSError, subprocess.TimeoutExpired) as error:
        raise BuildError(f"{what}: cannot run the bundled interpreter ({error}). Build on a machine of the target architecture.") from error
    if done.returncode != 0:
        tail = "\n".join((done.stdout + done.stderr).strip().splitlines()[-15:])
        raise BuildError(f"{what} failed (exit {done.returncode}):\n{tail}")
    return done


def listing(directory: Path) -> set[str]:
    return {p.name for p in directory.iterdir()} if directory.is_dir() else set()


def install_wheel(interpreter: Path, wheel: WheelInfo) -> None:
    """Install the wheel (and its dependencies, from the index) with the bundled interpreter, then prove it imports there.

    pip writes console scripts with an absolute shebang naming this build folder; they would break the moment the app is copied to
    /Applications (and a space in the path breaks a shebang anyway). The app starts `python -m sutra_app`, so the scripts pip added
    to python/bin are removed."""
    bin_dir = interpreter.parent
    before = listing(bin_dir)
    run_bundled(
        interpreter,
        ["-m", "pip", "install", "--no-input", "--disable-pip-version-check", "--no-warn-script-location", str(wheel.path)],
        "pip install of the wheel",
    )
    for name in sorted(listing(bin_dir) - before):
        path = bin_dir / name
        if path.is_file() and not path.is_symlink():
            path.unlink()
    probe = run_bundled(
        interpreter,
        ["-I", "-c", "import importlib.metadata as m, sutra_app; print(m.version('sutra-pro'))"],
        "importing sutra_app from the bundle",
    )
    installed = probe.stdout.strip().splitlines()[-1] if probe.stdout.strip() else ""
    if installed != wheel.version:
        raise BuildError(f"the bundle reports sutra-pro {installed!r} but the wheel is {wheel.version!r}")


def build_app(
    *,
    wheel: Path,
    arch: str,
    out: Path,
    python_archive: Optional[Path] = None,
    cache_dir: Optional[Path] = None,
    fetch: Fetch = fetch_url,
    allow_foreign_arch: bool = False,
) -> Path:
    """Build `<out>/Sutra Pro.app` and return its path. Replaces an app of that name already in `out`; touches nothing else."""
    if arch not in ARCHES:
        raise BuildError(f"unsupported arch {arch!r} (arm64 or x86_64)")
    if arch != host_arch() and not allow_foreign_arch:
        raise BuildError(
            f"this machine is {host_arch()} but the bundle is {arch}: the wheel is installed by running the bundled interpreter, "
            "so build on a machine of the target architecture (the workflow does)"
        )
    info = read_wheel(wheel)
    if not ICON.is_file():
        raise BuildError(f"the icon is missing: {ICON}")
    template = INFO_PLIST_TEMPLATE.read_text(encoding="utf-8")
    plist = render_info_plist(template, version=info.version)         # fail before downloading anything
    if python_archive is not None:
        if not python_archive.is_file():
            raise BuildError(f"python archive not found: {python_archive}")
        archive, archive_sha = python_archive, sha256_of(python_archive)
    else:
        archive, archive_sha = resolve_archive(arch, cache_dir or default_cache_dir(), fetch)

    out.mkdir(parents=True, exist_ok=True)
    app = out / APP_DIR
    # build beside the target and rename at the end: a failed build never leaves a half bundle under the final name
    stage = Path(tempfile.mkdtemp(prefix=".sutra-pro-build-", dir=out))
    try:
        contents = stage / APP_DIR / "Contents"
        macos, resources = contents / "MacOS", contents / "Resources"
        macos.mkdir(parents=True)
        resources.mkdir(parents=True)
        interpreter = extract_python(archive, resources)
        install_wheel(interpreter, info)

        launcher = macos / EXECUTABLE
        shutil.copyfile(LAUNCHER, launcher)
        launcher.chmod(launcher.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
        shutil.copyfile(ICON, resources / ICON.name)
        (contents / "Info.plist").write_text(plist, encoding="utf-8")
        (contents / "PkgInfo").write_text("APPL????", encoding="ascii")
        (resources / "build-info.json").write_text(
            json.dumps(
                {
                    "app": APP_NAME, "bundle_id": BUNDLE_ID, "version": info.version, "arch": arch,
                    "python_archive": archive.name, "python_archive_sha256": archive_sha,
                    "wheel": wheel.name, "wheel_sha256": info.sha256,
                },
                indent=2, sort_keys=True,
            ) + "\n",
            encoding="utf-8",
        )
        if app.exists():
            shutil.rmtree(app)
        (stage / APP_DIR).rename(app)
    finally:
        shutil.rmtree(stage, ignore_errors=True)
    return app


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Build Sutra Pro.app (launcher + bundled CPython + the wheel). Never signs.")
    parser.add_argument("--wheel", required=True, type=Path, help="the sutra_pro-X.Y.Z-py3-none-any.whl to install into the bundle")
    parser.add_argument("--arch", choices=sorted(ARCHES), default=None, help="target architecture (default: this machine's)")
    parser.add_argument("--out", required=True, type=Path, help="folder that receives 'Sutra Pro.app'")
    parser.add_argument("--python-archive", type=Path, default=None,
                        help="a local python-build-standalone archive to use instead of downloading one (trusted as given)")
    parser.add_argument("--cache-dir", type=Path, default=None, help="download cache (default: $SUTRA_BUNDLE_CACHE or ~/.cache/sutra-pro-bundle)")
    parser.add_argument("--allow-foreign-arch", action="store_true", help="skip the native-architecture check (tests with a fake interpreter)")
    args = parser.parse_args(argv)
    arch = args.arch or host_arch()
    try:
        app = build_app(
            wheel=args.wheel, arch=arch, out=args.out, python_archive=args.python_archive,
            cache_dir=args.cache_dir, allow_foreign_arch=args.allow_foreign_arch,
        )
    except BuildError as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    print(f"built {app} ({arch})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
