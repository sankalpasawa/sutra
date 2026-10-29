"""j2ui_words_table.py -- substitutions S4 and S5 of scripts/sync_j2_ui.py (A5.1.3): the kind-neutral wording of the page.

S4 is a table WORDS of (id, original, replacement) byte strings. Each original occurs exactly once in the page after S1 (guard 7).
Every replacement keeps the line count of its original and is the original itself when WD(key, default) has no word set, so a
website department's page reads exactly as before. S5 is the one line that defines WD, inserted after `const $ = ...`.
Rows S4.35 and S4.36 are behaviour edits (the New run and Start over handlers); S4.33 carries the statements of S4.37 (the static markup is set from the words only when one is set).

Guard 8: a WD( inside a template interpolation is wrapped in esc( unless its key is a boolean the page only tests (SAFE_KEYS)."""
import re

S5_ANCHOR = b"const $ = id => document.getElementById(id);"
S5_LINE = b'const WD = (k, d) => { const w = CTX && CTX.words; return w && w[k] != null ? w[k] : d; };'
#: keys whose value is only tested or iterated by the page, never put into markup as given
SAFE_KEYS = ("pick", "can_open", "can_download", "hide_tabs", "steps", "examples", "follow_ups")

_OPEN = b'<a href="site/latest${runQ().replace("&", "?")}" target="_blank" rel="noopener">Open full screen</a>'
_DOWN = b'`<a href="site/latest${runQ().replace("&", "?")}" download="my-website.html">Download the HTML file</a>`'
_STEPS = (b'["Reading your request\xe2\x80\xa6", "Reading your request\xe2\x80\xa6", "Planning your website\xe2\x80\xa6", "Planning your website\xe2\x80\xa6", "Planning your website\xe2\x80\xa6",\n'
          b'       "Planning your website\xe2\x80\xa6", "Building your website\xe2\x80\xa6", "Checking everything works on phones and computers\xe2\x80\xa6", "Almost there\xe2\x80\xa6"]')
_E = "…".encode()


def _b(s):
    return s.encode("utf-8")


def _row(i, a, b):
    return (i, _b(a) if isinstance(a, str) else a, _b(b) if isinstance(b, str) else b)


WORDS = [
    _row("S4.06", 'const examples = s => s.doc ? PRD_EXAMPLES : EXAMPLES;',
         'const examples = s => WD("examples", s.doc ? PRD_EXAMPLES : EXAMPLES);'),
    _row("S4.07", '<small>Your website team</small>${esc(plain(a.say))}',
         '<small>${esc(WD("team", "Your website team"))}</small>${esc(plain(a.say))}'),
    _row("S4.08", '<small>${s.doc ? "Your document team" : "Your website team"}</small>',
         '<small>${esc(WD("team", s.doc ? "Your document team" : "Your website team"))}</small>'),
    _row("S4.09", '<div><label>What should we make? <select class="outsel" aria-label="What to build">${outOptions(s)}</select></label></div>',
         '${WD("pick", true) ? `<div><label>What should we make? <select class="outsel" aria-label="What to build">${outOptions(s)}</select></label></div>` : ""}'),
    _row("S4.10", '${s.doc ? "Describe the product. We\'ll ask for any facts we need, then write the PRD." : "Describe the website you want. We\'ll ask a few questions, then build it."}',
         '${esc(WD("start", s.doc ? "Describe the product. We\'ll ask for any facts we need, then write the PRD." : "Describe the website you want. We\'ll ask a few questions, then build it."))}'),
    _row("S4.11", '<small>Your website team</small>${esc(plain(m.text))}',
         '<small>${esc(WD("team", "Your website team"))}</small>${esc(plain(m.text))}'),
    _row("S4.12", '`Your ${s.doc ? "document" : "website"} is ready`',
         '`${esc(WD("ready", `Your ${s.doc ? "document" : "website"} is ready`))}`'),
    _row("S4.13", '$("stitle").textContent = s.doc ? "Your document team" : "Your website team";',
         '$("stitle").textContent = WD("team", s.doc ? "Your document team" : "Your website team");'),
    _row("S4.14", '...(s.versions ? ["website"] : [])];', '...(s.versions ? [esc(WD("built", "website"))] : [])];'),
    _row("S4.15a", _OPEN, '${WD("can_open", true) ? `' + _OPEN.decode() + '` : ""}'),
    _row("S4.15b", _DOWN, '(WD("can_download", true) ? ' + _DOWN.decode() + ' : "")'),
    _row("S4.16", _STEPS, b'WD("steps", ' + _STEPS + b')'),
    _row("S4.17", ': s.doc ? "Describe the product\u2026" : "Describe the website you want\u2026";',
         ': WD("describe", s.doc ? "Describe the product…" : "Describe the website you want…");'),
    _row("S4.18", '? "Ask for a change…" : "Describe the website you want. The agents take it from there…";',
         '? "Ask for a change…" : WD("describe_long", "Describe the website you want. The agents take it from there…");'),
    _row("S4.19", 'items = ["Add a section for visiting hours", "Looks good"];',
         'items = WD("follow_ups", ["Add a section for visiting hours", "Looks good"]);'),
    _row("S4.20", '(checked by code, ${s.doc ? "document" : "site"} v${last.version})',
         '(checked by code, ${esc(WD("noun", s.doc ? "document" : "site"))} v${last.version})'),
    _row("S4.21", 'Cycle ${a.cycle} · ${s.doc ? "document" : "site"} v${a.version}',
         'Cycle ${a.cycle} · ${esc(WD("noun", s.doc ? "document" : "site"))} v${a.version}'),
    _row("S4.22", 'Audit checks the site against', 'Audit checks the ${esc(WD("noun", "site"))} against'),
    _row("S4.23", '<h3>${s.doc ? "Document rubric" : "Design and usability rubric"}</h3>',
         '<h3>${esc(WD("rubric", s.doc ? "Document rubric" : "Design and usability rubric"))}</h3>'),
    _row("S4.24", '<span class="tag">site v${m.version}</span>', '<span class="tag">${esc(WD("noun", "site"))} v${m.version}</span>'),
    _row("S4.25", 'return "site v" + m.version;', 'return WD("noun", "site") + " v" + m.version;'),
    _row("S4.26", 'audit:"J2.g checks the site"', 'get audit(){ return "J2.g checks the " + WD("noun", "site"); }'),
    _row("S4.27", '<dt>site</dt>', '<dt>${esc(WD("noun", "site"))}</dt>'),
    _row("S4.28", 'audit: "The checks run on each version of the site."',
         'get audit(){ return "The checks run on each version of the " + WD("noun", "site") + "."; }'),
    _row("S4.29", 'The first workflow that runs writes the style guide (palette, fonts, spacing, buttons, cards) before any section is built. Every workflow agent follows it.',
         '${esc(WD("style_empty", "The first workflow that runs writes the style guide (palette, fonts, spacing, buttons, cards) before any section is built. Every workflow agent follows it."))}'),
    _row("S4.30a", 'Memory is off (J2_MEMORY=0): no playbooks are read or saved in this run.',
         '${esc(WD("memory_off", "Memory is off (J2_MEMORY=0): no playbooks are read or saved in this run."))}'),
    _row("S4.30b", 'Memory is off (J2_MEMORY=0): no lessons are read or saved in this run.',
         '${esc(WD("memory_off", "Memory is off (J2_MEMORY=0): no lessons are read or saved in this run."))}'),
    _row("S4.31", '"Open the site preview"', 'WD("go_preview", "Open the site preview")'),
    _row("S4.32", '|| "<option>no site yet</option>"', '|| "<option>no " + esc(WD("noun", "site")) + " yet</option>"'),
    _row("S4.33", '$("tab-board").hidden = !s.has_board;',
         '$("tab-board").hidden = !s.has_board; '
         'WD("hide_tabs", []).forEach(t => { const b = document.querySelector(`.tabs [data-tab="${t}"]`); if (b) b.hidden = true; }); '
         '{ const ft = WD("frame_title", null), tm = WD("team", null), nt = WD("new_task", null); '
         'if (ft != null){ $("sframe").title = ft; $("frame").title = ft; } if (tm != null) $("stitle").textContent = tm; '
         'if (nt != null) $("reset").textContent = nt; }'),
    _row("S4.34", '`<div class="legend" data-legend><b>Output types</b> ${legend} <span class="empty">Click one to filter; click again to clear. Status is always a word as well as a colour.</span></div>`',
         '(WD("pick", true) ? `<div class="legend" data-legend><b>Output types</b> ${legend} <span class="empty">Click one to filter; click again to clear. Status is always a word as well as a colour.</span></div>` : "")'),
    _row("S4.35b", '$("reset").onclick = async () => { await fetch(',
         '$("reset").onclick = async () => { if (WD("new_task", null) != null){ ($("sbox").offsetParent ? $("sbox") : $("box")).focus(); return; } await fetch('),
    _row("S4.36a", '<button type="button" class="ghost" id="sretry">Start over</button>',
         '<button type="button" class="ghost" id="sretry">${esc(WD("retry", "Start over"))}</button>'),
    _row("S4.36b", 'if (b.id === "sretry"){ await fetch(',
         'if (b.id === "sretry"){ if (WD("retry", null) != null){ const u = (s => (s.allChat || []).filter(x => x.who === "user").pop())(CTX || {}); if (u) await sendText(u.text); return; } await fetch('),
]
