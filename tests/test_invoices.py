import pytest

from moyo import actions, cloud, db, invoices


@pytest.fixture
def prof(con):
    p = db.get_setting(con, "invoice_profile")
    db.set_setting(con, "invoice_profile", {**p, "next_number": 14, "bank": {
        "name": "FCMB (First City Monument Bank)", "account_name": "Moyocode Technologies", "number": "0123456789"}})
    return con


def test_totals_are_calculated_not_guessed():
    t = invoices.build([{"description": "Website development", "amount": "₦150,000"},
                        {"description": "Hosting", "amount": 50000, "qty": 2}], discount="₦20,000", deposit_pct=50)
    assert t["subtotal"] == 250000 and t["total"] == 230000 and t["deposit"] == 115000 and t["balance"] == 115000


def test_missing_or_bad_amounts_are_refused():
    with pytest.raises(invoices.InvoiceError, match="won't guess"):
        invoices.build([{"description": "Website"}])
    with pytest.raises(invoices.InvoiceError):
        invoices.build([{"description": "Website", "amount": 100}], discount=500)
    with pytest.raises(invoices.InvoiceError):
        invoices.build([])


def test_numbering_continues_and_stays_unique(prof):
    a = invoices.create(prof, "Kemi Stores", [{"description": "Website", "amount": 450000}], make_pdf=False)
    b = invoices.create(prof, "Tunde Ltd", [{"description": "Logo", "amount": 50000}], make_pdf=False)
    assert (a["number"], b["number"]) == ("MC-014", "MC-015")
    assert db.get_setting(prof, "invoice_profile")["next_number"] == 16


def test_layout_and_html(prof):
    p = db.get_setting(prof, "invoice_profile")
    inv = invoices.create(prof, "<script>x</script> Co", [{"description": "Website", "amount": 150000}],
                          deposit_pct=50, make_pdf=False)
    h = invoices.render_html(p, inv)
    assert inv["layout"] == "simple" and "Deposit Due (50%)" in h and "₦75,000" in h
    assert "0123456789" in h and "Moyocode Technologies" in h and "<script>x" not in h  # client text is escaped
    inv2 = invoices.create(prof, "LagosStudio", [{"item": "Development", "description": "Website", "amount": 300000}],
                           discount=50000, make_pdf=False)
    h2 = invoices.render_html(p, inv2)
    assert inv2["layout"] == "itemized" and "Total Project Value" in h2 and "- ₦50,000" in h2 and "₦250,000" in h2


def test_action_creates_draft_only(prof, monkeypatch):
    monkeypatch.setattr(invoices, "to_pdf", lambda html_text, out: out)
    r = actions.execute(prof, "create_invoice", {"client": "Kemi Stores",
                                                 "items": [{"description": "Website", "amount": "₦450,000"}],
                                                 "deposit_pct": 50}, actor="user")
    assert "MC-014" in r["reply"] and "haven't sent it" in r["reply"] and "₦225,000" in r["reply"]
    assert prof.execute("SELECT COUNT(*) FROM earnings").fetchone()[0] == 0  # never logged as earned
    assert actions.REGISTRY["create_invoice"].tier == "low"
    r2 = actions.execute(prof, "create_invoice", {"client": "X", "items": [{"description": "Website"}]})
    assert r2.get("error") and "won't guess" in r2["reply"]


def test_redacted_amounts_restore_inside_item_lists(con):
    red = cloud.Redactor(con)
    red.map = {"AMOUNT_1": "₦450,000", "CLIENT_1": "Kemi Stores"}
    out = red.restore({"client": "CLIENT_1", "items": [{"description": "Website", "amount": "AMOUNT_1"}]})
    assert out == {"client": "Kemi Stores", "items": [{"description": "Website", "amount": "₦450,000"}]}
