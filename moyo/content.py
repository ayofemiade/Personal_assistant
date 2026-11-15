"""Content publishing log and daily commitments (manual entry in v0.1; APIs in Stage 4)."""
from __future__ import annotations

from datetime import date, datetime, timedelta

from moyo.db import get_setting, now_iso, rows, today

PLATFORMS = ("tiktok", "instagram", "linkedin", "x")
LABEL = {"tiktok": "TikTok", "instagram": "Instagram", "linkedin": "LinkedIn", "x": "X"}


def log_post(con, platform: str, title: str | None = None, on: str | None = None, url: str | None = None,
             views: int | None = None, likes: int | None = None, comments: int | None = None,
             hook: str | None = None, pillar: str | None = None) -> dict:
    platform = platform.lower()
    if platform not in PLATFORMS:
        raise ValueError(f"Platform must be one of {PLATFORMS}")
    cur = con.execute("INSERT INTO content_log(date, platform, title, hook, pillar, url, views, likes, comments, "
                      "created_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
                      (on or today().isoformat(), platform, title, hook, pillar, url, views, likes, comments, now_iso()))
    return dict(con.execute("SELECT * FROM content_log WHERE id=?", (cur.lastrowid,)).fetchone())


def status(con, ref: date | None = None) -> dict:
    ref = ref or today()
    iso, y = ref.isoformat(), (ref - timedelta(days=1)).isoformat()
    week_start = (ref - timedelta(days=ref.weekday())).isoformat()
    cm = get_setting(con, "content_commitments")

    def count(platform, frm, to):
        return con.execute("SELECT COUNT(*) FROM content_log WHERE platform=? AND date BETWEEN ? AND ?",
                           (platform, frm, to)).fetchone()[0]

    # streak = consecutive days (ending today or yesterday) with both TikTok and Instagram posted
    streak, d = 0, ref if count("tiktok", iso, iso) and count("instagram", iso, iso) else ref - timedelta(days=1)
    while count("tiktok", d.isoformat(), d.isoformat()) and count("instagram", d.isoformat(), d.isoformat()):
        streak += 1
        d -= timedelta(days=1)
    return {
        "today": {p: count(p, iso, iso) > 0 for p in ("tiktok", "instagram")},
        "yesterday": {p: count(p, y, y) > 0 for p in ("tiktok", "instagram")},
        "linkedin_this_week": count("linkedin", week_start, iso),
        "linkedin_target": cm.get("linkedin_per_week", 3),
        "x_this_week": count("x", week_start, iso),
        "daily_streak": streak,
        "recent": rows(con.execute("SELECT * FROM content_log ORDER BY date DESC, id DESC LIMIT 20")),
        "metrics_connected": False,
    }


def _median(xs):
    xs = sorted(xs)
    n = len(xs)
    return None if not n else xs[n // 2] if n % 2 else (xs[n // 2 - 1] + xs[n // 2]) / 2


def performance(con, ref: date | None = None, days: int = 1) -> dict:
    """Recent posts vs YOUR baseline (median of the previous 14 posts on the same platform).
    Only real synced numbers are used; missing metrics stay missing."""
    ref = ref or today()
    since = (ref - timedelta(days=days)).isoformat()
    out = {}
    for p in ("tiktok", "instagram"):
        posts = rows(con.execute("SELECT * FROM content_log WHERE platform=? AND (views IS NOT NULL OR likes IS NOT NULL) "
                                 "ORDER BY COALESCE(posted_at, date) DESC LIMIT 40", (p,)))
        recent = [x for x in posts if since <= x["date"] < ref.isoformat()] if days else []
        items = []
        now = datetime.now()
        for x in recent:
            posted = datetime.fromisoformat(x["posted_at"]) if x["posted_at"] else None
            fresh = bool(posted and now - posted < timedelta(hours=24))
            older = [o for o in posts if (o["posted_at"] or o["date"]) < (x["posted_at"] or x["date"])
                     and o["views"]][:14]
            base = _median([o["views"] for o in older]) if len(older) >= 3 else None
            eng = ((x["likes"] or 0) + (x["comments"] or 0) + (x["shares"] or 0)) / x["views"] if x["views"] else None
            base_eng = _median([((o["likes"] or 0) + (o["comments"] or 0) + (o["shares"] or 0)) / o["views"]
                                for o in older if o["views"]]) if len(older) >= 3 else None
            items.append({**{k: x[k] for k in ("id", "title", "url", "views", "likes", "comments", "shares", "date")},
                          "baseline_views": round(base) if base is not None else None,
                          "fresh": fresh,  # < 24h old: too early to judge against the usual
                          "vs_baseline": round(x["views"] / base, 2) if base and x["views"] and not fresh else None,
                          "engagement_pct": round(eng * 100, 1) if eng is not None else None,
                          "baseline_engagement_pct": round(base_eng * 100, 1) if base_eng is not None else None})
        viewed = [o for o in posts if o["views"]]
        last14 = viewed[:14]
        out[p] = {"recent": items, "baseline_views": round(_median([o["views"] for o in last14])) if len(last14) >= 3 else None,
                  "posts_with_metrics": len(posts), "views_available": bool(viewed),
                  "best_recent": max(viewed[:7], key=lambda o: o["views"], default=None),
                  "worst_recent": min(viewed[:7], key=lambda o: o["views"], default=None)}
    hist = (get_setting(con, "followers") or {})
    for p in ("tiktok", "instagram"):
        h = hist.get(p, {})
        vals = list(h.values())
        out[p]["followers"] = vals[-1] if vals else None
        week_ago = [v for d, v in h.items() if d <= (ref - timedelta(days=7)).isoformat()]
        out[p]["followers_7d_change"] = vals[-1] - week_ago[-1] if vals and week_ago else None
    return out


def performance_sentences(perf: dict) -> list[str]:
    out = []
    for p, label in (("tiktok", "TikTok"), ("instagram", "Instagram")):
        for x in perf[p]["recent"]:
            t = f"\"{x['title'][:50]}\"" if x["title"] else "your video"
            v = f"{x['views']:,} views, " if x["views"] is not None else ""
            s = f"{label} {t}: {v}{x['likes'] or 0:,} likes, {x['comments'] or 0:,} comments"
            if x.get("fresh"):
                s += " (posted under 24 hours ago, too early to judge)"
            elif x["vs_baseline"] is not None:
                s += (f", {x['vs_baseline']:.1f} times your usual {x['baseline_views']:,} views" if x["vs_baseline"] >= 1.15
                      else f", below your usual {x['baseline_views']:,} views" if x["vs_baseline"] <= 0.85
                      else ", about your usual views")
            if x["engagement_pct"] is not None and x["baseline_engagement_pct"]:
                if x["engagement_pct"] >= x["baseline_engagement_pct"] * 1.2:
                    s += f"; engagement {x['engagement_pct']}% is higher than usual"
                elif x["engagement_pct"] <= x["baseline_engagement_pct"] * 0.8:
                    s += f"; engagement {x['engagement_pct']}% is lower than usual"
            out.append(s + ".")
    return out


def pending_today(con, ref: date | None = None) -> list[str]:
    st = status(con, ref)
    out = [LABEL[p] for p, done in st["today"].items() if not done]
    ref = ref or today()
    days_left_in_week = 6 - ref.weekday()
    li_needed = st["linkedin_target"] - st["linkedin_this_week"]
    if li_needed > 0 and li_needed > days_left_in_week - 1:
        out.append("LinkedIn")
    return out
