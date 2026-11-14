"""The page builder's command: give a goal in your words, get a small department folder with its page.

usage, from lab/:
  python3 extensions/g2.py "a website for my organisation"       build one system (the stand-in matcher picks the domain)
  python3 extensions/g2.py "ship the order" --domain order       the caller picks the domain (an agent or a person)
  python3 extensions/g2.py --list                                the domains the catalogue knows
  python3 extensions/g2.py --demo                                the six demo asks and the four exhibits
  ... --out DIR                                                  where to write (default results/built)

Writes <out>/<folder>/index.html (the page), system.json, workflow.json, atoms.json and scaffold.json (or draft-pack.json
when no domain was chosen), record.json (every look and run of the kernel behind the page, whole) and manifest.json (the
SHA-256 of every other file). The folder is named from the ASCII letters and digits of the words plus sixteen characters of the
manifest's digest, so its name stands for the bytes of every file in it. A folder is written into only when everything
it holds is a plain file with the bytes of this very system's file of that name: so one folder never holds the files of
two systems, a link is never written through, and a write that was cut short can be finished by running the command
again. The file names are a closed list; no name from a pack or from the words becomes one. Everything written is
PROPOSED_ONLY: nothing runs outside the local model.

The independent verifier reads nothing this command writes: the systems it checks are in the record
(results/actual_run_records.json, under scenes.system), with every file's text.

How a call ends, always with at most one line on standard error and never with a traceback (a traceback is a defect):
  exit 0   every folder asked for was written, and one line per folder on standard output says where
  exit 2   refused: nothing was written by this call (no words, an unknown domain, a damaged catalogue or pack, a folder
           that holds what is not this system, a place that cannot be a folder)
  exit 3   something was written and the call did not end well: the disk failed while the files were being written
           (the next run finishes the folder or refuses it), or everything was written and the line that says where
           could not be printed (standard output is closed). A character standard output cannot encode is printed as
           an escape, so an ASCII terminal is no reason to fail."""
from __future__ import annotations
from pathlib import Path
import argparse, sys, json
ROOT = Path(__file__).resolve().parents[1]
if __name__ == '__main__':   # run as a script, this file's own folder leads the import path: the lab's root must, and that folder must not
    sys.path[:] = [p for p in sys.path if Path(p or '.').resolve() != ROOT / 'extensions']
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from extensions.system import build_system, catalogue_rows

BUILT = ROOT / 'results' / 'built'      # where a build lands unless --out says otherwise
CATALOGUE, EXHIBITS = '171_domain_catalogue', '172_domain_exhibits'
DEMO = [('a website for my organisation', None), ('complete a customer order when the item is out of stock', None),
        ('answer and store customer enquiries', None), ('check a workflow against the standard', None), ('a weekly newsletter for my donors', None),
        ('order a website', None)]   # the last two build nothing: no domain shares a word with the fifth, and two domains tie on the sixth


def load_pack(name: str) -> dict:
    if type(name) is not str or not name or any(not (ch.isascii() and (ch.isalnum() or ch in '_-')) for ch in name):
        raise ValueError('A pack name is letters, digits, dash and underscore')
    return json.loads((ROOT / 'scenarios' / (name + '.json')).read_text(encoding='utf-8'))


def _domains(name: str) -> list:
    """The rows of a pack that lists domains, refused (ValueError) unless the pack loads and every row is whole."""
    try:
        rows = load_pack(name)['domains']
    except (OSError, LookupError, TypeError, ValueError, RecursionError) as why:
        raise ValueError(f'The pack {name} does not load as a list of domains ({type(why).__name__})') from None
    catalogue_rows(rows)
    return rows


def catalogue() -> list:
    """The closed list of reviewed domains (the pack 171_domain_catalogue, authored in tools/packs/system.py)."""
    return _domains(CATALOGUE)


def exhibits() -> list:
    """Rows that are not in the catalogue: what the builder says when a plan cannot start or does not get there."""
    return _domains(EXHIBITS)


def build(words: str, domain: str | None = None) -> dict:
    return build_system(words, catalogue(), load_pack, domain)


def demo() -> list:
    """The six demo asks on the catalogue, then each exhibit built from its own row with the row's own words."""
    rows = catalogue()
    return [build_system(words, rows, load_pack, domain) for words, domain in DEMO] + [build_system(row['say'], [row], load_pack, row['id']) for row in exhibits()]


def check(system: dict, out) -> Path:
    """The folder <out>/<folder>/ a system would be written into. Refused (ValueError) when it is a link or is not a folder,
    or holds anything that is not a plain file with the bytes of this system's file of that name (.DS_Store, which a file
    browser leaves behind, aside). Reads only: nothing is written here."""
    d = Path(out) / system['folder']
    files = {name: text.encode('utf-8') for name, text in system['files'].items()}
    if d.is_symlink() or (d.exists() and not d.is_dir()):
        raise ValueError(f'{d} is a link or a file, not a folder: nothing was written')
    if d.is_dir():
        for p in sorted(d.iterdir()):
            plain = p.is_file() and not p.is_symlink()
            if plain and p.name == '.DS_Store':
                continue
            if not plain or p.name not in files or p.stat().st_size != len(files[p.name]) or p.read_bytes() != files[p.name]:
                raise ValueError(f'{d} already holds something that is not this system ({p.name}): nothing was written')
    return d


def write(system: dict, out, begun: list | None = None) -> Path:
    """Write the system's files into <out>/<folder>/ and return the folder. Bytes on disk are the bytes that were hashed.
    Refused (ValueError), with nothing written, as `check` refuses. A disk that fails while the files are being written can
    leave some of them behind; they are this system's own bytes or a file cut short, and the next run finishes or refuses.
    `begun`, when given, gets the folder as soon as this call has made anything on the disk (the folder itself, or one above
    it): a caller can tell a refusal, which touched nothing, from a write that failed."""
    d = check(system, out)
    missing = [q for q in [d] + list(d.parents) if not q.exists()]   # the folders this call would have to make
    try:
        d.mkdir(parents=True, exist_ok=True)
    finally:
        if begun is not None and (d.is_dir() or any(q.exists() for q in missing)):
            begun.append(d)
    for name, text in sorted(system['files'].items(), key=lambda item: (item[0] == 'manifest.json', item[0])):   # the manifest last: it names every other file
        (d / name).write_bytes(text.encode('utf-8'))
    return d


def _say(line: str) -> None:
    """One line on standard output, in what that stream can take: a character it cannot encode is written as an escape."""
    encoding = getattr(sys.stdout, 'encoding', None) or 'utf-8'
    print(line.encode(encoding, 'backslashreplace').decode(encoding, 'backslashreplace'))
    sys.stdout.flush()


class _Parser(argparse.ArgumentParser):
    def error(self, message):   # one line and no usage block: a refusal says what was refused
        self.exit(2, f'{self.prog}: error: {" ".join(str(message).split())}\n')

    def after(self, message):   # the call wrote something and did not end well: one line, and another exit code than a refusal's
        self.exit(3, f'{self.prog}: error: {" ".join(str(message).split())}\n')


def main(argv) -> int:
    p = _Parser(prog='g2.py', description='Give a goal in your words, get a small department folder with its page.')
    p.add_argument('words', nargs='*', help='the goal, in your own words')
    p.add_argument('--domain', help='the reviewed domain to build from (see --list); without it a stand-in word matcher picks one')
    p.add_argument('--out', default=None, help='the directory to write into (default results/built)')
    p.add_argument('--list', action='store_true', help='list the domains the catalogue knows')
    p.add_argument('--demo', action='store_true', help='build the six demo asks and the four exhibits')
    args = p.parse_args(argv)
    if (args.list or args.demo) and (args.words or args.domain is not None or (args.list and args.demo)):
        p.error('--list and --demo take no words and no --domain, and not each other')
    try:   # everything that can be refused is found here, before the first byte is written
        rows = catalogue()
        if args.list:
            for d in rows:
                _say(f"{d['id']:<18} {d['title']:<18} say: {d['say']}")
            return 0
        if not args.demo and not args.words:
            p.error('say the goal in words, or use --list or --demo')
        if args.out == '':
            p.error('--out needs a directory')
        out = Path(BUILT if args.out is None else args.out).resolve()
        systems = demo() if args.demo else [build_system(' '.join(args.words), rows, load_pack, args.domain)]
        for s in systems:   # every folder is looked at before the first file is written: a refusal writes nothing, also when several systems were asked for
            check(s, out)
    except (ValueError, OSError, RecursionError) as why:
        p.error(str(why) or type(why).__name__)
    done, begun = [], []
    try:
        for s in systems:
            done.append(write(s, out, begun))
    except (ValueError, OSError) as why:
        if not begun:   # the first folder was looked at once more and refused: the disk was not touched
            p.error(str(why) or type(why).__name__)
        p.after(f'stopped while writing, after {len(done)} of {len(systems)} folders under {out} ({type(why).__name__}: {why}); run the command again to finish or refuse what is there')
    try:
        for s, d in zip(systems, done):
            _say(f"{s['verdict']:<10} {s['asked']}  ->  {d}/index.html")
    except (ValueError, OSError, LookupError) as why:
        p.after(f'{len(done)} of {len(systems)} folders were written under {out}, and the line that says so could not be printed ({type(why).__name__})')
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
