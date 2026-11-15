"""Classifier adapter (0.15.0-refusals, matrix row R49): a requested action is read by its words and put in classes.

A request is {'kind': 'command' | 'tool' | 'path' | 'host', 'text': '...'}. `classes_of` names the classes of a closed table of
ten it falls in (none for an ordinary action). Each class is read in one kind of request, the way the Sutra charter reads it
(PERMISSIONS.md), by plain string tests: nothing is run, opened or looked up.

  command  by its words, any of them (Trust Mode, Tier 1.6, reads the leading one): rewriting git history, a recursive delete
           outside the build folders, disks and system services, remote and shared systems, another user. A command that is
           not made of plain words (a quote, a substitution, a combinator, a redirection, a glob, a control character) is
           itself a class, `unreadable_command`. A command is NOT read for the paths or addresses among its words.
  tool     by the words of its name (Tier 1.7): a delete-class verb, a bulk change.
  path     by its parts (Tier 3): a credential store. A path that carries a wildcard or a variable names no one place and is
           refused as a request (ValueError), like any request of the wrong shape.
  host     by its form (Tier 1.9), the other way round: a host is public only when it is a plain http(s) URL (scheme, two
           slashes, a host, an optional port, a path; no user part, no backslash) whose host is a public address written as
           four plain numbers or in brackets, or a dotted name that ends in a word not kept for local use. Everything else
           (another scheme, a bare host, a private, loopback, link-local, multicast or reserved address, a number in any
           other form, a single word, a local name) is in `private_host`.

The kernel never sees a request. A step that carries one is authored through this module: `screened(step, request)` is one
verified evidence row, named by the step AND the digest of the request, and `prerequisites(step, request)` are the facts the
step must require: that row, and `may:<class>` for each of its classes. Only the row of exactly that request satisfies the
step: the reading of another request is another fact. What a department refuses is then pack content, per class and not per
request: a decision (a final FALSE row) on `may:<class>` refuses, an ordinary TRUE row permits, a step of kind `ask` asks.

Two authoring-time audits, both lists that are empty when all is in order. `unscreened(pack)` names every step whose request,
screening row and prerequisites do not agree. `unruled(packs)` names the classes of the table a department's packs do not rule
on. The second matters because the kernel reads a step's prerequisites in order and stops at the first that yields no plan: a
class nobody ruled on (no row on its permission, no rule and no step for it), read before a refused one, names the look
QUERY_EVIDENCE and the refusal is never read (nothing runs either way). With every class ruled, a refused class names the look
REFUSED whatever else the step is in."""
from __future__ import annotations
import ipaddress, re, unicodedata
from kernel.core import State, digest
import extensions.asks   # the action kind `ask`: registered, so `unruled` can fold a pack that rules by a question

SOURCE = 'adapter:refusals/classes@1'
KINDS = ('command', 'tool', 'path', 'host')
PLAIN = re.compile(r'[A-Za-z0-9 _./=:@,%~-]+')   # a command made of plain words: these characters and nothing else
SAFE_TREE = re.compile(r'(\./|/tmp/)?(dist|build|out|\.next|node_modules|\.cache|cache|tmp|\.tmp|coverage|target|\.turbo|\.parcel-cache|\.pytest_cache|__pycache__)/?')
ESCALATORS = {'sudo', 'su', 'doas', 'pkexec'}
REMOTES = {'ssh', 'scp', 'sftp', 'rsync', 'aws', 'gcloud', 'vercel', 'supabase', 'doctl', 'fly', 'heroku', 'kubectl', 'helm', 'ansible', 'terraform', 'pulumi',
           'render', 'railway', 'netlify', 'psql', 'mysql', 'mongo', 'mongosh', 'redis-cli', 'sqlite3', 'duckdb'}
PUBLISHERS = {'npm', 'yarn', 'pnpm', 'bun'}
UPLOADERS = {'pip', 'twine', 'poetry'}
SYSTEM = {'dd', 'diskutil', 'launchctl', 'defaults', 'fdisk', 'parted', 'mount', 'umount', 'kextload', 'kextunload'}
DESTROYERS = {'delete', 'destroy', 'drop', 'purge', 'wipe', 'truncate', 'eradicate', 'expunge', 'uninstall', 'deauthorize', 'trash'}
STORES = {'.ssh', '.aws', '.gnupg', 'keychains'}
KEYCHAINS = ('.keychain', '.keychain-db')
WILD = re.compile(r'[*?\[\]{}$`]')   # in a path: a wildcard or a variable
URL = re.compile(r'https?://(\[[0-9a-f:.]+\]|[a-z0-9.-]+)(:[0-9]{1,5})?([/?#].*)?', re.I | re.S)
LABEL = re.compile(r'[a-z0-9]([a-z0-9-]*[a-z0-9])?')
LOCAL_NAMES = {'localhost', 'localdomain', 'local', 'internal', 'intranet', 'lan', 'home', 'corp'}   # last labels kept for local use, by a standard or by custom
NETS4 = [ipaddress.ip_network(n) for n in (   # IPv4 that is not public: this network, private, shared, loopback, link-local, protocol and documentation ranges, benchmarking, multicast, reserved
    '0.0.0.0/8', '10.0.0.0/8', '100.64.0.0/10', '127.0.0.0/8', '169.254.0.0/16', '172.16.0.0/12', '192.0.0.0/24', '192.0.2.0/24', '192.168.0.0/16',
    '198.18.0.0/15', '198.51.100.0/24', '203.0.113.0/24', '224.0.0.0/4', '240.0.0.0/4')]
GLOBAL6 = ipaddress.ip_network('2000::/3')   # IPv6 is public only in here (global unicast), and not in the four ranges below
NOT6 = [ipaddress.ip_network(n) for n in ('2001::/23', '2001:db8::/32', '2002::/16', '3fff::/20')]   # protocol assignments (Teredo carries an IPv4 address), documentation, 6to4 (carries an IPv4 address), documentation


def _tokens(text):   # the words of a command, also of one that is not plain: whatever stands between its words only separates them
    return [t for t in re.split(r'[^A-Za-z0-9_./=:@,%~+-]+', text) if t]


def _words(text):   # each word without its directory and without a leading = (a shell may read =sudo as sudo), in lower case (a file system may not tell SUDO from sudo)
    return [t.split('/')[-1].lstrip('=').lower() for t in _tokens(text)]


def _flag(text, letters, long):   # a short flag (-rf, -fd) that carries one of the letters, or a long flag that begins like `long` (a program may take a long flag cut short)
    return any(t.startswith(long) if t.startswith('--') else t.startswith('-') and set(t[1:]) & set(letters) for t in _tokens(text))


def _history_rewrite(text):
    words = _words(text)
    return 'git' in words and _flag(text, 'f', '--forc') and ('push' in words or 'clean' in words)


def _recursive_delete(text):
    tokens, words = _tokens(text), _words(text)
    if 'rm' not in words or not _flag(text, 'rR', '--r'):
        return False
    paths = [p for p in tokens[words.index('rm') + 1:] if not p.startswith('-')]
    return not paths or not all(SAFE_TREE.fullmatch(p) for p in paths)   # the build folders may go; anything else, or nothing named, is in the class


def _disk_or_system(text):
    words = set(_words(text))
    return bool(words & SYSTEM or any(w.startswith('mkfs') for w in words)
                or (words & {'chmod', 'chown'} and _flag(text, 'R', '--rec')))


def _remote_mutation(text):
    words = set(_words(text))
    return bool(words & REMOTES or (words & PUBLISHERS and 'publish' in words) or ('docker' in words and words & {'push', 'login'})
                or (words & UPLOADERS and words & {'upload', 'publish'}))


def _names(text):   # the words of a tool's name: snake_case, kebab-case, dotted or camelCase
    return {n.lower() for n in re.findall(r'[A-Z]+(?![a-z])|[A-Z]?[a-z]+', text)}


def _bulk_tool(text):
    names = _names(text)
    return bool(names & {'bulk', 'mass'} or ('batch' in names and names & {'modify', 'delete'}) or {'apply', 'labels'} <= names)


def _credential_path(path):   # a path with a part that is a credential store; letters are folded as a file system that ignores case folds them, and dots and spaces at the end of a part are dropped as some file systems drop them
    parts = [unicodedata.normalize('NFKC', p).casefold().strip().rstrip('. ') for p in re.split(r'[/\\]+', path)]
    return any(p in STORES or p.endswith(KEYCHAINS) for p in parts)


def _private_host(text):   # True unless the text is a plain http(s) URL to a public address or to a dotted name that ends in a word not kept for local use
    found = URL.fullmatch(text)
    if found is None or '\\' in text:
        return True   # no scheme, another scheme, one slash, a user part, a backslash, nothing where the host should be, or something after the colon that is not a port
    host = found.group(1).lower()
    if host.startswith('['):
        try:
            address = ipaddress.IPv6Address(host[1:-1])
        except ValueError:
            return True
        return address not in GLOBAL6 or any(address in net for net in NOT6)
    labels = host.split('.')
    if not all(LABEL.fullmatch(label) for label in labels):
        return True   # an empty part (a dot at an end, two dots) or a hyphen at an end of a part
    if all(label.isdigit() for label in labels):
        if len(labels) != 4 or any((len(label) > 1 and label[0] == '0') or int(label) > 255 for label in labels):
            return True   # a number that is not four plain parts (127.1, 2130706433, 010.0.0.1): some programs read it as an address
        address = ipaddress.IPv4Address('.'.join(labels))
        return any(address in net for net in NETS4)
    return len(labels) < 2 or not labels[-1].isalpha() or labels[-1] in LOCAL_NAMES   # a name: one word alone, a last part that is not a word (0x7f.0.0.1), a name kept for local use


CLASSES = {   # class: (the kind of request it is read in, what is in it, the test). The order here is the order a step's prerequisites are read in.
    'history_rewrite': ('command', 'rewrites or discards shared git history (git push --force, git clean -f)', _history_rewrite),
    'recursive_delete': ('command', 'deletes a tree outside the build folders (rm -r)', _recursive_delete),
    'disk_or_system': ('command', 'touches disks, mounts or system services (dd, mkfs, mount, launchctl, chmod -R)', _disk_or_system),
    'remote_mutation': ('command', 'changes a remote or shared system (ssh, rsync, kubectl, psql, a publish)', _remote_mutation),
    'privilege_escalation': ('command', 'runs as another user (sudo, su, doas, pkexec)', lambda text: bool(set(_words(text)) & ESCALATORS)),
    'unreadable_command': ('command', 'is not made of plain words (a quote, a substitution, a combinator, a redirection, a glob, a control character)',
                           lambda text: PLAIN.fullmatch(text) is None),
    'destructive_tool': ('tool', 'a tool named with a delete-class verb (delete, drop, purge, trash)', lambda text: bool(_names(text) & DESTROYERS)),
    'bulk_tool': ('tool', 'a tool that changes many records at once (bulk, mass, batch modify)', _bulk_tool),
    'credential_path': ('path', 'a path inside a credential store (.ssh, .aws, .gnupg, a keychain)', _credential_path),
    'private_host': ('host', 'anything but a plain http(s) URL to a public address or name (loopback, private, link-local, multicast and reserved ranges, a local name, another scheme)', _private_host),
}


def _checked(request):
    if (type(request) is not dict or set(request) != {'kind', 'text'} or type(request['kind']) is not str or request['kind'] not in KINDS
            or type(request['text']) is not str or not request['text'].strip() or len(request['text']) > 2000):
        raise ValueError('A request is {kind: command, tool, path or host; text: what is asked}, at most 2000 characters')
    kind, text = request['kind'], request['text']
    if kind == 'tool' and not re.fullmatch(r'[A-Za-z0-9_.:/-]+', text):
        raise ValueError('A tool is named by letters, digits and _ . : / -')
    if kind == 'host' and not re.fullmatch(r'[\x21-\x7e]+', text):
        raise ValueError('A host or an address is printable text without spaces')
    if kind == 'path' and (re.search(r'[\x00-\x1f\x7f]', text) or WILD.search(text)):
        raise ValueError('A path names one place: no control character, no wildcard, no variable')
    return kind, text


def classes_of(request: dict) -> list[str]:
    """The classes of the table a request falls in, in the table's order; [] for an ordinary action. A request of the wrong shape is refused (ValueError)."""
    kind, text = _checked(request)
    return [name for name, (read_in, _, test) in CLASSES.items() if kind == read_in and test(text)]


def _named(step, request):
    classes = classes_of(request)   # the request is checked first: one of the wrong shape gets no name and no row
    if type(step) is not str or not step:
        raise ValueError('A step is named')
    return f'screened:{step}@req-{digest(request)[:12]}', classes


def screened(step: str, request: dict) -> dict:
    """The evidence row of one screened step: verified, from this adapter, named and versioned by the digest of the request, carrying its classes."""
    name, classes = _named(step, request)
    return {'predicate': name, 'truth': 'TRUE', 'verified': True, 'source': SOURCE, 'version': 'req-' + digest(request)[:12], 'request': dict(request), 'classes': classes}


def prerequisites(step: str, request: dict) -> list[str]:
    """What a step that carries this request must require: the screening row of exactly this request, then the permission of each of its classes."""
    name, classes = _named(step, request)
    return [name] + ['may:' + c for c in classes]


def unscreened(pack: dict, every: bool = False) -> list[str]:
    """The authoring-time audit of one pack: a sentence for every step that carries a request and whose screening row or
    prerequisites are not what this adapter reads in that request; [] when every such step is in order. With `every`, a step
    that carries no request is named too (a question to a person aside): for a pack in which nothing may run unread."""
    if type(pack) is not dict or type(pack.get('methods', [])) is not list or type(pack.get('evidence', [])) is not list:
        raise ValueError('A pack holds its methods and its evidence in lists')
    rows = {r['predicate']: r for r in pack.get('evidence', []) if isinstance(r, dict) and type(r.get('predicate')) is str}   # a row without a name is no screening row
    found = []
    for m in pack.get('methods', []):
        if not isinstance(m, dict):
            found.append('a method that is not an object cannot be read')
            continue
        mid = m.get('id')
        if 'request' not in m:
            if every and m.get('action') != 'ask':
                found.append(f'{mid}: it carries no request, so nothing was screened')
            continue
        try:
            want, needs = screened(mid, m['request']), prerequisites(mid, m['request'])
        except ValueError as e:
            found.append(f'{mid}: its request cannot be read ({e})')
            continue
        requires = m['requires'] if type(m.get('requires')) is list else []
        if rows.get(want['predicate']) != want:
            found.append(f"{mid}: the pack does not carry the screening row of its request ({'no row of that name' if want['predicate'] not in rows else 'another request, version or list of classes'})")
        missing = [p for p in needs if p not in requires]
        if missing:
            found.append(f"{mid}: its prerequisites leave out {', '.join(missing)}")
        other = [p for p in requires if type(p) is str and p.startswith('screened:') and p != want['predicate']]
        if other:
            found.append(f"{mid}: it requires the screening of another request ({', '.join(other)})")
    return found


def unruled(packs) -> list[str]:
    """The authoring-time audit of a department's rulings: the classes of the table, in its order, on which these packs (one,
    or a list in load order) carry no ruling; [] when every class is ruled. A ruling on may:<class> is a decision (a final
    TRUE or FALSE row), an ordinary TRUE row that reads, or a question (an approved step of kind ask). An ordinary FALSE row
    and a rule are not rulings: the first is no refusal, the second no evidence (a step planned on a rule's head stops at its
    own gate, which reads stored rows). The packs are folded with the kernel's own State, so what stands after them is what
    the kernel would read."""
    packs = [packs] if type(packs) is dict else packs
    if type(packs) is not list:
        raise ValueError('The packs are one pack or a list of packs, in load order')
    try:
        s = State.from_packs(packs)
    except ValueError as e:
        raise ValueError(f'The kernel refuses these packs: {e}') from None
    asked = {m['effect'] for m in s.methods.values() if m.get('action') == 'ask' and m.get('approved', True)}
    return [c for c in CLASSES if not (s.evidence.get(s.key('may:' + c), {}).get('final') or s.fact('may:' + c)['truth'] == 'TRUE' or 'may:' + c in asked)]
