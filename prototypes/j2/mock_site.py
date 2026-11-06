"""Scripted website builder used only in mock mode, so the demo runs without an
API key. With a real key, the Development agent writes the HTML itself."""
import html


def build(brief, design, version, fixes=()):
    p = design["palette"]
    f = design["fonts"]
    name = html.escape(brief.get("site_name", "CityCare Hospital"))
    emergency = "108" if "emergency" in " ".join(brief.get("must_have", [])).lower() else "108"
    sticky = "sticky-emergency" in fixes
    depts = [("Cardiology", "Heart checks, ECG, angioplasty"),
             ("Orthopaedics", "Joint care, sports injuries, physiotherapy"),
             ("Paediatrics", "Newborn care, vaccination, child health"),
             ("Neurology", "Stroke care, epilepsy, headache clinic"),
             ("Maternity", "Antenatal care, labour suites, NICU"),
             ("Emergency & Trauma", "24/7 casualty with ICU backup")]
    doctors = [("Dr. Meera Iyer", "Cardiology", "18 yrs"), ("Dr. Arjun Rao", "Orthopaedics", "12 yrs"),
               ("Dr. Sana Khan", "Paediatrics", "10 yrs"), ("Dr. Vikram Shah", "Neurology", "15 yrs")]
    dept_html = "".join(f'<article class="card"><h3>{d}</h3><p>{t}</p></article>' for d, t in depts)
    doc_html = "".join(
        f'<article class="doc"><div class="avatar">{n.split()[1][0]}{n.split()[-1][0]}</div>'
        f'<h3>{n}</h3><p>{s} · {y}</p></article>' for n, s, y in doctors)
    testi = ""
    if "testimonials" in fixes:
        quotes = [("The emergency team saw my father within minutes. Calm, clear and kind.", "Ramesh K."),
                  ("Booking online took two minutes and the OPD wait was short.", "Priya S."),
                  ("Dr. Sana Khan made our daughter's first vaccination stress-free.", "Anita and Rahul")]
        testi = ('<section id="stories"><div class="wrap"><h2>Patient stories</h2><div class="grid">' +
                 "".join(f'<article class="card"><p>“{q}”</p><b>{a}</b></article>' for q, a in quotes) +
                 '</div></div></section>')
    opts = "".join(f"<option>{d}</option>" for d, _ in depts)
    bar = (f'<div class="ebar">Emergency? Call <a href="tel:{emergency}">{emergency}</a> · '
           f'Ambulance 24/7</div>') if sticky else ""
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>{name}</title>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family={f['heading'].replace(' ', '+')}:wght@600;700&family={f['body'].replace(' ', '+')}:wght@400;500&display=swap">
<style>
:root{{--p:{p['primary']};--s:{p['secondary']};--a:{p['accent']};--bg:{p['background']};--t:{p['text']}}}
*{{box-sizing:border-box}}body{{margin:0;font:16px/1.6 '{f['body']}',system-ui,sans-serif;color:var(--t);background:var(--bg)}}
h1,h2,h3{{font-family:'{f['heading']}',Georgia,serif;line-height:1.2;margin:0 0 .4em}}
.wrap{{max-width:1100px;margin:0 auto;padding:0 20px}}
.ebar{{position:sticky;top:0;z-index:10;background:var(--a);color:#fff;text-align:center;padding:8px;font-weight:600}}
.ebar a{{color:#fff}}
header{{background:#fff;border-bottom:1px solid #e5e7eb}}
nav{{display:flex;justify-content:space-between;align-items:center;padding:14px 0;gap:12px;flex-wrap:wrap}}
.logo{{font-family:'{f['heading']}',serif;font-size:22px;font-weight:700;color:var(--p)}}
nav ul{{display:flex;gap:18px;list-style:none;margin:0;padding:0;flex-wrap:wrap}}nav a{{color:var(--t);text-decoration:none}}
.btn{{display:inline-block;background:var(--p);color:#fff;padding:12px 20px;border-radius:8px;text-decoration:none;font-weight:600;border:0;cursor:pointer}}
.btn.alt{{background:#fff;color:var(--p);border:2px solid var(--p)}}
.hero{{background:linear-gradient(120deg,var(--p),var(--s));color:#fff;padding:72px 0}}
.hero p{{max-width:560px;font-size:18px;opacity:.95}}.hero .btn{{background:#fff;color:var(--p);margin-right:10px}}
.stats{{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin-top:36px}}
.stats div{{background:rgba(255,255,255,.14);padding:14px;border-radius:10px}}.stats b{{display:block;font-size:24px}}
section{{padding:56px 0}}.grid{{display:grid;grid-template-columns:repeat(3,1fr);gap:16px}}
.card,.doc{{background:#fff;border:1px solid #e5e7eb;border-radius:12px;padding:20px}}
.card h3{{color:var(--p)}}.docs{{display:grid;grid-template-columns:repeat(4,1fr);gap:16px}}
.avatar{{width:56px;height:56px;border-radius:50%;background:var(--s);color:#fff;display:grid;place-items:center;font-weight:700;margin-bottom:10px}}
form{{display:grid;grid-template-columns:1fr 1fr;gap:12px;background:#fff;padding:24px;border-radius:12px;border:1px solid #e5e7eb}}
input,select{{padding:11px;border:1px solid #cbd5e1;border-radius:8px;font:inherit}}form .full{{grid-column:1/-1}}
.contact{{display:grid;grid-template-columns:1fr 1fr;gap:24px}}
footer{{background:var(--t);color:#e5e7eb;padding:24px 0;font-size:14px}}
@media(max-width:800px){{.grid,.docs,.stats,.contact,form{{grid-template-columns:1fr}}}}
</style></head><body>
{bar}
<header><div class="wrap"><nav><span class="logo">{name}</span>
<ul><li><a href="#departments">Departments</a></li><li><a href="#doctors">Doctors</a></li><li><a href="#appointment">Appointments</a></li><li><a href="#contact">Contact</a></li></ul>
<a class="btn" href="#appointment">Book appointment</a></nav></div></header>
<section class="hero"><div class="wrap"><h1>Care you can trust, close to home</h1>
<p>{html.escape(brief.get('purpose', 'Multi-speciality hospital with 24/7 emergency care.'))}</p>
<a class="btn" href="#appointment">Book an appointment</a><a class="btn alt" href="#departments">Find a department</a>
<div class="stats"><div><b>250+</b>beds</div><div><b>60+</b>specialists</div><div><b>24/7</b>emergency</div><div><b>NABH</b>accredited</div></div>
</div></section>
<section id="departments"><div class="wrap"><h2>Departments</h2><div class="grid">{dept_html}</div></div></section>
<section id="doctors" style="background:#fff"><div class="wrap"><h2>Our doctors</h2><div class="docs">{doc_html}</div></div></section>
{testi}
<section id="appointment"><div class="wrap"><h2>Book an appointment</h2>
<form onsubmit="event.preventDefault();this.querySelector('.ok').hidden=false">
<input required placeholder="Full name" aria-label="Full name"><input required placeholder="Phone" aria-label="Phone">
<select aria-label="Department">{opts}</select><input type="date" aria-label="Preferred date">
<button class="btn full">Request appointment</button><p class="ok full" hidden>Thanks. Our team will call you to confirm.</p></form></div></section>
<section id="contact" style="background:#fff"><div class="wrap contact"><div><h2>Visit us</h2>
<p>12 MG Road, Bengaluru 560001<br>OPD: Mon–Sat, 8 am – 8 pm<br>Reception: +91 00000 11111</p></div>
<div><h2>Emergency</h2><p>Ambulance and casualty open 24/7.<br>Call <b>{emergency}</b> or +91 00000 22222.</p></div></div></section>
<footer><div class="wrap">© 2026 {name} · Sample site generated by the agent studio (v{version})</div></footer>
</body></html>"""
