"""Tool Gateway: the ONLY way anything (text parser, cloud model, later voice) changes data or the laptop.

Every action has a permission tier:
  read     – runs immediately, changes nothing
  low      – runs immediately, logged (tasks, leads, opening workspaces…)
  confirm  – Moyo asks first; runs only after Moyosore confirms (money, deletions, rates)
  (anything not registered is prohibited)
"""
from __future__ import annotations

import secrets
import time
from dataclasses import dataclass
from datetime import date
from typing import Callable

from moyo import audit, briefing, content, memory, money, planner, tasks, workspaces
from moyo.dates import fmt_money
from moyo.db import get_setting, set_setting, today


@dataclass
class Action:
    tier: str
    fn: Callable
    summary: Callable[..., str] | None = None


class ActionError(ValueError):
    pass


def _reply(text, data=None, **kw):
    return {"reply": text, "data": data, **kw}


def _due_text(d: str | None) -> str:
    if not d:
        return ""
    dd = date.fromisoformat(d)
    delta = (dd - today()).days
    return " for today" if delta == 0 else " for tomorrow" if delta == 1 else f" for {dd.strftime('%A %d %b')}"


# ---------------------------------------------------------------- handlers
def a_plan(con, **_):
    p = planner.build(con, now=__import__("datetime").datetime.now())
    lines = [f"{i + 1}. {t['title']} ({t['why']})" for i, t in enumerate(p["top3"])]
    txt = ("Your top priorities today:\n" + "\n".join(lines)) if lines else "You have no open tasks yet."
    return _reply(txt, p, view="today")


def a_briefing(con, **_):
    b = briefing.build(con)
    return _reply(b["text"], b, view="today")


def a_progress(con, **_):
    st = money.challenge_status(con)
    txt = (f"You've earned {fmt_money(st['earned_usd'], 'USD')} of {fmt_money(st['target_usd'], 'USD')} "
           f"({st['pct']}%). {fmt_money(st['remaining_usd'], 'USD')} to go in {st['days_left']} days, which is about "
           f"{fmt_money(st['required_per_week_usd'], 'USD')} a week. "
           + ("You're on pace." if st["on_track"] else
              f"You're {fmt_money(abs(st['gap_vs_pace_usd']), 'USD')} behind the straight-line pace.")
           + f" Weighted pipeline: {fmt_money(st['weighted_pipeline_usd'], 'USD')}.")
    return _reply(txt, st, view="money")


def a_add_task(con, title, due=None, due_time=None, priority=3, category=None, recurrence=None,
               estimate_min=45, lead=None, **_):
    lead_id = None
    if lead:
        l = money.find_lead(con, lead)
        lead_id = l["id"] if l else None
    t = tasks.add(con, title, due_date=due, due_time=due_time, priority=int(priority), category=category,
                  recurrence=recurrence, estimate_min=int(estimate_min), lead_id=lead_id)
    rec = f", repeating {t['recurrence']}" if t["recurrence"] else ""
    return _reply(f"Added task #{t['id']}: \"{t['title']}\"{_due_text(t['due_date'])}"
                  f"{' at ' + t['due_time'] if t['due_time'] else ''} ({t['category']}{rec}).", t, view="tasks")


def _resolve_task(con, task_id=None, task=None) -> dict:
    if task_id:
        return tasks.get(con, int(task_id))
    if task:
        found = tasks.find(con, task)
        if not found:
            raise ActionError(f"I couldn't find an open task matching \"{task}\".")
        return found[0]
    raise ActionError("Which task? Give its number or some words from its title.")


def a_complete(con, task_id=None, task=None, **_):
    t = _resolve_task(con, task_id, task)
    r = tasks.complete(con, t["id"])
    nxt = f" Next one scheduled{_due_text(r['next']['due_date'])}." if r["next"] else ""
    return _reply(f"Done: \"{t['title']}\".{nxt}", r, view="tasks")


def a_move(con, new_date, task_id=None, task=None, **_):
    t = _resolve_task(con, task_id, task)
    u = tasks.update(con, t["id"], due_date=new_date)
    return _reply(f"Moved \"{u['title']}\"{_due_text(new_date)}.", u, view="tasks")


def a_add_lead(con, name, service=None, value=None, currency="USD", stage="new", followup=None, **_):
    l = money.add_lead(con, name, service=service, value=float(value) if value else None,
                       currency=currency or "USD", stage=stage, next_followup=followup)
    v = f", worth {fmt_money(l['value'], l['currency'])}" if l["value"] else ""
    return _reply(f"New lead #{l['id']}: {l['name']}{' (' + service + ')' if service else ''}{v}, stage {l['stage']}."
                  + (f" Follow-up{_due_text(followup)}." if followup else " When should you follow up?"),
                  l, view="money")


def a_update_lead(con, name, stage=None, followup=None, value=None, **_):
    l = money.find_lead(con, name)
    if not l:
        raise ActionError(f"No lead matching \"{name}\".")
    fields = {k: v for k, v in (("stage", stage), ("next_followup", followup), ("value", value)) if v is not None}
    u = money.update_lead(con, l["id"], **fields)
    bits = []
    if stage:
        bits.append(f"stage → {stage}")
    if followup:
        bits.append(f"follow-up{_due_text(followup)}")
    if value:
        bits.append(f"value → {fmt_money(float(value), u['currency'])}")
    return _reply(f"Updated {u['name']}: {', '.join(bits) or 'no changes'}.", u, view="money")


def s_payment(con, amount, currency="NGN", client=None, earned_date=None, paid=False, invoice=None, method=None,
              reference=None, **_):
    if paid:  # money received → the ledger (it may settle an invoice)
        from moyo.revenue import ledger
        try:
            inv_id = _invoice_by_number(con, invoice)["id"] if invoice else None
            return ledger.summary_payment(con, amount, currency or "NGN", client, earned_date, inv_id, method, reference)
        except ledger.LedgerError as e:
            return f"I can't record this yet: {e}"
    cur = (currency or "NGN").upper()
    extra = ""
    if cur == "NGN":
        rate = get_setting(con, "ngn_per_usd")
        extra = f" ≈ {fmt_money(float(amount) / rate, 'USD')} at ₦{rate:,.0f}/$" if rate else " (no ₦/$ rate set yet!)"
    return (f"Log {fmt_money(float(amount), cur)}{extra} earned"
            f"{' from ' + client if client else ''}{' on ' + earned_date if earned_date else ' today'}"
            f"{', already paid' if paid else ', not yet paid'}?")


def a_payment(con, amount, currency="NGN", client=None, earned_date=None, paid=False, service=None, invoice=None,
              method=None, reference=None, **_):
    if paid:
        from moyo.revenue import ledger
        try:
            inv_id = _invoice_by_number(con, invoice)["id"] if invoice else None
            p = ledger.record_payment(con, amount, currency or "NGN", client, earned_date, inv_id, method or "bank_transfer", reference)
        except ledger.LedgerError as e:
            raise ActionError(str(e))
        st = money.challenge_status(con)
        settled = ", ".join(f"{a['number']}" for a in p["allocations"])
        return _reply(f"Recorded {fmt_money(p['amount'], p['currency'])} received"
                      + (f", settling {settled}" if settled else "") + f". Collected so far: {fmt_money(st['earned_usd'], 'USD')} "
                      f"of {fmt_money(st['target_usd'], 'USD')}.", {"payment_id": p["id"]}, view="money")
    lead = money.find_lead(con, client) if client else None
    e = money.add_earning(con, float(amount), currency or "NGN", client=client, earned_date=earned_date,
                          service=service, lead_id=None, paid=bool(paid))  # deals live in the revenue tables now
    if lead:
        from moyo.revenue import crm
        crm.log_activity(con, "payment", f"Payment logged: {fmt_money(e['amount'], e['currency'])}"
                         + (" (paid)" if paid else " (not yet paid)"), deal_id=lead["id"])
    st = money.challenge_status(con)
    return _reply(f"Logged {fmt_money(e['amount'], e['currency'])} (= {fmt_money(e['usd_amount'], 'USD')}). "
                  f"Challenge total: {fmt_money(st['earned_usd'], 'USD')} of {fmt_money(st['target_usd'], 'USD')}.",
                  e, view="money")


def a_log_post(con, platform, title=None, **_):
    p = content.log_post(con, platform, title=title)
    st = content.status(con)
    return _reply(f"Logged your {content.LABEL[p['platform']]} post for today. Daily streak: {st['daily_streak']} day(s).",
                  p, view="today")


def a_memory_list(con, **_):
    return _reply(memory.summary_text(con), memory.listing(con), view="memory")


def a_remember(con, content_text, kind="fact", category="general", valid_until=None, **_):
    m = memory.add(con, content_text, category=category, kind=kind, valid_until=valid_until)
    return _reply(f"Noted ({m['kind']}): {m['content']}", m, view="memory")


def s_forget(con, memory_id=None, about=None, **_):
    m = _resolve_memory(con, memory_id, about)
    return f"Forget this permanently? \"{m['content']}\""


def _resolve_memory(con, memory_id=None, about=None):
    if memory_id:
        r = con.execute("SELECT * FROM memory WHERE id=?", (int(memory_id),)).fetchone()
        if r:
            return dict(r)
    if about:
        found = memory.search(con, about)
        if found:
            return found[0]
    raise ActionError(f"I don't have anything stored about \"{about or memory_id}\".")


def a_forget(con, memory_id=None, about=None, **_):
    m = _resolve_memory(con, memory_id, about)
    memory.delete(con, m["id"])
    return _reply(f"Forgotten: \"{m['content']}\"", m, view="memory")


def s_rate(con, ngn_per_usd, **_):
    return f"Set the exchange rate to ₦{float(ngn_per_usd):,.0f} = $1 for new entries?"


def a_rate(con, ngn_per_usd, **_):
    v = float(ngn_per_usd)
    if not 100 <= v <= 100000:
        raise ActionError("That rate looks wrong. Give naira per dollar, e.g. 1500.")
    set_setting(con, "ngn_per_usd", v)
    return _reply(f"Exchange rate set: ₦{v:,.0f} = $1. Past entries keep the rate they were logged with.", v)


def a_workspace(con, profile, **_):
    r = workspaces.launch(profile)
    opened = [a["name"] for a in r["apps"]] + ([f"{len(r['urls'])} browser tab(s)"] if r["urls"] else []) + \
             (["your Spotify playlist"] if r["music"] else [])
    warn = (" Note: " + " ".join(r["problems"])) if r["problems"] else ""
    return _reply(f"{r['label']}: opening {', '.join(opened) or 'nothing (profile is empty)'}.{warn}", r)


def a_media(con, action, times=1, **_):
    workspaces.media(action, int(times))
    return _reply({"play_pause": "Toggled play/pause.", "next": "Next track.", "previous": "Previous track.",
                   "volume_up": "Volume up.", "volume_down": "Volume down.", "mute": "Toggled mute."}[action])


def a_content_status(con, **_):
    from moyo import social
    st = content.status(con)
    t = st["today"]
    txt = (f"Today: TikTok {'✓ posted' if t['tiktok'] else '✗ not yet'}, Instagram {'✓ posted' if t['instagram'] else '✗ not yet'}. "
           f"LinkedIn this week: {st['linkedin_this_week']}/{st['linkedin_target']}. Streak: {st['daily_streak']} day(s).")
    if social.ig_connected() or social.tt_connected():
        lines = content.performance_sentences(content.performance(con))
        txt += ("\nYesterday: " + " ".join(lines)) if lines else "\nNo posts with stats from yesterday yet."
        txt += "\nFull 7-day breakdown in the Content tab."
    else:
        txt += " Connect Instagram/TikTok in Settings to see views, likes and comments."
    return _reply(txt, st, view="content")


def a_coach(con, **_):
    from moyo import coach
    c = coach.generate(con)
    return _reply(coach.speech_text(c) or "I don't have enough data to coach you yet. Add tasks and leads first.",
                  c, view="today")


def a_calendar(con, day=None, **_):
    from moyo import google_api
    if not google_api.connected():
        return _reply("Google Calendar isn't connected. Connect it in Settings → Google.", view="settings")
    d = date.fromisoformat(day) if day else today()
    evs = google_api.events_on(con, d)
    label = "today" if d == today() else "tomorrow" if (d - today()).days == 1 else d.strftime("%A %d %b")
    if not evs:
        return _reply(f"Nothing on your Google Calendar {label}.", evs, view="today")
    lines = [f"• {'All day' if e['all_day'] else e['start'][11:16] + '–' + e['end'][11:16]}  {e['title']}"
             + (f" ({e['location']})" if e["location"] else "") for e in evs]
    return _reply(f"Your calendar {label}:\n" + "\n".join(lines), evs, view="today")


def a_inbox(con, **_):
    from moyo import google_api
    if not google_api.connected():
        return _reply("Gmail isn't connected. Connect it in Settings → Google.", view="settings")
    ib = google_api.inbox(con)
    txt = f"{ib['unread_24h']} unread email(s) in the last 24 hours."
    if ib["from_leads"]:
        txt += "\nFrom leads/clients:\n" + "\n".join(f"• {e['from_name']}: {e['subject']}" for e in ib["from_leads"][:5])
    elif ib["important"]:
        txt += " None from leads or clients. Most recent personal mail:\n" + "\n".join(
            f"• {e['from_name']}: {e['subject']}" for e in ib["important"][:5])
    else:
        txt += " Nothing from leads, clients or people. Just promotions and notifications."
    return _reply(txt + "\nOpen any email from the Inbox card on Today.", ib, view="today")


def a_start_day(con, **_):
    from moyo import routine
    r = routine.start(con)
    return _reply(r["reply"], r, view="today", read_briefing=r["read_briefing"])


def a_list_tasks(con, **_):
    ov = tasks.overview(con)
    def fmt(ts): return "; ".join(f"#{t['id']} {t['title']}" for t in ts[:6]) or "none"
    return _reply(f"Overdue: {fmt(ov['overdue'])}\nToday: {fmt(ov['today'])}\nThis week: {fmt(ov['upcoming'])}",
                  ov, view="tasks")


def a_create_invoice(con, client, items, discount=0, deposit_pct=None, due_days=None, bill_to=None, notes=None,
                     currency="NGN", layout=None, **_):
    """Creates a DRAFT PDF only. Never sends it and never logs money as earned."""
    import os

    from moyo import invoices
    from moyo.revenue import crm, ledger
    deal = crm.find_deal(con, client) if client else None
    try:
        inv = ledger.create_draft(con, client, items, discount, deposit_pct, due_days, bill_to, notes, currency, layout,
                                  deal_id=_["deal_id"] if _.get("deal_id") else (deal["id"] if deal else None))
    except (invoices.InvoiceError, ledger.LedgerError, crm.CRMError) as e:
        raise ActionError(str(e))
    m = lambda v: invoices.money_str(v, inv["currency"])  # noqa: E731
    dep = inv.get("deposit_pct")
    msg = (f"Draft invoice {inv['number']} for {inv['client']}: total {m(inv['total'])}"
           + (f", {dep}% deposit {m(inv['total'] * dep / 100)}" if dep and dep < 100 else "")
           + ". It's saved for you to review. I haven't sent it to anyone. When you send it, mark it as sent in Revenue → Money.")
    if inv["pdf_path"] and os.environ.get("MOYO_NO_BACKGROUND") != "1":
        try:
            os.startfile(inv["pdf_path"])  # show the draft
        except OSError:
            pass
    return _reply(msg, {k: inv[k] for k in ("id", "number", "client", "pdf_path", "due_date", "total")}, view="money")


def a_list_invoices(con, **_):
    from moyo import invoices
    from moyo.revenue import ledger
    inv = ledger.listing(con, include_historical=False, limit=8)
    if not inv:
        return _reply("No invoices yet. Say e.g. \"create an invoice for Kemi Stores, website development 450,000 naira, 50% deposit\".")
    return _reply("Recent invoices: " + "; ".join(
        f"{i['number']} {i['client']} {invoices.money_str(i['total'], i['currency'])} ({i['state'].replace('_', ' ')}"
        + (f", {invoices.money_str(i['balance'], i['currency'])} still owed" if i['state'] in ('issued', 'part_paid', 'overdue') else "")
        + ")" for i in inv) + ".", [{k: i[k] for k in ("id", "number", "client", "total", "balance", "state")} for i in inv],
        view="money")


def _invoice_by_number(con, number):
    from moyo.revenue import ledger
    n = str(number or "").strip().upper()
    if n and not n.startswith("MC-") and n.isdigit():
        n = f"MC-{int(n):03d}"
    r = con.execute("SELECT id FROM ledger_invoices WHERE upper(number)=?", (n,)).fetchone()
    if not r:
        raise ActionError(f"I can't find invoice {number}.")
    return ledger.get(con, r["id"])


def s_issue(con, number, **_):
    from moyo.revenue import ledger
    return ledger.summary_issue(con, _invoice_by_number(con, number)["id"])


def a_issue(con, number, **_):
    from moyo.revenue import ledger
    try:
        inv = ledger.issue(con, _invoice_by_number(con, number)["id"])
    except ledger.LedgerError as e:
        raise ActionError(str(e))
    return _reply(f"Invoice {inv['number']} is marked as sent. I'll remind you if it's unpaid after {inv['due_date']}.",
                  {"id": inv["id"]}, view="money")


def s_void(con, number, reason, **_):
    inv = _invoice_by_number(con, number)
    return f"Void invoice {inv['number']} for {inv['client']}? Reason: {reason}. It stays on record as void."


def a_void(con, number, reason, **_):
    from moyo.revenue import ledger
    try:
        inv = ledger.void(con, _invoice_by_number(con, number)["id"], reason)
    except ledger.LedgerError as e:
        raise ActionError(str(e))
    return _reply(f"Invoice {inv['number']} is void.", {"id": inv["id"]}, view="money")


def s_refund(con, payment_id, amount, reason, **_):
    from moyo.revenue import ledger
    p = ledger.payment(con, int(payment_id))
    return (f"Record a refund of {fmt_money(float(amount), p['currency'])} on the {fmt_money(p['amount'], p['currency'])} "
            f"payment from {p['payer_label'] or p['company'] or 'this payer'} ({p['received_date']})? Reason: {reason}. "
            "This reduces your collected total.")


def a_refund(con, payment_id, amount, reason, **_):
    from moyo.revenue import ledger
    try:
        ledger.refund(con, int(payment_id), amount, reason)
    except ledger.LedgerError as e:
        raise ActionError(str(e))
    return _reply("Refund recorded.", view="money")


def s_reverse(con, payment_id, reason, **_):
    from moyo.revenue import ledger
    p = ledger.payment(con, int(payment_id))
    return (f"Cancel the payment entry of {fmt_money(p['amount'], p['currency'])} on {p['received_date']} as a MISTAKE? "
            f"Reason: {reason}. It stays on record but stops counting. (If money was actually returned, use a refund instead.)")


def a_reverse(con, payment_id, reason, **_):
    from moyo.revenue import ledger
    try:
        ledger.reverse_payment(con, int(payment_id), reason)
    except ledger.LedgerError as e:
        raise ActionError(str(e))
    return _reply("That payment entry is cancelled.", view="money")


def a_money_owed(con, **_):
    from moyo import invoices
    from moyo.revenue import ledger
    o = ledger.owed(con)
    if not o["invoices"]:
        return _reply("Nobody owes you money right now (no unpaid sent invoices).", o, view="money")
    lines = [f"{i['client']}: {invoices.money_str(i['balance'], i['currency'])} on {i['number']}"
             + (" (overdue)" if i in o["overdue"] else f", due {i['due_date']}") for i in o["invoices"][:8]]
    return _reply("Money owed to you:\n" + "\n".join(lines), {"count": len(o["invoices"])}, view="money")


# ---------------------------------------------------------------- Revenue Toolkit (Phase 1)
def _deal_or_error(con, name):
    from moyo.revenue import crm
    d = crm.find_deal(con, name or "")
    if not d:
        raise ActionError(f"I couldn't find a deal for \"{name}\". Say \"new lead …\" to add it.")
    return d


def s_capture(con, **f):
    from moyo.revenue import capture
    return capture.summary_text(capture.normalize(f))


def a_capture(con, **f):
    from moyo.revenue import capture, crm
    try:
        r = capture.commit(con, {k: v for k, v in capture.normalize(f).items() if k != "ai_fields"})
    except crm.DuplicateError as e:
        raise ActionError(str(e))
    except crm.CRMError as e:
        raise ActionError(str(e))
    d = r["deal"]
    msg = f"Saved: {d['title']} ({d['stage_label']})"
    if r["reused_contact"]:
        msg += f". I linked it to {r['reused_contact']}, who was already in Moyo"
    msg += f". Next: {d['next_action']} on {d['next_action_due']}." if d["next_action_due"] else ". It has no next step yet: when should you follow up?"
    return _reply(msg, {"deal_id": d["id"]}, view="money")


def a_who_to_contact(con, **_):
    from moyo.revenue import followups
    items = followups.today_list(con)
    if not items:
        return _reply("Nobody needs a follow-up today. Good time to add new leads or reach out to past clients.", [], view="money")
    lines = [f"{i + 1}. {it['name']}: {it['reasons'][0]}" + (f" (next: {it['next_action']})" if it.get("next_action") else "")
             for i, it in enumerate(items[:5])]
    return _reply(f"{len(items)} to contact today:\n" + "\n".join(lines), items, view="money")


def a_followed_up(con, name, note=None, channel=None, next_date=None, next_action=None, **_):
    from moyo.revenue import followups
    d = _deal_or_error(con, name)
    u = followups.done(con, d["id"], note=note, channel=channel, next_due=next_date, next_action=next_action)
    return _reply(f"Logged the follow-up with {d['name']}." + (f" Next step on {u['next_action_due']}." if u["next_action_due"]
                  else " When's the next step?"), {"deal_id": d["id"]}, view="money")


def a_move_deal(con, name, stage, lost_reason=None, **_):
    from moyo.revenue import crm
    d = _deal_or_error(con, name)
    try:
        u = crm.move_stage(con, d["id"], stage, lost_reason=lost_reason)
    except crm.CRMError as e:
        raise ActionError(str(e))
    extra = " Winning a deal doesn't record money: log the payment when it arrives." if u["stage_key"] == "won" else ""
    return _reply(f"{d['name']} moved to {u['stage_label']}.{extra}", {"deal_id": d["id"]}, view="money")


def a_next_step(con, name, next_action, date, **_):
    from moyo.revenue import crm
    d = _deal_or_error(con, name)
    u = crm.update_deal(con, d["id"], next_action=next_action, next_action_due=date)
    return _reply(f"Next step for {d['name']}: {u['next_action']} on {u['next_action_due']}.", {"deal_id": d["id"]}, view="money")


def a_deal_note(con, name, note, **_):
    from moyo.revenue import crm
    d = _deal_or_error(con, name)
    crm.log_activity(con, "note", note, deal_id=d["id"])
    return _reply(f"Noted on {d['name']}.", {"deal_id": d["id"]}, view="money")


def a_draft_followup(con, name, channel="whatsapp", goal=None, **_):
    from moyo.revenue import outreach
    d = _deal_or_error(con, name)
    dr = outreach.draft(con, d["id"], channel or "whatsapp", goal)
    tail = "" if (dr["wa_link"] or dr["gmail_link"]) else " (No phone or email saved for them yet.)"
    return _reply(f"Draft for {d['name']}:\n\n{dr['text']}\n\nOpen it from the Revenue page to send it yourself.{tail}",
                  dr, view="money")


REGISTRY: dict[str, Action] = {
    "capture_lead": Action("confirm", a_capture, s_capture),   # facts only after you confirm the card
    "who_to_contact": Action("read", a_who_to_contact),
    "followed_up": Action("low", a_followed_up),
    "move_deal": Action("low", a_move_deal),
    "set_next_step": Action("low", a_next_step),
    "deal_note": Action("low", a_deal_note),
    "draft_followup": Action("read", a_draft_followup),        # a draft only; you send it
    "create_invoice": Action("low", a_create_invoice),   # draft file only; sending is always Moyosore's
    "list_invoices": Action("read", a_list_invoices),
    "issue_invoice": Action("confirm", a_issue, s_issue),      # YOU sent it; Moyo never sends
    "void_invoice": Action("confirm", a_void, s_void),
    "refund_payment": Action("confirm", a_refund, s_refund),
    "reverse_payment": Action("confirm", a_reverse, s_reverse),
    "money_owed": Action("read", a_money_owed),
    "get_daily_plan": Action("read", a_plan),
    "get_briefing": Action("read", a_briefing),
    "get_target_progress": Action("read", a_progress),
    "get_content_status": Action("read", a_content_status),
    "list_tasks": Action("read", a_list_tasks),
    "get_coaching": Action("read", a_coach),
    "get_calendar": Action("read", a_calendar),
    "start_day": Action("low", a_start_day),
    "get_inbox": Action("read", a_inbox),
    "what_do_you_know": Action("read", a_memory_list),
    "add_task": Action("low", a_add_task),
    "complete_task": Action("low", a_complete),
    "move_task": Action("low", a_move),
    "add_lead": Action("low", a_add_lead),
    "update_lead": Action("low", a_update_lead),
    "log_post": Action("low", a_log_post),
    "remember": Action("low", a_remember),
    "open_workspace": Action("low", a_workspace),
    "media": Action("low", a_media),
    "log_payment": Action("confirm", a_payment, s_payment),
    "forget": Action("confirm", a_forget, s_forget),
    "set_rate": Action("confirm", a_rate, s_rate),
}

PENDING: dict[str, dict] = {}
PENDING_TTL = 600


def execute(con, name: str, args: dict, actor: str = "user") -> dict:
    act = REGISTRY.get(name)
    if not act:
        audit.log(con, actor, name, "prohibited", args, "refused")
        return _reply(f"I'm not allowed to do \"{name}\".", error=True)
    try:
        if act.tier == "confirm":
            summary = act.summary(con, **args)
            pid = secrets.token_urlsafe(8)
            PENDING[pid] = {"name": name, "args": args, "actor": actor, "ts": time.time(), "summary": summary}
            audit.log(con, actor, name, act.tier, args, "awaiting confirmation")
            return _reply(summary, needs_confirmation=True, pending_id=pid, action=name)
        out = act.fn(con, **args)
        if act.tier != "read":
            audit.log(con, actor, name, act.tier, args)
        return {**out, "action": name}
    except (ActionError, tasks.TaskError, money.MoneyError, workspaces.WorkspaceError, ValueError, TypeError) as e:
        audit.log(con, actor, name, act.tier, args, f"error: {e}")
        return _reply(str(e), error=True, action=name)


def confirm(con, pid: str, accept: bool) -> dict:
    p = PENDING.pop(pid, None)
    if not p or time.time() - p["ts"] > PENDING_TTL:
        return _reply("That request expired. Please ask again.", error=True)
    act = REGISTRY[p["name"]]
    if not accept:
        audit.log(con, p["actor"], p["name"], act.tier, p["args"], "cancelled by user")
        return _reply("Cancelled. Nothing was changed.", action=p["name"])
    try:
        out = act.fn(con, **p["args"])
        audit.log(con, p["actor"], p["name"], act.tier, p["args"], "confirmed + done")
        return {**out, "action": p["name"]}
    except (ActionError, money.MoneyError, ValueError, TypeError) as e:
        audit.log(con, p["actor"], p["name"], act.tier, p["args"], f"error: {e}")
        return _reply(str(e), error=True, action=p["name"])
