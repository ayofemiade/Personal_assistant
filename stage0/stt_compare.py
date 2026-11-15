# /// script
# requires-python = ">=3.10,<3.14"
# dependencies = [
#   "faster-whisper>=1.1",
#   "av>=11,<19",
#   "numpy>=1.24",
#   "soundfile>=0.12",
#   "jiwer>=3.0",
#   "num2words>=0.5",
#   "keyring>=25",
#   "google-genai>=1.0",
#   "httpx>=0.27",
# ]
# ///
"""Compare speech engines on the SAME saved recordings (stage0/audio/).

Engines:
  local:<model>  faster-whisper on CPU (e.g. local:small.en, local:large-v3-turbo)
  gemini         Gemini Flash transcription (free tier, key from Credential Manager)
  live           Gemini Live native-audio: transcribes your speech AND measures
                 time-to-first-spoken-reply (the real voice-assistant experience)
  groq           Groq Whisper-large-v3-turbo (free tier, needs groq key)

Run:  uv run --python 3.13 stage0/stt_compare.py                    (all available)
      uv run --python 3.13 stage0/stt_compare.py --engines gemini,live
      uv run --python 3.13 stage0/stt_compare.py --list-models      (show Gemini models)
Results: stage0/stt_results.json (text only).
"""
from __future__ import annotations

import argparse
import asyncio
import io
import json
import os
import sys
import time
from pathlib import Path

import jiwer
import keyring
import numpy as np
import soundfile as sf

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
from phrases import normalise  # noqa: E402

AUDIO = Path(os.environ.get("MOYO_AUDIO_DIR", HERE / "audio"))
SR = 16_000
STT_PROMPT = ("Transcribe this English speech exactly as spoken, word for word. "
              "Output only the transcript, nothing else.")


def key(name: str) -> str | None:
    try:
        return keyring.get_password("moyo-ai", name)
    except Exception:
        return None


def load_set() -> list[dict]:
    mf = AUDIO / "manifest.json"
    if not mf.exists():
        sys.exit("No recordings yet. Run: uv run --python 3.13 stage0/record_phrases.py")
    items = json.loads(mf.read_text(encoding="utf-8-sig"))
    for it in items:
        audio, sr = sf.read(AUDIO / it["file"], dtype="float32")
        assert sr == SR
        it["audio"] = audio
        it["wav"] = (AUDIO / it["file"]).read_bytes()
    return items


# ---------------------------------------------------------------- engines
def run_local(model_name: str, items):
    from faster_whisper import WhisperModel
    m = WhisperModel(model_name, device="cpu", compute_type="int8")
    out = []
    for it in items:
        t = time.perf_counter()
        segs, _ = m.transcribe(it["audio"], language="en", beam_size=5, vad_filter=True,
                               condition_on_previous_text=False)
        out.append(({"text": " ".join(s.text for s in segs).strip()}, time.perf_counter() - t))
    return out


def gemini_client():
    k = key("gemini_api_key")
    if not k:
        return None
    from google import genai
    # Live API on the free tier only answers on v1beta; the SDK default returns HTTP 404.
    return genai.Client(api_key=k, http_options={"api_version": "v1beta"})


def pick_model(client, want: str, live: bool) -> str:
    names = []
    for m in client.models.list():
        acts = getattr(m, "supported_actions", None) or []
        name = m.name.removeprefix("models/")
        if live and "bidiGenerateContent" in acts:
            names.append(name)
        if not live and "generateContent" in acts and "flash" in name and not any(
                x in name for x in ("live", "tts", "image", "audio", "embedding")):
            names.append(name)
    if want and want in names:
        return want
    if want and not names:
        return want
    pref = ["native-audio", "flash-live", "live"] if live else ["flash-latest", "flash-lite", "flash"]
    for p in pref:
        for n in names:
            if p in n:
                return n
    return want or names[0]


def call_with_retry(fn, tries=4):
    for i in range(tries):
        try:
            return fn()
        except Exception as e:  # rate limit / transient
            msg = str(e)
            if i < tries - 1 and any(c in msg for c in ("429", "RESOURCE_EXHAUSTED", "503", "UNAVAILABLE")):
                time.sleep(15 * (i + 1))
                continue
            raise


def run_gemini(items, model):
    from google.genai import types
    client = gemini_client()
    out = []
    for it in items:
        t = time.perf_counter()
        r = call_with_retry(lambda: client.models.generate_content(
            model=model,
            contents=[STT_PROMPT, types.Part.from_bytes(data=it["wav"], mime_type="audio/wav")]))
        out.append(({"text": (r.text or "").strip()}, time.perf_counter() - t))
        time.sleep(4)  # stay well under free-tier per-minute limits
    return out


async def _live_one(client, model, audio: np.ndarray):
    from google.genai import types
    pcm = (np.clip(audio, -1, 1) * 32767).astype("<i2")
    pcm = np.concatenate([pcm, np.zeros(SR, dtype="<i2")])  # 1 s trailing silence for end-of-speech
    config = {
        "response_modalities": ["AUDIO"],
        "input_audio_transcription": {},
        "output_audio_transcription": {},
        "system_instruction": "You are Moyo, a personal assistant. Reply in one short spoken sentence. "
                              "Do not take any action; this is a test.",
    }
    heard, reply = [], []
    t_end = first_audio = None
    async with client.aio.live.connect(model=model, config=config) as session:
        step = SR // 10  # 100 ms chunks
        for i in range(0, len(pcm), step):
            await session.send_realtime_input(
                audio=types.Blob(data=pcm[i:i + step].tobytes(), mime_type="audio/pcm;rate=16000"))
            await asyncio.sleep(0.1)  # real-time pacing, like a live mic
        t_end = time.perf_counter()
        await session.send_realtime_input(audio_stream_end=True)
        async for msg in session.receive():
            sc = msg.server_content
            if not sc:
                continue
            if sc.input_transcription and sc.input_transcription.text:
                heard.append(sc.input_transcription.text)
            if sc.output_transcription and sc.output_transcription.text:
                reply.append(sc.output_transcription.text)
            if sc.model_turn and first_audio is None:
                if any(p.inline_data for p in sc.model_turn.parts or []):
                    first_audio = time.perf_counter()
            if sc.turn_complete:
                break
    latency = (first_audio - t_end) if first_audio else None
    return {"text": "".join(heard).strip(), "reply": "".join(reply).strip(),
            "first_reply_audio_s": round(latency, 2) if latency is not None else None}


def run_live(items, model):
    client = gemini_client()
    out = []
    for it in items:
        t = time.perf_counter()
        try:
            res = asyncio.run(asyncio.wait_for(_live_one(client, model, it["audio"]), timeout=60))
        except Exception as e:
            res = {"text": "", "error": f"{type(e).__name__}: {e}"[:200]}
        out.append((res, time.perf_counter() - t))
        time.sleep(2)
    return out


def run_groq(items, model="whisper-large-v3-turbo"):
    import httpx
    k = key("groq_api_key")
    out = []
    for it in items:
        t = time.perf_counter()
        r = call_with_retry(lambda: httpx.post(
            "https://api.groq.com/openai/v1/audio/transcriptions",
            headers={"Authorization": f"Bearer {k}"},
            files={"file": (it["file"], io.BytesIO(it["wav"]), "audio/wav")},
            data={"model": model, "language": "en", "response_format": "json", "temperature": "0"},
            timeout=60).raise_for_status())
        out.append(({"text": r.json().get("text", "").strip()}, time.perf_counter() - t))
        time.sleep(3.5)  # free tier ~20 req/min
    return out


# ---------------------------------------------------------------- main
def score(name, items, results):
    refs = [normalise(it["text"]) for it in items]
    hyps = [normalise(r[0].get("text", "")) or "_" for r in results]
    rows = []
    for it, (res, secs), ref, hyp in zip(items, results, refs, hyps):
        rows.append({"id": it["id"], "expected": it["text"], "heard": res.get("text", ""),
                     "wer": round(jiwer.wer(ref, hyp), 3), "seconds": round(secs, 2),
                     **{k: v for k, v in res.items() if k not in ("text",)}})
    exact = sum(1 for r in rows if r["wer"] == 0)
    summary = {"wer": round(jiwer.wer(refs, hyps), 3), "exact_phrases": f"{exact}/{len(rows)}",
               "avg_seconds": round(sum(r["seconds"] for r in rows) / len(rows), 2)}
    lat = [r["first_reply_audio_s"] for r in rows if r.get("first_reply_audio_s") is not None]
    if lat:
        summary["avg_time_to_spoken_reply_s"] = round(sum(lat) / len(lat), 2)
    errs = [r for r in rows if r.get("error")]
    if errs:
        summary["errors"] = len(errs)
        summary["first_error"] = errs[0]["error"]
    return summary, rows


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser()
    ap.add_argument("--engines", default="local:small.en,local:large-v3-turbo,gemini,live,groq")
    ap.add_argument("--gemini-model", default="gemini-3.5-flash")
    ap.add_argument("--live-model", default="gemini-3.1-flash-live-preview")
    ap.add_argument("--list-models", action="store_true")
    ap.add_argument("--limit", type=int, default=0, help="only the first N recordings")
    ap.add_argument("--audio-dir", default=None, help="folder of recordings (default stage0/audio)")
    a = ap.parse_args()
    global AUDIO
    if a.audio_dir:
        AUDIO = Path(a.audio_dir)

    if a.list_models:
        c = gemini_client() or sys.exit("No Gemini key saved. Run: uv run stage0/set_key.py gemini")
        for m in c.models.list():
            print(m.name, getattr(m, "supported_actions", ""))
        return

    items = load_set()
    if a.limit:
        items = items[:a.limit]
    print(f"{len(items)} recordings loaded.\n")
    report = {}
    for eng in a.engines.split(","):
        eng = eng.strip()
        try:
            if eng.startswith("local:"):
                label = eng
                print(f"→ {label} (first run downloads the model)…")
                res = run_local(eng.split(":", 1)[1], items)
            elif eng in ("gemini", "live"):
                c = gemini_client()
                if not c:
                    print(f"→ {eng}: skipped (no Gemini key; run: uv run stage0/set_key.py gemini)")
                    continue
                model = pick_model(c, a.live_model if eng == "live" else a.gemini_model, eng == "live")
                label = f"{eng}:{model}"
                print(f"→ {label}…")
                res = run_live(items, model) if eng == "live" else run_gemini(items, model)
            elif eng == "groq":
                if not key("groq_api_key"):
                    print("→ groq: skipped (no Groq key; run: uv run stage0/set_key.py groq)")
                    continue
                label = "groq:whisper-large-v3-turbo"
                print(f"→ {label}…")
                res = run_groq(items)
            else:
                print(f"→ unknown engine {eng}, skipped")
                continue
        except Exception as e:
            print(f"   FAILED: {type(e).__name__}: {str(e)[:300]}")
            continue
        summary, rows = score(label, items, res)
        report[label] = {"summary": summary, "rows": rows}
        print(f"   {summary}")
        for r in sorted(rows, key=lambda r: -r["wer"])[:3]:
            if r["wer"] > 0:
                print(f"     heard \"{r['heard']}\"  (expected \"{r['expected']}\")")
        if not a.limit:  # don't overwrite full results with a partial trial
            prev = {}
            p = HERE / "stt_results.json"
            if p.exists():
                prev = json.loads(p.read_text(encoding="utf-8"))
            prev.update(report)
            p.write_text(json.dumps(prev, indent=2), encoding="utf-8")

    print("\n=========== SUMMARY ===========")
    for label, d in report.items():
        s = d["summary"]
        extra = f"  spoken reply after {s['avg_time_to_spoken_reply_s']}s" if "avg_time_to_spoken_reply_s" in s else ""
        print(f"{label:45s} WER {s['wer']:.1%}  exact {s['exact_phrases']}  {s['avg_seconds']}s/phrase{extra}")
    print("\nFull text results: stage0/stt_results.json")


if __name__ == "__main__":
    main()
