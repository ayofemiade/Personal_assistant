# /// script
# requires-python = ">=3.10,<3.14"
# dependencies = ["sounddevice>=0.5", "numpy>=1.24", "soundfile>=0.12", "soxr>=0.3",
#                 "httpx>=0.27", "keyring>=25", "jiwer>=3.0", "num2words>=0.5"]
# ///
"""Find which microphone capture path gives speech models the cleanest audio.

Records the same sentence through each available input path (Windows MME,
WASAPI, WDM-KS raw array, headset jack…), measures how much of it is wiped to
digital silence, and transcribes each with Groq Whisper.

Run:  uv run --python 3.13 stage0/mic_check.py
Saves clips to stage0/audio/mic_check/ (local; delete whenever).
"""
from __future__ import annotations

import io
import json
import sys
import time
from pathlib import Path

import httpx
import jiwer
import keyring
import numpy as np
import sounddevice as sd
import soundfile as sf
import soxr

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
from phrases import normalise  # noqa: E402

OUT = HERE / "audio" / "mic_check"
SENTENCE = "Move that task to Friday, and log a payment of two hundred thousand naira from Adebayo Ventures."
SECONDS = 7


def candidates():
    seen = []
    for i, d in enumerate(sd.query_devices()):
        if d["max_input_channels"] < 1:
            continue
        api = sd.query_hostapis(d["hostapi"])["name"]
        name = d["name"]
        if any(x in name.lower() for x in ("stereo mix", "sound mapper", "primary sound")):
            continue
        if api == "Windows DirectSound":
            continue  # same signal path as MME
        seen.append((i, api, name, d["max_input_channels"], int(d["default_samplerate"])))
    return seen


def capture(idx, ch, sr, api):
    extra = None
    if api == "Windows WASAPI":
        extra = sd.WasapiSettings(exclusive=False)
    rec = sd.rec(int(SECONDS * sr), samplerate=sr, channels=ch, dtype="float32",
                 device=idx, extra_settings=extra, blocking=True)
    return rec


def groq(wav_bytes, k):
    r = httpx.post("https://api.groq.com/openai/v1/audio/transcriptions",
                   headers={"Authorization": f"Bearer {k}"},
                   files={"file": ("clip.wav", io.BytesIO(wav_bytes), "audio/wav")},
                   data={"model": "whisper-large-v3-turbo", "language": "en", "temperature": "0"},
                   timeout=60)
    r.raise_for_status()
    return r.json().get("text", "").strip()


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    OUT.mkdir(parents=True, exist_ok=True)
    k = keyring.get_password("moyo-ai", "groq_api_key")
    paths = candidates()
    print("Sentence to say each time (same voice, same distance):\n")
    print(f"   \"{SENTENCE}\"\n")
    print("Tip: if you have earphones with a mic, plug them in BEFORE starting so they appear too.\n")
    results = []
    for n, (idx, api, name, ch, sr) in enumerate(paths, 1):
        print(f"[{n}/{len(paths)}] {api} | {name} ({ch} ch, {sr} Hz)")
        if input("   Enter = record 7 s, s = skip: ").strip().lower() == "s":
            continue
        try:
            print("   ● speak now…")
            rec = capture(idx, ch, sr, api)
        except Exception as e:
            print(f"   ✗ could not open this path: {str(e)[:120]}\n")
            continue
        energy = (rec ** 2).mean(axis=0)
        best = int(np.argmax(energy))
        mono = rec[:, best] if energy[best] > 0 else rec.mean(axis=1)
        mono16 = soxr.resample(mono, sr, 16000).astype("float32")
        peak = float(np.abs(mono16).max())
        if peak < 0.01:
            print(f"   ✗ silent on this path (peak {peak:.3f})\n")
            continue
        if peak < 0.3:  # simple gain normalisation for fair comparison
            mono16 = mono16 * (0.5 / peak)
        i16 = (np.clip(mono16, -1, 1) * 32767).astype("<i2")
        zero_pct = float((i16 == 0).mean() * 100)
        buf = io.BytesIO()
        sf.write(buf, i16, 16000, format="WAV", subtype="PCM_16")
        fname = f"{n:02d}_{api.split()[-1]}_{idx}.wav"
        (OUT / fname).write_bytes(buf.getvalue())
        heard, wer = "", None
        if k:
            try:
                heard = groq(buf.getvalue(), k)
                wer = jiwer.wer(normalise(SENTENCE), normalise(heard) or "_")
            except Exception as e:
                heard = f"(groq error: {str(e)[:80]})"
        results.append({"path": f"{api} | {name}", "device_index": idx, "channel": best,
                        "file": fname, "digital_silence_pct": round(zero_pct, 1),
                        "heard": heard, "wer": None if wer is None else round(wer, 3)})
        print(f"   digital silence {zero_pct:.0f}%  |  heard: \"{heard}\"  |  WER {'' if wer is None else f'{wer:.0%}'}\n")
        time.sleep(1)
    (OUT / "results.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
    print("=========== MIC SUMMARY ===========")
    for r in sorted(results, key=lambda r: (r["wer"] if r["wer"] is not None else 9)):
        w = "n/a" if r["wer"] is None else f"{r['wer']:.0%}"
        print(f"WER {w:>5}  silence {r['digital_silence_pct']:>4}%  dev {r['device_index']:>2}  {r['path'][:70]}")


if __name__ == "__main__":
    main()
