from datetime import date, datetime

import pytest

from moyo import actions, commands, content, db, memory, money, planner, tasks
from moyo.cloud import Redactor
from moyo.dates import parse_amount, parse_date, parse_time

REF = date(2026, 11, 12)  # Thursday


# ---------------------------------------------------------------- parsing helpers
@pytest.mark.parametrize("text,expected", [
    ("tomorrow", date(2026, 11, 13)), ("friday", date(2026, 11, 13)), ("on Friday", date(2026, 11, 13)),
    ("next friday", date(2026, 11, 13)), ("thursday", date(2026, 11, 19)), ("monday", date(2026, 11, 16)),
    ("next week", date(2026, 11, 16)), ("in 3 days", date(2026, 11, 15)), ("15 november", date(2026, 11, 15)),
    ("5 jan", date(2027, 1, 5)), ("20/11", date(2026, 11, 20)), ("2026-12-01", date(2026, 12, 1)), ("today", REF),
])
def test_parse_date(text, expected):
    assert parse_date(text, REF) == expected


@pytest.mark.parametrize("text,expected", [
    ("₦200,000", (200000, "NGN")), ("200k naira", (200000, "NGN")), ("$500", (500, "USD")),
    ("five hundred dollars", (500, "USD")), ("two hundred thousand naira", (200000, "NGN")),
    ("1.5m", (1500000, None)), ("250 usd", (250, "USD")),
])
def test_parse_amount(text, expected):
    assert parse_amount(text) == expected


def test_parse_time():
    assert parse_time("10 a.m.") == "10:00" and parse_time("7pm") == "19:00" and parse_time("at 3:30 pm") == "15:30"


# ---------------------------------------------------------------- command parser (the 30 voice phrases + more)
@pytest.mark.parametrize("text,action,check", [
    ("Moyo, what's my plan for today?", "get_daily_plan", {}),
    ("Which of my tasks is most important?", "get_daily_plan", {}),
    ("Add a task to contact that potential client tomorrow.", "add_task", {"due": "2026-11-13"}),
    ("How much have we generated towards the ten K target?", "get_target_progress", {}),
    ("Open my development workspace.", "open_workspace", {"profile": "development"}),
    ("Move that task to Friday.", "move_task", {"new_date": "2026-11-13"}),
    ("Log a payment of two hundred thousand naira from Adebayo Ventures.", "log_payment",
     {"amount": 200000, "currency": "NGN", "client": "Adebayo Ventures"}),
    ("log payment ₦150,000 from Kemi Stores paid", "log_payment", {"amount": 150000, "paid": True, "client": "Kemi Stores"}),
    ("I earned $300 from Bolt Labs", "log_payment", {"amount": 300, "currency": "USD", "client": "Bolt Labs"}),
    ("Add a new lead called Chukwuemeka Foods, website redesign, five hundred dollars.", "add_lead",
     {"name": "Chukwuemeka Foods", "service": "website redesign", "value": 500, "currency": "USD"}),
    ("Mark the proposal for Oluwaseun as sent.", "update_lead", {"name": "Oluwaseun", "stage": "proposal"}),
    ("Remind me to follow up with Tunde on Thursday at ten a.m.", "add_task", {"due": "2026-11-19", "due_time": "10:00"}),
    ("follow up with Tunde tomorrow", "add_task", {"title": "Follow up with Tunde", "category": "sales", "due": "2026-11-13"}),
    ("Start coding mode and play my focus playlist.", None, {}),
    ("Pause the music.", "media", {"action": "play_pause"}),
    ("Turn the volume down a little.", "media", {"action": "volume_down"}),
    ("Did I post on TikTok today?", "get_content_status", {}),
    ("What do you know about me?", "what_do_you_know", {}),
    ("Forget the ConvergsAI pricing idea.", "forget", {"about": "ConvergsAI pricing idea"}),
    ("How much do I need to earn per week to hit the target?", "get_target_progress", {}),
    ("Create a recurring task to publish an Instagram reel every day at seven p.m.", "add_task",
     {"recurrence": "daily", "due_time": "19:00"}),
    ("Read my morning briefing.", "get_briefing", {}),
    ("I posted on TikTok: why most Nigerian businesses lose leads", "log_post", {"platform": "tiktok"}),
    ("done 4", "complete_task", {"task_id": 4}),
    ("set rate 1500", "set_rate", {"ngn_per_usd": 1500}),
    ("coding mode", "open_workspace", {"profile": "coding"}),
    ("What's on my Google Calendar this afternoon?", "get_calendar", {}),
    ("any meetings tomorrow?", "get_calendar", {"day": "2026-11-13"}),
    ("what's on my calendar on Monday", "get_calendar", {"day": "2026-11-16"}),
    ("check my emails", "get_inbox", {}),
    ("do I have any unread mail from clients", "get_inbox", {}),
    ("add task send proposal to Tunde tomorrow urgent", "add_task",
     {"title": "send proposal to Tunde", "due": "2026-11-13", "priority": 1}),
])
def test_parser(text, action, check):
    r = commands.parse(text)
    if action is None:
        return  # allowed to fall through to cloud
    assert r is not None, text
    assert r[0] == action, (text, r)
    for k, v in check.items():
        assert r[1].get(k) == v, (text, k, r[1])


def test_parser_unknown_goes_to_cloud():
    assert commands.parse("what's the meaning of life") is None


# ---------------------------------------------------------------- money
def test_challenge_empty(con):
    st = money.challenge_status(con, REF)
    assert st["earned_usd"] == 0 and st["remaining_usd"] == 10000
    assert st["days_total"] == 92 and st["days_left"] == 88
    assert st["required_per_week_usd"] == pytest.approx(10000 / (88 / 7), abs=0.01)
    assert not st["on_track"]


def test_ngn_requires_rate(con):
    with pytest.raises(money.MoneyError):
        money.add_earning(con, 200000, "NGN", client="X")


def test_earnings_math(con):
    db.set_setting(con, "ngn_per_usd", 1600)
    money.add_earning(con, 320000, "NGN", client="Adebayo", earned_date="2026-11-10")
    money.add_earning(con, 500, "USD", client="Bolt", earned_date="2026-11-11", paid=True)
    money.add_earning(con, 999, "USD", client="Old", earned_date="2026-11-01")  # before challenge: excluded
    st = money.challenge_status(con, REF)
    # D41: the $10K counts money when PAID; the unpaid ₦320k ($200) is outstanding, not progress
    # outstanding = everything still owed (incl. the pre-challenge $999): money owed is owed regardless of the window
    assert st["earned_usd"] == 500 and st["collected_usd"] == 500 and st["outstanding_usd"] == 1199
    assert st["earned_this_week_usd"] == 500 and st["progress_word"] == "collected"
    # rate change later doesn't alter past entries
    db.set_setting(con, "ngn_per_usd", 2000)
    assert money.challenge_status(con, REF)["earned_usd"] == 500


def test_pipeline(con):
    money.add_lead(con, "Chukwuemeka Foods", value=500, stage="proposal", next_followup="2026-11-10")
    money.add_lead(con, "Nobody", stage="new")
    p = money.pipeline_summary(con, REF)
    assert p["weighted_usd"] == 250 and p["open"] == 2
    assert p["followups_due"][0]["overdue"] is True and p["leads_without_value"] == 1


# ---------------------------------------------------------------- tasks
def test_recurring_task(con):
    t = tasks.add(con, "Publish IG reel", due_date="2026-11-12", recurrence="daily")
    r = tasks.complete(con, t["id"])
    assert r["next"]["due_date"] == "2026-11-13" and r["next"]["recurrence"] == "daily"
    w = tasks.add(con, "LinkedIn post", due_date="2026-11-13", recurrence="weekly:MO,WE,FR")
    assert tasks.complete(con, w["id"])["next"]["due_date"] == "2026-11-16"


def test_category_guess():
    assert tasks.guess_category("Send proposal to Tunde") == "sales"
    assert tasks.guess_category("Send invoice to Kemi") == "revenue"
    assert tasks.guess_category("Record TikTok video") == "content"


# ---------------------------------------------------------------- planner
def test_planner_priorities_and_no_overlap(con):
    tasks.add(con, "Study for exam", category="study", due_date="2026-11-20")
    tasks.add(con, "Send invoice to Kemi", due_date="2026-11-12", estimate_min=30)
    tasks.add(con, "Fix client website bug", category="client", due_date="2026-11-11", estimate_min=60)
    p = planner.build(con, REF)
    assert p["top3"][0]["title"] in ("Fix client website bug", "Send invoice to Kemi")
    assert all(x["why"] for x in p["top3"])
    blocks = sorted(p["blocks"], key=lambda b: b["start"])
    for a, b in zip(blocks, blocks[1:]):
        assert a["end"] <= b["start"], (a, b)
    assert p["planned_minutes"] <= p["free_minutes"] * 0.85 + 1
    assert any(b["title"] == "Startup meeting (work)" for b in blocks)  # Thursday
    assert blocks[-1]["kind"] == "review"


def test_planner_respects_now(con):
    tasks.add(con, "Proposal", due_date="2026-11-12")
    p = planner.build(con, REF, now=datetime(2026, 11, 12, 16, 7))
    task_blocks = [b for b in p["blocks"] if b["kind"] == "task"]
    assert all(b["start"] >= "16:15" for b in task_blocks)


def test_content_pending_items_in_plan(con):
    p = planner.build(con, REF)
    titles = [b["title"] for b in p["blocks"]]
    assert "Create & publish TikTok video" in titles
    content.log_post(con, "tiktok", "x")
    assert "Create & publish TikTok video" not in [b["title"] for b in planner.build(con, REF)["blocks"]]


# ---------------------------------------------------------------- gateway
def test_payment_needs_confirmation(con):
    db.set_setting(con, "ngn_per_usd", 1500)
    r = actions.execute(con, "log_payment", {"amount": 150000, "currency": "NGN", "client": "Ade", "paid": True})
    assert r["needs_confirmation"] and "₦150,000" in r["reply"]
    assert money.challenge_status(con, REF)["earned_usd"] == 0  # nothing written yet
    done = actions.confirm(con, r["pending_id"], True)
    assert not done.get("error") and money.challenge_status(con, REF)["earned_usd"] == 100
    assert actions.confirm(con, r["pending_id"], True)["error"]  # can't replay


def test_cancel_and_prohibited(con):
    r = actions.execute(con, "forget", {"about": "ConvergsAI"})
    before = len(memory.listing(con))
    actions.confirm(con, r["pending_id"], False)
    assert len(memory.listing(con)) == before
    assert actions.execute(con, "run_shell", {"cmd": "del *"})["error"]
    log = con.execute("SELECT action, result FROM audit_log ORDER BY id").fetchall()
    assert ("run_shell", "refused") in [tuple(x) for x in log]


def test_plan_memory_requires_expiry(con):
    with pytest.raises(ValueError):
        memory.add(con, "Focus on Lagos restaurants this week", kind="plan")


# ---------------------------------------------------------------- privacy
def test_redactor(con):
    money.add_lead(con, "Adebayo Ventures")
    red = Redactor(con)
    s = red.redact("remind me to chase Adebayo Ventures about the ₦200,000 invoice on 14 Nov")
    assert "Adebayo" not in s and "200,000" not in s and "14 Nov" in s
    assert red.restore({"title": "Chase CLIENT_1 about AMOUNT_1"})["title"] == "Chase Adebayo Ventures about ₦200,000"


def test_seed_has_no_invented_numbers(con):
    assert con.execute("SELECT COUNT(*) FROM earnings").fetchone()[0] == 0
    assert con.execute("SELECT COUNT(*) FROM leads").fetchone()[0] == 0
    assert db.get_setting(con, "ngn_per_usd") is None
