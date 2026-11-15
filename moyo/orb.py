"""The wake orb: a small always-on-top card that appears after a double clap (or "wake test").

It starts as just a glowing dot, speaks the short brief (captions on screen too), then asks
"Want to see your full dashboard?". Enter = open dashboard, S = start my day, Esc = later.
Runs as its own process (pythonw -m moyo.orb) and only talks to Moyo's local API.
"""
from __future__ import annotations

import io
import json
import math
import os
import queue
import subprocess
import sys
import threading
import time
import tkinter as tk

import requests

PORT = int(os.environ.get("MOYO_PORT", "8765"))
BASE = f"http://127.0.0.1:{PORT}"
HDR = {"X-Moyo": "1"}

# dark tokens from MOYO_AI_DESIGN_SYSTEM.md (the orb is always dark so it reads on any wallpaper)
BG, SURFACE2, LINE = "#1B1916", "#24211D", "#33302B"
TEXT, TEXT2, TEXT3 = "#F1ECE4", "#ADA597", "#857D70"
ACCENT, ACCENT_INK, ACCENT_SOFT = "#F2A93B", "#1B1308", "#3A2A12"
FONT = "Segoe UI"
W = 380
IDLE_CLOSE_S = 90


def _mix(a: str, b: str, t: float) -> str:
    pa, pb = [int(a[i:i + 2], 16) for i in (1, 3, 5)], [int(b[i:i + 2], 16) for i in (1, 3, 5)]
    return "#" + "".join(f"{round(x + (y - x) * t):02x}" for x, y in zip(pa, pb))


def open_dashboard(view: str = "today") -> None:
    from moyo.workspaces import chrome
    url = f"{BASE}/#{view}"
    c = chrome()
    if c:
        subprocess.Popen([c, f"--app={url}", "--window-size=1360,900", "--autoplay-policy=no-user-gesture-required"],
                         creationflags=0x00000008, close_fds=True)
    else:
        import webbrowser
        webbrowser.open(url)


class Voice:
    """Fetches each sentence from /api/tts (Moyo's chosen voice) one ahead, plays it, interruptible."""

    def __init__(self, events: queue.Queue):
        self.events, self.stopped = events, False

    def _clip(self, text):
        import soundfile as sf
        r = requests.post(f"{BASE}/api/tts", json={"text": text}, headers=HDR, timeout=40)
        r.raise_for_status()
        data, sr = sf.read(io.BytesIO(r.content), dtype="float32")
        return data, sr

    def run(self, sentences: list[str]) -> None:
        import sounddevice as sd
        clips: queue.Queue = queue.Queue()

        def fetch():
            for s in sentences:
                if self.stopped:
                    break
                try:
                    clips.put((s, self._clip(s)))
                except Exception:
                    clips.put((s, None))
            clips.put(None)
        threading.Thread(target=fetch, daemon=True).start()
        voice_ok = False
        while not self.stopped:
            item = clips.get()
            if item is None:
                break
            s, clip = item
            self.events.put(("caption", s))
            if clip is not None:
                voice_ok = True
                try:
                    if os.environ.get("MOYO_ORB_SILENT") == "1":  # testing: same timing, no sound
                        end = time.time() + len(clip[0]) / clip[1]
                        while not self.stopped and time.time() < end:
                            time.sleep(0.05)
                        continue
                    sd.play(*clip)
                    while not self.stopped and sd.get_stream().active:
                        time.sleep(0.05)
                except Exception:
                    time.sleep(min(6, 0.6 + len(s) / 16))
            else:  # voice unavailable: still show the words long enough to read
                end = time.time() + min(6, 0.6 + len(s) / 16)
                while not self.stopped and time.time() < end:
                    time.sleep(0.05)
            time.sleep(0.12)
        self.events.put(("done", voice_ok))

    def stop(self):
        self.stopped = True
        try:
            import sounddevice as sd
            sd.stop()
        except Exception:
            pass


class Orb:
    def __init__(self, source: str = "clap"):
        try:  # crisp text on high-DPI screens
            import ctypes
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except Exception:
            pass
        self.root = tk.Tk()
        self.root.withdraw()
        self.S = max(1.0, self.root.winfo_fpixels("1i") / 96)
        self.events: queue.Queue = queue.Queue()
        self.voice = Voice(self.events)
        self.spotter = None
        self.chat = None               # VoiceChat while a two-way conversation is open
        self._said_hello = False
        self.phase = "waking"          # waking → speaking → asking → closing
        self.t0 = time.time()
        self.idle_since = None
        self.source = source
        self._build()

    # ------------------------------------------------------------ layout
    def _build(self):
        r = self.root
        r.overrideredirect(True)
        r.attributes("-topmost", True)
        r.attributes("-toolwindow", True)
        r.attributes("-alpha", 0.0)
        r.configure(bg=BG, highlightthickness=1, highlightbackground=LINE)
        r.title("Moyo")

        head = tk.Frame(r, bg=BG)
        head.pack(fill="x", padx=self.px(14), pady=(self.px(12), self.px(10)))
        self.dot = tk.Canvas(head, width=self.px(28), height=self.px(28), bg=BG, highlightthickness=0)
        self.dot.pack(side="left")
        self.halo = self.dot.create_oval(*[self.px(v) for v in (2, 2, 26, 26)], fill=ACCENT_SOFT, outline="")
        self.core = self.dot.create_oval(*[self.px(v) for v in (8, 8, 20, 20)], fill=ACCENT, outline="")
        tk.Label(head, text="Moyo", bg=BG, fg=TEXT, font=(FONT, 11, "bold")).pack(side="left", padx=(self.px(10), self.px(6)))
        self.status = tk.Label(head, text="Waking up…", bg=BG, fg=TEXT3, font=(FONT, 10))
        self.status.pack(side="left")
        close = tk.Label(head, text="✕", bg=BG, fg=TEXT3, font=(FONT, 11), cursor="hand2", padx=6)
        close.pack(side="right")
        close.bind("<Button-1>", lambda e: self.later())
        close.bind("<Enter>", lambda e: close.configure(fg=TEXT))
        close.bind("<Leave>", lambda e: close.configure(fg=TEXT3))

        self.body = tk.Frame(r, bg=BG)
        self.caption = tk.Label(self.body, text="", bg=BG, fg=TEXT, font=(FONT, 12), justify="left",
                                anchor="w", wraplength=self.px(W - 36))
        self.caption.pack(fill="x", padx=self.px(18), pady=(0, self.px(4)))
        self.skip = self._button(self.body, "Skip  ›", self.finish_speaking, kind="ghost")
        self.skip.pack(anchor="e", padx=self.px(12), pady=(self.px(2), self.px(12)))

        self.ask = tk.Frame(r, bg=BG)
        self.question = tk.Label(self.ask, text="", bg=BG, fg=TEXT, font=(FONT, 12, "bold"), anchor="w",
                                 justify="left", wraplength=self.px(W - 36))
        self.question.pack(fill="x", padx=self.px(18), pady=(self.px(4), self.px(10)))
        row = tk.Frame(self.ask, bg=BG)
        row.pack(fill="x", padx=self.px(14), pady=(0, self.px(6)))
        self._button(row, "Open dashboard", self.open, kind="primary").pack(side="left")
        self._button(row, "Start my day", self.start_day, kind="secondary").pack(side="left", padx=self.px(8))
        self._button(row, "Later", self.later, kind="ghost").pack(side="left")
        tk.Label(self.ask, text="Say “open my dashboard”, “start my day”, “later”, or just ask me something.  Keys: Enter · S · T · Esc", bg=BG, fg=TEXT3,
                 font=(FONT, 9), wraplength=self.px(W - 36), justify="left").pack(anchor="w", padx=self.px(18), pady=(self.px(2), self.px(12)))

        # talk panel (two-way voice)
        self.talk = tk.Frame(r, bg=BG)
        self.you = tk.Label(self.talk, text="", bg=BG, fg=TEXT2, font=(FONT, 10), justify="left", anchor="w",
                            wraplength=self.px(W - 36))
        self.you.pack(fill="x", padx=self.px(18), pady=(0, self.px(6)))
        self.reply = tk.Label(self.talk, text="Go ahead, I'm listening.", bg=BG, fg=TEXT, font=(FONT, 12), justify="left",
                              anchor="w", wraplength=self.px(W - 36))
        self.reply.pack(fill="x", padx=self.px(18), pady=(0, self.px(10)))
        trow = tk.Frame(self.talk, bg=BG)
        trow.pack(fill="x", padx=self.px(14), pady=(0, self.px(6)))
        self._button(trow, "Open dashboard", self.open, kind="secondary").pack(side="left")
        self._button(trow, "End", self.later, kind="ghost").pack(side="left", padx=self.px(8))
        tk.Label(self.talk, text="While this is open your voice goes to Google Gemini. Esc ends.", bg=BG, fg=TEXT3,
                 font=(FONT, 9), wraplength=self.px(W - 36), justify="left").pack(anchor="w", padx=self.px(18), pady=(self.px(2), self.px(12)))

        # confirm panel: only YOU can approve (click, Enter, or "confirm" heard offline on this laptop)
        self.confirm = tk.Frame(r, bg=BG)
        tk.Label(self.confirm, text="Needs your OK", bg=BG, fg=ACCENT, font=(FONT, 10, "bold"), anchor="w").pack(
            fill="x", padx=self.px(18), pady=(0, self.px(4)))
        self.confirm_text = tk.Label(self.confirm, text="", bg=BG, fg=TEXT, font=(FONT, 12), justify="left", anchor="w",
                                     wraplength=self.px(W - 36))
        self.confirm_text.pack(fill="x", padx=self.px(18), pady=(0, self.px(10)))
        crow = tk.Frame(self.confirm, bg=BG)
        crow.pack(fill="x", padx=self.px(14), pady=(0, self.px(6)))
        self._button(crow, "Confirm", lambda: self._answer_confirm(True), kind="primary").pack(side="left")
        self._button(crow, "Cancel", lambda: self._answer_confirm(False), kind="secondary").pack(side="left", padx=self.px(8))
        tk.Label(self.confirm, text="Say “confirm” or “cancel”.  Keys: Enter · Esc", bg=BG, fg=TEXT3, font=(FONT, 9)).pack(
            anchor="w", padx=self.px(18), pady=(self.px(2), self.px(12)))

        r.bind("<Escape>", lambda e: self._answer_confirm(False) if self.phase == "confirm" else self.later())
        r.bind("<Return>", lambda e: self.open() if self.phase == "asking" else
               self._answer_confirm(True) if self.phase == "confirm" else self.finish_speaking())
        r.bind("<Key-s>", lambda e: self.start_day() if self.phase == "asking" else None)
        r.bind("<Key-t>", lambda e: self.start_talk() if self.phase == "asking" else None)
        r.bind("<space>", lambda e: self.finish_speaking() if self.phase == "speaking" else None)

    def px(self, n) -> int:
        return round(n * self.S)

    def _button(self, parent, text, cmd, kind):
        bg, fg, hov = {"primary": (ACCENT, ACCENT_INK, _mix(ACCENT, "#ffffff", .15)),
                       "secondary": (SURFACE2, TEXT, LINE),
                       "ghost": (BG, TEXT2, SURFACE2)}[kind]
        b = tk.Label(parent, text=text, bg=bg, fg=fg, font=(FONT, 10, "bold" if kind == "primary" else "normal"),
                     padx=self.px(12), pady=self.px(6), cursor="hand2")
        b.bind("<Button-1>", lambda e: cmd())
        b.bind("<Enter>", lambda e: b.configure(bg=hov, fg=TEXT if kind == "ghost" else fg))
        b.bind("<Leave>", lambda e: b.configure(bg=bg, fg=fg))
        return b

    def _place(self):
        r = self.root
        r.update_idletasks()
        h = r.winfo_reqheight()
        w, m = self.px(W), self.px(24)
        r.geometry(f"{w}x{h}+{r.winfo_screenwidth() - w - m}+{m}")

    def _round_corners(self):
        try:  # Windows 11: ask DWM for rounded corners (harmless elsewhere)
            import ctypes
            hwnd = ctypes.windll.user32.GetParent(self.root.winfo_id())
            pref = ctypes.c_int(2)
            ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, 33, ctypes.byref(pref), ctypes.sizeof(pref))
        except Exception:
            pass

    # ------------------------------------------------------------ animation + event pump
    def _tick(self):
        t = time.time() - self.t0
        talking_aloud = self.chat is not None and self.chat._speaking()
        speed = 2.4 if self.phase == "speaking" or talking_aloud else 1.2
        if talking_aloud and self.phase == "talking":
            self.status.configure(text="Speaking")
        k = (math.sin(t * speed * math.pi) + 1) / 2
        rad = self.S * (9 + 4 * k if self.phase != "asking" else 11)
        c = self.S * 14
        self.dot.coords(self.halo, c - rad, c - rad, c + rad, c + rad)
        self.dot.itemconfigure(self.halo, fill=_mix(BG, ACCENT, .12 + .22 * k) if self.phase != "asking" else ACCENT_SOFT)
        a = float(self.root.attributes("-alpha"))
        if self.phase != "closing" and a < 1.0:
            self.root.attributes("-alpha", min(1.0, a + 0.12))
        elif self.phase == "closing":
            if a <= 0.05:
                self.root.destroy()
                return
            self.root.attributes("-alpha", a - 0.15)
        try:
            while True:
                kind, val = self.events.get_nowait()
                if kind == "brief":
                    self._speak(val)
                elif kind == "caption":
                    self.status.configure(text="Speaking")
                    self.caption.configure(text=val)
                    self._place()
                elif kind == "done":
                    self.finish_speaking(voice_ok=val)
                elif kind == "error":
                    self.status.configure(text="Can't reach Moyo")
                    self.caption.configure(text=val)
                    self.body.pack(fill="x")
                    self.skip.pack_forget()
                    self._place()
                    self.idle_since = time.time()
                elif kind == "listening" and self.phase == "asking":
                    self.status.configure(text="Listening · say “open my dashboard”" if val else "Your call")
                elif kind == "answer" and self.phase == "asking":
                    self.status.configure(text="Heard you")
                    {"open": self.open, "start_day": self.start_day, "later": self.later, "talk": self.start_talk}[val]()
                elif kind == "say":
                    self.caption.configure(text=val, fg=TEXT)
                    self._place()
                elif kind == "answer_talk" and self.phase == "asking":
                    self.start_talk(first_audio=val)
                elif kind.startswith("chat_"):
                    self._chat_event(kind[5:], val)
        except queue.Empty:
            pass
        if self.idle_since and time.time() - self.idle_since > IDLE_CLOSE_S and self.phase != "closing":
            self.later()
        self.root.after(33, self._tick)

    # ------------------------------------------------------------ flow
    def _load(self):
        try:
            r = requests.get(f"{BASE}/api/wake/brief", timeout=15)
            r.raise_for_status()
            self.events.put(("brief", r.json()))
        except Exception:
            self.events.put(("error", "Moyo isn't running right now. Start it with Ctrl+Alt+M."))

    def _speak(self, brief):
        self.brief = brief
        if self.phase != "waking":  # skipped/closed before the brief arrived
            return
        self.phase = "speaking"
        self.status.configure(text="Getting your brief…")
        self.body.pack(fill="x")
        self._place()
        threading.Thread(target=self.voice.run, args=(brief["sentences"],), daemon=True).start()

    def finish_speaking(self, voice_ok=True):
        if self.phase not in ("speaking", "waking"):
            return
        self.voice.stop()
        self.phase = "asking"
        self.status.configure(text="Your call" if voice_ok else "Voice unavailable · captions only")
        self.skip.pack_forget()
        self.caption.configure(fg=TEXT2)
        q = getattr(self, "brief", {}).get("question", "Want to see your full dashboard?")
        if self.caption.cget("text") == "":
            self.body.pack_forget()
        self.question.configure(text=q)
        self.ask.pack(fill="x")
        self._place()
        self.root.focus_force()
        self.idle_since = time.time()
        threading.Thread(target=self._say_question, args=(q,), daemon=True).start()

    def _say_question(self, q):
        if os.environ.get("MOYO_ORB_SILENT") != "1":
            try:
                import sounddevice as sd
                sd.play(*self.voice._clip(q))
                sd.wait()  # finish speaking before listening, so Moyo doesn't hear itself
            except Exception:
                pass
        self._listen_for_answer()

    def _listen_for_answer(self, max_s: float = 60):
        """Offline: listens (in memory only) for 'open my dashboard' / 'yes' / 'start my day' / 'later'."""
        try:
            import sounddevice as sd

            from moyo.clap import FRAME, SR, PhraseSpotter, _pcm16, answer_intent, answer_recognizer
            spotter = self.spotter or PhraseSpotter()
            rec = answer_recognizer(spotter)
            q: queue.Queue = queue.Queue()
            buf: list = []
            self.events.put(("listening", True))
            with sd.InputStream(samplerate=SR, channels=1, dtype="float32", blocksize=FRAME * 4,
                                callback=lambda d, f, t, st: q.put(d[:, 0].copy())):
                end = time.time() + max_s
                while self.phase == "asking" and time.time() < end:
                    try:
                        chunk = q.get(timeout=0.2)
                    except queue.Empty:
                        continue
                    buf.append(chunk)
                    if rec.AcceptWaveform(_pcm16(chunk)):
                        text = json.loads(rec.Result()).get("text", "")
                        intent = answer_intent(text)
                        if intent:
                            self.events.put(("answer", intent))
                            return
                        if text.count("[unk]") >= 2:  # sounds like a real question: hand it to the conversation
                            import numpy as np
                            self.events.put(("answer_talk", np.concatenate(buf[-100:])))
                            return
                        buf = []
            self.events.put(("listening", False))
        except Exception:
            self.events.put(("listening", False))

    def _close(self):
        self.voice.stop()
        if self.chat:
            self.chat.stop()
        self.phase = "closing"

    # ------------------------------------------------------------ two-way voice
    def start_talk(self, first_audio=None):
        if self.chat is not None or self.phase == "closing":
            return
        self.voice.stop()
        self.phase = "talking"
        self.idle_since = None
        for f in (self.body, self.ask, self.confirm):
            f.pack_forget()
        self.you.configure(text="")
        self.you.pack_forget()
        self.reply.configure(text="One moment, connecting…", fg=TEXT2)
        self.talk.pack(fill="x")
        self._said_hello = False
        self.status.configure(text="Connecting…")
        self._place()

        def go():
            try:
                cfg = requests.get(f"{BASE}/api/voice/config", timeout=10).json()
                from moyo.cloud import api_key
                api_key = (lambda k=PRELOAD.get("key"): k) if PRELOAD.get("key") else api_key
                from moyo.voice import VoiceChat
                key = api_key()
                if not key:
                    raise RuntimeError("no Gemini key is saved")
                self.chat = VoiceChat(BASE, HDR, lambda k, v: self.events.put(("chat_" + k, v)), key,
                                      voice=cfg.get("chat_voice") or "Sulafat", spotter=self.spotter,
                                      first_audio=first_audio, tools=cfg.get("tools"))
                self.chat.start()
            except Exception as e:
                try:
                    from moyo.voice import vlog
                    vlog(f"start failed: {type(e).__name__}: {e}")
                except Exception:
                    pass
                self.events.put(("chat_error", f"I can't start a voice chat right now ({e})."))
        threading.Thread(target=go, daemon=True).start()

    def _answer_confirm(self, ok):
        if self.chat is not None and self.phase == "confirm":
            self.chat.answer_confirm(ok)

    def _chat_event(self, kind, val):
        if self.phase == "closing":
            return
        if kind == "state" and val == "listening" and not self._said_hello:
            self._said_hello = True
            if self.reply.cget("text").startswith("One moment"):
                self.reply.configure(text="Go ahead, I'm listening.", fg=TEXT)
                self._place()
        if kind == "state" and self.phase == "talking":
            self.status.configure(text={"listening": "Listening", "thinking": "Thinking…",
                                        "speaking": "Speaking"}.get(val, val))
        elif kind == "you":
            self.you.configure(text=f"You: {val}")
            if not self.you.winfo_ismapped():
                self.you.pack(fill="x", padx=self.px(18), pady=(0, self.px(6)), before=self.reply)
            self._place()
        elif kind == "moyo":
            self.reply.configure(text=val, fg=TEXT)
            self._place()
        elif kind == "confirm":
            self.phase = "confirm"
            self.talk.pack_forget()
            self.confirm_text.configure(text=val)
            self.confirm.pack(fill="x")
            self.status.configure(text="Waiting for you")
            self._place()
            self.root.focus_force()
        elif kind == "confirm_done":
            self.phase = "talking"
            self.confirm.pack_forget()
            self.talk.pack(fill="x")
            self.status.configure(text="Confirmed" if val else "Cancelled")
            self._place()
        elif kind == "open":
            threading.Thread(target=open_dashboard, daemon=True).start()
        elif kind == "error":
            self.status.configure(text="Voice unavailable")
            self.reply.configure(text=val)
            self._place()
            self.idle_since = time.time()
        elif kind == "end":
            self.chat = None
            if self.phase in ("talking", "confirm") and self.status.cget("text") != "Voice unavailable":
                self._close()

    def open(self):
        self._close()
        threading.Thread(target=open_dashboard, daemon=True).start()

    def later(self):
        self._close()

    def start_day(self):
        self.status.configure(text="Starting your day…")
        self.ask.pack_forget()
        self.body.pack(fill="x")
        self.voice.stop()

        def go():
            try:
                r = requests.post(f"{BASE}/api/routine/start", headers=HDR, timeout=30)
                r.raise_for_status()
                self.events.put(("say", r.json().get("reply", "Starting your day.").replace(" Here's your briefing.", "")))
            except Exception:
                self.events.put(("say", "I couldn't start your day. Open Moyo and try again."))
            open_dashboard("today")
            time.sleep(4)
            self.phase = "closing"
        threading.Thread(target=go, daemon=True).start()

    def _load_speech(self):
        try:  # load the offline recogniser while the brief is playing (~1 s)
            from moyo.clap import PhraseSpotter
            self.spotter = PRELOAD.get("spotter") or PhraseSpotter()
        except Exception:
            pass
        try:  # and the Gemini library (slow first import), so a conversation starts quickly
            import google.genai  # noqa: F401

            import moyo.voice  # noqa: F401
        except Exception:
            pass

    def run(self):
        self._place()
        self.root.deiconify()
        self._round_corners()
        self.root.focus_force()
        threading.Thread(target=self._load_speech, daemon=True).start()
        if self.source == "talk":
            self.root.after(50, self.start_talk)
        else:
            threading.Thread(target=self._load, daemon=True).start()
        self.root.after(33, self._tick)
        self.root.mainloop()


PRELOAD: dict = {}


def _preload() -> None:
    """Everything slow, done in advance: speech model, Gemini library, API key (~2.5 s)."""
    try:
        from moyo.clap import PhraseSpotter
        PRELOAD["spotter"] = PhraseSpotter()
    except Exception:
        pass
    try:
        import google.genai  # noqa: F401
        import sounddevice  # noqa: F401
        import soundfile  # noqa: F401

        import moyo.voice  # noqa: F401
        from moyo.cloud import api_key
        PRELOAD["key"] = api_key()
    except Exception:
        pass


def standby() -> None:
    """Wait (pre-loaded, invisible) until Moyo's server says to show the orb. Localhost only, with a secret key."""
    from multiprocessing.connection import Listener
    secret = bytes.fromhex(os.environ.get("MOYO_ORB_KEY", ""))
    parent = int(os.environ.get("MOYO_PARENT_PID", "0"))
    listener = Listener(("127.0.0.1", 0), authkey=secret)
    print(listener.address[1], flush=True)       # tell the server which port to use
    sys.stdout = sys.stderr = open(os.devnull, "w")

    def watch_parent():  # never outlive the Moyo server
        import ctypes
        while True:
            time.sleep(3)
            h = ctypes.windll.kernel32.OpenProcess(0x1000, False, parent)  # PROCESS_QUERY_LIMITED_INFORMATION
            code = ctypes.c_ulong()
            alive = bool(h) and ctypes.windll.kernel32.GetExitCodeProcess(h, ctypes.byref(code)) and code.value == 259
            if h:
                ctypes.windll.kernel32.CloseHandle(h)
            if not alive:
                os._exit(0)
    if parent:
        threading.Thread(target=watch_parent, daemon=True).start()
    _preload()
    with listener.accept() as conn:
        source = conn.recv()
    listener.close()
    Orb(str(source)).run()


def main():
    if sys.stdout is None or sys.stderr is None:  # pythonw: no console
        sys.stdout = sys.stderr = open(os.devnull, "w")
    if "--standby" in sys.argv:
        standby()
        return
    Orb(sys.argv[1] if len(sys.argv) > 1 else "clap").run()


if __name__ == "__main__":
    main()
