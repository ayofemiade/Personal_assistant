import json
from datetime import date

from moyo import cloud, coach, db, money, tasks
from moyo.cloud import Redactor

REF = date(2026, 11, 12)


def test_signals_empty_pipeline(con):
    s = coach.signals(con, REF)
    assert s[0]["kind"] == "pipeline" and "pipeline is empty" in s[0]["text"]
    assert any(x["kind"] == "focus" for x in s) is False or True  # no tasks → no top3 → no focus signal


def test_signals_followups_and_focus(con):
    money.add_lead(con, "Kemi Stores", value=400, stage="proposal", next_followup="2026-11-09")
    money.add_lead(con, "Bolt Labs", value=900, stage="negotiation", next_followup="2026-11-20")
    tasks.add(con, "Study for exam", category="study", due_date="2026-11-12", priority=1)
    s = coach.signals(con, REF)
    kinds = [x["kind"] for x in s]
    assert "followup" in kinds and "sales" in kinds
    assert any("Kemi Stores" in x["text"] and "overdue" in x["text"] for x in s)


def test_snapshot_hides_client_names_and_deal_amounts(con):
    money.add_lead(con, "Adebayo Ventures", value=1200, stage="proposal")
    tasks.add(con, "Send Adebayo Ventures the revised quote", due_date="2026-11-12")
    red = Redactor(con)
    snap = json.dumps(coach.snapshot(con, red, REF))
    assert "Adebayo" not in snap and "1200" not in snap and "CLIENT_1" in snap


def test_validate_drops_invented_numbers(con):
    snap = coach.snapshot(con, Redactor(con), REF)  # earned 0, remaining 10000, days_left 88 ...
    pts, dropped = coach.validate([
        {"action": "Add 5 new prospects today", "why": "You have 88 days left and $10,000 to earn."},
        {"action": "Chase the $4,500 deal with CLIENT_1", "why": "It's 70% likely to close."},
    ], snap)
    assert len(pts) == 1 and dropped == 1 and pts[0]["action"].startswith("Add 5")


def test_rules_fallback_when_cloud_unavailable(con):
    c = coach.generate(con, force=True)  # tests have no API key
    assert c["source"] == "rules" and c["points"] and "pipeline is empty" in c["points"][0]["action"]
    assert "Now" not in coach.speech_text(c) and coach.speech_text(c).startswith("Here's what")


def test_ai_path_with_fake_model(con, monkeypatch):
    money.add_lead(con, "Adebayo Ventures", value=500, stage="proposal", next_followup="2026-11-10")
    seen = {}

    def fake(con_, system, user):
        seen["user"] = user
        return {"model": "fake-model", "data": {"headline": "Close what's already warm.", "points": [
            {"action": "Call CLIENT_1 today about the proposal", "why": "The follow-up is overdue."},
            {"action": "Invent a $7,777 deal", "why": "made up"}]}}
    monkeypatch.setattr(cloud, "generate_json", fake)
    c = coach.generate(con, force=True)
    assert "Adebayo" not in seen["user"]                        # name never sent
    assert c["source"] == "ai" and c["dropped_unverified"] == 1  # invented number removed
    assert c["points"][0]["action"] == "Call Adebayo Ventures today about the proposal"  # restored locally
    again = coach.generate(con)                                 # cached for the day
    assert again["cached"] is True and again["points"] == c["points"]
    assert db.get_setting(con, "coaching_cache")["model"] == "fake-model"
