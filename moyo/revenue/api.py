"""HTTP endpoints for the Revenue screens. Mounted by server.py; same guard (localhost, X-Moyo on writes),
same lock and audit log. Nothing here sends anything outside the laptop except AI calls the user triggers
(drafts/summaries, D41)."""
from __future__ import annotations

from datetime import date, timedelta

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from moyo import audit, db, money
from moyo.revenue import capture, conversations, crm, followups, outreach

router = APIRouter(prefix="/api/rev")
_run = None  # set by server.mount(): (fn) -> result under the DB lock
_con = None


def mount(app, run, con):
    global _run, _con
    _run, _con = run, con
    app.include_router(router)


def go(fn):
    try:
        return _run(fn)
    except crm.DuplicateError as e:
        return JSONResponse({"detail": str(e), "duplicate": {"id": e.existing["id"], "full_name": e.existing["full_name"]}},
                            status_code=409)
    except crm.CRMError as e:
        raise HTTPException(400, str(e))


def _stats(c) -> dict:
    deals = crm.list_deals(c)
    open_d = [d for d in deals if d["is_open"]]
    by_cur: dict = {}
    for d in open_d:
        if d["value"]:
            by_cur[d["currency"]] = by_cur.get(d["currency"], 0) + d["value"]
    pipe = money.pipeline_summary(c)
    hist = c.execute("SELECT COUNT(*) n, AVG(t) a FROM (SELECT SUM(l.amount_minor) t FROM ledger_invoices i "
                     "JOIN ledger_invoice_lines l ON l.invoice_id=i.id WHERE i.historical=1 AND i.currency='NGN' "
                     "GROUP BY i.id)").fetchone()
    ch = money.challenge_status(c)
    rate = db.get_setting(c, "ngn_per_usd")
    avg_ngn = (hist["a"] / 100) if hist["n"] else None
    needed = None
    if avg_ngn and rate and ch["remaining_usd"]:
        needed = round(ch["remaining_usd"] * rate / avg_ngn)
    return {"open": len(open_d), "open_value_by_currency": by_cur, "weighted_usd": pipe["weighted_usd"],
            "no_next_step": len(pipe["neglected"]), "won": sum(1 for d in deals if d["stage_key"] == "won"),
            "lost": sum(1 for d in deals if d["stage_key"] == "lost"),
            "avg_past_invoice_ngn": round(avg_ngn) if avg_ngn else None, "past_invoices": hist["n"],
            "deals_needed_at_avg": needed, "challenge": ch}


@router.get("/overview")
def overview():
    def f():
        c = _con()
        board = []
        recent = (date.today() - timedelta(days=30)).isoformat()
        for s in crm.stages(c):
            ds = [d for d in crm.list_deals(c) if d["stage_key"] == s["key"]
                  and (s["is_open"] or (d["updated_at"] or "")[:10] >= recent)]
            board.append({**s, "deals": ds})
        return {"today": followups.today_list(c), "board": board, "stats": _stats(c)}
    return go(f)


class TextIn(BaseModel):
    text: str


@router.post("/capture/preview")
def capture_preview(body: TextIn):
    return go(lambda: capture.extract(_con(), body.text[:2000]))


@router.post("/capture/commit")
def capture_commit(fields: dict):
    def f():
        c = _con()
        r = capture.commit(c, capture.normalize({k: v for k, v in fields.items() if k not in ("ai_fields", "missing")}))
        audit.log(c, "user", "capture_lead", "low", {"deal_id": r["deal"]["id"], "ai_fields": fields.get("ai_fields")})
        return r
    return go(f)


@router.get("/deal/{did}")
def deal_detail(did: int):
    def f():
        c = _con()
        d = crm.get_deal(c, did)
        contact = crm.get_contact(c, d["primary_contact_id"]) if d["primary_contact_id"] else None
        convs = db.rows(c.execute("SELECT id, imported_from, created_at, summary, (SELECT COUNT(*) FROM messages m "
                                  "WHERE m.conversation_id=conversations.id) n FROM conversations WHERE contact_id=? "
                                  "ORDER BY id DESC", (d["primary_contact_id"],))) if d["primary_contact_id"] else []
        return {"deal": d, "contact": contact, "timeline": crm.timeline(c, deal_id=did, contact_id=d["primary_contact_id"]),
                "conversations": convs, "stages": crm.stages(c), "today": followups.evaluate(c, d, db.today())}
    return go(f)


@router.patch("/deal/{did}")
def deal_patch(did: int, body: dict):
    def f():
        c = _con()
        allowed = crm.DEAL_FIELDS | {"stage"}
        fields = {k: v for k, v in body.items() if k in allowed}
        d = crm.update_deal(c, did, **fields)
        audit.log(c, "user", "edit_deal", "low", {"id": did, **fields})
        return d
    return go(f)


class FollowIn(BaseModel):
    action: str                      # done | snooze | reschedule | dismiss
    days: int | None = None
    due: str | None = None
    note: str | None = None
    channel: str | None = None
    next_due: str | None = None
    next_action: str | None = None
    reason: str | None = None


@router.post("/deal/{did}/followup")
def deal_followup(did: int, body: FollowIn):
    def f():
        c = _con()
        if body.action == "done":
            r = followups.done(c, did, body.note, body.channel, body.next_due, body.next_action)
        elif body.action == "snooze":
            r = followups.snooze(c, did, body.days or 1)
        elif body.action == "reschedule":
            r = followups.reschedule(c, did, body.due, body.next_action)
        elif body.action == "dismiss":
            followups.dismiss(c, did, body.reason or "")
            r = crm.get_deal(c, did)
        else:
            raise crm.CRMError("Unknown follow-up action.")
        audit.log(c, "user", f"followup_{body.action}", "low", {"deal_id": did})
        return r
    return go(f)


class ContactIn(BaseModel):
    full_name: str
    phone: str | None = None
    whatsapp: str | None = None
    email: str | None = None
    role: str | None = None


@router.post("/deal/{did}/contact")
def deal_contact(did: int, body: ContactIn):
    """Add (or attach an existing) contact to a deal so drafts can be opened in WhatsApp/Gmail."""
    def f():
        c = _con()
        d = crm.get_deal(c, did)
        if d["primary_contact_id"]:  # add channels to the existing person
            for kind in ("phone", "whatsapp", "email"):
                v = getattr(body, kind)
                if v:
                    crm.add_channel(c, d["primary_contact_id"], kind, v)
            cid = d["primary_contact_id"]
        else:
            cont = crm.create_contact(c, body.full_name, company_id=d["company_id"], phone=body.phone,
                                      whatsapp=body.whatsapp, email=body.email, role=body.role)
            cid = cont["id"]
            c.execute("UPDATE deals SET primary_contact_id=?, updated_at=? WHERE id=?", (cid, db.now_iso(), did))
            c.execute("INSERT OR IGNORE INTO deal_contacts(deal_id, contact_id, role) VALUES (?,?, 'primary')", (did, cid))
        audit.log(c, "user", "edit_contact", "low", {"deal_id": did, "contact_id": cid})
        return crm.get_contact(c, cid)
    return go(f)


@router.post("/deal/{did}/note")
def deal_note(did: int, body: TextIn):
    def f():
        c = _con()
        crm.log_activity(c, "note", body.text.strip()[:2000], deal_id=did)
        audit.log(c, "user", "deal_note", "low", {"deal_id": did})
        return {"ok": True}
    return go(f)


class DraftIn(BaseModel):
    deal_id: int
    channel: str = "whatsapp"
    goal: str | None = None


@router.post("/draft")
def draft(body: DraftIn):
    def f():
        c = _con()
        r = outreach.draft(c, body.deal_id, body.channel, body.goal)
        audit.log(c, f"cloud:{r['source']}" if r["source"] != "template" else "moyo", "draft_followup", "read",
                  {"deal_id": body.deal_id, "channel": body.channel})
        return r
    return go(f)


class SentIn(BaseModel):
    deal_id: int
    channel: str
    text: str
    next_due: str | None = None
    next_action: str | None = None


@router.post("/sent")
def sent(body: SentIn):
    """You pressed send in WhatsApp/Gmail: log it, and set the next step."""
    def f():
        c = _con()
        outreach.mark_sent(c, body.deal_id, body.channel, body.text)
        d = followups.done(c, body.deal_id, note=None, channel=None, next_due=body.next_due,
                           next_action=body.next_action) if body.next_due is not None else crm.get_deal(c, body.deal_id)
        audit.log(c, "user", "message_sent_by_user", "low", {"deal_id": body.deal_id, "channel": body.channel})
        return d
    return go(f)


class ImportIn(BaseModel):
    deal_id: int
    text: str
    source: str = "export"


@router.post("/import")
def import_chat(body: ImportIn):
    def f():
        c = _con()
        r = conversations.import_chat(c, body.text[:2_000_000], deal_id=body.deal_id,
                                      source="paste" if body.source == "paste" else "export")
        audit.log(c, "user", "import_whatsapp", "low", {"deal_id": body.deal_id, "messages": r["messages"], "new": r["new"]})
        return r
    return go(f)


@router.post("/conversation/{cid}/summarize")
def conv_summarize(cid: int):
    def f():
        c = _con()
        r = conversations.summarize(c, cid)
        audit.log(c, f"cloud:{r.get('model')}" if r.get("model") else "moyo", "summarize_conversation", "read",
                  {"conversation_id": cid, "ok": "error" not in r})
        return r
    return go(f)


class ConfirmSummaryIn(BaseModel):
    deal_id: int | None = None
    summary: str = ""
    commitments: list[dict] = []
    next_step: str | None = None
    next_due: str | None = None


@router.post("/conversation/{cid}/confirm")
def conv_confirm(cid: int, body: ConfirmSummaryIn):
    def f():
        c = _con()
        r = conversations.confirm_summary(c, cid, body.deal_id, body.summary, body.commitments, body.next_step, body.next_due)
        audit.log(c, "user", "confirm_conversation_summary", "low", {"conversation_id": cid, **r})
        return r
    return go(f)


class MergeIn(BaseModel):
    keep_id: int
    merge_id: int


@router.post("/merge")
def merge(body: MergeIn):
    def f():
        c = _con()
        r = crm.merge_contacts(c, body.keep_id, body.merge_id)
        audit.log(c, "user", "merge_contacts", "confirm", {"keep": body.keep_id, "merged": body.merge_id})
        return r
    return go(f)


# ---------------------------------------------------------------- Phase 2: money, invoices, proposals
@router.get("/money")
def money_overview():
    def f():
        c = _con()
        from moyo.revenue import ledger, renewals
        legacy = db.rows(c.execute("SELECT * FROM earnings ORDER BY earned_date DESC, id DESC"))
        o = ledger.owed(c)
        light = lambda i: {k: i[k] for k in ("id", "number", "client", "issue_date", "due_date", "currency", "total", "paid",  # noqa: E731
                                              "balance", "state", "status", "deal_id", "pdf_path", "deposit_pct", "historical")}
        return {"challenge": money.challenge_status(c), "ngn_per_usd": db.get_setting(c, "ngn_per_usd"),
                "owed": [light(i) for i in o["invoices"]], "outstanding_by_currency": o["outstanding_by_currency"],
                "overdue_by_currency": o["overdue_by_currency"],
                "invoices": [light(i) for i in ledger.listing(c)],
                "payments": [{k: p[k] for k in ("id", "received_date", "amount", "currency", "method", "reference", "payer_label",
                                                "company", "allocations", "refunded_minor", "reversed", "unallocated_minor")}
                             for p in ledger.payments(c)],
                "renewals": renewals.upcoming(c), "legacy_earnings": legacy}
    return go(f)


class InvoiceIn(BaseModel):
    client: str | None = None
    deal_id: int | None = None
    items: list[dict]
    discount: float = 0
    deposit_pct: int | None = None
    due_days: int | None = None
    bill_to: str | None = None
    notes: list[str] | None = None
    currency: str = "NGN"


@router.post("/invoice")
def invoice_create(body: InvoiceIn):
    def f():
        from moyo import invoices as ui
        from moyo.revenue import ledger
        c = _con()
        try:
            inv = ledger.create_draft(c, body.client, body.items, body.discount, body.deposit_pct, body.due_days, body.bill_to,
                                      body.notes, body.currency, deal_id=body.deal_id)
        except (ui.InvoiceError, ledger.LedgerError) as e:
            raise crm.CRMError(str(e))
        audit.log(c, "user", "create_invoice", "low", {"number": inv["number"], "deal_id": body.deal_id})
        return {"id": inv["id"], "number": inv["number"], "pdf_path": inv["pdf_path"]}
    return go(f)


@router.get("/invoice/{iid}")
def invoice_get(iid: int):
    from moyo.revenue import ledger
    return go(lambda: ledger.get(_con(), iid))


def _open_file(path: str | None):
    import os
    if not path or not os.path.exists(path):
        raise crm.CRMError("That PDF isn't there any more.")
    if os.environ.get("MOYO_NO_BACKGROUND") != "1":
        os.startfile(path)
    return {"ok": True}


@router.post("/invoice/{iid}/open")
def invoice_open(iid: int):
    from moyo.revenue import ledger
    return go(lambda: _open_file(ledger.get(_con(), iid).get("pdf_path")))


@router.post("/proposal/{pid}/open")
def proposal_open(pid: int):
    from moyo.revenue import proposals
    return go(lambda: _open_file(proposals.get(_con(), pid).get("pdf_path")))


class ProposalIn(BaseModel):
    deal_id: int
    content: dict


@router.post("/proposal")
def proposal_create(body: ProposalIn):
    def f():
        from moyo import invoices as ui
        from moyo.revenue import proposals
        c = _con()
        try:
            p = proposals.create(c, body.deal_id, body.content)
        except (ui.InvoiceError, proposals.ProposalError) as e:
            raise crm.CRMError(str(e))
        audit.log(c, "user", "create_proposal", "low", {"number": p["number"], "deal_id": body.deal_id})
        return p
    return go(f)


@router.get("/proposal/{pid}")
def proposal_get(pid: int):
    from moyo.revenue import proposals
    return go(lambda: proposals.get(_con(), pid))


@router.put("/proposal/{pid}")
def proposal_save(pid: int, content: dict):
    def f():
        from moyo import invoices as ui
        from moyo.revenue import proposals
        c = _con()
        try:
            p = proposals.save(c, pid, content)
        except (ui.InvoiceError, proposals.ProposalError) as e:
            raise crm.CRMError(str(e))
        audit.log(c, "user", "save_proposal", "low", {"id": pid, "version": p["version"]})
        return p
    return go(f)


class StatusIn(BaseModel):
    status: str
    reason: str | None = None


@router.post("/proposal/{pid}/status")
def proposal_status(pid: int, body: StatusIn):
    def f():
        from moyo.revenue import proposals
        c = _con()
        try:
            p = proposals.set_status(c, pid, body.status, body.reason)
        except proposals.ProposalError as e:
            raise crm.CRMError(str(e))
        audit.log(c, "user", f"proposal_{body.status}", "low", {"id": pid})
        return p
    return go(f)


@router.post("/proposal/{pid}/invoice")
def proposal_invoice(pid: int):
    def f():
        from moyo import invoices as ui
        from moyo.revenue import proposals
        c = _con()
        try:
            inv = proposals.to_invoice(c, pid)
        except (ui.InvoiceError, proposals.ProposalError) as e:
            raise crm.CRMError(str(e))
        audit.log(c, "user", "invoice_from_proposal", "low", {"proposal_id": pid, "number": inv["number"]})
        return {"id": inv["id"], "number": inv["number"]}
    return go(f)


class DealIdIn(BaseModel):
    deal_id: int


@router.post("/proposal/ai")
def proposal_ai(body: DealIdIn):
    def f():
        from moyo.revenue import proposals
        c = _con()
        try:
            r = proposals.ai_draft(c, body.deal_id)
        except proposals.ProposalError as e:
            raise crm.CRMError(str(e))
        audit.log(c, f"cloud:{r.get('model')}", "draft_proposal_words", "read", {"deal_id": body.deal_id})
        return r
    return go(f)


@router.get("/deal/{did}/docs")
def deal_docs(did: int):
    def f():
        from moyo.revenue import ledger, proposals
        c = _con()
        invs = [{k: i[k] for k in ("id", "number", "total", "balance", "currency", "state", "issue_date")}
                for i in ledger.listing(c) if i["deal_id"] == did]
        return {"proposals": [{k: p[k] for k in ("id", "number", "status", "state", "version", "total", "currency", "valid_until")}
                              for p in proposals.for_deal(c, did)], "invoices": invs}
    return go(f)
