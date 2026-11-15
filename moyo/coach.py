"""AI coaching for the briefing.

1. Deterministic *signals* are computed from the database (always available, offline).
2. A free cloud model turns the signals + an anonymised snapshot into 3–4 practical coaching points.
3. Every number in the model's answer is checked against the snapshot; points with invented
   numbers are dropped. If the cloud is unavailable, the signals themselves are shown.

Privacy (decision D7): client names never leave the laptop (CLIENT_n placeholders), and individual
deal amounts aren't sent; only your own aggregate challenge figures are.
"""
from __future__ import annotations

import hashlib
import json
import re
from datetime import date, datetime, timedelta

from moyo import content, money, planner, tasks
from moyo.cloud import Redactor
from moyo.db import get_setting, now_iso, rows, set_setting, today

STALE_HOURS = 3


# ---------------------------------------------------------------- 1. signals (rules, no AI)
def signals(con, ref: date | None = None) -> list[dict]:
    ref = ref or today()
    ch = money.challenge_status(con, ref)
    pipe = money.pipeline_summary(con, ref)
    ov = tasks.overview(con, ref)
    cs = content.status(con, ref)
    plan = planner.build(con, ref)
    out = []

    def add(kind, priority, text):
        out.append({"kind": kind, "priority": priority, "text": text})

    remaining, weekly = ch["remaining_usd"], ch["required_per_week_usd"]
    if ch["active"] and remaining > 0:
        if pipe["open"] == 0:
            add("pipeline", 1, f"Your pipeline is empty. With ${remaining:,.0f} to go, new prospects are the "
                               "bottleneck: everything else waits on leads.")
        elif ch["pipeline_coverage"] is not None and ch["pipeline_coverage"] < 1:
            add("pipeline", 1, f"Your weighted pipeline (${pipe['weighted_usd']:,.0f}) covers only "
                               f"{ch['pipeline_coverage']:.0%} of the ${remaining:,.0f} still needed. You need more "
                               "or bigger opportunities, not just more follow-ups.")
        if not ch["on_track"]:
            add("pace", 2, f"You're ${abs(ch['gap_vs_pace_usd']):,.0f} behind the straight-line pace; the target now "
                           f"needs about ${weekly:,.0f} a week.")
        if ch["earned_this_week_usd"] == 0 and ref.weekday() >= 2:
            add("pace", 2, "Nothing earned yet this week. A small quick win (an upsell or a short paid job) would "
                           "restart momentum.")
    overdue_fu = [f for f in pipe["followups_due"] if f["overdue"]]
    if overdue_fu:
        add("followup", 1, f"{len(overdue_fu)} follow-up(s) overdue: {', '.join(f['name'] for f in overdue_fu[:3])}. "
                           "Overdue follow-ups are the cheapest money you can win back.")
    if pipe["neglected"]:
        add("followup", 2, f"No next step set for {', '.join(n['name'] for n in pipe['neglected'][:3])}. Give each "
                           "a follow-up date so they don't go cold.")
    if pipe["leads_without_value"]:
        add("pipeline", 3, f"{pipe['leads_without_value']} lead(s) have no deal value, so I can't judge "
                           "which matter most. Add an estimate.")
    proposals = pipe["by_stage"].get("proposal", 0) + pipe["by_stage"].get("negotiation", 0)
    if proposals >= 2:
        add("sales", 2, f"{proposals} deals are at proposal/negotiation stage: closing these is worth more than "
                        "starting new outreach today.")
    top_cats = [t["category"] for t in plan["top3"]]
    if top_cats and not {"revenue", "sales", "client"} & set(top_cats) and ch["active"]:
        add("focus", 1, "None of today's top 3 priorities moves money. Add one revenue or sales task "
                        "(a proposal, a follow-up, or outreach).")
    if ov["overdue"]:
        add("tasks", 2, f"{len(ov['overdue'])} overdue task(s). Do them, reschedule them, or drop them; "
                        "a long overdue list hides what matters.")
    if plan["overloaded"]:
        add("load", 2, "Today has more important work than time. Decide now what you're NOT doing.")
    if not cs["yesterday"]["tiktok"] or not cs["yesterday"]["instagram"]:
        missed = [p for p, ok in (("TikTok", cs["yesterday"]["tiktok"]), ("Instagram", cs["yesterday"]["instagram"])) if not ok]
        add("content", 3, f"No {' or '.join(missed)} post logged yesterday. Batch-record 2–3 videos in one "
                          "session to protect the daily streak.")
    if cs["linkedin_this_week"] < cs["linkedin_target"] and ref.weekday() >= 3:
        add("content", 3, f"LinkedIn: {cs['linkedin_this_week']} of {cs['linkedin_target']} posts this week. "
                          "LinkedIn is where business clients see you; one post about a recent build would count.")
    from moyo import google_api
    if google_api.connected():
        waiting = google_api.inbox(con)["from_leads"]
        if waiting:
            add("followup", 1, f"Unread email from {', '.join(sorted({e['from_name'] for e in waiting})[:3])}. "
                               "Replying fast to leads and clients is one of the easiest ways to win work.")
    out.sort(key=lambda s: s["priority"])
    return out


# ---------------------------------------------------------------- 2. anonymised snapshot for the model
def snapshot(con, red: Redactor, ref: date | None = None) -> dict:
    ref = ref or today()
    ch = money.challenge_status(con, ref)
    pipe = money.pipeline_summary(con, ref)
    plan = planner.build(con, ref)
    ov = tasks.overview(con, ref)
    cs = content.status(con, ref)
    leads = sorted(money.all_leads(con, open_only=True), key=lambda l: l["updated_at"], reverse=True)[:12]
    vals = [money.lead_usd(con, l) for l in leads]
    known = [v for v in vals if v]
    hi = sorted(known)[len(known) * 2 // 3] if known else None

    def size(v):
        if v is None:
            return "unknown"
        return "large" if hi and v >= hi and len(known) > 1 else "small" if v < 300 else "medium"
    yrev = con.execute("SELECT value_created, distractions FROM reviews WHERE date=?",
                       ((ref - timedelta(days=1)).isoformat(),)).fetchone()
    red_title = lambda s: red.redact(s or "")[:90]  # noqa: E731
    from moyo import google_api
    mail = cal = None
    if google_api.connected():
        ib = google_api.inbox(con)
        # counts and redacted senders only: subjects and bodies never go to the AI
        lead_names = {l["id"]: l["name"] for l in money.all_leads(con)}
        # sender names are personal data: send only the lead placeholder (CLIENT_n), never the person's name
        mail = {"unread_last_24h": ib["unread_24h"],
                "unread_from_leads_or_clients": sorted({red.redact(lead_names[e["lead_id"]]) if e["lead_id"] in lead_names
                                                        else "a client" for e in ib["from_leads"]})}
        cal = [{"time": "all day" if e["all_day"] else e["start"][11:16], "title": red_title(e["title"])}
               for e in google_api.events_on(con, ref)][:8]
    from moyo import social
    perf = None
    if social.ig_connected() or social.tt_connected():
        pf = content.performance(con, ref, days=7)
        perf = {p: {"your_usual_views": pf[p]["baseline_views"], "followers": pf[p]["followers"],
                    "followers_change_7d": pf[p]["followers_7d_change"],
                    "last_7_days": [{"topic": red_title(x["title"]), "views": x["views"], "likes": x["likes"],
                                     "comments": x["comments"], "times_usual_views": x["vs_baseline"],
                                     "engagement_pct": x["engagement_pct"]} for x in pf[p]["recent"]]}
                for p in ("tiktok", "instagram")}
    return {
        "content_performance": perf,
        "inbox": mail, "calendar_today": cal,
        "today": ref.strftime("%A %Y-%m-%d"),
        "challenge": {**{k: round(ch[k]) for k in ("target_usd", "earned_usd", "remaining_usd", "gap_vs_pace_usd",
                                                    "required_per_week_usd", "earned_this_week_usd",
                                                    "weighted_pipeline_usd")},
                      "days_left": ch["days_left"], "on_track": ch["on_track"],
                      "pipeline_covers_pct_of_remaining": (round(ch["pipeline_coverage"] * 100)
                                                           if ch["pipeline_coverage"] is not None else None)},
        "pipeline": {"open": pipe["open"], "by_stage": pipe["by_stage"],
                     "leads": [{"lead": red.redact(l["name"]), "stage": l["stage"], "deal_size": size(v),
                                "days_since_update": (ref - date.fromisoformat(l["updated_at"][:10])).days,
                                "follow_up": ("overdue" if l["next_followup"] and l["next_followup"] < ref.isoformat()
                                              else "due today" if l["next_followup"] == ref.isoformat()
                                              else "scheduled" if l["next_followup"] else "none")}
                               for l, v in zip(leads, vals)]},
        "tasks": {"overdue": [red_title(t["title"]) for t in ov["overdue"][:6]],
                  "due_today": [red_title(t["title"]) for t in ov["today"][:6]],
                  "this_week": len(ov["upcoming"])},
        "plan_top3": [{"title": red_title(p["title"]), "category": p["category"]} for p in plan["top3"]],
        "content": {"posted_yesterday": cs["yesterday"], "daily_streak": cs["daily_streak"],
                    "linkedin_this_week": cs["linkedin_this_week"], "linkedin_target": cs["linkedin_target"]},
        "yesterday_review": {"value_created": red_title(yrev["value_created"]) if yrev else None,
                             "distractions": red_title(yrev["distractions"]) if yrev else None},
    }


SYSTEM = (
    "You are Moyo, the personal executive assistant and accountability coach of Moyosore, a Nigerian software "
    "developer and founder of MoyoCode Technologies (websites, custom software, AI agents, automation). He is "
    "trying to EARN $10,000 by 8 Feb 2027 while studying, creating daily TikTok/Instagram content and going to "
    "the gym. Priorities: revenue work > client delivery > sales/follow-ups > content > study > personal, but "
    "health, exams and urgent client work can override.\n"
    "Using ONLY the JSON data provided, give practical coaching for today. Rules:\n"
    "- 3 or 4 points, each a specific action he can take today, with a short reason grounded in the data.\n"
    "- Never invent numbers, clients, deals, metrics or events. Only use numbers that appear in the data.\n"
    "- CLIENT_n are private placeholders for real client names: refer to them exactly as written.\n"
    "- Prefer actions with a clear path to revenue; don't create busywork. Be warm, direct, encouraging; no fluff.\n"
    "- If data is thin (e.g. no leads), say what to set up first.\n"
    "- If content_performance is present: judge posts by engagement and vs his usual views, not raw views; "
    "suggest one concrete content experiment based on what over- or under-performed.\n"
    'Reply as JSON: {"headline": "<one sentence, max 20 words>", "points": [{"action": "...", "why": "..."}]}'
)


def _numbers(text: str) -> list[float]:
    out = []
    for m in re.finditer(r"\d[\d,]*(?:\.\d+)?", text):
        try:
            out.append(float(m.group().replace(",", "")))
        except ValueError:
            pass
    return out


def _allowed_numbers(snap: dict) -> set[float]:
    found = set(_numbers(json.dumps(snap)))
    extra = set()
    for n in found:
        extra |= {round(n), round(n, 1), round(n, 2)}
        if 0 < n <= 1:
            extra |= {round(n * 100), round(n * 100, 1)}  # coverage 0.12 → 12%
    return found | extra | {float(i) for i in range(0, 11)} | {2026.0, 2027.0, 10000.0, 10.0, 8.0}


def validate(points: list[dict], snap: dict) -> tuple[list[dict], int]:
    allowed = _allowed_numbers(snap)
    kept, dropped = [], 0
    for p in points:
        txt = f"{p.get('action', '')} {p.get('why', '')}"
        bad = [n for n in _numbers(txt) if n not in allowed and round(n) not in allowed]
        if bad or not p.get("action"):
            dropped += 1
        else:
            kept.append({"action": str(p["action"]).strip(), "why": str(p.get("why", "")).strip()})
    return kept, dropped


def _fingerprint(snap: dict) -> str:
    return hashlib.sha256(json.dumps(snap, sort_keys=True).encode()).hexdigest()[:16]


def generate(con, force: bool = False) -> dict:
    """Return coaching for today, using the cache unless data changed and it's stale (or force)."""
    from moyo.cloud import generate_json  # local import avoids a cycle
    red = Redactor(con)
    snap = snapshot(con, red)
    fp = _fingerprint(snap)
    sig = signals(con)
    cache = get_setting(con, "coaching_cache") or {}
    fresh = (cache.get("date") == today().isoformat() and cache.get("source") == "ai" and (
        cache.get("fingerprint") == fp or
        datetime.fromisoformat(cache["generated_at"]) > datetime.now() - timedelta(hours=STALE_HOURS)))
    if fresh and not force:
        return {**cache, "signals": sig, "cached": True}

    result = generate_json(con, SYSTEM, json.dumps(snap, ensure_ascii=False))
    if "data" in result and isinstance(result["data"], dict):
        data = result["data"]
        pts, dropped = validate(list(data.get("points") or [])[:5], snap)
        headline = str(data.get("headline") or "").strip()
        if not validate([{"action": headline}], snap)[0]:
            headline = ""
        if pts:
            out = {"date": today().isoformat(), "generated_at": now_iso(), "fingerprint": fp, "source": "ai",
                   "model": result.get("model"), "headline": red.restore(headline),
                   "points": [red.restore(p) for p in pts], "dropped_unverified": dropped}
            set_setting(con, "coaching_cache", out)
            return {**out, "signals": sig, "cached": False}
    # cloud unavailable or nothing verifiable → rule-based coaching (always truthful)
    out = {"date": today().isoformat(), "generated_at": now_iso(), "fingerprint": fp, "source": "rules",
           "model": None, "headline": "Here's what your numbers say today.",
           "points": [{"action": s["text"], "why": ""} for s in sig[:4]],
           "note": result.get("error") or "The AI coach gave no verifiable advice, so these come from your data directly."}
    return {**out, "signals": sig, "cached": False}


def speech_text(c: dict) -> str:
    if not c.get("points"):
        return ""
    lines = [c.get("headline") or "My coaching for today."]
    for i, p in enumerate(c["points"], 1):
        lines.append(f"{i}. {p['action']}" + (f" {p['why']}" if p.get("why") else ""))
    return "\n\n".join(lines)
