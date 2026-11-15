"""Daily planner: deterministic scoring + time-blocking, with an explanation for every priority.

Scoring follows Moyosore's framework (revenue > client > sales > content > study > personal),
then urgency and explicit priority can override it. The day is never filled to 100%."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta

from moyo import content, money, tasks
from moyo.db import get_setting, today

CAT_WEIGHT = {"revenue": 60, "client": 50, "sales": 40, "content": 30, "study": 20, "personal": 10, "other": 10}
CAT_LABEL = {"revenue": "moves the $10K target directly", "client": "MoyoCode client commitment",
             "sales": "pipeline/sales work that leads to revenue", "content": "personal-brand commitment",
             "study": "university/learning commitment", "personal": "personal commitment", "other": "general task"}
PRIO_BONUS = {1: 35, 2: 20, 3: 8, 4: 0}
DAYS = ["MO", "TU", "WE", "TH", "FR", "SA", "SU"]


@dataclass
class Item:
    title: str
    category: str
    minutes: int
    score: float
    reasons: list[str] = field(default_factory=list)
    task_id: int | None = None
    fixed_time: str | None = None


def _hm(s: str) -> datetime:
    return datetime.strptime(s, "%H:%M")


def score_task(t: dict, ref: date) -> Item:
    s = CAT_WEIGHT.get(t["category"], 10) + PRIO_BONUS.get(t["priority"], 0)
    reasons = [CAT_LABEL.get(t["category"], "task")]
    if t["priority"] == 1:
        reasons.append("you marked it top priority")
    if t["due_date"]:
        d = (date.fromisoformat(t["due_date"]) - ref).days
        if d < 0:
            s += 45
            reasons.append(f"overdue by {-d} day{'s' if d < -1 else ''}")
        elif d == 0:
            s += 35
            reasons.append("due today")
        elif d == 1:
            s += 15
            reasons.append("due tomorrow")
        elif d <= 3:
            s += 8
            reasons.append(f"due in {d} days")
    if t.get("lead_id"):
        s += 5
        reasons.append("linked to a live lead")
    return Item(t["title"], t["category"], int(t["estimate_min"] or 45), s, reasons, t["id"], t.get("due_time"))


def candidates(con, ref: date) -> list[Item]:
    items = []
    horizon = (ref + timedelta(days=7)).isoformat()
    for t in tasks.listing(con):
        if t["depends_on"]:
            dep = con.execute("SELECT status FROM tasks WHERE id=?", (t["depends_on"],)).fetchone()
            if dep and dep["status"] != "done":
                continue  # blocked
        if t["due_date"] and t["due_date"] > horizon and t["priority"] > 1:
            continue
        items.append(score_task(t, ref))
    # follow-ups due from the pipeline, if no task already covers them
    pipe = money.pipeline_summary(con, ref)
    covered = {(t["lead_id"]) for t in tasks.listing(con) if t["lead_id"]}
    for f in pipe["followups_due"]:
        if f["id"] not in covered:
            items.append(Item(f"Follow up with {f['name']}", "sales", 20,
                              CAT_WEIGHT["sales"] + (45 if f["overdue"] else 35),
                              [CAT_LABEL["sales"], "follow-up overdue" if f["overdue"] else "follow-up due today"]))
    # content commitments not yet published today
    for p in content.pending_today(con, ref):
        items.append(Item(f"Create & publish {p} video" if p != "LinkedIn" else "Write & publish LinkedIn post",
                          "content", 60 if p != "LinkedIn" else 30, CAT_WEIGHT["content"] + 35,
                          [CAT_LABEL["content"], "daily publishing commitment" if p != "LinkedIn"
                           else "behind on LinkedIn posts this week"]))
    items.sort(key=lambda i: -i.score)
    return items


def fixed_blocks(sched: dict, ref: date) -> list[dict]:
    wd = DAYS[ref.weekday()]
    return [f for f in sched["fixed"] if f["days"] == "*" or wd in f["days"].split(",")]


def build(con, ref: date | None = None, now: datetime | None = None) -> dict:
    ref = ref or today()
    sched = get_setting(con, "schedule")
    items = candidates(con, ref)
    day_start = _hm(sched["day_start"])
    day_end = _hm(sched["day_end"])
    if now and ref == today():
        n = _hm(now.strftime("%H:%M"))
        n = n + timedelta(minutes=(15 - n.minute % 15) % 15)
        day_start = max(day_start, n)
    review_start = day_end - timedelta(minutes=20)
    fixed = [{"title": f["title"], "start": _hm(f["start"]), "end": _hm(f["end"]), "kind": "fixed"}
             for f in fixed_blocks(sched, ref)]
    from moyo.google_api import events_on  # Google Calendar events (if connected) are fixed commitments too
    for ev in events_on(con, ref):
        if not ev["all_day"]:
            s, e = _hm(ev["start"][11:16]), _hm(ev["end"][11:16]) if ev["end"][:10] == ref.isoformat() else _hm("23:59")
            if e > s:
                fixed.append({"title": f"📅 {ev['title']}", "start": s, "end": e, "kind": "calendar"})
    # the real calendar wins over routine blocks from Settings that overlap it (avoids duplicate "meetings")
    cal = [f for f in fixed if f["kind"] == "calendar"]
    hidden_assumed = [f["title"] for f in fixed if f["kind"] == "fixed"
                      and any(c["start"] < f["end"] and f["start"] < c["end"] for c in cal)]
    fixed = [f for f in fixed if not (f["kind"] == "fixed" and f["title"] in hidden_assumed)]
    fixed = [f for f in fixed if f["end"] > day_start]
    # free windows
    busy = sorted([(f["start"], f["end"]) for f in fixed] + [(review_start, day_end)])
    windows, cur = [], day_start
    for s, e in busy:
        if s > cur:
            windows.append([cur, min(s, review_start)])
        cur = max(cur, e)
    windows = [w for w in windows if (w[1] - w[0]).seconds >= 20 * 60]
    free_min = sum((w[1] - w[0]).seconds // 60 for w in windows)
    budget = free_min * (100 - sched["buffer_pct"]) / 100

    blocks, scheduled, used = [], [], 0
    queue = list(items)
    for w in windows:
        t, since_break = w[0], 0
        while queue and t < w[1]:
            it = queue[0]
            room = (w[1] - t).seconds // 60
            if used + it.minutes > budget:
                break
            if since_break >= sched["focus_block_min"] and room > sched["break_min"] + 20:
                blocks.append({"title": "Break", "start": t, "end": t + timedelta(minutes=sched["break_min"]),
                               "kind": "break"})
                t += timedelta(minutes=sched["break_min"])
                since_break = 0
                continue
            if it.minutes > (w[1] - t).seconds // 60:
                # try a smaller item that fits this window
                fit = next((x for x in queue if x.minutes <= (w[1] - t).seconds // 60
                            and used + x.minutes <= budget), None)
                if not fit:
                    break
                it = fit
            queue.remove(it)
            end = t + timedelta(minutes=it.minutes)
            blocks.append({"title": it.title, "start": t, "end": end, "kind": "task", "task_id": it.task_id,
                           "category": it.category})
            scheduled.append(it)
            used += it.minutes
            since_break += it.minutes
            t = end + timedelta(minutes=5)
    blocks += [{**f, "kind": "fixed" if f["kind"] == "fixed" else "calendar"} for f in fixed]
    blocks.append({"title": "End-of-day review", "start": review_start, "end": day_end, "kind": "review"})
    blocks.sort(key=lambda b: b["start"])
    top = items[:3]
    return {
        "date": ref.isoformat(),
        "schedule_confirmed": sched.get("confirmed", False),
        "top3": [{"title": i.title, "why": "; ".join(i.reasons), "task_id": i.task_id, "category": i.category}
                 for i in top],
        "blocks": [{**b, "start": b["start"].strftime("%H:%M"), "end": b["end"].strftime("%H:%M")} for b in blocks],
        "unscheduled": [{"title": i.title, "task_id": i.task_id, "minutes": i.minutes} for i in queue],
        "hidden_assumed": hidden_assumed,
        "free_minutes": free_min, "planned_minutes": used, "buffer_pct": sched["buffer_pct"],
        "overloaded": bool(queue) and any(i.score >= 80 for i in queue),
    }
