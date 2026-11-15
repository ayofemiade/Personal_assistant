"""Invoice drafts in Moyocode's own house style (modelled on Moyosore's invoices in the owner's invoice folder).

Rules:
- Moyo only CREATES DRAFTS (a PDF in the Invoices folder). It never sends or issues an invoice and never
  logs the money as earned. Moyosore reviews and sends it himself.
- Every amount comes from his request; totals, deposit and balance are calculated here, never by the AI.
- Missing amounts are an error, not a guess.
"""
from __future__ import annotations

import base64
import html
import json
import subprocess
import tempfile
from datetime import date, timedelta
from pathlib import Path

from moyo.db import DATA_DIR, get_setting, now_iso, rows, set_setting, today

SCHEMA = """
CREATE TABLE IF NOT EXISTS invoices (
    id INTEGER PRIMARY KEY,
    number TEXT NOT NULL UNIQUE,
    client TEXT NOT NULL,
    bill_to TEXT,
    issue_date TEXT NOT NULL,
    due_date TEXT,
    currency TEXT NOT NULL DEFAULT 'NGN',
    items TEXT NOT NULL,
    discount REAL NOT NULL DEFAULT 0,
    deposit_pct INTEGER,
    layout TEXT NOT NULL,
    notes TEXT,
    subtotal REAL NOT NULL,
    total REAL NOT NULL,
    status TEXT NOT NULL DEFAULT 'draft' CHECK (status IN ('draft','sent','paid','void')),
    pdf_path TEXT,
    created_at TEXT NOT NULL
);
"""

LOGO = DATA_DIR / "brand" / "mc-logo.jpg"


class InvoiceError(ValueError):
    pass


def ensure_schema(con) -> None:
    con.executescript(SCHEMA)


def profile(con) -> dict:
    return get_setting(con, "invoice_profile")


def money_str(v: float, currency: str = "NGN") -> str:
    sym = "₦" if currency.upper() == "NGN" else "$"
    s = f"{abs(v):,.2f}".rstrip("0").rstrip(".") if v % 1 else f"{abs(v):,.0f}"
    return f"{'- ' if v < 0 else ''}{sym}{s}"


def _num(v, what: str) -> float:
    if v is None or v == "":
        raise InvoiceError(f"I need the {what}. I won't guess amounts on an invoice.")
    if isinstance(v, str):
        from moyo.dates import parse_amount
        pa = parse_amount(v)
        if not pa:
            raise InvoiceError(f"I couldn't read the {what} \"{v}\".")
        v = pa[0]
    v = float(v)
    if v < 0:
        raise InvoiceError(f"The {what} can't be negative.")
    return v


def build(items: list, discount=0, deposit_pct=None, currency="NGN") -> dict:
    """Normalise line items and calculate totals (the only place totals are computed)."""
    if not items:
        raise InvoiceError("An invoice needs at least one item, e.g. \"Website development ₦150,000\".")
    out = []
    for it in items:
        if isinstance(it, str):
            it = {"description": it}
        desc = (it.get("description") or it.get("title") or "").strip()
        if not desc:
            raise InvoiceError("Every item needs a description.")
        qty = int(it.get("qty") or it.get("quantity") or 1)
        if qty < 1:
            raise InvoiceError("Quantity must be at least 1.")
        price = _num(it.get("amount", it.get("price")), f"amount for \"{desc}\"")
        out.append({"item": (it.get("item") or it.get("category") or "").strip(), "description": desc,
                    "qty": qty, "price": price, "amount": price * qty})
    subtotal = sum(i["amount"] for i in out)
    disc = _num(discount, "discount") if discount else 0.0
    if disc > subtotal:
        raise InvoiceError("The discount is bigger than the total.")
    total = subtotal - disc
    dep = None
    if deposit_pct not in (None, "", 0):
        dep = int(round(float(deposit_pct)))
        if not 1 <= dep <= 100:
            raise InvoiceError("The deposit must be between 1% and 100%.")
    return {"items": out, "subtotal": subtotal, "discount": disc, "total": total, "deposit_pct": dep,
            "deposit": round(total * dep / 100, 2) if dep else None,
            "balance": round(total - total * dep / 100, 2) if dep else None, "currency": currency.upper()}


def next_number(con) -> str:
    p = profile(con)
    n = int(p.get("next_number") or 1)
    used = {r["number"] for r in rows(con.execute("SELECT number FROM invoices"))}
    while f"{p.get('prefix', 'MC-')}{n:03d}" in used:
        n += 1
    return f"{p.get('prefix', 'MC-')}{n:03d}"


def _d(iso: str) -> str:
    return date.fromisoformat(iso).strftime("%d/%m/%y")  # his invoices use DD/MM/YY


def render_html(p: dict, inv: dict) -> str:
    e = html.escape
    cur = inv["currency"]
    m = lambda v: e(money_str(v, cur))  # noqa: E731
    logo = ""
    if LOGO.exists():
        logo = f'<img class="logo" alt="MC" src="data:image/jpeg;base64,{base64.b64encode(LOGO.read_bytes()).decode()}">'
    bill = "<br>".join(e(x) for x in [inv["client"], *(inv.get("bill_to") or "").splitlines()] if x.strip())
    contact = "".join(f"<div>{e(x)}</div>" for x in (p.get("phone"), p.get("email")) if x)
    meta = (f'<div class="lbl">INVOICE #</div><div>{e(inv["number"])}</div>'
            f'<div class="lbl">DATE</div><div>{_d(inv["issue_date"])}</div>'
            + (f'<div class="lbl">INVOICE DUE DATE</div><div>{_d(inv["due_date"])}</div>' if inv.get("due_date") else ""))
    t = inv["totals"]
    if inv["layout"] == "itemized":
        rows_html = "".join(
            f'<tr><td>{e(i["item"])}</td><td>{e(i["description"])}</td><td class="n">{i["qty"]}</td>'
            f'<td class="n">{m(i["price"])}</td><td class="n">{m(i["amount"])}</td></tr>' for i in t["items"])
        if t["discount"]:
            rows_html += (f'<tr class="sum"><td></td><td class="r">Total Project Value</td><td></td><td></td>'
                          f'<td class="n">{m(t["subtotal"])}</td></tr>'
                          f'<tr><td>Discount</td><td>Discount on Total Project Value</td><td></td>'
                          f'<td class="n">{m(-t["discount"])}</td><td class="n">{m(-t["discount"])}</td></tr>')
        rows_html += (f'<tr class="grand"><td></td><td class="r"><b>Total Payable</b></td><td></td>'
                      f'<td class="n"><b>TOTAL</b></td><td class="n"><b>{m(t["total"])}</b></td></tr>')
        table = ('<table class="items"><thead><tr><th>ITEMS</th><th>DESCRIPTION</th><th class="n">QUANTITY</th>'
                 f'<th class="n">PRICE</th><th class="n">AMOUNT</th></tr></thead><tbody>{rows_html}</tbody></table>')
    else:
        rows_html = "".join(f'<tr><td>{e(i["description"])}{f" (×{i["qty"]})" if i["qty"] > 1 else ""}</td>'
                            f'<td>{m(i["amount"])}</td></tr>' for i in t["items"])
        if t["discount"]:
            rows_html += f'<tr><td>Discount</td><td>{m(-t["discount"])}</td></tr>'
        rows_html += f'<tr><td>Total Contract Value</td><td>{m(t["total"])}</td></tr>'
        if t["deposit_pct"] and t["deposit_pct"] < 100:
            rows_html += f'<tr><td>Deposit Due ({t["deposit_pct"]}%)</td><td><b>{m(t["deposit"])}</b></td></tr>'
        table = f'<table class="simple"><thead><tr><th>Description</th><th>Amount</th></tr></thead><tbody>{rows_html}</tbody></table>'
    if t["deposit_pct"] and t["deposit_pct"] < 100:
        terms = (f'<p>Total Contract Value: {m(t["total"])}</p>'
                 f'<ul><li><b>{t["deposit_pct"]}% ({m(t["deposit"])})</b>: payable upon acceptance of this invoice and '
                 f'before commencement of the project.</li>'
                 f'<li><b>Remaining {100 - t["deposit_pct"]}% ({m(t["balance"])})</b>: payable upon successful completion '
                 f'and delivery of the project.</li></ul>')
    else:
        terms = f'<p>Full payment of {m(t["total"])} is due' + (
            f' by {_d(inv["due_date"])}.</p>' if inv.get("due_date") else ".</p>")
    notes = "".join(f"<li>{e(n)}</li>" for n in (inv.get("notes") or []))
    bank = p.get("bank") or {}
    bank_html = "".join(f"<div>{lbl}: {e(v)}</div>" for lbl, v in (
        ("Bank Name", bank.get("name")), ("Account Name", bank.get("account_name")), ("Account Number", bank.get("number"))) if v)
    return f"""<!doctype html><html><head><meta charset="utf-8"><title>Invoice {e(inv['number'])}</title><style>
@page {{ size: A4; margin: 0; }}
* {{ box-sizing: border-box; }}
body {{ margin: 0; font-family: Arial, Helvetica, sans-serif; color: #111; font-size: 13px; }}
.page {{ position: relative; min-height: 296mm; padding: 0 0 44px; }}
.bar {{ height: 38px; background: #147F91; }}
.head {{ display: flex; justify-content: space-between; padding: 26px 42px 12px; border-bottom: 3px solid #e3e3e3; }}
.logo {{ width: 52px; height: 52px; display: block; background: #000; }}
h1 {{ font-size: 48px; margin: 4px 0 0; font-weight: 700; letter-spacing: -.5px; }}
.biz {{ text-align: right; font-size: 13px; line-height: 1.8; }}
.biz b {{ font-size: 15px; }}
.meta {{ display: flex; justify-content: space-between; padding: 18px 42px 20px; border-bottom: 3px solid #e3e3e3; }}
.lbl {{ font-size: 10.5px; font-weight: 700; margin-top: 8px; }}
.bill .lbl {{ margin: 0 0 10px; }} .bill {{ font-size: 14px; line-height: 1.6; }}
.inv {{ text-align: right; line-height: 1.9; }}
table {{ border-collapse: collapse; margin: 26px 42px 6px; width: calc(100% - 84px); }}
.simple td, .simple th {{ border: 1px solid #222; padding: 10px 10px 16px; font-size: 17px; color: #444; text-align: left; vertical-align: top; width: 50%; }}
.simple th {{ font-size: 14px; color: #111; }}
.items th {{ font-size: 10.5px; text-align: left; padding: 8px 6px 12px; border-bottom: 1px solid #ddd; }}
.items td {{ padding: 7px 6px; font-size: 14px; vertical-align: top; }}
.items .n {{ text-align: right; }} .items .r {{ text-align: right; }}
.items tr.grand td {{ font-size: 18px; padding-top: 16px; }}
.section {{ padding: 6px 42px; }}
.section h2 {{ font-size: 19px; font-weight: 400; color: #444; margin: 12px 0 6px; }}
.section p, .section li {{ font-size: 15px; color: #333; line-height: 1.5; }}
.section ul {{ margin: 0; padding-left: 26px; }}
.pay div {{ line-height: 1.8; font-size: 14px; }} .pay h3 {{ font-size: 14px; margin: 12px 0 2px; }}
.foot {{ position: absolute; left: 0; right: 0; bottom: 0; background: #4F81BD; color: #fff; font-size: 14.5px; padding: 8px 76px; }}
</style></head><body><div class="page">
<div class="bar"></div>
<div class="head"><div>{logo}<h1>Invoice</h1></div>
<div class="biz"><b>{e(p.get('business', 'MOYOCODE'))}</b><div>{e(p.get('address', ''))}</div>{contact}</div></div>
<div class="meta"><div class="bill"><div class="lbl">BILL TO:</div>{bill}</div><div class="inv">{meta}</div></div>
{table}
<div class="section"><h2>Payment Terms</h2>{terms}</div>
{f'<div class="section"><h2>Notes</h2><ul>{notes}</ul></div>' if notes else ''}
<div class="section pay"><h3>Payment Information</h3>{bank_html}</div>
<div class="foot">{e(p.get('footer', ''))}</div>
</div></body></html>"""


def to_pdf(html_text: str, out: Path) -> Path:
    from moyo.workspaces import chrome
    exe = chrome()
    if not exe:
        raise InvoiceError("Chrome/Edge wasn't found, so I can't make the PDF.")
    out.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as d:
        src = Path(d) / "invoice.html"
        src.write_text(html_text, encoding="utf-8")
        subprocess.run([exe, "--headless=new", "--disable-gpu", "--no-pdf-header-footer", f"--user-data-dir={d}\\profile",
                        f"--print-to-pdf={out}", src.as_uri()], capture_output=True, timeout=60,
                       creationflags=0x08000000)
    if not out.exists() or out.stat().st_size < 1000:
        raise InvoiceError("Making the PDF failed.")
    return out


def create(con, client: str, items: list, discount=0, deposit_pct=None, due_days=None, bill_to=None,
           notes=None, currency="NGN", layout=None, issue_date: str | None = None, make_pdf: bool = True) -> dict:
    ensure_schema(con)
    client = (client or "").strip()
    if not client:
        raise InvoiceError("Who is the invoice for?")
    p = profile(con)
    t = build(items, discount, deposit_pct if deposit_pct is not None else p.get("default_deposit_pct"), currency)
    issued = issue_date or today().isoformat()
    dd = p.get("default_due_days", 30) if due_days is None else int(due_days)
    due = (date.fromisoformat(issued) + timedelta(days=dd)).isoformat() if dd else None
    if isinstance(notes, str):
        notes = [notes]
    lay = layout or ("itemized" if (t["discount"] or any(i["item"] or i["qty"] > 1 for i in t["items"])) else "simple")
    number = next_number(con)
    inv = {"number": number, "client": client, "bill_to": bill_to, "issue_date": issued, "due_date": due,
           "currency": t["currency"], "layout": lay, "notes": notes or [], "totals": t}
    pdf = None
    if make_pdf:
        safe = "".join(c for c in client if c.isalnum() or c in " -_").strip()[:40] or "client"
        pdf = to_pdf(render_html(p, inv), Path(p["save_dir"]) / f"Invoice {number} {safe}.pdf")
    con.execute("INSERT INTO invoices(number, client, bill_to, issue_date, due_date, currency, items, discount, deposit_pct, "
                "layout, notes, subtotal, total, status, pdf_path, created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,'draft',?,?)",
                (number, client, bill_to, issued, due, t["currency"], json.dumps(t["items"]), t["discount"], t["deposit_pct"],
                 lay, json.dumps(notes or []), t["subtotal"], t["total"], str(pdf) if pdf else None, now_iso()))
    set_setting(con, "invoice_profile", {**p, "next_number": int(number.split("-")[-1]) + 1})
    return {**inv, "pdf_path": str(pdf) if pdf else None}


def listing(con, limit: int = 20) -> list[dict]:
    ensure_schema(con)
    return rows(con.execute("SELECT id, number, client, issue_date, due_date, currency, total, deposit_pct, status, pdf_path "
                            "FROM invoices ORDER BY id DESC LIMIT ?", (limit,)))
