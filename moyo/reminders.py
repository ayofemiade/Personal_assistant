"""Proactive reminders: rules → deduplicated notifications → (optionally) a desktop toast.

Levels (design system §5): urgent = toast with sound, even in quiet hours; important = silent toast outside
quiet hours; info = Moyo's notification list only. Every reminder has a stable key, so it fires once.
All text is built from Moyo's own data; email/calendar text is passed to the toast safely (moyo.notify).
"""
from __future__ import annotations

from datetime import date, datetime, timedelta

from moyo import content, google_api, money, notify, tasks
from moyo.db import get_setting, now_iso, rows

PORT_URL = "http://127.0.0.1:8765/"


def _t(hm: str) -> tuple[int, int]:
    h, m = hm.split(":")
    return int(h), int(m)


def in_quiet_hours(now: datetime, start: str, end: str) -> bool:
    s, e, n = _t(start), _t(end), (now.hour, now.minute)
    return (s <= n or n < e) if s > e else (s <= n < e)


def _at(now: datetime, hm: str) -> bool:
    return (now.hour, now.minute) >= _t(hm)


def candidates(con, now: datetime) -> list[dict]:
    """Every reminder that *should* exist right now (dedupe happens on insert)."""
    cfg = get_setting(con, "notifications")
    sched = get_setting(con, "schedule")
    routine = get_setting(con, "routine")
    d, iso = now.date(), now.date().isoformat()
    out: list[dict] = []

    def add(key, level, title, body, view):
        out.append({"key": key, "level": level, "title": title, "body": body, "view": view})

    # A. morning: offer the "Start my day" routine once per day
    if routine.get("morning_prompt") and routine.get("last_run") != iso and _at(now, routine.get("prompt_after", "07:00")) \
            and now.hour < 12:
        add(f"startday:{iso}", "important", "Good morning, Moyosore", "Ready to start your day? Click to open your workspace and briefing.",
            "start-day")

    # content: not posted by the reminder time
    if _at(now, cfg.get("content_reminder_time", "19:00")):
        st = content.status(con, d)
        for p, label in (("tiktok", "TikTok"), ("instagram", "Instagram")):
            if not st["today"][p]:
                add(f"content:{iso}:{p}", "important", f"No {label} post yet today",
                    f"Your daily {label} video keeps the {st['daily_streak']}-day streak alive." if st["daily_streak"]
                    else f"Your daily {label} video is still to do.", "content")

    # sales: overdue / due follow-ups (after the working day starts)
    if _at(now, sched.get("day_start", "08:00")):
        pipe = money.pipeline_summary(con, d)
        for f in pipe["followups_due"]:
            add(f"followup:{f['id']}:{iso}", "important" if f["overdue"] else "info",
                f"Follow up with {f['name']}" + (" (overdue)" if f["overdue"] else " today"),
                f"Stage: {f['stage']}. Follow-ups are the cheapest money to win.", "money")
        ov = tasks.overview(con, d)
        if ov["overdue"]:
            add(f"overdue:{iso}", "info", f"{len(ov['overdue'])} overdue task(s)",
                "Do, reschedule or drop them so today's plan stays honest.", "tasks")
        # weekly pace check on Mondays
        ch = money.challenge_status(con, d)
        if d.weekday() == 0 and ch["active"] and not ch["on_track"]:
            add(f"pace:{d.isocalendar()[0]}-W{d.isocalendar()[1]}", "important", "New week: $10K pace check",
                f"You need about ${ch['required_per_week_usd']:,.0f} this week. Pick the leads that can close.", "money")

    # money owed: sent invoices past their due date (once a week each), renewals coming up (30 days ahead)
    if _at(now, sched.get("day_start", "08:00")):
        from moyo import invoices as _ui
        from moyo.revenue import ledger, renewals
        wk = f"{d.isocalendar()[0]}-W{d.isocalendar()[1]}"
        for inv in ledger.owed(con, d)["overdue"]:
            late = (d - date.fromisoformat(inv["due_date"])).days
            add(f"invoice-overdue:{inv['id']}:{wk}", "important",
                f"{inv['client']} owes {_ui.money_str(inv['balance'], inv['currency'])} ({inv['number']})",
                f"{late} day{'s' if late != 1 else ''} overdue. A short, friendly reminder usually does it.", "money")
        for r in renewals.upcoming(con, d, within_days=30):
            add(f"renewal:{r['company_id']}:{r['kind']}:{r['due']}", "info",
                f"{r['company']}: {r['kind']} renewal due {r['due']}",
                f"Last invoiced on {r['last_invoice']} ({r['last_date']}). Ask them to renew before it lapses.", "money")

    # inbox: unread email from a lead or client (once per email)
    if google_api.connected():
        for e in google_api.inbox(con)["from_leads"]:
            add(f"leadmail:{e['id']}", "important", f"Email from {e['from_name']}",
                f"{e['subject'][:80]}. Reply fast; it's a lead/client.", "today")
        lead = cfg.get("event_lead_minutes", 15)
        for ev in google_api.events_on(con, d):
            if ev["all_day"]:
                continue
            start = datetime.fromisoformat(ev["start"])
            if timedelta(0) <= start - now <= timedelta(minutes=lead):
                add(f"event:{ev['id']}:{ev['start']}", "important", f"{ev['title']} at {start:%H:%M}",
                    f"Starts in {max(1, int((start - now).total_seconds() // 60))} min" + (f" · {ev['location']}" if ev["location"] else ""),
                    "today")
        st = google_api.STATE
        if st.get("last_sync_error"):
            add(f"google:{iso}", "important", "Google needs attention", st["last_sync_error"][:140], "settings")

    # connections: Instagram token running out
    from moyo import social
    ig = social.status()["instagram"]
    if ig["connected"] and not ig.get("auto_renews") and ig.get("token_days_left") is not None and ig["token_days_left"] <= 7:
        add(f"igtoken:{d.isocalendar()[1]}", "important", "Instagram token expires soon",
            f"About {ig['token_days_left']} day(s) left. Generate a new token in Meta and reconnect in Settings.", "settings")

    # end-of-day review
    end_h, end_m = _t(sched.get("day_end", "22:30"))
    review_at = datetime.combine(d, datetime.min.time()).replace(hour=end_h, minute=end_m) - timedelta(
        minutes=cfg.get("review_minutes_before_end", 30))
    if now >= review_at and not con.execute("SELECT 1 FROM reviews WHERE date=?", (iso,)).fetchone():
        add(f"review:{iso}", "info", "Time for your end-of-day review", "Two minutes: what moved, what didn't, what moves to tomorrow.", "review")

    # weekly review: Sunday evening
    if d.weekday() == 6 and now.hour >= 17:
        add(f"weekly:{d.isocalendar()[0]}-W{d.isocalendar()[1]}", "important", "Your weekly review is ready",
            "See the week's money, content and tasks in one place.", "review")
    return out


def tick(con, now: datetime | None = None, send_toasts: bool = True) -> list[dict]:
    """Create new notifications and toast the eligible ones. Returns the newly created ones."""
    now = now or datetime.now()
    cfg = get_setting(con, "notifications")
    if not cfg.get("enabled", True):
        return []
    quiet = in_quiet_hours(now, cfg.get("quiet_start", "22:30"), cfg.get("quiet_end", "07:00"))
    new = []
    for c in candidates(con, now):
        cur = con.execute("INSERT OR IGNORE INTO notifications(key, level, title, body, view, created_at) VALUES (?,?,?,?,?,?)",
                          (c["key"], c["level"], c["title"], c["body"], c["view"], now_iso()))
        if not cur.rowcount:
            continue
        nid = cur.lastrowid
        eligible = cfg.get("toasts", True) and c["level"] in cfg.get("toast_levels", ["urgent", "important"]) \
            and (c["level"] == "urgent" or not quiet)
        if eligible and send_toasts:
            notify.toast(c["title"], c["body"] or "", url=PORT_URL + "#" + (c["view"] or "today"), urgent=c["level"] == "urgent")
            con.execute("UPDATE notifications SET toasted=1 WHERE id=?", (nid,))
        new.append({**c, "id": nid, "toasted": bool(eligible and send_toasts)})
    # keep the list short
    con.execute("DELETE FROM notifications WHERE created_at < ?", ((now - timedelta(days=30)).isoformat(),))
    return new


def listing(con, limit: int = 40) -> dict:
    items = rows(con.execute("SELECT * FROM notifications ORDER BY id DESC LIMIT ?", (limit,)))
    unread = con.execute("SELECT COUNT(*) FROM notifications WHERE read_at IS NULL").fetchone()[0]
    return {"items": items, "unread": unread}


def mark_read(con, ids: list[int] | None = None) -> None:
    if ids:
        con.executemany("UPDATE notifications SET read_at=? WHERE id=? AND read_at IS NULL", [(now_iso(), i) for i in ids])
    else:
        con.execute("UPDATE notifications SET read_at=? WHERE read_at IS NULL", (now_iso(),))


def weekly_summary(con, ref: date) -> dict:
    """Facts for the weekly review (Mon–Sun containing `ref`). All numbers from the database."""
    start = ref - timedelta(days=ref.weekday())
    end = start + timedelta(days=6)
    s, e = start.isoformat(), end.isoformat()
    earned = con.execute("SELECT COALESCE(SUM(usd_amount),0), COUNT(*) FROM earnings WHERE earned_date BETWEEN ? AND ?", (s, e)).fetchone()
    done = con.execute("SELECT COUNT(*) FROM tasks WHERE status='done' AND substr(completed_at,1,10) BETWEEN ? AND ?", (s, e)).fetchone()[0]
    leads = con.execute("SELECT COUNT(*) FROM deals WHERE historical=0 AND substr(created_at,1,10) BETWEEN ? AND ?",
                        (s, e)).fetchone()[0]
    posts = {p: con.execute("SELECT COUNT(*), AVG(views), MAX(views) FROM content_log WHERE platform=? AND date BETWEEN ? AND ?",
                            (p, s, e)).fetchone() for p in ("tiktok", "instagram", "linkedin", "x")}
    top = con.execute("SELECT platform, title, views FROM content_log WHERE date BETWEEN ? AND ? AND views IS NOT NULL "
                      "ORDER BY views DESC LIMIT 1", (s, e)).fetchone()
    reviews = con.execute("SELECT COUNT(*) FROM reviews WHERE date BETWEEN ? AND ?", (s, e)).fetchone()[0]
    return {"start": s, "end": e, "earned_usd": round(earned[0], 2), "earnings_count": earned[1], "tasks_done": done,
            "leads_added": leads, "daily_reviews": reviews,
            "posts": {p: {"count": v[0], "avg_views": round(v[1]) if v[1] is not None else None, "max_views": v[2]} for p, v in posts.items()},
            "top_post": dict(top) if top else None}
