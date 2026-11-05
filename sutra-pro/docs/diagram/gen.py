import html, json, pathlib, re
E = html.escape
out = []
_stack = []                          # y shifts of the open <g transform="translate(0,N)"> groups
def a(s):
    out.append(s)
    m = re.match(r'<g transform="translate\(0,(-?[\d.]+)\)">', s)
    if m: _stack.append(float(m.group(1)))
    elif s == '</g>': _stack.pop()
ANCH = {}                            # box name -> (x, y, w, h) in figure coordinates, filled while drawing
def anchor(name, x, y, w, h): ANCH[name] = (x, y + sum(_stack), w, h)

def box(x, y, w, h, cls, title, lines, tcls="t-b", bar=None, dash=False, lh=16.5, ty=22, ly=43, lcls="t-s"):
    anchor(title, x, y, w, h)
    a(f'<rect class="bx {cls}{" dashed" if dash else ""}" x="{x}" y="{y}" width="{w}" height="{h}" rx="9"/>')
    if bar: a(f'<rect class="{bar}" x="{x}" y="{y}" width="{w}" height="5" rx="2.5"/>')
    a(f'<text class="{tcls}" x="{x+14}" y="{y+ty}">{E(title)}</text>')
    for i, l in enumerate(lines):
        a(f'<text class="{lcls}" x="{x+14}" y="{y+ly+i*lh}">{E(l)}</text>')

def line(d, cls="edge", marker="ah", dash=False, both=False):
    m = f' marker-end="url(#{marker})"' if marker else ""
    s = f' marker-start="url(#{marker})"' if both else ""
    a(f'<path class="{cls}{" dashed" if dash else ""}" d="{d}"{m}{s}/>')

def badge(cx, cy, n):
    a(f'<circle class="badge" cx="{cx}" cy="{cy}" r="9.5"/><text class="t-badge" x="{cx}" y="{cy+4}" text-anchor="middle">{n}</text>')

def label(x, y, s, anchor="start", rot=None, cls="t-e"):
    r = f' transform="rotate({rot} {x} {y})"' if rot is not None else ""
    a(f'<text class="{cls}" x="{x}" y="{y}" text-anchor="{anchor}"{r}>{E(s)}</text>')

def band(y0, y1, name, cls="band"):
    anchor("band:" + name.split(" (")[0], 44, y0, 976, y1 - y0)
    a(f'<rect class="{cls}" x="44" y="{y0}" width="976" height="{y1-y0}" rx="12"/>')
    label(62, (y0 + y1) / 2, name, anchor="middle", rot=-90, cls="t-band")

def node(cx, y, w, h, txt, cls="node", tcls="t-n"):
    a(f'<rect class="{cls}" x="{cx-w/2:g}" y="{y}" width="{w}" height="{h}" rx="6"/>'
      f'<text class="{tcls}" x="{cx}" y="{y+h/2+4:g}" text-anchor="middle">{E(txt)}</text>')

# The orchestration row is taller than before so the one global org chart has room.
# Everything under it is drawn in a group moved down by DY, so its own coordinates stay as they were.
OT, CH = 250, 224            # top and height of the three orchestration boxes
OB = OT + CH                 # their bottom edge
DY = OB + 10 - 425           # shift for the bands below
EXC = 92                     # extra height of each function card (FH = 105 + EXC)
GAP = 10                     # gap between the cards and the lifecycle strip
STRIP = 46                   # height of the "inside every node" strip
EX = EXC + GAP + STRIP       # everything under the strip moves down by this (148; budget 160)
FH = 105 + EXC               # height of a function card (197)
LOW = f'<g transform="translate(0,{DY})">'
XP = 90                      # v6: the Experience band gains a second row for the Console page; everything under it moves down by this
SH = 60                      # v6: the connector band gains the stub box; the providers band moves down by this
OPX = 94                     # v6: the Operator box sits under the chat-flow key, in the server column
KEYH = 366                   # height of the decisions key under the figure (97 entries in 4 columns of 25 rows)
W, H0 = 1300, 1140 + DY + EX + XP + OPX
H = H0 + 8 + KEYH + 10
a(f'<svg viewBox="0 0 {W} {H}" xmlns="http://www.w3.org/2000/svg" role="img" aria-label="Sutra app architecture: the user chat interface and its Simple and Detailed J2 views and the Console page sit on a chat agent that, for every task, checks the one global org chart and reuses, adds to or rearranges it as the need arises, and hands the task to the Identity node of the department; the agent references the Python interface library and builds workflows and a graph through a connector layer; the department runtime runs the five J2 functions as agentic graph nodes, five per department, each with its own chat session and its own goal, task, context, work atom, verify and constraints, where every turn of a node is one work atom that opens, works, closes through a check run by code, or is refused or abandoned, and whose events update the workflow graph and the chat sessions and are kept in an append-only atom log; a connector router, which records cost per atom, picks between a Claude connector and a Codex connector, both children of a ModelConnector base class; server state holds the workflow graph with atoms per node, chat sessions, department records including the global org chart, the atom log, artifacts, the template library and a cost ledger; an Operator box lists the sutra-pro commands, and a stub connector with a demo reply book serves the offline mode.">')
a('<defs>'
  '<marker id="ah" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse"><path d="M0,0 L10,5 L0,10 z" fill="currentColor"/></marker>'
  '<marker id="inh" viewBox="0 0 12 12" refX="11" refY="6" markerWidth="11" markerHeight="11" orient="auto"><path d="M1,1 L11,6 L1,11 z" fill="var(--card)" stroke="currentColor" stroke-width="1.3"/></marker>'
  '</defs>')

# band backgrounds and labels (the three lower bands are drawn further down, inside the moved group)
band(30, 200 + XP, "EXPERIENCE")

# ---------- Experience
box(150, 40, 400, 150, "card", "User chat interface · J2 Simple view", [
    "Chat with your team; Identity is the one voice",
    "Progress bar · live preview · example briefs",
    "Questions arrive as cards: options or your answer",
    "Ready card: open · download · ask for a change"])
box(570, 40, 440, 150, "card", "Detailed view · J2 left rail", [
    "Sections, Needs-you badge, light / dark / system",
    "Map views: Tree · Line · Solar system · Constellation",
    "Goal · Charter · Workflows · Priorities · Timeline",
    "Board · Story · Audit · Documents · Artifacts",
    "Library · Lessons · Playbooks · Report · Run details",
    "Agent drawer: who each agent talked to, why, atom cards"], lh=16)
box(1040, 40, 210, 150, "card hot", "Workflow graph view", [
    "nodes: departments, divisions,",
    "steps, and each department's",
    "5 function nodes, atom counts",
    "follows the global org chart",
    "click a node: its chat",
    "updates as agents work"])
# v6: the third page, /console (sutra_app/ui/pages/console.html); sits between the two arrows that leave the row above
box(392, 204, 320, 76, "card", "Console", [
    "usage and cost", "Atom log", "health and diagnostics"], ty=20, ly=38, lh=14.5)

# everything from the orchestration row down moves by XP (the Experience band grew a row)
a(f'<g transform="translate(0,{XP})">')
band(240, OB + 10, "ORCHESTRATION")
# ---------- Orchestration
box(150, OT, 250, CH, "card hot", "Chat agent (orchestrator)", [
    "for every task it:",
    "· reads the global org chart",
    "· reuses, adds or rearranges",
    "  nodes as the need arises",
    "· references the model library",
    "· builds workflows + graph via",
    "  the connector layer",
    "· hands the task to the",
    "  department's Identity",
    "· links each node to its chat",
    "· keeps the graph up to date"], lh=16)

# the one global org chart: a single tree that every task can reuse, add to or rearrange
CX0, CW = 430, 286
a(f'<rect class="bx card hot" x="{CX0}" y="{OT}" width="{CW}" height="{CH}" rx="9"/>')
anchor("One global org chart", CX0, OT, CW, CH)
a(f'<text class="t-b" x="{CX0+14}" y="{OT+22}">One global org chart<tspan class="t-e" font-weight="400" dx="7">· example</tspan></text>')
a(f'<text class="t-e" x="{CX0+14}" y="{OT+38}">grows and reshapes with each task, on need</text>')
RX, S1, S2 = 573, 503, 643                       # root and the two department centres
node(RX, 298, 64, 20, "Root", "node root")
a(f'<path class="edge thin" d="M{RX},318 V325 H{S1} V332 M{RX},325 H{S2} V332" marker-end="none"/>')
node(S1, 332, 84, 22, "Sales"); node(S2, 332, 84, 22, "Support")
a(f'<path class="edge thin" d="M{S1},354 V361 H472 V368 M{S1},361 H534 V368 M{S2},354 V361 H612 V368 M{S2},361 H674 V368" marker-end="none"/>')
node(472, 368, 54, 20, "Leads", "node", "t-n sm")
node(534, 368, 54, 20, "+ Quotes", "node add", "t-n sm")
node(612, 368, 54, 20, "Tickets", "node", "t-n sm")
node(674, 368, 54, 20, "Returns", "node mv", "t-n sm")
label(534, 401, "added by task N", anchor="middle", cls="t-tag")
label(702, 401, "moved by task N", anchor="end", cls="t-tag")
for i, (cls, nm, d) in enumerate((("node", "Reuse", "need fits existing nodes"),
                                  ("node add", "Add", "no node yet: add one"),
                                  ("node mv", "Rearrange", "move, merge or split nodes"))):
    y = 426 + i * 16
    a(f'<rect class="{cls}" x="{CX0+14}" y="{y-10}" width="26" height="11" rx="3"/>')
    label(CX0 + 50, y, nm, cls="t-n")
    label(CX0 + 116, y, d, cls="t-e")
badge(CX0 + CW - 16, OT + 16, "7")

box(740, OT, 270, CH, "card hot", "Interface library (Python models)", [
    "FunctionNode (base), children <X>Node:",
    "Identity · Adaptation · Priority",
    "Coordination · Audit",
    "Atom (base): goal, constraints,",
    "context, work, verify, state",
    "AtomView: J2 atom/1 (for builders)",
    "Departments · Goal · Evaluation",
    "Org chart · Chart change",
    "Also base: Workflow · Step · Template",
    "Artifact models + rules as data",
    "closed models, checked at every write,",
    "including every org chart change"], lh=15.5, ly=41)

# ---------- Server panel, top part (stays beside the orchestration row)
a(f'<rect class="band" x="1030" y="238" width="232" height="{696 + DY + EX}" rx="12"/>')
anchor("Server contents", 1030, 238, 232, 696 + DY + EX)
box(1042, 250, 208, 102, "card hot", "Workflow graph store", ["nodes ↔ chat session ids", "atoms filed under each node", "edges · status · versions", "nodes mirror the org chart"], ty=21, ly=40)
box(1042, 362, 208, 102, "card hot", "Chat sessions", ["one per node, Claude or Codex", "session id, transcript, cards", "only Identity speaks to you", "a moved node keeps its chat"], ty=21, ly=40)

# ---------- Everything below the orchestration row (moved down by DY)
a(LOW)
band(460, 796 + EX, "DEPARTMENT RUNTIME (J2 ENGINE · 5 NODES PER DEPARTMENT)")

# ---------- Runtime
fx = [150, 324, 498, 672, 846]
Y0 = 475                                                       # top of the cards (LOW coordinates)
anchor("five function cards", 150, Y0, 860, FH)
FN = [("Identity", "f-id", "Client Lead · J2.a·d·h",
       [("GOAL", "aligned with the charter"), ("TASK", "charter · rulings · done"),
        ("CONTEXT", "charter, chat; no money"), ("WORK ATOM YIELDS", "charter, rule, question"),
        ("VERIFY", "charter stamp + workable"), ("CONSTRAINTS", "the only voice to you")]),
      ("Adaptation", "f-ad", "Strategist · J2.b",
       [("GOAL", "smallest useful change"), ("TASK", "certainty, plan, propose"),
        ("CONTEXT", "charter, record, lessons"), ("WORK ATOM YIELDS", "proposal with its checks"),
        ("VERIFY", "atom rules; plan ≥ 0.80"), ("CONSTRAINTS", "never approves its plan")]),
      ("Priority", "f-pr", "Prioritiser · J2.c·f",
       [("GOAL", "envelope for each plan"), ("TASK", "price, check run limits"),
        ("CONTEXT", "plan, budget, spend"), ("WORK ATOM YIELDS", "GRANT, COUNTER, REFUSE"),
        ("VERIFY", "limit set, within budget"), ("CONSTRAINTS", "prices, never orders")]),
      ("Coordination", "f-co", "Scheduler · J2.f",
       [("GOAL", "right order, no clashes"), ("TASK", "schedule, hold, lock"),
        ("CONTEXT", "registered, deps, locks"), ("WORK ATOM YIELDS", "rule, order, holds"),
        ("VERIFY", "only registered ids run"), ("CONSTRAINTS", "never raises an envelope")]),
      ("Audit", "f-au", "Quality Reviewer · J2.g",
       [("GOAL", "verdict backed by proof"), ("TASK", "check the real result"),
        ("CONTEXT", "charter + real result"), ("WORK ATOM YIELDS", "one finding per item"),
        ("VERIFY", "PASS only with proof"), ("CONSTRAINTS", "never audits own work")])]
for x, (nm, c, tag, rows) in zip(fx, FN):
    a(f'<rect class="bx card {c}b" x="{x}" y="{Y0}" width="164" height="{FH}" rx="9"/><rect class="{c}" x="{x}" y="{Y0}" width="164" height="5" rx="2.5"/>')
    a(f'<rect class="bx {c}b mark" x="{x+10}" y="{Y0+16}" width="20" height="10" rx="5"/>')            # the J2 map chip: a function node
    a(f'<text class="t-b {c}t" x="{x+37}" y="{Y0+26}">{nm}</text>')
    a(f'<circle class="badge" cx="{x+149}" cy="{Y0+21}" r="8"/><text class="t-badge" x="{x+149}" y="{Y0+24.7}" text-anchor="middle">5</text>')   # step 5: linked to its chat
    a(f'<text class="t-s2" x="{x+12}" y="{Y0+41}">{E(tag)}</text>')
    for i, (lab, txt) in enumerate(rows):
        top = Y0 + 46 + i * 24
        a(f'<path class="dv" d="M{x+8},{top} H{x+156}"/>')
        a(f'<text class="t-lab {c}t" x="{x+12}" y="{top+9.5}">{lab}</text>')
        a(f'<text class="t-k" x="{x+12}" y="{top+20.5}">{E(txt)}</text>')
# a comb ties the strip to all five cards
cb = Y0 + FH
cxs = [x + 82 for x in fx]
a(f'<path class="edge thin" d="M{cxs[0]},{cb} V{cb+5} H{cxs[4]} V{cb} M{cxs[1]},{cb} V{cb+5} M{cxs[2]},{cb} V{cb+5} M{cxs[3]},{cb} V{cb+5}" marker-end="none"/>')
# the Work-Atom lifecycle that runs inside every node
SY = cb + GAP
anchor("strip", 150, SY, 860, STRIP)
CAP = 150
cells = [("open", 124, ["goal, constraints,", "context, check first"], False),
         ("work", 124, ["AI call, code step,", "or a question to you"], False),
         ("verify, close", 176, ["pass: card + log row", "fail: retry, then recover"], False),
         ("exit: refuse", 118, ["bad goal or check:", "logged as refused"], True),
         ("exit: abandon", 118, ["reason required;", "no check, log row"], True)]
a(f'<rect class="bx step" x="150" y="{SY}" width="{CAP}" height="{STRIP}" rx="8"/>')
a(f'<text class="t-lab" x="160" y="{SY+15}">INSIDE EVERY NODE</text>')
a(f'<text class="t-s2" x="160" y="{SY+28}">1 turn = 1 atom</text><text class="t-s2" x="160" y="{SY+40}">a TASK runs as atoms</text>')
cx = 150 + CAP + 10
for k, (t, w, subs, ex) in enumerate(cells):
    a(f'<rect class="bx step{" dashed" if ex else ""}" x="{cx}" y="{SY}" width="{w}" height="{STRIP}" rx="8"/>')
    a(f'<text class="t-c" x="{cx+10}" y="{SY+16}">{E(t)}</text>')
    for j, sub in enumerate(subs):
        a(f'<text class="t-s2" x="{cx+10}" y="{SY+29+j*12}">{E(sub)}</text>')
    if k in (0, 1):
        line(f"M{cx+w},{SY+23} h10")
    cx += w + 10
# Department records sits beside the card row; the atom log sits beside the strip. Both are drawn before the shifted group opens
box(1042, Y0, 208, FH, "card", "Department records", ["the one global org chart", "goal · done-when · rules", "board · ledger · asks", "runs · readings · change log"], ty=21, ly=40)
box(1042, SY, 208, STRIP, "card", "Atom log", ["append-only · one row per atom"], ty=19, ly=35)

# everything from the chips down moves by EX
a(f'<g transform="translate(0,{EX})">')
band(826, 1020 + SH, "CONNECTOR LAYER (NEW)", "band conn")
chips = [("Workflow builder agents", "template first, then build"), ("Code validator", "model · rules · checks"), ("Confidence judge", "scores plans and changes"),
         ("Budget and rate card", "credits · caps · override"), ("Memory", "lessons · playbooks"),
         ("Message board", "answers can edit documents"), ("Document chain", "PRD → HLD → LLD, versioned"), ("Site build + checks", "browser checks · style"),
         ("Sends / deeds", "email via SMTP (opt-in)"), ("Run views", "Map · atoms · tree"),
         ("Template library", "reuse · extend · create"), ("Charter change", "Identity → plan → Relay"), ("Artifact schemas", "pydantic shape + rules"),
         ("Story + agent views", "built from the records"), ("Plan + priorities", "bargains · cuts · plan")]
for i, (t, sub) in enumerate(chips):
    x = fx[i % 5]; y = 592 + (i // 5) * 54
    a(f'<rect class="bx chip" x="{x}" y="{y}" width="164" height="46" rx="8"/>')
    a(f'<text class="t-c" x="{x+10}" y="{y+19}">{E(t)}</text><text class="t-s2" x="{x+10}" y="{y+36}">{E(sub)}</text>')
anchor("J2 chips", 150, 592, 860, 154)
a('<rect class="bx loop" x="150" y="756" width="860" height="30" rx="8"/>')
a('<text class="t-s" x="164" y="775">J2 loop:  a enough to start? › b propose › c price › d resolve › e validate › f run › g audit › h done, or back to b</text>')

# ---------- Connector layer
box(150, 844, 250, 150, "card conn-c", "Connector router", [
    "picks provider and model per atom",
    "falls back when one is away",
    "checks sign-in and quota first",
    "cost per atom: usd and tokens",
    "stays inside Priority's envelope",
    "carries the transcript on a switch",
    "asks for structured JSON when supported"], ly=42, lh=15.5)
box(430, 844, 580, 66, "card conn-c", "ModelConnector (interface · base class)", [
    "start · send · stream · stop · resume · auth_status · usage",
    "call_json(prompt, tools, schema, timeout) → (object, usd, how)"], ly=40, lh=16, ty=21)
box(430, 934, 285, 76, "card conn-c", "Claude connector (extends base)", [
    "claude CLI · stream-json · session resume",
    "your subscription login, never an API key",
    "permission modes · Sutra MCP tools"], ly=40, lh=15, ty=20)
box(725, 934, 285, 76, "card conn-c", "Codex connector (extends base)", [
    "codex exec --json · one process per turn",
    "your ChatGPT login, never an API key",
    "model list from Codex · token usage"], ly=40, lh=15, ty=20)
# v6: StubConnector (sutra_app/connectors/stub.py); --offline gives it the demo reply book (D97)
box(150, 1004, 250, 62, "card conn-c", "Stub connector (extends base)", [
    "no CLI, no login · used by tests",
    "offline: demo reply book"], ty=20, ly=38, lh=15)
# ---------- Providers (moved down by SH)
a(f'<g transform="translate(0,{SH})">')
band(1039, 1119, "PROVIDERS")
box(150, 1046, 250, 70, "card dashed-c", "Tool connectors (MCP)", [
    "Sutra tools · GitHub",
    "Claude-held Gmail · Drive · Slack"], ty=20, ly=38, lh=15, dash=True)
box(430, 1050, 285, 58, "card", "Claude CLI", ["signed in on this Mac"], ty=21, ly=40)
box(725, 1050, 285, 58, "card", "Codex CLI", ["on this Mac · signed in via Sutra"], ty=21, ly=40)
a('</g>')   # end of the SH group

# ---------- Server contents panel, lower part
label(1146, 924, "SERVER CONTENTS", anchor="middle", cls="t-band-h")
box(1042, 592, 208, 96, "card", "Artifacts and blobs", ["site vN · PRD · HLD · LLD", "screenshots · receipts", "style guide · charter"], ty=21, ly=40)
box(1042, 700, 208, 92, "card", "Template library", ["generic per artifact kind", "specialised, versioned", "routing index", "each run keeps its own copy"], ty=21, ly=39, lh=15)
box(1042, 844, 208, 66, "card conn-c", "Usage and cost ledger", ["usd (Claude) · tokens (Codex)", "one row per call, by atom"], ty=21, ly=40)

# ---------- Key
a('<rect class="bx card" x="1030" y="948" width="232" height="180" rx="10"/>')
a('<text class="t-b" x="1044" y="970">Chat flow</text>')
steps = ["read the global org chart", "reference the model library", "Claude CLI + models → workflow", "graph shown to the user", "each node linked to its chat", "graph updates as agents work", "departments, divisions → chat"]
for i, s in enumerate(steps):
    y = 990 + i * 18
    a(f'<circle class="badge" cx="1053" cy="{y-4}" r="8"/><text class="t-badge" x="1053" y="{y-0.5}" text-anchor="middle">{i+1}</text><text class="t-s" x="1068" y="{y}">{E(s)}</text>')
# v6: the Operator box (sutra_app/ops/: cli.py, doctor.py, backup.py, exporter.py, retention.py, lock.py, logsetup.py)
box(1030, 1140, 232, 82, "card", "Operator", [
    "sutra-pro doctor · status · stop · config",
    "backup · restore · export · prune",
    "one instance per data folder · logs"], ty=21, ly=40, lh=14.5, lcls="t-s2")
a('</g>')   # end of the EX group
a('</g>')   # end of the DY group
a('</g>')   # end of the XP group

# ---------- Arrows (the ones that touch the orchestration row are drawn here, with DY added where they reach below it)
# A user message
line(f"M295,190 V{250+XP}"); label(303, 222, "user message")
# detailed view reads the runtime
line(f"M728,190 V{460+DY+XP}"); label(736, 207, "department views (read)")
a(f'<g transform="translate(0,{XP})">')
# B agent <-> chart (1): the agent reads the chart and writes its changes back
line("M400,332 H430", both=True); badge(415, 316, "1")
# C agent -> library (2)
line(f"M290,{OB} V{OB+25} H875 V{OB}"); badge(520, OB+25, "2"); label(302, OB+41, "reference the models")
# D agent -> router via gutter (3)
line(f"M150,345 H122 V{894+DY+EX} H150"); badge(122, 600+DY, "3"); label(112, 700+DY, "claude cli + python models", anchor="middle", rot=-90)
# E agent -> graph store (3)
line("M380,250 V238 H1100 V250"); badge(950, 238, "3"); label(760, 233, "structured workflow + graph", cls="t-e")
a('</g>')   # the two arrows below cross the XP shift, so their lower ends carry it
# F graph store -> graph view (4, 6)
line(f"M1190,{250+XP} V190"); badge(1190, 222 + XP / 2, "4"); label(1178, 212 + XP / 2, "live", anchor="end")
# G graph view -> chat sessions (5, 7)
line(f"M1250,115 H1272 V{362+51+XP} H1250"); badge(1272, 250 + XP / 2, "5"); label(1291, 300 + XP / 2, "node opens its chat", anchor="middle", rot=-90)
a(f'<g transform="translate(0,{XP})">')
# H chart -> runtime
line(f"M480,{OB} V{460+DY}"); label(488, 475+DY-6, "create or reuse a department · 5 nodes")
# library validates runtime
line(f"M960,{OB} V{460+DY}"); label(952, 475+DY-6, "validates records", anchor="end", cls="t-e")

a(LOW)
# runtime <-> records, beside the function row (not shifted by EX)
line("M1010,527 H1042", both=True)
line(f"M1010,{SY+23} H1042")                      # the strip writes the atom log
line(f"M1025,{SY+23} V242 H1042")                 # and up the gutter to the graph store (step 6)
line("M1025,354 H1042")                            # and to the chat sessions (step 5)
badge(1025, 300, "6"); badge(1025, 392, "5")
a(f'<g transform="translate(0,{EX})">')
# runtime -> router (every AI step)
line("M275,786 V844"); label(283, 820, "every call has an atom id")
# router -> base; base -> ledger
line("M400,877 H430")
line("M1010,877 H1042")
# inheritance
line("M572,934 V911", cls="edge inh", marker="inh"); label(580, 926, "extends")
line("M867,934 V911", cls="edge inh", marker="inh"); label(875, 926, "extends")
# connectors -> providers
line(f"M572,1010 V{1050+SH}"); label(580, 1036 + SH / 2, "spawns")
line(f"M867,1010 V{1050+SH}"); label(875, 1036 + SH / 2, "spawns")
# tools -> Claude CLI (dashed)
a(f'<g transform="translate(0,{SH})">'); line("M400,1080 H430", dash=True); a('</g>')
# runtime <-> artifacts / templates
line("M1010,640 H1042", both=True)
line("M1010,723 H1042", both=True)
a('</g>')   # end of the EX group
a('</g>')   # end of the DY group
a('</g>')   # end of the XP group
# ---------- Decisions: a pill of D-numbers on every box they concern, and the full key at the bottom
DEC = json.loads(pathlib.Path(__file__).with_name("decisions.json").read_text())
by_anchor = {}
for d in DEC:
    if d["anchor"]:
        # the lifecycle strip belongs to the function nodes: one pill row for both keeps the card row's edges clear
        by_anchor.setdefault("five function cards" if d["anchor"] == "strip" else d["anchor"], []).append(d["id"])
# per-anchor placement of the pill row: (side, dx, dy, how many ids before "+N"); sides: tl, tr (straddle the top edge), br (bottom edge)
PLACE = {
    "five function cards": ("br", 0, 0, 2),           # the top edge carries arrow labels; the comb tick at x=928 stays clear
    "Chat agent (orchestrator)": ("tl", 0, 0, 3),     # arrow E rises at x=380
    "One global org chart": ("tl", 0, 0, 3),          # badge 7 sits inside the top-right corner
    "Interface library (Python models)": ("tl", 0, 0, 3),   # chat-flow badge 3 sits on the top-right corner
    "Workflow graph store": ("br", 0, 0, 3),          # arrow F rises from the top edge
    "Chat sessions": ("tl", 0, 0, 3),
}
def pills(name, ids):
    ax, ay, aw, ah = ANCH[name]
    side, dx, dy, mx = PLACE.get(name, ("tl" if name.startswith("band:") else "tr", 0, 0, 3))
    shown = ids[:mx] + ([f"+{len(ids) - mx}"] if len(ids) > mx else [])
    wid = [round(7 + 5.1 * len(t), 1) for t in shown]
    total = sum(wid) + 3 * (len(wid) - 1)
    x = ax + 14 + dx if side == "tl" else ax + aw - 10 - total + dx
    y = (ay - 7 if side in ("tl", "tr") else ay + ah - 6) + dy
    for t, w in zip(shown, wid):
        a(f'<rect class="dp" x="{x:g}" y="{y:g}" width="{w}" height="13" rx="6.5"/><text class="dpt" x="{x + w / 2:g}" y="{y + 9.6:g}" text-anchor="middle">{t}</text>')
        x += w + 3
for name, ids in by_anchor.items():
    pills(name, sorted(ids, key=lambda t: int(t[1:])))
ky = H0 + 8
a(f'<rect class="band" x="44" y="{ky}" width="1218" height="{KEYH}" rx="12"/>')
a(f'<text class="t-b" x="62" y="{ky + 24}">Decisions the owner did not have to take: {len(DEC)}, each with why and what was rejected in docs/DECISIONS.md</text>')
a(f'<text class="t-e" x="1244" y="{ky + 24}" text-anchor="end">pill on a box = decisions about it</text>')
rows = -(-len(DEC) // 4)
for i, d in enumerate(DEC):
    col, row = divmod(i, rows)
    x = 62 + col * 300
    y = ky + 48 + row * 12.6
    lab = d["label"]
    tl = ' textLength="256" lengthAdjust="spacingAndGlyphs"' if len(lab) > 47 else ""
    a(f'<text class="dkn" x="{x}" y="{y:g}">{d["id"]}</text><text class="dkt" x="{x + 33}" y="{y:g}"{tl}>{E(lab)}</text>')
a('</svg>')
svg = "\n".join(out)

page = '''<meta charset="utf-8">
<title>Sutra App Architecture</title>
<meta name="claude:viewport-fit-sides" content="cover">
<style>
/* Layout: one wide diagram in tiers, read top to bottom; the numbered circles are the chat flow from the draw.io page. */
:root{
  --bg:#fafaf9; --card:#ffffff; --soft:#f5f4f2; --line:#d9d6d2; --ink:#1c1917; --ink2:#44403c; --muted:#78716c;
  --acc:#8A5D2E; --acc-bg:#f6efe7; --acc-line:#e0c9ad; --hot:#f3efff; --hot-line:#b7b0e8;
  --id:#6059C5; --id-bg:#F1F0FA; --ad:#9B3FB3; --ad-bg:#F6EEF8; --pr:#2B7179; --pr-bg:#ECF2F3; --co:#356C97; --co-bg:#EDF2F6; --au:#B03E6C; --au-bg:#F8EEF2;
  --badge:#1c1917; --badge-ink:#fafaf9;
}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){
  --bg:#0C0B09; --card:#1C1A17; --soft:#161412; --line:#3a352f; --ink:#F5F0E8; --ink2:#d9d2c7; --muted:#9a938a;
  --acc:#C4956A; --acc-bg:rgba(196,149,106,.12); --acc-line:rgba(196,149,106,.4); --hot:rgba(147,142,215,.10); --hot-line:rgba(147,142,215,.5);
  --id:#938ED7; --id-bg:rgba(147,142,215,.14); --ad:#C07DD1; --ad-bg:rgba(192,125,209,.14); --pr:#3EA4AF; --pr-bg:rgba(62,164,175,.14); --co:#629CC8; --co-bg:rgba(98,156,200,.14); --au:#D17C9E; --au-bg:rgba(209,124,158,.14);
  --badge:#F5F0E8; --badge-ink:#0C0B09; color-scheme:dark;}}
:root[data-theme="dark"]{
  --bg:#0C0B09; --card:#1C1A17; --soft:#161412; --line:#3a352f; --ink:#F5F0E8; --ink2:#d9d2c7; --muted:#9a938a;
  --acc:#C4956A; --acc-bg:rgba(196,149,106,.12); --acc-line:rgba(196,149,106,.4); --hot:rgba(147,142,215,.10); --hot-line:rgba(147,142,215,.5);
  --id:#938ED7; --id-bg:rgba(147,142,215,.14); --ad:#C07DD1; --ad-bg:rgba(192,125,209,.14); --pr:#3EA4AF; --pr-bg:rgba(62,164,175,.14); --co:#629CC8; --co-bg:rgba(98,156,200,.14); --au:#D17C9E; --au-bg:rgba(209,124,158,.14);
  --badge:#F5F0E8; --badge-ink:#0C0B09; color-scheme:dark}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);font:14px/1.5 system-ui,-apple-system,"Segoe UI",Roboto,sans-serif;
  padding-left:max(16px,env(safe-area-inset-left,0px));padding-right:max(16px,env(safe-area-inset-right,0px))}
.wrap{max-width:1360px;margin:0 auto;padding-block:20px 32px}
h1{font:600 20px/1.3 system-ui,-apple-system,"Segoe UI",Roboto,sans-serif;margin:0 0 12px;letter-spacing:-.005em}
.scroll{overflow-x:auto;border:1px solid var(--line);border-radius:14px;background:var(--soft)}
figure{margin:0}
svg{display:block;width:100%;min-width:1040px;height:auto;color:var(--muted)}
svg text{font-family:system-ui,-apple-system,"Segoe UI",Roboto,sans-serif;fill:var(--ink)}
.bx{fill:var(--card);stroke:var(--line);stroke-width:1}
.bx.hot{fill:var(--hot);stroke:var(--hot-line)}
.bx.conn-c{fill:var(--acc-bg);stroke:var(--acc)}
.bx.dashed-c{fill:var(--card);stroke:var(--acc)}
.bx.chip{fill:var(--card)}
.bx.loop{fill:var(--card);stroke-dasharray:5 4}
.bx.dashed,.dashed{stroke-dasharray:5 4}
.band{fill:var(--bg);stroke:var(--line);stroke-width:1}
.band.conn{stroke:var(--acc-line)}
.f-id{fill:var(--id)} .f-ad{fill:var(--ad)} .f-pr{fill:var(--pr)} .f-co{fill:var(--co)} .f-au{fill:var(--au)}
.f-idb{stroke:var(--id)} .f-adb{stroke:var(--ad)} .f-prb{stroke:var(--pr)} .f-cob{stroke:var(--co)} .f-aub{stroke:var(--au)}
svg .f-idt{fill:var(--id)} svg .f-adt{fill:var(--ad)} svg .f-prt{fill:var(--pr)} svg .f-cot{fill:var(--co)} svg .f-aut{fill:var(--au)}
.t-b{font-size:13.5px;font-weight:600}
.dp{fill:var(--card);stroke:var(--acc-line);stroke-width:1}.dpt{font-size:8px;font-weight:700;fill:var(--acc)}.dkn{font-size:8.8px;font-weight:700;fill:var(--acc)}.dkt{font-size:8.8px;fill:var(--ink2)}
.t-k{font-size:10.5px;fill:var(--ink2)}
.t-lab{font-size:9px;font-weight:700;letter-spacing:.06em}
.dv{stroke:var(--line);stroke-width:1;fill:none}
.bx.step{fill:var(--soft)}
.bx.mark{stroke-width:1.6}
.t-s{font-size:11.5px;fill:var(--ink2)}
.t-s2{font-size:10.5px;fill:var(--muted)}
.t-c{font-size:12px;font-weight:600}
.t-e{font-size:11px;fill:var(--muted)}
.t-n{font-size:11px;font-weight:600}.t-n.sm{font-size:9.5px}
.t-tag{font-size:10px;font-weight:600;fill:var(--id)}
.t-band{font-size:11px;font-weight:600;letter-spacing:.09em;fill:var(--muted)}
.t-band-h{font-size:11px;font-weight:600;letter-spacing:.09em;fill:var(--muted)}
.t-badge{font-size:11px;font-weight:700;fill:var(--badge-ink)}
.badge{fill:var(--badge)}
.node{fill:var(--card);stroke:var(--hot-line);stroke-width:1.2}
.node.root{fill:var(--hot)}
.node.add{fill:var(--id-bg);stroke:var(--id);stroke-dasharray:4 3}
.node.mv{stroke:var(--id);stroke-width:2.4}
.edge{fill:none;stroke:currentColor;stroke-width:1.5}
.edge.thin{stroke-width:1.1}
.edge.inh{stroke:var(--acc);color:var(--acc)}
.edge.dashed{stroke-dasharray:5 4}
@media (prefers-reduced-motion:reduce){*{animation:none!important;transition:none!important}}
</style>
<div class="wrap">
<h1>Sutra app architecture</h1>
<div class="scroll" role="region" aria-label="Architecture diagram, scrolls sideways on a narrow screen" tabindex="0">
<figure>
''' + svg + '''
</figure>
</div>
</div>
'''
import pathlib
OUT = pathlib.Path(__file__).with_name("arch.html")   # python3 docs/diagram/gen.py writes the page next to this file
OUT.write_text(page)
print(len(page), "H =", H, "DY =", DY)
