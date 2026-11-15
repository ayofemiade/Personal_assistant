"""SQLite storage: the single source of truth for Moyo. Nothing here is invented;
every number Moyo reports comes from these tables."""
from __future__ import annotations

import json
import os
import sqlite3
from datetime import date, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = Path(os.environ.get("MOYO_DATA_DIR", ROOT / "data"))

SCHEMA = """
CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS memory (
    id INTEGER PRIMARY KEY,
    category TEXT NOT NULL,
    kind TEXT NOT NULL CHECK (kind IN ('fact','preference','assumption','plan','historical')),
    content TEXT NOT NULL,
    source TEXT NOT NULL DEFAULT 'user',
    valid_until TEXT,
    confirmed INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS projects (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    category TEXT NOT NULL,
    description TEXT,
    active INTEGER NOT NULL DEFAULT 1
);
CREATE TABLE IF NOT EXISTS tasks (
    id INTEGER PRIMARY KEY,
    title TEXT NOT NULL,
    description TEXT,
    project_id INTEGER REFERENCES projects(id),
    category TEXT NOT NULL DEFAULT 'other'
        CHECK (category IN ('revenue','client','sales','content','study','personal','other')),
    priority INTEGER NOT NULL DEFAULT 3 CHECK (priority BETWEEN 1 AND 4),
    due_date TEXT,
    due_time TEXT,
    estimate_min INTEGER NOT NULL DEFAULT 45,
    status TEXT NOT NULL DEFAULT 'todo' CHECK (status IN ('todo','doing','done','cancelled')),
    notes TEXT,
    depends_on INTEGER REFERENCES tasks(id),
    recurrence TEXT,
    lead_id INTEGER REFERENCES leads(id),
    created_at TEXT NOT NULL,
    completed_at TEXT
);
CREATE TABLE IF NOT EXISTS leads (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    contact TEXT,
    service TEXT,
    stage TEXT NOT NULL DEFAULT 'new'
        CHECK (stage IN ('new','qualified','proposal','negotiation','won','lost')),
    value REAL,
    currency TEXT NOT NULL DEFAULT 'USD',
    usd_rate REAL,
    probability REAL,
    next_followup TEXT,
    notes TEXT,
    source TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS earnings (
    id INTEGER PRIMARY KEY,
    earned_date TEXT NOT NULL,
    amount REAL NOT NULL CHECK (amount > 0),
    currency TEXT NOT NULL,
    usd_rate REAL NOT NULL CHECK (usd_rate > 0),
    usd_amount REAL NOT NULL,
    client TEXT,
    lead_id INTEGER REFERENCES leads(id),
    service TEXT,
    description TEXT,
    payment_status TEXT NOT NULL DEFAULT 'unpaid' CHECK (payment_status IN ('unpaid','paid')),
    paid_date TEXT,
    counts_toward_challenge INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS content_log (
    id INTEGER PRIMARY KEY,
    date TEXT NOT NULL,
    platform TEXT NOT NULL CHECK (platform IN ('tiktok','instagram','linkedin','x')),
    title TEXT,
    hook TEXT,
    pillar TEXT,
    url TEXT,
    views INTEGER,
    likes INTEGER,
    comments INTEGER,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS reviews (
    date TEXT PRIMARY KEY,
    completed TEXT,
    not_completed TEXT,
    value_created TEXT,
    distractions TEXT,
    carry_over TEXT,
    notes TEXT,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS audit_log (
    id INTEGER PRIMARY KEY,
    ts TEXT NOT NULL,
    actor TEXT NOT NULL,
    action TEXT NOT NULL,
    tier TEXT NOT NULL,
    detail TEXT,
    result TEXT
);
-- Gmail: metadata only (sender, subject, date, labels). Bodies are fetched on demand and never stored.
CREATE TABLE IF NOT EXISTS emails (
    id TEXT PRIMARY KEY,
    thread_id TEXT,
    received_at TEXT NOT NULL,
    from_name TEXT,
    from_email TEXT,
    subject TEXT,
    unread INTEGER NOT NULL DEFAULT 0,
    labels TEXT,
    kind TEXT NOT NULL DEFAULT 'other',
    lead_id INTEGER,
    synced_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS events (
    id TEXT PRIMARY KEY,
    calendar TEXT,
    start TEXT NOT NULL,
    end TEXT NOT NULL,
    all_day INTEGER NOT NULL DEFAULT 0,
    title TEXT,
    location TEXT,
    synced_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS notifications (
    id INTEGER PRIMARY KEY,
    key TEXT NOT NULL UNIQUE,          -- dedupe: one reminder per key (e.g. "content:2026-11-13:tiktok")
    level TEXT NOT NULL CHECK (level IN ('urgent','important','info')),
    title TEXT NOT NULL,
    body TEXT,
    view TEXT,                         -- page to open when clicked
    created_at TEXT NOT NULL,
    toasted INTEGER NOT NULL DEFAULT 0,
    read_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_notif_created ON notifications(created_at);
CREATE INDEX IF NOT EXISTS idx_emails_date ON emails(received_at);
CREATE INDEX IF NOT EXISTS idx_events_start ON events(start);
CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status, due_date);
CREATE INDEX IF NOT EXISTS idx_earn_date ON earnings(earned_date);
CREATE INDEX IF NOT EXISTS idx_content_date ON content_log(date, platform);
"""

DEFAULT_SETTINGS = {
    "challenge": {
        "target_usd": 10000,
        "start": "2026-11-08",
        "end": "2027-02-08",
        "basis": "collected",  # D41: money counts when it is paid
        "exclusions": ["personal income", "refunds"],
    },
    # NGN per 1 USD. Deliberately empty: Moyo never guesses an exchange rate.
    "ngn_per_usd": None,
    "schedule": {
        "confirmed": False,  # these times are assumptions until Moyosore confirms them
        "wake": "07:00",
        "day_start": "08:00",
        "day_end": "22:30",
        "fixed": [
            {"title": "Startup meeting (work)", "start": "09:00", "end": "10:00", "days": "MO,TU,WE,TH,FR"},
            {"title": "Lunch", "start": "13:00", "end": "13:45", "days": "*"},
            {"title": "Gym", "start": "18:00", "end": "19:30", "days": "MO,TU,WE,TH,FR,SA"},
            {"title": "Dinner", "start": "19:45", "end": "20:15", "days": "*"},
        ],
        "focus_block_min": 90,
        "break_min": 15,
        "buffer_pct": 15,
    },
    "content_commitments": {"tiktok": "daily", "instagram": "daily", "linkedin_per_week": 3},
    # Proactive reminders (B). Desktop toasts only for these levels; info stays in Moyo's notification list.
    "notifications": {"enabled": True, "toasts": True, "toast_levels": ["urgent", "important"],
                      "quiet_start": "22:30", "quiet_end": "07:00", "content_reminder_time": "19:00",
                      "event_lead_minutes": 15, "review_minutes_before_end": 30},
    # Clap-to-wake: OFF until Moyosore turns it on. Mic is analysed in memory only; paused in quiet hours.
    # mode "clap_phrase" = clap, then say "let's get to work" (default: this mic dulls claps); "double_clap" = claps only.
    "clap": {"enabled": False, "mode": "clap_phrase", "calibrated": False, "params": {}, "listen_in_quiet_hours": False},
    # "Start my day" routine (A).
    "routine": {"workspace": "coding", "music": True, "read_briefing": True, "morning_prompt": True,
                "prompt_after": "07:00", "last_run": None},
    # Invoices (drafts only; Moyosore sends them). Bank details are filled in privately in the local database.
    "invoice_profile": {"business": "MOYOCODE", "address": "Abeokuta, Nigeria", "phone": "",
                        "email": "info@moyocode.com", "prefix": "MC-", "next_number": 1, "default_due_days": 30,
                        "default_deposit_pct": None, "bank": {"name": "", "account_name": "", "number": ""},
                        "save_dir": str(Path.home() / "Documents" / "Moyo" / "Invoices"),
                        "footer": "Thank you for trusting Moyocode to power your digital presence. Let’s build something impactful."},
    # Briefing voice: chosen in Settings → Voice. Falls back to other natural voices, then the basic browser voice.
    "voice": {"engine": "gemini", "voice": "Sulafat", "speed": 1.0, "fallback": True, "chosen": False,
              "chat_voice": "Sulafat"},  # two-way conversations (Gemini Live can only use its own voices)
    # Tried in order; free-tier daily caps differ a lot (gemini-3.5-flash is only ~20/day).
    "cloud": {"enabled": True, "redact_clients_and_amounts": True,
              "models": ["gemini-3.5-flash-lite", "gemini-3.1-flash-lite", "gemini-3.5-flash", "groq:openai/gpt-oss-120b"]},
}


def now_iso() -> str:
    return datetime.now().replace(microsecond=0).isoformat()


def today() -> date:
    override = os.environ.get("MOYO_TODAY")  # tests only
    return date.fromisoformat(override) if override else date.today()


def db_path() -> Path:
    return DATA_DIR / "moyo.db"


def connect(path: Path | None = None) -> sqlite3.Connection:
    p = path or db_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(p, check_same_thread=False, isolation_level=None)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON")
    con.execute("PRAGMA journal_mode = WAL")
    con.execute("PRAGMA busy_timeout = 10000")  # background syncs write from their own connection
    return con


def init(con: sqlite3.Connection) -> bool:
    """Create tables; seed on first run. Returns True if the DB was new."""
    new = con.execute("SELECT name FROM sqlite_master WHERE name='settings'").fetchone() is None
    con.executescript(SCHEMA)
    for k, v in DEFAULT_SETTINGS.items():
        con.execute("INSERT OR IGNORE INTO settings(key, value) VALUES (?, ?)", (k, json.dumps(v)))
        stored = get_setting(con, k)
        if isinstance(v, dict) and isinstance(stored, dict) and set(v) - set(stored):
            set_setting(con, k, {**v, **stored})  # add new default keys, keep the user's values
    # migrations for databases created by earlier versions
    cols = {r[1] for r in con.execute("PRAGMA table_info(content_log)")}
    for col, typ in (("external_id", "TEXT"), ("shares", "INTEGER"), ("metrics_updated_at", "TEXT"),
                     ("posted_at", "TEXT")):
        if col not in cols:
            con.execute(f"ALTER TABLE content_log ADD COLUMN {col} {typ}")
    con.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_content_ext ON content_log(platform, external_id) "
                "WHERE external_id IS NOT NULL")
    from moyo.revenue import schema as revenue_schema
    revenue_schema.ensure(con)
    if new:
        from moyo.seed import seed
        seed(con)
    return new


def get_setting(con, key):
    row = con.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
    return json.loads(row["value"]) if row else DEFAULT_SETTINGS.get(key)


def set_setting(con, key, value) -> None:
    con.execute("INSERT INTO settings(key, value) VALUES (?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value=excluded.value", (key, json.dumps(value)))


def rows(cur) -> list[dict]:
    return [dict(r) for r in cur.fetchall()]


def backup(con: sqlite3.Connection, keep: int = 14) -> Path | None:
    """One backup per day in data/backups, keeping the last `keep`."""
    bdir = DATA_DIR / "backups"
    bdir.mkdir(parents=True, exist_ok=True)
    target = bdir / f"moyo-{today().isoformat()}.db"
    if target.exists():
        return None
    dest = sqlite3.connect(target)
    with dest:
        con.backup(dest)
    dest.close()
    for old in sorted(bdir.glob("moyo-*.db"))[:-keep]:
        old.unlink()
    return target
