"""Clap-to-wake manager (runs inside the Moyo server).

- Listens only when Settings → clap.enabled is on, and not in quiet hours (unless allowed).
- The mic is analysed 10 ms at a time in memory; nothing is recorded or sent anywhere.
- A double clap opens the wake orb (a separate small process). While the orb is open, more claps are ignored.
"""
from __future__ import annotations

import os
import subprocess
import sys
import threading
import time
from dataclasses import fields
from datetime import datetime
from pathlib import Path

from moyo import audit, db

ROOT = Path(__file__).resolve().parent.parent


def params_from(cfg: dict):
    from moyo.clap import Params
    known = {f.name for f in fields(Params)}
    return Params(**{k: v for k, v in (cfg.get("params") or {}).items() if k in known})


def should_listen(cfg: dict, notif: dict, now: datetime) -> tuple[bool, str]:
    from moyo.reminders import in_quiet_hours
    if not cfg.get("enabled"):
        return False, "off"
    if not cfg.get("listen_in_quiet_hours") and in_quiet_hours(now, notif["quiet_start"], notif["quiet_end"]):
        return False, "quiet_hours"
    return True, "listening"


def _python() -> str:
    exe = Path(sys.executable)
    w = exe.with_name("pythonw.exe")
    return str(w if w.exists() else exe)


class WakeManager:
    def __init__(self):
        self.listener = None
        self.params_key = None
        self.reason = "off"
        self.orb: subprocess.Popen | None = None
        self.standby = None              # (process, port, secret): a pre-loaded orb waiting to be shown
        self.last_wake: str | None = None
        self._lock = threading.Lock()

    # ------------------------------------------------------------ orb
    def orb_open(self) -> bool:
        return bool(self.orb and self.orb.poll() is None)

    def spawn_standby(self) -> None:
        """Start an invisible, pre-loaded orb so the next wake/talk opens in ~1 s instead of ~4 s."""
        import secrets
        with self._lock:
            if self.standby and self.standby[0].poll() is None:
                return
            secret = secrets.token_bytes(16)
            env = {**os.environ, "MOYO_PORT": os.environ.get("MOYO_PORT", "8765"), "MOYO_ORB_KEY": secret.hex(),
                   "MOYO_PARENT_PID": str(os.getpid())}
            proc = subprocess.Popen([_python(), "-m", "moyo.orb", "--standby"], cwd=str(ROOT), env=env,
                                    stdout=subprocess.PIPE, creationflags=0x08000000, close_fds=True)
        try:
            port = int(proc.stdout.readline().strip() or 0)
        except Exception:
            port = 0
        with self._lock:
            if port:
                self.standby = (proc, port, secret)
            else:
                proc.kill()

    def _replenish(self, proc) -> None:
        try:
            proc.wait()
        except Exception:
            pass
        time.sleep(1.5)
        self.spawn_standby()

    def launch_orb(self, source: str = "clap") -> bool:
        from multiprocessing.connection import Client
        with self._lock:
            if self.orb_open():
                return False
            sb, self.standby = self.standby, None
            self.orb = None
            if sb and sb[0].poll() is None:
                try:
                    with Client(("127.0.0.1", sb[1]), authkey=sb[2]) as c:
                        c.send(source)
                    self.orb = sb[0]
                except Exception:
                    sb[0].kill()
            if self.orb is None:  # no standby ready: start one directly (slower)
                env = {**os.environ, "MOYO_PORT": os.environ.get("MOYO_PORT", "8765")}
                self.orb = subprocess.Popen([_python(), "-m", "moyo.orb", source], cwd=str(ROOT), env=env,
                                            creationflags=0x08000000, close_fds=True)  # no console window
            self.last_wake = db.now_iso()
            threading.Thread(target=self._replenish, args=(self.orb,), daemon=True).start()
        return True

    def _on_wake(self):
        if self.orb_open():
            return
        if self.launch_orb("clap"):
            try:
                c = db.connect()
                audit.log(c, "moyo", "clap_wake", "read", None, "orb opened")
                c.close()
            except Exception:
                pass

    # ------------------------------------------------------------ listener
    def reconcile(self, con, now: datetime | None = None) -> None:
        """Start/stop/retune the mic listener to match settings. Called every minute and after settings change."""
        cfg, notif = db.get_setting(con, "clap"), db.get_setting(con, "notifications")
        want, self.reason = should_listen(cfg, notif, now or datetime.now())
        mode = cfg.get("mode") or "clap_phrase"
        key = repr((mode, sorted((cfg.get("params") or {}).items())))
        with self._lock:
            if self.listener and (not want or key != self.params_key or not self.listener.running):
                self.listener.stop()
                self.listener = None
            if want and not self.listener:
                from moyo.clap import PHRASE_PARAMS, Listener
                params = PHRASE_PARAMS if mode == "clap_phrase" else params_from(cfg)
                self.listener = Listener(params, self._on_wake, mode=mode)
                self.listener.start()
                self.params_key = key
                if self.listener.error:
                    self.reason = "mic_error"

    def stop(self):
        with self._lock:
            if self.listener:
                self.listener.stop()
                self.listener = None

    def status(self, con) -> dict:
        cfg = db.get_setting(con, "clap")
        lst = self.listener
        from moyo.clap import MODEL_DIR, WAKE_PHRASE
        return {"enabled": bool(cfg.get("enabled")), "calibrated": bool(cfg.get("calibrated")),
                "mode": cfg.get("mode") or "clap_phrase", "phrase": WAKE_PHRASE, "phrase_model": MODEL_DIR.exists(),
                "windows": lst.windows if lst else 0, "last_heard": lst.last_heard if lst else None,
                "heard_log": list(lst.heard_log[-10:]) if lst else [],
                "mic_reconnects": lst.reconnects if lst else 0,
                "seconds_since_audio": round(time.time() - lst.last_audio, 1) if lst and lst.last_audio else None,
                "listen_in_quiet_hours": bool(cfg.get("listen_in_quiet_hours")),
                "listening": bool(lst and lst.running), "state": self.reason,
                "error": lst.error if lst else None, "last_wake": self.last_wake, "orb_open": self.orb_open()}


manager = WakeManager()
