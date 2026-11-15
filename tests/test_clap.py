import numpy as np

from moyo.clap import SR, Params, analyze

rng = np.random.default_rng(7)


def silence(ms, noise=0.002):
    return (rng.standard_normal(int(SR * ms / 1000)) * noise).astype(np.float32)


def clap(amp=0.5):
    n = int(SR * 0.08)
    env = np.exp(-np.arange(n) / (SR * 0.012))           # very fast decay
    return (rng.standard_normal(n) * env * amp).astype(np.float32)


def speech(ms=400, amp=0.3):
    t = np.arange(int(SR * ms / 1000)) / SR
    env = np.minimum(1, t / 0.06)                         # slow attack, sustained
    sig = sum(np.sin(2 * np.pi * f * t) / k for k, f in enumerate((180, 360, 540, 720), 1))
    return (sig * env * amp / 2).astype(np.float32)


def knock(amp=0.6):
    t = np.arange(int(SR * 0.12)) / SR
    return (np.sin(2 * np.pi * 110 * t) * np.exp(-t / 0.02) * amp).astype(np.float32)


def cat(*parts):
    return np.concatenate(parts)


def test_double_clap_triggers_once():
    sig = cat(silence(600), clap(), silence(300), clap(), silence(1200))
    trig, ev = analyze(sig)
    assert len(trig) == 1 and len(ev) == 2


def test_single_clap_does_not_trigger():
    assert analyze(cat(silence(600), clap(), silence(1500)))[0] == []


def test_claps_too_far_apart_do_not_trigger():
    assert analyze(cat(silence(600), clap(), silence(1200), clap(), silence(1200)))[0] == []


def test_applause_does_not_trigger():
    parts = [silence(600)]
    for _ in range(8):
        parts += [clap(), silence(120)]
    assert analyze(cat(*parts, silence(1500)))[0] == []


def test_speech_does_not_trigger():
    sig = cat(silence(500), speech(), silence(150), speech(300), silence(200), speech(), silence(1200))
    assert analyze(sig)[0] == []


def test_low_knock_does_not_trigger():
    sig = cat(silence(500), knock(), silence(250), knock(), silence(1200))
    assert analyze(sig)[0] == []


def test_quiet_typing_does_not_trigger():
    parts = [silence(500)]
    for _ in range(10):
        parts += [clap(amp=0.004), silence(140)]                # tiny clicks: below loudness threshold
    assert analyze(cat(*parts, silence(1200)))[0] == []


def test_cooldown_prevents_repeat():
    pair = [clap(), silence(300), clap(), silence(1000)]
    sig = cat(silence(600), *pair, *pair, silence(500))
    assert len(analyze(sig)[0]) == 1                           # second pair within 8 s cooldown


def test_digital_silence_gating_like_this_laptop():
    # Intel Smart Sound zeros quiet parts; background becomes -90 dB; claps must still be detected.
    z = lambda ms: np.zeros(int(SR * ms / 1000), np.float32)
    assert len(analyze(cat(z(600), clap(), z(300), clap(), z(1200)))[0]) == 1


# ---------------------------------------------------------------- wake manager, brief, API
from datetime import datetime  # noqa: E402

from fastapi.testclient import TestClient  # noqa: E402

from moyo import briefing, db, server, wake  # noqa: E402

NOTIF = {"quiet_start": "22:30", "quiet_end": "07:00"}


def test_listener_follows_setting_and_quiet_hours():
    noon, night = datetime(2026, 11, 12, 12, 0), datetime(2026, 11, 12, 23, 30)
    assert wake.should_listen({"enabled": False}, NOTIF, noon) == (False, "off")
    assert wake.should_listen({"enabled": True}, NOTIF, noon) == (True, "listening")
    assert wake.should_listen({"enabled": True}, NOTIF, night) == (False, "quiet_hours")
    assert wake.should_listen({"enabled": True, "listen_in_quiet_hours": True}, NOTIF, night)[0]


def test_calibrated_params_are_used_and_unknown_keys_ignored():
    p = wake.params_from({"params": {"min_db": -40.5, "bright_min": 0.7, "evil": 1}})
    assert p.min_db == -40.5 and p.bright_min == 0.7 and p.gap_max_ms == Params().gap_max_ms


def test_clap_is_off_by_default(con):
    assert db.get_setting(con, "clap")["enabled"] is False


def test_wake_brief_is_short_and_uses_only_stored_data(con):
    b = briefing.short(con, datetime(2026, 11, 12, 8, 0))
    assert b["question"] == "Want to see your full dashboard?"
    assert 3 <= len(b["sentences"]) <= 7
    assert b["sentences"][0].startswith("Good morning, Moyosore")
    assert "$0" in b["sentences"][1] and "$10,000" in b["sentences"][1]  # nothing earned yet: never invented


def test_wake_api(monkeypatch):
    c, H = TestClient(server.app), {"X-Moyo": "1"}
    assert c.get("/api/wake/brief").json()["sentences"]
    st = c.get("/api/wake/status").json()
    assert st["listening"] is False and "enabled" in st
    assert c.put("/api/settings/clap", json={"enabled": True}).status_code == 403  # header required
    r = c.put("/api/settings/clap", json={"enabled": True, "params": {"min_db": 0}}, headers=H).json()
    assert r["enabled"] is True and r["listening"] is False  # tests never open the mic
    assert db.get_setting(server.con(), "clap")["params"] == {}  # params only change via calibration
    c.put("/api/settings/clap", json={"enabled": False}, headers=H)
    launched = []
    monkeypatch.setattr(wake.manager, "launch_orb", lambda source="clap": launched.append(source) or True)
    assert c.post("/api/wake/test", headers=H).json() == {"opened": True} and launched == ["test"]


# ---------------------------------------------------------------- clap + "let's get to work" (offline Vosk)
import io  # noqa: E402

import pytest  # noqa: E402

from moyo import clap as clapmod  # noqa: E402

needs_model = pytest.mark.skipif(not clapmod.MODEL_DIR.exists(), reason="Vosk model not downloaded")


@pytest.fixture(scope="module")
def say():
    import soundfile as sf

    from moyo import tts
    cache = {}

    def _say(text):
        if text not in cache:
            data, _ = tts.synthesize(text, "kokoro", "af_heart", 1.0)
            x, sr = sf.read(io.BytesIO(data), dtype="float32")
            cache[text] = clapmod._to16k(x.mean(1) if x.ndim > 1 else x, sr) * 0.5
        return cache[text]
    return _say


@pytest.fixture(scope="module")
def spotter():
    return clapmod.PhraseSpotter()


def run_listener(sig, spotter):
    woke = []
    lst = clapmod.Listener(clapmod.PHRASE_PARAMS, lambda: woke.append(1), mode="clap_phrase", spotter=spotter, sync=True)
    for i in range(0, len(sig), 640):
        lst.process(sig[i:i + 640])
    return woke, lst


@needs_model
def test_clap_then_phrase_wakes(say, spotter):
    woke, lst = run_listener(cat(silence(800), clap(0.3), silence(400), say("Let's get to work."), silence(5000)), spotter)
    assert woke == [1] and "get to work" in lst.last_heard


@needs_model
def test_clap_then_other_words_does_not_wake(say, spotter):
    woke, lst = run_listener(cat(silence(800), clap(0.3), silence(400), say("Let's get some water."), silence(5000)), spotter)
    assert woke == [] and lst.windows >= 1


@needs_model
def test_clap_alone_only_opens_window(spotter):
    woke, lst = run_listener(cat(silence(800), clap(0.3), silence(6000)), spotter)
    assert woke == [] and lst.windows == 1


@needs_model
def test_phrase_mode_cooldown(say, spotter):
    once = [silence(800), clap(0.3), silence(400), say("Let's get to work."), silence(1500)]
    woke, _ = run_listener(cat(*once, *once, silence(4000)), spotter)  # second attempt within 8 s: ignored
    assert woke == [1]


def test_phrase_match_allows_swallowed_to():
    assert clapmod.phrase_matches("lets get work") and clapmod.phrase_matches("lets get to work")
    assert not clapmod.phrase_matches("lets get [unk]") and not clapmod.phrase_matches("work")
    assert not clapmod.phrase_matches("we get to work at nine")  # needs "let's"


@needs_model
def test_everyday_talk_not_heard_as_phrase(say, spotter):
    for text in ["I need to get to the office and work on the project.", "Let's go to the gym later.",
                 "Okay let me check my email first.", "We got work to do today.", "Let's get some water."]:
        heard = spotter.check(cat(silence(300), say(text), silence(500)))
        assert not clapmod.phrase_matches(heard), (text, heard)
    assert clapmod.phrase_matches(spotter.check(cat(silence(300), say("Let's get to work."), silence(500))))


def test_answer_intents():
    a = clapmod.answer_intent
    assert a("open my dashboard") == a("yes please") == a("show me the dashboard") == "open"
    assert a("start my day") == "start_day"
    assert a("later") == a("not now") == a("no thanks") == "later"
    assert a("[unk]") is None and a("") is None


@needs_model
def test_spoken_answers_recognised(say, spotter):
    import json as _json
    for text, want in [("Open my dashboard.", "open"), ("Yes please.", "open"), ("Start my day.", "start_day"),
                       ("Not now.", "later"), ("I need some water.", None)]:
        r = clapmod.answer_recognizer(spotter)
        r.AcceptWaveform(clapmod._pcm16(cat(silence(300), say(text), silence(600))))
        heard = _json.loads(r.FinalResult()).get("text", "")
        assert clapmod.answer_intent(heard) == want, (text, heard)


def test_lets_get_started_also_wakes():
    assert clapmod.phrase_matches("lets get started") and clapmod.phrase_matches("let us get started")
    assert not clapmod.phrase_matches("we get started at nine")


def test_listener_reconnects_when_mic_goes_silent_after_sleep(monkeypatch):
    import sys
    import time as _t
    import types
    opened = []

    class SilentStream:  # like Windows after Modern Standby: "active", but no audio ever arrives
        def __init__(self, **kw): opened.append(kw)
        def start(self): pass
        def stop(self): pass
        def close(self): pass
        active = True
    fake = types.SimpleNamespace(InputStream=SilentStream, _terminate=lambda: None, _initialize=lambda: None)
    monkeypatch.setitem(sys.modules, "sounddevice", fake)
    monkeypatch.setattr(clapmod, "STALE_S", 0.5)
    lst = clapmod.Listener(clapmod.Params(), lambda: None, mode="double_clap")
    lst.start()
    _t.sleep(2.6)
    lst.stop()
    assert lst.reconnects >= 1 and len(opened) >= 2   # it noticed the silence and reopened the mic
