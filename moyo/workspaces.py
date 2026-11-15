"""Workspace profiles: launch ONLY allowlisted apps/URLs from config/workspaces.json.
No shell, no arbitrary commands, no paths outside the config."""
from __future__ import annotations

import ctypes
import json
import os
import re
import subprocess
import sys
from pathlib import Path

from moyo.db import ROOT

CONFIG = ROOT / "config" / "workspaces.json"
CHROME_CANDIDATES = [r"%ProgramFiles%\Google\Chrome\Application\chrome.exe",
                     r"%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe",
                     r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe"]
SPOTIFY_URI = re.compile(r"^spotify:(playlist|album|track|artist):[A-Za-z0-9]{10,40}$")
SAFE_ROOTS = [os.path.expandvars(p).lower() for p in
              ("%LOCALAPPDATA%", "%ProgramFiles%", "%ProgramFiles(x86)%", "%APPDATA%")]


class WorkspaceError(ValueError):
    pass


def load() -> dict:
    path = CONFIG if CONFIG.exists() else CONFIG.with_name("workspaces.example.json")  # your own copy is private
    data = json.loads(path.read_text(encoding="utf-8"))
    return {k: v for k, v in data.items() if not k.startswith("_")}


def resolve_profile(name: str) -> str | None:
    n = name.lower().strip()
    aliases = {"dev": "coding", "development": "coding", "code": "coding", "programming": "coding",
               "work": "general", "biz": "business", "sales": "business", "creator": "content",
               "content creation": "content", "school": "study", "uni": "study", "university": "study"}
    n = aliases.get(n, n)
    return n if n in load() else None


def _exe(path: str) -> str:
    p = os.path.expandvars(path)
    pl = p.lower()
    if not pl.endswith(".exe") or not any(pl.startswith(r) for r in SAFE_ROOTS):
        raise WorkspaceError(f"Refusing to launch {path}: not an allowlisted program location.")
    if not Path(p).exists():
        raise WorkspaceError(f"{path} is not installed.")
    return p


def chrome() -> str | None:
    for c in CHROME_CANDIDATES:
        p = os.path.expandvars(c)
        if Path(p).exists():
            return p
    return None


def plan(name: str) -> dict:
    """What would be launched (used for dry runs, the UI and tests)."""
    key = resolve_profile(name)
    if not key:
        raise WorkspaceError(f"No workspace called '{name}'. Options: {', '.join(load())}.")
    prof = load()[key]
    apps, problems = [], []
    for a in prof.get("apps", []):
        try:
            apps.append({"name": a["name"], "exe": _exe(a["path"]),
                         "args": [os.path.expandvars(x) for x in a.get("args", [])]})
        except WorkspaceError as e:
            problems.append(str(e))
    urls = [u for u in prof.get("urls", []) if u.startswith("https://")]
    music = prof.get("music")
    if music and not SPOTIFY_URI.match(music):
        problems.append(f"Ignoring music '{music}': not a Spotify URI.")
        music = None
    return {"key": key, "label": prof.get("label", key), "apps": apps, "urls": urls, "music": music,
            "problems": problems}


def launch(name: str, dry_run: bool = False) -> dict:
    p = plan(name)
    if dry_run or sys.platform != "win32":
        return {**p, "launched": False}
    flags = 0x00000008 | 0x00000200  # DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP
    for a in p["apps"]:
        subprocess.Popen([a["exe"], *a["args"]], creationflags=flags, close_fds=True)
    if p["urls"]:
        c = chrome()
        if c:
            subprocess.Popen([c, "--new-window", *p["urls"]], creationflags=flags, close_fds=True)
        else:
            import webbrowser
            for u in p["urls"]:
                webbrowser.open(u)
    if p["music"]:
        os.startfile(p["music"])  # validated spotify: URI → Spotify app
    return {**p, "launched": True}


# ---------------------------------------------------------------- media keys (any player)
VK = {"play_pause": 0xB3, "next": 0xB0, "previous": 0xB1, "volume_up": 0xAF, "volume_down": 0xAE, "mute": 0xAD}


def media(action: str, times: int = 1) -> None:
    if action not in VK:
        raise WorkspaceError(f"Unknown media action {action}.")
    if sys.platform != "win32":
        return
    for _ in range(max(1, min(times, 10))):
        ctypes.windll.user32.keybd_event(VK[action], 0, 0, 0)
        ctypes.windll.user32.keybd_event(VK[action], 0, 2, 0)
