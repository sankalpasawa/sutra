"""The recorded systems of the page builder (extensions/system.py), kept in the record under scenes.system.
scene(lab) -> {"schema", "systems", "command"}. Every pack loaded here is a scenario file (lab's own pack loader reads them).

  systems  ten systems, in this order: the six demo asks on the catalogue (pack 171_domain_catalogue: a website, an order,
           the enquiry desk, the workflow standard, a newsletter that no domain covers, and words that two domains share
           equally), then the four exhibits (pack 172_domain_exhibits: no plan, a plan that stops at a step, a yes after
           which every step ran and the goal still does not hold, a yes after which the kernel has no plan left). Each is kept as
             folder  the name of the folder the command would write
             files   the text of every file of that folder (index.html is the page; record.json holds every look and run whole)
             looks   {"runs": [...]}: every look and run of record.json once more, as results, in the builder's fixed order
                     (the first look, the runs along the yes path, what each no led to, the look after each no that completed,
                     the last look, the standard's judgement), so the verifier checks each of them like any other run.
                     A system without a domain has no looks: its one look is at a draft the builder made from the words,
                     which is no scenario file. That look is four rows; the independent checks work the draft, the four
                     rows, their hashes and the whole result out again from the words and compare record.json with it.
  command  the command itself, run five times in temporary folders that are removed afterwards. In the first folder: a
           build, the same build again, the same build after a stranger's file was put into its folder (refused), and an
           unknown domain (refused). In a second folder: the same build with a standard output that takes no line (a
           closed pipe), so everything is written and nothing can be reported. Each step keeps the arguments, the exit
           code, what was printed (the folder's path written as <out>) and the SHA-256 of every file then in the folder,
           so the record shows that the command writes the recorded bytes, that a second run changes nothing, that a
           refusal is one line with exit code 2 and writes nothing, and that a write which could not be reported is one
           line with exit code 3."""
import contextlib
import hashlib
import io
import json
import tempfile
from pathlib import Path

LOOKS = 8    # the looks in this sequence (a dict holding a list under runs): the `looks` of each of the eight systems that have a domain
RUNS = 30    # the runs in this sequence (a dict with trace and trace_root_sha256): every look and run of those eight systems' record.json, once more


def counted(v, got=None):
    """The looks and the runs in a part of the sequence, found by their shape wherever they sit."""
    got = got if got is not None else [0, 0]
    if type(v) is dict:
        got[0] += type(v.get('runs')) is list
        got[1] += 'trace' in v and 'trace_root_sha256' in v
        for x in v.values():
            counted(x, got)
    elif type(v) is list:
        for x in v:
            counted(x, got)
    return got


def scene(lab):
    from extensions import system as G
    from extensions import g2
    load = lab['pack']   # tools/run_all.py's loader: a scenario file by name
    catalogue, exhibits = load(g2.CATALOGUE)['domains'], load(g2.EXHIBITS)['domains']
    built = [G.build_system(words, catalogue, load, domain) for words, domain in g2.DEMO] + [G.build_system(row['say'], [row], load, row['id']) for row in exhibits]
    systems = []
    for s in built:
        record = json.loads(s['files']['record.json'])
        systems.append(dict({'folder': s['folder'], 'files': s['files']}, **({} if 'draft' in record else {'looks': {'runs': G.looks(record)}})))

    class Closed(io.StringIO):
        """A standard output that takes nothing, as a pipe whose reader has gone."""
        def write(self, text):
            raise BrokenPipeError(32, 'Broken pipe')

    def step(out, argv, before=None, said=None):
        """One run of the command into `out`: what it was given, how it ended, what it printed, and every file then there."""
        if before:
            before()
        said, complained = said or io.StringIO(), io.StringIO()
        try:
            with contextlib.redirect_stdout(said), contextlib.redirect_stderr(complained):
                code = g2.main(argv + ['--out', str(out)])
        except SystemExit as stop:
            code = stop.code
        lines = lambda text: text.getvalue().replace(str(out), '<out>').splitlines()
        return {'argv': argv + ['--out', '<out>'], 'exit': code, 'stdout': lines(said), 'stderr': lines(complained),
                'written': {p.relative_to(out).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(out.rglob('*')) if p.is_file()}}

    words = g2.DEMO[0][0].split()
    with tempfile.TemporaryDirectory() as t:
        out = Path(t).resolve()
        command = [step(out, words), step(out, words),
                   step(out, words, lambda: (out / built[0]['folder'] / 'notes.txt').write_text('mine', encoding='utf-8')),
                   step(out, ['a', 'site', '--domain', 'nobody-reviewed-this'])]
    with tempfile.TemporaryDirectory() as t:
        command.append(step(Path(t).resolve(), words, said=Closed()))
    made = {'schema': 'core-algorithm/systems-record/3', 'systems': systems, 'command': command}
    if counted(made) != [LOOKS, RUNS]:   # the two numbers this file states are the sequence's own: a change that moves them stops the build until they are stated again
        raise ValueError(f'tools/scenes/system.py states LOOKS = {LOOKS} and RUNS = {RUNS}; the sequence holds {counted(made)}')
    return made
