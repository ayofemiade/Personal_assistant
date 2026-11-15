"""Money ledger (Phase 2): invoices, payments, allocations, refunds, corrections.

Rules (docs/revenue/REVENUE_TOOLKIT_DATA_MODEL.md):
- Integer minor units + original currency; each issued invoice / payment / refund snapshots the ₦/$ rate.
- Append-only: issued invoices and payments are never edited or deleted. Voids, refunds and reversals are new rows
  (refunds/adjustments) with a reason; only DRAFT invoices can change.
- Paid / part-paid / overdue are DERIVED here (one function), never stored.
- The $10K (D41) counts money received: Σ active payments − refunds in the challenge window.
- Moyo never sends an invoice: "issue" means YOU sent it (confirm tier)."""
from __future__ import annotations

import json
from datetime import date, timedelta

from moyo.db import get_setting, now_iso, rows, set_setting, today
from moyo.revenue import crm


class LedgerError(ValueError):
    pass


EXTRA_INVOICE_COLS = (("client_label", "TEXT"), ("deposit_pct", "INTEGER"), ("layout", "TEXT"), ("notes", "TEXT"),
                      ("proposal_id", "INTEGER"))


def ensure_columns(con) -> None:
    have = {r[1] for r in con.execute("PRAGMA table_info(ledger_invoices)")}
    for col, typ in EXTRA_INVOICE_COLS:
        if col not in have:
            con.execute(f"ALTER TABLE ledger_invoices ADD COLUMN {col} {typ}")


def fx(con, currency: str) -> tuple[float | None, callable]:
    """(ngn_per_usd snapshot, to_usd_minor(minor))."""
    cur = currency.upper()
    if cur == "USD":
        return None, (lambda m: m)
    if cur == "NGN":
        rate = get_setting(con, "ngn_per_usd")
        if not rate:
            raise LedgerError("I need your ₦/$ rate first (Settings → Money), so I never guess a conversion.")
        return float(rate), (lambda m: int(round(m / float(rate))))
    raise LedgerError(f"Unsupported currency {currency}.")


# ---------------------------------------------------------------- invoices
def _tx(con, name: str):
    class T:
        def __enter__(self):
            con.execute(f"SAVEPOINT {name}")

        def __exit__(self, et, e, tb):
            if et:
                con.execute(f"ROLLBACK TO {name}")
            con.execute(f"RELEASE {name}")
            return False
    return T()


def resolve_company(con, client: str | None, deal_id: int | None) -> tuple[int | None, int | None, str]:
    if deal_id:
        d = crm.get_deal(con, deal_id)
        return d["company_id"], d["primary_contact_id"], d["name"]
    name = (client or "").strip()
    if not name:
        raise LedgerError("Who is it for?")
    co = crm.find_company(con, name)
    if not co:
        co = crm.get_or_create_company(con, name)
    return co["id"], None, co["name"]


def create_draft(con, client: str | None, items: list, discount=0, deposit_pct=None, due_days=None, bill_to=None,
                 notes=None, currency="NGN", layout=None, deal_id: int | None = None, proposal_id: int | None = None,
                 make_pdf: bool = True) -> dict:
    from moyo import invoices as ui  # house-style renderer + totals (validated, never guessed)
    ensure_columns(con)
    p = ui.profile(con)
    t = ui.build(items, discount, deposit_pct if deposit_pct is not None else p.get("default_deposit_pct"), currency)
    company_id, contact_id, label = resolve_company(con, client, deal_id)
    if client and client.strip() and client.strip() != label and not deal_id:
        label = client.strip()
    issued = today().isoformat()
    dd = p.get("default_due_days", 30) if due_days is None else int(due_days)
    due = (date.fromisoformat(issued) + timedelta(days=dd)).isoformat() if dd else None
    notes = [notes] if isinstance(notes, str) else (notes or [])
    lay = layout or ("itemized" if (t["discount"] or any(i["item"] or i["qty"] > 1 for i in t["items"])) else "simple")
    number = next_number(con)
    with _tx(con, "inv_draft"):
        cur = con.execute("INSERT INTO ledger_invoices(number, deal_id, company_id, contact_id, bill_to, issue_date, due_date, currency, "
                          "status, client_label, deposit_pct, layout, notes, proposal_id, created_at) "
                          "VALUES (?,?,?,?,?,?,?,?, 'draft', ?,?,?,?,?,?)",
                          (number, deal_id, company_id, contact_id, bill_to, issued, due, t["currency"], label, t["deposit_pct"],
                           lay, json.dumps(notes), proposal_id, now_iso()))
        iid = cur.lastrowid
        for i, it in enumerate(t["items"]):
            con.execute("INSERT INTO ledger_invoice_lines(invoice_id, position, category, description, qty, unit_minor, amount_minor, kind) "
                        "VALUES (?,?,?,?,?,?,?, 'service')", (iid, i + 1, it["item"] or None, it["description"], it["qty"],
                                                              round(it["price"] * 100), round(it["amount"] * 100)))
        if t["discount"]:
            con.execute("INSERT INTO ledger_invoice_lines(invoice_id, position, description, qty, unit_minor, amount_minor, kind) "
                        "VALUES (?,?, 'Discount on total project value', 1, ?, ?, 'discount')",
                        (iid, len(t["items"]) + 1, -round(t["discount"] * 100), -round(t["discount"] * 100)))
        set_setting(con, "invoice_profile", {**p, "next_number": int(number.split("-")[-1]) + 1})
        if deal_id:
            crm.log_activity(con, "note", f"Invoice {number} drafted ({ui.money_str(t['total'], t['currency'])})", deal_id=deal_id)
    if make_pdf:
        render_pdf(con, iid)
    return get(con, iid)


def next_number(con) -> str:
    from moyo import invoices as ui
    p = ui.profile(con)
    n = int(p.get("next_number") or 1)
    used = {r[0] for r in con.execute("SELECT number FROM ledger_invoices")}
    if con.execute("SELECT name FROM sqlite_master WHERE name='invoices'").fetchone():  # Phase-1 drafts
        used |= {r[0] for r in con.execute("SELECT number FROM invoices")}
    while f"{p.get('prefix', 'MC-')}{n:03d}" in used:
        n += 1
    return f"{p.get('prefix', 'MC-')}{n:03d}"


def lines(con, iid: int) -> list[dict]:
    return rows(con.execute("SELECT * FROM ledger_invoice_lines WHERE invoice_id=? ORDER BY position", (iid,)))


def _reversed_payments(con) -> set[int]:
    return {r[0] for r in con.execute("SELECT target_id FROM ledger_adjustments WHERE target_table='ledger_payments' "
                                      "AND field='reversed'")}


def get(con, iid: int) -> dict:
    ensure_columns(con)
    r = con.execute("SELECT i.*, co.name AS company FROM ledger_invoices i LEFT JOIN companies co ON co.id=i.company_id "
                    "WHERE i.id=?", (iid,)).fetchone()
    if not r:
        raise LedgerError("Invoice not found.")
    inv = dict(r)
    ls = lines(con, iid)
    total = sum(l["amount_minor"] for l in ls)
    rev = _reversed_payments(con)
    allocs = [a for a in rows(con.execute("SELECT a.*, p.received_date, p.method, p.reference FROM ledger_allocations a "
                                          "JOIN ledger_payments p ON p.id=a.payment_id WHERE a.invoice_id=?", (iid,)))
              if a["payment_id"] not in rev]
    paid = sum(a["amount_minor"] for a in allocs)
    inv.update(lines=ls, total_minor=total, paid_minor=paid, balance_minor=max(total - paid, 0), allocations=allocs,
               total=total / 100, paid=paid / 100, balance=max(total - paid, 0) / 100,
               notes=json.loads(inv["notes"]) if inv.get("notes") else [],
               client=inv.get("client_label") or inv.get("company") or "")
    inv["state"] = state(inv)
    return inv


def state(inv: dict, ref: date | None = None) -> str:
    """draft | issued | part_paid | paid | overdue | void | historical. Derived, never stored."""
    ref = ref or today()
    if inv["status"] == "void":
        return "void"
    if inv["status"] == "draft":
        return "draft"
    if inv.get("historical") and not inv.get("payment_status_known", 1):
        return "historical"
    if inv["total_minor"] > 0 and inv["paid_minor"] >= inv["total_minor"]:
        return "paid"
    if inv["due_date"] and inv["due_date"] < ref.isoformat():
        return "overdue"
    return "part_paid" if inv["paid_minor"] else "issued"


def listing(con, include_historical: bool = True, limit: int = 200) -> list[dict]:
    ensure_columns(con)
    q = "SELECT id FROM ledger_invoices" + ("" if include_historical else " WHERE historical=0") + " ORDER BY issue_date DESC, id DESC LIMIT ?"
    return [get(con, r[0]) for r in con.execute(q, (limit,))]


def render_pdf(con, iid: int) -> str:
    from pathlib import Path

    from moyo import invoices as ui
    inv = get(con, iid)
    p = ui.profile(con)
    items = [{"item": l["category"] or "", "description": l["description"], "qty": l["qty"], "price": l["unit_minor"] / 100,
              "amount": l["amount_minor"] / 100} for l in inv["lines"] if l["kind"] != "discount"]
    disc = -sum(l["amount_minor"] for l in inv["lines"] if l["kind"] == "discount") / 100
    t = ui.build(items, disc, inv.get("deposit_pct"), inv["currency"])
    view = {"number": inv["number"], "client": inv["client"], "bill_to": inv.get("bill_to"), "issue_date": inv["issue_date"],
            "due_date": inv["due_date"], "currency": inv["currency"], "layout": inv.get("layout") or "simple",
            "notes": inv["notes"], "totals": t}
    safe = "".join(c for c in inv["client"] if c.isalnum() or c in " -_").strip()[:40] or "client"
    out = ui.to_pdf(ui.render_html(p, view), Path(p["save_dir"]) / f"Invoice {inv['number']} {safe}.pdf")
    con.execute("UPDATE ledger_invoices SET pdf_path=? WHERE id=?", (str(out), iid))
    return str(out)


def summary_issue(con, iid: int) -> str:
    from moyo import invoices as ui
    inv = get(con, iid)
    return (f"Mark invoice {inv['number']} ({ui.money_str(inv['total'], inv['currency'])} for {inv['client']}) as SENT to the client? "
            f"Only do this once you've actually sent it. It then counts as money owed to you, due {inv['due_date'] or 'on receipt'}.")


def issue(con, iid: int, actor: str = "user") -> dict:
    inv = get(con, iid)
    if inv["status"] != "draft":
        raise LedgerError(f"Invoice {inv['number']} is already {inv['status']}.")
    if inv["total_minor"] <= 0:
        raise LedgerError("An invoice must total more than zero.")
    rate, _ = fx(con, inv["currency"])
    with _tx(con, "inv_issue"):
        con.execute("UPDATE ledger_invoices SET status='issued', issued_at=?, fx_ngn_per_usd=? WHERE id=? AND status='draft'",
                    (now_iso(), rate, iid))
        if inv["deal_id"]:
            from moyo import invoices as ui
            crm.log_activity(con, "invoice_sent", f"Invoice {inv['number']} sent: {ui.money_str(inv['total'], inv['currency'])}, "
                             f"due {inv['due_date'] or 'on receipt'}", deal_id=inv["deal_id"], source=actor)
    return get(con, iid)


def void(con, iid: int, reason: str, actor: str = "user") -> dict:
    inv = get(con, iid)
    if not (reason or "").strip():
        raise LedgerError("Voiding needs a reason (it stays on record).")
    if inv["status"] == "void":
        raise LedgerError("Already void.")
    if inv["paid_minor"]:
        raise LedgerError("This invoice has payments against it. Refund or reverse them first.")
    with _tx(con, "inv_void"):
        con.execute("UPDATE ledger_invoices SET status='void', void_reason=? WHERE id=?", (reason.strip(), iid))
        con.execute("INSERT INTO ledger_adjustments(target_table, target_id, field, old_value, new_value, reason, actor, at) "
                    "VALUES ('ledger_invoices', ?, 'status', ?, 'void', ?, ?, ?)", (iid, inv["status"], reason.strip(), actor, now_iso()))
    return get(con, iid)


def update_draft(con, iid: int, **f) -> dict:
    """Only drafts can change: replace lines/terms, then re-render."""
    inv = get(con, iid)
    if inv["status"] != "draft":
        raise LedgerError("Issued invoices can't be edited. Void it (with a reason) and create a new one.")
    from moyo import invoices as ui
    items = f.get("items")
    with _tx(con, "inv_upd"):
        if items is not None:
            t = ui.build(items, f.get("discount", 0), f.get("deposit_pct", inv.get("deposit_pct")), inv["currency"])
            con.execute("DELETE FROM ledger_invoice_lines WHERE invoice_id=?", (iid,))
            for i, it in enumerate(t["items"]):
                con.execute("INSERT INTO ledger_invoice_lines(invoice_id, position, category, description, qty, unit_minor, amount_minor, kind) "
                            "VALUES (?,?,?,?,?,?,?, 'service')", (iid, i + 1, it["item"] or None, it["description"], it["qty"],
                                                                  round(it["price"] * 100), round(it["amount"] * 100)))
            if t["discount"]:
                con.execute("INSERT INTO ledger_invoice_lines(invoice_id, position, description, qty, unit_minor, amount_minor, kind) "
                            "VALUES (?,?, 'Discount on total project value', 1, ?, ?, 'discount')",
                            (iid, len(t["items"]) + 1, -round(t["discount"] * 100), -round(t["discount"] * 100)))
        for k in ("due_date", "bill_to", "deposit_pct"):
            if k in f:
                con.execute(f"UPDATE ledger_invoices SET {k}=? WHERE id=?", (f[k], iid))
    render_pdf(con, iid)
    return get(con, iid)


# ---------------------------------------------------------------- payments
def open_invoices(con, company_id: int | None) -> list[dict]:
    if not company_id:
        return []
    ids = [r[0] for r in con.execute("SELECT id FROM ledger_invoices WHERE company_id=? AND status='issued' AND historical=0 "
                                     "ORDER BY due_date IS NULL, due_date, issue_date, id", (company_id,))]
    return [i for i in (get(con, x) for x in ids) if i["balance_minor"] > 0]


def plan_allocation(con, amount_minor: int, currency: str, company_id: int | None, invoice_id: int | None) -> list[tuple[int, int]]:
    """FIFO across the client's open invoices in the SAME currency (or one named invoice)."""
    targets = [get(con, invoice_id)] if invoice_id else open_invoices(con, company_id)
    out, left = [], amount_minor
    for inv in targets:
        if left <= 0:
            break
        if inv["currency"] != currency.upper() or inv["status"] != "issued" or inv["balance_minor"] <= 0:
            continue
        take = min(left, inv["balance_minor"])
        out.append((inv["id"], take))
        left -= take
    return out


def summary_payment(con, amount, currency="NGN", client=None, received_date=None, invoice_id=None, method=None, reference=None,
                    deal_id=None) -> str:
    from moyo import invoices as ui
    amt = round(float(amount) * 100)
    company_id = None
    name = client or ""
    if deal_id:
        d = crm.get_deal(con, deal_id)
        company_id, name = d["company_id"], d["name"]
    elif client:
        co = crm.find_company(con, client)
        company_id = co["id"] if co else None
    rate, to_usd = fx(con, currency)
    plan = plan_allocation(con, amt, currency, company_id, invoice_id)
    parts = [f"Record {ui.money_str(amt / 100, currency)} RECEIVED" + (f" from {name}" if name else "")
             + f" on {received_date or today().isoformat()}" + (f" (≈ ${to_usd(amt) / 100:,.2f} at ₦{rate:,.0f}/$)" if rate else "") + "?"]
    for iid, take in plan:
        inv = get(con, iid)
        parts.append(f"It settles {ui.money_str(take / 100, currency)} of invoice {inv['number']} (balance "
                     f"{ui.money_str(inv['balance'], inv['currency'])}).")
    left = amt - sum(t for _, t in plan)
    if left > 0:
        parts.append(f"{ui.money_str(left / 100, currency)} isn't matched to an invoice: it's kept as credit for {name or 'this payer'}.")
    parts.append("This counts toward your $10K.")
    return " ".join(parts)


def record_payment(con, amount, currency="NGN", client=None, received_date=None, invoice_id=None, method="bank_transfer",
                   reference=None, deal_id=None, actor="user", external_id=None) -> dict:
    amt = round(float(amount) * 100)
    if amt <= 0:
        raise LedgerError("The amount must be more than zero.")
    when = received_date or today().isoformat()
    date.fromisoformat(when)
    if when > today().isoformat():
        raise LedgerError("A payment can't be received in the future.")
    company_id, contact_id, name = (None, None, (client or "").strip())
    if deal_id or client:
        company_id, contact_id, name = resolve_company(con, client, deal_id)
    if invoice_id:
        inv = get(con, invoice_id)
        company_id = company_id or inv["company_id"]
        if inv["status"] != "issued":
            raise LedgerError(f"Invoice {inv['number']} is {inv['status']}: only sent (issued) invoices take payments.")
    rate, to_usd = fx(con, currency)
    plan = plan_allocation(con, amt, currency, company_id, invoice_id)
    with _tx(con, "pay"):
        cur = con.execute("INSERT INTO ledger_payments(received_date, amount_minor, currency, method, reference, payer_label, contact_id, "
                          "company_id, fx_ngn_per_usd, usd_minor, external_id, created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                          (when, amt, currency.upper(), method or "bank_transfer", reference, name or None, contact_id, company_id,
                           rate, to_usd(amt), external_id, now_iso()))
        pid = cur.lastrowid
        for iid, take in plan:
            con.execute("INSERT INTO ledger_allocations(payment_id, invoice_id, amount_minor, created_at) VALUES (?,?,?,?)",
                        (pid, iid, take, now_iso()))
        deal_ids = {deal_id} | {get(con, i)["deal_id"] for i, _ in plan}
        from moyo import invoices as ui
        for did in [x for x in deal_ids if x]:
            crm.log_activity(con, "payment", f"Payment received: {ui.money_str(amt / 100, currency)}"
                             + (f" (ref {reference})" if reference else ""), deal_id=did, source=actor)
    return payment(con, pid)


def payment(con, pid: int) -> dict:
    r = con.execute("SELECT p.*, co.name AS company FROM ledger_payments p LEFT JOIN companies co ON co.id=p.company_id WHERE p.id=?",
                    (pid,)).fetchone()
    if not r:
        raise LedgerError("Payment not found.")
    p = dict(r)
    p["allocations"] = rows(con.execute("SELECT a.invoice_id, a.amount_minor, i.number FROM ledger_allocations a "
                                        "JOIN ledger_invoices i ON i.id=a.invoice_id WHERE a.payment_id=?", (pid,)))
    p["refunded_minor"] = con.execute("SELECT COALESCE(SUM(amount_minor),0) FROM ledger_refunds WHERE payment_id=?", (pid,)).fetchone()[0]
    p["reversed"] = pid in _reversed_payments(con)
    p["unallocated_minor"] = 0 if p["reversed"] else p["amount_minor"] - sum(a["amount_minor"] for a in p["allocations"])
    p["amount"] = p["amount_minor"] / 100
    return p


def payments(con, limit: int = 200) -> list[dict]:
    return [payment(con, r[0]) for r in con.execute("SELECT id FROM ledger_payments ORDER BY received_date DESC, id DESC LIMIT ?", (limit,))]


def refund(con, pid: int, amount, reason: str, refund_date: str | None = None, actor="user") -> dict:
    p = payment(con, pid)
    amt = round(float(amount) * 100)
    if not (reason or "").strip():
        raise LedgerError("A refund needs a reason.")
    if p["reversed"]:
        raise LedgerError("That payment entry was reversed.")
    if amt <= 0 or amt > p["amount_minor"] - p["refunded_minor"]:
        raise LedgerError("The refund can't be more than what's left of the payment.")
    rate, to_usd = fx(con, p["currency"])
    when = refund_date or today().isoformat()
    with _tx(con, "refund"):
        con.execute("INSERT INTO ledger_refunds(payment_id, date, amount_minor, reason, fx_ngn_per_usd, usd_minor, created_at) "
                    "VALUES (?,?,?,?,?,?,?)", (pid, when, amt, reason.strip(), rate, to_usd(amt), now_iso()))
    return payment(con, pid)


def reverse_payment(con, pid: int, reason: str, actor="user") -> dict:
    """For a payment logged BY MISTAKE (typo, duplicate). The row stays; an adjustment marks it reversed and
    its allocations stop counting. Money actually returned to a client is a refund, not a reversal."""
    p = payment(con, pid)
    if not (reason or "").strip():
        raise LedgerError("Say why (e.g. 'entered twice').")
    if p["reversed"]:
        raise LedgerError("Already reversed.")
    con.execute("INSERT INTO ledger_adjustments(target_table, target_id, field, old_value, new_value, reason, actor, at) "
                "VALUES ('ledger_payments', ?, 'reversed', 'active', 'reversed', ?, ?, ?)", (pid, reason.strip(), actor, now_iso()))
    return payment(con, pid)


# ---------------------------------------------------------------- totals (the $10K and money owed)
def collected_usd(con, start: str, end: str) -> float:
    """Money received in [start, end] in USD at each payment's own rate, minus refunds dated in the window."""
    rev = _reversed_payments(con)
    pay = sum(r["usd_minor"] or 0 for r in rows(con.execute(
        "SELECT id, usd_minor FROM ledger_payments WHERE received_date BETWEEN ? AND ?", (start, end))) if r["id"] not in rev)
    ref = con.execute("SELECT COALESCE(SUM(usd_minor),0) FROM ledger_refunds WHERE date BETWEEN ? AND ?", (start, end)).fetchone()[0]
    return (pay - ref) / 100


def owed(con, ref: date | None = None) -> dict:
    ref = ref or today()
    invs = [i for i in listing(con, include_historical=False) if i["status"] == "issued" and i["balance_minor"] > 0]
    by_cur: dict = {}
    over: dict = {}
    for i in invs:
        by_cur[i["currency"]] = by_cur.get(i["currency"], 0) + i["balance"]
        if state(i, ref) == "overdue":
            over[i["currency"]] = over.get(i["currency"], 0) + i["balance"]
    usd = 0.0
    for c, v in by_cur.items():
        try:
            _, to_usd = fx(con, c)
            usd += to_usd(round(v * 100)) / 100
        except LedgerError:
            pass
    return {"invoices": invs, "outstanding_by_currency": by_cur, "overdue_by_currency": over, "outstanding_usd_now": round(usd, 2),
            "overdue": [i for i in invs if state(i, ref) == "overdue"]}


def migrate_legacy_invoices(con) -> int:
    """Phase-1 `invoices` drafts → ledger drafts (same number, same PDF)."""
    if not con.execute("SELECT name FROM sqlite_master WHERE name='invoices'").fetchone():
        return 0
    ensure_columns(con)
    n = 0
    for r in rows(con.execute("SELECT * FROM invoices")):
        if con.execute("SELECT 1 FROM ledger_invoices WHERE number=?", (r["number"],)).fetchone():
            continue
        co = crm.get_or_create_company(con, r["client"], source="import")
        cur = con.execute("INSERT INTO ledger_invoices(number, company_id, bill_to, issue_date, due_date, currency, status, pdf_path, "
                          "client_label, deposit_pct, layout, notes, created_at) VALUES (?,?,?,?,?,?, 'draft', ?,?,?,?,?,?)",
                          (r["number"], co["id"], r["bill_to"], r["issue_date"], r["due_date"], r["currency"], r["pdf_path"],
                           r["client"], r["deposit_pct"], r["layout"], r["notes"], r["created_at"]))
        iid = cur.lastrowid
        items = json.loads(r["items"] or "[]")
        for i, it in enumerate(items):
            con.execute("INSERT INTO ledger_invoice_lines(invoice_id, position, category, description, qty, unit_minor, amount_minor, kind) "
                        "VALUES (?,?,?,?,?,?,?, 'service')", (iid, i + 1, it.get("item") or None, it["description"], it.get("qty", 1),
                                                              round(it["price"] * 100), round(it["amount"] * 100)))
        if r["discount"]:
            con.execute("INSERT INTO ledger_invoice_lines(invoice_id, position, description, qty, unit_minor, amount_minor, kind) "
                        "VALUES (?,?, 'Discount on total project value', 1, ?, ?, 'discount')",
                        (iid, len(items) + 1, -round(r["discount"] * 100), -round(r["discount"] * 100)))
        n += 1
    return n
