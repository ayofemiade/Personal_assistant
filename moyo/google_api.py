"""Google connection: Gmail (read-only) + Google Calendar (read-only).

- Sign-in uses Google's own consent page in your browser; Moyo never sees your password.
- The OAuth client file and refresh token live in Windows Credential Manager, not in files.
- Gmail: only sender / subject / date / labels are synced (decision D19). A full email is fetched
  only when you click Open, shown on this laptop, and never stored or sent to any AI.
- Email and calendar text is untrusted data: it is displayed, never executed as instructions.
"""
from __future__ import annotations

import base64
import html
import json
import re
import threading
from datetime import date, datetime, timedelta, timezone
from email.utils import parseaddr

from moyo import audit
from moyo.db import now_iso, rows, today

SCOPES = ["https://www.googleapis.com/auth/gmail.readonly",
          "https://www.googleapis.com/auth/calendar.readonly"]
SERVICE = "moyo-ai"
GMAIL = "https://gmail.googleapis.com/gmail/v1/users/me"
CAL = "https://www.googleapis.com/calendar/v3"

STATE = {"connecting": False, "error": None, "last_sync": None, "last_sync_error": None, "account": None}
_lock = threading.Lock()


class GoogleError(RuntimeError):
    pass


# ---------------------------------------------------------------- secrets
def _kr():
    import keyring
    return keyring


def save_client(cfg_text: str) -> dict:
    try:
        cfg = json.loads(cfg_text)
    except json.JSONDecodeError:
        raise GoogleError("That file isn't valid JSON. Download the OAuth client file again.")
    inner = cfg.get("installed") or cfg.get("web")
    if not inner or "client_id" not in inner or "client_secret" not in inner:
        raise GoogleError("This isn't an OAuth client file. Create one of type 'Desktop app' and download its JSON.")
    if "installed" not in cfg:
        raise GoogleError("This client is a 'Web application'. Create an OAuth client of type 'Desktop app' instead.")
    slim = {"installed": {k: inner[k] for k in ("client_id", "client_secret", "auth_uri", "token_uri") if k in inner}}
    _kr().set_password(SERVICE, "google_client", json.dumps(slim))
    return {"client_id": inner["client_id"][:24] + "…"}


def client_config() -> dict | None:
    v = _kr().get_password(SERVICE, "google_client")
    return json.loads(v) if v else None


def refresh_token() -> str | None:
    return _kr().get_password(SERVICE, "google_refresh_token")


def connected() -> bool:
    try:
        return bool(client_config() and refresh_token())
    except Exception:
        return False


# ---------------------------------------------------------------- sign-in
def connect_blocking() -> str:
    """Opens Google's consent page in the browser and waits for approval (loopback redirect)."""
    from google_auth_oauthlib.flow import InstalledAppFlow
    cfg = client_config()
    if not cfg:
        raise GoogleError("Upload your OAuth client file first.")
    flow = InstalledAppFlow.from_client_config(cfg, SCOPES)
    creds = flow.run_local_server(host="127.0.0.1", port=0, open_browser=True, prompt="consent",
                                  access_type="offline", timeout_seconds=300,
                                  authorization_prompt_message="",
                                  success_message="Moyo is now connected to Google. You can close this tab.")
    if not creds.refresh_token:
        raise GoogleError("Google didn't return a refresh token. Remove Moyo's access at "
                          "myaccount.google.com/permissions and connect again.")
    granted = set(creds.granted_scopes or SCOPES)
    missing = [s.rsplit("/", 1)[-1] for s in SCOPES if s not in granted]
    _kr().set_password(SERVICE, "google_refresh_token", creds.refresh_token)
    if missing:
        raise GoogleError(f"Connected, but you didn't tick: {', '.join(missing)}. Reconnect and allow both.")
    return "ok"


def connect_async(on_done=None) -> None:
    def run():
        STATE.update(connecting=True, error=None)
        try:
            connect_blocking()
            if on_done:
                on_done()
        except Exception as e:
            STATE["error"] = str(e)
        finally:
            STATE["connecting"] = False
    threading.Thread(target=run, daemon=True).start()


def _credentials():
    from google.oauth2.credentials import Credentials
    cfg, rt = client_config(), refresh_token()
    if not cfg or not rt:
        raise GoogleError("Google isn't connected.")
    i = cfg["installed"]
    return Credentials(token=None, refresh_token=rt, token_uri=i.get("token_uri", "https://oauth2.googleapis.com/token"),
                       client_id=i["client_id"], client_secret=i["client_secret"], scopes=SCOPES)


_session = None


def session():
    """Authorised HTTP session (refreshes the access token automatically)."""
    global _session
    if _session is None:
        from google.auth.transport.requests import AuthorizedSession
        _session = AuthorizedSession(_credentials())
    return _session


def _get(url: str, **params) -> dict:
    global _session
    for attempt in range(3):  # networks drop: retry with a fresh connection before giving up
        try:
            r = session().get(url, params=params, timeout=30)
            break
        except Exception as e:
            if attempt == 2 or not any(k in type(e).__name__ for k in ("Transport", "Connection", "Timeout", "SSL", "Protocol")):
                if attempt == 2:
                    raise GoogleError("Couldn't reach Google (network problem). Moyo will retry at the next sync.")
                raise
            _session = None
            import time as _t
            _t.sleep(2 * (attempt + 1))
    if r.status_code in (401, 403):
        body = r.text[:300]
        if "invalid_grant" in body or r.status_code == 401:
            raise GoogleError("Google access expired or was revoked. Reconnect Google in Settings.")
        raise GoogleError(f"Google refused the request ({r.status_code}). Is the API enabled in your project?")
    r.raise_for_status()
    return r.json()


def disconnect(con) -> None:
    global _session
    rt = None
    try:
        rt = refresh_token()
        if rt:
            import requests
            requests.post("https://oauth2.googleapis.com/revoke", params={"token": rt}, timeout=15)
    except Exception:
        pass  # still remove local copies
    for name in ("google_refresh_token",):
        try:
            _kr().delete_password(SERVICE, name)
        except Exception:
            pass
    _session = None
    con.execute("DELETE FROM emails")
    con.execute("DELETE FROM events")
    STATE.update(last_sync=None, account=None, error=None)


# ---------------------------------------------------------------- Gmail (metadata only)
PROMO = {"CATEGORY_PROMOTIONS": "promotions", "CATEGORY_SOCIAL": "social", "CATEGORY_UPDATES": "updates",
         "CATEGORY_FORUMS": "forums"}


def _classify(con, from_name: str, from_email: str, labels: list[str]) -> tuple[str, int | None]:
    fe = (from_email or "").lower()
    domain = fe.split("@")[-1] if "@" in fe else ""
    generic = {"gmail.com", "yahoo.com", "outlook.com", "hotmail.com", "icloud.com", "live.com"}
    # Revenue Toolkit: match the sender's email to a contact channel (exact), then company name / domain.
    if fe:
        r = con.execute("SELECT d.id FROM contact_channels ch JOIN deals d ON d.primary_contact_id=ch.contact_id "
                        "WHERE ch.kind='email' AND ch.value_norm=? AND d.archived_at IS NULL "
                        "ORDER BY d.updated_at DESC LIMIT 1", (fe,)).fetchone()
        if r:
            return ("lead", r["id"])
    from moyo import money
    for l in money.all_leads(con):
        c = (l["contact"] or "").lower()
        if (l["name"] and len(l["name"]) > 2 and l["name"].lower() in (from_name or "").lower()):
            return ("lead", l["id"])
        if domain and domain not in generic and c.endswith("@" + domain):
            return ("lead", l["id"])
    for e in rows(con.execute("SELECT DISTINCT client FROM earnings WHERE client IS NOT NULL")):
        if len(e["client"]) > 2 and e["client"].lower() in (from_name or "").lower():
            return ("client", None)
    for lab, kind in PROMO.items():
        if lab in labels:
            return (kind, None)
    if re.search(r"no-?reply|notifications?@|mailer|newsletter|digest", fe):
        return ("updates", None)
    return ("personal", None)


def sync_gmail(con, days: int = 3, limit: int = 60) -> int:
    data = _get(f"{GMAIL}/messages", q=f"in:inbox newer_than:{days}d", maxResults=limit)
    n = 0
    for m in data.get("messages", []):
        msg = _get(f"{GMAIL}/messages/{m['id']}", format="metadata",
                   metadataHeaders=["From", "Subject", "Date"])
        hdr = {h["name"].lower(): h["value"] for h in msg.get("payload", {}).get("headers", [])}
        name, addr = parseaddr(hdr.get("from", ""))
        labels = msg.get("labelIds", [])
        kind, lead_id = _classify(con, name, addr, labels)
        received = datetime.fromtimestamp(int(msg.get("internalDate", "0")) / 1000).replace(microsecond=0).isoformat()
        con.execute(
            "INSERT INTO emails(id, thread_id, received_at, from_name, from_email, subject, unread, labels, kind, "
            "lead_id, synced_at) VALUES (?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET unread=excluded.unread, "
            "labels=excluded.labels, kind=excluded.kind, lead_id=excluded.lead_id, synced_at=excluded.synced_at",
            (m["id"], msg.get("threadId"), received, (name or addr)[:120], addr[:200],
             (hdr.get("subject") or "(no subject)")[:300], int("UNREAD" in labels), ",".join(labels), kind,
             lead_id, now_iso()))
        n += 1
    cutoff = (datetime.now() - timedelta(days=14)).isoformat()
    con.execute("DELETE FROM emails WHERE received_at < ?", (cutoff,))
    return n


def _walk_text(part: dict) -> tuple[str, str]:
    mime = part.get("mimeType", "")
    data = part.get("body", {}).get("data")
    plain = htmltext = ""
    if data:
        raw = base64.urlsafe_b64decode(data + "=" * (-len(data) % 4)).decode("utf-8", "replace")
        if mime == "text/plain":
            plain = raw
        elif mime == "text/html":
            htmltext = raw
    for p in part.get("parts", []) or []:
        a, b = _walk_text(p)
        plain, htmltext = plain or a, htmltext or b
    return plain, htmltext


def read_email(msg_id: str) -> dict:
    """Full email, fetched on demand for display only. Never stored, never sent to an AI."""
    if not re.fullmatch(r"[A-Za-z0-9]{6,40}", msg_id):
        raise GoogleError("Invalid email id.")
    msg = _get(f"{GMAIL}/messages/{msg_id}", format="full")
    hdr = {h["name"].lower(): h["value"] for h in msg.get("payload", {}).get("headers", [])}
    plain, htm = _walk_text(msg.get("payload", {}))
    if not plain and htm:
        t = re.sub(r"(?is)<(script|style).*?</\1>", " ", htm)
        t = re.sub(r"(?i)<br\s*/?>|</p>|</div>|</tr>", "\n", t)
        plain = html.unescape(re.sub(r"<[^>]+>", " ", t))
    plain = re.sub(r"[ \t]+", " ", re.sub(r"\n\s*\n\s*\n+", "\n\n", plain)).strip()
    return {"id": msg_id, "from": hdr.get("from"), "to": hdr.get("to"), "date": hdr.get("date"),
            "subject": hdr.get("subject"), "body": plain[:20000],
            "gmail_link": f"https://mail.google.com/mail/u/0/#inbox/{msg.get('threadId', msg_id)}"}


def account_email() -> str | None:
    try:
        return _get(f"{GMAIL}/profile").get("emailAddress")
    except Exception:
        return None


# ---------------------------------------------------------------- Calendar
def _local(dt_str: str) -> datetime:
    d = datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
    return d.astimezone().replace(tzinfo=None) if d.tzinfo else d


def sync_calendar(con, days: int = 8) -> int:
    start = datetime.combine(today(), datetime.min.time()).astimezone()
    end = start + timedelta(days=days)
    cals = [c for c in _get(f"{CAL}/users/me/calendarList").get("items", [])
            if c.get("selected") or c.get("primary")]
    con.execute("DELETE FROM events")
    n = 0
    for c in cals:
        items = _get(f"{CAL}/calendars/{requests_quote(c['id'])}/events", timeMin=start.isoformat(),
                     timeMax=end.isoformat(), singleEvents="true", orderBy="startTime", maxResults=100).get("items", [])
        for ev in items:
            if ev.get("status") == "cancelled" or ev.get("transparency") == "transparent" and "date" in ev.get("start", {}):
                continue
            mine = next((a for a in ev.get("attendees", []) if a.get("self")), None)
            if mine and mine.get("responseStatus") == "declined":
                continue
            s, e = ev.get("start", {}), ev.get("end", {})
            all_day = "date" in s
            st = s.get("date") if all_day else _local(s["dateTime"]).isoformat()
            en = e.get("date") if all_day else _local(e["dateTime"]).isoformat()
            con.execute("INSERT OR REPLACE INTO events(id, calendar, start, end, all_day, title, location, synced_at) "
                        "VALUES (?,?,?,?,?,?,?,?)",
                        (f"{c['id']}|{ev['id']}"[:250], c.get("summary", "")[:80], st, en, int(all_day),
                         (ev.get("summary") or "(busy)")[:200], (ev.get("location") or "")[:200], now_iso()))
            n += 1
    return n


def requests_quote(s: str) -> str:
    from urllib.parse import quote
    return quote(s, safe="")


def events_on(con, d: date) -> list[dict]:
    iso = d.isoformat()
    return rows(con.execute("SELECT * FROM events WHERE (all_day=0 AND substr(start,1,10)=?) OR "
                            "(all_day=1 AND start<=? AND end>?) ORDER BY all_day DESC, start", (iso, iso, iso)))


# ---------------------------------------------------------------- sync orchestration
def sync_all(con) -> dict:
    if not connected():
        return {"ok": False, "error": "Google isn't connected."}
    with _lock:
        out = {"ok": True}
        try:
            out["emails"] = sync_gmail(con)
            out["events"] = sync_calendar(con)
            STATE["account"] = STATE.get("account") or account_email()
            STATE.update(last_sync=now_iso(), last_sync_error=None)
            audit.log(con, "moyo", "google_sync", "read", {"emails": out["emails"], "events": out["events"]})
        except Exception as e:
            msg = str(e) if isinstance(e, GoogleError) else f"{type(e).__name__}: {str(e)[:150]}"
            STATE["last_sync_error"] = msg
            audit.log(con, "moyo", "google_sync", "read", None, f"error: {msg}")
            out = {"ok": False, "error": msg}
        return out


def inbox(con, limit: int = 40) -> dict:
    since = (datetime.now() - timedelta(hours=24)).isoformat()
    em = rows(con.execute("SELECT * FROM emails ORDER BY received_at DESC LIMIT ?", (limit,)))
    important = [e for e in em if e["kind"] in ("lead", "client", "personal")]
    return {
        "connected": connected(), "last_sync": STATE["last_sync"], "error": STATE["last_sync_error"],
        "unread_24h": con.execute("SELECT COUNT(*) FROM emails WHERE unread=1 AND received_at>=?", (since,)).fetchone()[0],
        "from_leads": [e for e in em if e["kind"] in ("lead", "client") and e["unread"]],
        "important": important[:12], "all": em,
    }
