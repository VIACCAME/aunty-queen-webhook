"""Dashboard for counselors: https://<render-url>/dashboard (password = DASHBOARD_KEY in Render).

Pure helpers: turning Sheet rows into stats, rendering HTML, and reading uploaded Excel/CSV files.
The routes live in app.py.
"""
import csv
import html
import io
import re
from collections import Counter
from datetime import datetime, timedelta, timezone

E = html.escape


# ----------------------------------------------------------------------------
# Stats
# ----------------------------------------------------------------------------
def age_bucket(value):
    if re.search(r"under|moins", str(value or ""), re.I):
        return "Under 18"
    m = re.search(r"\d{1,2}", str(value or ""))
    if not m:
        return "Not given"
    age = int(m.group())
    if age < 18:
        return "Under 18"
    if age < 25:
        return "18–24"
    if age < 35:
        return "25–34"
    return "35+"


def clean(value, default="Not given"):
    v = str(value or "").strip().lstrip("'")
    return default if not v or v.lower() == "skipped" else v


def city_name(value):
    v = clean(value)
    return v if v == "Not given" else v.strip().title()


def parse_time(value):
    try:
        t = datetime.fromisoformat(str(value).strip().lstrip("'"))
        return t if t.tzinfo else t.replace(tzinfo=timezone.utc)
    except Exception:
        return None


def wants_pills(row):
    return bool(clean(row.get("pill_choice"), "")) or (
        clean(row.get("preference"), "") == "Pills" and clean(row.get("decision"), "").startswith("Continue"))


def find_column(headers, *words):
    for h in headers:
        low = str(h).lower()
        if any(w in low for w in words):
            return h
    return None


def compute_stats(intakes, contacts, imported):
    real = [r for r in intakes if clean(r.get("phone"), "")]
    stats = {
        "people": len({clean(r.get("phone")) for r in real} | {clean(c.get("phone")) for c in contacts}),
        "intakes": len(real),
        "completed": sum(1 for r in real if r.get("status") == "completed"),
        "urgent": sum(1 for r in real if r.get("status") == "URGENT"),
        "pills": sum(1 for r in real if wants_pills(r)),
        "opted_out": sum(1 for c in contacts if c.get("opted_out") == "yes"),
        "imported": len(imported),
    }
    now = datetime.now(timezone.utc)
    stats["last_30_days"] = sum(1 for r in real if (parse_time(r.get("started_at")) or now - timedelta(days=99)) > now - timedelta(days=30))

    def count(field, fn=clean, rows=real):
        return Counter(fn(r.get(field)) for r in rows).most_common()

    stats["by_month"] = sorted(Counter(str(r.get("started_at", ""))[:7] for r in real if r.get("started_at")).items())
    stats["by_gender"] = count("gender")
    stats["by_age"] = count("age", age_bucket)
    stats["by_city"] = count("city", city_name)[:12]
    stats["by_language"] = count("language", lambda v: {"fr": "French", "en": "English"}.get(str(v), clean(v)))
    stats["by_need"] = count("category")
    stats["by_heard"] = count("heard_from")
    stats["by_education"] = count("education")
    stats["by_method"] = [(k, v) for k, v in count("pill_choice") if k != "Not given"]
    stats["by_status"] = count("status")

    # Old records uploaded from Excel: best-effort columns.
    headers = list(imported[0].keys()) if imported else []
    g, a, c, d = (find_column(headers, "gender", "sex", "genre"), find_column(headers, "age"),
                  find_column(headers, "city", "town", "ville", "region", "location"),
                  find_column(headers, "date", "year", "année", "annee"))
    stats["imported_gender"] = count(g, rows=imported) if g else []
    stats["imported_age"] = count(a, age_bucket, rows=imported) if a else []
    stats["imported_city"] = count(c, city_name, rows=imported)[:12] if c else []
    stats["imported_year"] = sorted(Counter(re.search(r"(20\d\d)", str(r.get(d, ""))).group(1)
                                            for r in imported if d and re.search(r"(20\d\d)", str(r.get(d, "")))).items())

    stats["pill_requests"] = sorted([r for r in real if wants_pills(r)],
                                    key=lambda r: str(r.get("updated_at", "")), reverse=True)[:60]
    stats["recent"] = sorted(real, key=lambda r: str(r.get("updated_at", "")), reverse=True)[:40]
    return stats


def broadcast_audience(contacts, imported, now=None):
    """Who may receive the broadcast: not opted out, quiet for 7+ days, not broadcast to in the last 30 days."""
    now = now or datetime.now(timezone.utc)
    phones, seen = [], set()
    for c in contacts:
        phone = re.sub(r"\D", "", str(c.get("phone", "")))
        if not phone or phone in seen:
            continue
        seen.add(phone)
        if c.get("opted_out") == "yes":
            continue
        last = parse_time(c.get("last_seen"))
        if last and last > now - timedelta(days=7):
            continue
        sent = parse_time(c.get("last_broadcast_at"))
        if sent and sent > now - timedelta(days=30):
            continue
        phones.append(phone)
    pcol = find_column(list(imported[0].keys()) if imported else [], "phone", "tel", "whatsapp", "number", "numéro")
    for r in imported if pcol else []:
        phone = re.sub(r"\D", "", str(r.get(pcol, "")))
        if len(phone) == 9:  # local Cameroon number
            phone = "237" + phone
        if len(phone) >= 11 and phone not in seen:
            seen.add(phone)
            phones.append(phone)
    return phones


# ----------------------------------------------------------------------------
# Excel / CSV upload
# ----------------------------------------------------------------------------
def read_upload(filename, raw):
    """Rows (list of dicts) from an .xlsx or .csv file. Empty rows are dropped."""
    name = (filename or "").lower()
    if name.endswith(".csv"):
        text = raw.decode("utf-8-sig", errors="replace")
        rows = list(csv.DictReader(io.StringIO(text)))
    elif name.endswith((".xlsx", ".xlsm")):
        from openpyxl import load_workbook
        wb = load_workbook(io.BytesIO(raw), read_only=True, data_only=True)
        rows = []
        for ws in wb.worksheets:
            it = ws.iter_rows(values_only=True)
            header = next(it, None)
            if not header:
                continue
            keys = [str(h).strip() if h is not None else f"column_{i + 1}" for i, h in enumerate(header)]
            for values in it:
                if values and any(v not in (None, "") for v in values):
                    row = {k: ("" if v is None else (v.isoformat() if hasattr(v, "isoformat") else str(v)))
                           for k, v in zip(keys, values)}
                    row["sheet"] = ws.title
                    rows.append(row)
    else:
        raise ValueError("Please upload an .xlsx or .csv file.")
    return [{k: v for k, v in r.items() if k} for r in rows if any(str(v).strip() for v in r.values())]


# ----------------------------------------------------------------------------
# HTML
# ----------------------------------------------------------------------------
STYLE = """
:root{--bg:#fbf7f4;--card:#fff;--ink:#2b1d26;--muted:#7a6872;--line:#eadfe3;--brand:#7b2d5b;--brand2:#c58b2b;--soft:#f6eaf1;--warn:#b42318}
@media (prefers-color-scheme:dark){:root{--bg:#171215;--card:#221a1f;--ink:#f3e9ee;--muted:#b7a5ae;--line:#3a2d34;--brand:#e08ab8;--brand2:#e6b45e;--soft:#2f2229;--warn:#ff8a7a}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:15px/1.5 system-ui,-apple-system,Segoe UI,sans-serif}
header{background:var(--brand);color:#fff;padding:18px 16px}header h1{margin:0;font-size:20px}header p{margin:2px 0 0;opacity:.85;font-size:13px}
header a{color:#fff}main{max-width:1100px;margin:0 auto;padding:16px}
.kpis{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:10px}
.kpi{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:12px}.kpi b{display:block;font-size:26px;color:var(--brand)}
.kpi span{color:var(--muted);font-size:13px}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(300px,1fr));gap:12px;margin-top:12px}
.card{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:14px;overflow:hidden}.card h2{font-size:15px;margin:0 0 10px}
.bar{display:grid;grid-template-columns:minmax(90px,38%) 1fr 40px;align-items:center;gap:8px;margin:5px 0;font-size:13px}
.bar i{display:block;height:10px;border-radius:6px;background:var(--brand2)}.bar em{font-style:normal;color:var(--muted);text-align:right}
.bar span{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
table{width:100%;border-collapse:collapse;font-size:13px}th,td{text-align:left;padding:7px 6px;border-bottom:1px solid var(--line);vertical-align:top}
th{color:var(--muted);font-weight:600}.wide{overflow-x:auto}.tag{display:inline-block;padding:1px 8px;border-radius:10px;background:var(--soft);font-size:12px}
.tag.urgent{background:var(--warn);color:#fff}.note{color:var(--muted);font-size:13px}.msg{padding:10px 12px;border-radius:10px;background:var(--soft);margin:10px 0}
form.inline{display:flex;flex-wrap:wrap;gap:8px;align-items:center}input,select,button{font:inherit;padding:8px 10px;border-radius:8px;border:1px solid var(--line);background:var(--card);color:var(--ink)}
button{background:var(--brand);color:#fff;border:0;cursor:pointer}.chat .in{background:var(--soft)}.chat div{padding:8px 10px;border-radius:10px;margin:6px 0;max-width:85%}
.chat .bot{background:var(--card);border:1px solid var(--line);margin-left:auto}.chat .counselor{background:#e7f5ea;color:#1d4d2a;margin-left:auto}
.chat small{display:block;color:var(--muted);font-size:11px}
"""


def page(title, body):
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><meta name="robots" content="noindex">
<title>{E(title)}</title><style>{STYLE}</style></head><body>{body}</body></html>"""


def login_page(error=""):
    err = f'<p class="msg">{E(error)}</p>' if error else ""
    return page("Aunty Queen dashboard", f"""
<header><h1>Aunty Queen · Dashboard</h1><p>Counselors only</p></header>
<main><div class="card" style="max-width:420px;margin:30px auto">{err}
<form method="post" action="/dashboard/login"><p><label>Password<br>
<input type="password" name="key" autocomplete="current-password" style="width:100%" autofocus></label></p>
<button type="submit">Open dashboard</button></form></div></main>""")


def bars(title, items, note=""):
    items = [(k, v) for k, v in items if k]
    if not items:
        return f'<div class="card"><h2>{E(title)}</h2><p class="note">No data yet.</p></div>'
    top = max(v for _, v in items) or 1
    rows = "".join(f'<div class="bar"><span title="{E(str(k))}">{E(str(k))}</span>'
                   f'<i style="width:{max(4, round(v * 100 / top))}%"></i><em>{v}</em></div>' for k, v in items)
    n = f'<p class="note">{E(note)}</p>' if note else ""
    return f'<div class="card"><h2>{E(title)}</h2>{rows}{n}</div>'


def short(v, n=60):
    v = clean(v, "")
    return v if len(v) <= n else v[:n - 1] + "…"


def dashboard_page(stats, audience_size, message="", template_default=""):
    s = stats
    msg = f'<p class="msg">{E(message)}</p>' if message else ""
    kpis = "".join(f'<div class="kpi"><b>{v}</b><span>{E(k)}</span></div>' for k, v in [
        ("people reached", s["people"]), ("conversations", s["intakes"]), ("last 30 days", s["last_30_days"]),
        ("completed intakes", s["completed"]), ("pill requests", s["pills"]), ("urgent cases", s["urgent"]),
        ("old records imported", s["imported"]), ("opted out of updates", s["opted_out"])])

    pills = "".join(
        f"<tr><td>{E(short(r.get('updated_at'), 16))}</td><td>{E(short(r.get('name'), 20))}</td>"
        f"<td>{E(short(r.get('age'), 6))}</td><td>{E(short(r.get('city'), 18))}</td><td>{E(short(r.get('lmp'), 24))}</td>"
        f"<td>{E(short(r.get('pill_choice') or r.get('preference'), 26))}</td><td>{E(short(r.get('health_issues'), 30))}</td>"
        f"<td>{E(short(r.get('summary'), 400))}</td>"
        f"<td><a href=\"/dashboard/chat?phone={E(clean(r.get('phone'), ''))}\">chat</a></td></tr>" for r in s["pill_requests"])
    pills_table = (f'<div class="wide"><table><tr><th>Updated</th><th>Name</th><th>Age</th><th>Town</th><th>Last period</th>'
                   f'<th>Method</th><th>Health</th><th>Summary for counselor</th><th></th></tr>{pills}</table></div>'
                   if pills else '<p class="note">No pill requests yet.</p>')

    recent = "".join(
        f"<tr><td>{E(short(r.get('updated_at'), 16))}</td><td>{E(short(r.get('name'), 20))}</td>"
        f"<td>{E({'fr': 'FR', 'en': 'EN'}.get(str(r.get('language')), ''))}</td><td>{E(short(r.get('category'), 40))}</td>"
        f"<td><span class=\"tag{' urgent' if r.get('status') == 'URGENT' else ''}\">{E(short(r.get('status'), 24))}</span></td>"
        f"<td>{E(short(r.get('last_step'), 16))}</td>"
        f"<td><a href=\"/dashboard/chat?phone={E(clean(r.get('phone'), ''))}\">chat</a></td></tr>" for r in s["recent"])

    imported_cards = ""
    if s["imported"]:
        imported_cards = f"""<h2 style="margin:22px 0 4px">Old records (imported)</h2><div class="grid">
{bars("By year", s["imported_year"])}{bars("By gender", s["imported_gender"])}
{bars("By age", s["imported_age"])}{bars("By town", s["imported_city"])}</div>"""

    return page("Aunty Queen dashboard", f"""
<header><h1>Aunty Queen · Dashboard</h1><p>Confidential. Do not share screenshots. <a href="/dashboard/logout">Log out</a></p></header>
<main>{msg}<div class="kpis">{kpis}</div>
<div class="grid">{bars("Conversations by month", s["by_month"])}{bars("What she needs", s["by_need"])}
{bars("Gender", s["by_gender"])}{bars("Age", s["by_age"])}{bars("Town / city (top 12)", s["by_city"])}
{bars("Language", s["by_language"])}{bars("How she heard of us", s["by_heard"])}{bars("Education", s["by_education"])}
{bars("Pill method chosen", s["by_method"])}{bars("Status", s["by_status"])}</div>

<div class="card" style="margin-top:12px"><h2>💊 Pill requests</h2>{pills_table}</div>
<div class="card" style="margin-top:12px"><h2>Recent conversations</h2><div class="wide"><table>
<tr><th>Updated</th><th>Name</th><th>Lang</th><th>Need</th><th>Status</th><th>Step</th><th></th></tr>{recent}</table></div></div>
{imported_cards}
<div class="grid">
<div class="card"><h2>⬆️ Import old data (Excel or CSV)</h2>
<p class="note">The first row must be column names. Columns like <i>date, gender, age, town, phone</i> are picked up for the stats and broadcast.</p>
<form class="inline" method="post" action="/dashboard/import" enctype="multipart/form-data">
<input type="file" name="file" accept=".xlsx,.csv" required><button type="submit">Upload</button></form></div>

<div class="card"><h2>📣 Discreet broadcast</h2>
<p class="note"><b>{audience_size}</b> people can receive it now: past contacts and imported numbers who did not reply STOP,
have not written in the last 7 days, and got no broadcast in the last 30 days.
WhatsApp only allows a template that Meta approved in Infobip (WhatsApp → Templates). Keep it neutral: nothing about abortion or pills.</p>
<form method="post" action="/dashboard/broadcast">
<p><label>Template name<br><input name="template" value="{E(template_default)}" placeholder="aunty_queen_checkin" required></label></p>
<p><label>Language<br><select name="language"><option value="en">English</option><option value="fr">French</option></select></label></p>
<p><label>Type <b>SEND {audience_size}</b> to confirm<br><input name="confirm" autocomplete="off" required></label></p>
<button type="submit">Send broadcast</button></form></div>
</div>
<p class="note" style="margin-top:20px">Data lives in the private Google Sheet (tabs: Intakes, Contacts, Messages, Imported).</p>
</main>""")


def chat_page(phone, messages, contact):
    rows = "".join(
        f'<div class="{E({"client": "in"}.get(m.get("direction", ""), m.get("direction", "")))}">'
        f'<small>{E(m.get("direction", ""))} · {E(short(m.get("time"), 19))}</small>{E(m.get("text", ""))}</div>'
        for m in messages)
    profile = ", ".join(f"{k}: {E(str(v))}" for k, v in (contact or {}).items()
                        if v and k in ("name", "age", "gender", "city", "education", "pregnancies_children",
                                       "heard_from", "language", "first_seen", "last_seen", "opted_out"))
    return page("Chat · Aunty Queen", f"""
<header><h1>Chat history</h1><p><a href="/dashboard">← Back to dashboard</a></p></header>
<main><div class="card"><p class="note">{profile or "No profile yet."}</p>
<div class="chat">{rows or '<p class="note">No messages saved yet.</p>'}</div></div></main>""")
