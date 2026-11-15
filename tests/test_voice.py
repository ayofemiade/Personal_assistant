from fastapi.testclient import TestClient

from moyo import server, tts

H = {"X-Moyo": "1"}
c = TestClient(server.app)


def test_speakable_money():
    s = tts.speakable("You've earned $133.33 of your $10K target; need $785 a week, ₦200,000 logged, 12% done.")
    assert "133 dollars 33 cents" in s and "ten K target" in s and "785 dollars" in s
    assert "200,000 naira" in s and "12 percent" in s and "$" not in s and "₦" not in s


def test_voice_catalog_and_settings():
    v = c.get("/api/voices").json()
    assert {"gemini", "edge", "kokoro", "browser"} <= set(v["engines"])
    assert any(x["id"] == "en-NG-EzinneNeural" for x in v["engines"]["edge"]["voices"])
    assert v["current"]["engine"] == "gemini" and v["current"]["chosen"] is False
    r = c.put("/api/settings/voice", json={"engine": "edge", "voice": "en-NG-AbeoNeural", "speed": 9}, headers=H).json()
    assert r["engine"] == "edge" and r["speed"] == 1.4 and r["chosen"] is True
    assert c.put("/api/settings/voice", json={"engine": "shell"}, headers=H).status_code == 400


def test_tts_falls_back_then_reports(monkeypatch):
    calls = []

    def boom(name):
        def f(text, voice, speed):
            calls.append(name)
            raise tts.TTSError(f"{name} down")
        return f
    monkeypatch.setattr(tts, "ENGINES", {k: boom(k) for k in tts.ENGINES})
    r = c.post("/api/tts", json={"text": "Hello Moyosore"}, headers=H)
    assert r.status_code == 503 and len(calls) == 3  # chosen voice + two fallbacks tried

    def ok(text, voice, speed):
        return b"RIFFfake", "audio/wav"
    monkeypatch.setattr(tts, "ENGINES", {**{k: boom(k) for k in tts.ENGINES}, "kokoro": ok})
    r = c.post("/api/tts", json={"text": "Hello again"}, headers=H)
    assert r.status_code == 200 and r.headers["x-moyo-voice"].startswith("kokoro")
