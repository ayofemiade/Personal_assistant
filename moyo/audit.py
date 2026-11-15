"""Append-only activity log: every change Moyo makes is recorded here."""
from __future__ import annotations

import json

from moyo.db import now_iso, rows


def log(con, actor: str, action: str, tier: str, detail=None, result: str = "ok") -> None:
    con.execute("INSERT INTO audit_log(ts, actor, action, tier, detail, result) VALUES (?,?,?,?,?,?)",
                (now_iso(), actor, action, tier, json.dumps(detail, default=str) if detail is not None else None, result))


def recent(con, limit: int = 100) -> list[dict]:
    return rows(con.execute("SELECT * FROM audit_log ORDER BY id DESC LIMIT ?", (limit,)))
