"""Import past invoices (from before the $10K challenge) as HISTORY (D41 decision 3).

They create the client (company/contact), a historical won deal and a historical issued invoice with its lines.
Payment status is recorded as UNKNOWN (never assumed paid); they never count toward the $10K.
Used for: real average deal size, client list, renewal reminders, and "past client" outreach."""
from __future__ import annotations

from datetime import datetime

from moyo.db import now_iso
from moyo.revenue import crm


def import_invoice(con, rec: dict) -> dict:
    """rec = {number, date (YYYY-MM-DD), company, contact?, role?, bill_to?, currency, deposit_pct?, terms_note?,
              lines: [{description, amount, category?, kind?: service|discount}], source_file}"""
    number = f"{rec['number']} ({datetime.fromisoformat(rec['date']).strftime('%d/%m/%y')})"
    ex = con.execute("SELECT id FROM ledger_invoices WHERE number=?", (number,)).fetchone()
    if ex:
        return {"skipped": number}
    con.execute("SAVEPOINT hist")
    try:
        co = crm.get_or_create_company(con, rec["company"], source="import")
        cid = None
        if rec.get("contact"):
            same = [c for c in crm.find_contacts_by_name(con, rec["contact"]) if c["company_id"] == co["id"]]
            cid = same[0]["id"] if same else crm.create_contact(con, rec["contact"], company_id=co["id"], role=rec.get("role"),
                                                                 source="import")["id"]
        total = sum(round(l["amount"] * 100) for l in rec["lines"])
        d = crm.create_deal(con, rec.get("title") or f"{co['name']} · invoice {rec['number']}", company_id=co["id"],
                            contact_id=cid, value=total / 100, currency=rec.get("currency", "NGN"), stage_k="won",
                            source="past_client", notes=rec.get("terms_note"), actor="import", historical=True,
                            created_at=f"{rec['date']}T09:00:00")
        cur = con.execute("INSERT INTO ledger_invoices(number, deal_id, company_id, contact_id, bill_to, issue_date, currency, status, "
                          "issued_at, pdf_path, historical, payment_status_known, created_at) VALUES (?,?,?,?,?,?,?, 'issued', ?, ?, 1, 0, ?)",
                          (number, d["id"], co["id"], cid, rec.get("bill_to"), rec["date"], rec.get("currency", "NGN"),
                           f"{rec['date']}T09:00:00", rec.get("source_file"), now_iso()))
        inv_id = cur.lastrowid
        for i, l in enumerate(rec["lines"]):
            amt = round(l["amount"] * 100)
            con.execute("INSERT INTO ledger_invoice_lines(invoice_id, position, category, description, qty, unit_minor, amount_minor, kind) "
                        "VALUES (?,?,?,?,1,?,?,?)", (inv_id, i + 1, l.get("category"), l["description"], amt, amt,
                                                     l.get("kind") or ("discount" if amt < 0 else "service")))
        crm.log_activity(con, "invoice_sent", f"Past invoice {rec['number']} ({rec['date']}): ₦{total / 100:,.0f}. "
                         "Payment status not recorded in Moyo.", deal_id=d["id"], source="import",
                         occurred_at=f"{rec['date']}T09:00:00", external_id=f"hist-{number}")
        con.execute("RELEASE hist")
    except Exception:
        con.execute("ROLLBACK TO hist")
        con.execute("RELEASE hist")
        raise
    return {"imported": number, "deal_id": d["id"], "total": total / 100}
