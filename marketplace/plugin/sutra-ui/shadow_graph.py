"""shadow_graph.py -- the Shadow graph and the task detail, derived (PRD amendment A5, A5.2).

Nothing here is stored. `build()` reads the missions, the goals, the conversations, the costs and the departments ONCE each, derives
nodes and edges from the ids they hold, lays them out (deterministic columns and rows), validates the result ONCE as `shadow.graph`
and only then memoises the validated dict for two seconds. A memo hit is returned as it is: neither this module nor the route
validates it again (finding F11). `detail(mid)` does the same for one task as `shadow.task_detail`.

Sources, field by field, are in the table that opens test_shadow_graph_build.py. A field this file reads that main does not write yet
(`executor`, `department_ref`, `department_decision`, P3's) is read tolerantly: absent means no department edge. No import of app."""
import calendar
import os
import re
import threading
import time

import goal_store
import layer_schema
import mission_engine
import shadow_conversations
import shadow_costs
import shadow_ledger

try:                                                  # P3's reader; absent or failing means the missions' own refs are all there is
    import dept_read
except Exception:                                     # noqa: BLE001
    dept_read = None

MEMO_SECONDS = 2.0
MAX_TASKS = 60
RECENT_DAYS = 7
JUST_ENDED = 3600                                     # include_done=0 still shows a task that ended within the hour
MAX_CONVERSATIONS = 20
MAX_TIMELINE = 200
_MID = re.compile(r'^m-[0-9a-f]{12}$')
_GID = re.compile(r'^g-[0-9a-f]{12}$')
_REF = re.compile(r'^[A-Za-z0-9_.-]{1,80}$')
_OPEN = re.compile(r'^[A-Za-z0-9._:-]{1,80}$')

#: mission state -> node status
TASK_STATUS = {'draft': 'draft', 'brief_confirm': 'draft', 'queued': 'waiting', 'running': 'working', 'paused': 'waiting',
               'blocked': 'blocked', 'done': 'done', 'failed': 'failed', 'stopped': 'stopped'}
#: DeptRow.state -> node status (a stopped department is off)
DEPT_STATUS = {'not_started': 'idle', 'working': 'working', 'waiting': 'waiting', 'blocked': 'blocked', 'stopped': 'off', 'done': 'done',
               'idle': 'idle'}
GOAL_STATUS = {'draft': 'draft', 'working': 'working', 'verifying': 'working', 'blocked': 'blocked', 'done': 'done', 'stopped': 'stopped'}
WORDS = {'draft': 'Draft', 'working': 'Working', 'waiting': 'Waiting', 'blocked': 'Blocked', 'done': 'Done', 'failed': 'Failed',
         'stopped': 'Stopped', 'idle': 'Idle', 'off': 'Off'}
HELD_WORDS = {'stopped': 'is Off', 'blocked': 'is blocked', 'founder_rule': 'a rule of yours says so'}

_LOCK = threading.Lock()
_MEMO = {}


def _validate(name, value):
    """The one place a built value is checked (a test counts the calls)."""
    return layer_schema.check(name, value)


# ---------------------------------------------------------------- readers --

def _stamp(ts):
    try:
        return calendar.timegm(time.strptime(str(ts)[:19], '%Y-%m-%dT%H:%M:%S'))
    except (ValueError, TypeError):
        return 0


def _sig(path):
    try:
        st = os.stat(path)
        return (st.st_mtime_ns, st.st_size)
    except OSError:
        return None


def _homes():
    base = os.path.realpath(shadow_ledger.shadow_home())
    return {k: os.path.join(base, k) for k in ('missions', 'conversations', 'goals')}


def _signature():
    """What the memo is keyed by: the missions, goals and conversations directories (a save replaces a file, so the directory moves),
    the cost file, the two ledgers a timeline reads, and the departments' own signature."""
    h = _homes()
    out = [_sig(h['missions']), _sig(h['conversations']), _sig(h['goals']), _sig(os.path.join(os.path.dirname(h['missions']), 'costs.jsonl'))]
    for kind in ('actions', 'missions'):
        try:
            out.append(_sig(shadow_ledger._path(kind)))
        except Exception:                             # noqa: BLE001
            out.append(None)
    out.append(_dept_signature())
    return tuple(out)


def _dept_signature():
    try:
        fn = getattr(dept_read, 'signature', None)
        return fn() if fn else None
    except Exception:                                 # noqa: BLE001
        return None


def _dept_rows():
    """{ref: DeptRow dict} from dept_read (one call), or {} when it is absent or fails."""
    if dept_read is None:
        return {}
    try:
        root = getattr(dept_read, 'root_ref', None)
        rows = dept_read.rows(root() if callable(root) else None)
        rows = rows.get('departments', []) if isinstance(rows, dict) else rows
        return {r['ref']: r for r in rows or [] if isinstance(r, dict) and r.get('ref')}
    except Exception:                                 # noqa: BLE001
        return {}


def _cost_rows():
    try:
        return shadow_costs._rows()
    except Exception:                                 # noqa: BLE001
        return []


def _read_all():
    """One list of each source; a file that does not read is skipped."""
    try:
        missions = mission_engine.MissionStore().list()
    except Exception:                                 # noqa: BLE001
        missions = []
    missions = [m for m in missions if isinstance(m, dict) and _MID.match(str(m.get('id') or '')) and m.get('state') in TASK_STATUS]
    try:
        goals = {g['id']: g for g in goal_store.GoalStore().list() if isinstance(g, dict) and _GID.match(str(g.get('id') or ''))}
    except Exception:                                 # noqa: BLE001
        goals = {}
    try:
        convs = [c for c in shadow_conversations.list_all() if isinstance(c, dict)]
    except Exception:                                 # noqa: BLE001
        convs = []
    try:
        costs = shadow_costs.by_mission()
    except Exception:                                 # noqa: BLE001
        costs = {}
    return missions, goals, convs, costs, _dept_rows()


# ---------------------------------------------------------------- derive --

def _clip(text, n):
    one = ' '.join(str(text or '').split())
    return one if len(one) <= n else one[:n - 1].rstrip() + '…'


def _decision(m):
    """The mission's stored create-or-reuse decision when it fits the interface, else None (a stored record that does not fit is not drawn)."""
    d = m.get('department_decision')
    if not isinstance(d, dict):
        return None
    try:
        return d if not layer_schema.validate('dept.decision', d) else None
    except Exception:                                 # noqa: BLE001
        return None


def _executor(m):
    return 'department' if m.get('executor') == 'department' else 'worker'


def _dept_target(m, dec):
    """(ref, kind, reason, confidence, held) of the department edge, or None. No decision or `none`: no edge, unless the mission names one."""
    if dec is not None:
        act = dec.get('final_action')
        ref = dec.get('final_ref') if act == 'use' else dec.get('result_ref') if act == 'create' else None
        if not ref or not _REF.match(ref):
            return None
        held = bool(dec.get('held'))
        reason = _clip((dec.get('choice') or {}).get('reason'), 300)
        if held:
            notes = '; '.join(o.get('note', '') for o in dec.get('overrides') or [] if o.get('note')) or HELD_WORDS.get(dec.get('held_reason'), 'is held')
            reason = _clip('Held: %s' % notes, 300)
        return ref, ('spawned' if act == 'create' else 'uses'), reason, (dec.get('choice') or {}).get('confidence'), held
    ref = m.get('department_ref')
    if isinstance(ref, str) and _REF.match(ref):
        return ref, 'uses', 'The task was handed to it', None, False
    return None


def _select(missions, include_done, now, focus):
    live = [m for m in missions if m['state'] not in mission_engine.TERMINAL]
    ended = [m for m in missions if m['state'] in mission_engine.TERMINAL]
    horizon = JUST_ENDED if not include_done else RECENT_DAYS * 86400
    ended = [m for m in ended if now - _stamp(m.get('updated_at')) <= horizon]
    key = lambda m: (_stamp(m.get('updated_at')), m.get('created_ns', 0), m['id'])
    live.sort(key=key, reverse=True)
    ended.sort(key=key, reverse=True)
    picked = live + ended
    if focus:
        mine = [m for m in missions if m['id'] == focus]
        return mine, False
    return picked[:MAX_TASKS], len(picked) > MAX_TASKS


def _derive(missions, goals, convs, costs, depts, include_done=False, focus=None, now=None):
    """(graph dict, extras). extras: per drawn task its decision, ref and conversation, for detail()."""
    now = now or int(time.time())
    picked, truncated = _select(missions, include_done, now, focus)
    nodes, edges, extras = {}, {}, {}

    def node(nid, kind, label, status, col, row, open_kind, ref, sub=None, since=None, cost=None, tip=''):
        if nid in nodes:
            return
        ok = open_kind != 'none' and ref and _OPEN.match(str(ref))
        nodes[nid] = {'id': nid, 'kind': kind, 'label': _clip(label, 80) or kind.title(), 'sub': _clip(sub, 120) or None, 'status': status,
                      'col': col, 'row': min(row, 399), 'open': {'kind': open_kind if ok else 'none', 'ref': str(ref) if ok else None},
                      'since': since if since and re.match(r'^\d{4}-\d\d-\d\d', str(since)) else None,
                      'cost_usd': round(cost, 4) if cost else None, 'tip': _clip(tip or WORDS.get(status, ''), 240)}

    def edge(kind, source, target, reason=None, confidence=None, live=False, held=False):
        eid = '%s:%s>%s' % (kind, source, target)
        if eid not in edges and source in nodes and target in nodes:
            edges[eid] = {'id': eid, 'kind': kind, 'source': source, 'target': target, 'reason': reason, 'confidence': confidence,
                          'live': bool(live), 'held': bool(held)}

    task_rows = {}
    for i, m in enumerate(picked):
        task_rows[m['id']] = 0 if focus else 2 * i
    mean = (sum(task_rows.values()) / len(task_rows)) if task_rows else 0
    working = any(m['state'] == 'running' for m in picked)
    node('shadow:now', 'shadow', 'Shadow', 'working' if working else 'idle', 0, int(round(mean)), 'none', None, sub='Now',
         tip='Shadow is working' if working else 'Shadow is idle')

    conv_of = {}
    for c in convs:
        if c.get('mission_id'):
            conv_of.setdefault(c['mission_id'], c)
    dept_users = {}                                    # ref -> [rows], in first-seen order
    dept_edges = []
    for m in picked:
        mid, r = m['id'], task_rows[m['id']]
        status = TASK_STATUS[m['state']]
        tid = 'task:' + mid
        node(tid, 'task', m.get('objective') or 'Untitled task', status, 2, r, 'task', mid, since=m.get('created_at'), cost=costs.get(mid),
             tip=WORDS[status])
        edge('has', 'shadow:now', tid, live=status == 'working')
        on = m['state'] == 'running'
        gid = m.get('goal_id')
        if gid and gid in goals:
            g = goals[gid]
            gs = GOAL_STATUS.get(g.get('state'), 'idle')
            node('goal:' + gid, 'goal', g.get('outcome') or 'A goal', gs, 1, r, 'goal', gid, tip=WORDS[gs])
            edge('attempt', 'goal:' + gid, tid, live=on)
        c = conv_of.get(mid)
        if c and re.match(r'^shc-[0-9a-z]{6,40}$', str(c.get('id'))):
            node('conv:' + c['id'], 'conversation', c.get('title') or 'A conversation', 'idle', 1, r + 1, 'conversation', c['id'],
                 since=c.get('created_at'), tip='A conversation Shadow turned into this task')
            edge('opened', 'conv:' + c['id'], tid)
        if m.get('task_chat_session'):
            node('tchat:' + mid, 'task_chat', 'Task chat', 'working' if on else 'idle', 3, r, 'task', mid, tip='The chat about this task')
            edge('steered_by', tid, 'tchat:' + mid, live=on)
        if m.get('target_session') and _executor(m) == 'worker':
            existing = m.get('target_mode') == 'existing'
            node('worker:' + mid, 'worker', 'Your chat' if existing else 'Worker', 'working' if on else 'idle', 4, r, 'session', m['target_session'],
                 tip='Your own chat does the work' if existing else 'The chat that does the work')
            edge('driven_by', tid, 'worker:' + mid, live=on)
        dec = _decision(m)
        extras[mid] = {'decision': dec, 'conversation': c}
        hit = _dept_target(m, dec)
        if hit:
            dept_users.setdefault(hit[0], []).append(r)
            dept_edges.append((tid, hit, on))

    # a node is two rows tall: a department takes the row nearest the mean of its tasks that is two or more rows from every other
    # node of its column (a task chat sits there too), so no two boxes overlap
    used_rows = {n['row'] for n in nodes.values() if n['col'] == 3}
    for ref, rs in dept_users.items():
        want = int(round(sum(rs) / len(rs)))
        r = next(c for d in range(0, 400) for c in (want + d, want - d) if c >= 0 and all(abs(c - u) >= 2 for u in used_rows))
        used_rows.add(r)
        row = depts.get(ref)
        if row:
            st = DEPT_STATUS.get(row.get('state'), 'idle')
            st = 'off' if row.get('stopped') else st
            node('dept:' + ref, 'department', row.get('name') or ref, st, 3, r, 'dept_page', ref, sub=row.get('kind'), tip=WORDS.get(st, ''))
        else:
            node('dept:' + ref, 'department', ref, 'off', 3, r, 'dept_page', ref, tip='Record not found')
    for tid, (ref, kind, reason, conf, held), on in dept_edges:
        edge(kind, tid, 'dept:' + ref, reason=reason, confidence=conf, live=on and nodes['dept:' + ref]['status'] == 'working', held=held)

    if not focus:
        free = 2 * len(picked)
        for c in [c for c in convs if not c.get('mission_id') and re.match(r'^shc-[0-9a-z]{6,40}$', str(c.get('id')))][:MAX_CONVERSATIONS]:
            node('conv:' + c['id'], 'conversation', c.get('title') or 'A conversation', 'working' if c.get('pending_since') else 'idle', 1, free,
                 'conversation', c['id'], since=c.get('created_at'), tip='A conversation')
            edge('has', 'shadow:now', 'conv:' + c['id'])
            free += 1

    graph = {'nodes': list(nodes.values()), 'edges': list(edges.values()), 'as_of': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime(now)),
             'focus': focus if focus and ('task:' + focus) in nodes else None, 'truncated': bool(truncated), 'shadow_on': True}
    return graph, extras


# ---------------------------------------------------------------- memo ----

def _memo(key, make):
    sig = _signature()
    now = time.monotonic()
    with _LOCK:
        hit = _MEMO.get(key)
        if hit and hit[0] == sig and now - hit[1] < MEMO_SECONDS:
            return hit[2]
    value = make()
    if _signature() != sig:                           # something moved while it was being read (or a store made its directory): not kept
        return value
    with _LOCK:
        if len(_MEMO) > 64:
            _MEMO.clear()
        _MEMO[key] = (sig, now, value)
    return value


def clear():
    """Forget the memo (tests; a write that must show at once)."""
    with _LOCK:
        _MEMO.clear()


def build(focus=None, include_done=False):
    """The ShadowGraph dict, validated once before it is memoised; a hit is returned without another check."""
    focus = focus if isinstance(focus, str) and _MID.match(focus) else None

    def make():
        missions, goals, convs, costs, depts = _read_all()
        if focus and not any(m['id'] == focus for m in missions):
            raise _Unknown(focus)
        graph, _ = _derive(missions, goals, convs, costs, depts, bool(include_done), focus)
        return _validate('shadow.graph', graph)
    try:
        return _memo(('graph', focus, bool(include_done)), make)
    except _Unknown:
        return build(None, include_done)


class _Unknown(Exception):
    pass


# ---------------------------------------------------------------- detail --

_ACTION_KIND = {'decision': ('decided', 'shadow'), 'say': ('said', 'shadow'), 'ask_screen': ('asked', 'shadow'), 'spawn': ('did', 'system')}


def _timeline(m, dec, c):
    rows = [{'at': m.get('created_at') or '0000-00-00', 'kind': 'said', 'by': 'founder', 'text': _clip(m.get('objective'), 300) or 'A task', 'ref': None}]
    for r in shadow_ledger.read_for_mission('missions', m['id'], MAX_TIMELINE):
        word = WORDS.get(TASK_STATUS.get(r.get('state'), ''), '') or str(r.get('state') or '')
        rows.append({'at': r.get('ts'), 'kind': 'state', 'by': 'system', 'text': _clip(r.get('note') or word, 300) or 'A change', 'ref': None})
    for r in shadow_ledger.read_for_mission('actions', m['id'], MAX_TIMELINE):
        kind, by = _ACTION_KIND.get(r.get('kind'), ('did', 'shadow'))
        rows.append({'at': r.get('ts'), 'kind': kind, 'by': by, 'text': _clip(r.get('summary') or r.get('kind'), 300) or 'A step', 'ref': None})
    if dec:
        ref = dec.get('final_ref') or dec.get('result_ref')
        rows.append({'at': dec.get('at'), 'kind': 'department', 'by': 'shadow', 'ref': ('dept:' + ref) if ref and _OPEN.match('dept:' + ref) else None,
                     'text': _clip((dec.get('choice') or {}).get('reason'), 300) or 'Chose a department'})
    rows = [r for r in rows if re.match(r'^\d{4}-\d\d-\d\d', str(r['at'] or ''))]
    rows.sort(key=lambda r: str(r['at']))               # stable: ties keep the order they were gathered in
    return rows[-MAX_TIMELINE:]


def detail(mid):
    """The ShadowTaskDetail dict of one task, validated once, or None when no such task."""
    if not (isinstance(mid, str) and _MID.match(mid)):
        return None

    def make():
        missions, goals, convs, costs, depts = _read_all()
        m = next((x for x in missions if x['id'] == mid), None)
        if m is None:
            raise _Unknown(mid)
        graph, extras = _derive(missions, goals, convs, costs, depts, True, mid)
        dec, conv = extras[mid]['decision'], extras[mid]['conversation']
        drawn = {n['id']: n for n in graph['nodes']}
        departments = [depts[n['id'][5:]] for n in graph['nodes'] if n['kind'] == 'department' and n['id'][5:] in depts]
        chats = []
        if ('tchat:' + mid) in drawn:
            chats.append({'role': 'shadow_chat', 'label': 'Task chat', 'live': m['state'] == 'running', 'open': drawn['tchat:' + mid]['open'],
                          'alt_open': {'kind': 'session', 'ref': m['task_chat_session']} if _OPEN.match(str(m['task_chat_session'])) else None})
        if conv and ('conv:' + conv['id']) in drawn:
            chats.append({'role': 'conversation', 'label': drawn['conv:' + conv['id']]['label'], 'live': False,
                          'open': drawn['conv:' + conv['id']]['open'], 'alt_open': None})
        if ('worker:' + mid) in drawn:
            chats.append({'role': 'worker', 'label': drawn['worker:' + mid]['label'], 'live': m['state'] == 'running',
                          'open': drawn['worker:' + mid]['open'], 'alt_open': None})
        for n in graph['nodes']:
            if n['kind'] == 'department':
                chats.append({'role': 'department_page', 'label': n['label'], 'live': n['status'] == 'working', 'open': n['open'], 'alt_open': None})
        per = {}
        for r in _cost_rows():
            if r.get('mission_id') == mid and r.get('kind') in ('now', 'shadow', 'worker', 'department'):
                line = per.setdefault(r['kind'], [0.0, 0])
                line[0] += float(r.get('usd') or 0)
                line[1] += 1
        costs_out = [{'role': k, 'usd': round(v[0], 6), 'turns': v[1]} for k, v in sorted(per.items())]
        head = {'id': mid, 'objective': _clip(m.get('objective'), 400) or 'Untitled task', 'state': m['state'],
                'template': _clip(m.get('template'), 40), 'executor': _executor(m), 'goal_id': m.get('goal_id') if m.get('goal_id') in goals else None,
                'created': m.get('created_at') or graph['as_of'], 'updated': m.get('updated_at') or graph['as_of'],
                'turns_used': int(m.get('turns_used') or 0)}
        out = {'task': head, 'graph': graph, 'decision': dec, 'departments': departments, 'chats': chats, 'costs': costs_out,
               'total_usd': round(sum(c['usd'] for c in costs_out), 6), 'timeline': _timeline(m, dec, conv), 'as_of': graph['as_of']}
        return _validate('shadow.task_detail', out)
    try:
        return _memo(('detail', mid), make)
    except _Unknown:
        return None
