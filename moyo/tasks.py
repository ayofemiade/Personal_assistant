"""Tasks: CRUD, recurrence, overdue/upcoming views."""
from __future__ import annotations

from datetime import date, timedelta

from moyo.db import now_iso, rows, today

CATEGORIES = ("revenue", "client", "sales", "content", "study", "personal", "other")
DAYS = ["MO", "TU", "WE", "TH", "FR", "SA", "SU"]


class TaskError(ValueError):
    pass


def get(con, task_id: int) -> dict:
    r = con.execute("SELECT t.*, p.name project FROM tasks t LEFT JOIN projects p ON p.id=t.project_id "
                    "WHERE t.id=?", (task_id,)).fetchone()
    if not r:
        raise TaskError(f"Task #{task_id} not found.")
    return dict(r)


def project_id(con, name: str | None) -> int | None:
    if not name:
        return None
    r = con.execute("SELECT id FROM projects WHERE lower(name) LIKE lower(?)", (f"%{name}%",)).fetchone()
    return r["id"] if r else None


def guess_category(title: str) -> str:
    t = title.lower()
    if any(w in t for w in ("invoice", "payment", "pay ", "close deal", "contract", "upsell", "owes", "chase",
                            "collect", "₦", "$")):
        return "revenue"
    if any(w in t for w in ("follow up", "follow-up", "proposal", "lead", "prospect", "pitch", "outreach",
                            "contact", "call ", "dm ", "cold email", "sales", "referral")):
        return "sales"
    if any(w in t for w in ("client", "deliver", "deploy", "fix ", "bug", "website for", "build ", "deadline")):
        return "client"
    if any(w in t for w in ("tiktok", "instagram", "reel", "linkedin", "post", "video", "content", "record", "edit")):
        return "content"
    if any(w in t for w in ("study", "exam", "lecture", "assignment", "course", "read chapter", "learn")):
        return "study"
    if any(w in t for w in ("gym", "read ", "book", "rest", "family", "doctor")):
        return "personal"
    return "other"


def add(con, title: str, due_date: str | None = None, due_time: str | None = None, category: str | None = None,
        priority: int = 3, estimate_min: int = 45, project: str | None = None, description: str | None = None,
        recurrence: str | None = None, lead_id: int | None = None, depends_on: int | None = None,
        notes: str | None = None) -> dict:
    title = title.strip().rstrip(".")
    if not title:
        raise TaskError("Task title is empty.")
    if not category or category == "other":
        category = guess_category(title)
    if category not in CATEGORIES:
        raise TaskError(f"Unknown category {category}.")
    if recurrence:
        validate_recurrence(recurrence)
    cur = con.execute(
        "INSERT INTO tasks(title, description, project_id, category, priority, due_date, due_time, estimate_min, "
        "notes, depends_on, recurrence, lead_id, created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (title, description, project_id(con, project), category, priority, due_date, due_time, estimate_min,
         notes, depends_on, recurrence, lead_id, now_iso()))
    return get(con, cur.lastrowid)


def update(con, task_id: int, **fields) -> dict:
    allowed = {"title", "description", "category", "priority", "due_date", "due_time", "estimate_min",
               "status", "notes", "depends_on", "recurrence"}
    fields = {k: v for k, v in fields.items() if k in allowed}
    if "recurrence" in fields and fields["recurrence"]:
        validate_recurrence(fields["recurrence"])
    get(con, task_id)
    if fields:
        con.execute(f"UPDATE tasks SET {', '.join(f'{k}=?' for k in fields)} WHERE id=?", (*fields.values(), task_id))
    return get(con, task_id)


def validate_recurrence(rule: str) -> None:
    if rule == "daily" or rule == "weekdays":
        return
    if rule.startswith("weekly:") and all(d in DAYS for d in rule[7:].split(",")):
        return
    raise TaskError("Recurrence must be 'daily', 'weekdays' or 'weekly:MO,WE,FR'.")


def next_occurrence(rule: str, after: date) -> date:
    d = after + timedelta(days=1)
    for _ in range(14):
        wd = DAYS[d.weekday()]
        if rule == "daily" or (rule == "weekdays" and d.weekday() < 5) or (
                rule.startswith("weekly:") and wd in rule[7:].split(",")):
            return d
        d += timedelta(days=1)
    return d


def complete(con, task_id: int) -> dict:
    t = get(con, task_id)
    if t["status"] == "done":
        return {"task": t, "next": None}
    con.execute("UPDATE tasks SET status='done', completed_at=? WHERE id=?", (now_iso(), task_id))
    nxt = None
    if t["recurrence"]:
        base = date.fromisoformat(t["due_date"]) if t["due_date"] else today()
        nd = next_occurrence(t["recurrence"], max(base, today() - timedelta(days=1)))
        nxt = add(con, t["title"], due_date=nd.isoformat(), due_time=t["due_time"], category=t["category"],
                  priority=t["priority"], estimate_min=t["estimate_min"], description=t["description"],
                  recurrence=t["recurrence"], lead_id=t["lead_id"])
        con.execute("UPDATE tasks SET project_id=? WHERE id=?", (t["project_id"], nxt["id"]))
    return {"task": get(con, task_id), "next": nxt}


def find(con, text: str) -> list[dict]:
    """Open tasks whose title best matches `text` (simple word overlap)."""
    words = {w for w in text.lower().split() if len(w) > 2 and w not in {"the", "that", "task", "and", "for", "with"}}
    open_tasks = rows(con.execute("SELECT * FROM tasks WHERE status IN ('todo','doing')"))
    scored = []
    for t in open_tasks:
        tw = set(t["title"].lower().split())
        s = len(words & tw) + (3 if text.lower().strip() in t["title"].lower() else 0)
        if s:
            scored.append((s, t))
    scored.sort(key=lambda x: (-x[0], x[1]["id"]))
    return [t for _, t in scored]


def listing(con, status: str = "open") -> list[dict]:
    where = "t.status IN ('todo','doing')" if status == "open" else "t.status=?"
    args = () if status == "open" else (status,)
    return rows(con.execute(
        f"SELECT t.*, p.name project FROM tasks t LEFT JOIN projects p ON p.id=t.project_id WHERE {where} "
        "ORDER BY CASE WHEN t.due_date IS NULL THEN 1 ELSE 0 END, t.due_date, t.priority, t.id", args))


def overview(con, ref: date | None = None) -> dict:
    ref = ref or today()
    open_t = listing(con)
    iso = ref.isoformat()
    week = (ref + timedelta(days=7)).isoformat()
    done_today = con.execute("SELECT COUNT(*) FROM tasks WHERE status='done' AND substr(completed_at,1,10)=?",
                             (iso,)).fetchone()[0]
    return {
        "overdue": [t for t in open_t if t["due_date"] and t["due_date"] < iso],
        "today": [t for t in open_t if t["due_date"] == iso],
        "upcoming": [t for t in open_t if t["due_date"] and iso < t["due_date"] <= week],
        "no_date": [t for t in open_t if not t["due_date"]],
        "done_today": done_today,
    }
