"""Renewals: recurring revenue you've already earned once (hosting, domains, maintenance plans).

From sent (and historical) invoice lines that look recurring, the next renewal date is the latest such invoice
for that client + kind, plus a year (or a month for monthly plans). Nothing is invoiced automatically: Moyo
reminds you ahead of time so you can ask the client."""
from __future__ import annotations

import re
from datetime import date, timedelta

from moyo.db import rows, today

KINDS = [  # (kind, regex on the line description, period days)
    ("hosting", r"\b(hosting|domain|ssl)\b", 365),
    ("maintenance", r"\b(maintenance|support|retainer)\b.*\b(annual|yearly|1\s*-?\s*year|year)\b|\b(annual|yearly)\b.*\bmaintenance\b", 365),
    ("maintenance_monthly", r"\b(maintenance|support|retainer)\b.*\bmonthly\b|\bmonthly\b.*\b(maintenance|support|retainer)\b", 30),
]


def _kind(desc: str) -> tuple[str, int] | None:
    d = (desc or "").lower()
    for k, rx, period in KINDS:
        if re.search(rx, d):
            return k, period
    return None


def upcoming(con, ref: date | None = None, within_days: int = 365) -> list[dict]:
    ref = ref or today()
    latest: dict = {}
    for r in rows(con.execute(
            "SELECT i.id, i.number, i.issue_date, i.company_id, co.name AS company, l.description, l.amount_minor, i.currency "
            "FROM ledger_invoice_lines l JOIN ledger_invoices i ON i.id=l.invoice_id LEFT JOIN companies co ON co.id=i.company_id "
            "WHERE i.status='issued' AND l.kind!='discount'")):
        k = _kind(r["description"])
        if not k or not r["company_id"]:
            continue
        key = (r["company_id"], k[0])
        if key not in latest or r["issue_date"] > latest[key]["issue_date"]:
            latest[key] = {**r, "kind": k[0], "period": k[1]}
    out = []
    for (cid, kind), r in latest.items():
        due = date.fromisoformat(r["issue_date"]) + timedelta(days=r["period"])
        days = (due - ref).days
        if -60 <= days <= within_days:
            out.append({"company_id": cid, "company": r["company"], "kind": kind.replace("_", " "), "last_invoice": r["number"],
                        "last_date": r["issue_date"], "description": r["description"], "due": due.isoformat(), "days": days,
                        "last_amount": r["amount_minor"] / 100 if r["amount_minor"] > 0 else None, "currency": r["currency"]})
    return sorted(out, key=lambda x: x["due"])
