# /// script
# requires-python = ">=3.10,<3.14"
# dependencies = [
#   "faster-whisper>=1.0",
#   "av>=11,<19",
#   "sounddevice>=0.5",
#   "numpy>=1.24",
#   "jiwer>=3.0",
# ]
# ///
"""Moyo AI — Stage 0 speech-to-text accuracy test.

Records you reading short Moyo-style commands, then transcribes each one with
several local faster-whisper models and reports word error rate (WER) and speed.

Privacy: audio is held in memory only and is never written to disk.
Run:  uv run --python 3.13 stage0/voice_test.py            (all 30 phrases)
      uv run --python 3.13 stage0/voice_test.py --quick    (first 10 phrases)
Results are written to stage0/voice_test_results.json (text only, no audio).
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path

import jiwer
import numpy as np
import sounddevice as sd

SAMPLE_RATE = 16_000
MODELS = ["base.en", "small.en", "distil-small.en", "medium.en"]

PHRASES = [
    "Moyo, what's my plan for today?",
    "How did yesterday's Instagram video perform?",
    "Which of my tasks is most important?",
    "Add a task to contact that potential client tomorrow.",
    "How much have we generated towards the ten K target?",
    "Open my development workspace.",
    "Let's work on MoyoCode's lead generation.",
    "Remind me what I was doing yesterday.",
    "Move that task to Friday.",
    "Log a payment of two hundred thousand naira from Adebayo Ventures.",
    "Add a new lead called Chukwuemeka Foods, website redesign, five hundred dollars.",
    "Mark the proposal for Oluwaseun as sent.",
    "Remind me to follow up with Tunde on Thursday at ten a.m.",
    "Start coding mode and play my focus playlist.",
    "Pause the music.",
    "Turn the volume down a little.",
    "What's on my Google Calendar this afternoon?",
    "I'm going to the gym, block two hours this evening.",
    "Did I post on TikTok today?",
    "Schedule a LinkedIn post for Wednesday about AI automation for small businesses.",
    "What do you know about me?",
    "Forget the ConvergsAI pricing idea.",
    "Show me my overdue follow-ups.",
    "How much do I need to earn per week to hit the target?",
    "Create a recurring task to publish an Instagram reel every day at seven p.m.",
    "Open Antigravity and the MoyoCode website project.",
    "Take a screenshot.",
    "Read my morning briefing.",
    "Cancel that.",
    "Good night Moyo, let's do the end of day review.",
]


def normalise(text: str) -> str:
    text = text.lower()
    text = re.sub(r"[^a-z0-9' ]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def record_phrase(idx: int, total: int, phrase: str) -> np.ndarray | None:
    print(f"\n[{idx}/{total}]  \"{phrase}\"")
    cmd = input("  Press Enter to START recording (s = skip, q = quit): ").strip().lower()
    if cmd == "q":
        raise KeyboardInterrupt
    if cmd == "s":
        return None
    chunks: list[np.ndarray] = []

    def cb(indata, frames, t, status):  # noqa: ARG001
        chunks.append(indata.copy())

    with sd.InputStream(samplerate=SAMPLE_RATE, channels=1, dtype="float32", callback=cb):
        input("  ● Recording… speak, then press Enter to STOP.")
    audio = np.concatenate(chunks)[:, 0] if chunks else np.zeros(0, dtype=np.float32)
    peak = float(np.max(np.abs(audio))) if audio.size else 0.0
    print(f"  captured {audio.size / SAMPLE_RATE:.1f}s, peak level {peak:.2f}"
          + ("  ⚠ very quiet — move closer to the mic" if peak < 0.05 else ""))
    return audio


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--quick", action="store_true", help="first 10 phrases only")
    ap.add_argument("--models", default=",".join(MODELS))
    args = ap.parse_args()

    phrases = PHRASES[:10] if args.quick else PHRASES
    print("Default input device:", sd.query_devices(kind="input")["name"])
    print("Read each phrase naturally, in your normal voice and pace.")

    recordings: list[tuple[str, np.ndarray]] = []
    try:
        for i, p in enumerate(phrases, 1):
            a = record_phrase(i, len(phrases), p)
            if a is not None and a.size > SAMPLE_RATE * 0.3:
                recordings.append((p, a))
    except KeyboardInterrupt:
        print("\nStopping recording early.")
    if not recordings:
        sys.exit("No recordings captured.")

    from faster_whisper import WhisperModel

    results: dict = {"phrases": len(recordings), "models": {}}
    for name in args.models.split(","):
        print(f"\nLoading {name} (first run downloads it)…")
        model = WhisperModel(name, device="cpu", compute_type="int8")
        refs, hyps, secs, audio_secs = [], [], 0.0, 0.0
        rows = []
        for ref, audio in recordings:
            t0 = time.perf_counter()
            segs, _ = model.transcribe(audio, language="en", beam_size=5, vad_filter=True)
            hyp = " ".join(s.text for s in segs).strip()
            dt = time.perf_counter() - t0
            secs += dt
            audio_secs += audio.size / SAMPLE_RATE
            refs.append(normalise(ref))
            hyps.append(normalise(hyp))
            rows.append({"ref": ref, "hyp": hyp, "wer": round(jiwer.wer(normalise(ref), normalise(hyp) or "_"), 3)})
        wer = jiwer.wer(refs, [h or "_" for h in hyps])
        results["models"][name] = {
            "wer": round(wer, 3),
            "avg_latency_s": round(secs / len(recordings), 2),
            "real_time_factor": round(secs / audio_secs, 2),
            "per_phrase": rows,
        }
        print(f"  {name}: WER {wer:.1%}, avg {secs / len(recordings):.2f}s per phrase")
        worst = sorted(rows, key=lambda r: r["wer"], reverse=True)[:3]
        for r in worst:
            if r["wer"] > 0:
                print(f"    heard: \"{r['hyp']}\"  (expected \"{r['ref']}\")")
        del model

    out = Path(__file__).with_name("voice_test_results.json")
    out.write_text(json.dumps(results, indent=2), encoding="utf-8")
    print(f"\nSaved text-only results to {out}")
    print("\nSummary:")
    for n, m in results["models"].items():
        print(f"  {n:16s} WER {m['wer']:.1%}   {m['avg_latency_s']}s/phrase   RTF {m['real_time_factor']}")


if __name__ == "__main__":
    main()
