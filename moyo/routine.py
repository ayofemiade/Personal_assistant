"""'Start my day': open the chosen workspace, start music, then the dashboard reads the briefing aloud.

Triggered by: the Today button, "start my day"/"good morning" in the command bar, the morning
notification, or the Start-my-day shortcut (Ctrl+Alt+S → moyo --start-day). Low-risk tier: it only
launches allowlisted apps (workspaces.json) and presses the media play key.
"""
from __future__ import annotations

import threading
import time

from moyo import audit, workspaces
from moyo.db import get_setting, now_iso, set_setting, today


def _play_music_later(delay: float = 6.0) -> None:
    def run():
        time.sleep(delay)  # give Spotify time to open the playlist
        try:
            workspaces.media("play_pause")
        except Exception:
            pass
    threading.Thread(target=run, daemon=True).start()


def start(con, actor: str = "user", dry_run: bool = False) -> dict:
    cfg = get_setting(con, "routine")
    opened, problems, music = [], [], False
    profile = cfg.get("workspace")
    if profile:
        try:
            r = workspaces.launch(profile, dry_run=dry_run)
            opened = [a["name"] for a in r["apps"]] + ([f"{len(r['urls'])} browser tab(s)"] if r["urls"] else [])
            problems = r["problems"]
            if cfg.get("music") and r.get("music"):
                music = True
                if not dry_run and r.get("launched"):
                    _play_music_later()
        except workspaces.WorkspaceError as e:
            problems.append(str(e))
    set_setting(con, "routine", {**cfg, "last_run": today().isoformat()})
    con.execute("UPDATE notifications SET read_at=COALESCE(read_at, ?) WHERE key=?", (now_iso(), f"startday:{today().isoformat()}"))
    audit.log(con, actor, "start_day", "low", {"workspace": profile, "opened": opened, "music": music})
    parts = [f"Opening {workspaces.load().get(profile, {}).get('label', profile)}: {', '.join(opened) or 'nothing to open'}."] if profile else []
    if music:
        parts.append("Starting your music.")
    if problems:
        parts.append("Note: " + " ".join(problems))
    if cfg.get("read_briefing"):
        parts.append("Here's your briefing.")
    return {"reply": " ".join(["Good morning, Moyosore.", *parts]),
            "read_briefing": bool(cfg.get("read_briefing")), "opened": opened, "music": music, "problems": problems}
