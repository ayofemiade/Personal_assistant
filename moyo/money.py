"""$10K challenge, earnings ledger and sales pipeline. All arithmetic is plain SQL/Python:
the AI never computes money."""
from __future__ import annotations

from datetime import date, timedelta

from moyo.db import get_setting, now_iso, rows, today
from moyo.dates import fmt_money

STAGE_PROB = {"new": 0.1, "contacted": 0.15, "engaged": 0.25, "discovery": 0.35, "proposal": 0.5, "negotiation": 0.7,
              "won": 1.0, "lost": 0.0, "nurture": 0.05}  # estimates (pipeline_stages table is the source)
OPEN_STAGES = ("new", "contacted", "engaged", "discovery", "proposal", "negotiation")


class MoneyError(ValueError):
    pass


def usd_rate_for(con, currency: str, rate: float | None = None) -> float:
    """USD per 1 unit of `currency`. NGN needs a rate Moyosore has set; Moyo never guesses."""
    currency = currency.upper()
    if currency == "USD":
        return 1.0
    if currency == "NGN":
        ngn_per_usd = rate or get_setting(con, "ngn_per_usd")
        if not ngn_per_usd:
            raise MoneyError("I need your naira-to-dollar rate first. Set it in Settings "
                             "(e.g. 'set rate 1500' means ₦1,500 = $1).")
        return 1.0 / float(ngn_per_usd)
    raise MoneyError(f"Unsupported currency {currency}. Use NGN or USD.")


def add_earning(con, amount: float, currency: str, client: str | None = None, earned_date: str | None = None,
                service: str | None = None, description: str | None = None, lead_id: int | None = None,
                paid: bool = False, ngn_per_usd: float | None = None) -> dict:
    if amount <= 0:
        raise MoneyError("Amount must be positive.")
    rate = usd_rate_for(con, currency, ngn_per_usd)
    d = earned_date or today().isoformat()
    cur = con.execute(
        "INSERT INTO earnings(earned_date, amount, currency, usd_rate, usd_amount, client, lead_id, service, "
        "description, payment_status, paid_date, created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
        (d, amount, currency.upper(), rate, round(amount * rate, 2), client, lead_id, service, description,
         "paid" if paid else "unpaid", d if paid else None, now_iso()))
    return dict(con.execute("SELECT * FROM earnings WHERE id=?", (cur.lastrowid,)).fetchone())


def challenge_status(con, ref: date | None = None) -> dict:
    ref = ref or today()
    c = get_setting(con, "challenge")
    start, end = date.fromisoformat(c["start"]), date.fromisoformat(c["end"])
    target = float(c["target_usd"])
    collected_basis = c.get("basis") == "collected"
    from moyo.revenue import ledger
    if collected_basis:  # D41: progress = money actually received in the challenge window (ledger + legacy rows)
        legacy = con.execute(
            "SELECT COALESCE(SUM(usd_amount),0) s, COUNT(*) n FROM earnings WHERE counts_toward_challenge=1 "
            "AND payment_status='paid' AND COALESCE(paid_date, earned_date) BETWEEN ? AND ?", (c["start"], c["end"])).fetchone()
        earned = {"s": legacy["s"] + ledger.collected_usd(con, c["start"], c["end"]),
                  "n": legacy["n"] + con.execute("SELECT COUNT(*) FROM ledger_payments WHERE received_date BETWEEN ? AND ?",
                                                 (c["start"], c["end"])).fetchone()[0]}
    else:  # older "earned" rule: earned entries + every payment received (money received is always earned)
        e = con.execute(
            "SELECT COALESCE(SUM(usd_amount),0) s, COUNT(*) n FROM earnings WHERE counts_toward_challenge=1 "
            "AND earned_date BETWEEN ? AND ?", (c["start"], c["end"])).fetchone()
        earned = {"s": e["s"] + ledger.collected_usd(con, c["start"], c["end"]), "n": e["n"]}
    collected = con.execute(
        "SELECT COALESCE(SUM(usd_amount),0) FROM earnings WHERE counts_toward_challenge=1 AND payment_status='paid' "
        "AND earned_date BETWEEN ? AND ?", (c["start"], c["end"])).fetchone()[0] + ledger.collected_usd(con, c["start"], c["end"])
    week_start = ref - timedelta(days=ref.weekday())
    this_week = con.execute(
        "SELECT COALESCE(SUM(usd_amount),0) FROM earnings WHERE counts_toward_challenge=1 AND "
        + ("payment_status='paid' AND COALESCE(paid_date, earned_date)" if collected_basis else "earned_date")
        + " BETWEEN ? AND ?", (week_start.isoformat(), ref.isoformat())).fetchone()[0] \
        + (ledger.collected_usd(con, week_start.isoformat(), ref.isoformat()) if collected_basis else 0)
    total_days = (end - start).days
    elapsed = min(max((ref - start).days, 0), total_days)
    days_left = max((end - ref).days, 0)
    remaining = max(target - earned["s"], 0)
    expected_by_now = target * elapsed / total_days if total_days else target
    weeks_left = days_left / 7
    pipe = pipeline_summary(con)
    return {
        "target_usd": target, "start": c["start"], "end": c["end"], "basis": c["basis"],
        "progress_word": "collected" if collected_basis else "earned",
        "earned_usd": round(earned["s"], 2), "entries": earned["n"],
        "collected_usd": round(collected, 2),
        "outstanding_usd": round(con.execute(
            "SELECT COALESCE(SUM(usd_amount),0) FROM earnings WHERE counts_toward_challenge=1 AND payment_status!='paid'"
        ).fetchone()[0] + ledger.owed(con, ref)["outstanding_usd_now"], 2) if collected_basis else round(earned["s"] - collected, 2),
        "remaining_usd": round(remaining, 2), "pct": round(min(earned["s"] / target * 100, 100), 1),
        "days_total": total_days, "days_elapsed": elapsed, "days_left": days_left,
        "expected_by_now_usd": round(expected_by_now, 2),
        "gap_vs_pace_usd": round(earned["s"] - expected_by_now, 2),
        "on_track": earned["s"] >= expected_by_now,
        "required_per_week_usd": round(remaining / weeks_left, 2) if weeks_left > 0 else remaining,
        "earned_this_week_usd": round(this_week, 2),
        "weighted_pipeline_usd": pipe["weighted_usd"],
        "pipeline_coverage": round(pipe["weighted_usd"] / remaining, 2) if remaining else None,
        "active": start <= ref <= end,
    }


# ---------------------------------------------------------------- leads / pipeline
# Since the Revenue Toolkit (D41) leads live in companies/contacts/deals (moyo/revenue/crm.py).
# These functions keep the old "lead" shape so the brief, coach, voice and commands keep working.
def _as_lead(con, d: dict) -> dict:
    from moyo.revenue import crm
    ch = crm.primary_channel(con, d.get("primary_contact_id"), ("whatsapp", "phone", "email"))
    return {"id": d["id"], "name": d["name"], "contact": ch, "service": d.get("service") or d.get("title"),
            "stage": d["stage_key"], "value": d["value"], "currency": d["currency"], "usd_rate": None,
            "probability": (d["probability_est"] or 0) / 100, "next_followup": d["next_action_due"],
            "next_action": d.get("next_action"), "notes": d.get("notes"), "source": d.get("source"),
            "created_at": d["created_at"], "updated_at": d["updated_at"], "is_open": d["is_open"],
            "company_id": d.get("company_id"), "contact_id": d.get("primary_contact_id"), "title": d.get("title")}


def all_leads(con, open_only: bool = False) -> list[dict]:
    from moyo.revenue import crm
    return [_as_lead(con, d) for d in crm.list_deals(con, open_only=open_only)]


def add_lead(con, name: str, service: str | None = None, value: float | None = None, currency: str = "USD",
             stage: str = "new", next_followup: str | None = None, contact: str | None = None,
             notes: str | None = None, source: str | None = None, actor: str = "user") -> dict:
    """Company (or person) + deal in one step. `contact` may be a phone or email."""
    from moyo.revenue import crm
    co = crm.get_or_create_company(con, name)
    cid = None
    if contact:
        kind = "email" if "@" in contact else "phone"
        ex = crm.find_contact_by_channel(con, kind, contact)
        cid = ex["id"] if ex else crm.create_contact(con, name, company_id=co["id"], **{kind: contact})["id"]
    d = crm.create_deal(con, f"{name} · {service}" if service else name, company_id=co["id"], contact_id=cid,
                        value=value, currency=currency or "NGN", stage_k=stage, service=service, source=source or "other",
                        next_action="Follow up" if next_followup else None, next_action_due=next_followup,
                        notes=notes, actor=actor)
    if next_followup:
        crm.sync_deal_followup(con, d["id"])
    return _as_lead(con, crm.get_deal(con, d["id"]))


def update_lead(con, lead_id: int, **fields) -> dict:
    from moyo.revenue import crm
    m = {"next_followup": "next_action_due"}
    f = {m.get(k, k): v for k, v in fields.items() if k in {"stage", "value", "currency", "probability",
                                                              "next_followup", "notes", "next_action"}}
    if "probability" in f and f["probability"] is not None and f["probability"] <= 1:
        f["probability"] = round(f["probability"] * 100)
    if f.get("next_action_due") and not f.get("next_action"):
        f["next_action"] = crm.get_deal(con, lead_id).get("next_action") or "Follow up"
    return _as_lead(con, crm.update_deal(con, lead_id, **f))


def find_lead(con, name: str) -> dict | None:
    from moyo.revenue import crm
    d = crm.find_deal(con, name)
    return _as_lead(con, d) if d else None


def lead_usd(con, lead: dict) -> float | None:
    if lead.get("value") is None:
        return None
    try:
        return lead["value"] * usd_rate_for(con, lead["currency"])
    except MoneyError:
        return None


def pipeline_summary(con, ref: date | None = None) -> dict:
    ref = ref or today()
    leads = all_leads(con)
    open_leads = [l for l in leads if l["is_open"]]
    weighted = unvalued = 0.0
    for l in open_leads:
        v = lead_usd(con, l)
        if v is None:
            unvalued += 1
        else:
            weighted += v * l["probability"]
    by_stage: dict = {}
    for l in leads:
        by_stage[l["stage"]] = by_stage.get(l["stage"], 0) + 1
    won = [l for l in leads if l["stage"] == "won"]
    won_vals = [v for v in (lead_usd(con, l) for l in won) if v is not None]
    due = [l for l in open_leads if l["next_followup"] and l["next_followup"] <= ref.isoformat()]
    return {
        "open": len(open_leads), "by_stage": by_stage, "weighted_usd": round(weighted, 2),
        "leads_without_value": int(unvalued),
        "avg_won_deal_usd": round(sum(won_vals) / len(won_vals), 2) if won_vals else None,
        "followups_due": [{"id": l["id"], "name": l["name"], "date": l["next_followup"],
                           "overdue": l["next_followup"] < ref.isoformat(), "stage": l["stage"]} for l in due],
        "neglected": [{"id": l["id"], "name": l["name"], "stage": l["stage"]} for l in open_leads
                      if not l["next_followup"]],
    }


def money_line(st: dict) -> str:
    return (f"{fmt_money(st['earned_usd'], 'USD')} of {fmt_money(st['target_usd'], 'USD')} earned "
            f"({st['pct']}%), {st['days_left']} days left, need {fmt_money(st['required_per_week_usd'], 'USD')}/week")
