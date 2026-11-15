import hashlib
import json
import time
import urllib.parse
from datetime import date, datetime

import pytest

from moyo import coach, content, social
from moyo.cloud import Redactor
from moyo import money

REF = date(2026, 11, 12)


class R:
    def __init__(self, data, status=200):
        self._d, self.status_code = data, status
        self.headers = {"content-type": "application/json"}

    def json(self):
        return self._d


@pytest.fixture
def secrets_store(monkeypatch):
    store = {}
    monkeypatch.setattr(social, "_get_secret", lambda n: store.get(n))
    monkeypatch.setattr(social, "_set_secret", lambda n, v: store.__setitem__(n, v))
    monkeypatch.setattr(social, "_del_secret", lambda n: store.pop(n, None))
    monkeypatch.setattr(social, "ig_connected", lambda: "instagram" in store)
    monkeypatch.setattr(social, "tt_connected", lambda: "tiktok_tokens" in store)
    return store


def ig_get(url, params=None, timeout=None):
    path = url.split("graph.instagram.com/")[1]
    if path == "me":
        return R({"user_id": "1", "username": "moyosore.builds", "account_type": "BUSINESS", "followers_count": 1520})
    if path == "me/media":
        return R({"data": [
            {"id": "ig1", "caption": "How I built an AI receptionist\n#ai", "timestamp": "2026-11-11T18:30:00+0000",
             "permalink": "https://instagram.com/p/1", "like_count": 140, "comments_count": 22},
            {"id": "ig2", "caption": "Day 3 of the 10K challenge", "timestamp": "2026-11-10T18:00:00+0000",
             "permalink": "https://instagram.com/p/2", "like_count": 40, "comments_count": 3},
        ]})
    if path == "ig1/insights":
        return R({"data": [{"name": "views", "values": [{"value": 3200}]}, {"name": "shares", "values": [{"value": 15}]}]})
    if path == "ig2/insights":
        return R({"error": {"message": "Insights not available yet"}}, 400)
    raise AssertionError(path)


def test_instagram_sync_and_merge_manual_entry(con, secrets_store, monkeypatch):
    monkeypatch.setattr(social.httpx, "get", ig_get)
    content.log_post(con, "instagram", "my manual note", on="2026-11-11")  # logged by hand earlier
    info = social.ig_save_token("IGAA" + "x" * 60)
    assert info["username"] == "moyosore.builds"
    out = social.sync_all(con)
    assert out["ok"] and out["instagram"] == 2
    posts = {r["external_id"]: dict(r) for r in con.execute("SELECT * FROM content_log WHERE platform='instagram'")}
    assert len(posts) == 2  # manual entry merged, not duplicated
    assert posts["ig1"]["views"] == 3200 and posts["ig1"]["likes"] == 140 and posts["ig1"]["shares"] == 15
    assert posts["ig1"]["title"] == "How I built an AI receptionist"
    assert posts["ig2"]["views"] is None  # unavailable insight stays missing, never guessed


def test_instagram_bad_token(secrets_store, monkeypatch):
    monkeypatch.setattr(social.httpx, "get", lambda *a, **k: R({"error": {"message": "Invalid OAuth access token"}}, 400))
    with pytest.raises(social.SocialError, match="token"):
        social.ig_save_token("IGAA" + "y" * 60)
    with pytest.raises(social.SocialError):
        social.ig_save_token("short")


def test_token_cleaning_and_hints():
    tok = "IGAA" + "z" * 150
    assert social.clean_token(f'  "{tok[:80]}\n{tok[80:]}"  ') == tok
    assert social.clean_token(f"https://x.com/cb#access_token={tok}&expires_in=5184000") == tok
    assert "App ID" in social.describe("2161124037816863")
    assert "Facebook token" in social.describe("EAA" + "q" * 150) and "EAA" + "q" not in social.describe("EAA" + "q" * 150)


def test_unified_login_eaa_token_for_instagram_user(con, secrets_store, monkeypatch):
    """2026 'Unified login': token starts with EAA but /me on graph.facebook.com IS the Instagram user."""
    IGID = "17840000000000001"

    def get(url, params=None, timeout=None):
        f = (params or {}).get("fields", "")
        if url.endswith(f"graph.facebook.com/{IGID}/media"):
            return R({"data": [{"id": "u1", "caption": "unified post", "timestamp": "2026-11-11T09:00:00+0000",
                                "like_count": 5, "comments_count": 2}]})
        if url.endswith("graph.facebook.com/me"):  # what the user hit: /me isn't the IG node
            if "followers_count" in f or "username" in f:
                return R({"error": {"message": "(#100) Tried accessing nonexisting field (username)"}}, 400)
            return R({"id": "999"})
        if url.endswith(f"graph.facebook.com/{IGID}"):
            if f == "followers_count":
                return R({"followers_count": 2100})
            return R({"id": IGID, "username": "moyocode"})
        if url.endswith("graph.facebook.com/u1/insights"):
            return R({"data": [{"name": "views", "values": [{"value": 777}]}]})
        return R({"error": {"message": "Cannot parse access token"}}, 400)
    monkeypatch.setattr(social.httpx, "get", get)
    with pytest.raises(social.SocialError, match="account ID"):  # without the ID: clear tip
        social.ig_save_token("EAA" + "u" * 200)
    info = social.ig_save_token("EAA" + "u" * 200, IGID)
    assert info["username"] == "moyocode" and info["route"] == "facebook" and info["followers"] == 2100
    assert social.sync_all(con)["instagram"] == 1
    assert con.execute("SELECT views FROM content_log WHERE external_id='u1'").fetchone()[0] == 777


def test_facebook_flavour_token(con, secrets_store, monkeypatch):
    def fb_get(url, params=None, timeout=None):
        if "graph.facebook.com/" not in url:
            return R({"error": {"message": "Cannot parse access token"}}, 400)
        path = url.split("graph.facebook.com/")[1]
        if path == "me":
            return R({"id": "100", "name": "Moyosore"})  # a Facebook person, not an Instagram account
        if path == "me/accounts":
            return R({"data": [{"name": "MoyoCode", "instagram_business_account": {"id": "178", "username": "moyosore.builds",
                                                                                    "followers_count": 1520}}]})
        if path == "178":
            return R({"username": "moyosore.builds", "followers_count": 1520})
        if path == "178/media":
            return R({"data": [{"id": "m9", "caption": "FB-flavour post", "timestamp": "2026-11-11T10:00:00+0000",
                                "like_count": 9, "comments_count": 1}]})
        if path == "m9/insights":
            return R({"data": [{"name": "views", "values": [{"value": 444}]}]})
        raise AssertionError(path)
    monkeypatch.setattr(social.httpx, "get", fb_get)
    assert social.ig_save_token("EAA" + "f" * 150)["username"] == "moyosore.builds"
    assert social.sync_all(con)["instagram"] == 1
    assert con.execute("SELECT views FROM content_log WHERE external_id='m9'").fetchone()[0] == 444


def test_tiktok_pkce_hex_and_auth_url(secrets_store):
    social.tt_save_client("awxyz12345", "s" * 32)
    v, c = social._pkce()
    assert c == hashlib.sha256(v.encode()).hexdigest() and len(c) == 64  # TikTok desktop wants HEX
    q = urllib.parse.parse_qs(urllib.parse.urlparse(social.tt_auth_url("st8", c)).query)
    assert q["redirect_uri"] == ["http://127.0.0.1:8977/callback/"] and q["code_challenge_method"] == ["S256"]
    assert q["scope"] == ["user.info.basic,user.info.stats,video.list"]


def test_tiktok_sync_with_refresh_and_paging(con, secrets_store, monkeypatch):
    social.tt_save_client("awxyz12345", "s" * 32)
    secrets_store["tiktok_tokens"] = {"access_token": "old", "refresh_token": "r1", "expires_at": time.time() - 5,
                                      "refresh_expires_at": time.time() + 9999, "scope": social.TT_SCOPES}
    posted = []

    def post(url, data=None, headers=None, timeout=None):
        posted.append(data)
        return R({"access_token": "new", "refresh_token": "r2", "expires_in": 86400, "refresh_expires_in": 31536000,
                  "scope": social.TT_SCOPES, "open_id": "o"})
    calls = []

    def request(method, url, params=None, headers=None, json=None, timeout=None):
        calls.append((method, url, headers["Authorization"], json))
        if url.endswith("user/info/"):
            if "username" in params["fields"]:  # needs user.info.profile, which Moyo doesn't request
                return R({"error": {"code": "scope_not_authorized",
                                    "message": "The user did not authorize the scope required for completing this request."}})
            return R({"data": {"user": {"display_name": "Moyosore", "follower_count": 980}}, "error": {"code": "ok"}})
        ts = int(datetime(2026, 11, 11, 20).timestamp())
        if not json.get("cursor"):
            return R({"data": {"videos": [{"id": 111, "title": "AI agent for a Lagos pharmacy", "create_time": ts,
                                           "view_count": 5400, "like_count": 300, "comment_count": 41, "share_count": 12}],
                               "cursor": 123, "has_more": True}, "error": {"code": "ok"}})
        return R({"data": {"videos": [{"id": 112, "video_description": "older one", "create_time": ts - 86400,
                                       "view_count": 900, "like_count": 30, "comment_count": 2, "share_count": 0}],
                           "has_more": False}, "error": {"code": "ok"}})
    monkeypatch.setattr(social.httpx, "post", post)
    monkeypatch.setattr(social.httpx, "request", request)
    out = social.sync_all(con)
    assert out == {"ok": True, "tiktok": 2}
    assert posted[0]["grant_type"] == "refresh_token" and secrets_store["tiktok_tokens"]["access_token"] == "new"
    assert all(h == "Bearer new" for _, _, h, _ in calls)
    row = con.execute("SELECT * FROM content_log WHERE external_id='111'").fetchone()
    assert row["views"] == 5400 and row["date"] == "2026-11-11"


def _seed_history(con, platform, views_list, start_day=1):
    for i, v in enumerate(views_list):
        d = f"2026-11-{start_day + i:02d}"
        con.execute("INSERT INTO content_log(date, platform, title, views, likes, comments, shares, posted_at, external_id, created_at) "
                    "VALUES (?,?,?,?,?,?,?,?,?,?)", (d, platform, f"post {i}", v, v // 20, v // 100, 0, d + "T18:00:00",
                                                       f"{platform}{i}", d))


def test_performance_vs_baseline(con):
    _seed_history(con, "tiktok", [1000, 1200, 800, 1100, 900, 1000, 3000], start_day=5)  # last one = 11 Nov
    perf = content.performance(con, REF)
    x = perf["tiktok"]["recent"][0]
    assert x["date"] == "2026-11-11" and x["baseline_views"] == 1000 and x["vs_baseline"] == 3.0
    s = content.performance_sentences(perf)[0]
    assert "3,000 views" in s and "3.0 times your usual 1,000 views" in s


def test_dropped_connection_is_retried(con, secrets_store, monkeypatch):
    calls = {"n": 0}

    def flaky(url, params=None, timeout=None):
        calls["n"] += 1
        if calls["n"] == 1:
            raise social.httpx.ConnectError("[WinError 10054] connection forcibly closed")
        return ig_get(url, params, timeout)
    monkeypatch.setattr(social.httpx, "get", flaky)
    monkeypatch.setattr(social.time, "sleep", lambda s: None)
    secrets_store["instagram"] = {"token": "IGAA" + "x" * 60, "kind": "instagram", "ig_id": "me", "refreshed_at": time.time()}
    assert social.sync_all(con) == {"ok": True, "instagram": 2}


def test_fresh_post_is_not_judged(con):
    _seed_history(con, "tiktok", [1000, 1200, 800, 1100], start_day=5)
    just_now = datetime.now().replace(microsecond=0)
    con.execute("UPDATE content_log SET views=30, posted_at=?, date=? WHERE external_id='tiktok3'",
                (just_now.isoformat(), "2026-11-11"))
    x = content.performance(con, REF)["tiktok"]["recent"][0]
    assert x["fresh"] is True and x["vs_baseline"] is None
    assert "too early to judge" in content.performance_sentences(content.performance(con, REF))[0]


def test_coach_gets_redacted_content_metrics(con, secrets_store, monkeypatch):
    secrets_store["instagram"] = {"token": "t", "refreshed_at": time.time()}
    money.add_lead(con, "Kemi Stores")
    _seed_history(con, "instagram", [500, 600, 700, 650], start_day=8)  # 8–11 Nov: inside the 7-day window
    con.execute("UPDATE content_log SET title='Website for Kemi Stores' WHERE external_id='instagram3'")
    snap = coach.snapshot(con, Redactor(con), REF)
    topics = [x["topic"] for x in snap["content_performance"]["instagram"]["last_7_days"]]
    assert "Website for CLIENT_1" in topics and "Kemi" not in json.dumps(snap)
