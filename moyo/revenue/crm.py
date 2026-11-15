"""Companies, contacts, channels (duplicate-proof), deals, stages and the activity timeline.

Rules: one person = one record (phones normalised to E.164, emails lower-cased; UNIQUE per channel).
A clash is never merged silently: it raises DuplicateError with the existing record, so the UI/voice can
offer "use existing" or "merge". Every write records provenance (source, confirmed)."""
from __future__ import annotations

import json
import re
from datetime import date

from moyo.db import now_iso, rows, today


class CRMError(ValueError):
    pass


class DuplicateError(CRMError):
    def __init__(self, msg, existing: dict):
        super().__init__(msg)
        self.existing = existing


# ---------------------------------------------------------------- money helpers (integer minor units)
def to_minor(amount) -> int | None:
    if amount is None or amount == "":
        return None
    return int(round(float(amount) * 100))


def from_minor(v: int | None) -> float | None:
    return None if v is None else v / 100


# ---------------------------------------------------------------- normalisation
def norm_phone(raw: str, default_cc: str = "234") -> str | None:
    """'0803 123 4567' / '+234 803…' / '234803…' / '(0)803…' → '+2348031234567'."""
    if not raw:
        return None
    s = raw.strip()
    plus = s.startswith("+") or s.startswith("00")
    d = re.sub(r"\D", "", s)
    if s.startswith("00"):
        d = d[2:]
    if not d:
        return None
    if plus:
        out = d
    elif d.startswith(default_cc) and len(d) >= 12:
        out = d
    elif d.startswith("0") and len(d) == 11:  # Nigerian local format
        out = default_cc + d[1:]
    elif len(d) == 10 and d[0] in "789":    # 803… without the leading 0
        out = default_cc + d
    else:
        out = d
    if not 8 <= len(out) <= 15:
        raise CRMError(f"\"{raw}\" doesn't look like a phone number.")
    return "+" + out


def norm_email(raw: str) -> str | None:
    if not raw:
        return None
    e = raw.strip().lower()
    if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[a-z]{2,}", e):
        raise CRMError(f"\"{raw}\" doesn't look like an email address.")
    return e


def norm_name(name: str) -> str:
    n = re.sub(r"[^\w\s]", " ", (name or "").lower())
    n = re.sub(r"\b(ltd|limited|plc|inc|llc|nigeria|ng|co|company|enterprises?|ventures?|the)\b", " ", n)
    return re.sub(r"\s+", " ", n).strip()


def channel_norm(kind: str, value: str) -> str:
    if kind in ("phone", "whatsapp"):
        return norm_phone(value)
    if kind == "email":
        return norm_email(value)
    return value.strip().lower().lstrip("@")


# ---------------------------------------------------------------- companies & contacts
def find_company(con, name: str) -> dict | None:
    n = norm_name(name)
    if not n:
        return None
    r = con.execute("SELECT * FROM companies WHERE name_norm=? AND archived_at IS NULL", (n,)).fetchone()
    return dict(r) if r else None


def get_or_create_company(con, name: str, source="user", confirmed=1, **fields) -> dict:
    name = (name or "").strip()
    if not name:
        raise CRMError("A company needs a name.")
    ex = find_company(con, name)
    if ex:
        return ex
    t = now_iso()
    cur = con.execute("INSERT INTO companies(name, name_norm, industry, location, website, notes, source, confirmed, "
                      "created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
                      (name, norm_name(name), fields.get("industry"), fields.get("location"), fields.get("website"),
                       fields.get("notes"), source, int(confirmed), t, t))
    return dict(con.execute("SELECT * FROM companies WHERE id=?", (cur.lastrowid,)).fetchone())


def find_contact_by_channel(con, kind: str, value: str) -> dict | None:
    kinds = ("phone", "whatsapp") if kind in ("phone", "whatsapp") else (kind,)
    v = channel_norm(kind, value)
    r = con.execute(f"SELECT c.* FROM contact_channels ch JOIN contacts c ON c.id=ch.contact_id WHERE ch.value_norm=? "
                    f"AND ch.kind IN ({','.join('?' * len(kinds))}) AND c.archived_at IS NULL", (v, *kinds)).fetchone()
    return dict(r) if r else None


def find_contacts_by_name(con, name: str) -> list[dict]:
    return rows(con.execute("SELECT c.*, co.name AS company FROM contacts c LEFT JOIN companies co ON co.id=c.company_id "
                            "WHERE lower(c.full_name)=lower(?) AND c.archived_at IS NULL", (name.strip(),)))


def add_channel(con, contact_id: int, kind: str, value: str, primary: bool = False) -> None:
    v = channel_norm(kind, value)
    ex = find_contact_by_channel(con, kind, value)
    if ex and ex["id"] != contact_id:
        raise DuplicateError(f"{value} already belongs to {ex['full_name']}.", ex)
    con.execute("INSERT OR IGNORE INTO contact_channels(contact_id, kind, value, value_norm, is_primary) VALUES (?,?,?,?,?)",
                (contact_id, kind, value.strip(), v, int(primary)))


def create_contact(con, full_name: str, company_id: int | None = None, phone: str | None = None,
                   email: str | None = None, whatsapp: str | None = None, role: str | None = None,
                   source="user", confirmed=1, notes: str | None = None) -> dict:
    full_name = (full_name or "").strip()
    if not full_name:
        raise CRMError("A contact needs a name.")
    chans = [(k, v) for k, v in (("phone", phone), ("whatsapp", whatsapp), ("email", email)) if v]
    for k, v in chans:  # duplicate check BEFORE writing anything
        ex = find_contact_by_channel(con, k, v)
        if ex:
            raise DuplicateError(f"{v} already belongs to {ex['full_name']}. Use that contact or merge them.", ex)
    t = now_iso()
    cur = con.execute("INSERT INTO contacts(company_id, full_name, role, notes, source, confirmed, created_at, updated_at) "
                      "VALUES (?,?,?,?,?,?,?,?)", (company_id, full_name, role, notes, source, int(confirmed), t, t))
    cid = cur.lastrowid
    for i, (k, v) in enumerate(chans):
        add_channel(con, cid, k, v, primary=(i == 0))
    return get_contact(con, cid)


def get_contact(con, cid: int) -> dict:
    r = con.execute("SELECT c.*, co.name AS company FROM contacts c LEFT JOIN companies co ON co.id=c.company_id "
                    "WHERE c.id=?", (cid,)).fetchone()
    if not r:
        raise CRMError("Contact not found.")
    d = dict(r)
    d["channels"] = rows(con.execute("SELECT kind, value, value_norm, is_primary FROM contact_channels WHERE contact_id=? "
                                     "ORDER BY is_primary DESC, id", (cid,)))
    return d


def primary_channel(con, contact_id: int | None, kinds=("whatsapp", "phone")) -> str | None:
    if not contact_id:
        return None
    r = con.execute(f"SELECT value_norm FROM contact_channels WHERE contact_id=? AND kind IN ({','.join('?' * len(kinds))}) "
                    "ORDER BY kind='whatsapp' DESC, is_primary DESC, id LIMIT 1", (contact_id, *kinds)).fetchone()
    return r["value_norm"] if r else None


def merge_contacts(con, keep_id: int, merge_id: int, actor="user") -> dict:
    """Moves channels, deals, activities and follow-ups from `merge_id` to `keep_id`; archives `merge_id`.
    A snapshot goes to merge_log so it can be reviewed/undone by hand."""
    if keep_id == merge_id:
        raise CRMError("That's the same contact.")
    keep, gone = get_contact(con, keep_id), get_contact(con, merge_id)
    snap = {"merged": gone, "deals": [r["id"] for r in rows(con.execute(
        "SELECT id FROM deals WHERE primary_contact_id=?", (merge_id,)))]}
    for ch in gone["channels"]:
        con.execute("DELETE FROM contact_channels WHERE contact_id=? AND value_norm=? AND kind=?",
                    (merge_id, ch["value_norm"], ch["kind"]))
        con.execute("INSERT OR IGNORE INTO contact_channels(contact_id, kind, value, value_norm) VALUES (?,?,?,?)",
                    (keep_id, ch["kind"], ch["value"], ch["value_norm"]))
    for tbl, col in (("deals", "primary_contact_id"), ("activities", "contact_id"), ("follow_ups", "contact_id"),
                     ("conversations", "contact_id")):
        con.execute(f"UPDATE {tbl} SET {col}=? WHERE {col}=?", (keep_id, merge_id))
    con.execute("UPDATE OR IGNORE deal_contacts SET contact_id=? WHERE contact_id=?", (keep_id, merge_id))
    if not keep["company_id"] and gone["company_id"]:
        con.execute("UPDATE contacts SET company_id=? WHERE id=?", (gone["company_id"], keep_id))
    con.execute("UPDATE contacts SET archived_at=? WHERE id=?", (now_iso(), merge_id))
    con.execute("INSERT INTO merge_log(kept_contact_id, merged_contact_id, snapshot, at) VALUES (?,?,?,?)",
                (keep_id, merge_id, json.dumps(snap, default=str), now_iso()))
    log_activity(con, "note", f"Merged {gone['full_name']} into this contact", contact_id=keep_id, source=actor)
    return get_contact(con, keep_id)


# ---------------------------------------------------------------- stages & deals
def stages(con) -> list[dict]:
    return rows(con.execute("SELECT * FROM pipeline_stages ORDER BY position"))


def stage(con, key: str) -> dict:
    r = con.execute("SELECT * FROM pipeline_stages WHERE key=?", (key,)).fetchone()
    if not r:
        raise CRMError(f"Unknown stage \"{key}\". Stages: " + ", ".join(s["key"] for s in stages(con)))
    return dict(r)


STAGE_ALIASES = {"qualified": "engaged", "lead": "new", "proposal sent": "proposal", "negotiating": "negotiation",
                 "closed": "won", "done": "won", "dead": "lost"}


def stage_key(raw: str | None) -> str:
    k = (raw or "new").strip().lower()
    return STAGE_ALIASES.get(k, k)


def create_deal(con, title: str, company_id: int | None = None, contact_id: int | None = None, value=None,
                currency: str = "NGN", stage_k: str = "new", service: str | None = None, source: str = "other",
                source_detail: str | None = None, next_action: str | None = None, next_action_due: str | None = None,
                expected_close: str | None = None, notes: str | None = None, actor: str = "user",
                historical: bool = False, created_at: str | None = None) -> dict:
    if not (title or "").strip():
        raise CRMError("A deal needs a title, e.g. \"Kemi Stores website\".")
    sk = stage_key(stage_k)
    st = stage(con, sk)
    svc = None
    if service:
        r = con.execute("SELECT id FROM services WHERE key=? OR lower(label)=lower(?)", (service, service)).fetchone()
        svc = r["id"] if r else None
    t = created_at or now_iso()
    cur = con.execute(
        "INSERT INTO deals(company_id, primary_contact_id, title, service_id, value_minor, currency, stage_key, source, "
        "source_detail, expected_close, next_action, next_action_due, notes, historical, won_at, lost_at, created_at, updated_at) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (company_id, contact_id, title.strip(), svc, to_minor(value), (currency or "NGN").upper(), sk, source,
         source_detail, expected_close, next_action, next_action_due, notes, int(historical),
         t if st["is_won"] else None, t if st["is_lost"] else None, t, t))
    did = cur.lastrowid
    if contact_id:
        con.execute("INSERT OR IGNORE INTO deal_contacts(deal_id, contact_id, role) VALUES (?,?, 'primary')", (did, contact_id))
    con.execute("INSERT INTO stage_history(deal_id, from_stage, to_stage, at, actor) VALUES (?,?,?,?,?)",
                (did, None, sk, t, actor))
    log_activity(con, "created", f"Deal created: {title.strip()}", deal_id=did, contact_id=contact_id,
                 company_id=company_id, source=actor, occurred_at=t)
    return get_deal(con, did)


def get_deal(con, did: int) -> dict:
    r = con.execute(
        "SELECT d.*, co.name AS company, c.full_name AS contact, s.label AS stage_label, s.is_open, "
        "s.default_probability, s.stale_after_days, sv.label AS service "
        "FROM deals d LEFT JOIN companies co ON co.id=d.company_id LEFT JOIN contacts c ON c.id=d.primary_contact_id "
        "JOIN pipeline_stages s ON s.key=d.stage_key LEFT JOIN services sv ON sv.id=d.service_id WHERE d.id=?",
        (did,)).fetchone()
    if not r:
        raise CRMError("Deal not found.")
    d = dict(r)
    d["value"] = from_minor(d["value_minor"])
    d["probability_est"] = d["probability"] if d["probability"] is not None else d["default_probability"]
    d["name"] = d["company"] or d["contact"] or d["title"]
    last = con.execute("SELECT MAX(occurred_at) AS t FROM activities WHERE deal_id=? AND kind NOT IN ('created')",
                       (did,)).fetchone()["t"]
    d["last_touch"] = last
    return d


def list_deals(con, open_only: bool = False, include_historical: bool = False) -> list[dict]:
    q = "SELECT d.id FROM deals d JOIN pipeline_stages s ON s.key=d.stage_key WHERE d.archived_at IS NULL"
    if open_only:
        q += " AND s.is_open=1"
    if not include_historical:
        q += " AND d.historical=0"
    return [get_deal(con, r["id"]) for r in con.execute(q + " ORDER BY s.position, d.next_action_due IS NULL, d.next_action_due")]


def find_deal(con, name: str) -> dict | None:
    """Best open/recent deal matching a company, contact or title."""
    n = (name or "").strip()
    if not n:
        return None
    like = f"%{n}%"
    r = con.execute(
        "SELECT d.id FROM deals d LEFT JOIN companies co ON co.id=d.company_id LEFT JOIN contacts c ON c.id=d.primary_contact_id "
        "JOIN pipeline_stages s ON s.key=d.stage_key WHERE d.archived_at IS NULL AND d.historical=0 AND "
        "(lower(co.name)=lower(?) OR lower(c.full_name)=lower(?) OR lower(d.title)=lower(?) OR co.name_norm=? "
        " OR co.name LIKE ? OR c.full_name LIKE ? OR d.title LIKE ?) "
        "ORDER BY s.is_open DESC, d.updated_at DESC LIMIT 1", (n, n, n, norm_name(n), like, like, like)).fetchone()
    return get_deal(con, r["id"]) if r else None


DEAL_FIELDS = {"title", "value", "currency", "probability", "next_action", "next_action_due", "expected_close",
               "notes", "lost_reason", "source", "source_detail"}


def update_deal(con, did: int, actor: str = "user", **fields) -> dict:
    d = get_deal(con, did)
    if "stage" in fields or "stage_key" in fields:
        move_stage(con, did, fields.pop("stage", None) or fields.pop("stage_key"), actor=actor,
                   lost_reason=fields.get("lost_reason"))
    upd = {k: v for k, v in fields.items() if k in DEAL_FIELDS}
    if "value" in upd:
        upd["value_minor"] = to_minor(upd.pop("value"))
    if "probability" in upd and upd["probability"] is not None:
        upd["probability_source"] = "user"
    for k in ("next_action_due", "expected_close"):
        if upd.get(k):
            date.fromisoformat(upd[k])
    if upd:
        sets = ", ".join(f"{k}=?" for k in upd)
        con.execute(f"UPDATE deals SET {sets}, updated_at=? WHERE id=?", (*upd.values(), now_iso(), did))
        if "next_action_due" in upd or "next_action" in upd:
            sync_deal_followup(con, did)
    return get_deal(con, d["id"])


def move_stage(con, did: int, new_stage: str, actor: str = "user", lost_reason: str | None = None) -> dict:
    d = get_deal(con, did)
    sk = stage_key(new_stage)
    st = stage(con, sk)
    if sk == d["stage_key"]:
        return d
    if st["is_lost"] and not (lost_reason or d.get("lost_reason")):
        lost_reason = "not recorded"
    t = now_iso()
    con.execute("UPDATE deals SET stage_key=?, updated_at=?, won_at=CASE WHEN ? THEN ? ELSE won_at END, "
                "lost_at=CASE WHEN ? THEN ? ELSE lost_at END, lost_reason=COALESCE(?, lost_reason), "
                "probability=NULL, probability_source='stage' WHERE id=?",
                (sk, t, st["is_won"], t, st["is_lost"], t, lost_reason, did))
    con.execute("INSERT INTO stage_history(deal_id, from_stage, to_stage, at, actor) VALUES (?,?,?,?,?)",
                (did, d["stage_key"], sk, t, actor))
    log_activity(con, "stage_change", f"{d['stage_label']} → {st['label']}" + (f" ({lost_reason})" if st["is_lost"] else ""),
                 deal_id=did, contact_id=d["primary_contact_id"], company_id=d["company_id"], source=actor)
    if not st["is_open"]:  # closed deals need no follow-up
        con.execute("UPDATE follow_ups SET status='done', updated_at=? WHERE deal_id=? AND status IN ('open','snoozed')",
                    (t, did))
    return get_deal(con, did)


# ---------------------------------------------------------------- activities & follow-ups
def log_activity(con, kind: str, summary: str, contact_id=None, company_id=None, deal_id=None, channel=None,
                 direction=None, occurred_at: str | None = None, source: str = "user", confirmed: int = 1,
                 external_id: str | None = None) -> int | None:
    if deal_id and not (contact_id and company_id):
        r = con.execute("SELECT primary_contact_id, company_id FROM deals WHERE id=?", (deal_id,)).fetchone()
        if r:
            contact_id = contact_id or r["primary_contact_id"]
            company_id = company_id or r["company_id"]
    if contact_id and not company_id:
        r = con.execute("SELECT company_id FROM contacts WHERE id=?", (contact_id,)).fetchone()
        company_id = r["company_id"] if r else None
    t = now_iso()
    cur = con.execute("INSERT OR IGNORE INTO activities(kind, channel, contact_id, company_id, deal_id, occurred_at, summary, "
                      "direction, source, confirmed, external_id, created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                      (kind, channel, contact_id, company_id, deal_id, occurred_at or t, summary[:2000], direction,
                       source, confirmed, external_id, t))
    if deal_id and kind not in ("created",):
        con.execute("UPDATE deals SET updated_at=? WHERE id=?", (t, deal_id))
    return cur.lastrowid or None


def timeline(con, contact_id=None, deal_id=None, company_id=None, limit: int = 100) -> list[dict]:
    conds, args = [], []
    for col, v in (("contact_id", contact_id), ("deal_id", deal_id), ("company_id", company_id)):
        if v:
            conds.append(f"{col}=?")
            args.append(v)
    if not conds:
        return []
    return rows(con.execute(f"SELECT * FROM activities WHERE {' OR '.join(conds)} ORDER BY occurred_at DESC, id DESC LIMIT ?",
                            (*args, limit)))


def sync_deal_followup(con, did: int) -> None:
    """The deal's next action is its single open user follow-up."""
    d = get_deal(con, did)
    t = now_iso()
    con.execute("UPDATE follow_ups SET status='done', updated_at=? WHERE deal_id=? AND status IN ('open','snoozed') "
                "AND created_by='deal'", (t, did))
    if d["next_action_due"] and d["is_open"]:
        con.execute("INSERT INTO follow_ups(deal_id, contact_id, due_date, reason, created_by, created_at, updated_at) "
                    "VALUES (?,?,?,?, 'deal', ?, ?)", (did, d["primary_contact_id"], d["next_action_due"],
                                                       d["next_action"] or "Follow up", t, t))


def days_since(iso: str | None, ref: date | None = None) -> int | None:
    if not iso:
        return None
    return ((ref or today()) - date.fromisoformat(iso[:10])).days
