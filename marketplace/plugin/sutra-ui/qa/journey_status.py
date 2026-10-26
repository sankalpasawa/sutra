#!/usr/bin/env python3
"""qa/journey_status.py -- the status of the user journeys (PRD amendment A3.6): run the tests the journeys list, compute the
state of every row from what passed, and keep one status document per journey (journeys/status/<id>.json).

    --static                  the cases that need no run (JC-1 to JC-7, JC-9 to JC-12); seconds
    --check                   the gate's lane: the static cases, then the run, then the comparison with journeys/status/*.json;
                              exit 1 on a static fault, a failing row, an unproven or fault row in a journey that is not
                              declared, or a status file that is stale (its hash is not its journey's) or differs from what
                              the tests give now
    --check --no-run          the static cases, and the staleness of each status file by hash only; no test is run (the
                              fallback if the full lane would take the gate over its budget)
    --write [id]              the same as --check, then writes the status document of one journey (or of all of them);
                              whoever changes a journey or renames a test a journey lists runs it for that journey

A state is computed from the results and never typed: a row changes state only when a test it lists changes its result, or a
package changes the row. The documents are deterministic: sorted keys, no clock.

The run: the tests the journeys that are not declared list are grouped by file. Each Python file is run once,
`python -m pytest -q -p no:cacheprovider --junitxml <tmp> <ids>`, on a registry of its own as the gate's lane() does; a
parametrised test folds to its name and all its cases must pass. Each node file is run once and its lines are read: `ok   <name>`
or `FAIL <name>`. A listed test that no result mentions is `missing`, and a missing test is a failing row.

The last line is `journeys: <n> rows, <p> proven, <w> wanted, <f> faults`: the rows of the journeys that are not declared, how
many are proven and how many are wanted, and how many problems this run found.
"""
import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent           # the plugin folder
sys.path.insert(0, str(HERE))

#: a test file may take this long to run; past it its tests are missing and the problem is told
TIMEOUT = 1800


def _isolate():
    """Nothing this run imports may touch the owner's records: the registry, the chats, the shadow home and the agent data are
    pointed at folders of their own unless a caller already pointed them somewhere that is not the live home (as conftest.py does)."""
    live = {'SUTRA_NATIVE_HOME': '~/.sutra-native', 'SEO_AGENT_DATA': '~/.sutra-ui/agents/seo', 'SUTRA_UI_CHATS': '~/.sutra-ui/chats',
            'SUTRA_SHADOW_HOME': '~/.sutra-ui/shadow'}
    for name, where in live.items():
        root, current = os.path.realpath(os.path.expanduser(where)), os.environ.get(name, '').strip()
        if current:
            resolved = os.path.realpath(os.path.expanduser(current))
            if resolved != root and not resolved.startswith(root + os.sep):
                continue
        os.environ[name] = tempfile.mkdtemp(prefix='sutra-journeys-%s-' % name.lower())


# ---- what a run gives back -----------------------------------------------------------------------------------------------
def split_refs(refs):
    """The listed tests by file: ({python file: [refs]}, {node file: [refs]})."""
    py, js = {}, {}
    for ref in sorted(set(refs)):
        if ref.startswith('js:'):
            js.setdefault(ref[3:].partition('#')[0], []).append(ref)
        else:
            py.setdefault(ref.partition('::')[0], []).append(ref)
    return py, js


def parse_junit(source, refs):
    """{ref: 'passed' | 'failed' | 'missing'} for the refs of one Python file, from a JUnit file (a path, or its text). A test case
    has a classname (`test_j1`, or `test_engine_runtime.TestTheFiveJourneys`) and a name (a parametrised one ends `[param]`): the
    ref is rebuilt as file.py::[Class::]name with the bracket cut, and the cases of one name are folded: all passed is passed, any
    failure or error is failed. A case that was skipped did not run, and a ref no case mentions is missing."""
    text = source if str(source).lstrip().startswith('<') else Path(source).read_text(encoding='utf-8')
    seen = {}
    for case in ET.fromstring(text).iter('testcase'):
        parts = (case.get('classname') or '').split('.')
        name = re.sub(r'\[.*\]$', '', case.get('name') or '')
        module, klass = parts[0] + '.py', '::'.join(parts[1:])
        ref = '::'.join([module] + ([klass] if klass else []) + [name])
        if case.find('failure') is not None or case.find('error') is not None:
            got = 'failed'
        elif case.find('skipped') is not None:
            got = 'skipped'
        else:
            got = 'passed'
        before = seen.get(ref)
        seen[ref] = 'failed' if 'failed' in (before, got) else 'skipped' if 'skipped' in (before, got) else 'passed'
    return {ref: seen.get(ref) if seen.get(ref) in ('passed', 'failed') else 'missing' for ref in refs}


def parse_node(text, refs):
    """{ref: 'passed' | 'failed' | 'missing'} for the refs `js:file#Wnn` of one node file, from what it printed. A line `ok   <name>`
    passes, and a line `FAIL <name>` fails, every ref whose id begins the name followed by `:` or a space; a ref with no such line
    is missing, and one with a FAIL line is failed whatever else passed."""
    lines = [(line[:4], line[5:].strip()) for line in text.splitlines() if line.startswith(('ok   ', 'FAIL '))]
    out = {}
    for ref in refs:
        wid = ref.partition('#')[2]
        mine = [mark for mark, name in lines if name == wid or name.startswith(wid + ':') or name.startswith(wid + ' ')]
        out[ref] = 'failed' if 'FAIL' in mine else 'passed' if mine else 'missing'
    return out


def run_python(name, refs):
    """One Python test file, run once on a registry of its own: {ref: result}. A ref no test of the file answers to is missing."""
    from journeys import status
    here = [r for r in refs if status.resolve_test(r)]            # pytest stops at a name it cannot find: it is not asked for
    out = {r: 'missing' for r in refs}
    if not here:
        return out
    home, xml = tempfile.mkdtemp(prefix='sutra-journeys-run-'), tempfile.mktemp(prefix='sutra-journeys-', suffix='.xml')
    try:
        env = dict(os.environ, SUTRA_NATIVE_HOME=home)
        cmd = [sys.executable, '-m', 'pytest', '-q', '-p', 'no:cacheprovider', '--junitxml', xml] + here
        try:
            subprocess.run(cmd, cwd=str(HERE), env=env, capture_output=True, timeout=TIMEOUT)
        except subprocess.TimeoutExpired:
            print('%s did not finish in %d seconds: the tests it lists count as missing' % (name, TIMEOUT))
            return out
        if os.path.exists(xml):
            try:
                out.update(parse_junit(xml, here))
            except ET.ParseError:
                print('%s left a result file that cannot be read: the tests it lists count as missing' % name)
    finally:
        shutil.rmtree(home, ignore_errors=True)
        if os.path.exists(xml):
            os.remove(xml)
    return out


def run_node(name, refs):
    """One node test file, run once: {ref: result}."""
    node = shutil.which('node')
    if not node or not (HERE / name).is_file():
        print('%s was not run (%s): the tests it lists count as missing' % (name, 'no node' if not node else 'no such file'))
        return {r: 'missing' for r in refs}
    try:
        done = subprocess.run([node, name], cwd=str(HERE), capture_output=True, text=True, timeout=TIMEOUT)
    except subprocess.TimeoutExpired:
        print('%s did not finish in %d seconds: the tests it lists count as missing' % (name, TIMEOUT))
        return {r: 'missing' for r in refs}
    return parse_node(done.stdout, refs)


def run_tests(refs):
    """Every listed test run, one process per file: {ref: 'passed' | 'failed' | 'missing'}."""
    py, js = split_refs(refs)
    out = {}
    for name, here in py.items():
        out.update(run_python(name, here))
    for name, here in js.items():
        out.update(run_node(name, here))
    return out


# ---- what the run means --------------------------------------------------------------------------------------------------
def disk_docs():
    """The status documents on disk, {id: document}; a file that is not JSON is a document of nothing."""
    import journeys
    out = {}
    for p in sorted((journeys.FOLDER / 'status').glob('*.json')):
        try:
            out[p.stem] = json.loads(p.read_text(encoding='utf-8'))
        except (OSError, ValueError):
            out[p.stem] = None
    return out


def problems(js, docs, on_disk, ran=True):
    """The problems of a run, one sentence each (JC-8, journeys/status.py::case_jc8)."""
    from journeys import status
    return status.case_jc8(js, docs, on_disk, ran)


def summary(js, docs, found):
    """The last line: the rows of the journeys that are not declared, how many are proven and how many wanted, and the problems."""
    rows = [r['state'] for jid, d in docs.items() if not js[jid].get('declared') for r in d['rows'].values()]
    return 'journeys: %d rows, %d proven, %d wanted, %d faults' % (len(rows), rows.count('proven'), rows.count('wanted'), found)


def documents(js, results):
    """The computed document of each journey that is not declared."""
    from journeys import status
    return status.compute_all(js, results)


def states_of(docs):
    """The state of every row of the documents, by row_key: what a `same_as` row of another journey is read from."""
    return {'%s:%s' % (jid, key): row['state'] for jid, doc in docs.items() for key, row in doc['rows'].items()}


def without_run(js, on_disk):
    """What can be said with no test run: each journey's document as its file holds it when the file is whole and its hash is
    the journey's now; any other journey read from its definition alone, a row that lists tests being unknown."""
    import journeys
    from journeys import status
    from layers import S
    docs, states = {}, {}
    for jid, disk in on_disk.items():
        if jid in js and isinstance(disk, dict) and disk.get('definitions_sha') == journeys.sha_of(js[jid]) and not S.validate('journey.status', disk):
            docs[jid] = disk
            states.update(states_of({jid: disk}))
    for jid in sorted(js, key=journeys.natural):
        if jid not in docs:
            got = status.row_states(js[jid], {}, states)
            docs[jid] = {'id': jid, 'definitions_sha': journeys.sha_of(js[jid]), 'rows': {k: {'state': v, 'failing': []} for k, v in got.items()}}
    return docs


def write(doc, journeys_module):
    """One status document, as the runner keeps it: sorted keys, indent 1, a final newline, no clock."""
    folder = journeys_module.FOLDER / 'status'
    folder.mkdir(parents=True, exist_ok=True)
    (folder / (doc['id'] + '.json')).write_text(json.dumps(doc, sort_keys=True, indent=1, ensure_ascii=False) + '\n', encoding='utf-8')


# ---- the modes -----------------------------------------------------------------------------------------------------------
def static_faults():
    """The faults of the static cases over the journeys of the folder, one sentence each, with the case that found it."""
    from journeys import contract
    return ['%s: %s' % (cid, f) for cid, faults in contract.cases().items() for f in faults]


def main(argv=None):
    ap = argparse.ArgumentParser(description='The status of the user journeys.')
    ap.add_argument('--static', action='store_true', help='the cases that need no run')
    ap.add_argument('--check', action='store_true', help='static, then the run, then the comparison with the status files')
    ap.add_argument('--no-run', action='store_true', help='with --check: no test is run; the status files are compared by hash')
    ap.add_argument('--write', nargs='?', const='*', metavar='id', help='check, then write the status file of one journey (or all)')
    args = ap.parse_args(argv)
    if not (args.static or args.check or args.write):
        ap.error('say what to do: --static, --check or --write [id]')
    _isolate()
    import journeys
    from journeys import status
    try:
        js = journeys.load()
    except ValueError as exc:
        print(exc)
        print('journeys: 0 rows, 0 proven, 0 wanted, 1 faults')
        return 1
    if args.write not in (None, '*') and args.write not in js:
        print('no journey %s' % args.write)
        return 2
    found = static_faults()
    for line in found:
        print(line)
    if args.static:
        print('journeys: %d journeys, %d static faults' % (len(js), len(found)))
        return 1 if found else 0
    live, on_disk = {i: j for i, j in js.items() if not j.get('declared')}, disk_docs()
    ran = not (args.check and args.no_run)
    if not ran:
        docs = without_run(live, on_disk)
    elif args.write not in (None, '*'):                          # one journey: its tests are run, the others are as their files hold them
        docs = without_run(live, on_disk)
        if args.write in live:
            states = states_of({i: d for i, d in docs.items() if i != args.write})
            docs[args.write] = status.compute(live[args.write], run_tests(status.tests_listed(live[args.write])), states)
    else:
        docs = documents(js, run_tests(status.tests_listed(live)))
    if args.write is not None:
        if args.write != '*' and args.write not in live:
            print('%s is declared: it has no status to write' % args.write)
        for jid, doc in docs.items():
            if args.write in ('*', jid):
                write(doc, journeys)
        if args.write == '*':
            for orphan in sorted(set(on_disk) - set(live)):
                (journeys.FOLDER / 'status' / (orphan + '.json')).unlink()
                print('removed the status file of %s: no journey has one by that name (a declared journey has none)' % orphan)
        on_disk = disk_docs()
    more = problems(live, docs, on_disk, ran=ran)
    for line in more:
        print(line)
    print(summary(js, docs, len(found) + len(more)))
    return 1 if found or more else 0


if __name__ == '__main__':
    sys.exit(main())
