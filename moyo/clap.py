"""Double-clap wake detector (local DSP, no AI, no recording).

A clap is a sudden, loud, broadband burst that decays within ~0.1 s. We look at 10 ms frames:
  level  : frame loudness (dBFS)
  rise   : how far above the recent background (dB) the frame jumps
  bright : RMS of the first difference / RMS of the signal. ~1.4 for hiss/clicks (claps), ~0.2–0.6 for voiced speech
A "double clap" = two confirmed clap onsets 150–700 ms apart, a quiet-ish lead-in, and no third onset right after
(so applause, typing bursts and music are rejected). Audio lives only in a small in-memory ring buffer.
"""
from __future__ import annotations

import json
import queue
import sys
import threading
import time
from collections import deque
from dataclasses import asdict, dataclass

import numpy as np

SR = 16_000
FRAME = 160  # 10 ms
FLOOR_DB = -90.0


@dataclass
class Params:
    min_db: float = -32.0       # onset must be at least this loud
    rise_db: float = 16.0       # ...and this much above the recent background
    bright_min: float = 0.85    # ...and this "bright" (broadband)
    decay_db: float = 10.0      # must fall by this much...
    decay_ms: int = 160         # ...within this time
    gap_min_ms: int = 150       # between the two claps
    gap_max_ms: int = 700
    after_ms: int = 600         # no third onset in this window
    cooldown_s: float = 8.0
    refractory_ms: int = 80     # ignore new onsets this soon after one (some mics add an echo ~110 ms later)
    quiet_after_ms: int = 0     # >0: a clap must be followed by this much near-quiet (talking isn't)...
    quiet_start_ms: int = 120   # ...starting this long after the clap (skips the mic's echo)...
    quiet_drop_db: float = 12.0 # ...meaning at least this far below the clap's peak


def frame_features(x: np.ndarray) -> tuple[float, float]:
    rms = float(np.sqrt(np.mean(x * x)))
    level = max(20 * np.log10(rms + 1e-12), FLOOR_DB)
    d = np.diff(x)
    bright = float(np.sqrt(np.mean(d * d)) / (rms + 1e-9)) if rms > 1e-6 else 0.0
    return level, bright


class Detector:
    """Feed 10 ms frames; returns True on a confirmed double clap."""

    def __init__(self, p: Params | None = None):
        self.p = p or Params()
        self.t = 0                     # frame index
        self.hist: deque[float] = deque(maxlen=30)   # 300 ms background
        self.pending = None            # onset waiting for decay confirmation: (t, level)
        self.onsets: list[int] = []    # confirmed onset frame indices
        self.last_trigger = -10**9
        self.events: list[dict] = []   # for calibration/diagnostics
        self.settling = None           # confirmed onset waiting for its quiet-after check: (t0, peak, event)

    def _bg(self) -> float:
        return float(np.median(self.hist)) if self.hist else FLOOR_DB

    def feed(self, frame: np.ndarray) -> bool:
        p, t = self.p, self.t
        level, bright = frame_features(frame)
        bg = self._bg()
        fired = False
        # 1) confirm a pending onset once it has decayed fast enough (clap-like), or drop it
        if self.pending:
            t0, l0, b0, r0 = self.pending
            if level > l0 and (t - t0) <= 3:  # still rising (a clap rarely starts on a frame edge): track the peak
                self.pending = (t0, level, b0, r0 + level - l0)
                l0 = level
            elif level <= l0 - p.decay_db:
                ev = {"t": t0 * 10, "level": round(l0, 1), "bright": round(b0, 2), "rise": round(r0, 1)}
                if p.quiet_after_ms:
                    self.settling = (t0, l0, ev)
                else:
                    self.onsets.append(t0)
                    self.events.append(ev)
                self.pending = None
            elif (t - t0) * 10 > p.decay_ms:
                self.pending = None  # too sustained: speech/music, not a clap
        # 1b) quiet-after check: a clap is an isolated burst; speech keeps going syllable after syllable
        elif self.settling:
            t0, pk, ev = self.settling
            since = (t - t0) * 10
            if since >= p.quiet_start_ms and level > pk - p.quiet_drop_db:
                self.settling = None                      # sound continued: talking, not a clap
            elif since >= p.quiet_start_ms + p.quiet_after_ms:
                self.onsets.append(t0)
                self.events.append(ev)
                self.settling = None
        # 2) new onset candidate
        elif level >= p.min_db and level - bg >= p.rise_db and bright >= p.bright_min \
                and (not self.onsets or (t - self.onsets[-1]) * 10 > p.refractory_ms):
            self.pending = (t, level, bright, level - bg)
        # 3) double-clap logic: evaluate once the latest onset has settled (no follow-up within after_ms)
        self.onsets = [o for o in self.onsets if (t - o) * 10 <= 3000]   # remember the last 3 s
        if len(self.onsets) >= 2 and (t - self.onsets[-1]) * 10 >= p.after_ms:
            a, b = self.onsets[-2], self.onsets[-1]
            gap = (b - a) * 10
            lead_in_clear = not [o for o in self.onsets[:-2] if (a - o) * 10 < 800]  # nothing just before: not applause
            if p.gap_min_ms <= gap <= p.gap_max_ms and lead_in_clear and (t - self.last_trigger) * 10 >= p.cooldown_s * 1000:
                fired = True
                self.last_trigger = t
            self.onsets = []
        elif len(self.onsets) == 1 and (t - self.onsets[-1]) * 10 >= p.gap_max_ms + p.after_ms:
            self.onsets = []  # lone clap expired
        self.hist.append(level)
        self.t += 1
        return fired


def analyze(signal: np.ndarray, p: Params | None = None) -> tuple[list[int], list[dict]]:
    """Offline: returns (trigger times in ms, onset events)."""
    d = Detector(p)
    triggers = []
    n = len(signal) // FRAME
    for i in range(n):
        if d.feed(signal[i * FRAME:(i + 1) * FRAME]):
            triggers.append(i * 10)
    # flush so a final double clap is evaluated
    silence = np.zeros(FRAME, dtype=np.float32)
    for j in range(int((d.p.after_ms + 50) / 10)):
        if d.feed(silence):
            triggers.append((n + j) * 10)
    return triggers, d.events


# ---------------------------------------------------------------- wake phrase (offline, Vosk)
from pathlib import Path  # noqa: E402

MODEL_DIR = Path(__file__).resolve().parent.parent / "models" / "vosk-model-small-en-us-0.15"
WAKE_PHRASE = "let's get to work"
# The recogniser may only choose between these (or [unk]); that keeps it accurate and stops it hearing anything else.
# Everyday words give normal talk somewhere else to go, so it isn't squeezed into the wake phrase.
EVERYDAY = ("i you we he she it they me my your our us them this that these what who where when why how which "
            "is are was were be been am do does did have has had will would can could should may might must "
            "go going went come coming get got getting give take make made know think want need like see look "
            "say said tell talk call send check try put keep let lets start stop finish done "
            "a an the and but or so if then because not no yes yeah okay ok right well just really very too also "
            "now today tomorrow yesterday later morning night time day week minute hour first last next "
            "here there in on at to for from with about up down out of off over back home office gym "
            "water food eat drink money phone email message meeting project client video post "
            "good bad great nice fine sure thanks thank please hello hi bye one two three some more all").split()
WAKE_GRAMMAR = ["lets get to work", "let us get to work", "lets get work", "lets get started", "let us get started",
                *EVERYDAY, "[unk]"]
STALE_S = 6  # seconds without any audio from the mic before the listener reconnects (sleep/resume)


def _wlog(msg: str) -> None:
    try:
        from datetime import datetime as _dt

        from moyo.db import DATA_DIR
        with open(DATA_DIR / "voice.log", "a", encoding="utf-8") as f:
            f.write(f"{_dt.now().isoformat(timespec='milliseconds')} wake: {msg}\n")
    except Exception:
        pass
# This laptop's mic dulls claps (brightness ~0.1-0.5) and adds an echo ~110 ms later, so in phrase mode the clap
# check is deliberately loose: a clap only opens a short listening window; the phrase decides.
PHRASE_PARAMS = Params(min_db=-42.0, rise_db=12.0, bright_min=0.0, decay_db=8.0, decay_ms=300,
                       refractory_ms=200, cooldown_s=8.0, quiet_after_ms=180, quiet_start_ms=120, quiet_drop_db=12.0)
WINDOW_S = 6.0      # listen for the phrase this long after a clap
PREROLL_S = 1.0     # ...including this much audio from just before (so the first word isn't cut off)


def phrase_matches(text: str) -> bool:
    import re  # "to" is often swallowed when said quickly ("let's get-work"), so it's optional
    return bool(re.search(r"\blet(s| us) get ((to )?work|started)\b", text or ""))


class PhraseSpotter:
    def __init__(self, model_dir: Path = MODEL_DIR):
        import vosk
        if not Path(model_dir).exists():
            raise FileNotFoundError(f"Speech model missing: {model_dir}")
        vosk.SetLogLevel(-1)
        self.model = vosk.Model(str(model_dir))

    def recognizer(self):
        import vosk
        return vosk.KaldiRecognizer(self.model, SR, json.dumps(WAKE_GRAMMAR))

    def check(self, sig: np.ndarray) -> str:
        """Offline helper (tests): returns what was recognised in a 16 kHz float signal."""
        r = self.recognizer()
        r.AcceptWaveform(_pcm16(sig))
        return json.loads(r.FinalResult()).get("text", "")


# Answers to "Want to see your full dashboard?" (the orb listens for these after it asks).
ANSWER_GRAMMAR = ["open my dashboard", "open the dashboard", "open dashboard", "show me the dashboard", "show my dashboard",
                  "yes", "yes please", "yeah", "sure", "okay", "go ahead",
                  "start my day", "start the day",
                  "later", "not now", "no", "no thanks", "close", "maybe later",
                  "lets talk", "talk to me", "i have a question", "can we talk",
                  "[unk]"]


def answer_intent(text: str) -> str | None:
    """'open' | 'start_day' | 'later' | 'talk' | None, from a recognised answer."""
    t = f" {(text or '').replace('[unk]', ' ')} "
    if "start my day" in t or "start the day" in t:
        return "start_day"
    if any(w in t for w in (" lets talk ", " talk to me ", " have a question ", " can we talk ")):
        return "talk"
    if any(w in t for w in (" later ", " not now ", " no ", " no thanks ", " close ")):
        return "later"
    if "dashboard" in t or any(w in t for w in (" yes ", " yeah ", " sure ", " okay ", " go ahead ")):
        return "open"
    return None


def answer_recognizer(spotter: "PhraseSpotter"):
    import vosk
    return vosk.KaldiRecognizer(spotter.model, SR, json.dumps(ANSWER_GRAMMAR))


def _pcm16(x: np.ndarray) -> bytes:
    return (np.clip(x, -1, 1) * 32767).astype("<i2").tobytes()


# ---------------------------------------------------------------- live listener
class Listener:
    """Background mic listener. Audio lives only in memory and is never stored.

    mode "double_clap": wake on a double clap.
    mode "clap_phrase": any clap opens a 4.5 s window; wake only if "let's get to work" is heard in it.
    """

    def __init__(self, params: Params, on_wake, device=None, mode: str = "double_clap",
                 spotter: PhraseSpotter | None = None, sync: bool = False):
        self.params, self.on_wake, self.device, self.mode = params, on_wake, device, mode
        self.spotter, self.sync = spotter, sync
        self.det = Detector(params)
        self.stream = None
        self.paused = False
        self.error = None
        self.started_at = None
        self.last_wake = None
        self.last_heard = None          # last phrase-window result (diagnostics, never audio)
        self.windows = 0
        self.heard_log: list[str] = []  # what each window heard (text only), newest last
        self.last_audio: float | None = None  # when the mic last delivered sound (sleep/resume watchdog)
        self.reconnects = 0
        self._watching = False
        self._stop_evt = threading.Event()
        self._buf = np.zeros(0, dtype=np.float32)
        self._lock = threading.Lock()
        self._ring: deque[np.ndarray] = deque(maxlen=int(PREROLL_S * 100))
        self._win_left = 0              # frames left in the current phrase window
        self._rec = None
        self._q: "queue.Queue | None" = None
        self._last_wake_frame = -10**9

    # -- frame processing (shared by the live stream and tests)
    def process(self, chunk: np.ndarray) -> None:
        with self._lock:
            self._buf = np.concatenate([self._buf, chunk])
            while len(self._buf) >= FRAME:
                fr, self._buf = self._buf[:FRAME], self._buf[FRAME:]
                self._frame(fr)

    def _frame(self, fr: np.ndarray) -> None:
        n_events = len(self.det.events)
        fired = self.det.feed(fr)
        if self.mode != "clap_phrase":
            if fired:
                self._wake()
            return
        self._ring.append(fr)
        if self._win_left > 0:
            self._send(("frame", fr))
            self._win_left -= 1
            if self._win_left == 0:
                self._send(("end", None))
        elif len(self.det.events) > n_events and \
                (self.det.t - self._last_wake_frame) * 10 >= self.params.cooldown_s * 1000:
            self.windows += 1
            self._send(("start", list(self._ring)))
            self._win_left = int(WINDOW_S * 100)

    def _send(self, item) -> None:
        if self.sync:
            self._handle(item)
        elif self._q is not None:
            self._q.put(item)

    def _handle(self, item) -> None:
        kind, val = item
        if kind == "start":
            self._rec = self.spotter.recognizer()
            self._rec.AcceptWaveform(_pcm16(np.concatenate(val)))
        elif kind == "frame" and self._rec is not None:
            if self._rec.AcceptWaveform(_pcm16(val)):
                self._judge(json.loads(self._rec.Result()).get("text", ""))
        elif kind == "end" and self._rec is not None:
            self._judge(json.loads(self._rec.FinalResult()).get("text", ""), final=True)

    def _judge(self, text: str, final: bool = False) -> None:
        if text:
            self.last_heard = text
        if final or phrase_matches(text):
            self.heard_log = (self.heard_log + [text or "(nothing)"])[-20:]
        if phrase_matches(text):
            self._rec = None
            self._win_left = 0
            self._last_wake_frame = self.det.t
            self._wake()
        elif final:
            self._rec = None

    def _worker(self) -> None:
        while self._q is not None:
            try:
                item = self._q.get(timeout=0.5)
            except queue.Empty:
                continue
            try:
                self._handle(item)
            except Exception as e:
                self.error = f"{type(e).__name__}: {e}"

    def _wake(self) -> None:
        self.last_wake = time.time()
        if self.sync:
            self.on_wake()
        else:
            threading.Thread(target=self.on_wake, daemon=True).start()

    def _cb(self, data, frames, t, status):
        self.last_audio = time.time()
        if not self.paused:
            self.process(data[:, 0].copy())

    def _open_stream(self) -> None:
        import sounddevice as sd
        self.stream = sd.InputStream(samplerate=SR, channels=1, dtype="float32", blocksize=FRAME * 4,
                                     device=self.device, callback=self._cb)
        self.stream.start()
        self.last_audio = time.time()

    def _close_stream(self) -> None:
        s, self.stream = self.stream, None
        if s:
            try:
                s.stop(); s.close()
            except Exception:
                pass

    def start(self):
        try:
            if self.mode == "clap_phrase" and self.spotter is None:
                self.spotter = PhraseSpotter()
            self._q = queue.Queue()
            threading.Thread(target=self._worker, daemon=True).start()
            self._open_stream()
            self.started_at = time.time()
            self.error = None
        except Exception as e:
            self.error = f"{type(e).__name__}: {e}"
            self.stream = None
        self._watching = True
        self._stop_evt.clear()
        self._wd = threading.Thread(target=self._watchdog, daemon=True)
        self._wd.start()

    def _watchdog(self) -> None:
        """After Modern Standby / lid close, Windows can leave the mic stream 'active' but silent forever.
        If no audio arrives for STALE_S, reopen the device (and keep retrying if it isn't back yet)."""
        import sounddevice as sd
        while self._watching:
            if self._stop_evt.wait(2) or not self._watching:  # stop() wakes us at once
                return
            stale = time.time() - (self.last_audio or 0) > STALE_S
            if self.stream is not None and not stale:
                continue
            try:
                self._close_stream()
                sd._terminate(); sd._initialize()  # re-scan devices: the mic may have re-enumerated after resume
                self._open_stream()
                self.error = None
                self.reconnects += 1
                _wlog(f"mic reconnected (#{self.reconnects}) after no audio")
            except Exception as e:
                self.error = f"{type(e).__name__}: {e}"
                if self._stop_evt.wait(3):
                    return

    def stop(self):
        self._watching = False
        self._stop_evt.set()
        wd = getattr(self, "_wd", None)
        if wd and wd is not threading.current_thread():
            wd.join(timeout=5)  # no stray watchdog may touch the audio device after stop
        self._close_stream()
        self._q = None

    @property
    def running(self) -> bool:
        return bool(self.stream and self.stream.active)


# ---------------------------------------------------------------- calibration (run in a terminal)
PHASES = [
    ("quiet", 5, "Stay quiet for 5 seconds (normal room noise is fine)."),
    ("claps", 18, "CLAP TWICE, like a quick 'clap-clap', 4 times, with a 3-second pause between each pair."),
    ("noise", 12, "Now the usual noises: type on the keyboard, tap or knock on the desk, put a cup down."),
    ("speech", 10, "Now talk normally for 10 seconds, e.g. read this sentence out loud a few times."),
]


def _record(seconds: float) -> np.ndarray:
    import sounddevice as sd
    chunks = []
    with sd.InputStream(samplerate=SR, channels=1, dtype="float32", blocksize=FRAME * 4,
                        callback=lambda d, f, t, s: chunks.append(d[:, 0].copy())):
        time.sleep(1.0)        # let the mic's start-up silence pass (this laptop: ~0.5 s)
        chunks.clear()
        time.sleep(seconds)
    return np.concatenate(chunks) if chunks else np.zeros(0, np.float32)


def calibrate() -> dict:
    """Guided calibration. Prints results and returns tuned Params (as dict). Audio is discarded."""
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    loose = Params(min_db=-55, rise_db=8, bright_min=0.4, decay_db=6, decay_ms=200)
    feats = {}
    print("Moyo clap calibration. Nothing is saved except the tuned numbers.\n")
    for name, secs, text in PHASES:
        input(f"\n{text}\n  Press Enter to start ({secs}s)…")
        print("  ● listening…")
        sig = _record(secs)
        _, ev = analyze(sig, loose)
        feats[name] = ev
        print(f"  heard {len(ev)} sharp sound(s)")
    claps = feats["claps"]
    if len(claps) < 4:
        print("\nI heard fewer than 4 claps. Clap a bit louder or closer to the laptop and run calibration again.")
        return {}
    lv = np.array([e["level"] for e in claps]); br = np.array([e["bright"] for e in claps]); rs = np.array([e["rise"] for e in claps])
    # thresholds: just under the quieter claps, but above what the noise/speech phases produced
    p = Params(min_db=float(np.percentile(lv, 15) - 4), rise_db=float(max(10, np.percentile(rs, 15) - 4)),
               bright_min=float(max(0.6, np.percentile(br, 15) * 0.9)))
    others = feats["noise"] + feats["speech"] + feats["quiet"]
    fp = [e for e in others if e["level"] >= p.min_db and e["rise"] >= p.rise_db and e["bright"] >= p.bright_min]
    print(f"\nYour claps: loudness {lv.min():.0f}…{lv.max():.0f} dB, brightness {br.min():.2f}…{br.max():.2f}")
    print(f"Chosen thresholds: loudness ≥ {p.min_db:.0f} dB, jump ≥ {p.rise_db:.0f} dB, brightness ≥ {p.bright_min:.2f}")
    print(f"Other sounds that would pass as single claps: {len(fp)} (a double clap needs two in the right rhythm)")
    print("\nNow a final check: clap twice when ready (10 s).")
    input("  Press Enter to start…")
    trig, _ = analyze(_record(10), p)
    print(f"  {'✓ Double clap detected!' if trig else '✗ Not detected. Try clapping a bit closer, or run calibration again.'}")
    return asdict(p) | {"calibrated": bool(trig), "false_single_claps": len(fp)}


CUES = (2.0, 6.0, 10.0)  # seconds into the recording when the diagnostic asks for a double clap


def _record_with_cues(seconds: float, cues=CUES) -> np.ndarray:
    import sounddevice as sd
    chunks = []
    with sd.InputStream(samplerate=SR, channels=1, dtype="float32", blocksize=FRAME * 4,
                        callback=lambda d, f, t, s: chunks.append(d[:, 0].copy())):
        time.sleep(1.0)
        chunks.clear()
        t0 = time.time()
        for c in cues:
            while time.time() - t0 < c - 1.0:
                time.sleep(0.02)
            print("  get ready…", flush=True)
            while time.time() - t0 < c:
                time.sleep(0.005)
            print("  >>> CLAP-CLAP NOW <<<", flush=True)
        while time.time() - t0 < seconds:
            time.sleep(0.02)
    return np.concatenate(chunks) if chunks else np.zeros(0, np.float32)


def peaks(sig: np.ndarray, min_level=-60.0, min_jump=8.0) -> list[dict]:
    n = len(sig) // FRAME
    feats = [frame_features(sig[i * FRAME:(i + 1) * FRAME]) for i in range(n)]
    lv = np.array([f[0] for f in feats]); br = np.array([f[1] for f in feats])
    out, i = [], 30
    while i < n:
        bg = float(np.median(lv[i - 30:i]))
        if lv[i] >= min_level and lv[i] - bg >= min_jump:
            pk = i + int(np.argmax(lv[i:i + 5]))
            fall = next(((k - pk) * 10 for k in range(pk + 1, min(n, pk + 60)) if lv[k] <= lv[pk] - 10), 600)
            out.append({"t": i * 10, "level": round(float(lv[pk]), 1), "jump": round(float(lv[pk] - bg), 1),
                        "bright": round(float(max(br[i], br[pk])), 2), "fall10_ms": fall})
            i = pk + 5
        else:
            i += 1
    return out, lv


def _to16k(x: np.ndarray, sr: float) -> np.ndarray:
    if int(sr) == SR:
        return x.astype(np.float32)
    k = max(1, int(round(sr / SR)))
    if k > 1:  # crude low-pass before resampling
        x = np.convolve(x, np.ones(k) / k, mode="same")
    n = int(len(x) * SR / sr)
    return np.interp(np.arange(n) * sr / SR, np.arange(len(x)), x).astype(np.float32)


def input_sources() -> list[dict]:
    """The default mic path plus the raw WASAPI array (if present)."""
    import sounddevice as sd
    out = [{"name": "default (Windows mic path)", "device": None, "channels": 1, "sr": SR}]
    for i, d in enumerate(sd.query_devices()):
        if d["max_input_channels"] > 0 and sd.query_hostapis(d["hostapi"])["name"] == "Windows WASAPI":
            out.append({"name": f"WASAPI #{i}", "device": i, "channels": d["max_input_channels"],
                        "sr": int(d["default_samplerate"])})
    return out


def compare(seconds: float = 13.0) -> None:
    """Guided double claps recorded through every mic path at once; prints how well claps stand out on each."""
    import contextlib

    import sounddevice as sd
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    srcs = input_sources()
    print("Moyo mic comparison. Only numbers are printed; nothing is saved.\n")
    print("Stay quiet, and double-clap ONLY when you see CLAP-CLAP NOW (3 times).")
    input("  Press Enter to start…")
    bufs = {i: [] for i in range(len(srcs))}
    errors = {}
    with contextlib.ExitStack() as st:
        for i, s in enumerate(srcs):
            try:
                st.enter_context(sd.InputStream(samplerate=s["sr"], channels=s["channels"], dtype="float32",
                                                device=s["device"], callback=lambda d, f, t, x, i=i: bufs[i].append(d.copy())))
            except Exception as e:
                errors[i] = f"{type(e).__name__}: {e}"
        time.sleep(1.0)
        for b in bufs.values():
            b.clear()
        t0 = time.time()
        for c in CUES:
            while time.time() - t0 < c - 1.0:
                time.sleep(0.02)
            print("  get ready…", flush=True)
            while time.time() - t0 < c:
                time.sleep(0.005)
            print("  >>> CLAP-CLAP NOW <<<", flush=True)
        while time.time() - t0 < seconds:
            time.sleep(0.02)
    report = []
    for i, s in enumerate(srcs):
        if i in errors or not bufs[i]:
            print(f"\n{s['name']}: could not record ({errors.get(i, 'no audio')})")
            continue
        raw = np.concatenate(bufs[i])
        variants = [(f"{s['name']} ch{c + 1}", raw[:, c]) for c in range(raw.shape[1])]
        if raw.shape[1] > 1:
            variants.append((f"{s['name']} mix", raw.mean(axis=1)))
        for label, x in variants:
            sig = _to16k(x, s["sr"])
            pk, lv = peaks(sig)
            in_cue = lambda p: any(c * 1000 + 150 <= p["t"] <= c * 1000 + 2000 for c in CUES)
            cue_top = [max([p["level"] for p in pk if c * 1000 + 150 <= p["t"] <= c * 1000 + 2000] or [-90]) for c in CUES]
            other = max([p["level"] for p in pk if not in_cue(p)] or [-90])
            row = {"source": label, "median_db": round(float(np.median(lv)), 1), "cue_peaks_db": cue_top,
                   "loudest_other_db": other, "separation_db": round(min(cue_top) - other, 1)}
            report.append(row)
    print("\n source                          median  clap peaks (cue 1/2/3)   loudest other  separation")
    for r in report:
        print(f"  {r['source']:30s} {r['median_db']:6.0f}  {' / '.join(f'{v:.0f}' for v in r['cue_peaks_db']):>22s}"
              f"   {r['loudest_other_db']:12.0f}  {r['separation_db']:+9.1f}")
    print("\n(Separation = quietest clap minus loudest non-clap sound. Positive and big is good.)")
    print("RESULT_COMPARE " + json.dumps(report))


def diagnose(seconds: float = 13.0) -> None:
    """Guided: tells you exactly when to double-clap, then prints numbers (the audio is discarded)."""
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    print("Moyo clap diagnostics. Only numbers are printed; nothing is saved.\n")
    print("Stay quiet, and double-clap ('clap-clap') ONLY when you see CLAP-CLAP NOW (3 times).")
    input("  Press Enter to start…")
    sig = _record_with_cues(seconds)
    pk, lv = peaks(sig)
    print(f"\nExact digital silence: {np.mean(lv <= FLOOR_DB + 0.1):.0%} of frames. "
          f"Level percentiles 10/50/90: {' / '.join(f'{np.percentile(lv, q):.0f}' for q in (10, 50, 90))} dB")
    print("\n time    where        peak dB  jump  bright  fall10ms")
    for p in pk:
        cue = next((c for c in CUES if c * 1000 - 300 <= p["t"] <= c * 1000 + 2000), None)
        tag = f"cue {CUES.index(cue) + 1}" if cue else "-- other"
        print(f"  {p['t'] / 1000:5.2f}s  {tag:11s} {p['level']:7.1f} {p['jump']:+6.1f}  {p['bright']:5.2f}  {p['fall10_ms']:6d}")
    print("\nRESULT_DIAG " + json.dumps({"cues_ms": [int(c * 1000) for c in CUES], "peaks": pk}))


def phrase_test() -> None:
    """Live test of clap + 'let's get to work' with the real listener. Prints text only."""
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    steps = [(3, f"CLAP once, then say: \"{WAKE_PHRASE}\"", True),
             (14, "CLAP once, then say something else, e.g. \"let's get some water\"", False),
             (25, f"CLAP once, then say: \"{WAKE_PHRASE}\"", True)]
    print("Moyo wake test (clap + phrase). Nothing is recorded or saved.\n")
    input("  Press Enter to start…")
    t0 = time.time()
    wakes = []
    lst = Listener(PHRASE_PARAMS, lambda: (wakes.append(round(time.time() - t0, 1)),
                                           print(f"  ✓ WOKE at {time.time() - t0:.1f}s", flush=True)), mode="clap_phrase")
    print("  loading speech model…", flush=True)
    lst.start()
    if lst.error:
        print("  ✗ " + lst.error)
        return
    t0 = time.time()
    log_n, w = 0, 0

    def report(n):
        nonlocal w
        if lst.windows != w:
            w = lst.windows
            print(f"  · {time.time() - t0:4.1f}s  sharp sound → listening (window {w})", flush=True)
        for heard in lst.heard_log[n:]:
            print(f"  · {time.time() - t0:4.1f}s  window heard: {heard!r}", flush=True)
        return len(lst.heard_log)

    for at, text, _ in steps:
        while time.time() - t0 < at:
            log_n = report(log_n)
            time.sleep(0.05)
        print(f"\n  >>> {text} <<<", flush=True)
    end = time.time() + 9
    while time.time() < end:
        log_n = report(log_n)
        time.sleep(0.05)
    lst.stop()
    expected = sum(1 for *_, should in steps if should)
    print(f"\nWoke {len(wakes)} time(s) {wakes}; expected {expected} (the 'something else' step should NOT wake).")
    print("RESULT_PHRASE " + json.dumps({"wakes_s": wakes, "expected": expected, "windows": lst.windows}))


if __name__ == "__main__" and "--phrase-test" in sys.argv:  # python -m moyo.clap --phrase-test
    phrase_test()
    sys.exit(0)

if __name__ == "__main__" and "--compare" in sys.argv:  # python -m moyo.clap --compare
    compare()
    sys.exit(0)

if __name__ == "__main__" and "--diag" in sys.argv:  # python -m moyo.clap --diag
    diagnose()
    sys.exit(0)

if __name__ == "__main__":  # uv run python -m moyo.clap
    result = calibrate()
    if result:
        from moyo import db
        con = db.connect(); db.init(con)
        cur = db.get_setting(con, "clap")
        db.set_setting(con, "clap", {**cur, "params": {k: v for k, v in result.items() if k in Params.__dataclass_fields__},
                                     "calibrated": result["calibrated"]})
        print("\nSaved to Moyo. " + ("Turn on clap-to-wake in Settings → Morning & reminders." if result["calibrated"]
                                     else "Saved anyway; run calibration again if wake-ups are unreliable."))
        print("RESULT " + json.dumps(result))
