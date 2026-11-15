"""Text-to-speech engines for Moyo, with a fallback chain.

  gemini  – Google Gemini TTS (free tier, natural, warm; needs internet + daily quota)
  edge    – Microsoft neural voices incl. Nigerian English (free, via the unofficial
            Edge read-aloud service used by the open-source edge-tts package: may stop working)
  kokoro  – Kokoro-82M on this laptop (free, offline, private; Apache-2.0)
  browser – the browser's built-in voices (played client-side; last resort)
"""
from __future__ import annotations

import asyncio
import hashlib
import io
import re
import threading
import wave

from moyo.db import DATA_DIR, ROOT, get_setting

KOKORO_DIR = ROOT / "models" / "kokoro"
CACHE = DATA_DIR / "tts_cache"

CATALOG = {
    "gemini": {
        "label": "Gemini (Google)", "note": "Most natural and warm. Needs internet; free daily limit.",
        "voices": [
            ("Sulafat", "Warm"), ("Achird", "Friendly"), ("Vindemiatrix", "Gentle"), ("Kore", "Firm, clear"),
            ("Aoede", "Breezy"), ("Leda", "Youthful"), ("Puck", "Upbeat"), ("Charon", "Informative"),
            ("Gacrux", "Mature"), ("Orus", "Steady"), ("Zephyr", "Bright"), ("Sadaltager", "Knowledgeable"),
        ],
    },
    "edge": {
        "label": "Microsoft natural voices", "note": "Includes Nigerian English. Free, needs internet; unofficial service.",
        "voices": [
            ("en-NG-EzinneNeural", "Ezinne · Nigerian English, female"), ("en-NG-AbeoNeural", "Abeo · Nigerian English, male"),
            ("en-US-AvaNeural", "Ava · American, expressive"), ("en-US-AndrewNeural", "Andrew · American, warm"),
            ("en-GB-SoniaNeural", "Sonia · British"), ("en-GB-RyanNeural", "Ryan · British"),
        ],
    },
    "kokoro": {
        "label": "Kokoro (offline)", "note": "Runs on this laptop: private and works without internet.",
        "voices": [
            ("af_heart", "Heart · American, warm"), ("af_bella", "Bella · American"), ("af_nicole", "Nicole · American, soft"),
            ("bf_emma", "Emma · British"), ("am_michael", "Michael · American"), ("bm_george", "George · British"),
        ],
    },
    "browser": {"label": "Basic (Windows)", "note": "Built into the browser. Always available, sounds robotic.", "voices": []},
}

GEMINI_MODELS = ["gemini-3.8-flash-tts", "gemini-3.8-flash-lite-tts", "gemini-3.1-flash-tts-preview",
                 "gemini-2.5-flash-preview-tts"]
DEFAULT_CHAIN = [("gemini", "Sulafat"), ("edge", "en-NG-EzinneNeural"), ("kokoro", "af_heart")]


class TTSError(RuntimeError):
    pass


def speakable(text: str) -> str:
    """Make money, symbols and abbreviations sound right when read aloud."""
    t = text
    t = re.sub(r"\$?10[kK]\b", "ten K", t).replace("Ten-K", "Ten K")
    t = re.sub(r"\$([\d,]+)\.(\d\d)\b", lambda m: f"{m.group(1)} dollars {int(m.group(2))} cents"
               if int(m.group(2)) else f"{m.group(1)} dollars", t)
    t = re.sub(r"\$([\d,]+(?:\.\d+)?)", lambda m: f"{m.group(1)} dollars", t)
    t = re.sub(r"₦([\d,]+(?:\.\d+)?)", lambda m: f"{m.group(1)} naira", t)
    t = re.sub(r"(\d+(?:\.\d+)?)%", r"\1 percent", t)
    t = re.sub(r"\s*\n+\s*", "\n", t)
    return t.strip()


def _wav(pcm: bytes, rate: int = 24000) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(pcm)
    return buf.getvalue()


# ---------------------------------------------------------------- engines
def gemini(text: str, voice: str, speed: float) -> tuple[bytes, str]:
    import keyring
    from google import genai
    from google.genai import types
    key = keyring.get_password("moyo-ai", "gemini_api_key")
    if not key:
        raise TTSError("No Gemini key saved.")
    pace = "at a relaxed, unhurried pace" if speed < 0.95 else "at a lively, slightly quick pace" if speed > 1.05 else "at a natural pace"
    prompt = (f"Read this aloud warmly and naturally, {pace}, like a trusted personal assistant speaking to "
              f"Moyosore. Do not add or change any words:\n\n{text}")
    client = genai.Client(api_key=key, http_options={"api_version": "v1beta", "timeout": 90000})
    cfg = types.GenerateContentConfig(response_modalities=["AUDIO"], speech_config=types.SpeechConfig(
        voice_config=types.VoiceConfig(prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name=voice))))
    last = None
    for m in GEMINI_MODELS:
        try:
            r = client.models.generate_content(model=m, contents=prompt, config=cfg)
            part = r.candidates[0].content.parts[0].inline_data
            mime = (part.mime_type or "").lower()
            if "wav" in mime:
                return part.data, "audio/wav"
            rate = int(re.search(r"rate=(\d+)", mime).group(1)) if "rate=" in mime else 24000
            return _wav(part.data, rate), "audio/wav"
        except Exception as e:  # quota / overload → next model
            last = e
    raise TTSError(f"Gemini voices unavailable ({type(last).__name__}).")


def edge(text: str, voice: str, speed: float) -> tuple[bytes, str]:
    import edge_tts
    rate = f"{round((speed - 1) * 100):+d}%"

    async def run():
        out = bytearray()
        async for chunk in edge_tts.Communicate(text, voice, rate=rate).stream():
            if chunk["type"] == "audio":
                out.extend(chunk["data"])
        return bytes(out)
    try:
        data = asyncio.run(asyncio.wait_for(run(), 60))
    except Exception as e:
        raise TTSError(f"Microsoft voices unavailable ({type(e).__name__}).")
    if not data:
        raise TTSError("Microsoft voices returned no audio.")
    return data, "audio/mpeg"


_kokoro = None
_kokoro_lock = threading.Lock()


def kokoro(text: str, voice: str, speed: float) -> tuple[bytes, str]:
    global _kokoro
    model = KOKORO_DIR / "kokoro-v1.0.int8.onnx"
    voices = KOKORO_DIR / "voices-v1.0.bin"
    if not model.exists() or not voices.exists():
        raise TTSError("Kokoro model files are missing (models/kokoro).")
    import soundfile as sf
    from kokoro_onnx import Kokoro
    with _kokoro_lock:
        if _kokoro is None:
            _kokoro = Kokoro(str(model), str(voices))
        lang = "en-gb" if voice.startswith("b") else "en-us"
        samples, sr = _kokoro.create(text, voice=voice, speed=max(0.5, min(speed, 1.6)), lang=lang)
    buf = io.BytesIO()
    sf.write(buf, samples, sr, format="WAV", subtype="PCM_16")
    return buf.getvalue(), "audio/wav"


ENGINES = {"gemini": gemini, "edge": edge, "kokoro": kokoro}


def synthesize(text: str, engine: str, voice: str, speed: float = 1.0, use_cache: bool = True) -> tuple[bytes, str]:
    if engine not in ENGINES:
        raise TTSError(f"Unknown voice engine {engine}.")
    text = speakable(text)[:5000]
    if not text:
        raise TTSError("Nothing to say.")
    h = hashlib.sha256(f"{engine}|{voice}|{speed}|{text}".encode()).hexdigest()[:32]
    if use_cache:
        for ext, mime in ((".wav", "audio/wav"), (".mp3", "audio/mpeg")):
            p = CACHE / (h + ext)
            if p.exists():
                return p.read_bytes(), mime
    data, mime = ENGINES[engine](text, voice, speed)
    if use_cache:
        CACHE.mkdir(parents=True, exist_ok=True)
        (CACHE / (h + (".mp3" if mime == "audio/mpeg" else ".wav"))).write_bytes(data)
        files = sorted(CACHE.iterdir(), key=lambda p: p.stat().st_mtime)
        for old in files[:-200]:  # keep the cache small
            old.unlink(missing_ok=True)
    return data, mime


def speak_with_fallback(con, text: str) -> tuple[bytes, str, str]:
    """Use the chosen voice; if it fails, fall back through the other natural voices.
    Raises TTSError when everything fails (the browser then uses its basic voice)."""
    pref = get_setting(con, "voice")
    chain = [(pref["engine"], pref["voice"])] if pref["engine"] in ENGINES else []
    if pref.get("fallback", True):
        chain += [c for c in DEFAULT_CHAIN if c[0] != pref["engine"]]
    errors = []
    for eng, voice in chain:
        try:
            data, mime = synthesize(text, eng, voice, float(pref.get("speed", 1.0)))
            return data, mime, f"{eng}:{voice}"
        except TTSError as e:
            errors.append(str(e))
        except Exception as e:  # never let a voice problem break Moyo
            errors.append(f"{eng}: {type(e).__name__}")
    raise TTSError("; ".join(errors) or "No voice engine available.")
