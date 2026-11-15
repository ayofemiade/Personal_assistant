"""Start Moyo: run the local server (if not already running) and open the dashboard window."""
from __future__ import annotations

import os
import socket
import subprocess
import sys
import threading
import time
import webbrowser

from moyo.server import PORT, app
from moyo.workspaces import chrome

URL = f"http://127.0.0.1:{PORT}/" + ("#start-day" if "--start-day" in sys.argv else "")


def running() -> bool:
    with socket.socket() as s:
        s.settimeout(0.3)
        return s.connect_ex(("127.0.0.1", PORT)) == 0


def open_window() -> None:
    c = chrome()
    if c and "--browser" not in sys.argv:
        # app-mode window: looks like a desktop app, no tabs/address bar
        # autoplay allowed so "Start my day" can read the briefing aloud without an extra click
        subprocess.Popen([c, f"--app={URL}", "--window-size=1360,900", "--autoplay-policy=no-user-gesture-required"],
                         creationflags=0x00000008, close_fds=True)
    else:
        webbrowser.open(URL)


def main() -> None:
    if sys.stdout is None or sys.stderr is None:  # started via pythonw (no console): log to a file
        from moyo.db import DATA_DIR
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        sys.stdout = sys.stderr = open(DATA_DIR / "moyo.log", "a", encoding="utf-8", buffering=1)
    if running():
        open_window()
        return
    if "--no-window" not in sys.argv:
        def later():
            for _ in range(50):
                if running():
                    open_window()
                    return
                time.sleep(0.2)
        threading.Thread(target=later, daemon=True).start()
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=PORT, log_level=os.environ.get("MOYO_LOG", "warning"))


if __name__ == "__main__":
    main()
