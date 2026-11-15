from fastapi.testclient import TestClient

from moyo import server, workspaces

H = {"X-Moyo": "1"}
c = TestClient(server.app)


def test_dashboard_loads():
    r = c.get("/api/dashboard")
    assert r.status_code == 200
    d = r.json()
    assert d["challenge"]["target_usd"] == 10000 and "Moyosore" in d["text"]
    assert "Performance numbers aren't connected yet" in d["text"]  # says what's missing


def test_security_guards():
    assert c.post("/api/chat", json={"text": "what's my plan"}).status_code == 403  # no X-Moyo header
    assert c.get("/api/dashboard", headers={"Host": "evil.example"}).status_code == 403
    assert c.post("/api/chat", json={"text": "plan"}, headers={**H, "Origin": "https://evil.example"}).status_code == 403


def test_chat_task_flow():
    r = c.post("/api/chat", json={"text": "add task send proposal to Tunde tomorrow"}, headers=H).json()
    assert r["via"] == "local" and "Added task" in r["reply"]
    tid = r["data"]["id"]
    r = c.post("/api/chat", json={"text": f"done {tid}"}, headers=H).json()
    assert r["reply"].startswith("Done")


def test_payment_confirm_flow_via_api():
    c.post("/api/action/set_rate", json={"ngn_per_usd": 1500}, headers=H)
    pend = c.post("/api/action/set_rate", json={"ngn_per_usd": 1500}, headers=H).json()
    c.post("/api/confirm", json={"pending_id": pend["pending_id"], "accept": True}, headers=H)
    r = c.post("/api/chat", json={"text": "log payment ₦300,000 from Kemi Stores"}, headers=H).json()
    assert r["needs_confirmation"] and "$200" in r["reply"] and "RECEIVED" in r["reply"]  # D41: payment = received → ledger
    assert c.get("/api/money").json()["challenge"]["earned_usd"] == 0
    c.post("/api/confirm", json={"pending_id": r["pending_id"], "accept": True}, headers=H)
    assert c.get("/api/money").json()["challenge"]["earned_usd"] == 200


def test_workspace_allowlist(monkeypatch):
    p = workspaces.plan("dev")
    assert p["key"] == "coding"
    for a in p["apps"]:
        assert a["exe"].lower().endswith(".exe")
    try:
        workspaces._exe(r"C:\Windows\System32\cmd.exe")
        assert False, "cmd.exe must be refused"
    except workspaces.WorkspaceError:
        pass


def test_memory_crud():
    items = c.get("/api/memory").json()
    mid = items[0]["id"]
    assert c.patch(f"/api/memory/{mid}", json={"content": "edited"}, headers=H).json()["content"] == "edited"
    assert c.delete(f"/api/memory/{mid}", headers=H).status_code == 200
    assert all(m["id"] != mid for m in c.get("/api/memory").json())
