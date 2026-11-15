"""Structured, inspectable memory: every item has a kind, source and optional expiry."""
from __future__ import annotations

from moyo.db import now_iso, rows, today

KINDS = ("fact", "preference", "assumption", "plan", "historical")


def listing(con, include_expired: bool = False) -> list[dict]:
    items = rows(con.execute("SELECT * FROM memory ORDER BY category, kind, id"))
    iso = today().isoformat()
    for m in items:
        m["expired"] = bool(m["valid_until"] and m["valid_until"] < iso)
    return items if include_expired else [m for m in items if not m["expired"]]


def add(con, content: str, category: str = "general", kind: str = "fact", source: str = "user",
        valid_until: str | None = None, confirmed: bool = True) -> dict:
    if kind not in KINDS:
        raise ValueError(f"kind must be one of {KINDS}")
    if kind == "plan" and not valid_until:
        raise ValueError("Plans are temporary: give an expiry date (valid_until).")
    ts = now_iso()
    cur = con.execute("INSERT INTO memory(category, kind, content, source, valid_until, confirmed, created_at, "
                      "updated_at) VALUES (?,?,?,?,?,?,?,?)",
                      (category, kind, content.strip(), source, valid_until, int(confirmed), ts, ts))
    return dict(con.execute("SELECT * FROM memory WHERE id=?", (cur.lastrowid,)).fetchone())


def update(con, mem_id: int, **fields) -> dict:
    allowed = {"category", "kind", "content", "valid_until", "confirmed"}
    fields = {k: v for k, v in fields.items() if k in allowed}
    if fields.get("kind") and fields["kind"] not in KINDS:
        raise ValueError(f"kind must be one of {KINDS}")
    if fields:
        con.execute(f"UPDATE memory SET {', '.join(f'{k}=?' for k in fields)}, updated_at=? WHERE id=?",
                    (*fields.values(), now_iso(), mem_id))
    r = con.execute("SELECT * FROM memory WHERE id=?", (mem_id,)).fetchone()
    if not r:
        raise ValueError(f"Memory #{mem_id} not found.")
    return dict(r)


def delete(con, mem_id: int) -> dict:
    r = con.execute("SELECT * FROM memory WHERE id=?", (mem_id,)).fetchone()
    if not r:
        raise ValueError(f"Memory #{mem_id} not found.")
    con.execute("DELETE FROM memory WHERE id=?", (mem_id,))
    return dict(r)


def search(con, text: str) -> list[dict]:
    words = [w for w in text.lower().split() if len(w) > 2]
    items = listing(con, include_expired=True)
    scored = [(sum(w in m["content"].lower() for w in words), m) for m in items]
    return [m for s, m in sorted(scored, key=lambda x: -x[0]) if s]


def summary_text(con) -> str:
    items = listing(con)
    if not items:
        return "I don't have anything stored about you yet."
    label = {"fact": "", "preference": " (preference)", "assumption": " (ASSUMPTION, please confirm)",
             "plan": " (temporary plan)", "historical": " (historical)"}
    lines = [f"• {m['content']}{label[m['kind']]}" for m in items]
    return "Here's what I know about you:\n" + "\n".join(lines) + \
        "\n\nYou can correct or delete any of this in the Memory tab."
