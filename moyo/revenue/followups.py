"""'Who to contact today': rule-based, explainable prioritisation (no AI ranking).

An open deal is on today's list if its next step is due/overdue, it has gone cold for its stage
(stale_after_days: Contacted 3, Proposal 4, Negotiation 2… D41), or it has no next step at all.
Score = value + stage + overdue + cold + promise + missing-next-step, each shown as a reason."""
from __future__ import annotations

import json
import math
from datetime import date, timedelta

from moyo.db import now_iso, rows, today
from moyo.revenue import crm

TOUCH_KINDS = ("note", "call", "meeting", "message_in", "message_out", "email_in", "email_out", "proposal_sent",
               "invoice_sent", "payment", "commitment")
DISMISS_DAYS = 7
REASON_ORDER = ["due", "waiting", "promise", "cold", "no_step", "value", "stage"]


def _usd(con, d: dict) -> float | None:
    if d["value"] is None:
        return None
    from moyo import money
    try:
        return d["value"] * money.usd_rate_for(con, d["currency"])
    except money.MoneyError:
        return None


def last_touch(con, deal_id: int) -> tuple[str | None, str | None]:
    """(last touch of any kind, last inbound message/email)."""
    r = con.execute(f"SELECT MAX(occurred_at) t FROM activities WHERE deal_id=? AND kind IN ({','.join('?' * len(TOUCH_KINDS))}) "
                    "AND NOT (kind='note' AND source='import')",  # bookkeeping from an import isn't contact
                    (deal_id, *TOUCH_KINDS)).fetchone()
    i = con.execute("SELECT MAX(occurred_at) t FROM activities WHERE deal_id=? AND kind IN ('message_in','email_in')",
                    (deal_id,)).fetchone()
    return r["t"], i["t"]


def _dismissed_recently(con, deal_id: int, ref: date) -> bool:
    r = con.execute("SELECT created_at FROM recommendations WHERE kind='followup' AND subject_table='deals' AND subject_id=? "
                    "AND status IN ('dismissed') ORDER BY id DESC LIMIT 1", (deal_id,)).fetchone()
    return bool(r) and (ref - date.fromisoformat(r["created_at"][:10])).days < DISMISS_DAYS


def evaluate(con, d: dict, ref: date) -> dict | None:
    """Returns a today-item for an open deal, or None if nothing is needed today."""
    if not d["is_open"] or d.get("historical"):
        return None
    reasons, score = [], 0.0
    due = d["next_action_due"]
    overdue = (ref - date.fromisoformat(due)).days if due else None
    touch, inbound = last_touch(con, d["id"])
    since = crm.days_since(touch or d["created_at"], ref)
    stale_limit = d["stale_after_days"]
    cold = stale_limit is not None and since is not None and since >= stale_limit
    no_step = not due
    due_now = due is not None and overdue >= 0
    if not (due_now or cold or no_step):
        return None
    if _dismissed_recently(con, d["id"], ref) and not due_now:
        return None
    usd = _usd(con, d)
    if usd:
        v = min(30.0, 6 * math.log10(max(usd, 1)))       # $100 → 12, $1,000 → 18, $10,000 → 24
        score += v
        reasons.append(("value", round(v, 1), f"Worth {crm.from_minor(d['value_minor']):,.0f} {d['currency']}"))
    p = d["probability_est"] or 0
    score += p * 0.3
    reasons.append(("stage", round(p * 0.3, 1), f"{d['stage_label']} (≈{p}% estimate)"))
    if due_now:
        o = min(25.0, 10 + overdue * 5)
        score += o
        reasons.append(("due", o, "Next step due today" if overdue == 0 else f"Next step {overdue} day{'s' if overdue > 1 else ''} overdue"))
    if cold:
        c = min(15.0, (since - stale_limit + 1) * 3)
        score += c
        reasons.append(("cold", c, f"No contact for {since} days (limit for this stage: {stale_limit})"))
    promise = con.execute("SELECT reason FROM follow_ups WHERE deal_id=? AND status='open' AND created_by IN ('ai','commitment') "
                          "AND confirmed=1 AND due_date<=? LIMIT 1", (d["id"], ref.isoformat())).fetchone()
    if promise:
        score += 10
        reasons.append(("promise", 10, f"You promised: {promise['reason']}"))
    if inbound and (not touch or inbound >= touch):
        score += 8
        reasons.append(("waiting", 8, "They messaged last: they're waiting on you"))
    if no_step:
        score += 5
        reasons.append(("no_step", 5, "No next step set"))
    return {"deal_id": d["id"], "name": d["name"], "title": d["title"], "contact": d["contact"],
            "contact_id": d["primary_contact_id"], "stage": d["stage_key"], "stage_label": d["stage_label"],
            "value": d["value"], "currency": d["currency"], "next_action": d["next_action"], "next_action_due": due,
            "last_touch": touch, "days_since_touch": since, "score": round(score, 1),
            # actionable reasons first (why today), then the context (value, stage)
            "reasons": [r[2] for r in sorted(reasons, key=lambda x: REASON_ORDER.index(x[0]))],
            "factors": {k: v for k, v, _ in reasons},
            "channels": {"whatsapp": crm.primary_channel(con, d["primary_contact_id"], ("whatsapp", "phone")),
                         "email": crm.primary_channel(con, d["primary_contact_id"], ("email",))}}


def today_list(con, ref: date | None = None, limit: int = 20) -> list[dict]:
    ref = ref or today()
    items = [i for i in (evaluate(con, d, ref) for d in crm.list_deals(con, open_only=True)) if i]
    return sorted(items, key=lambda i: -i["score"])[:limit]


# ---------------------------------------------------------------- actions on an item
def done(con, deal_id: int, note: str | None = None, channel: str | None = None, next_due: str | None = None,
         next_action: str | None = None, actor: str = "user") -> dict:
    d = crm.get_deal(con, deal_id)
    crm.log_activity(con, "message_out" if channel in ("whatsapp", "email") else "note",
                     note or f"Followed up{' on ' + channel if channel else ''}", deal_id=deal_id, channel=channel,
                     direction="out" if channel else None, source=actor)
    con.execute("UPDATE follow_ups SET status='done', updated_at=? WHERE deal_id=? AND status IN ('open','snoozed') "
                "AND due_date<=?", (now_iso(), deal_id, today().isoformat()))
    return crm.update_deal(con, deal_id, next_action_due=next_due, next_action=next_action or (d["next_action"] if next_due else None),
                           actor=actor)


def snooze(con, deal_id: int, days: int = 1, actor: str = "user") -> dict:
    d = crm.get_deal(con, deal_id)
    new = (today() + timedelta(days=max(1, int(days)))).isoformat()
    crm.log_activity(con, "note", f"Snoozed follow-up to {new}", deal_id=deal_id, source=actor)
    return crm.update_deal(con, deal_id, next_action_due=new, next_action=d["next_action"] or "Follow up", actor=actor)


def reschedule(con, deal_id: int, due: str, next_action: str | None = None, actor: str = "user") -> dict:
    date.fromisoformat(due)
    d = crm.get_deal(con, deal_id)
    return crm.update_deal(con, deal_id, next_action_due=due, next_action=next_action or d["next_action"] or "Follow up",
                           actor=actor)


def dismiss(con, deal_id: int, reason: str, actor: str = "user") -> None:
    if not (reason or "").strip():
        raise crm.CRMError("Tell me why, so I can learn what to stop suggesting.")
    con.execute("INSERT INTO recommendations(kind, subject_table, subject_id, title, status, feedback, created_at) "
                "VALUES ('followup','deals',?, 'Follow-up suggestion', 'dismissed', ?, ?)", (deal_id, reason.strip(), now_iso()))
    crm.log_activity(con, "note", f"Dismissed today's follow-up suggestion: {reason.strip()}", deal_id=deal_id, source=actor)


def brief_lines(con, ref: date | None = None, n: int = 3) -> list[str]:
    items = today_list(con, ref)
    if not items:
        return []
    top = "; ".join(f"{i['name']} ({i['reasons'][0].lower()})" for i in items[:n])
    return [f"{len(items)} deal{'s' if len(items) != 1 else ''} need{'s' if len(items) == 1 else ''} attention today. "
            f"Start with: {top}."]


def as_json(items: list[dict]) -> str:
    return json.dumps(items, default=str)
