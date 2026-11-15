"""Phase 2 ledger: exact money, append-only corrections, derived states, the $10K from real payments."""
import random

import pytest

from moyo import actions, db, invoices, money
from moyo.revenue import crm, ledger

RATE = 1300


@pytest.fixture
def L(con, monkeypatch):
    monkeypatch.setattr(invoices, "to_pdf", lambda html_text, out: out)  # no Chrome in tests
    db.set_setting(con, "ngn_per_usd", RATE)
    p = db.get_setting(con, "invoice_profile")
    db.set_setting(con, "invoice_profile", {**p, "next_number": 14})
    return con


def lagos_studio(con, **kw):
    """Golden case from the real Lagos Studio invoice: ₦350,000 − ₦50,000 = ₦300,000, 70% mobilisation."""
    return ledger.create_draft(con, "Lagos Studio Ltd", [
        {"item": "Website Services", "description": "Hosting & Domain Name (1 Year)", "amount": 50000},
        {"item": "Development", "description": "Website Development & Initial Maintenance", "amount": 300000}],
        discount=50000, deposit_pct=70, **kw)


def test_golden_lagos_studiostudio_deposit_then_balance(L):
    inv = lagos_studio(L)
    assert inv["number"] == "MC-014" and inv["total_minor"] == 30000000 and inv["state"] == "draft"
    inv = ledger.issue(L, inv["id"])
    assert inv["state"] == "issued" and inv["fx_ngn_per_usd"] == RATE
    p1 = ledger.record_payment(L, 210000, "NGN", "Lagos Studio Ltd", "2026-11-10", reference="FT123")
    assert p1["allocations"][0]["amount_minor"] == 21000000 and ledger.get(L, inv["id"])["state"] == "part_paid"
    ledger.record_payment(L, 90000, "NGN", "Lagos Studio Ltd", "2026-11-12")
    done = ledger.get(L, inv["id"])
    assert done["state"] == "paid" and done["balance_minor"] == 0 and done["paid_minor"] == 30000000
    assert money.challenge_status(L)["earned_usd"] == round(300000 / RATE, 2)  # $230.77 collected


def test_issued_invoices_cannot_be_edited_only_voided_with_reason(L):
    inv = ledger.issue(L, lagos_studio(L)["id"])
    with pytest.raises(ledger.LedgerError, match="can't be edited"):
        ledger.update_draft(L, inv["id"], items=[{"description": "x", "amount": 1}])
    with pytest.raises(ledger.LedgerError, match="reason"):
        ledger.void(L, inv["id"], "")
    ledger.record_payment(L, 1000, "NGN", invoice_id=inv["id"])
    with pytest.raises(ledger.LedgerError, match="payments against it"):
        ledger.void(L, inv["id"], "client cancelled")
    assert L.execute("SELECT COUNT(*) FROM ledger_adjustments").fetchone()[0] == 0


def test_issue_needs_a_rate_never_guesses(L):
    inv = lagos_studio(L)
    db.set_setting(L, "ngn_per_usd", None)
    with pytest.raises(ledger.LedgerError, match="rate"):
        ledger.issue(L, inv["id"])


def test_fifo_allocation_overpayment_and_currency(L):
    a = ledger.issue(L, ledger.create_draft(L, "Kemi Stores", [{"description": "Deposit", "amount": 200000}])["id"])
    b = ledger.issue(L, ledger.create_draft(L, "Kemi Stores", [{"description": "Balance", "amount": 200000}])["id"])
    usd = ledger.issue(L, ledger.create_draft(L, "Kemi Stores", [{"description": "Plugin", "amount": 100}], currency="USD")["id"])
    p = ledger.record_payment(L, 450000, "NGN", "Kemi Stores", "2026-11-12")
    assert [(x["number"], x["amount_minor"]) for x in p["allocations"]] == [(a["number"], 20000000), (b["number"], 20000000)]
    assert p["unallocated_minor"] == 5000000                       # ₦50,000 kept as credit, not invented anywhere
    assert ledger.get(L, usd["id"])["paid_minor"] == 0           # naira never pays a dollar invoice


def test_rate_change_never_rewrites_history(L):
    ledger.record_payment(L, 130000, "NGN", "Ade", "2026-11-12")
    before = money.challenge_status(L)["earned_usd"]
    db.set_setting(L, "ngn_per_usd", 2000)
    assert money.challenge_status(L)["earned_usd"] == before == 100.0


def test_refund_and_reversal(L):
    inv = ledger.issue(L, ledger.create_draft(L, "Bolt", [{"description": "Bot", "amount": 100}], currency="USD")["id"])
    p = ledger.record_payment(L, 100, "USD", "Bolt", "2026-11-12")
    with pytest.raises(ledger.LedgerError):
        ledger.refund(L, p["id"], 150, "too much")
    ledger.refund(L, p["id"], 40, "partial scope cut")
    assert money.challenge_status(L)["earned_usd"] == 60.0
    q = ledger.record_payment(L, 999, "USD", "Bolt", "2026-11-12")  # typo
    ledger.reverse_payment(L, q["id"], "typed the wrong amount")
    assert money.challenge_status(L)["earned_usd"] == 60.0 and ledger.payment(L, q["id"])["reversed"]
    assert ledger.get(L, inv["id"])["paid_minor"] == 10000       # the reversed entry's allocation stopped counting
    assert L.execute("SELECT COUNT(*) FROM ledger_payments").fetchone()[0] == 2  # nothing deleted


def test_challenge_window_and_future_dates(L):
    ledger.record_payment(L, 130000, "NGN", "Old client", "2026-11-01")   # before 8 Nov: excluded
    assert money.challenge_status(L)["earned_usd"] == 0
    with pytest.raises(ledger.LedgerError, match="future"):
        ledger.record_payment(L, 1, "NGN", "X", "2030-01-01")


def test_history_is_never_owed_or_paid(L):
    from moyo.revenue import history
    history.import_invoice(L, {"number": "MC-001", "date": "2026-09-10", "company": "Grace Mission",
                               "lines": [{"description": "Domain & Hosting renewal (1 year)", "amount": 100000}]})
    assert ledger.owed(L)["invoices"] == [] and ledger.listing(L)[0]["state"] == "historical"


def test_overdue_is_derived(L):
    inv = ledger.issue(L, ledger.create_draft(L, "Late Co", [{"description": "Site", "amount": 50000}], due_days=0)["id"])
    L.execute("UPDATE ledger_invoices SET due_date='2026-11-01' WHERE id=?", (inv["id"],))
    o = ledger.owed(L)
    assert o["overdue"][0]["number"] == inv["number"] and o["overdue_by_currency"]["NGN"] == 50000


def test_actions_issue_and_pay_by_invoice_number(L):
    inv = lagos_studio(L)
    r = actions.execute(L, "issue_invoice", {"number": inv["number"]})
    assert r["needs_confirmation"] and "SENT" in r["reply"] and ledger.get(L, inv["id"])["status"] == "draft"
    actions.confirm(L, r["pending_id"], True)
    r = actions.execute(L, "log_payment", {"amount": 210000, "currency": "NGN", "paid": True, "invoice": "14"})
    assert "settles" in r["reply"] and "MC-014" in r["reply"]
    done = actions.confirm(L, r["pending_id"], True)
    assert "settling MC-014" in done["reply"] and ledger.get(L, inv["id"])["state"] == "part_paid"


def test_legacy_draft_invoices_move_to_ledger(L):
    invoices.create(L, "kemi", [{"description": "Website", "amount": 500000}], make_pdf=False)
    assert ledger.migrate_legacy_invoices(L) == 1 and ledger.migrate_legacy_invoices(L) == 0
    inv = ledger.listing(L)[0]
    assert inv["number"] == "MC-014" and inv["total"] == 500000 and inv["status"] == "draft"
    assert ledger.next_number(L) == "MC-015"


def test_random_allocations_keep_invariants(L):
    rnd = random.Random(7)
    ids = [ledger.issue(L, ledger.create_draft(L, "Rand Co", [{"description": f"Item {i}", "amount": rnd.randint(1000, 90000)}])["id"])["id"]
           for i in range(6)]
    for _ in range(12):
        ledger.record_payment(L, rnd.randint(500, 60000), "NGN", "Rand Co", "2026-11-12")
    for i in ids:
        inv = ledger.get(L, i)
        assert 0 <= inv["paid_minor"] <= inv["total_minor"] and inv["balance_minor"] == inv["total_minor"] - inv["paid_minor"]
    for p in ledger.payments(L):
        assert sum(a["amount_minor"] for a in p["allocations"]) <= p["amount_minor"]


# ---------------------------------------------------------------- proposals
from moyo.revenue import proposals  # noqa: E402


def test_proposal_versions_status_and_invoice(L):
    d = crm.create_deal(L, "Kemi Stores · website", company_id=crm.get_or_create_company(L, "Kemi Stores")["id"], stage_k="discovery")
    p = proposals.create(L, d["id"], {"problem": "Orders come in by DM and get lost.", "scope": "Product catalogue\nPaystack checkout",
                                      "pricing": [{"description": "Website design & development", "amount": "₦400,000"},
                                                  {"description": "Hosting & domain (1 year)", "amount": 50000}],
                                      "deposit_pct": 50})
    assert p["number"] == "P-001" and p["version"] == 1 and p["total"] == 450000 and p["content"]["scope"] == ["Product catalogue", "Paystack checkout"]
    with pytest.raises(proposals.ProposalError):
        proposals.set_status(L, p["id"], "accepted")               # must be sent first
    proposals.set_status(L, p["id"], "sent")
    d2 = crm.get_deal(L, d["id"])
    assert d2["stage_key"] == "proposal" and d2["value"] == 450000  # moved forward, value from the proposal
    p = proposals.save(L, p["id"], {"pricing": [{"description": "Website", "amount": 380000}]})
    assert p["version"] == 2 and p["status"] == "draft" and len(p["versions"]) == 2   # v1 (sent) stays on record
    proposals.set_status(L, p["id"], "sent")
    proposals.set_status(L, p["id"], "accepted")
    inv = proposals.to_invoice(L, p["id"])
    assert inv["status"] == "draft" and inv["total"] == 380000 and inv["deposit_pct"] == 50 and inv["deal_id"] == d["id"]
    with pytest.raises(proposals.ProposalError, match="already exists"):
        proposals.to_invoice(L, p["id"])
    assert "Investment" in proposals.render_html(L, proposals.get(L, p["id"]))


def test_proposal_prices_never_guessed(L):
    d = crm.create_deal(L, "X", stage_k="engaged")
    with pytest.raises(Exception, match="won't guess"):
        proposals.create(L, d["id"], {"pricing": [{"description": "Website"}]})


# ---------------------------------------------------------------- renewals & reminders
def test_renewals_from_history_and_overdue_reminder(L):
    from datetime import datetime

    from moyo import reminders
    from moyo.revenue import history, renewals
    history.import_invoice(L, {"number": "MC-001", "date": "2025-11-20", "company": "Grace Mission",
                               "lines": [{"description": "Domain & Hosting renewal (1 year)", "amount": 100000}]})
    history.import_invoice(L, {"number": "MC-001", "date": "2026-07-03", "company": "Ade Law firm",
                               "lines": [{"description": "Website Maintenance (Annual)", "amount": 400000}]})
    up = renewals.upcoming(L)
    assert [(r["company"], r["kind"], r["due"]) for r in up] == [("Grace Mission", "hosting", "2026-11-20"), ("Ade Law firm", "maintenance", "2027-07-03")]
    inv = ledger.issue(L, ledger.create_draft(L, "Late Co", [{"description": "Site", "amount": 50000}])["id"])
    L.execute("UPDATE ledger_invoices SET due_date='2026-11-05' WHERE id=?", (inv["id"],))
    keys = {c["key"]: c for c in reminders.candidates(L, datetime(2026, 11, 12, 10, 0))}
    assert any(k.startswith(f"invoice-overdue:{inv['id']}:") for k in keys)
    assert any(k.startswith("renewal:") and "2026-11-20" in k for k in keys)      # within 30 days
    assert not any("2027-07-03" in k for k in keys)                              # too far ahead to nag
