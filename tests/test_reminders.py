import base64
from datetime import datetime

import pytest

from moyo import content, db, money, notify, reminders, routine, tasks, workspaces
from moyo.server import app  # noqa: F401  (ensures routes import cleanly)

THU = datetime(2026, 11, 12, 19, 30)  # MOYO_TODAY in tests = Thursday 12 Nov 2026


@pytest.fixture
def sent(monkeypatch):
    calls = []
    monkeypatch.setattr(notify, "toast", lambda title, body, url=None, urgent=False: calls.append((title, body, url, urgent)) or True)
    return calls


def keys(con):
    return {r["key"] for r in db.rows(con.execute("SELECT key FROM notifications"))}


def test_quiet_hours_wrap_midnight():
    assert reminders.in_quiet_hours(datetime(2026, 1, 1, 23, 0), "22:30", "07:00")
    assert reminders.in_quiet_hours(datetime(2026, 1, 1, 6, 59), "22:30", "07:00")
    assert not reminders.in_quiet_hours(datetime(2026, 1, 1, 7, 0), "22:30", "07:00")
    assert reminders.in_quiet_hours(datetime(2026, 1, 1, 13, 0), "12:00", "14:00")


def test_content_reminder_fires_once_and_toasts(con, sent):
    new = reminders.tick(con, THU)
    k = keys(con)
    assert "content:2026-11-12:tiktok" in k and "content:2026-11-12:instagram" in k
    assert any(t[0] == "No TikTok post yet today" for t in sent) and sent[0][2].startswith("http://127.0.0.1:8765/#")
    again = reminders.tick(con, THU)
    assert again == [] and len(new) >= 2  # dedupe: nothing fires twice


def test_posted_content_not_reminded(con, sent):
    content.log_post(con, "tiktok", "posted", on="2026-11-12")
    reminders.tick(con, THU)
    assert "content:2026-11-12:tiktok" not in keys(con) and "content:2026-11-12:instagram" in keys(con)


def test_quiet_hours_store_but_do_not_toast(con, sent):
    reminders.tick(con, datetime(2026, 11, 12, 23, 0))
    assert keys(con)  # recorded in the bell
    assert sent == []  # but no pop-up during quiet hours
    rows = db.rows(con.execute("SELECT toasted FROM notifications"))
    assert all(r["toasted"] == 0 for r in rows)


def test_followups_and_overdue(con, sent):
    money.add_lead(con, "Kemi Stores", stage="proposal", next_followup="2026-11-10")
    tasks.add(con, "Old task", due_date="2026-11-01")
    reminders.tick(con, datetime(2026, 11, 12, 9, 0))
    n = {r["key"]: r for r in db.rows(con.execute("SELECT * FROM notifications"))}
    fk = [k for k in n if k.startswith("followup:")][0]
    assert n[fk]["level"] == "important" and "overdue" in n[fk]["title"]
    assert n["overdue:2026-11-12"]["level"] == "info"
    assert not any("Old task" in t[0] or "overdue task" in t[0] for t in sent)  # info never pops up


def test_morning_prompt_once_until_routine_runs(con, sent, monkeypatch):
    monkeypatch.setattr(workspaces, "launch", lambda name, dry_run=False: {"apps": [], "urls": [], "music": None, "problems": [], "launched": False, "key": name, "label": name})
    reminders.tick(con, datetime(2026, 11, 12, 7, 30))
    assert "startday:2026-11-12" in keys(con)
    r = routine.start(con)
    assert db.get_setting(con, "routine")["last_run"] == "2026-11-12" and r["read_briefing"] is True
    unread = con.execute("SELECT read_at FROM notifications WHERE key='startday:2026-11-12'").fetchone()[0]
    assert unread is not None  # running the routine clears the prompt


def test_disabled_means_nothing(con, sent):
    cfg = db.get_setting(con, "notifications"); cfg["enabled"] = False; db.set_setting(con, "notifications", cfg)
    assert reminders.tick(con, THU) == [] and sent == []


def test_weekly_summary(con):
    db.set_setting(con, "ngn_per_usd", 1500)
    money.add_earning(con, 150000, "NGN", client="A", earned_date="2026-11-10")
    content.log_post(con, "linkedin", "x", on="2026-11-11")
    w = reminders.weekly_summary(con, datetime(2026, 11, 12).date())
    assert w["start"] == "2026-11-09" and w["end"] == "2026-11-15"
    assert w["earned_usd"] == 100 and w["posts"]["linkedin"]["count"] == 1


def test_toast_text_cannot_become_powershell():
    evil = "Kemi'); Remove-Item C:\\ -Recurse; ('  $(calc) <x>"
    cmd = notify.build_command(notify.build_xml(evil, evil, url="http://127.0.0.1:8765/#today"))
    flat = " ".join(cmd)
    assert "Remove-Item" not in flat and "calc" not in flat  # outer command is base64 only
    script = base64.b64decode(cmd[-1]).decode("utf-16-le")
    assert "Remove-Item" not in script and "$(calc)" not in script  # inner script carries only base64 data
    xml = notify.build_xml(evil, evil)
    assert "&lt;x&gt;" in xml and "<x>" not in xml


def test_start_day_command_parses():
    from moyo import commands
    for t in ("good morning", "Good morning Moyo", "start my day", "let's start the day"):
        assert commands.parse(t) == ("start_day", {}), t
