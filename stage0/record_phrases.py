# /// script
# requires-python = ">=3.10,<3.14"
# dependencies = ["sounddevice>=0.5", "numpy>=1.24", "soundfile>=0.12", "soxr>=0.3"]
# ///
"""Record the Moyo test phrases and save them as WAV files for engine comparison.

v2: the microphone stays OPEN for the whole session and keeps a 0.6 s pre-roll
buffer. Your laptop mic outputs ~0.5 s of dead silence every time a stream
starts, which was cutting off the first word of every phrase in v1.

Run:  uv run --python 3.13 stage0/record_phrases.py --out stage0/audio_v2 --quick
      (--quick = first 10 phrases; --device N to choose a capture device)
"""
from __future__ import annotations

import argparse
import collections
import json
import sys
import threading
import time
from pathlib import Path

import numpy as np
import sounddevice as sd
import soundfile as sf
import soxr

sys.path.insert(0, str(Path(__file__).parent))
from phrases import PHRASES  # noqa: E402

PREROLL_S = 0.6


class Mic:
    """Always-on input stream with a pre-roll ring buffer."""

    def __init__(self, device=None):
        info = sd.query_devices(device if device is not None else sd.default.device[0], "input")
        self.sr = int(info["default_samplerate"])
        self.ring = collections.deque(maxlen=int(self.sr * PREROLL_S / 1024) + 2)
        self.capture: list[np.ndarray] | None = None
        self.lock = threading.Lock()
        self.stream = sd.InputStream(device=device, samplerate=self.sr, channels=1,
                                     dtype="float32", blocksize=1024, callback=self._cb)
        self.name = info["name"]

    def _cb(self, data, frames, t, status):
        block = data[:, 0].copy()
        with self.lock:
            if self.capture is not None:
                self.capture.append(block)
            else:
                self.ring.append(block)

    def start_take(self):
        with self.lock:
            self.capture = list(self.ring)

    def end_take(self) -> np.ndarray:
        with self.lock:
            blocks, self.capture = self.capture or [], None
        audio = np.concatenate(blocks) if blocks else np.zeros(0, np.float32)
        return soxr.resample(audio, self.sr, 16000).astype("float32")


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(Path(__file__).parent / "audio_v2"))
    ap.add_argument("--quick", action="store_true", help="first 10 phrases only")
    ap.add_argument("--device", type=int, default=None)
    a = ap.parse_args()
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    phrases = PHRASES[:10] if a.quick else PHRASES

    mic = Mic(a.device)
    mic.stream.start()
    print("Microphone:", mic.name, f"({mic.sr} Hz) — warming up…")
    time.sleep(1.5)  # let the mic's start-up silence pass
    print("Ready. The mic stays on until the end; nothing is saved between phrases.\n")

    manifest = []
    try:
        for i, phrase in enumerate(phrases, 1):
            while True:
                print(f"[{i}/{len(phrases)}]  \"{phrase}\"")
                cmd = input("  Enter = record, s = skip, q = quit: ").strip().lower()
                if cmd in ("q", "s"):
                    break
                mic.start_take()
                input("  ● Recording… speak, then press Enter to STOP.")
                time.sleep(0.25)  # catch the tail of the last word
                audio = mic.end_take()
                peak = float(np.abs(audio).max()) if audio.size else 0.0
                if audio.size < 16000 * 0.8 or peak < 0.03:
                    print(f"  ⚠ too short or silent (peak {peak:.2f}), let's redo that one.\n")
                    continue
                path = out / f"{i:02d}.wav"
                sf.write(path, audio, 16000, subtype="PCM_16")
                manifest.append({"id": i, "file": path.name, "text": phrase})
                print(f"  ✓ saved {audio.size / 16000:.1f}s (peak {peak:.2f})\n")
                break
            if cmd == "q":
                break
    finally:
        mic.stream.stop()
        mic.stream.close()
        print("Microphone closed.")
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(f"Saved {len(manifest)} recordings to {out}")


if __name__ == "__main__":
    main()
