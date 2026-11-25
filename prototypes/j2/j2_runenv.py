"""The environment a built script runs in: code, never the model, makes it.

A built folder that holds a requirements.txt gets a virtual environment of its own, and the test rerun, the dry run on
copies and the real run all use that environment's python, never the system one. Nothing here asks the Requester:
j2.py asks (RUN <code>) and calls install() only after the approval.

  interpreter()        J2_RUN_PYTHON when it is set, else the first python3.13, 3.12, 3.11 or 3.10 found (on the
                       PATH, then the interpreter this engine itself runs on when it is one of those versions)
  plan(folder)         None without a requirements.txt; else its hash, its packages, the interpreter, the cached
                       environment (ready or not) and what stops it ("problem", or "bad" lines for the builder)
  install(plan, ...)   makes the environment and installs the packages, from PyPI only
  missing_imports(...) the top-level imports of a script that do not resolve with a given python
  tail(text)           the last TAIL characters, what every receipt keeps of stdout and of stderr

Environments are kept by the hash of requirements.txt in the data folder (J2_DATA_DIR, default ~/.j2), outside the
repo and outside runs/. An environment counts only once its record (RECORD) is written, after a clean install.
"""
import ast
import hashlib
import importlib.util
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import sysconfig
import tempfile
import time

TAIL = 2000                                          # characters of stdout and of stderr a receipt keeps
VERSIONS = ("3.13", "3.12", "3.11", "3.10")          # the interpreters looked for, newest first
INDEX = "https://pypi.org/simple"                    # the only place packages come from
PYPI_HOSTS = ("pypi.org", "files.pythonhosted.org")  # what the sandbox lets the install step reach, and nothing else
REQUIREMENTS = "requirements.txt"
RECORD = "j2-env.json"                               # written last: an environment without it is not used
PINNED = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*(\[[A-Za-z0-9._,\s-]+\])?\s*==\s*[A-Za-z0-9][A-Za-z0-9._+!-]*")
_PROBE = "import json, sys; print(json.dumps(['%d.%d.%d' % sys.version_info[:3], sys.base_prefix]))"
_FIND = ("import importlib.util, json, sys; sys.path.insert(0, sys.argv[1]); "
         "print(json.dumps([m for m in sys.argv[2:] if importlib.util.find_spec(m) is None]))")


def tail(text):
    """The end of a command's output, as a receipt keeps it (bytes from a stopped command are decoded)."""
    if isinstance(text, bytes):
        text = text.decode("utf-8", "replace")
    return str(text or "")[-TAIL:]


def data_dir():
    """Where environments are kept: J2_DATA_DIR, else ~/.j2. Never the repo, never a run folder."""
    return os.path.realpath(os.path.expanduser(os.getenv("J2_DATA_DIR") or os.path.join("~", ".j2")))


def is_python(program):
    """True when a runner's program is a python (python, python3, python3.12, a path to one): only then is it swapped
    for the environment's python."""
    return bool(re.fullmatch(r"python[0-9.]*(\.exe)?", os.path.basename(str(program or "")).lower()))


_seen = {}


def describe(python):
    """{"python": its path, "python_version", "base"} of an interpreter (asked once per path), or None when it can't run."""
    path = python if os.path.sep in str(python) else shutil.which(str(python))
    if not path or not os.path.isfile(path):
        return None
    if path not in _seen:
        try:
            p = subprocess.run([path, "-c", _PROBE], capture_output=True, text=True, timeout=30)
            version, base = json.loads(p.stdout.strip().splitlines()[-1])
            _seen[path] = {"python": path, "python_version": version, "base": base}
        except (OSError, ValueError, IndexError, subprocess.TimeoutExpired):
            _seen[path] = None
    return _seen[path]


def interpreter():
    """(what describe() gives, "") for the interpreter environments are made with, or (None, the plain reason)."""
    named = str(os.getenv("J2_RUN_PYTHON") or "").strip()
    if named:
        d = describe(os.path.expanduser(named))
        return (d, "") if d else (None, f"J2_RUN_PYTHON names {named}, which is not a Python that runs")
    for v in VERSIONS:
        if d := describe("python" + v):
            return d, ""
    own = describe(sys.executable) if sys.executable else None      # the interpreter this engine runs on, when it is one of them
    if own and own["python_version"].rsplit(".", 1)[0] in VERSIONS:
        return own, ""
    return None, ("no Python " + ", ".join(VERSIONS[::-1]) + " was found on this computer to make its environment "
                  "(install one, or set J2_RUN_PYTHON to one)")


def packages(text):
    """(packages, bad): the lines of a requirements.txt as "name==version", and the lines code will not install: an
    option (another index, a link, an editable install), a URL or path, or a package without an exact version."""
    good, bad = [], []
    for raw in text.splitlines():
        line = raw.split(" #", 1)[0].strip()
        if not line or line.startswith("#"):
            continue
        if PINNED.fullmatch(line):
            good.append(re.sub(r"\s+", "", line))
        else:
            bad.append(line)
    return good, bad


def env_python(env_dir):
    """The python of an environment folder."""
    return os.path.join(env_dir, "Scripts", "python.exe") if os.name == "nt" else os.path.join(env_dir, "bin", "python")


def plan(folder):
    """None when the built folder has no requirements.txt, or one that names no package (only blank lines and
    comments): nothing to install, so no environment and no question. Else what code needs to know before it asks or runs:
    {"hash" (sha256 of the file), "packages", "bad" (lines for the builder to fix), "requirements" (its path), "dir"
    (the environment's folder), "ready" (installed and recorded), "problem" (why it can't be made: no interpreter,
    bad lines; "" when it can), and, once ready, "python", "python_version", "installed" ({name: version}) and
    "reads" (the folders a sandbox must let it read); before that, "base" (the interpreter it will be made with)}."""
    path = os.path.join(folder, REQUIREMENTS)
    try:
        with open(path, "rb") as f:
            raw = f.read()
    except OSError:
        return None
    digest = hashlib.sha256(raw).hexdigest()
    good, bad = packages(raw.decode("utf-8", "replace"))
    if not good and not bad:
        return None
    env_dir = os.path.join(data_dir(), "envs", digest[:24])
    out = {"hash": digest, "packages": good, "bad": bad, "requirements": path, "dir": env_dir, "ready": False,
           "problem": ""}
    try:
        with open(os.path.join(env_dir, RECORD), encoding="utf-8") as f:
            rec = json.load(f)
    except (OSError, ValueError):
        rec = None
    if rec and rec.get("requirements_sha256") == digest and os.path.isfile(env_python(env_dir)):
        return {**out, "ready": True, "python": env_python(env_dir), "python_version": rec.get("python_version"),
                "installed": rec.get("installed") or {}, "reads": [env_dir] + [x for x in [rec.get("base")] if x]}
    if bad:
        return {**out, "problem": "requirements.txt has lines code will not install: " + "; ".join(bad)}
    base, why = interpreter()
    return {**out, "base": base, "problem": why}


def bad_lines(p):
    """What the builder is told when its requirements.txt can't be installed as written ("" when it can)."""
    if not p or p["ready"] or not p["bad"]:
        return ""
    return ("- refused: requirements.txt may only name packages from PyPI, each with its exact version "
            "(name==1.2.3), one per line; no options, links or paths. Fix: " + "; ".join(p["bad"]))


def facts(p):
    """What a receipt records of a ready environment: the interpreter's path and version, the requirements hash and
    the installed packages with their versions."""
    return {"python": p["python"], "python_version": p.get("python_version"), "requirements_sha256": p["hash"],
            "installed": p.get("installed") or {}}


def install(p, timeout, sandbox=None, env=None):
    """Make the environment of a plan and install its packages, from PyPI only (the index is named, pip's own settings
    and environment variables are ignored). sandbox: the sandbox runtime's command (J2_SANDBOX=1), which then runs the
    install step with the network open to PYPI_HOSTS only and writes only in the environment's folder; making the
    empty environment needs no network and runs as a plain process. The record is written only after a clean install,
    so a failed one is never used; its folder is removed.
    env: the environment variables pip (and a package's own build code) gets; None: this process's own.
    {"ok", "exit", "stdout", "stderr" (tails), "seconds", "command" (the install step), "sandbox" (its settings, or
    None), "evidence", and when ok what facts() gives}."""
    env_dir, base, t0 = p["dir"], p["base"], time.time()
    py = env_python(env_dir)
    cmd = [py, "-m", "pip", "install", "--isolated", "--disable-pip-version-check", "--no-input", "--no-cache-dir",
           "--index-url", INDEX, "-r", p["requirements"]]
    tmp = os.path.join(env_dir, ".tmp")      # pip's working files stay inside the one folder the install may write
    out = {"ok": False, "exit": None, "stdout": "", "stderr": "", "command": cmd, "sandbox": None}
    shutil.rmtree(env_dir, ignore_errors=True)
    os.makedirs(os.path.dirname(env_dir), exist_ok=True)
    conf = None

    def failed(step, proc=None, why=""):
        shutil.rmtree(env_dir, ignore_errors=True)
        if proc is not None:
            out.update(exit=proc.returncode, stdout=tail(proc.stdout), stderr=tail(proc.stderr))
        last = next((x.strip() for x in reversed((out["stderr"] or out["stdout"]).splitlines()) if x.strip()), "no output")
        return {**out, "seconds": round(time.time() - t0, 2),
                "evidence": f"{step} {why or 'exited ' + str(out['exit'])} ({last[:200]})"}
    try:
        made = subprocess.run([base["python"], "-m", "venv", env_dir], capture_output=True, text=True, timeout=timeout)
        if made.returncode != 0 or not os.path.isfile(py):
            return failed("making the environment", made)
        argv = cmd
        if sandbox:
            settings = {"network": {"allowedDomains": list(PYPI_HOSTS), "deniedDomains": []},
                        "filesystem": {"denyRead": ["~"], "allowWrite": [env_dir], "denyWrite": [],
                                       "allowRead": [env_dir, os.path.dirname(p["requirements"]), base["base"]]}}
            fd, conf = tempfile.mkstemp(prefix=".install-", suffix=".json", dir=os.path.dirname(env_dir))
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(settings, f)
            argv, out["sandbox"] = shlex.split(sandbox) + ["-s", conf, "-c", shlex.join(cmd)], settings
        os.makedirs(tmp, exist_ok=True)
        got = subprocess.run(argv, capture_output=True, text=True, timeout=timeout,
                             env={**(os.environ if env is None else env), "TMPDIR": tmp, "TEMP": tmp, "TMP": tmp})
        shutil.rmtree(tmp, ignore_errors=True)
        if got.returncode != 0:
            return failed("installing the packages", got)
        out.update(exit=0, stdout=tail(got.stdout), stderr=tail(got.stderr))
        listed = subprocess.run([py, "-m", "pip", "list", "--isolated", "--disable-pip-version-check", "--format=json"],
                                capture_output=True, text=True, timeout=timeout)
        try:
            installed = {x["name"]: x["version"] for x in json.loads(listed.stdout)}
        except (ValueError, KeyError, TypeError):
            return failed("listing the installed packages", listed)
        rec = {"requirements_sha256": p["hash"], "python_version": base["python_version"], "base": base["base"],
               "made_with": base["python"], "installed": installed, "t": time.strftime("%Y-%m-%dT%H:%M:%S")}
        with open(os.path.join(env_dir, RECORD), "w", encoding="utf-8") as f:
            json.dump(rec, f, indent=1)
        return {**out, "ok": True, "seconds": round(time.time() - t0, 2), "python": py,
                "python_version": base["python_version"], "requirements_sha256": p["hash"], "installed": installed,
                "evidence": f"installed {len(p['packages'])} package(s) from PyPI into {env_dir} "
                            f"(Python {base['python_version']}, {len(installed)} with what they need)"}
    except subprocess.TimeoutExpired as e:
        out.update(stdout=tail(e.stdout), stderr=tail(e.stderr))
        return failed("the install", why=f"ran past {timeout:g}s and was stopped")
    except OSError as e:
        return failed("the install", why=f"could not start: {e}")
    finally:
        if conf:
            os.unlink(conf)


def top_imports(path):
    """The modules a script imports at its top level (statements of the module itself, not ones inside a function, a
    try or an if), by their first name. [] when the file can't be read as Python."""
    try:
        with open(path, encoding="utf-8") as f:
            tree = ast.parse(f.read())
    except (OSError, SyntaxError, ValueError):
        return []
    names = []
    for node in tree.body:
        if isinstance(node, ast.Import):
            names += [a.name.split(".")[0] for a in node.names]
        elif isinstance(node, ast.ImportFrom) and not node.level and node.module:
            names.append(node.module.split(".")[0])
    return list(dict.fromkeys(names))


def in_stdlib(name):
    """A top-level module name is part of the standard library of the Python the engine runs on."""
    names = getattr(sys, "stdlib_module_names", None)      # Python 3.10 and later
    if names is not None:
        return name in names
    if name in sys.builtin_module_names:
        return True
    try:
        origin = getattr(importlib.util.find_spec(name), "origin", None) or ""
    except (ImportError, ValueError):
        return False
    lib = sysconfig.get_paths()["stdlib"]
    return origin in ("built-in", "frozen") or (origin.startswith(lib + os.sep) and "site-packages" not in origin)


def beyond_stdlib(script, folder):
    """The modules a script needs that are neither Python's standard library nor a module of the built folder: its
    top-level imports, and those of the folder's own modules it imports, followed. [] means it runs without any
    installed package. Only read, never imported or run. None when the script can't be read."""
    folder, todo, seen, out = os.path.realpath(folder), [os.path.realpath(script)], set(), []
    if not os.path.isfile(todo[0]):
        return None
    while todo:
        path = todo.pop()
        if path in seen:
            continue
        seen.add(path)
        for name in top_imports(path):
            own = [p for base in (os.path.dirname(path), folder) for p in (os.path.join(base, name + ".py"),
                                                                           os.path.join(base, name, "__init__.py"))
                   if os.path.isfile(p)]
            if own:
                todo.append(os.path.realpath(own[0]))
            elif not in_stdlib(name) and name not in out:
                out.append(name)
    return out


def script_of(command, folder):
    """The built script a command runs: its first argument that is a .py file in the built folder, or None."""
    for x in list(command or [])[1:]:
        p = os.path.join(folder, x)
        if not os.path.isabs(x) and x.endswith(".py") and os.path.isfile(p):
            return p
    return None


def missing_imports(python, script, timeout=60):
    """The top-level imports of a script that do not resolve with this python (the script's own folder counts, so a
    module built beside it resolves). Nothing is imported or run: only looked up. None when the lookup could not run."""
    names = top_imports(script)
    if not names:
        return []
    exe = python if os.path.sep in str(python) else shutil.which(str(python))
    if not exe:
        return None
    try:
        p = subprocess.run([exe, "-c", _FIND, os.path.dirname(os.path.abspath(script))] + names,
                           capture_output=True, text=True, timeout=timeout, cwd=os.path.dirname(os.path.abspath(script)))
        return list(json.loads(p.stdout.strip().splitlines()[-1]))
    except (OSError, ValueError, IndexError, subprocess.TimeoutExpired):
        return None


if __name__ == "__main__":      # python j2_runenv.py <built folder>: what code would do with it, nothing installed
    print(json.dumps(plan(sys.argv[1]) if len(sys.argv) > 1 else interpreter(), indent=1, default=str))
