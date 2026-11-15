"""Local API + dashboard. Binds to 127.0.0.1 only.

Security: requests must target 127.0.0.1/localhost on our port (blocks DNS-rebinding), and every
state-changing request must carry the X-Moyo header (a web page on another site can't send it
without a CORS preflight, which we never approve)."""
from __future__ import annotations

import json
import os
import threading
from datetime import datetime
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from moyo import actions, audit, briefing, cloud, commands, content, db, memory, money, planner, tasks, workspaces

PORT = int(os.environ.get("MOYO_PORT", "8765"))
STATIC = Path(__file__).parent / "static"

app = FastAPI(title="Moyo AI", docs_url=None, redoc_url=None, openapi_url=None)
_lock = threading.RLock()
_con = None


def con():
    global _con
    if _con is None:
        _con = db.connect()
        db.init(_con)
        db.backup(_con)
    return _con


@app.middleware("http")
async def guard(request: Request, call_next):
    host = (request.headers.get("host") or "").split(":")[0]
    if host not in ("127.0.0.1", "localhost", "testserver"):
        return JSONResponse({"detail": "forbidden host"}, status_code=403)
    if request.method not in ("GET", "HEAD", "OPTIONS") and request.headers.get("x-moyo") != "1":
        return JSONResponse({"detail": "missing X-Moyo header"}, status_code=403)
    origin = request.headers.get("origin")
    if origin and not any(origin.startswith(f"http://{h}") for h in ("127.0.0.1", "localhost")):
        return JSONResponse({"detail": "forbidden origin"}, status_code=403)
    response = await call_next(request)
    if request.url.path.startswith("/static/"):
        response.headers["Cache-Control"] = "no-cache"  # always revalidate, so updates show up immediately
    return response


def run(fn, *a, **kw):
    with _lock:
        try:
            return fn(*a, **kw)
        except (ValueError, tasks.TaskError, money.MoneyError, workspaces.WorkspaceError) as e:
            raise HTTPException(400, str(e))


# ---------------------------------------------------------------- dashboard & chat
@app.get("/")
def index():
    from fastapi.responses import HTMLResponse
    # stamp asset URLs with their modification time so the window always loads the current version
    html = (STATIC / "index.html").read_text(encoding="utf-8")
    for name in ("app.js", "revenue.js", "revenue-money.js", "style.css"):
        v = int((STATIC / name).stat().st_mtime)
        html = html.replace(f"/static/{name}", f"/static/{name}?v={v}")
    return HTMLResponse(html, headers={"Cache-Control": "no-store"})


@app.get("/api/dashboard")
def dashboard():
    def build():
        c = con()
        b = briefing.build(c, datetime.now())
        return {**b, "now": datetime.now().isoformat(timespec="minutes"),
                "routine_ran_today": db.get_setting(c, "routine").get("last_run") == db.today().isoformat(),
                "tasks_overview": tasks.overview(c), "memory_count": len(memory.listing(c)),
                "ngn_per_usd": db.get_setting(c, "ngn_per_usd"), "cloud_ready": bool(cloud.api_key())}
    return run(build)


class ChatIn(BaseModel):
    text: str


@app.post("/api/chat")
def chat(body: ChatIn):
    text = body.text.strip()[:2000]
    if not text:
        raise HTTPException(400, "Say something first.")

    def go():
        c = con()
        parsed = commands.parse(text)
        if parsed and parsed[0] == "capture_lead" and "text" in parsed[1]:
            from moyo.revenue import capture
            f = capture.extract(c, parsed[1]["text"])
            parsed = ("capture_lead", {k: v for k, v in f.items() if k not in ("missing",) and v not in (None, "", [])})
        if parsed:
            return {**actions.execute(c, parsed[0], parsed[1], actor="user"), "via": "local"}
        res = cloud.interpret(c, text)
        if "action" in res:
            out = actions.execute(c, res["action"], res["args"], actor=f"cloud:{res.get('model')}")
            return {**out, "via": "cloud", "model": res.get("model"), "redacted": res.get("redacted", False)}
        if "reply" in res:
            audit.log(c, f"cloud:{res.get('model')}", "chat_reply", "read", {"redacted": res.get("redacted")})
            return {"reply": res["reply"], "via": "cloud", "model": res.get("model"), "redacted": res.get("redacted", False)}
        return {"reply": res["error"] + " Examples: \"add task call Tunde tomorrow\", \"what's my plan\", "
                "\"log payment ₦200,000 from Adebayo Ventures\".", "via": "local", "error": True}
    return run(go)


class ConfirmIn(BaseModel):
    pending_id: str
    accept: bool


@app.post("/api/confirm")
def confirm(body: ConfirmIn):
    return run(lambda: actions.confirm(con(), body.pending_id, body.accept))


@app.post("/api/action/{name}")
def action(name: str, args: dict):
    """Structured actions from UI forms go through the same gateway (tiers, confirmation, audit)."""
    return run(lambda: actions.execute(con(), name, args, actor="user"))


# ---------------------------------------------------------------- tasks
@app.get("/api/tasks")
def list_tasks(status: str = "open"):
    return run(lambda: tasks.listing(con(), status))


class TaskPatch(BaseModel):
    title: str | None = None
    due_date: str | None = None
    due_time: str | None = None
    priority: int | None = None
    category: str | None = None
    status: str | None = None
    estimate_min: int | None = None
    notes: str | None = None
    recurrence: str | None = None


@app.patch("/api/tasks/{tid}")
def patch_task(tid: int, body: TaskPatch):
    fields = body.model_dump(exclude_unset=True)

    def go():
        t = tasks.update(con(), tid, **fields)
        audit.log(con(), "user", "edit_task", "low", {"id": tid, **fields})
        return t
    return run(go)


# ---------------------------------------------------------------- money
@app.get("/api/money")
def money_view():
    def go():
        c = con()
        return {"challenge": money.challenge_status(c), "pipeline": money.pipeline_summary(c),
                "leads": money.all_leads(c),
                "earnings": db.rows(c.execute("SELECT * FROM earnings ORDER BY earned_date DESC, id DESC")),
                "ngn_per_usd": db.get_setting(c, "ngn_per_usd")}
    return run(go)


@app.post("/api/earnings/{eid}/paid")
def mark_paid(eid: int):
    def go():
        c = con()
        c.execute("UPDATE earnings SET payment_status='paid', paid_date=? WHERE id=?",
                  (db.today().isoformat(), eid))
        audit.log(c, "user", "mark_paid", "low", {"id": eid})
        return {"ok": True}
    return run(go)


class LeadPatch(BaseModel):
    stage: str | None = None
    next_followup: str | None = None
    value: float | None = None
    currency: str | None = None
    notes: str | None = None
    contact: str | None = None
    service: str | None = None


@app.patch("/api/leads/{lid}")
def patch_lead(lid: int, body: LeadPatch):
    fields = body.model_dump(exclude_unset=True)

    def go():
        l = money.update_lead(con(), lid, **fields)
        audit.log(con(), "user", "edit_lead", "low", {"id": lid, **fields})
        return l
    return run(go)


# ---------------------------------------------------------------- memory
@app.get("/api/memory")
def memory_list():
    return run(lambda: memory.listing(con(), include_expired=True))


class MemPatch(BaseModel):
    content: str | None = None
    kind: str | None = None
    category: str | None = None
    valid_until: str | None = None
    confirmed: bool | None = None


@app.patch("/api/memory/{mid}")
def memory_patch(mid: int, body: MemPatch):
    fields = body.model_dump(exclude_unset=True)
    if "confirmed" in fields:
        fields["confirmed"] = int(fields["confirmed"])

    def go():
        m = memory.update(con(), mid, **fields)
        audit.log(con(), "user", "edit_memory", "low", {"id": mid, **fields})
        return m
    return run(go)


@app.delete("/api/memory/{mid}")
def memory_delete(mid: int):
    def go():
        m = memory.delete(con(), mid)
        audit.log(con(), "user", "delete_memory", "confirm", {"id": mid, "content": m["content"]},
                  "confirmed in UI + done")
        return {"ok": True}
    return run(go)


# ---------------------------------------------------------------- workspaces, media, settings, review, audit
@app.get("/api/workspaces")
def ws_list():
    def go():
        out = []
        for k in workspaces.load():
            try:
                out.append(workspaces.plan(k))
            except workspaces.WorkspaceError as e:
                out.append({"key": k, "label": k, "problems": [str(e)], "apps": [], "urls": [], "music": None})
        return out
    return run(go)


@app.get("/api/settings")
def settings_get():
    return run(lambda: {k: db.get_setting(con(), k) for k in db.DEFAULT_SETTINGS})  # shared connection: always under the lock


@app.put("/api/settings/schedule")
def settings_schedule(body: dict):
    def go():
        cur = db.get_setting(con(), "schedule")
        allowed = {"wake", "day_start", "day_end", "fixed", "focus_block_min", "break_min", "buffer_pct", "confirmed"}
        new = {**cur, **{k: v for k, v in body.items() if k in allowed}}
        for f in new["fixed"]:
            datetime.strptime(f["start"], "%H:%M"), datetime.strptime(f["end"], "%H:%M")
        db.set_setting(con(), "schedule", new)
        audit.log(con(), "user", "edit_schedule", "low", body)
        return new
    return run(go)


@app.put("/api/settings/cloud")
def settings_cloud(body: dict):
    def go():
        cur = db.get_setting(con(), "cloud")
        new = {**cur, **{k: v for k, v in body.items() if k in ("enabled", "redact_clients_and_amounts", "models")}}
        db.set_setting(con(), "cloud", new)
        audit.log(con(), "user", "edit_cloud_settings", "low", body)
        return new
    return run(go)


class ReviewIn(BaseModel):
    completed: str = ""
    not_completed: str = ""
    value_created: str = ""
    distractions: str = ""
    carry_over: str = ""
    notes: str = ""


@app.get("/api/review")
def review_get():
    def go():
        c = con()
        iso = db.today().isoformat()
        r = c.execute("SELECT * FROM reviews WHERE date=?", (iso,)).fetchone()
        done = db.rows(c.execute("SELECT id, title, category FROM tasks WHERE status='done' "
                                 "AND substr(completed_at,1,10)=?", (iso,)))
        left = [t for t in tasks.listing(c) if t["due_date"] and t["due_date"] <= iso]
        return {"saved": dict(r) if r else None, "done_today": done, "still_open": left}
    return run(go)


@app.post("/api/review")
def review_save(body: ReviewIn):
    def go():
        c = con()
        iso = db.today().isoformat()
        c.execute("INSERT INTO reviews(date, completed, not_completed, value_created, distractions, carry_over, notes, "
                  "created_at) VALUES (?,?,?,?,?,?,?,?) ON CONFLICT(date) DO UPDATE SET completed=excluded.completed, "
                  "not_completed=excluded.not_completed, value_created=excluded.value_created, "
                  "distractions=excluded.distractions, carry_over=excluded.carry_over, notes=excluded.notes",
                  (iso, body.completed, body.not_completed, body.value_created, body.distractions, body.carry_over,
                   body.notes, db.now_iso()))
        audit.log(c, "user", "save_review", "low", {"date": iso})
        return {"ok": True}
    return run(go)


# ---------------------------------------------------------------- Google (Gmail + Calendar, read-only)
SYNC_MINUTES = 15


def _sync_loop():
    import time as _t

    from moyo import google_api, social
    last_social = 0.0
    bg = db.connect()  # own connection (SQLite WAL): network syncs never block the dashboard
    con()  # make sure the schema exists
    while True:
        try:
            if google_api.connected():
                google_api.sync_all(bg)
        except Exception:
            pass
        try:  # social metrics change slowly (and Instagram can lag 48h): every 3 hours is plenty
            if (social.ig_connected() or social.tt_connected()) and _t.time() - last_social > 3 * 3600:
                social.sync_all(bg)
                last_social = _t.time()
        except Exception:
            pass
        _t.sleep(SYNC_MINUTES * 60)


def _sync_con():
    """Fresh connection for user-triggered syncs, so slow networks don't freeze other requests."""
    c = db.connect()
    c.execute("PRAGMA busy_timeout = 10000")
    return c


def _reminder_loop():
    """Every minute: evaluate reminder rules (own DB connection; never blocks the dashboard)."""
    import time as _t

    from moyo import reminders, wake
    con()
    rc = db.connect()
    try:
        wake.manager.reconcile(rc)  # clap listener starts right away (if turned on), not after 20 s
    except Exception:
        pass
    try:
        wake.manager.spawn_standby()
    except Exception:
        pass
    _t.sleep(20)  # let the first syncs land before the first evaluation
    while True:
        try:
            wake.manager.reconcile(rc)  # follows settings + quiet hours
        except Exception:
            pass
        try:  # keep a pre-loaded orb ready (fast wake / talk)
            if not wake.manager.orb_open():
                wake.manager.spawn_standby()
        except Exception:
            pass
        try:
            reminders.tick(rc)
        except Exception as e:  # a bad rule must never kill the loop
            try:
                audit.log(rc, "moyo", "reminders_tick", "read", None, f"error: {type(e).__name__}: {str(e)[:120]}")
            except Exception:
                pass
        _t.sleep(60)


@app.on_event("startup")
def _start_background():
    if os.environ.get("MOYO_NO_BACKGROUND") != "1":
        threading.Thread(target=_sync_loop, daemon=True).start()
        threading.Thread(target=_reminder_loop, daemon=True).start()


# ---------------------------------------------------------------- notifications + routine
@app.get("/api/notifications")
def notifications_list():
    from moyo import reminders
    return run(lambda: reminders.listing(con()))


class ReadIn(BaseModel):
    ids: list[int] | None = None


@app.post("/api/notifications/read")
def notifications_read(body: ReadIn):
    from moyo import reminders
    run(lambda: reminders.mark_read(con(), body.ids))
    return {"ok": True}


@app.post("/api/notifications/test")
def notifications_test():
    from moyo import notify
    ok = notify.toast("Moyo test notification", "Desktop notifications are working. Click to open Moyo.",
                      url="http://127.0.0.1:8765/#today")
    return {"ok": ok}


@app.post("/api/routine/start")
def routine_start():
    from moyo import routine
    return run(lambda: routine.start(con()))


@app.get("/api/wake/brief")
def wake_brief():
    return run(lambda: briefing.short(con()))


@app.get("/api/wake/status")
def wake_status():
    from moyo import wake
    return run(lambda: wake.manager.status(con()))


@app.post("/api/wake/test")
def wake_test():
    """Open the wake orb now, without clapping (to try it out)."""
    from moyo import wake
    opened = wake.manager.launch_orb("test")
    run(lambda: audit.log(con(), "user", "wake_test", "low", None, "opened" if opened else "already open"))
    return {"opened": opened}


from moyo.revenue import api as _rev_api  # noqa: E402

_rev_api.mount(app, run, con)


@app.get("/api/invoices")
def invoices_list():
    from moyo import invoices
    from moyo.revenue import ledger
    return run(lambda: [{k: i[k] for k in ("id", "number", "client", "issue_date", "due_date", "currency", "total", "balance",
                                           "state", "status", "pdf_path")} for i in ledger.listing(con(), include_historical=False, limit=50)])


@app.post("/api/invoices/{iid}/open")
def invoices_open(iid: int):
    """Opens a draft Moyo created (path comes from Moyo's own records, never from the request)."""
    row = run(lambda: con().execute("SELECT pdf_path FROM ledger_invoices WHERE id=?", (iid,)).fetchone())
    if not row or not row["pdf_path"] or not os.path.exists(row["pdf_path"]):
        raise HTTPException(404, "That invoice PDF isn't there any more.")
    os.startfile(row["pdf_path"])
    return {"ok": True}


@app.post("/api/wake/talk")
def wake_talk():
    """Open the orb straight into a voice conversation."""
    from moyo import wake
    opened = wake.manager.launch_orb("talk")
    run(lambda: audit.log(con(), "user", "voice_talk_opened", "low", None, "opened" if opened else "already open"))
    return {"opened": opened}


@app.get("/api/voice/config")
def voice_config():
    from moyo import voice as vc
    pref = run(lambda: db.get_setting(con(), "voice"))
    return {"tools": cloud.DECLS, "chat_voice": pref.get("chat_voice") or vc.DEFAULT_VOICE, "model": vc.LIVE_MODEL}


class VoiceToolIn(BaseModel):
    name: str
    args: dict = {}


@app.post("/api/voice/tool")
def voice_tool(body: VoiceToolIn):
    """Actions proposed by Gemini during a voice conversation: same gateway (tiers, confirmation, audit)."""
    if body.name not in {d["name"] for d in cloud.DECLS}:
        run(lambda: audit.log(con(), "voice:gemini-live", body.name, "prohibited", body.args, "refused"))
        return {"reply": "That isn't something Moyo can do.", "error": True}
    args = dict(body.args)
    if isinstance(args.get("amount"), str):
        from moyo.dates import parse_amount
        pa = parse_amount(args["amount"])
        if pa:
            args["amount"], args["currency"] = pa[0], pa[1] or args.get("currency", "NGN")
    return run(lambda: actions.execute(con(), body.name, args, actor="voice:gemini-live"))


@app.put("/api/settings/clap")
def settings_clap(body: dict):
    from moyo import wake

    def go():
        c = con()
        cur = db.get_setting(c, "clap")
        new = {**cur, **{k: bool(v) for k, v in body.items() if k in ("enabled", "listen_in_quiet_hours")}}
        if "mode" in body:
            if body["mode"] not in ("clap_phrase", "double_clap"):
                raise ValueError("Unknown wake mode.")
            new["mode"] = body["mode"]
        db.set_setting(c, "clap", new)
        audit.log(c, "user", "edit_clap_wake", "low", body)
        if os.environ.get("MOYO_NO_BACKGROUND") != "1":
            wake.manager.reconcile(c)
        return wake.manager.status(c)
    return run(go)


@app.get("/api/review/week")
def review_week(offset: int = 0):
    from datetime import timedelta as _td

    from moyo import reminders
    return run(lambda: reminders.weekly_summary(con(), db.today() - _td(days=7 * max(0, min(offset, 52)))))


@app.put("/api/settings/notifications")
def settings_notifications(body: dict):
    def go():
        cur = db.get_setting(con(), "notifications")
        allowed = {"enabled", "toasts", "toast_levels", "quiet_start", "quiet_end", "content_reminder_time",
                   "event_lead_minutes", "review_minutes_before_end"}
        new = {**cur, **{k: v for k, v in body.items() if k in allowed}}
        for k in ("quiet_start", "quiet_end", "content_reminder_time"):
            datetime.strptime(new[k], "%H:%M")
        if not set(new["toast_levels"]) <= {"urgent", "important", "info"}:
            raise ValueError("Unknown notification level.")
        db.set_setting(con(), "notifications", new)
        audit.log(con(), "user", "edit_notifications", "low", body)
        return new
    return run(go)


@app.put("/api/settings/routine")
def settings_routine(body: dict):
    def go():
        cur = db.get_setting(con(), "routine")
        new = {**cur, **{k: v for k, v in body.items() if k in ("workspace", "music", "read_briefing", "morning_prompt", "prompt_after")}}
        if new["workspace"] and not workspaces.resolve_profile(new["workspace"]):
            raise ValueError("Unknown workspace.")
        datetime.strptime(new["prompt_after"], "%H:%M")
        db.set_setting(con(), "routine", new)
        audit.log(con(), "user", "edit_routine", "low", body)
        return new
    return run(go)


@app.get("/api/google/status")
def google_status():
    from moyo import google_api
    has_client = False
    try:
        has_client = bool(google_api.client_config())
    except Exception:
        pass
    return {"has_client": has_client, "connected": google_api.connected(), **google_api.STATE,
            "sync_minutes": SYNC_MINUTES}


@app.post("/api/google/client")
def google_client(body: dict):
    from moyo import google_api
    try:
        info = google_api.save_client(json.dumps(body))
    except google_api.GoogleError as e:
        raise HTTPException(400, str(e))
    run(lambda: audit.log(con(), "user", "google_client_saved", "low", info))
    return info


@app.post("/api/google/connect")
def google_connect():
    from moyo import google_api
    if not google_api.client_config():
        raise HTTPException(400, "Upload your OAuth client file first.")

    def after():
        with _lock:
            audit.log(con(), "user", "google_connected", "low", {"scopes": "gmail.readonly, calendar.readonly"})
            google_api.sync_all(con())
    google_api.connect_async(after)
    return {"started": True}


@app.post("/api/google/sync")
def google_sync():
    from moyo import google_api
    c = _sync_con()
    try:
        return google_api.sync_all(c)
    finally:
        c.close()


@app.post("/api/google/disconnect")
def google_disconnect():
    from moyo import google_api

    def go():
        google_api.disconnect(con())
        audit.log(con(), "user", "google_disconnected", "low", {"local_email_and_calendar_copies": "deleted"})
        return {"ok": True}
    return run(go)


@app.get("/api/inbox")
def inbox_list():
    from moyo import google_api
    return run(lambda: google_api.inbox(con()))


@app.get("/api/inbox/{msg_id}")
def inbox_open(msg_id: str):
    from moyo import google_api
    try:
        m = google_api.read_email(msg_id)
    except google_api.GoogleError as e:
        raise HTTPException(400, str(e))
    run(lambda: audit.log(con(), "user", "open_email", "read", {"id": msg_id}))  # subject/body deliberately not logged
    return m


# ---------------------------------------------------------------- Instagram + TikTok (read-only)
@app.get("/api/social/status")
def social_status():
    from moyo import social
    return social.status()


class IGToken(BaseModel):
    token: str
    ig_id: str | None = None


@app.post("/api/social/instagram/token")
def social_ig_token(body: IGToken):
    from moyo import social

    def go():
        try:
            info = social.ig_save_token(body.token, body.ig_id)
        except social.SocialError as e:
            raise HTTPException(400, str(e))
        audit.log(con(), "user", "instagram_connected", "low", {"username": info.get("username")})
        social.sync_all(con())
        return info
    return run(go)


class TTClient(BaseModel):
    client_key: str
    client_secret: str


@app.post("/api/social/tiktok/client")
def social_tt_client(body: TTClient):
    from moyo import social
    try:
        social.tt_save_client(body.client_key, body.client_secret)
    except social.SocialError as e:
        raise HTTPException(400, str(e))
    run(lambda: audit.log(con(), "user", "tiktok_client_saved", "low", {"client_key": body.client_key[:6] + "…"}))
    return {"ok": True}


@app.post("/api/social/tiktok/connect")
def social_tt_connect():
    from moyo import social
    if not social.tt_client():
        raise HTTPException(400, "Save your TikTok Client key and secret first.")

    def after():
        with _lock:
            audit.log(con(), "user", "tiktok_connected", "low", {"scopes": social.TT_SCOPES})
            social.sync_all(con())
    social.tt_connect_async(after)
    return {"started": True}


@app.post("/api/social/sync")
def social_sync():
    from moyo import social
    c = _sync_con()
    try:
        return social.sync_all(c)
    finally:
        c.close()


@app.post("/api/social/{platform}/disconnect")
def social_disconnect(platform: str):
    from moyo import social

    def go():
        try:
            social.disconnect(con(), platform)
        except social.SocialError as e:
            raise HTTPException(400, str(e))
        audit.log(con(), "user", f"{platform}_disconnected", "low", None)
        return {"ok": True}
    return run(go)


@app.get("/api/content/performance")
def content_performance(days: int = 7):
    return run(lambda: content.performance(con(), days=max(1, min(days, 30))))


@app.get("/api/coaching")
def coaching(refresh: bool = False):
    from moyo import coach

    def go():
        c = coach.generate(con(), force=refresh)
        if not c.get("cached"):
            audit.log(con(), f"cloud:{c.get('model')}" if c["source"] == "ai" else "moyo", "coaching", "read",
                      {"source": c["source"], "points": len(c["points"]), "dropped_unverified": c.get("dropped_unverified", 0)})
        return {**c, "speech": coach.speech_text(c)}
    return run(go)


@app.get("/api/voices")
def voices():
    from moyo import tts
    pref = run(lambda: db.get_setting(con(), "voice"))
    return {"current": pref, "engines": {k: {"label": v["label"], "note": v["note"],
                                             "voices": [{"id": i, "label": l} for i, l in v["voices"]]}
                                         for k, v in tts.CATALOG.items()},
            "sample": "Good morning, Moyosore. Here's what you need to know today. You've earned $133 of your $10K target, "
                      "so let's focus on the proposals that can close this week."}


class TTSIn(BaseModel):
    text: str
    engine: str | None = None   # None = use the chosen voice with fallback
    voice: str | None = None
    speed: float = 1.0


@app.post("/api/tts")
def tts_speak(body: TTSIn):
    from fastapi.responses import Response

    from moyo import tts
    try:
        if body.engine:  # preview of one specific voice: no fallback, so you hear exactly that voice
            data, mime = tts.synthesize(body.text, body.engine, body.voice or "", body.speed)
            used = f"{body.engine}:{body.voice}"
        else:
            data, mime, used = tts.speak_with_fallback(con(), body.text)
    except tts.TTSError as e:
        raise HTTPException(503, str(e))
    return Response(content=data, media_type=mime, headers={"X-Moyo-Voice": used, "Cache-Control": "no-store"})


@app.put("/api/settings/voice")
def settings_voice(body: dict):
    from moyo import tts

    def go():
        cur = db.get_setting(con(), "voice")
        new = {**cur, **{k: v for k, v in body.items() if k in ("engine", "voice", "speed", "fallback", "chat_voice")}, "chosen": True}
        if new["engine"] not in list(tts.ENGINES) + ["browser"]:
            raise ValueError("Unknown voice engine.")
        new["speed"] = max(0.7, min(float(new["speed"]), 1.4))
        db.set_setting(con(), "voice", new)
        audit.log(con(), "user", "set_voice", "low", new)
        return new
    return run(go)


@app.get("/api/audit")
def audit_list(limit: int = 100):
    return run(lambda: audit.recent(con(), min(limit, 500)))


@app.get("/api/content")
def content_get():
    return run(lambda: content.status(con()))


@app.get("/api/plan")
def plan_get():
    return run(lambda: planner.build(con(), now=datetime.now()))


app.mount("/static", StaticFiles(directory=STATIC), name="static")
