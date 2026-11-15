"""Instagram (Business, Instagram API with Instagram Login) + TikTok (Login Kit for Desktop + Display API).

Official APIs only: no scraping, no passwords. Read-only: Moyo can't post, comment or change anything.
Tokens live in Windows Credential Manager. Metrics synced: views, likes, comments (+ shares where offered).
"""
from __future__ import annotations

import hashlib
import http.server
import json
import secrets
import threading
import time
import urllib.parse
from datetime import datetime, timedelta

import httpx

from moyo import audit
from moyo.db import now_iso, rows

SERVICE = "moyo-ai"
IG = "https://graph.instagram.com"
TT_AUTH = "https://www.tiktok.com/v2/auth/authorize/"
TT_TOKEN = "https://open.tiktokapis.com/v2/oauth/token/"
TT_API = "https://open.tiktokapis.com/v2"
TT_PORT = 8977
TT_REDIRECT = f"http://127.0.0.1:{TT_PORT}/callback/"
TT_SCOPES = "user.info.basic,user.info.stats,video.list"

STATE = {"tiktok_connecting": False, "tiktok_error": None, "last_sync": None, "last_sync_error": None,
         "instagram_account": None, "tiktok_account": None}
_lock = threading.Lock()


class SocialError(RuntimeError):
    pass


def _kr():
    import keyring
    return keyring


def _net(fn, tries: int = 3):
    """Retry dropped connections / timeouts (common on mobile data) before reporting an error."""
    for i in range(tries):
        try:
            return fn()
        except (httpx.TransportError, ConnectionError) as e:
            if i == tries - 1:
                raise SocialError(f"Network problem reaching the platform ({type(e).__name__}). "
                                  "Moyo will retry at the next sync.")
            time.sleep(2 * (i + 1))


def _get_secret(name):
    try:
        v = _kr().get_password(SERVICE, name)
        return json.loads(v) if v else None
    except Exception:
        return None


def _set_secret(name, value):
    _kr().set_password(SERVICE, name, json.dumps(value))


def _del_secret(name):
    try:
        _kr().delete_password(SERVICE, name)
    except Exception:
        pass


# ================================================================ Instagram
def ig_connected() -> bool:
    return bool(_get_secret("instagram"))


def _ig_get(path: str, token: str, **params) -> dict:
    r = _net(lambda: httpx.get(f"{IG}/{path}", params={**params, "access_token": token}, timeout=30))
    data = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
    if r.status_code >= 400 or "error" in data:
        msg = (data.get("error") or {}).get("message", f"HTTP {r.status_code}")
        if r.status_code in (400, 401) and ("token" in msg.lower() or "session" in msg.lower()):
            raise SocialError(f"Instagram token expired or invalid ({msg}). Generate a new one and paste it in Settings.")
        raise SocialError(f"Instagram: {msg}")
    return data


FB = "https://graph.facebook.com"


def clean_token(raw: str) -> str:
    """Tolerate common copy-paste noise: quotes, line breaks, 'access_token=…' or a whole URL."""
    t = raw.strip().strip("\"'`")
    if "access_token=" in t:
        t = urllib.parse.parse_qs(urllib.parse.urlparse(t).query or urllib.parse.urlparse(t).fragment or t)\
            .get("access_token", [t.split("access_token=", 1)[1].split("&")[0]])[0]
    return "".join(t.split())


def describe(t: str) -> str:
    """Safe hint about what was pasted (never reveals the token)."""
    kind = ("Instagram token (IG…)" if t.startswith("IG") else "Facebook token (EAA…)" if t.startswith("EAA")
            else "not a token: maybe an App ID, App secret or a one-time code" if t.isdigit() or len(t) < 100
            else "unknown format")
    return f"{len(t)} characters, looks like: {kind}"


def _fb_get(path: str, token: str, **params) -> dict:
    r = _net(lambda: httpx.get(f"{FB}/{path}", params={**params, "access_token": token}, timeout=30))
    data = r.json() if r.headers.get("content-type", "").startswith(("application/json", "text/javascript")) else {}
    if r.status_code >= 400 or "error" in data:
        raise SocialError(f"Facebook: {(data.get('error') or {}).get('message', f'HTTP {r.status_code}')}")
    return data


def _fb_find_ig(token: str) -> dict:
    pages = _fb_get("me/accounts", token, fields="name,instagram_business_account{id,username,followers_count}")
    for p in pages.get("data", []):
        ig = p.get("instagram_business_account")
        if ig:
            return ig
    raise SocialError("This Facebook token works, but no Instagram Business account is linked to your Facebook Pages. "
                      "Use the Instagram login token instead (it starts with IG).")


def _followers(get, path, tok):
    try:
        return get(path, tok, fields="followers_count").get("followers_count")
    except SocialError:
        return None  # some token flavours can't read this field; never guessed


def ig_save_token(token: str, ig_id: str | None = None) -> dict:
    t = clean_token(token)
    ig_id = (ig_id or "").strip() or None
    if ig_id and not ig_id.isdigit():
        raise SocialError("The Instagram account ID is the long NUMBER under your username in Meta's token box "
                          "(it starts with 1784…), not your @username.")
    if len(t) < 40:
        raise SocialError(f"That isn't an access token ({describe(t)}). Copy the long token shown after "
                          "'Generate token'.")
    # Meta issues several token flavours (IG… from Instagram login; EAA… from "Unified login" or Facebook login).
    # Try every legitimate route, asking only for id + username, and keep the first that returns a username.
    hosts = [("facebook", _fb_get), ("instagram", _ig_get)] if t.startswith("EAA") else \
            [("instagram", _ig_get), ("facebook", _fb_get)]
    errors = []
    for kind, get in hosts:
        for path in ([ig_id] if ig_id else []) + ["me"]:
            try:
                node = get(path, t, fields="id,username")
                if node.get("username"):
                    # the Facebook host needs the numeric node id for /media; the Instagram host accepts "me"
                    ref = node.get("id") or path if kind == "facebook" else path
                    return _save_ig(t, kind, ref, node["username"], _followers(get, ref, t), kind)
                errors.append(f"{kind}/{'id' if path == ig_id else 'me'}: no Instagram username (got {sorted(node)})")
            except SocialError as e:
                errors.append(f"{kind}/{'id' if path == ig_id else 'me'}: {e}")
    try:
        ig = _fb_find_ig(t)
        return _save_ig(t, "facebook", ig["id"], ig.get("username"), ig.get("followers_count"), "pages")
    except SocialError as e:
        errors.append(f"pages: {e}")
    raise SocialError("Instagram didn't accept this token by any route ("
                      + " | ".join(errors) + f"). [What you pasted: {describe(t)}]"
                      + ("" if ig_id else " Tip: also paste your Instagram account ID (the number under your "
                                          "username in Meta's token box)."))


def _save_ig(t, kind, ref, username, followers, route):
    _set_secret("instagram", {"token": t, "kind": kind, "ig_id": ref, "username": username,
                              "saved_at": time.time(), "refreshed_at": time.time()})
    STATE["instagram_account"] = username
    return {"username": username, "followers": followers, "route": route}


def ig_refresh_if_needed() -> None:
    """Long-lived tokens last 60 days; refresh weekly (allowed once the token is 24h old)."""
    s = _get_secret("instagram")
    if not s or s.get("kind") == "facebook" or time.time() - s.get("refreshed_at", 0) < 7 * 86400:
        return
    try:
        r = httpx.get(f"{IG}/refresh_access_token", params={"grant_type": "ig_refresh_token",
                                                            "access_token": s["token"]}, timeout=30).json()
        if r.get("access_token"):
            s.update(token=r["access_token"], refreshed_at=time.time())
            _set_secret("instagram", s)
    except Exception:
        pass  # sync will report a clear error if the token has really expired


def ig_sync(con, limit: int = 25) -> int:
    s = _get_secret("instagram")
    if not s:
        return 0
    ig_refresh_if_needed()
    s = _get_secret("instagram")
    tok = s["token"]
    STATE["instagram_insights_error"] = None
    get = _fb_get if s.get("kind") == "facebook" else _ig_get
    me_path = s.get("ig_id") or "me"
    me = get(me_path, tok, fields="id,username")
    STATE["instagram_account"] = me.get("username")
    _record_followers(con, "instagram", _followers(get, me_path, tok))
    media = get(f"{me_path}/media", tok, limit=limit,
                fields="id,caption,media_type,media_product_type,timestamp,permalink,like_count,comments_count")
    n = 0
    for m in media.get("data", []):
        views = shares = None
        try:
            ins = get(f"{m['id']}/insights", tok, metric="views,shares")
            vals = {i["name"]: (i.get("values") or [{}])[0].get("value", i.get("total_value", {}).get("value"))
                    for i in ins.get("data", [])}
            views, shares = vals.get("views"), vals.get("shares")
        except SocialError as e:
            # some media types / very new posts have no insights yet: shown as "n/a", never guessed
            if "permission" in str(e).lower():
                STATE["instagram_insights_error"] = ("Views unavailable: your token is missing the "
                                                     "instagram_manage_insights permission. See docs/SOCIAL_SETUP.md.")
        ts = _local(m["timestamp"])
        _upsert(con, "instagram", m["id"], ts, (m.get("caption") or "").strip().split("\n")[0][:140],
                m.get("permalink"), views, m.get("like_count"), m.get("comments_count"), shares)
        n += 1
    return n


# ================================================================ TikTok
def tt_client() -> dict | None:
    return _get_secret("tiktok_client")


def tt_connected() -> bool:
    return bool(_get_secret("tiktok_tokens"))


def tt_save_client(client_key: str, client_secret: str) -> None:
    ck, cs = client_key.strip(), client_secret.strip()
    if len(ck) < 8 or len(cs) < 16:
        raise SocialError("Paste both the Client key and the Client secret from your TikTok app.")
    _set_secret("tiktok_client", {"client_key": ck, "client_secret": cs})


def _pkce() -> tuple[str, str]:
    verifier = secrets.token_urlsafe(64)[:96]
    challenge = hashlib.sha256(verifier.encode()).hexdigest()  # TikTok desktop: HEX-encoded SHA256
    return verifier, challenge


def tt_auth_url(state: str, challenge: str) -> str:
    c = tt_client()
    return TT_AUTH + "?" + urllib.parse.urlencode({
        "client_key": c["client_key"], "response_type": "code", "scope": TT_SCOPES,
        "redirect_uri": TT_REDIRECT, "state": state, "code_challenge": challenge, "code_challenge_method": "S256"})


def _tt_token(form: dict) -> dict:
    c = tt_client()
    r = httpx.post(TT_TOKEN, data={"client_key": c["client_key"], "client_secret": c["client_secret"], **form},
                   headers={"Content-Type": "application/x-www-form-urlencoded"}, timeout=30)
    data = r.json()
    if "access_token" not in data:
        raise SocialError(f"TikTok sign-in failed: {data.get('error_description') or data.get('error') or r.status_code}")
    tokens = {"access_token": data["access_token"], "refresh_token": data["refresh_token"],
              "expires_at": time.time() + int(data.get("expires_in", 86400)) - 120,
              "refresh_expires_at": time.time() + int(data.get("refresh_expires_in", 31536000)),
              "scope": data.get("scope", ""), "open_id": data.get("open_id")}
    _set_secret("tiktok_tokens", tokens)
    return tokens


def tt_connect_blocking(open_browser: bool = True, timeout: int = 300) -> None:
    if not tt_client():
        raise SocialError("Save your TikTok Client key and secret first.")
    verifier, challenge = _pkce()
    state = secrets.token_urlsafe(16)
    result: dict = {}

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            q = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            if not self.path.startswith("/callback"):
                self.send_response(404)
                self.end_headers()
                return
            if q.get("state", [""])[0] != state:
                result["error"] = "State mismatch (possible forged request). Try again."
            elif "error" in q:
                result["error"] = q.get("error_description", q["error"])[0]
            else:
                result["code"] = q.get("code", [""])[0]
            ok = "code" in result
            body = ("<h2>Moyo is now connected to TikTok. You can close this tab.</h2>" if ok
                    else f"<h2>TikTok connection failed</h2><p>{result.get('error', '')}</p>").encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *a):
            pass

    try:
        srv = http.server.HTTPServer(("127.0.0.1", TT_PORT), Handler)
    except OSError:
        raise SocialError(f"Port {TT_PORT} is busy. Close whatever is using it and try again.")
    srv.timeout = 2
    url = tt_auth_url(state, challenge)
    if open_browser:
        import webbrowser
        webbrowser.open(url)
    deadline = time.time() + timeout
    try:
        while not result and time.time() < deadline:
            srv.handle_request()
    finally:
        srv.server_close()
    if "code" not in result:
        raise SocialError(result.get("error") or "Timed out waiting for TikTok sign-in.")
    tokens = _tt_token({"code": result["code"], "grant_type": "authorization_code",
                        "redirect_uri": TT_REDIRECT, "code_verifier": verifier})
    missing = [s for s in TT_SCOPES.split(",") if s not in tokens["scope"]]
    if missing:
        raise SocialError(f"Connected, but TikTok didn't grant: {', '.join(missing)}. Add those scopes to your app and reconnect.")


def tt_connect_async(on_done=None) -> None:
    def run():
        STATE.update(tiktok_connecting=True, tiktok_error=None)
        try:
            tt_connect_blocking()
            if on_done:
                on_done()
        except Exception as e:
            STATE["tiktok_error"] = str(e)
        finally:
            STATE["tiktok_connecting"] = False
    threading.Thread(target=run, daemon=True).start()


def _tt_access() -> str:
    t = _get_secret("tiktok_tokens")
    if not t:
        raise SocialError("TikTok isn't connected.")
    if time.time() >= t["expires_at"]:
        if time.time() >= t.get("refresh_expires_at", 0):
            raise SocialError("TikTok access expired. Reconnect TikTok in Settings.")
        t = _tt_token({"grant_type": "refresh_token", "refresh_token": t["refresh_token"]})
    return t["access_token"]


def _tt_call(method: str, path: str, fields: str, body: dict | None = None) -> dict:
    tok = _tt_access()
    r = _net(lambda: httpx.request(method, f"{TT_API}/{path}", params={"fields": fields},
                                   headers={"Authorization": f"Bearer {tok}", "Content-Type": "application/json"},
                                   json=body, timeout=30))
    data = r.json()
    err = data.get("error") or {}
    if err.get("code") not in (None, "ok"):
        raise SocialError(f"TikTok: {err.get('message') or err.get('code')}")
    return data.get("data") or {}


def tt_sync(con, pages: int = 2) -> int:
    if not tt_connected():
        return 0
    # only fields covered by user.info.basic + user.info.stats ("username" would need user.info.profile)
    user = _tt_call("GET", "user/info/", "open_id,display_name,follower_count,video_count").get("user", {})
    STATE["tiktok_account"] = user.get("display_name")
    _record_followers(con, "tiktok", user.get("follower_count"))
    n, cursor = 0, None
    for _ in range(pages):
        body = {"max_count": 20, **({"cursor": cursor} if cursor else {})}
        d = _tt_call("POST", "video/list/", "id,title,video_description,create_time,share_url,view_count,"
                                             "like_count,comment_count,share_count,duration", body)
        for v in d.get("videos", []):
            ts = datetime.fromtimestamp(int(v["create_time"]))
            title = (v.get("title") or v.get("video_description") or "").strip().split("\n")[0][:140]
            _upsert(con, "tiktok", str(v["id"]), ts, title, v.get("share_url"), v.get("view_count"),
                    v.get("like_count"), v.get("comment_count"), v.get("share_count"))
            n += 1
        if not d.get("has_more"):
            break
        cursor = d.get("cursor")
    return n


# ================================================================ shared
def _local(iso: str) -> datetime:
    d = datetime.fromisoformat(iso.replace("Z", "+00:00").replace("+0000", "+00:00"))
    return d.astimezone().replace(tzinfo=None) if d.tzinfo else d


def _upsert(con, platform, ext_id, ts: datetime, title, url, views, likes, comments, shares):
    day = ts.date().isoformat()
    existing = con.execute("SELECT id FROM content_log WHERE platform=? AND external_id=?", (platform, ext_id)).fetchone()
    if not existing:  # attach to a manual "I posted" entry for the same day instead of double counting
        existing = con.execute("SELECT id FROM content_log WHERE platform=? AND date=? AND external_id IS NULL "
                               "ORDER BY id LIMIT 1", (platform, day)).fetchone()
    vals = (day, title or None, url, views, likes, comments, shares, ts.isoformat(), now_iso())
    if existing:
        con.execute("UPDATE content_log SET date=?, title=COALESCE(?, title), url=?, views=?, likes=?, comments=?, "
                    "shares=?, posted_at=?, metrics_updated_at=?, external_id=? WHERE id=?", (*vals, ext_id, existing["id"]))
    else:
        con.execute("INSERT INTO content_log(date, title, url, views, likes, comments, shares, posted_at, "
                    "metrics_updated_at, external_id, platform, created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                    (*vals, ext_id, platform, now_iso()))


def _record_followers(con, platform, count):
    if count is None:
        return
    from moyo.db import get_setting, set_setting, today
    hist = get_setting(con, "followers") or {}
    hist.setdefault(platform, {})[today().isoformat()] = int(count)
    hist[platform] = dict(sorted(hist[platform].items())[-60:])
    set_setting(con, "followers", hist)


def sync_all(con) -> dict:
    out = {"ok": True}
    with _lock:
        for name, fn, connected in (("instagram", ig_sync, ig_connected), ("tiktok", tt_sync, tt_connected)):
            if not connected():
                continue
            try:
                out[name] = fn(con)
            except Exception as e:
                msg = str(e) if isinstance(e, SocialError) else f"{type(e).__name__}: {str(e)[:150]}"
                out["ok"] = False
                out[f"{name}_error"] = msg
        errs = "; ".join(v for k, v in out.items() if k.endswith("_error"))
        STATE.update(last_sync=now_iso(), last_sync_error=errs or None)
        audit.log(con, "moyo", "social_sync", "read", {k: v for k, v in out.items() if k != "ok"},
                  "ok" if out["ok"] else f"error: {errs}")
    return out


def disconnect(con, platform: str) -> None:
    if platform == "instagram":
        _del_secret("instagram")
        STATE["instagram_account"] = None
    elif platform == "tiktok":
        t = _get_secret("tiktok_tokens")
        c = tt_client()
        if t and c:
            try:
                httpx.post(f"{TT_API}/oauth/revoke/", data={"client_key": c["client_key"], "client_secret": c["client_secret"],
                                                            "token": t["access_token"]}, timeout=15)
            except Exception:
                pass
        _del_secret("tiktok_tokens")
        STATE["tiktok_account"] = None
    else:
        raise SocialError("Unknown platform.")
    # keep the post log (your own history) but drop synced metrics so nothing stale lingers
    con.execute("UPDATE content_log SET external_id=NULL, metrics_updated_at=NULL WHERE platform=?", (platform,))


def status() -> dict:
    ig = _get_secret("instagram") or {}
    tt = _get_secret("tiktok_tokens") or {}
    return {"instagram": {"connected": bool(ig), "account": STATE["instagram_account"] or ig.get("username"),
                          "auto_renews": ig.get("kind") == "instagram",
                          "insights_error": STATE.get("instagram_insights_error"),
                          "token_days_left": round((ig.get("refreshed_at", 0) + 60 * 86400 - time.time()) / 86400) if ig else None},
            "tiktok": {"connected": bool(tt), "has_client": bool(tt_client()), "account": STATE["tiktok_account"],
                       "connecting": STATE["tiktok_connecting"], "error": STATE["tiktok_error"],
                       "redirect_uri": TT_REDIRECT, "scopes": TT_SCOPES},
            "last_sync": STATE["last_sync"], "last_sync_error": STATE["last_sync_error"]}
