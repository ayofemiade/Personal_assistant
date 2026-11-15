"""Morning briefing built only from stored data. Missing data is stated, never invented."""
from __future__ import annotations

from datetime import datetime

from moyo import content, money, planner, tasks
from moyo.dates import fmt_money
from moyo.db import today


def greeting(now: datetime) -> str:
    h = now.hour
    return "Good morning" if h < 12 else "Good afternoon" if h < 17 else "Good evening"


def build(con, now: datetime | None = None) -> dict:
    now = now or datetime.now()
    ref = today()
    ch = money.challenge_status(con, ref)
    pipe = money.pipeline_summary(con, ref)
    tv = tasks.overview(con, ref)
    cs = content.status(con, ref)
    plan = planner.build(con, ref, now)
    parts = [f"{greeting(now)}, Moyosore. Here's what you need to know for {ref.strftime('%A, %d %B')}."]

    # $10K
    pace = "on pace" if ch["on_track"] else f"{fmt_money(abs(ch['gap_vs_pace_usd']), 'USD')} behind the straight-line pace"
    parts.append(
        f"Ten-K challenge: {fmt_money(ch['earned_usd'], 'USD')} {ch.get('progress_word', 'earned')} of {fmt_money(ch['target_usd'], 'USD')}, "
        f"{ch['days_left']} days left. You're {pace}. To finish, you need about "
        f"{fmt_money(ch['required_per_week_usd'], 'USD')} a week."
        + (f" This week so far: {fmt_money(ch['earned_this_week_usd'], 'USD')}." if ch["earned_this_week_usd"] else ""))
    if pipe["open"]:
        cov = ch["pipeline_coverage"]
        parts.append(f"Pipeline: {pipe['open']} open lead{'s' if pipe['open'] != 1 else ''}, weighted value "
                     f"{fmt_money(pipe['weighted_usd'], 'USD')}"
                     + (f", covering {cov:.0%} of what's left." if cov is not None else ".")
                     + (f" {pipe['leads_without_value']} lead(s) have no value yet." if pipe['leads_without_value'] else ""))
    else:
        parts.append("Your pipeline is empty: there are no open leads recorded. Adding prospects is the fastest way "
                     "to make the target reachable.")
    from moyo.revenue import followups as _fu
    parts.extend(_fu.brief_lines(con, ref))  # who to contact today, with the top reasons

    # tasks
    if tv["overdue"]:
        parts.append(f"You have {len(tv['overdue'])} overdue task{'s' if len(tv['overdue']) > 1 else ''}: "
                     + ", ".join(t["title"] for t in tv["overdue"][:3]) + ".")
    parts.append(f"{len(tv['today'])} task{'s' if len(tv['today']) != 1 else ''} due today"
                 + (f", {len(tv['upcoming'])} more this week." if tv["upcoming"] else "."))

    # content
    y = cs["yesterday"]
    posted = [n for n, ok in (("TikTok", y["tiktok"]), ("Instagram", y["instagram"])) if ok]
    missed = [n for n, ok in (("TikTok", y["tiktok"]), ("Instagram", y["instagram"])) if not ok]
    from moyo import social
    perf_lines = content.performance_sentences(content.performance(con, ref)) if (
        social.ig_connected() or social.tt_connected()) else []
    parts.append("Content yesterday: " + (f"posted on {' and '.join(posted)}" if posted else "nothing logged")
                 + (f"; not logged on {' and '.join(missed)}." if missed and posted else ".")
                 + f" LinkedIn this week: {cs['linkedin_this_week']} of {cs['linkedin_target']}."
                 + (" " + " ".join(perf_lines) if perf_lines else
                    " Views and engagement will appear once Instagram and TikTok sync." if (social.ig_connected() or social.tt_connected())
                    else " Performance numbers aren't connected yet, so I can't report views or engagement."))

    # inbox (Gmail metadata only)
    from moyo import google_api
    if google_api.connected():
        ib = google_api.inbox(con)
        if ib["from_leads"]:
            who = "; ".join(f"{e['from_name']} about \"{e['subject'][:60]}\"" for e in ib["from_leads"][:3])
            parts.append(f"Inbox: {ib['unread_24h']} unread in the last day. From leads or clients: {who}.")
        else:
            parts.append(f"Inbox: {ib['unread_24h']} unread in the last day, none from your leads or clients.")
        allday = [e["title"] for e in google_api.events_on(con, ref) if e["all_day"]]
        if allday:
            parts.append("All-day on your calendar: " + ", ".join(allday[:3]) + ".")

    # schedule & priorities
    fixed = [b for b in plan["blocks"] if b["kind"] in ("fixed", "calendar")]
    if any(b["kind"] == "calendar" for b in fixed):
        parts.append("From your calendar and routine: " + ", ".join(f"{b['title'].lstrip('📅 ')} at {b['start']}" for b in fixed) + ".")
    elif fixed:
        parts.append("Fixed commitments: " + ", ".join(f"{b['title']} at {b['start']}" for b in fixed) + "."
                     + ("" if plan["schedule_confirmed"] else " (These times are my assumptions until you confirm them.)"))
    if plan["top3"]:
        parts.append("I recommend prioritising: " + " ".join(
            f"{i + 1}. {p['title']}, because it's {p['why']}." for i, p in enumerate(plan["top3"])))
    else:
        parts.append("You have no open tasks. Add your priorities and I'll plan the day around them.")
    if plan["overloaded"]:
        parts.append("Heads-up: today has more important work than free time. I left some items unscheduled "
                     "rather than overbooking you.")
    parts.append("Let's get started.")
    return {"text": "\n\n".join(parts), "challenge": ch, "pipeline": pipe, "plan": plan,
            "tasks": {k: (v if isinstance(v, int) else len(v)) for k, v in tv.items()}, "content": cs}


WAKE_QUESTION = "Want to see your full dashboard?"


def short(con, now: datetime | None = None) -> dict:
    """The clap-to-wake brief: five or six sentences, only stored data, then one question."""
    now = now or datetime.now()
    ref = today()
    ch = money.challenge_status(con, ref)
    tv = tasks.overview(con, ref)
    plan = planner.build(con, ref, now)
    s = [f"{greeting(now)}, Moyosore. I'm here."]
    s.append(f"You've {ch.get('progress_word', 'earned')} {fmt_money(ch['earned_usd'], 'USD')} of your {fmt_money(ch['target_usd'], 'USD')} target, "
             f"with {ch['days_left']} days left, so you need about {fmt_money(ch['required_per_week_usd'], 'USD')} a week.")
    due, over = len(tv["today"]), len(tv["overdue"])
    s.append((f"{due} task{'s' if due != 1 else ''} due today" if due else "Nothing is due today")
             + (f", and {over} overdue." if over else "."))
    hm = now.strftime("%H:%M")
    nxt = next((b for b in plan["blocks"] if b["kind"] in ("fixed", "calendar") and b["start"] >= hm), None)
    if nxt:
        s.append(f"Next on your schedule: {nxt['title'].lstrip('📅 ')} at {nxt['start']}.")
    if plan["top3"]:
        s.append(f"Top priority: {plan['top3'][0]['title']}.")
    from moyo.revenue import followups as _fu
    today_fu = _fu.today_list(con, ref)
    if today_fu:
        s.append(f"{len(today_fu)} deal{'s' if len(today_fu) != 1 else ''} to follow up today, starting with {today_fu[0]['name']}.")
    from moyo import google_api
    if google_api.connected():
        n = len(google_api.inbox(con)["from_leads"])
        if n:
            s.append(f"{n} recent email{'s' if n != 1 else ''} from leads or clients.")
    return {"sentences": s, "question": WAKE_QUESTION}
